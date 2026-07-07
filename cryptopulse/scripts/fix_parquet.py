"""
修复损坏的 Parquet 文件
删除所有损坏的 parquet 文件，然后重新下载。
"""
import sys
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

DATA_DIR = os.path.join(ROOT, "data", "BTC-USDT-SWAP")
ALL_INTERVALS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D"]

def check_and_fix():
    if not os.path.exists(DATA_DIR):
        print(f"数据目录不存在: {DATA_DIR}")
        return

    corrupted = []
    for bar in ALL_INTERVALS:
        fname = f"klines_{bar.lower()}.parquet"
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            print(f"  {bar}: 文件不存在")
            continue

        size = os.path.getsize(path)
        if size == 0:
            print(f"  {bar}: 空文件 (0 字节)，删除")
            os.remove(path)
            corrupted.append(bar)
            continue

        # 尝试读取验证
        try:
            import pandas as pd
            pd.read_parquet(path)
            print(f"  {bar}: 正常 ({size/1024/1024:.1f} MB)")
        except Exception as e:
            print(f"  {bar}: 损坏 ({e})，删除后重新下载")
            os.remove(path)
            corrupted.append(bar)

    if not corrupted:
        print("\n所有文件正常！")
        return

    print(f"\n已删除 {len(corrupted)} 个损坏文件: {', '.join(corrupted)}")
    print("开始重新下载...\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT
    script_path = os.path.join(ROOT, "scripts", "update_data.py")
    result = subprocess.run(
        [sys.executable, script_path, "--intervals", ",".join(corrupted)],
        cwd=ROOT, env=env,
    )
    if result.returncode == 0:
        print("\n修复完成！")
    else:
        print(f"\nupdate_data 执行失败 (返回码 {result.returncode})")

if __name__ == "__main__":
    check_and_fix()
