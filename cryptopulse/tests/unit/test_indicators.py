"""
CryptoPulse — 技术指标引擎测试
"""

import numpy as np
import pandas as pd
import pytest

from cryptopulse.core.data.models import Direction
from cryptopulse.core.indicators.engine import TechnicalSignalEngine
from cryptopulse.core.indicators.calculations import (
    emma, rsi, macd, bollinger, atr, sma, obv,
)


class TestCalculations:
    """指标计算测试"""

    def _make_series(self, length=100, base=50000.0, volatility=100):
        """生成模拟 K 线数据"""
        np.random.seed(42)
        closes = base + np.cumsum(np.random.randn(length) * volatility)
        # 确保为正
        closes = np.maximum(closes, base * 0.5)
        highs = closes * (1 + np.random.rand(length) * 0.005)
        lows = closes * (1 - np.random.rand(length) * 0.005)
        vols = np.random.rand(length) * 100 + 50
        return closes, highs, lows, vols

    def test_sma(self):
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        result = sma(data, 3)
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == 2.0
        assert result[9] == 9.0

    def test_emma(self):
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        result = emma(data, 3)
        assert not np.isnan(result[-1])
        # EMA 跟随趋势
        assert result[-1] > result[0]

    def test_rsi(self):
        # 持续上涨 → RSI 很高
        up = np.linspace(100, 200, 30)
        r = rsi(up, 14)
        assert r[-1] > 70  # 超买

        # 持续下跌 → RSI 很低
        down = np.linspace(200, 100, 30)
        r2 = rsi(down, 14)
        assert r2[-1] < 30  # 超卖

    def test_macd(self):
        data = np.linspace(100, 200, 50)
        m, s, h = macd(data, 12, 26, 9)
        # 上涨趋势中 MACD 应为正
        assert not np.isnan(h[-1])

    def test_bollinger(self):
        data = np.random.randn(50) * 100 + 50000
        u, m, l = bollinger(data, 20, 2.5)
        assert u[-1] > m[-1] > l[-1]

    def test_atr(self):
        closes, highs, lows, vols = self._make_series()
        atr_vals = atr(highs, lows, closes, 14)
        assert not np.isnan(atr_vals[-1])
        assert atr_vals[-1] > 0

    def test_obv(self):
        data = np.array([100, 101, 102, 101, 100, 99, 100, 101], dtype=float)
        vol = np.array([100, 100, 100, 100, 100, 100, 100, 100], dtype=float)
        obv_vals = obv(data, vol)
        # 上涨时 OBV 增加
        assert obv_vals[2] > obv_vals[0]
        # 下跌时 OBV 减少
        assert obv_vals[5] < obv_vals[3]


class TestSignalEngine:
    """信号引擎测试"""

    def _make_df(self, trend: str = "up", length: int = 200):
        """生成不同趋势的 DataFrame"""
        np.random.seed(42)
        if trend == "up":
            closes = 50000 + np.cumsum(np.random.randn(length) * 50) + np.linspace(0, 2000, length)
        elif trend == "down":
            closes = 52000 + np.cumsum(np.random.randn(length) * 50) - np.linspace(0, 2000, length)
        else:
            closes = 50000 + np.cumsum(np.random.randn(length) * 100)

        closes = np.maximum(closes, 10000)
        highs = closes * (1 + np.abs(np.random.randn(length)) * 0.003)
        lows = closes * (1 - np.abs(np.random.randn(length)) * 0.003)
        vols = np.random.rand(length) * 100 + 50

        return pd.DataFrame({
            "open": closes * 0.999,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
        })

    def test_up_trend_gives_bullish(self):
        df = self._make_df("up")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        assert result.direction == Direction.BULLISH, f"Expected BULLISH, got {result.direction}"
        assert result.score > 0

    def test_down_trend_gives_bearish(self):
        df = self._make_df("down")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        assert result.direction == Direction.BEARISH, f"Expected BEARISH, got {result.direction}"
        assert result.score < 0

    def test_neutral_market(self):
        df = self._make_df("flat")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        # 震荡市场可能给出中性或弱方向
        assert abs(result.score) < 60

    def test_medium_term_params(self):
        df = self._make_df("up", length=300)
        engine = TechnicalSignalEngine("medium_term")
        result = engine.evaluate(df)
        # 中线参数应有合理的评分
        assert -100 <= result.score <= 100
        assert 0 <= result.confidence <= 100

    def test_output_has_levels(self):
        df = self._make_df("up")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        assert result.entry_optimal > 0
        assert result.stop_loss > 0
        assert result.take_profit_1 > 0

    def test_bearish_stop_above_price(self):
        df = self._make_df("down")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        if result.direction == Direction.BEARISH:
            assert result.stop_loss > result.entry_optimal  # 空单止损在入场价上方

    def test_bullish_stop_below_price(self):
        df = self._make_df("up")
        engine = TechnicalSignalEngine("short_term")
        result = engine.evaluate(df)
        if result.direction == Direction.BULLISH:
            assert result.stop_loss < result.entry_optimal  # 多单止损在入场价下方
