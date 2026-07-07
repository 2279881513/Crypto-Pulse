"""
修复 app.py — engine创建移到5m/15m数据加载之前 + 清理重复代码
"""
import re

with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# =============================================================
# 1. 删除第一个重复的5m加载块(行440-457不合理的位置)
# =============================================================
block1_start = c.find("            all_adx5 = adx(h5, l5, c5, engine.adx_period)")
if block1_start >= 0:
    block1_start = c.rfind("            ", 0, block1_start)  # 找到该行的缩进开始
    # 找到# === 加载 5m 数据之前
    marker = "# === 加载 5m 数据做多时间框架分析 ==="
    marker_pos = c.find(marker, block1_start)
    if marker_pos >= 0:
        # 从第一个5m相关代码到第二个5m之前
        block1_end = c.find("        # === 加载 5m 数据做多时间框架分析 ===", marker_pos + 10)
        if block1_end >= 0:
            c = c[:block1_start] + c[block1_end:]
            print("✅ 已删除第一份重复5m代码")
        else:
            print("⚠️ 未找到第二份5m代码起始")
    else:
        print("⚠️ 未找到5m标记")
else:
    print("⚠️ 未找到 all_adx5")

# =============================================================
# 2. 把 engine = TechnicalSignalEngine(style) 移到5m/15m之前
# =============================================================
# 先找现在 engine 的位置
eng_line = "engine = TechnicalSignalEngine(style)"
eng_pos = c.find(eng_line)
if eng_pos >= 0:
    # 找它前面的 marker
    # 找5m加载开始之前的一个空行位置
    mtf_start = c.find("# === 加载 5m 数据做多时间框架分析 ===")
    if mtf_start >= 0:
        # 把engine移到5m加载之前
        # 删除原来的engine行(保留后面的空行前移)
        c = c.replace(eng_line + "\n\n", "\n", 1)
        # 在5m加载前插入engine
        insert_pos = c.find("# === 加载 5m 数据做多时间框架分析 ===")
        if insert_pos >= 0:
            c = c[:insert_pos] + "        engine = TechnicalSignalEngine(style)\n\n" + c[insert_pos:]
            print("✅ engine已移到5m数据加载之前")
    else:
        print("⚠️ 未找到5m加载标记")
else:
    print("⚠️ 未找到engine行")

# =============================================================
# 3. 移除重复的15m代码中的冗余部分
# =============================================================
# 检查是否有两个all_vol_ma5
if c.count("all_vol_ma5 = sma(v5, 20)") > 1:
    first = c.find("all_vol_ma5 = sma(v5, 20)")
    second = c.find("all_vol_ma5 = sma(v5, 20)", first + 10)
    # 删除从second到下一个空行之前
    line_end = c.find("\n", second)
    while line_end < len(c) and c[line_end:line_end+1] == "\n":
        line_end += 1
    c = c[:second] + c[line_end:]
    print("✅ 移除重复的all_vol_ma5")

# =============================================================
# 4. 修复_score_at函数: s["rsi"]使用engine.rsi_ob
# =============================================================
# 检查是否有 r>=80: 而非 engine.rsi_ob
if 'if r>=80: s["rsi"]' in c:
    c = c.replace('if r>=80: s["rsi"]', 'if r>=engine.rsi_ob: s["rsi"]')
    print("✅ RSI评分恢复使用engine.rsi_ob")

# =============================================================
# 写入
# =============================================================
with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("\n✅ 修复完成！重启web服务后跑回测即可看到5m多时间框架效果。")
print("如果回测出错，检查控制台报错信息并贴给我。")
