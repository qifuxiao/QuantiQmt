---
id: TASK-002
title: Implement versioned message contracts
status: completed
depends_on: [TASK-001, TASK-011]
spec_refs: [CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ORDER-INTENT-V1, CONTRACT-STRATEGY-TARGET-V1, CONTRACT-BROKER-TRADE-V1, CONTRACT-ORDER-STATUS-V1, CONTRACT-CANCEL-ORDER-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-LEDGER-TRADE-POSTED-V1, CONTRACT-PORTFOLIO-POSITION-CHANGED-V1]
allowed_paths: [src/quantiqmt/contracts/**, tests/contract/messages/**]
forbidden_paths: [src/quantiqmt/oms/**, src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/contract/messages", "poetry run mypy src/quantiqmt/contracts"]
---

# Objective

依据 JSON Schema 实现不可变 DTO、编码/解码和 golden fixtures。

## Acceptance criteria

- [x] 所有必填、枚举、Decimal string、UTC 和 additionalProperties 规则一致。
- [x] valid/minimal/maximal/invalid/unknown-enum fixtures 通过。
- [x] 编码往返不损失精度，未知 schema version 明确失败。
- [x] 未修改 spec Schema 以迁就实现。

## Evidence

- Schema Registry routes are derived from active Contract Catalog entries and deep-frozen.
- Payload and Envelope construction is factory-only, schema validated and deeply immutable.
- Runtime validation covers required/additional fields, enums, RFC3339, UUID, oneOf/allOf/if/then and explicit unknown versions.
- Twelve message directories contain 75 deterministic disk fixtures, including minimal, maximal, precision, unknown-enum and conditional failures.
- Maximal fixtures include all optional fields, maxLength boundaries and eight-digit Decimal semantic scale.
- Official jsonschema validation is cross-checked against runtime acceptance.
- Independent Review result: `APPROVE`; no P0-P3 findings after correction rounds.
- `poetry run pytest tests/contract/messages`: passed, 139 tests.
- `poetry run pytest`: passed, 213 tests.
- `poetry run mypy src tests`: passed.
- `poetry run ruff check .`: passed.
- `poetry run ruff format --check .`: passed.
- `poetry run python scripts/validate_specs.py`: passed.
- No forbidden-path changes, unverified criteria, known risks, or spec deviations.
- Merged to `main` as PR #8 (`6d2b2ce`) on 2026-07-06.
