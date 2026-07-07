"""
重刷最近 7 天的 K 线数据
删除本地 parquet 中最近 7 天的数据，然后调用 update_data 重新下载补全。
"""
import sys
import os
import subprocess
from datetime import datetime, timezone

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd

DATA_DIR = os.path.join(ROOT, "data", "BTC-USDT-SWAP")
ALL_INTERVALS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D"]

def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def refresh():
    now = now_ms()
    seven_days_ago = now - 7 * 86400_000

    if not os.path.exists(DATA_DIR):
        print(f"数据目录不存在: {DATA_DIR}")
        return

    total_removed = 0
    for bar in ALL_INTERVALS:
        fname = f"klines_{bar.lower()}.parquet"
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            print(f"  {bar}: 文件不存在，跳过")
            continue

        df = pd.read_parquet(path)
        before = len(df)
        if df.empty:
            continue

        remove_count = len(df[df["timestamp"] >= seven_days_ago])
        total_removed += remove_count
        if remove_count == 0:
            print(f"  {bar}: 最近7天无数据")
            continue

        df = df[df["timestamp"] < seven_days_ago].copy()
        df.to_parquet(path, index=False)
        print(f"  {bar}: 删 {remove_count} 条，剩 {len(df)} 条")

    if total_removed == 0:
        print("最近7天没有数据可删除")
        return

    print(f"\n已删除 {total_removed} 条，开始重新下载...\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT
    script_path = os.path.join(ROOT, "scripts", "update_data.py")
    result = subprocess.run(
        [sys.executable, script_path, "--intervals", ",".join(ALL_INTERVALS)],
        cwd=ROOT, env=env,
    )
    if result.returncode == 0:
        print("刷新完成！")
    else:
        print(f"update_data 执行失败 (返回码 {result.returncode})")

if __name__ == "__main__":
    refresh()
