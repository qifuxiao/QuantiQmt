from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from quantiqmt.market.errors import MarketContractError
from quantiqmt.market.quality import RecoveryEvidenceRegistry
from quantiqmt.market.validation import MarketEventValidator

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/contract/messages/fixtures"
EVENTS = (
    "market.tick_received.v1",
    "market.bar_closed.v1",
    "market.quality_changed.v1",
    "market.session_changed.v1",
)


def load(message_type: str, name: str = "minimal.valid.json") -> dict[str, object]:
    return json.loads((FIXTURES / message_type / name).read_text(encoding="utf-8"))


def joined(*parts: object) -> str:
    return ":".join(str(part) for part in parts)


def validator() -> MarketEventValidator:
    values = json.loads(
        (FIXTURES / "internal/market-data.v1/valid.json").read_text(encoding="utf-8")
    )["dtos"]
    by_type = {item["dto_type"]: item for item in values}
    recovery = RecoveryEvidenceRegistry()
    recovery.register_snapshot("SIM:600000.XSHG:10", by_type["MARKET_SNAPSHOT"])
    recovery.register_checkpoint("SIM:600000.XSHG:am:10", by_type["BAR_AGGREGATION_CHECKPOINT"])
    return MarketEventValidator(recovery_resolver=recovery)


def envelope(message_type: str, payload: dict[str, object]) -> dict[str, object]:
    if message_type == "market.tick_received.v1":
        expected = {
            "source": f"MarketGateway/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": joined("market", payload["provider"], payload["instrument_id"], "tick"),
            "aggregate_version": payload["source_sequence"],
            "idempotency_key": joined(
                "market.tick",
                payload["provider"],
                payload["instrument_id"],
                payload["source_sequence"],
            ),
        }
    elif message_type == "market.bar_closed.v1":
        expected = {
            "source": f"BarAggregator/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": joined(
                "market",
                payload["provider"],
                payload["instrument_id"],
                "bar",
                payload["timeframe_seconds"],
                payload["calendar_version"],
                payload["session_id"],
            ),
            "aggregate_version": payload["source_sequence_end"],
            "idempotency_key": joined(
                "market.bar",
                payload["provider"],
                payload["instrument_id"],
                payload["calendar_version"],
                payload["session_id"],
                payload["timeframe_seconds"],
                payload["window_start"],
            ),
        }
    elif message_type == "market.quality_changed.v1":
        expected = {
            "source": f"MarketQuality/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": joined(
                "market", payload["provider"], payload["instrument_id"], "quality"
            ),
            "aggregate_version": payload["quality_version"],
            "idempotency_key": joined(
                "market.quality",
                payload["provider"],
                payload["instrument_id"],
                payload["quality_version"],
            ),
        }
    else:
        expected = {
            "source": f"SessionScheduler/{payload['calendar_id']}",
            "partition_key": payload["exchange"],
            "aggregate_id": joined(
                "market",
                payload["calendar_id"],
                payload["calendar_version"],
                payload["exchange"],
                payload["session_id"],
                "session",
            ),
            "aggregate_version": payload["transition_sequence"],
            "idempotency_key": joined(
                "market.session",
                payload["calendar_id"],
                payload["calendar_version"],
                payload["exchange"],
                payload["session_id"],
                payload["transition_sequence"],
            ),
        }
    return {
        "message_id": payload["event_id"],
        "message_type": message_type,
        "schema_version": 1,
        "occurred_at": payload["event_time"],
        "received_at": payload["received_at"],
        "correlation_id": "correlation-market-0001",
        "causation_id": None,
        **expected,
        "payload": payload,
    }


@pytest.mark.parametrize("message_type", EVENTS)
def test_all_four_public_market_events_pass_combined_validation(message_type: str) -> None:
    payload = load(message_type)
    assert validator().validate(envelope(message_type, payload))


def test_envelope_payload_binding_and_identity_collision_fail_closed() -> None:
    payload = load("market.tick_received.v1")
    validator = MarketEventValidator()
    message = envelope("market.tick_received.v1", payload)
    validator.validate(message)

    unbound = deepcopy(message)
    unbound["source"] = "MarketGateway/WRONG"
    with pytest.raises(MarketContractError, match="binding mismatch"):
        validator.validate(unbound)

    collision = deepcopy(message)
    collision["payload"]["last_price"] = "10.02"  # type: ignore[index]
    with pytest.raises(MarketContractError, match="identity collision"):
        validator.validate(collision)
