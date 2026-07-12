"""
CryptoPulse — Flask Web UI
直接使用 requests 调用 OKX REST API（带代理支持）
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from flask import Flask, render_template, jsonify, request, Response

from cryptopulse.core.risk import get_risk_manager

# ---- Risk Manager ----
risk_mgr = get_risk_manager()


# ---- NumPy JSON 编码器（防止 bool_/int64/float64 导致 jsonify 报错） ----
class _NumpyProvider(Flask.json_provider_class):
    def dumps(self, obj, **kwargs):
        return super().dumps(_convert_numpy(obj), **kwargs)


def _convert_numpy(obj):
    """递归地将 numpy 类型转换为原生 Python 类型"""
    if isinstance(obj, dict):
        return {k: _convert_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_numpy(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


app = Flask(__name__)
app.json_provider_class = _NumpyProvider
app.json = _NumpyProvider(app)

# 代理配置
PROXY = os.environ.get("PROXY", "") or os.environ.get("HTTP_PROXY", "") or ""

LOG_FILE = _root / "data" / "cryptopulse.log"


def _log_event(event: str, data: dict = None) -> None:
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = {"ts": ts, "event": event}
        if data:
            entry["data"] = data
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _okx_get(path: str, params: dict = None) -> dict | None:
    """通过 requests 调用 OKX API，自动重试 demo/生产域名"""
    import requests
    kwargs = {"params": params, "timeout": 15}
    if PROXY:
        kwargs["proxies"] = {"http": PROXY, "https": PROXY}

    for domain in ("https://www.okx.bet", "https://www.okx.com"):
        try:
            resp = requests.get(f"{domain}{path}", **kwargs)
            data = resp.json()
            if data.get("code") == "0":
                return data
        except Exception as e:
            print(f"OKX API fail ({domain}): {e}", file=sys.stderr)
    return None


def _fetch_candles(symbol: str, bar: str, limit: int) -> list:
    """
    获取 K线数据，支持分页，返回从旧到新排列的原始 OKX item 列表。
    先用单次请求拿 300 根，不够再往前翻页。
    """
    limit = min(limit, 1000)
    page_size = min(limit, 300)
    all_items = []
    before_ts = None

    while len(all_items) < limit:
        params = {"instId": symbol, "bar": bar, "limit": str(page_size)}
        if before_ts is not None:
            params["before"] = before_ts

        data = _okx_get("/api/v5/market/candles", params)
        if not data or "data" not in data or not data["data"]:
            break

        items = data["data"]  # 最新→最旧
        # 去重
        existing_ts = {item[0] for item in all_items}
        new_items = [item for item in items if item[0] not in existing_ts]
        if not new_items:
            break

        all_items.extend(new_items)

        if len(new_items) < page_size:
            break  # 没有更多数据了

        before_ts = new_items[-1][0]  # 最旧的作为下一页起点

    # 从旧到新排列
    all_items.reverse()
    return all_items[:limit]




# ---- routes ----
@app.route("/ping")
def ping():
    return "pong"


@app.route("/")
def index():
    """回测页面（主页面）"""
    return render_template("backtest.html")


def _compute_signal(i,close,high,low,openp,vol,
                     all_ema_f,all_ema_m,all_ema_s,all_macd_hist,all_rsi,
                     all_bb_upper,all_bb_mid,all_bb_lower,all_atr,all_adx,all_obv,all_vol_ma20,
                     all_ema_f5=None,all_ema_m5=None,all_ema_s5=None,
                     all_adx5=None,all_rsi5=None,all_macd_h5=None,c5=None,idx_5m_map=None):
    """1m+5m双框架评分 — 与回测完全一致"""
    if i < 199: return None
    price=close[i]; ema_f=all_ema_f[i]; ema_m=all_ema_m[i]; ema_s=all_ema_s[i]
    macd_h=all_macd_hist[i]; rsi_v=all_rsi[i]
    bb_u=all_bb_upper[i]; bb_m=all_bb_mid[i]; bb_l=all_bb_lower[i]
    adx_v=all_adx[i]; obv_v=all_obv[i]
    vr=vol[i]/all_vol_ma20[i] if all_vol_ma20[i]>0 else 0
    idx5=idx_5m_map[i] if idx_5m_map is not None else -1
    has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])
    s={}
    # ---- EMA趋势过滤 + RSI极值入场 ----
    adx_l=adx_v if not np.isnan(adx_v) else 0
    d="neutral"; cf=30; total_score=0
    is_oversold = not np.isnan(rsi_v) and rsi_v <= 30
    is_ob = not np.isnan(rsi_v) and rsi_v >= 70
    at_bb_lower = not np.isnan(bb_u) and price <= bb_l + (bb_m - bb_l) * 0.3
    at_bb_upper = not np.isnan(bb_u) and price >= bb_u - (bb_u - bb_m) * 0.3
    ema_trend_up = not np.isnan(ema_f) and price > ema_f
    ema_trend_down = not np.isnan(ema_f) and price < ema_f
    if is_oversold and at_bb_lower and adx_l >= 10:
        d="bullish"; total_score=60
    # 做空：ADX>45时强趋势中不做空（用户数据：仅33%成功率）
    # 但ADX>50+BB上轨时强趋势豁免做空
    if d=="neutral" and is_ob and at_bb_upper and adx_l >= 10:
        if adx_l <= 45 or adx_l > 50:
            d="bearish"; total_score=-60
    cf=min(100,max(30,int(55+adx_l*0.5)))
    if d!="neutral" and cf<35: d="neutral"
    # === 强趋势方向保护：ADX>45时只允许顺势交易 ===
    # 防止在强下跌趋势中抄底、强上涨趋势中摸顶
    if d != "neutral" and adx_l > 45:
        if d == "bullish" and ema_trend_down:
            d = "neutral"
        elif d == "bearish" and ema_trend_up:
            d = "neutral"
    # === 极端趋势保护：ADX>80不开新仓 ===
    # 极端单边行情中任何入场风险极高
    if d != "neutral" and adx_l > 80:
        d = "neutral"
    rlist=[]
    if is_oversold: rlist.append("RSI超卖")
    if is_ob: rlist.append("RSI超买")
    if at_bb_lower: rlist.append("BB下轨")
    if at_bb_upper: rlist.append("BB上轨")
    if adx_l>=35: rlist.append("趋势强")
    r=",".join(rlist[:4]) if rlist else "中性"
    return {"direction":d,"score":round(total_score,1),"confidence":cf,"reason":r,"signals":s,"adx_val":adx_l,"rsi_val":rsi_v if not np.isnan(rsi_v) else 50,"at_bb_lower":at_bb_lower,"at_bb_upper":at_bb_upper}


@app.route("/api/backtest")
def api_backtest():
    """回测分析 API — 从本地 Parquet 读取历史数据，支持指定时间段"""
    try:
        print(f"[回测] 开始处理请求, style={request.args.get('style','?')}, lookahead={request.args.get('lookahead','?')}, start={request.args.get('start','?')[:20]}, end={request.args.get('end','?')[:20]}", file=sys.stderr)
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style", "short_term")
        lookahead = request.args.get("lookahead", 480, type=int)
        bar = "1m" if style == "short_term" else "4H"
        # 止盈止损参数（百分比）
        sl_pct = request.args.get("sl", 0.0, type=float)
        tp_pct = request.args.get("tp", 0.0, type=float)
        fee_rate = request.args.get("fee", 0.0005, type=float)
        cap = request.args.get("cap", 1000, type=float)
        lev = request.args.get("lev", 1, type=float)
        fee_filter = request.args.get("fee_filter", "0", type=str) == "1"
        # 实时模式：只统计此时间戳之后的交易
        trade_start_ms = request.args.get("trade_start", 0, type=int)
        # 导出模式：跳过K线数据生成，只返回交易数据
        csv_export = request.args.get("format") == "csv"
        raw_export = request.args.get("raw") == "1"

        # 时间范围：支持 start/end (Unix ms 或 ISO 日期)
        now_ms = int(time.time() * 1000)
        raw_start = request.args.get("start", "")
        raw_end = request.args.get("end", "")

        def _parse_ts(val: str, default: int) -> int:
            if not val:
                return default
            if val.isdigit():
                return int(val)
            try:
                # 支持 "2026/05/01 00:00", "2026-05-01 00:00", "2026-05-01T00:00" 等格式
                cleaned = val.replace("/", "-").replace("T", " ")
                # "2026-05-01 00:00" → 需要处理
                if " " in cleaned and cleaned.count("-") >= 2:
                    parts = cleaned.split(" ")
                    date_part = parts[0]
                    time_part = parts[1] if len(parts) > 1 else "00:00"
                    cleaned = date_part + "T" + time_part
                elif cleaned.count("-") >= 2 and "T" not in cleaned:
                    cleaned += "T00:00"
                dt = datetime.fromisoformat(cleaned)
                return int(dt.timestamp() * 1000)
            except Exception:
                return default

        end_ts = _parse_ts(raw_end, now_ms)
        # 默认回测最近 7 天
        start_ts = _parse_ts(raw_start, end_ts - 7 * 86400_000)

        # ---- 从本地 Parquet 读取数据 ----
        import pandas as pd
        from cryptopulse.config import DATA_DIR

        parquet_path = DATA_DIR / "BTC-USDT-SWAP" / f"klines_{bar.lower()}.parquet"
        if not parquet_path.exists() or parquet_path.stat().st_size == 0:
            return jsonify({"error": f"本地数据文件不存在或为空: {parquet_path}"}), 404

        try:
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            return jsonify({"error": f"读取本地数据失败: {e}"}), 503

        # 用K线最新时间取代系统时间（K线数据才是真实最新）
        latest_ts = int(df["timestamp"].max())
        if not raw_end:
            end_ts = latest_ts
        if not raw_start:
            start_ts = end_ts - 7 * 86400_000
        # 过滤时间范围
        mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
        df = df[mask].sort_values("timestamp").reset_index(drop=True)

        if len(df) < 100:
            return jsonify({"error": f"所选时间段内数据不足 (需≥200根, 实际{len(df)}根)"}), 503

        # ---- 批量计算信号（一次性算完指标，逐位判信号，比滑窗快 10x+）----
        import numpy as np
        from cryptopulse.core.data.models import Direction
        from cryptopulse.core.indicators.engine import TechnicalSignalEngine
        from cryptopulse.core.indicators.calculations import (
            adx, atr, bollinger, emma, macd, obv, rsi, sma,
        )

        close = df["close"].values.astype(float)
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        vol = df["volume"].values.astype(float)
        openp = df["open"].values.astype(float)

        engine = TechnicalSignalEngine(style)

        # === 加载 5m 数据做多时间框架分析 ===
        ts_5m_path = parquet_path.parent / "klines_5m.parquet"
        df_5m = pd.read_parquet(ts_5m_path) if ts_5m_path.exists() else pd.DataFrame()
        if not df_5m.empty:
            df_5m = df_5m.sort_values("timestamp").reset_index(drop=True)
            c5=df_5m["close"].values.astype(float); h5=df_5m["high"].values.astype(float)
            l5=df_5m["low"].values.astype(float); v5=df_5m["volume"].values.astype(float)
            ts5=df_5m["timestamp"].values
            # 5m 指标
            all_ema_f5 = emma(c5, engine.ema_fast); all_ema_m5 = emma(c5, engine.ema_mid); all_ema_s5 = emma(c5, engine.ema_slow)
            all_rsi5 = rsi(c5, engine.rsi_period)
            all_bb_u5, all_bb_m5, all_bb_l5 = bollinger(c5, engine.bb_period, engine.bb_std)
            all_adx5 = adx(h5, l5, c5, engine.adx_period)
            all_macd_l5, all_macd_s5, all_macd_h5 = macd(c5, engine.macd_fast, engine.macd_slow, engine.macd_signal)
            idx_5m_map = []
            j = 0
            for t in df["timestamp"].values:
                while j < len(ts5) - 1 and ts5[j+1] <= t:
                    j += 1
                idx_5m_map.append(j)
            idx_5m_map = np.array(idx_5m_map)
        else:
            idx_5m_map, all_ema_f5, all_ema_m5, all_ema_s5 = None, None, None, None
            all_rsi5, all_bb_u5, all_bb_m5, all_bb_l5 = None, None, None, None
            all_adx5, all_macd_h5 = None, None
        # 一次算出全部指标（向量化）
        all_ema_f = emma(close, engine.ema_fast)
        all_ema_m = emma(close, engine.ema_mid)
        all_ema_s = emma(close, engine.ema_slow)
        all_macd_line, all_macd_sig, all_macd_hist = macd(close, engine.macd_fast, engine.macd_slow, engine.macd_signal)
        all_rsi = rsi(close, engine.rsi_period)
        all_bb_upper, all_bb_mid, all_bb_lower = bollinger(close, engine.bb_period, engine.bb_std)
        all_atr = atr(high, low, close, 14)
        all_adx = adx(high, low, close, engine.adx_period)
        all_obv = obv(close, vol)
        all_vol_ma20 = sma(vol, 20)

        candles_out = []
        signals_raw = []
        all_signals = []  # 所有信号（含观望）
        # 进场冷却：同一方向连续信号间隔不足 cool_bars 根 K 线时跳过
        cool_bars = 2  # 冷却K线数：至少间隔1根K线（原为1导致连续逆势进场）
        last_trade_dir = None
        last_trade_idx = -cool_bars
        for i in range(len(df)):
            signal = _compute_signal(i, close, high, low, openp, vol,
                    all_ema_f, all_ema_m, all_ema_s, all_macd_hist, all_rsi,
                    all_bb_upper, all_bb_mid, all_bb_lower, all_atr, all_adx, all_obv, all_vol_ma20,
                    all_ema_f5, all_ema_m5, all_ema_s5,
                    all_adx5, all_rsi5, all_macd_h5, c5, idx_5m_map)
            ts = int(df["timestamp"].iloc[i])
            if signal:
                all_signals.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
                if signal["direction"] != "neutral":
                    # 进场冷却检查
                    dir_now = signal["direction"]
                    if dir_now == last_trade_dir and i - last_trade_idx < cool_bars:
                        # 强趋势+布林带触边时，冷却期豁免（仍有最小间隔限制）
                        adx_val = signal.get("adx_val", 0)
                        sig_bb_lower = signal.get("at_bb_lower", False)
                        sig_bb_upper = signal.get("at_bb_upper", False)
                        if adx_val > 50 and (sig_bb_lower or sig_bb_upper):
                            # 豁免但至少间隔0根K线（阻止同一根K线重复进场）
                            if i - last_trade_idx >= 1:
                                signal["cooled"] = False
                                signal["cooling_exempt"] = True
                                if trade_start_ms <= 0 or ts >= trade_start_ms:
                                    signals_raw.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
                                    last_trade_dir = dir_now
                                    last_trade_idx = i
                            else:
                                signal["cooled"] = True
                        else:
                            # 同方向冷却期内，把当前信号标记为"被冷却跳过"但记录在 all_signals
                            signal["cooled"] = True
                    else:
                        signal["cooled"] = False
                        if trade_start_ms <= 0 or ts >= trade_start_ms:
                            signals_raw.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
                            last_trade_dir = dir_now
                            last_trade_idx = i
            if not csv_export:
                candles_out.append({
                    "t": ts,
                    "o": openp[i], "h": high[i], "l": low[i], "c": close[i],
                    "v": vol[i], "s": signal,
                })
        # ---- 原始K线导出 ----
        if raw_export:
            import io
            buf = io.StringIO()
            buf.write("timestamp,open,high,low,close,volume,direction,score,confidence,reason\n")
            for i in range(len(df)):
                ts = df["timestamp"].iloc[i]
                sig = _compute_signal(i, close, high, low, openp, vol,
                    all_ema_f, all_ema_m, all_ema_s, all_macd_hist, all_rsi,
                    all_bb_upper, all_bb_mid, all_bb_lower, all_atr, all_adx, all_obv, all_vol_ma20,
                    all_ema_f5, all_ema_m5, all_ema_s5,
                    all_adx5, all_rsi5, all_macd_h5, c5, idx_5m_map)
                if sig:
                    dir_v = sig["direction"]
                    buf.write(f"{ts},{openp[i]},{high[i]},{low[i]},{close[i]},{vol[i]},{dir_v},{sig['score']},{sig['confidence']},{sig['reason']}\n")
            return Response(buf.getvalue(), mimetype="text/csv;charset=utf-8-sig", headers={"Content-Disposition": f"attachment; filename=klines_{style}.csv"})

        trades = []
        sl_cooldown_until = 0  # 止损冷却截止时间戳（毫秒）
        sl_cooldown_ms = 300 * 1000  # 5分钟
        sl_cooldown_zones = []  # 收集冷却区间用于画线

        for sr in signals_raw:
            idx = sr["idx"]
            sig = sr["sig"]
            entry_price = sr["price"]
            entry_ts = sr["ts"]

            # ---- 止损冷却检查 ----
            if entry_ts < sl_cooldown_until:
                # 在冷却期内，跳过此交易，标记风控原因
                sig["risk_blocked"] = True
                remaining_s = (sl_cooldown_until - entry_ts) // 1000
                sig["risk_reason"] = "止损冷却中"
                continue

            # 验证：看 lookahead 期间价格是否触摸过入场价方向（用高/低点，更宽容）
            future_end = min(idx + lookahead, len(df) - 1)
            future_start = idx + 1
            future_count = future_end - idx
            if future_count < lookahead:
                continue

            is_bullish = sig["direction"] == "bullish"
            is_bearish = sig["direction"] == "bearish"

            # ---- 止盈止损: ATR ----
            atr_entry = all_atr[idx] if not np.isnan(all_atr[idx]) else close[idx] * 0.005
            # 止盈 = 入场价 + n × ATR, 其中n为风险系数(通常2-3)
            risk_n = 3.0
            sl_mult = 2.0
            tp_mult = risk_n
            if is_bullish:
                sl_price = entry_price - atr_entry * sl_mult
                sl_init = sl_price
                tp_price = entry_price + atr_entry * tp_mult
            elif is_bearish:
                sl_price = entry_price + atr_entry * sl_mult
                sl_init = sl_price
                tp_price = entry_price - atr_entry * tp_mult
            else:
                sl_price = entry_price
                tp_price = entry_price
                sl_init = entry_price

            # ---- 保本检查：TP1利润必须高于手续费才值得进场 ----
            fee_cost_pct = fee_rate * 2 * 100  # 双边手续费百分比
            if is_bullish:
                tp1_pct = (tp_price / entry_price - 1) * 100
            elif is_bearish:
                tp1_pct = (1 - tp_price / entry_price) * 100
            else:
                tp1_pct = 0
            if tp1_pct <= fee_cost_pct:
                sig["risk_blocked"] = True
                sig["risk_reason"] = "TP1利润不足覆盖手续费"
                continue

            # ---- 验证出场（止损/止盈/超时） ----
            correct = False
            sl_hit = False
            tp_hit = False
            exit_reason = "超时"

            for j in range(future_start, future_end + 1):
                bar_high = high[j]
                bar_low = low[j]

                if is_bullish:
                    # 先检查止盈
                    if bar_high >= tp_price:
                        exit_price = tp_price
                        correct = True; tp_hit = True; exit_reason = "止盈"; break
                    # 再检查止损
                    if bar_low <= sl_price:
                        exit_price = sl_price
                        correct = False; sl_hit = True; exit_reason = "止损"
                        sl_cooldown_until = df["timestamp"].iloc[j] + sl_cooldown_ms
                        sl_cooldown_zones.append({"start_ts": df["timestamp"].iloc[j], "end_ts": sl_cooldown_until, "sl_price": sl_price})
                        break

                elif is_bearish:
                    if bar_low <= tp_price:
                        exit_price = tp_price
                        correct = True; tp_hit = True; exit_reason = "止盈"; break
                    if bar_high >= sl_price:
                        exit_price = sl_price
                        correct = False; sl_hit = True; exit_reason = "止损"
                        sl_cooldown_until = df["timestamp"].iloc[j] + sl_cooldown_ms
                        sl_cooldown_zones.append({"start_ts": df["timestamp"].iloc[j], "end_ts": sl_cooldown_until, "sl_price": sl_price})
                        break

            # 如果止损止盈都没触发，用收盘价
            if not sl_hit and not tp_hit:
                exit_price = close[future_end]
                if is_bullish:
                    correct = bool(exit_price > entry_price)
                elif is_bearish:
                    correct = bool(exit_price < entry_price)

            # PnL 模拟
            pnl_pct = (exit_price / entry_price - 1) * (1 if is_bullish else -1) * 100

            trades.append({
                "timestamp": entry_ts,
                "time": time.strftime("%m-%d %H:%M:%S", time.gmtime(entry_ts / 1000)),
                "direction": sig["direction"],
                "score": sig["score"],
                "confidence": sig["confidence"],
                "entry_price": round(entry_price, 1),
                "exit_price": round(exit_price, 1),
                "sl_price": round(sl_init, 1) if is_bullish or is_bearish else None,
                "tp_price": round(tp_price, 1) if tp_price is not None else None,
                "lookahead": lookahead,
                "correct": correct,
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": exit_reason,
            })

        # ---- 实时模式过滤：只统计 trade_start 之后的交易 ----
        # ---- 汇总统计 ----
        total_trades = len(trades)
        correct_trades = sum(1 for t in trades if t["correct"])
        wrong_trades = total_trades - correct_trades
        accuracy = round(correct_trades / total_trades * 100, 1) if total_trades > 0 else 0

        bullish_trades = [t for t in trades if t["direction"] == "bullish"]
        bearish_trades = [t for t in trades if t["direction"] == "bearish"]

        correct_bullish = sum(1 for t in bullish_trades if t["correct"])
        correct_bearish = sum(1 for t in bearish_trades if t["correct"])

        # PnL 统计
        total_pnl_pct = sum(t["pnl_pct"] for t in trades)
        wins = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        avg_win = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
        avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
        max_win = round(max(t["pnl_pct"] for t in trades), 2) if trades else 0
        max_loss = round(min(t["pnl_pct"] for t in trades), 2) if trades else 0
        profit_factor = round(abs(sum(t["pnl_pct"] for t in wins) / sum(t["pnl_pct"] for t in losses)) if losses else 0, 2)

        # 胜率（按PnL>0计算）
        win_rate = round(len(wins) / total_trades * 100, 1) if total_trades > 0 else 0

        # 连续统计
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        cur_wins = 0
        cur_losses = 0
        for t in trades:
            if t["correct"]:
                cur_wins += 1
                cur_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, cur_wins)
            else:
                cur_losses += 1
                cur_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, cur_losses)

        def _fmt_ts(ts: int) -> str:
            return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")

        # 最后一条信号的预测（下一根K线方向）
        # 从末尾往前找最后一个有信号的K线作为预测
        prediction = None
        for c in reversed(candles_out):
            sig = c.get("s")
            if sig and sig.get("direction") and sig["direction"] != "neutral":
                prediction = {
                    "direction": sig["direction"],
                    "score": sig["score"],
                    "confidence": sig["confidence"],
                }
                break

        # ---- CSV导出（format=csv模式：所有信号明细） ----
        if csv_export:
            if not all_signals:
                return jsonify({"error": "没有信号数据"}), 404
            sig_rows = []
            for n, sr in enumerate(all_signals, 1):
                idx = sr["idx"]
                sig = sr["sig"]
                s = sig.get("signals", {}) or {}
                p = close[idx]
                atr_v = all_atr[idx] if not np.isnan(all_atr[idx]) else 0
                adx_v = all_adx[idx] if not np.isnan(all_adx[idx]) else 20
                vr = vol[idx] / all_vol_ma20[idx] if all_vol_ma20[idx] > 0 else 1
                hr = time.gmtime(sr["ts"] / 1000).tm_hour
                is_dir = sig["direction"] != "neutral"
                # SL/TP验证
                entry_price = p
                # 方向对应的SL/TP — 根据5m ADX动态调整
                atr_entry = all_atr[idx] if not np.isnan(all_atr[idx]) else p * 0.005
                # 止盈 = 入场价 + n × ATR
                risk_n = 3.0
                sl_mult_sig = 2.0
                tp_mult_sig = risk_n
                bull_sl = entry_price - atr_entry * sl_mult_sig
                bull_tp = entry_price + atr_entry * tp_mult_sig
                bear_sl = entry_price + atr_entry * sl_mult_sig
                bear_tp = entry_price - atr_entry * tp_mult_sig
                correct = None; exit_price = None; exit_reason = ""; pnl_pct = None
                if is_dir:
                    is_bull = sig["direction"] == "bullish"
                    future_end = min(idx + lookahead, len(df) - 1)
                    exit_price = close[future_end]
                    correct = False; exit_reason = "超时"
                    _sl = bull_sl if is_bull else bear_sl
                    _tp = bull_tp if is_bull else bear_tp
                    sl_init = _sl
                    tp_init = _tp
                    for j in range(idx + 1, future_end + 1):
                        bh, bl = high[j], low[j]
                        if is_bull:
                            if bh >= _tp: exit_price = _tp; correct = True; exit_reason = "止盈"; break
                            if bl <= _sl: exit_price = _sl; correct = False; exit_reason = "止损"; break
                        else:
                            if bl <= _tp: exit_price = _tp; correct = True; exit_reason = "止盈"; break
                            if bh >= _sl: exit_price = _sl; correct = False; exit_reason = "止损"; break
                    pnl_pct = round((exit_price / entry_price - 1) * (1 if is_bull else -1) * 100, 4)
                fee_cost = round(fee_rate * 2 * 100, 3)
                fee_triggered = is_dir and abs(pnl_pct or 0) < fee_cost
                row = {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(sr["ts"] / 1000)),
                    "price": round(p, 1),
                    "open": round(openp[idx], 1),
                    "high": round(high[idx], 1),
                    "low": round(low[idx], 1),
                    "volume": round(vol[idx], 4),
                    "direction": sig["direction"],
                    "score": sig["score"],
                    "confidence": sig["confidence"],
                    "reason": sig["reason"],
                    "entry_price": round(entry_price, 1) if is_dir else "",
                    "sl_price": round(sl_init, 1) if is_dir else "",
                    "tp_price": round(tp_init, 1) if is_dir else "",
                    "exit_price": round(exit_price, 1) if exit_price else "",
                    "exit_reason": exit_reason,
                    "correct": "Y" if correct else ("N" if correct is False else ""),
                    "pnl_pct": pnl_pct,
                    "保本": "未触发" if fee_triggered else "",
                    "#": n,
                    "ema": round(s.get("ema", 0), 2),
                    "momentum": round(s.get("momentum", 0), 2),
                    "macd": round(s.get("macd", 0), 2),
                    "rsi_val": round(sig.get("rsi_val", 50), 1),
                    "rsi_score": round(s.get("rsi", 0), 2),
                    "bb": round(s.get("bollinger", 0), 2),
                    "vol_ratio": round(vr, 2),
                    "vol_score": round(s.get("volume", 0), 2),
                    "obv_score": round(s.get("obv", 0), 2),
                    "micro": round(s.get("micro", 0), 2),
                    "adx": round(adx_v, 1),
                    "atr": round(atr_v, 2),
                    "adx_category": "强趋势" if adx_v >= 35 else ("中趋势" if adx_v >= 25 else ("弱趋势" if adx_v >= 20 else "无趋势")),
                    "price_trend": "up" if p > openp[idx] else "down",
                    "hour_of_day": hr,
                }
                sig_rows.append(row)
            # 统计
            total_s = len(sig_rows)
            bullish = sum(1 for r in sig_rows if r["direction"] == "bullish")
            bearish = sum(1 for r in sig_rows if r["direction"] == "bearish")
            neutral_s = sum(1 for r in sig_rows if r["direction"] == "neutral")
            import io as _io
            b = _io.StringIO()
            # ---- 交易汇总 ----
            if total_trades > 0:
                b.write("【回测结果汇总】\n")
                if fee_filter: b.write(f"(已开启保本过滤, 阈值 {round(fee_rate*2*100,3)}%)\n")
                b.write(f"交易笔数,{total_trades}\n正确,{correct_trades} ({round(correct_trades/total_trades*100,1)}%)\n错误,{wrong_trades} ({round(wrong_trades/total_trades*100,1)}%)\n")
                b.write(f"准确率,{accuracy}%\n总毛利,{round(total_pnl_pct,2)}%\n总手续费,{round(total_trades*fee_rate*2*100,2)}%\n净利,{round(total_pnl_pct-total_trades*fee_rate*2*100,2)}%\n")
                b.write(f"胜率,{win_rate}%\n盈亏比,{profit_factor}\n平均盈,{avg_win}%\n平均亏,{avg_loss}%\n")
                sl_c = sum(1 for t in trades if t["exit_reason"] == "止损")
                tp_c = sum(1 for t in trades if t["exit_reason"] == "止盈")
                ti_c = sum(1 for t in trades if t["exit_reason"] == "超时")
                b.write(f"止损,{sl_c}笔({round(sl_c/total_trades*100,1)}%)\n止盈,{tp_c}笔({round(tp_c/total_trades*100,1)}%)\n超时,{ti_c}笔({round(ti_c/total_trades*100,1)}%)\n")
                b.write(f"\n【仓位参数】\n本金,{cap} USDT\n杠杆,{int(lev)}x\n费率,{round(fee_rate*100,2)}%\n每笔手续费,{round(fee_rate*2*100,3)}%\n总手续费金额,{round(total_trades*fee_rate*2*cap*lev/100,1)} USDT\n")
                b.write(f"验证值,{lookahead}根K线\n\n")
            # ---- 信号明细 ----
            b.write("【信号明细汇总】\n")
            b.write(f"总信号数,{total_s}\n做多,{bullish}\n做空,{bearish}\n观望,{neutral_s}\n")
            b.write(f"做多占比,{round(bullish/total_s*100,1)}%\n做空占比,{round(bearish/total_s*100,1)}%\n观望占比,{round(neutral_s/total_s*100,1)}%\n\n")
            b.write("【信号明细】\n")
            cols = ["#","time","price","open","high","low","volume","direction","score","confidence","reason",
                    "entry_price","sl_price","exit_price","exit_reason","correct","pnl_pct","保本",
                    "rsi_val","rsi_score","bb","adx","atr","adx_category","风控原因"]
            # 为每条信号添加风控原因（回测中检测是否在冷却期内）
            for row in sig_rows:
                if row.get("direction") in ("bullish", "bearish"):
                    dir_str = "long" if row["direction"] == "bullish" else "short"
                    can_open, reason = risk_mgr.can_open_new_position(dir_str)
                    row["风控原因"] = reason if not can_open else ""
                else:
                    row["风控原因"] = ""
            avail = [c for c in cols if c in sig_rows[0]]
            csv_df = pd.DataFrame(sig_rows)
            csv_df[avail].to_csv(b, index=False)
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            return Response(b.getvalue(), mimetype="text/csv;charset=utf-8-sig", headers={"Content-Disposition": f"attachment; filename=signals_{style}_{ts_str}.csv"})

        return jsonify({
            "symbol": symbol,
            "style": style,
            "lookahead": lookahead,
            "date_range": {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "start": _fmt_ts(start_ts),
                "end": _fmt_ts(end_ts),
            },
            "stats": {
                "total_trades": total_trades,
                "correct": correct_trades,
                "wrong": wrong_trades,
                "accuracy": accuracy,
                "bullish": len(bullish_trades),
                "bearish": len(bearish_trades),
                "correct_bullish": correct_bullish,
                "correct_bearish": correct_bearish,
                "total_pnl_pct": round(total_pnl_pct, 2),
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "max_win": max_win,
                "max_loss": max_loss,
                "profit_factor": profit_factor,
                "max_consecutive_wins": max_consecutive_wins,
                "max_consecutive_losses": max_consecutive_losses,
                "signal_total": len(all_signals),
                "signal_bullish": sum(1 for s in all_signals if s["sig"]["direction"] == "bullish"),
                "signal_bearish": sum(1 for s in all_signals if s["sig"]["direction"] == "bearish"),
                "signal_neutral": sum(1 for s in all_signals if s["sig"]["direction"] == "neutral"),
            },
            "trades": trades,
            "candles": candles_out,
            "total_candles": len(candles_out),
            "all_signals": [{"ts":s["ts"],"direction":s["sig"]["direction"],"score":s["sig"]["score"],"confidence":s["sig"]["confidence"],"reason":s["sig"]["reason"]} for s in all_signals],
            "prediction": prediction,
            "sl_cooldown_zones": sl_cooldown_zones,
        })

    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/logs")
def api_logs():
    limit = request.args.get("limit", 100, type=int)
    if not LOG_FILE.exists():
        return jsonify([])
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        return jsonify([json.loads(l) for l in reversed(lines[-limit:]) if l.strip()])
    except Exception:
        return jsonify([])


@app.route("/api/risk/status")
def api_risk_status():
    """获取当前风控状态"""
    try:
        return jsonify(risk_mgr.get_risk_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/risk/trigger-sl", methods=["POST"])
def api_risk_trigger_sl():
    """手动触发止损冷却"""
    try:
        data = request.get_json(silent=True) or {}
        reason = data.get("reason", "手工触发")
        risk_mgr.trigger_stop_loss(reason)
        _log_event("risk_trigger_sl", {"reason": reason})
        return jsonify({"ok": True, "status": risk_mgr.get_risk_status()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/risk/clear-sl", methods=["POST"])
def api_risk_clear_sl():
    """清除止损冷却状态"""
    try:
        risk_mgr.clear_stop_loss()
        _log_event("risk_clear_sl", {})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"[CryptoPulse] Starting on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=True, threaded=True)
