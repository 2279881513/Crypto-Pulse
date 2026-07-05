"""
CryptoPulse — OKX HTTP REST 客户端封装

用于：
- 获取历史 K 线初始化 Ring Buffer
- 盘口快照对齐
- 补充 WebSocket 不提供的历史数据

基于 python-okx SDK，但封装为我们的数据模型。
"""

from __future__ import annotations

from typing import Any, Optional

import okx.MarketData as MarketData
from loguru import logger

from cryptopulse.config import settings
from cryptopulse.core.data.models import KLine, OrderBook, OrderBookLevel

# 市场数据 REST 限频: 60 req / 2s
# 我们会做简单限速保护
_RATE_LIMIT_WINDOW = 2.0  # 秒
_MAX_REQUESTS = 55  # 留余量


class OKXRestClient:
    """OKX REST API 客户端"""

    def __init__(self) -> None:
        # 公开市场数据不需要 API Key，但 SDK 要求传值。
        # 用空字符串避免 None 导致 bytes(None, ...) 报错。
        empty_if_missing = lambda v: v if v else ""
        self._market_api = MarketData.MarketAPI(
            api_key=empty_if_missing(settings.okx_api_key),
            api_secret_key=empty_if_missing(settings.okx_secret_key),
            passphrase=empty_if_missing(settings.okx_passphrase),
            flag="1" if settings.okx_use_demo else "0",
            domain=settings.okx_rest_base,
            debug=False,
        )
        self._request_count = 0
        self._window_start = 0.0

    # ------------------------------------------------------------------
    # K 线数据
    # ------------------------------------------------------------------

    def get_candles(self, inst_id: str, bar: str,
                    limit: int = 300,
                    after: Optional[int] = None,
                    before: Optional[int] = None) -> list[KLine]:
        """
        获取 K 线数据（最新 300 根）。
        
        Args:
            inst_id: "BTC-USDT"
            bar: "1m" | "5m" | "4H" | "1D"
            limit: 最多 300（单次）
            after: 获取此 time 之前的数据（Unix 毫秒）
            before: 获取此 time 之后的数据
        """
        self._rate_limit()

        params = {"instId": inst_id, "bar": bar}
        if limit:
            params["limit"] = min(limit, 300)
        if after:
            params["after"] = str(after)
        if before:
            params["before"] = str(before)

        result = self._market_api.get_candlesticks(**params)
        return self._parse_candle_result(result)

    def get_history_candles(self, inst_id: str, bar: str,
                            limit: int = 1440,
                            after: Optional[int] = None,
                            before: Optional[int] = None) -> list[KLine]:
        """
        获取历史 K 线（每次最多 1440 根）。
        """
        self._rate_limit()

        params = {"instId": inst_id, "bar": bar}
        if limit:
            params["limit"] = min(limit, 1440)
        if after:
            params["after"] = str(after)
        if before:
            params["before"] = str(before)

        result = self._market_api.get_history_candlesticks(**params)
        return self._parse_candle_result(result)

    def _parse_candle_result(self, result: dict) -> list[KLine]:
        """解析 OKX candle 返回"""
        if result.get("code") != "0":
            logger.error(f"获取 K 线失败: {result}")
            return []

        data = result.get("data", [])
        # OKX 返回顺序：最新在前，我们反转使之从旧到新
        klines = [KLine.from_okx(item) for item in reversed(data)]
        return klines

    # ------------------------------------------------------------------
    # 盘口数据
    # ------------------------------------------------------------------

    def get_orderbook(self, inst_id: str, depth: int = 400) -> Optional[OrderBook]:
        """获取盘口快照"""
        self._rate_limit()

        result = self._market_api.get_orderbook(instId=inst_id, sz=str(depth))
        if result.get("code") != "0":
            logger.error(f"获取盘口失败: {result}")
            return None

        data = result.get("data", [{}])[0]
        return OrderBook.from_okx(data)

    # ------------------------------------------------------------------
    # 其他市场数据
    # ------------------------------------------------------------------

    def get_ticker(self, inst_id: str) -> Optional[dict[str, Any]]:
        """获取 Ticker"""
        self._rate_limit()
        result = self._market_api.get_ticker(instId=inst_id)
        if result.get("code") == "0" and result.get("data"):
            return result["data"][0]
        return None

    # ------------------------------------------------------------------
    # 批量下载（用于回测数据准备）
    # ------------------------------------------------------------------

    def download_full_history(self, inst_id: str, bar: str,
                              start_ts: int, end_ts: int) -> list[KLine]:
        """
        分批下载完整历史 K 线。
        start_ts/end_ts: Unix 毫秒时间戳
        """
        all_klines: list[KLine] = []
        cursor = end_ts  # 从最新往前取

        while cursor > start_ts:
            batch = self.get_history_candles(
                inst_id=inst_id, bar=bar,
                limit=1440, before=cursor,
            )
            if not batch:
                break

            all_klines.extend(batch)
            cursor = batch[0].timestamp
            logger.info(f"  下载中... {bar} {len(all_klines)} 根, 到 {cursor}")

            # 避免超过限频
            import time
            time.sleep(0.5)

        # 去重
        seen = set()
        unique = []
        for k in all_klines:
            if k.timestamp not in seen:
                seen.add(k.timestamp)
                unique.append(k)

        unique.sort(key=lambda x: x.timestamp)
        logger.info(f" 历史数据下载完成: {inst_id} {bar} {len(unique)} 根")
        return unique

    # ------------------------------------------------------------------
    # 限速保护
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """简单限速"""
        import time
        now = time.time()
        if now - self._window_start > _RATE_LIMIT_WINDOW:
            self._request_count = 0
            self._window_start = now

        self._request_count += 1
        if self._request_count >= _MAX_REQUESTS:
            sleep_time = _RATE_LIMIT_WINDOW - (now - self._window_start)
            if sleep_time > 0:
                logger.debug(f"限速保护: 等待 {sleep_time:.2f}s")
                time.sleep(sleep_time + 0.1)
            self._request_count = 0
            self._window_start = time.time()
