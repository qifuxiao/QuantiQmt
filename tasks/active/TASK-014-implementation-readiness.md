---
id: TASK-014
title: Systematic implementation readiness and task queue optimization
status: active
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
  - tasks/active/TASK-014-implementation-readiness.md
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

- [ ] 形成一份系统性 Implementation Readiness Review，明确当前 spec/task 队列哪些任务可执行、哪些必须阻塞、缺少哪些契约。
- [ ] 重新评估 TASK-004、TASK-005、TASK-006、TASK-007、TASK-008、TASK-009、TASK-010 的状态、依赖、`spec_refs`、`allowed_paths`、验收标准和验证命令。
- [ ] 将表面 ready 但缺少 L4 契约的任务改为 blocked，并写明解除阻塞所需的 spec-change task。
- [ ] 为 Risk、Strategy SDK、Execution/Broker Simulator、Ledger/Portfolio、Target Resolver、Backtest/Live、Observability、Config/Control、Recovery/Reconciliation、Market Gateway 等后续 Phase 补齐或拆分可独立执行的 backlog tasks。
- [ ] 对每个新/调整后的 task 明确：目标、非目标、依赖、允许路径、禁止路径、验收标准、验证命令、Review 重点和 rollback/风险说明。
- [ ] 如发现规范缺口，创建独立 spec-change backlog task，而不是在实现任务中要求 Agent 自行发明契约。
- [ ] 更新 `spec/manifest.yaml` 的版本、兼容性、迁移、受影响任务说明；若仅新增 review/task 队列信息，也必须说明无运行时兼容影响。
- [ ] 不修改 `src/**`、`tests/**`、`migrations/**`、`.github/**` 或依赖配置。

## Required evidence

- Readiness Review 文档或规范条目，覆盖 TASK-004～TASK-010 及后续 Phase 缺口。
- 更新后的 `tasks/index.yaml` 与 backlog tasks，可解释每个 ready/blocked 状态。
- 对 TASK-004 是否可恢复实现给出明确结论；若仍 blocked，列出准确阻塞项。
- `poetry run python scripts/validate_specs.py` 通过。
- `poetry run pytest tests/spec tests/contract` 通过。

## Notes

本任务是队列治理任务，不是交易功能实现任务。它完成后，后续实现任务应能被分配给不同项目成员和 AI Agent，并通过独立 Review 判断是否符合 spec，而不是依赖架构师口头解释。
