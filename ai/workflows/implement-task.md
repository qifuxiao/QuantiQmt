# Workflow: Implement One Task

## 1. Intake

读取根/子目录 AGENTS、active task、全部 spec_refs、已有实现和测试。确认依赖 completed、路径权限充分、规范无冲突；否则停止并报告。

## 2. Plan

将 acceptance criteria 映射为代码修改和测试。不扩大范围；需要规范变化时转入 spec-change workflow。

## 3. Implement

先建立失败测试或契约 fixture，再做最小实现。保持安全不变量、类型、错误码、日志/指标和失败路径。

## 4. Verify

执行任务全部命令，并按验收项检查。必要时运行受影响的上层测试，但不得用跳过/放宽测试制造通过。

## 5. Evidence

```text
Task: TASK-XXX
Spec refs read:
Changed files:
Acceptance evidence:
Commands and exit codes:
Unverified scope:
Risks/limitations:
Spec deviations: none | details
```

## 6. Handoff

不得自行标记 completed。请求独立 Review，并保持变更可审查、无无关格式化。
