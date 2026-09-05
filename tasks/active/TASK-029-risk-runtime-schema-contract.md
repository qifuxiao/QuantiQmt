---
id: TASK-029
title: Define deployable Risk output Schema and runtime validation contract
status: active
depends_on: [TASK-015, TASK-030, TASK-031]
spec_refs: [CONTRACT-RISK-DECISION-V1, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, PORTS-RISK, CONTRACT-CATALOG]
allowed_paths:
  - spec/manifest.yaml
  - spec/contracts/risk/**
  - spec/contracts/events/risk.order_evaluated.v2.schema.json
  - spec/interfaces/risk-ports.md
  - src/quantiqmt/contracts/**
  - src/quantiqmt/risk/model.py
  - src/quantiqmt/risk/audit.py
  - src/quantiqmt/risk/runner.py
  - src/quantiqmt/risk/evaluator.py
  - pyproject.toml
  - tests/spec/**
  - tests/contract/messages/**
  - tests/unit/contracts/**
  - tests/unit/risk/**
  - tests/property/risk/**
  - tasks/backlog/TASK-005-risk-engine.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/active/TASK-029-risk-runtime-schema-contract.md
  - tasks/active/TASK-005-risk-engine.md
  - tasks/active/README.md
  - tasks/index.yaml
  - ai/packets/TASK-029-IMPLEMENTATION-v1.md
  - ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml
  - tasks/completed/TASK-029-risk-runtime-schema-contract.md
  - scripts/validate_agent_environment.py
  - ai/packets/TASK-029-EVIDENCE-REPAIR-v2.md
  - ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml
forbidden_paths:
  - migrations/**
  - src/quantiqmt/order/**
  - src/quantiqmt/broker/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract tests/unit/contracts
    - poetry run pytest tests/unit/risk tests/property/risk
    - poetry run mypy src/quantiqmt/contracts
    - poetry run ruff check .
    - poetry run ruff format --check .
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

为 Risk 输出 DTO 建立可部署、可复现的正式 JSON Schema 运行时契约，使 `RuleResult`、`RiskDecisionV1`、`RiskAuditOutputV1` 及 `risk.order_evaluated.v2` 的 validated factory 在冻结对象前统一执行正式 Schema validation 和 semantic validation。

## Non-goals

- 不修改 Risk 业务规则、错误码、事件字段或状态语义；
- 不实现 TASK-005 的 Risk evaluator；
- 不把源码 checkout 路径作为生产运行时的隐含依赖；
- 不通过宽松 Schema、默认值或 fallback 放行非法 Risk 输出。

## Required decisions

- 冻结 Risk output Schema 的权威文件、版本和 Catalog 路由；
- 冻结运行时加载方式：wheel/安装包必须包含所需 Schema，或建立明确的独立 runtime contract package；
- `SchemaRegistry` 在开发 checkout、wheel、容器和只安装主包环境中的行为一致；缺失/版本不匹配必须 fail-startup 或 fail-closed；
- 明确 output DTO factory、Runner、v1 projection、v2 envelope 共用的 validator API；
- 明确 Schema validation 与 semantic validation 的顺序、错误码和不可变性边界；
- 增加兼容性、迁移、部署和回滚说明，并更新 TASK-005 的依赖与 allowed paths。

## Acceptance criteria

- [ ] 所有 Risk output Schema 均有正式 Catalog ID、版本、fixture 和 validator 路由；
- [ ] 安装后的 wheel/容器无需读取源码 `spec/**` 即可完成 Risk output Schema validation；
- [ ] Schema 缺失、损坏、版本不匹配均产生可观测的 fail-closed 诊断，不得静默回退；
- [ ] 所有 Risk output factory 与 v2 envelope 使用同一正式 Schema + semantic validator 入口；
- [ ] priority、reason/error code、UUID/hash、RFC3339 UTC-Z、typed value、嵌套字段和数组边界由正式 Schema 覆盖；
- [ ] contract/property tests 覆盖 checkout、wheel/main-only、缺失 Schema、版本不匹配和全部 output fixture；
- [ ] `TASK-005` 只有在 TASK-029 独立 Review APPROVE 后，才恢复为可完成状态；
- [ ] manifest 版本、兼容性、迁移和回滚说明同步更新。

## Review focus

- 是否真正使用正式 Schema，而不是把契约重新复制成第二套手写判断；
- wheel、容器和开发环境是否一致且不依赖当前工作目录；
- Schema/semantic validator 是否 fail-closed、可观测、可审计；
- 是否避免通过修改 Risk 业务逻辑掩盖部署契约缺失。

## Risks and rollback

- Schema 加载失败时必须保持 Risk/交易门禁关闭；
- 若无法在不改变公开契约的前提下完成部署，应保持 TASK-005 blocked，先提交新的 spec-change；
- 回滚只能回到上一份已接受的 Schema/manifest 版本，不得恢复源码路径隐式加载。

## Governance freeze evidence

- PR #46 was closed; its branch and commits must not be reused as implementation or review evidence.
- TASK-029 is moved to `backlog/blocked` pending TASK-031 governance recovery and independent Review.
- TASK-029 MUST NOT be reactivated until TASK-031 is completed and independently reviewed; this freeze does not alter TASK-029 allowed_paths or acceptance criteria.

## Human activation evidence

- Human explicitly authorized TASK-029 as the next product implementation task and limited this
  change to an activation-only PR.
- Dependency repair PR: <https://github.com/qifuxiao/QuantiQmt/pull/108>.
- Reviewed TASK-030 repair Head: `cac4534d0cf42f1acc4f44c0e9eb097908cb0901`.
- Independent APPROVE: <https://github.com/qifuxiao/QuantiQmt/pull/108#pullrequestreview-5110897820>.
- PR #108 merge commit and expected activation Base:
  `286c3901b3801fd752feaaf615167cef248a9494`; merged at `2026-09-04T08:38:24Z`.
- The activation preflight verified PR #108 as merged, the reviewed Head and Approval as exact,
  live `main` at the expected Base, a clean worktree, no active task, and trusted completed
  delivery for TASK-015, TASK-030, and TASK-031.
- This new lifecycle resets current delivery execution to `not_started/not_run/pending/prohibited`.
  It does not rewrite the historical PR #46 facts above or treat that closed work as delivery,
  implementation, Review, or completion evidence.

## Frozen Implementation Plan Amendment: TASK-029-PLAN-v2

- Plan version: `TASK-029-PLAN-v2`.
- Planning/Repair Base: `1bc232d367261302b397556b36a6b3284f8784d7`.
- Human repair authorization:
  <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5549863721>, comment
  `5549863721`, authored by `qifuxiao`, created and last updated at
  `2026-09-05T06:06:08Z`, raw-body SHA-256
  `0efa5bb59c51c46d8fc783e9664fd75ddc67463bec65c400a4d36c8720018adb`.
- This Amendment preserves the product implementation and acceptance evidence already produced at
  exact Head `1bc232d367261302b397556b36a6b3284f8784d7`; the Risk Schema bundle, output
  factories, Runner/audit/envelope integration, and product tests MUST NOT be reimplemented.
- The only current blockers are the formal environment-evidence validator's TASK-057-only identity
  gate and the evidence producer identity. This Amendment authorizes only the future validator
  repair and its tests after a new canonical assignment and Coordinator-authored Handoff v2.
- No verification command is waived. A changed exact Head invalidates prior final evidence and
  requires the unchanged six commands to be rerun before new environment evidence is accepted.
- Product outcome: deliver an installable Risk Schema bundle and loader whose behavior is the
  same in a source checkout, an installed wheel, and a container consuming that wheel. The
  installed package must validate Risk outputs without reading source `spec/**`.
- Explicit demo: build and install the wheel into an isolated environment whose working tree
  and source `spec/**` are unavailable, then validate accepted and rejected Risk output fixtures
  through the installed public contract path and show fail-closed diagnostics for a missing,
  damaged, or version-mismatched bundle.

### Tests-first implementation order

1. Add failing contract/unit/property tests before runtime changes. Cover the manifest/Catalog
   routes and packaged resources for `RuleResult`, `RiskDecisionV1`, `RiskAuditOutputV1`, and
   `risk.order_evaluated.v2`; accepted and invalid fixtures; checkout/package parity; isolated
   wheel/main-only execution; non-source working directories; and missing, damaged, partial,
   digest-mismatched, unresolved-reference, and version-mismatched bundles.
2. Make the reviewed manifest-indexed Risk Schema graph a deterministic package resource under
   `src/quantiqmt/contracts/**`. The loader must verify bundle format, manifest version, content
   digests, contract IDs, paths, Catalog routes, and all JSON Schema references before exposing
   a validator. Runtime loading must use package resources only and must never fall back to the
   repository, current working directory, caller-supplied source roots, defaults, or a looser
   hand-written schema.
3. Reuse one contracts-owned validator entry for every Risk output. Each factory must assemble a
   primitive candidate, execute `Schema validation → semantic validation → freeze`, and return a
   deeply immutable value only after both validations pass. `RuleResult` and `RiskDecisionV1`
   validate through their accepted Schema identity or the exact self-contained v2 fragment;
   `RiskAuditOutputV1` and the authoritative v2 payload validate through the same resolved graph.
4. Route Runner completion, v1 compatibility projection, and v2 envelope construction through
   that same entry. A validation failure must prevent freezing/returning an invalid output,
   projection, persistence/publication, approved OMS transition, and entry into Execution. No
   path may repair, reorder, deduplicate, coerce, default, or retry an invalid output.
5. Preserve every accepted Event field, DTO field/type, UUID/hash rule, RFC3339 UTC-Z rule,
   typed-value encoding, reason/error code, Risk rule, ordering rule, timeout rule, reduce-only
   rule, metric, and state transition. TASK-029 may add only the deployable Schema/Catalog routing,
   unified validation boundary, immutable construction integration, diagnostics, and tests needed
   by its existing acceptance criteria; it must not invent a parallel contract or Risk policy.
6. Use existing error/exception and observability contracts. Bundle absence, corruption, partial
   content, unresolved references, and version mismatch must fail startup or fail closed at the
   validation boundary with bounded, non-sensitive diagnostics; they must never silently select
   source `spec/**`, an older bundle, or permissive validation.
7. Build the wheel according to `ai/workflows/poetry-verification.md`, preserve and audit any
   pre-existing `dist/` artifacts, run the isolated installed-package demo, and require the final
   contract run to have no wheel-related skip. Then execute every `verification.commands` entry
   exactly as written and record exit codes, changed paths, acceptance evidence, and unverified
   scope against the frozen Implementation Base and exact Head.

### Deliverable and path boundaries

- Runtime deliverable: the reviewed, versioned, checksum-verified Risk Schema bundle; a
  package-resource-only loader/resolver; one shared Schema validator entry; Schema/semantic/freeze
  integration in the existing Risk factories, Runner, audit projection, and envelope path; and
  bounded fail-closed diagnostics.
- Test deliverable: checkout, wheel/main-only, container-equivalent installed-package, fixture,
  tamper/version/reference, shared-entry, immutability, and property coverage within the existing
  allowed test paths.
- Lifecycle deliverables may later use only
  `ai/packets/TASK-029-IMPLEMENTATION-v1.md`,
  `ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml`, and
  `tasks/completed/TASK-029-risk-runtime-schema-contract.md`. This activation PR creates none of
  them and performs no TASK-029 implementation.
- `TASK-005` remains `backlog/blocked`; TASK-029 completion and an exact-Head independent APPROVE
  are prerequisites to any separate Human-authorized TASK-005 activation.

### PLAN_BLOCKED conditions

- A required implementation needs any forbidden or unauthorized path, dependency/lockfile/CI
  change, Mini QMT access, account/market/order operation, or TASK-005 implementation.
- Passing requires changing an accepted Event/DTO field, error/reason code, Risk rule, ordering,
  state transition, or weakening Schema/semantic validation, immutability, or fail-closed behavior.
- The exact Implementation Base does not contain this Plan and its future Packet/Handoff, the
  canonical Human assignment is missing or inconsistent, another writer is active, or Base/Head
  identity drifts.
- The installed wheel cannot validate without source `spec/**`, any required test/verification
  command fails or remains skipped, or checkout/wheel/container-equivalent behavior differs.

## Frozen delivery sequence

`activation-only PR` → `Independent Review` → `Human merge` →
`freeze new exact Implementation Base` → `Coordinator creates Packet/Handoff` →
`Human canonical assignment` → `Implementation Agent tests-first implementation` → `CI` →
`Independent Review` → `Human merge` → `closeout` → `TASK-005`.

No later step is authorized by this activation PR. In particular, it does not authorize self-review,
Approval, merge, TASK-029 implementation, TASK-005 activation, Mini QMT access, or release.
