"""Deterministically materialize reviewed message payload fixtures."""

from __future__ import annotations

import json
import runpy
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).with_name("fixtures")
SCHEMAS = ROOT / "spec" / "contracts"
UUID1 = "550e8400-e29b-41d4-a716-446655440000"

MAXIMAL_ADDITIONS: dict[str, dict[str, object]] = {
    "strategy.submit_order_intent.v1": {"decision_id": UUID1, "tags": {"desk": "alpha"}},
    "strategy.submit_target.v1": {"reason_code": "REBALANCE"},
    "execution.cancel_order.v1": {"broker_order_id": "broker-order-1"},
    "broker.trade_reported.v1": {
        "order_id": UUID1,
        "client_order_id": "client-1",
        "commission": "0.01000000",
        "tax": "0",
        "broker_sequence": 1,
    },
    "oms.order_status_changed.v1": {
        "broker_order_id": "broker-order-1",
        "average_price": "10.01000000",
        "source_report_id": "report-1",
    },
    "risk.order_evaluated.v1": {},
    "execution.attempt_started.v1": {"cancel_request_id": UUID1},
    "execution.outcome_unknown.v1": {"cancel_request_id": UUID1},
    "broker.order_reported.v1": {
        "order_id": UUID1,
        "broker_order_id": "broker-order-1",
        "average_price": "10.01000000",
        "broker_sequence": 1,
        "raw_error_code": "0",
    },
    "ledger.trade_posted.v1": {"commission": "0.01000000", "tax": "0"},
    "portfolio.position_changed.v1": {
        "average_cost": "10.01000000",
        "market_value": "1001.00000000",
    },
}


def _schema_path(message_type: str) -> Path:
    domain = "commands" if message_type.startswith(("strategy.", "execution.cancel")) else "events"
    return SCHEMAS / domain / f"{message_type}.schema.json"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sample(schema: dict[str, Any]) -> object:
    if "enum" in schema:
        return schema["enum"][0]
    declared = schema.get("type")
    types = declared if isinstance(declared, list) else [declared]
    kind = next((item for item in types if item != "null"), None)
    if kind == "string":
        pattern = schema.get("pattern", "")
        if schema.get("format") == "date-time":
            return "2026-07-02T02:00:00Z"
        if schema.get("format") == "date":
            return "2026-07-02"
        if schema.get("format") == "uuid":
            return UUID1
        if "[A-Z]{3}" in pattern:
            return "CNY"
        if "\\." in pattern:
            return "1.00000000"
        return "x"
    if kind == "integer":
        return max(1, schema.get("minimum", 0))
    if kind == "object":
        return {name: _sample(prop) for name, prop in schema.get("properties", {}).items()}
    if kind == "array":
        return [_sample(schema.get("items", {}))]
    return None


def _maximalize(value: object, schema: dict[str, Any]) -> object:
    if isinstance(value, str):
        pattern = schema.get("pattern", "")
        if "\\." in pattern:
            negative = value.startswith("-")
            whole = value.lstrip("-").split(".", 1)[0]
            return f"{'-' if negative else ''}{whole}.00000000"
        maximum = schema.get("maxLength")
        if maximum is not None and not any(key in schema for key in ("enum", "format", "pattern")):
            return "x" * maximum
        return value
    if isinstance(value, list):
        item_schema = schema.get("items", {})
        return [_maximalize(item, item_schema) for item in value]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        result = {
            key: _maximalize(item, properties.get(key, schema.get("additionalProperties", {})))
            for key, item in value.items()
        }
        for key, property_schema in properties.items():
            if key not in result:
                result[key] = _maximalize(_sample(property_schema), property_schema)
        maximum = schema.get("maxProperties")
        additional = schema.get("additionalProperties")
        if maximum is not None and isinstance(additional, dict):
            while len(result) < maximum:
                result[f"k{len(result):02d}"] = _maximalize(_sample(additional), additional)
        return result
    return value


def _first_enum(schema: dict[str, Any]) -> tuple[list[str], str] | None:
    for name, prop in schema.get("properties", {}).items():
        if "enum" in prop:
            return [name], name
        nested = _first_enum(prop)
        if nested is not None:
            return [name, *nested[0]], nested[1]
    items = schema.get("items")
    if isinstance(items, dict):
        nested = _first_enum(items)
        if nested is not None:
            return ["0", *nested[0]], nested[1]
    return None


def _set_path(value: Any, path: list[str], replacement: object) -> None:
    cursor = value
    for part in path[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    if isinstance(cursor, list):
        cursor[int(path[-1])] = replacement
    else:
        cursor[path[-1]] = replacement


def main() -> None:
    namespace = runpy.run_path(str(Path(__file__).with_name("test_message_contracts.py")))
    payloads: dict[str, dict[str, object]] = namespace["PAYLOADS"]
    for message_type, minimal in sorted(payloads.items()):
        schema = json.loads(_schema_path(message_type).read_text(encoding="utf-8"))
        directory = FIXTURES / message_type
        _write(directory / "minimal.valid.json", minimal)
        maximal = deepcopy(minimal)
        maximal.update(MAXIMAL_ADDITIONS.get(message_type, {}))
        if message_type == "risk.order_evaluated.v1":
            maximal["rule_results"][0].update(  # type: ignore[index]
                {"measured_value": "1.00000000", "limit_value": "2.00000000"}
            )
        _write(directory / "maximal.valid.json", _maximalize(maximal, schema))

        missing = deepcopy(minimal)
        missing.pop(schema["required"][0])
        _write(directory / "invalid.missing-required.json", missing)

        additional = deepcopy(minimal)
        additional["unexpected_property"] = True
        _write(directory / "invalid.additional-property.json", additional)

        precision = deepcopy(minimal)
        decimal_field = next(
            (
                name
                for name, prop in schema["properties"].items()
                if "pattern" in prop
                and isinstance(minimal.get(name), str)
                and any(token in prop["pattern"] for token in ("[0-9]", "\\d"))
            ),
            None,
        )
        numeric = next(
            (name for name, prop in schema["properties"].items() if prop.get("type") == "integer"),
            None,
        )
        if decimal_field is not None:
            precision[decimal_field] = 0.5
        elif numeric is not None:
            precision[numeric] = 0.5
        else:
            temporal = next(
                name
                for name, prop in schema["properties"].items()
                if prop.get("format") == "date-time"
            )
            precision[temporal] = "2026-07-02T02:00:00,1Z"
        obsolete = directory / "invalid.precision-or-format.json"
        if obsolete.exists():
            obsolete.unlink()
        _write(directory / "invalid.precision.json", precision)

        enum_path = _first_enum(schema)
        if enum_path is not None:
            unknown = deepcopy(minimal)
            _set_path(unknown, enum_path[0], "UNKNOWN_ENUM_V1")
            _write(directory / "invalid.unknown-enum.json", unknown)

    conditional: dict[str, tuple[str, dict[str, object]]] = {
        "oms.order_registered.v1": ("invalid.limit-missing-price.json", {"limit_price": None}),
        "execution.attempt_started.v1": (
            "invalid.cancel-missing-request-id.json",
            {"operation": "CANCEL"},
        ),
        "execution.outcome_unknown.v1": (
            "invalid.reconciliation-not-required.json",
            {"reconciliation_required": False},
        ),
    }
    for message_type, (filename, changes) in conditional.items():
        value = deepcopy(payloads[message_type])
        value.update(changes)
        _write(FIXTURES / message_type / filename, value)

    missing_field_cases = {
        "strategy.submit_order_intent.v1": ("invalid.limit-missing-price.json", "limit_price"),
        "execution.outcome_unknown.v1": (
            "invalid.cancel-missing-request-id.json",
            "cancel_request_id",
        ),
        "strategy.submit_target.v1": ("invalid.one-of-no-match.json", "target_weight"),
    }
    for message_type, (filename, field) in missing_field_cases.items():
        value = deepcopy(payloads[message_type])
        if message_type == "execution.outcome_unknown.v1":
            value["operation"] = "CANCEL"
        value.pop(field, None)
        _write(FIXTURES / message_type / filename, value)


if __name__ == "__main__":
    main()
