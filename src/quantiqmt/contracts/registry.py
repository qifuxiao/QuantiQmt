"""Approved message schema registry."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from quantiqmt.contracts.errors import (
    SchemaBundleError,
    UnknownMessageTypeError,
    UnsupportedSchemaVersionError,
)

_CATALOG_ENTRY = re.compile(r"name:\s*([^,}]+).*?schema:\s*([^,}]+).*?status:\s*active")
_EXPECTED_CATALOG_ID = "CONTRACT-CATALOG"
_EXPECTED_CATALOG_VERSION = 3
_RUNTIME_MANIFEST = "runtime-manifest.json"


class SchemaRegistry:
    """Immutable registry loading the accepted schema snapshot once."""

    def __init__(self, schema_root: Path | Traversable) -> None:
        self._root = schema_root
        routes = _active_routes(schema_root / "catalog.yaml")
        self._schemas = MappingProxyType(
            {name: _load_schema(schema_root / relative) for name, relative in routes.items()}
        )
        self._envelope = _load_schema(schema_root / "common/message-envelope.v1.schema.json")

    @classmethod
    def project_default(cls) -> SchemaRegistry:
        """Load schemas from a source checkout for development/spec tooling."""
        root = Path(__file__).resolve().parents[3] / "spec" / "contracts"
        return cls(root)

    @classmethod
    def runtime_default(cls) -> SchemaRegistry:
        """Load only the immutable schema bundle packaged with the distribution."""
        root = resources.files("quantiqmt.contracts.schema_bundle")
        try:
            manifest = json.loads((root / _RUNTIME_MANIFEST).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise SchemaBundleError("runtime schema manifest is missing or corrupt") from exc
        if (
            manifest.get("bundle_version") != 1
            or manifest.get("catalog_id") != _EXPECTED_CATALOG_ID
            or manifest.get("catalog_version") != _EXPECTED_CATALOG_VERSION
        ):
            raise SchemaBundleError("runtime schema manifest version mismatch")
        registry = cls(root)
        required = manifest.get("required_routes")
        if not isinstance(required, list) or any(
            route not in registry.message_types for route in required
        ):
            raise SchemaBundleError("runtime schema bundle is missing a required route")
        return registry

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

    def document(self, relative_path: str) -> Mapping[str, Any]:
        """Load a non-routed internal schema from the same immutable root."""
        return _load_schema(self._root / relative_path)

    @property
    def message_types(self) -> tuple[str, ...]:
        return tuple(self._schemas)

    def validator(self) -> SchemaValidator:
        return SchemaValidator(self)

    @property
    def _references(self) -> Mapping[str, Mapping[str, Any]]:
        return MappingProxyType(
            {
                schema["$id"]: schema
                for schema in self._schemas.values()
                if isinstance(schema.get("$id"), str)
            }
        )


class SchemaValidator:
    """Single schema → semantic validation boundary for all adapters."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    def validate_payload(
        self, message_type: str, schema_version: int, payload: Mapping[str, object]
    ) -> None:
        from quantiqmt.contracts.validation import validate

        validate(
            payload,
            self._registry.payload(message_type, schema_version),
            path="$.payload",
            references=self._registry._references,
        )

    def validate_schema(
        self, instance: object, schema: Mapping[str, Any], *, path: str = "$"
    ) -> None:
        from quantiqmt.contracts.validation import validate

        validate(instance, schema, path=path, references=self._registry._references)

    def validate_envelope(self, envelope: Mapping[str, object]) -> None:
        from quantiqmt.contracts.validation import validate

        validate(envelope, self._registry.envelope, references=self._registry._references)

    def validate_with_semantics(
        self,
        message_type: str,
        schema_version: int,
        payload: Mapping[str, object],
        semantic_validator: Callable[[Mapping[str, object]], None],
    ) -> None:
        self.validate_payload(message_type, schema_version, payload)
        semantic_validator(payload)


def _load_schema(path: Path | Traversable) -> Mapping[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            document = json.load(stream)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise SchemaBundleError(f"schema resource is missing or corrupt: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"schema root must be an object: {path}")
    return cast(Mapping[str, Any], _deep_freeze(document))


def _active_routes(path: Path | Traversable) -> dict[str, str]:
    routes: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise SchemaBundleError("contract catalog is missing") from exc
    catalog_id = re.search(r"^\s*id:\s*(\S+)", text, re.MULTILINE)
    catalog_version = re.search(r"^\s*version:\s*(\d+)", text, re.MULTILINE)
    if (
        catalog_id is None
        or catalog_id.group(1) != _EXPECTED_CATALOG_ID
        or catalog_version is None
        or int(catalog_version.group(1)) != _EXPECTED_CATALOG_VERSION
    ):
        raise SchemaBundleError("contract catalog id or version mismatch")
    for line in text.splitlines():
        match = _CATALOG_ENTRY.search(line)
        if match is not None:
            routes[match.group(1).strip()] = match.group(2).strip()
    if not routes:
        raise SchemaBundleError(f"catalog contains no active schema routes: {path}")
    return routes


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
