# PORTS-CONTROL — Control Plane L4 Ports

Status: Draft. Owner: ControlPlane. This contract freezes logical Port
preconditions, postconditions and failure semantics. It does not freeze runtime
classes, database tables/indexes, repository layout, or an in-memory history.

## Trust boundary

Control validation distinguishes four layers:

1. Untrusted wire DTOs and Events are validated for structure, enum, exact
   number/time representation, scope, identity and checksum/fingerprint
   integrity.
2. Immutable Domain objects, opaque references and Protocol return values are
   valid Application operation inputs; not every internal value is a public
   JSON DTO.
3. A checksum/fingerprint proves stored-content integrity or canonical content
   identity. It is not a signature and does not establish source authorization.
4. Source authenticity comes from controlled logical Ports backed by committed
   PostgreSQL transactions, access control, exact query keys and CAS/unique
   constraints.

The trust anchors in this task are `control_journal`,
`versioned_config_store`, Inbox and Outbox. Contract tests may corrupt a wire
DTO or a stored record without updating its stored checksum. They MUST NOT model
an attacker who controls a trusted Port return value and recomputes every hash;
Port provenance, transaction and CAS correctness belong to TASK-025 or an
independent storage integration task. Accepted facts never recursively prove
the authenticity of other accepted facts.

## Logical authority Ports

The names below are descriptive logical contracts, not prescribed Python APIs:

- `ControlJournalPort.read_command(identity)` and `read_result(identity)`
  return one committed immutable record or absence using the exact typed key.
  Appends use expected-version CAS and a unique idempotency identity.
- `RecoveryBarrierReadPort.read_exact(scope, barrier_reference)` returns one
  immutable `RecoveryBarrierSnapshot` containing scope, barrier version, stored
  checksum and the committed `RecoveryBarrier`; it never returns an arbitrary
  caller-selected payload.
- `VersionedConfigStorePort.read_active(domain)` and `read_result(identity)`
  return the committed ActiveVersion/result selected by an exact key.
- `InboxPort.read_accepted(message_id)` returns an `AcceptedMessageRef` with
  message ID, correlation ID, occurred/accepted times and aggregate ordering
  fields. It does not replay the parent payload through the child validator.
- Outbox persistence shares the authoritative state-change transaction required
  by the corresponding workflow.

PostgreSQL `control_journal` remains System Mode/Kill Switch authority;
its recovery ordering follows `WF-RECOVERY`.
Component memory is cache only. Physical repository/table/index/migration
design remains outside TASK-022.

## Scope and validation operations

`ControlScope = {scope_type, scope_id}` where type is `GLOBAL`, `ACCOUNT`,
`STRATEGY`, or `INSTRUMENT`. GLOBAL requires null ID; all others require a
non-empty ID. The key is `GLOBAL` or `{scope_type}:{scope_id}`. Command, result,
state and Event scopes match exactly; scoped Envelope aggregate/partition keys
equal the scope key.

Implementations may organize code freely, but must provide behavior equivalent
to these operations:

- `ValidateControlEvent(envelope, payload, optional prior state,
  AcceptedMessageRef when non-root, injected time)`.
- `ValidateRecoveryPassed(transition, exact barrier reference,
  RecoveryBarrierSnapshot, injected time)`.
- `ValidateKillSwitchCommand(command, current scoped state, authorization,
  lease, RecoveryBarrierSnapshot when disabling, optional prior committed
  command record, injected time)`.
- `ValidateKillSwitchResult(result, committed command record, optional prior
  committed result, current scoped state, expected effect ACKs, injected time)`.
- `ValidateConfigActivation(candidate/result, policy, component capabilities,
  hard limits, current ActiveVersion, optional prior committed result, injected
  time)`.

Schema validation alone never authorizes persistence, publication, consumer
apply, transition, barrier opening or an external side effect.

## Public fact Events and lineage

The four Events use canonical `MessageEnvelopeV1`; the Control combined schema
only refines its existing fields. Each Event binds type/version/source,
aggregate/partition/version, occurred time and idempotency identity to payload.
Root Events have null causation and `correlation_id = message_id`. Non-root
Events require an `AcceptedMessageRef`; child causation/correlation and
time/order must match that reference. Parent wire validation occurred at parent
ingress and is not recursively repeated.

- `system.mode_changed.v1`: legal persisted transition only.
- `system.component_health_changed.v1`: `generation` fences an instance;
  `state_version` orders component transitions and binds aggregate version.
  The producer allocates `previous + 1` through transition persistence/CAS.
  Consumers treat equal/lower versions as duplicate/stale and defer, replay or
  fail visibly on a gap. A single wire schema validates range, not prior state.
- `system.kill_switch_changed.v1`: committed APPLIED state change only.
- `config.version_activated.v1`: only the atomic
  `ActiveVersion + Event + Outbox` success fact. REJECTED, PARTIAL, ROLLED_BACK
  and UNKNOWN remain internal results/audit facts.

Control-owned timestamps are canonical UTC `Z` with at most six fractional
digits. Shared MessageEnvelope RFC 3339 compatibility remains unchanged.

## Kill Switch and recovery

Kill Switch identity is
`(KILL_SWITCH_COMMAND, scope_type, scope_id, idempotency_key)`. Same committed
identity/content returns the stored result; different content is
`QQ-STORAGE-7001`. Expected-version conflict is `QQ-COMMON-1003`. An uncertain
commit is queried with the same identity, never retried with a new key.

Prior committed records come from `ControlJournalPort` and bind the exact query
identity. Their stored fingerprint is recomputed to detect corruption before
duplicate/conflict handling. The fingerprint does not authenticate the Port.
Exact duplicate is stable before mutable current-state checks.

ON blocks new OrderIntent/Risk approval while preserving cancel, recovery and
approved reduce-risk capacity. OFF and `STARTING -> NORMAL / RecoveryPassed`
both read an exact committed OPEN `RecoveryBarrierSnapshot` and validate:

- scope, barrier ID, generation, barrier version and stored checksum;
- OPEN state, non-null opened_at, freshness and complete six-gate evidence;
- command/transition reference, leader lease and fencing token;
- healthy component/config/market/audit/reconciliation/lag evidence.

Changing snapshot content without updating its stored checksum is corruption.
Source authenticity is supplied by `RecoveryBarrierReadPort`, not by a nested
self-certified acceptance wrapper or provenance hash. OFF never restores NORMAL.

## Configuration activation

Config candidate checksum remains RFC 8785 JCS over the complete security
projection. Exact Decimal/I-JSON rules, secret references, component capability
binding, hard-limit currency/content and strictest-limit checks remain required.

Each required component result binds component identity, generation,
capability, activation mode and safe boundary, and records three distinct facts:

- prepare result: `PREPARED | REJECTED | UNKNOWN`;
- candidate effect: `NOT_ATTEMPTED | APPLIED | REJECTED | UNKNOWN`, with exact
  candidate target version/checksum whenever attempted;
- rollback effect: `NOT_REQUIRED | APPLIED | REJECTED | UNKNOWN`, with exact
  previous ActiveVersion target whenever rollback is required.

A rejected prepare forbids attempting the candidate; an unknown prepare allows
only NOT_ATTEMPTED or UNKNOWN candidate effect; APPLIED/REJECTED candidate
effects require PREPARED.

ACK keys equal required components. Result identity is
`(CONFIG_ACTIVATION, domain, candidate version, idempotency key)`:

- APPLIED: candidate ActiveVersion/Event/Outbox committed; every candidate
  effect APPLIED; rollback NOT_REQUIRED; no safe scope or reconciliation.
- REJECTED: no new ActiveVersion and only known NOT_ATTEMPTED/REJECTED candidate effects; rollback
  NOT_REQUIRED; no reconciliation.
- PARTIAL: no second ActiveVersion; mixed/partial/unknown effects; enter SAFE
  scope and reconcile the same identity.
- ROLLED_BACK: current/rollback target equals the previous committed
  ActiveVersion. Every component that applied the candidate has an APPLIED
  rollback to that target; other components use NOT_REQUIRED. Only then is the
  side effect COMPLETE and reconciliation false.
- UNKNOWN: commit/effect remains uncertain, no new active-authority claim,
  enter SAFE scope and reconcile the same identity. All component candidate
  effects may be APPLIED while the database commit remains UNKNOWN.

Exact prior result replay returns DUPLICATE before mutable ActiveVersion lookup;
same identity with different canonical content is `QQ-STORAGE-7001`.

## Lease and observability

Lease/fencing is checked immediately before every external side effect. Expiry,
revocation, epoch regression or stale fencing fails closed. Sensitive values
are rejected recursively. Alert-definition labels use the schema allowlist;
runtime metrics use the per-metric low-cardinality labels in
`NFR-OBSERVABILITY`, never raw `scope_id` or other entity IDs.
