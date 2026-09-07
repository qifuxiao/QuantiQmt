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
- Initial coordination commit: `33584e39a31b04b5a9d14a5c3b39c8c06a3889c0`.
- Handoff: `ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml`, to be added alone immediately after
  the recreated Plan/Packet amendment commit. Its parent and current task/Packet blobs must be
  frozen after that amendment commit is created.

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

This initial comment authorizes coordination; the following subsequent Human comments freeze the
assignment and authorize the narrow topology, format, and path amendments. All comments have author
`qifuxiao`, repository `qifuxiao/QuantiQmt`, PR `110`, and issue URL
<https://api.github.com/repos/qifuxiao/QuantiQmt/issues/110>.

| Authority | Comment URL | API URL | Created = updated (UTC) | Raw-body SHA-256 |
|---|---|---|---|---|
| Canonical Plan-v2 assignment | <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5551747729> | <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5551747729> | `2026-09-05T12:16:39Z` | `cb6d38d01e00ad676196b290c536136d270a915e58340e4b16e61d63fb230085` |
| Post-implementation topology | <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552251354> | <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552251354> | `2026-09-05T13:49:27Z` | `9885937238b94640126fce8d34b66aa6ec6519ddec45d4629b0d2e60a6ad0dbd` |
| Plan-version syntax correction | <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552436069> | <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552436069> | `2026-09-05T14:21:36Z` | `d0c3f01ef30d0152cba3ec5ddb96febb0d0c74fa70175f52f12f98dbbf5bc4e6` |
| Consolidated path repair | <https://github.com/qifuxiao/QuantiQmt/pull/110#issuecomment-5552503283> | <https://api.github.com/repos/qifuxiao/QuantiQmt/issues/comments/5552503283> | `2026-09-05T14:33:18Z` | `757c4fab0df3c7487e7e76d0fe487cbbe25e22a8ea99c4dbbbf01904c5743e88` |

The final authorization permits rebuilding two coordination commits from the unchanged remote
initial coordination commit. Rejected local coordination commits must never be pushed, incorporated,
or frozen as authority. The Plan identity remains `TASK-029-PLAN-v2`; only the terminal punctuation
on its Plan-version line is removed. Exactly three allowed-path entries are added:
`scripts/validate_ai_handoff.py`, `spec/contracts/catalog.yaml`, and
`src/quantiqmt/risk/__init__.py`. The latter two accept only the existing product changes at the
repair starting Head (Catalog registration/version and shared validator export); no further product
edit to either is authorized.

## Writer and producer state

- The existing sole Implementation writer is
  `task-029-implementation-codex-windows-1` / `qfxyyy` / Implementation Agent / Codex / Windows /
  `portable`. It remains paused at exact Head
  `1bc232d367261302b397556b36a6b3284f8784d7`.
- This pause is not a `STOP` or `SWITCH`; no second Implementation writer exists or is authorized.
- Canonical assignment: unedited comment `5551747729`, sentinel
  `QUANTIQMT_GITHUB_AUTHORITY_V1`, schema version `1`, one `ASSIGN` event with sequence `1`,
  Starting/PR Head both equal to the repair starting Head and `single_writer: true`.
- Authorized independent evidence producer:
  `task-029-environment-verification-codex-windows-1` / `qifuxiao` /
  Environment Verification Agent / Codex / Windows / `portable`.
- This producer is evidence-only and may act only after the Coordinator-authored Handoff v2 and
  final repaired exact Head exist. It is not another Implementation writer.

## Objective and preserved product result

Repair `scripts/validate_agent_environment.py` and `scripts/validate_ai_handoff.py` so they validate
TASK-029's explicitly frozen post-implementation topology, paths, and evidence from the exact Git
Head while preserving historical standard Handoff validation, TASK-057 v3/v4, and every fail-closed
trust boundary.

The product implementation and acceptance evidence at the repair starting Head are retained. The
installed Risk Schema bundle, checksum/version/reference verification, package-resource-only loader,
shared Schema-then-semantic validation entry, immutable output construction, Runner, v1 projection,
v2 envelope, and their tests are not implementation targets and MUST NOT be rewritten. Those prior
results are historical after any Head change; the same six commands must run again on the repaired
exact Head before formal environment evidence.

## Exact repair scope

The later assigned repair implementation may modify only:

- `scripts/validate_agent_environment.py`;
- `tests/spec/test_validate_agent_environment.py`;
- `scripts/validate_ai_handoff.py`;
- `tests/spec/test_validate_ai_handoff.py`.

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

### Frozen topology and repository-relative paths

Handoff topology identity is explicitly `post_implementation_repair_v1`, allowlisted only for:
`TASK-029` / `TASK-029-PLAN-v2` / `TASK-029-EVIDENCE-REPAIR-v2` /
`ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml` / PR `110` /
Base `b4b3f07c734c894032bd02f98e8cc914aa26f5d5` /
Planning Base `1bc232d367261302b397556b36a6b3284f8784d7`.

The repaired Handoff validator must prove:

- expected Base equals live PR Base and is an ancestor of Planning Base;
- Planning Base equals the exact PR Head at repair authorization and canonical assignment;
- initial coordination commit `33584e39a31b04b5a9d14a5c3b39c8c06a3889c0` has Planning Base
  as its sole parent;
- every commit from Planning Base through frozen final coordination commit changes only
  `tasks/active/TASK-029-risk-runtime-schema-contract.md` and this Repair Packet;
- PR-Base historical task blob `131eadc3c966db0f2173539a040aaa45a02959fa` may differ from the
  Plan-v2 blob only for this exact topology; Plan-v2 blob is identical at Handoff parent and Head;
- Handoff introduction has the exact frozen final coordination commit as its sole parent and adds
  only the exact Handoff-v2 path; Handoff content remains continuously immutable thereafter;
- PR Base remains the final PR Head's merge-base and all existing product commits remain unchanged.

Do not infer topology from filenames, branches, glob recency, arbitrary fields, caller parameters,
or evidence. Historical standard Handoff and TASK-057 v3/v4 behavior must remain unchanged.

Allowed-path repair must use deterministic repository-relative semantics for exact literal paths
and existing `/**` subtree patterns. Check Handoff and task allowlists independently, then apply
forbidden paths with unconditional rejection precedence. Reject absolute/backslash paths, empty or
dot segments, parent traversal, malformed glob syntax, and paths outside the repository. Caller or
evidence input, branches, or filenames cannot provide authority.

Tests must prove exact-path and subtree-descendant acceptance; sibling/non-descendant rejection;
forbidden precedence; malformed/traversal rejection; coverage of every PR #110 Base...Head path;
and fail-closed behavior when either accepted historical Catalog or Risk export path is removed
from either frozen allowlist. Add positive and negative real-Git topology tests for every frozen
ancestry, coordination-path, task-blob, introduction-parent, add-only, and history constraint above.

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

The Handoff freezes one required `portable` lane with capability `portable`, `minimum_records: 1`,
and the six commands above, in the exact task order; `windows_miniqmt` is prohibited. No task
verification command or delivery field changes. Both formal validators and all six TASK-029
commands must exit `0` at the final repaired exact Head with applicable frozen/live inputs.

### Authorized pre-repair result

Execute the current unmodified Handoff validator with the exact task, Handoff-v2, PR Base, and new
Handoff Head. Record actual exit code and all messages as `EXPECTED_PRE_REPAIR_FAILURE` only for:

1. reversed planning-ancestry requirement;
2. historical PR-Base task blob differing from amended Plan-v2 task blob;
3. Handoff introduction parent being the final coordination commit rather than PR Base;
4. literal-versus-`/**` allowed-path matching incompatibility.

Multiple affected-path lines belong to the fourth class; they are not individual waivers. Any
other error is `PLAN_BLOCKED`. The result is not passed, waived, skipped, or final evidence.
`validate_specs.py`, schema/identity/assignment/producer/lane/command/blob/path audits, and
`git diff --check` must succeed before push. The environment validator's pre-existing TASK-057-only
gate remains an implementation repair target, not satisfied evidence.

## Frozen continuation sequence

1. Recreate the Plan/Packet amendment directly on remote initial coordination commit
   `33584e39a31b04b5a9d14a5c3b39c8c06a3889c0`; change only the active TASK-029 and this Packet.
2. Verify all five Human authority comments, including canonical assignment `5551747729`.
3. The Coordinator creates an add-only Handoff v2 that freezes the exact coordination commit,
   amended task blob, Packet blob, live PR authority, assignment identity/digest, producer allowlist,
   and deep-equal lanes/commands.
4. After authorized pre-repair checks, push only the two new commits to the existing repair branch
   and stop. Later, the original sole Implementation Agent starts at the frozen PR Head and merges
   the exact Coordinator branch with `git merge --no-ff`, preserving all coordination commits.
   Synchronization must precede red tests or validator edits. It then records red tests, repairs only
   the two validators and their tests, commits, and pushes to the existing Implementation PR.
5. All six commands rerun against the new exact Head. The independently assigned Environment
   Verification Agent publishes canonical evidence, and the formal validator validates it live.
6. New exact-Head CI completes, followed by Independent Review and Human-only Approval/merge.
7. Closeout and any TASK-005 state change require separate Human authority and a separate PR.

Any missing or out-of-order gate is `PLAN_BLOCKED`.

## Explicitly forbidden

- creating Handoff v2 before its separate add-only commit on the recreated amendment;
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
- Repair requires any path beyond the four exact implementation targets.
- Historical TASK-057 behavior cannot be preserved, or TASK-029 support would weaken a trust,
  command, capability, side-effect, schema, or fail-closed boundary.
- Any final exact verification command fails, is waived, or is not represented truthfully in
  evidence; any pre-repair error falls outside the four explicitly authorized classes.
- TASK-005 ceases to be blocked before separate exact-Head Review and Human authorization.
