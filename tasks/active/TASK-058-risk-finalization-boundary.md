---
id: TASK-058
title: Specify Risk finalization timing and bounded failure boundaries
status: active
depends_on: [TASK-003, TASK-015, TASK-029]
spec_refs: [INV-RISK, INV-CONSISTENCY, PORTS-RISK, NFR-PERFORMANCE, NFR-OBSERVABILITY, WF-SUBMIT-ORDER, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, CONTRACT-ERROR-CATALOG]
allowed_paths:
  - spec/interfaces/risk-ports.md
  - spec/nfr/performance.yaml
  - spec/nfr/observability.yaml
  - spec/workflows/submit-order.yaml
  - spec/manifest.yaml
  - ai/packets/TASK-058-IMPLEMENTATION-v1.md
  - ai/handoffs/TASK-058-IMPLEMENTATION-v1.yaml
forbidden_paths:
  - src/**
  - tests/**
  - scripts/**
  - tasks/**
  - .github/**
  - migrations/**
  - spec/contracts/**
  - spec/invariants/**
  - spec/state-machines/**
  - pyproject.toml
  - poetry.lock
  - poetry.toml
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run python scripts/validate_specs.py
        - poetry run pytest tests/spec tests/contract
  prohibited_lanes:
    - windows_miniqmt
delivery:
  schema_version: 1
  contract_status: draft
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

独立 spec-change task：消除 Risk 最终输出验证、计时和有界失败出口的契约歧义，
使 TASK-005 后续可以在不放宽 deadline、正式验证链或交易不变量的前提下实现。
本任务交付规范，不交付 Risk 运行时代码。

## Plan and activation

- Plan version: `TASK-058-PLAN-v1`
- Planning Base: `b9b313d2af1071281bc62c0919ee4caceae85825`
- Prior implementation: https://github.com/qifuxiao/QuantiQmt/pull/117
- Supersession authority: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5628617915
- Canonical STOP: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5629435266
- Preserved STOP Head: `88d217661f6d6c127758fc245336a9f806788ab9`

Human 本次单独授权从上述实时 main 创建准备 PR：暂停 TASK-005、激活本任务，
并仅更新必要任务元数据、投影测试和精确 environment-validator 身份支持。
该一次性准备授权不属于后续规范写入者的 allowed_paths；合并前不开始规范修改。
候选方案中的遥测下界计数、固定资源上限、诊断接口及失败出口仅是待正式评审的
设计方向，不是已接受规范，不追认 PR #117 的实现或历史 Review。

依赖 TASK-003、TASK-015、TASK-029 必须维持可信 completed。本任务不依赖暂停的
TASK-005，不建立循环；TASK-005 的恢复另行授权。

## Deliverables and acceptance criteria

- [ ] 仅在 allowed_paths 中五份规范落地计时和最终构造边界；不得省略
  primitive candidate → Draft 2020-12 Schema → PORTS-RISK semantics → deep freeze，
  最终 candidate 固定后不再改字段，不形成无界验证/更新时间循环。
- [ ] 明确定义 audit 采样与完整完成耗时的区别、整数向上换算和逐规则下界；
  原绝对 deadline 覆盖聚合、最终构造、验证、冻结及交付，达到预算拒绝，
  不重置预算、不允许 late PASS，不提高既有 4ms NFR 目标。
- [ ] 明确正常 worker 与一次有界 cleanup 的独立容量、唯一终态及 permit 所有权；
  阻塞 worker 不被无限替换，宿主限制 Runner 数量，不宣称 CPython 硬实时隔离。
- [ ] 明确无有效 audit 的失败出口、原异常保留与 cleanup 失败分类；调用方不得
  由异常名/文本猜重试或伪造 RiskDecision，不得投影、发布、approved OMS 迁移或
  Execution；同步修订无条件返回 timeout audit 的冲突叙述。
- [ ] 明确非等待遥测入口、固定存储/样本/worker 上限、无重试、有限标签；
  失败计数仅为可漏计下界，包含饱和与 BUSY/AVAILABLE 本地诊断语义。
  区分 observer 部分副作用与整批失败，不把零下界当作零丢失证明；
  遥测降级不能扩张为权威 audit/Outbox 丢失许可。
- [ ] manifest 更新版本，并准确区分测量字段澄清与新增本地诊断/失败接口；
  给出兼容性、调用方部署次序、回滚及受影响 TASK-005，不改变已发布
  Schema/Event/DTO/错误码/Order 状态，不将新接口谎称为零行为变化。
- [ ] 提交完整边界案例评审矩阵：正常/拒绝、ceil 到期、最终验证失败、
  cleanup 阻塞/饱和、late completion、遥测竞争/溢出/关闭/observer 异常及阻塞。
  运行全部原始验证命令；构建 wheel 后两个 installed-wheel 测试必须实际执行，
  不以 skip、mock 或候选规范 Approval 冒充未来运行时或 Mini QMT 验收。

## Non-goals and failure handling

不修改业务代码、测试、validator、其他 task、依赖或 CI；不新增业务 DTO、Event、
错误码、状态迁移，不改变 Risk hard limit、reduce-only、UNKNOWN、审计持久化语义。
不移植或合并 PR #117，不改写其 Packet/Handoff/assignment/evidence。
若五份规范不能完整承载兼容性与失败边界，或现有验证确需额外写入路径，
停止报告具体冲突并请求精确授权，不自行扩大范围或绕过测试。
本任务不访问 Mini QMT、账户、行情、委托、真实资金、部署或 release。

## Execution and handoff sequence

准备 PR 独立 Review → Human Approval/merge → 实时冻结新的 exact main Base
→ packet-only TASK-058 PR → Human canonical assignment → Coordinator add-only Handoff
→ assigned writer 首次无改写 merge 同步 → 正式 Handoff validation
→ 五份规范变更与兼容性审查 → portable evidence/CI → 独立 Review
→ Human merge → 独立 closeout → Human 另行授权 TASK-005 重规划/激活。

准备合并后的 Base 同时用于新 packet-only PR 和独立 add-only Handoff 的 parent；
task blob 在该 Base 与 Implementation Head 相同。Packet identity 和 Handoff
filename stem 均为 `TASK-058-IMPLEMENTATION-v1`，不修改 validator 的标准拓扑。
沿用既有 `repair_context.superseded_head_sha` 字段冻结 packet-only Starting Head，
不虚构 Repair 历史。不在本任务文档中猜测未来 Base、PR number、writer 或 evidence。
真实 Packet、Handoff、assignment 尚不存在；本准备 PR 不产生正式环境证据。

## Verification and expected demonstration

规范改动前后执行上述 verification.commands，使用 exact-Head 源码和兼容 Poetry
环境；先执行 `poetry build` 以实际覆盖 installed-wheel 契约，保留命令原文、
exit code、passed/failed/skipped、源码绑定和未验证范围。构建不得覆盖用户产物。
未来规范补丁的验收矩阵与原始日志可随 PR 报告，不新增仓库报告路径。
演示结果是五份规范间一致、可实现且可独立评审的边界说明；不是性能或交易验收。
