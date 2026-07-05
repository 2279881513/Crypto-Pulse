"""
CryptoPulse — 技术指标计算模块
使用 pandas/numpy 实现，无 TA-Lib 依赖
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def emma(close: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均（手动实现，兼容 TA-Lib 结果）"""
    result = np.zeros_like(close)
    result[:] = np.nan
    if len(close) < period:
        return result
    multiplier = 2.0 / (period + 1)
    result[period - 1] = np.mean(close[:period])
    for i in range(period, len(close)):
        result[i] = (close[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def sma(close: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均"""
    result = np.zeros_like(close)
    result[:] = np.nan
    if len(close) < period:
        return result
    cumsum = np.cumsum(close)
    result[period - 1] = cumsum[period - 1] / period
    result[period:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI 计算"""
    result = np.zeros_like(close)
    result[:] = np.nan
    if len(close) <= period:
        return result

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.zeros_like(close)
    avg_loss = np.zeros_like(close)

    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    result = 100 - (100 / (1 + rs))
    return result


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 计算，返回 (macd_line, signal_line, histogram)"""
    ema_fast = emma(close, fast)
    ema_slow = emma(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = emma(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(close: np.ndarray, period: int = 20, std_dev: float = 2.5):
    """布林带计算"""
    middle = sma(close, period)
    std = np.zeros_like(close)
    std[:] = np.nan
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1:i + 1])
    upper = middle + std * std_dev
    lower = middle - std * std_dev
    return upper, middle, lower


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """平均真实波幅"""
    result = np.zeros_like(close)
    result[:] = np.nan
    if len(close) < period + 1:
        return result

    tr = np.zeros_like(close)
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    result[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, len(close)):
        result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """能量潮（OBV）"""
    result = np.zeros_like(close)
    result[0] = volume[0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            result[i] = result[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            result[i] = result[i - 1] - volume[i]
        else:
            result[i] = result[i - 1]
    return result


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """平均趋向指数（简化版）"""
    result = np.zeros_like(close)
    result[:] = np.nan
    if len(close) < period * 2:
        return result

    # 趋向线
    plus_dm = np.zeros_like(close)
    minus_dm = np.zeros_like(close)
    tr = np.zeros_like(close)

    for i in range(1, len(close)):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # 平滑
    atr_val = atr(high, low, close, period)
    plus_di = np.zeros_like(close)
    minus_di = np.zeros_like(close)
    for i in range(period, len(close)):
        sum_pdm = np.sum(plus_dm[i - period + 1:i + 1])
        sum_mdm = np.sum(minus_dm[i - period + 1:i + 1])
        plus_di[i] = 100 * sum_pdm / (atr_val[i] * period + 1e-10)
        minus_di[i] = 100 * sum_mdm / (atr_val[i] * period + 1e-10)

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    result[period * 2 - 1] = np.mean(dx[period:period * 2])
    for i in range(period * 2, len(close)):
        result[i] = (result[i - 1] * (period - 1) + dx[i]) / period
    return result
