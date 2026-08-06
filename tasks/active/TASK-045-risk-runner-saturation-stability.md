---
id: TASK-045
title: Stabilize RiskEvaluationRunner saturation concurrency
status: active
depends_on: [TASK-015]
spec_refs:
  - INV-RISK
  - PORTS-RISK
  - CONTRACT-RISK-AUDIT-OUTPUT-V1
  - NFR-RELIABILITY
allowed_paths:
  - src/quantiqmt/risk/runner.py
  - tests/unit/risk/test_risk_engine.py
  - tests/property/risk/test_risk_properties.py
  - tasks/active/TASK-045-risk-runner-saturation-stability.md
  - tasks/active/README.md
  - tasks/index.yaml
forbidden_paths:
  - spec/**
  - docs/**
  - migrations/**
  - .github/**
  - pyproject.toml
  - poetry.lock
  - src/quantiqmt/risk/model.py
  - src/quantiqmt/risk/audit.py
  - src/quantiqmt/risk/evaluator.py
  - src/quantiqmt/risk/__init__.py
  - tests/spec/**
  - tests/contract/**
verification:
  commands:
    - poetry run pytest tests/unit/risk tests/property/risk
    - poetry run pytest tests/unit tests/property tests/spec tests/contract --cov --cov-report=term-missing
    - poetry run mypy src/quantiqmt/risk
    - poetry run ruff check src/quantiqmt/risk/runner.py tests/unit/risk/test_risk_engine.py tests/property/risk/test_risk_properties.py
    - poetry run ruff format --check src/quantiqmt/risk/runner.py tests/unit/risk/test_risk_engine.py tests/property/risk/test_risk_properties.py
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

Eliminate the reproducible CI flakiness in `RiskEvaluationRunner` saturation handling while preserving the accepted fail-closed timeout and audit contracts.

## Trigger evidence

- PR #54 Head `655d142bca62a175f42232963ab6b62cf6d5265d` and PR #55 Head `fb9660f9995ad8cebaec580fea58b794a9576d79` each produced a `FlakyFailure` in `test_generated_timeout_saturation_does_not_invalidate_admitted_result`.
- In both failures, an already admitted evaluation unexpectedly returned `decision_origin=TIMEOUT_GUARD` after a concurrent second request was correctly rejected for saturation; authorized reruns passed without source changes.
- PR #54 and PR #55 changed only governance files, so they did not introduce or repair this Risk behavior.

## Required behavior

- A request that acquired the sole admission slot remains isolated from a later saturated request; the later request cannot alter the admitted attempt's generation, deadline, result, or admission ownership.
- A saturated request continues to fail closed with `TIMEOUT_GUARD` and cannot enter the evaluator.
- Admission is released exactly once on success, timeout, evaluator failure, and late completion; no permit leak or over-release is allowed.
- Timeout and audit semantics remain exactly those frozen by `PORTS-RISK` and `CONTRACT-RISK-AUDIT-OUTPUT-V1`.

## Non-goals

- No new Risk rule, DTO, Event, error code, state transition, public schema, or workflow behavior.
- No TASK-029 or TASK-005 implementation, activation, dependency change, or release authorization.
- No skip, xfail, retry wrapper, arbitrary sleep, or blanket timeout increase used to hide nondeterminism.
- No change to the bounded single-worker/single-in-flight contract or the existing input-version filter policy.

## Acceptance criteria

- [ ] The failure mechanism is reproduced and explained with an execution timeline showing admission, worker execution, saturation response, timeout fencing, and release ownership.
- [ ] Deterministic tests prove that a saturated second request returns `TIMEOUT_GUARD` without changing the already admitted request's final `EVALUATOR` result.
- [ ] Tests use explicit synchronization and bounded deadlines rather than scheduler-dependent sleeps or Hypothesis retries.
- [ ] Success, timeout, evaluator exception, saturation, and late-completion paths prove exactly-once admission release with no semaphore over-release or permit leak.
- [ ] Existing fail-closed timeout, semantic audit validation, metrics, bounded-state, and duplicate-input behavior remain unchanged and pass regression tests.
- [ ] The full CI-equivalent unit/property/spec/contract suite passes without rerunning a failed job.
- [ ] All modifications stay within `allowed_paths`; TASK-005 and TASK-029 remain blocked and no other task is activated.

## Review focus

- Verify the fix removes the scheduling race rather than merely widening wall-clock timeouts.
- Verify a late worker result cannot overwrite or invalidate another attempt.
- Verify semaphore ownership is local to the admitted attempt and released exactly once.
- Verify tests would fail against the pre-fix implementation for the identified reason.

## Risks and rollback

- Incorrect admission fencing could allow concurrent evaluation, leak capacity, or convert a valid result into a timeout audit.
- Roll back the implementation and tests together if deterministic concurrency guarantees cannot be proven; keep downstream Risk tasks blocked and release prohibited.
