# CryptoPulse · 加密货币技术分析回测系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.0-green)
![Lightweight Charts](https://img.shields.io/badge/Lightweight%20Charts-4.0-orange)
![License](https://img.shields.io/badge/License-PPL--3.0-lightgrey)

**基于价格行为/结构分析的 BTC 永续合约量化回测系统**

</div>

---

## 📋 功能特性

| 功能 | 说明 |
|------|------|
| **趋势结构** | 道氏理论：基于摆动高低点（pivot）识别趋势方向 |
| **支撑阻力** | 自动识别关键支撑/阻力位，突破/回踩入场 |
| **成交量确认** | 所有信号必须有成交量放大（>MA20×1.8）才执行 |
| **K线位置过滤** | 破位K线收盘必须在极端位（实体>影线），证明方向主导 |
| **挂单突破** | 入场价设在 pivot 价位（模拟 stop 挂单），不等收盘确认 |
| **止盈止损** | 止盈 = max(波幅, ATR×2.0)，止损 = ATR×1.5，确保盈亏比≥1.33 |
| **追踪止损** | 价格到达 TP1 后止损移至入场价保本 |
| **止损冷却** | 止损触发后暂停交易 N 分钟（可开关可调），期间不开新仓 |
| **连续亏损保护** | 同方向连续亏损 3 次后暂停该方向交易 |
| **保本检查** | TP1 利润 ≥ 双边手续费才进场，不达标则放弃并标记 💰 |
| **风控标记** | 被风控阻止的信号：利润不足→💰，其他→⛔ 橙色箭头 |
| **风控统计** | 底部面板显示风控原因分布，可点击高亮对应 K 线 |
| **仓位管理** | 本金、杠杆、费率可调，自动计算净利、ROI、手续费 |
| **交易明细** | 点击某条记录自动跳转到对应 K 线并闪烁标记 |
| **CSV 导出** | 交易明细和原始信号均可导出，文件名精确到秒 |
| **日期历史** | 输入框自动保存历史查询记录（localStorage） |
| **实时模式** | 加载 7 天历史数据预热，每 30 秒自动刷新 |
| **到最新** | 自动刷新到最新数据，适用于监控当前行情 |
| **多时间周期** | 短线 1m / 中线 4H 一键切换 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install flask pandas numpy loguru aiohttp websocket-client requests
```

### 2. 配置 API

编辑 `cryptopulse/.env` 文件，填入你的 OKX API 密钥：

```ini
OKX_API_KEY="你的 API Key"
OKX_SECRET_KEY="你的 Secret Key"
OKX_PASSPHRASE="你的 Passphrase"
OKX_USE_DEMO="true"        # 默认使用模拟盘
```

> 如果不需要实盘交易，`OKX_USE_DEMO="true"` 即可，回测不需要 API Key。

### 3. 下载历史数据

```bash
# 下载所有周期
python cryptopulse/scripts/update_data.py

# 仅下载指定周期
python cryptopulse/scripts/update_data.py --intervals 1m,5m,15m

# 持续同步（每 60 秒检查）
python cryptopulse/scripts/update_data.py --loop
```

### 4. 启动回测系统

```bash
python cryptopulse/run_web.py
```

浏览器打开 **http://127.0.0.1:8080**

---

## 📁 项目结构

```
cryptopulse/
├── run_web.py                 # Web 服务入口
├── main.py                    # 实时数据管道入口
├── .env                       # 环境配置（API Key等）
├── .env.example               # 配置模板
│
├── api/                       # Web UI
│   ├── app.py                 # Flask 后端（回测API + 路由）
│   ├── templates/
│   │   └── backtest.html      # 回测页面
│   └── static/
│       ├── backtest.css       # 样式
│       └── js/
│           ├── backtest-init.js      # 全局变量 + 设置持久化
│           ├── backtest-chart.js     # K线图渲染 + 交互
│           ├── backtest-data.js      # 日期处理 + 模式切换
│           ├── backtest-panels.js    # 主逻辑：回测请求 + 统计面板
│           ├── backtest-export.js    # CSV 导出
│           └── backtest-risk.js      # 风控状态管理
│
├── config/
│   └── __init__.py            # 配置管理（Settings dataclass）
│
├── core/
│   ├── data/
│   │   ├── models.py          # 数据模型（KLine, OrderBook 等）
│   │   ├── okx_client.py      # OKX REST API 客户端
│   │   ├── pipeline.py        # 数据管道（实时流处理）
│   │   ├── ring_buffer.py     # 环形缓冲区
│   │   └── ws_manager.py      # WebSocket 管理器
│   ├── indicators/
│   │   ├── __init__.py        # 指标计算（compute_indicators / score_indicators）
│   │   ├── calculations.py    # 核心指标函数（sma, ema, rsi, atr, adx 等）
│   │   └── engine.py          # 信号引擎（TechnicalSignalEngine）
│   ├── output/
│   │   └── formatter.py       # 输出格式化
│   └── risk/
│       └── __init__.py        # 风险控制（RiskManager 止损冷却等）
│
├── scripts/
│   ├── update_data.py         # 增量补全 K 线数据
│   ├── download_historical.py # 全量下载历史数据
│   ├── refresh_7days.py       # 刷新最近 7 天数据
│   └── fix_parquet.py         # 修复损坏的 Parquet 文件
│
├── tests/
│   ├── conftest.py
│   └── unit/
│       ├── test_indicators.py
│       ├── test_models.py
│       ├── test_ring_buffer.py
│       └── test_ws_manager.py
│
└── data/                      # 数据目录（gitignored）
    └── BTC-USDT-SWAP/
        ├── klines_1m.parquet
        ├── klines_5m.parquet
        ├── klines_15m.parquet
        └── ...
```

---

## 🖥️ 界面说明

### 顶部栏

| 元素 | 说明 |
|------|------|
| **交易风格** | `1m`（短线）/ `4H`（中线）一键切换 |
| **时间输入框** | 支持 `2026/05/01 00:00 - 2026/05/31 00:00` 格式，自动保存历史 |
| **日期选择器** | 开始/结束日期时间选择 |
| **快捷按钮** | 1天 / 3天 / 7天 / 30天 / 90天 |
| **📡 到最新** | 自动刷新到最新数据（每 30 秒） |
| **🔄 实时** | 加载 7 天数据预热，模拟实时交易（每 30 秒刷新） |
| **验证值** | 入场后检查多少根 K 线（5/10/20/30） |
| **📊 预测** | 显示历史信号预测 K 线 |
| **回测** | 执行回测 |
| **保本开关** | 过滤利润不够扣手续费的交易 |
| **止损冷却** | 止损触发后的冷却时间（分钟） |

### 统计面板

回测完成后，顶部显示关键统计：

| 指标 | 说明 |
|------|------|
| **信号** | 总信号数（📈 做多 / 📉 做空） |
| **正确/错误** | 交易正确/错误笔数 |
| **准确率** | 正确交易占比 |
| **总 PnL** | 累计盈亏百分比 |
| **胜率** | 盈利交易占比（按 PnL > 0） |
| **盈亏比** | 总盈利 / 总亏损绝对值 |
| **平均盈/亏** | 盈利/亏损交易的平均 PnL |
| **连赢/连亏** | 最大连续盈利/亏损次数 |

### 底部面板

| 标签页 | 内容 |
|--------|------|
| **仓位** | 本金/杠杆/费率设置 + 净利/ROI 计算 |
| **📋 交易明细** | 每笔交易的入场/出场/PnL，点击跳转到对应 K 线 |
| **📊 PnL 分布** | 累计盈亏曲线 |
| **💰 盈亏** | 盈亏分布统计直方图 |
| **📊 评分** | 评分分布 + 离场原因分布（含超时盈利/亏损细分） |
| **📶 信号明细** | 总信号数、做多/做空占比 |
| **⚠️ 风控** | 风控阻止统计 + 风控原因分布 + 规则说明 |

### K 线图交互

- **鼠标悬停**：显示 K 线详情、信号评分、交易入场/出场信息
- **紫色出场线**：悬停在交易 K 线上显示出场价格线（✨ 止盈 / 🛑 止损 / ⏱️ 超时）
- **橙色箭头 ⛔**：被风控阻止的信号
- **橙色柱条**：止损冷却区间
- **右键菜单**：放大 / 缩小 / 重置 / 预测 K 线 / 导出 CSV / 清除高亮
- **高亮功能**：点击评分/离场原因/风控原因，K 线图上只显示匹配信号

---

## 📈 策略说明

> 详细策略参数和历史回测表现见 [当前策略指标说明.md](./当前策略指标说明.md)

### 核心理念

**不做预测，只做跟随**。完全基于价格行为：

| 要素 | 说明 |
|------|------|
| **趋势结构** | 道氏理论：更高的高点和低点 = 上升，更低的高点和低点 = 下降 |
| **支撑阻力** | 用 pivot 自动识别关键价位（left=3, right=3, lookback=30） |
| **成交量确认** | 放量 > 1.8×MA20，且 K 线收盘在极端位 |
| **挂单突破** | 入场价 = pivot 价位（模拟 stop 挂单），不等收盘确认 |
| **追踪止损** | 价格到达 trail_activate 后止损移至成本价 |

### 入场信号

| 信号 | 做多条件 | 做空条件 | 信心 |
|:----:|----------|----------|:----:|
| **放量突破** | 上升趋势 + 收盘破 pivot high + 多方 K 线 + 放量>1.8× | 下降趋势 + 收盘破 pivot low + 空方 K 线 + 放量>1.8× | 70~75 |
| **连续实体** | 连续 3 根阳线 + 放量 + 多方 K 线 | 连续 3 根阴线 + 放量 + 空方 K 线 | 60 |

### K 线位置过滤

- **多方破位**：收盘 > 开盘 **且** 实体 > 影线（多方主导）
- **空方破位**：收盘 < 开盘 **且** 实体 > 影线（空方主导）

### 止盈止损

```
止损（固定）：
  ATR × 1.5
  做多：入场价 − 1.5 × ATR
  做空：入场价 + 1.5 × ATR

止盈：
  TP 距离 = max(波幅, ATR × 2.0)    ← 确保 TP/SL ≥ 1.33
  TP1 = 入场价 ± TP 距离 × 1.0
  TP2 = 入场价 ± TP 距离 × 1.5
  TP3 = 入场价 ± TP 距离 × 2.0

追踪止损：
  到达 trail_activate（≈ TP1）后，止损移至入场价保本
```

### 风控规则

| 规则 | 说明 |
|------|------|
| **止损冷却** | 止损触发后暂停交易 N 分钟（默认 5 分钟，可开关可调） |
| **保本检查** | TP1 利润 ≥ 0.10%（双边手续费）才进场，不达标则放弃并标记 💰 |
| **连续亏损保护** | 同方向连续亏损 3 次后暂停该方向交易 |
| **追踪止损** | 到达 TP1 后将止损移至入场价保本 |

### 出场判断

| 结果 | 条件 |
|:----:|------|
| ✅ **止盈** | K 线最高/低价触及止盈价 |
| ❌ **止损** | K 线最高/低价触及止损价 |
| ⏱️ **超时** | 验证期内未触及以上两者，用收盘价判断盈亏 |

### 策略执行流程

```
每根 K 线
  → 取 30 根识别 pivot（left=3, right=3）
  → 趋势结构判断（道氏理论）
  → 入场信号检查
      ├─ 放量破位（趋势 + 突破 + 放量 + K 线位置）
      └─ 连续实体（3 根同向 + 放量）
  → 止损冷却检查 → 连续亏损检查 → 保本检查（TP1 ≥ 0.10%）
  → 执行交易（止损 ATR×1.5，止盈 max(波幅, ATR×2.0)）
  → 到达 TP1 后追踪止损保本
```

---

## 📊 数据说明

| 项目 | 说明 |
|------|------|
| **数据源** | OKX API (`BTC-USDT-SWAP` 永续合约) |
| **存储格式** | Parquet (`data/BTC-USDT-SWAP/`) |
| **支持周期** | 1m / 5m / 15m / 30m / 1H / 4H / 1D |
| **数据更新** | `update_data --loop` 每 60 秒自动同步 |

---

## 🛠️ 脚本参考

| 脚本 | 用途 | 用法 |
|------|------|------|
| `run_web.py` | 启动回测 Web UI | `python run_web.py` |
| `main.py` | 实时数据管道 + 信号输出 | `python main.py --symbol BTC-USDT --style short_term` |
| `update_data.py` | 增量补全 K 线数据 | `python scripts/update_data.py --intervals 1m,5m --loop` |
| `download_historical.py` | 全量下载历史数据 | `python scripts/download_historical.py --intervals 1m,5m,4h,1d --start 2024-01-01` |
| `refresh_7days.py` | 刷新最近 7 天数据 | `python scripts/refresh_7days.py` |
| `fix_parquet.py` | 修复损坏的 Parquet | `python scripts/fix_parquet.py` |

---

## 🧪 测试

```bash
# 运行所有测试
python -m pytest cryptopulse/tests/ -v

# 运行指定测试
python -m pytest cryptopulse/tests/unit/test_indicators.py -v
```

---

## 🛠️ 技术栈

- **后端**: Python / Flask
- **前端**: Lightweight Charts (TradingView) / 原生 JavaScript
- **数据**: Pandas / NumPy / Parquet
- **API**: OKX REST API / WebSocket

---

## 📜 版权声明

本软件采用 **Prosperity Public License 3.0.0** 许可证。

- ✅ **允许** — 个人学习、研究、测试、教育目的
- ❌ **禁止** — 商业用途、倒卖转售
- ❌ **禁止** — 实盘交易、投资决策

本软件的回测结果仅为历史数据统计，不构成任何投资建议。加密货币交易存在高风险，使用本软件所产生的一切后果由使用者自行承担。

详细条款请查看 [LICENSE](./LICENSE) 文件。
