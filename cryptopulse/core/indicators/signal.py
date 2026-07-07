"""
CryptoPulse — 信号生成器

将技术指标评分 + 微观结构评分合并，生成最终交易计划。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from cryptopulse.core.data.models import Direction, SignalAction, TradingPlan
from cryptopulse.core.indicators import compute_indicators, score_indicators


@dataclass
class SignalResult:
    action: SignalAction
    confidence: int       # 0-100
    direction: Direction
    tech_score: float     # -100 ~ +100
    summary: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    atr: float
    position_pct: float
    risk_reward: float


def generate_signal(
    kline_data: dict[str, pd.DataFrame],
    ticker: Optional[dict] = None,
    style: str = "short_term",
) -> SignalResult:
    """
    从 K 线数据生成交易信号。

    Args:
        kline_data: {interval: DataFrame} 包含每个周期的 K 线
        ticker: 最新 ticker 数据
        style: "short_term" 或 "medium_term"

    Returns:
        SignalResult 包含完整交易计划
    """
    # 选取主周期和辅助周期
    if style == "short_term":
        main_interval, aux_interval = "1m", "5m"
        atr_multiplier_sl = 1.2
        atr_multiplier_tp = (1.3, 2.2, 3.5)
    else:
        main_interval, aux_interval = "4H", "1D"
        atr_multiplier_sl = 1.5
        atr_multiplier_tp = (2.0, 4.0, 7.0)

    # 计算指标
    main_df = kline_data.get(main_interval, pd.DataFrame())
    aux_df = kline_data.get(aux_interval, pd.DataFrame())

    if main_df.empty:
        return _neutral_signal("无K线数据")

    main_df = compute_indicators(main_df)
    aux_df = compute_indicators(aux_df) if not aux_df.empty else pd.DataFrame()

    # 主周期评分
    main_dir, main_score, main_details = score_indicators(main_df)

    # 辅助周期评分
    aux_dir, aux_score, aux_details = score_indicators(aux_df) if not aux_df.empty else (Direction.NEUTRAL, 0, {})

    # --- 周期共振判断 ---
    if main_dir == aux_dir and main_dir != Direction.NEUTRAL:
        resonance_bonus = 1.3  # 共振加分
    elif main_dir != aux_dir and main_dir != Direction.NEUTRAL and aux_dir != Direction.NEUTRAL:
        resonance_bonus = 0.5  # 分歧减分
    else:
        resonance_bonus = 1.0

    combined_score = main_score * 0.65 + aux_score * 0.35
    combined_score *= resonance_bonus

    # --- 方向判定 ---
    # 注意: score_indicators 内部已做 ADX 过滤(ADX<25时|score|<35变中性)
    # 且使用阈值30, 所以这里用15做宽松的二次筛选即可
    if combined_score > 15:
        action = SignalAction.LONG
        direction = Direction.BULLISH
    elif combined_score < -15:
        action = SignalAction.SHORT
        direction = Direction.BEARISH
    else:
        return _neutral_signal(f"评分不足: {combined_score:.1f}/100")

    # --- 计算具体点位 ---
    latest = main_df.iloc[-1]
    atr = latest.get("atr", 0)
    price = latest["close"]

    # 避免 ATR 为 0
    atr = max(atr, price * 0.002)  # 至少 0.2%

    if action == SignalAction.LONG:
        entry = price
        stop_loss = price - atr * atr_multiplier_sl
        tp1 = price + atr * atr_multiplier_tp[0]
        tp2 = price + atr * atr_multiplier_tp[1]
        tp3 = price + atr * atr_multiplier_tp[2]
    else:
        entry = price
        stop_loss = price + atr * atr_multiplier_sl
        tp1 = price - atr * atr_multiplier_tp[0]
        tp2 = price - atr * atr_multiplier_tp[1]
        tp3 = price - atr * atr_multiplier_tp[2]

    # 置信度 — 基于评分和ADX趋势强度
    abs_score = abs(combined_score)
    adx_val = main_details.get("adx", 30)
    adx_bonus = 1.15 if adx_val >= 35 else (1.05 if adx_val >= 25 else 0.9)

    if abs_score > 60:
        confidence = min(95, int(abs_score * 1.2 * adx_bonus))
    elif abs_score > 40:
        confidence = min(85, int(abs_score * 1.1 * adx_bonus))
    elif abs_score > 30:
        confidence = min(75, int(abs_score * 1.0 * adx_bonus))
    else:
        confidence = min(65, int(abs_score * 0.9 * adx_bonus))

    confidence = min(100, max(10, confidence))

    # 仓位建议（基于波动率和信心）
    vol_factor = max(0.3, min(1.0, 0.03 / (atr / price))) if atr > 0 else 0.5
    position = round(confidence / 100 * vol_factor * 30, 1)  # 最多 30%
    position = max(5, min(30, position))

    # 盈亏比
    risk = abs(entry - stop_loss)
    reward = abs(tp2 - entry)
    rr = round(reward / risk, 2) if risk > 0 else 1.0

    # 总结
    summary_parts = []
    if main_dir == aux_dir and main_dir != Direction.NEUTRAL:
        summary_parts.append(f"{main_interval}/{aux_interval}共振看{'涨' if action == SignalAction.LONG else '跌'}")
    else:
        summary_parts.append(f"{main_interval}{'看涨' if main_dir == Direction.BULLISH else '看跌' if main_dir == Direction.BEARISH else '中性'}")

    summary_parts.append(f"评分{combined_score:.0f}")
    summary_parts.append(f"ATR={atr:.1f}")
    adx_val = main_details.get("adx", 0)
    if adx_val >= 35:
        summary_parts.append("强趋势")
    elif adx_val >= 25:
        summary_parts.append("有趋势")
    summary = " ".join(summary_parts)

    return SignalResult(
        action=action,
        confidence=confidence,
        direction=direction,
        tech_score=round(combined_score, 1),
        summary=summary,
        entry=round(entry, 1),
        stop_loss=round(stop_loss, 1),
        take_profit_1=round(tp1, 1),
        take_profit_2=round(tp2, 1),
        take_profit_3=round(tp3, 1),
        atr=round(atr, 1),
        position_pct=position,
        risk_reward=rr,
    )


def _neutral_signal(reason: str) -> SignalResult:
    return SignalResult(
        action=SignalAction.NEUTRAL,
        confidence=0,
        direction=Direction.NEUTRAL,
        tech_score=0,
        summary=f"观望: {reason}",
        entry=0, stop_loss=0,
        take_profit_1=0, take_profit_2=0, take_profit_3=0,
        atr=0, position_pct=0, risk_reward=0,
    )


def format_signal(result: SignalResult) -> str:
    """将 SignalResult 格式化为可读的交易计划"""
    if result.action == SignalAction.NEUTRAL:
        return f"当前建议【观望】 {result.summary}"

    action_str = "做多" if result.action == SignalAction.LONG else "做空"
    lines = [
        f"{'='*50}",
        f"  CryptoPulse 交易信号",
        f"{'='*50}",
        f"  当前建议: 【{action_str}】",
        f"  信心评分: {result.confidence}/100",
        f"  技术评分: {result.tech_score:+.1f}",
        f"  {'='*40}",
        f"  入场区间: {result.entry:.1f}",
        f"  止盈 1:   {result.take_profit_1:.1f} (30%仓位)",
        f"  止盈 2:   {result.take_profit_2:.1f} (30%仓位)",
        f"  止盈 3:   {result.take_profit_3:.1f} (40%仓位)",
        f"  止损价:   {result.stop_loss:.1f}",
        f"  {'='*40}",
        f"  ATR(14):  {result.atr:.1f}",
        f"  建议仓位: {result.position_pct}%",
        f"  盈亏比:   {result.risk_reward}",
        f"  {'='*40}",
        f"  {result.summary}",
        f"{'='*50}",
    ]
    return "\n".join(lines)
