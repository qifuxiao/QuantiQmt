# ADR-0008：Python 与基础技术栈基线

> Status: Accepted — 2026-07-02

## Context

AI Agent 开发需要冻结运行时、数据类型、持久化、消息和可选环境依赖，避免各任务独立选型。

## Decision

- CPython 3.12.x，项目声明 `>=3.12,<3.13`。
- Domain 优先使用 frozen/slots dataclass、Protocol、Enum 和 Decimal。
- JSON Schema 是跨边界 Payload 字段契约；首版序列化使用 JSON。
- PostgreSQL 使用 SQLAlchemy 2 async、asyncpg 和 Alembic。
- Redis 使用 redis-py asyncio，仅作消息/缓存/租约，不作事实来源。
- FastAPI/uvicorn、Storage、Observability 和 live-qmt 使用可选依赖组。
- xtquant 仅 Windows Live Adapter 环境安装，核心测试与回测不依赖它。

## Consequences

本地与 CI 必须安装 Python 3.12；不同能力按 extras 安装。JSON 优先可审计性，性能不足时通过 Benchmark 和新 ADR 决定二进制协议。

## Approval

已通过 `spec/reviews/BASELINE-0.1-REVIEW.md` 人工批准。
