"""
CryptoPulse — 环形缓冲区（Ring Buffer）
维护最新 N 根 K 线的内存队列，支持向量化指标计算。

设计要点：
- 固定长度 FIFO，自动淘汰旧数据
- 实时数据推送更新最新一根（未确认）
- 新 K 线闭合时自动推入
- 与回测数据加载接口一致，确保离线/实时逻辑相同
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import pandas as pd

from cryptopulse.core.data.models import KLine


class KLineRingBuffer:
    """
    K 线环形缓冲区。

    维护最新 ``capacity`` 根 K 线。
    对外暴露 pandas DataFrame，供向量化指标库（TA-Lib / pandas-ta）使用。

    Usage:
        buf = KLineRingBuffer(capacity=200, interval="1m")
        buf.push(kline)          # 推送新 K 线
        buf.update(kline)        # 更新最新一根（未确认）
        df = buf.to_dataframe()  # 获取 DataFrame: [open, high, low, close, volume]
    """

    def __init__(self, capacity: int = 200, interval: str = "1m") -> None:
        assert capacity >= 10, "capacity 至少 10 根"
        self.capacity = capacity
        self.interval = interval
        self._klines: deque[KLine] = deque(maxlen=capacity)
        self._latest: Optional[KLine] = None  # 当前未确认的 K 线

    # ------------------------------------------------------------------
    # 推送 / 更新
    # ------------------------------------------------------------------

    def push(self, kline: KLine) -> None:
        """推送一条新的（已闭合的）K 线"""
        if self._klines and kline.timestamp <= self._klines[-1].timestamp:
            return  # 去重
        if self._latest and kline.timestamp == self._latest.timestamp:
            # 最新未确认的已确认
            kline.confirm = True
            self._latest = None
        self._klines.append(kline)

    def update(self, kline: KLine) -> None:
        """更新当前未闭合的 K 线"""
        if self._klines and kline.timestamp < self._klines[-1].timestamp:
            return
        if self._klines and kline.timestamp == self._klines[-1].timestamp:
            kline.confirm = True
            self._klines[-1] = kline
            self._latest = None
        else:
            self._latest = kline

    # ------------------------------------------------------------------
    # 数据导出
    # ------------------------------------------------------------------

    def to_dataframe(self, include_unconfirmed: bool = True) -> pd.DataFrame:
        """
        导出为 pandas DataFrame，列: [open, high, low, close, volume, timestamp]
        """
        data = list(self._klines)
        if include_unconfirmed and self._latest is not None:
            data.append(self._latest)

        records = [
            {
                "timestamp": k.timestamp,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
                "volume_quote": k.volume_quote,
            }
            for k in data
        ]
        df = pd.DataFrame(records)
        if not df.empty:
            df.set_index("timestamp", inplace=True)
        return df

    def to_array(self) -> tuple:
        """导出为 numpy 数组元组 (open, high, low, close, volume) 用于 TA-Lib"""
        df = self.to_dataframe()
        return (
            df["open"].values,
            df["high"].values,
            df["low"].values,
            df["close"].values,
            df["volume"].values,
        )

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @property
    def is_full(self) -> bool:
        return len(self._klines) >= self.capacity

    @property
    def current_count(self) -> int:
        return len(self._klines)

    @property
    def latest_close(self) -> Optional[float]:
        """最新收盘价"""
        if self._latest is not None:
            return self._latest.close
        if self._klines:
            return self._klines[-1].close
        return None

    @property
    def latest_kline(self) -> Optional[KLine]:
        """最新 K 线（未确认优先）"""
        return self._latest or (self._klines[-1] if self._klines else None)

    def __len__(self) -> int:
        return len(self._klines)

    def __repr__(self) -> str:
        return (
            f"KLineRingBuffer(interval={self.interval}, "
            f"filled={len(self._klines)}/{self.capacity}, "
            f"latest_close={self.latest_close})"
        )


class RingBufferManager:
    """
    管理多个周期的环形缓冲区。
    一个交易对在一种风格下会同时维护两个周期的缓冲区。
    """

    def __init__(self, short_intervals: tuple = ("1m", "5m"),
                 medium_intervals: tuple = ("4H", "1D"),
                 short_capacity: int = 200,
                 medium_capacity: int = 100) -> None:
        self.buffers: dict[str, KLineRingBuffer] = {}

        for interval in short_intervals:
            self.buffers[interval] = KLineRingBuffer(capacity=short_capacity, interval=interval)
        for interval in medium_intervals:
            self.buffers[interval] = KLineRingBuffer(capacity=medium_capacity, interval=interval)

    def get(self, interval: str) -> KLineRingBuffer:
        return self.buffers[interval]

    def push_kline(self, interval: str, kline: KLine) -> None:
        """推送已闭合 K 线到对应周期缓冲区"""
        if interval in self.buffers:
            self.buffers[interval].push(kline)

    def update_kline(self, interval: str, kline: KLine) -> None:
        """更新未闭合 K 线"""
        if interval in self.buffers:
            self.buffers[interval].update(kline)

    def all_dataframes(self, include_unconfirmed: bool = True) -> dict[str, pd.DataFrame]:
        """导出所有周期的 DataFrame"""
        return {
            interval: buf.to_dataframe(include_unconfirmed)
            for interval, buf in self.buffers.items()
        }
