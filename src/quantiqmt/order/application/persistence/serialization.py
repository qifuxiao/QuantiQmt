"""Canonical JSON, fingerprints, state payloads, and journal checksums."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from quantiqmt.order.application.persistence.model import (
    JournalAppend,
    JsonValue,
    MutableJsonValue,
    OrderRegistration,
    OrderSnapshot,
    PersistedOrder,
)
from quantiqmt.order.domain import FactIdentity, ProcessedFact
from quantiqmt.shared import format_utc

GENESIS_PREVIOUS_COMPONENT = "0" * 64


def canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    """Serialize the supported JSON subset exactly as STORAGE-ORDER-PERSISTENCE."""
    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_lower_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def registration_to_payload(registration: OrderRegistration) -> dict[str, MutableJsonValue]:
    return {
        "order_id": registration.order_id.value,
        "intent_id": registration.intent_id.value,
        "client_order_id": registration.client_order_id,
        "account_id": registration.account_id,
        "instrument_id": registration.instrument_id.value,
        "side": registration.side,
        "position_effect": registration.position_effect,
        "order_type": registration.order_type,
        "quantity": registration.quantity.value,
        "limit_price": (
            registration.limit_price.to_primitive()
            if registration.limit_price is not None
            else None
        ),
        "time_in_force": registration.time_in_force,
        "owner_strategy_id": registration.owner_strategy_id,
        "owner_strategy_version": registration.owner_strategy_version,
        "registered_at": format_utc(registration.registered_at),
    }


def registration_fingerprint(intent_payload: Mapping[str, JsonValue]) -> str:
    """Fingerprint an already validated OrderIntent payload, preserving Decimal scale strings."""
    return sha256_lower_hex(canonical_json_bytes(intent_payload))


def order_state_payload(persisted: PersistedOrder) -> dict[str, MutableJsonValue]:
    order = persisted.order
    return {
        "order_id": order.order_id.value,
        "intent_id": persisted.registration.intent_id.value,
        "client_order_id": persisted.registration.client_order_id,
        "registration": registration_to_payload(persisted.registration),
        "state": order.state.value,
        "quantity": order.quantity.value,
        "cumulative_quantity": order.cumulative_quantity.value,
        "aggregate_version": order.version,
        "processed_facts": [
            {
                "namespace": identity.namespace,
                "key": identity.key,
                "fingerprint": fact.fingerprint,
                "trade_quantity": (
                    fact.trade_quantity.value if fact.trade_quantity is not None else None
                ),
            }
            for identity, fact in sorted(
                order.processed_facts.items(), key=lambda item: (item[0].namespace, item[0].key)
            )
        ],
        "fact_conflicts": [
            {
                "namespace": identity.namespace,
                "key": identity.key,
                "conflicting_fingerprints": cast(
                    list[MutableJsonValue],
                    sorted(fingerprints),
                ),
            }
            for identity, fingerprints in sorted(
                order.fact_conflicts.items(), key=lambda item: (item[0].namespace, item[0].key)
            )
        ],
        "broker_sequences": [
            {"stream": stream, "last_observed_sequence": sequence}
            for stream, sequence in sorted(order.broker_sequences.items())
        ],
        "provisional_mappings": [],
        "registration_fingerprint": persisted.registration_fingerprint,
    }


def journal_checksum(entry: JournalAppend, previous_entry_checksum: str | None) -> str:
    previous_component = previous_entry_checksum or GENESIS_PREVIOUS_COMPONENT
    entry_component = canonical_json_bytes(journal_payload_without_checksums(entry))
    return sha256_lower_hex(previous_component.encode("utf-8") + b"\n" + entry_component)


def journal_with_registration_fingerprint(
    entry: JournalAppend, registration_fingerprint: str
) -> JournalAppend:
    payload = _mutable_json(entry.payload)
    if not isinstance(payload, dict):
        raise TypeError("journal payload must be an object")
    post_state = payload.get("post_state")
    if not isinstance(post_state, dict):
        raise ValueError("journal payload must contain post_state object")
    post_state["registration_fingerprint"] = registration_fingerprint
    return JournalAppend(
        entry.journal_id,
        entry.order_id,
        entry.aggregate_version,
        entry.event_type,
        cast(Mapping[str, JsonValue], payload),
        entry.occurred_at,
        entry.correlation_id,
        entry.causation_id,
    )


def journal_payload_without_checksums(entry: JournalAppend) -> dict[str, MutableJsonValue]:
    return {
        "journal_id": entry.journal_id.value,
        "order_id": entry.order_id.value,
        "aggregate_version": entry.aggregate_version,
        "event_type": entry.event_type,
        "schema_version": 1,
        "payload": _mutable_json(entry.payload),
        "occurred_at": format_utc(entry.occurred_at),
        "correlation_id": entry.correlation_id,
        "causation_id": entry.causation_id,
    }


def snapshot_payload_without_checksum(snapshot: OrderSnapshot) -> dict[str, MutableJsonValue]:
    return {
        "snapshot_id": snapshot.snapshot_id.value,
        "order_id": snapshot.order_id.value,
        "aggregate_version": snapshot.aggregate_version,
        "schema_version": snapshot.schema_version,
        "state_payload": _mutable_json(snapshot.state_payload),
        "journal_head_checksum": snapshot.journal_head_checksum,
        "created_at": format_utc(snapshot.created_at),
    }


def snapshot_checksum(snapshot: OrderSnapshot | Mapping[str, JsonValue]) -> str:
    if isinstance(snapshot, OrderSnapshot):
        return sha256_lower_hex(canonical_json_bytes(snapshot_payload_without_checksum(snapshot)))
    return sha256_lower_hex(canonical_json_bytes(snapshot))


def _normalize_json(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        raise TypeError("canonical JSON forbids float")
    if isinstance(value, datetime):
        raise TypeError("canonical JSON requires timestamps as UTC Z strings")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return {
            unicodedata.normalize("NFC", key): _normalize_json(item) for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [_normalize_json(item) for item in value]
    raise TypeError(f"unsupported canonical JSON value {type(value).__name__}")


def _mutable_json(value: object) -> MutableJsonValue:
    normalized = _normalize_json(value)
    return cast(MutableJsonValue, normalized)


def processed_fact_to_payload(identity: FactIdentity, fact: ProcessedFact) -> dict[str, object]:
    return {
        "namespace": identity.namespace,
        "key": identity.key,
        "fingerprint": fact.fingerprint,
        "trade_quantity": fact.trade_quantity.value if fact.trade_quantity is not None else None,
    }
