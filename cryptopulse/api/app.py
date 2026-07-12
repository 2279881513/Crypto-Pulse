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
                     _unused1=None,_unused2=None,_unused3=None,_unused4=None,_unused5=None,
                     _unused6=None,_unused7=None,_unused8=None,_unused9=None,all_atr=None,_unused10=None,_unused11=None,all_vol_ma20=None,
                     _unused12=None,_unused13=None,_unused14=None,_unused15=None,_unused16=None,_unused17=None):
    """
    价格行为/结构策略 v2 — Deepseek 优化版
    Fix1: TP = max(波幅, ATR×2.0) 确保盈亏比 >= 1.33
    Fix2: 入场价 = pivot价位（模拟挂单突破），不等收盘
    Fix3: left=3 减少噪音假突破
    Fix4: 破位K线收盘位置过滤 + 跟随K线确认
    Fix6: 返回追踪止损参考位
    """
    LOOKBACK = 30
    if i < LOOKBACK: return None

    h_slice = high[max(0,i-LOOKBACK):i+1]
    l_slice = low[max(0,i-LOOKBACK):i+1]
    c = close[i]; o = openp[i]; h = high[i]; l = low[i]

    # Fix3: left=3 减少噪音
    left = 3
    pivots_high = []
    pivots_low = []
    for p in range(left, len(h_slice) - left):
        if h_slice[p] == max(h_slice[p-left:p+left+1]):
            pivots_high.append((i - LOOKBACK + p, h_slice[p]))
        if l_slice[p] == min(l_slice[p-left:p+left+1]):
            pivots_low.append((i - LOOKBACK + p, l_slice[p]))

    # ---- 趋势结构 ----
    trend = "neutral"
    ph_sorted = sorted(pivots_high, key=lambda x: x[0])
    pl_sorted = sorted(pivots_low, key=lambda x: x[0])
    if len(ph_sorted) >= 2 and len(pl_sorted) >= 2:
        last_two_ph = ph_sorted[-2:]
        last_two_pl = pl_sorted[-2:]
        ph_higher = last_two_ph[1][1] > last_two_ph[0][1]
        pl_higher = last_two_pl[1][1] > last_two_pl[0][1]
        if ph_higher and pl_higher:
            trend = "uptrend"
        elif not ph_higher and not pl_higher:
            trend = "downtrend"

    # ---- 关键价位 ----
    nearest_resistance = pivots_high[-1][1] if pivots_high else None
    nearest_support = pivots_low[-1][1] if pivots_low else None

    # ---- 成交量确认 ----
    vol_ma20 = all_vol_ma20[i] if all_vol_ma20 is not None and all_vol_ma20[i] > 0 else None
    vol_ratio = vol[i] / vol_ma20 if vol_ma20 else 1.0
    vol_confirm = vol_ratio > 1.5

    # ---- ATR 参考 ----
    atr_v = all_atr[i] if all_atr is not None and not np.isnan(all_atr[i]) else (c * 0.005)

    # ---- 入场信号 ----
    direction = "neutral"
    reasons = []
    confidence = 50
    entry_price = None  # Fix2: 入场价放pivot位（挂单突破）

    # Fix4: 破位K线收盘位置过滤
    # 做空：收盘在K线下半部分（实体>影线），证明空方主导
    bear_candle_ok = (c < o) and ((o - c) > (h - l) * 0.5)
    # 做多：收盘在K线上半部分
    bull_candle_ok = (c > o) and ((c - o) > (h - l) * 0.5)

    # 5a. 做空：下降趋势 + 跌破最近支撑 + 放量 + 空方K线
    if trend == "downtrend" and nearest_support is not None and c < nearest_support and vol_confirm and bear_candle_ok:
        direction = "bearish"
        confidence = 70
        if vol_ratio > 2.0: confidence = 75
        # Fix2: 入场价在支撑位（挂单突破）
        entry_price = nearest_support
        reasons.append("下破支撑 {:.1f}(放量{:.1f}x)".format(nearest_support, vol_ratio))

    # 5b. 做多：上升趋势 + 突破最近阻力 + 放量 + 多方K线
    if direction == "neutral" and trend == "uptrend" and nearest_resistance is not None and c > nearest_resistance and vol_confirm and bull_candle_ok:
        direction = "bullish"
        confidence = 70
        if vol_ratio > 2.0: confidence = 75
        entry_price = nearest_resistance
        reasons.append("上破阻力 {:.1f}(放量{:.1f}x)".format(nearest_resistance, vol_ratio))

    # 5c. 回踩确认
    if direction == "neutral":
        if nearest_resistance is not None and h >= nearest_resistance and c < nearest_resistance and c < o:
            direction = "bearish"; confidence = 65
            entry_price = nearest_resistance
            reasons.append("回踩阻力 {:.1f} 回落".format(nearest_resistance))
        if nearest_support is not None and l <= nearest_support and c > nearest_support and c > o:
            direction = "bullish"; confidence = 65
            entry_price = nearest_support
            reasons.append("回踩支撑 {:.1f} 反弹".format(nearest_support))

    # 5d. 连续实体（趋势延续）- 此时用收盘价入场
    if direction == "neutral" and i >= 2:
        # Fix4: 跟随K线确认 — 前一根确认破位，这根跟着走
        prev_body = abs(close[i-1] - openp[i-1])
        prev2_body = abs(close[i-2] - openp[i-2])
        avg_price = (c + o + close[i-1] + openp[i-1]) / 4
        if prev_body / avg_price > 0.002 and prev2_body / avg_price > 0.002:
            # 连续3根阴线（含当前）+ 放量
            if close[i-2] < openp[i-2] and close[i-1] < openp[i-1] and bear_candle_ok and vol_confirm:
                direction = "bearish"; confidence = 60
                entry_price = c  # 连续确认用收盘价
                reasons.append("连续实体阴线延续下跌")
            elif close[i-2] > openp[i-2] and close[i-1] > openp[i-1] and bull_candle_ok and vol_confirm:
                direction = "bullish"; confidence = 60
                entry_price = c
                reasons.append("连续实体阳线延续上涨")

    # ---- Fix1: 止盈 = max(波幅, ATR×2.0) 确保盈亏比 ----
    # Fix6: 返回追踪止损参考位
    tp1 = None; tp2 = None; tp3 = None; trail_activate = None
    
    if direction in ("bearish", "bullish") and entry_price is not None:
        is_short = direction == "bearish"
        # 波幅距离
        wave_dist = None
        if nearest_resistance is not None and nearest_support is not None:
            wave_dist = nearest_resistance - nearest_support
        # ATR 距离（保底）
        atr_dist = atr_v * 2.0
        
        # Fix1: TP距离 = max(波幅, ATR×2.0)
        if wave_dist is not None and wave_dist > 0:
            tp_dist = max(wave_dist, atr_dist)
        else:
            tp_dist = atr_dist
        
        if is_short:
            tp1 = entry_price - tp_dist
            tp2 = entry_price - tp_dist * 1.5
            tp3 = entry_price - tp_dist * 2.0
            # Fix6: 到达TP1后将止损移至成本价
            trail_activate = entry_price - tp_dist * 1.0
        else:
            tp1 = entry_price + tp_dist
            tp2 = entry_price + tp_dist * 1.5
            tp3 = entry_price + tp_dist * 2.0
            trail_activate = entry_price + tp_dist * 1.0

    score = int(confidence * 0.9) if direction == "bullish" else (-int(confidence * 0.9) if direction == "bearish" else 0)
    result_reason = ";".join(reasons) if reasons else ("上升趋势" if trend == "uptrend" else "下降趋势" if trend == "downtrend" else "盘整")

    return {
        "direction": direction, "score": score, "confidence": confidence,
        "reason": result_reason, "trend": trend,
        "vol_ratio": round(vol_ratio, 2),
        "entry_price": entry_price,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "trail_activate": trail_activate,
        "nearest_support": nearest_support, "nearest_resistance": nearest_resistance,
    }


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
        # 止损冷却控制
        sl_cooldown_ms = request.args.get("sl_cooldown", 300, type=int) * 1000  # 秒→毫秒
        sl_cooldown_enabled = request.args.get("sl_cooldown_enabled", "1", type=str) == "1"
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

        # ---- 批量计算信号 ----
        import numpy as np
        from cryptopulse.core.data.models import Direction
        from cryptopulse.core.indicators.calculations import atr, sma

        close = df["close"].values.astype(float)
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        vol = df["volume"].values.astype(float)
        openp = df["open"].values.astype(float)

        all_atr = atr(high, low, close, 14)
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
                    all_vol_ma20=all_vol_ma20, all_atr=all_atr)
            ts = int(df["timestamp"].iloc[i])
            if signal:
                all_signals.append({"idx": i, "sig": signal, "price": close[i], "ts": ts})
                if signal["direction"] != "neutral":
                    # 进场冷却检查
                    dir_now = signal["direction"]
                    if dir_now == last_trade_dir and i - last_trade_idx < cool_bars:
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
                    all_vol_ma20=all_vol_ma20, all_atr=all_atr)
                if sig:
                    dir_v = sig["direction"]
                    buf.write(f"{ts},{openp[i]},{high[i]},{low[i]},{close[i]},{vol[i]},{dir_v},{sig['score']},{sig['confidence']},{sig['reason']}\n")
            return Response(buf.getvalue(), mimetype="text/csv;charset=utf-8-sig", headers={"Content-Disposition": f"attachment; filename=klines_{style}.csv"})

        trades = []
        sl_cooldown_until = 0  # 止损冷却截止时间戳（毫秒）
        sl_cooldown_zones = []  # 收集冷却区间用于画线
        # 连续亏损保护
        max_consecutive_losses = 3  # 连续亏损N次后暂停该方向交易
        cons_losses = {"bullish": 0, "bearish": 0}  # 各方向连续亏损计数

        for sr in signals_raw:
            idx = sr["idx"]
            sig = sr["sig"]
            entry_price = sig.get("entry_price") or sr["price"]  # Fix2: 优先用信号返回的pivot入场价
            entry_ts = sr["ts"]
            dir_str = sig.get("direction", "")

            # ---- 连续亏损保护 ----
            if dir_str in ("bullish", "bearish"):
                if cons_losses[dir_str] >= max_consecutive_losses:
                    sig["risk_blocked"] = True
                    sig["risk_reason"] = f"连续{max_consecutive_losses}次亏损，暂停{dir_str}方向"
                    continue

            # ---- 止损冷却检查 ----
            if sl_cooldown_enabled and entry_ts < sl_cooldown_until:
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

            # ---- 止损: ATR×1.5, 止盈: 信号返回的tp1（已按 fix1 优化）----
            atr_entry = all_atr[idx] if not np.isnan(all_atr[idx]) else close[idx] * 0.005
            sl_mult = 1.5
            if is_bullish:
                sl_price = entry_price - atr_entry * sl_mult
                sl_init = sl_price
                # tp1 来自信号（= max(波幅, ATR×2.0)），有保底
                tp_price = sig.get("tp1") or (entry_price + atr_entry * 2.0)
                trail_activate = sig.get("trail_activate") or (entry_price + atr_entry * 2.0)
            elif is_bearish:
                sl_price = entry_price + atr_entry * sl_mult
                sl_init = sl_price
                tp_price = sig.get("tp1") or (entry_price - atr_entry * 2.0)
                trail_activate = sig.get("trail_activate") or (entry_price - atr_entry * 2.0)
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
                    # Fix6: 追踪止损 — 到达激活价后将止损移至成本价
                    if trail_activate is not None and bar_high >= trail_activate:
                        sl_price = max(sl_price, entry_price)
                        # 继续持仓，不移除激活标记
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
                    # Fix6: 追踪止损
                    if trail_activate is not None and bar_low <= trail_activate:
                        sl_price = min(sl_price, entry_price)
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
                "risk_n": 2.0,
                "exit_reason": exit_reason,
            })
            # 更新连续亏损计数（用于连续亏损保护）
            other_dir = "bearish" if dir_str == "bullish" else "bullish"
            if correct:
                cons_losses[dir_str] = 0
                cons_losses[other_dir] = 0  # 任意方向盈利时清零双方
            else:
                cons_losses[dir_str] += 1
                cons_losses[other_dir] = 0  # 另一方归零

        # ---- 传播风控标记到所有信号（用于K线图橙色箭头）----
        for item in all_signals:
            sig = item["sig"]
            if sig.get("cooled"):
                sig["risk_blocked"] = True
                sig["risk_reason"] = "同方向冷却间隔不足"
            # 已在回测循环中被设置为risk_blocked的信号保持原样

        # ---- 更新连续亏损计数 ----
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
                vr = vol[idx] / all_vol_ma20[idx] if all_vol_ma20[idx] > 0 else 1
                hr = time.gmtime(sr["ts"] / 1000).tm_hour
                is_dir = sig["direction"] != "neutral"
                # SL/TP验证
                entry_price = p
                # 方向对应的SL/TP — 根据5m ADX动态调整
                atr_entry = all_atr[idx] if not np.isnan(all_atr[idx]) else p * 0.005
                # 止盈 = 入场价 + n × ATR
                risk_n = 2.0
                sl_mult_sig = 1.5
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
                    "vol_ratio": round(vr, 2),
                    "atr": round(atr_v, 2),
                    "trend": sig.get("trend", ""),
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
                    "atr","vol_ratio","trend","风控原因"]
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
            "sl_cooldown_ms": sl_cooldown_ms,
            "sl_cooldown_enabled": sl_cooldown_enabled,
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
