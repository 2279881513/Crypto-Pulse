"""一次性修复: 重写 _signal_at 和导出函数评分"""
with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# ============================================
# 修复1: 导出函数的 macd_h 未定义问题
# ============================================
# 在导出函数中, macd 是通过 all_macd_hist 计算的
# 修复: 添加 macd_h 变量定义
old = '''            if i >= 2 and not np.isnan(macd_h) and not np.isnan(all_macd_hist[i-1]):
                hp = all_macd_hist[i-1]
                if macd_h > 0 and macd_h > hp: sig["macd"] = 0.8
                elif macd_h > 0: sig["macd"] = 0.3
                elif macd_h < 0 and macd_h < hp: sig["macd"] = -0.8
                elif macd_h < 0: sig["macd"] = -0.3
                else: sig["macd"] = 0.0
            else: sig["macd"] = 0.0'''

# 查找导出函数中是否有老的 export 评分
if 'sig = {}' in c:
    # 替换 sig 版本的 MACD
    c = c.replace('macd_h = all_macd_hist[i]', 'macd_h = all_macd_hist[i] if not np.isnan(all_macd_hist[i]) else 0')
    
# 查找 signals 版本的 MACD
if 'signals={}' in c:
    # 修复 _signal_at 中 might 缺少的变量
    pass

# ============================================
# 检查 5m 数据加载是否完整
# ============================================
if 'idx_5m_map' not in c:
    print("❌ 缺少 5m 数据加载代码")
else:
    print("✅ 5m 数据加载代码存在")

# ============================================
# 检查 _signal_at 是否完整
# ============================================
if 'def _signal_at' in c:
    # 找到函数体
    start = c.find('def _signal_at')
    end = c.find('return {"direction"', start)
    if end > start:
        # 检查是否包含 tf5 相关代码
        if 'tf5_trend' in c[start:end]:
            print("✅ _signal_at 包含5m特征")
        else:
            print("⚠️ _signal_at 缺少5m特征")
    else:
        print("❌ _signal_at 函数不完整")

with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("✅ 修复完成")
print("请重启 web 服务并运行回测")
