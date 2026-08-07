from __future__ import annotations

import json
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


def _validate_scenario_semantics(scenario: dict[str, Any]) -> None:
    produced: set[int] = set()
    for expected, step in enumerate(scenario["steps"], start=1):
        if step["sequence"] != expected:
            raise ValueError("step sequence must be contiguous from one")
        references = []
        if "source_sequence" in step:
            references.append(step["source_sequence"])
        references.extend(step.get("source_sequences", []))
        if any(reference not in produced for reference in references):
            raise ValueError("source sequence must reference a prior emission group")
        if step["action"] != "DELAY":
            produced.add(step["sequence"])


def _validate_capability_semantics(capability: dict[str, Any]) -> None:
    client_id = capability["client_order_id"]
    rate_limit = capability["rate_limit"]
    if client_id["min_length"] > client_id["max_length"]:
        raise ValueError("client_order_id minimum exceeds maximum")
    if rate_limit["reserved_cancel"] + rate_limit["reserved_reconciliation"] > rate_limit["burst"]:
        raise ValueError("reserved capacity exceeds burst")


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
    }
    _validate_capability_semantics(fixture["dtos"][0])


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "execution-broker-gateway.v1/invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_gateway_rejects_unsafe_or_ambiguous_dtos(case: dict[str, Any]) -> None:
    gateway, _ = _validators()
    assert not gateway.is_valid(case["dto"])


@pytest.mark.parametrize("mutation", ["client_id_range", "reserved_capacity"])
def test_capability_semantics_fail_closed_on_cross_field_conflicts(mutation: str) -> None:
    gateway, _ = _validators()
    fixture = _load(FIXTURE_ROOT / "execution-broker-gateway.v1/all-dtos.valid.json")
    capability = deepcopy(fixture["dtos"][0])
    if mutation == "client_id_range":
        capability["client_order_id"]["min_length"] = 33
    else:
        capability["rate_limit"]["reserved_cancel"] = 19
        capability["rate_limit"]["reserved_reconciliation"] = 2

    gateway.validate(capability)
    with pytest.raises(ValueError):
        _validate_capability_semantics(capability)


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
    _validate_scenario_semantics(fixture)


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "broker-scenario.v1/semantic-invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_scenario_semantic_validator_rejects_ordering_ambiguity(case: dict[str, Any]) -> None:
    _, scenario = _validators()
    scenario.validate(case["scenario"])
    with pytest.raises(ValueError):
        _validate_scenario_semantics(case["scenario"])


@pytest.mark.parametrize(
    "case",
    _load(FIXTURE_ROOT / "broker-scenario.v1/invalid.json")["cases"],
    ids=lambda case: case["name"],
)
def test_scenario_rejects_nondeterministic_or_imprecise_cases(case: dict[str, Any]) -> None:
    _, scenario = _validators()
    assert not scenario.is_valid(case["scenario"])


def test_normative_text_freezes_ownership_unknown_and_determinism() -> None:
    ports = Path("spec/interfaces/core-ports.md").read_text(encoding="utf-8")
    submit = yaml.safe_load(Path("spec/workflows/submit-order.yaml").read_text(encoding="utf-8"))
    cancel = yaml.safe_load(Path("spec/workflows/cancel-order.yaml").read_text(encoding="utf-8"))
    reliability = yaml.safe_load(Path("spec/nfr/reliability.yaml").read_text(encoding="utf-8"))

    assert "Execution MUST NOT own or advance OMS business state" in ports
    assert "same idempotency_key and client_order_id" in ports
    assert submit["workflow"]["unknown_outcome"]["blind_retry"] == "forbidden"
    assert cancel["workflow"]["unknown_outcome"]["blind_retry"] == "forbidden"
    assert reliability["nfr"]["broker_simulator"]["determinism_inputs"] == [
        "scenario",
        "seed",
        "manual_clock",
        "request_sequence",
    ]
