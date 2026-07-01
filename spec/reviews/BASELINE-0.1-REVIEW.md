# Spec Baseline 0.1 Review

> Status: Approved

## 必须确认的决策

- [x] 生产 Python 固定为 CPython 3.12.x。
- [x] Domain 使用 frozen/slots dataclass 和 Decimal；边界契约使用 JSON Schema。
- [x] 首版内部序列化使用 JSON，性能不足须用数据和 ADR 驱动替换。
- [x] PostgreSQL Adapter 使用 SQLAlchemy 2 async + asyncpg，迁移使用 Alembic。
- [x] Redis Adapter 使用 redis-py asyncio；Redis 不作为业务权威来源。
- [x] MiniQMT/xtquant 仅 Windows live-qmt 可选依赖，核心 CI 不依赖 QMT。
- [x] 交易链路为 OrderIntent→OMS 注册→Risk→OMS 迁移→Execution。
- [x] At-Least-Once + Inbox/Outbox + 幂等 + 对账，而非端到端 Exactly Once。
- [x] Shared Kernel 值对象规则可作为 TASK-001 的实施契约。
- [x] 初始性能工作负载和 P99 是工程目标，需基准测试后正式承诺。

## 规范完整性

- [x] INV-TRADING/CONSISTENCY/RISK 已审查。
- [x] Order/Strategy/System/Connection/Account/Portfolio/Reconciliation 状态机已审查。
- [x] Submit/Cancel/Trade/Recovery/Reconnect/Config Workflow 已审查。
- [x] Source of Truth 已审查。
- [x] `planned` 消息在相关实现任务激活前必须补齐 Schema。

## 批准

```text
Reviewer: Project Owner
Role: Architecture Approver
Decision: APPROVE
Date: 2026-07-02
Notes: Approved explicitly in the Codex project thread. Planned messages still require TASK-011 before implementation.
```

Baseline accepted. The Git tag `spec-v0.1.0` is created only after the reviewed changes are committed and merged.
