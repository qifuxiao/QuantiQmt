# PORTS-ORDER-PERSISTENCE：Order 持久化 Port

本文件定义逻辑签名；实现可使用同步或异步 Python Protocol，但参数、结果、错误与原子性不得改变。所有集合返回不可变 tuple，所有 DTO 不包含 ORM/数据库对象。

## DTO

```python
class OrderRegistration(Protocol):
    order_id: Identifier
    intent_id: Identifier
    client_order_id: str
    account_id: str
    instrument_id: InstrumentId
    side: str
    position_effect: str
    order_type: str
    quantity: Quantity
    limit_price: Price | None
    time_in_force: str
    owner_strategy_id: str
    owner_strategy_version: str
    registered_at: datetime  # UTC aware

class PersistedOrder(Protocol):
    registration: OrderRegistration
    order: Order
    registration_fingerprint: str

class JournalAppend(Protocol):
    journal_id: Identifier
    order_id: Identifier
    aggregate_version: int
    event_type: Literal["ORDER_REGISTERED", "ORDER_TRANSITION_APPLIED"]
    payload: Mapping[str, JsonValue]
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None

class OrderCommit(Protocol):
    persisted_order: PersistedOrder
    journal: JournalAppend
    outbox_messages: tuple[MessageEnvelope, ...]

class RegisterOutcome(Protocol):
    persisted_order: PersistedOrder
    created: bool  # False only for identical intent replay

class RecoveryLoad(Protocol):
    persisted_order: PersistedOrder
    source: Literal["SNAPSHOT_PLUS_JOURNAL", "FULL_JOURNAL"]
    snapshot_diagnostic: str | None
```

`JsonValue` 只允许 JSON null/bool/int/string/list/object；Decimal 使用规范字符串，禁止 float、datetime 对象和任意 Python pickle。

## OrderRepository

```python
class OrderRepository(Protocol):
    def register(
        self,
        commit: OrderCommit,
        *,
        deadline_monotonic_ns: int,
    ) -> RegisterOutcome: ...

    def get(self, order_id: Identifier, *, deadline_monotonic_ns: int) -> PersistedOrder | None: ...

    def get_by_intent(
        self,
        intent_id: Identifier,
        *,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder | None: ...

    def get_by_client_order_id(
        self,
        client_order_id: str,
        *,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder | None: ...

    def save(
        self,
        commit: OrderCommit,
        *,
        expected_version: int,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder: ...

    def load_for_recovery(
        self,
        order_id: Identifier,
        *,
        deadline_monotonic_ns: int,
    ) -> RecoveryLoad: ...
```

## SnapshotStore

```python
class OrderSnapshotStore(Protocol):
    def write(self, snapshot: OrderSnapshot, *, deadline_monotonic_ns: int) -> None: ...
    def latest_valid(self, order_id: Identifier, *, deadline_monotonic_ns: int) -> OrderSnapshot | None: ...
```

SnapshotStore 不得独立改变 Order row 或 Journal。调用者只为已经 committed 的 aggregate version 写 Snapshot。

## OutboxStore

```python
class OutboxStore(Protocol):
    def claim(self, worker_id: str, policy: ClaimPolicy) -> tuple[ClaimedMessage, ...]: ...
    def mark_published(self, message_id: str, claim_token: Identifier) -> bool: ...
    def release_failed(self, message_id: str, claim_token: Identifier, failure: PublishFailure) -> bool: ...
    def renew(self, message_id: str, claim_token: Identifier, policy: ClaimPolicy) -> bool: ...
```

- `claim` 只能返回 `PENDING` 或 lease 已过期的 `CLAIMED` 记录，并原子写入新的随机 claim token。
- mark/release/renew 必须 compare-and-swap `(message_id, claim_token, status=CLAIMED)`；token 不匹配返回 False，不得修改记录。
- Store 不执行网络发布；Publisher 不直接更新数据库。
- 生产实现使用 PostgreSQL transaction clock 计算 claim/lease/publish/retry 时间，禁止使用各 Worker 本机 wall clock 比较持久化 lease。测试通过可控 Store clock 或显式过期 fixture，不使用 sleep。

## Canonical errors

| 条件 | 结果 |
|---|---|
| 相同 intent、相同 fingerprint | `RegisterOutcome(created=False)` |
| 相同 intent、不同 fingerprint | `QQ-STORAGE-7001` |
| expected version 不匹配 | `QQ-COMMON-1003` |
| 原子提交失败 | `QQ-STORAGE-7002` |
| Snapshot 无效但 Journal 完整 | fallback + `QQ-STORAGE-7003` diagnostic |
| claim token/lease 丢失 | `QQ-STORAGE-7004`，不确认发布 |
| Journal 缺口或损坏 | `QQ-RECOVERY-8002`，恢复屏障关闭 |

超时与取消必须回滚当前事务；不能返回部分成功。
