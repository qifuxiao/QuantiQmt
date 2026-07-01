# Workflow: Diagnose Failure

1. 保护现场：记录 correlation_id、时间窗口、版本、组件状态，不先重启或清数据。
2. 判断是否影响交易安全；不确定时进入 SAFE/HALTED，并保留撤单/恢复能力。
3. 沿 Market→Strategy→Target→OMS→Risk→Execution→Broker→Trade→Ledger 查询证据。
4. 区分确定失败、暂时失败和 UNKNOWN_OUTCOME。
5. 对照 spec 状态机/Workflow/Source of Truth，禁止通过直接改库“修好”。
6. 给出根因、影响范围、恢复证据、长期修复和回归测试。

Agent 不得执行生产修复、解除 Kill Switch 或账务调整，除非 task 明确授权且满足审批。
