"""
CryptoPulse — 风险控制系统

提供止损冷却、AI 风控接口等功能。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Optional


class RiskManager:
    """风险控制管理器"""

    # 止损冷却时间（秒）
    SL_COOLDOWN = 300  # 5 分钟

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self._lock = Lock()
        self._state_file = state_file
        # 上次止损触发时间戳（秒）
        self._last_sl_trigger_time: float = 0
        self._sl_reason: str = ""
        # 活跃风控原因列表
        self._active_risk_reasons: list[dict] = []
        self._load_state()

    # ---- 持久化 ----

    def _load_state(self) -> None:
        if self._state_file and self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._last_sl_trigger_time = data.get("last_sl_time", 0)
                self._sl_reason = data.get("sl_reason", "")
                self._active_risk_reasons = data.get("active_risks", [])
            except Exception:
                pass

    def _save_state(self) -> None:
        if self._state_file:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(
                    {
                        "last_sl_time": self._last_sl_trigger_time,
                        "sl_reason": self._sl_reason,
                        "active_risks": self._active_risk_reasons[-20:],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    # ---- 止损风控 ----

    def trigger_stop_loss(self, reason: str = "") -> None:
        """
        记录止损触发事件。
        调用后系统进入冷却期，期间不允许开新仓。
        """
        with self._lock:
            now = time.time()
            self._last_sl_trigger_time = now
            self._sl_reason = reason
            self._active_risk_reasons.append(
                {
                    "type": "stop_loss",
                    "time": now,
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                    "reason": reason,
                }
            )
            self._save_state()

    def clear_stop_loss(self) -> None:
        """手动清除止损冷却状态"""
        with self._lock:
            self._last_sl_trigger_time = 0
            self._sl_reason = ""
            self._save_state()

    @property
    def in_sl_cooldown(self) -> bool:
        """是否处于止损冷却期"""
        with self._lock:
            if self._last_sl_trigger_time <= 0:
                return False
            elapsed = time.time() - self._last_sl_trigger_time
            return elapsed < self.SL_COOLDOWN

    @property
    def sl_cooldown_remaining(self) -> int:
        """止损冷却剩余秒数"""
        with self._lock:
            if self._last_sl_trigger_time <= 0:
                return 0
            remaining = self.SL_COOLDOWN - (time.time() - self._last_sl_trigger_time)
            return max(0, int(remaining))

    # ---- 风控检查 ----

    def can_open_new_position(self, direction: str = "") -> tuple[bool, str]:
        """
        检查是否允许开新仓。

        Returns:
            (allowed, reason_if_blocked)
        """
        reasons: list[str] = []

        # 1. 止损冷却
        if self.in_sl_cooldown:
            remaining = self.sl_cooldown_remaining
            m, s = divmod(remaining, 60)
            reasons.append(f"止损冷却中（剩余{m}分{s}秒）")

        # 2. AI 风控（占位）
        # TODO: 实现 AI 风控检测
        # ai_result = self.ai_risk_check(symbol, direction)
        # if not ai_result["pass"]:
        #     reasons.append(ai_result["reason"])

        if reasons:
            return False, "；".join(reasons)
        return True, ""

    # ---- AI 风控接口（占位） ----

    def ai_risk_check(
        self,
        symbol: str = "",
        direction: str = "",
        market_data: Optional[dict] = None,
    ) -> dict:
        """
        AI 风控检测接口（待实现）。

        Args:
            symbol: 交易对，如 "BTC-USDT"
            direction: "long" 或 "short"
            market_data: 市场数据（K线、深度等）

        Returns:
            {
                "pass": bool,           # 是否通过风控
                "confidence": float,    # 风险置信度 0-1
                "reason": str,          # 风控原因
                "details": dict,        # 详细分析
            }
        """
        # TODO: 接入 AI 风控模型
        _ = symbol, direction, market_data
        return {
            "pass": True,
            "confidence": 1.0,
            "reason": "AI风控未启用（占位符）",
            "details": {},
        }

    # ---- 状态查询 ----

    def get_risk_status(self) -> dict:
        """获取当前风控状态（用于前端展示）"""
        with self._lock:
            remaining = self.sl_cooldown_remaining
            m, s = divmod(remaining, 60)
            return {
                "in_sl_cooldown": self.in_sl_cooldown,
                "sl_cooldown_remaining": remaining,
                "sl_cooldown_display": f"{m}分{s}秒" if remaining > 0 else "",
                "sl_triggered": self._last_sl_trigger_time > 0,
                "last_sl_time": self._last_sl_trigger_time,
                "last_sl_time_str": (
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(self._last_sl_trigger_time),
                    )
                    if self._last_sl_trigger_time > 0
                    else ""
                ),
                "sl_reason": self._sl_reason,
                "active_risks": list(self._active_risk_reasons[-10:]),
            }


# ---- 模块单例 ----
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """获取全局 RiskManager 单例"""
    global _risk_manager
    if _risk_manager is None:
        from cryptopulse.config import DATA_DIR

        state_file = DATA_DIR / "risk_state.json"
        _risk_manager = RiskManager(state_file=state_file)
    return _risk_manager
