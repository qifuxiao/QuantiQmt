---
id: TASK-045
title: Stabilize RiskEvaluationRunner saturation concurrency
status: completed
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
  - tasks/completed/TASK-045-risk-runner-saturation-stability.md
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
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_independent_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/57
    reviewed_head_sha: 4b252aae29f120611b9b9773e8e8ef3935c85218
    review_verdict: APPROVE
    reviewer: qifuxiao
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/57#pullrequestreview-4873377772
    merge_commit_sha: 7a39d1a0cad5455b2df0043a9449d4c4da2c36b5
    ci_evidence: >-
      Reviewed Head 4b252aae29f120611b9b9773e8e8ef3935c85218 passed 4/4 GitHub CI:
      quality jobs 92577541060 and 92577528619; persistence-postgresql jobs 92577541110
      and 92577528618.
    human_authorization_evidence: >-
      2026-08-06 human authorization: 授权将
      tasks/completed/TASK-045-risk-runner-saturation-stability.md 精确加入 TASK-045
      allowed_paths；仅用于记录 PR #57 的正式 Review、CI 与 merge evidence，并执行
      TASK-045 active→completed 收尾迁移。不得激活或解锁其他业务任务。
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

- [x] The failure mechanism is reproduced and explained with an execution timeline showing admission, worker execution, saturation response, timeout fencing, and release ownership.
- [x] Deterministic tests prove that a saturated second request returns `TIMEOUT_GUARD` without changing the already admitted request's final `EVALUATOR` result.
- [x] Tests use explicit synchronization and bounded deadlines rather than scheduler-dependent sleeps or Hypothesis retries.
- [x] Success, timeout, evaluator exception, saturation, and late-completion paths prove exactly-once admission release with no semaphore over-release or permit leak.
- [x] Existing fail-closed timeout, semantic audit validation, metrics, bounded-state, and duplicate-input behavior remain unchanged and pass regression tests.
- [x] The full CI-equivalent unit/property/spec/contract suite passes without rerunning a failed job.
- [x] All modifications stay within `allowed_paths`; TASK-005 and TASK-029 remain blocked and no other task is activated.

## Implementation evidence

### Root cause and execution timeline

- The production ownership defect was an exception-path permit leak. After admission, the
  runner released the bounded semaphore only in selected return branches; a non-timeout
  exception from `iterator`, `future.result()`, `decide()`, semantic validation, or metrics
  escaped without releasing the permit. The implementation now uses a per-admission,
  thread-safe release-once guard with explicit caller, registering, callback, and released
  states. Only a successfully registered real worker-timeout callback takes ownership; the
  caller's `finally` retains ownership if callback registration raises.
- The historical flaky property test also coupled the maximum 4,000 microsecond business
  evaluation deadline to two OS-thread scheduling round trips. A busy runner could therefore
  correctly time out the admitted request even though the saturated request never changed its
  attempt. The replacement GateEvaluator performs the saturated re-entrant call from the
  already admitted internal worker, making the ordering deterministic without widening the
  business timeout, sleeping, retrying, or suppressing Hypothesis health checks.
- Deterministic success timeline: first request acquires admission -> internal worker enters
  GateEvaluator -> GateEvaluator invokes the second request -> second request cannot acquire
  admission, emits validated `TIMEOUT_GUARD`, and never enters the evaluator -> GateEvaluator
  records the release signal and yields the admitted results -> first request returns the
  `EVALUATOR` audit -> the first request's `finally` releases admission exactly once.
- Deterministic timeout timeline: first request acquires admission -> internal worker blocks ->
  bounded `future.result()` expires -> ownership transfers to the future callback and the
  timeout audit returns -> a second request remains saturated -> the explicit worker release
  signal allows late completion -> the callback discards the late output and releases admission
  exactly once.

### Acceptance evidence

- `test_saturation_does_not_invalidate_admitted_attempt` and
  `test_generated_timeout_saturation_does_not_invalidate_admitted_result` assert the second
  request's `TIMEOUT_GUARD`, the first request's `EVALUATOR` result, a single evaluator entry,
  and a single admission release.
- `test_evaluator_exception_releases_admission_exactly_once` fails against the previous runner:
  after the first evaluator exception the leaked permit makes the next unique request saturate.
  It now proves the exception still propagates fail-closed and the next request is admitted.
- `test_timeout_late_completion_owns_admission_until_worker_exits` proves timeout ownership is
  not released early, saturation cannot steal it, late output is fenced, and callback release is
  exactly once. The immediate-timeout and invalid-audit tests separately assert exactly-once
  release from synchronous timeout and semantic-validator exception paths.
- `poetry run pytest tests/unit/risk tests/property/risk`: 77 passed in one run.
- `poetry run pytest tests/unit tests/property tests/spec tests/contract --cov
  --cov-report=term-missing`: 407 passed in one run; total coverage 85%.
- A bounded 100-iteration subprocess stress loop ran four targeted concurrency tests per
  iteration: 400/400 targeted executions passed with no retry of a failed iteration.
- `poetry run mypy src/quantiqmt/risk`, targeted Ruff check/format, and
  `poetry run python scripts/validate_specs.py` all exited 0; `git diff --check` passed.
- Implementation-PR diff and task-state audits showed only TASK-045 allowed paths changed;
  before independent Review, TASK-045 remained the sole `active` task with Review `pending`.
  The completion evidence below records the later approved/merged closeout transition;
  TASK-005 and TASK-029 remain `blocked`, and release remains `prohibited`.

### PR #57 P1 ownership-handoff remediation

- Review of Head `5c42aa6ba451d6e481f930d364f3d206661ba17b` identified that setting
  `release_on_exit=false` before `Future.add_done_callback()` leaked the permit when callback
  registration raised. `_AdmissionOwnership` now performs a locked state transition to
  `registering`, rolls back to caller ownership on registration failure, records successful
  asynchronous handoff as `callback`, and makes both caller and callback release through the same
  idempotent `released` fence.
- `test_timeout_callback_registration_failure_releases_real_admission_once` uses the runner's
  real `BoundedSemaphore`: the registration exception propagates, exactly one permit can be
  acquired afterward, and a subsequent unique evaluation succeeds.
- `test_timeout_callback_synchronous_registration_releases_exactly_once` forces callback execution
  inside `add_done_callback()` and proves callback plus caller `finally` release only once.
- `test_timeout_callback_asynchronous_completion_releases_exactly_once` stores the callback,
  proves another request remains saturated, then invokes late completion on a controlled thread
  and proves exactly one release.
- A separate bounded 100-iteration subprocess stress loop ran these three callback-handoff tests:
  300/300 executions passed without retrying a failed iteration.

### Completion evidence

- PR #57 was independently reviewed at Head
  `4b252aae29f120611b9b9773e8e8ef3935c85218`; qifuxiao submitted formal `APPROVE` at
  <https://github.com/qifuxiao/QuantiQmt/pull/57#pullrequestreview-4873377772>.
- The reviewed Head passed 4/4 GitHub CI checks: quality jobs
  <https://github.com/qifuxiao/QuantiQmt/actions/runs/31089723966/job/92577541060> and
  <https://github.com/qifuxiao/QuantiQmt/actions/runs/31089719871/job/92577528619>, plus
  persistence-postgresql jobs
  <https://github.com/qifuxiao/QuantiQmt/actions/runs/31089723966/job/92577541110> and
  <https://github.com/qifuxiao/QuantiQmt/actions/runs/31089719871/job/92577528618>.
- PR #57 merged as `7a39d1a0cad5455b2df0043a9449d4c4da2c36b5` on 2026-08-06.
- Human authorization on 2026-08-06 added only the completed TASK-045 path for this closeout,
  Review/CI/merge evidence, and active-to-completed migration. It did not authorize activating,
  unlocking, implementing, or releasing TASK-005, TASK-029, or any other business task.

## Review focus

- Verify the fix removes the scheduling race rather than merely widening wall-clock timeouts.
- Verify a late worker result cannot overwrite or invalidate another attempt.
- Verify semaphore ownership is local to the admitted attempt and released exactly once.
- Verify tests would fail against the pre-fix implementation for the identified reason.

## Risks and rollback

- Incorrect admission fencing could allow concurrent evaluation, leak capacity, or convert a valid result into a timeout audit.
- Roll back the implementation and tests together if deterministic concurrency guarantees cannot be proven; keep downstream Risk tasks blocked and release prohibited.
