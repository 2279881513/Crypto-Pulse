"""
分析信号数据，寻找提高准确率的方法
"""
import pandas as pd
import numpy as np

df = pd.read_csv('.reasonix/attachments/clipboard-20260706-015254.330819-000002.csv')

print(f'=== 总行数: {len(df)}')
print()

# 只看有方向的信号（非neutral）
directional = df[df['direction'] != 'neutral'].copy()
print(f'=== 有方向信号统计 ===')
print(f'总数: {len(directional)}')
print(f'bullish: {len(directional[directional["direction"]=="bullish"])}')
print(f'bearish: {len(directional[directional["direction"]=="bearish"])}')
print()

correct = directional[directional['correct']=='Y']
wrong = directional[directional['correct']=='N']
print(f'正确: {len(correct)}, 错误: {len(wrong)}, 准确率: {round(len(correct)/len(directional)*100, 1)}%')
print()

# 按方向
for d in ['bullish', 'bearish']:
    subset = directional[directional['direction']==d]
    c = len(subset[subset['correct']=='Y'])
    w = len(subset[subset['correct']=='N'])
    print(f'{d}: 总{c+w} 正确{c} 错误{w} 准确率{round(c/(c+w)*100,1)}%')

print()

# === 1. total_score 阈值优化 ===
print('=== total_score 绝对值阈值分析 ===')
for bucket in [(20,25),(25,30),(30,35),(35,40),(40,50),(50,60),(60,100)]:
    lo,hi = bucket
    sub = directional[(directional['total_score'].abs()>=lo) & (directional['total_score'].abs()<hi)]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        print(f'|score|∈[{lo},{hi}): 总{len(sub)} 正确{c} 错误{len(sub)-c} 准确率{round(c/len(sub)*100,1)}% 信号占比{round(len(sub)/len(directional)*100,1)}%')

print()

# 累计分析：如果提高threshold
print('=== 累计准确率 (|score| >= threshold) ===')
for th in [20, 25, 30, 35, 40, 45, 50]:
    sub = directional[directional['total_score'].abs() >= th]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        print(f'|score|>={th}: 信号{len(sub)}({round(len(sub)/len(directional)*100,1)}%) 正确{c} 准确率{round(c/len(sub)*100,1)}%')

print()

# === 2. confidence 分析 ===
print('=== confidence 累积准确率 ===')
for th in [30, 35, 40, 45, 50, 55, 60]:
    sub = directional[directional['confidence'] >= th]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        print(f'conf>={th}: 信号{len(sub)}({round(len(sub)/len(directional)*100,1)}%) 准确率{round(c/len(sub)*100,1)}%')

print()

# === 3. 单个特征区分能力 ===
print('=== 各特征对正确/错误的分组均值 ===')
features = ['ema','momentum','macd','rsi_score','bb','vol_score','obv_score','micro','adx']
for f in features:
    if f in directional.columns:
        corr_mean = directional.loc[directional['correct']=='Y', f].mean()
        wrong_mean = directional.loc[directional['correct']=='N', f].mean()
        # 也用中位数
        corr_med = directional.loc[directional['correct']=='Y', f].median()
        wrong_med = directional.loc[directional['correct']=='N', f].median()
        print(f'{f:12s}: 正确均值={corr_mean:.3f} 错误均值={wrong_mean:.3f} 差异={corr_mean-wrong_mean:.3f} | 中位数: 正确={corr_med:.3f} 错误={wrong_med:.3f}')

print()

# === 4. ADX趋势强度过滤 ===
print('=== ADX过滤 ===')
for adx_th in [20, 25, 30, 35, 40]:
    sub = directional[directional['adx'] >= adx_th]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        w = len(sub[sub['correct']=='N'])
        print(f'ADX>={adx_th}: 总{len(sub)}({round(len(sub)/len(directional)*100,1)}%) 正确{c} 准确率{round(c/len(sub)*100,1)}%')

print()

# === 5. 综合过滤策略 ===
print('=== 综合过滤策略 ===')
strategies = [
    ('|score|>=25', directional['total_score'].abs() >= 25),
    ('|score|>=30', directional['total_score'].abs() >= 30),
    ('conf>=40', directional['confidence'] >= 40),
    ('conf>=50', directional['confidence'] >= 50),
    ('ADX>=25', directional['adx'] >= 25),
    ('|score|>=25 & conf>=40', (directional['total_score'].abs()>=25) & (directional['confidence']>=40)),
    ('|score|>=25 & ADX>=25', (directional['total_score'].abs()>=25) & (directional['adx']>=25)),
    ('|score|>=30 & conf>=40', (directional['total_score'].abs()>=30) & (directional['confidence']>=40)),
    ('|score|>=30 & ADX>=25', (directional['total_score'].abs()>=30) & (directional['adx']>=25)),
    ('|score|>=30 & conf>=40 & ADX>=25', (directional['total_score'].abs()>=30) & (directional['confidence']>=40) & (directional['adx']>=25)),
]
for name, mask in strategies:
    sub = directional[mask]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        w = len(sub[sub['correct']=='N'])
        # 估算PnL（平均盈-平均亏）
        avg_win = sub.loc[sub['correct']=='Y', 'pnl_pct'].mean() if c>0 else 0
        avg_loss = sub.loc[sub['correct']=='N', 'pnl_pct'].mean() if w>0 else 0
        total_pnl = sub['pnl_pct'].sum()
        print(f'{name:35s}: 信号{len(sub):4d}({round(len(sub)/len(directional)*100,1):5.1f}%) | 正确率{round(c/len(sub)*100,1):5.1f}% | 总PnL{total_pnl:+.2f}% | 均盈{avg_win:+.3f}% 均亏{avg_loss:+.3f}%')

print()

# === 6. 基于规则的质量评分改进 ===
# 对每个特征的极端值赋予更高权重
print('=== 极端特征值分析 ===')
# 例如：当多个特征同时指向同一方向时准确率
directional['bullish_features'] = ((directional['ema']>0).astype(int) + 
    (directional['momentum']>0).astype(int) + 
    (directional['macd']>0).astype(int) + 
    (directional['rsi_score']>0).astype(int) + 
    (directional['bb']>0).astype(int) + 
    (directional['vol_score']>0).astype(int) + 
    (directional['obv_score']>0).astype(int))

directional['bearish_features'] = ((directional['ema']<0).astype(int) + 
    (directional['momentum']<0).astype(int) + 
    (directional['macd']<0).astype(int) + 
    (directional['rsi_score']<0).astype(int) + 
    (directional['bb']<0).astype(int) + 
    (directional['vol_score']<0).astype(int) + 
    (directional['obv_score']<0).astype(int))

print('当N个特征一致看多时的准确率:')
for n in range(4, 9):
    sub = directional[directional['bullish_features'] >= n]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        print(f'  {n}个特征看多: 信号{len(sub)} 准确率{round(c/len(sub)*100,1)}%')

print('当N个特征一致看空时的准确率:')
for n in range(4, 9):
    sub = directional[directional['bearish_features'] >= n]
    if len(sub)>0:
        c = len(sub[sub['correct']=='Y'])
        print(f'  {n}个特征看空: 信号{len(sub)} 准确率{round(c/len(sub)*100,1)}%')

# 一致性程度
directional['consensus'] = directional['bullish_features'] - directional['bearish_features']
print()
print('=== 一致性强弱与准确率 ===')
for level in range(-7, 8):
    sub = directional[directional['consensus'] == level]
    if len(sub) > 0:
        c = len(sub[sub['correct']=='Y'])
        print(f'consensus={level:+d}: 信号{len(sub):4d} 准确率{round(c/len(sub)*100,1):5.1f}%')

print()
print('=== 各特征极端值(±0.5以上)的单独准确率 ===')
for f in ['ema','momentum','macd','rsi_score','bb','vol_score','obv_score','micro']:
    # 正向极端
    pos = directional[directional[f] >= 0.5]
    if len(pos)>0:
        c_pos = len(pos[pos['correct']=='Y'])
        print(f'{f:12s} >+0.5: 信号{len(pos):4d} 准确率{round(c_pos/len(pos)*100,1):5.1f}%', end='')
    # 负向极端
    neg = directional[directional[f] <= -0.5]
    if len(neg)>0:
        c_neg = len(neg[neg['correct']=='Y'])
        print(f'  |  <{f} -0.5: 信号{len(neg):4d} 准确率{round(c_neg/len(neg)*100,1):5.1f}%')
    else:
        print()
