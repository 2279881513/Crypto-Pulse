"""
CryptoPulse — 技术信号引擎
多周期评分卡，输出方向倾向 + 入场/止盈/止损
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from cryptopulse.core.data.models import Direction
from cryptopulse.core.indicators.calculations import (
    adx, atr, bollinger, emma, macd, obv, rsi, sma,
)


@dataclass
class SignalResult:
    """信号输出"""
    direction: Direction
    score: float                     # -100 ~ +100
    confidence: int                  # 0-100
    adx_value: float
    entry_zone_low: float
    entry_zone_high: float
    entry_optimal: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    summary: str                     # 一句话理由
    details: dict                    # 各项指标详情


class TechnicalSignalEngine:
    """
    多周期技术信号引擎

    短线参数（1m/5m）:
        EMA(5,13,21), MACD(5,13,5), RSI(14) 80/20, BB(20,2.5)

    中线参数（4h/1d）:
        EMA(20,50,200), MACD(12,26,9), RSI(14) 75/25, BB(20,3.0)
    """

    def __init__(self, style: str = "short_term") -> None:
        self.style = style
        if style == "short_term":
            self.ema_fast, self.ema_mid, self.ema_slow = 5, 13, 21
            self.macd_fast, self.macd_slow, self.macd_signal = 5, 13, 5
            self.rsi_period, self.rsi_ob, self.rsi_os = 14, 80, 20
            self.bb_period, self.bb_std = 20, 2.5
            self.adx_period = 14
        else:
            self.ema_fast, self.ema_mid, self.ema_slow = 20, 50, 200
            self.macd_fast, self.macd_slow, self.macd_signal = 12, 26, 9
            self.rsi_period, self.rsi_ob, self.rsi_os = 14, 75, 25
            self.bb_period, self.bb_std = 20, 3.0
            self.adx_period = 14

    def evaluate(self, df: pd.DataFrame, trend_5m: Optional[str] = None) -> SignalResult:
        """
        对一组 K 线进行技术面评估。

        df: 包含 [open, high, low, close, volume] 的 DataFrame，索引为时间戳
        trend_5m: 可选，5m趋势方向（"bullish"/"bearish"/"neutral"/None），用于方向一致性过滤
        """
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        openp = df["open"].values
        vol = df["volume"].values
        price = close[-1]

        # ---------------------------------------------------------------
        # 1. 计算所有指标
        # ---------------------------------------------------------------
        ema_f = emma(close, self.ema_fast)
        ema_m = emma(close, self.ema_mid)
        ema_s = emma(close, self.ema_slow)

        macd_line, macd_signal_line, macd_hist = macd(
            close, self.macd_fast, self.macd_slow, self.macd_signal
        )

        rsi_val = rsi(close, self.rsi_period)
        bb_upper, bb_mid, bb_lower = bollinger(close, self.bb_period, self.bb_std)
        atr_val = atr(high, low, close, 14)
        adx_val = adx(high, low, close, self.adx_period)
        obv_val = obv(close, vol)

        # 体积比（当前量 / 20周期均量）
        vol_ma20 = sma(vol, 20)
        vol_ratio = vol[-1] / vol_ma20[-1] if vol_ma20[-1] > 0 else 0

        # 2. 各项评分（仅存储指标值，方向由条件判定）
        # ---------------------------------------------------------------
        signals = {}
        signals["rsi_val"] = rsi_val[-1] if not np.isnan(rsi_val[-1]) else 50
        adx_latest = adx_val[-1] if not np.isnan(adx_val[-1]) else 0
        signals["adx"] = adx_latest
        signals["atr"] = atr_val[-1] if not np.isnan(atr_val[-1]) else 0

        # ---------------------------------------------------------------
        # 3. 方向判定
        # ---------------------------------------------------------------
        total_score = 0
        at_bb_lower = not np.isnan(bb_upper[-1]) and price <= bb_lower[-1] + (bb_mid[-1] - bb_lower[-1]) * 0.3
        at_bb_upper_band = not np.isnan(bb_upper[-1]) and price >= bb_upper[-1] - (bb_upper[-1] - bb_mid[-1]) * 0.3

        # ---- RSI极值 + BB位置入场（优化参数） ----
        is_oversold = not np.isnan(rsi_val[-1]) and rsi_val[-1] <= 20
        is_ob = not np.isnan(rsi_val[-1]) and rsi_val[-1] >= 80
        ema_trend_up = not np.isnan(ema_f[-1]) and price > ema_f[-1]
        ema_trend_down = not np.isnan(ema_f[-1]) and price < ema_f[-1]
        direction = Direction.NEUTRAL; total_score = 0
        if is_oversold and at_bb_lower and adx_latest >= 10:
            direction = Direction.BULLISH; total_score = 60
        if direction == Direction.NEUTRAL and is_ob and at_bb_upper_band and adx_latest >= 10 and adx_latest <= 45:
            direction = Direction.BEARISH; total_score = -60
        confidence = min(100, max(30, int(55 + adx_latest * 0.5)))
        if direction != Direction.NEUTRAL and confidence < 35:
            direction = Direction.NEUTRAL

        # ---- 5m 方向一致性过滤 ----
        # trend_5m 由 app.py 传入，基于 5m EMA 排列+ADX 判定
        if direction != Direction.NEUTRAL and trend_5m is not None:
            if trend_5m == "neutral":
                # 5m 无趋势 → 观望
                direction = Direction.NEUTRAL
            elif direction == Direction.BULLISH and trend_5m == "bearish":
                # 5m 向下 → 不做多
                direction = Direction.NEUTRAL
            elif direction == Direction.BEARISH and trend_5m == "bullish":
                # 5m 向上 → 不做空
                direction = Direction.NEUTRAL

        # ---------------------------------------------------------------
        # 4. 入场/止盈/止损点位（结合支撑阻力和 ATR）
        # ---------------------------------------------------------------
        current_atr = atr_val[-1] if not np.isnan(atr_val[-1]) else price * 0.005

        # 找出最近 30 根的摆动低点（支撑）和高点（阻力）
        lookback = min(30, len(close) - 1)
        supports = []
        resistances = []
        for i in range(lookback - 1):
            idx = len(close) - lookback + i
            if idx < 2 or idx >= len(close) - 1:
                continue
            # 局部低点：左右都比它高
            if low[idx] < low[idx - 1] and low[idx] < low[idx + 1]:
                supports.append(low[idx])
            # 局部高点：左右都比它低
            if high[idx] > high[idx - 1] and high[idx] > high[idx + 1]:
                resistances.append(high[idx])

        # 取最近的有效支撑/阻力
        nearest_support = max([s for s in supports if s < price]) if any(s < price for s in supports) else None
        nearest_resistance = min([r for r in resistances if r > price]) if any(r > price for r in resistances) else None

        if direction == Direction.BULLISH:
            entry_low = price - current_atr * 0.3
            entry_high = price + current_atr * 0.3
            entry_opt = price
            # 止损：放在最近支撑下方一点，或者 ATR 止损（收紧）
            if nearest_support:
                stop = min(nearest_support - current_atr * 0.2, price - current_atr * 2.0)
            else:
                stop = price - current_atr * 2.0
            # 止盈：放在最近阻力附近，或 ATR 目标
            if nearest_resistance:
                tp1 = min(nearest_resistance - current_atr * 0.2, price + current_atr * 2.5)
                tp2 = min(nearest_resistance + current_atr * 0.3, price + current_atr * 4.0)
                tp3 = nearest_resistance + current_atr * 2.0
            else:
                tp1 = price + current_atr * 2.5
                tp2 = price + current_atr * 4.0
                tp3 = price + current_atr * 6.0
        elif direction == Direction.BEARISH:
            entry_low = price - current_atr * 0.3
            entry_high = price + current_atr * 0.3
            entry_opt = price
            if nearest_resistance:
                stop = max(nearest_resistance + current_atr * 0.2, price + current_atr * 2.0)
            else:
                stop = price + current_atr * 2.0
            if nearest_support:
                tp1 = max(nearest_support + current_atr * 0.2, price - current_atr * 2.5)
                tp2 = max(nearest_support - current_atr * 0.3, price - current_atr * 4.0)
                tp3 = nearest_support - current_atr * 2.0
            else:
                tp1 = price - current_atr * 2.5
                tp2 = price - current_atr * 4.0
                tp3 = price - current_atr * 6.0
        else:
            entry_low = price * 0.99
            entry_high = price * 1.01
            entry_opt = price
            stop = price
            tp1 = price
            tp2 = price
            tp3 = price

        # 手续费过滤：利润必须高于手续费才值得做
        fee_pct = 0.05  # 单边手续费 0.05%
        min_tp1_pct = 0.04  # 短线波动小，TP1 > 0.04% 即可（开平0.1%靠杠杆覆盖）
        if self.style == "medium_term":
            min_tp1_pct = fee_pct * 1.5  # 中线保证金 TP1 > 0.075%
        tp1_pct = abs(tp1 - price) / price * 100 if price > 0 else 0
        if direction != Direction.NEUTRAL and tp1_pct < min_tp1_pct:
            direction = Direction.NEUTRAL
            confidence = 10
            summary = f"TP1涨幅({tp1_pct:.2f}%)不够覆盖手续费，建议观望"

        # 构建理由
        details = {k: f"{v:+.2f}" for k, v in signals.items()}
        details["vol_ratio"] = f"{vol_ratio:.2f}"
        details["adx"] = f"{adx_latest:.1f}"
        details["rsi"] = f"{rsi_val[-1]:.1f}" if not np.isnan(rsi_val[-1]) else "N/A"
        if nearest_support:
            details["支撑"] = f"{nearest_support:.1f}"
        if nearest_resistance:
            details["阻力"] = f"{nearest_resistance:.1f}"

        summary = self._build_summary(direction, total_score, adx_latest, signals)

        return SignalResult(
            direction=direction,
            score=round(total_score, 1),
            confidence=confidence,
            adx_value=round(adx_latest, 1),
            entry_zone_low=round(entry_low, 1),
            entry_zone_high=round(entry_high, 1),
            entry_optimal=round(entry_opt, 1),
            stop_loss=round(stop, 1),
            take_profit_1=round(tp1, 1),
            take_profit_2=round(tp2, 1),
            take_profit_3=round(tp3, 1),
            summary=summary,
            details=details,
        )

    def _build_summary(self, direction: Direction, score: float,
                       adx_val: float, signals: dict) -> str:
        """生成多行详细理由"""
        ema_sig = signals.get("ema", 0)
        macd_sig = signals.get("macd", 0)
        rsi_sig = signals.get("rsi", 0)
        bb_sig = signals.get("bollinger", 0)
        vol_sig = signals.get("volume", 0)
        obv_sig = signals.get("obv", 0)

        lines = []

        # 方向判断 + 信心
        if direction == Direction.BULLISH:
            dir_text = "看多"
        elif direction == Direction.BEARISH:
            dir_text = "看空"
        else:
            dir_text = "观望"

        # 趋势
        trend_parts = []
        if ema_sig > 0.5:
            trend_parts.append("EMA多头排列（短>中>长），趋势向上")
        elif ema_sig < -0.5:
            trend_parts.append("EMA空头排列（短<中<长），趋势向下")
        else:
            trend_parts.append("EMA排列混乱，无明确趋势方向")

        if adx_val >= 25:
            trend_parts.append(f"ADX {adx_val:.0f} 存在趋势")
        else:
            trend_parts.append(f"ADX {adx_val:.0f} 市场震荡")

        lines.append("📊 趋势：" + "，".join(trend_parts))

        # 动能
        momo_parts = []
        if macd_sig > 0.5:
            momo_parts.append("MACD零上金叉，多头动能持续增强")
        elif macd_sig > 0:
            momo_parts.append("MACD偏多，但动能尚弱")
        elif macd_sig < -0.5:
            momo_parts.append("MACD零下死叉，空头动能持续增强")
        elif macd_sig < 0:
            momo_parts.append("MACD偏空，但动能尚弱")
        else:
            momo_parts.append("MACD信号中性")

        lines.append("⚡ 动能：" + "，".join(momo_parts))

        # 超买超卖
        extreme_parts = []
        bb_val = signals.get("bollinger", 0)
        if rsi_sig > 0.5:
            extreme_parts.append("RSI进入超卖区，存在反弹需求")
        elif rsi_sig < -0.5:
            extreme_parts.append("RSI进入超买区，注意回调风险")
        else:
            extreme_parts.append("RSI处于中性区域")

        if bb_sig > 0.5:
            extreme_parts.append("价格触及布林下轨，超卖反弹信号")
        elif bb_sig < -0.5:
            extreme_parts.append("价格触及布林上轨，超买回调信号")

        lines.append("📐 位置：" + "，".join(extreme_parts))

        # 成交量
        vol_parts = []
        if vol_sig > 0.5:
            vol_parts.append("成交量放大配合价格方向，突破可信")
        elif vol_sig > 0:
            vol_parts.append("成交量温和，行情尚需确认")
        elif vol_sig > -0.5:
            vol_parts.append("成交量偏低，动能不足")
        else:
            vol_parts.append("缩量运行，市场观望情绪浓")

        if obv_sig > 0.3:
            vol_parts.append("OBV与价格同向，资金流入")
        elif obv_sig < -0.3:
            vol_parts.append("OBV与价格背离，资金流出")
        else:
            vol_parts.append("OBV中性，资金面无明显方向")

        lines.append("💰 量能：" + "，".join(vol_parts))

        # 一句话行动建议
        if direction == Direction.BULLISH:
            lines.append(f"✅ 建议：技术面综合偏多（{score:+.0f}分），可在入场区间内择机做多，止损设于下方")
        elif direction == Direction.BEARISH:
            lines.append(f"✅ 建议：技术面综合偏空（{score:+.0f}分），可在入场区间内择机做空，止损设于上方")

        return "\n".join(lines)
