# Agent Task Queue

`tasks/` 把 Roadmap 拆成最小、可独立验收的工作单元。Task 不得复制 spec，只通过 `spec_refs` 引用。

## 状态目录

- `backlog/`：尚未执行；front matter 状态为 blocked 或 ready。
- `active/`：经过人工选择，允许 Agent 执行；同一 Agent 一次只处理一个。
- `completed/`：独立 Review 验收完成。
- `templates/`：任务模板。

## 激活规则

1. 依赖任务全部 completed。
2. spec_refs 存在且状态足够稳定。
3. acceptance criteria 可自动或人工验证。
4. allowed_paths 足够完成任务且不包含无关范围。
5. 人类将任务从 backlog 移入 active，并把 status 改为 active。

Agent 不得自行激活、拆大范围任务或修改任务验收标准以适配自己的实现。

## 完成证据

任务报告必须包含变更文件、逐项验收结果、命令和退出码、测试摘要、未验证项、风险及 spec 偏差。Review 通过后才移入 completed。
