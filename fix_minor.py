with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()
# 修复1: 重复赋值
c=c.replace('if adx5>=35: s["tf5_adx"]=0.8; s["tf5_adx"]=0.3','if adx5>=35: s["tf5_adx"]=0.8')
# 修复2: return和candles_out挤在一起
c=c.replace('"confidence":cf}        candles_out = []','"confidence":cf}\n        candles_out = []')
with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)
print("✅ 修复完成")
