# TASK-029 Implementation Packet v1

## Frozen identity and bootstrap state

- Task: `TASK-029`
- Plan: `TASK-029-PLAN-v1`
- Packet identity: `TASK-029-IMPLEMENTATION-v1`
- Packet path: `ai/packets/TASK-029-IMPLEMENTATION-v1.md`
- Repository: `qifuxiao/QuantiQmt`
- Expected Implementation Base / PR Base: `b4b3f07c734c894032bd02f98e8cc914aa26f5d5`
- Branch: `codex/task-029-implementation`
- Current stage: `packet-only bootstrap`
- Canonical Human assignment: `pending`
- Handoff: `pending`
- Implementation Agent: `pending`
- Single writer: no implementation writer may exist before the canonical Human assignment
- Packet-only Starting Head / PR Head: the SHA of the first commit that adds only this Packet;
  it remains pending until that commit is pushed and the independent Implementation PR exists

This Packet is the only authorized addition in the bootstrap commit. It does not assign an
Implementation Agent, create a Handoff, or authorize implementation. The Packet consumer must use
the exact Base, branch, Plan, Packet blob, PR identity, canonical Human assignment, and later
Coordinator-authored Handoff; any drift is `PLAN_BLOCKED`.

## Authority and invariant baseline

The bootstrap preflight must prove all of the following before this file is committed:

- activation PR #109 remains merged with Head
  `376ed9054a3330f5b78e1776295e5f0dae43291f`;
- PR #109 merge commit and live `main` both equal the exact Implementation Base above;
- TASK-029 is the unique active task;
- TASK-015, TASK-030, and TASK-031 are trusted completed dependencies;
- TASK-005 remains `backlog/blocked`;
- the worktree is clean and neither this Packet nor
  `ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml` exists on the Base.

The implementation must preserve every accepted Event, DTO field/type, error/reason code, Risk
rule, ordering rule, timeout rule, reduce-only rule, metric, state transition, and the mandatory
`OrderIntent -> OMS registration -> Risk -> OMS transition -> Execution` chain. TASK-029 may add
only deployable Schema/Catalog routing, a package-resource-only bundle/loader, the shared output
validation boundary, immutable construction integration, bounded diagnostics, and tests required
by the active task. It must not access Mini QMT, query an account or market data, submit/cancel an
order, activate TASK-005, or introduce a parallel business contract.

## Frozen schema identities and validation boundary

The implementation must use the accepted schema graph rather than copy it into hand-written output
checks:

- `RuleResult` resolves through `CONTRACT-RISK-ORDER-EVALUATED-V2` at the exact JSON Pointer
  `/properties/decision/properties/rule_results/items` unless an already accepted Catalog identity
  is present at the implementation Head. No new DTO or looser parallel schema is permitted.
- `RiskDecisionV1` resolves through `CONTRACT-RISK-DECISION-V1`, whose accepted `$ref` targets the
  v2 `decision` fragment.
- `RiskAuditOutputV1` resolves through `CONTRACT-RISK-AUDIT-OUTPUT-V1`, whose accepted `$ref` targets
  the v2 root.
- `risk.order_evaluated.v2` resolves through the active `CONTRACT-CATALOG` message route and the
  same v2 schema graph.

The package bundle must carry the reviewed manifest version, Catalog routes, the complete referenced
Risk graph, stable contract/path identities, content and document digests, and resolvable JSON Schema
references. Runtime code may load it only with `importlib.resources` from the installed
`quantiqmt.contracts.resources` package. It must never read repository `spec/**`, the current working
directory, a caller-provided source root, an older resource, a default payload, or a permissive
fallback. Source checkout, installed wheel, and container-equivalent installed-package execution
must therefore use the same bytes and produce the same accepted/rejected results.

Every output factory and construction path must follow exactly:

1. assemble a primitive candidate without coercion, repair, sorting, deduplication, or defaults;
2. run Draft 2020-12 Schema validation using the shared contracts-owned entry;
3. run the existing `PORTS-RISK` semantic validator in its normative first-failure order; and
4. deep-freeze and return only after both validation stages succeed.

Runner completion, v1 compatibility projection, and v2 envelope construction must use that same
entry. Any unknown contract identity, invalid candidate, missing/partial/damaged bundle, digest or
manifest-version mismatch, or unresolved reference must fail startup or fail closed at the boundary
with bounded, non-sensitive diagnostics. Failure must prevent freezing/returning an invalid DTO,
v1 projection, persistence/publication, approved OMS transition, and entry into Execution. There is
no retry or fallback path for invalid output.

## Tests-first file plan

The assigned Implementation Agent must first add failing tests/fixtures within these exact allowed
areas, commit or otherwise preserve auditable red evidence, and only then make the minimum runtime
changes needed for green:

- `tests/spec/**`: manifest/Catalog identity, version, compatibility, migration, rollback, package
  resource inclusion, and source-spec independence assertions;
- `tests/contract/messages/**`: accepted and rejected `RuleResult`, `RiskDecisionV1`,
  `RiskAuditOutputV1`, and `risk.order_evaluated.v2` fixtures, including UUID/hash, UTC-Z,
  reason/error code, priority, typed-value, nested-field, array-bound, and additional-property cases;
- `tests/unit/contracts/**`: shared route/resolver behavior; checkout/package parity; non-source
  working directory; missing, malformed, partial, content/document/bundle-digest-mismatched,
  unresolved-reference, and manifest-version-mismatched resources; isolated installed-wheel and
  main-package-only behavior;
- `tests/unit/risk/**` and `tests/property/risk/**`: all output factories and Runner/audit/envelope
  paths prove `Schema validation -> semantic validation -> freeze`, deep immutability, shared-entry
  use, fail-closed propagation, and no repair/coercion/retry.

Only after the red phase may implementation touch the minimum necessary subset of:

- `spec/manifest.yaml`, `spec/contracts/catalog.yaml`, `spec/contracts/risk/**`, and
  `spec/contracts/events/risk.order_evaluated.v2.schema.json` for the versioned Catalog/manifest
  routing and compatibility/migration/rollback record, without changing accepted fields or meaning;
- `src/quantiqmt/contracts/bundle.py`, `registry.py`, `validation.py`, `errors.py`, `__init__.py`, and
  `resources/schema-bundle.v1.json` for deterministic package-resource loading/resolution and
  bounded existing-exception diagnostics;
- `src/quantiqmt/risk/model.py`, `audit.py`, `runner.py`, and, only if the common factory call graph
  requires it, `evaluator.py` for the unified validation boundary.

`pyproject.toml` is not planned for modification because package-resource inclusion already exists;
if the wheel cannot carry the bundle without changing packaging metadata, the agent must stop and
request a narrowly reviewed Packet/Handoff update rather than changing dependencies. `poetry.lock`,
CI, migrations, Broker/Order code, task files, and every path outside TASK-029 `allowed_paths` are
not implementation targets.

## Acceptance-to-evidence matrix

| TASK-029 acceptance criterion | Planned allowed path(s) | Red -> green stage | Exact verification command(s) | Success evidence | Failure / fail-closed behavior |
|---|---|---|---|---|---|
| All Risk output Schemas have a formal Catalog identity/version, fixtures, and validator route | `spec/manifest.yaml`; `spec/contracts/catalog.yaml`; accepted Risk schemas; `tests/spec/**`; `tests/contract/messages/**`; packaged bundle | Red: identity/fragment/route and fixture tests fail. Green: manifest-indexed resource exposes only accepted IDs/routes and exact fragments. | `poetry run python scripts/validate_specs.py`; `poetry run pytest tests/spec tests/contract tests/unit/contracts` | Validator resolves RuleResult fragment, Decision, Audit, and v2 route from one verified graph; all valid/invalid fixtures produce expected outcomes. | Unknown/duplicate/missing ID, path, fragment, or route rejects bundle/validation; no handwritten fallback. |
| Installed wheel/container validates without source `spec/**` | `src/quantiqmt/contracts/**`; `tests/unit/contracts/**` | Red: installed-wheel test from a non-source cwd with source unavailable fails. Green: package resource alone validates accepted and rejected fixtures. | `poetry build`; `poetry run pytest tests/spec tests/contract tests/unit/contracts` | Attributable wheel contains the bundle; isolated main-package-only test runs with source tree/spec unavailable and final contract run has zero wheel-related skips. | Missing resource fails startup/boundary; never reads checkout, cwd, environment, or caller source root. |
| Missing, damaged, or version-mismatched Schema is observable and fail closed | `src/quantiqmt/contracts/bundle.py`; `registry.py`; `errors.py`; `tests/unit/contracts/**` | Red: tamper matrix exposes current gaps. Green: each corruption class raises bounded existing exception/diagnostic before validator exposure. | `poetry run pytest tests/spec tests/contract tests/unit/contracts`; `poetry run mypy src/quantiqmt/contracts` | Separate tests cover absent, malformed, partial, digest, version, and unresolved-ref cases with non-sensitive deterministic messages. | No older bundle, partial validator, default, retry, or source fallback is selected. |
| Every output factory and v2 envelope uses one formal Schema + semantic entry | `src/quantiqmt/contracts/validation.py`; `registry.py`; `src/quantiqmt/risk/model.py`; `audit.py`; `runner.py`; conditionally `evaluator.py`; unit/property tests | Red: call-path spies and invalid semantic candidates prove bypasses. Green: every path calls the contracts-owned entry before freeze/project/envelope. | `poetry run pytest tests/unit/risk tests/property/risk`; `poetry run mypy src/quantiqmt/contracts` | Tests prove shared entry use and exact Schema -> semantic -> freeze order for RuleResult, Decision, Audit, Runner, v1 projection, and v2 envelope. | First failure stops construction and downstream OMS/publish/Execution effects; no repair or retry. |
| Formal Schema covers priority, reason/error code, UUID/hash, UTC-Z, typed value, nesting, and arrays | accepted Risk schemas and exact fragment routes; `tests/contract/messages/**`; `tests/property/risk/**`; packaged bundle | Red: one mutation per boundary is rejected by expected schema location. Green: accepted boundary vectors pass unchanged and invalid mutations fail. | `poetry run pytest tests/spec tests/contract tests/unit/contracts`; `poetry run pytest tests/unit/risk tests/property/risk` | Mutation/property matrix covers lower/upper bounds, enums/patterns, additional properties, typed unions, and nested/array limits. | Invalid/unknown values remain invalid; no coercion, truncation, default, reordering, or enum expansion. |
| Tests cover checkout, wheel/main-only, bundle failures/version drift, and all output fixtures | `tests/spec/**`; `tests/contract/messages/**`; `tests/unit/contracts/**`; `tests/unit/risk/**`; `tests/property/risk/**` | Red suite is recorded before runtime edits; green suite covers every named environment/failure mode. | `poetry run pytest tests/spec tests/contract tests/unit/contracts`; `poetry run pytest tests/unit/risk tests/property/risk` | Both commands exit 0; wheel-related tests are executed, not skipped; checkout and installed results are byte/diagnostic equivalent where applicable. | Any missing case, skip, divergent result, or inability to isolate source `spec/**` leaves the task blocked. |
| TASK-005 remains blocked until exact-Head independent APPROVE | read-only assertions over `tasks/backlog/TASK-005-risk-engine.md`, `tasks/index.yaml`, and active-task state; no implementation mutation | Red/green are governance assertions: the implementation diff must preserve TASK-005 blocked and TASK-029 active. | `poetry run python scripts/validate_specs.py`; exact Base...Head path audit | TASK-005 remains blocked in file/index; no TASK-005 implementation path changes; later activation requires separate Human authority after exact-Head Review. | Any activation, evaluator scope expansion into TASK-005, or task-state change is `PLAN_BLOCKED`. |
| Manifest version plus compatibility, migration, deployment, and rollback are synchronized | `spec/manifest.yaml`; generated `src/quantiqmt/contracts/resources/schema-bundle.v1.json`; `src/quantiqmt/contracts/bundle.py`; `tests/spec/**`; `tests/unit/contracts/**` | Red: parity/version/lifecycle assertions fail. Green: one reviewed version and digest set is consistent in spec, loader, and wheel. | `poetry run python scripts/validate_specs.py`; `poetry run pytest tests/spec tests/contract tests/unit/contracts`; `poetry run mypy src/quantiqmt/contracts` | Manifest and bundle version match; compatibility is no public DTO/Event/error/state change; migration is package replacement only; deployment is reader/validator before use; rollback selects only a prior accepted packaged bundle while Risk stays closed. | Version drift or rollback to source lookup fails startup/closed; inability to preserve public compatibility requires a separate spec-change task. |

After the above acceptance commands pass, the exact Head must also pass:

- `poetry run ruff check .`
- `poetry run ruff format --check .`

The six active-task `verification.commands` are opaque exact strings and must later be partitioned
without omission or substitution into the Handoff's required environment lane declarations.
`poetry build` is the task-Plan-required artifact setup/evidence step; it does not replace any of the
six commands.

## Wheel and container-equivalent evidence

The assigned agent must follow `ai/workflows/poetry-verification.md`: record sanitized Poetry/Python
environment facts; inventory every pre-existing `dist/` artifact with size and checksum; run the
exact `poetry build`; identify only attributable new artifacts; and never delete, overwrite, or
rename an existing/user-owned artifact. The final contract command must execute the isolated-wheel
case with zero wheel-related skips.

The isolated test must install or unpack only the attributable wheel into a temporary test-owned
location, run from a non-source working directory with repository `spec/**` unavailable, import the
installed `quantiqmt` package rather than `src/`, validate representative accepted and rejected
output fixtures, and exercise missing/damaged/version-mismatched resource diagnostics. It must not
install/upgrade project dependencies, create an unapproved persistent environment, use the source
checkout as a runtime fallback, or claim a Mini QMT/container capability that was not tested.

## Required continuation order

1. Push the packet-only commit and create the independent TASK-029 Implementation PR.
2. Stop. A Human publishes the unedited canonical assignment on that PR.
3. The Coordinator creates one add-only `ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml` commit freezing
   repository, PR, Base, packet path/blob, packet-only PR Head, assignment identity/digest, producer
   allowlist, and deep-equal required/prohibited lanes and commands.
4. The assigned Implementation Agent first synchronizes the Coordinator-authored Handoff without
   rewriting it; its Starting Head must equal the assigned PR Head and single-writer event state.
5. The assigned Implementation Agent records failing tests, performs the minimum implementation,
   runs all required verification, and publishes required exact-Head environment evidence.
6. Exact-Head CI completes, then an Independent Review Agent reviews that unchanged Head.
7. A Human alone may approve and merge the Implementation PR.
8. A Human separately records closeout authorization; a distinct Closeout PR performs only the
   authorized active-to-completed transition and remains subject to independent Review/Human merge.

Any missing or out-of-order gate, Base/Head/Packet/Handoff/assignment drift, concurrent writer,
failed or skipped required command, or changed Head after evidence/Review is `PLAN_BLOCKED`.

## Explicitly unauthorized in this bootstrap

This bootstrap does not authorize creating a Handoff; editing Python, tests, spec, task, dependency,
lockfile, or CI files; starting implementation; assigning an agent; self-reviewing; approving;
merging; closing out TASK-029; activating or implementing TASK-005; releasing software; connecting
to Mini QMT; querying accounts or market data; or sending/cancelling any order. Real-money trading
remains forbidden.
