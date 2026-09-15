# Active Tasks

当前 active task：TASK-058（唯一）。

- 路径：`tasks/active/TASK-058-risk-finalization-boundary.md`
- 状态：`active / draft / not_started / not_run / pending / prohibited`
- 计划：`TASK-058-PLAN-v3`
- Planning Base：`4fb7ad1ecb5d726fff7f54d107de69fbabe69688`
- 依赖：TASK-003、TASK-015、TASK-029 均为可信 completed。
- 可演示结果：可评审的 Risk 最终验证、计时、失败出口与有界遥测规范及兼容性说明。

本准备 PR 仅执行 task 正文列出的六路径 v3 衔接、精确身份支持与 CI 构建前置；
不修改规范正文，不创建 Packet/Handoff、不分配 Implementation Agent。
后续实施范围为五份规范与 task 中列出的三个精确测试文件，准备权限不得继承。
PR #119 旧 writer 已由 Human STOP：
https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5646729029
远端 STOP Head 为 `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`；
本地同步 `02fc1857a2fa885ba59477de37a7e20ca965fc3f` 保留、未推送，不是远端 Head。
旧 Packet/Handoff 保持不变；准备合并后使用新 Base、新 PR、新 assignment 和 v3 交接，
首次 no-ff 同步与正式 Handoff gate 通过前不得实施。本准备 PR 不关闭 #119。
PR #121 的 v2 writer 已由 Human STOP：
https://github.com/qifuxiao/QuantiQmt/pull/121#issuecomment-5673301389
STOP Head 为 `a3b15fdf9ca5e7783a7d0218450dd3933b034379`，零 active writer；
STOP 不授权恢复旧 writer。保留 #121 的分支、提交、评论与 v1/v2 Packet/Handoff，
不关闭、不改写、不推送旧分支。本阶段不转移八文件、不创建 v3 Packet/Handoff。
准备合并后冻结新 Base，以标准 Packet-only / add-only Handoff 拓扑另行交接；
后续仅转移 task 冻结的八文件准确差异，不携带旧 task、交接文件或同步拓扑。
CI 仅在 quality 的现有 Test 前增加 `poetry build`，其余 jobs 和命令不变。
不推进 skip 例外或 waiver；新 exact Head 完整测试与 CI 实际零 skip 后，
由独立 Environment Verification Agent 产生同 Head evidence，再独立 Review。
TASK-005 为 backlog/blocked，PR #117 已关闭未合并，历史权威保留。
候选方向不是规范 Approval；后续规范变更需独立评审和 Human merge。
TASK-053 及其他任务未获激活；release、Mini QMT 和交易权限不变。
