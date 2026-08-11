from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from itertools import pairwise, product
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from quantiqmt.contracts import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "spec" / "contracts"
FIXTURES = Path(__file__).with_name("fixtures")
EVENTS = {
    "market.tick_received.v1": "events/market.tick_received.v1.schema.json",
    "market.bar_closed.v1": "events/market.bar_closed.v1.schema.json",
    "market.quality_changed.v1": "events/market.quality_changed.v1.schema.json",
    "market.session_changed.v1": "events/market.session_changed.v1.schema.json",
}
QUALITY_REASONS = {
    "NORMAL": {"INITIAL_BASELINE_VERIFIED", "RECOVERY_VERIFIED"},
    "DEGRADED": {"BACKPRESSURE", "SOURCE_LAG"},
    "STALE": {"STALE_DEADLINE_EXCEEDED"},
    "GAP": {"SOURCE_SEQUENCE_GAP", "CONTROLLED_DROP"},
    "UNAVAILABLE": {"DISCONNECTED", "SNAPSHOT_UNAVAILABLE"},
    "RECOVERING": {"BACKFILL_STARTED", "SNAPSHOT_VERIFYING"},
}
SESSION_TRANSITIONS = {
    ("CLOSED", "PRE_OPEN"): "CALENDAR_BOUNDARY",
    ("PRE_OPEN", "OPEN"): "CALENDAR_BOUNDARY",
    ("OPEN", "BREAK"): "CALENDAR_BOUNDARY",
    ("BREAK", "OPEN"): "CALENDAR_BOUNDARY",
    ("OPEN", "CLOSING"): "CALENDAR_BOUNDARY",
    ("CLOSING", "CLOSED"): "CALENDAR_BOUNDARY",
    ("CLOSED", "CLOSED"): "DUPLICATE_SUPPRESSED",
}


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validator(relative: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("timestamp must be canonical UTC Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_market_event_semantics(message_type: str, payload: dict[str, Any]) -> None:
    if _utc(payload["received_at"]) < _utc(payload["event_time"]):
        raise ValueError("received_at precedes event_time")
    if payload["partition_key"] != payload.get("instrument_id", payload.get("exchange")):
        raise ValueError("partition identity mismatch")

    quality = payload.get("quality")
    gap_start = payload.get("gap_start_sequence")
    gap_end = payload.get("gap_end_sequence")
    if quality == "GAP":
        if not isinstance(gap_start, int) or not isinstance(gap_end, int) or gap_start > gap_end:
            raise ValueError("GAP requires an ordered range")
    elif gap_start is not None or gap_end is not None:
        raise ValueError("non-GAP event cannot claim a gap range")

    if message_type == "market.tick_received.v1":
        if payload["source_sequence"] < payload["watermark_sequence"]:
            raise ValueError("tick source sequence is behind watermark")
        return

    if message_type == "market.bar_closed.v1":
        if not (_utc(payload["window_start"]) < _utc(payload["window_end"])):
            raise ValueError("bar window is inverted")
        prices = [Decimal(payload[name]) for name in ("open", "high", "low", "close")]
        if prices[1] < prices[2] or max(prices[0], prices[3]) > prices[1]:
            raise ValueError("invalid OHLC")
        if min(prices[0], prices[3]) < prices[2]:
            raise ValueError("invalid OHLC")
        if payload["source_sequence_start"] > payload["source_sequence_end"]:
            raise ValueError("bar sequence range is inverted")
        if payload["watermark_sequence"] < payload["source_sequence_end"]:
            raise ValueError("bar closed before watermark")
        projection = {key: value for key, value in payload.items() if key != "content_checksum"}
        if payload["content_checksum"] != _canonical_hash(projection):
            raise ValueError("bar checksum mismatch")
        return

    if message_type == "market.quality_changed.v1":
        if payload["reason_code"] not in QUALITY_REASONS[payload["quality"]]:
            raise ValueError("quality/reason mismatch")
        if payload["quality"] == "NORMAL" and payload["unresolved_gap_count"] != 0:
            raise ValueError("NORMAL cannot retain unresolved gaps")
        if payload["quality"] == "NORMAL" and payload["recovery_checkpoint"] is None:
            raise ValueError("NORMAL requires verified recovery evidence")
        if payload["quality"] == "RECOVERING" and payload["recovery_checkpoint"] is None:
            raise ValueError("RECOVERING requires a checkpoint")
        return

    transition = (payload["from_state"], payload["to_state"])
    if SESSION_TRANSITIONS.get(transition) != payload["reason_code"]:
        raise ValueError("illegal session transition")
    if payload["calendar_version"] != payload["session_calendar_version"]:
        raise ValueError("session/calendar version mismatch")
    if not (_utc(payload["session_open_at"]) < _utc(payload["session_close_at"])):
        raise ValueError("session interval is inverted")


def validate_market_contract_semantics(document: dict[str, Any]) -> None:
    dtos = document["dtos"]
    by_type = {dto["dto_type"]: dto for dto in dtos}
    calendar = by_type["TRADING_CALENDAR"]
    intervals = calendar["sessions"]
    if any(
        _utc(current["close_at"]) > _utc(following["open_at"])
        for current, following in pairwise(intervals)
    ):
        raise ValueError("calendar sessions overlap")

    request = by_type["SUBSCRIPTION_REQUEST"]
    if request["queue_capacity"] < request["batch_capacity"]:
        raise ValueError("unbounded/invalid capacity")
    if request["warning_watermark"] >= request["critical_watermark"]:
        raise ValueError("watermark order invalid")
    if request["critical_watermark"] >= request["queue_capacity"]:
        raise ValueError("critical watermark exceeds capacity")

    result = by_type["SUBSCRIPTION_RESULT"]
    if result["operation"] != request["operation"]:
        raise ValueError("subscription operation mismatch")
    if result["subscription_id"] != request["subscription_id"]:
        raise ValueError("subscription identity mismatch")
    if result["generation"] != request["generation"]:
        raise ValueError("subscription generation mismatch")

    lifecycle_request = by_type["LIFECYCLE_REQUEST"]
    lifecycle_result = by_type["LIFECYCLE_RESULT"]
    if lifecycle_result["request_id"] != lifecycle_request["request_id"]:
        raise ValueError("lifecycle request identity mismatch")
    if lifecycle_result["operation"] != lifecycle_request["operation"]:
        raise ValueError("lifecycle operation mismatch")
    if lifecycle_result["generation"] != lifecycle_request["generation"]:
        raise ValueError("lifecycle generation mismatch")

    snapshot = by_type["MARKET_SNAPSHOT"]
    snapshot_request = by_type["SNAPSHOT_REQUEST"]
    snapshot_result = by_type["SNAPSHOT_RESULT"]
    if snapshot["calendar_version"] != calendar["calendar_version"]:
        raise ValueError("snapshot/calendar version mismatch")
    if snapshot["quality"] == "NORMAL" and (
        snapshot["stale"] or snapshot["unresolved_gap_count"] != 0
    ):
        raise ValueError("snapshot claims healthy while stale")
    if snapshot_result["request_id"] != snapshot_request["request_id"]:
        raise ValueError("snapshot request identity mismatch")
    if snapshot_result["snapshot"] != snapshot:
        raise ValueError("snapshot result payload mismatch")
    if snapshot_request["instrument_id"] != snapshot["instrument_id"]:
        raise ValueError("snapshot instrument mismatch")
    if snapshot_request["calendar_version"] != snapshot["calendar_version"]:
        raise ValueError("snapshot request calendar mismatch")

    health = by_type["MARKET_HEALTH"]
    health_request = by_type["HEALTH_REQUEST"]
    if health["request_id"] != health_request["request_id"]:
        raise ValueError("health request identity mismatch")
    if health["status"] == "HEALTHY" and health["quality"] != "NORMAL":
        raise ValueError("health/quality mismatch")

    policy = by_type["BAR_AGGREGATION_POLICY"]
    checkpoint = by_type["BAR_AGGREGATION_CHECKPOINT"]
    if checkpoint["calendar_version"] != calendar["calendar_version"]:
        raise ValueError("aggregator/calendar version mismatch")
    if checkpoint["watermark_sequence"] < checkpoint["last_final_sequence"]:
        raise ValueError("watermark regressed")
    if policy["allowed_lateness_ms"] < 0 or policy["timeframe_seconds"] <= 0:
        raise ValueError("invalid aggregation policy")
    if policy["late_after_final"] != "REJECT_AND_EMIT_GAP_EVIDENCE":
        raise ValueError("late-after-final cannot rewrite history")

    inputs = [dto for dto in dtos if dto["dto_type"] == "BAR_AGGREGATION_INPUT"]
    identities: dict[tuple[str, int], str] = {}
    for item in inputs:
        if item["calendar_version"] != calendar["calendar_version"]:
            raise ValueError("input/calendar version mismatch")
        if item["session_id"] != checkpoint["session_id"]:
            raise ValueError("cross-session aggregation")
        identity = (item["instrument_id"], item["source_sequence"])
        content_hash = _canonical_hash({key: value for key, value in item.items() if key != "mode"})
        if identity in identities and identities[identity] != content_hash:
            raise ValueError("duplicate identity with different payload")
        identities[identity] = content_hash

    live = [item for item in inputs if item["mode"] == "LIVE"]
    replay = [item for item in inputs if item["mode"] == "REPLAY"]
    if [{k: v for k, v in item.items() if k != "mode"} for item in live] != [
        {k: v for k, v in item.items() if k != "mode"} for item in replay
    ]:
        raise ValueError("live/replay normalized inputs differ")


def test_catalog_registry_and_manifest_register_all_market_contracts() -> None:
    registry = SchemaRegistry.project_default()
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in manifest["catalogs"]["contracts"]}
    assert set(EVENTS).issubset(registry.message_types)
    assert {
        "CONTRACT-MARKET-TICK-RECEIVED-V1",
        "CONTRACT-MARKET-BAR-CLOSED-V1",
        "CONTRACT-MARKET-QUALITY-CHANGED-V1",
        "CONTRACT-MARKET-SESSION-CHANGED-V1",
        "CONTRACT-MARKET-DATA-V1",
    }.issubset(ids)
    for message_type in EVENTS:
        registered = registry.payload(message_type, 1)
        assert registered["$id"] == _load(SCHEMAS / EVENTS[message_type])["$id"]
        _validator(EVENTS[message_type]).validate(
            _load(FIXTURES / message_type / "minimal.valid.json")
        )


@pytest.mark.parametrize("message_type", EVENTS)
def test_market_event_payloads_fit_the_canonical_message_envelope(
    message_type: str,
) -> None:
    payload = _load(FIXTURES / message_type / "minimal.valid.json")
    aggregate_version = payload.get(
        "source_sequence",
        payload.get("quality_version", payload.get("transition_sequence")),
    )
    envelope = {
        "message_id": f"message-{payload['event_id']}",
        "message_type": message_type,
        "schema_version": 1,
        "occurred_at": payload["event_time"],
        "received_at": payload["received_at"],
        "correlation_id": "correlation-market-0001",
        "causation_id": None,
        "aggregate_id": payload.get("instrument_id", payload.get("exchange")),
        "aggregate_version": aggregate_version,
        "source": f"market/{payload.get('provider', 'calendar')}",
        "partition_key": payload["partition_key"],
        "idempotency_key": payload["event_id"],
        "payload": payload,
    }
    _validator("common/message-envelope.v1.schema.json").validate(envelope)
    _validator(EVENTS[message_type]).validate(envelope["payload"])


@pytest.mark.parametrize("message_type", EVENTS)
@pytest.mark.parametrize("fixture_name", ["minimal.valid.json", "maximal.valid.json"])
def test_market_event_valid_fixtures_pass_schema_and_semantics(
    message_type: str, fixture_name: str
) -> None:
    payload = _load(FIXTURES / message_type / fixture_name)
    _validator(EVENTS[message_type]).validate(payload)
    validate_market_event_semantics(message_type, payload)


@pytest.mark.parametrize("message_type", EVENTS)
@pytest.mark.parametrize(
    "fixture_name",
    [
        "invalid.missing-required.json",
        "invalid.additional-property.json",
        "invalid.enum.json",
        "invalid.precision.json",
        "semantic-invalid.cross-field.json",
    ],
)
def test_market_event_invalid_fixture_matrix_is_rejected(
    message_type: str, fixture_name: str
) -> None:
    payload = _load(FIXTURES / message_type / fixture_name)
    errors = list(_validator(EVENTS[message_type]).iter_errors(payload))
    if errors:
        return
    with pytest.raises(ValueError):
        validate_market_event_semantics(message_type, payload)


def test_internal_market_gateway_and_aggregator_contract_is_machine_valid() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    for dto in document["dtos"]:
        validator.validate(dto)
    validate_market_contract_semantics(document)


def test_gateway_idempotency_snapshot_failure_and_health_matrix_are_exhaustive() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}

    replay = deepcopy(by_type["SUBSCRIPTION_RESULT"])
    replay["outcome"] = "IDEMPOTENT_REPLAY"
    replay["reason_code"] = "ALREADY_APPLIED"
    validator.validate(replay)

    rejected_snapshot = deepcopy(by_type["SNAPSHOT_RESULT"])
    rejected_snapshot["outcome"] = "REJECTED"
    rejected_snapshot["reason_code"] = "STALE"
    rejected_snapshot["snapshot"] = None
    validator.validate(rejected_snapshot)

    health = by_type["MARKET_HEALTH"]
    for status, quality, reason in [
        ("HEALTHY", "NORMAL", "OK"),
        ("DEGRADED", "DEGRADED", "BACKPRESSURE"),
        ("DEGRADED", "STALE", "STALE"),
        ("DEGRADED", "GAP", "GAP"),
        ("DEGRADED", "RECOVERING", "RECOVERING"),
        ("DISCONNECTED", "UNAVAILABLE", "DISCONNECTED"),
    ]:
        candidate = deepcopy(health)
        candidate.update(status=status, quality=quality, reason_code=reason)
        validator.validate(candidate)


def test_market_health_rejects_every_contradictory_status_combination() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    health = next(dto for dto in document["dtos"] if dto["dto_type"] == "MARKET_HEALTH")
    allowed = {
        ("HEALTHY", "NORMAL", "OK"),
        ("DEGRADED", "DEGRADED", "BACKPRESSURE"),
        ("DEGRADED", "DEGRADED", "SOURCE_LAG"),
        ("DEGRADED", "STALE", "STALE"),
        ("DEGRADED", "GAP", "GAP"),
        ("DEGRADED", "RECOVERING", "RECOVERING"),
        ("DISCONNECTED", "UNAVAILABLE", "UNAVAILABLE"),
        ("DISCONNECTED", "UNAVAILABLE", "DISCONNECTED"),
    }
    statuses = ["HEALTHY", "DEGRADED", "DISCONNECTED"]
    qualities = ["NORMAL", "DEGRADED", "STALE", "GAP", "UNAVAILABLE", "RECOVERING"]
    reasons = [
        "OK",
        "BACKPRESSURE",
        "SOURCE_LAG",
        "STALE",
        "GAP",
        "RECOVERING",
        "UNAVAILABLE",
        "DISCONNECTED",
    ]
    for status, quality, reason in product(statuses, qualities, reasons):
        candidate = deepcopy(health)
        candidate.update(status=status, quality=quality, reason_code=reason)
        assert validator.is_valid(candidate) is ((status, quality, reason) in allowed)


def test_internal_schema_invalid_matrix_is_rejected() -> None:
    validator = _validator("market/market-data.v1.schema.json")
    for dto in _load(FIXTURES / "internal/market-data.v1/schema_invalid.json")["dtos"]:
        case_name = dto.pop("case")
        assert list(validator.iter_errors(dto)), case_name


def test_internal_semantic_invalid_matrix_is_rejected() -> None:
    base = _load(FIXTURES / "internal/market-data.v1/valid.json")
    for case in _load(FIXTURES / "internal/market-data.v1/semantic-invalid.json")["cases"]:
        document = deepcopy(base)
        dto = next(item for item in document["dtos"] if item["dto_type"] == case["dto_type"])
        dto[case["field"]] = case["value"]
        with pytest.raises(ValueError, match=case["error"]):
            validate_market_contract_semantics(document)


def test_live_and_replay_inputs_share_schema_identity_and_deterministic_order() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    inputs = [dto for dto in document["dtos"] if dto["dto_type"] == "BAR_AGGREGATION_INPUT"]
    live = [
        {k: v for k, v in dto.items() if k != "mode"} for dto in inputs if dto["mode"] == "LIVE"
    ]
    replay = [
        {k: v for k, v in dto.items() if k != "mode"} for dto in inputs if dto["mode"] == "REPLAY"
    ]
    assert live == replay
    assert [_canonical_hash(item) for item in live] == [_canonical_hash(item) for item in replay]
