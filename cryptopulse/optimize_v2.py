#!/usr/bin/env python3
"""
暴力优化脚本 v2 — 多进程并行
用法: python optimize_v2.py [--days 7] [--workers 0]
"""
import argparse, itertools, sys, os, time, json, multiprocessing as mp
from pathlib import Path
import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_root.parent))
sys.path.insert(0, str(_root / "core" / "indicators"))
from cryptopulse.core.indicators.calculations import sma, emma, rsi, atr, adx, bollinger, macd, obv
from cryptopulse.core.indicators.engine import TechnicalSignalEngine

DATA_DIR = _root / "data"
FEE_RATE = 0.0005

def load_data(symbol="BTC-USDT-SWAP", days=7):
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
    close = df1["close"].values.astype(float)
    high = df1["high"].values.astype(float)
    low = df1["low"].values.astype(float)
    vol = df1["volume"].values.astype(float)
    fe = emma(close, engine.ema_fast)
    _, _, mh = macd(close, engine.macd_fast, engine.macd_slow, engine.macd_signal)
    rs = rsi(close, engine.rsi_period)
    bu, bm, bl = bollinger(close, engine.bb_period, engine.bb_std)
    av = atr(high, low, close, 14)
    ad = adx(high, low, close, engine.adx_period)
    ef5 = idxm = None
    if df5 is not None:
        c5 = df5["close"].values.astype(float)
        h5 = df5["high"].values.astype(float)
        l5 = df5["low"].values.astype(float)
        ef5 = emma(c5, engine.ema_fast)
        ad5 = adx(h5, l5, c5, engine.adx_period)
        _, _, m5 = macd(c5, engine.macd_fast, engine.macd_slow, engine.macd_signal)
        idxm = np.searchsorted(df5["timestamp"].values, df1["timestamp"].values, side="right") - 1
        idxm[idxm < 0] = 0
    vm = sma(vol, 20)
    return close, high, low, vol, fe, mh, rs, bu, bm, bl, av, ad, ef5, idxm, vm

def run_one(p):
    """p = (params_dict, data_tuple)"""
    pr, dt = p
    close, high, low, vol, ema_f, macd_h, rsi_v, bb_u, bb_m, bb_l, atr_v, adx_v, ema_f5, idx_map, vol_ma20 = dt
    n = len(close); look = pr["lookahead"]; min_b = 200; trades = []
    for i in range(min_b, n - look):
        price = close[i]; al = adx_v[i] if not np.isnan(adx_v[i]) else 0
        bbiu, bmi, bli = bb_u[i], bb_m[i], bb_l[i]
        abl = not np.isnan(bbiu) and price <= bli + (bmi - bli) * 0.3
        abu = not np.isnan(bbiu) and price >= bbiu - (bbiu - bmi) * 0.3
        os_ = not np.isnan(rsi_v[i]) and rsi_v[i] <= pr["rsi_os"]
        ob_ = not np.isnan(rsi_v[i]) and rsi_v[i] >= pr["rsi_ob"]
        d = "neutral"
        if os_ and abl and al >= pr["adx_min"]:
            ek = True
            if pr["use_ema"] and al >= 35:
                ek = not np.isnan(ema_f[i]) and price > ema_f[i]
            if ek:
                cf = min(100, max(30, int(55 + al * 0.5)))
                if cf >= 35:
                    d = "bullish"
                    if pr.get("use_macd",0) and not np.isnan(macd_h[i]) and macd_h[i] < 0:
                        d = "neutral"
                    if d!="neutral" and pr.get("use_volume",0):
                        vr = vol[i]/vol_ma20[i] if vol_ma20[i]>0 else 0
                        if vr < 1.2: d = "neutral"
        if d == "neutral" and ob_ and abu and al >= pr["adx_min"]:
            ek = True
            if pr["use_ema"] and al >= 35:
                ek = not np.isnan(ema_f[i]) and price < ema_f[i]
            if ek:
                cf = min(100, max(30, int(55 + al * 0.5)))
                if cf >= 35:
                    d = "bearish"
                    if pr.get("use_macd",0) and not np.isnan(macd_h[i]) and macd_h[i] > 0:
                        d = "neutral"
                    if d!="neutral" and pr.get("use_volume",0):
                        vr = vol[i]/vol_ma20[i] if vol_ma20[i]>0 else 0
                        if vr < 1.2: d = "neutral"
        if d == "neutral": continue
        ep = price; ae = atr_v[i] if not np.isnan(atr_v[i]) else price * 0.005
        sm, tm = pr["sl_mult"], pr["tp_mult"]
        sl = ep - ae * sm if d == "bullish" else ep + ae * sm
        tp = ep + ae * tm if d == "bullish" else ep - ae * tm
        correct = False; xp = close[n-1]; xr = "超时"
        fe = min(i + look, n - 1)
        for j in range(i+1, fe+1):
            bh, bll = high[j], low[j]
            if d == "bullish":
                if bh >= tp: xp = tp; correct = True; xr = "止盈"; break
                if bll <= sl: xp = sl; xr = "止损"; break
            else:
                if bll <= tp: xp = tp; correct = True; xr = "止盈"; break
                if bh >= sl: xp = sl; xr = "止损"; break
        if xr == "超时": correct = xp > ep if d == "bullish" else xp < ep
        pnl = (xp/ep - 1) * (1 if d == "bullish" else -1) * 100
        trades.append({"c": correct, "p": pnl})
    t = len(trades)
    if t == 0:
        return {"t":0,"a":0,"pf":0,"net":0,"s":-999}
    c = sum(1 for x in trades if x["c"])
    a = c/t*100; w = [x for x in trades if x["p"]>0]; l = [x for x in trades if x["p"]<=0]
    tp = sum(x["p"] for x in trades); tf = t * FEE_RATE * 2 * 100; net = tp - tf
    pf = abs(sum(x["p"] for x in w) / max(1e-10, abs(sum(x["p"] for x in l))))
    aw = sum(x["p"] for x in w)/len(w) if w else 0
    al = sum(x["p"] for x in l)/len(l) if l else 0
    # 综合评分: 净利润优先（正净利最重要）
    trade_quality = min(t / 30, 1.0)  # 30笔以上算充分
    sc = net * 10 * trade_quality + pf * 2 + a * 0.3
    if t < 15: sc = -999  # 太少交易不统计
    res = {"t":t,"a":round(a,1),"pf":round(pf,2),"net":round(net,2),
           "aw":round(aw,2),"al":round(al,2),"s":round(sc,1)}
    res.update(pr)
    return res

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    nw = args.workers or mp.cpu_count()

    print(f"加载数据 ({args.days}天)...")
    df1, df5 = load_data(days=args.days)
    print(f"  1m: {len(df1)}行, 5m: {len(df5)}行" if df5 is not None else f"  1m: {len(df1)}行")
    engine = TechnicalSignalEngine()
    dt = compute_indicators(df1, df5, engine)

    pg = {"rsi_os":[25,30,35],"rsi_ob":[75,80],"adx_min":[10,15],
          "tp_mult":[3.0,4.0,5.0],"sl_mult":[1.5,2.0],
          "lookahead":[480],"use_ema":[0,1],
          "use_macd":[0,1],"use_volume":[0,1]}
    ks = list(pg.keys())
    combos = [dict(zip(ks, vs)) for vs in itertools.product(*pg.values())]
    total = len(combos)
    print(f"\n组合: {total} | 进程: {nw}")
    print("参数:", " ".join(f"{k}={pg[k]}" for k in ks), "\n")

    tasks = [(c, dt) for c in combos]
    start = time.time()
    results = []
    with mp.Pool(nw) as pool:
        done = 0
        for r in pool.imap_unordered(run_one, tasks, chunksize=4):
            results.append((r, r["s"]))
            done += 1
            if done % 50 == 0 or done == total:
                el = time.time() - start
                eta = el/done*(total-done) if done else 0
                sys.stdout.write(f"\r[{done}/{total}] ETA {eta:.0f}s  最新: 交易{r['t']}笔 准确率{r['a']}% 盈亏比{r['pf']}  ")
                sys.stdout.flush()

    print(f"\n\n完成! {time.time()-start:.0f}秒 ({total/max(1,time.time()-start):.0f}组/秒)")

    results.sort(key=lambda x: x[1], reverse=True)
    print(f"\n{'='*70}")
    print(f"TOP {args.top}")
    print(f"{'='*70}")
    print(f"{'综合':>5} {'准确率':>5} {'盈亏比':>5} {'净利%':>7} {'交易':>4} {'RSI卖':>3} {'RSI买':>3} {'ADX':>2} {'TP':>3} {'SL':>3} {'窗':>4} {'EMA':>3} {'MACD':>4} {'VOL':>3}")
    print("-"*55)
    for r, _ in results[:args.top]:
        et = "开" if r.get("use_ema",0) else "关"
        et = "开" if r.get("use_ema",0) else "关"
        mt = "开" if r.get("use_macd",0) else "关"
        vt = "开" if r.get("use_volume",0) else "关"
        print(f"{r['s']:>5.0f} {r['a']:>5.1f}% {r['pf']:>5.2f} {r['net']:>6.1f}% {r['t']:>4} {r['rsi_os']:>3} {r['rsi_ob']:>3} {r['adx_min']:>2} {r['tp_mult']:>3.1f} {r['sl_mult']:>3.1f} {r['lookahead']:>4} {et:>3} {mt:>4} {vt:>3}")

    out = _root / "data" / "optimize_results.json"
    with open(out, "w") as f:
        json.dump([r for r,_ in results], f, indent=2)
    print(f"\n保存到 {out}")

if __name__ == "__main__":
    main()
