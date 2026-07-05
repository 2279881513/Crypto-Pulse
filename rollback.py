"""回滚到 64.8% 的 1m+5m 双时间框架系统"""
import re

with open('cryptopulse/api/app.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 回滚升级脚本引入的所有15m相关代码
# 1. 移除15m数据加载部分
c15_start = c.find('# === 加载 15m 数据 ===')
c15_end = c.find('\n        # ========== 15m 大趋势确认 ==========')
if c15_start >= 0 and c15_end >= 0:
    # 找到15m数据加载的完整代码块
    end_of_block = c.find('\n        idx_5m_map = np.array(idx_5m_map)', c15_end)
    if end_of_block > 0:
        # 找到15m数据加载的后面部分
        c = c[:c15_start] + c[end_of_block:]

# 2. 回滚权重
c = c.replace('"tf15_trend":0.15,"tf15_adx":0.06,"tf15_macd":0.04}', '"tf5_trend":0.18,"tf5_adx":0.08,"tf5_rsi":0.06,"tf5_macd":0.04}')

# 3. 移除15m特征评分
c = c.replace('''            # ========== 15m 大趋势确认 ==========
            idx15=idx_15m_map[i] if idx_15m_map is not None else -1
            has15=idx15>=0 and all_ema_f15 is not None and not np.isnan(all_ema_f15[idx15])
            if has15:
                ef15,em15,es15=all_ema_f15[idx15],all_ema_m15[idx15],all_ema_s15[idx15]
                if ef15>em15>es15: signals["tf15_trend"]=1.0  # 15m多头
                elif ef15<em15<es15: signals["tf15_trend"]=-1.0  # 15m空头
                else: signals["tf15_trend"]=0.0
                adx15=all_adx15[idx15] if not np.isnan(all_adx15[idx15]) else 0
                if adx15>=30: signals["tf15_adx"]=0.8
                elif adx15>=20: signals["tf15_adx"]=0.3
                else: signals["tf15_adx"]=-0.3
                mh15=all_macd_h15[idx15] if not np.isnan(all_macd_h15[idx15]) else 0
                if mh15>0: signals["tf15_macd"]=0.5
                elif mh15<0: signals["tf15_macd"]=-0.5
                else: signals["tf15_macd"]=0.0
            else:
                signals["tf15_trend"]=0.0;signals["tf15_adx"]=0.0;signals["tf15_macd"]=0.0''', '')

# 4. 恢复方向判定阈值
c = c.replace('''            if total_score>35: direction=Direction.BULLISH
            elif total_score<-28: direction=Direction.BEARISH''',
'''            if total_score>30: direction=Direction.BULLISH
            elif total_score<-30: direction=Direction.BEARISH''')

# 5. 移除多头额外信心要求
c = c.replace('''            # 多头额外信心要求
            if direction==Direction.BULLISH and conf<55: direction=Direction.NEUTRAL''', '')

# 6. 恢复15m趋势过滤为5m过滤
c = c.replace('''            # 5m+15m无趋势时过滤''',
'''            # 5m无趋势时过滤''')
c = c.replace('''            # 15m趋势与方向不一致时过滤(需15m趋势支持)
            if direction!=Direction.NEUTRAL and has15:
                tf15_sig=signals.get("tf15_trend",0)
                if direction==Direction.BULLISH and tf15_sig<0.5 and abs(total_score)<40:
                    direction=Direction.NEUTRAL
                if direction==Direction.BEARISH and tf15_sig>-0.5 and abs(total_score)<40:
                    direction=Direction.NEUTRAL''', '')

with open('cryptopulse/api/app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("✅ 已回滚到 1m+5m 双时间框架系统 (64.8%版本)")
print("重启web服务后跑回测即可验证")
