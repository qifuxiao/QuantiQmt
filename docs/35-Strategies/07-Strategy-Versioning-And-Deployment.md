# Strategy Versioning and Deployment

> Status: Proposed

## 策略制品

每个不可变制品包含：strategy_name/version、code artifact checksum、SDK version range、Python/依赖 lock hash、manifest、parameter schema、state schema、数据需求、owner、build id、测试报告和签名。

代码版本、参数版本和运行实例版本分别记录：

```text
strategy_code_version
parameter_set_version
strategy_instance_id
runtime_generation
```

任何决策、Target 和 OrderIntent 都携带这些关联信息。

## Manifest

声明输出模式、订阅、Timer、账户/标的 scope、是否允许做空、最大频率、资源预算、checkpoint schema、停止政策和必要平台能力。部署系统拒绝未声明或超权限能力。

## 环境晋级

```text
Development → Replay/Backtest → Simulation → Paper → Limited Live → Production
```

同一制品 checksum 晋级，禁止在环境之间手工修改代码。参数可以按环境使用独立批准版本，但必须留痕。

## 发布方式

- Shadow：消费实时数据但输出进入隔离 Sink，不产生订单。
- Canary：限定账户、资金、标的和时间窗口。
- Blue/Green：新旧 Runtime 均准备，仅一个 generation 有输出权限。
- Rollback：暂停新版本，恢复兼容 checkpoint 或启用旧版本；不回滚已发生交易事实。

## 状态迁移

state schema 变化必须提供纯函数迁移和 golden fixture。无法安全迁移时从明确初始状态启动，并由准入审批确认；不得忽略旧 checkpoint 字段。

## 供应链

生产只运行 CI 构建、签名并登记的制品。依赖漏洞、许可证、secret、动态下载和非确定构建检查必须通过。策略不得在运行时 pip install 或从网络加载未登记代码。
