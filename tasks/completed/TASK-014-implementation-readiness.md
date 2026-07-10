---
id: TASK-014
title: Systematic implementation readiness and task queue optimization
status: completed
depends_on: [TASK-013]
spec_refs:
  - INV-TRADING
  - INV-CONSISTENCY
  - INV-RISK
  - CONTRACT-CATALOG
  - PORTS-CORE
  - PORTS-ORDER-PERSISTENCE
  - SM-ORDER
  - WF-SUBMIT-ORDER
  - WF-ORDER-COMMIT
  - WF-RECOVERY
  - NFR-PERFORMANCE
  - NFR-RELIABILITY
  - NFR-OBSERVABILITY
allowed_paths:
  - spec/manifest.yaml
  - spec/reviews/**
  - spec/contracts/**
  - spec/interfaces/**
  - spec/workflows/**
  - spec/repositories/**
  - spec/storage/**
  - spec/state-machines/**
  - spec/nfr/**
  - tasks/completed/TASK-014-implementation-readiness.md
  - tasks/backlog/**
  - tasks/index.yaml
  - tasks/active/README.md
forbidden_paths: [src/**, tests/**, migrations/**, pyproject.toml, poetry.lock, .github/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

在恢复 TASK-004 或启动 TASK-005/TASK-008 之前，系统性审计并优化规范与任务队列，使后续实现任务达到可由多人和 Codex/Claude/Gemini/Cursor 等 AI Agent 独立执行、独立 Review、独立验收的 L4 Implementation Specification 水平。

## Non-goals

- 不编写业务代码、测试、migration 或 CI 配置。
- 不实现 TASK-004、TASK-005、TASK-008 或任何交易功能。
- 不削弱现有安全、风控、幂等、恢复、金额精度和越权依赖约束。
- 不把尚未具备 L4 规范的实现任务标记为 ready。

## Acceptance criteria

- [x] 形成一份系统性 Implementation Readiness Review，明确当前 spec/task 队列哪些任务可执行、哪些必须阻塞、缺少哪些契约。
- [x] 重新评估 TASK-004、TASK-005、TASK-006、TASK-007、TASK-008、TASK-009、TASK-010 的状态、依赖、`spec_refs`、`allowed_paths`、验收标准和验证命令。
- [x] 将表面 ready 但缺少 L4 契约的任务改为 blocked，并写明解除阻塞所需的 spec-change task。
- [x] 为 Risk、Strategy SDK、Execution/Broker Simulator、Ledger/Portfolio、Target Resolver、Backtest/Live、Observability、Config/Control、Recovery/Reconciliation、Market Gateway 等后续 Phase 补齐或拆分可独立执行的 backlog tasks。
- [x] 对每个新/调整后的 task 明确：目标、非目标、依赖、允许路径、禁止路径、验收标准、验证命令、Review 重点和 rollback/风险说明。
- [x] 如发现规范缺口，创建独立 spec-change backlog task，而不是在实现任务中要求 Agent 自行发明契约。
- [x] 更新 `spec/manifest.yaml` 的版本、兼容性、迁移、受影响任务说明；若仅新增 review/task 队列信息，也必须说明无运行时兼容影响。
- [x] 不修改 `src/**`、`tests/**`、`migrations/**`、`.github/**` 或依赖配置。

## Evidence

- Added `REVIEW-IMPLEMENTATION-READINESS-0.5`, covering TASK-004 through TASK-010 and later Phase gaps.
- Manifest updated to `0.5.0` with `no_runtime_contract_change`; no public message schema, storage schema, code, tests, migrations, dependency or CI changes.
- TASK-004 moved to `ready` because TASK-013 completed the Order persistence/outbox contracts.
- TASK-005 and TASK-008 moved to `blocked` pending Risk and Strategy Runtime L4 contract tasks.
- TASK-006 through TASK-010 dependencies, `spec_refs`, acceptance criteria, review focus and risk notes were recalibrated.
- Added TASK-015 through TASK-027 for Risk, Strategy SDK/runtime, Execution/Broker, Ledger/Portfolio/Reconciliation, TargetResolver, Market data, Backtest/Live parity, Observability/Control, MarketGateway, Backtest, MiniQMT and Reconciliation.
- Independent Review result: `APPROVE`; no P0-P3 findings.
- `poetry run python scripts/validate_specs.py`: passed.
- `poetry run pytest tests/spec tests/contract`: passed, 143 tests.
- Ruff and Mypy: passed.
- Merged to `main` as PR #21 (`96b5e59`) on 2026-07-10.
