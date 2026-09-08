# Active Tasks

当前 active task：TASK-005（唯一）。

- 路径：`tasks/active/TASK-005-risk-engine.md`
- 状态：`active / accepted / not_started / not_run / pending / prohibited`
- 计划：`TASK-005-PLAN-v1`
- Planning Base：`f09811a17972d1d446a95806821fd80586858e11`
- 依赖：TASK-003、TASK-015、TASK-029 均为可信 completed。
- 可演示结果：固定快照和规则集产生确定性 Risk Decision，对非法输入及超限 fail-closed。

本 activation-only PR 不创建 Packet/Handoff、不分配 Implementation Agent，
不开始业务实现。TASK-053 及其他任务未获激活；release、Mini QMT 和交易权限不变。
