# Multi-Strategy Coordination

> Status: Proposed

多个策略共用账户时，不能简单把各自 Buy/Sell 指令同时发送。系统必须明确资金分配、持仓归属、目标聚合和内部对冲政策。

## 推荐模型

第一阶段使用“共享账户、虚拟子组合（Strategy Sleeve）”：

- 每个策略拥有 strategy_id 和虚拟资金/风险预算。
- Ledger/Portfolio 按 strategy_id 记录归属，同时维护账户级真实净持仓。
- Risk 同时检查策略 sleeve、账户和全局限制。
- OMS 保存订单 owner_strategy_id；聚合订单则保存 allocation plan。

## 目标聚合

```text
strategy targets
→ mandate validation
→ strategy-level target quantity
→ conflict/netting policy
→ account-level desired delta
→ allocation plan
→ OrderIntent
```

## 冲突策略

| 模式 | 行为 | 初始建议 |
|---|---|---|
| Isolated | 各策略独立订单，不内部净额 | 参考/调试策略 |
| Net at Account | 同标的目标净额后外发 | 组合型生产策略 |
| Priority | 高优先级策略先占资金/限额 | 紧急减仓/风险策略 |
| Proportional Scale | 资金不足按预算比例缩放 | 同等级策略 |

生产环境必须按 account/strategy group 配置一种明确政策，禁止运行时临时猜测。

## 内部交叉

策略 A 买、策略 B 卖时，是否内部净额只影响外部交易量，不能伪造成 Broker 成交。内部归属调整使用独立 Allocation/Ledger 事实，保留参考价格、费用分配和审计。首版可以禁止内部交叉，优先保证语义清晰。

## 资金分配

每个 Sleeve 定义 capital_budget、gross/net exposure、single-instrument limit、daily loss 和 priority。可用资金先保留费用、冻结、活动订单和安全 buffer，再按政策分配。

## 成交分配

聚合订单的成交按预先冻结的 allocation plan 分配，支持比例和确定性余数规则。不得在看到成交价格后选择性分配给表现更好的策略。分配结果可重放且总量等于 Broker Trade quantity。

## 策略停止

停止策略需明确 policy：保留仓位、逐步平仓、立即请求减仓或转移给人工组合。停止 Worker 本身不会默认撤单或清仓。

## 初始范围

第一版建议一个生产策略对应一个 account 或独立 Sleeve，禁止复杂跨策略内部交叉；Target Aggregation 和 allocation plan 保留接口，待单策略闭环稳定后启用净额优化。
