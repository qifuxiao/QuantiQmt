"""Deterministic public OMS message builders for Order journal commits."""

from __future__ import annotations

from collections.abc import Mapping

from quantiqmt.contracts import MessageEnvelope, SchemaRegistry
from quantiqmt.order.application.persistence.model import JournalAppend, PersistedOrder
from quantiqmt.order.application.persistence.serialization import sha256_lower_hex
from quantiqmt.order.domain import OrderEvent, OrderState
from quantiqmt.shared import format_utc


def deterministic_message_id(message_type: str, order_id: str, aggregate_version: int) -> str:
    return sha256_lower_hex(f"outbox:v1|{message_type}|{order_id}|{aggregate_version}")


def build_order_registered_envelope(
    persisted: PersistedOrder,
    journal: JournalAppend,
    registry: SchemaRegistry,
) -> MessageEnvelope:
    registration = persisted.registration
    message_type = "oms.order_registered.v1"
    occurred_at = format_utc(registration.registered_at)
    payload = {
        "order_id": registration.order_id.value,
        "intent_id": registration.intent_id.value,
        "account_id": registration.account_id,
        "instrument_id": registration.instrument_id.value,
        "side": registration.side,
        "position_effect": registration.position_effect,
        "order_type": registration.order_type,
        "quantity": registration.quantity.value,
        "limit_price": registration.limit_price.to_primitive()
        if registration.limit_price is not None
        else None,
        "time_in_force": registration.time_in_force,
        "owner_strategy_id": registration.owner_strategy_id,
        "owner_strategy_version": registration.owner_strategy_version,
        "registered_at": occurred_at,
    }
    return MessageEnvelope.create(
        _envelope(message_type, persisted.order.order_id.value, 1, occurred_at, journal, payload),
        registry,
    )


def build_order_status_changed_envelope(
    *,
    order_id: str,
    aggregate_version: int,
    from_status: OrderState | str,
    to_status: OrderState | str,
    reason_code: OrderEvent | str,
    cumulative_quantity: int,
    total_quantity: int,
    journal: JournalAppend,
    registry: SchemaRegistry,
    broker_order_id: str | None = None,
    average_price: str | None = None,
    source_report_id: str | None = None,
) -> MessageEnvelope:
    message_type = "oms.order_status_changed.v1"
    occurred_at = format_utc(journal.occurred_at)
    payload = {
        "order_id": order_id,
        "from_status": _enum_value(from_status),
        "to_status": _enum_value(to_status),
        "reason_code": _enum_value(reason_code),
        "broker_order_id": broker_order_id,
        "cum_quantity": cumulative_quantity,
        "leaves_quantity": total_quantity - cumulative_quantity,
        "average_price": average_price,
        "source_report_id": source_report_id,
        "changed_at": occurred_at,
    }
    return MessageEnvelope.create(
        _envelope(message_type, order_id, aggregate_version, occurred_at, journal, payload),
        registry,
    )


def _envelope(
    message_type: str,
    order_id: str,
    aggregate_version: int,
    occurred_at: str,
    journal: JournalAppend,
    payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "message_id": deterministic_message_id(message_type, order_id, aggregate_version),
        "message_type": message_type,
        "schema_version": 1,
        "occurred_at": occurred_at,
        "received_at": occurred_at,
        "correlation_id": journal.correlation_id,
        "causation_id": journal.causation_id,
        "aggregate_id": order_id,
        "aggregate_version": aggregate_version,
        "source": "OMS",
        "partition_key": order_id,
        "idempotency_key": f"{order_id}:{aggregate_version}:{message_type}",
        "payload": payload,
    }


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
