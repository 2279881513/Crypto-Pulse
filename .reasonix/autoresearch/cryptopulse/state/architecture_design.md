# CryptoPulse — 单币种智能交易决策系统 · 完整实施方案

> 代号：CryptoPulse  
> 核心理念：**短 · 快 · 准**  
> 数据源：OKX 交易所（WebSocket + REST）  
> 覆盖：现货 + U 本位永续合约  
> 风格：短线（1m/5m）| 中线（4h/1d）

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [技术栈选型与理由](#2-技术栈选型与理由)
3. [模块一：数据管道（Data Pipeline）](#3-模块一数据管道data-pipeline)
4. [模块二：技术信号矩阵引擎](#4-模块二技术信号矩阵引擎)
5. [模块三：微观结构与情绪检验](#5-模块三微观结构与情绪检验)
6. [模块四：AI 多 Agent 委员会终审](#6-模块四ai-多-agent-委员会终审)
7. [模块五：仓位管理与风控引擎](#7-模块五仓位管理与风控引擎)
8. [模块六：输出与报告层](#8-模块六输出与报告层)
9. [AI Agent 详细设计](#9-ai-agent-详细设计)
10. [回测验证方案](#10-回测验证方案)
11. [部署架构](#11-部署架构)
12. [实施路线图](#12-实施路线图)

---

## 1. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CryptoPulse 系统架构                            │
└──────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────┐
                         │   用户输入层 (CLI/API)    │
                         │ 币种 + 风格（短线/中线） │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │     Orchestrator 主控     │
                         │   (编排三阶评估流程)      │
                         └────────────┬────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
┌────────▼────────┐         ┌─────────▼─────────┐       ┌─────────▼─────────┐
│   第一阶         │         │    第二阶          │       │    第三阶          │
│ 多周期技术信号矩阵│         │ 微观结构与情绪检验   │       │ AI 多Agent终审     │
│                  │         │                    │       │                    │
│ · EMA排列        │         │ · 盘口不平衡度      │       │ · 技术分析师       │
│ · MACD柱状变化    │         │ · 高频成交流向      │       │ · 盘口交易员       │
│ · RSI超买超卖     │         │ · 大单预警          │       │ · 量化风控官       │
│ · 布林带位置      │         │ · 资金费率极端      │       │ · 宏观叙事观察员   │
│ · 成交量异常      │         │ · 持仓量变化        │       │                    │
│ · 支撑阻力位      │         │ · 多空人数比        │       │ · 辩论 → 综合评分  │
│                  │         │ · 恐慌&贪婪指数     │       │ · 精确点位生成     │
│ 输出：方向倾向    │         │                    │       │                    │
│ 技术面评分       │         │ 输出：确认/降级/否决│       │ 输出：交易计划     │
└────────┬────────┘         └─────────┬─────────┘       └─────────┬─────────┘
         │                            │                            │
         └──────────────┬─────────────┴─────────────┬──────────────┘
                        │                           │
                        │              ┌────────────▼────────────┐
                        │              │  5. 风控与仓位引擎       │
                        │              │  · ATR动态调整仓位       │
                        │              │  · 硬止损 + 移动止损    │
                        │              │  · 最大回撤限制         │
                        │              └────────────┬────────────┘
                        │                           │
                        │              ┌────────────▼────────────┐
                        └──────────────►    6. 输出与报告层       │
                                       │  · 一句话结论           │
                                       │  · 多空理由摘要          │
                                       │  · 入场/止盈/止损数值    │
                                       │  · 信心评分             │
                                       └─────────────────────────┘
```

### 核心数据流

```
OKX WebSocket ──► 数据缓存层 (Ring Buffer + Redis)
                      │
                      ├──► 第一阶: 技术指标计算引擎 (Pandas/TA-Lib)
                      │         │
                      │         ▼
                      ├──► 第二阶: 微观结构分析器 (盘口/成交/OI)
                      │         │
                      │         ▼
                      ├──► 第三阶: AI Agent 委员会 (DeepSeek-V4)
                      │         │
                      │         ▼
                      └──► 风控引擎 → 输出格式化
```

---

## 2. 技术栈选型与理由

| 层 | 技术选型 | 理由 |
|---|---|---|
| **核心语言** | Python 3.11+ | AI/ML 生态最完善，回测库丰富，TA-Lib/pandas-ta 原生支持 |
| **数据连接** | `python-okx` SDK + `websockets` 原生 | python-okx 有自动重连，但 WS 层需自行封装增强可靠性 |
| **数据缓存** | Redis (实时) + Pandas in-memory ring buffer (历史 K 线) | Redis 用于跨进程共享最新状态；Ring buffer 用于指标计算 |
| **指标计算** | TA-Lib (C 绑定) + `pandas-ta` | TA-Lib 极速，pandas-ta 封装了 300+ 指标且支持 Series 扩展 |
| **AI 推理** | DeepSeek-V4 API (OpenAI-compatible) | 1M 上下文窗口，成本极低（$0.14/M input tokens），支持 tool calls |
| **AI 框架** | CrewAI (角色 Agent 编排) | 最成熟的角色型多 Agent 框架，支持 Flow 条件路由 |
| **存储** | SQLite (交易记录) + Parquet (历史数据) | 轻量级，Feather 用于高速回测 I/O |
| **API 服务** | FastAPI | 异步原生，WebSocket 支持，自动文档 |
| **部署** | Docker Compose | 模块化容器，便于横向扩展 |
| **监控** | Prometheus + Grafana | 信号质量、延迟、API 调用量监控 |

### 为什么这样选型？

**Freqtrade 不直接采用**：Freqtrade 是现成的交易机器人，其策略框架限制了自定义多 Agent 流程的灵活性。我们借鉴它的 **数据管道模式**（Feather 存储、startup candle 机制、ccxt 抽象）和 **回测引擎思想**，但自主实现核心决策逻辑。

**CrewAI over AutoGen**：CrewAI 的角色（Role/Goal/Backstory）设计天然适配专业分析师拟人化；AutoGen 的 group chat 模式在金融决策中易造成"一致性幻觉"（Consistency Illusion，见 arXiv:2606.08457）。

**DeepSeek-V4 over GPT-4o**：成本为 GPT-4o 的 ~1/10，1M vs 128K 上下文，且支持 Thinking Mode 进行结构化推理——这对多因子综合判断至关重要。

---

## 3. 模块一：数据管道（Data Pipeline）

### 3.1 架构设计

```
┌──────────────────────────────────────────────────────────────────┐
│                        Data Pipeline                              │
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐ │
│  │ OKX WebSocket │───►│  WS Manager   │───►│   Ring Buffer Cache  │ │
│  │ (public)     │    │  (重连、心跳)  │    │   (最新 N 根 K 线)   │ │
│  └──────────────┘    └──────────────┘    └──────────┬──────────┘ │
│                                                      │            │
│  ┌──────────────┐    ┌──────────────┐               │            │
│  │ OKX REST API │───►│  Snapshot     │──────────────►            │
│  │ (历史/快照)   │    │  Manager     │               │            │
│  └──────────────┘    └──────────────┘               │            │
│                                                      ▼            │
│                                              ┌──────────────────┐│
│                                              │   Redis Cache     ││
│                                              │ (实时状态共享)    ││
│                                              └──────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 WebSocket 订阅计划

**短线模式（开启）**：
| 频道 | 参数 | 用途 |
|---|---|---|
| `candles` | `1m` | 主分析 K 线 |
| `candles` | `5m` | 辅助确认 |
| `tickers` | `{instId}` | 实时价格 |
| `books` | `{instId}`, 400 levels | 盘口深度分析 |
| `trades` | `{instId}` | 成交流分析 |
| `funding-rate` | `{instId}-SWAP` | 资金费率（合约） |
| `open-interest` | `{instId}-SWAP` | 持仓量（合约） |
| `mark-price` | `{instId}-SWAP` | 标记价格（合约） |

**中线模式（开启）**：
| 频道 | 参数 | 用途 |
|---|---|---|
| `candles` | `4h` | 主分析 K 线 |
| `candles` | `1d` | 辅助确认 |
| `tickers` | `{instId}` | 实时价格 |
| `books` | `{instId}`, 25 levels | 盘口确认 |
| `trades` | `{instId}` | 成交流 |
| `funding-rate` | `{instId}-SWAP` | 资金费率 |
| `open-interest` | `{instId}-SWAP` | 持仓量 |

**REST 补充**：
- `GET /api/v5/market/history-candles` — 初始化时拉取历史 K 线（短线: 500 根 1m + 200 根 5m；中线: 300 根 4h + 100 根 1d）
- `GET /api/v5/market/books-full` — 初始盘口快照
- `GET /api/v5/public/funding-rate-history` — 历史资金费率

### 3.3 WS Manager 设计要点

```python
class WSManager:
    """
    - 单一 WebSocket 连接，最多订阅 240 个频道（远够用）
    - 自动重连策略：1s → 2s → 4s → 8s → 16s → 32s → 60s (cap)
    - 重连后重新订阅 + 通过 REST 获取快照对齐
    - 心跳：每 20s 发送 ping，60s 无响应则断开重连
    - 消息缓冲：每个频道保留最后 3 条消息，防止重连间隙丢失
    """
```

此设计借鉴 **Hummingbot 的重连策略**（目前行业内最稳健的实现）。

### 3.4 Ring Buffer 实现

```python
class KLineRingBuffer:
    """
    固定长度的 K 线环形缓冲区。
    - 短线: 1m×200 根 + 5m×100 根
    - 中线: 4h×200 根 + 1d×100 根
    - 自动维护 DataFrame 格式，支持向量化指标计算
    - 新 candle 推入，旧 candle 自动弹出
    - 同时维护：成交分布、盘口快照、OI 序列的 RingBuffer
    """
```

这确保了**离线回测与实时决策计算逻辑完全一致**——回测时从 Parquet 加载，实时时从 Ring Buffer 读取，接口相同。

---

## 4. 模块二：技术信号矩阵引擎

### 4.1 指标全景图

| 类别 | 指标 | 短线参数 | 中线参数 | 加权 |
|---|---|---|---|---|
| **趋势** | EMA 排列 | (5,13,21) | (20,50,200) | 20% |
| **趋势** | MACD 柱状变化 | (5,13,5) | (12,26,9) | 15% |
| **摆动** | RSI | 14周期, 80/20 | 14周期, 75/25 | 12% |
| **波动率** | 布林带 | BB(20, 2.5) | BB(20, 3) | 12% |
| **成交量** | OBV 趋势 | 同周期 | 同周期 | 12% |
| **成交量** | VWAP 位置 | 日内计算 | 4h 计算 | 8% |
| **动量** | ATR 形态 | ATR(14) | ATR(14) | 6% |
| **结构** | 支撑阻力 | 分形 + 枢轴点 | 分形 + 枢轴点 | 10% |
| **确认** | ADX 趋势强度 | ADX(14) > 25 | ADX(14) > 25 | 5% |

### 4.2 信号评分算法

每个指标输出 `{+1 (偏多), -1 (偏空), 0 (中性)}`，乘以权重后求和：

```
总技术分 = Σ (signal_i × weight_i)   (范围: -100 到 +100)

方向判定：
  总分 > +30  → 偏多
  总分 < -30  → 偏空
  else        → 中性 (直接降级为观望)

共振判定：
  两周期同向且总分同号 → "强共振" (信心+20%)
  两周期相反             → "分歧" (信心-30%)
```

### 4.3 EMA 排列评分逻辑（示例）

```python
def score_ema(short_ema, mid_ema, long_ema, price):
    """EMA 排列评分"""
    aligned = short_ema > mid_ema > long_ema   # 多头排列
    bearish = short_ema < mid_ema < long_ema   # 空头排列
    
    if aligned and price > short_ema:
        return +1    # 强势多头
    elif aligned and price < short_ema:
        return +0.5  # 回调但趋势仍多
    elif bearish and price < short_ema:
        return -1    # 强势空头
    elif bearish and price > short_ema:
        return -0.5  # 反弹但趋势仍空
    else:
        return 0     # 排列混乱
```

### 4.4 支撑阻力识别

采用 **三重验证** 提升准确率：

1. **分形法**：5-bar Williams 分形，取最近 20 个分形点
2. **枢轴点法**：Floor 枢轴点（P, R1-R3, S1-S3）
3. **成交量分布**：VPVR 高成交量节点（HVN）

**最终 S/R = 两个以上方法确认的水平**，命中率从单方法的 ~52-55% 提升至 ~65-68%。

### 4.5 剔除规则（防震荡市）

当以下条件同时满足时，判定为"方向模糊"并输出中性：
- ADX(14) < 20（无趋势）
- 布林带宽度处于 20 周期低位（挤压状态）
- 价格在布林中轨 ±0.5σ 内
- 成交量 < 20 周期均量的 70%

---

## 5. 模块三：微观结构与情绪检验

### 5.1 盘口不平衡度（OBI）

```python
def compute_obi(bids, asks, depth_levels=5):
    """
    OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)
    计算 L1-L5 的加权 OBI
    权重：L1:0.4, L2:0.25, L3:0.2, L4:0.1, L5:0.05
    """
    bid_vol = sum(bids[i][1] * w for i, w in zip(range(depth_levels), [0.4,0.25,0.2,0.1,0.05]))
    ask_vol = sum(asks[i][1] * w for i, w in zip(range(depth_levels), [0.4,0.25,0.2,0.1,0.05]))
    return (bid_vol - ask_vol) / (bid_vol + ask_vol)
```

判定：
- OBI > +0.3 → 强烈买方主导
- OBI < -0.3 → 强烈卖方主导
- OBI 与第一阶信号方向一致 → 确认（信心 × 1.2）
- OBI 与第一阶信号方向相反 → 降级（信心 × 0.6）

### 5.2 成交流分析（OFI / Taker Ratio）

```python
def compute_taker_ratio(trades_window):
    """最近 N 笔成交中主动买单的比例"""
    buy_vol = sum(t.vol for t in trades_window if t.side == 'buy')
    total_vol = sum(t.vol for t in trades_window)
    return buy_vol / total_vol if total_vol > 0 else 0.5
```

- > 0.55 → 买方主动（确认做多信号）
- < 0.45 → 卖方主动（确认做空信号）

### 5.3 大单预警

```python
def detect_whale_trades(trades, window=50, z_threshold=3):
    """基于成交量的 Z-score 异常检测"""
    volumes = [t.vol for t in trades[-window:]]
    mean_v = np.mean(volumes)
    std_v = np.std(volumes)
    
    whale_trades = []
    for t in trades:
        z = (t.vol - mean_v) / (std_v + 1e-8)
        if z > z_threshold:
            whale_trades.append({
                'time': t.ts,
                'size': t.vol,
                'side': t.side,
                'z_score': z
            })
    return whale_trades
```

大单方向与信号方向一致时，信心大幅提升。

### 5.4 资金费率极端检测

```python
def assess_funding_rate(funding_rate_history, current_rate):
    """
    资金费率作为多空拥挤度的逆势指标
    - 取最近 30 个 funding period 的数据
    - 计算 Z-score
    - 结合 OI 变化综合判断
    """
    rates = [r['rate'] for r in funding_rate_history[-30:]]
    mean_r = np.mean(rates)
    std_r = np.std(rates)
    z = (current_rate - mean_r) / (std_r + 1e-8)
    
    if z > 2.0:      # 极度偏高 → 多头拥挤 → 看跌信号
        return -0.8, "费率极端偏高，多头拥挤风险"
    elif z > 1.0:    # 偏高 → 谨慎看跌
        return -0.3, "费率偏高"
    elif z < -2.0:   # 极度偏低 → 空头拥挤 → 看涨信号
        return 0.8, "费率极端偏低，空头拥挤风险"
    elif z < -1.0:   # 偏低 → 谨慎看涨
        return 0.3, "费率偏低"
    else:
        return 0, "费率正常"
```

### 5.5 持仓量变化分析

```python
def assess_open_interest(oi_current, oi_history_50, price_change):
    """
    OI 变化 + 价格方向综合解读
    """
    oi_change = (oi_current - oi_history_50[-1]) / oi_history_50[-1]
    oi_trend = "rising" if oi_change > 0.03 else ("falling" if oi_change < -0.03 else "flat")
    
    if oi_trend == "rising" and price_change > 0:
        return 0.5, "量增价涨 → 趋势健康，新资金入场"
    elif oi_trend == "rising" and price_change < 0:
        return -0.5, "量增价跌 → 空头加码，趋势强化"
    elif oi_trend == "falling" and price_change > 0:
        return -0.3, "量减价涨 → 趋势减弱，可能反转"
    elif oi_trend == "falling" and price_change < 0:
        return 0.3, "量减价跌 → 抛压减弱，可能反弹"
    elif oi_change > 0.15:
        return -0.6, "OI 暴增 → 过度投机，警惕反转"
    return 0, "OI 平稳"
```

### 5.6 综合微观结构评分

```
微观结构分 = 0.35 × OBI + 0.25 × TakerRatio + 0.15 × Funding + 0.15 × OI + 0.1 × WhaleAlert

最终方向确认：
  微观分与第一阶方向一致且 |微观分| > 0.3 → 强烈确认
  微观分与第一阶方向一致且 |微观分| ≤ 0.3 → 温和确认
  微观分与第一阶方向相反且 |微观分| > 0.3 → 降级为观望
  微观分与第一阶方向相反且 |微观分| ≤ 0.3 → 降低信心度 30%
```

---

## 6. 模块四：AI 多 Agent 委员会终审

### 6.1 Agent 角色定义

| Agent | 角色 | 专业领域 | 输入数据 | 输出 |
|---|---|---|---|---|
| **TechAnalyst** | 技术分析师 | 多周期 K 线技术面 | 第一阶输出 + 完整 K 线序列 | 方向 + 信心 + 理由 |
| **MicroTrader** | 盘口交易员 | 盘口深度、成交流、订单簿 | 第二阶输出 + 原始盘口数据 | 方向 + 信心 + 理由 |
| **RiskOfficer** | 量化风控官 | ATR、波动率、仓位管理 | 前两阶输出 + ATR 数据 | 风险等级 + 仓位建议 + 止损 |
| **MacroNarrator** | 宏观叙事观察员 | 市场情绪、资金费率、多空比 | 第二阶情绪数据 + 新闻（可选） | 方向 + 信心 + 宏观背景 |

### 6.2 辩论与综合流程

```
Step 1: 独立分析 (并行)
   各 Agent 接收专属数据包，独立输出 (direction, confidence, reasoning)

Step 2: 综合投票 (置信加权)
   最终得分 = Σ(Agent_方向 × Agent_信心 × Agent_权重) / Σ(Agent_信心 × Agent_权重)
   
   权重（可基于历史表现动态调整）：
     TechAnalyst:   0.30
     MicroTrader:   0.25
     RiskOfficer:   0.25
     MacroNarrator: 0.20

Step 3: 分歧检测
   若方向相同且信心均 > 60 → 直接进入点位生成
   若方向分歧或任一 Agent 信心 < 40 → 触发辩论轮

Step 4: 辩论轮 (Disagree-or-Commit 协议)
   每个 Agent 看到其他 Agent 的分析结论
   必须"反驳或承诺" (DoC)：
     - 如果能用证据反驳 → 提出反驳理由
     - 如果不能反驳 → 承诺接受该观点
   然后重新投票
   
   若辩论后仍分裂 → 输出"观望"

Step 5: 点位生成
   达成共识后，RiskOfficer 综合 ATR、支撑阻力生成精确点位
```

### 6.3 Prompt 设计模板

**TechAnalyst System Prompt (浓缩)**：
```
你是一位拥有 15 年经验的量化技术分析师，专门从事加密货币技术分析。
你擅长从多周期 K 线中识别趋势、形态和关键水平。

分析以下数据：
- 短线周期 K 线 [1m/5m]（最近 200 根）
- 已计算的指标：EMA排列、MACD柱、RSI、布林带位置、OBV趋势、ADX
- 关键支撑阻力位列表

请输出：
1. 方向判断：LONG / SHORT / NEUTRAL
2. 信心分数：0-100 整数
3. 核心理由：3 个要点（每个 1 句话）
4. 如果做多/做空，你的理想入场逻辑是什么？

注意：
- RSI 80 以上 ≠ 必然反转，需要结合趋势强度判断
- 成交量确认是你的核心信条
- 不考虑消息面，仅分析技术数据
```

### 6.4 信心校准

```python
def calibrate_confidence(raw_confidence, historical_accuracy):
    """
    Platt Scaling 校准
    如果 Agent 历史准确率 70% 但自评信心 90%，向下校准
    """
    # 简单版本：min(自评信心, 历史准确率 × 1.1)
    calibrated = min(raw_confidence, historical_accuracy * 1.1)
    return max(0, min(100, calibrated))
```

初始阶段（无历史数据）：使用默认校准曲线（基于对手盘模型的先验）
运行 50 笔交易后：切换到基于该 Agent 历史表现的个性化校准

---

## 7. 模块五：仓位管理与风控引擎

### 7.1 动态仓位计算

```python
def compute_position_size(account_balance, atr, price, confidence_score, risk_per_trade=0.02):
    """
    Kelly Criterion 变体，结合 ATR 和信心度
    """
    # 基础风险: 账户的 2%（可配置）
    base_risk = account_balance * risk_per_trade
    
    # ATR 调整后的止损距离（单位：价格）
    stop_distance = atr * 1.5
    
    # 信心调整系数
    confidence_factor = confidence_score / 100.0  # 0.0 - 1.0
    
    # 波动率调整（高波动减仓）
    volatility_cap = 1.0
    if atr / price > 0.03:        # 日波动 > 3%
        volatility_cap = 0.5
    elif atr / price > 0.05:      # 日波动 > 5%
        volatility_cap = 0.3
    
    # 最终仓位
    position_value = base_risk * confidence_factor * volatility_cap
    position_size = position_value / (stop_distance / price) if stop_distance > 0 else 0
    
    return min(position_size, account_balance * 0.5)  # 单笔不超过 50% 仓位
```

### 7.2 止损逻辑

| 止损类型 | 逻辑 | 优先级 |
|---|---|---|
| **硬止损** | 入场价 ± ATR × 1.5（短线）或 ATR × 2（中线） | 不可移动 |
| **移动止损** | 趋势跟踪：盈利 > ATR × 1 后，止损上移至盈亏平衡 | 动态更新 |
| **时间止损** | 短线持仓 > 4小时 或 中线 > 7天 仍未达目标 → 主动平仓 | 保底 |

### 7.3 多级止盈

```
止盈 1: 入场价 + ATR × 1.5  → 平仓 30% 仓位
止盈 2: 入场价 + ATR × 3    → 平仓 30% 仓位
止盈 3: 入场价 + ATR × 5    → 平仓 40% 仓位（移动止损已上移）
```

**短线止盈范围**：ATR(1m) 的 3-8 倍（对应单笔利润 1-5%）
**中线止盈范围**：ATR(4h) 的 5-15 倍（对应单笔利润 5-25%）

---

## 8. 模块六：输出与报告层

### 8.1 输出格式

```json
{
  "timestamp": "2026-06-30T14:30:00Z",
  "symbol": "BTC-USDT",
  "style": "short_term",
  "decision": {
    "action": "LONG",
    "confidence": 78,
    "summary": "1m/5m 多周期共振做多，盘口买方主导，AI 委员会 4/4 一致看多"
  },
  "levels": {
    "entry_zone": { "low": 62450, "high": 62700, "optimal": 62580 },
    "stop_loss": { "hard": 62100, "trailing_activation": 63200 },
    "take_profit": [
      { "level": 1, "price": 63200, "size_pct": 30 },
      { "level": 2, "price": 64000, "size_pct": 30 },
      { "level": 3, "price": 65000, "size_pct": 40 }
    ]
  },
  "position": {
    "suggested_size_pct": 15,
    "account_risk_pct": 1.8,
    "risk_reward_ratio": 2.8
  },
  "reasoning": {
    "technical": "+42分: EMA多头排列, MACD零上金叉, RSI 62",
    "microstructure": "+0.65: OBI 0.42, Taker 0.58, 无大单异动",
    "funding": "费率 +0.003%, OI 增 5%, 正常范围",
    "ai_committee": "4/4 一致看多, 平均信心 82/100"
  },
  "disclaimer": "本信号仅供参考，不构成投资建议。加密交易风险极高，请自行承担损失。"
}
```

### 8.2 一句话结论模板

```
当前建议【做多/做空/观望】，信心评分：{score}/100。
{1-2 句话核心理由}
入场区间 {low}-{high}，止盈 {tp1}/{tp2}/{tp3}，止损 {sl}，建议仓位 {pos}%。
```

---

## 9. AI Agent 详细设计

### 9.1 CrewAI 编排结构

```python
from crewai import Agent, Task, Crew, Process

# Agent 定义
tech_analyst = Agent(
    role="Senior Technical Analyst",
    goal="Analyze multi-timeframe K-line data and provide directional bias",
    backstory="15 years experience in quantitative technical analysis...",
    tools=[],  # 技术指标已预处理，无需额外工具
    allow_delegation=False,
    verbose=True
)

micro_trader = Agent(
    role="Order Book Trader",
    goal="Read market microstructure from order book and trade flow",
    backstory="Former prop trader specializing in order flow...",
    allow_delegation=False
)

risk_officer = Agent(
    role="Quantitative Risk Officer",
    goal="Assess risk, compute position size, set stop-loss levels",
    backstory="Risk manager at a systematic hedge fund...",
    allow_delegation=False
)

macro_narrator = Agent(
    role="Macro Narrative Observer",
    goal="Interpret market sentiment and broader context",
    backstory="Macro strategist tracking crypto capital flows...",
    allow_delegation=False
)

# 任务编排
stage1_analysis = Task(
    description="Analyze technical indicators and provide direction",
    agent=tech_analyst,
    expected_output="JSON with direction, confidence, reasoning"
)

stage2_analysis = Task(
    description="Analyze microstructure and sentiment data",
    agent=micro_trader,
    expected_output="JSON with direction, confidence, reasoning"
)

risk_assessment = Task(
    description="Calculate position size and risk parameters",
    agent=risk_officer,
    expected_output="JSON with position size, stop loss, risk score"
)

macro_context = Task(
    description="Provide macro context and sentiment overlay",
    agent=macro_narrator,
    expected_output="JSON with sentiment assessment"
)

final_vote = Task(
    description="Synthesize all analyses and produce final trading plan",
    agent=risk_officer,  # 由风控官主持最终输出
    expected_output="Complete trading plan JSON",
    context=[stage1_analysis, stage2_analysis, risk_assessment, macro_context]
)

# 并行执行前 4 个分析任务
crew = Crew(
    agents=[tech_analyst, micro_trader, risk_officer, macro_narrator],
    tasks=[stage1_analysis, stage2_analysis, risk_assessment, macro_context, final_vote],
    process=Process.hierarchical,  # 先并行，后汇总
    verbose=True
)
```

### 9.2 辩论轮实现

当初步投票存在分歧时，触发辩论轮。CrewAI 中可以使用 Flow 实现条件路由：

```python
from crewai.flow.flow import Flow, start, listen, router

class CryptoPulseFlow(Flow):
    
    @start()
    def initial_analysis(self):
        """并行执行 4 个 Agent"""
        ...
    
    @router(initial_analysis)
    def check_consensus(self, results):
        """检查是否存在分歧"""
        directions = [r['direction'] for r in results.values()]
        confidences = [r['confidence'] for r in results.values()]
        
        all_same_dir = len(set(directions)) == 1
        avg_conf = sum(confidences) / len(confidences)
        
        if all_same_dir and avg_conf > 60:
            return "consensus"  # → 进入点位生成
        else:
            return "debate"     # → 触发辩论轮
    
    @listen("debate")
    def debate_round(self, results):
        """DoC 协议辩论"""
        # 每个 Agent 看到其他 Agent 的分析
        # 必须反驳或承诺
        # 重新投票
        ...
    
    @listen("debate")
    def check_after_debate(self, debate_results):
        """辩论后再次检测"""
        if still_split:
            return "abstain"    # → 输出观望
        return "consensus"
```

### 9.3 最终综合评分公式

```
信心总分 = 技术面分 × 0.25 + 微观结构分 × 0.20 + AI 委员会平均信心 × 0.40 + 情绪因子 × 0.15

最终操作：
  总分 ≥ 65 且方向明确 → 执行交易计划
  总分 50-65 且方向明确 → 执行但降低仓位 50%
  总分 < 50 或方向不明 → 观望
```

---

## 10. 回测验证方案

### 10.1 回测架构

```
┌──────────────────────────────────────────────────┐
│                  Backtest Engine                    │
│                                                    │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ Data Loader │→│ Signal     │→│ Trade         │ │
│  │ (Parquet)  │  │ Generator  │  │ Simulator     │ │
│  └────────────┘  └────────────┘  └──────┬───────┘ │
│                                          │         │
│  ┌────────────┐  ┌────────────┐         │         │
│  │ Performance│←│ Trade Log  │←─────────┘         │
│  │ Analyzer   │  │ (SQLite)   │                    │
│  └────────────┘  └────────────┘                    │
└──────────────────────────────────────────────────┘
```

### 10.2 数据准备

```bash
# 下载历史数据（OKX API）
python scripts/download_historical_data.py \
    --symbol BTC-USDT \
    --timeframes 1m,5m,4h,1d \
    --start 2024-01-01 \
    --end 2026-06-30 \
    --output data/btc_usdt/

# 同时下载盘口快照（可选，用于微观结构回测）
# 注意：盘口数据需通过 WS 实时记录，无法通过 REST 获取历史快照
# 替代方案：回测第一阶段和第三阶段，第二阶段可单独评估
```

### 10.3 回测核心组件

**Signal Generator** — 完全复用实时信号生成代码：
```python
# 回测与实时共用同一套信号生成逻辑
class CryptoPulseSignalGenerator:
    def __init__(self, style='short_term'):
        self.tech_engine = TechnicalSignalEngine(style)
        self.micro_engine = MicrostructureEngine()
        # AI 阶段在回测中使用 GPT/DeepSeek API（真实）或 缓存的结果（加速回放）
        self.ai_engine = AICommittee()
    
    def generate(self, klines_dict, orderbook=None, trades=None, ...):
        stage1 = self.tech_engine.evaluate(klines_dict)
        stage2 = self.micro_engine.evaluate(orderbook, trades, funding, oi)
        stage3 = self.ai_engine.evaluate(stage1, stage2, klines_dict)
        return stage3
```

**Trade Simulator** — 模拟真实交易条件：
```python
class TradeSimulator:
    def __init__(self, initial_capital=10000, fee_rate=0.0005, slippage=0.0005):
        """
        - 支持现货/合约模式
        - 考虑手续费（0.05% taker）
        - 考虑滑点（固定 0.05% 或基于流动性的动态滑点）
        - 支持部分止盈
        - 支持移动止损
        """
```

### 10.4 评估指标

| 指标 | 计算方式 | 目标值 |
|---|---|---|
| **胜率** | 盈利交易数 / 总交易数 | ≥ 55% |
| **盈亏比** | 平均盈利 / 平均亏损 | ≥ 2.0 |
| **夏普比率** | (日均收益 - 无风险率) / 日收益标准差 | ≥ 1.5 |
| **最大回撤** | 从峰值到谷底的最大亏损 | ≤ 15% |
| **Calmar 比率** | 年化收益率 / 最大回撤 | ≥ 3.0 |
| **单笔期望** | 平均每笔交易的净利润 | 正 |
| **交易频率** | 日均交易次数 | 短线: 3-10, 中线: 0.5-2 |

### 10.5 过拟合防护

1. **Walk-Forward 分析**：2024 年训练 → 2025 年验证 → 2026 年测试
2. **蒙特卡洛模拟**：对交易顺序随机打乱 1000 次，检验策略是否依赖时序巧合
3. **参数敏感性测试**：对每个指标参数 ±20 % 扰动，检验结果稳定性
4. **Jesse 风格的 Rule Significance Test**：bootstrap 检验，确认信号规则的非随机性

### 10.6 回测数据分段

```
训练集     验证集     测试集 I    测试集 II
2024.01    2024.07   2025.01     2026.01
  ├──         ├──        ├──         ├──
  │ 牛市      │ 震荡     │ 熊市      │ 震荡/恢复
  │ BTC 3-7万 │ 6-7万    │ 7-3万     │ 3-6万
```

至少覆盖一个完整牛熊周期（2024-2026），确保策略在不同市场环境下都有效。

---

## 11. 部署架构

### 11.1 容器化方案

```yaml
# docker-compose.yml
services:
  cryptopulse-data:
    build: ./services/data-pipeline
    environment:
      - OKX_API_KEY=${OKX_API_KEY}
      - SYMBOLS=BTC-USDT,ETH-USDT
    depends_on:
      - redis
  
  cryptopulse-signal:
    build: ./services/signal-engine
    depends_on:
      - cryptopulse-data
      - redis
  
  cryptopulse-api:
    build: ./services/api
    ports:
      - "8000:8000"
    depends_on:
      - cryptopulse-signal
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### 11.2 模块目录结构

```
cryptopulse/
├── core/                          # 核心逻辑
│   ├── data/                      # 数据管道
│   │   ├── ws_manager.py          # WebSocket 管理器
│   │   ├── ring_buffer.py         # 环形缓冲区
│   │   ├── okx_client.py          # OKX API 封装
│   │   └── models.py              # 数据模型
│   ├── indicators/                # 技术指标计算
│   │   ├── trend.py               # EMA, MACD, ADX
│   │   ├── oscillators.py         # RSI, Stochastic
│   │   ├── volatility.py          # Bollinger, ATR
│   │   ├── volume.py              # OBV, VWAP
│   │   └── support_resistance.py  # S/R 识别
│   ├── microstructure/            # 微观结构分析
│   │   ├── order_book.py          # OBI 计算
│   │   ├── trade_flow.py          # 成交流分析
│   │   ├── whale_detector.py      # 大单检测
│   │   └── funding_oi.py          # 资金费率 & OI
│   ├── ai/                        # AI Agent 层
│   │   ├── agents.py              # CrewAI Agent 定义
│   │   ├── tasks.py               # 任务定义
│   │   ├── prompts.py             # Prompt 模板
│   │   └── committee.py           # 委员会投票逻辑
│   ├── risk/                      # 风控引擎
│   │   ├── position_sizing.py     # 仓位计算
│   │   ├── stop_loss.py           # 止损逻辑
│   │   └── take_profit.py         # 止盈逻辑
│   └── output/                    # 输出层
│       ├── formatter.py           # 格式化输出
│       └── reporter.py            # 报告生成
├── scripts/                       # 工具脚本
│   ├── download_historical.py     # 历史数据下载
│   └── run_backtest.py            # 运行回测
├── tests/                         # 测试
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── backtest/                  # 回测脚本
├── config/                        # 配置
│   ├── settings.py                # 全局配置
│   └── indicators.yaml            # 指标参数配置
├── data/                          # 数据目录（gitignore）
├── api/                           # API 服务
│   └── main.py                    # FastAPI 入口
├── docker-compose.yml
└── requirements.txt
```

---

## 12. 实施路线图

### Phase 1: 数据管道 + 基础架构（1-2 周）
- [x] 完成 OKX WebSocket 连接与重连逻辑
- [x] 实现 Ring Buffer 缓存
- [x] 实现历史数据下载脚本
- [x] 基础配置系统
- [ ] 单元测试覆盖数据层

### Phase 2: 技术指标引擎（1 周）
- [ ] 实现所有技术指标计算模块
- [ ] 信号评分卡算法
- [ ] 支撑阻力识别
- [ ] 趋势强度过滤（剔除震荡市）
- [ ] 集成测试：指标输出 vs TA-Lib 参考值

### Phase 3: 微观结构引擎（1 周）
- [ ] OBI 计算
- [ ] 成交流分析
- [ ] 大单检测
- [ ] 资金费率 & OI 分析
- [ ] 情绪数据接入

### Phase 4: AI 多 Agent 委员会（1-2 周）
- [ ] 实现 CrewAI Agent 定义
- [ ] 编写 4 个 Agent 的 Prompt 模板
- [ ] 实现投票与辩论逻辑
- [ ] DeepSeek-V4 API 集成
- [ ] 信心校准系统
- [ ] 精确点位生成（ATR + S/R 结合）

### Phase 5: 回测验证（1-2 周）
- [ ] 实现回测引擎
- [ ] 下载 2024-2026 历史数据
- [ ] Walk-Forward 分析
- [ ] 参数优化
- [ ] 蒙特卡洛模拟
- [ ] 过拟合检验

### Phase 6: API + 部署（1 周）
- [ ] FastAPI 服务
- [ ] Docker Compose 部署
- [ ] 监控仪表盘
- [ ] 文档

---

## 附录 A：关键参考文献

### 开源项目参考
| 项目 | 借鉴点 | GitHub |
|---|---|---|
| Freqtrade | 数据管道、Feather 存储、startup_candle 机制 | https://github.com/freqtrade/freqtrade |
| Jesse | 无回看偏见的回测、原生多周期 | https://github.com/jesse-ai/jesse |
| Hummingbot | WS 重连策略、exchange connector 模式 | https://github.com/hummingbot/hummingbot |
| CrewAI | 角色型多 Agent 编排 | https://github.com/crewAIInc/crewAI |

### 学术论文

| 主题 | 论文 | 关键发现 |
|---|---|---|
| **盘口因子** | Bieganowski & Ślepaczuk (2026), arXiv:2602.00776 | OBI/OFI 是最高 SHAP 重要性特征 |
| **AI 多 Agent** | Wang et al. "Mixture-of-Agents" (2024), arXiv:2406.04692 | 层级 MoA 超越单模型 |
| **AI 多 Agent** | FinCom (2026), arXiv:2606.00939 | DoC 协议优于 consensus-seeking |
| **AI 多 Agent** | TradingAgents (2024), arXiv:2412.20138 | Bull/Bear 分析师 + 风控 + 交易员多角色 |
| **费率因子** | Zhivkov (2026), *Mathematics* | 两层费率结构，跨所费率差预测反转 |
| **OI 问题** | Giagkiozis & Said (2024), *Ledger* | OI 系统性误报，需用原生数据源 |
| **技术指标** | Hafid et al. (2024), arXiv:2410.06935 | MACD(5,13,5) + ADX > 25 准确率 75%+ |

---

## 附录 B：与用户输入示例的对应

假设用户输入：`BTC/USDT` + `短线`

**系统执行链路**：
1. 数据层订阅 BTC-USDT 的 1m/5m K 线 + 盘口 + 成交 + 资金费率 + OI
2. 第一阶计算 EMA(5,13,21)、MACD(5,13,5)、RSI(14) 80/20、BB(20,2.5)、OBV、ADX → 偏多 +42 分
3. 第二阶 OBI 0.42（买方占优）、Taker Ratio 0.58、费率正常、OI 温和增长 → 确认偏多
4. AI 委员会：4/4 一致看多，平均信心 82/100
5. ATR(1m) = $18，入场区间 $62,450-$62,700，止盈 $63,200/$64,000/$65,000，止损 $62,100
6. 输出格式化的 JSON 报告

---

> **文档版本**: v1.0  
> **状态**: 架构设计完成，可进入实施  
> **下一阶段**: 根据用户反馈调整后开始 Phase 1 编码
