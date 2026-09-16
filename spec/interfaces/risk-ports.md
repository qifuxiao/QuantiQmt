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
- `hard_limit_policy_hash` 是 `{hard_limit_policy_version, valuation_currency, system_hard_limits}` 的 RFC 8785 canonical SHA-256。该 policy 由安全治理的 immutable baseline 发布，不属于普通 hot config；ConfigService 只能引用当前 accepted policy，不能在 RuleSet candidate 中改值。hash 不匹配或 candidate policy 未被接受均以 `QQ-RISK-4007` 拒绝激活。
- RiskInput 的 `rule_set_version/rule_set_hash` MUST 分别等于传入 RuleSet 的 `rule_set_version/content_hash`，否则以 `QQ-RISK-4011` / `RISK_RULE_SET_VERSION_MISMATCH` 拒绝。
- Order `checksum` 对去掉自身 checksum 的 Order Snapshot 计算；其他 Snapshot 的 `metadata.checksum` 对去掉该 checksum 的完整 Snapshot 计算，算法同上。checksum 不匹配以 `QQ-RISK-4008` 拒绝。TIMEOUT/UNAVAILABLE Snapshot 的 `snapshot_version` 是 Snapshot builder attempt identity，checksum 覆盖 null data 和失败 quality，不能伪装成源数据版本。
- `decision_id` MUST 为 `uuid5(UUID("b5a6c3cc-2be0-5e6f-a9ec-2d9a4e769979"), input_version + ":" + content_hash)`；不得使用 UUID4。hash 校验失败时输出使用重新计算的实际 input/rule-set hash，不能以调用方声称的错误 hash 生成 identity。`semantic_decision_hash` 对 RiskDecision 去掉 `decision_id` 和自身 hash 后按上述 canonical JSON 计算。
- DTO 在构造后 MUST deep immutable；不得在一次决策中切换 `rule_set_version` 或任何 Snapshot version。

RiskDecision 的 `order_id/expected_order_version` MUST 等于 Input Order 的 `order_id/aggregate_version`；`input_version` 使用已验证或重新计算的实际 hash；`rule_set_version/rule_set_hash` 使用本次唯一 RuleSet；三个 `snapshot_states` 逐一记录 version、派生 quality、age 和对应 max age。Decision 不携带 business timestamp 或 latency，所有运行时测量只进入 RiskAuditOutput。

### V1 单一计价币种

V1 不支持跨币种求值或 FX 换算。`RiskInput.valuation_currency`、`RiskRuleSet.valuation_currency`、`account.currency`、`portfolio.base_currency` 和 `market.currency` MUST 是完全相同的 ISO 4217 三位大写代码。Order 的 `limit_price`、Market 的价格字段、Account 的全部金额字段、四个 scope metrics 的 exposure 字段，以及 `ORDER_NOTIONAL`，均以该唯一币种计价；`PROJECTED_LEVERAGE` 是无币种比率。

`system_hard_limits` 中 `max_order_notional`、`max_projected_gross_exposure`、`max_projected_net_exposure_abs`、`max_daily_loss` 的币种由 RuleSet 顶层 `valuation_currency` 唯一指定。金额 metric 的动态 `DECIMAL` limit 必须携带同一非 null `currency`；`PROJECTED_LEVERAGE` 的 `DECIMAL.currency` 必须为 null。Input 内部币种不一致以 `QQ-RISK-4008` 拒绝，RuleSet 内部 limit 币种不一致以 `QQ-RISK-4007` 拒绝，分别合法但 Input 与 RuleSet 的 `valuation_currency` 不一致以 `QQ-RISK-4011` 拒绝。实现不得直接比较不同币种的名义数字、不得自行读取汇率，也不得通过全部拒绝来代替这项确定性校验；未来支持跨币种必须发布新 RiskInput/RuleSet 契约，携带不可变、版本化 FX snapshot 和 Decimal 舍入规则。

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

### RiskRuleResult typed value

`measured_value` 和 `limit_value` 只允许 null 或下列带 `kind` 判别的值，禁止数字编码 boolean/string/set：

| kind | payload | canonical 规则 |
|---|---|---|
| `DECIMAL` | `value: decimal string`, `currency: ISO code \| null` | 金额 metric 的 currency 等于本次 `valuation_currency`；`PROJECTED_LEVERAGE` 为 null |
| `INTEGER` | `value: integer` | JSON integer，不转 decimal string |
| `BOOLEAN` | `value: boolean` | 只允许 JSON true/false |
| `STRING` | `value: string` | `INSTRUMENT_ALLOWED` measured 为 `order.instrument_id` |
| `STRING_SET` | `values: string[]` | 唯一且按 Unicode code point 升序，`INSTRUMENT_ALLOWED` limit 使用此类型 |

metric 与 typed value 的映射固定：`TRADING_ENABLED=BOOLEAN/BOOLEAN`；`INSTRUMENT_ALLOWED=STRING/STRING_SET`；`ORDER_QUANTITY`、`PRICE_DEVIATION_BPS`、`POSITION_QUANTITY`、`ORDER_COUNT_WINDOW`、`CANCEL_RATIO_BPS=INTEGER/INTEGER`；`ORDER_NOTIONAL`、`AVAILABLE_CASH`、`PROJECTED_GROSS_EXPOSURE`、`PROJECTED_NET_EXPOSURE_ABS`、`PROJECTED_LEVERAGE`、`DAILY_LOSS=DECIMAL/DECIMAL`。适用的 SYSTEM_HARD_LIMIT/SCOPED_RULE 必须记录非 null measured/limit；scope 不匹配的 NOT_APPLICABLE 可令 measured 为 null，但仍记录 typed limit。Synthetic validity/timeout 只有在该 guard 没有语义测量值或限额时才可使用 null，禁止以 null 隐藏已参与判断的值。

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

Runner 在每个确定性规则边界前后读取注入的 monotonic_ns，使用无溢出非负整数
`latency_us = (delta_ns + 999) // 1000` 向上换算，禁止 float 或 wall clock。
`start_ns` MUST 在本次 admission、worker/candidate 构造及聚合之前采样；
原始绝对 deadline 为 `start_ns + evaluation_timeout_us * 1000`，不得在阶段切换时重置。
规则、聚合、最终构造、Schema、semantics、deep freeze 和 caller handback 全部在预算内。
任一检查点 `ceil((now_ns-start_ns)/1000) >= evaluation_timeout_us` 即失去正常交付资格；
整数向上取整可能早于绝对 deadline 触发：3,999,001ns 在 4000us 预算下得到 4000us，MUST NOT PASS。
仅以原始纳秒差小于 4,000,000ns 放行不符合此契约。

audit 的 `sample_ns` 是聚合与 `evaluated_at` 获取完成后、最终 primitive candidate 构造之前的
一次采样；`evaluated_at` 由外层 Clock 注入 UTC business time，不参与 Decision hash。
`timeout_floor` 在 TIMEOUT_GUARD 时为 `evaluation_timeout_us`，其他 origin 为 0。
`total_latency_us = max(ceil((sample_ns-start_ns)/1000), sum(rule_timings[*].latency_us), timeout_floor)`。
逐规则独立 ceil 的和可能大于整体 ceil；该字段是带规则下界及 timeout floor 的采样审计值，
不是完整完成耗时，也不得宣称每个增量都来自原始测量。合成 timeout guard 自身仍有一条实际
构造边界的非负整数 timing。若正常 candidate 的 total 已达到预算，MUST 转入 timeout 选择，
不得为了维持 EVALUATOR/PASS 而 clamp、删 timing 或改变下界。

最终 candidate 固定后 MUST NOT 修改任何字段，包括 `evaluated_at`、timings 和 total。
正常与 timeout 输出都 MUST 完整经过 `primitive candidate → Draft 2020-12 Schema validation →
PORTS-RISK semantic validation → deep freeze`。禁止先验证后换时间/复制未验证字段，
禁止 validate/update-time/revalidate 循环。候选构造、最终验证及冻结的成本由独立完成测量覆盖。
`terminal_ns` 在 caller 选定唯一终态并作最终 handback 检查时采样；
`completion_latency_us = ceil((terminal_ns-start_ns)/1000)` 包含 admission、等待、聚合、构造、
全部最终验证、冻结以及失败 cleanup。`risk_evaluation_latency_us` MUST 等于有效 audit 的 total；
新增 `risk_completion_latency_us` 记录完整完成测量。两者不得混用，完整完成的 p99 目标仍为 4ms。
handback 检查之后不得再同步执行 observer、阻塞清理或输出构造；函数返回/raise 的固定路径仍
属于交付成本，未来运行时验收 MUST 测量调用方实际返回延迟，不能把 Python 调度开销排除以证明 NFR。

elapsed 达到预算时，即使当前 `next()`、聚合或最终验证尚未返回，caller MUST 停止等待正常
worker，撤销其交付资格并 fence late output。最多一次独立有界 cleanup 尝试构造
`decision_origin=TIMEOUT_GUARD` 的 REJECT，追加 `RISK.SYSTEM.EVALUATION_TIMEOUT`，
error=`QQ-RISK-4005`，保留截止选择时可验证的已完成 immutable prefix，丢弃未完成结果。
仅当完整验证链成功且 cleanup handback 未到其等待上限，才返回 timeout audit；否则按下述
无有效 audit 失败出口结束。cleanup 不延长正常 PASS 的原始绝对 deadline。
相同 input_version 不得重评，重试必须由 Application 明确决定并重建含新 evaluation_time 的
RiskInput，因此产生新 input_version/decision_id；异常本身不授权重试。

Runner 的成功返回 MUST 是有效的 `CONTRACT-RISK-AUDIT-OUTPUT-V1`：`decision` 是完整
RiskDecision；`evaluation_timeout_us` 等于本次 RuleSet 值。无有效 audit 时 MUST 抛出本地失败，
不保证每次调用都有 audit。RiskRuleResult 是确定性 Decision 的组成部分且不含 latency；
RuleTiming 是 Runner 测量值。逐规则审计视图是二者按复合 key 一对一 join 的结果，
不得把 `latency_us` 写回 RiskRuleResult 或语义 hash。

### 有限 worker、permit 与唯一终态

每个 Runner MUST 在启动时固定正整数 `max_in_flight` 个 normal worker，另有恰好一个
cleanup worker，独立 permit、零等待 backlog。normal 容量不足时只允许一次 cleanup admission，
不得为 normal pool 排队。cleanup 等待绝对上限为选择 cleanup 的 `selection_ns + 4_000_000`，
即最多 4000us；admission、candidate、验证、freeze 和 handback 均消耗此上限，进度不能续期。
这是失败收尾资源上限，不是新的 PASS 预算，亦不提高完整完成的 4ms NFR。
cleanup 容量不足、等待到期或已关闭立即返回本地失败，不排队、不重试、不递归 cleanup。

caller 独占一次调用的终态选择；normal/cleanup worker 仅提供带 attempt identity 的候选或异常。
在最终正常交付之前 MUST 再检查原始 deadline；在 cleanup 交付之前 MUST 检查 cleanup deadline。
同一时刻的预算到期优先于正常结果；一旦选择 timeout/failure，late PASS、late REJECT 或 late
exception 均不能改变 caller 结果或产生审计/OMS/Execution 副作用。已选定最终验证失败也不能
被随后 timeout 或 cleanup 替换。deadline 前发现的业务 REJECT 仍须经过完整验证链。

从 admission 到实际 worker 结束，permit MUST 始终归该 worker 所有；caller timeout、取消、
close 或 fence 不能释放正在运行的 worker permit。只有实际完成（含异常退出），或证明任务
尚未开始且已取消，才允许恰好一次释放。已 fence worker 仍计入容量，禁止 replacement；
不得利用新建 Runner、重建 executor 或隐藏队列规避阻塞 worker 上限。
完成规则的 immutable prefix 发布和读取必须有界、非等待；不可获得一致 prefix 时走
`RESULT_UNAVAILABLE` 本地失败，不拼接在运行对象。8192 条结果已满而需追加 timeout guard 时，
不得截断已完成结果或越过 Schema maxItems；cleanup 验证失败即走无有效 audit 出口。

宿主 MUST 固定正整数 Runner 总数和同时调用上限、零等待 backlog；计数包含已 retired/closed
但仍有活 worker 的 Runner。超限在入口 fail closed，不启动更多 worker。
shutdown 关闭 admission、fence 输出；有界 join 只允许在宿主控制路径，交易路径禁止 join。
未退出 worker 的资源和许可仍被宿主持有；宿主必须停止接收更多工作并由运维处理，不能循环
重建。CPython 调度、GIL 及任意扩展/observer 行为不提供硬实时或同进程强隔离保证；本规范的
容量与等待设计不能充当这些保证，后续 TASK-005 必须提供实际 deadline/阻塞边界证据。

### 无有效 audit 的本地失败接口

`RiskRunFailure` 是本地 Port 异常接口，不是新业务 DTO、Event、错误码或 Order 状态。
其只读属性为 `kind`、`original_exception`、`cleanup_exception`；无异常对象时为 None。
kind 的有限集合为 `ORIGINAL_FAILURE`、`RESULT_UNAVAILABLE`、`CLEANUP_CAPACITY`、
`CLEANUP_WAIT_EXHAUSTED`、`CLEANUP_WORKER_EXCEPTION`、`CLOSED`。
`original_exception` MUST 保留原异常对象及其 cause，不按异常名称/文本归类；包装的
`__cause__` 指向该原异常（若存在）。最终 Schema/semantics/freeze 异常被 caller 选中时，
kind 为 ORIGINAL_FAILURE，原样保留 first failure，禁止 repair/retry/fallback 或 timeout audit
替代；没有第二次 cleanup 验证机会。

cleanup 仅处理预算/normal admission 失败的 timeout 构造，不挽救已选中的输出验证异常。
cleanup 无 permit 为 CLEANUP_CAPACITY；caller 等待上限到期为 CLEANUP_WAIT_EXHAUSTED；
cleanup worker 实际抛出的任何异常，包括 builtin TimeoutError，均为 CLEANUP_WORKER_EXCEPTION，
并保存在 `cleanup_exception` 及其原 cause 中，不能混淆为 caller wait timeout。
若存在此前选定的原异常 MUST 同时保留，cleanup 故障不得覆盖它；没有原异常时不得伪造。
close 先于终态选择则为 CLOSED；终态选择后 close 不改结果。
本地故障不得映射到输入无效 `QQ-RISK-4008`；`QQ-RISK-4005` 仅用于有效 TIMEOUT_GUARD audit。

无有效 audit 时，OrderApplication MUST 保留已注册订单 identity/state 并显式处理故障；
MUST NOT 伪造 RiskDecision、自动迁移 OMS REJECTED、生成 v1 projection、持久化/发布 v1/v2、
应用 approved OMS transition 或进入 Execution。记录受控失败诊断，不能以虚假 risk event 填补。
不得由 builtin exception name/text 推断是否重试；本地 kind 也不构成自动重试权限。
权威 audit/Outbox 故障始终 fail closed，不受以下可丢遥测许可影响。

### 非等待遥测与下界诊断

`RiskTelemetry` 位于 observer adapter 边界。单个实例固定一个 consumer worker、一个 pending
slot、两个预分配 512KiB buffer；最多 8192 个 rule histogram 样本和四个 summary 样本
（evaluation histogram、completion histogram、decision counter、fail-closed counter）。
无有效 audit 时只允许 completion 和本地 fail-closed 样本，不能伪造 decision/rule 样本。
数值仅允许固定 8 byte unsigned uint64，metric/label 编码为固定 enum id；只有无高基数 label
的 latency、有限 decision/origin/error/reason 标签，禁止 rule_id 或任意字符串。
enum 表启动时冻结，decision/origin/error 使用现有契约枚举，local fail-closed reason 仅使用
上述 kind；禁止运行时注册标签。独立 loss counters 不占用/递归生成遥测样本。

producer MUST 先 try-only 取得空闲 buffer 与 pending reservation，再构造 batch；禁止先复制
audit、创建样本列表或编码无界整数/字符串。构造只写预留 buffer、有限索引和固定数量元数据，
每个 audit 最多一次入队，不保留 audit 引用，不在交易线程调用 observer。超出数值、条数或
encoded bytes 上限时整批 FULL drop；不得 clamp 权威审计值。normal worker/调用并发不能增加
buffer 数；正在构造、pending、consumer processing 都占用相应 reservation/buffer。

所有入口锁都是非嵌套、非等待的单次 try-lock，禁止 spin、retry 或递归 metrics。
无法取得 admission 锁为 CONTENDED；已关闭为 CLOSED；无 buffer/slot 或 oversize 为 FULL。
consumer 对已取走 batch 至多按编码顺序投递一次；observer 抛异常为 OBSERVER_EXCEPTION，
允许已有 prefix 样本发生副作用，丢弃其余样本，禁止重播整批或把已发送 prefix 撤销。
observer 阻塞时一直持有 consumer worker 和其 buffer，不新建替代 worker；最多再有一个
pending batch，其后 FULL。任意同进程 observer 可阻塞 GIL/耗尽自身资源，容量声明仅约束
adapter 所有的 worker/buffer，不能声称隔离任意 callback 的全部进程副作用。

每种 drop reason 有一个 uint64 饱和计数器：它计的是成功观察到的 batch loss 事件下界，
不是准确丢失样本数。更新仅尝试一次共享控制锁，必须在释放 admission/buffer 操作的锁后进行；
admission、closed 状态、计数及诊断快照共享该控制锁，每个操作单独取得且绝不重入或嵌套。
竞争时允许漏计且不再补记/重试，饱和于 `2**64-1` 并置对应 saturated 标志。
因此标识为 LOWER_BOUND；零下界不能证明零丢失，也不能证明 NFR 合规。
observer 异常可能只丢后缀，不能按整批样本数计作准确丢失；BUSY 与饱和都不能伪装成完整计数。

本地只读 `try_diagnostics()` 返回固定大小 immutable snapshot：`state=AVAILABLE` 时含
`semantics=LOWER_BOUND`、四个 `lower_bounds`、四个 `saturated` 与 `closed`；控制锁忙时只返回
`state=BUSY`，其余值缺失，禁止以零或旧值冒充新快照。AVAILABLE 仅保证本地已计入值的一致快照，
不保证未漏计。`closed` 表示 close 已完成，不是 observer 已退出；close 与统计 snapshot 在
同一控制锁下各自有界提交，无法取得锁时返回 BUSY，不能报告已关闭。

`close()` 是幂等 try-only 本地控制接口，返回 AVAILABLE（关闭完成）或 BUSY（未完成、无
关闭状态变更）；不得在方法内重试。其线性化点关闭 admission 并 fence 未提交 producer，
丢弃 pending batch（尝试一次 CLOSED 下界计数），不释放正在构造或 processing 的 buffer。
这些所有者实际结束时归还 buffer，已 fence producer 不得发布并尝试记录 CLOSED；已进入
observer 的样本副作用不可撤回，in-flight consumer 不开始剩余样本。控制方仅可在预先固定的
宿主 shutdown 期限内有界再次调用 BUSY 的 close，禁止交易路径等待或 join。
统计计数更新与关闭状态快照提交不得嵌套其他锁；close 只尝试一次控制锁，取得后完成固定大小
状态转移，BUSY 无部分关闭，不能通过阻塞锁获得该保证。关闭/异常也不允许销毁仍被 worker
使用的 buffer。

遥测降级 MUST NOT 改变已选终态或授权丢失权威 audit/Outbox；审计可用性、fail-closed 和
transaction 约束保持不变。新诊断/失败接口要求调用方适配和独立规范 Review；文本测试和
旧 bundle 测试不是未来 Runner、故障调度覆盖或性能验收。

### RiskAuditSemanticValidator

标准 Draft 2020-12 Schema 负责 RiskAuditOutput 字段、类型和局部结构；跨数组和跨字段不变量由规范性 `RiskAuditSemanticValidator.validate(audit: RiskAuditOutputV1) -> None` 强制执行。TASK-005 MUST 实现该 validator。Runner 生成完整 audit 后、生成 v1 compatibility projection 前、以及权威 v2 与兼容 v1 Outbox 写入前 MUST 调用它。任一检查失败 MUST fail-closed：不得修补、重排、去重或猜测 audit，不得生成 v1，不得持久化或发布 v1/v2，不得应用 approved transition 或进入 Execution。

Validator MUST 按以下顺序检查并在首个失败处拒绝：

1. `decision.rule_results` 非空，数组位置 `i` 的 `evaluation_index == i`，所有 `rule_id` 唯一；RuleSet 本身的 rule_id 唯一性仍由 RuleSet validator 在求值前保证。
2. `rule_timings` 数量严格等于 `rule_results` 数量；数组位置 `i` 的 `evaluation_index == i`，timing 的 `(evaluation_index, rule_id)` 必须逐项等于 result，不得 missing、duplicate、extra 或 unsorted。
3. `total_latency_us >= sum(rule_timings[*].latency_us)`，使用无溢出的非负整数求和。
4. `EVALUATOR` 与 `INPUT_GUARD`：不得存在 `phase=TIMEOUT_GUARD` 或 `rule_id=RISK.SYSTEM.EVALUATION_TIMEOUT`；`completed_rule_count == len(rule_results)`。EVALUATOR 可 PASS/REJECT；INPUT_GUARD 必须 REJECT。
5. `TIMEOUT_GUARD`：Decision 必须 REJECT 且 primary/error 分别为 `RISK_EVALUATION_TIMEOUT`/`QQ-RISK-4005`；唯一 timeout result 必须是最后一条，`phase=TIMEOUT_GUARD`、`rule_id=RISK.SYSTEM.EVALUATION_TIMEOUT`、`result=REJECT`、`reason_code=RISK_EVALUATION_TIMEOUT`；其 timing 必须存在并与其 index/id 匹配；`completed_rule_count == len(rule_results)-1`，明确只计 timeout 前已完成的确定性规则、不计 synthetic timeout guard；`total_latency_us >= evaluation_timeout_us`。

因此三种 origin 都为每条已发布 RuleResult 保存一条 RuleTiming；只有 TIMEOUT_GUARD 的 `completed_rule_count` 排除最后的 synthetic guard。任何 schema-valid 但未通过上述 validator 的对象都不是有效 RiskAuditOutput。

`risk.order_evaluated.v2` 的自包含 schema 是 `CONTRACT-RISK-AUDIT-OUTPUT-V1` 与 `CONTRACT-RISK-DECISION-V1` 的唯一机器字段源；两个内部契约通过 URN/JSON Pointer 引用它。Schema 与 `RiskAuditSemanticValidator` 共同构成机器可执行的完整 audit validity contract。Event envelope 的 `schema_version=2`，payload 内的 `schema_version=1` 表示 RiskAuditOutput DTO 版本，二者不得混淆。该 v2 事件按 `STORAGE-SOT` 作为 RiskDecision 的权威持久化审计事件；因此 typed measured/limit、完整 Decision 和独立 RuleTiming 均可无歧义复盘。权威 v2 与兼容 v1 Outbox record MUST 和 approved OMS transition 在同一事务持久化，二者成功前不得执行。

已发布的 `risk.order_evaluated.v1` schema 保持不变，仅作为兼容投影。Projection MUST 只接受已经通过 `RiskAuditSemanticValidator` 的 v2 audit；失败时不得生成 payload。顶层 identity/decision/rule_set 逐字段取 Decision；`snapshot_versions` 取三个 `snapshot_states.snapshot_version`；每个公开 `rule_results` 按已验证的相同数组位置及 `(evaluation_index, rule_id)` 投影 `rule_id/result/reason_code` 和对应 timing 的 `latency_us`，禁止重新搜索、猜测或容忍歧义。typed `DECIMAL` 投影其 `value` decimal string；`INTEGER` 仅在无前导零的十进制表示满足 v1 decimal pattern 时投影该 string，超出 v1 18 位范围时投影 null；`BOOLEAN`、`STRING`、`STRING_SET` 不能无损表示，必须投影为 null。measured/limit 各自独立按此规则投影，不得发明数值编码。V1 不再是完整权威审计，不承载 input hash、snapshot quality、phase/scope/priority、exception、total latency或 error code；消费者不得猜测这些缺失字段。不得向 v1 payload 添加 schema 未声明字段。

两个 Event envelope 的 `correlation_id=order.intent_id`、`causation_id` 为触发 Risk 的 OrderRegistered message id、`aggregate_id=order_id`、`aggregate_version=expected_order_version`、`partition_key=order_id`。为保留 v1 已发布 identity，v1 `message_id=decision_id`；v2 `message_id=uuid5(UUID("b5a6c3cc-2be0-5e6f-a9ec-2d9a4e769979"), decision_id + ":risk.order_evaluated.v2")`。OMS 只能在 `expected_order_version` 匹配时应用 Decision；冲突返回 `QQ-COMMON-1003`，重新读取后由 Application 明确决定是否以新 input_version 重评。

指标必须至少包含 `risk_evaluation_latency_us` histogram、`risk_rule_latency_us` histogram、`risk_decisions_total{decision,origin,error_code}` counter、`risk_fail_closed_total{reason}` counter。禁止使用 order/account/instrument/correlation 等高基数字段作为 metric label。

## Risk output runtime Schema bundle

`RuleResult`、`RuleTiming`、`RiskDecisionV1`、`RiskAuditOutputV1` 与
`risk.order_evaluated.v2` MUST 分别通过 `CONTRACT-RISK-RULE-RESULT-V1`、
`CONTRACT-RISK-RULE-TIMING-V1`、`CONTRACT-RISK-DECISION-V1`、
`CONTRACT-RISK-AUDIT-OUTPUT-V1` 和 `CONTRACT-CATALOG` 的 active message route，解析到同一份
`CONTRACT-RISK-ORDER-EVALUATED-V2` Schema graph。前四个内部身份只引用该 graph 的精确 root 或
JSON Pointer，不复制字段定义。

生产 runtime MUST 只从安装包 `quantiqmt.contracts.resources` 通过 `importlib.resources` 读取
版本化 bundle。bundle 暴露 validator 前 MUST 校验 bundle 格式、manifest version、Catalog route、
contract/path identity、content/document/bundle SHA-256 以及全部 `$ref`。缺失、损坏、partial、digest
不匹配、version 不匹配或 unresolved reference 均 fail closed；禁止读取 repository `spec/**`、cwd、
caller source root、旧版本、默认 payload 或宽松 fallback。

所有 output factory MUST 严格执行 `primitive candidate → Draft 2020-12 Schema validation →
PORTS-RISK semantic validation → deep freeze`。任一阶段失败时不得返回或冻结无效对象，也不得继续
v1 projection、v2 envelope、持久化/发布、approved OMS transition 或 Execution；不得 coercion、
repair、default、deduplicate、reorder、retry 或 fallback。checkout、installed wheel 与只安装主包的
container-equivalent 环境 MUST 使用相同 bundle bytes 并产生相同接受/拒绝结果。
