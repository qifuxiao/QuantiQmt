---
id: TASK-001
title: Implement immutable shared value types
status: active
depends_on: [TASK-000]
spec_refs: [INV-CONSISTENCY, NFR-PERFORMANCE, CONTRACT-VALUE-TYPES]
allowed_paths: [src/quantiqmt/shared/**, tests/unit/shared/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/oms/**]
verification:
  commands: ["poetry run pytest tests/unit/shared", "poetry run mypy src/quantiqmt/shared"]
---

# Objective

实现不可变 ID、Money、Price、Quantity、InstrumentId、UTC 时间辅助类型和 Clock Protocol。

## Non-goals

- 不实现订单、事件总线、数据库或 Broker。

## Acceptance criteria

- [ ] Money/Price 不接受 float 构造。
- [ ] 金额运算显式 currency/scale/rounding。
- [ ] 时间值必须带时区；延迟使用 monotonic clock。
- [ ] 类型不可变、可比较、可序列化并覆盖边界测试。
- [ ] 不导入 Infrastructure 依赖。
