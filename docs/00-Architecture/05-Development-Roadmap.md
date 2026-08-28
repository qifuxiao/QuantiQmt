# Development Roadmap

> Status: Proposed  
> 每个 Phase 通过退出条件后才能进入依赖它的生产开发；可并行的仅限无依赖工作。阶段顺序不代表代码目录层级。

## M1 可运行系统优先

当前产品优先级是 [M1 Mini QMT Simulation Delivery](07-M1-MiniQMT-Simulation-Delivery.md)：
在不绕过 task dependency 和安全不变量的前提下，每个阶段优先交付能运行、能观察、能
恢复、能审计的最薄垂直切片。首个外部验收必须连接 Mini QMT 模拟账号；Broker
Simulator 是前置测试基线而不是替代品。

任务队列而非本文决定实际激活顺序。近期开发必须优先解除持久化、Risk、Execution、
Control、Mini QMT、Ledger/Reconciliation 与 Backtest 的既有依赖，并在每个实现 task
交付一个明确命令或演示证据；不继续创建与 M1 无直接解锁关系的泛化治理工作。

## Phase 0：工程基线

建立 Python/依赖锁定、CI、类型检查、测试框架、配置 schema、错误模型、Clock、ID/Money/Quantity/InstrumentSpec。退出：Shared Kernel 契约和数值/时间测试通过。

## Phase 1：消息与持久化基础

实现 Message Envelope、Command/Event DTO、PostgreSQL migration、UnitOfWork、Order Journal、Outbox/Inbox、Redis Stream Adapter。退出：重复投递、崩溃恢复和 schema 兼容契约通过。

## Phase 2：OMS Domain

实现 Order 聚合、完整状态机、幂等注册、版本控制和审计，不连接真实 Broker。退出：迁移全边、Property Test、每个持久化边界 kill 测试通过。

## Phase 3：Risk

实现不可变风险快照、规则引擎、版本化规则集和 fail-closed。退出：规则矩阵、边界、新鲜度和确定性测试通过。

## Phase 4：Execution 与 Broker Simulator

实现 Execution Port、限流、attempt、UNKNOWN 语义、fencing 和可编程 Broker Simulator。退出：拒单、部分成交、重复、乱序、超时和双 Leader 测试通过。

## Phase 5：Ledger、Portfolio 与 Reconciliation

实现 Trade 去重、双重记账、持仓投影、Snapshot、差异 Case 和修复命令。退出：账本守恒、重放 checksum、Broker 差异测试通过。

## Phase 6：Market Gateway、Strategy SDK 与 Strategy Runtime

先冻结 Strategy SDK、Context、Target 模型和 TargetResolver，再接入可控 Historical/Simulated Market，随后接 MiniQMT 行情；实现策略生命周期、checkpoint、订阅和数据质量。退出：参考 Buy and Hold 闭环、峰值背压、gap/stale、策略隔离和确定性通过。

## Phase 7：Backtest

实现 VirtualClock、Deterministic Scheduler、Historical Market、Execution Simulator、费用/滑点和指标。退出：无未来函数、相同输入 checksum 一致、与 Live Port 契约一致。

## Phase 8：MiniQMT Live Adapter

实现连接、能力矩阵、查询、下单/撤单、回调标准化、重连和完整对账。Mini QMT
模拟账号是 M1 强制验收路径，先完成 READONLY，再显式启用 SIM_TRADING；真实资金仍
禁止。退出：全部 M1 acceptance 场景通过，随后 Paper 环境连续 5 个交易日无未解释差异。

## Phase 9：Operations and Observability

实现 Control API、配置热更新、Kill Switch、结构化日志、Trace、Prometheus、Grafana、Alert 和 Runbook。安全能力不是最后才考虑；各前置 Phase 同步埋点，本阶段完成平台集成。

## Phase 10：Production Qualification

执行 Target/Stress/24h 长稳、故障注入、PITR、OMS 接管、灾备和安全评审。按 Paper → Limited Live → Production 逐级准入，不以工期跳过门禁。

## 每阶段交付物

设计/ADR、类型与接口、实现、migration、测试、benchmark、指标/告警、Runbook、已知限制和版本说明。没有恢复与故障测试的模块不算完成。
