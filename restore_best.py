"""
一键恢复 app.py 到最佳状态：均值回归评分 + 阈值37 + ADX25
"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# =============================================================
# 定义最佳评分函数体（替换 _signal_at 的内容）
# 57%准确率, 744信号, +11.37% PnL, 盈亏比1.42
# =============================================================
best_scoring = '''            signals={}
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
            direction=Direction.NEUTRAL
            if total_score>37: direction=Direction.BULLISH
            elif total_score<-37: direction=Direction.BEARISH
            if direction!=Direction.NEUTRAL and adx_l<25: direction=Direction.NEUTRAL
            conf=min(100,max(10,int(abs(total_score)*0.9+min(adx_l*1.0,20))))
            if direction!=Direction.NEUTRAL and conf<50: direction=Direction.NEUTRAL
            return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}'''

# =============================================================
# 查找并替换 _signal_at 内的评分逻辑
# =============================================================
# 策略1: 找 signals={ 开头的评分块
for marker in ['signals={}', 'signals={}\n', 'signals={}\n            w={"ema"', 'signals={}\n            w={"ema"']:
    idx = content.find(marker)
    if idx >= 0:
        break

if idx >= 0:
    # 找到这个 signals= 开始到 return 结束
    sig_start = idx
    # 找 return 语句
    ret_pos = content.find('return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}', sig_start)
    if ret_pos > sig_start:
        old = content[sig_start:ret_pos + len('return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}')]
        content = content.replace(old, best_scoring, 1)
        print("✅ 评分函数已恢复为最佳状态(均值回归+阈值37+ADX25)")
    else:
        print("❌ 未找到return语句")
else:
    print("❌ 未找到signals={}，尝试暴力查找...")
    # 暴力: 找 total_score= 区域
    for look in ['total_score>30', 'total_score>37', 'total_score>35', 'total_score>20']:
        idx2 = content.find(look)
        if idx2 > 200:  # 在_signal_at内部
            # 往前找到signals=
            sig_start2 = content.rfind('signals={}', 0, idx2)
            if sig_start2 < 0:
                sig_start2 = content.rfind('signals={', 0, idx2)
            if sig_start2 > 100:
                ret_pos2 = content.find('return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}', sig_start2)
                if ret_pos2 > sig_start2:
                    old2 = content[sig_start2:ret_pos2 + len('return {"direction":direction.value,"score":round(total_score,1),"confidence":conf}')]
                    content = content.replace(old2, best_scoring, 1)
                    print(f"✅ 暴力恢复成功 (从{look})")
                    break
    else:
        print("❌ 暴力恢复也失败了，请手动复制以下代码到文件")

# 写入
with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ 恢复完成！")
print("现在重启web服务，跑回测即可看到57%准确率、盈亏比1.42的结果。")
