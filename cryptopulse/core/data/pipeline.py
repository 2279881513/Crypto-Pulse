"""
CryptoPulse — 数据管道编排器

将 WSManager、OKXRestClient、RingBufferManager 串联起来：
1. 初始化时通过 REST 拉取历史数据填充 Ring Buffer
2. 启动 WebSocket 连接获取实时更新
3. 将实时数据写入 Ring Buffer，同时推送到 Redis（可选）
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from loguru import logger

from cryptopulse.config import settings
from cryptopulse.config import TradingStyle
from cryptopulse.core.data.models import KLine
from cryptopulse.core.data.okx_client import OKXRestClient
from cryptopulse.core.data.ring_buffer import RingBufferManager
from cryptopulse.core.data.ws_manager import WSManager


class DataPipeline:
    """
    数据管道：管理实时数据流与历史数据缓存。

    Usage:
        pipeline = DataPipeline(symbol="BTC-USDT", style="short_term")
        await pipeline.initialize()   # REST 初始化 + WS 连接
        await pipeline.run()          # 保持运行
    """

    def __init__(self, symbol: str = "BTC-USDT",
                 style: str = "short_term") -> None:
        self.symbol = symbol
        self.style = style

        # 短线用 1m + 5m，中线用 4H + 1D
        if style == "short_term":
            self.intervals = ("1m", "5m")
        else:
            self.intervals = ("4H", "1D")

        # 核心组件
        self.rest = OKXRestClient()
        self.ws = WSManager(proxy=settings.proxy)
        self.buffers = RingBufferManager(
            short_intervals=self.intervals if style == "short_term" else (),
            medium_intervals=self.intervals if style == "medium_term" else (),
        )

        # 额外数据缓存
        self._latest_ticker: Optional[dict[str, Any]] = None
        self._orderbook: Optional[Any] = None
        self._funding_rates: list[dict] = []
        self._oi_history: list[dict] = []
        self._trades_window: list[dict] = []  # 最近的成交
        self._candle_poll_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        初始化数据管道：
        1. REST 拉取历史 K 线填充 Ring Buffer
        2. 设置 WebSocket 订阅
        3. 注册回调
        4. 启动 WS 连接（注意：run() 中启动）
        """
        logger.info(f" 初始化数据管道: {self.symbol} | {self.style}")

        # Step 1: 拉取历史数据
        await self._load_historical_data()

        # Step 2: 配置 WS 订阅
        self._setup_ws_subscriptions()

        # Step 3: 注册回调
        self._register_callbacks()

        logger.info(f" 数据管道初始化完成: {self.buffers}")

    async def run(self, stop_event: Optional[asyncio.Event] = None) -> None:
        """启动 WebSocket 主循环 + K 线轮询"""
        logger.info(" 启动 WebSocket 实时数据流...")

        # WS 任务
        ws_task = asyncio.create_task(self.ws.connect())

        # K 线轮询任务（candles WS 频道不可用，改用 REST 轮询）
        self._candle_poll_task = asyncio.create_task(self._poll_candles_loop())

        # 等待 WS 完成（或被取消）
        try:
            await ws_task
        finally:
            self._candle_poll_task.cancel()
            try:
                await self._candle_poll_task
            except asyncio.CancelledError:
                pass

    async def stop(self) -> None:
        """停止数据管道"""
        await self.ws.disconnect()
        logger.info("⏹ 数据管道已停止")

    # ------------------------------------------------------------------
    # 历史数据加载
    # ------------------------------------------------------------------

    async def _load_historical_data(self) -> None:
        """从 REST API 加载历史 K 线（失败时静默继续，WS 连接后会自动补充）"""
        logger.info(f"加载历史数据 ({self.intervals})...")

        for interval in self.intervals:
            buf = self.buffers.get(interval)
            needed = buf.capacity * 2

            try:
                klines = self.rest.get_history_candles(
                    inst_id=self.symbol,
                    bar=interval,
                    limit=min(needed, 1440),
                )
            except Exception as e:
                logger.warning(f"get_history_candles 失败 ({e})，尝试 get_candles ...")
                klines = []

            if not klines:
                try:
                    klines = self.rest.get_candles(
                        inst_id=self.symbol,
                        bar=interval,
                        limit=min(needed, 300),
                    )
                except Exception as e:
                    logger.warning(f"get_candles 也失败: {e}")
                    klines = []

            for k in klines:
                buf.push(k)
            logger.info(f"  {interval}: {buf.current_count} 根 K 线已加载")

    # ------------------------------------------------------------------
    # WebSocket 配置
    # ------------------------------------------------------------------

    async def _poll_candles_loop(self) -> None:
        """通过 REST API 轮询 K 线（WS candles 频道不可用）"""
        logger.info(f" K 线轮询启动 ({self.intervals})...")
        while True:
            try:
                for interval in self.intervals:
                    try:
                        klines = self.rest.get_candles(
                            inst_id=self.symbol,
                            bar=interval,
                            limit=2,  # 只取最新 2 根
                        )
                        for k in klines:
                            if k.confirm:
                                self.buffers.push_kline(interval, k)
                            else:
                                self.buffers.update_kline(interval, k)
                    except Exception as e:
                        logger.debug(f"K 线轮询失败 ({interval}): {e}")

                # 根据最短周期决定轮询间隔
                interval_seconds = {"1m": 60, "5m": 300, "4H": 14400, "1D": 86400}
                min_sec = min(interval_seconds.get(i, 60) for i in self.intervals)
                # 轮询成功后打印状态
                buf_1m = self.buffers.get('1m') if '1m' in self.buffers.buffers else None
                buf_5m = self.buffers.get('5m') if '5m' in self.buffers.buffers else None
                c1 = buf_1m.latest_close if buf_1m else 0
                c5 = buf_5m.latest_close if buf_5m else 0
                logger.info(f" K 线轮询 | 1m最新:{c1} 5m最新:{c5}")
                await asyncio.sleep(min_sec // 2)  # 半周期轮询

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"轮询循环异常: {e}")
                await asyncio.sleep(10)

    def _setup_ws_subscriptions(self) -> None:
        """按交易风格配置订阅（candles 用 REST 轮询替代）"""
        inst_id = self.symbol

        # WS 支持：tickers, trades, books
        self.ws.subscribe_ticker(inst_id)
        self.ws.subscribe_trades(inst_id)

        if self.style == "short_term":
            self.ws.subscribe_orderbook(inst_id, 400)
        else:
            self.ws.subscribe_orderbook(inst_id, 25)

        # 合约专属
        swap_id = inst_id + "-SWAP"
        self.ws.subscribe_funding_rate(swap_id)
        self.ws.subscribe_open_interest(swap_id)
        self.ws.subscribe_mark_price(swap_id)

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def _register_callbacks(self) -> None:
        """将 WS 数据分发到 Ring Buffer"""

        async def handle_ticker(data: list, arg: dict) -> None:
            if data:
                self._latest_ticker = data[0]
                ticker = data[0]
                logger.info(f" 实时: {ticker.get('instId','')} ${ticker.get('last','')}  (24h vol: {ticker.get('volCcy24h','')})")

        async def handle_trades(data: list, arg: dict) -> None:
            for t in data:
                self._trades_window.append({
                    "trade_id": t.get("tradeId", ""),
                    "ts": int(t.get("ts", "0")),
                    "price": float(t.get("px", "0")),
                    "size": float(t.get("sz", "0")),
                    "side": t.get("side", ""),
                })
            # 保留最近 1000 笔
            if len(self._trades_window) > 1000:
                self._trades_window = self._trades_window[-1000:]

        async def handle_orderbook(data: list, arg: dict) -> None:
            if data:
                self._orderbook = data[0]

        async def handle_funding(data: list, arg: dict) -> None:
            if data:
                self._funding_rates.extend(data)
                if len(self._funding_rates) > 100:
                    self._funding_rates = self._funding_rates[-100:]

        async def handle_oi(data: list, arg: dict) -> None:
            if data:
                self._oi_history.extend(data)
                if len(self._oi_history) > 100:
                    self._oi_history = self._oi_history[-100:]

        # 注册回调（candles 已改用 REST 轮询）
        self.ws.set_callback("tickers", handle_ticker)
        self.ws.set_callback("trades", handle_trades)
        self.ws.set_callback("books", handle_orderbook)
        self.ws.set_callback("funding-rate", handle_funding)
        self.ws.set_callback("open-interest", handle_oi)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """获取当前快照（供分析引擎使用）"""
        return {
            "symbol": self.symbol,
            "style": self.style,
            "klines": self.buffers.all_dataframes(),
            "ticker": self._latest_ticker,
            "trades_window": self._trades_window[-200:],
            "funding_rates": self._funding_rates[-30:],
            "oi_history": self._oi_history[-50:],
            "orderbook": self._orderbook,
        }
