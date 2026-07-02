# PORTS-STRATEGY：策略 Port 契约

## StrategyRuntime

MUST 提供 load/start/pause/stop/checkpoint。只有 RUNNING generation 能输出 Target/OrderIntent；旧 generation 输出必须拒绝。Runtime MUST 限制 CPU、内存、回调 deadline、队列和输出频率。

## Strategy SDK

策略只接收只读 StrategyContext，通过 initialize/on_market/on_timer/on_order/on_trade/checkpoint/restore 参与运行。SDK MUST NOT 暴露 Broker、Repository、SQL、Redis 或通用网络客户端。

## TargetResolver

MUST 以 Target、版本化 Position/Account/Market snapshot、活动订单影响和 InstrumentSpec 为输入，输出确定性的 OrderIntent/NoAction/Rejected。相同 target_id 与输入版本必须产生相同 resolution；必须扣除活动订单 expected_delta。

## Dependency Rule

`strategies → strategy_sdk → contracts`。任何从 strategy 包到 trading_platform/infrastructure 的 import 都是架构违规。
