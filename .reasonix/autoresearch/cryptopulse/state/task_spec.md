# CryptoPulse — 单币种智能交易决策工具

## Goal
Design a complete production-ready architecture for a single-coin intelligent trading decision tool ("CryptoPulse") based on OKX exchange data. Deliver a full implementation plan with technical stack, module breakdown, AI Agent design, and backtesting methodology.

## Core Requirements
1. **Data Layer**: OKX WebSocket real-time streams (1m/5m/4h/1d K-lines, ticker, order book, funding rate, open interest, mark price) + REST snapshots + local cache
2. **Analysis Pipeline — 3-Stage Evaluation**:
   - Stage 1: Multi-timeframe technical signal matrix (EMA, MACD, RSI, Bollinger, volume, S/R)
   - Stage 2: Market microstructure & sentiment verification (order book imbalance, flow, large orders, funding rate, OI changes, fear & greed)
   - Stage 3: AI multi-agent committee (DeepSeek-style) for final decision, entry/exit points, position sizing
3. **Output**: Standardized trading plan with confidence score, entry zone, take-profit levels, stop-loss, position %
4. **Style Adaptation**: Short-term (1m/5m) vs Medium-term (4h/1d)

## Key Research Areas
- OKX WebSocket & REST API capabilities and limitations
- Open-source crypto signal systems (Freqtrade, Jesse, Gekko, etc.)
- Technical indicators & microstructure factors for crypto
- AI multi-agent committee design patterns
- Backtesting methodology for crypto strategies

## Success Criteria
- [ ] Complete architecture document covering all layers
- [ ] Detailed module breakdown with interfaces
- [ ] AI Agent design with agent roles, debate mechanism, scoring
- [ ] Technical stack recommendation with rationale
- [ ] Backtesting & validation plan
- [ ] Literature survey summary
