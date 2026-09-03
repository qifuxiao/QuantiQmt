# TASK-057 final mypy stub compatibility repair packet

## Frozen identity

- Task: `TASK-057`
- Plan: `TASK-057-PLAN-v4`
- Packet identity: `TASK-057-MYPY-STUB-COMPAT-v4`
- Packet path: `ai/packets/TASK-057-MYPY-STUB-COMPAT-v4.md`
- Exact Base: `872aa7666f8811ad3a1e49b671a9c1290085330a`
- Repair branch: `codex/task-057-final-repair`
- Bootstrap phase: `packet-only`
- Canonical Human assignment: `pending`
- Repair v4 Handoff: `pending`
- Implementation Agent: `pending`
- Repair PR number, URL, and packet-only PR Head: `pending until this packet-only commit is pushed and the new PR exists`

This packet is freshly authored under the Human final recovery authority in
<https://github.com/qifuxiao/QuantiQmt/pull/105#issuecomment-5521721079>. It does
not reuse the superseded PR #105 Packet blob or treat that PR, its branch, commit,
Packet, or assignment as current authority. PR #105 must remain closed and
unmerged, and `codex/task-057-mypy-stub-compat-repair` must not be modified,
rebased, force-pushed, or reused.

## Immutable bootstrap baseline

The packet-only commit must have the exact Base above and may add only this
file. At bootstrap time TASK-057 is the only active task, TASK-055 and TASK-056
are completed, and neither this Packet nor `ai/handoffs/TASK-057-REPAIR-v4.yaml`
exists on the exact Base.

The historical TASK-057 Handoff blobs on the exact Base are frozen and must
remain byte-for-byte unchanged:

- `ai/handoffs/TASK-057-IMPLEMENTATION-v1.yaml`: `3a974140e42b717491bb8e2989c3e1c738a24dc3`
- `ai/handoffs/TASK-057-REPAIR-v2.yaml`: `b833798dfe3b3273e82b19d99984dec2a2bee1ca`
- `ai/handoffs/TASK-057-REPAIR-v3.yaml`: `89e7ea742badc4a0d698b3920ac0b52457ebfae6`

The existing TASK-057 v3 Handoff verification command remains the historical
immutable-baseline verification. It does not identify or authorize this v4
repair.

## Minimum authorized repair

No implementation is authorized in the packet-only phase. After the required
assignment and Handoff gates are complete, the assigned Implementation Agent
may make only the minimum test-first repair needed to:

1. preserve support for historical `TASK-057-PLAN-v3` / `REPAIR-v3` authority;
2. support current `TASK-057-PLAN-v4` / `REPAIR-v4` authority;
3. reject unknown or mismatched Plan/Handoff identities;
4. preserve the exact historical PR #100 Head test;
5. add current v4 positive and identity-mismatch tests; and
6. make the two `jsonschema` imports in `scripts/validate_specs.py` and
   `scripts/validate_agent_environment.py` mypy-compatible without changing
   validator runtime behavior.

The candidate annotation `# type: ignore[import-untyped,unused-ignore]` is
permitted only if the same exact implementation Head proves
`poetry run mypy src scripts` with exit code 0 in both actual environments:

- a lock-compatible environment without `types-jsonschema`; and
- a Reviewer-class environment with `types-jsonschema` present.

Neither environment may add, remove, synchronize, or upgrade project
dependencies. The repair must not use a bare `# type: ignore`, disable or relax
`warn_unused_ignores`, change mypy configuration or the frozen command, use
`Any` or dynamic imports to evade checks, or alter validator behavior.

## Required continuation order

1. Push this single-file packet-only commit and open the new Repair PR.
2. Stop; a Human publishes a new, unedited canonical assignment on that PR.
3. The Coordinator creates an add-only
   `ai/handoffs/TASK-057-REPAIR-v4.yaml` commit that freezes the existing PR,
   assignment, exact Base, packet path/blob, PR number, and packet-only PR Head.
4. The assigned Implementation Agent's first writer action synchronizes that
   Coordinator-authored Handoff commit without rewriting it.
5. Only then may that agent implement the minimum test-first repair and produce
   dual-environment mypy evidence for the same exact Head.
6. Run full TASK-057 verification and CI, obtain independent Review of the
   exact Head, and leave merge to the Human.
7. Use a separate Closeout PR, independent closeout Review, and Human merge.

Any missing, changed, or out-of-order identity or gate is `PLAN_BLOCKED`.

## Prohibited scope

This packet does not authorize creating the v4 Handoff, assigning an
Implementation Agent, changing scripts or tests, implementing the repair,
self-reviewing, approving, merging, closing out TASK-057, or accessing Mini QMT.

No dependency, lockfile, mypy configuration, CI, spec, business-code,
completed-task, migration, `.clinerules`, v1/v2/v3 Handoff, or Mini QMT change is
authorized. No Mini QMT connection, account query, order, or cancellation is
authorized. `scripts/validate_ai_handoff.py` and its tests must remain unchanged.

After bootstrap, implementation remains bounded to the Human-authorized paths:

- `scripts/validate_specs.py`
- `scripts/validate_agent_environment.py`
- `tests/spec/test_validate_agent_environment.py`
- `ai/packets/TASK-057-MYPY-STUB-COMPAT-v4.md`
- `ai/handoffs/TASK-057-REPAIR-v4.yaml`

These later paths are not authorized changes in the current packet-only commit.
