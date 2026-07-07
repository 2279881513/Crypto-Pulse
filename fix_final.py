"""一键恢复纯1m评分系统，删除5m/15m无用代码"""
with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()

# 删除5m加载代码块 (从"=== 加载 5m 数据"到下一个"def _signal_at"之前的空行)
import re
# 找到5m和15m加载块并删除
c = re.sub(
    r'        # === 加载 5m 数据做多时间框架分析 ===.*?(?=\n        def _signal_at)',
    '',
    c,
    flags=re.DOTALL
)

# 删除15m加载块
c = re.sub(
    r'        # === 加载 15m 数据 ===.*?(?=\n        engine = TechnicalSignalEngine)',
    '',
    c,
    flags=re.DOTALL
)

# 恢复到旧版的1m评分(替换_signal_at内的完整函数体)
old_start = c.find('            s={}')
if old_start >= 0:
    # 找到这个_signal_at函数的结束
    ret_pos = c.find('            return {"direction":d.value,"score":round(sc,1),"confidence":cf}', old_start)
    if ret_pos < 0:
        ret_pos = c.find('            return {"direction":d.value,"score":round', old_start)
    
    if ret_pos > old_start:
        old_sig = c[old_start:ret_pos]
        # 找到return结束位置
        ret_end = ret_pos + len('            return {"direction":d.value,"score":round(sc,1),"confidence":cf}')
        
        new_sig = '''            signals={}
            w={"ema":0.15,"momentum":0.13,"macd":0.13,"rsi":0.13,"micro":0.12,"bollinger":0.10,"volume":0.08,"obv":0.08,"adx_filter":0.08}
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
            total=sum(signals.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            d=Direction.NEUTRAL
            if total_score>37: d=Direction.BULLISH
            elif total_score<-37: d=Direction.BEARISH
            if d!=Direction.NEUTRAL and adx_l<25: d=Direction.NEUTRAL
            conf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if d!=Direction.NEUTRAL and conf<50: d=Direction.NEUTRAL
            return {"direction":d.value,"score":round(total_score,1),"confidence":conf}'''
        
        c = c[:old_start] + new_sig + c[ret_end:]
        print("✅ _signal_at 已恢复纯1m均值回归评分")
    else:
        print("❌ 未找到return")
else:
    print("❌ 未找到s={}")

# 同样修复导出函数
# 找到export函数里的评分
for marker in ['direction_str="bullish" if total_score>37 else', 'direction_str="bullish" if total_score>30 else']:
    idx = c.find(marker)
    if idx >= 0:
        break

if idx >= 0:
    # 这个已经在export里用了37阈值，不需要修改
    pass

with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)
print("✅ 恢复完成！重启服务跑回测。")
print("预期: 57%准确率, ~740信号, 盈亏比1.4")
