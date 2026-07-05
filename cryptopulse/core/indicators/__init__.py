"""
CryptoPulse — 技术指标计算引擎

基于 pandas-ta 计算多个技术指标，输出多空评分。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cryptopulse.core.data.models import Direction


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    对 K 线 DataFrame 计算全套技术指标，返回带指标列的 DataFrame。

    输入 df 必须包含: open, high, low, close, volume
    """
    if df.empty or len(df) < 50:
        return df

    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # --- 趋势指标 ---
    # EMA
    df["ema_short"] = close.ewm(span=5, adjust=False).mean()
    df["ema_mid"] = close.ewm(span=13, adjust=False).mean()
    df["ema_long"] = close.ewm(span=21, adjust=False).mean()

    # MACD (5, 13, 5) — 短线优化参数
    ema_fast = close.ewm(span=5, adjust=False).mean()
    ema_slow = close.ewm(span=13, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=5, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ADX (趋势强度)
    df["adx"] = _compute_adx(high, low, close, period=14)

    # --- 摆动指标 ---
    # RSI (14)
    df["rsi"] = _compute_rsi(close, period=14)

    # Stoch RSI
    df["stoch_k"], df["stoch_d"] = _compute_stoch_rsi(close, period=14)

    # --- 波动率指标 ---
    # 布林带 (20, 2.5)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_mid"] = bb_mid
    df["bb_upper"] = bb_mid + 2.5 * bb_std
    df["bb_lower"] = bb_mid - 2.5 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid  # 带宽比
    df["bb_position"] = (close - bb_mid) / (bb_std + 1e-10)  # 价格在布林带中的 Z 位置

    # ATR (14)
    df["atr"] = _compute_atr(high, low, close, period=14)

    # --- 成交量指标 ---
    # OBV
    df["obv"] = _compute_obv(close, volume)
    df["obv_ema"] = df["obv"].ewm(span=14, adjust=False).mean()
    df["obv_trend"] = df["obv"] - df["obv_ema"]

    # VWAP
    df["vwap"] = (volume * (high + low + close) / 3).rolling(20).sum() / volume.rolling(20).sum()

    # 成交量异常
    df["volume_ma"] = volume.rolling(20).mean()
    df["volume_ratio"] = volume / df["volume_ma"]  # >1.5 表示放量

    return df


def score_indicators(df: pd.DataFrame) -> tuple[Direction, float, dict]:
    """
    基于技术指标打分，输出方向倾向和评分。

    Returns:
        (direction, total_score, details)
        direction: BULLISH / BEARISH / NEUTRAL
        total_score: -100 ~ +100
        details: 各指标明细
    """
    if df.empty or len(df) < 50:
        return Direction.NEUTRAL, 0.0, {}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    scores = {}
    signals = []

    # 1. EMA 排列评分 (权重 25%)
    ema_score = _score_ema(latest, df)
    scores["ema"] = ema_score
    signals.append(("EMA排列", ema_score, 0.25))

    # 2. MACD 评分 (权重 10%)
    macd_score = _score_macd(latest, prev)
    scores["macd"] = macd_score
    signals.append(("MACD", macd_score, 0.10))

    # 3. RSI 评分 (权重 10%)
    rsi_score = _score_rsi(latest)
    scores["rsi"] = rsi_score
    signals.append(("RSI", rsi_score, 0.10))

    # 4. 动量评分 (权重 15%)
    mom_score = _score_momentum(latest, df)
    scores["momentum"] = mom_score
    signals.append(("动量", mom_score, 0.15))

    # 5. 布林带评分 (权重 10%)
    bb_score = _score_bollinger(latest)
    scores["bollinger"] = bb_score
    signals.append(("布林带", bb_score, 0.10))

    # 6. OBV 评分 (权重 12%)
    obv_score = _score_obv(latest)
    scores["obv"] = obv_score
    signals.append(("OBV", obv_score, 0.12))

    # 7. VWAP 评分 (权重 5%)
    vwap_score = _score_vwap(latest)
    scores["vwap"] = vwap_score
    signals.append(("VWAP", vwap_score, 0.05))

    # 8. 成交量评分 (权重 8%)
    vol_score = _score_volume(latest)
    scores["volume"] = vol_score
    signals.append(("成交量", vol_score, 0.08))

    # 9. 微观结构评分 (权重 5%)
    micro_score = latest.get("micro", 0)
    if isinstance(micro_score, (int, float)):
        micro_score = max(-1.0, min(1.0, micro_score * 0.5))
    else:
        micro_score = 0.0
    scores["micro"] = micro_score
    signals.append(("微观", micro_score, 0.05))

    # ========== 加权总分 ==========
    total = sum(score * weight for _, score, weight in signals)

    # ========== ADX 趋势强度过滤 ==========
    adx = latest.get("adx", 0)
    scores["adx"] = adx

    if adx < 25:
        scores["trend_filter"] = f"无趋势(ADX={adx:.0f})"
        # 盘整期：只有高评分才发信号，边缘信号直接过滤
        if abs(total) < 35:
            scores["filtered_by_adx"] = True
            return Direction.NEUTRAL, 0.0, scores
    elif adx >= 35:
        # 强趋势：放大评分
        total *= 1.15
        scores["trend_boost"] = True

    # ========== 方向判定（调高阈值到30） ==========
    # 数据验证: 阈值30+ADX≥30 → 56.4%准确率 +19.60%PnL
    # 相比原始系统: 55.1%准确率 +16.35%PnL
    threshold = 30
    if total > threshold:
        direction = Direction.BULLISH
    elif total < -threshold:
        direction = Direction.BEARISH
    else:
        direction = Direction.NEUTRAL
        direction = Direction.NEUTRAL

    return direction, round(total, 1), scores


# ======================================================================
# 内部评分函数
# ======================================================================

def _score_ema(latest: pd.Series, df: pd.DataFrame) -> float:
    """EMA 排列评分: +1 多头排列, -1 空头排列, 0 混乱"""
    s, m, l = latest.get("ema_short", 0), latest.get("ema_mid", 0), latest.get("ema_long", 0)
    price = latest["close"]

    if s > m > l and price > s:
        return 1.0  # 强势多头
    elif s > m > l:
        return 0.5  # 趋势多但价格回调
    elif s < m < l and price < s:
        return -1.0  # 强势空头
    elif s < m < l:
        return -0.5  # 趋势空但价格反弹

    # 检查粘合/交叉
    ema_close_together = abs(s - m) / price < 0.001 and abs(m - l) / price < 0.001
    if ema_close_together:
        return 0.0  # 粘合无方向

    return 0.0


def _score_macd(latest: pd.Series, prev: pd.Series) -> float:
    """MACD 评分"""
    macd = latest.get("macd", 0)
    hist = latest.get("macd_hist", 0)
    prev_hist = prev.get("macd_hist", 0)

    if macd > 0 and hist > 0 and hist > prev_hist:
        return 1.0  # 零上金叉+柱线伸长
    elif macd > 0 and hist > 0:
        return 0.5  # 零上金叉
    elif macd > 0 and hist < 0 and hist < prev_hist:
        return -0.5  # 零上死叉
    elif macd < 0 and hist < 0 and hist < prev_hist:
        return -1.0  # 零下死叉
    elif macd < 0 and hist > 0 and hist > prev_hist:
        return 0.5  # 零下金叉（底背离可能）

    return 0.0


def _score_rsi(latest: pd.Series) -> float:
    """RSI 评分（加密币使用 80/20 阈值，增加粒度）"""
    rsi = latest.get("rsi", 50)

    if rsi > 80:
        return -0.8  # 超买，看空
    elif rsi > 72:
        return -0.5  # 高度超买区域
    elif rsi > 65:
        return -0.3  # 偏多高位
    elif rsi > 58:
        return -0.1  # 中性偏多
    elif rsi > 50:
        return 0.0   # 中线上方中性
    elif rsi > 42:
        return 0.0   # 中线下方中性
    elif rsi > 35:
        return 0.1   # 中性偏空
    elif rsi > 28:
        return 0.3   # 偏空低位
    elif rsi > 20:
        return 0.5   # 低超卖区域
    else:
        return 0.8   # 超卖，看多


def _score_bollinger(latest: pd.Series) -> float:
    """布林带评分"""
    pos = latest.get("bb_position", 0)

    if pos > 3.0:
        return -1.0  # 突破上轨，严重超买
    elif pos > 2.0:
        return -0.7
    elif pos > 1.0:
        return -0.3
    elif pos > -1.0:
        return 0.0  # 中轨附近
    elif pos > -2.0:
        return 0.3
    elif pos > -3.0:
        return 0.7
    else:
        return 1.0  # 突破下轨，严重超卖


def _score_obv(latest: pd.Series) -> float:
    """OBV 趋势评分"""
    obv_trend = latest.get("obv_trend", 0)
    close = latest["close"]

    # 用 OBV 与价格的关系判断
    if obv_trend > close * 0.001:  # OBV 显著向上
        return 0.7
    elif obv_trend > 0:
        return 0.3
    elif obv_trend > -close * 0.001:
        return -0.3
    else:
        return -0.7


def _score_vwap(latest: pd.Series) -> float:
    """VWAP 位置评分"""
    close = latest.get("close", 0)
    vwap = latest.get("vwap", close)
    if vwap == 0:
        return 0.0

    diff = (close - vwap) / vwap
    if diff > 0.02:
        return -0.5  # 远高于 VWAP，可能超买
    elif diff > 0.005:
        return -0.2
    elif diff > -0.005:
        return 0.0  # 接近 VWAP
    elif diff > -0.02:
        return 0.2
    else:
        return 0.5  # 远低于 VWAP，可能超卖


def _score_momentum(latest: pd.Series, df: pd.DataFrame) -> float:
    """动量评分：基于短期价格变化率"""
    close = latest["close"]
    # 取前5根K线的收盘价计算动量变化率
    n = 5
    if len(df) >= n + 1:
        past_close = df.iloc[-n - 1]["close"]
        mom = (close - past_close) / past_close * 100  # 百分比
    else:
        return 0.0

    # 加密币波动大，放宽阈值
    if mom > 0.8:
        return 1.0   # 强动量向上
    elif mom > 0.4:
        return 0.7
    elif mom > 0.15:
        return 0.3
    elif mom > -0.15:
        return 0.0   # 动量不明显
    elif mom > -0.4:
        return -0.3
    elif mom > -0.8:
        return -0.7
    else:
        return -1.0   # 强动量向下


def _score_volume(latest: pd.Series) -> float:
    """成交量评分：放量确认趋势，缩量警告反转"""
    vol_ratio = latest.get("volume_ratio", 1.0)
    bb_pos = latest.get("bb_position", 0)

    if vol_ratio > 2.0:
        # 异常放量：配合布林带位置判断方向
        if bb_pos > 1.5:
            return -0.8  # 放量上轨 = 派发
        elif bb_pos < -1.5:
            return 0.8   # 放量下轨 = 吸筹
        else:
            return 0.3  # 一般性放量
    elif vol_ratio > 1.5:
        return 0.2  # 温和放量
    elif vol_ratio < 0.5:
        return -0.2  # 缩量
    else:
        return 0.0


# ======================================================================
# 指标计算辅助函数
# ======================================================================

def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _compute_stoch_rsi(close: pd.Series, period: int = 14) -> tuple:
    rsi = _compute_rsi(close, period)
    min_rsi = rsi.rolling(period).min()
    max_rsi = rsi.rolling(period).max()
    stoch_k = 100 * (rsi - min_rsi) / (max_rsi - min_rsi + 1e-10)
    stoch_d = stoch_k.rolling(3).mean()
    return stoch_k, stoch_d


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """简化 ADX 计算"""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    adx = dx.rolling(period).mean()
    return adx


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    obv = (volume * (~close.diff().le(0) * 2 - 1)).cumsum()
    return obv
