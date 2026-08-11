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

`ControlSemanticValidator` MUST validate envelope and payload together before
publish or outbox persistence. Its normative order is structural envelope,
payload schema, combined event binding, then cross-object semantics. The same
validator MUST run before Outbox persist, publish, consumer apply, control
transition, restore/replay and every external side effect. Failure rejects
without repair, reordering, persistence, publication or execution. Same identity plus the same canonical payload
fingerprint is a duplicate; same identity with a different fingerprint is a
fail-closed collision and MUST retain evidence.

For combined control events, `causation_id` is required. A root event may use
the explicit root context only; otherwise it MUST reference a known direct
parent with an earlier sequence and identical correlation. Self references,
unknown/future parents and cross-correlation links are rejected. Recursive
redaction scans reject credentials, secrets, raw tokens and raw account
identifiers; structured audit evidence is never a metric label.

## CommandBus and control actions

Control commands use `CommandBus`, never EventBus request/response simulation.
Every command has an absolute UTC deadline, an idempotency key, expected
version and fencing evidence. A timeout after dispatch is `UNKNOWN`; the same
command identity is reconciled and never reissued with a new identity.

`KillSwitchCommand` and `ConfigCandidate` are validated by schema and then by
the same semantic validator at dispatch, persistence and recovery restore.
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

## Alerts and runbooks

Alert definitions freeze P0/P1/P2 severity, authoritative metric, threshold and
version, sustained trigger window, recovery window, owner, runbook URI and
correlation/evidence fields. Critical lag uses the source received-watermark
delta, not queue depth alone. Alerts are safety signals and never become the
authoritative trading state.
