# PORTS-STRATEGY：策略 Port 契约

## StrategyRuntime

MUST 提供 load/start/pause/stop/checkpoint。只有 RUNNING generation 能输出 Target/OrderIntent；旧 generation 输出必须拒绝。Runtime MUST 限制 CPU、内存、回调 deadline、队列和输出频率。

### StrategyContext (CONTRACT-STRATEGY-CONTEXT-V1)

`StrategyContext` 是只读 DTO，包含策略身份/版本、单调递增 `generation`、`LIVE` 或 `BACKTEST` 模式、不可变 market/account/portfolio snapshot 版本、最小权限 scope 和 `as_of`。Live 不得暴露未来数据；Backtest 必须有有限的 backtest end，并拒绝读取 end 之后的数据。同一 snapshot version 与查询在两种模式下必须得到相同值。SDK 不得暴露可变 Repository、系统时钟、Secret、Broker、SQL、Redis 或网络客户端。

### Callback 与 deadline (CONTRACT-STRATEGY-CALLBACK-V1)

`initialize`、`on_market`、`on_timer`、`on_order`、`on_trade` 均使用 CONTRACT-STRATEGY-CALLBACK-V1 envelope，带 callback id、generation、context snapshot 和绝对 deadline。Runtime 按策略串行派发，拒绝过期或重复 callback；超时转为有界 Runtime failure。输入不可变，callback 不得修改 OMS 或外部状态。

### Output 与 generation fencing (CONTRACT-STRATEGY-OUTPUT-V1)

只有 RUNNING generation 且拥有 `EMIT_TARGET` 或 `EMIT_ORDER_INTENT` scope 才能输出。Runtime 先做 schema 校验，再执行 output id、频率、队列和 generation fencing；旧 generation 必须拒绝。Target 只能交给 TargetResolver，OrderIntent 必须符合已发布 command contract，并仍需 OMS 注册与 Risk。策略不得直接调用 Broker、OMS、Repository 或 Execution port。

### Checkpoint (CONTRACT-STRATEGY-CHECKPOINT-V1)

Checkpoint envelope 包含 strategy/version/generation、schema version、captured timestamp、opaque payload 和 canonical payload bytes 的 SHA-256。Canonicalization 固定采用 RFC 8785 JCS：对象键按其原始属性名的 UTF-16 code units 排序（不是 Unicode code points）、无空白、UTF-8 无 BOM、Unicode scalar 与 RFC 8785 number serialization；hash 输入只包含 payload 值，不包含 envelope 或 payload_sha256。Restore 对缺失、不支持、格式错误、checksum/version 不匹配或过期 generation 必须 fail-closed；恢复原子失败时保持 PAUSED 或 ERROR，不能恢复输出。重复 checkpoint 与 callback id 必须幂等忽略。

规范向量：payload 属性名 U+10000 `𐀀` 与 U+E000 `` 按 RFC 8785 UTF-16 code-unit 顺序必须先排 U+10000（代理项 D800 DC00）再排 U+E000（E000），即 canonical member order 为 `{"𐀀":2,"":1}`；任何按 Unicode code point 排序的实现均不符合本契约。

### Runtime 限制、失败与审计

Runtime 必须配置有限 CPU、内存、callback deadline、队列深度和输出频率。资源超限、callback 异常、无效输出、依赖过期或 checkpoint 失败必须写入带 correlation_id 的 `strategy.state_changed.v1` 审计事件：可恢复故障转 PAUSED，完整性/安全故障转 ERROR。Resume 需要新鲜 approved context、已验证 checkpoint/dependencies 和新 generation；worker failure 不得改变 OMS 订单。

## Strategy SDK

策略只接收只读 StrategyContext，通过 initialize/on_market/on_timer/on_order/on_trade/checkpoint/restore 参与运行。SDK MUST NOT 暴露 Broker、Repository、SQL、Redis 或通用网络客户端。

## TargetResolver

`CONTRACT-TARGET-RESOLVER-V1`、`CONTRACT-TARGET-RESOLVER-SEMANTIC-V1`、
`WF-TARGET-RESOLUTION` 和 `STORAGE-TARGET-RESOLUTION` 是 Target Resolver 的完整
V1 契约。现有公开 `strategy.submit_target.v1` 与
`strategy.submit_order_intent.v1` Payload Schema 保持不变；本节冻结内部输入、
计算、审计、重放和 Port 语义。

### Logical signatures

```python
class TargetResolutionSnapshotPort(Protocol):
    def build(
        self,
        accepted_target: AcceptedTargetRef,
        resolution_trigger: ResolutionTrigger,
        target: SubmitStrategyTargetPayloadV1,
        mandate: StrategyMandate,
        instrument_spec: InstrumentSpec,
        policy: TargetResolutionPolicy,
        *,
        resolution_time: datetime,
        deadline_monotonic_ns: int,
    ) -> TargetResolutionRequest | ResolutionTriggerReceipt: ...

class TargetResolver(Protocol):
    def resolve(self, request: TargetResolutionRequest) -> TargetResolutionResult: ...

class TargetResolutionJournalPort(Protocol):
    def register_target(
        self, accepted_target: AcceptedTargetRef, target: SubmitStrategyTargetPayloadV1,
        *, deadline_monotonic_ns: int
    ) -> RegisteredTarget: ...

    def get_by_trigger(
        self, target_id: str, trigger_message_id: str,
        *, deadline_monotonic_ns: int
    ) -> tuple[ResolutionTriggerReceipt, StoredTargetResolution | None] | None: ...

    def get_by_input_fingerprint(
        self, input_fingerprint: str, *, deadline_monotonic_ns: int
    ) -> StoredTargetResolution | None: ...

    def has_unresolved_intent_handoff(
        self, account_id: str, scope_id: str, instrument_id: str,
        *, deadline_monotonic_ns: int
    ) -> bool: ...

    def commit_new_resolution(
        self,
        request: TargetResolutionRequest,
        result: TargetResolutionResult,
        *,
        deadline_monotonic_ns: int,
    ) -> StoredTargetResolution: ...

    def link_exact_input_replay(
        self, trigger: ResolutionTrigger, existing: StoredTargetResolution,
        *, deadline_monotonic_ns: int
    ) -> ResolutionTriggerReceipt: ...

    def commit_snapshot_rejection(
        self, receipt: ResolutionTriggerReceipt, *, deadline_monotonic_ns: int
    ) -> ResolutionTriggerReceipt: ...

    def commit_handoff_deferred(
        self, receipt: ResolutionTriggerReceipt, *, deadline_monotonic_ns: int
    ) -> ResolutionTriggerReceipt: ...

    def commit_trigger_rejection(
        self, receipt: ResolutionTriggerReceipt, *, deadline_monotonic_ns: int
    ) -> ResolutionTriggerReceipt: ...

    def record_oms_registration(
        self, accepted: AcceptedMessageRef, registered: OmsOrderRegisteredV1,
        *, deadline_monotonic_ns: int
    ) -> StoredTargetResolution: ...
```

`TargetResolver.resolve` MUST 是纯计算：不得访问 Broker、Execution、Risk、OMS
Repository、数据库、Redis、网络或系统时钟。Snapshot 与 Journal Port 是
Application 边界，不得由策略持有；所有返回 DTO 都不可变且不暴露 ORM、SDK 或
Repository 对象。Port 的等待必须受调用方绝对 deadline 限制，不得延长 deadline。
Snapshot 构建超时、缺失或无法形成完整可信 Request 时，不得伪造 Snapshot 或
resolution identity；Application 必须通过 Journal 原子记录无 `resolution_id` 的
`SNAPSHOT_REJECTED/QQ-STRATEGY-3003` trigger receipt。同一 trigger 重放直接返回该
失败回执，新的可信 trigger 才可再次尝试构建。
Trigger 的 `source_contract_id` 表示 manifest contract 或本 Resolver contract 内部
source type，`source_state_version` 表示触发事实已进入的权威 projection 版本，两者
不得混用。POSITION/ORDER/ACCOUNT/MARKET trigger 必须由
Snapshot builder 证明其 state version 分别被 Portfolio/OMS active-order/Account/Market
Snapshot 精确包含；TARGET_ACCEPTED 与 Scheduler 的 state version 必须为 null。包含
关系不成立时记录 `SNAPSHOT_REJECTED/SNAPSHOT_IDENTITY_MISMATCH`，不得调用纯 Resolver。

### Mandate, scope and immutable inputs

`StrategyMandate` 精确绑定 strategy id/version、`STRATEGY_SLEEVE` scope、account、
portfolio、允许的 Target 类型和 instrument、long-only 上限、最大权重/数量、现金
buffer 及有效期。Target 的 strategy/scope/instrument 任一不匹配都返回
`REJECTED`，不得修正或扩大 Mandate。V1 仅支持非负整数 long-only Position；负
Target 或 short 必须发布新契约版本。

`InstrumentSpec` 冻结整数 Quantity、lot size、min order quantity、tick size、
currency minor unit、动态价格带来源、向零 quantity rounding、BUY 向下与 SELL
向上 tick rounding，以及显式 sell-to-zero odd-lot 能力。所有 Price、Weight、
Money 与 Notional 都是普通 Decimal 字符串，float/NaN/Infinity/指数形式和负零
禁止进入 Resolver。

`TargetResolutionSnapshot` 是一次不可变、可校验的派生 read model，不是新的事实
来源。它绑定 Portfolio current position、Strategy sleeve attribution、内部 Account
projected available cash、Market reference price/price band、完整 OMS active-order
snapshot 的 version/checksum/as-of/quality。builder MUST 从各权威来源读取同一
account/portfolio/scope/instrument/currency，并在投影前验证源 checksum。任何 stale、
partial、unavailable、uncertain、超龄、混合身份、缺失或 checksum 不匹配均
fail-closed，不能产生 Intent：能够形成完整 Request 的不可信证据生成
`REJECTED/QQ-STRATEGY-3003` Resolution；无法形成完整 Request 的超时、缺失或坏证据
生成无 resolution identity 的 `SNAPSHOT_REJECTED/QQ-STRATEGY-3003` trigger receipt。
Broker 查询不是该 Snapshot 的权威来源。

Portfolio、Strategy sleeve 与 OMS active-order Snapshot 必须绑定相同 trade
watermark；Account 的 reservation snapshot version 必须等于 active-order snapshot
version。每个活动订单同时携带 original/cumulative/position-applied cumulative 和
leaves，且 `position_applied_cumulative == cumulative`、
`leaves == original - cumulative`。否则当前持仓与未成交影响可能双算，必须以
`ACTIVE_ORDER_SNAPSHOT_INVALID/QQ-STRATEGY-3003` 拒绝。

### Deterministic calculation

规范算法以 Semantic Contract 为准，顺序不可交换：

1. `POSITION` 直接给出 desired quantity；`WEIGHT` 使用
   `floor(total_equity * target_weight / reference_price)`，中间值为 Decimal。
2. `unadjusted_delta = desired_quantity - sleeve_quantity`。
3. 对按 `order_id` 排序的完整活动订单集合，BUY leaves 为正、SELL leaves 为负；
   `active_order_expected_delta = sum(expected_delta)`，
   `residual_delta = desired_quantity - (sleeve_quantity + active effect)`。
4. UNKNOWN/CANCEL_UNKNOWN 等非终态也按 OMS leaves 保守计入，禁止换 ID 重试；
   混合方向、与原始 delta 反向或会越过 Target 的活动订单返回 `REJECTED`，不得发
   反向订单抵消。精确覆盖 Target 返回 `NO_ACTION`。
5. 先应用 quantity/notional deadband，再将绝对 residual 向零取整到 lot；不得通过
   四舍五入扩大风险。只有配置允许、Target 为零且卖出恰好清空剩余可卖 sleeve 时，
   可使用 sell-to-zero odd-lot 例外。普通结果低于 min quantity 为 `NO_ACTION`。
6. SELL 不得使用 pending BUY 作为可卖数量；候选数量大于扣除 active SELL 后的
   sleeve available quantity 时拒绝。BUY 以向上量化到 currency minor unit 的
   notional 检查 `projected_available_cash - notional >= required_cash_buffer`；违反
   时拒绝，不能静默缩量。
7. LIMIT price 从已绑定 reference price 产生：BUY 向下、SELL 向上取整到 tick，
   随后必须处于含端点的动态 price band 内。

每个 Result 都携带 source versions/checksums 可关联的 `input_fingerprint` 和完整
calculation evidence。`NO_ACTION` 与 `REJECTED` 具有封闭 reason enum；拒绝结果
不能携带 OrderIntent。

### Identity, replay and Order chain

所有 fingerprint 使用 RFC 8785 JCS UTF-8 SHA-256；key 按原始属性名 UTF-16 code
units 排序，不做 Unicode normalization，Decimal 字符串原样参与 hash。固定
namespace `7a6bdb48-22b7-5f65-bb55-63e4a8ff6325`：

```text
resolution_id = UUID5(namespace, input_fingerprint)
intent_id = UUID5(resolution_id, "order-intent:0")
OrderIntent envelope message_id = idempotency_key = intent_id
```

Application MUST 先以 `target_id + target_fingerprint` 注册稳定 Target 身份；同
target id 不同 payload 返回 `QQ-STRATEGY-3002`。随后在读取任何新 Snapshot 前以
`(target_id, resolution_trigger.message_id)` 查询 Journal：相同 trigger fingerprint
返回精确已提交记录，不同内容复用 trigger id 返回
`RESOLUTION_TRIGGER_CONFLICT/QQ-STRATEGY-3002`。

Trigger 未命中 replay 后、读取新 Snapshot 前，Application MUST 按
account/scope/instrument 查询未完成的 Intent→OMS handoff。任何既有 INTENT 仍处于
`PENDING_OUTBOX` 或 `PUBLISHED_AWAITING_OMS` 时，本次 trigger 只能原子记录
`HANDOFF_DEFERRED/INTENT_HANDOFF_PENDING` 回执，不得读取 Snapshot 或生成新 Intent。
只有以相同 intent id 验证的 OMS durable registration receipt 才能迁移到
`OMS_REGISTERED`；随后必须由新的可信 `ORDER_CHANGED` trigger 发起下一次解析。

新的、已验证 trigger（Target 首次接受、Position/Order/Account/Market 变化或有界
Scheduler reevaluation）可以在 Target 有效期内构建新 Snapshot，支持部分成交、订单
终态或资金/行情变化后的再求解。`input_fingerprint` 明确排除 trigger，仅绑定 canonical
Target、Mandate、InstrumentSpec、Policy 与完整 Snapshot；因此相同 Target+Snapshot
无论由哪个 trigger 到达都产生相同 resolution/intent identity。新 trigger 命中已有
input fingerprint 时只原子记录 `EXACT_INPUT_REPLAY` trigger receipt 并返回原记录，
不得再写 Outbox。commit 结果不确定时只查询相同 target/trigger/input/resolution ids，
不得换 Snapshot 重算。相同 deterministic ID 对应不同 fingerprint 是
`QQ-STORAGE-7011` 完整性事故。

INTENT Result 与 `strategy.submit_order_intent.v1` Outbox 必须原子提交。生成的
Intent 仍然进入 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution`；Resolver
不得执行 Risk、宣称 RiskPassed、直接写 OMS 或调用 Broker。Envelope 的 correlation
与 causation 均继承 canonical accepted Target，保证排除 trigger 的同一 input fingerprint
始终产生字节级相同 OrderIntent；本次 trigger lineage 由 Stored Request 与 trigger
receipt 审计，不写入 OrderIntent。partition 为 account id。Trigger 必须与该 Target
的 account/scope/instrument 绑定，
并经过有界 debounce/频率限制；无关事件不能触发重算。

### Failure and observability

`QQ-STRATEGY-3001` 表示确定性业务拒绝，`QQ-STRATEGY-3002` 表示 Target 或 Trigger
identity 重放冲突，`QQ-STRATEGY-3003` 表示 Snapshot/输入证据不可用或不可信。所有结果都
写入 append-only Resolution audit，所有已接受 trigger 结论写入 append-only trigger
receipt；INTENT 额外写 Outbox。结构化日志必须包含
resolution/target/strategy/scope/instrument/outcome/reason/fingerprint；指标仅使用
`outcome/reason_code/target_type` 等低基数字段，禁止把业务 ID、instrument 或 hash
作为 metric label。

## Dependency Rule

`strategies → strategy_sdk → contracts`。任何从 strategy 包到 trading_platform/infrastructure 的 import 都是架构违规。
