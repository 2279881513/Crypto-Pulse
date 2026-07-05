"""
CryptoPulse — 数据模型测试
"""

import pytest

from cryptopulse.core.data.models import KLine, OrderBook, OrderBookLevel, Interval


class TestKLine:
    def test_from_okx(self):
        raw = [
            "1597026383000",
            "50000.0",
            "50100.0",
            "49900.0",
            "50050.0",
            "100.0",
            "5000000.0",
            "0",
            "1",
        ]
        k = KLine.from_okx(raw)
        assert k.timestamp == 1597026383000
        assert k.open == 50000.0
        assert k.close == 50050.0
        assert k.volume == 100.0
        assert k.confirm is True

    def test_properties(self):
        k = KLine(
            timestamp=1000, open=100, high=110, low=90, close=105,
            volume=50, volume_quote=5000, confirm=True,
        )
        assert k.range == 20.0
        assert k.mid == 100.0


class TestInterval:
    def test_seconds(self):
        assert Interval.M1.seconds == 60
        assert Interval.H4.seconds == 14400
        assert Interval.D1.seconds == 86400

    def test_short_term(self):
        assert Interval.M1.for_short_term is True
        assert Interval.H4.for_short_term is False

    def test_medium_term(self):
        assert Interval.D1.for_medium_term is True
        assert Interval.M5.for_medium_term is False


class TestOrderBook:
    def test_from_okx(self):
        raw = {
            "asks": [["50010.0", "1.5", "2"], ["50020.0", "2.0", "3"]],
            "bids": [["49990.0", "2.5", "4"], ["49980.0", "1.0", "1"]],
            "ts": "1597026383000",
        }
        ob = OrderBook.from_okx(raw)
        assert ob.ts == 1597026383000
        assert len(ob.bids) == 2
        assert ob.bids[0].price == 49990.0
        assert ob.bids[0].size == 2.5
        assert ob.asks[0].price == 50010.0
