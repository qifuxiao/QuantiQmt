# PORTS-CORE：核心 Port 契约

## BrokerGateway

MUST 提供 connect/disconnect、submit_order、cancel_order、query_order/open_orders/trades/account/positions、capabilities、health。Submit/Cancel MUST 接收 idempotency_key、deadline 和 fencing_token；超时 MUST 返回 UNKNOWN_OUTCOME，不能返回普通失败。

## MarketGateway

MUST 提供 start/stop、subscribe/unsubscribe、snapshot、health。订阅幂等；回调只标准化并有界入队；Snapshot 包含 as_of、quality、version。

## EventPublisher/EventSubscriber

PublishReceipt 只表示 Backbone 接收。Subscriber 只有业务事务提交后 ACK；重投必须依赖 Inbox 幂等。Subscription 必须指定 consumer_name、event_types、partition、max_in_flight、retry 和 replay policy。

## CommandBus

MUST 提供明确接收者、deadline 和 CommandResult。MUST NOT 使用 EventBus request/response 模拟需要确定结果的下单、撤单和控制动作。

## Clock/Scheduler

Clock 提供 UTC business time 和 monotonic latency time。Scheduler Command 必须具有 job_id、misfire policy 和 idempotency_key。Domain MUST NOT 直接读取系统时间。

规范性逻辑签名及解释见 `docs/15-Interfaces/API-Contracts.md`；若该文档与本规范冲突，以本规范为准。
