# TASK-058 Implementation Packet

## Frozen identity and bootstrap boundary

- Task: TASK-058
- Plan: TASK-058-PLAN-v1
- Packet identity: TASK-058-IMPLEMENTATION-v1
- Repository: qifuxiao/QuantiQmt
- Expected Implementation Base / PR Base: `3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb`
- Branch: `codex/task-058-implementation`
- Active task: `tasks/active/TASK-058-risk-finalization-boundary.md`
- Task blob: `0c1feb2cec0f5357fdbb4e137ecfd45d80277b2a`
- Historical Planning Base: `b9b313d2af1071281bc62c0919ee4caceae85825`
- Preparation PR: https://github.com/qifuxiao/QuantiQmt/pull/118
- Reviewed preparation Head: `37c3080b3532e28bd914e5bd86e6740b7adcef6f`
- Current stage: packet-only bootstrap; not ready to merge.
- Canonical Human assignment: pending.
- Implementation Agent: pending, unassigned.
- Handoff: pending; `ai/handoffs/TASK-058-IMPLEMENTATION-v1.yaml` does not yet exist.
- Single writer: no implementation writer established before canonical Human assignment.

This Coordinator / Codex / Windows bootstrap is expressly authorized to add only this
Packet, validate it, commit, push and create the PR, then stop. Its commit and the
created PR establish the exact Starting Head externally; this file does not invent a
self-referential commit SHA, PR number, assignment URL or producer identity.

PR #118 authorizes preparation, not acceptance of the proposed Risk contract.
TASK-005 remains blocked. PR #117 is closed without merge at
`88d217661f6d6c127758fc245336a9f806788ab9`, not accepted completion:

- https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5628617915
- https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5629435266

Preserve that PR, branch, commits and historical Packet/Handoff/evidence. Do not reuse
its Base or assignment for TASK-058, and do not transplant its runtime implementation.

## Goal and authority

Produce a separately reviewable specification change resolving the final Risk output
construction, deadline accounting, bounded cleanup and telemetry boundaries. It is a
specification deliverable, not Risk runtime implementation, deployment or performance
acceptance. Follow root/nearest AGENTS, the manifest and all active-task spec_refs:
INV-RISK, INV-CONSISTENCY, PORTS-RISK, NFR-PERFORMANCE, NFR-OBSERVABILITY,
WF-SUBMIT-ORDER, CONTRACT-RISK-AUDIT-OUTPUT-V1,
CONTRACT-RISK-ORDER-EVALUATED-V2 and CONTRACT-ERROR-CATALOG.

Dependencies TASK-003, TASK-015 and TASK-029 must remain trusted completed.
This Packet does not supersede a normative MUST. The Human accepted lower-bound
telemetry counters, fixed resource limits, a diagnostic interface and explicit failure
exits only as a design direction awaiting formal specification Review. No runtime
consumer may adopt the candidate until its separate normative approval and deployment
requirements are met.

## Exact future specification scope

Only after assignment and Handoff gates may the assigned writer modify these five files:

| Path | Minimum intended change |
| --- | --- |
| `spec/interfaces/risk-ports.md` | Define final immutable candidate, complete validation pipeline, sampling/delivery boundaries, one terminal outcome, bounded normal/cleanup worker ownership, failure exits and local telemetry/diagnostic responsibilities. |
| `spec/nfr/performance.yaml` | Distinguish audit sampling from full completion latency; retain integer ceiling, original deadline and 4ms NFR; state finite capacities and the limits of timing/performance claims. |
| `spec/nfr/observability.yaml` | Define audit/completion metrics, finite labels, non-waiting bounded telemetry, observable but possibly undercounted losses, diagnostics and observer failure/close behavior. |
| `spec/workflows/submit-order.yaml` | Distinguish validated timeout REJECT from no-valid-audit failure; prohibit fabricated Decision, projection, publication, approved OMS transition and Execution on failure. |
| `spec/manifest.yaml` | Version the change and record compatibility, affected TASK-005, consumer adaptation/deployment order and safe rollback; distinguish clarification from new local interfaces or failure behavior. |

The task additionally allows this Packet and its own Handoff for their separately
authorized bootstrap steps; it does not give the later writer permission to rewrite
frozen authority. All other paths are out of scope. In particular preserve the task's
forbidden_paths exactly:

```yaml
forbidden_paths:
  - src/**
  - tests/**
  - scripts/**
  - tasks/**
  - .github/**
  - migrations/**
  - spec/contracts/**
  - spec/invariants/**
  - spec/state-machines/**
  - pyproject.toml
  - poetry.lock
  - poetry.toml
```

No validator fixes, test edits, dependency changes, CI changes, business DTO/Event/error
code/Order transition changes, weakened hard limits or reduce-only/UNKNOWN semantics.
No task restoration/activation, Mini QMT, accounts, market queries, orders, real money
or release. No extra repository report files.

## Candidate design and acceptance mapping

The following is a review plan, not a parallel normative contract or pre-approved implementation.
Resolve every boundary across the five files, preserving safety and the full validation chain.

1. **Final construction:** fix the final primitive candidate before Draft 2020-12
   Schema validation, then PORTS-RISK semantic validation, then deep freeze. No
   post-validation field mutation or immutable-copy bypass; no unbounded
   validate/update-time/revalidate loop. Cover normal and timeout candidates.
2. **Timing:** explicitly distinguish the audit sampling point from full terminal
   completion. Disclose ceiling conversion, per-rule sum lower bound and timeout floor
   rather than claiming all are raw measurements. The original absolute deadline still
   covers aggregation, candidate construction, validation, freeze and handback;
   reaching the budget rejects, and cleanup cannot extend PASS eligibility.
   Include the 3,999,001ns to 4000us boundary. Preserve the 4ms NFR and metric/audit
   consistency without omitting final validation cost from completion measurement.
3. **Bounded completion:** define one caller-owned terminal result; isolate late output.
   Specify finite normal and independent one-attempt cleanup capacities, zero waiting
   backlog, deadline start before admission/construction, and exact permit ownership
   through timeout/cancellation/actual worker completion. No replacement of blocked
   workers, unbounded Runner churn or blocking joins on the trading path.
   Define host-level limits and shutdown responsibilities; do not promise CPython
   hard realtime or same-process isolation from arbitrary observer behavior.
4. **Failure exits:** preserve the original selected validation exception and cause;
   distinguish cleanup wait exhaustion/capacity failure from worker-raised exceptions.
   A builtin exception name or text alone cannot identify retry eligibility.
   No valid audit means no fabricated Decision or automatic OMS REJECTED transition,
   no v1/v2 projection/publication and no Execution. Revise conflicting unconditional
   timeout-audit promises together, without reusing QQ-RISK-4008 for unrelated failure.
5. **Telemetry:** specify try-only admission, bounded encoded storage and finite
   sample/label sets; capacity must precede batch construction. The candidate direction
   uses one consumer, one pending slot, two preallocated 512KiB buffers, at most 8192
   rule plus four summary samples, and bounded numeric encoding. Oversize batches
   are dropped without clamping authoritative audit values. Define FULL/CONTENDED/
   OBSERVER_EXCEPTION/CLOSED accounting, non-nested non-waiting locks, prefix side
   effects on observer failure, no retries, no replacement of blocked observers and
   close ownership. Counters are uint64-saturating, possibly missed LOWER_BOUND
   observations; AVAILABLE/BUSY diagnostics cannot imply complete loss accounting.
   Zero lower-bound count is not proof of zero loss or NFR compliance. Lossy telemetry
   never authorizes loss of authoritative audit/Outbox. The exact local interface and
   resource constants still require formal cross-file review.
6. **Compatibility:** identify all affected callers and distinguish measurement
   clarification from new local failure/diagnostic interfaces. Preserve published
   Schema/Event/DTO/error/state contracts. If the proposal actually requires changing
   published field meaning or machine Schema, stop for new authority rather than
   labeling it compatible or silently editing forbidden contracts. State consumer
   adaptation before enabling the new Runner and rollback with trading gates closed.
7. **Reviewable evidence:** before edits, map current conflicting clauses to proposed
   replacements and expected boundary outcomes. Submit a complete PR review matrix for
   normal PASS/REJECT, rounding/deadline equality, final validation failure, cleanup
   blockage/saturation, late completion, telemetry contention/overflow/close/observer
   exception and blockage. Run unchanged tests; no tests/fixtures are writable in this
   task. Existing tests are not evidence of future runtime behavior. A required new
   test-file change needs additional scope authorization, not a bypass or invented pass.

Expected demonstration: consistent five-file specification diff, compatibility and
failure matrix that an independent Reviewer can check and a later TASK-005 writer can
implement without guessing. Do not claim production latency, all scheduling
interleavings, deployment or Mini QMT acceptance.

## Exact verification and environment evidence

Copy the following opaque values unchanged into the future Handoff; task/Handoff
declarations must be deep-equal:

```yaml
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run python scripts/validate_specs.py
        - poetry run pytest tests/spec tests/contract
  prohibited_lanes:
    - windows_miniqmt
```

Follow `ai/workflows/poetry-verification.md`. Verify an existing compatible environment,
Python and dependency-file checksums, and bind imports to the exact reviewed source.
Do not install/upgrade dependencies or silently use an old editable checkout.
Inventory dist before building; run the task-required `poetry build` without overwriting
user artifacts. Record attributable wheel size/hash. The final original pytest command
must execute installed-wheel cases with zero failures/skips. Record raw commands, exit
codes, counts, logs and limitations; distinguish sandbox failures from actual reruns.
Also audit exact Base...Head paths, unchanged task/authority blobs and `git diff --check`.

The assigned Environment Verification role must later publish unedited exact-Head
evidence and run the formal environment validator using its real URL and frozen
Base/Head. Current bootstrap checks are not that evidence. No synthetic comment, mock
GitHub object or absent Handoff can substitute for the live formal gates.

## Standard Handoff sequence and stop conditions

1. This one-file bootstrap commit creates the packet-only PR and then stops; no merge.
2. Human posts canonical assignment on that PR, binding its number, exact Base,
   branch, actual packet-only Starting Head, unique writer and authorized producers.
3. Separately authorized Coordinator creates an add-only Handoff commit whose direct
   parent is `3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb`, not the Packet commit.
   Freeze the task/Packet blobs, real PR, assignment URL/author/timestamps/digest,
   producers and exact lanes. Handoff filename stem and packet_version both equal
   `TASK-058-IMPLEMENTATION-v1`. Historical Planning Base is an ancestor of this Base.
   Existing `repair_context.superseded_head_sha` binds the packet-only Starting Head;
   that field name does not invent a prior TASK-058 repair.
4. The assigned writer first performs a non-rewriting `--no-ff` merge of that
   Coordinator commit into the packet-only branch, preserving its parent and blob.
   Isolated-worktree setup is not implementation. The first history change is that
   merge. Task blob stays identical at Base and Head. Run the complete formal Handoff
   validator against the resulting exact topology before normative edits.
5. Only then produce the five-file spec change, all task validation, exact-Head
   portable evidence and CI, followed by independent normative Review and Human merge.
6. Human separately authorizes closeout. TASK-005 remains blocked until specification
   acceptance/closeout and separate Human replan/reactivation with fresh authority.

Any Base/Head/task/Packet/Handoff/assignment drift, missing live authority, concurrent
writer, unsupported topology, failed required check, skipped required case, conflicting
normative requirement or need for another path is PLAN_BLOCKED. Preserve evidence and
report the exact conflict; do not rebase to a new Base, modify validators, weaken
deadline/validation, rewrite history or claim a waiver. This bootstrap stops after PR
creation, with assignment, Handoff and implementation still pending.
