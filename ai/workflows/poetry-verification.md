# Workflow: Poetry Environment Verification

本流程是工具使用说明，不是第二份依赖或业务契约。Implementation Agent 与 Environment
Verification Agent 必须执行 active task 的原始命令，并把 sandbox 访问失败与项目环境的真实
结果分开报告。

## 1. Discover the existing project environment

1. 在保存项目目录运行 `poetry --version` 和 `poetry env info`，记录 Poetry/Python 版本、环境
   路径叶节点、Executable 和 `Valid`；不要记录用户名、凭据或完整账号。
2. 通过 `poetry run python -c ...` 核对项目 Python 和 task 需要的依赖导入。
3. Windows `SymbolicLink` 的元数据显示为 0 字节、sandbox `access denied`、文件关联错误或
   launcher 在受限上下文不可读，只说明当前访问边界；这些现象不能证明 Poetry 损坏、依赖
   缺失或需要 reinstall。
4. 不得重装 Poetry、运行依赖安装、删除环境、创建 second environment、修改依赖配置，或用
   bundled Python、direct pytest、direct Ruff、direct mypy 替代 task 命令。

## 2. Minimum sandbox escalation

先尝试原始命令。Codex sandbox 无法访问现有用户环境时，只申请与命令一致的最小前缀：

- `poetry run ...` → `['poetry', 'run']`
- `poetry build` → `['poetry', 'build']`

不得申请任意 Python、任意 shell 或更宽前缀。批准只允许机械执行原始命令，不改变 task、依赖
或外部副作用权限。最终 evidence 分别记录 sandbox failure 的原命令/exit code 和获批后的真实
结果；不能用后者抹去前者。

## 3. Reuse from an independent worktree

独立 worktree 不得自动创建或安装空环境；不得创建 second environment，也不得安装依赖。
复用保存项目的 existing dependency-complete 环境前，
必须比较：

- Python implementation 和 major/minor version；
- worktree 与保存项目的 `pyproject.toml` blob/checksum；
- worktree 与保存项目的 `poetry.lock` blob/checksum。

任一不兼容或无法核验时返回 `PLAN_BLOCKED`。兼容时仍以原始 `poetry run ...` / `poetry build`
入口运行；不得绕过 Poetry 直接调用环境内工具。

## 4. Build and contract verification

构建前先记录 `dist/ before` 清单（路径、大小和 checksum），标记所有 existing/user-owned
artifact。只有 task 明确要求 build，或首次 contract 测试仅因缺少本项目 wheel 而 skip 时，
才运行原始 `poetry build`。

构建后记录 `dist/ after`，计算本轮 attributable artifact。复跑原始 contract 命令并要求最终
`0 skipped`；其他失败/skip 不能通过 build 掩盖。只允许清理能够由 before/after/checksum 证明
为本轮生成且 ignored 的 artifact，绝不删除、覆盖或改名 existing 用户产物。无法归因时停止并
保持产物不动。

## 5. Evidence and finish gate

Implementation Report / environment evidence 必须包含：task、Base、exact Head、assignment、
role/tool/OS、Poetry/Python/依赖版本、环境 `Valid`、每条原始 command 和 exit code、
passed/failed/skipped、sandbox 与沙箱外结果、worktree compatibility、dist before/after、
attributable artifacts、unverified scope、风险、evidence URL 和最终 clean worktree。

Head 改变后所有 environment evidence 失效。required lane、最终 contract `0 skipped`、产物归因
或 clean worktree 任一无法满足时，保持 `BLOCKED`，不得降低 task acceptance。
