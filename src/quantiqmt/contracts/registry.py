"""Approved message schema registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from quantiqmt.contracts.errors import UnknownMessageTypeError, UnsupportedSchemaVersionError

_CATALOG_ENTRY = re.compile(r"name:\s*([^,}]+).*?schema:\s*([^,}]+).*?status:\s*active")


class SchemaRegistry:
    """Immutable registry loading the accepted schema snapshot once."""

    def __init__(self, schema_root: Path) -> None:
        routes = _active_routes(schema_root / "catalog.yaml")
        self._schemas = MappingProxyType(
            {name: _load_schema(schema_root / relative) for name, relative in routes.items()}
        )
        self._envelope = _load_schema(schema_root / "common/message-envelope.v1.schema.json")

    @classmethod
    def project_default(cls) -> SchemaRegistry:
        """Load schemas from this source checkout; deployments should pass an explicit root."""
        root = Path(__file__).resolve().parents[3] / "spec" / "contracts"
        return cls(root)

    @property
    def envelope(self) -> Mapping[str, Any]:
        return self._envelope

    def payload(self, message_type: str, schema_version: int) -> Mapping[str, Any]:
        expected_suffix = f".v{schema_version}"
        if not message_type.endswith(expected_suffix):
            raise UnsupportedSchemaVersionError(
                f"message type {message_type!r} does not match schema version {schema_version}"
            )
        try:
            return self._schemas[message_type]
        except KeyError as exc:
            if message_type.rsplit(".v", 1)[0] in {
                name.rsplit(".v", 1)[0] for name in self._schemas
            }:
                raise UnsupportedSchemaVersionError(
                    f"unsupported schema version for {message_type!r}"
                ) from exc
            raise UnknownMessageTypeError(f"unknown message type {message_type!r}") from exc

    @property
    def message_types(self) -> tuple[str, ...]:
        return tuple(self._schemas)


def _load_schema(path: Path) -> Mapping[str, Any]:
    with path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError(f"schema root must be an object: {path}")
    return cast(Mapping[str, Any], _deep_freeze(document))


def _active_routes(path: Path) -> dict[str, str]:
    routes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _CATALOG_ENTRY.search(line)
        if match is not None:
            routes[match.group(1).strip()] = match.group(2).strip()
    if not routes:
        raise ValueError(f"catalog contains no active schema routes: {path}")
    return routes


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
