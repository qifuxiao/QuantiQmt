from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "spec" / "contracts"
SCHEMA_PATH = CONTRACTS / "strategy" / "target-resolver.v1.schema.json"
SEMANTIC_PATH = CONTRACTS / "strategy" / "target-resolver.semantic-validation.v1.yaml"
WORKFLOW_PATH = ROOT / "spec" / "workflows" / "target-resolution.yaml"
STORAGE_PATH = ROOT / "spec" / "storage" / "target-resolution.yaml"
TARGET_PATH = CONTRACTS / "commands" / "strategy.submit_target.v1.schema.json"
INTENT_PATH = CONTRACTS / "commands" / "strategy.submit_order_intent.v1.schema.json"
NAMESPACE = uuid.UUID("7a6bdb48-22b7-5f65-bb55-63e4a8ff6325")


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def _jcs(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("float is forbidden")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_jcs(key)}:{_jcs(value[key])}" for key in keys) + "}"
    raise TypeError(type(value).__name__)


def _hash(value: object) -> str:
    return hashlib.sha256(_jcs(value).encode("utf-8")).hexdigest()


def _checksum(value: dict[str, Any], field: str) -> str:
    projection = deepcopy(value)
    projection.pop(field)
    return _hash(projection)


def _input_hash(request: dict[str, Any]) -> str:
    projection = deepcopy(request)
    projection.pop("input_fingerprint")
    projection.pop("resolution_trigger")
    return _hash(projection)


def _trigger_hash(trigger: dict[str, Any]) -> str:
    return _checksum(trigger, "trigger_fingerprint")


def _registry() -> Registry:
    schemas = [_json(SCHEMA_PATH), _json(TARGET_PATH), _json(INTENT_PATH)]
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        _json(SCHEMA_PATH), registry=_registry(), format_checker=FormatChecker()
    )


def _source(source: str, version: str) -> dict[str, Any]:
    return {
        "source": source,
        "snapshot_version": version,
        "checksum": _hash({"source": source, "version": version}),
        "as_of": "2026-08-24T01:04:00Z",
        "quality": "FRESH",
        "completeness": "COMPLETE",
    }


def _request(*, target_type: str = "POSITION") -> dict[str, Any]:
    target: dict[str, Any] = {
        "target_id": "target-0000000000000001",
        "target_type": target_type,
        "strategy_id": "strategy-1",
        "strategy_version": "v1",
        "scope_id": "sleeve:strategy-1:acct-1",
        "instrument_id": "600000.XSHG",
        "decision_id": "decision-00000000000001",
        "input_event_id": "market-event-0000000001",
        "effective_at": "2026-08-24T01:00:00Z",
        "valid_until": "2026-08-24T02:00:00Z",
        "reason_code": "REBALANCE",
    }
    if target_type == "POSITION":
        target["target_quantity"] = 500
    else:
        target["target_weight"] = "0.50"

    mandate: dict[str, Any] = {
        "dto_type": "STRATEGY_MANDATE",
        "schema_version": 1,
        "mandate_id": "10000000-0000-5000-8000-000000000001",
        "mandate_version": "mandate-v1",
        "mandate_checksum": "0" * 64,
        "strategy_id": "strategy-1",
        "strategy_version": "v1",
        "scope_type": "STRATEGY_SLEEVE",
        "scope_id": "sleeve:strategy-1:acct-1",
        "account_id": "acct-1",
        "portfolio_id": "20000000-0000-5000-8000-000000000001",
        "allowed_target_types": ["POSITION", "WEIGHT"],
        "allowed_instrument_ids": ["600000.XSHG"],
        "long_only": True,
        "max_target_weight": "0.80",
        "max_position_quantity": 10000,
        "cash_buffer_ratio": "0.10",
        "cash_buffer_absolute": "5000.00",
        "effective_from": "2026-08-24T00:00:00Z",
        "effective_until": "2026-08-25T00:00:00Z",
    }
    mandate["mandate_checksum"] = _checksum(mandate, "mandate_checksum")

    instrument: dict[str, Any] = {
        "dto_type": "INSTRUMENT_SPEC",
        "schema_version": 1,
        "instrument_id": "600000.XSHG",
        "instrument_spec_version": "instrument-v1",
        "instrument_spec_checksum": "0" * 64,
        "currency": "CNY",
        "quantity_scale": 0,
        "lot_size": 100,
        "min_order_quantity": 100,
        "tick_size": "0.01",
        "currency_minor_unit": "0.01",
        "price_band_source": "MARKET_SNAPSHOT_LIMITS",
        "quantity_rounding": "TOWARD_ZERO",
        "buy_price_rounding": "FLOOR",
        "sell_price_rounding": "CEILING",
        "sell_to_zero_odd_lot_allowed": True,
        "effective_from": "2026-08-24T00:00:00Z",
        "effective_until": "2026-08-25T00:00:00Z",
    }
    instrument["instrument_spec_checksum"] = _checksum(instrument, "instrument_spec_checksum")

    policy: dict[str, Any] = {
        "dto_type": "TARGET_RESOLUTION_POLICY",
        "schema_version": 1,
        "resolver_policy_version": "TARGET_RESOLVER_V1",
        "policy_checksum": "0" * 64,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "position_effect": "AUTO",
        "price_reference_source": "MARKET_REFERENCE_PRICE",
        "quantity_deadband": 0,
        "notional_deadband": "0",
        "max_snapshot_age_ms": 300000,
    }
    policy["policy_checksum"] = _checksum(policy, "policy_checksum")

    active_order = {
        "order_id": "30000000-0000-5000-8000-000000000001",
        "intent_id": "40000000-0000-5000-8000-000000000001",
        "order_version": 3,
        "strategy_id": "strategy-1",
        "strategy_version": "v1",
        "scope_id": "sleeve:strategy-1:acct-1",
        "account_id": "acct-1",
        "instrument_id": "600000.XSHG",
        "state": "SUBMIT_UNKNOWN",
        "side": "BUY",
        "original_quantity": 100,
        "cumulative_quantity": 0,
        "position_applied_cumulative_quantity": 0,
        "leaves_quantity": 100,
        "expected_delta": 100,
        "effect_basis": "OMS_LEAVES_CONSERVATIVE_V1",
    }
    snapshot = {
        "dto_type": "TARGET_RESOLUTION_SNAPSHOT",
        "schema_version": 1,
        "snapshot_id": "50000000-0000-5000-8000-000000000001",
        "account_id": "acct-1",
        "portfolio_id": "20000000-0000-5000-8000-000000000001",
        "scope_id": "sleeve:strategy-1:acct-1",
        "instrument_id": "600000.XSHG",
        "currency": "CNY",
        "portfolio_source": _source("PortfolioProjection", "portfolio-v7"),
        "account_source": _source("AccountProjection", "account-v9"),
        "market_source": _source("MarketSnapshot", "market-v11"),
        "strategy_sleeve_source": _source("StrategySleeveProjection", "sleeve-v5"),
        "active_order_source": _source("OMSActiveOrderReadModel", "orders-v13"),
        "total_equity": "100000.00",
        "projected_available_cash": "100000.00",
        "current_position": {"quantity": 100, "available_quantity": 100},
        "strategy_sleeve": {"quantity": 100, "available_quantity": 100},
        "price_reference": {
            "source": "MARKET_REFERENCE_PRICE",
            "price": "10.01",
            "currency": "CNY",
            "lower_price_limit": "8.00",
            "upper_price_limit": "12.00",
            "observed_at": "2026-08-24T01:04:00Z",
        },
        "portfolio_trade_watermark": 21,
        "strategy_sleeve_trade_watermark": 21,
        "active_order_trade_watermark": 21,
        "account_reserved_orders_snapshot_version": "orders-v13",
        "active_order_effects": [active_order],
        "captured_at": "2026-08-24T01:04:01Z",
    }
    target_fingerprint = _hash(target)
    trigger = {
        "trigger_message_id": "target-message-00000001",
        "trigger_type": "TARGET_ACCEPTED",
        "source_contract_id": "CONTRACT-STRATEGY-TARGET-V1",
        "source_state_version": None,
        "account_id": "acct-1",
        "scope_id": "sleeve:strategy-1:acct-1",
        "instrument_id": "600000.XSHG",
        "source_payload_fingerprint": target_fingerprint,
        "trigger_fingerprint": "0" * 64,
        "occurred_at": "2026-08-24T01:00:00Z",
        "accepted_at": "2026-08-24T01:00:01Z",
    }
    trigger["trigger_fingerprint"] = _trigger_hash(trigger)
    request: dict[str, Any] = {
        "dto_type": "TARGET_RESOLUTION_REQUEST",
        "schema_version": 1,
        "accepted_target": {
            "message_id": "target-message-00000001",
            "correlation_id": "strategy-correlation-0001",
            "accepted_at": "2026-08-24T01:00:01Z",
            "generation": 3,
            "payload_fingerprint": target_fingerprint,
        },
        "resolution_trigger": trigger,
        "target": target,
        "mandate": mandate,
        "instrument_spec": instrument,
        "snapshot": snapshot,
        "policy": policy,
        "resolution_time": "2026-08-24T01:04:01Z",
        "target_fingerprint": target_fingerprint,
        "input_fingerprint": "0" * 64,
    }
    request["input_fingerprint"] = _input_hash(request)
    return request


def _null_calculation(stage: str = "INPUT_GUARD") -> dict[str, Any]:
    return {
        "decision_stage": stage,
        "target_weight": None,
        "desired_quantity": None,
        "sleeve_quantity": None,
        "active_order_expected_delta": None,
        "effective_quantity": None,
        "unadjusted_delta": None,
        "residual_delta": None,
        "deadband_notional": None,
        "rounded_quantity": None,
        "side": None,
        "reference_price": None,
        "limit_price": None,
        "estimated_notional": None,
        "projected_available_cash": None,
        "required_cash_buffer": None,
        "available_sell_quantity": None,
    }


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decimal_text(value: Decimal, quantum: Decimal | None = None) -> str:
    if quantum is not None:
        places = max(0, -quantum.as_tuple().exponent)
        return f"{value:.{places}f}"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _trigger_is_valid(request: dict[str, Any]) -> bool:
    trigger = request["resolution_trigger"]
    target = request["target"]
    mandate = request["mandate"]
    now = _utc(request["resolution_time"])
    expected_contracts = {
        "TARGET_ACCEPTED": {"CONTRACT-STRATEGY-TARGET-V1"},
        "POSITION_CHANGED": {"CONTRACT-PORTFOLIO-POSITION-CHANGED-V1"},
        "ORDER_CHANGED": {"CONTRACT-ORDER-REGISTERED-V1", "CONTRACT-ORDER-STATUS-V1"},
        "ACCOUNT_CHANGED": {"CONTRACT-TARGET-RESOLVER-V1#ACCOUNT-SNAPSHOT"},
        "MARKET_CHANGED": {"CONTRACT-MARKET-DATA-V1"},
        "SCHEDULED_REEVALUATION": {"CONTRACT-TARGET-RESOLVER-V1#SCHEDULE"},
    }
    if (
        trigger["source_contract_id"] not in expected_contracts[trigger["trigger_type"]]
        or _utc(request["accepted_target"]["accepted_at"]) > _utc(trigger["accepted_at"])
        or _utc(trigger["occurred_at"]) > _utc(trigger["accepted_at"])
        or _utc(trigger["accepted_at"]) > now
        or trigger["account_id"] != mandate["account_id"]
        or trigger["scope_id"] != target["scope_id"]
        or trigger["instrument_id"] != target["instrument_id"]
    ):
        return False
    if trigger["trigger_type"] in {"TARGET_ACCEPTED", "SCHEDULED_REEVALUATION"}:
        if trigger["source_state_version"] is not None:
            return False
    elif trigger["source_state_version"] is None:
        return False
    return trigger["trigger_type"] != "TARGET_ACCEPTED" or (
        trigger["trigger_message_id"] == request["accepted_target"]["message_id"]
        and trigger["source_payload_fingerprint"] == request["target_fingerprint"]
        and trigger["accepted_at"] == request["accepted_target"]["accepted_at"]
    )


def _trigger_source_is_included(request: dict[str, Any]) -> bool:
    trigger = request["resolution_trigger"]
    snapshot = request["snapshot"]
    source_field = {
        "POSITION_CHANGED": "portfolio_source",
        "ORDER_CHANGED": "active_order_source",
        "ACCOUNT_CHANGED": "account_source",
        "MARKET_CHANGED": "market_source",
    }.get(trigger["trigger_type"])
    if source_field is None:
        return True
    return trigger["source_state_version"] == snapshot[source_field]["snapshot_version"]


def _refresh_request(request: dict[str, Any]) -> None:
    request["mandate"]["mandate_checksum"] = _checksum(request["mandate"], "mandate_checksum")
    request["instrument_spec"]["instrument_spec_checksum"] = _checksum(
        request["instrument_spec"], "instrument_spec_checksum"
    )
    request["policy"]["policy_checksum"] = _checksum(request["policy"], "policy_checksum")
    request["target_fingerprint"] = _hash(request["target"])
    request["accepted_target"]["payload_fingerprint"] = request["target_fingerprint"]
    if request["resolution_trigger"]["trigger_type"] == "TARGET_ACCEPTED":
        request["resolution_trigger"]["source_payload_fingerprint"] = request["target_fingerprint"]
    request["resolution_trigger"]["trigger_fingerprint"] = _trigger_hash(
        request["resolution_trigger"]
    )
    request["input_fingerprint"] = _input_hash(request)


def _set_trigger(
    request: dict[str, Any],
    *,
    message_id: str,
    trigger_type: str,
    source_contract_id: str,
    source_state_version: str | None,
    source_payload: object,
    occurred_at: str,
    accepted_at: str,
) -> None:
    trigger = request["resolution_trigger"]
    trigger.update(
        {
            "trigger_message_id": message_id,
            "trigger_type": trigger_type,
            "source_contract_id": source_contract_id,
            "source_state_version": source_state_version,
            "source_payload_fingerprint": _hash(source_payload),
            "occurred_at": occurred_at,
            "accepted_at": accepted_at,
        }
    )
    _refresh_request(request)


def _result(
    request: dict[str, Any],
    outcome: str,
    reason: str,
    error: str | None,
    calculation: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "dto_type": "TARGET_RESOLUTION_RESULT",
        "schema_version": 1,
        "resolution_id": str(uuid.uuid5(NAMESPACE, str(request["input_fingerprint"]))),
        "target_id": request["target"]["target_id"],
        "target_fingerprint": request["target_fingerprint"],
        "input_fingerprint": request["input_fingerprint"],
        "outcome": outcome,
        "reason_code": reason,
        "error_code": error,
        "order_intent": intent,
        "intent_envelope": envelope,
        "calculation": calculation,
        "resolved_at": request["resolution_time"],
    }


def _reject(
    request: dict[str, Any], reason: str, error: str, calculation: dict[str, Any]
) -> dict[str, Any]:
    return _result(request, "REJECTED", reason, error, calculation)


def _resolve(request: dict[str, Any]) -> dict[str, Any]:
    _validator().validate(request)
    if request["target_fingerprint"] != _hash(request["target"]):
        raise ValueError("target fingerprint mismatch")
    if request["accepted_target"]["payload_fingerprint"] != request["target_fingerprint"]:
        raise ValueError("accepted target fingerprint mismatch")
    if request["resolution_trigger"]["trigger_fingerprint"] != _trigger_hash(
        request["resolution_trigger"]
    ):
        raise ValueError("resolution trigger fingerprint mismatch")
    for value, field in (
        (request["mandate"], "mandate_checksum"),
        (request["instrument_spec"], "instrument_spec_checksum"),
        (request["policy"], "policy_checksum"),
    ):
        if value[field] != _checksum(value, field):
            raise ValueError(f"{field} mismatch")
    if request["input_fingerprint"] != _input_hash(request):
        raise ValueError("input fingerprint mismatch")

    target = request["target"]
    mandate = request["mandate"]
    spec = request["instrument_spec"]
    snapshot = request["snapshot"]
    policy = request["policy"]
    now = _utc(request["resolution_time"])
    calculation = _null_calculation()

    if not _trigger_is_valid(request):
        raise ValueError("resolution trigger must be validated before pure resolution")
    if not _trigger_source_is_included(request):
        raise ValueError("trigger source must be included before pure resolution")
    if request["resolution_time"] != snapshot["captured_at"]:
        return _reject(request, "SNAPSHOT_IDENTITY_MISMATCH", "QQ-STRATEGY-3003", calculation)

    if now < _utc(target["effective_at"]):
        return _reject(request, "TARGET_NOT_YET_EFFECTIVE", "QQ-STRATEGY-3001", calculation)
    if now >= _utc(target["valid_until"]):
        return _reject(request, "TARGET_EXPIRED", "QQ-STRATEGY-3001", calculation)
    if not (_utc(mandate["effective_from"]) <= now < _utc(mandate["effective_until"])):
        return _reject(request, "MANDATE_NOT_EFFECTIVE", "QQ-STRATEGY-3001", calculation)
    if not (_utc(spec["effective_from"]) <= now < _utc(spec["effective_until"])):
        return _reject(request, "INSTRUMENT_SPEC_NOT_EFFECTIVE", "QQ-STRATEGY-3001", calculation)
    if (target["strategy_id"], target["strategy_version"]) != (
        mandate["strategy_id"],
        mandate["strategy_version"],
    ):
        return _reject(request, "TARGET_STRATEGY_MISMATCH", "QQ-STRATEGY-3001", calculation)
    if target["scope_id"] != mandate["scope_id"] or target["scope_id"] != snapshot["scope_id"]:
        return _reject(request, "TARGET_SCOPE_UNAUTHORIZED", "QQ-STRATEGY-3001", calculation)
    if target["target_type"] not in mandate["allowed_target_types"]:
        return _reject(request, "TARGET_TYPE_UNAUTHORIZED", "QQ-STRATEGY-3001", calculation)
    if (
        target["target_type"] == "WEIGHT"
        and (target.get("target_weight") is None or target.get("target_quantity") is not None)
    ) or (
        target["target_type"] == "POSITION"
        and (target.get("target_quantity") is None or target.get("target_weight") is not None)
    ):
        return _reject(request, "TARGET_SHAPE_INVALID", "QQ-STRATEGY-3001", calculation)
    if mandate["allowed_instrument_ids"] != sorted(mandate["allowed_instrument_ids"]):
        return _reject(request, "INSTRUMENT_UNAUTHORIZED", "QQ-STRATEGY-3001", calculation)
    if (
        target["instrument_id"] not in mandate["allowed_instrument_ids"]
        or target["instrument_id"] != spec["instrument_id"]
        or target["instrument_id"] != snapshot["instrument_id"]
    ):
        return _reject(request, "INSTRUMENT_UNAUTHORIZED", "QQ-STRATEGY-3001", calculation)
    if (
        mandate["account_id"] != snapshot["account_id"]
        or mandate["portfolio_id"] != snapshot["portfolio_id"]
        or spec["currency"] != snapshot["currency"]
        or spec["currency"] != snapshot["price_reference"]["currency"]
    ):
        return _reject(request, "SNAPSHOT_IDENTITY_MISMATCH", "QQ-STRATEGY-3003", calculation)

    if not (
        snapshot["portfolio_trade_watermark"]
        == snapshot["strategy_sleeve_trade_watermark"]
        == snapshot["active_order_trade_watermark"]
    ) or (
        snapshot["account_reserved_orders_snapshot_version"]
        != snapshot["active_order_source"]["snapshot_version"]
    ):
        return _reject(request, "SNAPSHOT_IDENTITY_MISMATCH", "QQ-STRATEGY-3003", calculation)

    max_age_ms = int(policy["max_snapshot_age_ms"])
    for source in (
        snapshot["portfolio_source"],
        snapshot["account_source"],
        snapshot["market_source"],
        snapshot["strategy_sleeve_source"],
        snapshot["active_order_source"],
    ):
        if source["quality"] != "FRESH" or source["completeness"] != "COMPLETE":
            return _reject(request, "SNAPSHOT_NOT_FRESH", "QQ-STRATEGY-3003", calculation)
        age_ms = int((now - _utc(source["as_of"])).total_seconds() * 1000)
        if age_ms < 0 or age_ms > max_age_ms:
            return _reject(request, "SNAPSHOT_TOO_OLD", "QQ-STRATEGY-3003", calculation)

    current = snapshot["current_position"]
    sleeve = snapshot["strategy_sleeve"]
    if (
        current["available_quantity"] > current["quantity"]
        or sleeve["quantity"] > current["quantity"]
        or sleeve["available_quantity"] > sleeve["quantity"]
        or sleeve["available_quantity"] > current["available_quantity"]
    ):
        return _reject(request, "SNAPSHOT_IDENTITY_MISMATCH", "QQ-STRATEGY-3003", calculation)

    price = Decimal(snapshot["price_reference"]["price"])
    lower = Decimal(snapshot["price_reference"]["lower_price_limit"])
    upper = Decimal(snapshot["price_reference"]["upper_price_limit"])
    if not (Decimal(0) < lower <= price <= upper):
        return _reject(request, "PRICE_REFERENCE_INVALID", "QQ-STRATEGY-3001", calculation)

    if target["target_type"] == "POSITION":
        desired = int(target["target_quantity"])
        if desired < 0 or desired > int(mandate["max_position_quantity"]):
            return _reject(request, "TARGET_POSITION_OUT_OF_RANGE", "QQ-STRATEGY-3001", calculation)
        target_weight: str | None = None
    else:
        weight = Decimal(target["target_weight"])
        max_weight = min(
            Decimal(mandate["max_target_weight"]),
            Decimal(1) - Decimal(mandate["cash_buffer_ratio"]),
        )
        if (
            weight < 0
            or (weight == 0 and str(target["target_weight"]).startswith("-"))
            or weight > max_weight
        ):
            return _reject(request, "TARGET_WEIGHT_OUT_OF_RANGE", "QQ-STRATEGY-3001", calculation)
        desired = int(
            (Decimal(snapshot["total_equity"]) * weight / price).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        if desired > int(mandate["max_position_quantity"]):
            return _reject(request, "TARGET_POSITION_OUT_OF_RANGE", "QQ-STRATEGY-3001", calculation)
        target_weight = target["target_weight"]

    sleeve_quantity = int(sleeve["quantity"])
    unadjusted = desired - sleeve_quantity
    effects = snapshot["active_order_effects"]
    if [item["order_id"] for item in effects] != sorted(item["order_id"] for item in effects):
        return _reject(request, "ACTIVE_ORDER_SNAPSHOT_INVALID", "QQ-STRATEGY-3003", calculation)
    seen_orders: set[str] = set()
    seen_intents: set[str] = set()
    for effect in effects:
        if effect["order_id"] in seen_orders or effect["intent_id"] in seen_intents:
            return _reject(
                request, "ACTIVE_ORDER_SNAPSHOT_INVALID", "QQ-STRATEGY-3003", calculation
            )
        seen_orders.add(effect["order_id"])
        seen_intents.add(effect["intent_id"])
        expected = int(effect["leaves_quantity"]) * (1 if effect["side"] == "BUY" else -1)
        if (
            effect["cumulative_quantity"] != effect["position_applied_cumulative_quantity"]
            or effect["leaves_quantity"]
            != effect["original_quantity"] - effect["cumulative_quantity"]
            or effect["expected_delta"] != expected
            or any(
                effect[field] != expected_value
                for field, expected_value in (
                    ("strategy_id", target["strategy_id"]),
                    ("strategy_version", target["strategy_version"]),
                    ("scope_id", target["scope_id"]),
                    ("account_id", snapshot["account_id"]),
                    ("instrument_id", target["instrument_id"]),
                )
            )
        ):
            return _reject(
                request, "ACTIVE_ORDER_SNAPSHOT_INVALID", "QQ-STRATEGY-3003", calculation
            )
    signs = {1 if int(effect["expected_delta"]) > 0 else -1 for effect in effects}
    active_delta = sum(int(effect["expected_delta"]) for effect in effects)
    effective = sleeve_quantity + active_delta
    residual = desired - effective
    calculation.update(
        {
            "decision_stage": "ACTIVE_ORDER_NETTING",
            "target_weight": target_weight,
            "desired_quantity": desired,
            "sleeve_quantity": sleeve_quantity,
            "active_order_expected_delta": active_delta,
            "effective_quantity": effective,
            "unadjusted_delta": unadjusted,
            "residual_delta": residual,
            "reference_price": _decimal_text(price),
            "projected_available_cash": snapshot["projected_available_cash"],
        }
    )
    if unadjusted == 0 and active_delta == 0:
        return _result(request, "NO_ACTION", "TARGET_ALREADY_SATISFIED", None, calculation)
    if len(signs) > 1 or (active_delta and (unadjusted == 0 or active_delta * unadjusted < 0)):
        return _reject(request, "ACTIVE_ORDER_DIRECTION_CONFLICT", "QQ-STRATEGY-3001", calculation)
    if abs(active_delta) > abs(unadjusted):
        return _reject(request, "ACTIVE_ORDERS_OVERSHOOT_TARGET", "QQ-STRATEGY-3001", calculation)
    if active_delta and abs(active_delta) == abs(unadjusted):
        return _result(request, "NO_ACTION", "ACTIVE_ORDERS_COVER_TARGET", None, calculation)

    residual_notional = abs(Decimal(residual) * price)
    calculation["decision_stage"] = "DEADBAND"
    calculation["deadband_notional"] = _decimal_text(residual_notional)
    if abs(residual) <= int(policy["quantity_deadband"]) or residual_notional <= Decimal(
        policy["notional_deadband"]
    ):
        return _result(request, "NO_ACTION", "WITHIN_DEADBAND", None, calculation)

    side = "BUY" if residual > 0 else "SELL"
    active_sell = sum(
        int(effect["leaves_quantity"]) for effect in effects if effect["side"] == "SELL"
    )
    available_sell = int(sleeve["available_quantity"]) - active_sell
    if available_sell < 0:
        return _reject(request, "ACTIVE_ORDER_SNAPSHOT_INVALID", "QQ-STRATEGY-3003", calculation)
    absolute_residual = abs(residual)
    sell_to_zero = (
        side == "SELL"
        and desired == 0
        and absolute_residual == available_sell
        and spec["sell_to_zero_odd_lot_allowed"]
    )
    lot = int(spec["lot_size"])
    rounded = absolute_residual if sell_to_zero else absolute_residual // lot * lot
    calculation.update(
        {
            "decision_stage": "ROUNDING",
            "rounded_quantity": rounded,
            "side": side,
            "available_sell_quantity": available_sell,
        }
    )
    if rounded == 0:
        return _result(request, "NO_ACTION", "ROUNDED_TO_ZERO", None, calculation)
    if rounded < int(spec["min_order_quantity"]) and not sell_to_zero:
        return _result(request, "NO_ACTION", "BELOW_MIN_ORDER_QUANTITY", None, calculation)
    if side == "SELL" and rounded > available_sell:
        return _reject(request, "INSUFFICIENT_AVAILABLE_QUANTITY", "QQ-STRATEGY-3001", calculation)

    tick = Decimal(spec["tick_size"])
    tick_rounding = ROUND_FLOOR if side == "BUY" else ROUND_CEILING
    limit_price = (price / tick).to_integral_value(rounding=tick_rounding) * tick
    calculation["limit_price"] = _decimal_text(limit_price, tick)
    if limit_price < lower or limit_price > upper:
        return _reject(request, "PRICE_OUTSIDE_BAND", "QQ-STRATEGY-3001", calculation)

    minor = Decimal(spec["currency_minor_unit"])
    required_buffer = max(
        Decimal(mandate["cash_buffer_absolute"]),
        Decimal(snapshot["total_equity"]) * Decimal(mandate["cash_buffer_ratio"]),
    ).quantize(minor, rounding=ROUND_CEILING)
    notional = (Decimal(rounded) * limit_price).quantize(minor, rounding=ROUND_CEILING)
    calculation.update(
        {
            "decision_stage": "CASH_OR_AVAILABILITY",
            "estimated_notional": _decimal_text(notional, minor),
            "required_cash_buffer": _decimal_text(required_buffer, minor),
        }
    )
    if side == "BUY" and Decimal(snapshot["projected_available_cash"]) - notional < required_buffer:
        return _reject(request, "CASH_BUFFER_BREACH", "QQ-STRATEGY-3001", calculation)

    resolution_id = str(uuid.uuid5(NAMESPACE, request["input_fingerprint"]))
    intent_id = str(uuid.uuid5(uuid.UUID(resolution_id), "order-intent:0"))
    intent = {
        "intent_id": intent_id,
        "strategy_id": target["strategy_id"],
        "strategy_version": target["strategy_version"],
        "account_id": snapshot["account_id"],
        "instrument_id": target["instrument_id"],
        "side": side,
        "position_effect": policy["position_effect"],
        "order_type": policy["order_type"],
        "quantity": rounded,
        "limit_price": _decimal_text(limit_price, tick),
        "time_in_force": policy["time_in_force"],
        "signal_time": target["effective_at"],
        "market_data_version": snapshot["market_source"]["snapshot_version"],
        "decision_id": target["decision_id"],
        "valid_until": target["valid_until"],
        "tags": {
            "target_id": target["target_id"],
            "resolution_id": resolution_id,
            "resolution_input_fingerprint": request["input_fingerprint"],
            "scope_id": target["scope_id"],
            "mandate_version": mandate["mandate_version"],
            "instrument_spec_version": spec["instrument_spec_version"],
            "portfolio_snapshot_version": snapshot["portfolio_source"]["snapshot_version"],
            "account_snapshot_version": snapshot["account_source"]["snapshot_version"],
            "market_snapshot_version": snapshot["market_source"]["snapshot_version"],
            "strategy_sleeve_version": snapshot["strategy_sleeve_source"]["snapshot_version"],
            "active_order_snapshot_version": snapshot["active_order_source"]["snapshot_version"],
            "resolver_policy_version": policy["resolver_policy_version"],
        },
    }
    envelope = {
        "message_id": intent_id,
        "message_type": "strategy.submit_order_intent.v1",
        "schema_version": 1,
        "occurred_at": request["resolution_time"],
        "correlation_id": request["accepted_target"]["correlation_id"],
        "causation_id": request["accepted_target"]["message_id"],
        "partition_key": snapshot["account_id"],
        "idempotency_key": intent_id,
    }
    calculation["decision_stage"] = "OUTPUT"
    result = _result(
        request,
        "INTENT",
        "ORDER_INTENT_CREATED",
        None,
        calculation,
        intent=intent,
        envelope=envelope,
    )
    _validator().validate(result)
    return result


def _stored(request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    intent = result["order_intent"]
    record = {
        "dto_type": "STORED_TARGET_RESOLUTION",
        "schema_version": 1,
        "target_id": request["target"]["target_id"],
        "target_fingerprint": request["target_fingerprint"],
        "resolution_id": result["resolution_id"],
        "input_fingerprint": request["input_fingerprint"],
        "request": request,
        "result": result,
        "result_fingerprint": _hash(result),
        "outbox_message_id": None if intent is None else intent["intent_id"],
        "publication_status": "NOT_APPLICABLE" if intent is None else "PENDING",
        "intent_handoff_status": "NOT_APPLICABLE" if intent is None else "PENDING_OUTBOX",
        "registered_order_id": None,
        "oms_registration_ref": None,
        "persisted_at": "2026-08-24T01:05:00.000001Z",
    }
    _validator().validate(record)
    return record


def _receipt(
    request: dict[str, Any],
    outcome: str,
    reason: str,
    error: str | None,
    resolution_id: str | None,
) -> dict[str, Any]:
    receipt = {
        "dto_type": "TARGET_RESOLUTION_TRIGGER_RECEIPT",
        "schema_version": 1,
        "target_id": request["target"]["target_id"],
        "target_fingerprint": request["target_fingerprint"],
        "trigger": deepcopy(request["resolution_trigger"]),
        "outcome": outcome,
        "reason_code": reason,
        "error_code": error,
        "resolution_id": resolution_id,
        "recorded_at": request["resolution_time"],
    }
    _validator().validate(receipt)
    return receipt


def _resolution_state() -> dict[str, Any]:
    return {
        "target_fingerprint": None,
        "by_trigger": {},
        "by_input": {},
        "unresolved_intent_id": None,
    }


def _mark_oms_registered(state: dict[str, Any], record: dict[str, Any]) -> None:
    record["publication_status"] = "PUBLISHED"
    record["intent_handoff_status"] = "OMS_REGISTERED"
    record["registered_order_id"] = "30000000-0000-5000-8000-000000000099"
    record["oms_registration_ref"] = {
        "message_id": "oms-registration-0000001",
        "accepted_at": "2026-08-24T01:05:01Z",
        "payload_fingerprint": _hash(
            {
                "intent_id": record["result"]["order_intent"]["intent_id"],
                "order_id": record["registered_order_id"],
            }
        ),
    }
    state["unresolved_intent_id"] = None
    _validator().validate(record)


def _resolve_cycle(
    request: dict[str, Any], state: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    registered = state["target_fingerprint"]
    if registered is None:
        state["target_fingerprint"] = request["target_fingerprint"]
    elif registered != request["target_fingerprint"]:
        return (
            _receipt(
                request,
                "TARGET_CONFLICT",
                "TARGET_REPLAY_CONFLICT",
                "QQ-STRATEGY-3002",
                None,
            ),
            None,
        )

    trigger = request["resolution_trigger"]
    trigger_id = trigger["trigger_message_id"]
    prior_trigger = state["by_trigger"].get(trigger_id)
    if prior_trigger is not None:
        trigger_fingerprint, prior_receipt, prior_record = prior_trigger
        if trigger_fingerprint != trigger["trigger_fingerprint"]:
            return (
                _receipt(
                    request,
                    "TRIGGER_CONFLICT",
                    "RESOLUTION_TRIGGER_CONFLICT",
                    "QQ-STRATEGY-3002",
                    None,
                ),
                None,
            )
        if prior_record is None:
            return prior_receipt, None
        return (
            _receipt(
                request,
                "EXACT_TRIGGER_REPLAY",
                "EXACT_TRIGGER_REPLAY",
                None,
                prior_record["resolution_id"],
            ),
            prior_record,
        )

    if not _trigger_is_valid(request):
        receipt = _receipt(
            request,
            "TRIGGER_REJECTED",
            "RESOLUTION_TRIGGER_INVALID",
            "QQ-STRATEGY-3003",
            None,
        )
        state["by_trigger"][trigger_id] = (
            trigger["trigger_fingerprint"],
            receipt,
            None,
        )
        return receipt, None

    if state["unresolved_intent_id"] is not None:
        receipt = _receipt(
            request,
            "HANDOFF_DEFERRED",
            "INTENT_HANDOFF_PENDING",
            None,
            None,
        )
        state["by_trigger"][trigger_id] = (
            trigger["trigger_fingerprint"],
            receipt,
            None,
        )
        return receipt, None

    if not _trigger_source_is_included(request):
        receipt = _receipt(
            request,
            "SNAPSHOT_REJECTED",
            "SNAPSHOT_IDENTITY_MISMATCH",
            "QQ-STRATEGY-3003",
            None,
        )
        state["by_trigger"][trigger_id] = (
            trigger["trigger_fingerprint"],
            receipt,
            None,
        )
        return receipt, None

    prior_input = state["by_input"].get(request["input_fingerprint"])
    if prior_input is not None:
        receipt = _receipt(
            request,
            "EXACT_INPUT_REPLAY",
            "EXACT_INPUT_REPLAY",
            None,
            prior_input["resolution_id"],
        )
        state["by_trigger"][trigger_id] = (
            trigger["trigger_fingerprint"],
            receipt,
            prior_input,
        )
        return receipt, prior_input

    record = _stored(request, _resolve(request))
    receipt = _receipt(
        request,
        "NEW_RESOLUTION",
        "NEW_RESOLUTION",
        None,
        record["resolution_id"],
    )
    state["by_trigger"][trigger_id] = (
        trigger["trigger_fingerprint"],
        receipt,
        record,
    )
    state["by_input"][request["input_fingerprint"]] = record
    if record["result"]["outcome"] == "INTENT":
        state["unresolved_intent_id"] = record["result"]["order_intent"]["intent_id"]
    return receipt, record


def test_target_resolver_contract_bundle_is_registered_and_machine_valid() -> None:
    schema = _json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    semantic = _yaml(SEMANTIC_PATH)
    workflow = _yaml(WORKFLOW_PATH)
    storage = _yaml(STORAGE_PATH)
    manifest = _yaml(ROOT / "spec" / "manifest.yaml")

    contract_ids = {item["id"] for item in manifest["catalogs"]["contracts"]}
    workflow_ids = {item["id"] for item in manifest["catalogs"]["workflows"]}
    storage_ids = {item["id"] for item in manifest["catalogs"]["storage"]}

    version = tuple(int(part) for part in manifest["specification"]["version"].split("."))
    assert version >= (0, 12, 0)
    assert schema["$id"] == "urn:quantiqmt:internal:target-resolver:v1"
    assert semantic["contract"]["id"] == "CONTRACT-TARGET-RESOLVER-SEMANTIC-V1"
    assert workflow["workflow"]["id"] == "WF-TARGET-RESOLUTION"
    assert storage["storage"]["id"] == "STORAGE-TARGET-RESOLUTION"
    assert {
        "CONTRACT-TARGET-RESOLVER-V1",
        "CONTRACT-TARGET-RESOLVER-SEMANTIC-V1",
    } <= contract_ids
    assert "WF-TARGET-RESOLUTION" in workflow_ids
    assert "STORAGE-TARGET-RESOLUTION" in storage_ids


def test_semantic_contract_freezes_safety_and_determinism_boundaries() -> None:
    semantic = _yaml(SEMANTIC_PATH)
    assert semantic["canonicalization"]["algorithm"] == "RFC8785_JCS"
    assert semantic["identity"]["intent_envelope_idempotency_key"] == "intent_id"
    assert semantic["resolution"]["active_order_effect"] == (
        "signed_leaves_quantity_from_complete_OMS_snapshot"
    )
    assert semantic["resolution"]["risk_decision"] == "never_performed_by_resolver"
    assert semantic["replay"]["same_target_id_same_target_fingerprint"] == (
        "retain_canonical_target_and_allow_only_a_new_verified_trigger_to_build_a_snapshot"
    )
    assert semantic["replay"]["same_target_id_different_target_fingerprint"] == (
        "reject_QQ_STRATEGY_3002_without_intent"
    )
    assert semantic["replay"]["same_trigger_id_same_trigger_fingerprint"] == (
        "return_EXACT_TRIGGER_REPLAY_receipt_and_exact_committed_resolution_or_exact_prior_SNAPSHOT_REJECTED_receipt_before_new_snapshot_read"
    )
    assert semantic["replay"]["new_trigger_same_input_fingerprint"] == (
        "record_EXACT_INPUT_REPLAY_receipt_and_return_exact_committed_record_without_new_Outbox"
    )


def test_schema_validates_request_result_and_exact_audit_record() -> None:
    request = _request()
    _validator().validate(request)
    result = _resolve(request)
    record = _stored(request, result)

    assert result["outcome"] == "INTENT"
    assert result["calculation"] == {
        "decision_stage": "OUTPUT",
        "target_weight": None,
        "desired_quantity": 500,
        "sleeve_quantity": 100,
        "active_order_expected_delta": 100,
        "effective_quantity": 200,
        "unadjusted_delta": 400,
        "residual_delta": 300,
        "deadband_notional": "3003",
        "rounded_quantity": 300,
        "side": "BUY",
        "reference_price": "10.01",
        "limit_price": "10.01",
        "estimated_notional": "3003.00",
        "projected_available_cash": "100000.00",
        "required_cash_buffer": "10000.00",
        "available_sell_quantity": 100,
    }
    assert record["outbox_message_id"] == result["order_intent"]["intent_id"]
    assert record["result_fingerprint"] == _hash(result)


def test_pre_resolution_failures_have_no_fabricated_resolution_or_outbox() -> None:
    request = _request()
    snapshot_failure = _receipt(
        request,
        "SNAPSHOT_REJECTED",
        "SNAPSHOT_BUILD_FAILED",
        "QQ-STRATEGY-3003",
        None,
    )
    integrity_failure = _receipt(
        request,
        "INTEGRITY_REJECTED",
        "DETERMINISTIC_IDENTITY_COLLISION",
        "QQ-STORAGE-7011",
        None,
    )
    assert snapshot_failure["resolution_id"] is None
    assert integrity_failure["resolution_id"] is None

    invalid = deepcopy(snapshot_failure)
    invalid["resolution_id"] = "90000000-0000-5000-8000-000000000001"
    with pytest.raises(ValidationError):
        _validator().validate(invalid)


def test_same_request_is_byte_deterministic_and_binds_intent_idempotency() -> None:
    request = _request()
    first = _resolve(deepcopy(request))
    second = _resolve(deepcopy(request))
    assert _jcs(first) == _jcs(second)
    assert first["resolution_id"] == str(uuid.uuid5(NAMESPACE, request["input_fingerprint"]))
    intent_id = str(uuid.uuid5(uuid.UUID(first["resolution_id"]), "order-intent:0"))
    assert first["order_intent"]["intent_id"] == intent_id
    assert first["intent_envelope"]["message_id"] == intent_id
    assert first["intent_envelope"]["idempotency_key"] == intent_id
    assert first["intent_envelope"]["causation_id"] == request["accepted_target"]["message_id"]
    assert "resolution_trigger_id" not in first["order_intent"]["tags"]
    assert "resolution_trigger_type" not in first["order_intent"]["tags"]
    vector = _yaml(SEMANTIC_PATH)["identity"]["reference_vector"]
    assert request["target_fingerprint"] == vector["target_fingerprint"]
    assert request["input_fingerprint"] == vector["input_fingerprint"]
    assert first["resolution_id"] == vector["resolution_id"]
    assert intent_id == vector["intent_id"]
    assert _hash(first) == vector["result_fingerprint"]


def test_exact_trigger_replay_returns_committed_record_before_new_snapshot_values_matter() -> None:
    original = _request()
    state = _resolution_state()
    first_receipt, committed = _resolve_cycle(original, state)
    assert first_receipt["outcome"] == "NEW_RESOLUTION"
    assert committed is not None

    replay = deepcopy(original)
    replay["snapshot"]["strategy_sleeve"]["quantity"] = 900
    replay["snapshot"]["market_source"]["snapshot_version"] = "market-v99"
    _refresh_request(replay)

    receipt, replayed = _resolve_cycle(replay, state)
    assert receipt["outcome"] == "EXACT_TRIGGER_REPLAY"
    assert replayed is committed


def test_new_trigger_with_same_input_is_exact_input_replay_without_new_outbox() -> None:
    original = _request()
    state = _resolution_state()
    _, committed = _resolve_cycle(original, state)
    assert committed is not None
    _mark_oms_registered(state, committed)

    replay = deepcopy(original)
    _set_trigger(
        replay,
        message_id="schedule-message-00000001",
        trigger_type="SCHEDULED_REEVALUATION",
        source_contract_id="CONTRACT-TARGET-RESOLVER-V1#SCHEDULE",
        source_state_version=None,
        source_payload={"schedule_id": "target-recheck", "tick": 1},
        occurred_at="2026-08-24T01:04:00Z",
        accepted_at="2026-08-24T01:04:00Z",
    )
    assert _jcs(_resolve(deepcopy(replay))) == _jcs(committed["result"])
    receipt, replayed = _resolve_cycle(replay, state)

    assert replay["input_fingerprint"] == original["input_fingerprint"]
    assert receipt["outcome"] == "EXACT_INPUT_REPLAY"
    assert receipt["resolution_id"] == committed["resolution_id"]
    assert replayed is committed
    assert len(state["by_input"]) == 1


def test_new_trigger_is_deferred_until_prior_intent_is_registered_by_oms() -> None:
    original = _request()
    state = _resolution_state()
    _, committed = _resolve_cycle(original, state)
    assert committed is not None

    deferred = deepcopy(original)
    deferred["snapshot"]["strategy_sleeve"]["quantity"] = 900
    _set_trigger(
        deferred,
        message_id="market-message-000000001",
        trigger_type="MARKET_CHANGED",
        source_contract_id="CONTRACT-MARKET-DATA-V1",
        source_state_version="market-v11",
        source_payload={"instrument_id": "600000.XSHG", "price": "10.02"},
        occurred_at="2026-08-24T01:04:00Z",
        accepted_at="2026-08-24T01:04:00Z",
    )
    receipt, record = _resolve_cycle(deferred, state)

    assert receipt["outcome"] == "HANDOFF_DEFERRED"
    assert receipt["reason_code"] == "INTENT_HANDOFF_PENDING"
    assert receipt["resolution_id"] is None
    assert record is None
    assert len(state["by_input"]) == 1
    replay_receipt, replay_record = _resolve_cycle(deferred, state)
    assert replay_receipt is receipt
    assert replay_record is None


def test_new_verified_trigger_can_resolve_same_target_again_after_snapshot_changes() -> None:
    original = _request()
    original["snapshot"]["active_order_effects"] = []
    _refresh_request(original)
    state = _resolution_state()
    first_receipt, first_record = _resolve_cycle(original, state)
    assert first_receipt["outcome"] == "NEW_RESOLUTION"
    assert first_record is not None
    assert first_record["result"]["order_intent"]["quantity"] == 400
    _mark_oms_registered(state, first_record)

    changed = deepcopy(original)
    snapshot = changed["snapshot"]
    snapshot["current_position"] = {"quantity": 300, "available_quantity": 300}
    snapshot["strategy_sleeve"] = {"quantity": 300, "available_quantity": 300}
    snapshot["portfolio_source"] = _source("PortfolioProjection", "portfolio-v8")
    snapshot["account_source"] = _source("AccountProjection", "account-v10")
    snapshot["market_source"] = _source("MarketSnapshot", "market-v12")
    snapshot["strategy_sleeve_source"] = _source("StrategySleeveProjection", "sleeve-v6")
    snapshot["active_order_source"] = _source("OMSActiveOrderReadModel", "orders-v14")
    for source_name in (
        "portfolio_source",
        "account_source",
        "market_source",
        "strategy_sleeve_source",
        "active_order_source",
    ):
        snapshot[source_name]["as_of"] = "2026-08-24T01:06:00Z"
    snapshot["price_reference"]["observed_at"] = "2026-08-24T01:06:00Z"
    snapshot["portfolio_trade_watermark"] = 22
    snapshot["strategy_sleeve_trade_watermark"] = 22
    snapshot["active_order_trade_watermark"] = 22
    snapshot["account_reserved_orders_snapshot_version"] = "orders-v14"
    snapshot["captured_at"] = "2026-08-24T01:06:01Z"
    changed["resolution_time"] = "2026-08-24T01:06:01Z"
    _set_trigger(
        changed,
        message_id="order-message-0000000001",
        trigger_type="ORDER_CHANGED",
        source_contract_id="CONTRACT-ORDER-STATUS-V1",
        source_state_version="orders-v14",
        source_payload={
            "order_id": "30000000-0000-5000-8000-000000000001",
            "state": "CANCELED",
            "cumulative_quantity": 200,
        },
        occurred_at="2026-08-24T01:05:59Z",
        accepted_at="2026-08-24T01:06:00Z",
    )
    second_receipt, second_record = _resolve_cycle(changed, state)

    assert second_receipt["outcome"] == "NEW_RESOLUTION"
    assert second_record is not None
    assert second_record["resolution_id"] != first_record["resolution_id"]
    assert (
        second_record["result"]["order_intent"]["intent_id"]
        != first_record["result"]["order_intent"]["intent_id"]
    )
    assert second_record["result"]["order_intent"]["quantity"] == 200
    assert len(state["by_input"]) == 2


def test_target_and_trigger_identity_conflicts_fail_closed_without_resolution() -> None:
    original = _request()
    state = _resolution_state()
    _, committed = _resolve_cycle(original, state)
    assert committed is not None

    conflict = deepcopy(original)
    conflict["target"]["target_quantity"] = 600
    _refresh_request(conflict)
    target_receipt, target_record = _resolve_cycle(conflict, state)
    assert target_receipt["outcome"] == "TARGET_CONFLICT"
    assert target_receipt["reason_code"] == "TARGET_REPLAY_CONFLICT"
    assert target_receipt["error_code"] == "QQ-STRATEGY-3002"
    assert target_record is None

    trigger_conflict = deepcopy(original)
    trigger_conflict["resolution_trigger"]["occurred_at"] = "2026-08-24T00:59:59Z"
    _refresh_request(trigger_conflict)
    trigger_receipt, trigger_record = _resolve_cycle(trigger_conflict, state)
    assert trigger_receipt["outcome"] == "TRIGGER_CONFLICT"
    assert trigger_receipt["reason_code"] == "RESOLUTION_TRIGGER_CONFLICT"
    assert trigger_receipt["error_code"] == "QQ-STRATEGY-3002"
    assert trigger_record is None

    invalid_pair = deepcopy(trigger_receipt)
    invalid_pair["reason_code"] = "TARGET_REPLAY_CONFLICT"
    with pytest.raises(ValidationError):
        _validator().validate(invalid_pair)


def test_weight_conversion_uses_decimal_and_never_rounds_quantity_away_from_zero() -> None:
    request = _request(target_type="WEIGHT")
    result = _resolve(request)
    assert result["outcome"] == "INTENT"
    assert result["calculation"]["desired_quantity"] == 4995
    assert result["calculation"]["residual_delta"] == 4795
    assert result["order_intent"]["quantity"] == 4700
    assert result["order_intent"]["limit_price"] == "10.01"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("already_satisfied", "TARGET_ALREADY_SATISFIED"),
        ("active_cover", "ACTIVE_ORDERS_COVER_TARGET"),
        ("deadband", "WITHIN_DEADBAND"),
        ("rounded_zero", "ROUNDED_TO_ZERO"),
        ("below_minimum", "BELOW_MIN_ORDER_QUANTITY"),
    ],
)
def test_complete_no_action_reason_matrix(mutation: str, reason: str) -> None:
    request = _request()
    if mutation == "already_satisfied":
        request["snapshot"]["active_order_effects"] = []
        request["target"]["target_quantity"] = 100
    elif mutation == "active_cover":
        request["target"]["target_quantity"] = 200
    elif mutation == "deadband":
        request["snapshot"]["active_order_effects"] = []
        request["target"]["target_quantity"] = 200
        request["policy"]["quantity_deadband"] = 100
    elif mutation == "rounded_zero":
        request["snapshot"]["active_order_effects"] = []
        request["target"]["target_quantity"] = 151
    else:
        request["snapshot"]["active_order_effects"] = []
        request["target"]["target_quantity"] = 150
        request["instrument_spec"]["lot_size"] = 10
        request["instrument_spec"]["min_order_quantity"] = 100
    _refresh_request(request)
    result = _resolve(request)
    assert result["outcome"] == "NO_ACTION"
    assert result["reason_code"] == reason
    assert result["order_intent"] is None
    assert result["error_code"] is None


def test_sell_to_zero_is_the_only_odd_lot_and_minimum_exception() -> None:
    request = _request()
    request["snapshot"]["active_order_effects"] = []
    request["snapshot"]["current_position"] = {"quantity": 50, "available_quantity": 50}
    request["snapshot"]["strategy_sleeve"] = {"quantity": 50, "available_quantity": 50}
    request["target"]["target_quantity"] = 0
    _refresh_request(request)
    result = _resolve(request)
    assert result["outcome"] == "INTENT"
    assert result["order_intent"]["side"] == "SELL"
    assert result["order_intent"]["quantity"] == 50

    request["instrument_spec"]["sell_to_zero_odd_lot_allowed"] = False
    _refresh_request(request)
    result = _resolve(request)
    assert result["outcome"] == "NO_ACTION"
    assert result["reason_code"] == "ROUNDED_TO_ZERO"


@pytest.mark.parametrize(
    ("mutation", "reason", "error"),
    [
        ("expired", "TARGET_EXPIRED", "QQ-STRATEGY-3001"),
        ("scope", "TARGET_SCOPE_UNAUTHORIZED", "QQ-STRATEGY-3001"),
        ("stale", "SNAPSHOT_NOT_FRESH", "QQ-STRATEGY-3003"),
        ("partial", "SNAPSHOT_NOT_FRESH", "QQ-STRATEGY-3003"),
        ("old", "SNAPSHOT_TOO_OLD", "QQ-STRATEGY-3003"),
        ("direction", "ACTIVE_ORDER_DIRECTION_CONFLICT", "QQ-STRATEGY-3001"),
        ("overshoot", "ACTIVE_ORDERS_OVERSHOOT_TARGET", "QQ-STRATEGY-3001"),
        ("unavailable_sell", "INSUFFICIENT_AVAILABLE_QUANTITY", "QQ-STRATEGY-3001"),
        ("cash", "CASH_BUFFER_BREACH", "QQ-STRATEGY-3001"),
        ("price", "PRICE_REFERENCE_INVALID", "QQ-STRATEGY-3001"),
    ],
)
def test_fail_closed_rejection_matrix(mutation: str, reason: str, error: str) -> None:
    request = _request()
    if mutation == "expired":
        request["resolution_time"] = request["target"]["valid_until"]
        request["snapshot"]["captured_at"] = request["resolution_time"]
    elif mutation == "scope":
        request["target"]["scope_id"] = "different-sleeve"
        request["resolution_trigger"]["scope_id"] = "different-sleeve"
    elif mutation == "stale":
        request["snapshot"]["market_source"]["quality"] = "STALE"
    elif mutation == "partial":
        request["snapshot"]["active_order_source"]["completeness"] = "PARTIAL"
    elif mutation == "old":
        request["snapshot"]["market_source"]["as_of"] = "2026-08-24T00:00:00Z"
    elif mutation == "direction":
        request["target"]["target_quantity"] = 0
    elif mutation == "overshoot":
        request["target"]["target_quantity"] = 150
    elif mutation == "unavailable_sell":
        request["snapshot"]["active_order_effects"] = []
        request["snapshot"]["strategy_sleeve"]["available_quantity"] = 50
        request["target"]["target_quantity"] = 0
    elif mutation == "cash":
        request["snapshot"]["active_order_effects"] = []
        request["snapshot"]["current_position"] = {"quantity": 0, "available_quantity": 0}
        request["snapshot"]["strategy_sleeve"] = {"quantity": 0, "available_quantity": 0}
        request["snapshot"]["projected_available_cash"] = "10001.00"
        request["target"]["target_quantity"] = 500
    elif mutation == "price":
        request["snapshot"]["price_reference"]["price"] = "12.01"
    _refresh_request(request)
    result = _resolve(request)
    assert result["outcome"] == "REJECTED"
    assert result["reason_code"] == reason
    assert result["error_code"] == error
    assert result["order_intent"] is None


@pytest.mark.parametrize("mutation", ["future", "target_identity", "scope"])
def test_invalid_resolution_trigger_is_rejected_before_pure_resolution(
    mutation: str,
) -> None:
    request = _request()
    if mutation == "future":
        request["resolution_trigger"]["accepted_at"] = "2026-08-24T01:05:00Z"
    elif mutation == "target_identity":
        request["resolution_trigger"]["trigger_message_id"] = "target-message-00000002"
    else:
        request["resolution_trigger"]["scope_id"] = "different-sleeve"
    _refresh_request(request)

    receipt, record = _resolve_cycle(request, _resolution_state())
    assert receipt["outcome"] == "TRIGGER_REJECTED"
    assert receipt["reason_code"] == "RESOLUTION_TRIGGER_INVALID"
    assert receipt["error_code"] == "QQ-STRATEGY-3003"
    assert receipt["resolution_id"] is None
    assert record is None
    with pytest.raises(ValueError, match="validated before pure resolution"):
        _resolve(request)


def test_trigger_source_state_must_be_included_in_corresponding_snapshot() -> None:
    request = _request()
    _set_trigger(
        request,
        message_id="market-message-000000099",
        trigger_type="MARKET_CHANGED",
        source_contract_id="CONTRACT-MARKET-DATA-V1",
        source_state_version="market-v99",
        source_payload={"instrument_id": "600000.XSHG", "price": "10.02"},
        occurred_at="2026-08-24T01:04:00Z",
        accepted_at="2026-08-24T01:04:00Z",
    )

    receipt, record = _resolve_cycle(request, _resolution_state())
    assert receipt["outcome"] == "SNAPSHOT_REJECTED"
    assert receipt["reason_code"] == "SNAPSHOT_IDENTITY_MISMATCH"
    assert record is None
    with pytest.raises(ValueError, match="source must be included"):
        _resolve(request)


def test_active_order_effect_must_be_complete_ordered_and_exactly_signed() -> None:
    request = _request()
    request["snapshot"]["active_order_effects"][0]["expected_delta"] = -100
    _refresh_request(request)
    assert _resolve(request)["reason_code"] == "ACTIVE_ORDER_SNAPSHOT_INVALID"

    request = _request()
    request["snapshot"]["active_order_effects"][0]["position_applied_cumulative_quantity"] = 1
    _refresh_request(request)
    assert _resolve(request)["reason_code"] == "ACTIVE_ORDER_SNAPSHOT_INVALID"

    request = _request()
    duplicate = deepcopy(request["snapshot"]["active_order_effects"][0])
    duplicate["order_id"] = "20000000-0000-5000-8000-000000000001"
    request["snapshot"]["active_order_effects"].append(duplicate)
    _refresh_request(request)
    assert _resolve(request)["reason_code"] == "ACTIVE_ORDER_SNAPSHOT_INVALID"


def test_trade_watermarks_and_account_reservations_must_match_active_orders() -> None:
    request = _request()
    request["snapshot"]["strategy_sleeve_trade_watermark"] = 20
    _refresh_request(request)
    assert _resolve(request)["reason_code"] == "SNAPSHOT_IDENTITY_MISMATCH"

    request = _request()
    request["snapshot"]["account_reserved_orders_snapshot_version"] = "orders-v12"
    _refresh_request(request)
    assert _resolve(request)["reason_code"] == "SNAPSHOT_IDENTITY_MISMATCH"


def test_pending_sell_is_netted_and_never_double_sells() -> None:
    request = _request()
    effect = request["snapshot"]["active_order_effects"][0]
    effect.update({"side": "SELL", "expected_delta": -100})
    request["snapshot"]["current_position"] = {"quantity": 500, "available_quantity": 500}
    request["snapshot"]["strategy_sleeve"] = {"quantity": 500, "available_quantity": 500}
    request["target"]["target_quantity"] = 300
    _refresh_request(request)
    result = _resolve(request)
    assert result["outcome"] == "INTENT"
    assert result["calculation"]["unadjusted_delta"] == -200
    assert result["calculation"]["active_order_expected_delta"] == -100
    assert result["calculation"]["residual_delta"] == -100
    assert result["calculation"]["available_sell_quantity"] == 400
    assert result["order_intent"]["side"] == "SELL"
    assert result["order_intent"]["quantity"] == 100


def test_side_specific_tick_rounding_and_post_round_price_band_are_enforced() -> None:
    sell = _request()
    sell["snapshot"]["active_order_effects"] = []
    sell["snapshot"]["current_position"] = {"quantity": 500, "available_quantity": 500}
    sell["snapshot"]["strategy_sleeve"] = {"quantity": 500, "available_quantity": 500}
    sell["snapshot"]["price_reference"]["price"] = "10.001"
    sell["target"]["target_quantity"] = 300
    _refresh_request(sell)
    result = _resolve(sell)
    assert result["order_intent"]["limit_price"] == "10.01"

    buy = _request()
    buy["snapshot"]["price_reference"].update({"price": "10.006", "lower_price_limit": "10.005"})
    _refresh_request(buy)
    result = _resolve(buy)
    assert result["outcome"] == "REJECTED"
    assert result["reason_code"] == "PRICE_OUTSIDE_BAND"


def test_target_shape_negative_zero_and_unsorted_mandate_fail_closed() -> None:
    shape = _request()
    shape["target"]["target_weight"] = "0.10"
    _refresh_request(shape)
    assert _resolve(shape)["reason_code"] == "TARGET_SHAPE_INVALID"

    missing = _request()
    missing["target"]["target_quantity"] = None
    _refresh_request(missing)
    assert _resolve(missing)["reason_code"] == "TARGET_SHAPE_INVALID"

    negative_position = _request()
    negative_position["target"]["target_quantity"] = -1
    _refresh_request(negative_position)
    assert _resolve(negative_position)["reason_code"] == "TARGET_POSITION_OUT_OF_RANGE"

    negative_zero = _request(target_type="WEIGHT")
    negative_zero["target"]["target_weight"] = "-0.0"
    _refresh_request(negative_zero)
    assert _resolve(negative_zero)["reason_code"] == "TARGET_WEIGHT_OUT_OF_RANGE"

    unsorted = _request()
    unsorted["mandate"]["allowed_instrument_ids"] = ["600001.XSHG", "600000.XSHG"]
    _refresh_request(unsorted)
    assert _resolve(unsorted)["reason_code"] == "INSTRUMENT_UNAUTHORIZED"


def test_no_action_and_rejected_records_never_create_outbox_messages() -> None:
    request = _request()
    request["snapshot"]["active_order_effects"] = []
    request["target"]["target_quantity"] = 100
    _refresh_request(request)
    no_action = _stored(request, _resolve(request))
    assert no_action["publication_status"] == "NOT_APPLICABLE"
    assert no_action["outbox_message_id"] is None

    rejected_request = _request()
    rejected_request["target"]["scope_id"] = "wrong"
    rejected_request["resolution_trigger"]["scope_id"] = "wrong"
    _refresh_request(rejected_request)
    rejected = _stored(rejected_request, _resolve(rejected_request))
    assert rejected["publication_status"] == "NOT_APPLICABLE"
    assert rejected["outbox_message_id"] is None

    invalid_error = deepcopy(rejected["result"])
    invalid_error["error_code"] = "QQ-STRATEGY-3003"
    with pytest.raises(ValidationError):
        _validator().validate(invalid_error)

    invalid_delivery = deepcopy(no_action)
    invalid_delivery["publication_status"] = "PENDING"
    with pytest.raises(ValidationError):
        _validator().validate(invalid_delivery)

    intent_record = _stored(_request(), _resolve(_request()))
    intent_record["registered_order_id"] = "30000000-0000-5000-8000-000000000099"
    with pytest.raises(ValidationError):
        _validator().validate(intent_record)

    intent_record = _stored(_request(), _resolve(_request()))
    intent_record["intent_handoff_status"] = "OMS_REGISTERED"
    with pytest.raises(ValidationError):
        _validator().validate(intent_record)

    intent_record = _stored(_request(), _resolve(_request()))
    intent_record["intent_handoff_status"] = "PUBLISHED_AWAITING_OMS"
    with pytest.raises(ValidationError):
        _validator().validate(intent_record)


def test_schema_and_fingerprints_reject_float_unknown_fields_and_tampering() -> None:
    request = _request()
    request["snapshot"]["price_reference"]["price"] = 10.01
    with pytest.raises(ValidationError):
        _validator().validate(request)
    with pytest.raises(ValueError, match="float"):
        _jcs(request)

    request = _request()
    request["unexpected"] = True
    with pytest.raises(ValidationError):
        _validator().validate(request)

    request = _request()
    request["mandate"]["cash_buffer_ratio"] = "0.20"
    request["input_fingerprint"] = _checksum(request, "input_fingerprint")
    with pytest.raises(ValueError, match="mandate_checksum"):
        _resolve(request)


def test_public_target_and_order_intent_wire_contracts_are_not_redefined() -> None:
    target = _json(TARGET_PATH)
    intent = _json(INTENT_PATH)
    assert target["$id"] == "urn:quantiqmt:command:strategy.submit_target:v1"
    assert intent["$id"] == "urn:quantiqmt:command:strategy.submit_order_intent:v1"
    assert "mandate" not in target["properties"]
    assert "resolution_id" not in intent["properties"]
    assert "idempotency_key" not in intent["properties"]
    assert _yaml(SEMANTIC_PATH)["identity"]["intent_envelope_idempotency_key"] == "intent_id"


def test_workflow_and_ports_preserve_oms_risk_execution_chain() -> None:
    workflow = _yaml(WORKFLOW_PATH)["workflow"]
    ports = (ROOT / "spec" / "interfaces" / "strategy-ports.md").read_text(encoding="utf-8")
    storage = _yaml(STORAGE_PATH)["storage"]
    steps = {step["id"]: step for step in workflow["steps"]}
    assert steps["commit_resolution"]["transaction"] == [
        "append_NEW_RESOLUTION_trigger_receipt",
        "append_STORED_TARGET_RESOLUTION",
        "append_OrderIntent_command_to_Outbox_only_for_INTENT",
    ]
    assert steps["publish_intent"]["next_workflow"] == "WF-SUBMIT-ORDER"
    assert "Risk_approval_or_bypass" in workflow["forbidden"]
    assert "不得访问 Broker、Execution、Risk、OMS" in ports
    assert "Repository、数据库、Redis、网络或系统时钟" in ports
    assert "OrderIntent → OMS 注册 → Risk → OMS 迁移 → Execution" in ports
    assert "HANDOFF_DEFERRED/INTENT_HANDOFF_PENDING" in ports
    assert (
        "new_snapshot_read_while_same_scope_has_unresolved_Intent_handoff" in workflow["forbidden"]
    )
    assert storage["transaction_rules"]["atomic"] is True
    assert storage["migration"]["owned_by_TASK_019"] is False


def test_jcs_utf16_order_and_error_catalog_are_frozen() -> None:
    semantic = _yaml(SEMANTIC_PATH)
    vector = semantic["canonicalization"]["normative_vectors"][0]
    assert _jcs(vector["input"]) == vector["canonical_json"]
    errors = _yaml(CONTRACTS / "errors" / "catalog.yaml")["errors"]
    by_code = {item["code"]: item["name"] for item in errors}
    assert by_code["QQ-STRATEGY-3001"] == "TARGET_RESOLUTION_REJECTED"
    assert by_code["QQ-STRATEGY-3002"] == "TARGET_REPLAY_CONFLICT"
    assert by_code["QQ-STRATEGY-3003"] == "TARGET_RESOLUTION_SNAPSHOT_INVALID"
