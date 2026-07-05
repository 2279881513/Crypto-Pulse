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

        # 时间范围：支持 start/end (Unix ms 或 ISO 日期)
        now_ms = int(time.time() * 1000)
        raw_start = request.args.get("start", "")
        raw_end = request.args.get("end", "")

        def _parse_ts(val: str, default: int) -> int:
            if not val:
                return default
            # 纯数字 → Unix ms
            if val.isdigit():
                return int(val)
            # ISO 格式 → 转 ms
            try:
                dt = datetime.fromisoformat(val)
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
        if not parquet_path.exists():
            return jsonify({"error": f"本地数据文件不存在: {parquet_path}"}), 404

        df = pd.read_parquet(parquet_path)
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
        all_ema_f = emma(close, engine.ema_fast)
        all_ema_m = emma(close, engine.ema_mid)
        all_ema_s = emma(close, engine.ema_slow)
        all_rsi = rsi(close, engine.rsi_period)
        all_bb_upper, all_bb_mid, all_bb_lower = bollinger(close, engine.bb_period, engine.bb_std)
        all_atr = atr(high, low, close, 14)
        all_adx = adx(high, low, close, engine.adx_period)
        all_obv = obv(close, vol)
        all_vol_ma20 = sma(vol, 20)
        all_macd_line, all_macd_sig, all_macd_hist = macd(close, engine.macd_fast, engine.macd_slow, engine.macd_signal)

        # === 加载 5m 数据做多时间框架分析 ===
        ts_5m_path = parquet_path.parent / "klines_5m.parquet"
        df_5m = pd.read_parquet(ts_5m_path) if ts_5m_path.exists() else pd.DataFrame()
        if not df_5m.empty:
            df_5m = df_5m.sort_values("timestamp").reset_index(drop=True)
            c5=df_5m["close"].values.astype(float); h5=df_5m["high"].values.astype(float)
            l5=df_5m["low"].values.astype(float); v5=df_5m["volume"].values.astype(float)
            ts5=df_5m["timestamp"].values
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

        # === 加载 15m 数据 ===
        ts_15m_path = parquet_path.parent / "klines_15m.parquet"
        df_15m = pd.read_parquet(ts_15m_path) if ts_15m_path.exists() else pd.DataFrame()
        if not df_15m.empty:
            df_15m = df_15m.sort_values("timestamp").reset_index(drop=True)
            c15=df_15m["close"].values.astype(float); h15=df_15m["high"].values.astype(float)
            l15=df_15m["low"].values.astype(float); v15=df_15m["volume"].values.astype(float)
            ts15=df_15m["timestamp"].values
            all_ema_f15 = emma(c15, engine.ema_fast*3); all_ema_m15 = emma(c15, engine.ema_mid*3); all_ema_s15 = emma(c15, engine.ema_slow*3)
            all_adx15 = adx(h15, l15, c15, engine.adx_period)
            all_macd_l15, all_macd_s15, all_macd_h15 = macd(c15, engine.macd_fast*3, engine.macd_slow*3, engine.macd_signal*3)
            idx_15m_map = []
            j = 0
            fifteen_min_ms = 15 * 60 * 1000
            for t in df["timestamp"].values:
                while j < len(ts15) - 1 and ts15[j+1] <= t:
                    j += 1
                idx_15m_map.append(j)
            idx_15m_map = np.array(idx_15m_map)
        else:
            idx_15m_map, all_ema_f15, all_ema_m15, all_ema_s15 = None, None, None, None
            all_adx15, all_macd_h15 = None, None
        engine = TechnicalSignalEngine(style)

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
def _signal_at(i: int) -> Optional[dict]:
            """1m+5m双框架评分"""
            if i < 99: return None
            price=close[i]; ema_f=all_ema_f[i]; ema_m=all_ema_m[i]; ema_s=all_ema_s[i]
            macd_h=all_macd_hist[i]; rsi_v=all_rsi[i]; bb_u=all_bb_upper[i]; bb_m=all_bb_mid[i]; bb_l=all_bb_lower[i]
            adx_v=all_adx[i]; obv_v=all_obv[i]; vr=vol[i]/all_vol_ma20[i] if all_vol_ma20[i]>0 else 0
            idx5=idx_5m_map[i] if idx_5m_map is not None else -1
            has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])
            s={}
            w={"ema":0.10,"momentum":0.08,"macd":0.08,"rsi":0.08,"micro":0.06,"bollinger":0.06,"volume":0.06,"obv":0.06,"adx_filter":0.06,"tf5_trend":0.18,"tf5_adx":0.08,"tf5_rsi":0.06,"tf5_macd":0.04}
            if not np.isnan(ema_f) and not np.isnan(ema_m) and not np.isnan(ema_s):
                al=ema_f>ema_m>ema_s;be=ema_f<ema_m<ema_s
                if al and price>ema_f: s["ema"]=-1.0
                elif al: s["ema"]=-0.5
                elif be and price<ema_f: s["ema"]=1.0
                elif be: s["ema"]=0.5
                else: s["ema"]=0.0
            else: s["ema"]=0.0
            if i>=5:
                mom=(close[i]-close[i-5])/close[i-5]*100
                if mom>0.08: s["momentum"]=-1.0
                elif mom>0.03: s["momentum"]=-0.5
                elif mom<-0.08: s["momentum"]=1.0
                elif mom<-0.03: s["momentum"]=0.5
                else: s["momentum"]=0.0
            else: s["momentum"]=0.0
            if i>=2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):
                hp=all_macd_hist[i-1]
                if macd_h>0 and macd_h>hp: s["macd"]=0.8
                elif macd_h>0: s["macd"]=0.3
                elif macd_h<0 and macd_h<hp: s["macd"]=-0.8
                elif macd_h<0: s["macd"]=-0.3
                else: s["macd"]=0.0
            else: s["macd"]=0.0
            if not np.isnan(rsi_v):
                r=rsi_v
                if r>=80: s["rsi"]=-1.0
                elif r>=70: s["rsi"]=-0.5
                elif r>=60: s["rsi"]=-0.2
                elif r>=55: s["rsi"]=0.2
                elif r>=45: s["rsi"]=0.0
                elif r>=40: s["rsi"]=-0.2
                elif r>=30: s["rsi"]=0.2
                elif r>=20: s["rsi"]=0.5
                else: s["rsi"]=1.0
            else: s["rsi"]=0.0
            if not np.isnan(bb_u):
                if price>bb_u: s["bollinger"]=-0.7
                elif price>bb_m: s["bollinger"]=0.3
                elif price>bb_l: s["bollinger"]=-0.3
                else: s["bollinger"]=0.7
            else: s["bollinger"]=0.0
            if vr>1.5:
                chg=(close[i]-close[i-4])/close[i-4] if i>=4 else 0
                s["volume"]=0.8 if chg>0.002 else(-0.8 if chg<-0.002 else 0.5)
            elif vr>1.0: s["volume"]=0.3
            elif vr>0.7: s["volume"]=-0.2
            else: s["volume"]=-0.5
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
            if i>=5 and not np.isnan(obv_v):
                ot=(obv_v-all_obv[i-4])/(abs(all_obv[i-4])+1e-10)
                if ot>0.01: s["obv"]=0.6
                elif ot<-0.01: s["obv"]=-0.6
                else: s["obv"]=0.0
            else: s["obv"]=0.0
            adx_l=adx_v if not np.isnan(adx_v) else 0
            if adx_l>=25 and adx_l<=40: s["adx_filter"]=0.3
            elif adx_l>40: s["adx_filter"]=0.8
            else: s["adx_filter"]=-0.5
            # 5m多时间框架
            if has5:
                ef5,em5,es5=all_ema_f5[idx5],all_ema_m5[idx5],all_ema_s5[idx5]
                if ef5>em5>es5: s["tf5_trend"]=1.0
                elif ef5<em5<es5: s["tf5_trend"]=-1.0
                else: s["tf5_trend"]=0.0
                adx5=all_adx5[idx5] if not np.isnan(all_adx5[idx5]) else 0
                if adx5>=35: s["tf5_adx"]=0.8; s["tf5_adx"]=0.3
                elif adx5>=25: s["tf5_adx"]=0.3
                else: s["tf5_adx"]=-0.5
                rsi5=all_rsi5[idx5] if not np.isnan(all_rsi5[idx5]) else 50
                if rsi5>75: s["tf5_rsi"]=-0.5
                elif rsi5<25: s["tf5_rsi"]=0.5
                else: s["tf5_rsi"]=0.0
                mh5=all_macd_h5[idx5] if not np.isnan(all_macd_h5[idx5]) else 0
                if mh5>0: s["tf5_macd"]=0.5
                elif mh5<0: s["tf5_macd"]=-0.5
                else: s["tf5_macd"]=0.0
            else:
                s["tf5_trend"]=0.0;s["tf5_adx"]=0.0;s["tf5_rsi"]=0.0;s["tf5_macd"]=0.0
            total=sum(s.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            d=Direction.NEUTRAL
            if total_score>30: d=Direction.BULLISH
            elif total_score<-30: d=Direction.BEARISH
            if d!=Direction.NEUTRAL and adx_l<25: d=Direction.NEUTRAL
            cf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if d!=Direction.NEUTRAL and cf<45: d=Direction.NEUTRAL
            return {"direction":d.value,"score":round(total_score,1),"confidence":cf}        candles_out = []
        signals_raw = []
        for i in range(len(df)):
            signal = _signal_at(i)
            if signal and signal["direction"] != "neutral":
                signals_raw.append({"idx": i, "sig": signal, "price": close[i], "ts": int(df["timestamp"].iloc[i])})
            candles_out.append({
                "t": int(df["timestamp"].iloc[i]),
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

            # 看后面 lookahead 根K线的收盘价
            future_end = min(idx + lookahead, len(candles_out) - 1)
            future_count = future_end - idx
            if future_count < lookahead:
                continue  # 没有足够未来数据

            exit_price = close[future_end]

            is_bullish = sig["direction"] == "bullish"
            is_bearish = sig["direction"] == "bearish"

            if is_bullish:
                correct = bool(exit_price > entry_price)
            elif is_bearish:
                correct = bool(exit_price < entry_price)
            else:
                continue  # 跳过中性

            # PnL 模拟（简单1:1方向，不含杠杆/仓位比例）
            pnl_pct = (exit_price / entry_price - 1) * (1 if is_bullish else -1) * 100

            trades.append({
                "timestamp": entry_ts,
                "time": time.strftime("%m-%d %H:%M", time.localtime(entry_ts / 1000)),
                "direction": sig["direction"],
                "score": sig["score"],
                "confidence": sig["confidence"],
                "entry_price": round(entry_price, 1),
                "exit_price": round(exit_price, 1),
                "lookahead": lookahead,
                "correct": correct,
                "pnl_pct": round(pnl_pct, 2),
                "sl": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
            })

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
        if not parquet_path.exists():
            return jsonify({"error": "数据文件不存在"}), 404

        df = pd.read_parquet(parquet_path)
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

            signals={}
            w={"ema":0.10,"momentum":0.08,"macd":0.08,"rsi":0.08,"micro":0.06,"bollinger":0.06,"volume":0.06,"obv":0.06,"adx_filter":0.06}
            vr=vol[i]/vol_ma20_v if vol_ma20_v>0 else 0
            if not np.isnan(ema_f) and not np.isnan(ema_m) and not np.isnan(ema_s):
                al=ema_f>ema_m>ema_s;be=ema_f<ema_m<ema_s
                if al and price>ema_f: signals["ema"]=-1.0
                elif al: signals["ema"]=-0.5
                elif be and price<ema_f: signals["ema"]=1.0
                elif be: signals["ema"]=0.5
                else: signals["ema"]=0.0
            else: signals["ema"]=0.0
            if i>=5:
                mom=(close[i]-close[i-5])/close[i-5]*100
                if mom>0.08: signals["momentum"]=-1.0
                elif mom>0.03: signals["momentum"]=-0.5
                elif mom<-0.08: signals["momentum"]=1.0
                elif mom<-0.03: signals["momentum"]=0.5
                else: signals["momentum"]=0.0
            else: signals["momentum"]=0.0
            if i>=2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):
                hp=all_macd_hist[i-1]
                if macd_h>0 and macd_h>hp: signals["macd"]=0.8
                elif macd_h>0: signals["macd"]=0.3
                elif macd_h<0 and macd_h<hp: signals["macd"]=-0.8
                elif macd_h<0: signals["macd"]=-0.3
                else: signals["macd"]=0.0
            else: signals["macd"]=0.0
            if not np.isnan(rsi_v):
                r=rsi_v
                if r>=engine.rsi_ob: signals["rsi"]=-1.0
                elif r>=70: signals["rsi"]=-0.5
                elif r>=60: signals["rsi"]=-0.2
                elif r>=55: signals["rsi"]=0.2
                elif r>=45: signals["rsi"]=0.0
                elif r>=40: signals["rsi"]=-0.2
                elif r>=30: signals["rsi"]=0.2
                elif r>=20: signals["rsi"]=0.5
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
                signals["volume"]=0.8 if chg>0.002 else(-0.8 if chg<-0.002 else 0.5)
            elif vr>1.0: signals["volume"]=0.3
            elif vr>0.7: signals["volume"]=-0.2
            else: signals["volume"]=-0.5
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
            if adx_raw>=25 and adx_raw<=40: signals["adx_filter"]=0.3
            elif adx_raw>40: signals["adx_filter"]=0.8
            else: signals["adx_filter"]=-0.5
            total=sum(signals.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            direction_str="bullish" if total_score>30 else("bearish" if total_score<-30 else "neutral")
            conf=min(100,max(10,int(abs(total_score)*0.9+min(adx_raw*1.0,20))))
            if direction_str!="neutral" and adx_raw<25: direction_str="neutral"
            if direction_str!="neutral" and conf<45: direction_str="neutral"

            # 未来价格验证
            future_end = min(i + lookahead, len(close) - 1)
            exit_price = close[future_end]
            is_bull = direction_str == "bullish"
            is_bear = direction_str == "bearish"
            correct = (exit_price > price) if is_bull else ((exit_price < price) if is_bear else None)
            pnl_pct = (exit_price / price - 1) * (100 if is_bull else -100) if (is_bull or is_bear) else 0

            records.append({
                "time": datetime.fromtimestamp(df["timestamp"].iloc[i] / 1000).strftime("%Y-%m-%d %H:%M"),
                "price": round(price, 1),
                "exit_price": round(exit_price, 1),
                "direction": direction_str,
                "total_score": round(total_score, 1),
                "confidence": conf,
                "correct": "Y" if correct else ("N" if correct is False else ""),
                "pnl_pct": round(pnl_pct, 2),
                "ema": round(sig.get("ema", 0), 2),
                "momentum": round(sig.get("momentum", 0), 2),
                "macd": round(sig.get("macd", 0), 2),
                "rsi_val": round(rsi_v, 1) if not np.isnan(rsi_v) else "",
                "rsi_score": round(sig.get("rsi", 0), 2),
                "bb": round(sig.get("bollinger", 0), 2),
                "vol_ratio": round(vol_ratio, 2),
                "vol_score": round(sig.get("volume", 0), 2),
                "obv_score": round(sig.get("obv", 0), 2),
                "micro": round(sig.get("micro", 0), 2),
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
    """返回 K 线 + 历史信号标注"""
    try:
        symbol = os.environ.get("SYMBOL", "BTC-USDT")
        style = request.args.get("style", "short_term")
        limit = request.args.get("limit", 500, type=int)
        limit = min(limit, 1000)
        bar = "1m" if style == "short_term" else "4H"

        # 分页获取 K 线
        raw_items = _fetch_candles(symbol, bar, limit)
        if not raw_items or len(raw_items) < 100:
            return jsonify({"error": f"need >=100 candles, got {len(raw_items) if raw_items else 0}"}), 503

        from cryptopulse.core.data.models import KLine
        from cryptopulse.core.data.ring_buffer import KLineRingBuffer
        from cryptopulse.core.indicators.engine import TechnicalSignalEngine

        all_klines = []
        for item in raw_items:
            try:
                all_klines.append(KLine.from_okx(item))
            except Exception:
                continue

        # 滑窗计算每个位置的信号
        clear_ts = _get_clear_timestamp()
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
