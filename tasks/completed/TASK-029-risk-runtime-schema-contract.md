---
id: TASK-029
title: Define deployable Risk output Schema and runtime validation contract
status: completed
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
  - scripts/validate_ai_handoff.py
  - spec/contracts/catalog.yaml
  - src/quantiqmt/risk/__init__.py
  - ai/packets/TASK-029-REVIEW-REPAIR-v3.md
  - ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml
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
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run python scripts/validate_specs.py
        - poetry run pytest tests/spec tests/contract tests/unit/contracts
        - poetry run pytest tests/unit/risk tests/property/risk
        - poetry run mypy src/quantiqmt/contracts
        - poetry run ruff check .
        - poetry run ruff format --check .
  prohibited_lanes:
    - windows_miniqmt
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: implementation
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/110
    reviewed_head_sha: e76ed9c4faacfa3d9521dfd1185f3a62b93f86ac
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/110#pullrequestreview-5133890761
    merge_commit_sha: 7681530fa835e28bb17db9ad19eb9cf61bfdcd18
    human_authorization_evidence: >-
      https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5573292852;
      qifuxiao; created_at=updated_at=2026-09-07T16:15:11Z;
      raw-body SHA-256=7a4bf1c8bf23c6126f40d1fe1d52c9bc31e14414bbad8ee01ad915432efe03b9;
      separate Human acceptance and closeout authority, not environment-producer acceptance.
    environment_evidence: >-
      https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5573098781;
      producer=task-029-environment-verification-codex-windows-1;
      role=Environment Verification Agent; author=qifuxiao;
      created_at=updated_at=2026-09-07T15:56:22Z;
      raw-body SHA-256=a3783e9851194aecb5c3503535617e01bff5da6520eafefd5e311b1eb230436a;
      portable Windows verification at reviewed_head_sha only; live validator exit 0.
    ci_evidence: >-
      4/4 exact-Head GitHub jobs completed/success at the reviewed implementation Head:
      https://github.com/qifuxiao/QuantiQmt/actions/runs/34138743216
      (quality 101795673929, persistence-postgresql 101795674081);
      https://github.com/qifuxiao/QuantiQmt/actions/runs/34138739709
      (quality 101795663753, persistence-postgresql 101795663358).
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

- [x] 所有 Risk output Schema 均有正式 Catalog ID、版本、fixture 和 validator 路由；
- [x] 安装后的 wheel/容器无需读取源码 `spec/**` 即可完成 Risk output Schema validation；
- [x] Schema 缺失、损坏、版本不匹配均产生可观测的 fail-closed 诊断，不得静默回退；
- [x] 所有 Risk output factory 与 v2 envelope 使用同一正式 Schema + semantic validator 入口；
- [x] priority、reason/error code、UUID/hash、RFC3339 UTC-Z、typed value、嵌套字段和数组边界由正式 Schema 覆盖；
- [x] contract/property tests 覆盖 checkout、wheel/main-only、缺失 Schema、版本不匹配和全部 output fixture；
- [x] `TASK-005` 只有在 TASK-029 独立 Review APPROVE 后，才恢复为可完成状态；
- [x] manifest 版本、兼容性、迁移和回滚说明同步更新。

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

- Plan version: `TASK-029-PLAN-v2`
- Planning/Repair Base: `1bc232d367261302b397556b36a6b3284f8784d7`.
- Human repair authorization:
  <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5549863721>, comment
  `5549863721`, authored by `qifuxiao`, created and last updated at
  `2026-09-05T06:06:08Z`, raw-body SHA-256
  `0efa5bb59c51c46d8fc783e9664fd75ddc67463bec65c400a4d36c8720018adb`.
- This Amendment preserves the product implementation and acceptance evidence already produced at
  exact Head `1bc232d367261302b397556b36a6b3284f8784d7`; the Risk Schema bundle, output
  factories, Runner/audit/envelope integration, and product tests MUST NOT be reimplemented.
- The evidence-gate repair covers `scripts/validate_agent_environment.py`,
  `scripts/validate_ai_handoff.py`, and their tests under the existing `tests/spec/**` allowlist.
  It addresses task/producer identity, the explicitly frozen post-implementation Handoff topology,
  and deterministic repository-relative allowed-path matching. Implementation remains gated by
  canonical assignment and the Coordinator-authored Handoff v2.
- Additional Human authorities (repository `qifuxiao/QuantiQmt`, PR `110`, author `qifuxiao`;
  issue URL <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/110>):
  - Topology authorization `5552251354`:
    <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552251354>;
    API URL <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552251354>;
    created/updated `2026-09-05T13:49:27Z`; raw-body SHA-256
    `9885937238b94640126fce8d34b66aa6ec6519ddec45d4629b0d2e60a6ad0dbd`.
  - Format correction authorization `5552436069`:
    <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552436069>;
    API URL <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552436069>;
    created/updated `2026-09-05T14:21:36Z`; raw-body SHA-256
    `d0c3f01ef30d0152cba3ec5ddb96febb0d0c74fa70175f52f12f98dbbf5bc4e6`.
  - Consolidated path repair authorization `5552503283`:
    <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552503283>;
    API URL <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552503283>;
    created/updated `2026-09-05T14:33:18Z`; raw-body SHA-256
    `757c4fab0df3c7487e7e76d0fe487cbbe25e22a8ea99c4dbbbf01904c5743e88`.
- The punctuation-free Plan-version line is a syntax-only correction. The added Catalog and Risk
  package-export paths accept only their existing changes at
  `1bc232d367261302b397556b36a6b3284f8784d7`; no further product modification is authorized.
  Product Plan, acceptance criteria, verification commands, delivery, dependencies, spec references,
  forbidden paths, and `TASK-029-PLAN-v2` identity remain unchanged.
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


## Completion evidence and acceptance mapping

Human accepted the implementation and separately authorized this mechanical closeout in
comment 5573292852. PR #110 was merged at 2026-09-07T16:12:37Z after qfxyyy's independent
Approval at 2026-09-07T16:11:58Z, bound to
`e76ed9c4faacfa3d9521dfd1185f3a62b93f86ac`. The historical activation, Plan, repair
authorities and verification records above are preserved as history; this completion projection
does not replace the original frozen active-task blob
`66b2830c3f10c45f74e04c4f0246e1f62fd51f9d`.

| Acceptance | Evidence at the reviewed implementation Head |
|---|---|
| Formal Risk output identities, versions, fixtures and routes | `tests/contract/messages/test_risk_output_runtime_contracts.py::test_each_risk_output_identity_resolves_one_formal_schema_graph`, accepted manifest/Catalog and packaged bundle |
| Installed wheel without source spec access | `tests/unit/contracts/test_risk_schema_runtime.py::test_task_029_wheel_validates_risk_graph_main_package_only_without_source`; isolated local wheel installation with --no-deps and source-free subprocess probes |
| Missing, damaged and mismatched bundles fail closed | Version/partial/digest and unresolved-reference tests in `test_risk_schema_runtime.py`; divergent canonical-path regression added during review repair |
| Shared Schema, semantic validation and freeze boundary | `tests/unit/risk/test_risk_schema_boundary.py` verifies factory/Runner/audit integration and rejection before semantics/freeze |
| Field and collection boundaries | `test_formal_audit_graph_rejects_output_boundary_mutations`, Risk contract fixtures, unit and property tests |
| Checkout and installed-package parity | Final contract/unit-contract run: 1009 passed, 0 failed, 0 skipped; Risk unit/property run: 79 passed, 0 failed, 0 skipped |
| TASK-005 gate | TASK-029 independently approved and accepted; TASK-005 remains backlog/blocked and requires separate Human activation |
| Versioning, compatibility, migration and rollback | Accepted `spec/manifest.yaml` version 0.15.0 and PORTS-RISK runtime bundle contract, unchanged by closeout |

Implementation verification used Windows, CPython 3.12.10 and Poetry 2.4.1. All six frozen
commands, the Handoff validator, wheel build and live environment validator exited 0.
The independently built wheel was 239296 bytes, SHA-256
`320918764fe832be9b54184b175ea642c83b09b0e7c45d3919f7b3b658d62a0d`.

The first contract attempt imported old editable source from the saved project and returned
1008 passed / 1 failed. The Environment Verification Agent retained that failure, set only the
process PYTHONPATH to the exact-Head worktree src, verified the imported path, and reran all six
commands successfully. This disclosure remains part of the accepted environment evidence.
No dependency installation or upgrade was used to repair the shared project environment.

The implementation evidence above validates only the reviewed implementation Head. Closeout
verification is a separate run on the closeout changes, recorded in the independent Closeout PR;
it must not be inferred from the implementation evidence. The closeout changes neither the
runtime product nor frozen Packet/Handoff v1, v2 or v3.

The installed-package tests are container-equivalent main-package probes, not native container
deployment evidence. Mini QMT, account/market queries, trading, real money and release remain
unverified and prohibited. M1 Mini QMT acceptance is not claimed.
