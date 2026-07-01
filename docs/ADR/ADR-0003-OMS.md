# ADR-0003：采用统一 OMS

> Status: Superseded in part by [ADR-0007](ADR-0007-OMS-Consistency.md)

## 保留决策

OMS 是订单聚合的唯一逻辑写入者；策略、Risk、Execution 和 Portfolio 均不得直接修改订单状态。策略只能产生 OrderIntent，所有订单必须经过统一风险链路。

## 被替代内容

- “统一 OMS”不等于只有一个物理进程，而是由 Leader lease 和 fencing 保证逻辑单写。
- 交易顺序统一为：`OrderIntent → OMS 注册 → Risk 决策 → OMS 迁移 → Execution → Broker`。
- 下单超时进入 SUBMIT_UNKNOWN，通过查询和对账收敛，禁止盲目重发。

规范性定义见 [Trading-Core.md](../30-Trading/Trading-Core.md) 和 [OMS-And-Risk-Specification.md](../30-Trading/OMS-And-Risk-Specification.md)。
