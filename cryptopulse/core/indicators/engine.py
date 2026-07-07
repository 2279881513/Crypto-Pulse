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

    def evaluate(self, df: pd.DataFrame) -> SignalResult:
        """
        对一组 K 线进行技术面评估。

        df: 包含 [open, high, low, close, volume] 的 DataFrame，索引为时间戳
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

        # ---------------------------------------------------------------
        # 2. 各项评分
        # ---------------------------------------------------------------
        signals = {}
        weights = {
            "ema": 0.12,        # 降低权重，1m上滞后明显
            "macd": 0.06,
            "rsi": 0.14,        # 增加均值回归权重
            "bollinger": 0.14,   # 增加布林带权重
            "volume": 0.04,
            "obv": 0.04,
            "adx_filter": 0.08,  # 降低，它是元信号不是方向信号
            "momentum": 0.06,     # 降低，1m上噪音大
            "micro": 0.06,
            "pullback": 0.14,    # 趋势回调入场
            "reversion": 0.12,   # RSI+BB极端反转
        }

        # --- EMA 排列评分 ---
        if not np.isnan(ema_f[-1]) and not np.isnan(ema_m[-1]) and not np.isnan(ema_s[-1]):
            aligned = ema_f[-1] > ema_m[-1] > ema_s[-1]
            bearish = ema_f[-1] < ema_m[-1] < ema_s[-1]
            if aligned and price > ema_f[-1]:
                signals["ema"] = 1.0
            elif aligned and price < ema_f[-1]:
                signals["ema"] = 0.5
            elif bearish and price < ema_f[-1]:
                signals["ema"] = -1.0
            elif bearish and price > ema_f[-1]:
                signals["ema"] = -0.5
            else:
                signals["ema"] = 0.0
        else:
            signals["ema"] = 0.0

        # --- 趋势回调入场评分 (pullback) ---
        # 强趋势中价格回踩EMA→趋势延续信号；价格远离EMA→超买/超卖预警
        if adx_latest >= 30 and not np.isnan(ema_f[-1]) and not np.isnan(atr_val[-1]):
            dist_to_ema = abs(price - ema_f[-1])
            ema_dist_ratio = dist_to_ema / (atr_val[-1] + 1e-10)
            ema_bull = ema_f[-1] > ema_m[-1] > ema_s[-1]
            ema_bear = ema_f[-1] < ema_m[-1] < ema_s[-1]
            if ema_bull and price >= ema_f[-1] - atr_val[-1] * 0.3 and price <= ema_f[-1] + atr_val[-1] * 0.3:
                signals["pullback"] = 1.0  # 多头趋势中回踩EMA，理想入场
            elif ema_bear and price <= ema_f[-1] + atr_val[-1] * 0.3 and price >= ema_f[-1] - atr_val[-1] * 0.3:
                signals["pullback"] = -1.0  # 空头趋势中反弹EMA，理想入场
            elif ema_bull and ema_dist_ratio > 2.0:
                signals["pullback"] = -0.5  # 多头趋势中价格远离EMA→超买回调风险
            elif ema_bear and ema_dist_ratio > 2.0:
                signals["pullback"] = 0.5   # 空头趋势中价格远离EMA→超卖反弹机会
            else:
                signals["pullback"] = 0.0
        else:
            signals["pullback"] = 0.0

        # --- MACD 评分 ---
        if not np.isnan(macd_hist[-1]) and not np.isnan(macd_hist[-2]):
            hist_now = macd_hist[-1]
            hist_prev = macd_hist[-2]
            macd_now = macd_line[-1]
            macd_sig = macd_signal_line[-1]
            if macd_now > macd_sig and hist_now > hist_prev and hist_now > 0:
                signals["macd"] = 1.0  # 零上金叉，柱增长
            elif macd_now > macd_sig and hist_now > 0:
                signals["macd"] = 0.5  # 零上金叉
            elif macd_now < macd_sig and hist_now < hist_prev and hist_now < 0:
                signals["macd"] = -1.0  # 零下死叉，柱增长
            elif macd_now < macd_sig and hist_now < 0:
                signals["macd"] = -0.5
            else:
                signals["macd"] = 0.0
        else:
            signals["macd"] = 0.0

        # --- RSI 评分 ---
        if not np.isnan(rsi_val[-1]):
            r = rsi_val[-1]
            if r >= 80:
                signals["rsi"] = -1.0
            elif r >= 70:
                signals["rsi"] = -0.5
            elif r >= 60:
                signals["rsi"] = -0.2
            elif r >= 45:
                signals["rsi"] = 0.2
            elif r >= 35:
                signals["rsi"] = 0.0
            elif r >= 25:
                signals["rsi"] = 0.3
            elif r >= 20:
                signals["rsi"] = 0.6
            else:
                signals["rsi"] = 1.0
        else:
            signals["rsi"] = 0.0

        # --- 布林带位置评分 ---
        if not np.isnan(bb_upper[-1]):
            if price > bb_upper[-1]:
                signals["bollinger"] = -0.7  # 突破上轨 → 超买
            elif price > bb_mid[-1]:
                signals["bollinger"] = 0.3  # 中上轨之间
            elif price > bb_lower[-1]:
                signals["bollinger"] = -0.3  # 中下轨之间
            else:
                signals["bollinger"] = 0.7  # 突破下轨 → 超卖
        else:
            signals["bollinger"] = 0.0

        # --- RSI+BB 极端反转评分 (reversion) ---
        if not np.isnan(rsi_val[-1]) and not np.isnan(bb_upper[-1]):
            r = rsi_val[-1]
            at_bb_lower = price <= bb_lower[-1] + (bb_mid[-1] - bb_lower[-1]) * 0.1
            at_bb_upper = price >= bb_upper[-1] - (bb_upper[-1] - bb_mid[-1]) * 0.1
            if r < 30 and at_bb_lower:
                signals["reversion"] = 1.0   # 强烈超卖+突破下轨→做多
            elif r > 70 and at_bb_upper:
                signals["reversion"] = -1.0  # 强烈超买+突破上轨→做空
            elif r < 35 and price < bb_mid[-1]:
                signals["reversion"] = 0.6   # 偏超卖+中下轨→偏向做多
            elif r > 65 and price > bb_mid[-1]:
                signals["reversion"] = -0.6  # 偏超买+中上轨→偏向做空
            else:
                signals["reversion"] = 0.0
        else:
            signals["reversion"] = 0.0

        # --- 成交量评分 ---
        if vol_ratio > 1.5:
            # 放量：方向由价格方向决定
            price_change = (close[-1] - close[-5]) / close[-5] if len(close) >= 5 else 0
            signals["volume"] = 0.8 if price_change > 0.002 else (-0.8 if price_change < -0.002 else 0.5)
        elif vol_ratio > 1.0:
            signals["volume"] = 0.3
        elif vol_ratio > 0.7:
            signals["volume"] = -0.2
        else:
            signals["volume"] = -0.5  # 缩量

        # --- OBV 趋势评分 ---
        if len(obv_val) > 5 and not np.isnan(obv_val[-1]):
            obv_trend = (obv_val[-1] - obv_val[-5]) / (abs(obv_val[-5]) + 1e-10)
            if obv_trend > 0.01:
                signals["obv"] = 0.6
            elif obv_trend < -0.01:
                signals["obv"] = -0.6
            else:
                signals["obv"] = 0.0
        else:
            signals["obv"] = 0.0

        # --- K线微观结构评分 ---
        cr = high[-1] - low[-1]
        if cr > 0:
            bd = abs(close[-1] - openp[-1]); br = bd / cr; cp = (close[-1] - low[-1]) / cr
            uw = (high[-1] - max(close[-1], openp[-1])) / cr
            lw = (min(close[-1], openp[-1]) - low[-1]) / cr
            if br > 0.7 and cp > 0.7:
                signals["micro"] = 0.8
            elif br > 0.7 and cp < 0.3:
                signals["micro"] = -0.8
            elif uw > 0.5 and br < 0.3:
                signals["micro"] = -0.5
            elif lw > 0.5 and br < 0.3:
                signals["micro"] = 0.5
            elif br < 0.2 and vol_ratio > 1.5:
                signals["micro"] = 0.4 if cp > 0.6 else (-0.4 if cp < 0.4 else 0.0)
            else:
                signals["micro"] = 0.0
        else:
            signals["micro"] = 0.0

        # --- 动量评分 (5根K线价格变化率) ---
        if len(close) >= 6:
            mom_pct = (close[-1] - close[-6]) / close[-6] * 100
            if mom_pct > 0.08:
                signals["momentum"] = 1.0
            elif mom_pct > 0.03:
                signals["momentum"] = 0.5
            elif mom_pct < -0.08:
                signals["momentum"] = -1.0
            elif mom_pct < -0.03:
                signals["momentum"] = -0.5
            else:
                signals["momentum"] = 0.0
        else:
            signals["momentum"] = 0.0

        # --- ADX 趋势强度 ---
        adx_latest = adx_val[-1] if not np.isnan(adx_val[-1]) else 0
        if adx_latest >= 35:
            signals["adx_filter"] = 0.8
        elif adx_latest >= 25:
            signals["adx_filter"] = 0.3
        elif adx_latest >= 20:
            signals["adx_filter"] = 0.0
        else:
            signals["adx_filter"] = -0.3

        # ---------------------------------------------------------------
        # 3. 综合评分
        # ---------------------------------------------------------------
        total = sum(signals.get(k, 0) * weights.get(k, 0) for k in weights)
        total_score = total * 100  # 映射到 -100 ~ +100
        total_score = max(-100, min(100, total_score))

        # ---- 方向判定: 根据 ADX 分模式动态阈值 ----
        # ADX>=35 强趋势→25分即可进场跟随趋势
        # ADX 25-34 有趋势→35分正常要求
        # ADX<25 弱趋势/震荡→45分过滤噪音
        if adx_latest >= 35:
            effective_threshold = 25
        elif adx_latest >= 25:
            effective_threshold = 35
        else:
            effective_threshold = 45

        if total_score > effective_threshold:
            direction = Direction.BULLISH
        elif total_score < -effective_threshold:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        # ---- ADX 弱趋势过滤: 无趋势+中等信号→放弃 ----
        if adx_latest < 25 and abs(total_score) < effective_threshold + 5:
            direction = Direction.NEUTRAL

        # ---- EMA 方向倾向过滤(仅强趋势时启用) ----
        # 弱趋势/震荡市中不过滤，避免压制空头信号
        ema_bullish = not any(np.isnan(x) for x in (ema_f[-1], ema_m[-1], ema_s[-1])) and ema_f[-1] > ema_m[-1] > ema_s[-1]
        ema_bearish = not any(np.isnan(x) for x in (ema_f[-1], ema_m[-1], ema_s[-1])) and ema_f[-1] < ema_m[-1] < ema_s[-1]
        if adx_latest >= 30:
            # 强趋势中才做方向一致性过滤
            if ema_bullish and direction == Direction.BEARISH:
                if abs(total_score) < 55:
                    direction = Direction.NEUTRAL
            elif ema_bearish and direction == Direction.BULLISH:
                if abs(total_score) < 55:
                    direction = Direction.NEUTRAL

        # 信心度
        adx_bonus = 1.15 if adx_latest >= 35 else (1.05 if adx_latest >= 25 else 0.9)
        confidence = min(100, max(10, int(abs(total_score) * 0.9 * adx_bonus)))
        if direction != Direction.NEUTRAL and confidence < 25:
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
                stop = min(nearest_support - current_atr * 0.2, price - current_atr * 1.2)
            else:
                stop = price - current_atr * 1.2
            # 止盈：放在最近阻力附近，或 ATR 目标（收紧，减少超时）
            if nearest_resistance:
                tp1 = min(nearest_resistance - current_atr * 0.2, price + current_atr * 1.3)
                tp2 = min(nearest_resistance + current_atr * 0.3, price + current_atr * 2.2)
                tp3 = nearest_resistance + current_atr * 1.0
            else:
                tp1 = price + current_atr * 1.3
                tp2 = price + current_atr * 2.2
                tp3 = price + current_atr * 3.5
        elif direction == Direction.BEARISH:
            entry_low = price - current_atr * 0.3
            entry_high = price + current_atr * 0.3
            entry_opt = price
            if nearest_resistance:
                stop = max(nearest_resistance + current_atr * 0.2, price + current_atr * 1.2)
            else:
                stop = price + current_atr * 1.2
            if nearest_support:
                tp1 = max(nearest_support + current_atr * 0.2, price - current_atr * 1.3)
                tp2 = max(nearest_support - current_atr * 0.3, price - current_atr * 2.2)
                tp3 = nearest_support - current_atr * 1.0
            else:
                tp1 = price - current_atr * 1.3
                tp2 = price - current_atr * 2.2
                tp3 = price - current_atr * 3.5
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
