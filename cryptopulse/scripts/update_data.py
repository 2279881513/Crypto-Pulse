"""
CryptoPulse — 增量补全 K 线数据

读取已有 Parquet 文件的最新时间戳，从 OKX API 补全缺失数据，
去重合并后保存回 Parquet。支持一次性补全或持续运行。

Usage:
    python scripts/update_data.py                        # 全部周期，跑一次
    python scripts/update_data.py --intervals 1m,5m      # 只补 1m 和 5m
    python scripts/update_data.py --loop                 # 持续运行（每 60 秒检查一次）
    python scripts/update_data.py --loop --interval 300  # 每 5 分钟检查一次
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

# 让 Python 能找到 cryptopulse 包
import sys
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from cryptopulse.config import settings, DATA_DIR
from cryptopulse.core.data.okx_client import OKXRestClient


# ---------- 配置 ----------

SYMBOL = "BTC-USDT"
DATA_SUBDIR = "BTC-USDT-SWAP"  # Parquet 文件所在子目录

# 所有支持的周期（与现有文件名对应）
ALL_INTERVALS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D"]
# 但现有文件名叫 klines_1m.parquet, klines_1h.parquet（小写 h）
# OKX API 的 bar 参数用 "1H"/"4H"，文件名统一小写
INTERVAL_FILE_MAP = {
    "1m": "klines_1m.parquet",
    "5m": "klines_5m.parquet",
    "15m": "klines_15m.parquet",
    "30m": "klines_30m.parquet",
    "1H": "klines_1h.parquet",   # 文件名用 1h 而非 1H
    "4H": "klines_4h.parquet",
    "1D": "klines_1d.parquet",
}


# ---------- 工具函数 ----------


def bar_to_ms(bar: str) -> int:
    """将周期字符串转换为毫秒数"""
    unit = bar[-1]
    num = int(bar[:-1])
    if unit == "m":
        return num * 60 * 1000
    elif unit in ("h", "H"):
        return num * 3600 * 1000
    elif unit in ("d", "D"):
        return num * 86400_000
    raise ValueError(f"未知周期: {bar}")


def now_ms() -> int:
    """当前 UTC 时间戳（毫秒）"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# ---------- 核心逻辑 ----------


def read_existing(data_dir: Path, bar: str) -> pd.DataFrame:
    """读取已有的 Parquet 数据，返回 DataFrame（含 timestamp 列）"""
    fname = INTERVAL_FILE_MAP[bar]
    path = data_dir / fname
    if path.exists():
        df = pd.read_parquet(path)
        if not df.empty and "timestamp" in df.columns:
            return df
    return pd.DataFrame()


def candles_to_records(klines: list) -> list[dict]:
    """将 KLine 对象列表转为字典列表（不含 volume_quote 以兼容现有格式）"""
    return [
        {
            "timestamp": k.timestamp,
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
        }
        for k in klines
    ]


def merge_and_save(df_old: pd.DataFrame, new_records: list[dict],
                   data_dir: Path, bar: str) -> int:
    """
    合并新旧数据、去重、排序、保存。
    返回新增的条数。
    """
    if not new_records:
        return 0

    new_df = pd.DataFrame(new_records)

    if df_old.empty:
        combined = new_df
    else:
        combined = pd.concat([df_old, new_df], ignore_index=True)

    # 去重（按 timestamp 保留最后一条）
    before = len(combined)
    combined.drop_duplicates(subset=["timestamp"], keep="last", inplace=True)
    after = len(combined)
    added = after - (len(df_old) if not df_old.empty else 0)

    combined.sort_values("timestamp", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    fname = INTERVAL_FILE_MAP[bar]
    path = data_dir / fname
    combined.to_parquet(path, index=False)

    logger.info(f"  {bar}: {len(df_old):,} → {len(combined):,} 条 (新增 {added})")
    return added


def _download_range_fast(client: OKXRestClient, bar: str,
                          start_ts: int, end_ts: int) -> list:
    """
    快速下载一段历史数据。

    大缺口时，把时间范围切成多段并发下载。
    小缺口直接串行（用较短 sleep 替代 0.5s）。
    """
    # 预估批次数
    interval_ms = bar_to_ms(bar)
    total_candles = int((end_ts - start_ts) / interval_ms) + 1
    batches = max(1, total_candles // 1400)

    if batches <= 16:
        result = _download_sequential(client, bar, start_ts, end_ts, sleep_s=0.12)
    else:
        result = _download_concurrent(client, bar, start_ts, end_ts,
                                      num_segments=min(8, batches // 4))

    # 安全过滤：只保留范围内的数据
    result = [k for k in result if start_ts <= k.timestamp <= end_ts]
    return result


def _download_sequential(client: OKXRestClient, bar: str,
                          start_ts: int, end_ts: int,
                          sleep_s: float = 0.12) -> list:
    """串行分页下载，每批显示进度。

    内置多重安全阀：
      - 下载量超过预期 + 1 批后强制停止
      - 超过最大批次数强制停止
      - cursor 无变化（卡死）时自动退出
    """
    from cryptopulse.core.data.models import KLine

    interval_ms = bar_to_ms(bar)
    total_expected = max(1, (end_ts - start_ts) // interval_ms)

    # 安全阀：最多下载预期量 + 1440 根冗余
    max_to_download = total_expected + 1440
    max_batches = max(50, total_expected // 200 + 30)

    all_klines: list[KLine] = []
    cursor = end_ts
    prev_cursor = None
    batch_no = 0

    while cursor > start_ts:
        batch_no += 1
        got = len(all_klines)
        pct = min(100, got * 100 // total_expected) if total_expected else 0
        logger.info(f"    [{bar}] 第 {batch_no}/{max_batches} 批 | "
                    f"已获 {got:,}/{total_expected:,} ({pct}%)")

        # 安全阀 1：最多批次数
        if batch_no > max_batches:
            logger.warning(f"    [{bar}] 达到最大批次数 {max_batches}，强制停止")
            break

        # 安全阀 2：已获取足够数据
        if got >= max_to_download:
            logger.info(f"    [{bar}] 已获 {got:,} 根，超过预期，停止下载")
            break

        batch = client.get_history_candles(
            inst_id=SYMBOL, bar=bar, limit=1440, after=cursor,
        )
        if not batch:
            break

        all_klines.extend(batch)
        cursor = batch[0].timestamp

        # 安全阀 3：cursor 没变化 → 卡死
        if prev_cursor is not None and cursor == prev_cursor:
            logger.warning(f"    [{bar}] cursor 不变，可能卡死，停止")
            break
        prev_cursor = cursor

        time.sleep(sleep_s)

    # 去重 + 排序
    seen = set()
    unique = []
    for k in sorted(all_klines, key=lambda x: x.timestamp):
        if k.timestamp not in seen:
            seen.add(k.timestamp)
            unique.append(k)
    logger.info(f"    [{bar}] 下载完成: {len(unique)} 根"
                f" (共 {batch_no} 批)")
    return unique


def _download_concurrent(client: OKXRestClient, bar: str,
                          start_ts: int, end_ts: int,
                          num_segments: int = 8) -> list:
    """并发分片下载：把时间范围切段，每段各自串行下载"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    chunk_ms = (end_ts - start_ts) // num_segments
    segments = []
    for i in range(num_segments):
        s = start_ts + i * chunk_ms
        e = start_ts + (i + 1) * chunk_ms if i < num_segments - 1 else end_ts
        segments.append((s, e))

    logger.info(f"  {bar}: 分 {num_segments} 片并发下载...")

    all_results = []
    with ThreadPoolExecutor(max_workers=num_segments) as ex:
        fut_map = {
            ex.submit(_download_sequential, client, bar, s, e, 0.15): (s, e)
            for s, e in segments
        }
        for fut in as_completed(fut_map):
            seg = fut_map[fut]
            try:
                data = fut.result()
                all_results.extend(data)
                logger.info(f"    [片 {seg[0]}] 完成: {len(data)} 根")
            except Exception as e:
                logger.error(f"    [片 {seg[0]}] 失败: {e}")

    # 全局去重 + 排序
    seen = set()
    unique = []
    for k in sorted(all_results, key=lambda x: x.timestamp):
        if k.timestamp not in seen:
            seen.add(k.timestamp)
            unique.append(k)
    return unique


def _fill_end_gap(client: OKXRestClient, df_old: pd.DataFrame,
                   data_dir: Path, bar: str,
                   interval_ms: int, now: int) -> list[dict]:
    """补末尾缺口：从最新数据时间戳到现在的缺失数据"""
    latest_ts = df_old["timestamp"].max() if not df_old.empty else 0

    if latest_ts >= now - interval_ms * 2:
        return []  # 已是最新

    gap_ms = now - latest_ts
    expected_missing = int(gap_ms / interval_ms) + 1
    logger.info(f"  {bar}: 末尾缺 {expected_missing} 根 (从 {latest_ts} 到 {now})")

    if expected_missing <= 1500:
        recent = client.get_history_candles(
            inst_id=SYMBOL, bar=bar, limit=1440,
        )
        return candles_to_records(
            [k for k in recent if k.timestamp > latest_ts]
        )

    logger.info(f"  {bar}: 末尾缺口较大，启动分页下载...")
    all_klines = _download_range_fast(
        client, bar,
        start_ts=latest_ts + interval_ms,
        end_ts=now,
    )
    return candles_to_records(
        [k for k in all_klines if k.timestamp > latest_ts]
    )


def _fill_mid_gaps(client: OKXRestClient, df_old: pd.DataFrame,
                    data_dir: Path, bar: str,
                    interval_ms: int) -> list[dict]:
    """
    检测并填补数据中间的空缺。

    检查实际条数 vs 预期条数，如果差太多就扫描具体缺口位置，
    逐个下载补齐。每个缺口仅下载缺失时间段内的数据。
    """
    if df_old.empty:
        return []

    timestamps = df_old["timestamp"].values
    min_ts = timestamps[0]
    max_ts = timestamps[-1]

    # 预期从 min 到 max 应有的条数
    expected_len = int((max_ts - min_ts) / interval_ms) + 1
    actual_len = len(timestamps)

    if actual_len >= expected_len * 0.999:
        return []  # 数据完整

    logger.warning(f"  {bar}: 数据不完整 "
                   f"({actual_len:,}/{expected_len:,})，扫描缺口...")

    # 找相邻时间戳差值 > 1.5 倍 interval 的位置
    diffs = timestamps[1:] - timestamps[:-1]
    gap_indices = np.where(diffs > interval_ms * 1.5)[0]

    all_new_records = []
    for idx in gap_indices:
        gap_start = timestamps[idx] + interval_ms
        gap_end = timestamps[idx + 1] - interval_ms
        gap_count = int((gap_end - gap_start) / interval_ms) + 1
        logger.info(f"  {bar}: 发现中间缺口 {gap_count} 根 "
                    f"({gap_start} ~ {gap_end})")

        # 用快速下载（after 向后翻页）+ 范围过滤
        fill_klines = _download_range_fast(
            client, bar,
            start_ts=gap_start,
            end_ts=gap_end,
        )
        fill_klines = [k for k in fill_klines
                       if gap_start <= k.timestamp <= gap_end]

        if fill_klines:
            records = candles_to_records(fill_klines)
            all_new_records.extend(records)
            logger.info(f"    -> 已补齐 {len(records)} 根")
        else:
            logger.warning(f"    -> 缺口无数据可补")

    return all_new_records


def update_interval(client: OKXRestClient, data_dir: Path, bar: str) -> int:
    """
    更新单个周期的数据。

    策略：
      1. 补末尾缺口（最新数据到当前时间）
      2. 检查中间空缺（实际条数与预期条数不符时扫描补齐）
    """
    df_old = read_existing(data_dir, bar)
    interval_ms = bar_to_ms(bar)
    now = now_ms()

    total_added = 0

    # 1. 补末尾
    end_records = _fill_end_gap(client, df_old, data_dir, bar, interval_ms, now)
    if end_records:
        added = merge_and_save(df_old, end_records, data_dir, bar)
        total_added += added
        # 重新读取（因为文件变了）
        df_old = read_existing(data_dir, bar)

    # 2. 补中间空缺
    mid_records = _fill_mid_gaps(client, df_old, data_dir, bar, interval_ms)
    if mid_records:
        added = merge_and_save(df_old, mid_records, data_dir, bar)
        total_added += added

    if total_added == 0:
        logger.debug(f"  {bar}: 已是最新且完整")

    return total_added


def run_once(client: OKXRestClient, data_dir: Path,
             intervals: list[str]) -> dict[str, int]:
    """运行一轮补全，返回每周期的新增条数"""
    results = {}
    for bar in intervals:
        try:
            added = update_interval(client, data_dir, bar)
            results[bar] = added
        except Exception as e:
            logger.error(f"  {bar} 更新失败: {e}")
            results[bar] = -1
    return results


def run_loop(client: OKXRestClient, data_dir: Path,
             intervals: list[str], sleep_secs: int) -> None:
    """持续运行模式"""
    logger.info(f"🔄 持续运行模式，每 {sleep_secs}s 检查一次")
    while True:
        logger.info(f"--- 检查更新 ({datetime.now().isoformat()}) ---")
        results = run_once(client, data_dir, intervals)
        total = sum(v for v in results.values() if v > 0)
        if total:
            logger.info(f"✅ 本轮新增 {total} 条")
        else:
            logger.info("  无新增数据")
        time.sleep(sleep_secs)


# ---------- 主入口 ----------


def parse_args():
    parser = argparse.ArgumentParser(
        description="增量补全 K 线数据（从 OKX API）"
    )
    parser.add_argument(
        "--intervals",
        default=",".join(ALL_INTERVALS),
        help=f"周期列表，逗号分隔，默认全部 ({','.join(ALL_INTERVALS)})",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="持续运行模式",
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="持续运行时的检查间隔（秒），默认 60",
    )
    return parser.parse_args()


def setup_proxy() -> None:
    """从 settings 读取代理，设置 HTTP_PROXY / HTTPS_PROXY 环境变量"""
    proxy = settings.proxy
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        logger.info(f"代理已配置: {proxy}")
    else:
        logger.info("未配置代理（直连）")


def interactive_menu():
    """交互式菜单"""
    print("=" * 50)
    print("  📥 CryptoPulse 数据补全工具")
    print("=" * 50)
    print("  1. 补全一次（所有周期）")
    print("  2. 持续运行（每 60 秒检查）")
    print("  3. 持续运行（每 30 秒检查）")
    print("  4. 只补指定周期")
    print("  0. 退出")
    print("=" * 50)

    while True:
        choice = input("  ⚡ 请选择 [0-4]: ").strip()
        if choice == "1":
            return {"intervals": ALL_INTERVALS, "loop": False}
        elif choice == "2":
            return {"intervals": ALL_INTERVALS, "loop": True, "interval_sec": 60}
        elif choice == "3":
            return {"intervals": ALL_INTERVALS, "loop": True, "interval_sec": 30}
        elif choice == "4":
            print(f"  可用周期: {', '.join(ALL_INTERVALS)}")
            bars = input("  请输入周期（逗号分隔，如 1m,5m,1H）: ").strip()
            if bars:
                selected = [b.strip() for b in bars.split(",")]
                valid = [b for b in selected if b in INTERVAL_FILE_MAP]
                if valid:
                    return {"intervals": valid, "loop": False}
                print(f"  ❌ 无效周期，可用: {', '.join(ALL_INTERVALS)}")
            else:
                print("  ❌ 请输入周期")
        elif choice == "0":
            print("  再见!")
            exit(0)
        else:
            print("  ❌ 无效选择，请输入 0-4")


def main():
    # 无参数 → 交互式菜单
    if len(sys.argv) <= 1 or sys.argv[1].startswith("--interactive"):
        cfg = interactive_menu()
        intervals = cfg["intervals"]
        loop_mode = cfg["loop"]
        loop_interval = cfg.get("interval_sec", 60)
    else:
        args = parse_args()
        intervals = [s.strip() for s in args.intervals.split(",")]
        loop_mode = args.loop
        loop_interval = args.interval

        # 验证周期
        for bar in intervals:
            if bar not in INTERVAL_FILE_MAP:
                print(f"❌ 不支持的周期: {bar}，可选: {', '.join(ALL_INTERVALS)}")
                return

    setup_proxy()
    client = OKXRestClient()
    data_dir = DATA_DIR / DATA_SUBDIR
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"📥 CryptoPulse 数据补全")
    logger.info(f"   交易对: {SYMBOL}")
    logger.info(f"   周期: {', '.join(intervals)}")
    logger.info(f"   目录: {data_dir}")
    logger.info(f"   模式: {'持续运行' if loop_mode else '一次性'}")

    if loop_mode:
        run_loop(client, data_dir, intervals, loop_interval)
    else:
        run_once(client, data_dir, intervals)


if __name__ == "__main__":
    main()
