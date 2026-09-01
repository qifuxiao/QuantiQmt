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
  - ai/handoffs/TASK-057-REPAIR-v2.yaml
  - ai/prompts/miniqmt-m1-task.md
  - ai/schemas/agent-assignment.schema.yaml
  - ai/schemas/agent-environment-evidence.schema.yaml
  - ai/workflows/poetry-verification.md
  - ai/workflows/team-collaboration.md
  - scripts/validate_agent_environment.py
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
  - tests/spec/test_validate_agent_environment.py
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
    - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
    - poetry run mypy src scripts
    - poetry run ruff check scripts/validate_specs.py scripts/validate_agent_environment.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
    - poetry run ruff format --check scripts/validate_specs.py scripts/validate_agent_environment.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
    - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-057'], active"
    - poetry run python scripts/validate_agent_environment.py --help
    - poetry run python scripts/validate_ai_handoff.py --task tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md --handoff ai/handoffs/TASK-057-REPAIR-v2.yaml --base-ref origin/main --head HEAD
    - poetry run pytest tests/spec
    - poetry run pytest tests/contract
    - poetry run ruff check .
    - poetry run ruff format --check .
    - poetry run pre-commit run --all-files
    - git diff --check origin/main...HEAD
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run python scripts/validate_specs.py
        - poetry run pytest tests/spec/test_validate_specs.py tests/spec/test_miniqmt_m1_delivery_governance.py tests/spec/test_codex_cline_collaboration_governance.py tests/spec/test_validate_ai_handoff.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
        - poetry run mypy src scripts
        - poetry run ruff check scripts/validate_specs.py scripts/validate_agent_environment.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
        - poetry run ruff format --check scripts/validate_specs.py scripts/validate_agent_environment.py tests/spec/test_agent_execution_environment_governance.py tests/spec/test_validate_agent_environment.py
        - poetry run python -c "from scripts.validate_specs import extract_front_matter, task_files; active=sorted(str(extract_front_matter(path).get('id')) for path in task_files() if extract_front_matter(path).get('status') == 'active'); assert active == ['TASK-057'], active"
        - poetry run python scripts/validate_agent_environment.py --help
        - poetry run python scripts/validate_ai_handoff.py --task tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md --handoff ai/handoffs/TASK-057-REPAIR-v2.yaml --base-ref origin/main --head HEAD
        - poetry run pytest tests/spec
        - poetry run pytest tests/contract
        - poetry run ruff check .
        - poetry run ruff format --check .
        - poetry run pre-commit run --all-files
        - git diff --check origin/main...HEAD
    - lane: windows
      capability: windows
      minimum_records: 1
      commands:
        - poetry --version
        - poetry env info
        - poetry run python -c "import sys; print(sys.executable); print(sys.version)"
        - poetry run python -c "import yaml, jsonschema, pytest; print('deps-ok')"
  prohibited_lanes:
    - windows_miniqmt
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: partial
  review_status: changes_requested
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
- 2026-09-01 人类在 PR #100 第四轮独立 Review 未通过后批准停止局部 Addendum 循环，
  采用本 `TASK-057-PLAN-v2` 架构重置。新增授权路径仅为两个治理 schema、正式环境证据
  validator、其测试和新的 Codex-only Repair Handoff；上述禁止范围不变。
- PR #100 的 `d2633e79254fe06cc0667dc3659d1946de774982` 是 Plan v1 的待修复 Head，
  不是 Plan v2 的可信 Implementation Base，也不得继续接受基于 v1 的局部补丁。

## Codex Implementation Plan

- Plan version: `TASK-057-PLAN-v2`
- Planning Base SHA: `ec2b95b165619af671a919a9950d40adfa9bbbaf`
- Superseded Plan: `TASK-057-PLAN-v1` 及其 Implementation/Repair 增量保留为审计历史，
  但不得再作为后续实现决策的权威来源。
- Implementation Base SHA: 只由本 Amendment 合并后 Codex-authored
  `ai/handoffs/TASK-057-REPAIR-v2.yaml` 的 `expected_base_sha` 提供；任何 Agent不得从
  移动的 `origin/main`、PR #100 或 task自行推断。
- Observable outcome: 一个新 task 能明确选择 Cline/Linux 或 Codex/Windows 作为
  Implementation Agent，将 portable、Windows 和 Windows/Mini QMT 验证分配给有能力的
  Agent；所有证据绑定同一精确 Head。Codex 在沙箱访问用户 Poetry 环境受限时请求最小
  沙箱外权限并执行 task冻结的原始 `poetry` 命令，不再误判 SymbolicLink 或创建替代环境。

### Plan v2 architecture reset

- 环境证据不再由治理测试文件中的私有 helper 解释。`scripts/validate_agent_environment.py`
  是唯一正式 machine gate，两个 `ai/schemas/*.schema.yaml` 是其版本化输入契约；测试只验证
  公开 schema/validator 行为，不得再实现第二套伪 validator。
- validator 必须自行读取精确 Head 的唯一 active task和冻结的 Repair v2 Handoff，从可信
  对象取得 task id、Base、PR Base、allowed paths和 `verification.commands`。CLI 参数或
  evidence record不得提供、覆盖或缩减 expected command set。
- `verification.commands` 在本任务中作为由 active task + Codex Handoff冻结的 opaque exact
  strings。validator验证逐项精确覆盖和结果，不尝试用 POSIX parser证明任意 PowerShell
  命令安全，也不接受 evidence自报的等价命令。命令是否可执行及宿主权限仍由 task审查、
  Agent adapter、最小 sandbox授权和 Independent Review共同控制。
- required lane必须 fail-closed：空 evidence collection、空 expected command set、重复或
  混入其他 task/Base/Head/PR/branch的 record、缺命令、非零 exit、非允许 skip、能力或授权
  不足，任一情况都不能满足 lane。
- required lanes只能来自精确task的 `verification.required_lanes`，并由Repair v2 Handoff
  原样冻结。两者必须deep-equal；缺失、空列表、重复/未知lane、空commands、未覆盖或重复覆盖
  顶层 `verification.commands`、caller/evidence覆盖均失败。TASK-057精确要求 `portable` 和
  `windows`；`windows_miniqmt` 在本任务中明确prohibited，不能被环境证据提升为required或PASS。
- assignment使用按序事件而非可选快照字段推断。正式事件只有 `ASSIGN`、`STOP`、`SWITCH`；
  sequence严格递增，任何时刻最多一个 writer。切换必须由 Human GitHub evidence授权，
  前任 `STOP` Head、新任 `SWITCH` starting Head和当时 PR Head三者精确相等。
- `xtquant` 版本是 provenance，不是猜测的 semver。证据记录脱敏后的 opaque value、可信
  source（例如 package metadata或vendor API）和采集结果；source/value未知或可能包含路径、
  账号、secret时保持 unverified/BLOCKED。禁止用宽松版本正则把任意文本当版本，也禁止因
  版本格式非 semver而误拒合法 vendor release。
- Mini QMT环境 capability与外部副作用 authorization必须分开验证。本任务只能定义证据门禁，
  始终禁止连接、账号查询或委托；后续模拟委托仍需独立 active task和可核验人类授权。

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
- 每个 lane 依据正式 schema记录 task、Base、Head、PR/branch、执行角色/tool、OS、Python/
  Poetry/xtquant provenance、命令、exit code、passed/failed/skipped、RFC3339时区时间、
  脱敏状态、未验证范围和 evidence URL。
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
- `ai/schemas/agent-assignment.schema.yaml`: 冻结有序 assignment事件、Human evidence、
  单 writer和精确 stop/switch Head所需字段与枚举。
- `ai/schemas/agent-environment-evidence.schema.yaml`: 冻结 evidence envelope、环境能力、
  版本 provenance、命令结果、counts、时间、脱敏和未验证范围字段。
- `scripts/validate_agent_environment.py`: 实现正式 fail-closed gate；只从 task/Handoff读取
  可信 identity和expected commands，验证 schema、assignment状态机、lane能力/授权、
  exact Head/PR/branch身份、required-lane deep equality、完整命令分区覆盖和结果一致性。
- `tasks/templates/task-template.md`: 增加 implementation assignment、verification lanes、
  environment evidence和精确 Head失效模板，去除固定 Cline角色。
- `scripts/validate_specs.py`: 仅在 Planning Base可复现时移除导致严格 mypy失败的多余
  `type: ignore`；不得改变规范解析/校验行为。
- `tasks/completed/TASK-022-observability-control-contracts.md`: 追加 2026-09-01 勘误，保留
  原始观察并把根因重分类为 Codex sandbox访问边界，不重写历史命令结果。
- `tests/spec/test_agent_execution_environment_governance.py`: 缩减为共享文档/template一致性和
  正式 validator的高层集成测试；删除其中承担产品逻辑的私有 parser/pseudo-validator。
- `tests/spec/test_validate_agent_environment.py`: 直接测试正式 schema/validator的正反例、
  Git身份加载、空集合/空expected set、混入record、完整命令覆盖、assignment事件状态机、
  capability/authorization和version provenance。
- `tests/spec/test_miniqmt_m1_delivery_governance.py`: Activation PR 仅把旧的“无 active task”
  投影更新为“TASK-057 是唯一 active”，并锁定 index；不改变 M1 产品与交易安全断言。

### Acceptance-to-test mapping

- 工具中立角色与无固定 Cline → 扫描共享规则/template，要求 Implementation Agent字段，
  同时允许 adapter保留工具专属入口。
- 正式契约 → schema Draft校验、validator CLI/import smoke和文档只引用该正式 gate；测试文件
  不得定义同名或等价的主验证逻辑。
- 可信输入 → evidence伪造expected commands、空task命令集、task/Handoff漂移、错误Base/PR/
  branch/Head和混入record均失败。
- required lanes → task/Handoff正例，以及缺失、空列表、空lane commands、重复/未知lane、
  顶层命令遗漏或重复分配、task/Handoff漂移及caller/evidence覆盖的失败样例。
- 单写者和中途切换 → 有序 `ASSIGN/STOP/SWITCH` 正例，以及乱序、缺人类 evidence、缺
  starting Head、双writer、stop/switch/PR Head不一致的失败样例。
- portable/windows/windows_miniqmt → capability matrix正反例；Linux声称 Windows/Mini QMT
  PASS 必须失败，Linux portable全部跳过也必须失败。
- Head绑定 → 环境 evidence Head与PR Head不同、推送后复用旧证据必须失败。
- Mini QMT副作用 → 无独立 active task或无可核验人类授权的模拟委托证据必须失败；任何
  real-money授权文本必须失败。
- Poetry → 对 task冻结的 exact command set执行完整覆盖；安全参数如 `-q` 只有在task中冻结
  才能通过，子shell或其他文本也只有作为被审查的task原始命令才可执行，evidence不得改写。
  最小 escalation、重装/删环境/bundled Python/直接替代/修改依赖配置由共享治理测试锁定。
- 版本 provenance → 可信source的opaque vendor version通过；未知source、空value及敏感信息
  泄漏失败，不对 `xtquant` 值臆造semver语法。
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
- schema版本未知、task/Handoff无法从Git精确读取、required lane为空、record身份混杂、
  assignment事件不可还原或正式 validator与文档冲突时，停止并返回 `PLAN_BLOCKED`。
- task与Repair v2 Handoff的required-lane声明不完全相等，或required-lane命令不能对顶层
  `verification.commands`形成无遗漏、无重复的精确分区时，停止并返回 `PLAN_BLOCKED`。

### Implementation order

1. 独立 Review本 Plan v2 Amendment PR；由人类合并后停止使用 Plan v1继续修补 PR #100。
2. Coordinator读取 amended main，创建 add-only `ai/handoffs/TASK-057-REPAIR-v2.yaml`：
   expected Base/PR Base均为 amended main，冻结 Plan v2 task blob、完整allowed paths，并在
   `repair_context.superseded_head_sha`记录 `d2633e79254fe06cc0667dc3659d1946de774982`；
   Handoff还必须原样冻结task的非空`verification.required_lanes`和`prohibited_lanes`。
3. 人类通过GitHub evidence分配一个 Implementation Agent，并明确授权把 Repair v2 Handoff
   lineage以普通、可审计的同步merge引入 PR #100；禁止rebase、force-push或并发writer。
4. Implementation Agent先提交正式 schema/validator失败测试，再实现最小 gate；随后调整
   共享workflow/template并删除旧治理测试中的私有pseudo-validator职责。
5. 最终PR Head必须同时包含 amended task、不可变Handoff v1/v2和授权实现；以amended main为
   PR Base，merge-base精确一致，`d2633e...` 为祖先，Repair v2 Handoff/task blob保持冻结。
6. 原样运行全部verification commands和Repair v2 path/Handoff audit；构建前保护既有dist，
   记录每条exit/skip、环境证据和CI。
7. 全新 Independent Review审查精确Head；只有人类可GitHub Approval/merge。合并后另建纯
   治理Closeout PR。

本 Amendment PR 自身只修改 active task，不会提前创建上述新文件；因此本 PR 的验证范围是
`validate_specs.py`、active/index一致性、现有治理投影、Ruff/format和精确changed-path audit。
只有 Amendment 合并并冻结 Repair v2 Handoff后，才执行本 task front matter列出的完整命令。

### PLAN_BLOCKED conditions

- 需要修改 forbidden path、`spec/`、业务代码、依赖、CI或真实资金权限。
- 现有 Handoff validator无法验证 amended-main → add-only Repair v2 Handoff → PR #100同步merge
  拓扑，或需要修改禁止路径 `scripts/validate_ai_handoff.py`。
- 无法从active task和Repair v2 Handoff取得唯一可信expected command set，或实现要求接受
  caller/evidence提供的预期命令。
- 需要构建通用PowerShell/POSIX shell安全解析器、执行未冻结命令或新增依赖。
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
- 不构建通用shell parser、不证明任意PowerShell/POSIX文本安全、不把有限关键词黑名单当
  安全边界；本任务采用冻结task exact command set和宿主最小权限边界。
- 不在本任务把全仓task命令迁移为structured argv。若以后需要argv-native执行格式，应以
  独立治理task、兼容迁移和schema版本升级完成。

## Deliverables

- 工具中立的Agent角色、分配和切换协议。
- portable、Windows、Windows/Mini QMT验证lane与标准证据格式。
- Codex/Poetry sandbox、worktree和build验证workflow。
- Cline/Linux与Codex/Windows能力边界adapter。
- 支持环境lane的task和Mini QMT Prompt模板。
- TASK-022追加式环境根因勘误。
- 两个版本化治理schema、一个正式环境证据validator及其独立正反测试。
- 可执行的治理正反测试和全仓Poetry验证证据；旧测试文件不再承担隐藏validator职责。

## Acceptance criteria

- [ ] 共享规则使用 Implementation Agent而非把实现角色绑定到Cline；adapter仍可保留工具名。
- [ ] Agent分配/切换记录tool、OS、starting Head、人类evidence和单写者停止点。
- [ ] Assignment采用有序事件模型；乱序、双writer或stop/switch/PR Head不一致时fail-closed。
- [ ] portable、windows、windows_miniqmt lane职责、能力和required/pending/BLOCKED语义明确。
- [ ] Linux Cline执行全部可移植验证，但不能执行或声称Windows/Mini QMT验收。
- [ ] Windows环境证据绑定精确Head；Head变化使旧证据和Review失效。
- [ ] 模拟委托需要独立active task和人类明确授权；真实资金始终禁止。
- [ ] Codex adapter要求最小沙箱外Poetry权限、原始命令和worktree环境兼容检查。
- [ ] SymbolicLink零长度或sandbox拒绝不能被当作Poetry损坏、依赖缺失或重装理由。
- [ ] build/contract流程保护既有dist，只清理本轮可归因产物，最终contract为0 skipped。
- [ ] TASK-022保留历史并追加可审计勘误，当前结论明确为sandbox访问边界。
- [ ] task template、Mini QMT Prompt、协作workflow和Implementation Report字段一致。
- [ ] 正式schema和`validate_agent_environment.py`是唯一machine gate；测试不复制主逻辑。
- [ ] validator只从精确task/Handoff读取identity和expected commands，拒绝caller/evidence覆盖。
- [ ] task以结构化非空声明要求`portable`和`windows`，并禁止`windows_miniqmt`；Repair v2
  Handoff必须原样冻结且validator必须deep-equal交叉校验。
- [ ] required lane在缺失/空声明、空records、空expected commands、重复或未知lane、混入
  identity、命令分区遗漏/重复、缺命令或结果不一致时失败，caller/evidence不得覆盖。
- [ ] command evidence精确覆盖冻结task命令；不依赖POSIX parser解释PowerShell，也不过拟合
  当前pytest/mypy参数。
- [ ] `xtquant`使用可信source + opaque value provenance；未知或敏感值失败，不猜测semver。
- [ ] 全部治理正反测试、task verification、mypy、Ruff、pre-commit和path audit通过。
- [ ] 未修改spec、业务代码、migration、依赖、CI、`.clinerules`或其他任务范围。

## Required evidence

- Handoff/assignment：Plan v2、Planning Base、Repair v2 Handoff commit/blob、expected Base、
  superseded Head、按序assignment events、tool/OS、Starting/STOP/SWITCH Head、人类assignment
  URL、GitHub PR Base/Head和完整path audit。
- Validator：两个schema的版本/路径、validator CLI和导入结果、可信task/Handoff解析、空集合、
  required-lane task/Handoff deep equality、identity混入、命令精确分区覆盖、assignment状态机
  及version provenance正反测试。
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
- Plan v1的反复局部修复已经证明私有helper边界不稳定；Plan v2通过缩小可信输入和建立正式
  gate控制风险。若正式schema仍不完整，应返回PLAN_BLOCKED并修订Plan，不继续追加黑名单。
- 回滚只恢复本任务治理文件和追加勘误；不删除历史证据、不修改业务状态或外部环境。
