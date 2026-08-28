# QuantiQmt

企业级 Python 量化交易系统，目标是安全、稳定、可恢复、可审计，并保持回测与实盘领域语义一致。

当前首个可运行里程碑（M1）必须连接 Mini QMT 模拟资金账号，完成从行情/策略意图到
OMS、Risk、Execution、Broker 回报、PostgreSQL 恢复和审计证据的端到端闭环。
Broker Simulator 用于确定性测试，不能替代 Mini QMT M1 验收；真实资金交易保持禁止。

## 项目入口

- 架构说明：[docs/README.md](docs/README.md)
- 唯一技术契约：[spec/README.md](spec/README.md)
- Agent 任务队列：[tasks/README.md](tasks/README.md)
- AI 工作流：[ai/README.md](ai/README.md)
- Agent 持久规则：[AGENTS.md](AGENTS.md)
- 产品北极星：[docs/00-Architecture/06-Product-North-Star.md](docs/00-Architecture/06-Product-North-Star.md)
- Mini QMT M1 验收：[docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md](docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md)

## 当前状态以机器索引为准

- 规范版本与权威索引以 [spec/manifest.yaml](spec/manifest.yaml) 为准。
- 当前可执行任务以 [tasks/index.yaml](tasks/index.yaml) 与 [tasks/active/README.md](tasks/active/README.md) 为准。
- `docs/` 解释架构背景和设计理由；实现字段、接口、状态机、Workflow、错误码和消息契约以 `spec/` 为准。
- 没有进入 `tasks/active/` 的任务不代表已经授权开发；Agent 必须按 [AGENTS.md](AGENTS.md) 读取 active task、`spec_refs` 和路径边界。

本项目不是 Notebook/因子研究框架，也不是策略快速拼装框架；核心目标是长期运行的交易基础设施、风控、执行、恢复和审计能力。策略产品层可以接入，但不能绕过 OMS、Risk、Execution 或 Source of Truth。
