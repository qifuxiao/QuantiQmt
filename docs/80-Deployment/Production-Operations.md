# 部署、配置与生产运维

> Status: Proposed

## 环境

`development/paper/staging/live` 使用相同构建产物，只通过版本化配置和凭证切换。Live 凭证不得出现在代码库、镜像、日志或普通配置文件中。

## 配置

配置分为静态启动项和动态业务项。风控限额、交易开关等动态配置必须有 schema、版本、审批人、激活时间、适用范围、回滚版本和审计记录；更新采用 prepare/validate/activate，不允许部分实例悄然使用不同版本。

## 进程监督

每个进程由 Supervisor/容器运行时管理，配置 readiness、liveness、优雅停止和资源上限。自动重启有速率限制；反复崩溃进入 Failed 状态并告警，避免重启风暴。

优雅停止顺序：停止新意图 → 等待/取消策略任务 → 刷新关键消息 → 保存 checkpoint → 释放 Leader lease → 关闭 Broker 连接。超时后强制退出也必须在下次启动执行完整对账。

## 发布

- 数据库迁移遵循 expand/migrate/contract，先保证前后版本兼容。
- 事件 schema 只做向后兼容新增；破坏性变化发布新版本消息。
- Trading Core 不做未经验证的全量同时升级；使用 Paper/Staging、影子流量或主备切换。
- 发布前检查配置、时间同步、磁盘、依赖、Broker 权限和 Kill Switch。
- 发布后检查订单 UNKNOWN、队列、延迟、拒单率和对账差异。

## 安全

控制面采用最小权限和角色分离；策略进程没有 Broker 凭证。高风险操作（解除 Kill Switch、账务调整、强制订单修复）需要二次确认，可选双人审批。所有网络连接加密，密钥定期轮换。

## 备份与灾备

PostgreSQL 执行全量备份和 WAL/PITR，并定期做恢复演练；Redis 不作为灾备事实来源。灾备文档必须记录 RTO/RPO、Broker 会话接管限制、备用环境配置、DNS/网络依赖及联系人。未演练的备份不视为可恢复能力。

## 开发前准入清单

测试矩阵和生产阶段门禁见 [../90-Quality/Test-And-Production-Acceptance.md](../90-Quality/Test-And-Production-Acceptance.md)。

- 所有 Proposed 架构决策完成评审。
- 核心 Command/Event schema 与错误码冻结首版。
- OMS 状态迁移表、风控 fail-open/closed 表完成。
- 故障矩阵、恢复和对账用例可转成自动测试。
- SLO、容量模型和基准测试方案明确。
- 安全模式、Kill Switch 与人工 Runbook 明确。
