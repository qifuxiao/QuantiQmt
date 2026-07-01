# ADR-0007：OMS 单写者与订单一致性

> Status: Proposed

## Context

统一 OMS 若被实现为单进程会成为单点；多个 OMS 同时写订单又可能重复下单。

## Decision

- OMS 是逻辑单写者，可部署主备或多副本。
- 只有持有有效 lease 和 fencing token 的 Leader 可产生 Broker Command。
- 策略意图先注册为订单，再执行风险决策；拒单同样保留完整历史。
- Broker 委托/成交是外部事实，OMS Journal 是内部意图和状态历史；冲突通过对账解决。
- 下单超时进入 UNKNOWN，不盲目重发。

## Consequences

系统需要选主、fencing、恢复屏障和 Broker 对账；但能够避免双写和不确定状态下的重复下单。

## Operational Impact

双 Leader、lease 临近过期、UNKNOWN 订单和对账差异均属于高优先级告警。
