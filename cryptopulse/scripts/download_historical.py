"""
CryptoPulse — 历史数据下载脚本

用于回测数据准备。从 OKX REST API 下载指定交易对的 K 线数据，
保存为 Parquet 格式，供后续回测使用。

Usage:
    python scripts/download_historical.py --symbol BTC-USDT --intervals 1m,5m,4h,1d --start 2024-01-01
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from cryptopulse.config import DATA_DIR
from cryptopulse.core.data.okx_client import OKXRestClient


def ts_from_date(date_str: str) -> int:
    """将 '2024-01-01' 转换为 Unix 毫秒"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def main():
    parser = argparse.ArgumentParser(description="下载历史 K 线数据")
    parser.add_argument("--symbol", default="BTC-USDT", help="交易对")
    parser.add_argument("--intervals", default="1m,5m,4h,1d", help="周期，逗号分隔")
    parser.add_argument("--start", default="2024-01-01", help="开始日期")
    parser.add_argument("--end", default="", help="结束日期（默认今天）")
    parser.add_argument("--output", default="", help="输出目录（默认 data/）")
    args = parser.parse_args()

    intervals = [s.strip() for s in args.intervals.split(",")]
    start_ts = ts_from_date(args.start)
    end_ts = ts_from_date(args.end) if args.end else int(datetime.now(timezone.utc).timestamp() * 1000)
    output_dir = args.output or str(DATA_DIR)

    client = OKXRestClient()

    for bar in intervals:
        logger.info(f"📥 下载 {args.symbol} {bar} ({args.start} ~ {args.end or '现在'})")
        klines = client.download_full_history(
            inst_id=args.symbol,
            bar=bar,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        if not klines:
            logger.warning(f"⚠️ {bar}: 无数据")
            continue

        # 转换为 DataFrame
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
            for k in klines
        ]
        df = pd.DataFrame(records)
        df.set_index("timestamp", inplace=True)

        # 保存
        safe_symbol = args.symbol.replace("-", "_").lower()
        filepath = f"{output_dir}/{safe_symbol}_{bar}.parquet"
        df.to_parquet(filepath)
        logger.info(f"✅ 已保存: {filepath} ({len(df)} 根 K 线)")

    logger.info("🎉 全部完成!")


if __name__ == "__main__":
    main()
