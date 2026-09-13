# TASK-058 Implementation Packet

## Frozen identity and bootstrap boundary

- Task: TASK-058
- Plan: TASK-058-PLAN-v2
- Packet identity: TASK-058-IMPLEMENTATION-v2
- Packet path: `ai/packets/TASK-058-IMPLEMENTATION-v2.md`
- Repository: qifuxiao/QuantiQmt
- Expected Implementation Base / PR Base: `4fb7ad1ecb5d726fff7f54d107de69fbabe69688`
- Branch: `codex/task-058-implementation-v2`
- Active task: `tasks/active/TASK-058-risk-finalization-boundary.md`
- Task blob: `3457ffe90f48aedc5cf2f5fddcbdb107f4d1cd83`
- Historical Planning Base: `3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb`
- Preparation PR: https://github.com/qifuxiao/QuantiQmt/pull/120
- Reviewed preparation Head: `0b7b9d932aa723da978dcc88a426378f711b11f5`
- Current stage: packet-only bootstrap; not ready to merge.
- Canonical Human assignment: pending.
- Implementation Agent: pending, unassigned.
- Handoff: pending; `ai/handoffs/TASK-058-IMPLEMENTATION-v2.yaml` does not yet exist.
- Single writer: no implementation writer established before canonical Human assignment.

This Coordinator / Codex / Windows bootstrap is expressly authorized to add only this
Packet, validate it, commit, push and create the PR, then stop. Its commit and the
created PR establish the exact Starting Head externally; this file does not invent a
self-referential commit SHA, PR number, assignment URL or producer identity.

PR #120 authorizes preparation, not acceptance of the proposed Risk contract.
TASK-005 remains blocked. PR #117 is closed without merge at
`88d217661f6d6c127758fc245336a9f806788ab9`, not accepted completion:

- https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5628617915
- https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5629435266

Preserve that PR, branch, commits and historical Packet/Handoff/evidence. Do not reuse
its Base or assignment for TASK-058, and do not transplant its runtime implementation.

## Preserved v1 and v2 supersession

This new PR supersedes #119 for future TASK-058 work; Human decides the old PR's disposition.
PR #119 remains open at remote STOP Head `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`.
The old assignment does not authorize v2:

- Assignment: https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5634925713
- STOP: https://github.com/qifuxiao/QuantiQmt/pull/119#issuecomment-5646729029
- STOP author: qifuxiao; created_at = updated_at = 2026-09-12T15:10:41Z.
- STOP raw-body SHA-256: `eadad8bf9af6a6085eb591d736d1288c1779d3752f46dfc1adf141b5ce583075`.
- Preserved local sync: `02fc1857a2fa885ba59477de37a7e20ca965fc3f`.
- Parents, in order: `f74ceb26d821cc9d53d3164225fe71c1dcbc1124`, `42ad3c3e1c65a1251d0b9654d1a36ce393dad094`.
- Packet v1 blob: `6c738559a3dda4edda66600f06e99c7efbe01d70`.
- Handoff v1 blob: `1a87f074bc73744316faded7963819a8c20db8ee`.

The original worktree was checked read-only with git cat-file, git show and git rev-parse:
`C:/Users/Administrator/.codex/visualizations/2026/09/12/01a095e2-9474-76c1-83a9-fa0ab117f77b/task058-specification`.
Preservation there is sufficient evidence; the new repository need not contain this
local-only object. Do not reconstruct, cherry-pick, rebase, delete, rewrite or push it,
or introduce it into v2 ancestry. The v2 bootstrap is one direct child of the new Base.
Do not rewrite any existing Packet, Handoff, assignment or evidence.

PR #120 Approval binds only preparation Head `0b7b9d932aa723da978dcc88a426378f711b11f5`:
https://github.com/qifuxiao/QuantiQmt/pull/120#pullrequestreview-5190988626
It does not approve candidate specification semantics, assign a writer or restore TASK-005.
Delivery remains draft / not_started / not_run / pending / prohibited.

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

Only after assignment and Handoff gates may the assigned writer modify these five
specification files and the three exact test paths listed below:

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
- tests/contract/**
- tests/property/**
- tests/integration/**
- scripts/**
- tasks/**
- .github/**
- migrations/**
- spec/contracts/**
- spec/invariants/**
- spec/state-machines/**
- ai/packets/TASK-058-IMPLEMENTATION-v1.md
- ai/handoffs/TASK-058-IMPLEMENTATION-v1.yaml
- pyproject.toml
- poetry.lock
- poetry.toml
```

No validator fixes, unlisted test edits, dependency changes, CI changes, business DTO/Event/error
code/Order transition changes, weakened hard limits or reduce-only/UNKNOWN semantics.
No task restoration/activation, Mini QMT, accounts, market queries, orders, real money
or release. No extra repository report files.

## Exact future test adaptation plan

Only these three test files may receive minimum necessary changes after writer gates:

| Path | Test-first adaptation and retained checks |
| --- | --- |
| `tests/spec/test_order_registration_binding_contracts.py` | Bind historical manifest version/change/previous assertions to the real frozen source. Keep current destructive-backfill prohibition, TASK-050 completion, TASK-048 dependency and legacy UNBOUND rebinding rejection checks. |
| `tests/spec/test_risk_runtime_schema_contract.py` | Retain every TASK-029 historical lifecycle assertion; validate current Catalog/Schema/routes in the current tree. Add TASK-058 version, compatibility, deployment/rollback and five-specification boundary checks. Never substitute a new version for published Schema/Event/DTO identities. |
| `tests/unit/contracts/test_schema_bundle.py` | Keep complete bytes parity against real frozen history and independently compare the current full contract index, file set and bytes with frozen source. Preserve duplicate/missing/unresolved/source-drift rejection phases, version/corruption/missing rejection and installed-wheel execution. |

Frozen historical manifest source:
`3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb:spec/manifest.yaml`,
blob `1a72adc78638dc223fb263df8beb69a7e2586bb3`.
Verify that exact source; missing history must fail, never synthesize history or skip.
The existing runtime bundle remains `0.15.0`. The old builder must reject a new manifest
version; do not patch constants or temporarily downgrade the manifest. Preserve current
contract bytes/index parity as well as historical parity. No mechanical version replacement,
historical assertion deletion, skip/xfail, mocked acceptance or weakened safety checks.
New-specification/old-bundle compatibility remains subject to formal normative Review.

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
   exception and blockage. Use only the three narrowly authorized test adaptations above, test first.
   Existing tests are not evidence of future runtime behavior. Any additional test
   path needs separate scope authorization, not a bypass or invented pass.

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
  - poetry run pytest tests/unit/contracts
  required_lanes:
  - lane: portable
    capability: portable
    minimum_records: 1
    commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
    - poetry run pytest tests/unit/contracts
  prohibited_lanes:
  - windows_miniqmt
```

Follow `ai/workflows/poetry-verification.md`. Verify an existing compatible environment,
Python and dependency-file checksums, and bind imports to the exact reviewed source.
Do not install/upgrade dependencies or silently use an old editable checkout.
Inventory dist before building; run the task-required `poetry build` without overwriting
user artifacts. Record attributable wheel size/hash. The final original pytest command
must execute both installed-wheel cases with zero failures/skips: market in
`tests/spec tests/contract`, Risk in `tests/unit/contracts`. `poetry build` is a
prerequisite, separate from the three opaque portable commands. Record raw commands, exit
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
   parent is `4fb7ad1ecb5d726fff7f54d107de69fbabe69688`, not the Packet commit.
   Freeze the task/Packet blobs, real PR, assignment URL/author/timestamps/digest,
   producers and exact lanes. Handoff filename stem and packet_version both equal
   `TASK-058-IMPLEMENTATION-v2`. Historical Planning Base is an ancestor of this Base.
   Existing `repair_context.superseded_head_sha` binds the packet-only Starting Head;
   that field name does not invent a prior TASK-058 repair.
4. The assigned writer first performs a non-rewriting `--no-ff` merge of that
   Coordinator commit into the packet-only branch, preserving its parent and blob.
   Isolated-worktree setup is not implementation. The first history change is that
   merge. Task blob stays identical at Base and Head. Run the complete formal Handoff
   validator against the resulting exact topology before normative edits.
5. Only then produce the five-file spec change and three bounded test adaptations, all task validation, exact-Head
   portable evidence and CI, followed by independent normative Review and Human merge.
6. Human separately authorizes closeout. TASK-005 remains blocked until specification
   acceptance/closeout and separate Human replan/reactivation with fresh authority.

Any Base/Head/task/Packet/Handoff/assignment drift, missing live authority, concurrent
writer, unsupported topology, failed required check, skipped required case, conflicting
normative requirement or need for another path is PLAN_BLOCKED. Preserve evidence and
report the exact conflict; do not rebase to a new Base, modify validators, weaken
deadline/validation, rewrite history or claim a waiver. This bootstrap stops after PR
creation, with assignment, Handoff and implementation still pending.
