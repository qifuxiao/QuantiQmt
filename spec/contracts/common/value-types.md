# CONTRACT-VALUE-TYPES：Shared Kernel 值对象

## Identifier

- MUST 使用规范小写 UUID 字符串作为内部 ID；V1 生成算法为 UUID4。
- MUST 在构造时验证格式；相同文本具有值相等和稳定 hash。
- MUST NOT 把数据库自增 ID、Broker ID 或策略名称混作内部 ID。
- Broker/client/trade ID 是独立受限字符串值对象，不假设 UUID。

## InstrumentId

- 是规范化、不透明、区分大小写的字符串，长度 1–64。
- Domain 不解析供应商代码；Reference Data/Gateway 负责供应商代码映射。
- 同一证券只有一个内部 InstrumentId，映射按 trading_day/version 管理。

## Currency

- 使用大写 ISO-4217 三字符代码；首版必须支持 CNY。
- 不同 Currency 的 Money 禁止直接加减或比较大小，除非显式通过版本化 FX Rate 转换。

## Decimal 规则

- 输入只接受 Decimal、int 或规范十进制字符串；MUST NOT 接受 float。
- 禁止 NaN、Infinity、负零和指数形式序列化。
- JSON 使用普通十进制字符串，不丢 trailing semantic scale。
- 中间计算使用局部 Decimal context，不修改进程全局 context。

## Money

- 字段：amount、currency。
- amount 最大 8 位小数；具体记账 scale 由 Currency/BusinessType 配置。
- 会计分录量化使用显式 rounding policy；默认 `ROUND_HALF_EVEN`。
- Money 乘除必须返回明确类型，禁止隐式与 Price 互换。

## Price

- 必须有限且大于零；最多 8 位小数。
- 下单前必须符合 InstrumentSpec.tick_size；Domain 值对象不自行猜测 tick。
- Price×Quantity 的结果是 Money，需要显式 currency 和量化规则。

## Quantity

- 首版证券交易 Quantity 是非负整数；Order quantity 必须大于零。
- 有符号持仓变化使用 PositionDelta，不能用负 Order Quantity。
- lot_size 取整默认向零；不足最小单位产生 NoAction/Dust，而非四舍五入扩大风险。
- 未来支持小数资产时发布新 Quantity 契约版本，不改变 V1 含义。

## Ratio / Weight

- 使用 Decimal；是否允许负数和大于 1 由 Strategy Mandate 决定。
- 普通多头 TargetWeight 默认范围 `[0, 1]`，组合合计和现金 buffer 由 TargetResolver 校验。

## 时间

- Business timestamp 必须是 UTC aware datetime；JSON 使用 ISO-8601 `...Z`。
- TradingDay 是交易日历给出的 `YYYY-MM-DD`，不能由 UTC 日期推断。
- 延迟测量使用 monotonic_ns，不能与业务时间比较。

## Clock Port

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...
```

Domain 禁止直接调用 datetime.now、time.time 或 time.monotonic。LiveClock 与 VirtualClock 必须通过同一契约测试。

## 序列化与日志

- 值对象序列化必须稳定、可往返且与 JSON Schema 一致。
- `str()` 用于规范机器表示；面向用户格式化使用单独 Presenter。
- Secret、账户敏感值不属于 Shared Kernel 通用值对象。
