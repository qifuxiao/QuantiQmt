# INV-RISK：风险不变量

1. MUST：所有新单、改单和扩大风险动作经过统一 Risk。
2. MUST：RiskDecision 由订单快照、行情/账户/组合快照版本和 rule_set_version 决定。
3. MUST：Risk 纯计算，不访问网络、数据库、Broker 或系统时钟。
4. MUST：关键快照 stale、partial、版本不匹配或 Risk 超时时 fail-closed。
5. MUST：策略级、账户级、组合级和系统级限额同时生效，最严格结果优先。
6. MUST：每次决策记录逐规则结果、测量值、限额、版本和耗时。
7. MUST NOT：动态配置突破系统硬安全上限。
8. MUST：减仓例外由显式规则决定，不能通过 side 字段猜测。
