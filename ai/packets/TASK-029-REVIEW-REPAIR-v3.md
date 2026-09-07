# TASK-029 Review Repair Packet v3

## Frozen identity and stage

- Task: `TASK-029`
- Plan: `TASK-029-PLAN-v2`
- Packet identity: `TASK-029-REVIEW-REPAIR-v3`
- Repository / PR: `qifuxiao/QuantiQmt#110`, <https://github.com/qifuxiao/QuantiQmt/pull/110>
- Exact PR Base: `b4b3f07c734c894032bd02f98e8cc914aa26f5d5`
- Exact reviewed / repair starting Head: `8b4c76d691849b126810be8953bfa7210ce18f43`
- Implementation branch: `codex/task-029-implementation`
- Coordinator branch: `codex/task-029-review-repair`
- Current stage: `Plan/Packet-only review-repair coordination`
- Canonical repair assignment: `pending`
- Repair Handoff v3: `pending`, at `ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml`
- Repair Implementation writer: `paused`; it MUST NOT resume before the new canonical Human
  assignment and Coordinator-authored Handoff v3 exist. No second writer is authorized.
- Environment Verification Agent: `evidence-only`.

Plan identity remains TASK-029-PLAN-v2. No new Plan version is authorized. The existing product
implementation MUST be preserved and MUST NOT be reimplemented. This Packet freezes exactly the
two findings below, not a new product implementation or another review verdict.

## Exact authority

Independent REQUEST_CHANGES Review:

- URL: <https://github.com/qifuxiao/QuantiQmt/pull/110#pullrequestreview-5132746737>
- Review ID: `5132746737`
- Author: `qfxyyy`
- State: `CHANGES_REQUESTED`
- Submitted at: `2026-09-07T13:56:30Z`
- Bound commit: `8b4c76d691849b126810be8953bfa7210ce18f43`
- Raw-body SHA-256: `aafc6c2d7e57391a205d6d4a8d652601c004803c7451cf76d7e0f488f60790f1`

Human review-repair authorization:

- URL: <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5569141265>
- Comment ID: `5569141265`
- Author: `qifuxiao`
- Created at: `2026-09-07T10:19:10Z`
- Updated at: `2026-09-07T10:19:10Z`
- Raw-body SHA-256: `147fea036dae2a0c4c171d3a8940d0f78dc39aa934c36942aef0a20723bfeb60`

The authorization is not the pending canonical repair assignment. Historical assignments do not
authorize resuming this repair. All identities and raw UTF-8 body digests must match live GitHub
authority. PR #110 must remain OPEN, non-draft, unmerged, with the exact Base and reviewed Head
above throughout this coordination step. Any mismatch is `PLAN_BLOCKED`; no substitute authority,
Base, Head, or inferred assignment is permitted.

## Immutable historical artifacts

| Artifact | Frozen Git blob |
|---|---|
| `ai/packets/TASK-029-IMPLEMENTATION-v1.md` | `df3f7e0237f07894e6e3445b613b6b614307fcb0` |
| `ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml` | `6af2d6aeb84693b6c6e8efc34793ff4f2636d46b` |
| `ai/packets/TASK-029-EVIDENCE-REPAIR-v2.md` | `b9ccd5f4b23a98754fb528ecfc250dbb1a0e0af0` |
| `ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml` | `d23b5cf077aa7994ea5f782162c45b31f1f88bb5` |

These files and Plan v2 history remain unchanged. Prior evidence and Review bind only their
original exact Head and cannot approve a changed Head.

## P1 — divergent duplicate Schema documents

Before exposing any resolver or validator, reject conflicting contract/route copies of the same
canonical path. Require agreement of canonical path, parsed document, Schema identity,
content/document digests, and effective resolved graph. Every contract, route, path, and URI entry
point MUST use the same verified document.

First add a failing negative regression reproducing the Risk v2 contract/route divergence with
`priority minimum=-1` in one copy. Then make the minimum loader repair so the divergent bundle
fails closed before resolution or validation is exposed, while valid identical copies continue to
resolve through one verified graph. Permissive selection, overwrite, `setdefault`, fallback, and
last-writer-wins are forbidden. Do not change product Schema bytes to conceal the conflict.

## P2 — task/Handoff lane deep-equal

Remove every TASK-029-specific special case or bypass of task/Handoff lane validation. Both task
and Handoff `required_lanes` and `prohibited_lanes` MUST exist, be validated independently, and
be deep-equal. Preserve the exact command partition check and opaque command strings, including
their order and multiplicity.

First add failing negative tests for missing declarations, conflicting declarations, reordered
commands, duplicated commands, substituted commands, an additional command, and prohibited-lane
mismatch. Then make the minimum validator repair. Preserve historical TASK-057 behavior and all
fail-closed GitHub, assignment, and environment-evidence checks; no trust, capability, identity,
command, or side-effect check may be weakened.

## Exact path boundaries and non-goals

This Coordinator commit may only modify
`tasks/active/TASK-029-risk-runtime-schema-contract.md` and add this Packet. In the task, add only
the frozen machine-readable lanes under `verification` and these two `allowed_paths` entries:

- `ai/packets/TASK-029-REVIEW-REPAIR-v3.md`
- `ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml`

All existing allowed paths, forbidden paths, dependencies, spec references, acceptance criteria,
verification commands, delivery state, product objectives/non-goals, and historical records MUST
remain unchanged. TASK-029 remains the unique active task, its TASK-015/030/031 dependencies remain
completed, and TASK-005 remains blocked. Adding the Handoff path does not authorize its creation
in this step.

The later assigned Implementation Agent may change only the minimum necessary subset of:

- `src/quantiqmt/contracts/bundle.py`
- `tests/unit/contracts/**`
- `scripts/validate_agent_environment.py`
- `tests/spec/test_validate_agent_environment.py`

Forbidden throughout this repair: modifying any product Schema or spec; `pyproject.toml`,
`poetry.lock`, or dependencies; CI; Broker, Order, Mini QMT, or unrelated product code; Packet or
Handoff v1; Repair Packet or Handoff v2; TASK-005 status; a second writer; rebase, cherry-pick
rewriting, or force-push; waiver, skip, or validator relaxation; self-review, Approval, merge, or
closeout by an Agent; Mini QMT access, account/market queries, order submission/cancellation,
release, or real-money operations.

## Frozen verification and expected demonstration

The task and later Handoff must each declare this exact lane structure (under `verification` in
the task), with commands byte-for-byte opaque exact to the unchanged task commands:

```yaml
required_lanes:
  - lane: portable
    capability: portable
    minimum_records: 1
    commands:
      - poetry run python scripts/validate_specs.py
      - poetry run pytest tests/spec tests/contract tests/unit/contracts
      - poetry run pytest tests/unit/risk tests/property/risk
      - poetry run mypy src/quantiqmt/contracts
      - poetry run ruff check .
      - poetry run ruff format --check .
prohibited_lanes:
  - windows_miniqmt
```

After implementation, run all six commands above, both formal validators
(`scripts/validate_ai_handoff.py` and `scripts/validate_agent_environment.py`) with the applicable
frozen/live inputs, and wheel verification following `ai/workflows/poetry-verification.md`.
Demonstrate rejection of the divergent duplicate Schema before resolver exposure and rejection
of each invalid task/Handoff lane case, while unchanged valid graphs and historical TASK-057
cases pass. Build and verify the isolated installed wheel without source `spec/**`; the final
contract run must have no wheel-related skip. Record command exit codes and truthful unverified
scope against the new exact Head; this coordination step does not claim implementation acceptance.

Before this Coordinator commit/push, require exit 0 for `poetry run python scripts/validate_specs.py`,
unique-active-TASK-029 and TASK-005-blocked assertions, opaque-exact lane/command deep equality,
the exact prohibited lane assertion, task unchanged-except-authorized-increments audit, exact
two-path and Packet-add-only audits, `git diff --check`, frozen v1/v2 blob audit, Handoff-v3 absence,
and final live PR/Review/authorization drift audit. Require a clean worktree before work and after
the single commit. Missing or failed gates are `PLAN_BLOCKED`, not waived or final evidence.

## Frozen continuation sequence

1. Coordinator makes this Plan/Packet-only amendment in one commit directly from the reviewed
   Head, with message `docs(ai): coordinate TASK-029 review repair`; push only
   `codex/task-029-review-repair`, then stop immediately. Do not create a PR or change PR #110 Head.
2. Human publishes a new canonical repair assignment on PR #110.
3. Coordinator creates `ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml` add-only, freezing the new
   assignment and exact coordination/task/Packet identities.
4. The assigned Implementation Agent synchronizes the Coordinator commits without rewriting them.
5. The assigned sole writer repairs P1/P2 tests-first within the four implementation path entries.
6. All TASK-029 commands, both formal validators, and wheel verification pass.
7. New exact-Head environment evidence is produced and formally validated.
8. New exact-Head GitHub CI passes.
9. A fresh Independent Review reviews that exact Head.
10. Human alone may provide Approval and merge after the required gates pass.
11. Closeout occurs separately with its own Human authorization.
12. TASK-005 may be handled only after separate Human authorization.

No later step is authorized by completion of this commit. A missing assignment/Handoff, identity
drift, out-of-order step, failed verification, scope expansion, or second writer is `PLAN_BLOCKED`.
This Coordinator does not publish assignment or environment evidence and does not start repair
implementation, Review, Approval, merge, or closeout.
