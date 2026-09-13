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
  - tests/spec/test_order_registration_binding_contracts.py
  - tests/spec/test_risk_runtime_schema_contract.py
  - tests/unit/contracts/test_schema_bundle.py
  - ai/packets/TASK-058-IMPLEMENTATION-v2.md
  - ai/handoffs/TASK-058-IMPLEMENTATION-v2.yaml
forbidden_paths:
  - src/**
  - tests/contract/**
  - tests/property/**
  - tests/integration/**
  - scripts/**
  - tasks/**
  - .github/**
  - migrations/**
  - spec/contracts/**
  - spec/invariants/**
  - spec/state-machines/**
  - ai/packets/TASK-058-IMPLEMENTATION-v1.md
  - ai/handoffs/TASK-058-IMPLEMENTATION-v1.yaml
  - pyproject.toml
  - poetry.lock
  - poetry.toml
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
    - poetry run pytest tests/unit/contracts
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run python scripts/validate_specs.py
        - poetry run pytest tests/spec tests/contract
        - poetry run pytest tests/unit/contracts
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

- Plan version: `TASK-058-PLAN-v2`
- Planning Base: `3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb`
- Historical v1 Planning Base: `b9b313d2af1071281bc62c0919ee4caceae85825`
- Prior implementation: https://github.com/qifuxiao/QuantiQmt/pull/117
- Supersession authority: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5628617915
- Canonical STOP: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5629435266
- Preserved STOP Head: `88d217661f6d6c127758fc245336a9f806788ab9`

Human 本次单独授权从上述实时 main 创建 v2 范围准备 PR；TASK-058 保持唯一 active，
TASK-005 保持 blocked。此次 Coordinator / Codex / Windows 准备权限仅限：

- `tasks/active/TASK-058-risk-finalization-boundary.md`
- `tasks/active/README.md`
- `tests/spec/test_miniqmt_m1_delivery_governance.py`
- `scripts/validate_agent_environment.py`
- `tests/spec/test_validate_agent_environment.py`

该一次性准备权限不得继承给后续规范 writer。准备阶段不修改五份规范或三份实施测试，
不创建 v2 Packet/Handoff，不修改业务、依赖、CI 或正式 Handoff validator。
未来 writer 仅有 front matter 的精确 allowed_paths；不在清单中的测试同样禁止写入。
v2 Packet/Handoff 仅供另行授权的 Coordinator bootstrap，冻结后 writer 不得改写。
候选方案中的遥测下界计数、固定资源上限、诊断接口及失败出口仅是待正式评审的
设计方向，不是已接受规范，不追认 PR #117 的实现或历史 Review。

### Preserved v1 authority

- PR: https://github.com/qifuxiao/QuantiQmt/pull/119
- Assignment: https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5634925713
- Canonical STOP: https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5646729029
- STOP remote Head: `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`
- STOP author: `qifuxiao`; created_at = updated_at = `2026-09-12T15:10:41Z`
- STOP raw-body SHA-256: `eadad8bf9af6a6085eb591d736d1288c1779d3752f46dfc1adf141b5ce583075`
- Preserved local-only sync: `02fc1857a2fa885ba59477de37a7e20ca965fc3f`
- Local sync parents: `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`,
  `42ad3c3e1c65a1251d0b9654d1a36ce393dad094`
- Frozen v1 Packet blob: `6c738559a3dda4edda66600f06e99c7efbe01d70`
- Frozen v1 Handoff blob: `1a87f074bc73744316faded7963819a8c20db8ee`

STOP 的 ASSIGN→STOP 序列结束于零 active writer；它不是继续实施或环境验收授权。
本地同步提交未推送，不是远端 STOP Head，不删除、改写或自动推送。
旧 Packet/Handoff byte-for-byte 保留；旧 assignment 不覆盖 v2 路径、Base 或 writer。
本准备 PR 不关闭、合并或继续写入 PR #119。

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

后续实施不修改业务代码、未列入 allowed_paths 的测试、validator、其他 task、依赖或 CI；
不新增业务 DTO、Event、
错误码、状态迁移，不改变 Risk hard limit、reduce-only、UNKNOWN、审计持久化语义。
不移植或合并 PR #117，不改写其 Packet/Handoff/assignment/evidence。
若五份规范不能完整承载兼容性与失败边界，或现有验证确需额外写入路径，
停止报告具体冲突并请求精确授权，不自行扩大范围或绕过测试。
本任务不访问 Mini QMT、账户、行情、委托、真实资金、部署或 release。

## Exact test adaptation boundary

仅允许三个实施测试文件中的最小必要变化，不机械替换版本号、删除历史断言、
增加 skip/xfail、mock 正式验收或弱化安全检查：

- `test_order_registration_binding_contracts.py`：将旧 manifest version/change/previous
  断言绑定真实冻结历史；保留当前禁止 destructive backfill、TASK-050 completed、
  TASK-048 依赖以及 legacy UNBOUND 禁止重绑定的全部断言。
- `test_risk_runtime_schema_contract.py`：保留 TASK-029 历史 lifecycle 全部断言；
  当前 Catalog/Schema/route 身份仍在当前树验证，新增 TASK-058 当前版本、兼容性、
  部署/回滚及五规范边界检查，不能用新版本替代已发布 Schema/Event/DTO 身份。
- `test_schema_bundle.py`：历史 bundle 对真实冻结来源保持完整 bytes parity；
  另验证当前完整 contract index、文件集合及 bytes 与冻结来源一致，不能只验证历史树。
  duplicate/missing/unresolved/source-drift 负例保留原拒绝阶段；旧 builder 对新 manifest
  版本不匹配仍须拒绝，不能 patch 常量或把当前 manifest 临时改回旧版本。

历史 manifest 来源为 `3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb:spec/manifest.yaml`，
blob 为 `1a72adc78638dc223fb263df8beb69a7e2586bb3`。读取需验证精确来源，
缺少历史对象必须失败，不得合成历史或 skip。现有 runtime bundle 的 `0.15.0` 身份、
版本/损坏/缺失拒绝检查及两个 wheel 用例不变，不将旧 runtime 声称为新规范实现。
新规范与旧 bundle 的兼容性仍须正式 Review；本准备授权不预先裁定。

## Execution and handoff sequence

准备 PR 独立 Review → Human Approval/merge → 实时冻结新的 exact main Base
→ 新的 v2 packet-only TASK-058 PR → 新 Human canonical assignment → Coordinator add-only Handoff
→ assigned writer 首次无改写 merge 同步 → 正式 Handoff validation
→ 五份规范变更与兼容性审查 → portable evidence/CI → 独立 Review
→ Human merge → 独立 closeout → Human 另行授权 TASK-005 重规划/激活。

准备合并后的 Base 同时用于新 packet-only PR 和独立 add-only Handoff 的 parent；
task blob 在该 Base 与 Implementation Head 相同。Packet identity 和 Handoff
filename stem 均为 `TASK-058-IMPLEMENTATION-v2`，不修改 validator 的标准拓扑。
沿用既有 `repair_context.superseded_head_sha` 字段冻结 packet-only Starting Head，
不虚构 Repair 历史。不在本任务文档中猜测未来 Base、PR number、writer 或 evidence。
新的 v2 Packet、Handoff、assignment 尚不存在；旧 v1 对象不能替代。
新 PR 明确 supersedes #119，旧 PR 的处置由 Human 决定，不能当作 TASK-058 完成。
本准备 PR 不产生正式实施环境证据，不增加任何拓扑豁免。

## Verification and expected demonstration

规范改动前后执行上述 verification.commands，使用 exact-Head 源码和兼容 Poetry
环境；先执行 `poetry build` 以实际覆盖 installed-wheel 契约，保留命令原文、
exit code、passed/failed/skipped、源码绑定和未验证范围。构建不得覆盖用户产物。
未来规范补丁的验收矩阵与原始日志可随 PR 报告，不新增仓库报告路径。
演示结果是五份规范间一致、可实现且可独立评审的边界说明；不是性能或交易验收。

三个 verification.commands 及 portable lane 必须在未来 Handoff 中逐字、逐序一致。
`poetry build` 是 wheel 前置步骤；`tests/spec tests/contract` 覆盖 market wheel，
`tests/unit/contracts` 覆盖 TASK-029 Risk wheel。全部 required tests 零失败、零 skip。

本次准备阶段还必须执行 `poetry run mypy src scripts`、`poetry run ruff check .`、
`poetry run ruff format --check .` 和 `git diff --check`，审计精确五路径、冻结对象、
唯一 active、依赖、TASK-005 blocked、源码绑定、dist 归因及两个 wheel 实际执行。
验证通过后提交、推送独立准备 PR，等待 exact-Head CI 后停止交给独立 Reviewer；
不自行 Approval/merge/closeout。
