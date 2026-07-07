"""修复导出函数缺少的变量定义"""
with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()

# 在 rsi_v = all_rsi[i] 后面加上 bb_u, bb_m, bb_l, obv_v
old = "            rsi_v = all_rsi[i]\n\n            signals={}\n            w={\"ema\":0.10"
new = "            rsi_v = all_rsi[i]\n            bb_u = all_bb_upper[i]; bb_m = all_bb_mid[i]; bb_l = all_bb_lower[i]\n            obv_v = all_obv[i]\n\n            signals={}\n            w={\"ema\":0.10"
c = c.replace(old, new, 1)

with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)
print("✅ 导出函数缺失变量已补全")
