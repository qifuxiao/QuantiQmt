from __future__ import annotations

import pytest

from quantiqmt.contracts import ContractValidationError
from quantiqmt.contracts.validation import validate

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:test:contract",
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "values", "identifier"],
    "properties": {
        "mode": {"enum": ["strict", "relaxed"]},
        "values": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"$ref": "#/$defs/value"},
        },
        "identifier": {"type": "string", "format": "uuid", "pattern": "^[0-9a-f-]{36}$"},
    },
    "allOf": [
        {
            "if": {"properties": {"mode": {"const": "strict"}}},
            "then": {"properties": {"values": {"maxItems": 1}}},
            "else": {"properties": {"values": {"minItems": 2}}},
        }
    ],
    "$defs": {"value": {"type": "string", "minLength": 1}},
}


def valid(mode: str = "strict", values: list[str] | None = None) -> dict[str, object]:
    return {
        "mode": mode,
        "values": ["one"] if values is None else values,
        "identifier": "550e8400-e29b-41d4-a716-446655440000",
    }


def test_draft202012_keywords_are_enforced() -> None:
    validate(valid(), SCHEMA)
    with pytest.raises(ContractValidationError):
        validate(
            {"mode": "strict", "values": ["one", "two"], "identifier": valid()["identifier"]},
            SCHEMA,
        )
    with pytest.raises(ContractValidationError):
        validate(valid(values=["one", "one"]), SCHEMA)
    with pytest.raises(ContractValidationError):
        validate({**valid(), "extra": True}, SCHEMA)
    with pytest.raises(ContractValidationError):
        validate({**valid(), "identifier": "not-a-date"}, SCHEMA)
    with pytest.raises(ContractValidationError):
        validate({"mode": "strict", "values": ["one"]}, SCHEMA)


def test_if_then_else_branch_is_enforced() -> None:
    with pytest.raises(ContractValidationError):
        validate(valid(mode="relaxed", values=["one"]), SCHEMA)
    validate(valid(mode="relaxed", values=["one", "two"]), SCHEMA)
