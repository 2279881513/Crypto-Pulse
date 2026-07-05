"""最终修复：完整替换 _signal_at 和 导出函数评分"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# ================================================
# 定位 _signal_at 函数的完整范围并替换
# ================================================
def_start = c.find('def _signal_at(i: int) -> Optional[dict]:')
def_end = c.find('        candles_out = []', def_start)

if def_start >= 0 and def_end > def_start:
    # 找到 def 行
    def_line_end = c.find('\n', def_start)
    
    # 构建新函数
    new_fn = '''def _signal_at(i: int) -> Optional[dict]:
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
            return {"direction":d.value,"score":round(total_score,1),"confidence":cf}'''
    
    c = c[:def_line_end] + '\n' + new_fn + c[def_end:]
    print("✅ _signal_at 已替换")
else:
    print("❌ 未找到 _signal_at")

# ================================================
# 修复导出函数中的 macd_h 错误
# ================================================
if 'macd_h = all_macd_hist[i]' in c:
    c = c.replace('macd_h = all_macd_hist[i]', 'macd_h = all_macd_hist[i] if not np.isnan(all_macd_hist[i]) else 0')
    print("✅ 导出函数 macd_h 已修复")

with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("\n✅ 修复完成！重启 web 服务后跑回测。")
print("预期结果: 准确率 ~65%, 信号量 ~1400")
