# Responsibility matrix (TASK-031 baseline)

This is a governance record, not a business implementation. Rows describe the current ownership boundary, evidence state, gaps and suggested follow-up work; suggested tasks are not activated by TASK-031.

| Flow / boundary | Owner | Current status | Gap or safety concern | Suggested follow-up |
| --- | --- | --- | --- | --- |
| OrderIntent → OMS registration | Order/OMS team | contract accepted; implementation evidence separately audited | registration/idempotency evidence must remain the single entry into execution | TASK-032 (suggested) |
| OMS → Risk | Risk integration owner | TASK-005 blocked; TASK-029 blocked | activation depends on completed prerequisites and runtime validator evidence | TASK-029 after TASK-031 review (suggested) |
| Risk → Outbox | Risk + persistence owners | contracts exist; historical delivery evidence is unverified where noted | atomic persistence and semantic audit evidence must be independently linked | TASK-033 (suggested) |
| Outbox → Execution | Execution owner | contract boundary recorded | UNKNOWN external outcomes require reconciliation, not blind retry | TASK-034 (suggested) |
| Inbox / Event Backbone | Messaging owner | responsibility recorded; implementation gap | deduplication, lease and replay evidence needs bounded operational policy | TASK-035 (suggested) |
| Broker report ingress | Broker integration owner | boundary only | report authenticity, ordering and UNKNOWN reconciliation need a dedicated review | TASK-036 (suggested) |
| Strategy runtime | Strategy owner | TASK-016 contracts accepted; TASK-008 not released | strategy event activation and market readiness remain open | TASK-037 (suggested) |
| Market data / snapshot | Market owner | boundary only | snapshot freshness, version and backtest/live parity require explicit readiness evidence | TASK-038 (suggested) |
