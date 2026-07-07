# CryptoPulse · 加密货币技术分析回测系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.0-green)
![Lightweight Charts](https://img.shields.io/badge/Lightweight%20Charts-4.0-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

**基于多因子技术指标的 BTC 永续合约回测与实时信号系统**

</div>

---

## 📋 功能特性

| 功能 | 说明 |
|------|------|
| **多因子评分** | EMA/MACD/RSI/布林带/OBV/ADX/成交量/K线形态 + 5分钟趋势共振 |
| **止盈止损** | 每笔交易可设置止损%、止盈%，支持价格线可视化 |
| **仓位管理** | 本金、杠杆、费率可调，自动计算净利、ROI、手续费 |
| **实时模拟** | 加载7天历史数据预热指标，从现在开始模拟交易 |
| **保本过滤** | 自动过滤利润不够扣手续费的低质量信号 |
| **数据源** | OKX API 自动下载，支持 1m/5m/15m/1H/4H/1D |
| **预测K线** | 根据最新信号绘制下一根预测K线 |
| **评分分布** | 按评分段统计准确率，点击可高亮K线图 |
| **交易明细** | 点击某条记录自动跳转到对应K线并闪烁标记 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install flask pandas numpy loguru aiohttp websocket-client requests
```

### 2. 配置 API

编辑 `.env` 文件，填入你的 OKX API 密钥：

```
OKX_API_KEY="你的API Key"
OKX_SECRET_KEY="你的Secret Key"
OKX_PASSPHRASE="你的Passphrase"
```

### 3. 下载数据

双击 `scripts\update_data.bat`，选择「持续运行（每30秒检查）」，或者手动下载：

```bash
python scripts/update_data.py --intervals 1m,5m,15m
```

### 4. 启动系统

```bash
python run_web.py
```

浏览器打开 `http://127.0.0.1:8080`

---

## 🖥️ 界面预览

### 回测页面 `/backtest`

- 选择时间范围，设置验证K线数、止盈止损百分比
- 快速切换 7天/30天/90天
- 📡 到最新模式：自动刷新最新数据
- 🔄 实时模式：加载历史数据预热，从现在开始交易

### Chart 页面 `/chart`

- 实时K线图，显示最新信号
- 下一根K线预测
- 止损/止盈/入场价格线

---

## ⚙️ 评分系统

13个技术指标加权评分，总分范围 **0~100**：

| 特征 | 权重 | 说明 |
|------|------|------|
| 1m EMA趋势 | 15% | 5/13/21 EMA排列方向 |
| 5m 趋势 | 12% | 5分钟EMA方向共振 |
| 动量 | 10% | 5根K线涨跌幅 |
| MACD | 10% | MACD柱动能方向 |
| 布林带 | 8% | 价格在布林带中的位置 |
| RSI | 8% | 超买超卖判断 |
| ADX | 6% | 趋势强度 |
| 成交量 | 6% | 放量/缩量确认 |
| OBV | 6% | 量价配合 |
| 微观结构 | 6% | K线形态（大阳线/大阴线/影线） |
| 5m ADX | 6% | 5分钟趋势强度 |
| 5m RSI | 4% | 5分钟超买超卖 |
| 5m MACD | 3% | 5分钟MACD方向 |

评分 > 40 且通过三重过滤（趋势共振、ADX强度、信心度）→ 产生信号

---

## 📊 数据说明

- 数据源：OKX API (`BTC-USDT-SWAP` 永续合约)
- 存储格式：Parquet (`data/BTC-USDT-SWAP/`)
- 支持周期：1m / 5m / 15m / 30m / 1H / 4H / 1D
- 数据更新：`update_data --loop` 每30秒自动同步

---

## 🛠️ 技术栈

- **后端**: Python / Flask
- **前端**: Lightweight Charts (TradingView) / 原生JavaScript
- **数据**: Pandas / NumPy / Parquet
- **API**: OKX REST API / WebSocket

---

## ⚠️ 版权声明

本软件仅供**学习交流使用**，严禁用于以下用途：

- ❌ **商业用途** — 不得用于任何商业活动或盈利目的
- ❌ **倒卖转售** — 不得以任何形式销售、转售本软件或其衍生版本
- ❌ **实盘交易** — 不得直接用于真实交易或投资决策

本软件的回测结果仅为历史数据统计，不构成任何投资建议。加密货币交易存在高风险，使用本软件所产生的一切后果由使用者自行承担。

Copyright © 2024 CryptoPulse. All rights reserved.
