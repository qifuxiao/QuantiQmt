---
id: TASK-054
title: Re-anchor delivery on mandatory MiniQMT simulation-account M1
status: completed
depends_on: []
spec_refs:
  - INV-TRADING
  - INV-CONSISTENCY
  - INV-RISK
  - CONTRACT-BACKTEST-PARITY-V1
  - PORTS-CORE
  - PORTS-BACKTEST
  - WF-SUBMIT-ORDER
  - WF-RECOVERY
  - WF-BROKER-RECONNECT
  - WF-BACKTEST-RUN
  - NFR-RELIABILITY
  - NFR-OBSERVABILITY
allowed_paths:
  - AGENTS.md
  - README.md
  - .env.example
  - .clinerules/00-quantiqmt-project.md
  - ai/README.md
  - ai/adapters/cline.md
  - ai/prompts/miniqmt-m1-task.md
  - docs/README.md
  - docs/00-Architecture/00-System-Vision.md
  - docs/00-Architecture/05-Development-Roadmap.md
  - docs/00-Architecture/06-Product-North-Star.md
  - docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md
  - docs/50-LiveTrading/Live-Trading.md
  - docs/60-Backtest/Backtest-Architecture.md
  - docs/80-Deployment/Configuration-Specification.md
  - tasks/backlog/TASK-053-dependency-sequencing-governance.md
  - tasks/active/TASK-053-dependency-sequencing-governance.md
  - tasks/backlog/TASK-054-miniqmt-m1-delivery-governance.md
  - tasks/active/TASK-054-miniqmt-m1-delivery-governance.md
  - tasks/completed/TASK-054-miniqmt-m1-delivery-governance.md
  - tasks/active/README.md
  - tasks/index.yaml
  - tests/spec/test_miniqmt_m1_delivery_governance.py
forbidden_paths:
  - spec/**
  - src/**
  - migrations/**
  - pyproject.toml
  - poetry.lock
  - .github/**
  - tests/unit/**
  - tests/property/**
  - tests/contract/**
  - tests/integration/**
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
  - tasks/backlog/TASK-052-task-004-delivery-revalidation.md
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py
    - poetry run ruff check tests/spec/test_miniqmt_m1_delivery_governance.py
    - poetry run ruff format --check tests/spec/test_miniqmt_m1_delivery_governance.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-054'], active"
    - git diff --check origin/main...HEAD
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/91
    reviewed_head_sha: 499864b3b5ea2df7f897c6ee8bb63ceeaaee1861
    review_verdict: APPROVE
    reviewer: qifuxiao
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/91
    merge_commit_sha: 1848625eb8743ef28d08fc165e90ed442d4c31d6
    review_submitted_at: '2026-08-29T07:40:59Z'
    reviewed_commit_sha: 499864b3b5ea2df7f897c6ee8bb63ceeaaee1861
    reviewer_association: OWNER
    review_api_evidence: https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/91/reviews
    merge_completed_at: '2026-08-29T07:41:14Z'
    ci_evidence: >-
      4/4 GitHub checks succeeded on the reviewed Head: two quality and two
      persistence-postgresql jobs from workflow runs 33182966111 and 33183099511.
    human_authorization_evidence: >-
      2026-08-29 user explicitly authorized closing TASK-054 and creating,
      activating and implementing TASK-055 Mini QMT read-only environment probe.
---

# Objective

把项目交付目标重新锚定为一个可实际运行、必须连接 Mini QMT 模拟资金账号的 M1，
并给 Codex、Cline 及其他 AI Agent 提供一致、可执行的开发入口。本文档治理不得改变
任何 Accepted contract，不实施交易业务代码，也不把说明文档当作生产准入证据。

## Human authorization

- 2026-08-28 人类批准将讨论结论写入项目，并要求随后使用 Codex/Cline 尽快交付
  “企业级、可恢复、可审计、回测与实盘语义一致”的量化交易系统。
- 人类明确要求首个可运行系统必须连接已安装的 Mini QMT，并先使用其提供的模拟账号
  做回测或模拟实盘。
- 本授权精确覆盖本任务 allowed paths 中的产品目标、M1 验收、AI 规则、配置示例、
  工具适配和机器治理测试；不授权业务实现、真实资金交易、部署、release 或修改 spec。
- 为保持唯一 active task，未完成的 TASK-053 原样暂停到 backlog/blocked，不声明完成。

## Deliverables

1. 产品北极星明确“可运行系统优先”，但完整保留 OMS、Risk、Execution、恢复和审计门禁。
2. M1 明确 Mini QMT 模拟账号是强制 acceptance path；Broker Simulator 只是自动化基线。
3. 定义 BACKTEST、MINIQMT_SIM_READONLY、MINIQMT_SIM_TRADING、LIVE_PROHIBITED 模式。
4. 定义本地 `.env` 配置、账号 allowlist、默认 Kill Switch、默认禁止下单和 secret 边界。
5. 明确 Mini QMT 客户端先登录；Python adapter 使用 `userdata_mini`、session 与 account，
   不把密码写入 Git、Prompt、日志或默认 `.env` 契约。
6. 定义回测不可变历史快照与模拟实盘共享 Domain/Application/Risk/OMS/Execution 语义。
7. 提供 Codex/Cline 统一入口和可复制的单任务开发 Prompt，不复制或改写规范正文。
8. 用机器测试锁定上述项目治理要求，并验证 TASK-053 暂停、TASK-054 唯一 active。

## Acceptance criteria

- [x] 根 README、AGENTS 和架构入口一致指向 Mini QMT 模拟账号强制 M1。
- [x] M1 文档有完整成功路径、失败路径、重启恢复、审计证据和明确的非目标。
- [x] `.env.example` 不含真实 secret/password，交易默认关闭，账号必须精确 allowlist。
- [x] 回测数据通过带校验和的不可变快照进入，运行时不读取未来或实时变化数据。
- [x] Mini QMT 断连、提交超时、回调重复/乱序均沿既有 UNKNOWN/reconciliation 语义处理。
- [x] LIVE/真实资金账号保持硬禁用，不能通过把 profile 字符串改成 live 绕过。
- [x] Codex/Cline 都被要求读取根 AGENTS、spec manifest、唯一 active task 和全部 spec refs。
- [x] 没有修改 spec、业务代码、migration、依赖、CI 或现有任务的业务 scope。
- [x] 所有 verification commands 通过，变更经独立 Review 后才可 closeout。

## Implementation evidence

- 根 `AGENTS.md`、README 与架构目录写入同一个 Mini QMT simulation-account M1 北极星，
  并保留完整 OrderIntent/OMS/Risk/Execution、UNKNOWN、恢复、审计与真实资金禁用门禁。
- 新增 M1 文档，定义四种 profile、fail-closed 启动、配置/secret 边界、十个验收场景、
  目标 operator command，并明确这些命令尚未实现。
- `.env.example` 只包含模拟账号占位符，默认 `MINIQMT_SIM_READONLY`、禁止发单、Kill
  Switch 生效、空 allowlist；未新增 QMT password/secret 字段。
- Backtest/Live/Configuration/Roadmap 文档同步不可变快照、共享语义与 Mini QMT 强制 M1，
  未修改任何 normative spec、ADR、runtime、migration、dependency 或 CI。
- 新增 Cline 短入口、工具中立 adapter 与 Mini QMT M1 Prompt；Codex 继续使用根
  `AGENTS.md`，两者均指向同一 manifest/active-task/spec-ref 权威链。
- 机器测试锁定产品规则、配置默认值、backtest/live parity、AI 工具入口与唯一 active
  task；测试先观察到预期 `4 failed, 1 passed`，实现后为 `5 passed`。
- TASK-053 仅暂停为 backlog/blocked，其业务正文、acceptance、delivery 五轴和依赖均未
  被完成或豁免；TASK-054 是唯一 active task。

## Verification evidence

- `poetry run python scripts/validate_specs.py`：通过。
- `poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py`：
  `50 passed`。
- `poetry run pytest tests/spec -q`：`56 passed`。
- focused 与全仓 `poetry run ruff check`：通过。
- focused 与全仓 `poetry run ruff format --check`：通过，`78 files already formatted`。
- 唯一 active task 命令确认结果为 `TASK-054`。
- exact allowed/forbidden path audit：通过；`git diff --check`：通过。

## Unverified scope

- 本任务没有启动 Mini QMT、导入已安装 xtquant、连接模拟账号、查询或发送订单；这些
  均属于后续独立实现 task，不得从文档/测试通过推断为已交付。
- Python 3.12 与本机 Mini QMT/xtquant 的实际兼容性、券商权限、客户端路径和模拟账号
  类型仍需后续只读环境探针验证。
- 实现交接时独立 Review、GitHub CI、merge 与 closeout 尚未发生；该历史边界现由下方
  final evidence 闭合。`release_status` 始终保持 prohibited。

## Final Review and closeout evidence

- PR #91 author `qfxyyy` delivered exact Head
  `499864b3b5ea2df7f897c6ee8bb63ceeaaee1861`.
- Different-author OWNER reviewer `qifuxiao` submitted formal `APPROVED` Review
  `PRR_kwDOTKo0088AAAABLXBRDg` on that exact Head at `2026-08-29T07:40:59Z`:
  https://github.com/qifuxiao/QuantiQmt/pull/91
- The exact Head passed 4/4 GitHub checks: two `quality` and two
  `persistence-postgresql` jobs.
- PR #91 merged to `main` as `1848625eb8743ef28d08fc165e90ed442d4c31d6`
  at `2026-08-29T07:41:14Z`.
- 2026-08-29 human authorization explicitly closes TASK-054 and authorizes creating,
  activating and implementing TASK-055. Release remains prohibited; this closeout
  does not claim any Mini QMT runtime connection or trading implementation.

## Review focus

- 文档是否把“尽快可运行”误写成可绕过 OMS、Risk、持久化、UNKNOWN 或恢复屏障。
- 是否把 Mini QMT 模拟账号当作强制 M1，而不是可选的最终阶段。
- 是否泄漏或鼓励保存密码、原始账号、Token、真实 Broker 凭据。
- 回测与模拟实盘是否共享语义边界，同时保留外部延迟/断连等现实差异。
- Agent 规则是否工具中立、可执行且没有与 `spec/` 冲突或自授权新业务 task。

## Risks and rollback

- 文档治理不能让尚未实现的功能看起来已交付；所有目标命令必须标为 target interface。
- Mini QMT/xtquant 与 Python 3.12 的实际兼容性尚未验证，后续实现 task 必须先做只读探针。
- 回滚只恢复本任务文档、配置模板、Agent 适配和任务队列投影，不触及数据或交易状态。
- `release_status` 始终 prohibited；真实资金交易需要独立任务、验收和人类授权。
