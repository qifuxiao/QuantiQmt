# PORTS-CONTROL: Observability and Control Plane L4

This contract is the normative boundary for control operations. It does not own
OMS order state, Risk decisions, broker effects, or database authority.

## Observability

Every message, log, trace span and audit record MUST carry the same
`correlation_id`; a child operation MUST carry its immediate `causation_id`.
The required context is `message_id`, `correlation_id`, `causation_id`,
`source`, `service`, `instance`, `environment`, `occurred_at`, `received_at`
and `error_code`. Secrets, credentials, tokens and raw account identifiers MUST
be redacted before a record crosses this port. Metrics MUST use only the
allow-listed bounded labels in `NFR-OBSERVABILITY`; order, trade, instrument,
account, strategy, message and correlation identifiers are prohibited labels.

Only `validate_control_message(message, validation_context)` is a usable
ControlSemanticValidator entrypoint for combined public events and the
`CONFIG_CANDIDATE`, `KILL_SWITCH_COMMAND` and `KILL_SWITCH_RESULT` DTOs; it returns one canonical decision:
`ACCEPTED`, `DUPLICATE`, `REJECTED` or `CONFLICT`. It MUST validate envelope and payload together before
publish or outbox persistence. Its normative order is structural envelope,
payload schema, combined event binding, then cross-object semantics. The same
validator MUST run at command ingress and before Outbox persist, event publish,
consumer apply, control transition, restore/replay and every external side
effect. Failure rejects
without repair, reordering, persistence, publication or execution. Structural
schema validation, canonical payload/checksum/fingerprint recomputation and all
immutable envelope/payload source, aggregate, idempotency, correlation and
causation bindings run before duplicate classification. Only then is a trusted
same-identity plus same-fingerprint replay a duplicate before mutable current
authority, barrier or lineage state is consulted; same identity with a
different fingerprint is a fail-closed collision and MUST retain evidence.

Event-specific config, kill-switch, mode, health and recovery-barrier checks are
private branches of that dispatcher only. Candidate/result-only, command/result-
only or barrier-only helpers are not validator APIs and MUST NOT be used as
runtime implementation entrypoints; candidate and command checks are private
branches selected by the unified dispatcher.
Direct Draft 2020-12 validation is a structural probe only. It never returns a
semantic acceptance decision and MUST NOT authorize persistence, publication,
consumer apply, state transition, recovery restore or an external side effect.

When the accepted authority context carries a recovery barrier, its CLOSED,
OPEN or INVALIDATED evidence is validated by the same entrypoint before the
event-specific decision; no barrier-only shortcut may bypass freshness,
authority or lineage checks.

`validation_context` is mandatory and is the `CONTRACT-CONTROL-VALIDATION-CONTEXT-V1`
DTO: it contains injected `evaluation_at`, accepted policy identity, known
message lineage, identity/fingerprint history, and accepted config/market/audit/
lease/component/reconciliation/critical-lag authorities. Omitting or supplying
an empty context is a validation error; a missing parent is never treated as a
root event.

The four combined public control events are never root events: `causation_id`
is required and MUST reference a known direct parent command/observation in
the injected validation context with an earlier sequence and identical
correlation. Root inputs, when needed, are authorized command/observation
context records and are not published as these events. Self references,
unknown/future parents and cross-correlation links are rejected. Recursive
redaction scans reject credentials, secrets, raw tokens and raw account
identifiers; structured audit evidence is never a metric label.

## CommandBus and control actions

Control commands use `CommandBus`, never EventBus request/response simulation.
Every command has an absolute UTC deadline, an idempotency key, expected
version and fencing evidence. A timeout after dispatch is `UNKNOWN`; the same
command identity is reconciled and never reissued with a new identity.
Every public or internal control timestamp crossing this contract uses canonical
UTC `Z` wire form with zero to six fractional digits. An ingress adapter MAY
parse an explicit RFC 3339 offset and normalize the same instant to UTC `Z`
before validation, but raw offsets, naive values, leap seconds, unknown `-00:00`
offsets and excess precision fail closed at the contract boundary. Safety
comparisons parse these values as aware instants and never compare strings.

`KillSwitchCommand` and `ConfigCandidate` are validated by schema and then by
the same semantic validator at dispatch, persistence and recovery restore.
The accepted config authority is immutable and versioned: its checksum is
SHA-256 over RFC 8785 JCS bytes for the complete candidate security projection:
config domain/version, actual candidate payload, sorted secret references and
required components, activation mode and safe boundary, system hard-limit
policy identity and content (including valuation currency and every accepted
system hard limit), candidate dynamic limits, plus the complete component
authority map and control policy identity. Only secret-reference and required-
component arrays are sorted as sets; other arrays preserve wire order, object
keys use RFC 8785 ordering, and Unicode is not normalized. Candidate currency
MUST equal policy currency, policy content MUST hash to the accepted checksum,
and no dynamic upper bound may exceed its accepted system hard limit. Payload
and every nested checksum projection value permit only finite, mathematically
integral I-JSON safe numbers or strings. The wire parser MUST preserve each JSON
number token's exact decimal value (for example Python `parse_float=Decimal`)
before structural and semantic validation; passing through binary float is
forbidden, and directly constructed binary-float API values fail closed without
proven exact-token provenance. Exact JSON `1`, `1.0` and `1e0` normalize to the
same integer before JCS; hidden fractional, underflow/overflow, non-finite and
out-of-safe-range numbers are rejected recursively. Schema `number` plus
`multipleOf: 1` is only a structural gate and cannot replace this exact semantic
gate. Prices, money, fees and other decimal
quantities remain canonical decimal strings and never binary floating point.
required components, ACK keys, authority required components and authority
component keys MUST be the same set. Each ACK MUST exactly bind component ID,
generation, capability version, activation mode and safe boundary; missing or
unknown authority components fail closed.
The public config activation event MUST exactly bind its secret references,
required components, activation mode, safe boundary, policy identity and
candidate checksum to that accepted candidate; changing any security field
without a new checksum is rejected.
Kill-switch command/result pairs MUST bind command identity and canonical
fingerprint, expected/previous/current versions, authorization identity and
checksum, leader lease/fencing evidence, absolute deadline and reconciliation
evidence. `UNKNOWN` is returned for possible commit and requires an
authoritative query; a new idempotency identity is forbidden. Disabling the
switch requires a verified recovery-evidence reference and MUST NOT restore
NORMAL automatically.
Internal command history always uses `KILL_SWITCH_COMMAND:{command_id}`; raw
external IDs are never registry keys. A `KILL_SWITCH_RESULT` has its own
`result_id` and canonical `result_fingerprint` under the disjoint
`KILL_SWITCH_RESULT:{result_id}` namespace. A second command-result index is
`KILL_SWITCH_COMMAND_RESULT:` plus SHA-256 of RFC 8785 JCS over exactly
`{command_id,idempotency_key,scope}`. It permits exactly one result per command.
The immutable command-history, command-result and result-entity records MUST be
registered atomically. Both result records carry command identity/idempotency,
scope and fingerprint plus result identity/fingerprint and reciprocal pointers.
Before every result acceptance or duplicate decision, the complete namespaced
registry is audited as a bijection: result-only or command-result-only orphans,
missing/wrong backlinks, multiple results for one command, one result linked to
multiple commands, or divergent decision/fingerprint evidence fail closed.
Recovery restore has the same global audit and cannot continue from a partial
snapshot. Only a replay matching both indexes and the original immutable command
history is `DUPLICATE`; it is stable after current command authority advances.
First results alone consult current command/authorization/lease/version/effect
authority before atomically recording all three histories.
That reference resolves only through the strict
`accepted_recovery_barriers` authority registry. Its map key and barrier ID,
generation, barrier version/checksum, evidence and aggregate digests, OPEN
state, kill-switch version, policy, authorization and injected-time freshness
MUST all match the command and event; arbitrary objects and stale evidence are
rejected.
Kill-switch outcomes are exhaustive and identical for the public event and
internal result DTO: APPLIED advances exactly one version and reaches desired
state; REJECTED keeps accepted state/version; PARTIAL stays fail-closed ON with
unchanged version and reconciliation required; TIMEOUT/UNKNOWN use UNKNOWN,
unchanged version and reconciliation under the same command identity and
fingerprint. Every outcome forbids implicit NORMAL restoration.
Effect ACKs are authority-bound for both forms: APPLIED requires the complete
expected set, REJECTED requires none, PARTIAL requires a non-empty strict
subset, and TIMEOUT/UNKNOWN may retain only an incomplete known subset while
reconciliation is required. Unknown, forged, future-observed or falsely
complete ACK evidence is rejected.
Kill switch ON blocks new OrderIntent and new Risk approval but preserves
cancel, recovery and explicitly approved reduce-risk capacity. It cannot change
OMS business state or bypass Risk/Execution.

## Lease and fencing

`LeaderLease` contains lease identity, holder, monotonic epoch, fencing token,
issued/expiry/renew-deadline timestamps and status. A token is checked before
every external side effect. Expiry, epoch regression, renewal after expiry or
cached success from a stale token is rejected without side effect.

## Recovery barrier

`RecoveryBarrier` starts CLOSED. Opening requires the complete evidence set
`CONFIG_VERIFIED`, `MARKET_FRESH`, `AUDIT_AVAILABLE`,
`RECONCILIATION_COMPLETE`, `LEASE_FENCED` and `OUTBOX_HEALTHY`, including
component versions, checksums and watermarks. While closed, new OrderIntent and
Risk approval are rejected. Reconnect alone never opens the barrier or restores
NORMAL. Evidence invalidation moves the barrier to conservative INVALIDATED
state and requires a new verified opening transition.
`opened_at` is mandatory and non-null only for an OPEN barrier; CLOSED and
INVALIDATED barriers MUST carry null `opened_at`. `market_fresh_until` is the sole Market freshness authority in barrier
evidence. It MUST exactly match the accepted Market authority and be strictly
later than injected `evaluation_at`; a generic `fresh_until` field is forbidden.
Evidence `observed_at` MUST NOT be later than `evaluation_at`.
Every semantic comparison of observed, occurred, approved, deadline, expiry,
freshness, opening or applied time parses strict RFC 3339 (`Z` or an explicit
known offset), normalizes to an aware UTC instant, and compares instants rather
than strings. Invalid, naive, unknown `-00:00` offsets and unsupported precision
fail closed.

## Alerts and runbooks

Alert definitions freeze P0/P1/P2 severity, authoritative metric, threshold and
version, sustained trigger window, recovery window, owner, runbook URI and
correlation/evidence fields. Critical lag uses the source received-watermark
delta, not queue depth alone. Alerts are safety signals and never become the
authoritative trading state.
