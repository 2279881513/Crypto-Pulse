"""
CryptoPulse — 数据模型定义
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Interval(str, Enum):
    """K 线周期"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"

    @property
    def seconds(self) -> int:
        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1H": 3600,
            "4H": 14400,
            "1D": 86400,
        }
        return mapping[self.value]

    @property
    def for_short_term(self) -> bool:
        return self in (Interval.M1, Interval.M5)

    @property
    def for_medium_term(self) -> bool:
        return self in (Interval.H4, Interval.D1)


class SignalAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"  # 观望


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class KLine:
    """一根 K 线"""
    timestamp: int          # Unix 毫秒
    open: float
    high: float
    low: float
    close: float
    volume: float           # 成交量（币数）
    volume_quote: float     # 成交量（计价币）
    confirm: bool = True    # true=已确认(已收盘), false=未确认(实时)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2

    @classmethod
    def from_okx(cls, raw: list) -> "KLine":
        """从 OKX API 原始数据创建"""
        return cls(
            timestamp=int(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
            volume_quote=float(raw[6]),
            confirm=raw[8] == "1",
        )


@dataclass
class OrderBookLevel:
    """盘口一个档位"""
    price: float
    size: float
    orders_count: int = 0


@dataclass
class OrderBook:
    """订单簿快照"""
    ts: int
    bids: list[OrderBookLevel]  # 买盘（价格降序）
    asks: list[OrderBookLevel]  # 卖盘（价格升序）

    @classmethod
    def from_okx(cls, raw: dict) -> "OrderBook":
        """从 OKX books 推送构建"""
        ts = int(raw["ts"])
        bids = [OrderBookLevel(price=float(b[0]), size=float(b[1]), orders_count=int(b[2]))
                for b in raw.get("bids", [])]
        asks = [OrderBookLevel(price=float(a[0]), size=float(a[1]), orders_count=int(a[2]))
                for a in raw.get("asks", [])]
        return cls(ts=ts, bids=bids, asks=asks)


@dataclass
class Trade:
    """一笔成交"""
    trade_id: str
    ts: int
    price: float
    size: float
    side: str  # "buy" or "sell"


@dataclass
class Ticker:
    """实时 Ticker"""
    inst_id: str
    ts: int
    last: float
    best_bid: float
    best_ask: float
    vol_24h: float
    high_24h: float
    low_24h: float
    change_pct: float  # 24h 涨跌幅 %


@dataclass
class FundingRate:
    """资金费率"""
    inst_id: str
    funding_rate: float
    next_funding_rate: float  # 预测的下期费率
    funding_time: int
    premium: float  # 溢价


@dataclass
class OpenInterest:
    """持仓量"""
    inst_id: str
    oi: float          # 持仓量（张数/币数）
    oi_value: float    # 持仓量（USD 价值）
    ts: int


@dataclass
class MarkPrice:
    """标记价格"""
    inst_id: str
    mark_price: float
    ts: int


@dataclass
class TechnicalScore:
    """第一阶技术面评分结果"""
    direction: Direction
    score: float                     # -100 ~ +100
    indicators: dict[str, float]     # 各指标得分明细
    key_levels: dict[str, float]     # S/R 关键价位
    trend_strength: float            # ADX 或等效


@dataclass
class MicrostructureScore:
    """第二阶微观结构评分结果"""
    direction: Direction
    score: float                     # -1.0 ~ +1.0
    obi: float                       # 盘口不平衡度
    taker_ratio: float               # 主动成交比
    funding_assessment: str          # 费率评估文本
    oi_assessment: str               # OI 评估文本
    whale_alerts: list[dict]         # 大单预警
    confirmation: str                # confirmed / downgraded / vetoed


@dataclass
class AgentVote:
    """单个 Agent 的投票"""
    agent_name: str
    direction: Direction
    confidence: int                  # 0-100
    reasoning: str
    calibrated_confidence: float = 0.0


@dataclass
class TradingPlan:
    """最终交易计划"""
    action: SignalAction
    confidence: int                  # 0-100 最终信心分
    summary: str                     # 一句话结论
    
    entry_zone_low: float
    entry_zone_high: float
    entry_optimal: float
    
    stop_loss_hard: float
    trailing_activation: float       # 移动止损激活价
    
    take_profit_levels: list[dict]   # [{level, price, size_pct}]
    
    position_size_pct: float         # 建议仓位 %
    risk_reward_ratio: float
    
    # 理由摘要
    reasoning: dict[str, str]        # technical, microstructure, funding, ai_committee
    
    timestamp: int
    symbol: str
    style: str
