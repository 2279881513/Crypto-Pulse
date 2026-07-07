#!/usr/bin/env python3
"""
暴力优化脚本 — 自动遍历参数组合，寻找最佳策略配置
用法: python optimize.py [--days 7]
"""
import argparse, itertools, sys, os, time, json
from pathlib import Path
import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent
# 添加项目根目录（cryptopulse 的父目录）使其成为可导入包
sys.path.insert(0, str(_root.parent))
sys.path.insert(0, str(_root / "core" / "indicators"))
from cryptopulse.core.indicators.calculations import sma, emma, rsi, atr, adx, bollinger, macd, obv
from cryptopulse.core.indicators.engine import TechnicalSignalEngine

DATA_DIR = _root / "data"
FEE_RATE = 0.0005  # 0.05% per side

def load_data(symbol="BTC-USDT-SWAP", days=7):
    """加载1m和5m数据"""
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - days * 86400 * 1000
    df1 = pd.read_parquet(DATA_DIR / symbol / "klines_1m.parquet")
    df1 = df1[df1["timestamp"] >= start_ts].reset_index(drop=True)
    try:
        df5 = pd.read_parquet(DATA_DIR / symbol / "klines_5m.parquet")
        df5 = df5[df5["timestamp"] >= start_ts].reset_index(drop=True)
    except:
        df5 = None
    return df1, df5

def compute_indicators(df1, df5, engine):
    """计算所有技术指标"""
    close = df1["close"].values.astype(float)
    high = df1["high"].values.astype(float)
    low = df1["low"].values.astype(float)
    op = df1["open"].values.astype(float)
    vol = df1["volume"].values.astype(float)
    
    all_ema_f = emma(close, engine.ema_fast)
    all_ema_m = emma(close, engine.ema_mid)
    all_ema_s = emma(close, engine.ema_slow)
    all_macd_l, all_macd_s, all_macd_hist = macd(close, engine.macd_fast, engine.macd_slow, engine.macd_signal)
    all_rsi = rsi(close, engine.rsi_period)
    all_bb_u, all_bb_m, all_bb_l = bollinger(close, engine.bb_period, engine.bb_std)
    all_atr = atr(high, low, close, 14)
    all_adx = adx(high, low, close, engine.adx_period)
    all_obv = obv(close, vol)
    all_vol_ma20 = sma(vol, 20)
    
    # 5m 数据
    ema_f5 = ema_m5 = ema_s5 = adx5 = rsi5 = macd_h5 = c5 = idx_map = None
    if df5 is not None:
        c5 = df5["close"].values.astype(float)
        h5 = df5["high"].values.astype(float)
        l5 = df5["low"].values.astype(float)
        v5 = df5["volume"].values.astype(float)
        ema_f5 = emma(c5, engine.ema_fast)
        ema_m5 = emma(c5, engine.ema_mid)
        ema_s5 = emma(c5, engine.ema_slow)
        adx5 = adx(h5, l5, c5, engine.adx_period)
        rsi5 = rsi(c5, engine.rsi_period)
        _, _, macd_h5 = macd(c5, engine.macd_fast, engine.macd_slow, engine.macd_signal)
        # 1m→5m 索引映射
        ts1 = df1["timestamp"].values
        ts5 = df5["timestamp"].values
        idx_map = np.searchsorted(ts5, ts1, side="right") - 1
        idx_map[idx_map < 0] = 0
    
    return (close, high, low, op, vol, all_ema_f, all_ema_m, all_ema_s,
            all_macd_hist, all_rsi, all_bb_u, all_bb_m, all_bb_l,
            all_atr, all_adx, all_obv, all_vol_ma20,
            ema_f5, ema_m5, ema_s5, adx5, rsi5, macd_h5, c5, idx_map)

def compute_signal(i, close, high, low, vol, ema_f, ema_m, ema_s,
                   macd_h, rsi_v, bb_u, bb_m, bb_l, adx_v,
                   ema_f5, idx5, has5,
                   rsi_os, rsi_ob, adx_min, use_ema):
    """参数化的信号计算"""
    price = close[i]
    adx_l = adx_v if not np.isnan(adx_v) else 0
    
    # BB 位置
    at_bb_lower = not np.isnan(bb_u) and price <= bb_l + (bb_m - bb_l) * 0.3
    at_bb_upper = not np.isnan(bb_u) and price >= bb_u - (bb_u - bb_m) * 0.3
    
    d = "neutral"; score = 0
    
    # EMA 趋势
    ema_up = not np.isnan(ema_f) and price > ema_f
    ema_down = not np.isnan(ema_f) and price < ema_f
    
    # 做多
    is_os = not np.isnan(rsi_v) and rsi_v <= rsi_os
    if is_os and at_bb_lower and adx_l >= adx_min:
        can_long = True
        if use_ema and not ema_up and adx_l >= 35:
            can_long = False
        if can_long:
            d = "bullish"; score = 60
    
    # 做空
    if d == "neutral":
        is_ob = not np.isnan(rsi_v) and rsi_v >= rsi_ob
        if is_ob and at_bb_upper and adx_l >= adx_min:
            can_short = True
            if use_ema and not ema_down and adx_l >= 35:
                can_short = False
            if can_short:
                d = "bearish"; score = -60
    
    return d, score

def run_backtest(close, high, low, op, vol, 
                 ema_f, ema_m, ema_s, macd_h, rsi_v,
                 bb_u, bb_m, bb_l, atr_v, adx_v,
                 ema_f5, idx5_map,
                 rsi_os, rsi_ob, adx_min, use_ema,
                 tp_mult, sl_mult, lookahead, min_bars=200):
    """运行回测"""
    n = len(close)
    trades = []
    
    for i in range(min_bars, n - lookahead):
        has5 = idx5_map is not None and i < len(idx5_map) and idx5_map[i] >= 0
        idx5 = idx5_map[i] if has5 else -1
        ef5 = ema_f5[idx5] if has5 and not np.isnan(ema_f5[idx5]) else None
        
        d, score = compute_signal(i, close, high, low, vol,
                                   ema_f[i], ema_m[i], ema_s[i],
                                   macd_h[i], rsi_v[i], bb_u[i], bb_m[i], bb_l[i], adx_v[i],
                                   ef5, idx5, has5,
                                   rsi_os, rsi_ob, adx_min, use_ema)
        
        if d == "neutral":
            continue
        
        entry_p = close[i]
        atr_e = atr_v[i] if not np.isnan(atr_v[i]) else close[i] * 0.005
        
        if d == "bullish":
            sl = entry_p - atr_e * sl_mult
            tp = entry_p + atr_e * tp_mult
        else:
            sl = entry_p + atr_e * sl_mult
            tp = entry_p - atr_e * tp_mult
        
        # 验证出场
        correct = False
        exit_p = close[i + lookahead]
        exit_reason = "超时"
        future_end = min(i + lookahead, n - 1)
        
        for j in range(i + 1, future_end + 1):
            bh, bl = high[j], low[j]
            if d == "bullish":
                if bh >= tp:
                    exit_p = tp; correct = True; exit_reason = "止盈"; break
                if bl <= sl:
                    exit_p = sl; exit_reason = "止损"; break
            else:
                if bl <= tp:
                    exit_p = tp; correct = True; exit_reason = "止盈"; break
                if bh >= sl:
                    exit_p = sl; exit_reason = "止损"; break
        
        if exit_reason == "超时":
            if d == "bullish":
                correct = exit_p > entry_p
            else:
                correct = exit_p < entry_p
        
        pnl = (exit_p / entry_p - 1) * (1 if d == "bullish" else -1) * 100
        trades.append({"correct": correct, "pnl": pnl, "reason": exit_reason})
    
    return trades

def score_result(trades):
    """计算综合评分"""
    total = len(trades)
    if total == 0:
        return {"trades": 0, "accuracy": 0, "profit_factor": 0, "net_pnl": 0, "score": -999}
    
    correct = sum(1 for t in trades if t["correct"])
    accuracy = correct / total * 100
    
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    
    total_pnl = sum(t["pnl"] for t in trades)
    total_fee = total * FEE_RATE * 2 * 100
    net_pnl = total_pnl - total_fee
    
    profit_factor = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else 0
    
    tp_count = sum(1 for t in trades if t["reason"] == "止盈")
    sl_count = sum(1 for t in trades if t["reason"] == "止损")
    
    # 综合评分: 准确率 × 盈亏比 × √交易数/50 × (1 + 净利/20)
    # 鼓励足够交易量+高质量信号
    trade_factor = (total / 50) ** 0.5
    pnl_factor = max(0, 1 + net_pnl / 20)
    composite = accuracy * profit_factor * trade_factor * pnl_factor if net_pnl > -90 else 0
    # 交易太少直接惩罚
    if total < 20:
        composite *= 0.2
    
    return {
        "trades": total, "accuracy": round(accuracy, 1),
        "profit_factor": round(profit_factor, 2),
        "net_pnl": round(net_pnl, 2),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "tp": tp_count, "sl": sl_count,
        "score": round(composite, 1)
    }

def main():
    parser = argparse.ArgumentParser(description="暴力优化策略参数")
    parser.add_argument("--days", type=int, default=7, help="回测天数")
    parser.add_argument("--top", type=int, default=10, help="显示前N个结果")
    args = parser.parse_args()
    
    print(f"加载数据 ({args.days}天)...")
    df1, df5 = load_data(days=args.days)
    print(f"  1m数据: {len(df1)} 行")
    if df5 is not None:
        print(f"  5m数据: {len(df5)} 行")
    
    engine = TechnicalSignalEngine()
    inds = compute_indicators(df1, df5, engine)
    close, high, low, op, vol, ema_f, ema_m, ema_s = inds[:8]
    macd_h, rsi_v, bb_u, bb_m, bb_l = inds[8:13]
    atr_v, adx_v = inds[13:15]
    ema_f5 = inds[18]
    idx5_map = inds[24]
    
    # 参数网格
    param_grid = {
        "rsi_os": [25, 30, 35, 40],
        "rsi_ob": [70, 75, 80],
        "adx_min": [10, 15, 20],
        "tp_mult": [3.0, 4.0, 5.0, 6.0],
        "sl_mult": [1.0, 1.5, 2.0],
        "lookahead": [240, 360, 480],
        "use_ema": [0, 1],
    }
    
    keys = list(param_grid.keys())
    total_combos = np.prod([len(param_grid[k]) for k in keys])
    print(f"\n参数组合总数: {total_combos}")
    print("参数:", " ".join(f"{k}={param_grid[k]}" for k in keys))
    print()
    
    results = []
    start = time.time()
    combo = 0
    
    for values in itertools.product(*[param_grid[k] for k in keys]):
        params = dict(zip(keys, values))
        combo += 1
        
        trades = run_backtest(
            close, high, low, op, vol,
            ema_f, ema_m, ema_s, macd_h, rsi_v,
            bb_u, bb_m, bb_l, atr_v, adx_v,
            ema_f5, idx5_map,
            params["rsi_os"], params["rsi_ob"], params["adx_min"],
            bool(params["use_ema"]),
            params["tp_mult"], params["sl_mult"], params["lookahead"]
        )
        
        r = score_result(trades)
        r.update(params)
        results.append(r)
        
        elapsed = time.time() - start
        eta = elapsed / combo * (total_combos - combo) if combo > 0 else 0
        sys.stdout.write(f"\r[{combo}/{total_combos}] 交易{r['trades']:3d}笔 准确率{r['accuracy']:4.1f}% 盈亏比{r['profit_factor']:.2f} 净利{r['net_pnl']:5.1f}% 综合{r['score']:5.1f} | ETA {eta:.0f}s    ")
        sys.stdout.flush()
    
    print(f"\n\n完成! 耗时 {time.time()-start:.0f}秒")
    
    # 排序
    results.sort(key=lambda r: r["score"], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"TOP {args.top} 最佳参数组合")
    print(f"{'='*80}")
    print(f"{'排名':>4} {'综合分':>6} {'准确率':>6} {'盈亏比':>6} {'净利%':>7} {'交易':>5} {'RSI卖':>5} {'RSI买':>5} {'ADX':>4} {'TP':>4} {'SL':>4} {'窗':>4} {'EMA':>4}")
    print("-"*80)
    
    for i, r in enumerate(results[:args.top]):
        ema_txt = "开" if r["use_ema"] else "关"
        print(f"{i+1:>4} {r['score']:>6.1f} {r['accuracy']:>5.1f}% {r['profit_factor']:>5.2f} {r['net_pnl']:>6.1f}% {r['trades']:>5} {r['rsi_os']:>4} {r['rsi_ob']:>4} {r['adx_min']:>3} {r['tp_mult']:>3.1f} {r['sl_mult']:>3.1f} {r['lookahead']:>4} {ema_txt:>3}")
        if i == 0:
            print(f"  → {r['trades']}笔交易 {r['tp']}止盈/{r['sl']}止损 平均盈{r['avg_win']}% 平均亏{r['avg_loss']}%")
    
    # 保存结果
    out = _root / "data" / "optimize_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n结果已保存到 {out}")

if __name__ == "__main__":
    main()
