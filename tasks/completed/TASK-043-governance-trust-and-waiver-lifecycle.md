---
id: TASK-043
title: Restore governance trust and waiver lifecycle
status: completed
depends_on: []
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/active/README.md
  - tasks/active/TASK-043-governance-trust-and-waiver-lifecycle.md
  - tasks/completed/TASK-043-governance-trust-and-waiver-lifecycle.md
  - tasks/backlog/TASK-005-risk-engine.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/completed/TASK-014-implementation-readiness.md
  - tasks/completed/TASK-015-risk-contracts.md
  - tasks/completed/TASK-030-risk-validator-integration-scope.md
  - tasks/governance-waivers.yaml
  - tasks/index.yaml
  - scripts/validate_specs.py
  - tests/spec/test_validate_specs.py
  - ai/governance/**
forbidden_paths:
  - src/**
  - spec/**
  - docs/**
  - migrations/**
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec
    - poetry run mypy src scripts
    - poetry run ruff check scripts tests/spec
    - poetry run ruff format --check scripts tests/spec
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_review_gate
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/52
    reviewed_head_sha: 1cb427cc6c1fed66a2808387471995d108bed305
    review_verdict: APPROVE
    reviewer: qifuxiao
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/52#pullrequestreview-4871949281
    merge_commit_sha: 2e4ff814e8e67d5850dc1ab5f0e51622d6dfc8c4
    human_authorization_evidence: 2026-08-06 human authorization to add the completed TASK-043 path and execute final closeout
---

# Objective

Restore a machine-verifiable governance baseline so historical delivery evidence, dependency activation, and expiring bootstrap waivers cannot silently diverge again.

## Non-goals

- 不实现 Risk、Strategy、Persistence、Execution、Broker 或任何业务运行时代码。
- 不修改 `spec/**`、公开 Event/Command/DTO、错误码、状态机、Workflow 或数据库 migration。
- 不把无法独立证明的历史 Review、CI、merge 或 release 事实改写为已验证事实。
- 不激活 TASK-005、TASK-029 或其他业务任务。

## Deliverables

- 明确 bootstrap waiver 的 active、retired、expired 生命周期；到期或治理任务完成后，规范校验仍能 fail-closed 且不会留下永久例外。
- 统一 `ready`、`blocked` 与实际 dependency unlockable 的机器语义；不可激活任务不得仅因文本标记为 ready。
- 对 TASK-014、TASK-015、TASK-030 的历史交付证据进行可追溯核验；无法证明的事实保持 `reported_unverified`，不得补造批准。
- 扩展 `validate_specs.py` 及 `tests/spec/test_validate_specs.py` 的真实 `validate_tasks()` 集成覆盖。
- 同步 `ai/governance/**`、任务索引和 active projection，记录责任人、到期日、remediation 与剩余阻断。

## Acceptance criteria

- [x] waiver 在有效期内、到期后、退休后和重复登记时均有明确且机器可验证的结果；不会因历史 bootstrap 例外导致规范门禁永久失败或允许业务解锁。
- [x] `ready` 任务的依赖可信度有明确语义；任何 `reported_unverified` 或缺失 delivery 的依赖都不能激活下游任务。
- [x] TASK-014、TASK-015、TASK-030 的 evidence 只接受可追溯 PR/head/review/merge/human authorization；未知事实仍写作 `unverifiable`。
- [x] 负例通过真实 `validate_tasks()` 路径覆盖：过期 waiver、重复 waiver、错误 beneficiary、缺失 evidence、reported_unverified 依赖和伪 ready 任务。
- [x] TASK-005、TASK-029 仍保持 blocked；本任务不解锁、不发布任何业务能力。
- [x] 所有 verification.commands 通过，且 allowed/forbidden path 审计无越权。

## Required evidence

- 记录 waiver 生命周期决策、历史证据核验结果、任务状态迁移、精确 Base/Head、Review 与 CI 证据。
- 每条 acceptance criterion 提供命令、fixture 或 GitHub 事实；不得用测试全绿替代历史 Review 证据。

## Governance evidence

- TASK-031 completed on main, so its one-time TASK-014 bootstrap exception is retired on 2026-08-05. Retired and expired records remain auditable but cannot unlock dependencies or release capability.
- `ready` is a backlog candidate label only. Actual activation requires every dependency to have trusted completed delivery; neither `ready` nor `blocked` bypasses that machine gate.
- TASK-014, TASK-015, and TASK-030 PR/head/merge facts were reconstructed from local Git objects on 2026-08-06. GitHub Review/CI queries could not be authenticated or reached, so unknown Review, CI, and human-authorization facts remain `reported_unverified` / `unverifiable` and release remains prohibited.
- TASK-005 and TASK-029 remain blocked. This task authorizes no business activation or release.
- Implementation was delivered by [PR #50](https://github.com/qifuxiao/QuantiQmt/pull/50) at head `b0c93bd44934b59a6b4febff0117266d85ccffb5` and merged as `a58f1cf64b680d612e96cec0b683b926a7beb6d5`; the merge parentage is reproducible from `origin/main`.
- PR #50 completed 4/4 CI checks. The implementation's local gates passed: specification validation; 32 spec tests; 191 contract tests; mypy over `src scripts`; Ruff check and format check over `scripts tests/spec`; and `git diff --check`.
- An independent Review session reached final verdict APPROVE, but it could not publish a formal GitHub Review and PR #50's GitHub reviews list is empty. This session result is not substituted for auditable GitHub Review evidence: `review_status` remains `pending`, no `completion_evidence` is added, release remains prohibited, and TASK-043 remains active pending third-party Review evidence.

## Closeout Review Gate

- Post-merge evidence sync [PR #51](https://github.com/qifuxiao/QuantiQmt/pull/51), head `26882647f523a345eed86adfde3d93445c990a1d`, merged as `da377c9e910676d5c04b55fd053396c7cc7be7c2` with 4/4 CI checks successful.
- The qifuxiao Review on PR #51 has GitHub state `COMMENTED`, not `APPROVED`. Its comment text must not be treated as formal approval or completion evidence.
- Closeout Review Gate PR #52 obtained an independent, auditable GitHub `APPROVED` Review from qifuxiao on exact head `1cb427cc6c1fed66a2808387471995d108bed305`, then merged as `2e4ff814e8e67d5850dc1ab5f0e51622d6dfc8c4`.
- Human authorization for this final closeout adds the exact completed TASK-043 path to `allowed_paths`; TASK-043 is now `completed` with `implementation_status: merged`, `acceptance_status: passed`, `review_status: approved`, and `release_status: prohibited`.
- TASK-005 and TASK-029 remain blocked. This final closeout uses only the formally approved evidence above; it does not add inferred or fabricated evidence, activate a business task, or authorize release.

## Final acceptance evidence

- Waiver lifecycle: `tests/spec/test_validate_specs.py` exercises active, expired, retired, duplicate, wrong-beneficiary, completed-remediation, and non-business-unlock behavior through the governance validator; the retired registry remains unchanged and release-prohibited.
- Dependency trust: real `validate_tasks()` fixtures reject missing or `reported_unverified` delivery and prove a textual `ready` state cannot unlock an active dependent.
- Historical evidence: TASK-014, TASK-015, and TASK-030 retain only Git-verifiable PR/head/merge facts; unavailable Review, CI, or authorization remains `unverifiable` and cannot unlock dependencies.
- Verification: specification validation, 32 spec tests, mypy, Ruff check, Ruff format check, and diff/path audits passed for the implementation and are rerun for this final closeout.
- Isolation: TASK-005 and TASK-029 remain blocked with zero task-body diff; no business capability is activated or released, and `release_status` remains `prohibited`.
- Review and authorization: PR #52 has formal `APPROVED` evidence at the exact reviewed head and was merged; a human explicitly authorized the completed path addition and final active-to-completed transition.

## Risks and rollback

- 若 waiver 生命周期或历史证据无法安全解释，保持所有业务任务 blocked，不能延长例外或绕过依赖门禁。
- 回滚只恢复治理元数据和验证器行为，不得改变业务代码、公开契约或持久化数据。
