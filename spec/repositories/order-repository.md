# REPO-ORDER：Order Repository 契约

聚合边界为 Order。Repository MUST 提供 get(order_id)、get_by_intent(intent_id)、save(order, expected_version)。

## 约束

- `intent_id`、`client_order_id` 唯一。
- save 使用乐观并发；版本冲突返回 QQ-COMMON-1003，不覆盖后写。
- Order Journal 以 `(order_id, aggregate_version)` 唯一并只追加。
- 聚合更新、Journal 和 Outbox 在同一事务提交。
- Repository MUST NOT 暴露通用 SQL 或返回 ORM 持久化对象给 Domain。
- 外部 Broker 调用 MUST NOT 位于数据库事务内。

## 恢复

加载有效 checksum 的最近 Snapshot，再重放更高 aggregate_version 的 Journal。Snapshot 无效时从完整 Journal 重建。
