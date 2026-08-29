---
id: TASK-055
title: Implement a fail-closed Mini QMT read-only environment probe
status: active
depends_on: [TASK-054]
spec_refs: [INV-TRADING, WF-BROKER-RECONNECT, WF-RECOVERY, NFR-RELIABILITY, NFR-OBSERVABILITY]
allowed_paths:
  - .env.example
  - src/quantiqmt/live/__init__.py
  - src/quantiqmt/live/qmt/__init__.py
  - src/quantiqmt/live/qmt/readonly_probe.py
  - scripts/probe_miniqmt_readonly.py
  - tests/unit/live_qmt/test_readonly_probe.py
  - tests/integration/live_qmt/test_readonly_probe_environment.py
  - tests/spec/test_miniqmt_m1_delivery_governance.py
  - tasks/active/TASK-055-miniqmt-readonly-environment-probe.md
  - tasks/backlog/TASK-055-miniqmt-readonly-environment-probe.md
  - tasks/completed/TASK-055-miniqmt-readonly-environment-probe.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
forbidden_paths:
  - spec/**
  - migrations/**
  - src/quantiqmt/order/**
  - src/quantiqmt/risk/**
  - src/quantiqmt/execution/**
  - src/quantiqmt/strategy/**
  - src/quantiqmt/simulation/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run pytest tests/unit/live_qmt/test_readonly_probe.py
    - poetry run pytest tests/integration/live_qmt/test_readonly_probe_environment.py
    - poetry run mypy src/quantiqmt/live/qmt scripts/probe_miniqmt_readonly.py
    - poetry run ruff check src/quantiqmt/live/qmt scripts/probe_miniqmt_readonly.py tests/unit/live_qmt tests/integration/live_qmt
    - poetry run ruff format --check src/quantiqmt/live/qmt scripts/probe_miniqmt_readonly.py tests/unit/live_qmt tests/integration/live_qmt
    - poetry run python scripts/validate_specs.py
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

实现一个 Windows/Mini QMT 的独立只读环境探针，在任何业务实现或交易副作用之前验证：
`userdata_mini`、Python/xtquant 兼容性、客户端连接、精确模拟账号订阅，以及资金、
持仓、委托、成交查询。探针只输出脱敏的能力与计数证据，不输出原始账号或持仓明细。

## Human authorization

- 2026-08-29 人类明确授权关闭 TASK-054，并创建、激活、实施 TASK-055；完成后提交
  GitHub PR。
- 授权仅限 Mini QMT 只读探针；严格禁止下单、撤单、真实资金账号和业务契约变更。

## Non-goals

- 不实现 TASK-026 Mini QMT MarketGateway/BrokerGateway adapter。
- 不调用任何下单、撤单、改单、还款、转账或其他 Broker 副作用 API。
- 不修改 Event、Command、DTO、错误码、状态机、Repository、Workflow 或规范 bundle。
- 不实现策略、OMS、Risk、Execution、Ledger、Portfolio、Reconciliation 或 Backtest。
- 不把只读连接成功当作 M1 或量化系统完成。
- 不保存密码，不自动登录 Mini QMT GUI，不读取真实资金账号。

## Implementation contract

- 模块导入必须在没有 xtquant 的 CI/Linux 环境安全；vendor import 只发生在已验证的
  Windows probe worker 内。
- 配置只接受 `MINIQMT_SIM_READONLY`，要求 `userdata_mini` 目录、非空模拟账号、
  精确 allowlist、`SIMULATION_ACCOUNT_CONFIRMED=true`、正整数唯一 session 和有界 timeout。
- 任何未知 profile、空/不匹配账号、未确认模拟账号、路径错误、import/连接/订阅/查询
  失败或 timeout 均 fail-closed，退出非零且不暴露账号。
- vendor facade 只暴露 start/connect/subscribe/query asset/positions/orders/trades、
  unsubscribe/stop；实现与测试必须机器证明不包含 order/cancel side-effect API 调用。
- 全探针在隔离子进程内运行；deadline 到期必须终止 worker，不能遗留无界等待。
- 公共输出只能包含安全 reason code、Python/platform/xtquant 版本、路径叶节点、连接/
  订阅/query 布尔值和集合计数；禁止账号 ID、密码、订单/成交/持仓内容。
- `.env` 只从显式 `--env-file` 加载 allowlisted keys，不执行插值/命令且不覆盖进程环境。

## Acceptance criteria

- [ ] 配置矩阵覆盖安全默认值、模拟确认、account allowlist、路径、session 与 timeout。
- [ ] 没有 xtquant、非 Windows、路径无效时稳定 fail-closed，模块仍可导入测试。
- [ ] fake vendor 测试证明只调用连接、订阅和五类只读查询/清理，不调用交易 API。
- [ ] timeout 测试证明 worker 被终止，结果不声明连接或查询成功。
- [ ] 输出脱敏测试证明原始 account ID、查询对象和完整路径不会进入 JSON/日志。
- [ ] 集成验证记录本机 Python/xtquant、userdata_mini、客户端连接、模拟账号订阅和
  asset/positions/orders/trades 查询结果；缺少本地配置时不得伪造通过。
- [ ] 所有 verification commands 通过；规范、业务代码、migration、依赖和 CI 未变。

## Expected demonstration

```powershell
poetry run python scripts/probe_miniqmt_readonly.py --env-file .env
```

成功只代表本机 Mini QMT read-only compatibility 已验证。输出不得包含账号或资产明细。

## Review focus

- 是否可通过任意路径到达 order/cancel/其他副作用 API。
- allowlist、simulation confirmation、profile、路径和 timeout 是否 fail-closed。
- subprocess timeout 是否真正终止 worker，而非泄漏后台交易线程。
- 输出、异常和测试失败是否泄露 account/path/vendor objects。
- 是否越权实现 TASK-026 或更改业务契约。

## Risks and rollback

- xtquant 与 Python 3.12/本机客户端可能不兼容；必须记录真实结果，不得升级依赖或
  修改 Python baseline 规避。
- vendor 查询 API 也可能阻塞；isolated process 是本任务的有界回滚边界。
- 回滚删除本任务新增 probe/test 文件并恢复配置模板；无数据库或 Broker 状态需回滚。
