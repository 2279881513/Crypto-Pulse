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

from flask import Flask, render_template, jsonify, request, Response

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


def _compute_signal(i,close,high,low,openp,vol,
                     all_ema_f,all_ema_m,all_ema_s,all_macd_hist,all_rsi,
                     all_bb_upper,all_bb_mid,all_bb_lower,all_adx,all_obv,all_vol_ma20,
                     all_ema_f5=None,all_ema_m5=None,all_ema_s5=None,
                     all_adx5=None,all_rsi5=None,all_macd_h5=None,c5=None,idx_5m_map=None):
    """1m+5m双框架评分 — 与回测完全一致"""
    if i < 99: return None
    price=close[i]; ema_f=all_ema_f[i]; ema_m=all_ema_m[i]; ema_s=all_ema_s[i]
    macd_h=all_macd_hist[i]; rsi_v=all_rsi[i]
    bb_u=all_bb_upper[i]; bb_m=all_bb_mid[i]; bb_l=all_bb_lower[i]
    adx_v=all_adx[i]; obv_v=all_obv[i]
    vr=vol[i]/all_vol_ma20[i] if all_vol_ma20[i]>0 else 0
    idx5=idx_5m_map[i] if idx_5m_map is not None else -1
    has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])
    s={}
    w={"ema":0.15,"momentum":0.10,"macd":0.10,"rsi":0.08,"micro":0.06,"bollinger":0.08,"volume":0.06,"obv":0.06,"adx_filter":0.06,"tf5_trend":0.12,"tf5_adx":0.06,"tf5_rsi":0.04,"tf5_macd":0.03}
    # --- EMA ---
    if not np.isnan(ema_f) and not np.isnan(ema_m) and not np.isnan(ema_s):
        al=ema_f>ema_m>ema_s;be=ema_f<ema_m<ema_s
        if al and price>ema_f: s["ema"]=1.0
        elif al: s["ema"]=0.5
        elif be and price<ema_f: s["ema"]=-1.0
        elif be: s["ema"]=-0.5
        else: s["ema"]=0.0
    else: s["ema"]=0.0
    # --- 动量 ---
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
    # --- 微观 ---
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
    # --- ADX ---
    adx_l=adx_v if not np.isnan(adx_v) else 0
    if adx_l>=35: s["adx_filter"]=0.8
    elif adx_l>=25: s["adx_filter"]=0.3
    elif adx_l>=20: s["adx_filter"]=0.0
    else: s["adx_filter"]=-0.3
    # --- 5m ---
    if has5:
        ef5,em5,es5=all_ema_f5[idx5],all_ema_m5[idx5],all_ema_s5[idx5]
        c5_p=c5[idx5] if idx5<len(c5) else price
        if ef5>em5>es5 and c5_p>ef5: s["tf5_trend"]=1.0
        elif ef5<em5<es5 and c5_p<ef5: s["tf5_trend"]=-1.0
        elif ef5>em5>es5: s["tf5_trend"]=0.5
        elif ef5<em5<es5: s["tf5_trend"]=-0.5
        else: s["tf5_trend"]=0.0
        ax5=all_adx5[idx5] if not np.isnan(all_adx5[idx5]) else 0
        if ax5>=35: s["tf5_adx"]=0.8
        elif ax5>=25: s["tf5_adx"]=0.3
        elif ax5>=20: s["tf5_adx"]=0.0
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
        else: s["tf5_macd"]=0.0
    else:
        s["tf5_trend"]=0.0;s["tf5_adx"]=0.0;s["tf5_rsi"]=0.0;s["tf5_macd"]=0.0
    total=sum(s.get(k,0)*w.get(k,0) for k in w)
    total_score=max(-100,min(100,total*100))
    d="neutral"
    if has5:
        tf5_val=s.get("tf5_trend",0)
        if total_score>40:
            d="neutral" if tf5_val<=-0.5 else "bullish"
        elif total_score<-40:
            d="neutral" if tf5_val>=0.5 else "bearish"
    else:
        if total_score>40: d="bullish"
        elif total_score<-40: d="bearish"
    if d!="neutral" and adx_l<25 and abs(total_score)<50:
        d="neutral"
    cf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
    if d!="neutral" and cf<35: d="neutral"
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
    return {"direction":d,"score":round(total_score,1),"confidence":cf,"reason":r,"signals":s,"adx_val":adx_l,"rsi_val":rsi_v if not np.isnan(rsi_v) else 50}


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
        fee_rate = request.args.get("fee", 0.0005, type=float)
        cap = request.args.get("cap", 1000, type=float)
        lev = request.args.get("lev", 1, type=float)
        fee_filter = request.args.get("fee_filter", "0", type=str) == "1"
        # 实时模式：只统计此时间戳之后的交易
        trade_start_ms = request.args.get("trade_start", 0, type=int)
        # 导出模式：跳过K线数据生成，只返回交易数据
        csv_export = request.args.get("format") == "csv"

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

        candles_out = []
        signals_raw = []
        for i in range(len(df)):
            signal = _compute_signal(i, close, high, low, openp, vol,
                    all_ema_f, all_ema_m, all_ema_s, all_macd_hist, all_rsi,
                    all_bb_upper, all_bb_mid, all_bb_lower, all_adx, all_obv, all_vol_ma20,
                    all_ema_f5, all_ema_m5, all_ema_s5,
                    all_adx5, all_rsi5, all_macd_h5, c5, idx_5m_map)
            ts = int(df["timestamp"].iloc[i])
            if signal and signal["direction"] != "neutral":
                if trade_start_ms <= 0 or ts >= trade_start_ms:
                    signals_raw.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
            if not csv_export:
                candles_out.append({
                    "t": ts,
                    "o": openp[i], "h": high[i], "l": low[i], "c": close[i],
                    "v": vol[i], "s": signal,
                })
        trades = []
        for sr in signals_raw:
            idx = sr["idx"]
            sig = sr["sig"]
            entry_price = sr["price"]
            entry_ts = sr["ts"]

            # 验证：看 lookahead 期间价格是否触摸过入场价方向（用高/低点，更宽容）
            future_end = min(idx + lookahead, len(df) - 1)
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

        # ---- CSV导出（format=csv模式） ----
        if csv_export:
            if not trades:
                return jsonify({"error": "没有交易数据"}), 404
            # 丰富详细字段
            sig_by_ts = {sr["ts"]: sr["sig"] for sr in signals_raw}
            for t in trades:
                sig = sig_by_ts.get(t["timestamp"])
                s = sig.get("signals", {}) if sig else {}
                idx = None
                for sr in signals_raw:
                    if sr["ts"] == t["timestamp"]:
                        idx = sr["idx"]; break
                if idx is not None:
                    p = close[idx]
                    atr_v = all_atr[idx]
                    t["max_favorable_pct"] = 0
                    t["max_adverse_pct"] = 0
                    t["sl_dist_pct"] = round(sl_pct, 2)
                    t["tp_dist_pct"] = round(tp_pct, 2)
                    t["signal_reason"] = sig["reason"]
                    t["trade_duration"] = lookahead
                    t["entry_atr_pct"] = round(atr_v / p * 100, 2) if not np.isnan(atr_v) else 0
                    t["price_trend"] = "up" if p > openp[idx] else "down"
                    t["entry_bar_dir"] = t["price_trend"]
                    t["hour_of_day"] = time.localtime(t["timestamp"] / 1000).tm_hour
                    adx_v = all_adx[idx] if not np.isnan(all_adx[idx]) else 20
                    t["adx_category"] = "强趋势" if adx_v >= 35 else ("中趋势" if adx_v >= 25 else ("弱趋势" if adx_v >= 20 else "无趋势"))
                    t["fee_cost"] = round(fee_rate * 2 * 100, 3)
                    t["net_pnl_pct"] = round(t["pnl_pct"] - t["fee_cost"], 4)
                    t["ema"] = round(s.get("ema", 0), 2)
                    t["momentum"] = round(s.get("momentum", 0), 2)
                    t["macd"] = round(s.get("macd", 0), 2)
                    t["rsi_val"] = round(sig.get("rsi_val", 50), 1)
                    t["rsi_score"] = round(s.get("rsi", 0), 2)
                    t["bb"] = round(s.get("bollinger", 0), 2)
                    vr = vol[idx] / all_vol_ma20[idx] if all_vol_ma20[idx] > 0 else 1
                    t["vol_ratio"] = round(vr, 2)
                    t["vol_score"] = round(s.get("volume", 0), 2)
                    t["obv_score"] = round(s.get("obv", 0), 2)
                    t["micro"] = round(s.get("micro", 0), 2)
                    t["adx"] = round(adx_v, 1)
                    t["atr"] = round(atr_v, 2) if not np.isnan(atr_v) else 0
            if fee_filter:
                mn = fee_rate * 2 * 100
                trades = [r for r in trades if abs(r["pnl_pct"]) >= mn]
            if not trades:
                return jsonify({"error": "过滤后无交易数据"}), 404
            # 序号放第一列，重新排序
            ordered = []
            first_cols = ["#","time","price","exit_price","sl_price","tp_price","direction","total_score","confidence","correct","pnl_pct","exit_reason","max_favorable_pct","max_adverse_pct","sl_dist_pct","tp_dist_pct","signal_reason","trade_duration","entry_atr_pct","price_trend","entry_bar_dir","hour_of_day","adx_category","fee_cost","net_pnl_pct","ema","momentum","macd","rsi_val","rsi_score","bb","vol_ratio","vol_score","obv_score","micro","adx","atr","lookahead"]
            # 加 price 别名
            for t in trades:
                t["price"] = t.get("entry_price", 0)
                t["total_score"] = t.get("score", 0)
                t["correct"] = "Y" if t.get("correct") else "N"
            for n, r in enumerate(trades, 1):
                r["#"] = n
            import io as _io
            b = _io.StringIO()
            b.write("【回测结果汇总】\n")
            if fee_filter: b.write(f"(已开启保本过滤, 阈值 {round(fee_rate*2*100,3)}%)\n")
            total_t = len(trades)
            c_n = sum(1 for r in trades if r["correct"] == "Y")
            tp_t = sum(r["pnl_pct"] for r in trades)
            ws = [r for r in trades if r["pnl_pct"] > 0]
            ls = [r for r in trades if r["pnl_pct"] <= 0]
            ft = round(total_t * fee_rate * 2 * 100, 2)
            nt = round(tp_t - ft, 2)
            b.write(f"交易笔数,{total_t}\n正确,{c_n} ({round(c_n/total_t*100,1)}%)\n错误,{total_t-c_n} ({round((total_t-c_n)/total_t*100,1)}%)\n")
            b.write(f"准确率,{round(c_n/total_t*100,1)}%\n总毛利,{round(tp_t,2)}%\n总手续费,{ft}%\n净利,{nt}%\n")
            b.write(f"胜率,{round(len(ws)/total_t*100,1)}%\n")
            pf2 = round(abs(sum(r['pnl_pct'] for r in ws)/max(abs(sum(r['pnl_pct'] for r in ls)),1e-10)),2) if ls else 0
            b.write(f"盈亏比,{pf2}\n")
            b.write(f"平均盈,{round(sum(r['pnl_pct'] for r in ws)/len(ws),2) if ws else 0}%\n平均亏,{round(sum(r['pnl_pct'] for r in ls)/len(ls),2) if ls else 0}%\n")
            sc = sum(1 for r in trades if r["exit_reason"] == "止损")
            tc2 = sum(1 for r in trades if r["exit_reason"] == "止盈")
            imc = sum(1 for r in trades if r["exit_reason"] == "时间到")
            b.write(f"止损,{sc}笔({round(sc/total_t*100,1)}%)\n止盈,{tc2}笔({round(tc2/total_t*100,1)}%)\n时间到,{imc}笔({round(imc/total_t*100,1)}%)\n")
            b.write(f"\n【仓位参数】\n本金,{cap} USDT\n杠杆,{int(lev)}x\n费率,{round(fee_rate*100,2)}%\n每笔手续费,{round(fee_rate*2*100,3)}%\n总手续费金额,{round(ft*cap*lev/100,1)} USDT\n")
            b.write("\n【每笔交易明细】\n")
            # 用有序列写
            csv_df = pd.DataFrame(trades)
            avail_cols = [c for c in first_cols if c in csv_df.columns]
            csv_df[avail_cols].to_csv(b, index=False)
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            return Response(b.getvalue(), mimetype="text/csv;charset=utf-8-sig", headers={"Content-Disposition": f"attachment; filename=backtest_{style}_{ts_str}.csv"})

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


def chart_data():
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
