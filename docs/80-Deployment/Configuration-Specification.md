# Configuration Specification

> Status: Proposed

## 配置分类

| 配置域 | 示例 | 变更方式 | 生效点 | 回滚 |
|---|---|---|---|---|
| Risk Rules/Limits | 单笔、仓位、日损、频率 | Hot Reload + 审批 | 新 OrderIntent 边界 | 激活上一版本 |
| Kill Switch/System Mode | 全局/账户/策略开关 | 实时控制命令 | 持久化后立即 | 需恢复审批 |
| Strategy Parameters | 窗口、阈值、目标权重 | Hot Reload/重启按策略声明 | Bar/Tick 安全边界 | 上一参数版本 |
| Subscription | symbols、depth | Controlled Hot Reload | Gateway 确认订阅后 | 恢复旧集合 |
| Alert Thresholds | latency、queue、error rate | Hot Reload | 下个评估周期 | 上一版本 |
| Broker Endpoint/Credentials | endpoint、account、secret ref | Restart | 进程启动 | 重启旧版本 |
| Redis/PostgreSQL | URL、pool、TLS | Restart | 进程启动 | 重启旧版本 |
| Process/Queue Size | worker、queue、batch | Restart | 进程启动 | 部署回滚 |
| Schema/Serialization | message version | 发布迁移 | 兼容窗口 | 版本化回退 |
| Trading Calendar/Instrument | session、tick size、lot | 版本激活，通常盘前 | 指定 trading_day | 激活前版/停机 |

## 配置结构

每个配置包含 `config_id, scope, version, schema_version, effective_from, expires_at?, created_by, approved_by?, checksum, payload`。Secret 仅保存 secret reference，不保存明文。

## 热更新协议

1. Propose：创建不可变候选版本。
2. Validate：Schema、业务范围、交叉约束和权限检查。
3. Prepare：所有必要组件加载但不启用。
4. Activate：ConfigService 持久化唯一 active version 并发布事件。
5. Swap：组件在安全边界原子替换 immutable snapshot。
6. Acknowledge：上报实际版本；不一致触发告警/回滚/SAFE。

一次订单风险决策只能使用一个 rule_set_version；热更新不能改变处理中订单的规则版本。是否对活动订单重新评估必须由单独 Workflow 明确触发。

## 环境与优先级

优先级从低到高：代码安全默认值 → 环境配置 → 部署实例配置 → 版本化动态配置 → 紧急控制命令。高优先级只能覆盖允许字段；Secret、schema 和安全下限不可被普通动态配置覆盖。

## 校验与安全

- 启动时未知字段默认失败，不能静默忽略拼写错误。
- 风控上限必须有系统硬上限；普通用户不能通过配置突破。
- Broker 账户、环境和 endpoint 交叉校验，防止测试策略连接生产账户。
- 所有变更记录 diff、操作者、审批、原因、时间和组件 ACK。
- 配置日志脱敏；Secret 通过受控 Provider 获取并支持轮换。

## 配置失败

候选版本校验失败不影响当前 active version。部分组件 Prepare/ACK 失败时禁止激活，或按配置域进入 SAFE；不得让同一交易链中的 OMS 和 Risk 长期运行不同版本。
