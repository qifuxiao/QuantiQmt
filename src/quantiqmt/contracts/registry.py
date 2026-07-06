"""Approved message schema registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from quantiqmt.contracts.errors import UnknownMessageTypeError, UnsupportedSchemaVersionError

_SCHEMA_PATHS = MappingProxyType(
    {
        "strategy.submit_order_intent.v1": "commands/strategy.submit_order_intent.v1.schema.json",
        "strategy.submit_target.v1": "commands/strategy.submit_target.v1.schema.json",
        "execution.cancel_order.v1": "commands/execution.cancel_order.v1.schema.json",
        "broker.trade_reported.v1": "events/broker.trade_reported.v1.schema.json",
        "oms.order_status_changed.v1": "events/oms.order_status_changed.v1.schema.json",
        "oms.order_registered.v1": "events/oms.order_registered.v1.schema.json",
        "risk.order_evaluated.v1": "events/risk.order_evaluated.v1.schema.json",
        "execution.attempt_started.v1": "events/execution.attempt_started.v1.schema.json",
        "execution.outcome_unknown.v1": "events/execution.outcome_unknown.v1.schema.json",
        "broker.order_reported.v1": "events/broker.order_reported.v1.schema.json",
        "ledger.trade_posted.v1": "events/ledger.trade_posted.v1.schema.json",
        "portfolio.position_changed.v1": "events/portfolio.position_changed.v1.schema.json",
    }
)


class SchemaRegistry:
    """Immutable registry loading the accepted schema snapshot once."""

    def __init__(self, schema_root: Path) -> None:
        self._schemas = MappingProxyType(
            {name: _load_schema(schema_root / relative) for name, relative in _SCHEMA_PATHS.items()}
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
    return MappingProxyType(document)
