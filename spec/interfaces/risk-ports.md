# PORTS-RISK：Risk L4 契约

本规范冻结 `RiskInputV1`、Snapshot DTO、`RiskRuleSetV1`、`RiskDecisionV1`、规则排序、fail-closed、减仓例外和审计映射。机器字段以 `CONTRACT-RISK-INPUT-V1`、`CONTRACT-RISK-RULE-SET-V1`、`CONTRACT-RISK-DECISION-V1`、`CONTRACT-RISK-AUDIT-OUTPUT-V1` 为准。

## 逻辑签名与纯计算边界

```python
class RiskEvaluator(Protocol):
    def iter_rule_results(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> Iterator[RiskRuleResultV1]: ...
    def decide(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1, results: tuple[RiskRuleResultV1, ...]) -> RiskDecisionV1: ...
    def evaluate(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> RiskDecisionV1: ...

class RiskEvaluationRunner(Protocol):
    def run(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> RiskAuditOutputV1: ...
```

`RiskEvaluator` MUST 是同步、不可变、确定性的纯计算，不读取网络、数据库、Broker、Redis、环境变量、可变全局状态、business clock 或 monotonic clock。`iter_rule_results` 按规范顺序惰性 yield；`decide` 只聚合已经完成的 immutable results；`evaluate` 等价于 `decide(..., tuple(iter_rule_results(...)))`。`RiskEvaluationRunner` 在每次 `next()` 外围读取注入的 `Clock.monotonic_ns()` 来记录完成规则的耗时，并用独立 deadline guard 覆盖正在运行的单条规则。相同 `risk_input` 与 `rule_set` 必须产生逐字节相同的 evaluator 语义决策；`evaluated_at` 和 latency 不属于该投影。

JSON Schema decode/typed DTO construction 位于 Port 之前。结构无效的 RiskInput 返回 `QQ-RISK-4008`，结构无效的 RuleSet 返回 `QQ-RISK-4007`，OrderApplication 使用已注册 Order identity fail-closed，且不得调用 evaluator 或从畸形 payload 猜 identity。`decision_origin=INPUT_GUARD` 只用于 schema-valid DTO 的语义完整性、Snapshot 或 RuleSet guard REJECT；完整业务规则求值的 PASS/REJECT 使用 `EVALUATOR`，运行预算超时使用 `TIMEOUT_GUARD`。

## 身份、不可变性与 canonical hash

- canonical JSON MUST 使用 RFC 8785 JSON Canonicalization Scheme：UTF-8、对象 key 按规范排序、数组保序、无 Unicode normalization；所有 Decimal 仍是普通字符串，禁止 float/NaN/Infinity。`input_version` 是 RiskInput 去掉自身 `input_version` 后 canonical bytes 的 SHA-256 64 位小写 hex。收到的 hash 不匹配时以 `QQ-RISK-4008` 拒绝。
- `content_hash` 对 RuleSet 去掉自身 `content_hash` 后使用同一算法。hash 不匹配、重复 `rule_id`、重复 `(scope, scope_id)` metrics 行或非法 metric/operator/limit 组合以 `QQ-RISK-4007` 拒绝。
- `hard_limit_policy_hash` 是 `{hard_limit_policy_version, system_hard_limits}` 的 RFC 8785 canonical SHA-256。该 policy 由安全治理的 immutable baseline 发布，不属于普通 hot config；ConfigService 只能引用当前 accepted policy，不能在 RuleSet candidate 中改值。hash 不匹配或 candidate policy 未被接受均以 `QQ-RISK-4007` 拒绝激活。
- RiskInput 的 `rule_set_version/rule_set_hash` MUST 分别等于传入 RuleSet 的 `rule_set_version/content_hash`，否则以 `QQ-RISK-4011` / `RISK_RULE_SET_VERSION_MISMATCH` 拒绝。
- Order `checksum` 对去掉自身 checksum 的 Order Snapshot 计算；其他 Snapshot 的 `metadata.checksum` 对去掉该 checksum 的完整 Snapshot 计算，算法同上。checksum 不匹配以 `QQ-RISK-4008` 拒绝。TIMEOUT/UNAVAILABLE Snapshot 的 `snapshot_version` 是 Snapshot builder attempt identity，checksum 覆盖 null data 和失败 quality，不能伪装成源数据版本。
- `decision_id` MUST 为 `uuid5(UUID("b5a6c3cc-2be0-5e6f-a9ec-2d9a4e769979"), input_version + ":" + content_hash)`；不得使用 UUID4。hash 校验失败时输出使用重新计算的实际 input/rule-set hash，不能以调用方声称的错误 hash 生成 identity。`semantic_decision_hash` 对 RiskDecision 去掉 `decision_id` 和自身 hash 后按上述 canonical JSON 计算。
- DTO 在构造后 MUST deep immutable；不得在一次决策中切换 `rule_set_version` 或任何 Snapshot version。

RiskDecision 的 `order_id/expected_order_version` MUST 等于 Input Order 的 `order_id/aggregate_version`；`input_version` 使用已验证或重新计算的实际 hash；`rule_set_version/rule_set_hash` 使用本次唯一 RuleSet；三个 `snapshot_states` 逐一记录 version、派生 quality、age 和对应 max age。Decision 不携带 business timestamp 或 latency，所有运行时测量只进入 RiskAuditOutput。

## Snapshot 质量和一致性

`evaluation_time` 是 OrderApplication 在组装输入前通过 Clock Port 注入的 UTC business time；evaluator 仅比较该字段，不读系统时钟。`age_ms = floor((evaluation_time - as_of) / 1ms)`；`as_of > evaluation_time` 是 invalid input。

Snapshot quality 的 canonical 语义如下：

| quality | 判定 | canonical error | 规则结果 reason |
|---|---|---|---|
| `FRESH` | `missing_fields=[]` 且 `age_ms <= freshness_limits_ms[source]` | none | 继续求值 |
| `STALE` | producer 标记 STALE，或计算 age 超过上限 | `QQ-RISK-4002` | `RISK_SNAPSHOT_STALE` |
| `PARTIAL` | producer 明确标记部分结果，且 `missing_fields` 非空 | `QQ-RISK-4003` | `RISK_SNAPSHOT_PARTIAL` |
| `TIMEOUT` | Snapshot builder 在 deadline 内未获得该来源 | `QQ-RISK-4010` | `RISK_SNAPSHOT_TIMEOUT` |
| `UNAVAILABLE` | 来源明确不可用或无可验证版本 | `QQ-RISK-4006` | `RISK_SNAPSHOT_UNAVAILABLE` |
| `VERSION_MISMATCH` | evaluator 派生状态；版本/identity/trading_day 不一致 | `QQ-RISK-4004` | `RISK_SNAPSHOT_VERSION_MISMATCH` |

同一来源同时满足多个失败条件时，派生 quality 优先级固定为 `VERSION_MISMATCH > UNAVAILABLE > TIMEOUT > PARTIAL > STALE > FRESH`；较低优先级状态不能覆盖较高优先级状态。

quality/data 必须自洽：FRESH/STALE 的 `missing_fields` 必须为空且所有本次适用规则所需值非 null；PARTIAL 必须列出缺失字段；TIMEOUT/UNAVAILABLE 可携带 null，但不得用于求值。producer 标记 FRESH 却缺值、PARTIAL 却漏报字段、或 missing_fields 与 null 值不一致，属于 invalid input `QQ-RISK-4008`，不得猜成其他质量。

Account/Portfolio 在 FRESH/STALE/PARTIAL 时 `aggregate_version` MUST 为非 null 且与其 `snapshot_version` 所代表的聚合版本一致；TIMEOUT/UNAVAILABLE 可为 null。Market metadata 的 `aggregate_version` MUST 为 null。LIMIT order 的 `risk_price_source=LIMIT_PRICE` 且 `risk_price=order.limit_price`；MARKET/BEST 的 source 必须为 `MARKET_WORST_CASE`，由同一 Market Snapshot 提供可审计的最坏可执行价格。`UNAVAILABLE` 只能用于非 FRESH quality。任一不一致以 `QQ-RISK-4008` 拒绝。

MUST 校验：Order/Account/Portfolio 的 `account_id` 相同；Order/Portfolio 的 `portfolio_id` 相同；Order/Market 的 `instrument_id` 相同；Account/Portfolio/Market 的 `trading_day` 相同；Order `market_data_version` 等于 Market `snapshot_version`；REDUCE evidence `position_snapshot_version` 等于 Portfolio `snapshot_version`。Portfolio `scope_metrics` 必须恰好包含与本单 identity 匹配的 ACCOUNT、PORTFOLIO、STRATEGY、INSTRUMENT 各一行，缺少、重复或多余行均为 invalid input。任一不匹配均 fail-closed。

四个 scope metrics 的 `activity_window_ms` 必须全部等于 RuleSet `system_hard_limits.activity_window_ms`。`order_count_window` 是半开区间 `(evaluation_time - activity_window_ms, evaluation_time]` 内已注册订单数，并包含当前已注册 Order 恰好一次；`cancel_ratio_bps = ceil(10000 * cancel_request_count / max(registered_order_count, 1))`，使用同一窗口。动态 rate rules 共享该窗口，V1 不允许每条规则自定义窗口。

`FRESH` 标签不能覆盖 age 计算；STALE/PARTIAL/TIMEOUT/UNAVAILABLE 标签也不能被本地数据看似完整而升级为 FRESH。任何扩大风险或 UNKNOWN 输入在关键 Snapshot 非 FRESH 时 MUST REJECT。减仓也不得绕过 Snapshot identity、version、checksum、position evidence 或 market/order 基本合法性。

## Metric 与 operator

规则只允许 schema 中的 metric，映射固定如下：

| metric | measured value | operator / limit kind | allowed rule scopes |
|---|---|---|---|
| `TRADING_ENABLED` | SYSTEM 取 `system_hard_limits.allow_new_risk`；其他 scope 取匹配 metrics 的 `enabled` | `BOOLEAN_TRUE / BOOLEAN(value=true)` | all |
| `INSTRUMENT_ALLOWED` | `order.instrument_id` | `IN_SET / STRING_SET` | all |
| `ORDER_QUANTITY` | `order.quantity` | `MAX / INTEGER` | all |
| `ORDER_NOTIONAL` | `abs(risk_price * quantity)`，Decimal，8 位 scale `ROUND_UP` | `MAX / DECIMAL` | all |
| `PRICE_DEVIATION_BPS` | Market DTO 的值；同时校验 `abs(risk_price-reference_price)/reference_price*10000` 向上取整一致 | `MAX / INTEGER` | all |
| `AVAILABLE_CASH` | Account `projected_available_cash` | `MIN / DECIMAL` | SYSTEM, ACCOUNT |
| `POSITION_QUANTITY` | 匹配 scope metrics 的 `abs(projected_position_quantity)`；SYSTEM 映射 ACCOUNT row | `MAX / INTEGER` | all |
| `PROJECTED_GROSS_EXPOSURE` | 匹配 scope metrics 的同名值；SYSTEM 映射 ACCOUNT row | `MAX / DECIMAL` | all |
| `PROJECTED_NET_EXPOSURE_ABS` | 匹配 scope metrics 的 `abs(projected_net_exposure)`；SYSTEM 映射 ACCOUNT row | `MAX / DECIMAL` | all |
| `PROJECTED_LEVERAGE` | 匹配 scope metrics 的同名值；SYSTEM 映射 ACCOUNT row | `MAX / DECIMAL` | all |
| `DAILY_LOSS` | Account `max(daily_loss, 0)` | `MAX / DECIMAL` | SYSTEM, ACCOUNT |
| `ORDER_COUNT_WINDOW` | 匹配 scope metrics 的同名值；SYSTEM 映射 ACCOUNT row | `MAX / INTEGER` | all |
| `CANCEL_RATIO_BPS` | 匹配 scope metrics 的同名值；SYSTEM 映射 ACCOUNT row | `MAX / INTEGER` | all |

不合法 scope/metric 组合使 RuleSet invalid。缺少适用 metric、出现多个相同 scope metrics、货币不一致、Decimal 溢出/非法、`reference_price <= 0` 或复算不一致均为 `QQ-RISK-4008`，不得使用默认 0。`MAX` 通过条件为 measured <= limit，`MIN` 为 measured >= limit，`BOOLEAN_TRUE` 为 measured is true，`IN_SET` 为 measured 属于 values；不得做字符串数值比较。所有金额/价格/比例最终判断 MUST 使用 Decimal，禁止 float。

## RuleSet 校验和硬限额

`system_hard_limits` 产生下列固定规则，属于不可删除 phase `SYSTEM_HARD_LIMIT`：

| priority | rule_id | measured value | hard field |
|---:|---|---|---|
| 10 | `SYSTEM.HARD.NEW_RISK_ENABLED` | INCREASE/UNKNOWN 时检查；verified REDUCE 为 NOT_APPLICABLE | `allow_new_risk` |
| 20 | `SYSTEM.HARD.ORDER_QUANTITY` | ORDER_QUANTITY | `max_order_quantity` |
| 30 | `SYSTEM.HARD.ORDER_NOTIONAL` | ORDER_NOTIONAL | `max_order_notional` |
| 40 | `SYSTEM.HARD.PRICE_DEVIATION_BPS` | PRICE_DEVIATION_BPS | `max_price_deviation_bps` |
| 50 | `SYSTEM.HARD.GROSS_EXPOSURE` | ACCOUNT row PROJECTED_GROSS_EXPOSURE | `max_projected_gross_exposure` |
| 60 | `SYSTEM.HARD.NET_EXPOSURE_ABS` | ACCOUNT row PROJECTED_NET_EXPOSURE_ABS | `max_projected_net_exposure_abs` |
| 70 | `SYSTEM.HARD.LEVERAGE` | ACCOUNT row PROJECTED_LEVERAGE | `max_projected_leverage` |
| 80 | `SYSTEM.HARD.DAILY_LOSS` | Account DAILY_LOSS | `max_daily_loss` |
| 90 | `SYSTEM.HARD.ORDER_COUNT_WINDOW` | ACCOUNT row ORDER_COUNT_WINDOW | `max_order_count_window` |
| 100 | `SYSTEM.HARD.CANCEL_RATIO_BPS` | ACCOUNT row CANCEL_RATIO_BPS | `max_cancel_ratio_bps` |

硬规则、Snapshot validity、input validity、timeout guard 永远不得出现在 `exempt_rule_ids`，且不接受 `reduction_exception=ALLOW_IF_VERIFIED`。`SYSTEM.HARD.NEW_RISK_ENABLED` 对 verified reduction 的 NOT_APPLICABLE 是该 hard rule 的固定语义，不是例外；其余 hard limit 对 REDUCE 仍生效。

对具有上表同 metric hard cap 的动态规则，`MAX` limit 必须小于等于 hard max，boolean 不得把 hard false 改为 true。`AVAILABLE_CASH`、`POSITION_QUANTITY`、`INSTRUMENT_ALLOWED` 等没有对应 hard field 的 metric 可以由动态规则定义；它们仍不能删除或改变任何 hard rule。违反关系使整个 RuleSet invalid，并以 `QQ-RISK-4007` fail-closed；不得悄悄 clamp 后继续。

`reduce_only_policy.exempt_rule_ids` 的每个 id 必须存在于 `rules`，对应 rule 必须声明 `ALLOW_IF_VERIFIED`，metric 不得为 `TRADING_ENABLED` 或 `INSTRUMENT_ALLOWED`，且不得是 SYSTEM.HARD 或 validity/timeout rule；否则整个 RuleSet invalid。声明 `ALLOW_IF_VERIFIED` 但未列入 policy 的 rule 按 `NEVER` 执行，不得隐式放行。

规则 metric/operator/limit 的唯一合法组合见上表。适用 scope identity：SYSTEM 使用 null；ACCOUNT=`order.account_id`；PORTFOLIO=`order.portfolio_id`；STRATEGY=`order.strategy_id`；INSTRUMENT=`order.instrument_id`。不匹配 scope 的规则输出 `NOT_APPLICABLE`，不能影响总决策。

## 确定性排序与最严格结果

必须完整求值，不因首个 REJECT 短路；timeout guard 除外。排序 key 为：

1. phase：`INPUT_VALIDITY < SNAPSHOT_VALIDITY < SYSTEM_HARD_LIMIT < SCOPED_RULE < TIMEOUT_GUARD`；
2. SCOPED_RULE 内 scope：`SYSTEM < ACCOUNT < PORTFOLIO < STRATEGY < INSTRUMENT`；
3. `priority` 升序；
4. `rule_id` 按 Unicode code point 升序。

每次评估始终产生以下 synthetic validity results，结果 PASS/REJECT 由本规范校验决定，scope 均为 SYSTEM/null：

| phase | priority | rule_id | responsibility |
|---|---:|---|---|
| INPUT_VALIDITY | 10 | `RISK.INPUT.CANONICAL` | schema-valid typed values、canonical hashes、checksum、Decimal/price recomputation |
| INPUT_VALIDITY | 20 | `RISK.INPUT.IDENTITY` | order/account/portfolio/instrument/trading_day identity |
| INPUT_VALIDITY | 30 | `RISK.INPUT.RULE_SET_BINDING` | input 与 RuleSet version/hash 一致 |
| INPUT_VALIDITY | 40 | `RISK.INPUT.REDUCTION_EVIDENCE` | explicit reduce-only evidence；非 REDUCE 为 NOT_APPLICABLE |
| INPUT_VALIDITY | 50 | `RISK.RULE_SET.VALIDITY` | RuleSet hash、唯一性、metric/operator、hard-cap 与 exception policy |
| SNAPSHOT_VALIDITY | 10 | `RISK.SNAPSHOT.ACCOUNT` | Account quality/freshness/required fields |
| SNAPSHOT_VALIDITY | 20 | `RISK.SNAPSHOT.PORTFOLIO` | Portfolio quality/freshness/scope metrics |
| SNAPSHOT_VALIDITY | 30 | `RISK.SNAPSHOT.MARKET` | Market quality/freshness/status/prices |
| SNAPSHOT_VALIDITY | 40 | `RISK.SNAPSHOT.CROSS_SOURCE` | cross-source versions and identities |

timeout 时追加 `TIMEOUT_GUARD/priority=0/rule_id=RISK.SYSTEM.EVALUATION_TIMEOUT`。硬规则使用上表 priority；动态规则使用 RuleSet priority。所有 synthetic/hard rule 的 `metric`、measured/limit 无定义时为 null，不能填伪造的 0。

九个 INPUT/SNAPSHOT synthetic guard 必须全部求值。只要任一 guard REJECT，evaluator 立即形成 `INPUT_GUARD` REJECT，不执行 SYSTEM_HARD_LIMIT 或 SCOPED_RULE；这不是以首个业务 REJECT 短路，而是防止用无效数据计算限额。只有全部 guard PASS/NOT_APPLICABLE 后，才完整执行所有 hard/scoped rules，且不得因其中任一 REJECT 跳过后续规则。

`evaluation_index` 必须等于最终数组从 0 开始的位置，RuleSet 内 `rule_id` 全局唯一。priority 只影响审计顺序，不影响结果强度。同一 metric 的所有适用规则都求值，因此更严格 limit 自然生效。总结果强度为 `REJECT > PASS > NOT_APPLICABLE`：任一 REJECT 则 REJECT；无 REJECT 且至少一个适用业务/硬规则 PASS 才能 PASS；没有可适用规则必须以 `QQ-RISK-4007` REJECT。

RuleResult encoding 固定：普通 PASS 使用 `RISK_RULE_PASSED` 且 `exception_applied=false`；减仓例外 PASS 使用 `RISK_REDUCE_ONLY_EXCEPTION_APPLIED` 且 `exception_applied=true`；NOT_APPLICABLE 使用 `RISK_RULE_NOT_APPLICABLE` 且 `exception_applied=false`；REJECT 使用下表对应 reason 且 `exception_applied=false`。Decision PASS 的 primary reason 固定为 `RISK_ALL_APPLICABLE_RULES_PASSED`。

除 timeout 外，`primary_reason_code` 取排序后第一个 REJECT 的 reason；`error_code` 使用 fail-closed taxonomy 映射。普通规则或硬限额 breach 映射 `QQ-RISK-4001`；Snapshot、input、RuleSet 与 timeout 使用专用 code。`decision_origin=TIMEOUT_GUARD` 时无条件以 `RISK_EVALUATION_TIMEOUT/QQ-RISK-4005` 为 primary/error，即使 timeout 前已有 REJECT，已有结果仍保留用于审计。

| reject reason family | error code |
|---|---|
| rule breach、hard limit、trading disabled、instrument not allowed | `QQ-RISK-4001` |
| stale | `QQ-RISK-4002` |
| partial | `QQ-RISK-4003` |
| Snapshot version/identity mismatch | `QQ-RISK-4004` |
| evaluation timeout | `QQ-RISK-4005` |
| unavailable | `QQ-RISK-4006` |
| invalid RuleSet | `QQ-RISK-4007` |
| invalid input/checksum/decimal/recomputation | `QQ-RISK-4008` |
| invalid reduction evidence | `QQ-RISK-4009` |
| Snapshot builder timeout | `QQ-RISK-4010` |
| RiskInput/RuleSet version or hash binding mismatch | `QQ-RISK-4011` |

## 减仓例外

side、`position_effect=CLOSE`、策略 tag 或负号均不能证明减仓。只有下列条件全部满足，`risk_effect=REDUCE` 才是 verified reduce-only：

1. `reduction_evidence.classification=VERIFIED_REDUCE_ONLY`；
2. evidence version 等于 Portfolio Snapshot version；
3. `quantity <= max_reducible_quantity = max(abs(position_quantity_before) - reserved_reduce_quantity, 0)`；
4. evidence `position_quantity_before` 必须等于 INSTRUMENT scope metrics 的 current 值；令 BUY signed delta=`+quantity`、SELL signed delta=`-quantity`，evidence `projected_position_quantity` 必须等于 before + delta，并等于该 metrics 的 projected 值；
5. projected position 的绝对值严格小于 before，且 `would_flip_position=false`；
6. 对应 Account/Portfolio/Instrument identity、trading_day、checksum 和所需持仓字段均有效。

任何失败将 risk effect 降级为 UNKNOWN 并以 `QQ-RISK-4009` REJECT。例外仅在 RuleSet policy enabled、rule 自身 `ALLOW_IF_VERIFIED`、且 rule_id 明确列入 `exempt_rule_ids` 时生效。原本会 REJECT 的该规则输出 PASS、`exception_applied=true`、reason=`RISK_REDUCE_ONLY_EXCEPTION_APPLIED`，仍记录原 measured/limit。例外不得用于 hard limit、Snapshot/input/RuleSet validity、timeout、instrument allowlist、trading halt 或 kill switch。

`risk_effect=UNKNOWN` 必须按风险扩大处理全部 hard/scoped rules，且永远不能使用减仓例外；`risk_effect=INCREASE` 同样没有 reduction evidence。将真实减仓保守标为 INCREASE 只会失去例外，不得形成放行漏洞。

## Timeout 与审计输出

Runner 在每个确定性规则边界前后读取 monotonic_ns，使用整数向上换算 `latency_us = ceil(delta_ns/1000)`；总耗时同样计算，且必须大于等于已记录逐规则耗时之和。不得使用 wall clock 计算 latency。`evaluated_at` 由外层 Clock 在结束后注入，仅用于审计，不参与 Decision hash。

elapsed 达到 `evaluation_timeout_us`（`total_latency_us >= evaluation_timeout_us`）时，即使当前 `next()` 尚未返回，Runner 也 MUST 停止等待并产生 `decision_origin=TIMEOUT_GUARD` 的 REJECT，追加 `RISK.SYSTEM.EVALUATION_TIMEOUT` 结果，error=`QQ-RISK-4005`，保留已完成结果，丢弃未完成结果。执行必须位于有界 cancellable worker；若底层不能证明已取消，attempt fencing 仍必须永久丢弃其 late output，且不能让超时 worker 无界堆积。相同 input_version 不得重评，重试必须重建含新 evaluation_time 的 RiskInput，因此产生新 input_version/decision_id。

Runner MUST 产生 `CONTRACT-RISK-AUDIT-OUTPUT-V1`：`decision` 是完整 RiskDecision；`evaluation_timeout_us` 等于本次 RuleSet 值；`rule_timings` 按 evaluation_index 排序并与 Decision 的每个 rule result 以 `(evaluation_index, rule_id)` 一一对应；`total_latency_us >= sum(rule_timings.latency_us)`；正常完成时 `completed_rule_count=len(rule_results)`，timeout 时等于 timeout guard 之前完成的规则数。该 DTO 是 Runner 的完整内部审计/测量输出，不创建新的 Storage authority。

已发布的 `risk.order_evaluated.v1` schema 保持不变，并按 `STORAGE-SOT` 继续作为 RiskDecision 的权威持久化审计事件：顶层 identity/decision/rule_set 逐字段取 Decision；`snapshot_versions` 取三个 `snapshot_states.snapshot_version`；每个公开 `rule_results` 投影 `rule_id/result/reason_code/measured_value/limit_value` 并从匹配 timing 取 `latency_us`；`evaluated_at` 取 AuditOutput。V1 不承载 input hash、snapshot quality、phase/scope/priority、exception、total latency或 error code；消费者不得猜测这些缺失字段，需要公共扩展时必须发布新 message version。不得向 v1 payload 添加 schema 未声明字段。

Event envelope MUST 使用 `message_id=decision_id`、`correlation_id=order.intent_id`、`causation_id` 为触发 Risk 的 OrderRegistered message id、`aggregate_id=order_id`、`aggregate_version=expected_order_version`、`partition_key=order_id`。OMS 只能在 `expected_order_version` 匹配时应用 Decision；冲突返回 `QQ-COMMON-1003`，重新读取后由 Application 明确决定是否以新 input_version 重评。

指标必须至少包含 `risk_evaluation_latency_us` histogram、`risk_rule_latency_us` histogram、`risk_decisions_total{decision,origin,error_code}` counter、`risk_fail_closed_total{reason}` counter。禁止使用 order/account/instrument/correlation 等高基数字段作为 metric label。
