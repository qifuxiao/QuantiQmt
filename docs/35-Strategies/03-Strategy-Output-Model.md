# Strategy Output Model

> Status: Proposed

策略输出表达投资目标，不代表交易平台已经批准。支持三种模式，策略 manifest 必须声明允许模式，不得在同一 instrument/decision 中混用冲突模式。

## TargetWeight

适用于资产配置、ETF 轮动、多因子和定期调仓。

```text
target_id, strategy_id, portfolio_scope, instrument_id,
target_weight, effective_at, valid_until, decision_id,
price_reference, constraints, reason_code
```

`target_weight` 的范围由策略 mandate 决定；普通多头策略为 `[0,1]`。同一 portfolio_scope 的目标权重总和、现金保留和杠杆必须满足 mandate。

## TargetPosition

适用于趋势、固定仓位和明确数量目标。

```text
target_id, strategy_id, account_scope, instrument_id,
target_quantity, effective_at, valid_until, decision_id,
constraints, reason_code
```

TargetPosition 是最终期望净数量，不是“再买多少”。重复提交相同 target_id 不会重复交易。

## OrderIntent

适用于网格、套利、事件驱动和执行时点敏感策略。

```text
intent_id, strategy_id, account_id, instrument_id,
side, position_effect, quantity, order_type, limit_price?,
time_in_force, valid_until, decision_id, execution_constraints
```

OrderIntent 仍需 OMS 注册和统一 Risk。策略不能指定 Broker 凭证、绕过限速或要求平台忽略风控。

## CancelIntent

只允许撤销该策略拥有或被授权管理的订单，字段为 `cancel_intent_id, strategy_id, order_id, reason_code, valid_until`。平台验证所有权、幂等和订单状态。

## 选择规则

| 场景 | 首选输出 |
|---|---|
| 目标组合/周期调仓 | TargetWeight |
| 单标的目标仓位 | TargetPosition |
| 精确价量和时效要求 | OrderIntent |
| 撤销活动订单 | CancelIntent |

如果 Target 模型能够表达需求，不应使用 OrderIntent。Target 模型更容易处理当前持仓、活动订单、资金分配和部分成交。

## 通用约束

- 每个输出带 strategy_id/version、decision_id、input_event_id、生成时间和有效期。
- 过期输出不执行并产生审计事件。
- 数值遵守 Decimal/Quantity 规则；不得使用 NaN、Infinity 或隐式 float。
- 输出通过 schema、权限、mandate、频率和重复检查后才能进入 TargetResolver/Order Application。
