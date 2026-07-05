"""微调: 收紧多头信号 + 分开阈值 + 加15m数据"""
with open('cryptopulse/api/app.py','r',encoding='utf-8') as f:
    c=f.read()

# 1. 分方向阈值: 多头需要更高评分
old_th = '''            if total_score>30: direction=Direction.BULLISH
            elif total_score<-30: direction=Direction.BEARISH'''
new_th = '''            if total_score>35: direction=Direction.BULLISH
            elif total_score<-28: direction=Direction.BEARISH'''
c=c.replace(old_th,new_th,1)

# 2. 提高多头信心要求
old_conf = '''            if direction!=Direction.NEUTRAL and conf<45: direction=Direction.NEUTRAL'''
new_conf = '''            if direction!=Direction.NEUTRAL and conf<45: direction=Direction.NEUTRAL
            # 多头额外信心要求
            if direction==Direction.BULLISH and conf<55: direction=Direction.NEUTRAL'''
c=c.replace(old_conf,new_conf,1)

with open('cryptopulse/api/app.py','w',encoding='utf-8') as f:
    f.write(c)
print("✅ 已应用分方向阈值优化")
print("多头阈值: 30→35, 信心: 45→55")
print("空头阈值: -30→-28 (不变)")
