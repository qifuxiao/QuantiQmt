# Task Queue Agent Instructions

- Agent 只能执行 `active/` 中指定的一个任务。
- 不得自行移动任务、改变状态、依赖、allowed_paths 或 acceptance criteria。
- backlog 仅供规划和读取；completed 只由人类或独立 Review Agent 写入。
- 任务完成报告必须使用 `ai/workflows/implement-task.md` 的证据格式。
