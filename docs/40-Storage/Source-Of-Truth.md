# Source of Truth Catalog

> Status: Proposed  
> 权威来源不是“数据存在哪里”，而是发生冲突时由谁裁决。任何新增业务数据必须先登记权威来源、缓存、持久化、恢复和差异处理。

| 数据 | 业务权威来源 | 永久记录 | 缓存/投影 | 恢复 | 冲突处理 |
|---|---|---|---|---|---|
| OrderIntent | OMS Journal | PostgreSQL | OMS memory | Journal replay | intent_id 幂等 |
| RiskDecision | Risk Audit Event | PostgreSQL | OMS order snapshot | 按 order_id 加载 | 保留版本，不覆盖 |
| 内部订单历史 | OMS Journal | PostgreSQL | OMS memory/read model | Snapshot + Journal | 聚合版本裁决 |
| 外部委托事实 | Broker | Broker + PostgreSQL observations | OMS read model | Broker query + merge | 对账 Case，不直接覆盖历史 |
| Trade | Broker | PostgreSQL trades | Portfolio projection | Broker query + unique-key import | Broker 证据裁决，重复去重 |
| Ledger | AccountLedger | PostgreSQL append-only entries | Balance projection | Ledger replay | 调整分录，不 UPDATE 历史 |
| Position | Trade/Ledger projection；Broker 为外部基线 | PostgreSQL journal/snapshot | memory/Redis | Replay + Broker reconcile | 差异工单/调整分录 |
| Account Cash | Ledger 为内部账务；Broker 为可交易外部基线 | PostgreSQL | Risk snapshot/Redis | Ledger replay + Broker query | SAFE，人工/规则修复 |
| Tick | MiniQMT/上游源 | 可选行情库 | process memory/Redis | 通常不可恢复，标记 gap | 不伪造缺失 Tick |
| Bar | 选定原始行情 + 聚合规则 | 行情库 | Redis/memory | 确定性重算 | 以数据集版本裁决 |
| Strategy Definition | Versioned strategy registry | PostgreSQL/artifact store | worker memory | 按版本加载 | 禁止运行未登记版本 |
| Strategy Runtime State | Strategy checkpoint + input event position | PostgreSQL | worker memory | checkpoint + replay | 无法验证则 PAUSED |
| Risk Rule Set | Versioned Config Store | PostgreSQL | immutable memory snapshot | 按 active version 加载 | 激活事件裁决 |
| Instrument Spec | Reference Data Store | PostgreSQL | memory/Redis | 按交易日版本加载 | 版本不一致禁止交易 |
| Trading Calendar | Calendar Store | PostgreSQL/artifact | memory | 按版本加载 | 缺失时 fail-closed |
| System Mode/Kill Switch | Control Journal | PostgreSQL | each component memory | 启动先恢复 | 最严格状态优先 |
| Consumer Offset | Stream Consumer Group | Redis + checkpoint policy | consumer memory | PEL reclaim/Inbox | Inbox 决定业务是否已处理 |
| Audit | Audit Journal | PostgreSQL/WORM archive | query index | archive restore | 只追加修正记录 |

## 重要区分

- Broker 是外部委托和成交的最终事实，但不是内部意图、风险原因、策略归属或账本历史的权威来源。
- PostgreSQL 是永久业务记录；Redis 是可重建加速层，不是订单/资金权威来源。
- Position/Account 同时存在内部账务视图和 Broker 可交易视图。风控使用哪个必须按规则声明；两者不一致时默认禁止扩大风险。
- Cache 不得拥有在永久记录中不存在的唯一业务事实。

## 缓存规则

缓存条目必须包含 source_version、as_of、quality 和 expires_at。缓存 miss 回源；缓存 stale 不得自动当作 fresh。删除全部 Redis 数据后，系统应能通过 PostgreSQL、Broker 和上游重新构建，并保持业务不变量。
