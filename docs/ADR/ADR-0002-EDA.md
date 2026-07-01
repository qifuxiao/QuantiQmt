# ADR-0002：采用事件驱动架构

> Status: Superseded in part by [ADR-0006](ADR-0006-Message-Semantics.md)

## 历史决策

系统使用事件传播跨组件业务事实，以降低发布者和消费者的直接耦合，并支持审计、追踪和投影重建。

## 被替代内容

“所有业务协作只能通过事件、禁止直接调用”不再有效。当前规范为：

- 动作用 Command，事实用 Event，读取用 Query。
- 同进程纯领域计算允许直接调用。
- 跨进程消息采用 At-Least-Once，通过幂等、Outbox/Inbox、聚合版本和对账保证正确性。

规范性定义见 [Event-Architecture.md](../10-EventDriven/Event-Architecture.md) 和 [Message-Contracts.md](../10-EventDriven/Message-Contracts.md)。
