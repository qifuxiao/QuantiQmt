"""Small deterministic validator for the JSON-Schema subset used by message V1."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, cast

from quantiqmt.contracts.errors import ContractValidationError

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
    re.ASCII,
)


def validate(
    instance: object,
    schema: Mapping[str, Any],
    *,
    path: str = "$",
    _root: Mapping[str, Any] | None = None,
) -> None:
    """Validate one instance against the contract-supported schema subset."""
    root = schema if _root is None else _root
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            _fail(path, "contains unsupported non-local $ref")
        target: object = root
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, Mapping) or part not in target:
                _fail(path, f"contains unresolved $ref {reference!r}")
            target = cast(Mapping[str, Any], target)[part]
        if not isinstance(target, Mapping):
            _fail(path, f"$ref {reference!r} does not resolve to a schema")
        validate(instance, cast(Mapping[str, Any], target), path=path, _root=root)
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if siblings:
            validate(instance, siblings, path=path, _root=root)
        return
    if "const" in schema and instance != schema["const"]:
        _fail(path, f"must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        _fail(path, f"unknown enum value {instance!r}")

    declared_type = schema.get("type")
    if declared_type is not None and not _matches_type(instance, declared_type):
        _fail(path, f"has invalid type; expected {declared_type!r}")
    if instance is None:
        return

    if isinstance(instance, str):
        _validate_string(instance, schema, path)
    elif isinstance(instance, int) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            _fail(path, f"must be >= {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            _fail(path, f"must be <= {maximum}")
    elif isinstance(instance, Mapping):
        _validate_object(instance, schema, path, root)
    elif isinstance(instance, list):
        _validate_array(instance, schema, path, root)

    for subschema in schema.get("allOf", []):
        validate(instance, subschema, path=path, _root=root)
    one_of = schema.get("oneOf")
    if one_of is not None:
        matches = sum(_is_valid(instance, candidate, path, root) for candidate in one_of)
        if matches != 1:
            _fail(path, "must match exactly one oneOf branch")
    any_of = schema.get("anyOf")
    if any_of is not None and not any(
        _is_valid(instance, candidate, path, root) for candidate in any_of
    ):
        _fail(path, "must match at least one anyOf branch")
    negated = schema.get("not")
    if negated is not None and _is_valid(instance, negated, path, root):
        _fail(path, "must not match forbidden schema")
    condition = schema.get("if")
    if condition is not None:
        branch = (
            schema.get("then", {})
            if _is_valid(instance, condition, path, root)
            else schema.get("else", {})
        )
        validate(instance, branch, path=path, _root=root)


def _validate_string(value: str, schema: Mapping[str, Any], path: str) -> None:
    if len(value) < schema.get("minLength", 0):
        _fail(path, "is shorter than minLength")
    maximum = schema.get("maxLength")
    if maximum is not None and len(value) > maximum:
        _fail(path, "is longer than maxLength")
    pattern = schema.get("pattern")
    if pattern is not None and re.search(pattern, value) is None:
        _fail(path, "does not match pattern")
    value_format = schema.get("format")
    try:
        if value_format == "uuid":
            uuid.UUID(value)
        elif value_format == "date":
            date.fromisoformat(value)
        elif value_format == "date-time":
            if _RFC3339.fullmatch(value) is None:
                raise ValueError("date-time must use RFC3339 syntax")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if "T" not in value or parsed.tzinfo is None:
                raise ValueError("date-time must include time and timezone")
    except ValueError as exc:
        _fail(path, f"is not a valid {value_format}", cause=exc)


def _validate_object(
    value: Mapping[object, object],
    schema: Mapping[str, Any],
    path: str,
    root: Mapping[str, Any],
) -> None:
    if not all(isinstance(key, str) for key in value):
        _fail(path, "object keys must be strings")
    required = schema.get("required", [])
    for name in required:
        if name not in value:
            _fail(path, f"missing required property {name!r}")
    maximum = schema.get("maxProperties")
    if maximum is not None and len(value) > maximum:
        _fail(path, "has too many properties")
    minimum = schema.get("minProperties")
    if minimum is not None and len(value) < minimum:
        _fail(path, "has too few properties")
    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        assert isinstance(key, str)
        if key in properties:
            validate(item, properties[key], path=f"{path}.{key}", _root=root)
        elif additional is False:
            _fail(path, f"additional property {key!r} is forbidden")
        elif isinstance(additional, Mapping):
            validate(item, additional, path=f"{path}.{key}", _root=root)


def _validate_array(
    value: Sequence[object], schema: Mapping[str, Any], path: str, root: Mapping[str, Any]
) -> None:
    if len(value) < schema.get("minItems", 0):
        _fail(path, "has too few items")
    maximum = schema.get("maxItems")
    if maximum is not None and len(value) > maximum:
        _fail(path, "has too many items")
    if schema.get("uniqueItems") is True:
        for index, item in enumerate(value):
            if item in value[:index]:
                _fail(path, "contains duplicate items")
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            validate(item, item_schema, path=f"{path}[{index}]", _root=root)


def _matches_type(value: object, declared: object) -> bool:
    names = declared if isinstance(declared, (list, tuple)) else [declared]
    checks = {
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "string": lambda item: isinstance(item, str),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, Mapping),
    }
    return any(isinstance(name, str) and name in checks and checks[name](value) for name in names)


def _is_valid(value: object, schema: Mapping[str, Any], path: str, root: Mapping[str, Any]) -> bool:
    try:
        validate(value, schema, path=path, _root=root)
    except ContractValidationError:
        return False
    return True


def _fail(path: str, message: str, *, cause: Exception | None = None) -> None:
    error = ContractValidationError(f"{path}: {message}")
    if cause is None:
        raise error
    raise error from cause
