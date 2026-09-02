# Codex Adapter

Codex 从仓库根 `AGENTS.md` 开始，并遵守目标子目录中更近的 `AGENTS.md`。任务 Prompt 只需指定 `tasks/active/TASK-XXX.md`，不要复制 spec。可复用流程使用 `ai/workflows/`；项目设置如需增加，应放 `.codex/config.toml`，不能承载业务契约。

Codex 是 tool/adapter，不自动等于角色。会话必须声明并只承担人类通过 GitHub evidence 分配的
Coordinator、Implementation Agent、Environment Verification Agent 或 Independent Review
Agent 之一；Human 的 activation、外部副作用授权、GitHub Approval/merge 和 closeout 权限
不能委托给 Agent 自行推断。

## Implementation / environment mode

- 作为 Implementation Agent 时，先验证 single-writer assignment、OS、精确 Starting Head、
  Handoff、Base、allowed/forbidden paths 和 clean worktree，并运行环境支持的全部 `portable`
  命令。任一缺失即 `PLAN_BLOCKED`。
- 作为 Environment Verification Agent 时，只报告当前宿主实际拥有的能力。Windows evidence
  必须来自 Windows；没有可用 Mini QMT、task-approved `xtquant`、session 或模拟账号 allowlist
  时不得声称 `windows_miniqmt` 通过，也不得连接客户端或产生委托。
- environment evidence 绑定 exact Head；Head 改变后必须重跑。Implementation Agent 不得
  Review 自己的提交，Environment Verification Agent 不提供 Review verdict。
- ordered assignment 和 environment evidence 分别遵循
  `ai/schemas/agent-assignment.schema.yaml` 与
  `ai/schemas/agent-environment-evidence.schema.yaml`；只使用正式
  `scripts/validate_agent_environment.py` gate，不在 adapter 复制验证逻辑。

## Poetry sandbox and worktree

遵循 `ai/workflows/poetry-verification.md`。必须执行 task 的原始 Poetry 命令；sandbox 无法访问
现有项目环境时只申请 `['poetry', 'run']`，构建时只申请 `['poetry', 'build']`。不得请求任意
Python/shell 权限，不得使用 bundled Python 或直接 pytest/Ruff/mypy 替代，不得 reinstall、
删除或创建第二套环境。

独立 worktree 复用环境前核对 Python、`pyproject.toml` 和 `poetry.lock`；构建前后保护既有
`dist/` 并只处理本轮可归因产物。报告必须区分 sandbox access boundary 与真实命令结果。
