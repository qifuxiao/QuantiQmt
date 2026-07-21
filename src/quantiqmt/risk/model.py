"""Immutable Risk DTOs, canonical JSON, and deterministic identities."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Literal, cast

JsonValue = None | bool | int | str | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
MutableJsonValue = (
    None | bool | int | str | list["MutableJsonValue"] | dict[str, "MutableJsonValue"]
)

RiskDecisionOutcome = Literal["PASS", "REJECT"]
RuleOutcome = Literal["PASS", "REJECT", "NOT_APPLICABLE"]
DecisionOrigin = Literal["EVALUATOR", "INPUT_GUARD", "TIMEOUT_GUARD"]
RulePhase = Literal[
    "INPUT_VALIDITY",
    "SNAPSHOT_VALIDITY",
    "SYSTEM_HARD_LIMIT",
    "SCOPED_RULE",
    "TIMEOUT_GUARD",
]
RuleScope = Literal["SYSTEM", "ACCOUNT", "PORTFOLIO", "STRATEGY", "INSTRUMENT"]

RISK_NAMESPACE = uuid.UUID("b5a6c3cc-2be0-5e6f-a9ec-2d9a4e769979")

ERROR_BY_REASON: Mapping[str, str] = MappingProxyType(
    {
        "RISK_RULE_BREACH": "QQ-RISK-4001",
        "RISK_HARD_LIMIT_BREACH": "QQ-RISK-4001",
        "RISK_TRADING_DISABLED": "QQ-RISK-4001",
        "RISK_INSTRUMENT_NOT_ALLOWED": "QQ-RISK-4001",
        "RISK_SNAPSHOT_STALE": "QQ-RISK-4002",
        "RISK_SNAPSHOT_PARTIAL": "QQ-RISK-4003",
        "RISK_SNAPSHOT_VERSION_MISMATCH": "QQ-RISK-4004",
        "RISK_EVALUATION_TIMEOUT": "QQ-RISK-4005",
        "RISK_SNAPSHOT_UNAVAILABLE": "QQ-RISK-4006",
        "RISK_RULE_SET_INVALID": "QQ-RISK-4007",
        "RISK_INPUT_INVALID": "QQ-RISK-4008",
        "RISK_REDUCTION_EVIDENCE_INVALID": "QQ-RISK-4009",
        "RISK_SNAPSHOT_TIMEOUT": "QQ-RISK-4010",
        "RISK_RULE_SET_VERSION_MISMATCH": "QQ-RISK-4011",
    }
)


class RiskContractError(ValueError):
    """Fail-closed risk contract error carrying its canonical code."""

    def __init__(self, code: str, reason_code: str, detail: str) -> None:
        super().__init__(f"{code}: {reason_code}: {detail}")
        self.code = code
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class RiskInputV1:
    values: Mapping[str, JsonValue]

    @classmethod
    def create(cls, values: Mapping[str, object]) -> RiskInputV1:
        frozen = _as_frozen_mapping(freeze_json(values))
        primitive = _as_mutable_mapping(thaw_json(frozen))
        actual_hash = hash_without(primitive, "input_version")
        declared = primitive.get("input_version")
        if declared != actual_hash:
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "input_version mismatch")
        return cls(frozen)

    @classmethod
    def unchecked(cls, values: Mapping[str, object]) -> RiskInputV1:
        return cls(_as_frozen_mapping(freeze_json(values)))

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return cast(dict[str, MutableJsonValue], thaw_json(self.values))


@dataclass(frozen=True, slots=True)
class RiskRuleSetV1:
    values: Mapping[str, JsonValue]

    @classmethod
    def create(cls, values: Mapping[str, object]) -> RiskRuleSetV1:
        frozen = _as_frozen_mapping(freeze_json(values))
        primitive = _as_mutable_mapping(thaw_json(frozen))
        actual_hash = hash_without(primitive, "content_hash")
        declared = primitive.get("content_hash")
        if declared != actual_hash:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "content_hash mismatch"
            )
        policy_hash = hard_limit_policy_hash(primitive)
        if primitive.get("hard_limit_policy_hash") != policy_hash:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "hard_limit_policy_hash mismatch"
            )
        return cls(frozen)

    @classmethod
    def unchecked(cls, values: Mapping[str, object]) -> RiskRuleSetV1:
        return cls(_as_frozen_mapping(freeze_json(values)))

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return cast(dict[str, MutableJsonValue], thaw_json(self.values))


@dataclass(frozen=True, slots=True)
class RuleResult:
    evaluation_index: int
    rule_id: str
    phase: RulePhase
    scope: RuleScope
    scope_id: str | None
    priority: int
    metric: str | None
    result: RuleOutcome
    reason_code: str
    measured_value: Mapping[str, JsonValue] | None
    limit_value: Mapping[str, JsonValue] | None
    exception_applied: bool = False

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return {
            "evaluation_index": self.evaluation_index,
            "rule_id": self.rule_id,
            "phase": self.phase,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "priority": self.priority,
            "metric": self.metric,
            "result": self.result,
            "reason_code": self.reason_code,
            "measured_value": thaw_json(self.measured_value)
            if self.measured_value is not None
            else None,
            "limit_value": thaw_json(self.limit_value) if self.limit_value is not None else None,
            "exception_applied": self.exception_applied,
        }


@dataclass(frozen=True, slots=True)
class RuleTiming:
    evaluation_index: int
    rule_id: str
    latency_us: int

    def to_primitive(self) -> dict[str, int | str]:
        return {
            "evaluation_index": self.evaluation_index,
            "rule_id": self.rule_id,
            "latency_us": self.latency_us,
        }


@dataclass(frozen=True, slots=True)
class RiskDecisionV1:
    decision_id: str
    decision_origin: DecisionOrigin
    input_version: str
    semantic_decision_hash: str
    order_id: str
    expected_order_version: int
    decision: RiskDecisionOutcome
    primary_reason_code: str
    error_code: str | None
    rule_set_version: str
    rule_set_hash: str
    snapshot_states: Mapping[str, JsonValue]
    rule_results: tuple[RuleResult, ...]

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return {
            "schema_version": 1,
            "decision_id": self.decision_id,
            "decision_origin": self.decision_origin,
            "input_version": self.input_version,
            "semantic_decision_hash": self.semantic_decision_hash,
            "order_id": self.order_id,
            "expected_order_version": self.expected_order_version,
            "decision": self.decision,
            "primary_reason_code": self.primary_reason_code,
            "error_code": self.error_code,
            "rule_set_version": self.rule_set_version,
            "rule_set_hash": self.rule_set_hash,
            "snapshot_states": thaw_json(self.snapshot_states),
            "rule_results": [result.to_primitive() for result in self.rule_results],
        }


@dataclass(frozen=True, slots=True)
class RiskAuditOutputV1:
    decision: RiskDecisionV1
    evaluated_at: str
    total_latency_us: int
    evaluation_timeout_us: int
    completed_rule_count: int
    rule_timings: tuple[RuleTiming, ...]

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return {
            "schema_version": 1,
            "decision": self.decision.to_primitive(),
            "evaluated_at": self.evaluated_at,
            "total_latency_us": self.total_latency_us,
            "evaluation_timeout_us": self.evaluation_timeout_us,
            "completed_rule_count": self.completed_rule_count,
            "rule_timings": [
                cast(dict[str, MutableJsonValue], timing.to_primitive())
                for timing in self.rule_timings
            ],
        }


def canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        _normalize_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_lower_hex(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def hash_without(values: Mapping[str, object], excluded_key: str) -> str:
    return sha256_lower_hex(
        canonical_json_bytes({key: item for key, item in values.items() if key != excluded_key})
    )


def hard_limit_policy_hash(rule_set: Mapping[str, object]) -> str:
    return sha256_lower_hex(
        canonical_json_bytes(
            {
                "hard_limit_policy_version": rule_set["hard_limit_policy_version"],
                "valuation_currency": rule_set["valuation_currency"],
                "system_hard_limits": rule_set["system_hard_limits"],
            }
        )
    )


def decision_id(input_version: str, content_hash: str) -> str:
    return str(uuid.uuid5(RISK_NAMESPACE, f"{input_version}:{content_hash}"))


def v2_message_id(decision_identifier: str) -> str:
    return str(uuid.uuid5(RISK_NAMESPACE, f"{decision_identifier}:risk.order_evaluated.v2"))


def semantic_decision_hash(decision: Mapping[str, object]) -> str:
    return sha256_lower_hex(
        canonical_json_bytes(
            {
                key: value
                for key, value in decision.items()
                if key not in {"decision_id", "semantic_decision_hash"}
            }
        )
    )


def decimal_value(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{field} must be decimal")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RiskContractError(
            "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{field} invalid decimal"
        ) from exc
    return parsed


def ceil_div_us(delta_ns: int) -> int:
    if delta_ns <= 0:
        return 0
    return (delta_ns + 999) // 1000


def rfc3339_z(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "timestamp must use UTC Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "invalid timestamp") from exc
    return parsed.astimezone(UTC)


def quantize_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING), "f")


def typed_decimal(value: Decimal | str, currency: str | None) -> Mapping[str, JsonValue]:
    decimal_string = str(value) if isinstance(value, str) else quantize_money(value)
    return MappingProxyType({"kind": "DECIMAL", "value": decimal_string, "currency": currency})


def typed_integer(value: int) -> Mapping[str, JsonValue]:
    return MappingProxyType({"kind": "INTEGER", "value": value})


def typed_boolean(value: bool) -> Mapping[str, JsonValue]:
    return MappingProxyType({"kind": "BOOLEAN", "value": value})


def typed_string(value: str) -> Mapping[str, JsonValue]:
    return MappingProxyType({"kind": "STRING", "value": value})


def typed_string_set(values: tuple[str, ...]) -> Mapping[str, JsonValue]:
    return MappingProxyType({"kind": "STRING_SET", "values": tuple(sorted(set(values)))})


def freeze_json(value: object) -> JsonValue:
    normalized = _normalize_json(value)
    return _freeze_normalized(normalized)


def thaw_json(value: object) -> MutableJsonValue:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def _normalize_json(value: object) -> MutableJsonValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "float is forbidden")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "object keys must be strings"
            )
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_normalize_json(item) for item in value]
    raise RiskContractError(
        "QQ-RISK-4008", "RISK_INPUT_INVALID", f"unsupported JSON value {type(value).__name__}"
    )


def _freeze_normalized(value: MutableJsonValue) -> JsonValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_normalized(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_normalized(item) for item in value)
    return value


def _as_frozen_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "root must be object")
    return value


def _as_mutable_mapping(value: MutableJsonValue) -> dict[str, MutableJsonValue]:
    if not isinstance(value, dict):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "root must be object")
    return value
