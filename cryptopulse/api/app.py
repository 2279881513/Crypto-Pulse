"""
CryptoPulse — Flask Web UI
直接使用 requests 调用 OKX REST API（带代理支持）
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from flask import Flask, render_template, jsonify, request

# 代理配置
PROXY = os.environ.get("PROXY", "") or os.environ.get("HTTP_PROXY", "") or ""

app = Flask(__name__)

# ---- 历史记录存储 ----
HISTORY_FILE = _root / "data" / "signal_history.jsonl"
HISTORY_FILE.parent.mkdir(exist_ok=True)
MAX_HISTORY = 10000
CLEAR_FILE = _root / "data" / "signal_clear.txt"
LOG_FILE = _root / "data" / "cryptopulse.log"


def _get_clear_timestamp() -> int:
    """获取清空时间戳，0=未清空"""
    try:
        if CLEAR_FILE.exists():
            return int(CLEAR_FILE.read_text().strip())
    except Exception:
        pass
    return 0


def _set_clear_timestamp(ts: int) -> None:
    CLEAR_FILE.write_text(str(ts))


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


def _evaluate_history() -> int:
    if not HISTORY_FILE.exists():
        return 0
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        evaluated = 0
        out_lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                out_lines.append(line)
                continue
            if "result" in rec:
                out_lines.append(line)
                continue
            rec["result"] = "pending"
            out_lines.append(json.dumps(rec, ensure_ascii=False))
            evaluated += 1
        HISTORY_FILE.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return evaluated
    except Exception:
        return 0


def _save_to_history(record: dict) -> None:
    """保存信号到历史记录（JSON Lines）"""
    try:
        record["_ts"] = int(time.time() * 1000)
        record["_time"] = time.strftime("%m-%d %H:%M", time.localtime())
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        # 限制文件行数
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) > MAX_HISTORY:
            HISTORY_FILE.write_text(
                "\n".join(lines[-MAX_HISTORY:]) + "\n", encoding="utf-8"
            )
    except Exception:
        pass


def _load_history(limit: int = 50) -> list[dict]:
    """加载历史记录"""
    if not HISTORY_FILE.exists():
        return []
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
        records = []
        for line in reversed(lines[-limit:]):
            if line.strip():
                records.append(json.loads(line))
        return records
    except Exception:
        return []


def _history_has_timestamp(ts: int) -> bool:
    """检查历史文件中是否已有该时间戳的记录"""
    if not HISTORY_FILE.exists():
        return False
    try:
        ts_str = str(ts)
        for line in HISTORY_FILE.read_text(encoding="utf-8").split("\n"):
            if ts_str in line:
                return True
    except Exception:
        pass
    return False


def _save_chart_signal(candle_ts: int, signal: dict, price: float) -> None:
    """保存K线图信号到历史文件"""
    try:
        if _history_has_timestamp(candle_ts):
            return
        import time
        record = {
            "_ts": candle_ts,
            "_time": time.strftime("%m-%d %H:%M", time.localtime(candle_ts / 1000)),
            "price": price,
            "direction": signal["direction"],
            "score": signal["score"],
            "confidence": signal["confidence"],
            "entry_optimal": signal.get("entry", price),
            "stop_loss": signal.get("sl", price * 0.99),
            "take_profit_1": signal.get("tp1", price * 1.01),
            "take_profit_2": signal.get("tp2", price * 1.02),
            "take_profit_3": signal.get("tp3", price * 1.03),
        }
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
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




def _fetch_signal(symbol: str = "BTC-USDT", style: str = "short_term"):
    """获取数据并计算信号（第一阶技术面 + 第二阶微观结构）"""
    from cryptopulse.core.data.ring_buffer import KLineRingBuffer
    from cryptopulse.core.indicators.engine import TechnicalSignalEngine

    interval = "1m" if style == "short_term" else "4H"
    buf = KLineRingBuffer(capacity=200, interval=interval)

    # --- 第一阶：技术面 ---
    engine = TechnicalSignalEngine(style)
    data = _okx_get("/api/v5/market/candles", {"instId": symbol, "bar": interval, "limit": "200"})
    if data and "data" in data:
        from cryptopulse.core.data.models import KLine
        for item in reversed(data["data"]):
            k = KLine.from_okx(item)
            buf.push(k)

    if not buf.is_full:
        return None, f"Data insufficient ({buf.current_count}/200)"

    df = buf.to_dataframe()
    result = engine.evaluate(df)

    # 获取最新价格
    ticker = _okx_get("/api/v5/market/ticker", {"instId": symbol})
    price = 0
    if ticker and "data" in ticker:
        price = float(ticker["data"][0].get("last", 0))
    price = price or result.entry_optimal

    _log_event("signal", {
        "symbol": symbol, "style": style,
        "direction": result.direction.value,
        "score": result.score,
        "confidence": result.confidence,
        "price": price,
    })

    return {
        "result": result,
        "symbol": symbol,
        "style": style,
        "price": price,
    }, None


# ---- routes ----
@app.route("/ping")
def ping():
    return "pong"


@app.route("/")
def index():
    error = None
    signal = None
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = os.environ.get("STYLE", "short_term")
        signal, error = _fetch_signal(symbol, style)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    return render_template("index.html", signal=signal, error=error,
                           proxy_configured=bool(PROXY),
                           symbol=symbol, style=style)


@app.route("/api/signal")
def api_signal():
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style") or os.environ.get("STYLE", "short_term")
        signal, error = _fetch_signal(symbol, style)
        if error:
            return jsonify({"error": error}), 503
        r = signal["result"]
        resp = {
            "symbol": signal["symbol"], "style": signal["style"],
            "price": signal["price"],
            "direction": r.direction.value,
            "score": r.score, "confidence": r.confidence,
            "adx": r.adx_value,
            "entry_optimal": r.entry_optimal,
            "entry_zone_low": r.entry_zone_low,
            "entry_zone_high": r.entry_zone_high,
            "stop_loss": r.stop_loss,
            "take_profit_1": r.take_profit_1,
            "take_profit_2": r.take_profit_2,
            "take_profit_3": r.take_profit_3,
            "summary": r.summary,
            "details": r.details,
        }
        if "micro" in signal:
            resp["micro"] = signal["micro"]
        _save_to_history(resp)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(_load_history(limit=limit))


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    """清空历史记录"""
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.write_text("", encoding="utf-8")
        _set_clear_timestamp(int(time.time() * 1000))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/restore", methods=["POST"])
def restore_signals():
    """恢复所有信号"""
    _set_clear_timestamp(0)
    return jsonify({"ok": True})


@app.route("/chart")
def chart_page():
    """K 线信号回溯页面"""
    return render_template("chart.html")


@app.route("/backtest")
def backtest_page():
    """回测页面 — 测试系统正确率"""
    return render_template("backtest.html")


@app.route("/api/backtest")
def api_backtest():
    """回测分析 API — 从本地 Parquet 读取历史数据，支持指定时间段"""
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style", "short_term")
        lookahead = request.args.get("lookahead", 3, type=int)
        bar = "1m" if style == "short_term" else "4H"
        # 止盈止损参数（百分比）
        sl_pct = request.args.get("sl", 0.0, type=float)
        tp_pct = request.args.get("tp", 0.0, type=float)
        # 实时模式：只统计此时间戳之后的交易
        trade_start_ms = request.args.get("trade_start", 0, type=int)

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
        # 过滤时间范围
        mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
        df = df[mask].sort_values("timestamp").reset_index(drop=True)

        if len(df) < 100:
            return jsonify({"error": f"所选时间段内数据不足 (需≥100根, 实际{len(df)}根)"}), 503

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

        def _signal_at(i: int) -> Optional[dict]:
            """1m+5m双框架评分 — v2 趋势跟踪版"""
            if i < 99: return None
            price=close[i]; ema_f=all_ema_f[i]; ema_m=all_ema_m[i]; ema_s=all_ema_s[i]
            macd_h=all_macd_hist[i]; rsi_v=all_rsi[i]; bb_u=all_bb_upper[i]; bb_m=all_bb_mid[i]; bb_l=all_bb_lower[i]
            adx_v=all_adx[i]; obv_v=all_obv[i]; vr=vol[i]/all_vol_ma20[i] if all_vol_ma20[i]>0 else 0
            idx5=idx_5m_map[i] if idx_5m_map is not None else -1
            has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])
            s={}
            # 权重归一化总和=1.0，趋势特征权重提升
            w={"ema":0.15,"momentum":0.10,"macd":0.10,"rsi":0.08,"micro":0.06,"bollinger":0.08,"volume":0.06,"obv":0.06,"adx_filter":0.06,"tf5_trend":0.12,"tf5_adx":0.06,"tf5_rsi":0.04,"tf5_macd":0.03}
            # --- EMA 趋势跟踪：涨→看涨，跌→看跌 ---
            if not np.isnan(ema_f) and not np.isnan(ema_m) and not np.isnan(ema_s):
                al=ema_f>ema_m>ema_s;be=ema_f<ema_m<ema_s
                if al and price>ema_f: s["ema"]=1.0
                elif al: s["ema"]=0.5
                elif be and price<ema_f: s["ema"]=-1.0
                elif be: s["ema"]=-0.5
                else: s["ema"]=0.0
            else: s["ema"]=0.0
            # --- 动量趋势跟踪 ---
            if i>=5:
                mom=(close[i]-close[i-5])/close[i-5]*100
                if mom>0.08: s["momentum"]=1.0
                elif mom>0.03: s["momentum"]=0.5
                elif mom<-0.08: s["momentum"]=-1.0
                elif mom<-0.03: s["momentum"]=-0.5
                else: s["momentum"]=0.0
            else: s["momentum"]=0.0
            # --- MACD ---
            if i>=2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):
                hp=all_macd_hist[i-1]
                if macd_h>0 and macd_h>hp: s["macd"]=1.0
                elif macd_h>0: s["macd"]=0.5
                elif macd_h<0 and macd_h<hp: s["macd"]=-1.0
                elif macd_h<0: s["macd"]=-0.5
                else: s["macd"]=0.0
            else: s["macd"]=0.0
            # --- RSI ---
            if not np.isnan(rsi_v):
                r=rsi_v
                if r>=80: s["rsi"]=-1.0
                elif r>=70: s["rsi"]=-0.5
                elif r>=60: s["rsi"]=-0.2
                elif r>=45: s["rsi"]=0.2
                elif r>=35: s["rsi"]=0.0
                elif r>=25: s["rsi"]=0.3
                elif r>=20: s["rsi"]=0.6
                else: s["rsi"]=1.0
            else: s["rsi"]=0.0
            # --- 布林带 ---
            if not np.isnan(bb_u):
                if price>bb_u: s["bollinger"]=-0.7
                elif price>bb_m: s["bollinger"]=0.3
                elif price>bb_l: s["bollinger"]=-0.3
                else: s["bollinger"]=0.7
            else: s["bollinger"]=0.0
            # --- 成交量 ---
            if vr>1.5:
                chg=(close[i]-close[i-4])/close[i-4] if i>=4 else 0
                s["volume"]=0.8 if chg>0.002 else(-0.8 if chg<-0.002 else 0.3)
            elif vr>1.0: s["volume"]=0.2
            elif vr>0.7: s["volume"]=-0.2
            else: s["volume"]=-0.3
            # --- K线微观结构 ---
            cr=high[i]-low[i]
            if cr>0:
                bd=abs(close[i]-openp[i]);br=bd/cr;cp=(close[i]-low[i])/cr
                uw=(high[i]-max(close[i],openp[i]))/cr;lw=(min(close[i],openp[i])-low[i])/cr
                if br>0.7 and cp>0.7: s["micro"]=0.8
                elif br>0.7 and cp<0.3: s["micro"]=-0.8
                elif uw>0.5 and br<0.3: s["micro"]=-0.5
                elif lw>0.5 and br<0.3: s["micro"]=0.5
                elif br<0.2 and vr>1.5: s["micro"]=0.4 if cp>0.6 else(-0.4 if cp<0.4 else 0.0)
                else: s["micro"]=0.0
            else: s["micro"]=0.0
            # --- OBV ---
            if i>=5 and not np.isnan(obv_v):
                ot=(obv_v-all_obv[i-4])/(abs(all_obv[i-4])+1e-10)
                if ot>0.01: s["obv"]=0.6
                elif ot<-0.01: s["obv"]=-0.6
                else: s["obv"]=0.0
            else: s["obv"]=0.0
            # --- ADX 趋势强度（不做硬过滤，加权调节）---
            adx_l=adx_v if not np.isnan(adx_v) else 0
            if adx_l>=35: s["adx_filter"]=0.8
            elif adx_l>=25: s["adx_filter"]=0.3
            elif adx_l>=20: s["adx_filter"]=0.0
            else: s["adx_filter"]=-0.3
            # --- 5m多时间框架（趋势跟踪方向，与1m同向共振）---
            if has5:
                ef5,em5,es5=all_ema_f5[idx5],all_ema_m5[idx5],all_ema_s5[idx5]
                c5_p=c5[idx5] if idx5<len(c5) else price
                if ef5>em5>es5 and c5_p>ef5: s["tf5_trend"]=1.0
                elif ef5<em5<es5 and c5_p<ef5: s["tf5_trend"]=-1.0
                elif ef5>em5>es5: s["tf5_trend"]=0.5
                elif ef5<em5<es5: s["tf5_trend"]=-0.5
                else: s["tf5_trend"]=0.0
                adx5=all_adx5[idx5] if not np.isnan(all_adx5[idx5]) else 0
                if adx5>=35: s["tf5_adx"]=0.8
                elif adx5>=25: s["tf5_adx"]=0.3
                elif adx5>=20: s["tf5_adx"]=0.0
                else: s["tf5_adx"]=-0.3
                rsi5=all_rsi5[idx5] if not np.isnan(all_rsi5[idx5]) else 50
                if rsi5>75: s["tf5_rsi"]=-0.5
                elif rsi5<25: s["tf5_rsi"]=0.5
                elif rsi5>60: s["tf5_rsi"]=-0.2
                elif rsi5<35: s["tf5_rsi"]=0.2
                else: s["tf5_rsi"]=0.0
                mh5=all_macd_h5[idx5] if not np.isnan(all_macd_h5[idx5]) else 0
                if i>0 and idx5>0:
                    mh5_p=all_macd_h5[idx5-1]
                    if mh5>0 and mh5>mh5_p: s["tf5_macd"]=0.8
                    elif mh5>0: s["tf5_macd"]=0.4
                    elif mh5<0 and mh5<mh5_p: s["tf5_macd"]=-0.8
                    elif mh5<0: s["tf5_macd"]=-0.4
                    else: s["tf5_macd"]=0.0
                else:
                    s["tf5_macd"]=0.0
            else:
                s["tf5_trend"]=0.0;s["tf5_adx"]=0.0;s["tf5_rsi"]=0.0;s["tf5_macd"]=0.0
            total=sum(s.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            d=Direction.NEUTRAL
            # 趋势共振：1m方向必须与5m大方向一致
            if has5:
                tf5_val=s.get("tf5_trend",0)
                if total_score>40:
                    if tf5_val<=-0.5: d=Direction.NEUTRAL
                    else: d=Direction.BULLISH
                elif total_score<-40:
                    if tf5_val>=0.5: d=Direction.NEUTRAL
                    else: d=Direction.BEARISH
            else:
                if total_score>40: d=Direction.BULLISH
                elif total_score<-40: d=Direction.BEARISH
            # ADX弱趋势过滤：无趋势+中等信号 → 放弃
            if d!=Direction.NEUTRAL and adx_l<25 and abs(total_score)<50:
                d=Direction.NEUTRAL
            # 信心度
            cf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if d!=Direction.NEUTRAL and cf<35: d=Direction.NEUTRAL
            # 生成原因说明
            reason=[]
            if s.get("ema",0)>0.5: reason.append("EMA↑")
            elif s.get("ema",0)<-0.5: reason.append("EMA↓")
            if s.get("momentum",0)>0.5: reason.append("MOM↑")
            elif s.get("momentum",0)<-0.5: reason.append("MOM↓")
            if s.get("macd",0)>0.5: reason.append("MACD↑")
            elif s.get("macd",0)<-0.5: reason.append("MACD↓")
            if s.get("rsi",0)>0.5: reason.append("RSI超卖")
            elif s.get("rsi",0)<-0.5: reason.append("RSI超买")
            if s.get("micro",0)>0.5: reason.append("大阳线")
            elif s.get("micro",0)<-0.5: reason.append("大阴线")
            if s.get("bollinger",0)>0.5: reason.append("BB下轨")
            elif s.get("bollinger",0)<-0.5: reason.append("BB上轨")
            if s.get("volume",0)>0.5: reason.append("放量↑")
            if s.get("obv",0)>0.5: reason.append("OBV↑")
            elif s.get("obv",0)<-0.5: reason.append("OBV↓")
            if s.get("adx_filter",0)>0.3: reason.append("趋势强")
            if has5:
                if s.get("tf5_trend",0)>0.5: reason.append("5M↑")
                elif s.get("tf5_trend",0)<-0.5: reason.append("5M↓")
            r=",".join(reason[:5]) if reason else "中性"
            return {"direction":d.value,"score":round(total_score,1),"confidence":cf,"reason":r}
        candles_out = []
        signals_raw = []
        for i in range(len(df)):
            signal = _signal_at(i)
            ts = int(df["timestamp"].iloc[i])
            if signal and signal["direction"] != "neutral":
                # 实时模式：trade_start 之前的信号不产生交易（只预热指标）
                if trade_start_ms <= 0 or ts >= trade_start_ms:
                    signals_raw.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
            candles_out.append({
                "t": ts,
                "o": openp[i], "h": high[i], "l": low[i], "c": close[i],
                "v": vol[i], "s": signal,
            })

        # ---- 验证每个信号 ----
        trades = []
        for sr in signals_raw:
            idx = sr["idx"]
            sig = sr["sig"]
            entry_price = sr["price"]
            entry_ts = sr["ts"]

            # 验证：看 lookahead 期间价格是否触摸过入场价方向（用高/低点，更宽容）
            future_end = min(idx + lookahead, len(candles_out) - 1)
            future_start = idx + 1
            future_count = future_end - idx
            if future_count < lookahead:
                continue

            exit_price = close[future_end]

            is_bullish = sig["direction"] == "bullish"
            is_bearish = sig["direction"] == "bearish"

            # ---- 止盈止损验证 ----
            correct = False
            sl_hit = False
            tp_hit = False
            exit_reason = "时间到"

            for j in range(future_start, future_end + 1):
                bar_high = high[j]
                bar_low = low[j]

                if is_bullish:
                    # 止盈：最高价 >= 入场价 + tp
                    if tp_pct > 0 and bar_high >= entry_price * (1 + tp_pct / 100):
                        exit_price = entry_price * (1 + tp_pct / 100)
                        correct = True
                        tp_hit = True
                        exit_reason = "止盈"
                        break
                    # 止损：最低价 <= 入场价 - sl
                    if sl_pct > 0 and bar_low <= entry_price * (1 - sl_pct / 100):
                        exit_price = entry_price * (1 - sl_pct / 100)
                        correct = False
                        sl_hit = True
                        exit_reason = "止损"
                        break

                elif is_bearish:
                    # 止盈：最低价 <= 入场价 - tp
                    if tp_pct > 0 and bar_low <= entry_price * (1 - tp_pct / 100):
                        exit_price = entry_price * (1 - tp_pct / 100)
                        correct = True
                        tp_hit = True
                        exit_reason = "止盈"
                        break
                    # 止损：最高价 >= 入场价 + sl
                    if sl_pct > 0 and bar_high >= entry_price * (1 + sl_pct / 100):
                        exit_price = entry_price * (1 + sl_pct / 100)
                        correct = False
                        sl_hit = True
                        exit_reason = "止损"
                        break

            # 如果SL/TP都没触发，用收盘价验证方向
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
                "time": time.strftime("%m-%d %H:%M", time.localtime(entry_ts / 1000)),
                "direction": sig["direction"],
                "score": sig["score"],
                "confidence": sig["confidence"],
                "entry_price": round(entry_price, 1),
                "exit_price": round(exit_price, 1),
                "sl_price": round(entry_price * (1 - sl_pct / 100), 1) if sl_pct > 0 else None,
                "tp_price": round(entry_price * (1 + tp_pct / 100), 1) if tp_pct > 0 else None,
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
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")

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
            },
            "trades": trades,
            "candles": candles_out,
            "total_candles": len(candles_out),
            "prediction": prediction,
        })

    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/backtest/export")
def api_backtest_export():
    """导出回测结果 CSV，用于算法优化分析"""
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style", "short_term")
        lookahead = request.args.get("lookahead", 3, type=int)
        sl_pct = request.args.get("sl", 0.0, type=float)
        tp_pct = request.args.get("tp", 0.0, type=float)
        bar = "1m" if style == "short_term" else "4H"

        now_ms = int(time.time() * 1000)
        raw_start = request.args.get("start", "")
        raw_end = request.args.get("end", "")

        def _parse_ts(val: str, default: int) -> int:
            if not val: return default
            if val.isdigit(): return int(val)
            try:
                dt = datetime.fromisoformat(val)
                return int(dt.timestamp() * 1000)
            except: return default

        end_ts = _parse_ts(raw_end, now_ms)
        start_ts = _parse_ts(raw_start, end_ts - 7 * 86400_000)

        import pandas as pd
        from cryptopulse.config import DATA_DIR
        parquet_path = DATA_DIR / "BTC-USDT-SWAP" / f"klines_{bar.lower()}.parquet"
        if not parquet_path.exists() or parquet_path.stat().st_size == 0:
            return jsonify({"error": "数据文件不存在或为空"}), 404
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as e:
            return jsonify({"error": f"读取数据失败: {e}"}), 503
        mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
        df = df[mask].sort_values("timestamp").reset_index(drop=True)
        if len(df) < 100:
            return jsonify({"error": "数据不足"}), 503

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

        all_ema_f = emma(close, engine.ema_fast)
        all_ema_m = emma(close, engine.ema_mid)
        all_ema_s = emma(close, engine.ema_slow)
        all_rsi = rsi(close, engine.rsi_period)
        all_adx = adx(high, low, close, engine.adx_period)
        all_atr = atr(high, low, close, 14)
        all_vol_ma20 = sma(vol, 20)
        all_macd_line, all_macd_sig, all_macd_hist = macd(close, engine.macd_fast, engine.macd_slow, engine.macd_signal)
        all_bb_upper, all_bb_mid, all_bb_lower = bollinger(close, engine.bb_period, engine.bb_std)
        all_obv = obv(close, vol)

        records = []
        for i in range(99, len(df)):
            if i + lookahead >= len(df):
                break
            price = close[i]
            ema_f, ema_m, ema_s = all_ema_f[i], all_ema_m[i], all_ema_s[i]
            rsi_v = all_rsi[i]
            adx_v = all_adx[i]
            atr_v = all_atr[i]
            vol_ma20_v = all_vol_ma20[i]
            macd_h = all_macd_hist[i]
            rsi_v = all_rsi[i]
            bb_u = all_bb_upper[i]; bb_m = all_bb_mid[i]; bb_l = all_bb_lower[i]
            obv_v = all_obv[i]

            signals={}
            w={"ema":0.15,"momentum":0.12,"macd":0.14,"rsi":0.12,"micro":0.10,"bollinger":0.12,"volume":0.08,"obv":0.10,"adx_filter":0.07}
            vr=vol[i]/vol_ma20_v if vol_ma20_v>0 else 0
            if not np.isnan(ema_f) and not np.isnan(ema_m) and not np.isnan(ema_s):
                al=ema_f>ema_m>ema_s;be=ema_f<ema_m<ema_s
                if al and price>ema_f: signals["ema"]=1.0
                elif al: signals["ema"]=0.5
                elif be and price<ema_f: signals["ema"]=-1.0
                elif be: signals["ema"]=-0.5
                else: signals["ema"]=0.0
            else: signals["ema"]=0.0
            if i>=5:
                mom=(close[i]-close[i-5])/close[i-5]*100
                if mom>0.08: signals["momentum"]=1.0
                elif mom>0.03: signals["momentum"]=0.5
                elif mom<-0.08: signals["momentum"]=-1.0
                elif mom<-0.03: signals["momentum"]=-0.5
                else: signals["momentum"]=0.0
            else: signals["momentum"]=0.0
            if i>=2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):
                hp=all_macd_hist[i-1]
                if macd_h>0 and macd_h>hp: signals["macd"]=1.0
                elif macd_h>0: signals["macd"]=0.5
                elif macd_h<0 and macd_h<hp: signals["macd"]=-1.0
                elif macd_h<0: signals["macd"]=-0.5
                else: signals["macd"]=0.0
            else: signals["macd"]=0.0
            if not np.isnan(rsi_v):
                r=rsi_v
                if r>=80: signals["rsi"]=-1.0
                elif r>=70: signals["rsi"]=-0.5
                elif r>=60: signals["rsi"]=-0.2
                elif r>=45: signals["rsi"]=0.2
                elif r>=35: signals["rsi"]=0.0
                elif r>=25: signals["rsi"]=0.3
                elif r>=20: signals["rsi"]=0.6
                else: signals["rsi"]=1.0
            else: signals["rsi"]=0.0
            if not np.isnan(bb_u):
                if price>bb_u: signals["bollinger"]=-0.7
                elif price>bb_m: signals["bollinger"]=0.3
                elif price>bb_l: signals["bollinger"]=-0.3
                else: signals["bollinger"]=0.7
            else: signals["bollinger"]=0.0
            if vr>1.5:
                chg=(close[i]-close[i-4])/close[i-4] if i>=4 else 0
                signals["volume"]=0.8 if chg>0.002 else(-0.8 if chg<-0.002 else 0.3)
            elif vr>1.0: signals["volume"]=0.2
            elif vr>0.7: signals["volume"]=-0.2
            else: signals["volume"]=-0.3
            cr=high[i]-low[i]
            if cr>0:
                bd=abs(close[i]-openp[i]);br=bd/cr;cp=(close[i]-low[i])/cr
                uw=(high[i]-max(close[i],openp[i]))/cr;lw=(min(close[i],openp[i])-low[i])/cr
                if br>0.7 and cp>0.7: signals["micro"]=0.8
                elif br>0.7 and cp<0.3: signals["micro"]=-0.8
                elif uw>0.5 and br<0.3: signals["micro"]=-0.5
                elif lw>0.5 and br<0.3: signals["micro"]=0.5
                elif br<0.2 and vr>1.5: signals["micro"]=0.4 if cp>0.6 else(-0.4 if cp<0.4 else 0.0)
                else: signals["micro"]=0.0
            else: signals["micro"]=0.0
            if i>=5 and not np.isnan(obv_v):
                ot=(obv_v-all_obv[i-4])/(abs(all_obv[i-4])+1e-10)
                if ot>0.01: signals["obv"]=0.6
                elif ot<-0.01: signals["obv"]=-0.6
                else: signals["obv"]=0.0
            else: signals["obv"]=0.0
            adx_raw=adx_v if not np.isnan(adx_v) else 0
            if adx_raw>=35: signals["adx_filter"]=0.8
            elif adx_raw>=25: signals["adx_filter"]=0.3
            elif adx_raw>=20: signals["adx_filter"]=0.0
            else: signals["adx_filter"]=-0.3
            total=sum(signals.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            direction_str="bullish" if total_score>40 else("bearish" if total_score<-40 else "neutral")
            conf=min(100,max(10,int(abs(total_score)*0.9+min(adx_raw*1.0,20))))
            if direction_str!="neutral" and adx_raw<25 and abs(total_score)<50: direction_str="neutral"
            if direction_str!="neutral" and conf<35: direction_str="neutral"

            # 止盈止损验证
            sl_price = price * (1 - sl_pct / 100) if sl_pct > 0 else None
            tp_price = price * (1 + tp_pct / 100) if tp_pct > 0 else None
            exit_reason = "时间到"

            future_end = min(i + lookahead, len(close) - 1)
            future_start = i + 1
            exit_price = close[future_end]
            is_bull = direction_str == "bullish"
            is_bear = direction_str == "bearish"
            correct = None

            if is_bull or is_bear:
                for j in range(future_start, future_end + 1):
                    bar_high = high[j]
                    bar_low = low[j]
                    if is_bull:
                        if tp_pct > 0 and bar_high >= tp_price:
                            exit_price = tp_price
                            correct = True
                            exit_reason = "止盈"
                            break
                        if sl_pct > 0 and bar_low <= sl_price:
                            exit_price = sl_price
                            correct = False
                            exit_reason = "止损"
                            break
                    elif is_bear:
                        if tp_pct > 0 and bar_low <= price * (1 - tp_pct / 100):
                            exit_price = price * (1 - tp_pct / 100)
                            correct = True
                            exit_reason = "止盈"
                            break
                        if sl_pct > 0 and bar_high >= price * (1 + sl_pct / 100):
                            exit_price = price * (1 + sl_pct / 100)
                            correct = False
                            exit_reason = "止损"
                            break
                if correct is None:
                    exit_price = close[future_end]
                    if is_bull:
                        correct = bool(exit_price > price)
                    elif is_bear:
                        correct = bool(exit_price < price)

            pnl_pct = (exit_price / price - 1) * (100 if is_bull else -100) if (is_bull or is_bear) else 0

            records.append({
                "time": datetime.fromtimestamp(df["timestamp"].iloc[i] / 1000).strftime("%Y-%m-%d %H:%M"),
                "price": round(price, 1),
                "exit_price": round(exit_price, 1),
                "sl_price": round(sl_price, 1) if sl_price else "",
                "tp_price": round(tp_price, 1) if tp_price else "",
                "direction": direction_str,
                "total_score": round(total_score, 1),
                "confidence": conf,
                "correct": "Y" if correct else ("N" if correct is False else ""),
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": exit_reason,
                "ema": round(signals.get("ema", 0), 2),
                "momentum": round(signals.get("momentum", 0), 2),
                "macd": round(signals.get("macd", 0), 2),
                "rsi_val": round(rsi_v, 1) if not np.isnan(rsi_v) else "",
                "rsi_score": round(signals.get("rsi", 0), 2),
                "bb": round(signals.get("bollinger", 0), 2),
                "vol_ratio": round(vr, 2),
                "vol_score": round(signals.get("volume", 0), 2),
                "obv_score": round(signals.get("obv", 0), 2),
                "micro": round(signals.get("micro", 0), 2),
                "adx": round(adx_raw, 1) if not np.isnan(adx_raw) else "",
                "atr": round(atr_v, 2) if not np.isnan(atr_v) else "",
                "lookahead": lookahead,
            })

        if not records:
            return jsonify({"error": "无交易数据"}), 404

        out_df = pd.DataFrame(records)
        csv_str = out_df.to_csv(index=False, encoding="utf-8-sig")

        from flask import Response
        return Response(
            csv_str,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=backtest_{style}_{start_ts}_{end_ts}.csv",
                "Content-Type": "text/csv; charset=utf-8-sig",
            }
        )
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chart-data")
def chart_data():
    """返回本地 K 线 + 实时信号（数据源：update_data 持续更新的 Parquet 文件）"""
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style", "short_term")
        limit = request.args.get("limit", 500, type=int)
        limit = min(limit, 1000)
        bar = "1m" if style == "short_term" else "4H"

        # 优先从本地 Parquet 读取（update_data 持续更新），没有则回退到 OKX API
        import pandas as pd
        from cryptopulse.config import DATA_DIR
        parquet_path = DATA_DIR / "BTC-USDT-SWAP" / f"klines_{bar.lower()}.parquet"
        use_local = parquet_path.exists()

        if use_local:
            df = pd.read_parquet(parquet_path)
            df = df.sort_values("timestamp").tail(limit).reset_index(drop=True)
            if len(df) < 100:
                use_local = False

        if not use_local:
            raw_items = _fetch_candles(symbol, bar, limit)
            if not raw_items or len(raw_items) < 100:
                return jsonify({"error": f"need >=100 candles, got {len(raw_items) if raw_items else 0}"}), 503
            from cryptopulse.core.data.models import KLine
            all_klines = []
            for item in raw_items:
                try:
                    all_klines.append(KLine.from_okx(item))
                except Exception:
                    continue
        else:
            from cryptopulse.core.data.models import KLine
            all_klines = []
            for _, row in df.iterrows():
                try:
                    all_klines.append(KLine(
                        timestamp=int(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        volume_quote=0.0,
                    ))
                except Exception:
                    continue

        # 滑窗计算每个位置的信号
        clear_ts = _get_clear_timestamp()
        from cryptopulse.core.data.ring_buffer import KLineRingBuffer
        from cryptopulse.core.indicators.engine import TechnicalSignalEngine
        engine = TechnicalSignalEngine(style)
        buf = KLineRingBuffer(capacity=100, interval=bar)

        candles_out = []
        for i, k in enumerate(all_klines):
            buf.push(k)
            signal = None
            if i >= 99 and buf.is_full and k.timestamp > clear_ts:
                df = buf.to_dataframe()
                try:
                    result = engine.evaluate(df)
                    signal = {
                        "direction": result.direction.value,
                        "score": result.score,
                        "confidence": result.confidence,
                        "entry": result.entry_optimal,
                        "sl": result.stop_loss,
                        "tp1": result.take_profit_1,
                        "tp2": result.take_profit_2,
                        "tp3": result.take_profit_3,
                        "summary": result.summary,
                    }
                except Exception:
                    pass
                if signal and signal["direction"] != "neutral":
                    _save_chart_signal(k.timestamp, signal, k.close)

            candles_out.append({
                "t": k.timestamp,
                "o": k.open, "h": k.high, "l": k.low, "c": k.close,
                "v": k.volume,
                "s": signal,
            })

        # 最后一条信号的预测（下一根K线方向）
        prediction = None
        last_signal = candles_out[-1]["s"] if candles_out else None
        if last_signal:
            prediction = {
                "direction": last_signal["direction"],
                "score": last_signal["score"],
                "confidence": last_signal["confidence"],
            }

        return jsonify({
            "symbol": symbol, "style": style,
            "candles": candles_out, "total": len(candles_out),
            "prediction": prediction,
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


@app.route("/api/analysis")
def api_analysis():
    """信号统计分析"""
    records = _load_history(limit=10000)
    if not records:
        return jsonify({"total": 0})
    total = len(records)
    bullish = sum(1 for r in records if r.get("direction") == "bullish")
    bearish = sum(1 for r in records if r.get("direction") == "bearish")
    neutral = sum(1 for r in records if r.get("direction") == "neutral")
    has_result = [r for r in records if "result" in r]
    correct = sum(1 for r in has_result if r["result"] == "correct")
    wrong = sum(1 for r in has_result if r["result"] == "wrong")
    pending = sum(1 for r in has_result if r["result"] == "pending")
    return jsonify({
        "total": total, "bullish": bullish, "bearish": bearish, "neutral": neutral,
        "evaluated": len(has_result),
        "correct": correct, "wrong": wrong, "pending": pending,
    })


if __name__ == "__main__":
    print(f"[CryptoPulse] Starting on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=True)
