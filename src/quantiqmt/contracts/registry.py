"""Approved message schema registry backed only by installed package resources."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from quantiqmt.contracts.bundle import SchemaBundle
from quantiqmt.contracts.errors import UnknownMessageTypeError, UnsupportedSchemaVersionError


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
        return self._bundle.contract(contract_id)
