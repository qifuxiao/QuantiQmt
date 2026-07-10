---
id: TASK-022
title: Complete Observability, Config, and Control L4 contracts
status: ready
depends_on: [TASK-014]
spec_refs: [INV-TRADING, INV-CONSISTENCY, INV-RISK, WF-CONFIG-ACTIVATION, NFR-OBSERVABILITY, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/state-machines/**, spec/nfr/**, tasks/backlog/TASK-022-observability-control-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结日志、指标、Trace、告警、配置激活、Kill Switch、system mode、leader/fencing 和 recovery barrier 的 L4 契约。

## Non-goals

- 不实现监控或控制面代码。
- 不接 Prometheus/Grafana/Alertmanager。
- 不修改交易状态机以绕过控制。

## Acceptance criteria

- [ ] 定义每条交易链路必须携带的 log/metric/trace 字段。
- [ ] 定义 P0/P1 告警、Runbook、critical lag 和 recovery barrier rules。
- [ ] 定义 config hot reload vs restart policy、version activation 和 rollback。
- [ ] 定义 Kill Switch、system mode、leader lease/fencing 和 stale token 行为。
- [ ] 为后续 Control/Observability implementation task 提供验收标准。

## Review focus

- 一笔交易能否从行情到成交完整还原。
- 控制面是否不能绕过 Risk/OMS/Execution。
- 告警是否避免高基数 label。

## Risks and rollback

- 观测不完整会让实盘事故不可复盘；控制面错误会直接影响交易安全。
