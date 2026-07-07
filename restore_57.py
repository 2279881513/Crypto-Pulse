"""
完全恢复 app.py — 纯1m均值回归, 阈值37, ADX25, 信心50
"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# ================================================
# 定义正确的评分代码（57%准确率版本）
# ================================================
correct_signal = '''            s={}
            w={"ema":0.15,"momentum":0.13,"macd":0.13,"rsi":0.13,"micro":0.12,"bollinger":0.10,"volume":0.08,"obv":0.08,"adx_filter":0.08}
            vr=vol[i]/vol_ma20_v if vol_ma20_v>0 else 0
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
                if r>=engine.rsi_ob: s["rsi"]=-1.0
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
            total=sum(s.get(k,0)*w.get(k,0) for k in w)
            total_score=max(-100,min(100,total*100))
            d=Direction.NEUTRAL
            if total_score>37: d=Direction.BULLISH
            elif total_score<-37: d=Direction.BEARISH
            if d!=Direction.NEUTRAL and adx_l<25: d=Direction.NEUTRAL
            cf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if d!=Direction.NEUTRAL and cf<50: d=Direction.NEUTRAL
            return {"direction":d.value,"score":round(total_score,1),"confidence":cf}'''

# ================================================
# 查找并替换 _signal_at 的评分代码
# ================================================
# 找到 s={} 的位置
idx = c.find('            s={}')
if idx < 0:
    idx = c.find('            signals={}')

if idx >= 0:
    # 找到这个评分块的结束 (return 语句)
    ret = c.find('return {"direction":', idx)
    if ret >= 0:
        ret_end = c.find('\n', ret)
        while ret_end < len(c) and c[ret_end:ret_end+4] in ['\n    ', '\n\n', '\n        ']:
            ret_end += 1
        # 从 s={} 到 return 行结束
        old_block = c[idx:ret_end]
        c = c.replace(old_block, correct_signal, 1)
        print("✅ _signal_at 已恢复为纯1m均值回归(57%版本)")
    else:
        print("❌ 未找到return")
else:
    print("❌ 未找到s={}")

# ================================================
# 删掉5m和15m的加载代码
# ================================================
c = c.replace('            idx5=idx_5m_map[i] if idx_5m_map is not None else -1\n            has5=idx5>=0 and all_ema_f5 is not None and not np.isnan(all_ema_f5[idx5])\n', '')
# 删除所有 tf5_ 相关的特征引用
for feat in ['"tf5_trend"', '"tf5_adx"', '"tf5_rsi"', '"tf5_macd"']:
    c = c.replace(feat + ',', '')
    c = c.replace(feat, '')
# 清理多余的逗号
c = c.replace(',,', ',')
c = c.replace(',}', '}')

with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)
print("✅ 5m无用代码已删除")
print("重启web服务跑回测。预期: 57%准确率, ~740信号, +11% PnL, 盈亏比1.4+")
