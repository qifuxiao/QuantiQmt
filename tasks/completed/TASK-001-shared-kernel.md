---
id: TASK-001
title: Implement immutable shared value types
status: completed
depends_on: [TASK-000]
spec_refs: [INV-CONSISTENCY, NFR-PERFORMANCE, CONTRACT-VALUE-TYPES]
allowed_paths: [src/quantiqmt/shared/**, tests/unit/shared/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/oms/**]
verification:
  commands: ["poetry run pytest tests/unit/shared", "poetry run mypy src/quantiqmt/shared"]
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: unverified
  review_status: reported_unverified
  release_status: prohibited
  remediation_task: TASK-031
  completion_evidence: {mode: historical_evidence_unverifiable, change_pr: unverifiable, reviewed_head_sha: unverifiable, review_verdict: reported_unverified, reviewer: unverifiable, evidence_url: unverifiable, merge_commit_sha: unverifiable, human_authorization_evidence: TASK-031 governance recovery authorization}
---


# Objective

实现不可变 ID、Money、Price、Quantity、InstrumentId、UTC 时间辅助类型和 Clock Protocol。

## Non-goals

- 不实现订单、事件总线、数据库或 Broker。

## Acceptance criteria

- [x] Money/Price 不接受 float 构造。
- [x] 金额运算显式 currency/scale/rounding。
- [x] 时间值必须带时区；延迟使用 monotonic clock。
- [x] 类型不可变、可比较、可序列化并覆盖边界测试。
- [x] 不导入 Infrastructure 依赖。

## Evidence

- Implementation commit `b636c46` only modifies `src/quantiqmt/shared/**` and `tests/unit/shared/**`.
- Task activation metadata is isolated in preceding commit `a94904f`.
- `LiveClock` and `VirtualClock` pass the same parameterized Clock contract test.
- `poetry run pytest tests/unit/shared`: passed, 70 tests.
- `poetry run pytest`: passed, 74 tests.
- `poetry run mypy src tests`: passed.
- `poetry run ruff check src tests`: passed.
- `poetry run ruff format --check src tests`: passed.
- `poetry run python scripts/validate_specs.py`: passed.
- Independent Re-Review result: `APPROVE`; no P0-P3 findings.
- No unverified acceptance criteria, known risks, or spec deviations.
- Merged to `main` as PR #2 (`baed630`) on 2026-07-02.
