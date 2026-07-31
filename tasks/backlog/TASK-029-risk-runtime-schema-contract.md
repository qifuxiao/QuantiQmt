---
id: TASK-029
title: Define deployable Risk output Schema and runtime validation contract
status: blocked
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
  acceptance_status: unverified
  review_status: reported_unverified
  release_status: prohibited
  remediation_task: TASK-031
  completion_evidence:
    mode: historical_evidence_unverifiable
    change_pr: unverifiable
    reviewed_head_sha: unverifiable
    review_verdict: reported_unverified
    reviewer: unverifiable
    evidence_url: unverifiable
    merge_commit_sha: unverifiable
    human_authorization_evidence: governance recovery authorization recorded in TASK-031
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
