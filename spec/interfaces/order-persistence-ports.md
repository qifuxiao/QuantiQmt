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

class RecoveryPage(Protocol):
    order_ids: tuple[Identifier, ...]
    next_page_token: str | None
    complete: bool

class SnapshotLookup(Protocol):
    snapshot: OrderSnapshot | None
    status: Literal["VALID", "ABSENT", "INVALID_DISCARDED"]
    diagnostic_code: Literal["QQ-STORAGE-7003"] | None
    diagnostic_detail: str | None
    invalid_snapshot_id: Identifier | None
    invalid_aggregate_version: int | None

class ClientOrderIdCandidate(Protocol):
    value: str
    broker: str
    account_id: str
    capability_version: str

class ClaimPolicy(Protocol):
    batch_size: int
    lease_duration_ms: int
    max_attempts: int
    initial_retry_delay_ms: int
    max_retry_delay_ms: int
    backoff_multiplier: str
    jitter_ratio: str

class ClaimedMessage(Protocol):
    message_id: str
    message_type: str
    aggregate_id: str | None
    aggregate_version: int | None
    partition_key: str
    envelope: Mapping[str, JsonValue]
    claim_token: Identifier
    lease_until: datetime  # PostgreSQL transaction clock + policy.lease_duration_ms
    attempt_count: int

class PublishFailure(Protocol):
    error_code: str
    error_detail: str
    retryable: bool

class OutboxMutationResult(Protocol):
    applied: bool
    code: Literal["OK", "QQ-STORAGE-7004"]
    detail: str | None
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

    def list_recovery_order_ids(
        self,
        *,
        scope: Literal["ALL", "ACTIVE_OR_UNKNOWN"],
        page_size: int,
        page_token: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryPage: ...

    def rebuild_projection_from_journal(
        self,
        order_id: Identifier,
        *,
        expected_journal_head_checksum: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryLoad: ...
```

- `list_recovery_order_ids` is the only full-start recovery enumeration contract. `page_size` MUST be between 1 and 1000; ordering MUST be deterministic by `(order_id)` so a restart can resume from `page_token`.
- `scope=ACTIVE_OR_UNKNOWN` includes states that may require broker reconciliation and all `UNKNOWN`/`SUSPENDED` states; `scope=ALL` is used for projection rebuild audits.
- `rebuild_projection_from_journal` MUST verify the complete Journal checksum chain and rewrite only the rebuildable `orders` projection for the same `order_id`. It MUST NOT alter Journal rows, Outbox rows, registration identity, or business facts. If `expected_journal_head_checksum` is non-null and no longer matches, return `QQ-COMMON-1003` so the caller restarts recovery for that order.

## ClientOrderIdFactory

```python
class ClientOrderIdFactory(Protocol):
    def create(
        self,
        registration: OrderRegistration,
        *,
        broker: str,
        broker_capability_snapshot: Mapping[str, JsonValue],
        deadline_monotonic_ns: int,
    ) -> ClientOrderIdCandidate: ...

    def validate(
        self,
        client_order_id: str,
        *,
        broker: str,
        broker_capability_snapshot: Mapping[str, JsonValue],
        deadline_monotonic_ns: int,
    ) -> None: ...
```

The factory is an Application Port. It MUST generate the ID before any Broker side effect, MUST validate length/charset/capability constraints for the selected Broker adapter, and MUST never query or mutate Repository state directly. Repository uniqueness remains authoritative; on a `client_order_id` uniqueness race the Application MAY call `create` again only if no Broker side effect has occurred and the original `intent_id` is still absent.

## SnapshotStore

```python
class OrderSnapshotStore(Protocol):
    def write(self, snapshot: OrderSnapshot, *, deadline_monotonic_ns: int) -> None: ...
    def latest_for_recovery(
        self,
        order_id: Identifier,
        *,
        deadline_monotonic_ns: int,
    ) -> SnapshotLookup: ...
```

SnapshotStore 不得独立改变 Order row 或 Journal。调用者只为已经 committed 的 aggregate version 写 Snapshot。
`status=ABSENT` means no snapshot rows exist. `status=INVALID_DISCARDED` means at least one candidate snapshot failed checksum/schema/head validation and the caller MUST record `QQ-STORAGE-7003`; `snapshot` MAY still contain the next lower valid snapshot, otherwise it is null and recovery continues with full Journal replay.

## OutboxStore

```python
class OutboxStore(Protocol):
    def claim(
        self,
        worker_id: str,
        policy: ClaimPolicy,
        *,
        deadline_monotonic_ns: int,
    ) -> tuple[ClaimedMessage, ...]: ...

    def mark_published(
        self,
        message_id: str,
        claim_token: Identifier,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult: ...

    def release_failed(
        self,
        message_id: str,
        claim_token: Identifier,
        failure: PublishFailure,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult: ...

    def renew(
        self,
        message_id: str,
        claim_token: Identifier,
        policy: ClaimPolicy,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult: ...
```

- `claim` 只能返回 `PENDING` 或 lease 已过期的 `CLAIMED` 记录，并原子写入新的随机 claim token。
- mark/release/renew 必须 compare-and-swap `(message_id, claim_token, status=CLAIMED, lease_until > postgresql_transaction_clock)`；token 不匹配或 lease 已过期返回 `OutboxMutationResult(applied=False, code="QQ-STORAGE-7004")`，不得修改记录。
- `renew` MUST extend `lease_until` from the PostgreSQL transaction clock, not from the previous lease value or Worker wall clock. An already expired lease cannot be renewed by the old Worker.
- `mark_published` after lease expiry is forbidden even if the publish call actually reached the backbone; the old Worker reports `QQ-STORAGE-7004` and the reclaimed Worker may publish the same `message_id` again.
- Store 不执行网络发布；Publisher 不直接更新数据库。
- 生产实现使用 PostgreSQL transaction clock 计算 claim/lease/publish/retry 时间，禁止使用各 Worker 本机 wall clock 比较持久化 lease。测试通过可控 Store clock 或显式过期 fixture，不使用 sleep。

## Canonical errors

| 条件 | 结果 |
|---|---|
| 相同 intent、相同 fingerprint | `RegisterOutcome(created=False)` |
| 相同 intent、不同 fingerprint | `QQ-STORAGE-7001` |
| expected version 不匹配 | `QQ-COMMON-1003` |
| 原子提交失败 | `QQ-STORAGE-7002` |
| order_id/client_order_id 唯一约束竞争且 bounded retry 用尽 | `QQ-STORAGE-7006` |
| Snapshot 无效但 Journal 完整 | fallback + `QQ-STORAGE-7003` diagnostic |
| claim token/lease 丢失 | `QQ-STORAGE-7004`，不确认发布 |
| Journal 缺口或损坏 | `QQ-RECOVERY-8002`，恢复屏障关闭 |

超时与取消必须回滚当前事务；不能返回部分成功。
