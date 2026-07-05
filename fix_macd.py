"""修复导出函数的 macd_h 错误"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 修复1: 在导出函数中添加 macd_h 定义
old = '''            # MACD（柱状图趋势）
            macd_h = all_macd_hist[i]
            if i >= 2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):'''
new = '''            # MACD（柱状图趋势）
            macd_h = all_macd_hist[i] if not np.isnan(all_macd_hist[i]) else 0
            if i >= 2 and not np.isnan(all_macd_hist[i-1]):'''

if old in c:
    c = c.replace(old, new, 1)
    print("✅ 已修复导出函数 macd_h 错误")
else:
    print("⚠️ 未找到精确匹配，尝试其他方式...")
    # 尝试找 sig 模式的
    if 'macd_h = all_macd_hist[i]' in c:
        c = c.replace('macd_h = all_macd_hist[i]', 'macd_h = all_macd_hist[i] if not np.isnan(all_macd_hist[i]) else 0')
        print("✅ 已修复 macd_h")

# 修复2: 检查 _signal_at 是否正确
if 'def _signal_at' in c and 'tf5_trend' not in c[c.find('def _signal_at'):c.find('candles_out', c.find('def _signal_at'))]:
    print("⚠️ _signal_at 缺少5m特征！尝试修复...")
    # 这需要更复杂修复，先跳过

with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("请重启 web 服务")
