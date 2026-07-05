"""完全替换 _signal_at 为 64.8% 的1m+5m双框架版本"""
import re

with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 找到 _signal_at 函数体
start = c.find('def _signal_at(i: int) -> Optional[dict]:')
body_start = c.find('"""', start) + 3
body_end = c.find('        candles_out = []', body_start)

# 新函数体 (正确的 64.8% 版本)
new_body = '"""计算第 i 根 K 线处的信号（1m+5m双框架）"""\n'
new_body += '''            if i < 99:
                return None
            price = close[i]
            ema_f, ema_m, ema_s = all_ema_f[i], all_ema_m[i], all_ema_s[i]
            macd_l, macd_s, macd_h = all_macd_line[i], all_macd_sig[i], all_macd_hist[i]
            rsi_v = all_rsi[i]
            bb_u, bb_m, bb_l = all_bb_upper[i], all_bb_mid[i], all_bb_lower[i]
            atr_v = all_atr[i]
            adx_v = all_adx[i]
            obv_v = all_obv[i]
            vol_ma20_v = all_vol_ma20[i]
            idx5=idx_5m_map[i] if idx_5m_map is not None else -1
            has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])

            signals={}
            w={"ema":0.10,"momentum":0.08,"macd":0.08,"rsi":0.08,"micro":0.06,"bollinger":0.06,"volume":0.06,"obv":0.06,"adx_filter":0.06,"tf5_trend":0.18,"tf5_adx":0.08,"tf5_rsi":0.06,"tf5_macd":0.04}
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
            adx_l=adx_v if not np.isnan(adx_v) else 0
            if adx_l>=25 and adx_l<=40: signals["adx_filter"]=0.3
            elif adx_l>40: signals["adx_filter"]=0.8
            else: signals["adx_filter"]=-0.5

            # 5m 趋势
            if has5:
                ef5,em5,es5=all_ema_f5[idx5],all_ema_m5[idx5],all_ema_s5[idx5]
                c5_price=all_ema_f5[idx5]
                if ef5>em5>es5 and c5_price>ef5: signals["tf5_trend"]=1.0
                elif ef5>em5>es5: signals["tf5_trend"]=0.5
                elif ef5<em5<es5 and c5_price<ef5: signals["tf5_trend"]=-1.0
                elif ef5<em5<es5: signals["tf5_trend"]=-0.5
                else: signals["tf5_trend"]=0.0
                adx5=all_adx5[idx5] if not np.isnan(all_adx5[idx5]) else 0
                if adx5>=35: signals["tf5_adx"]=0.8
                elif adx5>=25: signals["tf5_adx"]=0.3
                else: signals["tf5_adx"]=-0.5
                rsi5=all_rsi5[idx5] if not np.isnan(all_rsi5[idx5]) else 50
                if rsi5>75: signals["tf5_rsi"]=-0.5
                elif rsi5<25: signals["tf5_rsi"]=0.5
                else: signals["tf5_rsi"]=0.0
                mh5=all_macd_h5[idx5] if not np.isnan(all_macd_h5[idx5]) else 0
                if mh5>0: signals["tf5_macd"]=0.5
                elif mh5<0: signals["tf5_macd"]=-0.5
                else: signals["tf5_macd"]=0.0
            else:
                signals["tf5_trend"]=0.0;signals["tf5_adx"]=0.0;signals["tf5_rsi"]=0.0;signals["tf5_macd"]=0.0

            total=sum(signals.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            direction=Direction.NEUTRAL
            if total_score>30: direction=Direction.BULLISH
            elif total_score<-30: direction=Direction.BEARISH
            if direction!=Direction.NEUTRAL and adx_l<25: direction=Direction.NEUTRAL
            conf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if direction!=Direction.NEUTRAL and conf<45: direction=Direction.NEUTRAL
            return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}
'''

c2 = c[:body_start] + new_body + c[body_end:]

# 写回
with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c2)

print("✅ _signal_at 已完全替换为 64.8% 版本")
print("重启web服务后跑回测验证")
