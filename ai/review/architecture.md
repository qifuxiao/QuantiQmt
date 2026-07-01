# Architecture Review

- [ ] 依赖方向符合 Domain/Application/Ports/Infrastructure。
- [ ] 变更未创造第二套 DTO/Event/Error/State 定义。
- [ ] Command 与 Event 语义没有混淆。
- [ ] Repository 以聚合为边界且无通用 SQL 泄漏。
- [ ] 外部 I/O 有 timeout、错误翻译和资源上限。
- [ ] 队列、缓存、重试和并发有界。
- [ ] Live/Backtest 共享契约，不共享不现实假设。
- [ ] 公共行为有版本、兼容性和迁移路径。
- [ ] allowed_paths 内无任务外重构。
