---
id: TASK-055
title: Implement a fail-closed Mini QMT read-only environment probe
status: completed
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
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/92
    reviewed_head_sha: b3a17d9d2ce281232236c951b32ba698418ff6cf
    review_verdict: APPROVE
    reviewer: qifuxiao
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/92#pullrequestreview-5058394779
    merge_commit_sha: 2de733d674b4099ba8b250f57ae71a184558ffda
    review_submitted_at: '2026-08-29T14:49:38Z'
    reviewed_commit_sha: b3a17d9d2ce281232236c951b32ba698418ff6cf
    reviewer_association: OWNER
    review_api_evidence: https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/92/reviews
    merge_completed_at: '2026-08-29T14:50:12Z'
    independent_review_task: 01a04de1-6edd-7d20-a4f7-63c487de9daf
    ci_evidence: >-
      4/4 GitHub checks succeeded on the reviewed Head: two quality and two
      persistence-postgresql jobs from workflow runs 33258327588 and 33258329962.
    runtime_evidence: >-
      Windows 11, Python 3.12.10 and xtquant 250516.1.1 returned PROBE_OK for
      exact simulation-account subscription and five read-only query categories;
      38 unit tests and 2 local environment integration tests passed.
    human_authorization_evidence: >-
      2026-08-29 user explicitly authorized creating a TASK-055 closeout PR from
      latest main, recording merge/review/CI/read-only runtime evidence, without
      changing business implementation, specifications or trading permissions.
---

# Objective

实现一个 Windows/Mini QMT 的独立只读环境探针，在任何业务实现或交易副作用之前验证：
`userdata_mini`、Python/xtquant 兼容性、客户端连接、精确模拟账号订阅，以及资金、
持仓、委托、成交查询。探针只输出脱敏的能力与计数证据，不输出原始账号或持仓明细。

## Human authorization

- 2026-08-29 人类明确授权关闭 TASK-054，并创建、激活、实施 TASK-055；完成后提交
  GitHub PR。
- 授权仅限 Mini QMT 只读探针；严格禁止下单、撤单、真实资金账号和业务契约变更。
- 2026-08-29 人类明确授权基于已合并 PR #92 创建 TASK-055 closeout PR；仅允许记录
  merge/review/CI/实机只读证据并关闭生命周期，不得修改业务实现、规范或交易权限。

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

- [x] 配置矩阵覆盖安全默认值、模拟确认、account allowlist、路径、session 与 timeout。
- [x] 没有 xtquant、非 Windows、路径无效时稳定 fail-closed，模块仍可导入测试。
- [x] fake vendor 测试证明只调用连接、订阅和五类只读查询/清理，不调用交易 API。
- [x] timeout 测试证明 worker 被终止，结果不声明连接或查询成功。
- [x] 输出脱敏测试证明原始 account ID、查询对象和完整路径不会进入 JSON/日志。
- [x] 集成验证记录本机 Python/xtquant、userdata_mini、客户端连接、模拟账号订阅和
  asset/positions/orders/trades 查询结果；缺少本地配置时不得伪造通过。
- [x] 所有 verification commands 通过；规范、业务代码、migration、依赖和 CI 未变。

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

## Implementation evidence

- 2026-08-29 在 Windows 11、Python 3.12.10、xtquant 250516.1.1 与本机
  `userdata_mini` 上完成真实只读探针；结果为 `PROBE_OK`。
- 连接、精确模拟账号订阅、account status、asset、positions、orders、trades 查询均成功；
  公共结果仅记录布尔值和集合计数，positions/orders/trades 计数均为 0。
- 38 个 unit tests 与 2 个本机 integration tests 通过；mypy、ruff check、ruff format、
  `scripts/validate_specs.py` 全部通过；M1 delivery governance 5 个测试通过。
- 机器扫描与窄 facade 证明实现未调用 vendor order/cancel API；启动、连接、订阅、查询、
  cleanup、worker 创建和 deadline 失败均转换为脱敏 reason code。
- 运行限制：同一个 Mini QMT session ID 不得并发使用；stop 后立即复用可能暂时返回连接
  失败，必须等待客户端释放或由操作者配置另一个唯一正整数 session，不进行自动重试。
- 独立 Review 会话 `01a04c97-7560-78a3-8b4d-09aa0b5fa869` 对 head `f644b53` 提出
  5 个 P1 和 2 个 P2；后续修订增加精确 `STOCK`/健康状态/唯一身份校验、worker fd 输出
  隔离、仅 worker 可达的真实 factory、全程 deadline 与 terminate/kill 确认、Windows named
  mutex、部分配置 fail 和 AST vendor call allowlist；后续复审与最终结论见下方 closeout 证据。
- 对 head `105a7f6` 的首次复审确认六项修复有效，但发现 `terminate()` 异常会阻止
  `kill()` 以及同步 `process.start()` 不受 deadline 约束。后续修订将 terminate/join/kill
  分段保护，增加 daemon launch watchdog 与 worker launch gate，并让成功报告在 IPC/process
  句柄清理失败时降级；后续修订已经最终独立复审。
- 最新修订将 late-start cleanup 持有 session mutex 直至 worker 终止与资源关闭，并将非交易日
  `ACCOUNT_STATUS_CLOSED` 视为只读安全状态；其他 vendor 状态映射为脱敏 reason code。操作者在
  Mini QMT 界面恢复模拟账号连接后，2026-08-29 在实现 head `2b8cc03` 重跑真实只读探针，结果为
  `PROBE_OK`；connected/subscribed/account status/asset/positions/orders/trades 均为 true，且不输出
  账号、资产或完整路径。
- 同一环境随后执行 `tests/integration/live_qmt/test_readonly_probe_environment.py`，2 项测试通过；
  38 项 unit tests、5 项 M1 delivery governance tests、mypy、ruff check、ruff format check 与
  `scripts/validate_specs.py` 均通过。acceptance 恢复为 passed；实现交接阶段 release 始终 prohibited。
- 新独立 Review 任务 `01a04de1-6edd-7d20-a4f7-63c487de9daf` 对 head `808181a` 提出 1 个 P1
  与 1 个 P2：未确认 worker 死亡时 mutex 仍会释放，以及 launch watchdog 启动异常可能泄露
  traceback。后续修订在 worker 死亡不确定时将 mutex 隔离保留至父进程退出，并将 watchdog
  构造/启动异常转换为脱敏失败报告；新增两个失败注入测试。修订后真实只读探针再次返回
  `PROBE_OK`，2 项本机 integration tests 再次通过。

## Final Review and closeout evidence

- 独立只读 Review 任务 `01a04de1-6edd-7d20-a4f7-63c487de9daf` 对最终 head
  `b3a17d9d2ce281232236c951b32ba698418ff6cf` 给出 `APPROVED`：此前 mutex 生命周期与
  watchdog 异常边界 findings 已封闭，未发现 order/cancel/transfer/repay 副作用路径。
- 不同作者的 OWNER reviewer `qifuxiao` 于 `2026-08-29T14:49:38Z` 对同一精确 head 提交
  正式 GitHub `APPROVED` Review：
  https://github.com/qifuxiao/QuantiQmt/pull/92#pullrequestreview-5058394779
- 该 head 的 4/4 GitHub checks 全部成功：workflow runs `33258327588` 与 `33258329962`
  各包含一项 `quality` 和一项 `persistence-postgresql`。
- PR #92 于 `2026-08-29T14:50:12Z` 合并到 `main`，merge commit 为
  `2de733d674b4099ba8b250f57ae71a184558ffda`。
- closeout 只更新任务生命周期和可信证据。只读探针成功不授权模拟下单、真实资金交易、
  TASK-026 adapter、发布或 release；`release_status` 继续为 `prohibited`。

## Closeout verification

- closeout 分支基于 `origin/main@2de733d674b4099ba8b250f57ae71a184558ffda` 创建；该提交
  是 PR #92 的可信 merge commit。
- `poetry run pytest tests/unit/live_qmt/test_readonly_probe.py`：`38 passed`。
- `poetry run pytest tests/integration/live_qmt/test_readonly_probe_environment.py`：`2 passed`，
  只加载 allowlisted 本地配置且仅执行账户状态、资金、持仓、委托、成交查询。
- mypy、ruff check、ruff format check 与 `scripts/validate_specs.py` 全部通过。
- `tests/spec/test_miniqmt_m1_delivery_governance.py` 在生命周期变更前按预期为
  `1 failed, 4 passed`，变更后为 `5 passed`；active task 投影为空，TASK-053 仍为 blocked。
- closeout 未修改 `src/`、`spec/`、migration、依赖、CI、Broker 权限或运行时配置；`.env`
  未进入 Git，规范偏差为 none。
