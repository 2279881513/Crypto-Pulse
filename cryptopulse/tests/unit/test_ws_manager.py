"""
CryptoPulse — WS Manager 单元测试 (aiohttp 版)
"""

import pytest

from cryptopulse.core.data.ws_manager import WSManager


class TestWSManager:
    """WS Manager 基础功能测试（不连接真实 WS）"""

    def test_init(self):
        mgr = WSManager()
        assert mgr._subscriptions == []
        assert mgr._callbacks == {}

    def test_init_with_proxy(self):
        mgr = WSManager(proxy="http://127.0.0.1:10808")
        assert mgr._proxy == "http://127.0.0.1:10808"

    def test_subscribe(self):
        mgr = WSManager()
        mgr.subscribe("candles", {"instId": "BTC-USDT", "bar": "1m", "channel": "candles"})
        assert len(mgr._subscriptions) == 1

    def test_subscribe_dedup(self):
        mgr = WSManager()
        mgr.subscribe("candles", {"instId": "BTC-USDT", "bar": "1m", "channel": "candles"})
        mgr.subscribe("candles", {"instId": "BTC-USDT", "bar": "1m", "channel": "candles"})
        assert len(mgr._subscriptions) == 1

    def test_set_callback(self):
        mgr = WSManager()
        async def fake_cb(data, arg): pass
        mgr.set_callback("candles", fake_cb)
        assert "candles" in mgr._callbacks
        assert fake_cb in mgr._callbacks["candles"]

    def test_subscribe_candles(self):
        mgr = WSManager()
        mgr.subscribe_candles("BTC-USDT", "1m")
        assert len(mgr._subscriptions) == 1
        assert mgr._subscriptions[0]["channel"] == "candles"
        assert mgr._subscriptions[0]["instId"] == "BTC-USDT"

    def test_subscribe_helper_methods(self):
        mgr = WSManager()
        mgr.subscribe_ticker("BTC-USDT")
        mgr.subscribe_orderbook("BTC-USDT", 400)
        mgr.subscribe_trades("BTC-USDT")
        mgr.subscribe_funding_rate("BTC-USDT-SWAP")
        mgr.subscribe_open_interest("BTC-USDT-SWAP")
        mgr.subscribe_mark_price("BTC-USDT-SWAP")
        assert len(mgr._subscriptions) == 6

    def test_get_buffered(self):
        mgr = WSManager()
        assert mgr.get_buffered("candles") == []
