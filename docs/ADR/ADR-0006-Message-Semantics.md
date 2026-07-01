# ADR-0006：Command/Event 分离与 At-Least-Once

> Status: Proposed

## Context

“所有模块只通过事件”无法表达需要明确接收者和结果的下单、撤单、风控及控制动作；分布式 Exactly Once 也无法由 Redis 或 Broker 共同保证。

## Decision

- 动作用 Command，事实用 Event，读取用 Query。
- 跨进程消息采用 At-Least-Once。
- 通过 Outbox/Inbox、稳定幂等键、聚合版本和对账保证业务正确性。
- 不要求同进程 Domain 内部通过 EventBus 间接调用。

## Consequences

消息可能重复、延迟或乱序，消费者必须显式处理；换来可验证的失败语义和更清晰的调用边界。

## Operational Impact

监控重复率、积压年龄、Outbox 延迟、死信和聚合版本冲突。
