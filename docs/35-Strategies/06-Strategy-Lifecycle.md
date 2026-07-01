# Strategy Lifecycle and Runtime

> Status: Proposed

状态机以 [State Machine Catalog](../30-Trading/State-Machine-Catalog.md) 为准。本文规定每个阶段的动作和 Guard。

| 状态 | Runtime 行为 | 禁止 |
|---|---|---|
| CREATED | 加载 manifest/artifact metadata | 消费市场、输出目标 |
| INITIALIZING | 校验 SDK/参数/权限、加载 checkpoint | 连接 Broker |
| READY | 订阅完成、快照有效，等待 enable | 产生交易输出 |
| RUNNING | 串行处理事件并允许输出 | 超 scope 输出 |
| PAUSED | 保持 checkpoint/订单订阅，不处理新交易决策 | 新开仓输出 |
| ERROR | 隔离异常并告警 | 自动静默恢复 RUNNING |
| STOPPING | 停止输入、刷新 checkpoint、执行停止政策 | 丢弃未记录状态 |
| STOPPED | 释放资源 | 接收回调 |

## 启动 Guard

进入 RUNNING 前必须满足：artifact/manifest 签名有效、SDK 兼容、参数版本激活、Checkpoint 可恢复、行情和账户/组合快照新鲜、系统 NORMAL/允许的 DEGRADED、交易日历有效、策略 mandate 和限额加载完成。

## 暂停原因

人工暂停、行情 stale、处理超时、队列积压、连续异常、快照不一致、策略日损、配置版本不匹配或平台 SAFE。原因和状态变化必须持久化。

## 资源预算

每个 Worker/策略配置 CPU、内存、回调 deadline、最大队列、最大输出频率、日志速率和 checkpoint 大小。超限先暂停策略；不能让 Runtime 用无限重试拖垮平台。

## Checkpoint 时机

定时、状态变化、交易日关闭和优雅停止时生成。Checkpoint 提交与输入位置协调，恢复允许重复消费但不允许遗漏；策略事件处理必须幂等。

## 停止政策

`KEEP_POSITIONS`、`CANCEL_OPEN_ORDERS`、`REDUCE_TO_ZERO` 或 `TRANSFER_TO_MANUAL`。政策是审批配置；Runtime 仅发出意图，OMS/Risk 仍执行所有动作。

## 热升级

默认先 PAUSED→checkpoint→启动新版本 shadow restore→验证→切换；禁止两个版本同时拥有相同 strategy instance 的交易权限。切换使用 generation/fencing，旧 generation 输出被平台拒绝。
