# Core API and Port Contracts

> Status: Proposed  
> 本文是核心 Port 的解释性总览。规范性逻辑签名、错误语义、幂等约束和 DTO 边界以 `spec/interfaces/**` 与 `spec/manifest.yaml` 为准；若本文与 `spec/` 冲突，以 `spec/` 为准。

接口示例使用 Python typing 表达意图，不代表已经开始实现，也不得作为绕过 `spec/` 的第二套契约。所有公共 DTO 必须在对应 spec-change task 中冻结后才能被实现任务使用。

## 通用结果

跨基础设施 Port 不通过 `None/False` 模糊表达失败：成功返回明确 DTO；预期失败返回 `Result[T, SystemError]` 或抛出契约中列出的 typed exception。项目必须统一选择一种风格，不得混用。

所有异步操作支持 deadline/timeout；取消不代表外部动作未发生。

## MarketGateway

```python
class MarketGateway(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self, request: SubscribeRequest) -> Subscription: ...
    async def unsubscribe(self, subscription_id: str) -> None: ...
    async def snapshot(self, instrument_id: str) -> MarketSnapshot: ...
    def health(self) -> ComponentHealth: ...
```

- start/stop 幂等；start 成功不等于行情新鲜，readiness 由 Health 判定。
- subscribe 使用稳定 subscription_id；重复订阅合并引用计数，不能重复占用 Broker 资源。
- SDK 回调通过 Publisher Port 输出 Market Event，不由调用方传 callback 闭包。
- snapshot 明确返回 quality/as_of；陈旧数据不能伪装成新鲜快照。

## BrokerGateway

```python
class BrokerGateway(Protocol):
    async def connect(self) -> BrokerSession: ...
    async def disconnect(self) -> None: ...
    async def submit_order(self, command: BrokerSubmitCommand) -> SubmitReceipt: ...
    async def cancel_order(self, command: BrokerCancelCommand) -> CancelReceipt: ...
    async def query_order(self, query: OrderQuery) -> BrokerOrderSnapshot | NotFound: ...
    async def query_open_orders(self, account_id: str) -> Sequence[BrokerOrderSnapshot]: ...
    async def query_trades(self, query: TradeQuery) -> Sequence[BrokerTradeSnapshot]: ...
    async def query_account(self, account_id: str) -> BrokerAccountSnapshot: ...
    async def query_positions(self, account_id: str) -> Sequence[BrokerPositionSnapshot]: ...
    def capabilities(self) -> BrokerCapabilities: ...
    def health(self) -> ComponentHealth: ...
```

- submit/cancel 必须携带 deadline、idempotency_key、client_order_id 和 fencing_token。
- SubmitReceipt 仅表示 SDK 接收结果；除非 Broker 明确确认，不能等同订单已创建。
- Timeout/ConnectionLostAfterWrite 必须映射为 `UNKNOWN_OUTCOME`。
- Adapter 发布标准 BrokerOrder/Trade Event；原始错误码保留，Domain 只读取统一 error_code。
- query API 必须说明分页、查询窗口、最终一致性可见延迟和限流。

## ExecutionGateway

```python
class ExecutionGateway(Protocol):
    async def submit(self, command: SubmitOrderCommand) -> ExecutionAttempt: ...
    async def cancel(self, command: CancelOrderCommand) -> ExecutionAttempt: ...
    async def reconcile(self, order: OrderSnapshot) -> ReconciliationObservation: ...
```

ExecutionGateway 负责路由、能力校验、限速和 BrokerGateway 调用，不推进订单状态。每次 attempt 必须先持久化 `ExecutionAttemptStarted`。

## EventBus and CommandBus

```python
class EventPublisher(Protocol):
    async def publish(self, event: IntegrationEvent) -> PublishReceipt: ...

class EventSubscriber(Protocol):
    async def subscribe(self, spec: SubscriptionSpec, handler: EventHandler) -> SubscriptionHandle: ...

class CommandBus(Protocol):
    async def send(self, command: Command, deadline: Deadline) -> CommandResult: ...
```

- EventBus 不提供泛化 request/response；需要结果的动作通过 CommandBus。
- PublishReceipt 表示消息系统接受，不表示所有 Consumer 完成。
- Handler 只有业务事务成功后 ACK；失败按 retry policy 重投，超过预算进入 dead-letter。
- SubscriptionSpec 必须指定 consumer_name、event_types、partitioning、max_in_flight、retry_policy 和 replay_policy。

## OMS Application Port

```python
class OrderApplication(Protocol):
    async def submit_intent(self, command: SubmitOrderIntent) -> OrderRef: ...
    async def cancel_order(self, command: CancelOrder) -> OrderRef: ...
    async def handle_broker_order(self, report: BrokerOrderReport) -> OrderSnapshot: ...
    async def handle_trade(self, report: BrokerTradeReport) -> OrderSnapshot: ...
    async def get_order(self, order_id: str) -> OrderSnapshot: ...
```

submit_intent 先按 intent_id 幂等注册，再触发风险流程。API 返回不代表成交。所有写操作携带 expected_version 或使用内部单写者串行化。

## Strategy Runtime and Target Resolver Ports

```python
class StrategyRuntime(Protocol):
    async def load(self, artifact: StrategyArtifact) -> StrategyInstance: ...
    async def start(self, instance_id: str) -> None: ...
    async def pause(self, instance_id: str, reason: str) -> None: ...
    async def stop(self, instance_id: str, policy: StopPolicy) -> None: ...
    async def checkpoint(self, instance_id: str) -> StrategyCheckpoint: ...

class TargetResolver(Protocol):
    async def resolve(self, target: StrategyTarget, context: ResolutionContext) -> TargetResolution: ...
```

Runtime 只能发布 Target/OrderIntent，不能持有 Broker 能力。Resolver 是确定性 Application Service：输入包含快照版本和活动订单影响，输出 Intent 或带原因的 NoAction/Rejected。

## Risk Port

```python
class RiskEvaluator(Protocol):
    def evaluate(self, request: RiskEvaluationRequest) -> RiskDecision: ...
```

必须是确定性纯计算：无网络、数据库、系统时钟和可变全局状态。输入包含全部快照与版本；输出包含逐规则结果。

## Repository and Unit of Work

```python
class OrderRepository(Protocol):
    async def get(self, order_id: str) -> OrderAggregate | None: ...
    async def get_by_intent(self, intent_id: str) -> OrderAggregate | None: ...
    async def save(self, order: OrderAggregate, expected_version: int) -> None: ...

class UnitOfWork(Protocol):
    orders: OrderRepository
    outbox: OutboxRepository
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

- Repository 以聚合为边界，不暴露通用 `execute_sql()`。
- save 与 Domain Event→Outbox 写入同一事务。
- 并发版本错误必须是明确 Conflict，不得覆盖后写。

## Clock and Scheduler

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...

class Scheduler(Protocol):
    async def schedule(self, job: ScheduledCommand) -> JobHandle: ...
    async def cancel(self, job_id: str) -> None: ...
```

LiveClock 与 VirtualClock 通过同一契约测试。ScheduledCommand 包含稳定 job_id、deadline、misfire policy 和幂等键。

## Configuration Port

```python
class ConfigurationProvider(Protocol):
    async def current(self, scope: ConfigScope) -> VersionedConfig: ...
    async def watch(self, scope: ConfigScope) -> AsyncIterator[ConfigCandidate]: ...
    async def acknowledge(self, version: str, result: ActivationResult) -> None: ...
```

组件必须先 validate candidate，再原子切换 active snapshot；禁止在一次业务决策中读取两个配置版本。

## Control API

```text
POST /v1/order-intents
POST /v1/orders/{order_id}/cancel
POST /v1/kill-switches/{scope}/{id}:enable
POST /v1/kill-switches/{scope}/{id}:disable
POST /v1/system-mode:transition
GET  /v1/orders/{order_id}
GET  /v1/reconciliation-cases
POST /v1/reconciliation-cases/{case_id}:resolve
GET  /v1/health/readiness
GET  /v1/health/liveness
```

所有写 API 要求 request_id/idempotency_key、认证、授权、reason 和审计。HTTP 202 表示异步接受；最终状态通过订单查询/Event 获取。解除 Kill Switch、账务调整和强制修复必须执行审批策略。

## 契约治理

- 每个 Port 至少有一个 fake 和一个真实 Adapter 契约测试套件。
- 改签名、错误语义、幂等行为或时间语义必须新增 ADR。
- 禁止 Adapter 返回供应商 SDK 对象。
- 接口冻结不等于永不演进；破坏性变化提供新版本和迁移窗口。
