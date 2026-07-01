# Python 技术基线

> Status: Proposed

## 运行时

- 生产基线使用 CPython 3.12，锁定 patch 版本；升级 minor 版本必须通过全量契约、性能和恢复测试。
- 依赖使用 lockfile 固定直接与传递版本；构建产物可复现并生成 SBOM。
- Domain 使用标准库 `dataclasses(frozen=True, slots=True)`、Enum、Protocol 和 Decimal；边界校验可使用 Pydantic，但 Pydantic 模型不能成为领域实体。
- 所有公开接口和消息模型必须有严格类型标注；CI 运行静态类型检查。

## 数值与时间

- 资金、价格、费用禁止使用 float 做最终判断或结算。Adapter 在边界转换为 Decimal/整数 tick。
- Decimal context、舍入模式、货币 scale 和最小价格变动由 InstrumentSpec 统一定义。
- Domain 不能直接调用 `datetime.now()`、`time.time()`；通过 Clock Port 获取时间。
- 延迟测量使用单调时钟，业务时间使用 UTC aware datetime。

## 并发选择

| 场景 | 机制 |
|---|---|
| 网络、Redis、DB I/O | asyncio 或专用 I/O 线程，必须有 timeout |
| QMT SDK 回调 | SDK 管理线程 + 最小复制 + 非阻塞有界入队 |
| OMS 状态推进 | 单写者事件循环，禁止线程并发修改聚合 |
| CPU 密集策略/模型 | 独立进程或外部计算服务 |
| 轻量纯计算 | 当前线程直接调用 |
| 日志/指标导出 | 独立有界队列和 Worker |

GIL 意味着线程不用于扩展 CPU 密集计算。不得在 asyncio event loop 中调用同步 Broker/数据库接口；必须经专用线程/进程 Adapter 并设置预算。

## IPC 与序列化

- 跨进程使用版本化 Message Envelope；默认 JSON 便于审计，性能测试证明必要时可采用 MessagePack/Protobuf，但逻辑契约不变。
- 禁止 pickle 接收不可信或跨版本持久化数据。
- 大块历史数据可使用 Arrow/shared memory，但只传不可变批次和句柄；生命周期、checksum 和泄漏监控必须明确。
- 热路径避免反复 model↔dict↔JSON 转换；每个边界最多一次编码和一次解码。

## 异常与资源

- 禁止裸 `except:` 和捕获后静默继续；异常在边界翻译为统一错误模型。
- 所有外部调用必须有 timeout、取消处理和资源关闭。
- 队列、Task、线程池、连接池、缓存均必须显式配置上限。
- 后台 Task 必须被 TaskGroup/Supervisor 持有，异常不可成为无人观察的 task exception。

## 包与依赖

领域包不得依赖 infrastructure。每个限界上下文暴露 `domain/application/ports`，Adapter 位于 infrastructure，启动装配位于 bootstrap。禁止全局 service locator 和可变 singleton。

## 性能纪律

- 优化前先 profiling；基准测试固定数据、硬件、Python 与依赖版本。
- 行情对象使用 slots/批处理/预分配时必须有数据证明收益。
- 不在热路径创建高基数日志、深拷贝完整 OrderBook 或逐 Tick 执行数据库查询。
- 任何本地 C 扩展/NumPy 优化都必须保留纯 Python 契约测试，且明确线程安全性。
