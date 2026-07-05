"""
CryptoPulse — WebSocket 管理器

基于 websocket-client（同步库）+ asyncio 线程桥接。
原生支持 HTTP 代理，无任何兼容性问题。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import websocket
from loguru import logger

# 禁用 websocket-client 的冗长日志
websocket.enableTrace(False)


class WSManager:
    """
    OKX Public WebSocket Manager

    内部使用 websocket-client（同步）在独立线程中运行，
    通过 asyncio.Queue 回传消息到主协程。
    """

    MAX_RETRY_DELAY = 60
    WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

    def __init__(self, proxy: str = "") -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[websocket.WebSocketApp] = None
        self._subscriptions: list[dict[str, Any]] = []
        self._callbacks: dict[str, list[Callable]] = {}
        self._msg_queue: asyncio.Queue = asyncio.Queue()
        self._reconnect_count = 0
        self._proxy = proxy or os.environ.get("HTTPS_PROXY", "") or os.environ.get("HTTP_PROXY", "")
        self._msg_buffer: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # 订阅管理
    # ------------------------------------------------------------------

    def subscribe(self, channel: str, param: dict[str, Any]) -> None:
        sub = {"channel": channel, **param}
        for existing in self._subscriptions:
            if existing == sub:
                return
        self._subscriptions.append(sub)
        logger.info(f" 订阅: {channel} {param}")

    def set_callback(self, channel: str, callback: Callable) -> None:
        self._callbacks.setdefault(channel, []).append(callback)

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """启动 WebSocket 连接（运行在后台线程）"""
        self._running = True
        ws_url = self.WS_URL

        def _run():
            """在线程中运行的 WebSocket 主循环"""
            while self._running:
                try:
                    ws = websocket.WebSocket()
                    ws_kwargs = {
                        "url": ws_url,
                        "timeout": 10,
                    }
                    if self._proxy:
                        parsed = urlparse(self._proxy)
                        ws_kwargs["http_proxy_host"] = parsed.hostname or "127.0.0.1"
                        ws_kwargs["http_proxy_port"] = parsed.port or 10808
                        logger.info(f"通过代理连接: {ws_kwargs['http_proxy_host']}:{ws_kwargs['http_proxy_port']}")

                    ws.connect(**ws_kwargs)
                    self._reconnect_count = 0
                    logger.info(" WebSocket 已连接")

                    # 发送订阅
                    if self._subscriptions:
                        ws.send(json.dumps({"op": "subscribe", "args": self._subscriptions}))

                    # 消息循环
                    ws.settimeout(30)
                    while self._running:
                        try:
                            message = ws.recv()
                            if message:
                                self._msg_queue.put_nowait(("message", message))
                        except websocket.WebSocketTimeoutException:
                            continue
                        except Exception:
                            break

                    ws.close()
                    logger.info(" WS 连接已关闭")

                except Exception as e:
                    logger.warning(f" WS 异常: {type(e).__name__}: {e}")

                if self._running:
                    self._reconnect_count += 1
                    delay = min(2 ** (self._reconnect_count - 1), self.MAX_RETRY_DELAY)
                    logger.info(f" 等待 {delay}s 后重连...")
                    import time
                    time.sleep(delay)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

        # 启动消息分发协程
        await self._dispatch_loop()

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        if self._ws:
            self._ws.close()
        logger.info(" WebSocket 已断开")

    # ------------------------------------------------------------------
    # WebSocket 回调（在线程中运行）
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        """连接建立"""
        self._reconnect_count = 0
        logger.info(" WebSocket 已连接")
        # 发送订阅
        if self._subscriptions:
            payload = json.dumps({"op": "subscribe", "args": self._subscriptions})
            ws.send(payload)
            logger.debug(f"订阅消息已发送")

    def _on_message(self, ws, message: str) -> None:
        """收到消息 — 通过队列传给异步处理器"""
        self._msg_queue.put_nowait(("message", message))

    def _on_error(self, ws, error) -> None:
        """连接错误"""
        logger.warning(f" WS 错误: {type(error).__name__}: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """连接关闭"""
        logger.info(f" WS 关闭 (code={close_status_code})")

    # ------------------------------------------------------------------
    # 异步消息分发
    # ------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """从队列中读取消息并分发给回调"""
        last_status = 0.0
        while self._running:
            try:
                msg_type, data = await asyncio.wait_for(
                    self._msg_queue.get(), timeout=5.0
                )
                if msg_type == "message":
                    await self._handle_message(data)
            except asyncio.TimeoutError:
                # 每 10 秒打印一次状态
                now = asyncio.get_event_loop().time()
                if now - last_status > 10:
                    logger.info(f"运行中... (等待 WS 数据)")
                    last_status = now
                continue
            except Exception as e:
                logger.error(f"消息分发异常: {e}")

    async def _handle_message(self, raw: str) -> None:
        """处理 WS 消息"""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        arg = msg.get("arg", {})
        channel = arg.get("channel", "")
        data = msg.get("data", [])

        if msg.get("event") == "error":
            logger.error(f"订阅错误: {msg}")
            return
        if not channel or not data:
            return

        # 缓存
        self._msg_buffer.setdefault(channel, [])
        self._msg_buffer[channel].append(msg)
        if len(self._msg_buffer[channel]) > 3:
            self._msg_buffer[channel].pop(0)

        # 分发
        if channel in self._callbacks:
            for cb in self._callbacks[channel]:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(data, arg)
                    else:
                        cb(data, arg)
                except Exception as e:
                    logger.error(f"回调错误 [{channel}]: {e}")

    def get_buffered(self, channel: str) -> list[dict]:
        return self._msg_buffer.get(channel, [])

    # ------------------------------------------------------------------
    # 快捷订阅
    # ------------------------------------------------------------------

    def subscribe_candles(self, inst_id: str, bar: str) -> None:
        self.subscribe("candles", {"instId": inst_id, "bar": bar, "channel": "candles"})

    def subscribe_ticker(self, inst_id: str) -> None:
        self.subscribe("tickers", {"instId": inst_id, "channel": "tickers"})

    def subscribe_orderbook(self, inst_id: str, depth: int = 400) -> None:
        self.subscribe("books", {"instId": inst_id, "sz": str(depth), "channel": "books"})

    def subscribe_trades(self, inst_id: str) -> None:
        self.subscribe("trades", {"instId": inst_id, "channel": "trades"})

    def subscribe_funding_rate(self, inst_id: str) -> None:
        self.subscribe("funding-rate", {"instId": inst_id, "channel": "funding-rate"})

    def subscribe_open_interest(self, inst_id: str) -> None:
        self.subscribe("open-interest", {"instId": inst_id, "channel": "open-interest"})

    def subscribe_mark_price(self, inst_id: str) -> None:
        self.subscribe("mark-price", {"instId": inst_id, "channel": "mark-price"})
