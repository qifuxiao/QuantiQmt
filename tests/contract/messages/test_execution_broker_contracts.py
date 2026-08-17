from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "internal"
GATEWAY_SCHEMA = ROOT / "spec/contracts/execution/broker-gateway.v1.schema.json"
SCENARIO_SCHEMA = ROOT / "spec/contracts/simulation/broker-scenario.v1.schema.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    gateway = _load(GATEWAY_SCHEMA)
    scenario = _load(SCENARIO_SCHEMA)
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in (gateway, scenario)
    )
    return (
        Draft202012Validator(gateway, registry=registry, format_checker=FormatChecker()),
        Draft202012Validator(scenario, registry=registry, format_checker=FormatChecker()),
    )


def _validate_scenario_semantics(scenario: dict[str, Any], requests: list[dict[str, Any]]) -> None:
    if len(scenario["steps"]) != len(requests):
        raise ValueError("each scenario step must consume exactly one request")
    produced: set[int] = set()
    for expected, (step, request) in enumerate(
        zip(scenario["steps"], requests, strict=True), start=1
    ):
        if step["sequence"] != expected:
            raise ValueError("step sequence must be contiguous from one")
        if step["on_operation"] != request["operation"]:
            raise ValueError("step operation does not match the consumed request")
        references = []
        if "source_sequence" in step:
            references.append(step["source_sequence"])
        references.extend(step.get("source_sequences", []))
        if any(reference not in produced for reference in references):
            raise ValueError("source sequence must reference a prior emission group")
        remaining = request.get("remaining_quantity")
        fill = step.get("quantity", step.get("fill_quantity"))
        if fill is not None and (not isinstance(remaining, int) or fill > remaining):
            raise ValueError("fill quantity exceeds request remaining quantity")
        if step["action"] != "DELAY":
            produced.add(step["sequence"])


def _validate_capability_semantics(
    capability: dict[str, Any], registered_client_order_id: str
) -> None:
    client_id = capability["client_order_id"]
    rate_limit = capability["rate_limit"]
    if client_id["min_length"] > client_id["max_length"]:
        raise ValueError("client_order_id minimum exceeds maximum")
    if rate_limit["reserved_cancel"] + rate_limit["reserved_reconciliation"] > rate_limit["burst"]:
        raise ValueError("reserved capacity exceeds burst")
    try:
        flags = 0 if client_id["case_sensitive"] else re.IGNORECASE
        pattern = re.compile(client_id["pattern"], flags)
    except re.error as exc:
        raise ValueError("client_order_id pattern is invalid") from exc
    if not client_id["min_length"] <= len(registered_client_order_id) <= client_id["max_length"]:
        raise ValueError("registered client_order_id length violates capability")
    if pattern.fullmatch(registered_client_order_id) is None:
        raise ValueError("registered client_order_id does not match capability")


def _validate_execution_request_semantics(
    request: dict[str, Any], registration: dict[str, Any], capability: dict[str, Any]
) -> None:
    if request["capability_version"] != registration["broker_capability_version"]:
        raise ValueError("request capability version differs from registration")
    if capability["capability_version"] != registration["broker_capability_version"]:
        raise ValueError("capability snapshot differs from registration")
    if request["client_order_id"] != registration["client_order_id"]:
        raise ValueError("request client_order_id differs from registration")
    if request["broker"] != registration["broker"]:
        raise ValueError("request broker differs from registration")
    if capability["broker"] != registration["broker"]:
        raise ValueError("capability broker differs from registration")
    _validate_capability_semantics(capability, registration["client_order_id"])


def test_gateway_fixture_freezes_every_operation_and_canonical_result() -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")

    for dto in fixture["dtos"]:
        gateway.validate(dto)

    assert {dto["dto_type"] for dto in fixture["dtos"]} == {
        "BROKER_CAPABILITIES",
        "SUBMIT_ORDER_REQUEST",
        "CANCEL_ORDER_REQUEST",
        "QUERY_ORDER_REQUEST",
        "OPEN_ORDERS_REQUEST",
        "TRADES_REQUEST",
        "ACCOUNT_REQUEST",
        "POSITIONS_REQUEST",
        "OPERATION_RESULT",
        "ORDER_SNAPSHOT",
        "TRADE_SNAPSHOT",
        "ACCOUNT_SNAPSHOT",
        "POSITION_SNAPSHOT",
        "ORDER_PAGE",
        "TRADE_PAGE",
        "POSITION_PAGE",
        "READ_RESULT",
        "BROKER_HEALTH",
    }
    assert {dto["operation"] for dto in fixture["dtos"] if dto["dto_type"] == "READ_RESULT"} == {
        "QUERY_ORDER",
        "OPEN_ORDERS",
        "TRADES",
        "ACCOUNT",
        "POSITIONS",
    }
    _validate_capability_semantics(fixture["dtos"][0], "client-1")


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "execution-broker-gateway.v1/invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_gateway_rejects_unsafe_or_ambiguous_dtos(case: dict[str, Any]) -> None:
    gateway, _ = _validators()
    assert not gateway.is_valid(case["dto"])


@pytest.mark.parametrize(
    ("name", "repair"),
    [
        ("submit_missing_idempotency", ("idempotency_key", "idem-submit-1")),
        ("cancel_missing_fence", ("fencing_token", 7)),
        ("float_limit_price", ("limit_price", "10.01")),
    ],
)
def test_named_invalid_fixture_has_exactly_its_named_failure(
    name: str, repair: tuple[str, object]
) -> None:
    gateway, _ = _validators()
    cases = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/invalid.json")["cases"]
    invalid = deepcopy(next(case["dto"] for case in cases if case["name"] == name))

    assert invalid["capability_version"] == "sim-v1"
    assert not gateway.is_valid(invalid)
    field, value = repair
    invalid[field] = value
    gateway.validate(invalid)


@pytest.mark.parametrize(
    "mutation",
    ["client_id_range", "reserved_capacity", "invalid_regex", "registered_id_mismatch"],
)
def test_capability_semantics_fail_closed_on_cross_field_conflicts(mutation: str) -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    capability = deepcopy(fixture["dtos"][0])
    if mutation == "client_id_range":
        capability["client_order_id"]["min_length"] = 33
    elif mutation == "reserved_capacity":
        capability["rate_limit"]["reserved_cancel"] = 19
        capability["rate_limit"]["reserved_reconciliation"] = 2
    elif mutation == "invalid_regex":
        capability["client_order_id"]["pattern"] = "["

    if mutation == "invalid_regex":
        assert not gateway.is_valid(capability)
    else:
        gateway.validate(capability)
    with pytest.raises(ValueError):
        _validate_capability_semantics(
            capability, "client with spaces" if mutation == "registered_id_mismatch" else "client-1"
        )


def test_submit_cancel_require_frozen_capability_version() -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    for operation in ("SUBMIT_ORDER_REQUEST", "CANCEL_ORDER_REQUEST"):
        request = next(dto for dto in fixture["dtos"] if dto["dto_type"] == operation)
        gateway.validate(request)
        missing = deepcopy(request)
        missing.pop("capability_version")
        assert not gateway.is_valid(missing)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("request_capability_version", "request capability version"),
        ("capability_version", "capability snapshot"),
        ("request_client_order_id", "request client_order_id"),
        ("request_broker", "request broker"),
        ("capability_broker", "capability broker"),
    ],
)
def test_submit_cancel_semantics_bind_registration_and_capability_identity(
    mutation: str, message: str
) -> None:
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    registration = {
        "client_order_id": "client-1",
        "broker": "sim",
        "broker_capability_version": "sim-v1",
    }
    for operation in ("SUBMIT_ORDER_REQUEST", "CANCEL_ORDER_REQUEST"):
        capability = deepcopy(fixture["dtos"][0])
        request = deepcopy(next(dto for dto in fixture["dtos"] if dto["dto_type"] == operation))
        _validate_execution_request_semantics(request, registration, capability)
        if mutation == "request_capability_version":
            request["capability_version"] = "sim-v2"
        elif mutation == "capability_version":
            capability["capability_version"] = "sim-v2"
        elif mutation == "request_client_order_id":
            request["client_order_id"] = "client-2"
        elif mutation == "request_broker":
            request["broker"] = "other"
        elif mutation == "capability_broker":
            capability["broker"] = "other"
        with pytest.raises(ValueError, match=message):
            _validate_execution_request_semantics(request, registration, capability)


@pytest.mark.parametrize(
    ("status", "capability_version", "reason_code"),
    [
        ("HEALTHY", "sim-v1", None),
        ("DEGRADED", "sim-v1", "RATE_LIMITED"),
        ("DEGRADED", "sim-v1", "TRANSPORT_ERROR"),
        ("DISCONNECTED", None, "DISCONNECTED"),
    ],
)
def test_broker_health_accepts_only_frozen_legal_matrix(
    status: str, capability_version: str | None, reason_code: str | None
) -> None:
    gateway, _ = _validators()
    health = {
        "dto_type": "BROKER_HEALTH",
        "broker": "sim",
        "status": status,
        "capability_version": capability_version,
        "reason_code": reason_code,
        "observed_at": "2026-08-07T02:00:02Z",
    }
    gateway.validate(health)


def test_broker_health_rejects_every_contradictory_status_combination() -> None:
    gateway, _ = _validators()
    valid = {
        ("HEALTHY", "sim-v1", None),
        ("DEGRADED", "sim-v1", "RATE_LIMITED"),
        ("DEGRADED", "sim-v1", "TRANSPORT_ERROR"),
        ("DISCONNECTED", None, "DISCONNECTED"),
    }
    statuses = ("HEALTHY", "DEGRADED", "DISCONNECTED")
    versions = ("sim-v1", None)
    reasons = (None, "RATE_LIMITED", "TRANSPORT_ERROR", "DISCONNECTED", "ADAPTER_TEXT")

    for status in statuses:
        for capability_version in versions:
            for reason_code in reasons:
                combination = (status, capability_version, reason_code)
                if combination in valid:
                    continue
                health = {
                    "dto_type": "BROKER_HEALTH",
                    "broker": "sim",
                    "status": status,
                    "capability_version": capability_version,
                    "reason_code": reason_code,
                    "observed_at": "2026-08-07T02:00:02Z",
                }
                assert not gateway.is_valid(health), combination


@pytest.mark.parametrize(
    ("operation", "reason"),
    [("SUBMIT", "BROKER_CANCELED"), ("CANCEL", "BROKER_ACCEPTED")],
)
def test_operation_result_rejects_cross_operation_confirmations(
    operation: str, reason: str
) -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    result = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "OPERATION_RESULT")
    contradictory = deepcopy(result)
    contradictory.update(
        {
            "operation": operation,
            "outcome": "CONFIRMED",
            "reason_code": reason,
            "broker_order_id": "broker-1",
            "reconciliation_required": False,
        }
    )
    assert not gateway.is_valid(contradictory)


def test_operation_result_reject_cannot_claim_post_dispatch_timeout() -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    result = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "OPERATION_RESULT")
    contradictory = deepcopy(result)
    contradictory.update(
        {
            "outcome": "REJECTED",
            "reason_code": "TIMEOUT_AFTER_DISPATCH",
            "side_effect_possible": False,
            "reconciliation_required": False,
        }
    )
    assert not gateway.is_valid(contradictory)


@pytest.mark.parametrize(
    "reason",
    ["UNSUPPORTED_CAPABILITY", "RATE_LIMITED", "DEADLINE_EXCEEDED", "DISCONNECTED"],
)
def test_read_failures_are_typed_and_payload_free(reason: str) -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    reads = [dto for dto in fixture["dtos"] if dto["dto_type"] == "READ_RESULT"]
    for result in reads:
        gateway.validate(result)
        failed = deepcopy(result)
        failed.update({"outcome": "REJECTED", "reason_code": reason, "payload": None})
        failed["retry_after_ms"] = 10 if reason == "RATE_LIMITED" else None
        gateway.validate(failed)
        failed["payload"] = result["payload"] if result["payload"] is not None else {}
        assert not gateway.is_valid(failed)


def test_rate_limited_read_requires_retry_after() -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    result = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "READ_RESULT")
    result.update({"outcome": "REJECTED", "reason_code": "RATE_LIMITED", "payload": None})
    result["retry_after_ms"] = None
    assert not gateway.is_valid(result)


def test_unknown_outcome_is_machine_bound_to_reconciliation_and_same_identity() -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    unknown = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "OPERATION_RESULT")
    gateway.validate(unknown)

    no_reconciliation = deepcopy(unknown)
    no_reconciliation["reconciliation_required"] = False
    assert not gateway.is_valid(no_reconciliation)

    no_identity = deepcopy(unknown)
    no_identity.pop("idempotency_key")
    assert not gateway.is_valid(no_identity)


def test_scenario_fixture_covers_required_fault_model_deterministically() -> None:
    _, scenario = _validators()
    fixture = _load(FIXTURE_ROOT / "broker-scenario.v1/all-actions.valid.json")
    scenario.validate(fixture)

    assert {step["action"] for step in fixture["steps"]} == {
        "ACCEPT",
        "REJECT",
        "PARTIAL_FILL",
        "FULL_FILL",
        "DUPLICATE",
        "OUT_OF_ORDER",
        "DELAY",
        "DISCONNECT",
        "CANCEL_RACE",
    }
    assert fixture["clock"]["mode"] == "MANUAL"
    assert isinstance(fixture["seed"], int)
    context = _load(FIXTURE_ROOT / "broker-scenario.v1/semantic-context.valid.json")
    _validate_scenario_semantics(fixture, context["requests"])


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "broker-scenario.v1/semantic-invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_scenario_semantic_validator_rejects_ordering_ambiguity(case: dict[str, Any]) -> None:
    _, scenario = _validators()
    scenario.validate(case["scenario"])
    with pytest.raises(ValueError):
        _validate_scenario_semantics(case["scenario"], case["requests"])


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "broker-scenario.v1/invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_scenario_rejects_nondeterministic_or_imprecise_cases(case: dict[str, Any]) -> None:
    _, scenario = _validators()
    assert not scenario.is_valid(case["scenario"])


@pytest.mark.parametrize("negative_zero", ["-0", "-0.0", "-0.00", "-0.00000000"])
def test_signed_decimal_schema_rejects_every_negative_zero_form(negative_zero: str) -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    account = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "ACCOUNT_SNAPSHOT")
    invalid = deepcopy(account)
    invalid["cash_balance"] = negative_zero
    assert not gateway.is_valid(invalid)


def test_normative_text_freezes_ownership_unknown_and_determinism() -> None:
    ports = Path("spec/interfaces/core-ports.md").read_text(encoding="utf-8")
    persistence = Path("spec/interfaces/order-persistence-ports.md").read_text(encoding="utf-8")
    simulator = Path("spec/interfaces/broker-simulator.md").read_text(encoding="utf-8")
    submit = yaml.safe_load(Path("spec/workflows/submit-order.yaml").read_text(encoding="utf-8"))
    cancel = yaml.safe_load(Path("spec/workflows/cancel-order.yaml").read_text(encoding="utf-8"))
    reliability = yaml.safe_load(Path("spec/nfr/reliability.yaml").read_text(encoding="utf-8"))

    assert "Execution MUST NOT own or advance OMS business state" in ports
    assert "same idempotency_key and client_order_id" in ports
    assert "MUST return the schema-defined `ReadResult`" in ports
    assert "broker_capability_version" in persistence
    assert "step/request count mismatch" in simulator
    assert submit["workflow"]["unknown_outcome"]["blind_retry"] == "forbidden"
    assert cancel["workflow"]["unknown_outcome"]["blind_retry"] == "forbidden"
    assert reliability["nfr"]["broker_simulator"]["determinism_inputs"] == [
        "scenario",
        "seed",
        "manual_clock",
        "request_sequence",
    ]


def test_manifest_preserves_execution_contracts_across_market_spec_revision() -> None:
    manifest = yaml.safe_load(Path("spec/manifest.yaml").read_text(encoding="utf-8"))
    change = manifest["change"]
    ids = {entry["id"] for entries in manifest["catalogs"].values() for entry in entries}

    assert manifest["specification"]["version"] == "0.11.0"
    assert change["previous_version"] == "0.10.0"
    assert {
        "CONTRACT-EXECUTION-BROKER-GATEWAY-V1",
        "PORTS-BROKER-SIMULATOR",
        "CONTRACT-ORDER-REGISTERED-V1",
    } <= ids
    assert change["rollback"]["release"] == "prohibited"
