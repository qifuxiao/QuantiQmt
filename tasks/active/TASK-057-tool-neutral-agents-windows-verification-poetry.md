---
id: TASK-057
title: Generalize implementation agents and environment verification lanes
status: active
depends_on: [TASK-055, TASK-056]
spec_refs: []
allowed_paths:
  - AGENTS.md
  - ai/adapters/codex.md
  - ai/adapters/cline.md
  - ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml
  - ai/prompts/miniqmt-m1-task.md
  - ai/workflows/poetry-verification.md
  - ai/workflows/team-collaboration.md
  - scripts/validate_specs.py
  - tasks/templates/task-template.md
  - tasks/completed/TASK-022-observability-control-contracts.md
  - tasks/backlog/TASK-057-tool-neutral-agents-windows-verification-poetry.md
  - tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md
  - tasks/completed/TASK-057-tool-neutral-agents-windows-verification-poetry.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - tests/spec/test_miniqmt_m1_delivery_governance.py
  - tests/spec/test_agent_execution_environment_governance.py
forbidden_paths:
  - spec/**
  - src/**
  - migrations/**
  - pyproject.toml
  - poetry.lock
  - poetry.toml
  - .github/**
  - .clinerules/**
  - scripts/validate_ai_handoff.py
  - tests/unit/**
  - tests/property/**
  - tests/contract/**
  - tests/integration/**
  - tests/spec/test_validate_ai_handoff.py
  - tests/spec/test_codex_cline_collaboration_governance.py
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
  - tasks/backlog/TASK-052-task-004-delivery-revalidation.md
  - tasks/backlog/TASK-053-dependency-sequencing-governance.md
verification:
  commands:
    - poetry --version
    - poetry env info
    - poetry run python -c "import sys; print(sys.executable); print(sys.version)"
    - poetry run python -c "import yaml, jsonschema, pytest; print('deps-ok')"
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py tests/spec/test_agent_execution_environment_governance.py
    - poetry run mypy src scripts
    - poetry run ruff check scripts/validate_specs.py tests/spec/test_agent_execution_environment_governance.py
    - poetry run ruff format --check scripts/validate_specs.py tests/spec/test_agent_execution_environment_governance.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-057'], active"
    - poetry run python scripts/validate_ai_handoff.py --task tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md --handoff ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml --base-ref origin/main --head HEAD
    - poetry run pytest tests/spec
    - poetry run pytest tests/contract
    - poetry run ruff check .
    - poetry run ruff format --check .
    - poetry run pre-commit run --all-files
    - git diff --check origin/main...HEAD
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

建立工具中立的 Implementation Agent 与基于能力的验证 lane，使 Cline/Linux、Codex/Windows
或后续其他 Agent 能在相同 GitHub/Handoff 权威链下被明确分配；同时把 Windows/Mini QMT
实机证据和 Codex/Poetry 沙箱外执行规则固化为可测试的项目治理，杜绝 Linux 结果冒充
Windows 验收、环境访问失败冒充 Poetry 损坏，以及代码 Head 与环境证据错位。

## Human authorization

- 2026-09-01 人类明确批准创建并激活 TASK-057，范围为 tool-neutral implementation
  agents、Windows/Mini QMT verification lanes 和 Codex Poetry environment governance。
- 授权覆盖本任务 `allowed_paths` 中的共享规则、Codex/Cline adapter、协作与 Poetry
  workflow、Mini QMT Prompt、task template、治理测试、`validate_specs.py` 的可复现 mypy
  修复，以及 TASK-022 的追加式环境勘误。
- `ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml` 是现行 TASK-056 协议要求的 Codex-only
  生命周期交接物；本 Activation PR 只声明路径，不创建 Record。Record 必须在 Activation
  合并后基于新的精确 main 单文件创建。
- 本授权不允许修改 `spec/`、业务代码、migration、依赖、CI、`.clinerules/`、真实资金权限，
  也不允许连接 Mini QMT、查询账号或发送任何委托。环境和模拟委托规则仅作为后续 task
  的授权门槛，不是本任务的交易授权。

## Codex Implementation Plan

- Plan version: `TASK-057-PLAN-v1`
- Planning Base SHA: `7d77d87afacae327bc29ba6e2ecfc6b3d72318d1`
- Implementation Base SHA: 只由 Activation 合并后 Codex-authored
  `ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml` 的 `expected_base_sha` 提供；任何 Agent
  不得从移动的 `origin/main` 或 task 自行推断。
- Observable outcome: 一个新 task 能明确选择 Cline/Linux 或 Codex/Windows 作为
  Implementation Agent，将 portable、Windows 和 Windows/Mini QMT 验证分配给有能力的
  Agent；所有证据绑定同一精确 Head。Codex 在沙箱访问用户 Poetry 环境受限时请求最小
  沙箱外权限并执行原始 `poetry` 命令，不再误判 SymbolicLink 或创建替代环境。

### Authority and role design

- 共享角色使用工具中立名称：Coordinator、Implementation Agent、Environment Verification
  Agent、Independent Review Agent 和 Human。Cline、Codex 只是 adapter/tool，不等于角色。
- 每个 Implementation PR 同一时刻只有一个 Implementation Agent。中途切换必须由人类在
  GitHub 记录 tool、OS、精确 starting Head、前后 Agent 和授权范围；旧 Agent 从该 Head
  停止写入，禁止并发修改同一分支。
- Implementation Agent 不得 Review 自己的提交。Environment Verification Agent 只产生
  环境证据，不产生 Review verdict。独立 Review 必须来自未参与该 Head 实现的会话。
- 人类继续独占 task activation、外部副作用授权、GitHub Approval/merge 和 closeout。

### Verification lane design

- `portable`: Linux 或 Windows；静态检查、spec、unit/contract、Broker Simulator 和不导入
  vendor runtime 的测试。Implementation Agent 必须执行其环境支持的全部 portable 命令。
- `windows`: Windows-only compatibility/integration 证据。Linux结果不能满足该 lane。
- `windows_miniqmt`: Windows、已安装 Mini QMT、task-approved `xtquant`、`userdata_mini`、
  唯一 session 和精确模拟账号 allowlist。默认只读；任何模拟委托必须由独立 active task
  和人类再次明确授权。真实资金始终禁止。
- 每个 lane 记录 task、Base、Head、执行角色/tool、OS、Python/Poetry/xtquant版本、命令、
  exit code、passed/failed/skipped、时间、脱敏证据、未验证范围和 evidence URL。
- Head 改变后该 Head 的所有环境证据和 Review verdict 自动失效。缺少 task-required lane
  时只能 `BLOCKED`，不得以 Broker Simulator、Linux mock 或文字说明替代。

### Poetry and worktree design

- 项目规定的 `poetry run`/`poetry build` 命令必须原样执行，不得用 bundled Python、直接
  pytest/Ruff/mypy 或第二套环境替代。
- Codex sandbox 无法访问用户目录时，Codex adapter 要求使用最小沙箱外权限：
  `poetry run` 使用前缀 `['poetry', 'run']`，构建使用 `['poetry', 'build']`；不得申请任意
  Python 或任意 shell 权限。Git规则只能要求申请，不能替代宿主侧人类授权。
- 先执行 `poetry --version`、`poetry env info`、项目 Python/依赖导入检查。Windows
  SymbolicLink 的零长度元数据不是损坏证据；禁止仅凭 sandbox access denied、文件关联错误
  或零长度元数据重装 Poetry、删除环境或声称依赖缺失。
- 独立 worktree 先从保存项目目录发现 dependency-complete 环境并核对 Python和 lock兼容性；
  不自动创建/安装空环境。分支的 `pyproject.toml`/`poetry.lock` 不兼容时 `PLAN_BLOCKED`。
- wheel验证前记录 `dist/` 是否已有用户文件。只有 task要求构建或 contract因缺 wheel而skip
  时运行 `poetry build`；仅清理可证明由本轮生成的 ignored产物，禁止删除用户既有文件。
- 最终报告必须把 sandbox访问失败与获批沙箱外命令的真实结果分开，不得继续使用“Poetry
  launcher损坏”等已被新证据推翻的当前环境结论。

### File-level change plan

- `AGENTS.md`: 使用工具中立角色，并加入环境能力、lane证据和不冒充验证的持久规则。
- `ai/workflows/team-collaboration.md`: 定义 Agent分配/切换、Environment Verification阶段、
  精确 Head证据失效和五角色边界。
- `ai/adapters/cline.md`: 声明 Linux Cline仍须运行 portable测试，但不得声明 Windows或
  Mini QMT验收；Windows Cline仅按实际能力报告。
- `ai/adapters/codex.md`: 增加 Implementation/Windows Verification模式和最小 Poetry
  sandbox escalation/worktree规则，不复制业务契约。
- `ai/workflows/poetry-verification.md`: 提供环境发现、沙箱外执行、worktree复用、原始命令、
  build/contract复验、产物保护及标准证据报告的工具流程。
- `ai/prompts/miniqmt-m1-task.md`: 将 portable实现与 Windows/Mini QMT验证分开，明确缺少
  Windows证据时不得声称 M1验收。
- `tasks/templates/task-template.md`: 增加 implementation assignment、verification lanes、
  environment evidence和精确 Head失效模板，去除固定 Cline角色。
- `scripts/validate_specs.py`: 仅在 Planning Base可复现时移除导致严格 mypy失败的多余
  `type: ignore`；不得改变规范解析/校验行为。
- `tasks/completed/TASK-022-observability-control-contracts.md`: 追加 2026-09-01 勘误，保留
  原始观察并把根因重分类为 Codex sandbox访问边界，不重写历史命令结果。
- `tests/spec/test_agent_execution_environment_governance.py`: 用正反例锁定工具中立角色、
  单写者切换、lane能力、Head失效、human-only副作用、Poetry原命令、sandbox/worktree/
  SymbolicLink和历史勘误；禁止仅用有限关键词黑名单制造假阳性。
- `tests/spec/test_miniqmt_m1_delivery_governance.py`: Activation PR 仅把旧的“无 active task”
  投影更新为“TASK-057 是唯一 active”，并锁定 index；不改变 M1 产品与交易安全断言。

### Acceptance-to-test mapping

- 工具中立角色与无固定 Cline → 扫描共享规则/template，要求 Implementation Agent字段，
  同时允许 adapter保留工具专属入口。
- 单写者和中途切换 → 构造缺人类 evidence、缺 starting Head、并发写入的失败样例。
- portable/windows/windows_miniqmt → capability matrix正反例；Linux声称 Windows/Mini QMT
  PASS 必须失败，Linux portable全部跳过也必须失败。
- Head绑定 → 环境 evidence Head与PR Head不同、推送后复用旧证据必须失败。
- Mini QMT副作用 → 无独立 active task或无可核验人类授权的模拟委托证据必须失败；任何
  real-money授权文本必须失败。
- Poetry → 强制原始命令和最小 escalation前缀；重装/删环境/bundled Python/直接 pytest
  替代/修改依赖配置等反例必须失败。
- worktree/build → 空环境自动安装、lock不兼容继续执行、删除既有dist等反例必须失败。
- TASK-022 → 必须存在追加勘误并明确新根因，不得删除原始历史证据。

### Failure, concurrency, and recovery design

- 无唯一 active task、Handoff缺失/漂移、Base/Head不等、assignment缺人类证据、两个实现
  Agent同时写同一PR、required lane无可用环境时，停止并返回 `PLAN_BLOCKED`。
- Linux Agent可交付代码和portable证据，但 required Windows lane保持pending；不得自行把
  acceptance改成可选。Windows Agent从已推送精确 Head补证据，代码变化则重新验证。
- Poetry sandbox失败先请求最小升级；升级仍失败则报告原命令/exit和访问边界，不重装、不
  改依赖。worktree环境不兼容则停止并报告 lock/pyproject差异。
- Mini QMT客户端、session、账号类型或allowlist任一不确定时fail-closed；本治理任务本身
  禁止连接客户端或产生任何Broker副作用。

### Implementation order

1. 独立 Review并由人类合并 Activation PR。
2. Codex读取新的精确main，创建只含 `ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml` 的
   Codex-only commit；expected Base/PR Base均为该main，`superseded_head_sha`同样冻结为该
   Base，表示尚无实现提交。
3. 人类通过GitHub evidence分配一个独立 Windows Codex作为本任务 Implementation Agent；
   Coordinator与后续 Reviewer不得承担该实现。
4. Implementation Agent先写失败治理测试，再最小修改共享规则/adapters/workflow/template，
   追加TASK-022勘误，并在仍可复现时修复 `validate_specs.py` mypy问题。
5. 原样运行全部 verification commands；构建前保护既有dist，记录所有exit/skip和环境证据。
6. 正常push Implementation PR，不self-approve/merge/closeout；新 Codex Review精确 Head。
7. 人类合并后另建纯治理 Closeout PR。

### PLAN_BLOCKED conditions

- 需要修改 forbidden path、`spec/`、业务代码、依赖、CI或真实资金权限。
- 现有 Handoff validator无法在不修改其代码的情况下验证 TASK-057初始Handoff拓扑。
- 无法获得独立 Windows Implementation Agent或后续独立 Reviewer。
- Poetry项目环境与当前 `pyproject.toml`/`poetry.lock` 不兼容，或必须安装/升级依赖才能验证。
- 不能保护用户既有 `dist/`，或验证要求删除/覆盖不可归因于本轮的产物。
- Windows/Mini QMT规则与更高优先级 safety/spec发生冲突。

## Non-goals

- 不实现或修改 Mini QMT adapter、业务逻辑、交易契约、CI、部署或release。
- 不连接 Mini QMT客户端、不读取账号、不下单/撤单，不提供任何真实资金授权。
- 不修改 `.clinerules/`；Cline专属规则仍引用共享权威，不被复制成第二份业务规范。
- 不重装 Poetry、不创建第二套环境、不升级依赖、不提交wheel或其他构建产物。
- 不把当前机器的用户目录绝对路径硬编码为所有开发者的项目契约。

## Deliverables

- 工具中立的Agent角色、分配和切换协议。
- portable、Windows、Windows/Mini QMT验证lane与标准证据格式。
- Codex/Poetry sandbox、worktree和build验证workflow。
- Cline/Linux与Codex/Windows能力边界adapter。
- 支持环境lane的task和Mini QMT Prompt模板。
- TASK-022追加式环境根因勘误。
- 可执行的治理正反测试和全仓Poetry验证证据。

## Acceptance criteria

- [ ] 共享规则使用 Implementation Agent而非把实现角色绑定到Cline；adapter仍可保留工具名。
- [ ] Agent分配/切换记录tool、OS、starting Head、人类evidence和单写者停止点。
- [ ] portable、windows、windows_miniqmt lane职责、能力和required/pending/BLOCKED语义明确。
- [ ] Linux Cline执行全部可移植验证，但不能执行或声称Windows/Mini QMT验收。
- [ ] Windows环境证据绑定精确Head；Head变化使旧证据和Review失效。
- [ ] 模拟委托需要独立active task和人类明确授权；真实资金始终禁止。
- [ ] Codex adapter要求最小沙箱外Poetry权限、原始命令和worktree环境兼容检查。
- [ ] SymbolicLink零长度或sandbox拒绝不能被当作Poetry损坏、依赖缺失或重装理由。
- [ ] build/contract流程保护既有dist，只清理本轮可归因产物，最终contract为0 skipped。
- [ ] TASK-022保留历史并追加可审计勘误，当前结论明确为sandbox访问边界。
- [ ] task template、Mini QMT Prompt、协作workflow和Implementation Report字段一致。
- [ ] 全部治理正反测试、task verification、mypy、Ruff、pre-commit和path audit通过。
- [ ] 未修改spec、业务代码、migration、依赖、CI、`.clinerules`或其他任务范围。

## Required evidence

- Handoff/assignment：Plan、Planning Base、Handoff commit、expected Base、tool/OS、Starting
  Head、人类assignment URL、GitHub PR Base/Head和完整path audit。
- Poetry：Poetry/Python版本、环境路径/Valid、依赖导入、每条原始命令和exit code；明确区分
  sandbox失败与沙箱外真实结果。
- Tests：pytest passed/failed/skipped、非skip治理反例、mypy、Ruff、pre-commit和contract
  0 skipped；若首次contract因缺wheel而skip，还要记录`poetry build`及复跑证据。CI与本地差异
  必须解释。
- Artifacts：构建前后dist清单、哪些文件由本轮生成、清理结果和最终clean worktree。
- Completion：独立Review精确Head/verdict/evidence URL、CI、merge commit和单独人类closeout
  授权。未知事实保持pending/prohibited。

## Risks and rollback

- 过度流程化会拖慢简单任务；只有task声明required的环境lane才阻断，不要求所有任务运行
  Mini QMT。
- 环境证据可能泄漏账号/路径；只记录版本、路径叶节点和脱敏状态，禁止凭据/完整账号入Git。
- 仓库规则不能自动授予Codex宿主权限；缺人类批准时保持BLOCKED，不绕过sandbox。
- 回滚只恢复本任务治理文件和追加勘误；不删除历史证据、不修改业务状态或外部环境。
