"""Approved message schema registry backed only by installed package resources."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from quantiqmt.contracts.bundle import BundleIntegrityError, SchemaBundle
from quantiqmt.contracts.errors import UnknownMessageTypeError, UnsupportedSchemaVersionError
from quantiqmt.contracts.validation import validate


class SchemaRegistry:
    """Immutable registry loading the accepted schema snapshot once."""

    def __init__(self, schema_root: Path | None = None) -> None:
        # ``schema_root`` remains accepted for compatibility with existing callers, but is
        # deliberately ignored. Runtime contract authority is the verified installed bundle.
        del schema_root
        bundle = SchemaBundle.installed()
        routes = {
            cast(str, route["message_type"]): cast(str, route["path"]) for route in bundle.routes
        }
        self._schemas = MappingProxyType(
            {
                name: cast(Mapping[str, Any], bundle.contract_by_path(relative))
                for name, relative in routes.items()
            }
        )
        self._envelope = cast(Mapping[str, Any], bundle.contract("CONTRACT-MESSAGE-ENVELOPE-V1"))
        self._bundle = bundle
        self._contracts = MappingProxyType(
            {contract_id: bundle.contract(contract_id) for contract_id in bundle.contract_ids}
        )
        self._schema_uri_cache: dict[str, Mapping[str, Any]] = {}

    @classmethod
    def project_default(cls) -> SchemaRegistry:
        """Load the immutable installed resource (the name is retained for compatibility)."""
        return cls()

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

    def contract(self, contract_id: str) -> Any:
        """Return one canonical contract document from the verified bundle."""
        try:
            return self._contracts[contract_id]
        except KeyError as exc:
            raise BundleIntegrityError(
                f"contract is not present in installed bundle: {contract_id}"
            ) from exc

    def schema(self, contract_id: str) -> Mapping[str, Any]:
        """Return one Draft 2020-12 Schema from the verified bundle."""
        document = self.contract(contract_id)
        if not isinstance(document, Mapping) or document.get("$schema") != (
            "https://json-schema.org/draft/2020-12/schema"
        ):
            raise BundleIntegrityError(
                f"contract is not a Draft 2020-12 JSON Schema: {contract_id}"
            )
        return cast(Mapping[str, Any], document)

    def resolve_schema(self, uri: str) -> Mapping[str, Any]:
        """Resolve an absolute bundled Schema URI without filesystem or network access."""
        cached = self._schema_uri_cache.get(uri)
        if cached is None:
            cached = self._bundle.schema_by_uri(uri)
            self._schema_uri_cache[uri] = cached
        return cached

    def validate_contract(self, contract_id: str, candidate: object, *, path: str = "$") -> None:
        """Validate a candidate through the complete installed Schema graph."""
        validate(candidate, self.schema(contract_id), path=path, _resolver=self.resolve_schema)
