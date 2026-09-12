# Active Tasks

当前 active task：TASK-058（唯一）。

- 路径：`tasks/active/TASK-058-risk-finalization-boundary.md`
- 状态：`active / draft / not_started / not_run / pending / prohibited`
- 计划：`TASK-058-PLAN-v2`
- Planning Base：`3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb`
- 依赖：TASK-003、TASK-015、TASK-029 均为可信 completed。
- 可演示结果：可评审的 Risk 最终验证、计时、失败出口与有界遥测规范及兼容性说明。

本准备 PR 仅补充精确测试范围、第三条 portable 命令及 v2 身份支持；
不修改规范正文，不创建 Packet/Handoff、不分配 Implementation Agent。
后续实施范围为五份规范与 task 中列出的三个精确测试文件，准备权限不得继承。
PR #119 旧 writer 已由 Human STOP：
https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5646729029
远端 STOP Head 为 `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`；
本地同步 `02fc1857a2fa885ba59477de37a7e20ca965fc3f` 保留、未推送，不是远端 Head。
旧 Packet/Handoff 保持不变；准备合并后使用新 Base、新 PR、新 assignment 和 v2 交接，
首次 no-ff 同步与正式 Handoff gate 通过前不得实施。本准备 PR 不关闭 #119。
TASK-005 为 backlog/blocked，PR #117 已关闭未合并，历史权威保留。
候选方向不是规范 Approval；后续规范变更需独立评审和 Human merge。
TASK-053 及其他任务未获激活；release、Mini QMT 和交易权限不变。
