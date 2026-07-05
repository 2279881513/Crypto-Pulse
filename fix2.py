with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()
c=c.replace('candles_out = []candles_out = []','candles_out = []')
with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)
print("✅ 重复行已修复")
