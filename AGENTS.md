# QuantiQmt Agent Instructions

本仓库由人类与 Codex、Claude Code、Gemini、Cursor 等 AI Agent 协作开发。所有 Agent 必须遵守以下规则。

## 开始任务前

1. 读取本文件以及目标目录内更近的 `AGENTS.md`（若存在）。
2. 读取 `spec/README.md`、`spec/manifest.yaml`。
3. 只执行 `tasks/active/` 中明确指定的一个任务；没有 active task 时不得自主开始业务开发。
4. 读取任务 `spec_refs` 指向的全部规范并检查依赖任务状态。
5. 检查工作区已有变更，不覆盖或删除不属于当前任务的修改。

## 规范优先级

```text
安全与交易不变量
→ Accepted ADR
→ spec/ 规范性契约
→ 当前 active task
→ 本 AGENTS.md / 子目录 AGENTS.md
→ docs/ 解释性文档
→ Agent 自主判断
```

低优先级内容不得违反高优先级内容。发现冲突必须停止实现并报告，不能自行选择方便的一方。

## 实施边界

- 仅修改 task `allowed_paths`；不得修改 `forbidden_paths`。
- 不得自行新增、删除或改变 Event、Command、DTO、错误码、状态迁移、Repository 或 Workflow 契约。
- 契约确需变化时，先创建规范变更任务，更新 `spec/` 和兼容性说明，经评审后再实现。
- 策略不能导入 Broker、OMS Repository、数据库或 Redis 客户端。
- 禁止绕过 `OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution` 链路。
- 不确定的外部下单/撤单结果必须进入 UNKNOWN 并对账，禁止盲目重试。
- 不使用 float 处理最终价格、金额、费用和结算。

## 工作方式

- 先写或更新测试，再做满足任务的最小实现。
- 不做任务范围外的重构、依赖升级或格式化全仓库。
- 保持 Domain 纯净，I/O 位于 Port/Adapter 边界。
- 队列、重试、并发、缓存和外部调用必须有界且有 timeout。
- 新增公共行为必须包含日志、指标、错误码和失败路径。

## 完成与证据

完成前必须：

1. 执行 task 中所有 `verification.commands`。
2. 检查每条 acceptance criterion，并记录证据。
3. 报告修改文件、测试结果、未解决风险和规范偏差。
4. 不得自行把任务从 active 移到 completed；由人类或独立 Review Agent 验收后移动。

测试无法执行时不得声称完成，必须说明阻塞原因和未验证范围。

## Review

Review Agent 读取 `ai/review/`，优先检查交易安全、幂等、状态机、恢复、金额精度和越权依赖。发现违反 spec 的实现即为阻断问题，即使测试当前通过。
