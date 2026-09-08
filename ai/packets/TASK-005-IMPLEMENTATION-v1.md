# TASK-005 Implementation Packet v1

## Frozen identity and bootstrap boundary

- Repository: `qifuxiao/QuantiQmt`
- Task: `TASK-005`
- Plan: `TASK-005-PLAN-v1`
- Packet identity: `TASK-005-IMPLEMENTATION-v1`
- Expected Implementation Base / PR Base: `b9b313d2af1071281bc62c0919ee4caceae85825`
- Historical task Planning Base: `f09811a17972d1d446a95806821fd80586858e11`
- Branch: `codex/task-005-implementation`
- Task path: `tasks/active/TASK-005-risk-engine.md`
- Frozen task blob: `b5d10367c43294cc61543bdeb779717ff99e94b7`
- Stage: packet-only bootstrap; this first commit adds only this Packet.
- Canonical Human assignment: pending.
- Implementation Agent and environment producer: pending, not assigned.
- Handoff: pending; `ai/handoffs/TASK-005-IMPLEMENTATION-v1.yaml` does not yet exist.
- Single writer: no implementation writer is established before Human assignment.
- Release and Mini QMT access: prohibited.

Preparation was merged in [PR #116](https://github.com/qifuxiao/QuantiQmt/pull/116),
following activation in [PR #115](https://github.com/qifuxiao/QuantiQmt/pull/115).
This Packet is design/handoff input, not implementation authorization, acceptance evidence,
an environment record, or a Review. The new PR number and packet-only Starting Head are
to be bound from actual GitHub objects by the subsequent canonical assignment; they are
not self-referential identities invented in this commit. Do not merge the packet-only PR.

## Goal, authority, and non-goals

Deliver the active task's deterministic Risk evaluator and complete auditable outcomes
using immutable RiskInput and RuleSet. Read root and nearer AGENTS.md, spec/README.md,
spec/manifest.yaml, the exact task, and every task spec_ref before implementation.
All ten task acceptance criteria remain authoritative and unchanged.
TASK-003, TASK-015 and TASK-029 must remain trusted completed dependencies.

Existing model, evaluator, runner, audit and Risk tests are the starting implementation,
not an empty subsystem. Build an acceptance-to-test evidence matrix, identify actual gaps,
write failing tests first, then make only necessary changes. Existing compliant behavior
must be retained; passing historical tests alone do not establish current acceptance.
Reuse TASK-029's installed Schema bundle and Schema -> semantics -> deep-freeze boundary.
Do not define a new DTO, DSL, Event, error code, workflow, or state transition.

Expected demonstration: fixed immutable inputs repeatedly produce identical semantic
Decision bytes, UUID5 and hash; invalid snapshots and hard-limit violations reject;
injected-clock timeout produces an auditable REJECT that late PASS cannot replace.
This is a local portable Risk demonstration, not Mini QMT or end-to-end trading acceptance.

## File plan and acceptance mapping

The assigned implementer may modify only `src/quantiqmt/risk/**`,
`tests/unit/risk/**`, and `tests/property/risk/**` under the task/Handoff intersection.
Use existing files and add tests in those directories only when necessary.

| Task acceptance | Primary implementation / test focus |
| --- | --- |
| 1: ordering and strictest result | evaluator.py; unit and property permutations across all scopes, priority ties, multiple limits and REJECT dominance |
| 2: fail-closed taxonomy | evaluator.py/model.py; each snapshot/input/RuleSet failure and exact canonical code, including competing failures |
| 3: deterministic bytes and identity | model.py/evaluator.py; repeated inputs, canonical hash/UUID5 and exclusion of timestamps/latency |
| 4: hard safety limits | evaluator.py; all fixed hard rules, attempted removal/relaxation and reduction exceptions |
| 5: explicit reduction proof | evaluator.py; version, reservation, quantity, non-flip and identity boundaries; side/CLOSE/AUTO are insufficient |
| 6: complete audit and projection | runner.py/audit.py/model.py; typed values, all results, independent monotonic timings, v2 and lossy v1 mapping |
| 7: audit semantic rejection | audit.py and schema-boundary tests; missing/duplicate/extra/reordered/mismatched timings, indices/count/sum and timeout position |
| 8: currency | evaluator.py/model.py; valid single-currency cases and each inconsistent currency/limit, without FX fallback |
| 9: purity and bounded timing | evaluator.py/runner.py; injected Clock only outside evaluator, bounded workers and no I/O or mutable external state |
| 10: properties and failure boundaries | tests/property/risk/** plus unit regressions; permutations, hard caps, taxonomy, explicit reduction, Decimal/float and fenced late output |

Do not short-circuit business rules at the first rejection. Preserve the normative
input-guard early rejection and first-failure ordering. Keep monetary calculations Decimal,
never float or guessed defaults. Preserve bounded worker saturation/timeout handling,
attempt fencing, and the ban on same-input re-evaluation after timeout. Preserve mandatory
metrics with low-cardinality labels and audit/error paths; no new trading side effects.
Projection must reject invalid audit rather than repair, reorder or coerce it.

## Scope exclusions and frozen files

The eventual PR path audit may include this Packet and the add-only Handoff, but those
files are immutable authority, not implementation edit permissions. Future Handoff must
not inherit preparation-only task, validator or spec-test permissions from PR #116.
Do not modify tasks, scripts, tests/spec, spec, shared contracts, Order, Broker, storage,
CI, dependencies/lockfiles, historical Packets/Handoffs or unrelated files.
Do not access Mini QMT, accounts, market data, database, Redis, Broker or trading APIs;
do not activate other tasks or perform release/closeout. Runtime evaluator purity does
not prevent authorized GitHub/CI coordination outside runtime code.

## Required portable verification

Copy these exact opaque declarations into the Handoff without replacement or reordering:

```yaml
required_lanes:
  - lane: portable
    capability: portable
    minimum_records: 1
    commands:
      - poetry run pytest tests/unit/risk tests/property/risk
      - poetry run mypy src/quantiqmt/risk
prohibited_lanes:
  - windows_miniqmt
```

Both original commands must exit 0. The task grants no skip exemption. Record actual
passed/failed/skipped counts, versions, exact source import path and Head; do not reuse
another Head's results. Follow ai/workflows/poetry-verification.md; reuse a verified
compatible environment, do not install dependencies or manufacture environment evidence.
Supplemental specs, focused Ruff, diff and path/blob checks do not replace either command.
Live Handoff and environment validators must succeed after the authority chain exists.
Synthetic fixtures and bootstrap checks are not formal environment evidence.

## Standard topology and execution sequence

1. Create this packet-only PR from the exact Expected Base; stop for Human assignment.
2. Human publishes an immutable canonical assignment on that actual PR, binding exact
   Base, branch, packet-only Starting/PR Head, one writer and authorized evidence producer,
   role/tool/OS/lane, and ordered assignment events under the formal schema.
3. Coordinator independently creates an add-only Handoff commit whose parent is the same
   Expected Base, freezing task/Packet/assignment and strict scope. Handoff filename stem
   and packet_version are both `TASK-005-IMPLEMENTATION-v1`.
4. The existing `repair_context.superseded_head_sha` field binds the real packet-only
   Starting Head; this schema field name does not imply a fictional prior Repair PR.
5. Assigned Implementation Agent first synchronizes that Coordinator commit using a
   non-rewriting merge; no cherry-pick, squash, rebase or Handoff edits. Validate the full
   topology with the actual merge Head before business changes. Task blob stays identical
   at Base and Head. Preserve every frozen authority blob throughout implementation.
6. Test-first minimal implementation, full acceptance matrix and original commands;
   push to this same PR, then exact-Head CI and authorized portable environment evidence.
7. Independent Review of the final exact Head, Human Approval/merge, then separately
   authorized Closeout. An implementation report does not perform any later role.

## Stop and failure handling

Return PLAN_BLOCKED for Base/main drift before bootstrap, missing/untrusted dependencies,
missing assignment or Handoff, multiple writers, dirty overlapping work, scope/spec
conflict, invalid topology, validator failure or any missing required evidence. Report
the exact error and affected authority; never broaden paths, exempt a test, relax a
validator or invent a waiver. A genuine contract change requires separate Human direction.
Do not claim acceptance or start implementation during this packet-only phase.
