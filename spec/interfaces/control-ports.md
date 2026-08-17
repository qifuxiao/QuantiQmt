# PORTS-CONTROL — Control Plane L4 Ports

Status: Draft. Owner: ControlPlane. This contract freezes behavior and authority
boundaries; it does not freeze runtime classes, a database schema, repository
layout, or an in-memory history model.

## Authority layering

- Commands enter through `CommandBus` as required by `PORTS-CORE`; EventBus is
  not a request/reply transport.
- `STORAGE-SOT` is authoritative for System Mode and Kill Switch:
  PostgreSQL `control_journal` is durable authority and component memory is a
  cache only.
- Public Events are immutable facts emitted after their authoritative state
  transition has committed. Internal command results and audit facts describe
  rejected or uncertain attempts.
- Recovery follows `WF-RECOVERY`: restore the latest valid System Mode and Kill
  Switch for every scope from `control_journal` before opening a recovery
  barrier.
- A concrete Control Journal repository/table contract is intentionally outside
  TASK-022. It requires a separate storage spec-change task before runtime work
  needs a physical design.

## Common scope

`ControlScope = {scope_type, scope_id}` where `scope_type` is one of `GLOBAL`,
`ACCOUNT`, `STRATEGY`, or `INSTRUMENT`. `GLOBAL` requires `scope_id = null`;
every other type requires a non-empty ID. Its deterministic `scope_key` is
`GLOBAL` for global scope and `{scope_type}:{scope_id}` otherwise.

Kill Switch Command, Result, persisted authority and changed Event MUST carry
the same scope. For scoped public Events, MessageEnvelope `aggregate_id` and
`partition_key` both equal `scope_key`.

## Validation operations

The implementation may organize code freely, but every side-effecting boundary
must perform the equivalent typed operation and order specified by
`CONTRACT-CONTROL-SEMANTIC-VALIDATION-V1`:

- `ValidateControlEvent(envelope, payload, optional prior state, injected time)`
- `ValidateKillSwitchCommand(command, current scoped state, authorization,
  lease, optional recovery barrier, optional prior persisted command/result,
  injected time)`
- `ValidateKillSwitchResult(result, persisted command fact, optional prior
  result fact, current scoped state, expected ACK authority, injected time)`
- `ValidateConfigActivation(candidate/result, accepted policy/components/hard
  limits, optional prior result fact, injected time)`

Schema validation alone never authorizes dispatch, journal commit, outbox
persistence, publication, consumer apply, state transition, recovery-barrier
opening, or an external side effect.

## Public fact events

All four Events use canonical `MessageEnvelopeV1` without extra top-level wire
fields. `publisher`, `aggregate_type`, and `payload_fingerprint` are not envelope
fields. A payload fingerprint is computed semantically from RFC 8785 JCS bytes.

- `system.mode_changed.v1` reports one legal, persisted System Mode transition.
- `system.component_health_changed.v1` reports one legal, accepted component
  health transition.
- `system.kill_switch_changed.v1` reports only a persisted Kill Switch state
  change. Rejected or uncertain commands do not publish it.
- `config.version_activated.v1` reports only a successful atomic
  `ActiveVersion + Event + Outbox` commit. Rejected, partial, unknown and rolled
  back attempts are internal `ConfigActivationResult`/audit facts.

Control Event payload timestamps and combined-envelope timestamps are canonical
UTC `Z` with zero to six fractional digits. The shared Envelope contract keeps
its existing RFC 3339 compatibility; an adapter normalizes offsets before a
message enters the Control refinement.

## Kill Switch Command and Result

`KillSwitchCommand` carries command ID, scope, desired state, cancel policy,
reason, expected version, absolute deadline, idempotency key, authorization,
leader lease/fencing, and complete recovery-barrier references when disabling.

The persisted command identity is the typed tuple
`(KILL_SWITCH_COMMAND, scope_type, scope_id, idempotency_key)`. `command_id` is
trace identity, not a substitute for target scope. The canonical command
fingerprint covers every immutable security field and excludes only the
fingerprint field itself.

- Same persisted identity and same canonical command returns the original
  persisted result (`DUPLICATE`).
- Same identity and different canonical command is
  `QQ-STORAGE-7001 IDEMPOTENCY_CONFLICT`.
- `expected_version` is a CAS guard; stale versions use
  `QQ-COMMON-1003 VERSION_CONFLICT` and emit no changed Event.
- An uncertain journal commit is queried/reconciled using the same identity.
  Changing the idempotency key to retry is forbidden.

`KillSwitchResult` carries the same command/scope/version/authorization/
lease/fence facts and has `APPLIED`, `REJECTED`, or `UNKNOWN` outcome:

- `APPLIED`: desired state is effective, version advances exactly once,
  reconciliation is false, and complete expected effect ACKs are present.
- `REJECTED`: accepted state and version are unchanged, reconciliation is
  false, and no effect ACK is claimed.
- `UNKNOWN`: effective state is `UNKNOWN`, version is not fabricated,
  reconciliation is true, and only known incomplete ACK evidence may remain.

A single optional prior persisted result fact makes exact replay stable before
consulting mutable current state. Different result content or result ID is a
conflict. No cumulative history or storage layout is an input to validation.

Kill Switch ON blocks new OrderIntent and new Risk approval while preserving
cancel, recovery and explicitly approved reduce-risk capacity. OFF requires the
same complete, fresh, OPEN recovery barrier used by System Mode recovery. It
never restores NORMAL automatically and never mutates OMS business state.

## Configuration activation

The candidate checksum is SHA-256 over RFC 8785 JCS for the complete security
projection frozen in the semantic contract. Secret-reference and required-
component arrays are sorted as sets; other arrays preserve wire order. JSON
number tokens are parsed exactly and only finite, mathematical I-JSON safe
integers are accepted; prices, money, fees and decimal quantities remain
canonical decimal strings.

Candidate currency and hard-limit policy currency/content/checksum must match,
and a dynamic limit cannot relax an accepted system hard limit. Required
components, authority keys and ACK keys must be the same set, with every ACK
binding version, checksum, generation, capability and activation boundary.

## Lease, recovery, and observability

Lease/fencing is checked immediately before every external side effect. Expiry,
revocation, epoch regression, stale fencing, or renewal after expiry fails
closed.

A recovery barrier starts CLOSED and opens only with all six verified gates:
`CONFIG_VERIFIED`, `MARKET_FRESH`, `AUDIT_AVAILABLE`,
`RECONCILIATION_COMPLETE`, `LEASE_FENCED`, and `OUTBOX_HEALTHY`. OPEN requires a
non-null `opened_at`; CLOSED/INVALIDATED require null. Observations cannot be in
the future and market freshness must extend strictly beyond injected time.
`STARTING -> NORMAL / RECOVERY_PASSED` requires this complete OPEN authority.

Sensitive keys are rejected recursively. Metric labels are limited to the
frozen low-cardinality allowlist; detailed identities and evidence belong in
redacted logs, traces and audit facts.
