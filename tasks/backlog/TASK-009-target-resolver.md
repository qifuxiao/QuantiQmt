---
id: TASK-009
title: Implement deterministic target resolver
status: blocked
depends_on: [TASK-007, TASK-008, TASK-019]
spec_refs: [INV-TRADING, INV-RISK, PORTS-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-ORDER-INTENT-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-TARGET-RESOLVER-V1, CONTRACT-TARGET-RESOLVER-SEMANTIC-V1, WF-TARGET-RESOLUTION, STORAGE-TARGET-RESOLUTION]
allowed_paths: [src/quantiqmt/targeting/**, tests/unit/targeting/**, tests/property/targeting/**]
forbidden_paths: [src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/targeting tests/property/targeting"]
---

# Objective

按已冻结 V1 契约实现 TargetWeight/TargetPosition 到 OrderIntent/NoAction/Rejected 的纯确定性转换，以及使用注入 Snapshot/Journal Port 的 application orchestration。

## Blocking reason

等待全部直接依赖 TASK-007、TASK-008、TASK-019 分别通过独立 Review、合并并由人类以可信 delivery evidence 完成收尾。Target Resolver 契约缺口已由 TASK-019 草案消除，但本任务在全部依赖门禁完成且人类另行激活前保持 blocked。

## Frozen implementation boundary

- 在 `src/quantiqmt/targeting/**` 实现不可变 DTO 映射、纯 `TargetResolver.resolve`、`TargetResolutionSnapshotPort`/`TargetResolutionJournalPort` Protocol 和 application service；纯 Resolver 不得读取系统时钟或执行 I/O。
- 严格执行 `CONTRACT-TARGET-RESOLVER-SEMANTIC-V1` 的 guard 顺序、Decimal 计算、active-order signed leaves、deadband、lot/tick/minimum、sell-to-zero、cash buffer、price band、reason/error matrix 和固定 RFC8785/UUIDv5 向量，不得自行选算法或默认值。
- application service 必须先注册/核验稳定 target identity，再按 `(target_id, trigger_message_id)` 查询 trigger replay；只有新的可信 trigger 才能读取 Snapshot。构建 Snapshot 后按 input_fingerprint 去重：相同输入返回原记录且不得新增 Outbox，不同输入允许同一有效 Target 产生新的 Resolution。commit 不确定时查询同一 target/trigger/input/resolution identity，不得用新 Snapshot 重算。INTENT 必须通过 Journal Port 原子提交 trigger receipt + Resolution + Outbox；实现可用测试 fake/in-memory Port 验证协议。
- Snapshot Port 超时、缺失或无法形成完整可信 Request 时，application service 必须原子记录无 `resolution_id` 的 `SNAPSHOT_REJECTED/QQ-STRATEGY-3003` trigger receipt；不得伪造 Snapshot、Resolution 或 Intent。相同 trigger 返回原失败回执，只有新的可信 trigger 才可再次尝试。
- trigger replay 未命中后、读取 Snapshot 前，application service 必须检查同 account/scope/instrument 的未完成 Intent→OMS handoff。存在 `PENDING_OUTBOX` 或 `PUBLISHED_AWAITING_OMS` 时，仅记录 `HANDOFF_DEFERRED/INTENT_HANDOFF_PENDING` 回执；收到绑定同一 intent_id 的 OMS 注册证据并由新 `ORDER_CHANGED` trigger 驱动后才可继续，避免 Outbox 已提交但 OMS 尚不可见窗口内重复下单。
- 本任务不拥有 production storage adapter、数据库表或 migration。`STORAGE-TARGET-RESOLUTION` 的物理 PostgreSQL/Outbox 实现与上线必须由后续独立、人类授权任务交付；因此 TASK-009 本身不得声明 production release ready。
- 不修改已发布 Target/OrderIntent wire Schema，不执行 Risk，不调用 Broker/Execution，不导入 OMS Repository、数据库或 Redis client。

## Non-goals

- 不做最终 Risk approve。
- 不直接调用 Broker、OMS Repository 或数据库。
- 不处理 Portfolio/Ledger 权威计算，仅读取版本化 Snapshot。

## Acceptance criteria

- [ ] 纯 Resolver 对同一规范 request 产生与固定向量一致的 resolution/result/intent identity 和 canonical audit；不读取 Clock 或执行 I/O。
- [ ] POSITION/WEIGHT desired quantity、strategy sleeve delta 和完整 OMS active-order signed leaves 按冻结顺序计算；UNKNOWN/CANCEL_UNKNOWN 保守计入，方向冲突/overshoot 不产生 Intent。
- [ ] quantity/notional deadband、向零 lot rounding、min quantity、唯一 sell-to-zero odd-lot 例外、BUY/SELL tick rounding 和 inclusive price band 与契约一致且可审计。
- [ ] BUY cash buffer 使用 projected available cash 与向上量化 notional；违反时拒绝且不静默缩量。SELL 仅使用扣除 active SELL 后的 sleeve available quantity，不能出售 pending BUY。
- [ ] target_id 先核验稳定 payload identity；同 target_id 不同 fingerprint 返回 QQ-STRATEGY-3002。trigger replay 在任何新 Snapshot 读取前按 `(target_id, trigger_message_id)` 去重；相同 trigger 返回 exact committed record，不同 trigger fingerprint 返回 QQ-STRATEGY-3002。新 trigger 可基于新 Snapshot 重新解析；同 input_fingerprint 仅追加 replay receipt 且不新增 Outbox；commit UNKNOWN 只查询不重算。
- [ ] accepted Target/trigger 的 message、payload fingerprint、account/scope/instrument 和时间序列经过校验；Snapshot 构建失败原子记录无 resolution/outbox 的失败回执，重放不重复读取 Snapshot。
- [ ] 新 trigger 语义绑定失败在 Snapshot 前记录 `TRIGGER_REJECTED/RESOLUTION_TRIGGER_INVALID`；纯 Resolver 不以 trigger 字段分支，确保排除 trigger 的同 input fingerprint 始终产生字节级相同 Result/OrderIntent。
- [ ] 未完成 Intent→OMS handoff 在 Snapshot 前阻断同 scope 新解析；测试覆盖 Outbox pending、published-awaiting-OMS、注册证据绑定、同 trigger 精确 deferred replay 与新 ORDER_CHANGED trigger 解锁。
- [ ] stale/partial/unavailable/uncertain/超龄/checksum 或 identity 不一致 Snapshot、过期 Target、无效 Mandate/InstrumentSpec 和越权 scope 均 fail-closed，不产生 Intent。
- [ ] INTENT envelope 的 message_id/idempotency_key 均为 deterministic intent_id，保留 Target correlation/causation，并仅通过 Journal/Outbox 进入 `WF-SUBMIT-ORDER`。
- [ ] Property tests 覆盖 Decimal/float 拒绝、rounding 边界、cash buffer、sell-to-zero、target/trigger/input 三层 replay、部分成交或订单终态后的新 Snapshot 重解析、active order overlap、scope/identity、snapshot freshness 与 deterministic collision。

## Review focus

- Resolver 是否逐字段符合固定 RFC8785/UUIDv5 向量，而非“看起来 deterministic”。
- application service 是否在 Snapshot 前完成 target identity 与 trigger replay lookup、在 Snapshot 后完成 input replay lookup，并在 commit UNKNOWN 后查询而非重算。
- 是否把目标转换结果与 Risk 决策混淆，或绕过 OMS 注册/Risk/Execution 唯一路径。
- 是否保留 source versions/checksums、完整 calculation 与每个 NoAction/Rejected 的封闭 reason/error。
- 是否越权实现 production persistence/migration，或导入 Broker、OMS Repository、数据库、Redis、系统时钟。

## Risks and rollback

- 错误 delta 会造成过买/过卖；固定向量、重放、active-order overlap、cash/availability 和 fail-closed property tests 未全部通过前不得验收。
- TASK-009 只能交付 pure/application implementation；production Resolution Journal/Outbox adapter 与 migration 未由独立任务完成前，发布仍 prohibited。
