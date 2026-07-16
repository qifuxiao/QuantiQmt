# Tool-Neutral AI Workflows

`ai/` 保存 Agent 如何工作，不保存交易业务真相。业务契约只能位于 `spec/`；当前工作范围只能位于 `tasks/`。

```text
ai/
├── workflows/    # 实现、Review、规范变更、故障诊断
├── review/       # 安全与架构检查表
├── prompts/      # 工具无关任务角色模板
└── adapters/     # 各 AI 工具如何找到同一入口
```

任何工具适配文件都必须指向根 `AGENTS.md`、`spec/README.md` 和 active task，不复制契约正文。

## 团队协作

多成员、多 Codex 会话协作遵守 [workflows/team-collaboration.md](workflows/team-collaboration.md)。该文档定义协调会话、开发会话和 Review 会话的职责边界，以及跨成员 Review 的最小交接格式。
