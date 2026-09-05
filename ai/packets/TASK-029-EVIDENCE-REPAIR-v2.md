# TASK-029 Evidence-Gate Repair Packet v2

## Frozen identity

- Task: `TASK-029`.
- Plan: `TASK-029-PLAN-v2`.
- Packet identity: `TASK-029-EVIDENCE-REPAIR-v2`.
- Repair starting Head: `1bc232d367261302b397556b36a6b3284f8784d7`.
- PR Base: `b4b3f07c734c894032bd02f98e8cc914aa26f5d5`.
- Implementation PR: <https://github.com/qifuxiao/QuantiQmt/pull/110> (`#110`).
- Implementation branch: `codex/task-029-implementation`.
- Repair coordination branch: `codex/task-029-evidence-gate-repair`.
- Existing Implementation Packet: `ai/packets/TASK-029-IMPLEMENTATION-v1.md`, blob
  `df3f7e0237f07894e6e3445b613b6b614307fcb0`.
- Existing Implementation Handoff: `ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml`, blob
  `6af2d6aeb84693b6c6e8efc34793ff4f2636d46b`.
- Future Handoff: `ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml`, pending and not authorized in
  this coordination stage.

All identities are exact. Drift in the task, Plan, Packet, Handoff, PR, Base, Head, branch, comment,
producer, command set, or path set is `PLAN_BLOCKED`.

## Human repair authorization

- URL: <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5549863721>.
- Comment ID: `5549863721`.
- API URL: <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5549863721>.
- Issue URL: <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/110>.
- Author: `qifuxiao`.
- Created: `2026-09-05T06:06:08Z`.
- Updated: `2026-09-05T06:06:08Z`.
- Raw-body SHA-256:
  `0efa5bb59c51c46d8fc783e9664fd75ddc67463bec65c400a4d36c8720018adb`.

The comment is the authority for this Plan amendment and Packet only. It does not assign an
Implementation or Environment Verification Agent and does not authorize a Handoff, implementation,
evidence publication, Review, Approval, merge, closeout, external system access, or trading action.

## Writer and producer state

- The existing sole Implementation writer is
  `task-029-implementation-codex-windows-1` / `qfxyyy` / Implementation Agent / Codex / Windows /
  `portable`. It remains paused at exact Head
  `1bc232d367261302b397556b36a6b3284f8784d7`.
- This pause is not a `STOP` or `SWITCH`; no second Implementation writer exists or is authorized.
- New canonical assignment: pending Human action on PR #110.
- Intended independent evidence producer after that assignment:
  `task-029-environment-verification-codex-windows-1` / `qifuxiao` /
  Environment Verification Agent / Codex / Windows / `portable`.
- The intended producer is not authorized to act until the future canonical assignment and
  Coordinator-authored Handoff v2 freeze the complete live authority.

## Objective and preserved product result

Repair the single formal `scripts/validate_agent_environment.py` gate so it can validate TASK-029
evidence from the exact Git Head while preserving the historical TASK-057 v3/v4 contract and every
fail-closed trust boundary.

The product implementation and acceptance evidence at the repair starting Head are retained. The
installed Risk Schema bundle, checksum/version/reference verification, package-resource-only loader,
shared Schema-then-semantic validation entry, immutable output construction, Runner, v1 projection,
v2 envelope, and their tests are not implementation targets and MUST NOT be rewritten. Those prior
results are historical after any Head change; the same six commands must run again on the repaired
exact Head before formal environment evidence.

## Exact repair scope

The later assigned repair implementation may modify only:

- `scripts/validate_agent_environment.py`;
- `tests/spec/test_validate_agent_environment.py`.

The active task amendment, this Packet, and the future add-only Handoff are lifecycle artifacts, not
validator implementation targets. No product code, product spec, dependency, lockfile, CI, schema,
Packet v1, or Handoff v1 change is permitted.

## Required design

Generalize the existing validator from a TASK-057-only path and identity table into one fail-closed
authority loader driven by all three of the following, with no caller override:

1. the exact Git Head and the single active task discovered in that tree;
2. an explicit allowlist of supported `(task identity, Plan identity, Packet identity, Handoff
   path)` tuples;
3. the selected Handoff's exact task blob, filename/packet identity, required/prohibited lanes,
   opaque command partition, GitHub PR/comment authority, and producer allowlist.

The support table may add only the future TASK-029 Plan-v2/Handoff-v2 identity alongside the
historical TASK-057 v3/v4 identities. It MUST NOT glob for a newest or convenient Handoff, accept an
arbitrary task/Handoff, infer authority from filenames alone, or permit caller/evidence values to
replace task, command, PR, branch, Base, Head, assignment, or producer authority.

TASK-specific safety constraints remain explicit and fail closed. TASK-057 v3/v4 behavior and
fixtures remain supported byte-for-byte in meaning. TASK-029 permits only the frozen `portable`
lane, prohibits `windows_miniqmt`, and prohibits Mini QMT connection, account or market-data query,
order submission/cancellation, simulation order, and real-money activity.

## Tests-first repair requirements

Before changing validator runtime behavior, add failing tests covering:

- the positive `TASK-029-PLAN-v2` / `TASK-029-EVIDENCE-REPAIR-v2` exact-Head path;
- unchanged historical TASK-057 v3/v4 behavior;
- rejection of mixed task/Plan/Handoff identities;
- rejection of Handoff filename/Packet identity mismatch and unsupported identities;
- rejection of zero or multiple active tasks;
- rejection when task path, Handoff path, or task blob does not exist or match the exact Head;
- rejection of caller authority conflicting with frozen GitHub authority;
- rejection of missing, duplicate, substituted, or additional required commands;
- rejection of PR, Base, Head, branch, comment author/timestamps/digest, or producer drift;
- proof that local assignment documents and caller parameters cannot override live GitHub
  authority.

Then make the minimum validator-only change required for green. Schema validation, bounded fixed
origin/no-redirect GitHub GETs, duplicate-key rejection, exact SHA/branch/comment binding, ordered
single-writer validation, command deep equality/partitioning, lane capability checks, sanitized
provenance, side-effect prohibitions, and fail-closed error handling MUST remain at least as strict.

## Frozen verification

No command is waived, replaced, augmented, or reordered in the task contract. After the repair is
synchronized into the Implementation branch and committed, execute every exact command against the
new exact Head:

1. `poetry run python scripts/validate_specs.py`
2. `poetry run pytest tests/spec tests/contract tests/unit/contracts`
3. `poetry run pytest tests/unit/risk tests/property/risk`
4. `poetry run mypy src/quantiqmt/contracts`
5. `poetry run ruff check .`
6. `poetry run ruff format --check .`

Required lane declarations in the future Handoff must be deep-equal to the active task and form an
opaque exact partition of these six strings. Prior command results do not satisfy the changed Head.

## Frozen continuation sequence

1. This coordination commit changes only the active TASK-029 Plan amendment and this Packet, then
   is pushed to `codex/task-029-evidence-gate-repair`.
2. A Human publishes a new, unedited canonical assignment on PR #110.
3. The Coordinator creates an add-only Handoff v2 that freezes the exact coordination commit,
   amended task blob, Packet blob, live PR authority, assignment identity/digest, producer allowlist,
   and deep-equal lanes/commands.
4. The original sole Implementation Agent synchronizes the Coordinator commits without rewriting
   them, records red tests, implements the minimum validator repair, commits, and pushes to the
   existing Implementation PR.
5. All six commands rerun against the new exact Head. The independently assigned Environment
   Verification Agent publishes canonical evidence, and the formal validator validates it live.
6. New exact-Head CI completes, followed by Independent Review and Human-only Approval/merge.
7. Closeout and any TASK-005 state change require separate Human authority and a separate PR.

Any missing or out-of-order gate is `PLAN_BLOCKED`.

## Explicitly forbidden

- creating Handoff v2 during this coordination stage;
- modifying the validator, tests, product implementation, spec, dependencies, lockfile, CI, Packet
  v1, or Handoff v1 in this coordination commit;
- creating a second validator or weakening/bypassing schema or identity validation;
- accepting arbitrary task/Handoff files or selecting one by glob recency;
- allowing caller/evidence command, task, PR, Base, Head, branch, assignment, or producer overrides;
- waiving or skipping required verification;
- creating another Implementation writer, publishing assignment/evidence, reviewing, approving,
  merging, closing out, activating/implementing TASK-005, accessing Mini QMT, querying account or
  market data, or submitting/cancelling any order;
- real-money trading under any circumstance.

## PLAN_BLOCKED conditions

- PR #110, Base, Head, branch, active-task, dependency, Packet/Handoff v1 blob, Human authorization,
  writer, or worktree state drifts before the next frozen step.
- The future Handoff or assignment is missing, edited, out of order, or inconsistent.
- Repair requires any path beyond the two exact implementation targets.
- Historical TASK-057 behavior cannot be preserved, or TASK-029 support would weaken a trust,
  command, capability, side-effect, schema, or fail-closed boundary.
- Any exact verification command fails, is waived, or is not represented truthfully in evidence.
- TASK-005 ceases to be blocked before separate exact-Head Review and Human authorization.
