"""
CryptoPulse — 输出格式化
将 SignalResult 转换为用户可读的交易建议
"""

from __future__ import annotations

from cryptopulse.core.data.models import Direction
from cryptopulse.core.indicators.engine import SignalResult


def format_signal(result: SignalResult, symbol: str, style: str) -> str:
    """格式化为用户可读的交易建议"""
    style_name = "短线" if style == "short_term" else "中线"
    timeframe = "1m/5m" if style == "short_term" else "4H/1D"

    # 方向符号
    if result.direction == Direction.BULLISH:
        action = "🟢 做多 (LONG)"
        emoji = "📈"
    elif result.direction == Direction.BEARISH:
        action = "🔴 做空 (SHORT)"
        emoji = "📉"
    else:
        action = "⚪ 观望 (NEUTRAL)"
        emoji = "⏸️"

    lines = []
    lines.append("=" * 56)
    lines.append(f"  {emoji} CryptoPulse 交易信号")
    lines.append(f"  {symbol} | {style_name}分析 ({timeframe})")
    lines.append("=" * 56)
    lines.append("")
    lines.append(f"  ▶ 当前建议：{action}")
    lines.append(f"  ▶ 信心评分：{result.confidence}/100")
    lines.append(f"  ▶ 技术总分：{result.score:+.0f}")
    lines.append(f"  ▶ 趋势强度：{'强趋势' if result.adx_value >= 25 else '震荡/弱趋势'} (ADX {result.adx_value:.1f})")
    lines.append("")
    lines.append(f"  ┌─ 入场区间")
    lines.append(f"  │  最优：{result.entry_optimal:.2f}")
    lines.append(f"  │  范围：{result.entry_zone_low:.2f} ~ {result.entry_zone_high:.2f}")
    lines.append(f"  │")
    lines.append(f"  ├─ 目标价位")

    if result.direction == Direction.BULLISH:
        lines.append(f"  │  止盈1：{result.take_profit_1:.2f}  (30%仓位)")
        lines.append(f"  │  止盈2：{result.take_profit_2:.2f}  (30%仓位)")
        lines.append(f"  │  止盈3：{result.take_profit_3:.2f}  (40%仓位 + 移动止损)")
        lines.append(f"  │")
        lines.append(f"  ├─ 止损")
        lines.append(f"  │  硬止损：{result.stop_loss:.2f}")
        tp_range = ((result.take_profit_1 - result.entry_optimal) /
                    (result.entry_optimal - result.stop_loss + 1e-10))
        lines.append(f"  │  盈亏比：1:{tp_range:.2f}")
    elif result.direction == Direction.BEARISH:
        lines.append(f"  │  止盈1：{result.take_profit_1:.2f}  (30%仓位)")
        lines.append(f"  │  止盈2：{result.take_profit_2:.2f}  (30%仓位)")
        lines.append(f"  │  止盈3：{result.take_profit_3:.2f}  (40%仓位 + 移动止损)")
        lines.append(f"  │")
        lines.append(f"  ├─ 止损")
        lines.append(f"  │  硬止损：{result.stop_loss:.2f}")
        tp_range = ((result.entry_optimal - result.take_profit_1) /
                    (result.stop_loss - result.entry_optimal + 1e-10))
        lines.append(f"  │  盈亏比：1:{tp_range:.2f}")
    else:
        lines.append(f"  │  止盈1：--  (观望)"
        )
        lines.append(f"  │  止盈2：--")
        lines.append(f"  │  止盈3：--")
        lines.append(f"  ├─ 止损")
        lines.append(f"  │  硬止损：--")

    lines.append("")
    lines.append(f"  └─ 核心理由")
    lines.append(f"     {result.summary}")
    lines.append("")
    lines.append("  指标明细：")
    for k, v in result.details.items():
        lines.append(f"    {k}: {v}")
    lines.append("")
    lines.append("  ⚠️ 本信号仅供参考，不构成投资建议。加密交易风险极高。")
    lines.append("=" * 56)

    return "\n".join(lines)
