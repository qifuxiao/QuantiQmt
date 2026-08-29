# QuantiQmt 架构文档

QuantiQmt 是面向长期生产运行的量化交易系统，不是策略研究框架。本文档集提供架构解释、设计理由和运维背景；开发、评审、测试和运维的实现契约以 `spec/`、当前 active task 和根 `AGENTS.md` 的优先级为准。若 `docs/` 与 `spec/` 冲突，先修正过期文档；只有需要改变 Accepted ADR 或规范性契约时，才通过 ADR 或 spec-change task 变更。

> AI-first 工程入口：规范性技术契约位于 [../spec/README.md](../spec/README.md)，可执行任务位于 [../tasks/README.md](../tasks/README.md)，Agent 工作流位于 [../ai/README.md](../ai/README.md)。本目录保留架构解释与设计理由；发生冲突时以 `spec/` 为准。

## 阅读顺序

1. [系统愿景](00-Architecture/00-System-Vision.md)
   - [Product North Star](00-Architecture/06-Product-North-Star.md)
   - [M1 Mini QMT Simulation Delivery](00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md)
2. [架构原则](00-Architecture/01-Architecture-Principles.md)
3. [系统架构](00-Architecture/02-System-Architecture.md)
4. [领域与分层](00-Architecture/03-Domain-And-Layers.md)
   - [Python 技术基线](00-Architecture/04-Python-Technical-Baseline.md)
   - [Development Roadmap](00-Architecture/05-Development-Roadmap.md)
5. [事件架构](10-EventDriven/Event-Architecture.md)
   - [Event Catalog](10-EventDriven/Event-Catalog.md)
   - [Event Payload Catalog](10-EventDriven/Event-Payload-Catalog.md)
   - [消息与数据契约](10-EventDriven/Message-Contracts.md)
6. [核心 API 与 Port 契约](15-Interfaces/API-Contracts.md)
7. [并发模型](20-Concurrency/Concurrency-Model.md)
   - [容量模型与性能验收](20-Concurrency/Capacity-And-Performance.md)
   - [Performance Targets](20-Concurrency/Performance-Targets.md)
8. [交易核心](30-Trading/Trading-Core.md)
   - [OMS 与风控详细规格](30-Trading/OMS-And-Risk-Specification.md)
   - [Workflow Catalog](30-Trading/Workflow-Catalog.md)
   - [State Machine Catalog](30-Trading/State-Machine-Catalog.md)
9. [策略产品层](35-Strategies/00-Strategy-Platform-Architecture.md)
   - [Strategy SDK Contract](35-Strategies/01-Strategy-SDK-Contract.md)
   - [StrategyContext](35-Strategies/02-Strategy-Context.md)
   - [Strategy Output Model](35-Strategies/03-Strategy-Output-Model.md)
   - [Target Resolver](35-Strategies/04-Target-Resolver.md)
   - [Multi-Strategy Coordination](35-Strategies/05-Multi-Strategy-Coordination.md)
   - [Strategy Lifecycle](35-Strategies/06-Strategy-Lifecycle.md)
   - [Strategy Versioning and Deployment](35-Strategies/07-Strategy-Versioning-And-Deployment.md)
   - [Strategy Admission Standard](35-Strategies/08-Strategy-Admission-Standard.md)
   - [Reference Strategies](35-Strategies/09-Reference-Strategies.md)
   - [Repository Evolution](35-Strategies/10-Repository-Evolution.md)
10. [数据一致性与恢复](40-Storage/Data-Consistency-And-Recovery.md)
   - [核心逻辑 Schema](40-Storage/Logical-Schema.md)
   - [Source of Truth Catalog](40-Storage/Source-Of-Truth.md)
   - [Recovery Specification](40-Storage/Recovery-Specification.md)
11. [实盘运行](50-LiveTrading/Live-Trading.md)
12. [回测架构](60-Backtest/Backtest-Architecture.md)
13. [可观测性](70-Observability/Observability.md)
   - [Monitoring Specification](70-Observability/Monitoring-Specification.md)
   - [Error Code Catalog](70-Observability/Error-Code-Catalog.md)
14. [部署与生产运维](80-Deployment/Production-Operations.md)
   - [Configuration Specification](80-Deployment/Configuration-Specification.md)
   - [Local Development Environment](80-Deployment/Local-Development-Environment.md)
15. [测试、故障演练与生产准入](90-Quality/Test-And-Production-Acceptance.md)
   - [Testing Standard](90-Quality/Testing-Standard.md)

## 文档状态

| 状态 | 含义 |
|---|---|
| Draft | 尚未形成约束 |
| Proposed | 等待评审 |
| Accepted | 必须遵守 |
| Superseded | 已被新文档替代 |

当前新架构文档状态为 `Proposed`。性能数字是初始工程目标，完成基准测试后才能转为 Accepted。

## 全局术语

- **交易意图（OrderIntent）**：策略表达的期望，不是订单。
- **订单（Order）**：由 OMS 创建和拥有的交易实体。
- **命令（Command）**：要求一个明确所有者执行动作，可成功或失败。
- **事件（Event）**：已经发生的不可变事实。
- **逻辑单例**：业务上只有一个写入者；不等于物理上只有一个进程。
- **权威来源（SoT）**：冲突发生时拥有最终裁决权的数据源。

## 变更规则

- 跨领域边界、交易顺序、数据权威来源、持久化语义或部署拓扑的变更必须新增 ADR。
- Mermaid 图必须保留源码，不使用外部图片作为唯一图源。
- 每个关键设计必须描述正常路径、异常路径、恢复方式和可观测信号。
- 不在架构文档中承诺未经测量的“零延迟”“Exactly Once”或“永不丢失”。

## 规范优先级

发生不一致时按以下顺序裁决：安全不变量 → 最新 Accepted ADR → `spec/` → active task → `AGENTS.md` → 本目录主题文档 → Engineering Convention → 历史示例。事件、字段、接口、流程和状态的规范性版本以 `spec/manifest.yaml` 索引为准。旧 ADR 和工程规范中的示例名称不构成可实现契约。
