"""Immutable DTOs and canonical JSON codec."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from quantiqmt.contracts.errors import ContractValidationError
from quantiqmt.contracts.registry import SchemaRegistry
from quantiqmt.contracts.validation import JsonValue, validate


@dataclass(frozen=True, slots=True)
class ImmutablePayload(Mapping[str, object]):
    """Deeply immutable, schema-validated message payload."""

    message_type: str
    schema_version: int
    _values: Mapping[str, object]

    @classmethod
    def create(
        cls,
        message_type: str,
        schema_version: int,
        values: Mapping[str, object],
        registry: SchemaRegistry,
    ) -> ImmutablePayload:
        schema = registry.payload(message_type, schema_version)
        validate(values, schema, path="$.payload")
        return cls(message_type, schema_version, _freeze_mapping(values))

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def to_primitive(self) -> dict[str, JsonValue]:
        return _thaw_mapping(self._values)


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Immutable V1 envelope coupled to a validated payload version."""

    fields: Mapping[str, object]
    payload: ImmutablePayload

    @classmethod
    def create(cls, values: Mapping[str, object], registry: SchemaRegistry) -> MessageEnvelope:
        validate(values, registry.envelope)
        message_type = values.get("message_type")
        schema_version = values.get("schema_version")
        payload_value = values.get("payload")
        if not isinstance(message_type, str) or not isinstance(schema_version, int):
            raise ContractValidationError("invalid message type or schema version")
        if not isinstance(payload_value, Mapping):
            raise ContractValidationError("$.payload: must be an object")
        payload = ImmutablePayload.create(message_type, schema_version, payload_value, registry)
        fields = {key: value for key, value in values.items() if key != "payload"}
        return cls(_freeze_mapping(fields), payload)

    def to_primitive(self) -> dict[str, JsonValue]:
        result = _thaw_mapping(self.fields)
        result["payload"] = self.payload.to_primitive()
        return result


class MessageCodec:
    """Strict canonical UTF-8 JSON encoder and decoder."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    def decode(self, data: bytes | str) -> MessageEnvelope:
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractValidationError("invalid UTF-8 JSON message") from exc
        if not isinstance(value, dict):
            raise ContractValidationError("message root must be an object")
        return MessageEnvelope.create(value, self._registry)

    def encode(self, message: MessageEnvelope) -> bytes:
        return json.dumps(
            message.to_primitive(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[Any, Any]) -> Mapping[str, object]:
    if not all(isinstance(key, str) for key in value):
        raise ContractValidationError("object keys must be strings")
    return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})


def _thaw(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return _thaw_mapping(value)
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def _thaw_mapping(value: Mapping[str, object]) -> dict[str, JsonValue]:
    return {key: _thaw(item) for key, item in value.items()}
