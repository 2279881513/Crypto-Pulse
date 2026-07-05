"""
CryptoPulse — 数据管道测试
"""

import pytest
import pandas as pd
import numpy as np

from cryptopulse.core.data.models import KLine
from cryptopulse.core.data.ring_buffer import KLineRingBuffer


class TestKLineRingBuffer:
    """K 线环形缓冲区测试"""

    @pytest.fixture
    def sample_kline(self, ts: int = 1000000) -> KLine:
        return KLine(
            timestamp=ts,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.0,
            volume_quote=5_000_000.0,
            confirm=True,
        )

    def make_kline(self, ts: int, close: float) -> KLine:
        return KLine(
            timestamp=ts,
            open=close - 10,
            high=close + 20,
            low=close - 30,
            close=close,
            volume=100.0,
            volume_quote=close * 100,
            confirm=True,
        )

    def test_push_and_count(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        assert len(buf) == 0

        for i in range(5):
            buf.push(self.make_kline(1000 + i * 60, 50000.0 + i))
        assert len(buf) == 5
        assert buf.current_count == 5

    def test_capacity_limit(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        for i in range(20):
            buf.push(self.make_kline(1000 + i * 60, float(i)))
        assert len(buf) == 10
        # earliest ones were evicted
        assert buf.to_dataframe().iloc[0]["close"] == 10.0

    def test_to_dataframe(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        for i in range(3):
            buf.push(self.make_kline(1000 + i * 60, float(i * 10 + 50000)))

        df = buf.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == ["open", "high", "low", "close", "volume", "volume_quote"]

    def test_update_unconfirmed(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        buf.push(self.make_kline(1000, 50000.0))

        # 更新未确认的 K 线
        live = KLine(
            timestamp=1060,  # 当前周期未结束
            open=50050.0, high=50100.0, low=50020.0, close=50080.0,
            volume=50.0, volume_quote=2_500_000.0, confirm=False,
        )
        buf.update(live)

        df = buf.to_dataframe()
        assert len(df) == 2  # 确认的 + 未确认的
        assert df.iloc[-1]["close"] == 50080.0

    def test_duplicate_push(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        k = self.make_kline(1000, 50000.0)
        buf.push(k)
        buf.push(k)  # 重复
        assert len(buf) == 1

    def test_not_full(self):
        buf = KLineRingBuffer(capacity=100, interval="1m")
        assert not buf.is_full
        for i in range(100):
            buf.push(self.make_kline(1000 + i * 60, float(i)))
        assert buf.is_full

    def test_latest_close(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        assert buf.latest_close is None
        buf.push(self.make_kline(1000, 50000.0))
        assert buf.latest_close == 50000.0

        # 未确认的优先
        live = KLine(
            timestamp=1060, open=50050, high=50100, low=50020, close=50100,
            volume=50, volume_quote=2_500_000, confirm=False,
        )
        buf.update(live)
        assert buf.latest_close == 50100.0

    def test_to_array(self):
        buf = KLineRingBuffer(capacity=10, interval="1m")
        for i in range(5):
            buf.push(self.make_kline(1000 + i * 60, float(i * 10 + 50000)))
        opens, highs, lows, closes, volumes = buf.to_array()
        assert len(closes) == 5
        assert isinstance(closes, np.ndarray)
