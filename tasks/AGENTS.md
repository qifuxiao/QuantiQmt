# Task Queue Agent Instructions

- Agent 只能执行 `active/` 中指定的一个任务。
- 不得自行移动任务、改变状态、依赖、allowed_paths 或 acceptance criteria。
- backlog 仅供规划和读取；独立 Review Agent 只提供完成证据，不得授权或执行状态迁移。
- completed 只在单独记录且可核验的人类授权后写入；自动化只能机械执行该人类授权，
  不能成为替代授权者。
- 任务完成报告必须使用 `ai/workflows/implement-task.md` 的证据格式。
