# PORTS-STRATEGY：策略 Port 契约

## StrategyRuntime

MUST 提供 load/start/pause/stop/checkpoint。只有 RUNNING generation 能输出 Target/OrderIntent；旧 generation 输出必须拒绝。Runtime MUST 限制 CPU、内存、回调 deadline、队列和输出频率。

### StrategyContext (CONTRACT-STRATEGY-CONTEXT-V1)

`StrategyContext` 是只读 DTO，包含策略身份/版本、单调递增 `generation`、`LIVE` 或 `BACKTEST` 模式、不可变 market/account/portfolio snapshot 版本、最小权限 scope 和 `as_of`。Live 不得暴露未来数据；Backtest 必须有有限的 backtest end，并拒绝读取 end 之后的数据。同一 snapshot version 与查询在两种模式下必须得到相同值。SDK 不得暴露可变 Repository、系统时钟、Secret、Broker、SQL、Redis 或网络客户端。

### Callback 与 deadline (CONTRACT-STRATEGY-CALLBACK-V1)

`initialize`、`on_market`、`on_timer`、`on_order`、`on_trade` 均使用 CONTRACT-STRATEGY-CALLBACK-V1 envelope，带 callback id、generation、context snapshot 和绝对 deadline。Runtime 按策略串行派发，拒绝过期或重复 callback；超时转为有界 Runtime failure。输入不可变，callback 不得修改 OMS 或外部状态。

### Output 与 generation fencing (CONTRACT-STRATEGY-OUTPUT-V1)

只有 RUNNING generation 且拥有 `EMIT_TARGET` 或 `EMIT_ORDER_INTENT` scope 才能输出。Runtime 先做 schema 校验，再执行 output id、频率、队列和 generation fencing；旧 generation 必须拒绝。Target 只能交给 TargetResolver，OrderIntent 必须符合已发布 command contract，并仍需 OMS 注册与 Risk。策略不得直接调用 Broker、OMS、Repository 或 Execution port。

### Checkpoint (CONTRACT-STRATEGY-CHECKPOINT-V1)

Checkpoint envelope 包含 strategy/version/generation、schema version、captured timestamp、opaque payload 和 canonical payload bytes 的 SHA-256。Canonicalization 固定采用 RFC 8785 JCS：对象键按 Unicode code point 排序、无空白、UTF-8 无 BOM、Unicode scalar 与 RFC 8785 number serialization；hash 输入只包含 payload 值，不包含 envelope 或 payload_sha256。Restore 对缺失、不支持、格式错误、checksum/version 不匹配或过期 generation 必须 fail-closed；恢复原子失败时保持 PAUSED 或 ERROR，不能恢复输出。重复 checkpoint 与 callback id 必须幂等忽略。

### Runtime 限制、失败与审计

Runtime 必须配置有限 CPU、内存、callback deadline、队列深度和输出频率。资源超限、callback 异常、无效输出、依赖过期或 checkpoint 失败必须写入带 correlation_id 的 `strategy.state_changed.v1` 审计事件：可恢复故障转 PAUSED，完整性/安全故障转 ERROR。Resume 需要新鲜 approved context、已验证 checkpoint/dependencies 和新 generation；worker failure 不得改变 OMS 订单。

## Strategy SDK

策略只接收只读 StrategyContext，通过 initialize/on_market/on_timer/on_order/on_trade/checkpoint/restore 参与运行。SDK MUST NOT 暴露 Broker、Repository、SQL、Redis 或通用网络客户端。

## TargetResolver

MUST 以 Target、版本化 Position/Account/Market snapshot、活动订单影响和 InstrumentSpec 为输入，输出确定性的 OrderIntent/NoAction/Rejected。相同 target_id 与输入版本必须产生相同 resolution；必须扣除活动订单 expected_delta。

## Dependency Rule

`strategies → strategy_sdk → contracts`。任何从 strategy 包到 trading_platform/infrastructure 的 import 都是架构违规。
