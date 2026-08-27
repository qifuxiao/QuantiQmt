from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "spec/contracts/simulation/backtest-parity.v1.schema.json"
SEMANTIC_PATH = ROOT / "spec/contracts/simulation/backtest-parity.semantic-validation.v1.yaml"
PORT_PATH = ROOT / "spec/interfaces/backtest-ports.md"
WORKFLOW_PATH = ROOT / "spec/workflows/backtest-run.yaml"
FIXTURE_PATH = Path(__file__).with_name("fixtures") / "internal/backtest-parity.v1/valid.json"
NAMESPACE = uuid.UUID("2f35004e-90c8-5da8-97b8-767a692f0fcb")
SAFE_INTEGER_MAX = 9_007_199_254_740_991
PRIORITIES = {
    "CONTROL": 0,
    "HISTORICAL_RELEASE": 5,
    "SESSION": 10,
    "MARKET_QUALITY": 20,
    "BROKER_TRADE": 30,
    "BROKER_ORDER": 40,
    "MARKET_DATA": 50,
    "STRATEGY_CALLBACK": 60,
    "TIMER": 70,
    "CHECKPOINT": 80,
}
MESSAGE_CONTRACT = {
    "market.tick_received.v1": "CONTRACT-MARKET-TICK-RECEIVED-V1",
    "market.bar_closed.v1": "CONTRACT-MARKET-BAR-CLOSED-V1",
    "market.quality_changed.v1": "CONTRACT-MARKET-QUALITY-CHANGED-V1",
    "market.session_changed.v1": "CONTRACT-MARKET-SESSION-CHANGED-V1",
}
RUN_FINGERPRINT_FIELDS = (
    "schema_version",
    "mode",
    "start_at",
    "end_at",
    "seed",
    "contract_bundle",
    "code_artifact",
    "strategy_artifact",
    "strategy_parameters",
    "historical_dataset",
    "calendar",
    "tzdb",
    "market_policy",
    "execution_policy",
    "risk_rule_set",
    "target_policy",
    "initial_state",
    "scheduler_policy",
    "storage_policy",
    "no_lookahead",
    "ambient_randomness",
    "wall_clock",
)
EVIDENCE_FIELDS = (
    "run_id",
    "input_fingerprint",
    "status",
    "reason_code",
    "started_at",
    "ended_at",
    "event_count",
    "last_scheduler_key",
    "event_journal_checksum",
    "strategy_output_checksum",
    "broker_report_checksum",
    "ledger_checksum",
    "portfolio_checksum",
    "metrics_checksum",
)
SCHEDULER_EVENT_FINGERPRINT_FIELDS = (
    "schema_version",
    "run_id",
    "event_type",
    "dispatch_at",
    "priority",
    "source_id",
    "source_sequence",
    "causal_sequence",
    "contract_id",
    "payload_checksum",
    "idempotency_key",
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def _validator() -> Draft202012Validator:
    schema = _json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _dtos() -> dict[str, dict[str, Any]]:
    return {dto["dto_type"]: dto for dto in _json(FIXTURE_PATH)["dtos"]}


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("time must be canonical UTC Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _jcs_bytes(value: object) -> bytes:
    # Reference vectors contain only ASCII keys, canonical integer tokens and Decimal strings.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha(value: object) -> str:
    return hashlib.sha256(_jcs_bytes(value)).hexdigest()


def _projection(value: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: value[field] for field in fields}


def _validate_manifest(manifest: dict[str, Any]) -> None:
    expected_checksum = _sha(
        {key: value for key, value in manifest.items() if key != "content_checksum"}
    )
    if manifest["content_checksum"] != expected_checksum:
        raise ValueError("manifest checksum mismatch")
    prior_by_source: dict[str, int] = {}
    canonical = sorted(
        manifest["partitions"],
        key=lambda part: (
            part["source_id"].encode("ascii"),
            part["first_source_sequence"],
            part["partition_id"].encode("ascii"),
        ),
    )
    if canonical != manifest["partitions"]:
        raise ValueError("partitions are not in canonical order")
    for partition in manifest["partitions"]:
        if partition["first_source_sequence"] > partition["last_source_sequence"]:
            raise ValueError("partition sequence range is inverted")
        if _utc(partition["min_event_time"]) > _utc(partition["max_event_time"]):
            raise ValueError("partition event-time range is inverted")
        if _utc(partition["min_available_at"]) > _utc(partition["max_available_at"]):
            raise ValueError("partition availability range is inverted")
        previous = prior_by_source.get(partition["source_id"])
        if previous is not None and partition["first_source_sequence"] <= previous:
            raise ValueError("partition source sequence overlaps prior partition")
        prior_by_source[partition["source_id"]] = partition["last_source_sequence"]


def _validate_run_spec(run: dict[str, Any]) -> None:
    if _utc(run["start_at"]) >= _utc(run["end_at"]):
        raise ValueError("run start must be before end")
    fingerprint = _sha(_projection(run, RUN_FINGERPRINT_FIELDS))
    if run["input_fingerprint"] != fingerprint:
        raise ValueError("input fingerprint mismatch")
    if run["run_id"] != str(uuid.uuid5(NAMESPACE, fingerprint)):
        raise ValueError("run identity mismatch")
    if run["seed"] > SAFE_INTEGER_MAX:
        raise ValueError("seed is not I-JSON safe")
    if run["wall_clock"] != "FORBIDDEN" or run["ambient_randomness"] != "FORBIDDEN":
        raise ValueError("ambient nondeterminism is forbidden")


def _validate_history_page(
    request: dict[str, Any], result: dict[str, Any], virtual_now: str
) -> None:
    for key in ("request_id", "run_id", "manifest_checksum"):
        if request[key] != result[key]:
            raise ValueError(f"historical {key} mismatch")
    if _utc(request["available_at_lte"]) > _utc(virtual_now):
        raise ValueError("future data requested")
    if result["outcome"] == "WAIT":
        if _utc(result["next_available_at"]) <= _utc(virtual_now):
            raise ValueError("historical wait does not advance virtual time")
        return
    if result["outcome"] != "PAGE":
        return
    prior_key: tuple[datetime, bytes, int, str] | None = None
    for item in result["items"]:
        if _utc(item["event_time"]) > _utc(item["available_at"]):
            raise ValueError("event is available before it occurred")
        if _utc(item["available_at"]) > _utc(request["available_at_lte"]):
            raise ValueError("page contains event after request availability")
        if _utc(item["available_at"]) > _utc(virtual_now):
            raise ValueError("page exposes future event")
        if MESSAGE_CONTRACT[item["message_type"]] != item["contract_id"]:
            raise ValueError("message and contract are not bound")
        key = (
            _utc(item["available_at"]),
            item["source_id"].encode("ascii"),
            item["source_sequence"],
            item["event_id"],
        )
        if prior_key is not None and key <= prior_key:
            raise ValueError("historical page is not canonically ordered")
        prior_key = key


def _scheduler_key(event: dict[str, Any]) -> tuple[datetime, int, bytes, int, int, str]:
    return (
        _utc(event["dispatch_at"]),
        event["priority"],
        event["source_id"].encode("ascii"),
        event["source_sequence"],
        event["causal_sequence"],
        event["event_id"],
    )


def _scheduler_event_id(event: dict[str, Any]) -> str:
    fingerprint = _sha(_projection(event, SCHEDULER_EVENT_FINGERPRINT_FIELDS))
    return str(uuid.uuid5(uuid.UUID(event["run_id"]), fingerprint))


def _validate_scheduler_event(
    event: dict[str, Any],
    *,
    start_at: str,
    end_at: str,
    current_key: tuple[datetime, int, bytes, int, int, str] | None = None,
) -> None:
    if event["priority"] != PRIORITIES[event["event_type"]]:
        raise ValueError("scheduler priority mismatch")
    if event["event_id"] != _scheduler_event_id(event):
        raise ValueError("scheduler event identity mismatch")
    key = _scheduler_key(event)
    if not _utc(start_at) <= key[0] <= _utc(end_at):
        raise ValueError("scheduler event outside run bounds")
    if current_key is not None and key <= current_key:
        raise ValueError("causal retrograde scheduler insertion")


def _quantize(value: Decimal, unit: Decimal, rounding: str) -> Decimal:
    mode = {
        "CEILING": ROUND_CEILING,
        "FLOOR": ROUND_FLOOR,
        "HALF_EVEN": ROUND_HALF_EVEN,
    }[rounding]
    return (value / unit).quantize(Decimal("1"), rounding=mode) * unit


def _simulate_fill(
    order: dict[str, Any], market: dict[str, Any], policy: dict[str, Any]
) -> dict[str, str | int] | None:
    if market["scheduler_key"] <= order["accepted_scheduler_key"]:
        raise ValueError("matching fact is not after accepted order cutoff")
    if _utc(market["trade_time"]) <= _utc(order["accepted_at"]):
        raise ValueError("matching fact would create a retroactive fill")
    if market["available_at"] > order["virtual_now"]:
        raise ValueError("matching fact is not available")
    if market["session"] != "OPEN" or market["quality"] != "NORMAL":
        return None
    participation = Decimal(policy["matching"]["max_participation_rate"])
    if not Decimal("0") < participation <= Decimal("1"):
        raise ValueError("participation rate must be in (0,1]")
    available = int(Decimal(market["incremental_volume"]) * participation)
    if available <= 0:
        return None
    if not policy["matching"]["partial_fills"] and available < order["leaves_quantity"]:
        return None
    quantity = min(order["leaves_quantity"], available)
    base = Decimal(market["price"])
    tick = Decimal(policy["slippage"]["tick_size"])
    value = Decimal(policy["slippage"]["value"])
    model = policy["slippage"]["model"]
    slip = Decimal("0")
    if model == "FIXED_BPS":
        slip = base * value / Decimal("10000")
    elif model == "FIXED_TICKS":
        slip = tick * value
    elif model != "NONE" or value != Decimal("0"):
        raise ValueError("invalid NONE slippage model")
    if order["side"] == "BUY":
        price = _quantize(base + slip, tick, "CEILING")
        if order["limit_price"] is not None and price > Decimal(order["limit_price"]):
            return None
    else:
        price = _quantize(base - slip, tick, "FLOOR")
        if order["limit_price"] is not None and price < Decimal(order["limit_price"]):
            return None
    if not Decimal(market["price_band_low"]) <= price <= Decimal(market["price_band_high"]):
        return None
    fees = policy["fees"]
    unit = Decimal(fees["currency_minor_unit"])
    notional = price * quantity
    cumulative_notional = Decimal(order["prior_filled_notional"]) + notional
    cumulative_required_commission = max(
        Decimal(fees["minimum_commission"]),
        cumulative_notional * Decimal(fees["commission_rate"]),
    )
    cumulative_required_commission = _quantize(cumulative_required_commission, unit, "HALF_EVEN")
    commission = cumulative_required_commission - Decimal(order["prior_commission"])
    if commission < 0:
        raise ValueError("prior commission exceeds cumulative required commission")
    transfer = _quantize(notional * Decimal(fees["transfer_fee_rate"]), unit, "HALF_EVEN")
    tax = Decimal("0")
    if order["side"] == "SELL":
        tax = _quantize(notional * Decimal(fees["sell_tax_rate"]), unit, "HALF_EVEN")
    places = max(0, -unit.as_tuple().exponent)

    def render(value: Decimal) -> str:
        return f"{value:.{places}f}"

    return {
        "quantity": quantity,
        "price": render(price),
        "commission": render(commission),
        "transfer_fee": render(transfer),
        "tax": render(tax),
    }


def _allocate_competing_orders(
    orders: list[dict[str, Any]], incremental_volume: int, participation_rate: str
) -> list[tuple[str, int]]:
    budget = int(Decimal(incremental_volume) * Decimal(participation_rate))
    allocations = []
    for order in sorted(
        orders, key=lambda item: (item["accepted_scheduler_key"], item["order_id"])
    ):
        quantity = min(order["leaves_quantity"], budget)
        allocations.append((order["order_id"], quantity))
        budget -= quantity
    return allocations


def _normalize_trace(trace: list[dict[str, Any]]) -> str:
    excluded = {"host_id", "process_id", "connection_id", "wall_duration_us", "telemetry"}
    normalized = [{k: v for k, v in fact.items() if k not in excluded} for fact in trace]
    return _sha(normalized)


def test_contract_bundle_is_registered_and_machine_valid() -> None:
    schema = _json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    semantic = _yaml(SEMANTIC_PATH)
    workflow = _yaml(WORKFLOW_PATH)
    manifest = _yaml(ROOT / "spec/manifest.yaml")
    contract_ids = {entry["id"] for entry in manifest["catalogs"]["contracts"]}
    interface_ids = {entry["id"] for entry in manifest["catalogs"]["interfaces"]}
    workflow_ids = {entry["id"] for entry in manifest["catalogs"]["workflows"]}

    version = tuple(int(part) for part in manifest["specification"]["version"].split("."))
    assert version >= (0, 13, 0)
    assert schema["$id"] == "urn:quantiqmt:internal:backtest-parity:v1"
    assert semantic["contract"]["id"] == "CONTRACT-BACKTEST-PARITY-SEMANTIC-V1"
    assert workflow["workflow"]["id"] == "WF-BACKTEST-RUN"
    assert {"CONTRACT-BACKTEST-PARITY-V1", "CONTRACT-BACKTEST-PARITY-SEMANTIC-V1"} <= (contract_ids)
    assert "PORTS-BACKTEST" in interface_ids
    assert "WF-BACKTEST-RUN" in workflow_ids


def test_schema_accepts_all_frozen_dto_shapes() -> None:
    validator = _validator()
    dtos = _json(FIXTURE_PATH)["dtos"]
    for dto in dtos:
        validator.validate(dto)
    assert {dto["dto_type"] for dto in dtos} == {
        "BACKTEST_RUN_SPEC",
        "HISTORICAL_DATASET_MANIFEST",
        "HISTORICAL_READ_REQUEST",
        "HISTORICAL_READ_RESULT",
        "VIRTUAL_CLOCK_STATE",
        "SCHEDULER_EVENT",
        "SCHEDULER_RESULT",
        "EXECUTION_SIMULATION_POLICY",
        "BACKTEST_RUN_EVIDENCE",
        "PARITY_COMPARISON",
    }


@pytest.mark.parametrize(
    ("dto_type", "mutation"),
    [
        ("BACKTEST_RUN_SPEC", "unsafe_seed"),
        ("EXECUTION_SIMULATION_POLICY", "float_fee"),
        ("HISTORICAL_READ_RESULT", "contradictory_end"),
        ("BACKTEST_RUN_EVIDENCE", "completed_missing_checksum"),
        ("BACKTEST_RUN_EVIDENCE", "rejected_runtime_reason"),
        ("PARITY_COMPARISON", "contradictory_match"),
        ("SCHEDULER_EVENT", "additional_property"),
    ],
)
def test_schema_rejects_unsafe_or_ambiguous_dtos(dto_type: str, mutation: str) -> None:
    dto = deepcopy(_dtos()[dto_type])
    if mutation == "unsafe_seed":
        dto["seed"] = SAFE_INTEGER_MAX + 1
    elif mutation == "float_fee":
        dto["fees"]["commission_rate"] = 0.0003
    elif mutation == "contradictory_end":
        dto["outcome"] = "END"
        dto["reason_code"] = "END_OF_DATA"
        dto["next_cursor"] = None
    elif mutation == "completed_missing_checksum":
        dto["ledger_checksum"] = None
    elif mutation == "rejected_runtime_reason":
        dto["status"] = "REJECTED"
        dto["reason_code"] = "EXECUTION_MODEL_FAILURE"
    elif mutation == "contradictory_match":
        dto["mismatch_count"] = 1
    else:
        dto["unexpected"] = True
    assert not _validator().is_valid(dto)


def test_fixed_manifest_policy_run_and_evidence_vectors() -> None:
    dtos = _dtos()
    manifest = dtos["HISTORICAL_DATASET_MANIFEST"]
    policy = dtos["EXECUTION_SIMULATION_POLICY"]
    run = dtos["BACKTEST_RUN_SPEC"]
    evidence = dtos["BACKTEST_RUN_EVIDENCE"]
    comparison = dtos["PARITY_COMPARISON"]

    assert _sha({k: v for k, v in manifest.items() if k != "content_checksum"}) == (
        "19ba0975c700fcbca607e7a67cafcfe6e763aee6774b87e978fc33d70da9ab8d"
    )
    assert _sha({k: v for k, v in policy.items() if k != "content_checksum"}) == (
        "b96d56382939276e961c163b2cf9678fb13d7dc898ca34b7d7f3ebbdd23f2487"
    )
    assert _sha(_projection(run, RUN_FINGERPRINT_FIELDS)) == (
        "5f19980cb74a65891be02afe2e29ff285564ba33bbb732302f95081568d92461"
    )
    assert str(uuid.uuid5(NAMESPACE, run["input_fingerprint"])) == (
        "8f9c36a7-fdf4-590f-a914-d3109ee76e37"
    )
    assert _scheduler_event_id(dtos["SCHEDULER_EVENT"]) == ("41710a4d-2c4a-5786-bec3-602817da81b2")
    assert _sha(_projection(evidence, EVIDENCE_FIELDS)) == (
        "b92050f7b91c0ae2b5c7493782876485b835b490bd379e56a0bef729c8113bdc"
    )
    assert _sha({k: v for k, v in comparison.items() if k != "comparison_checksum"}) == (
        "5a1d7ef9606472af4dad2525ea6e0b45272e7001e95cd49439c6fc6500075995"
    )
    _validate_manifest(manifest)
    _validate_run_spec(run)


@pytest.mark.parametrize(
    "mutation",
    ["checksum", "sequence_inversion", "event_time_inversion", "availability_inversion"],
)
def test_manifest_semantics_fail_closed(mutation: str) -> None:
    manifest = deepcopy(_dtos()["HISTORICAL_DATASET_MANIFEST"])
    partition = manifest["partitions"][0]
    if mutation == "checksum":
        manifest["content_checksum"] = "0" * 64
    elif mutation == "sequence_inversion":
        partition["first_source_sequence"] = 101
    elif mutation == "event_time_inversion":
        partition["min_event_time"] = "2026-01-05T07:00:01Z"
    else:
        partition["min_available_at"] = "2026-01-05T07:00:01Z"
    with pytest.raises(ValueError):
        _validate_manifest(manifest)


def test_historical_market_releases_only_available_events() -> None:
    dtos = _dtos()
    request = dtos["HISTORICAL_READ_REQUEST"]
    result = dtos["HISTORICAL_READ_RESULT"]
    _validate_history_page(request, result, "2026-01-05T01:30:00.001000Z")

    future = deepcopy(result)
    future["items"][0]["available_at"] = "2026-01-05T01:30:00.002000Z"
    with pytest.raises(ValueError, match="after request availability"):
        _validate_history_page(request, future, "2026-01-05T01:30:00.002000Z")

    future_request = deepcopy(request)
    future_request["available_at_lte"] = "2026-01-05T01:30:00.002000Z"
    with pytest.raises(ValueError, match="future data requested"):
        _validate_history_page(future_request, result, "2026-01-05T01:30:00.001000Z")


def test_historical_wait_bootstraps_future_release_without_exposing_payload() -> None:
    dtos = _dtos()
    request = dtos["HISTORICAL_READ_REQUEST"]
    wait = deepcopy(dtos["HISTORICAL_READ_RESULT"])
    wait.update(
        outcome="WAIT",
        reason_code="NOT_YET_AVAILABLE",
        items=[],
        next_cursor="cursor-before-first-visible-row",
        next_available_at="2026-01-05T01:30:00.002000Z",
    )
    _validator().validate(wait)
    _validate_history_page(request, wait, request["available_at_lte"])
    assert set(wait) == {
        "dto_type",
        "schema_version",
        "request_id",
        "run_id",
        "manifest_checksum",
        "outcome",
        "reason_code",
        "items",
        "next_cursor",
        "next_available_at",
    }

    wait["next_available_at"] = request["available_at_lte"]
    with pytest.raises(ValueError, match="does not advance"):
        _validate_history_page(request, wait, request["available_at_lte"])


def test_historical_event_contract_identity_and_order_are_bound() -> None:
    dtos = _dtos()
    request = dtos["HISTORICAL_READ_REQUEST"]
    result = deepcopy(dtos["HISTORICAL_READ_RESULT"])
    result["items"][0]["contract_id"] = "CONTRACT-MARKET-BAR-CLOSED-V1"
    with pytest.raises(ValueError, match="message and contract"):
        _validate_history_page(request, result, request["available_at_lte"])

    result = deepcopy(dtos["HISTORICAL_READ_RESULT"])
    duplicate = deepcopy(result["items"][0])
    result["items"].append(duplicate)
    with pytest.raises(ValueError, match="canonically ordered"):
        _validate_history_page(request, result, request["available_at_lte"])


def test_virtual_clock_and_scheduler_use_one_canonical_order() -> None:
    dtos = _dtos()
    clock = dtos["VIRTUAL_CLOCK_STATE"]
    event = dtos["SCHEDULER_EVENT"]
    elapsed = int((_utc(clock["current_at"]) - _utc(clock["start_at"])).total_seconds() * 1_000_000)
    assert clock["elapsed_us"] == elapsed
    _validate_scheduler_event(event, start_at=clock["start_at"], end_at=clock["end_at"])

    same_time = []
    for event_type, priority in reversed(PRIORITIES.items()):
        candidate = deepcopy(event)
        candidate["event_type"] = event_type
        candidate["priority"] = priority
        candidate["event_id"] = _scheduler_event_id(candidate)
        same_time.append(candidate)
    assert [entry["event_type"] for entry in sorted(same_time, key=_scheduler_key)] == list(
        PRIORITIES
    )


@pytest.mark.parametrize("mutation", ["priority", "before_start", "retrograde", "identity_drift"])
def test_scheduler_rejects_priority_time_and_causality_conflicts(mutation: str) -> None:
    dtos = _dtos()
    clock = dtos["VIRTUAL_CLOCK_STATE"]
    event = deepcopy(dtos["SCHEDULER_EVENT"])
    current_key = None
    if mutation == "priority":
        event["priority"] = 60
    elif mutation == "before_start":
        event["dispatch_at"] = "2026-01-05T01:29:59Z"
        event["event_id"] = _scheduler_event_id(event)
    elif mutation == "retrograde":
        current_key = _scheduler_key(event)
    else:
        event["payload_checksum"] = "0" * 64
    with pytest.raises(ValueError):
        _validate_scheduler_event(
            event,
            start_at=clock["start_at"],
            end_at=clock["end_at"],
            current_key=current_key,
        )


def test_scheduler_cancel_outcomes_are_exhaustive_and_unambiguous() -> None:
    result = deepcopy(_dtos()["SCHEDULER_RESULT"])
    for outcome, reason in (
        ("CANCELED", "CANCELED"),
        ("IDEMPOTENT_REPLAY", "ALREADY_CANCELED"),
        ("REJECTED", "EVENT_NOT_FOUND"),
        ("REJECTED", "EVENT_ALREADY_DISPATCHED"),
    ):
        result.update(outcome=outcome, reason_code=reason)
        _validator().validate(result)

    result.update(outcome="CANCELED", reason_code="EVENT_NOT_FOUND")
    assert not _validator().is_valid(result)


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        (
            "BUY",
            {
                "quantity": 250,
                "price": "10.01",
                "commission": "5.00",
                "transfer_fee": "0.03",
                "tax": "0.00",
            },
        ),
        (
            "SELL",
            {
                "quantity": 250,
                "price": "9.99",
                "commission": "5.00",
                "transfer_fee": "0.02",
                "tax": "2.50",
            },
        ),
    ],
)
def test_execution_price_liquidity_and_fee_formulas_are_decimal_only(
    side: str, expected: dict[str, str | int]
) -> None:
    policy = _dtos()["EXECUTION_SIMULATION_POLICY"]
    order = {
        "side": side,
        "leaves_quantity": 300,
        "limit_price": "10.50" if side == "BUY" else "9.50",
        "accepted_scheduler_key": "0001",
        "accepted_at": "2026-01-05T01:30:00Z",
        "prior_filled_notional": "0",
        "prior_commission": "0",
        "virtual_now": "2026-01-05T01:30:01Z",
    }
    market = {
        "scheduler_key": "0002",
        "available_at": "2026-01-05T01:30:00.001000Z",
        "trade_time": "2026-01-05T01:30:00.000500Z",
        "session": "OPEN",
        "quality": "NORMAL",
        "price": "10",
        "incremental_volume": 1000,
        "price_band_low": "9",
        "price_band_high": "11",
    }
    assert _simulate_fill(order, market, policy) == expected


@pytest.mark.parametrize(
    ("mutation", "raises"),
    [
        ("future_scheduler_key", True),
        ("future_availability", True),
        ("non_normal_quality", False),
        ("closed_session", False),
        ("limit_not_crossed", False),
        ("outside_price_band", False),
        ("partial_disabled", False),
        ("participation_above_one", True),
    ],
)
def test_execution_never_uses_future_untradeable_or_unbounded_liquidity(
    mutation: str, raises: bool
) -> None:
    policy = deepcopy(_dtos()["EXECUTION_SIMULATION_POLICY"])
    order = {
        "side": "BUY",
        "leaves_quantity": 300,
        "limit_price": "10.50",
        "accepted_scheduler_key": "0001",
        "accepted_at": "2026-01-05T01:30:00Z",
        "prior_filled_notional": "0",
        "prior_commission": "0",
        "virtual_now": "2026-01-05T01:30:01Z",
    }
    market = {
        "scheduler_key": "0002",
        "available_at": "2026-01-05T01:30:00.001000Z",
        "trade_time": "2026-01-05T01:30:00.000500Z",
        "session": "OPEN",
        "quality": "NORMAL",
        "price": "10",
        "incremental_volume": 1000,
        "price_band_low": "9",
        "price_band_high": "11",
    }
    if mutation == "future_scheduler_key":
        market["scheduler_key"] = "0000"
    elif mutation == "future_availability":
        market["available_at"] = "2026-01-05T01:30:02Z"
    elif mutation == "non_normal_quality":
        market["quality"] = "GAP"
    elif mutation == "closed_session":
        market["session"] = "CLOSED"
    elif mutation == "limit_not_crossed":
        order["limit_price"] = "10.00"
    elif mutation == "outside_price_band":
        market["price_band_high"] = "10.00"
    elif mutation == "partial_disabled":
        policy["matching"]["partial_fills"] = False
        market["incremental_volume"] = 100
    else:
        policy["matching"]["max_participation_rate"] = "1.01"
    if raises:
        with pytest.raises(ValueError):
            _simulate_fill(order, market, policy)
    else:
        assert _simulate_fill(order, market, policy) is None


def test_none_slippage_requires_zero_and_never_clamps() -> None:
    policy = deepcopy(_dtos()["EXECUTION_SIMULATION_POLICY"])
    policy["slippage"]["model"] = "NONE"
    order = {
        "side": "BUY",
        "leaves_quantity": 1,
        "limit_price": "10",
        "accepted_scheduler_key": "0001",
        "accepted_at": "2026-01-05T01:30:00Z",
        "prior_filled_notional": "0",
        "prior_commission": "0",
        "virtual_now": "2026-01-05T01:30:01Z",
    }
    market = {
        "scheduler_key": "0002",
        "available_at": "2026-01-05T01:30:00.001000Z",
        "trade_time": "2026-01-05T01:30:00.000500Z",
        "session": "OPEN",
        "quality": "NORMAL",
        "price": "10",
        "incremental_volume": 100,
        "price_band_low": "9",
        "price_band_high": "11",
    }
    with pytest.raises(ValueError, match="invalid NONE"):
        _simulate_fill(order, market, policy)
    policy["slippage"]["value"] = "0"
    assert _simulate_fill(order, market, policy) is not None


def test_partial_fills_charge_minimum_commission_only_once_per_order() -> None:
    policy = deepcopy(_dtos()["EXECUTION_SIMULATION_POLICY"])
    policy["slippage"]["model"] = "NONE"
    policy["slippage"]["value"] = "0"
    order = {
        "side": "BUY",
        "leaves_quantity": 100,
        "limit_price": "10.50",
        "accepted_scheduler_key": "0001",
        "accepted_at": "2026-01-05T01:30:00Z",
        "prior_filled_notional": "1000.00",
        "prior_commission": "5.00",
        "virtual_now": "2026-01-05T01:30:02Z",
    }
    market = {
        "scheduler_key": "0003",
        "available_at": "2026-01-05T01:30:01.001000Z",
        "trade_time": "2026-01-05T01:30:01Z",
        "session": "OPEN",
        "quality": "NORMAL",
        "price": "10",
        "incremental_volume": 400,
        "price_band_low": "9",
        "price_band_high": "11",
    }

    fill = _simulate_fill(order, market, policy)

    assert fill is not None
    assert fill["commission"] == "0.00"


def test_competing_orders_consume_released_volume_once_in_canonical_order() -> None:
    orders = [
        {"order_id": "order-b", "accepted_scheduler_key": "0001", "leaves_quantity": 80},
        {"order_id": "order-a", "accepted_scheduler_key": "0001", "leaves_quantity": 80},
        {"order_id": "order-c", "accepted_scheduler_key": "0002", "leaves_quantity": 80},
    ]
    expected = [("order-a", 80), ("order-b", 20), ("order-c", 0)]
    assert _allocate_competing_orders(orders, 400, "0.25") == expected
    assert _allocate_competing_orders(list(reversed(orders)), 400, "0.25") == expected
    assert sum(quantity for _, quantity in expected) == 100


def test_next_bar_open_cannot_retroactively_fill_an_already_open_bar() -> None:
    policy = deepcopy(_dtos()["EXECUTION_SIMULATION_POLICY"])
    order = {
        "side": "BUY",
        "leaves_quantity": 100,
        "limit_price": "10.50",
        "accepted_scheduler_key": "0001",
        "accepted_at": "2026-01-05T01:31:00Z",
        "prior_filled_notional": "0",
        "prior_commission": "0",
        "virtual_now": "2026-01-05T01:32:00Z",
    }
    finalized_bar = {
        "scheduler_key": "0002",
        "available_at": "2026-01-05T01:31:59.001000Z",
        "trade_time": "2026-01-05T01:30:00Z",
        "session": "OPEN",
        "quality": "NORMAL",
        "price": "10",
        "incremental_volume": 1000,
        "price_band_low": "9",
        "price_band_high": "11",
    }

    with pytest.raises(ValueError, match="retroactive fill"):
        _simulate_fill(order, finalized_bar, policy)


def test_parity_normalization_excludes_only_adapter_telemetry() -> None:
    live = [
        {
            "message_id": "intent-1",
            "outcome": "RISK_PASSED",
            "price": "10.01",
            "state_version": 3,
            "host_id": "live-a",
            "wall_duration_us": 100,
        }
    ]
    backtest = deepcopy(live)
    backtest[0]["host_id"] = "sim-b"
    backtest[0]["wall_duration_us"] = 1
    assert _normalize_trace(live) == _normalize_trace(backtest)

    backtest[0]["price"] = "10.02"
    assert _normalize_trace(live) != _normalize_trace(backtest)


@pytest.mark.parametrize(
    ("mutation", "valid_match"),
    [
        ("none", True),
        ("normalized_checksum", False),
        ("mismatch_count", False),
        ("future_read_count", False),
    ],
)
def test_match_requires_equal_normalized_trace_and_zero_violations(
    mutation: str, valid_match: bool
) -> None:
    comparison = deepcopy(_dtos()["PARITY_COMPARISON"])
    if mutation == "normalized_checksum":
        comparison["normalized_backtest_checksum"] = "0" * 64
    elif mutation == "mismatch_count":
        comparison["mismatch_count"] = 1
    elif mutation == "future_read_count":
        comparison["future_read_count"] = 1
    actual = (
        comparison["normalized_live_checksum"] == comparison["normalized_backtest_checksum"]
        and comparison["mismatch_count"] == 0
        and comparison["future_read_count"] == 0
    )
    assert actual is valid_match


def test_ports_and_workflow_preserve_the_only_order_chain() -> None:
    ports = PORT_PATH.read_text(encoding="utf-8")
    workflow = _yaml(WORKFLOW_PATH)["workflow"]
    text = yaml.safe_dump(workflow, sort_keys=False)
    assert "OrderIntent_to_OMS_registration_to_Risk_to_OMS_transition_to_Execution" in text
    assert "simulator_mutates_OMS" in text
    assert "ExecutionSimulatorPort(ExecutionGateway" in ports
    assert "same Domain, Application, Strategy" in ports
    assert "never production approval" in ports


def test_semantic_contract_freezes_no_lookahead_determinism_and_parity_levels() -> None:
    semantic = _yaml(SEMANTIC_PATH)
    assert semantic["canonicalization"]["algorithm"] == "RFC8785_JCS"
    assert semantic["no_lookahead"]["release_guard"] == (
        "historical_event.available_at_lte_virtual_clock.current_at"
    )
    assert semantic["scheduler"]["canonical_key"] == [
        "dispatch_at",
        "priority",
        "source_id_ASCII",
        "source_sequence",
        "causal_sequence",
        "event_id",
    ]
    assert semantic["execution_simulation"]["oms_state_mutation"] == "forbidden"
    assert semantic["historical_market_port"]["wait"]["only_allowed_use"] == (
        "schedule_HISTORICAL_RELEASE_wakeup_at_next_available_at"
    )
    assert semantic["execution_simulation"]["matching"]["competing_order_priority"] == [
        "accepted_scheduler_key",
        "order_id_ASCII",
    ]
    assert semantic["execution_simulation"]["scenario_profile"][
        "forbidden_scenario_fill_actions"
    ] == ["PARTIAL_FILL", "FULL_FILL", "CANCEL_RACE"]
    assert (
        semantic["reproducibility"]["run_end_boundary"][
            "silent_truncation_or_COMPLETED_with_pending_order_timer_or_report"
        ]
        == "forbidden"
    )
    assert set(semantic["parity"]["scopes"]) == {"SHARED_LOGIC", "RECORDED_TRACE_REPLAY"}
    assert semantic["parity"]["backtest_result_is_production_approval"] is False


def test_task_010_is_only_a_reference_strategy_handoff() -> None:
    task = (ROOT / "tasks/backlog/TASK-010-reference-buy-hold.md").read_text(encoding="utf-8")
    assert "CONTRACT-BACKTEST-PARITY-V1" in task
    assert "PORTS-BACKTEST" in task
    assert "WF-BACKTEST-RUN" in task
    assert "不得自行定义" in task
    assert "收益承诺" in task


def test_nfrs_keep_backtest_resources_bounded_and_nondeterminism_out() -> None:
    performance = _yaml(ROOT / "spec/nfr/performance.yaml")["nfr"]
    reliability = _yaml(ROOT / "spec/nfr/reliability.yaml")["nfr"]
    assert performance["backtest"]["scheduler_queue_capacity"] == "finite_versioned_policy"
    assert performance["backtest"]["throughput_measurement_is_business_input"] is False
    assert reliability["backtest_live_parity"]["future_data"] == "forbidden"
    assert reliability["backtest_live_parity"]["direct_state_shortcut"] == "forbidden"
    assert reliability["backtest_live_parity"]["host_watchdog"] == (
        "termination_only_never_completed_business_outcome"
    )


def test_same_input_reproduces_identical_identity_and_scheduler_order() -> None:
    run_a = deepcopy(_dtos()["BACKTEST_RUN_SPEC"])
    run_b = deepcopy(run_a)
    _validate_run_spec(run_a)
    _validate_run_spec(run_b)
    assert run_a["run_id"] == run_b["run_id"]
    assert run_a["input_fingerprint"] == run_b["input_fingerprint"]

    event = _dtos()["SCHEDULER_EVENT"]
    events_a = [deepcopy(event) for _ in range(3)]
    for index, item in enumerate(events_a, start=1):
        item["source_sequence"] = index
        item["event_id"] = _scheduler_event_id(item)
    events_b = list(reversed(deepcopy(events_a)))
    assert [item["event_id"] for item in sorted(events_a, key=_scheduler_key)] == [
        item["event_id"] for item in sorted(events_b, key=_scheduler_key)
    ]


def test_changed_input_cannot_reuse_run_identity() -> None:
    run = deepcopy(_dtos()["BACKTEST_RUN_SPEC"])
    run["seed"] = 8
    with pytest.raises(ValueError, match="input fingerprint"):
        _validate_run_spec(run)
