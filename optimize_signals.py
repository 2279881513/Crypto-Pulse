"""
CryptoPulse 信号优化器 — 修复版
=================================
用法: python optimize_signals.py
无额外依赖 (pandas/numpy 即可)
"""

import pandas as pd
import numpy as np

# ============================================================
# 1. 加载数据
# ============================================================
df = pd.read_csv('.reasonix/attachments/clipboard-20260706-020041.957346-000003.csv')
directional = df[df['direction'] != 'neutral'].copy()
y = (directional['correct'] == 'Y').astype(int).values

print(f"=== 基线 ===")
print(f"总信号: {len(directional)}")
print(f"准确率: {y.mean()*100:.1f}%")
print()

# ============================================================
# 2. 暴力搜索最优阈值组合
# ============================================================
print("=" * 60)
print("方案一: 暴力搜索最优 total_score 阈值 + ADX 阈值")
print("=" * 60)

best_acc = 0
best_combo = None
results = []

for score_th in range(15, 55, 2):
    for adx_th in [0, 15, 20, 25, 30, 35]:
        mask = (directional['total_score'].abs() >= score_th)
        if adx_th > 0:
            mask &= (directional['adx'] >= adx_th)
        
        subset = directional[mask]
        if len(subset) < 50:
            continue
            
        acc = (subset['correct'] == 'Y').mean()
        total_pnl = subset['pnl_pct'].sum()
        n_signals = len(subset)
        
        results.append((score_th, adx_th, n_signals, acc, total_pnl))
        
        if acc > best_acc and n_signals >= 100:
            best_acc = acc
            best_combo = (score_th, adx_th, n_signals, acc, total_pnl)

results.sort(key=lambda x: -x[3])
print(f"\nTop 10 参数组合 (信号量>=100):")
print(f"{'阈值':>5} {'ADX':>4} {'信号数':>6} {'准确率':>7} {'总PnL':>8}")
for r in results[:10]:
    if r[2] >= 100:
        print(f"{r[0]:5d} {r[1]:4d} {r[2]:6d} {r[3]:6.1%} {r[4]:+8.2f}%")

print(f"\n最佳组合: 阈值={best_combo[0]}, ADX>={best_combo[1]}")
print(f"  信号量={best_combo[2]}, 准确率={best_combo[3]*100:.1f}%, 总PnL={best_combo[4]:+.2f}%")

# ============================================================
# 3. 用 numpy 做简单逻辑回归 (无需 sklearn)
# ============================================================
print("\n" + "=" * 60)
print("方案二: 用 Numpy 实现逻辑回归 — 找最优特征权重")
print("=" * 60)

feature_cols = ['ema', 'momentum', 'macd', 'rsi_score', 'bb', 
                'vol_score', 'obv_score', 'micro']
X = directional[feature_cols].fillna(0).values
y_bin = y.copy()

# 标准化
mean = X.mean(axis=0)
std = X.std(axis=0)
std[std == 0] = 1
X_scaled = (X - mean) / std

# 用梯度下降训练逻辑回归 (无 sklearn 依赖)
def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -100, 100)))

n_samples, n_features = X_scaled.shape
weights = np.zeros(n_features)
bias = 0.0
lr = 0.1
n_iters = 5000

for i in range(n_iters):
    z = np.dot(X_scaled, weights) + bias
    pred = sigmoid(z)
    error = pred - y_bin
    
    dw = np.dot(X_scaled.T, error) / n_samples
    db = np.mean(error)
    
    weights -= lr * dw
    bias -= lr * db

# 计算准确率
probs = sigmoid(np.dot(X_scaled, weights) + bias)
y_pred = (probs >= 0.5).astype(int)
lr_acc = (y_pred == y_bin).mean()
print(f"逻辑回归训练集准确率: {lr_acc*100:.1f}%")

print(f"\n学习到的最优权重 (标准化后):")
for name, coef in sorted(zip(feature_cols, weights), key=lambda x: -abs(x[1])):
    print(f"  {name:12s}: {coef:+.4f}")

print(f"\nLR概率分桶准确率:")
for lo in np.arange(0.5, 0.85, 0.05):
    hi = lo + 0.05
    mask = (probs >= lo) & (probs < hi)
    if mask.sum() > 10:
        acc_bucket = y_bin[mask].mean()
        print(f"  prob∈[{lo:.2f},{hi:.2f}): {mask.sum():4d}个, 准确率{acc_bucket*100:.1f}%")

# ============================================================
# 4. confidence 阈值过滤
# ============================================================
print("\n" + "=" * 60)
print("方案三: confidence 阈值过滤优化")
print("=" * 60)

for conf_th in [30, 35, 40, 45, 50, 55, 60]:
    mask = directional['confidence'] >= conf_th
    sub = directional[mask]
    if len(sub) > 0:
        acc = (sub['correct'] == 'Y').mean()
        pnl = sub['pnl_pct'].sum()
        print(f"  conf>={conf_th:2d}: 信号{len(sub):4d} ({len(sub)/len(directional)*100:4.1f}%) | "
              f"准确率{acc*100:.1f}% | 总PnL{pnl:+.2f}%")

# ============================================================
# 5. 综合策略对比 (含 LR 概率)
# ============================================================
print("\n" + "=" * 60)
print("方案四: 综合策略对比")
print("=" * 60)

strategies = [
    ("原始(score>=20)", directional['total_score'].abs() >= 20),
    ("score>=25", directional['total_score'].abs() >= 25),
    ("score>=30", directional['total_score'].abs() >= 30),
    ("score>=35", directional['total_score'].abs() >= 35),
    ("score>=25 & ADX>=25", 
     (directional['total_score'].abs() >= 25) & (directional['adx'] >= 25)),
    ("score>=30 & ADX>=25", 
     (directional['total_score'].abs() >= 30) & (directional['adx'] >= 25)),
    ("score>=35 & ADX>=25", 
     (directional['total_score'].abs() >= 35) & (directional['adx'] >= 25)),
    ("score>=25 & conf>=45", 
     (directional['total_score'].abs() >= 25) & (directional['confidence'] >= 45)),
    ("score>=30 & conf>=50", 
     (directional['total_score'].abs() >= 30) & (directional['confidence'] >= 50)),
    ("score>=25 & ADX>=25 & conf>=40", 
     (directional['total_score'].abs() >= 25) & (directional['adx']>=25) & (directional['confidence']>=40)),
    ("LR_prob>=0.55", probs >= 0.55),
    ("LR_prob>=0.60", probs >= 0.60),
    ("LR_prob>=0.65", probs >= 0.65),
]

for name, mask in strategies:
    sub = directional[mask]
    if len(sub) > 0:
        acc = (sub['correct'] == 'Y').mean()
        pnl = sub['pnl_pct'].sum()
        avg_win = sub.loc[sub['correct']=='Y', 'pnl_pct'].mean() if (sub['correct']=='Y').any() else 0
        avg_loss = sub.loc[sub['correct']=='N', 'pnl_pct'].mean() if (sub['correct']=='N').any() else 0
        print(f"  {name:35s}: 信号{len(sub):4d} ({len(sub)/len(directional)*100:4.1f}%) | "
              f"正确率{acc*100:.1f}% | PnL{pnl:+.2f}% | "
              f"均赢{avg_win:+.3f}% 均亏{avg_loss:+.3f}%")

# ============================================================
# 6. 用新权重重建 total_score 看效果
# ============================================================
print("\n" + "=" * 60)
print("方案五: 新权重重建 total_score 效果测试")
print("=" * 60)

# 新权重配置
new_weights = {
    'ema': 0.25, 'momentum': 0.15, 'macd': 0.10,
    'rsi_score': 0.10, 'bb': 0.10, 'obv_score': 0.12,
    'vol_score': 0.08, 'micro': 0.05
}

# 计算新总分 (按比例缩放到与旧 total_score 相近的量级)
old_scores = directional['total_score'].abs()
new_scores_raw = sum(directional[col] * w for col, w in new_weights.items())
# 缩放到与旧分数相同量级
scale_factor = old_scores.mean() / new_scores_raw.abs().mean()
new_scores = new_scores_raw * scale_factor

print(f"\n新权重计算的分数分布:")
print(f"  均值: {new_scores.mean():.1f} (旧: {old_scores.mean():.1f})")
print(f"  缩放因子: {scale_factor:.1f}")

# 测试不同阈值
for th in [20, 25, 30, 35, 40]:
    mask = new_scores.abs() >= th
    sub = directional[mask]
    if len(sub) > 0:
        acc = (sub['correct'] == 'Y').mean()
        pnl = sub['pnl_pct'].sum()
        print(f"  新系统阈值{th:2d}: 信号{len(sub):4d} ({len(sub)/len(directional)*100:4.1f}%) | "
              f"准确率{acc*100:.1f}% | PnL{pnl:+.2f}%")

# 新权重 + ADX过滤
for adx_th in [0, 25, 30]:
    for score_th in [25, 30, 35]:
        mask = (new_scores.abs() >= score_th)
        if adx_th > 0:
            mask &= (directional['adx'] >= adx_th)
        sub = directional[mask]
        if len(sub) >= 50:
            acc = (sub['correct'] == 'Y').mean()
            pnl = sub['pnl_pct'].sum()
            print(f"  新权重+ADX>={adx_th}+阈值{score_th:2d}: 信号{len(sub):4d} "
                  f"准确率{acc*100:.1f}% PnL{pnl:+.2f}%")

# ============================================================
# 7. 总结
# ============================================================
print("\n" + "=" * 60)
print("总结")
print("=" * 60)
print(f"""
从数据中得出的关键结论:

1. 原始系统 (阈值20, 无ADX过滤): 2505信号, 55.1%, +16.35%

2. 仅提高阈值到30: 减少至约{len(directional[directional['total_score'].abs()>=30])}信号
   准确率提升至约{directional[directional['total_score'].abs()>=30]['correct'].eq('Y').mean()*100:.1f}%

3. 仅提高阈值到37: 减少至约{len(directional[directional['total_score'].abs()>=37])}信号
   准确率提升至约{directional[directional['total_score'].abs()>=37]['correct'].eq('Y').mean()*100:.1f}%

4. 暴力搜索最佳: 阈值={best_combo[0]}, ADX>={best_combo[1]}
   准确率{best_combo[3]*100:.1f}%, {best_combo[2]}信号

5. 逻辑回归权重排序 (按影响力):
""")
for name, coef in sorted(zip(feature_cols, weights), key=lambda x: -abs(x[1])):
    print(f"   {name:12s}: {coef:+.4f}")
