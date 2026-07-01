# Reference Strategies

> Status: Proposed  
> 参考策略用于验证平台，不构成收益承诺，也不因进入代码库而自动获准实盘。

## 1. Buy and Hold / Target Position

目标：验证 TargetPosition→Resolver→OrderApplication→OMS 注册→Risk 决策→OMS 迁移→Execution→Trade→Portfolio 完整闭环。

- 输入：交易日历、单标的有效行情、账户/持仓快照。
- 输出：首次满足条件时目标数量；重复 Tick 不重复下单。
- 测试：部分成交、重启、活动订单扣减、停止后保留/减仓政策。
- 不以收益作为验收标准。

## 2. Dual Moving Average

目标：验证 Bar、指标状态、Checkpoint、信号去重和 Target 模型。

- 示例规则：短均线上穿长均线→配置目标仓位；下穿→目标为零。
- 均线窗口、Bar interval、目标比例为版本化参数。
- 只使用已关闭 Bar；禁止读取当前未完成 Bar 的最终 OHLC。
- 平仓仍经过 Risk，但 Risk 应区分减仓和扩大风险。

具体窗口不在平台架构中写死，策略文档/参数集决定。

## 3. ETF Rotation

目标：验证多标的、TargetWeight、资金分配、再平衡和组合风控。

- 按固定 schedule 对批准 ETF universe 计算版本化 score。
- 选择前 N 个并输出目标权重，保留现金 buffer。
- 定义停牌、涨跌停、缺失数据、无法卖出和入选并列规则。
- 测试换手、费用、流动性、成分变更和幸存者偏差。

## 暂缓作为首版参考

网格、统计套利、做市和高频策略需要更复杂的订单管理、腿级原子性、盘口模型或低延迟能力。在基础闭环、对账和故障恢复稳定前不作为首版目标。

## 每个参考策略的文档模板

Purpose、Universe、Data、Decision Schedule、Signal Formula、Output Model、Position Sizing、Exit、Strategy Risk、Parameters、Checkpoint、Metrics、Backtest Assumptions、Failure Behavior、Admission Status。
