from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import pytest
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from quantiqmt.contracts import (
    ContractValidationError,
    MessageCodec,
    MessageEnvelope,
    SchemaRegistry,
    UnsupportedSchemaVersionError,
)

UUID1 = "550e8400-e29b-41d4-a716-446655440000"
UUID2 = "550e8400-e29b-41d4-a716-446655440001"
NOW = "2026-07-02T02:00:00Z"
FIXTURE_ROOT = Path(__file__).with_name("fixtures")

PAYLOADS: dict[str, dict[str, object]] = {
    "strategy.submit_order_intent.v1": {
        "intent_id": UUID1,
        "strategy_id": "s",
        "strategy_version": "1",
        "account_id": "a",
        "instrument_id": "600000.XSHG",
        "side": "BUY",
        "position_effect": "AUTO",
        "order_type": "LIMIT",
        "quantity": 100,
        "limit_price": "10.01",
        "time_in_force": "DAY",
        "signal_time": NOW,
        "market_data_version": "m1",
        "valid_until": NOW,
    },
    "strategy.submit_target.v1": {
        "target_id": UUID1,
        "target_type": "WEIGHT",
        "strategy_id": "s",
        "strategy_version": "1",
        "scope_id": "a",
        "instrument_id": "600000.XSHG",
        "target_weight": "0.5",
        "decision_id": UUID2,
        "input_event_id": UUID1,
        "effective_at": NOW,
        "valid_until": NOW,
    },
    "execution.cancel_order.v1": {
        "cancel_request_id": UUID1,
        "order_id": UUID2,
        "client_order_id": "c1",
        "broker": "qmt",
        "account_id": "a",
        "expected_order_version": 1,
        "fencing_token": 1,
        "requested_at": NOW,
    },
    "broker.trade_reported.v1": {
        "broker": "qmt",
        "account_id": "a",
        "trading_day": "2026-07-02",
        "trade_id": "t1",
        "broker_order_id": "b1",
        "instrument_id": "600000.XSHG",
        "side": "BUY",
        "position_effect": "AUTO",
        "price": "10.01",
        "quantity": 100,
        "trade_time": NOW,
        "received_at": NOW,
    },
    "oms.order_status_changed.v1": {
        "order_id": UUID1,
        "from_status": "REGISTERED",
        "to_status": "RISK_PENDING",
        "reason_code": "START_RISK",
        "cum_quantity": 0,
        "leaves_quantity": 100,
        "changed_at": NOW,
    },
    "oms.order_registered.v1": {
        "order_id": UUID1,
        "intent_id": UUID2,
        "account_id": "a",
        "instrument_id": "600000.XSHG",
        "side": "BUY",
        "position_effect": "AUTO",
        "order_type": "LIMIT",
        "quantity": 100,
        "limit_price": "10.01",
        "time_in_force": "DAY",
        "owner_strategy_id": "s",
        "owner_strategy_version": "1",
        "registered_at": NOW,
    },
    "risk.order_evaluated.v1": {
        "decision_id": UUID1,
        "order_id": UUID2,
        "expected_order_version": 1,
        "decision": "PASS",
        "rule_set_version": "r1",
        "snapshot_versions": {"account": "a1", "portfolio": "p1", "market": "m1"},
        "rule_results": [
            {"rule_id": "limit", "result": "PASS", "reason_code": "OK", "latency_us": 1}
        ],
        "evaluated_at": NOW,
    },
    "execution.attempt_started.v1": {
        "attempt_id": UUID1,
        "order_id": UUID2,
        "operation": "SUBMIT",
        "client_order_id": "c1",
        "broker": "qmt",
        "account_id": "a",
        "expected_order_version": 2,
        "fencing_token": 1,
        "started_at": NOW,
    },
    "execution.outcome_unknown.v1": {
        "attempt_id": UUID1,
        "order_id": UUID2,
        "operation": "SUBMIT",
        "client_order_id": "c1",
        "broker": "qmt",
        "account_id": "a",
        "fencing_token": 1,
        "reason_code": "TIMEOUT",
        "reconciliation_required": True,
        "unknown_at": NOW,
    },
    "broker.order_reported.v1": {
        "report_id": "r1",
        "broker": "qmt",
        "account_id": "a",
        "trading_day": "2026-07-02",
        "client_order_id": "c1",
        "broker_status": "ACCEPTED",
        "cum_quantity": 0,
        "leaves_quantity": 100,
        "report_time": NOW,
        "received_at": NOW,
    },
    "ledger.trade_posted.v1": {
        "ledger_transaction_id": UUID1,
        "broker": "qmt",
        "account_id": "a",
        "trading_day": "2026-07-02",
        "trade_id": "t1",
        "order_id": UUID2,
        "instrument_id": "600000.XSHG",
        "side": "BUY",
        "position_effect": "AUTO",
        "price": "10.01000000",
        "quantity": 100,
        "currency": "CNY",
        "entries": [
            {"account_code": "SEC", "direction": "DEBIT", "amount": "1001.00", "currency": "CNY"},
            {"account_code": "CASH", "direction": "CREDIT", "amount": "1001.00", "currency": "CNY"},
        ],
        "posted_at": NOW,
    },
    "portfolio.position_changed.v1": {
        "account_id": "a",
        "instrument_id": "600000.XSHG",
        "trading_day": "2026-07-02",
        "position_version": 1,
        "source_ledger_transaction_id": UUID1,
        "previous_quantity": 0,
        "current_quantity": 100,
        "available_quantity": 0,
        "currency": "CNY",
        "changed_at": NOW,
    },
}


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry(Path("spec/contracts"))


def envelope(message_type: str, payload: dict[str, object], version: int = 1) -> dict[str, object]:
    return {
        "message_id": "message-00000001",
        "message_type": message_type,
        "schema_version": version,
        "occurred_at": NOW,
        "received_at": NOW,
        "correlation_id": "correlation-0001",
        "source": "tests",
        "partition_key": "p1",
        "payload": payload,
    }


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_all_approved_payloads_round_trip_without_precision_loss(
    registry: SchemaRegistry, message_type: str
) -> None:
    codec = MessageCodec(registry)
    original = envelope(message_type, PAYLOADS[message_type])
    decoded = codec.decode(codec.encode(MessageEnvelope.create(original, registry)))
    assert decoded.to_primitive() == original


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_required_and_additional_properties_are_strict(
    registry: SchemaRegistry, message_type: str
) -> None:
    payload = deepcopy(PAYLOADS[message_type])
    payload.pop(next(iter(payload)))
    with pytest.raises(ContractValidationError, match="missing required"):
        MessageEnvelope.create(envelope(message_type, payload), registry)

    payload = deepcopy(PAYLOADS[message_type])
    payload["unexpected"] = True
    with pytest.raises(ContractValidationError, match="additional property"):
        MessageEnvelope.create(envelope(message_type, payload), registry)


def test_unknown_enum_and_version_fail_explicitly(registry: SchemaRegistry) -> None:
    payload = deepcopy(PAYLOADS["oms.order_registered.v1"])
    payload["side"] = "UNKNOWN_FUTURE_SIDE"
    with pytest.raises(ContractValidationError, match="unknown enum"):
        MessageEnvelope.create(envelope("oms.order_registered.v1", payload), registry)
    with pytest.raises(UnsupportedSchemaVersionError):
        MessageEnvelope.create(envelope("oms.order_registered.v2", payload, 2), registry)


def test_payload_is_deeply_immutable_and_decimal_text_is_preserved(
    registry: SchemaRegistry,
) -> None:
    message = MessageEnvelope.create(
        envelope("ledger.trade_posted.v1", PAYLOADS["ledger.trade_posted.v1"]), registry
    )
    assert isinstance(message.fields, MappingProxyType)
    assert message.payload["price"] == "10.01000000"
    entries = message.payload["entries"]
    assert isinstance(entries, tuple)
    with pytest.raises(TypeError):
        message.payload._values["price"] = "1"  # type: ignore[index]


def test_malformed_json_and_non_object_root_fail(registry: SchemaRegistry) -> None:
    codec = MessageCodec(registry)
    with pytest.raises(ContractValidationError):
        codec.decode("{")
    with pytest.raises(ContractValidationError, match="root"):
        codec.decode("[]")


def test_public_constructors_cannot_bypass_validation(registry: SchemaRegistry) -> None:
    with pytest.raises(TypeError, match="create"):
        MessageEnvelope({}, object())
    payload_type = type(
        MessageEnvelope.create(
            envelope("oms.order_registered.v1", PAYLOADS["oms.order_registered.v1"]),
            registry,
        ).payload
    )
    with pytest.raises(TypeError, match="create"):
        payload_type("x", 1, {})


@pytest.mark.parametrize("bad_time", ["20260702T020000Z", "2026-07-02T02:00:00,1Z"])
def test_runtime_rejects_non_rfc3339_datetime(registry: SchemaRegistry, bad_time: str) -> None:
    payload = deepcopy(PAYLOADS["oms.order_registered.v1"])
    payload["registered_at"] = bad_time
    with pytest.raises(ContractValidationError):
        MessageEnvelope.create(envelope("oms.order_registered.v1", payload), registry)


def test_registry_schema_is_deeply_immutable(registry: SchemaRegistry) -> None:
    schema = registry.payload("execution.cancel_order.v1", 1)
    properties = schema["properties"]
    assert isinstance(properties, MappingProxyType)
    with pytest.raises(TypeError):
        properties["fencing_token"] = {}  # type: ignore[index]


@pytest.mark.parametrize(
    "path",
    sorted(FIXTURE_ROOT.glob("*/*.valid.json")),
    ids=lambda path: str(path.parent.name + "/" + path.name),
)
def test_disk_golden_valid_fixtures_pass(registry: SchemaRegistry, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    MessageEnvelope.create(envelope(path.parent.name, payload), registry)
    official = Draft202012Validator(
        registry.payload(path.parent.name, 1), format_checker=FormatChecker()
    )
    assert not list(official.iter_errors(payload))


@pytest.mark.parametrize(
    "path",
    sorted(FIXTURE_ROOT.glob("*/invalid.*.json")),
    ids=lambda path: str(path.parent.name + "/" + path.name),
)
def test_disk_golden_invalid_fixtures_fail(registry: SchemaRegistry, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(ContractValidationError):
        MessageEnvelope.create(envelope(path.parent.name, payload), registry)
    official = Draft202012Validator(
        registry.payload(path.parent.name, 1), format_checker=FormatChecker()
    )
    assert list(official.iter_errors(payload))


def test_every_message_has_required_disk_fixture_set(registry: SchemaRegistry) -> None:
    common = {
        "minimal.valid.json",
        "maximal.valid.json",
        "invalid.missing-required.json",
        "invalid.additional-property.json",
        "invalid.precision.json",
    }
    for message_type in registry.message_types:
        names = {path.name for path in (FIXTURE_ROOT / message_type).glob("*.json")}
        assert common <= names, message_type
    assert (
        FIXTURE_ROOT / "strategy.submit_order_intent.v1/invalid.limit-missing-price.json"
    ).is_file()
    assert (
        FIXTURE_ROOT / "execution.outcome_unknown.v1/invalid.cancel-missing-request-id.json"
    ).is_file()
    assert (FIXTURE_ROOT / "strategy.submit_target.v1/invalid.one-of-no-match.json").is_file()


def _assert_present_strings_reach_max_length(value: object, schema: object) -> None:
    if not isinstance(schema, MappingProxyType):
        return
    if (
        isinstance(value, str)
        and "maxLength" in schema
        and not any(key in schema for key in ("enum", "format", "pattern"))
    ):
        assert len(value) == schema["maxLength"]
    if isinstance(value, str) and "\\." in schema.get("pattern", ""):
        assert value.rsplit(".", 1)[-1] == "00000000"
    elif isinstance(value, dict):
        properties = schema.get("properties", {})
        assert set(properties) <= set(value)
        additional = schema.get("additionalProperties", {})
        for key, item in value.items():
            _assert_present_strings_reach_max_length(item, properties.get(key, additional))
    elif isinstance(value, list):
        for item in value:
            _assert_present_strings_reach_max_length(item, schema.get("items", {}))


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_maximal_fixtures_exercise_declared_string_boundaries(
    registry: SchemaRegistry, message_type: str
) -> None:
    path = FIXTURE_ROOT / message_type / "maximal.valid.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    _assert_present_strings_reach_max_length(payload, registry.payload(message_type, 1))


@pytest.mark.parametrize("message_type", sorted(PAYLOADS))
def test_runtime_acceptance_matches_official_jsonschema_for_golden_payloads(
    registry: SchemaRegistry, message_type: str
) -> None:
    schema = registry.payload(message_type, 1)
    official = Draft202012Validator(schema, format_checker=FormatChecker())
    assert not list(official.iter_errors(PAYLOADS[message_type]))
    MessageEnvelope.create(envelope(message_type, PAYLOADS[message_type]), registry)


@pytest.mark.parametrize(
    ("message_type", "field"),
    [
        ("strategy.submit_order_intent.v1", "side"),
        ("strategy.submit_target.v1", "target_type"),
        ("oms.order_registered.v1", "order_type"),
        ("risk.order_evaluated.v1", "decision"),
        ("execution.attempt_started.v1", "operation"),
        ("execution.outcome_unknown.v1", "operation"),
        ("broker.order_reported.v1", "broker_status"),
        ("ledger.trade_posted.v1", "side"),
    ],
)
def test_unknown_enum_golden_cases_are_rejected(
    registry: SchemaRegistry, message_type: str, field: str
) -> None:
    payload = deepcopy(PAYLOADS[message_type])
    payload[field] = "UNKNOWN_ENUM_V1"
    with pytest.raises(ContractValidationError, match="unknown enum"):
        MessageEnvelope.create(envelope(message_type, payload), registry)
