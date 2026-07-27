"""Draft 2020-12 validation at the contract boundary.

The project previously carried a partial handwritten interpreter.  Runtime
contract validation must use the same standards-compliant implementation in
checkout and packaged deployments, so this module is deliberately a thin
adapter around :mod:`jsonschema`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver
from jsonschema.exceptions import SchemaError, ValidationError

from quantiqmt.contracts.errors import ContractValidationError

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def validate(
    instance: object,
    schema: Mapping[str, Any],
    *,
    path: str = "$",
    references: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Validate an instance with the complete Draft 2020-12 vocabulary.

    ``references`` contains externally-addressable schemas (for example the
    Risk decision schema references the v2 event schema by URN).  Local
    ``$ref`` values are resolved by the validator itself.  All schema and
    instance failures are mapped to the stable contract error type.
    """
    try:
        store = dict(references or {})
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            store.setdefault(schema_id, schema)
        resolver = RefResolver.from_schema(schema, store=store)
        Draft202012Validator(
            schema,
            resolver=resolver,
            format_checker=FormatChecker(),
        ).validate(instance)
    except (ValidationError, SchemaError, ValueError, TypeError) as exc:
        detail = str(exc).splitlines()[0]
        raise ContractValidationError(f"{path}: {detail}") from exc
