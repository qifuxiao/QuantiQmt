"""Bounded health evaluation for transactional outbox publication safety."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CriticalOutboxLagPolicy:
    """Fail-fast bounds for order-critical outbox lag and dead-letter safety."""

    critical_lag_ms: int
    critical_dead_letter_count: int

    def __post_init__(self) -> None:
        if not 1 <= self.critical_lag_ms <= 300_000:
            raise ValueError("critical_lag_ms must be between 1 and 300000")
        if not 0 <= self.critical_dead_letter_count <= 100_000:
            raise ValueError("critical_dead_letter_count must be between 0 and 100000")


@dataclass(frozen=True, slots=True)
class OutboxLagSnapshot:
    """Monotonic health facts sampled by an outbox worker or monitor."""

    oldest_order_message_lag_ms: int
    order_dead_letter_count: int
    pending_order_message_count: int

    def __post_init__(self) -> None:
        if self.oldest_order_message_lag_ms < 0:
            raise ValueError("oldest_order_message_lag_ms must be non-negative")
        if self.order_dead_letter_count < 0:
            raise ValueError("order_dead_letter_count must be non-negative")
        if self.pending_order_message_count < 0:
            raise ValueError("pending_order_message_count must be non-negative")


@dataclass(frozen=True, slots=True)
class OutboxSafetyAction:
    """Safe action exposed to recovery/risk orchestration."""

    critical: bool
    reject_new_risk: bool
    emit_health_alert: bool
    reason_code: str


def evaluate_outbox_safety(
    snapshot: OutboxLagSnapshot, policy: CriticalOutboxLagPolicy
) -> OutboxSafetyAction:
    """Return the fail-closed action for critical order publication lag."""

    lag_critical = snapshot.oldest_order_message_lag_ms >= policy.critical_lag_ms
    dead_letter_critical = snapshot.order_dead_letter_count > policy.critical_dead_letter_count
    if dead_letter_critical:
        return OutboxSafetyAction(
            critical=True,
            reject_new_risk=True,
            emit_health_alert=True,
            reason_code="ORDER_OUTBOX_DEAD_LETTER_CRITICAL",
        )
    if lag_critical:
        return OutboxSafetyAction(
            critical=True,
            reject_new_risk=True,
            emit_health_alert=True,
            reason_code="ORDER_OUTBOX_LAG_CRITICAL",
        )
    return OutboxSafetyAction(
        critical=False,
        reject_new_risk=False,
        emit_health_alert=False,
        reason_code="OK",
    )
