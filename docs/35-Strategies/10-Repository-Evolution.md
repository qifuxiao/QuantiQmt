# Repository Evolution

> Status: Proposed

## 第一阶段：Monorepo

使用同一仓库但包边界严格分离。优势是 contracts 原子变更、统一 CI、回测/实盘契约测试和较低发布复杂度。CI 必须执行依赖规则，禁止 strategies 导入 trading_platform/infrastructure。

## 发布物分离

即使同仓库，也构建独立制品：

```text
quantiqmt-contracts
quantiqmt-strategy-sdk
quantiqmt-platform
strategy-<name>-<version>
```

Strategy Worker 镜像/环境只包含 SDK、contracts 和策略依赖，不包含 Broker 凭证与平台管理包。

## 拆仓条件

同时满足多项时考虑拆分：平台/策略团队独立、发布周期明显不同、多个策略团队使用平台、策略源码需要更严格权限、SDK 已稳定版本化、跨仓契约测试和私有包基础设施成熟。

## 目标多仓结构

```text
quantiqmt-platform
quantiqmt-contracts
quantiqmt-strategy-sdk
quantiqmt-strategies-<team>
```

通过私有包仓库和版本化消息连接。Contracts 变更先发布兼容版本，平台和策略在兼容窗口独立升级，禁止跨仓同步修改才能工作的破坏性发布。

## 不拆分的理由

拆仓库不会自动形成架构边界，反而可能增加版本地狱。只有包依赖、权限、进程、契约测试和制品治理已经成立，拆仓才有价值。
