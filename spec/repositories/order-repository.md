# REPO-ORDER：Order Repository 契约

## 聚合持久化边界

Repository 的持久化对象是 `PersistedOrder`，由纯 Domain `Order` 与不可变注册身份组成。Application 组装该对象；Infrastructure 只能实现 Port，不能把 ORM 对象泄漏给 Domain/Application。

```text
PersistedOrder
├── order: Order
├── intent_id: canonical lower-case UUID
├── client_order_id: non-empty opaque string, max 128
├── registration: immutable OrderRegistered fields
└── created_at / updated_at: UTC Z
```

- `intent_id` 来自已验证的 `strategy.submit_order_intent.v1`，在注册后不可改变。
- OrderApplication 必须把 V1 command 中较宽的 legacy identifier 约束收紧为 canonical lower-case UUID；不满足返回 `QQ-OMS-5001`，不得进入 Repository。
- `order_id` 由 Application 在首次注册尝试前生成，注册成功后不可改变。
- `client_order_id` 由 Application 的 `ClientOrderIdFactory` 在注册事务前生成并随注册持久化；它在任何 Broker 副作用之前存在，后续 submit/reconcile 必须复用，禁止超时后更换。
- V1 不规定 `client_order_id` 的字符生成算法；Factory 必须通过 Execution/Broker capability 校验，并保证仓库范围唯一。Repository 不生成或改写三个 ID。
- Domain `Order` 不因持久化需要读取数据库；身份由 Application persistence DTO 包装，禁止把它们塞入 Infrastructure 私有 ORM 后失去恢复可见性。

## 逻辑 Port

精确 DTO 与返回语义见 `PORTS-ORDER-PERSISTENCE`。Repository MUST 提供：

```text
register(registration, initial_order, journal_entry, outbox_messages)
get(order_id)
get_by_intent(intent_id)
get_by_client_order_id(client_order_id)
save(commit, expected_version)
load_for_recovery(order_id)
```

所有方法均有有界 deadline；不存在返回 `None`，存储故障返回 canonical storage error。禁止返回 ORM entity、connection、query builder 或通用 SQL handle。

## 注册幂等

- `intent_id` 是注册幂等键，`order_id`、`client_order_id` 均唯一。
- 首次注册 MUST 在一个 PostgreSQL 事务中写入 `orders + order_journal(version=1) + outbox(oms.order_registered.v1)`。
- 相同 `intent_id` 与相同 canonical registration fingerprint 重放，返回已有 `PersistedOrder`，不新增 Journal/Outbox/version。
- 相同 `intent_id` 但 registration fingerprint 不同，返回 `QQ-STORAGE-7001`，不得覆盖已有订单。
- 唯一约束竞争失败后必须按 `intent_id` 重读并执行上述相同/冲突判断；不能把任意 IntegrityError 当成幂等成功。
- registration fingerprint 是验证后 OrderIntent payload（不含 Message Envelope、received_at 和传输元数据）的 canonical JSON SHA-256；tags 按 key 排序，Decimal string 不重写 scale。

## 乐观并发与事务提交

- `save` 接收 `expected_version`，并要求 `commit.order.version == expected_version + 1`。
- 更新 MUST 使用 `(order_id, expected_version)` compare-and-swap；影响行数不是 1 时返回 `QQ-COMMON-1003`。
- Order row 更新、唯一 Journal append 和全部 Outbox insert MUST 在同一事务提交。
- 任一步失败必须回滚全部写入，返回 `QQ-STORAGE-7002` 或更具体 canonical code。
- 同一 `(order_id, aggregate_version)` Journal 冲突不得覆盖；重读后由调用者重新归并事实。
- Domain 判定的 duplicate/stale no-op 不调用 `save`，不得写 Journal、Outbox 或增加 version。
- 外部 Broker、Redis、Event Backbone 调用 MUST NOT 位于数据库事务内。

## Journal

Order Journal 是内部订单历史的权威来源，Append-only。V1 事件类型仅为：

- `ORDER_REGISTERED`：aggregate version 1，包含完整 registration 与初始 post-state。
- `ORDER_TRANSITION_APPLIED`：包含规范 OrderEvent/Action、previous/current state、accepted fact/conflict delta 及完整 post-state。

Journal 保存已经通过 Domain Guard 的事实；恢复时验证并恢复 committed post-state，不重新访问 Broker/DB，也不重新执行历史 Guard。任何修正使用更高版本 Journal 事实，禁止 UPDATE/DELETE 历史。

每个 accepted transition 对应且只对应一个新 aggregate version。Journal schema、checksum 和链校验见 `STORAGE-ORDER-PERSISTENCE`。

## Outbox 映射

- `ORDER_REGISTERED` MUST 同事务产生一个 `oms.order_registered.v1`。
- 每个 `ORDER_TRANSITION_APPLIED` MUST 同事务产生一个 `oms.order_status_changed.v1`，包括 `from_status == to_status` 但 cumulative/version 已变化的自迁移。
- Envelope 的 `aggregate_id=order_id`、`aggregate_version=post-state version`、`partition_key=order_id`。
- `reason_code` 使用触发的规范 `OrderEvent` 名称；`source_report_id` 仅在来源是 Broker OrderReport 时填写 report identity key，Trade 或非报告事实填 null。
- 同一事务 MAY 产生其他已在 Contract Catalog 激活的消息，但调用者必须显式提供；Repository 不猜测业务事件。
- planned message 不得写入生产 Outbox。

## Snapshot 与恢复

- Snapshot 是可丢弃的恢复加速层，不是权威来源。
- 加载 checksum、schema version、journal head checksum 均有效且 `snapshot.version <= journal.max_version` 的最高版本 Snapshot，再顺序重放更高版本 Journal。
- Snapshot 无效返回诊断 `QQ-STORAGE-7003` 并自动退化为完整 Journal 重放；不得用无效 Snapshot 启动交易。
- Journal 缺口、版本不连续、checksum/chain 不一致返回 `QQ-RECOVERY-8002` 并保持恢复屏障关闭。
- 重建结果必须恢复 registration identity、Order state/version/cumulative、processed fact fingerprints、conflict fingerprints、Broker sequences 和 provisional mappings。
- Snapshot 写入失败不回滚已提交订单事务；记录错误并继续依赖 Journal，但连续失败必须告警和容量保护。

## 隔离级别与重试

- 正确性依靠唯一约束与 compare-and-swap，不依靠进程内锁。
- 数据库 deadlock/serialization failure MAY 在事务完全回滚后有界重试；不得跨 deadline，无限重试禁止。
- `QQ-COMMON-1003` 只能由 Application 重读聚合、重新归并原始输入后有界重试；Repository 不在旧对象上自动覆盖。
- Commit 结果不确定时，调用者必须按 `order_id/intent_id + expected next version` 查询确认，禁止盲目再次产生不同 message IDs。
