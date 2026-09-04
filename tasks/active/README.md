# Active Tasks

当前 active task：TASK-029（唯一）。

- 路径：`tasks/active/TASK-029-risk-runtime-schema-contract.md`
- 状态：`active / accepted / not_started / not_run / pending / prohibited`
- 冻结计划：`TASK-029-PLAN-v1`
- Planning Base：`286c3901b3801fd752feaaf615167cef248a9494`
- 可演示结果：安装后的包无需读取源码 `spec/**` 即可验证 Risk outputs，并对 Schema
  缺失、损坏或版本不匹配 fail-closed。

本 activation-only PR 不创建 Packet/Handoff，不开始 TASK-029 实现。TASK-005 保持
`backlog/blocked`；TASK-053 及其他任务也不得并行激活。
