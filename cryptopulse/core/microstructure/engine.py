"""
CryptoPulse — 微观结构分析引擎
盘口不平衡度(OBI)、主动成交比(Taker Ratio)、大单检测
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MicroResult:
    """微观结构分析结果"""
    obi: float                    # 盘口不平衡度 -1~+1
    obi_signal: str               # 文字说明
    taker_ratio: float            # 主动成交比 0~1
    taker_signal: str
    whale_count: int              # 大单数量
    whale_signal: str
    total_score: float            # 综合评分 -1~+1
    confirmation: str             # confirmed / neutral / vetoed


class MicrostructureEngine:
    """
    微观结构分析引擎
    分析盘口深度、成交流、大单等数据，验证技术面信号方向。
    """

    def analyze(self, orderbook: dict | None,
                trades: list[dict] | None,
                whale_alerts: list[dict] | None = None) -> MicroResult:
        """综合分析所有微观数据"""

        # --- 1. 盘口不平衡度 OBI ---
        obi, obi_signal = self._calc_obi(orderbook)

        # --- 2. 主动成交比 ---
        taker_ratio, taker_signal = self._calc_taker_ratio(trades)

        # --- 3. 大单检测 ---
        whale_count, whale_signal = self._detect_whales(trades, whale_alerts)

        # --- 4. 综合评分 ---
        total = obi * 0.35 + (taker_ratio - 0.5) * 2 * 0.25 + \
                (whale_signal == "有大买单" and 0.5 or whale_signal == "有大卖单" and -0.5 or 0) * 0.15

        if total > 0.3:
            confirmation = "confirmed"
        elif total < -0.3:
            confirmation = "confirmed"
        else:
            confirmation = "neutral"

        return MicroResult(
            obi=round(obi, 3),
            obi_signal=obi_signal,
            taker_ratio=round(taker_ratio, 3),
            taker_signal=taker_signal,
            whale_count=whale_count,
            whale_signal=whale_signal,
            total_score=round(total, 3),
            confirmation=confirmation,
        )

    def _calc_obi(self, orderbook: dict | None) -> tuple[float, str]:
        """计算盘口不平衡度 OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)"""
        if not orderbook:
            return 0, "无盘口数据"

        try:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            if not bids or not asks:
                return 0, "盘口为空"

            # 取前 5 档，加权计算
            weights = [0.4, 0.25, 0.2, 0.1, 0.05]
            bid_vol = sum(float(b[1]) * w for b, w in zip(bids[:5], weights[:len(bids[:5])]))
            ask_vol = sum(float(a[1]) * w for a, w in zip(asks[:5], weights[:len(asks[:5])]))

            total = bid_vol + ask_vol
            if total == 0:
                return 0, "盘口无挂单"

            obi = (bid_vol - ask_vol) / total

            if obi > 0.3:
                signal = "买方主导，买单密集"
            elif obi > 0.1:
                signal = "买方略占优"
            elif obi < -0.3:
                signal = "卖方主导，卖单密集"
            elif obi < -0.1:
                signal = "卖方略占优"
            else:
                signal = "盘口平衡"

            return obi, signal

        except Exception:
            return 0, "盘口解析失败"

    def _calc_taker_ratio(self, trades: list[dict] | None) -> tuple[float, str]:
        """计算主动成交比 = 主动买单量 / 总成交量"""
        if not trades or len(trades) < 5:
            return 0.5, "成交数据不足"

        try:
            # 取最近 100 笔成交
            recent = trades[-100:]
            buy_vol = sum(float(t.get("size", 0)) for t in recent if t.get("side") == "buy")
            total_vol = sum(float(t.get("size", 0)) for t in recent)
            if total_vol == 0:
                return 0.5, "无有效成交"

            ratio = buy_vol / total_vol

            if ratio > 0.6:
                signal = "主动买盘占优，买方积极"
            elif ratio > 0.53:
                signal = "买方略积极"
            elif ratio < 0.4:
                signal = "主动卖盘占优，卖方积极"
            elif ratio < 0.47:
                signal = "卖方略积极"
            else:
                signal = "买卖均衡"

            return ratio, signal

        except Exception:
            return 0.5, "成交解析失败"

    def _detect_whales(self, trades: list[dict] | None,
                       whale_alerts: list[dict] | None = None) -> tuple[int, str]:
        """检测大单（Z-score 异常检测）"""
        if not trades or len(trades) < 20:
            return 0, "数据不足无法检测"

        try:
            volumes = [float(t.get("size", 0)) for t in trades[-200:]]
            if not volumes:
                return 0, "无成交数据"

            import numpy as np
            mean_v = float(np.mean(volumes))
            std_v = float(np.std(volumes))
            if std_v < 1e-10:
                return 0, "成交量无波动"

            whale_count = 0
            whale_buy_vol = 0
            whale_sell_vol = 0

            for t in trades[-100:]:
                v = float(t.get("size", 0))
                z = (v - mean_v) / std_v
                if z > 3:  # Z-score > 3 视为大单
                    whale_count += 1
                    if t.get("side") == "buy":
                        whale_buy_vol += v
                    else:
                        whale_sell_vol += v

            if whale_buy_vol > whale_sell_vol * 2:
                signal = "有大买单"
            elif whale_sell_vol > whale_buy_vol * 2:
                signal = "有大卖单"
            elif whale_count > 0:
                signal = f"检测到 {whale_count} 笔大单"
            else:
                signal = "无异常大单"

            return whale_count, signal

        except Exception:
            return 0, "大单检测异常"
