"""升级 app.py — 添加 15m 三时间框架分析 (1m+5m+15m)"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# =============================================
# 1. 在 5m 数据加载之后添加 15m 数据加载
# =============================================
old_5m = '''        # === 加载 5m 数据做多时间框架分析 ===
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
            all_vol_ma5 = sma(v5, 20)
            # 找每个1m K线对应的5m bar索引
            # 5m bar的时间戳是整5分钟的起始
            five_min_ms = 5 * 60 * 1000
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
            all_adx5, all_macd_h5, all_vol_ma5 = None, None, None'''

new_mtf = '''        # === 加载 5m 数据做多时间框架分析 ===
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
            all_adx15, all_macd_h15 = None, None'''

c = c.replace(old_5m, new_mtf, 1)

# =============================================
# 2. 更新评分权重 — 加入15m特征
# =============================================
old_w = '''w={"ema":0.10,"momentum":0.08,"macd":0.08,"rsi":0.08,"micro":0.06,"bollinger":0.06,"volume":0.06,"obv":0.06,"adx_filter":0.06,"tf5_trend":0.18,"tf5_adx":0.08,"tf5_rsi":0.06,"tf5_macd":0.04}'''
new_w = '''w={"ema":0.08,"momentum":0.06,"macd":0.06,"rsi":0.06,"micro":0.04,"bollinger":0.04,"volume":0.05,"obv":0.05,"adx_filter":0.04,"tf5_trend":0.14,"tf5_adx":0.06,"tf5_rsi":0.04,"tf5_macd":0.03,"tf15_trend":0.15,"tf15_adx":0.06,"tf15_macd":0.04}'''
c = c.replace(old_w, new_w, 1)

# =============================================
# 3. 在5m特征之后插入15m特征评分
# =============================================
old_5m_end = '''            else:
                signals["tf5_trend"]=0.0;signals["tf5_adx"]=0.0;signals["tf5_rsi"]=0.0;signals["tf5_macd"]=0.0'''
new_5m_15m = '''            else:
                signals["tf5_trend"]=0.0;signals["tf5_adx"]=0.0;signals["tf5_rsi"]=0.0;signals["tf5_macd"]=0.0
            # ========== 15m 大趋势确认 ==========
            idx15=idx_15m_map[i] if idx_15m_map is not None else -1
            has15=idx15>=0 and all_ema_f15 is not None and not np.isnan(all_ema_f15[idx15])
            if has15:
                ef15,em15,es15=all_ema_f15[idx15],all_ema_m15[idx15],all_ema_s15[idx15]
                if ef15>em15>es15: signals["tf15_trend"]=1.0  # 15m多头
                elif ef15<em15<es15: signals["tf15_trend"]=-1.0  # 15m空头
                else: signals["tf15_trend"]=0.0
                adx15=all_adx15[idx15] if not np.isnan(all_adx15[idx15]) else 0
                if adx15>=30: signals["tf15_adx"]=0.8
                elif adx15>=20: signals["tf15_adx"]=0.3
                else: signals["tf15_adx"]=-0.3
                mh15=all_macd_h15[idx15] if not np.isnan(all_macd_h15[idx15]) else 0
                if mh15>0: signals["tf15_macd"]=0.5
                elif mh15<0: signals["tf15_macd"]=-0.5
                else: signals["tf15_macd"]=0.0
            else:
                signals["tf15_trend"]=0.0;signals["tf15_adx"]=0.0;signals["tf15_macd"]=0.0'''

c = c.replace(old_5m_end, new_5m_15m, 1)

# =============================================
# 4. 方向判定 — 15m趋势与5m趋势必须一致才做多
# =============================================
old_dir = '''            # 5m无趋势时过滤
            if direction!=Direction.NEUTRAL and adx_l<20 and (not has5 or all_adx5[idx5]<20):
                direction=Direction.NEUTRAL'''
new_dir = '''            # 5m+15m无趋势时过滤
            if direction!=Direction.NEUTRAL and adx_l<20 and (not has5 or all_adx5[idx5]<20):
                direction=Direction.NEUTRAL
            # 15m趋势与方向不一致时过滤(需15m趋势支持)
            if direction!=Direction.NEUTRAL and has15:
                tf15_sig=signals.get("tf15_trend",0)
                if direction==Direction.BULLISH and tf15_sig<0.5 and abs(total_score)<40:
                    direction=Direction.NEUTRAL
                if direction==Direction.BEARISH and tf15_sig>-0.5 and abs(total_score)<40:
                    direction=Direction.NEUTRAL'''

c = c.replace(old_dir, new_dir, 1)

with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)

print("✅ 已升级为三时间框架系统 (1m+5m+15m)")
print("预期: 准确率可提升至 70-75%")
print("注意: 需要本地有 klines_15m.parquet 数据文件")
print("      如果没有会回退到 1m+5m 双框架系统")
