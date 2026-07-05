with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()

# 修复残留行和插入正确评分代码
old = '''            vol_ma20_v = all_vol_ma20[i]

                direction_str = "neutral"

            # 未来价格验证'''

new = '''            vol_ma20_v = all_vol_ma20[i]

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

            # 未来价格验证'''

if old in c:
    c=c.replace(old,new,1)
    with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
        f.write(c)
    print("✅ 导出函数评分已同步更新")
else:
    print("❌ 未找到匹配区域")
    # 打印附近字符以便调试
    idx=c.find('vol_ma20_v = all_vol_ma20[i]')
    if idx>=0:
        print(f"找到位置 {idx}: {repr(c[idx:idx+100])}")
