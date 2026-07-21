"""Immutable Risk DTOs, canonical JSON, and deterministic identities."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
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


@dataclass(frozen=True, slots=True, init=False)
class RiskInputV1:
    values: Mapping[str, JsonValue]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RiskInputV1 must be constructed with RiskInputV1.create()")

    @classmethod
    def create(cls, values: Mapping[str, object]) -> RiskInputV1:
        frozen = _as_frozen_mapping(freeze_json(values))
        primitive = _as_mutable_mapping(thaw_json(frozen))
        _validate_schema(
            "risk-input.v1.schema.json", primitive, "QQ-RISK-4008", "RISK_INPUT_INVALID"
        )
        actual_hash = hash_without(primitive, "input_version")
        declared = primitive.get("input_version")
        if declared != actual_hash:
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "input_version mismatch")
        return cls._from_frozen(frozen)

    @classmethod
    def unchecked(cls, values: Mapping[str, object]) -> RiskInputV1:
        del values
        raise TypeError("RiskInputV1.unchecked() is forbidden")

    @classmethod
    def _from_frozen(cls, values: Mapping[str, JsonValue]) -> RiskInputV1:
        instance = object.__new__(cls)
        object.__setattr__(instance, "values", values)
        return instance

    def to_primitive(self) -> dict[str, MutableJsonValue]:
        return cast(dict[str, MutableJsonValue], thaw_json(self.values))


@dataclass(frozen=True, slots=True, init=False)
class AcceptedHardPolicy:
    version: str
    valuation_currency: str
    system_hard_limits: Mapping[str, JsonValue]
    policy_hash: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("AcceptedHardPolicy must be constructed with AcceptedHardPolicy.create()")

    @classmethod
    def create(
        cls,
        *,
        version: str,
        valuation_currency: str,
        system_hard_limits: Mapping[str, object],
        policy_hash: str | None = None,
    ) -> AcceptedHardPolicy:
        payload = {
            "hard_limit_policy_version": version,
            "valuation_currency": valuation_currency,
            "system_hard_limits": _as_mutable_mapping(thaw_json(freeze_json(system_hard_limits))),
        }
        actual_hash = hard_limit_policy_hash(payload)
        if policy_hash is not None and policy_hash != actual_hash:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "accepted hard policy hash mismatch"
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "version", version)
        object.__setattr__(instance, "valuation_currency", valuation_currency)
        object.__setattr__(
            instance, "system_hard_limits", _as_frozen_mapping(freeze_json(system_hard_limits))
        )
        object.__setattr__(instance, "policy_hash", actual_hash)
        return instance

    def to_policy_payload(self) -> dict[str, MutableJsonValue]:
        return {
            "hard_limit_policy_version": self.version,
            "valuation_currency": self.valuation_currency,
            "system_hard_limits": thaw_json(self.system_hard_limits),
        }


@dataclass(frozen=True, slots=True, init=False)
class RiskRuleSetV1:
    values: Mapping[str, JsonValue]
    accepted_hard_policy: AcceptedHardPolicy

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RiskRuleSetV1 must be constructed with RiskRuleSetV1.create()")

    @classmethod
    def create(
        cls, values: Mapping[str, object], *, accepted_hard_policy: AcceptedHardPolicy
    ) -> RiskRuleSetV1:
        frozen = _as_frozen_mapping(freeze_json(values))
        primitive = _as_mutable_mapping(thaw_json(frozen))
        _validate_schema(
            "rule-set.v1.schema.json", primitive, "QQ-RISK-4007", "RISK_RULE_SET_INVALID"
        )
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
        if primitive.get("hard_limit_policy_version") != accepted_hard_policy.version:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy version"
            )
        if primitive.get("valuation_currency") != accepted_hard_policy.valuation_currency:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy currency"
            )
        if policy_hash != accepted_hard_policy.policy_hash:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy content"
            )
        accepted_limits = accepted_hard_policy.to_policy_payload()["system_hard_limits"]
        if primitive.get("system_hard_limits") != accepted_limits:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy limits"
            )
        return cls._from_frozen(frozen, accepted_hard_policy)

    @classmethod
    def unchecked(cls, values: Mapping[str, object]) -> RiskRuleSetV1:
        del values
        raise TypeError("RiskRuleSetV1.unchecked() is forbidden")

    @classmethod
    def _from_frozen(
        cls, values: Mapping[str, JsonValue], accepted_hard_policy: AcceptedHardPolicy
    ) -> RiskRuleSetV1:
        instance = object.__new__(cls)
        object.__setattr__(instance, "values", values)
        object.__setattr__(instance, "accepted_hard_policy", accepted_hard_policy)
        return instance

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

    def __post_init__(self) -> None:
        if self.measured_value is not None:
            object.__setattr__(
                self, "measured_value", _as_frozen_mapping(freeze_json(self.measured_value))
            )
        if self.limit_value is not None:
            object.__setattr__(
                self, "limit_value", _as_frozen_mapping(freeze_json(self.limit_value))
            )

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "snapshot_states", _as_frozen_mapping(freeze_json(self.snapshot_states))
        )
        object.__setattr__(self, "rule_results", tuple(self.rule_results))

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

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_timings", tuple(self.rule_timings))

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


def hash_snapshot_without_metadata_checksum(snapshot: Mapping[str, object]) -> str:
    mutable = _as_mutable_mapping(thaw_json(freeze_json(snapshot)))
    metadata = mutable.get("metadata")
    if not isinstance(metadata, dict):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "metadata must be object")
    metadata.pop("checksum", None)
    return sha256_lower_hex(canonical_json_bytes(mutable))


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


def _validate_schema(
    schema_file: str, payload: Mapping[str, object], code: str, reason_code: str
) -> None:
    try:
        if schema_file == "risk-input.v1.schema.json":
            _validate_risk_input_schema(payload)
        elif schema_file == "rule-set.v1.schema.json":
            _validate_rule_set_schema(payload)
        else:  # pragma: no cover - fixed internal call sites
            raise ValueError(f"unknown risk schema {schema_file}")
    except _SchemaError as exc:
        raise RiskContractError(code, reason_code, exc.detail) from exc


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


_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.ASCII,
)
_CURRENCY = re.compile(r"^[A-Z]{3}$", re.ASCII)
_DECIMAL = re.compile(r"^-?(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?$", re.ASCII)
_NON_NEG_DECIMAL = re.compile(r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?$", re.ASCII)
_POSITIVE_DECIMAL = re.compile(r"^(?=.*[1-9])(0|[1-9][0-9]{0,17})(\.[0-9]{1,8})?$", re.ASCII)
_RULE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,127}$", re.ASCII)


class _SchemaError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _validate_risk_input_schema(payload: Mapping[str, object]) -> None:
    _exact_keys(
        payload,
        {
            "schema_version",
            "input_version",
            "evaluation_time",
            "valuation_currency",
            "rule_set_version",
            "rule_set_hash",
            "order",
            "account",
            "portfolio",
            "market",
        },
        "$",
    )
    _const(payload["schema_version"], 1, "$.schema_version")
    _pattern(payload["input_version"], _HEX64, "$.input_version")
    _date_time_z(payload["evaluation_time"], "$.evaluation_time")
    _pattern(payload["valuation_currency"], _CURRENCY, "$.valuation_currency")
    _bounded_string(payload["rule_set_version"], "$.rule_set_version", 1, 64)
    _pattern(payload["rule_set_hash"], _HEX64, "$.rule_set_hash")
    _validate_order_schema(_object(payload["order"], "$.order"))
    _validate_account_schema(_object(payload["account"], "$.account"))
    _validate_portfolio_schema(_object(payload["portfolio"], "$.portfolio"))
    _validate_market_schema(_object(payload["market"], "$.market"))


def _validate_rule_set_schema(payload: Mapping[str, object]) -> None:
    _exact_keys(
        payload,
        {
            "schema_version",
            "rule_set_id",
            "rule_set_version",
            "content_hash",
            "valuation_currency",
            "hard_limit_policy_version",
            "hard_limit_policy_hash",
            "evaluation_timeout_us",
            "freshness_limits_ms",
            "system_hard_limits",
            "reduce_only_policy",
            "rules",
        },
        "$",
    )
    _const(payload["schema_version"], 1, "$.schema_version")
    _pattern(payload["rule_set_id"], _UUID, "$.rule_set_id")
    _bounded_string(payload["rule_set_version"], "$.rule_set_version", 1, 64)
    _pattern(payload["content_hash"], _HEX64, "$.content_hash")
    _pattern(payload["valuation_currency"], _CURRENCY, "$.valuation_currency")
    _bounded_string(payload["hard_limit_policy_version"], "$.hard_limit_policy_version", 1, 64)
    _pattern(payload["hard_limit_policy_hash"], _HEX64, "$.hard_limit_policy_hash")
    _integer_range(payload["evaluation_timeout_us"], "$.evaluation_timeout_us", 1, 4000)
    _validate_freshness_limits(_object(payload["freshness_limits_ms"], "$.freshness_limits_ms"))
    _validate_hard_limits(_object(payload["system_hard_limits"], "$.system_hard_limits"))
    _validate_reduce_policy(_object(payload["reduce_only_policy"], "$.reduce_only_policy"))
    rules = _array(payload["rules"], "$.rules", 0, 4096)
    for index, rule in enumerate(rules):
        _validate_rule_schema(_object(rule, f"$.rules[{index}]"), f"$.rules[{index}]")


def _validate_order_schema(order: Mapping[str, object]) -> None:
    _exact_keys(
        order,
        {
            "schema_version",
            "checksum",
            "order_id",
            "aggregate_version",
            "intent_id",
            "account_id",
            "portfolio_id",
            "strategy_id",
            "strategy_version",
            "instrument_id",
            "side",
            "position_effect",
            "order_type",
            "quantity",
            "limit_price",
            "time_in_force",
            "registered_at",
            "market_data_version",
            "risk_effect",
            "reduction_evidence",
        },
        "$.order",
    )
    _const(order["schema_version"], 1, "$.order.schema_version")
    _pattern(order["checksum"], _HEX64, "$.order.checksum")
    _pattern(order["order_id"], _UUID, "$.order.order_id")
    _integer_range(order["aggregate_version"], "$.order.aggregate_version", 1, None)
    _pattern(order["intent_id"], _UUID, "$.order.intent_id")
    for field, max_length in (
        ("account_id", 128),
        ("portfolio_id", 128),
        ("strategy_id", 128),
        ("strategy_version", 64),
        ("instrument_id", 64),
        ("market_data_version", 128),
    ):
        _bounded_string(order[field], f"$.order.{field}", 1, max_length)
    _enum(order["side"], {"BUY", "SELL"}, "$.order.side")
    _enum(order["position_effect"], {"OPEN", "CLOSE", "AUTO"}, "$.order.position_effect")
    _enum(order["order_type"], {"LIMIT", "MARKET", "BEST"}, "$.order.order_type")
    _integer_range(order["quantity"], "$.order.quantity", 1, None)
    if order["limit_price"] is not None:
        _pattern(order["limit_price"], _POSITIVE_DECIMAL, "$.order.limit_price")
    if order["order_type"] == "LIMIT" and not isinstance(order["limit_price"], str):
        raise _SchemaError("$.order.limit_price: LIMIT requires decimal string")
    _enum(order["time_in_force"], {"DAY", "IOC", "FOK"}, "$.order.time_in_force")
    _date_time_z(order["registered_at"], "$.order.registered_at")
    _enum(order["risk_effect"], {"INCREASE", "REDUCE", "UNKNOWN"}, "$.order.risk_effect")
    if order["risk_effect"] == "REDUCE":
        _validate_reduction_evidence(
            _object(order["reduction_evidence"], "$.order.reduction_evidence")
        )
    elif order["reduction_evidence"] is not None:
        raise _SchemaError("$.order.reduction_evidence: must be null unless REDUCE")


def _validate_snapshot_metadata(metadata: Mapping[str, object], path: str) -> None:
    _exact_keys(
        metadata,
        {
            "source",
            "snapshot_version",
            "schema_version",
            "aggregate_version",
            "as_of",
            "trading_day",
            "quality",
            "missing_fields",
            "checksum",
        },
        path,
    )
    _bounded_string(metadata["source"], f"{path}.source", 1, 128)
    _bounded_string(metadata["snapshot_version"], f"{path}.snapshot_version", 1, 128)
    _const(metadata["schema_version"], 1, f"{path}.schema_version")
    if metadata["aggregate_version"] is not None:
        _integer_range(metadata["aggregate_version"], f"{path}.aggregate_version", 1, None)
    _date_time_z(metadata["as_of"], f"{path}.as_of")
    _date_value(metadata["trading_day"], f"{path}.trading_day")
    _enum(
        metadata["quality"],
        {"FRESH", "STALE", "PARTIAL", "TIMEOUT", "UNAVAILABLE"},
        f"{path}.quality",
    )
    missing = _array(metadata["missing_fields"], f"{path}.missing_fields", 0, 64)
    _unique_items(missing, f"{path}.missing_fields")
    for index, item in enumerate(missing):
        _bounded_string(item, f"{path}.missing_fields[{index}]", 1, 128)
    if metadata["quality"] in {"FRESH", "STALE"} and missing:
        raise _SchemaError(f"{path}.missing_fields: must be empty for {metadata['quality']}")
    if metadata["quality"] == "PARTIAL" and not missing:
        raise _SchemaError(f"{path}.missing_fields: must be non-empty for PARTIAL")
    _pattern(metadata["checksum"], _HEX64, f"{path}.checksum")


def _validate_account_schema(account: Mapping[str, object]) -> None:
    _exact_keys(
        account,
        {
            "metadata",
            "account_id",
            "currency",
            "equity",
            "available_cash",
            "projected_available_cash",
            "margin_used",
            "daily_loss",
            "open_order_notional",
        },
        "$.account",
    )
    _validate_snapshot_metadata(
        _object(account["metadata"], "$.account.metadata"), "$.account.metadata"
    )
    _bounded_string(account["account_id"], "$.account.account_id", 1, 128)
    _pattern(account["currency"], _CURRENCY, "$.account.currency")
    for field in (
        "equity",
        "available_cash",
        "projected_available_cash",
        "margin_used",
        "daily_loss",
        "open_order_notional",
    ):
        _nullable_decimal(account[field], f"$.account.{field}")


def _validate_portfolio_schema(portfolio: Mapping[str, object]) -> None:
    _exact_keys(
        portfolio,
        {"metadata", "portfolio_id", "account_id", "base_currency", "scope_metrics"},
        "$.portfolio",
    )
    _validate_snapshot_metadata(
        _object(portfolio["metadata"], "$.portfolio.metadata"), "$.portfolio.metadata"
    )
    _bounded_string(portfolio["portfolio_id"], "$.portfolio.portfolio_id", 1, 128)
    _bounded_string(portfolio["account_id"], "$.portfolio.account_id", 1, 128)
    _pattern(portfolio["base_currency"], _CURRENCY, "$.portfolio.base_currency")
    rows = _array(portfolio["scope_metrics"], "$.portfolio.scope_metrics", 4, 4)
    for index, row in enumerate(rows):
        _validate_scope_metric_schema(
            _object(row, f"$.portfolio.scope_metrics[{index}]"),
            f"$.portfolio.scope_metrics[{index}]",
        )


def _validate_scope_metric_schema(row: Mapping[str, object], path: str) -> None:
    _exact_keys(
        row,
        {
            "scope",
            "scope_id",
            "enabled",
            "position_quantity",
            "projected_position_quantity",
            "projected_gross_exposure",
            "projected_net_exposure",
            "projected_leverage",
            "activity_window_ms",
            "order_count_window",
            "cancel_ratio_bps",
        },
        path,
    )
    _enum(row["scope"], {"ACCOUNT", "PORTFOLIO", "STRATEGY", "INSTRUMENT"}, f"{path}.scope")
    _bounded_string(row["scope_id"], f"{path}.scope_id", 1, 128)
    if row["enabled"] is not None and not isinstance(row["enabled"], bool):
        raise _SchemaError(f"{path}.enabled: must be boolean or null")
    for field in ("position_quantity", "projected_position_quantity", "order_count_window"):
        if row[field] is not None:
            _integer_range(
                row[field], f"{path}.{field}", 0 if field == "order_count_window" else None, None
            )
    _nullable_decimal(row["projected_gross_exposure"], f"{path}.projected_gross_exposure")
    _nullable_decimal(row["projected_net_exposure"], f"{path}.projected_net_exposure")
    _nullable_decimal(row["projected_leverage"], f"{path}.projected_leverage")
    _integer_range(row["activity_window_ms"], f"{path}.activity_window_ms", 1, 86_400_000)
    if row["cancel_ratio_bps"] is not None:
        _integer_range(row["cancel_ratio_bps"], f"{path}.cancel_ratio_bps", 0, 10_000)


def _validate_market_schema(market: Mapping[str, object]) -> None:
    _exact_keys(
        market,
        {
            "metadata",
            "instrument_id",
            "trading_status",
            "currency",
            "risk_price",
            "risk_price_source",
            "reference_price",
            "price_deviation_bps",
            "upper_price_limit",
            "lower_price_limit",
        },
        "$.market",
    )
    _validate_snapshot_metadata(
        _object(market["metadata"], "$.market.metadata"), "$.market.metadata"
    )
    _bounded_string(market["instrument_id"], "$.market.instrument_id", 1, 64)
    _enum(
        market["trading_status"],
        {"TRADING", "HALTED", "SUSPENDED", "CLOSED", "UNKNOWN"},
        "$.market.trading_status",
    )
    _pattern(market["currency"], _CURRENCY, "$.market.currency")
    for field in ("risk_price", "reference_price", "upper_price_limit", "lower_price_limit"):
        if market[field] is not None:
            _pattern(market[field], _POSITIVE_DECIMAL, f"$.market.{field}")
    _enum(
        market["risk_price_source"],
        {"LIMIT_PRICE", "MARKET_WORST_CASE", "UNAVAILABLE"},
        "$.market.risk_price_source",
    )
    if market["price_deviation_bps"] is not None:
        _integer_range(market["price_deviation_bps"], "$.market.price_deviation_bps", 0, None)


def _validate_reduction_evidence(evidence: Mapping[str, object]) -> None:
    _exact_keys(
        evidence,
        {
            "classification",
            "position_snapshot_version",
            "position_quantity_before",
            "reserved_reduce_quantity",
            "max_reducible_quantity",
            "projected_position_quantity",
            "would_flip_position",
        },
        "$.order.reduction_evidence",
    )
    _const(
        evidence["classification"],
        "VERIFIED_REDUCE_ONLY",
        "$.order.reduction_evidence.classification",
    )
    _bounded_string(
        evidence["position_snapshot_version"],
        "$.order.reduction_evidence.position_snapshot_version",
        1,
        128,
    )
    _integer_range(
        evidence["position_quantity_before"],
        "$.order.reduction_evidence.position_quantity_before",
        None,
        None,
    )
    _integer_range(
        evidence["reserved_reduce_quantity"],
        "$.order.reduction_evidence.reserved_reduce_quantity",
        0,
        None,
    )
    _integer_range(
        evidence["max_reducible_quantity"],
        "$.order.reduction_evidence.max_reducible_quantity",
        0,
        None,
    )
    _integer_range(
        evidence["projected_position_quantity"],
        "$.order.reduction_evidence.projected_position_quantity",
        None,
        None,
    )
    _const(evidence["would_flip_position"], False, "$.order.reduction_evidence.would_flip_position")


def _validate_freshness_limits(limits: Mapping[str, object]) -> None:
    _exact_keys(limits, {"account", "portfolio", "market"}, "$.freshness_limits_ms")
    for key in ("account", "portfolio", "market"):
        _integer_range(limits[key], f"$.freshness_limits_ms.{key}", 0, 86_400_000)


def _validate_hard_limits(limits: Mapping[str, object]) -> None:
    _exact_keys(
        limits,
        {
            "allow_new_risk",
            "max_order_quantity",
            "max_order_notional",
            "max_price_deviation_bps",
            "max_projected_gross_exposure",
            "max_projected_net_exposure_abs",
            "max_projected_leverage",
            "max_daily_loss",
            "activity_window_ms",
            "max_order_count_window",
            "max_cancel_ratio_bps",
        },
        "$.system_hard_limits",
    )
    if not isinstance(limits["allow_new_risk"], bool):
        raise _SchemaError("$.system_hard_limits.allow_new_risk: must be boolean")
    for field in ("max_order_quantity", "activity_window_ms", "max_order_count_window"):
        _integer_range(
            limits[field],
            f"$.system_hard_limits.{field}",
            1,
            86_400_000 if field == "activity_window_ms" else None,
        )
    _integer_range(
        limits["max_price_deviation_bps"], "$.system_hard_limits.max_price_deviation_bps", 0, None
    )
    _integer_range(
        limits["max_cancel_ratio_bps"], "$.system_hard_limits.max_cancel_ratio_bps", 0, 10_000
    )
    for field in (
        "max_order_notional",
        "max_projected_gross_exposure",
        "max_projected_net_exposure_abs",
        "max_projected_leverage",
        "max_daily_loss",
    ):
        _pattern(limits[field], _NON_NEG_DECIMAL, f"$.system_hard_limits.{field}")


def _validate_reduce_policy(policy: Mapping[str, object]) -> None:
    _exact_keys(policy, {"enabled", "exempt_rule_ids"}, "$.reduce_only_policy")
    if not isinstance(policy["enabled"], bool):
        raise _SchemaError("$.reduce_only_policy.enabled: must be boolean")
    exempt = _array(policy["exempt_rule_ids"], "$.reduce_only_policy.exempt_rule_ids", 0, 256)
    _unique_items(exempt, "$.reduce_only_policy.exempt_rule_ids")
    for index, rule_id in enumerate(exempt):
        _pattern(rule_id, _RULE_ID, f"$.reduce_only_policy.exempt_rule_ids[{index}]")


def _validate_rule_schema(rule: Mapping[str, object], path: str) -> None:
    _exact_keys(
        rule,
        {
            "rule_id",
            "scope",
            "scope_id",
            "priority",
            "metric",
            "operator",
            "limit",
            "reduction_exception",
        },
        path,
    )
    _pattern(rule["rule_id"], _RULE_ID, f"{path}.rule_id")
    _enum(
        rule["scope"], {"SYSTEM", "ACCOUNT", "PORTFOLIO", "STRATEGY", "INSTRUMENT"}, f"{path}.scope"
    )
    if rule["scope"] == "SYSTEM":
        if rule["scope_id"] is not None:
            raise _SchemaError(f"{path}.scope_id: SYSTEM requires null")
    else:
        _bounded_string(rule["scope_id"], f"{path}.scope_id", 1, 128)
    _integer_range(rule["priority"], f"{path}.priority", 0, 1_000_000)
    _enum(
        rule["metric"],
        {
            "TRADING_ENABLED",
            "INSTRUMENT_ALLOWED",
            "ORDER_QUANTITY",
            "ORDER_NOTIONAL",
            "PRICE_DEVIATION_BPS",
            "AVAILABLE_CASH",
            "POSITION_QUANTITY",
            "PROJECTED_GROSS_EXPOSURE",
            "PROJECTED_NET_EXPOSURE_ABS",
            "PROJECTED_LEVERAGE",
            "DAILY_LOSS",
            "ORDER_COUNT_WINDOW",
            "CANCEL_RATIO_BPS",
        },
        f"{path}.metric",
    )
    _enum(rule["operator"], {"BOOLEAN_TRUE", "IN_SET", "MAX", "MIN"}, f"{path}.operator")
    _validate_limit_schema(_object(rule["limit"], f"{path}.limit"), f"{path}.limit")
    _enum(
        rule["reduction_exception"], {"NEVER", "ALLOW_IF_VERIFIED"}, f"{path}.reduction_exception"
    )


def _validate_limit_schema(limit: Mapping[str, object], path: str) -> None:
    kind = limit.get("kind")
    if kind == "DECIMAL":
        _exact_keys(limit, {"kind", "value", "currency"}, path)
        _pattern(limit["value"], _NON_NEG_DECIMAL, f"{path}.value")
        if limit["currency"] is not None:
            _pattern(limit["currency"], _CURRENCY, f"{path}.currency")
        return
    if kind == "INTEGER":
        _exact_keys(limit, {"kind", "value"}, path)
        _integer_range(limit["value"], f"{path}.value", 0, None)
        return
    if kind == "BOOLEAN":
        _exact_keys(limit, {"kind", "value"}, path)
        if not isinstance(limit["value"], bool):
            raise _SchemaError(f"{path}.value: must be boolean")
        return
    if kind == "STRING_SET":
        _exact_keys(limit, {"kind", "values"}, path)
        values = _array(limit["values"], f"{path}.values", 1, 10_000)
        _unique_items(values, f"{path}.values")
        for index, value in enumerate(values):
            _bounded_string(value, f"{path}.values[{index}]", 1, 128)
        return
    raise _SchemaError(f"{path}: must match exactly one limit branch")


def _exact_keys(value: Mapping[str, object], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise _SchemaError(f"{path}: missing required property {sorted(missing)[0]!r}")
    if extra:
        raise _SchemaError(f"{path}: additional property {sorted(extra)[0]!r} is forbidden")


def _object(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _SchemaError(f"{path}: must be object")
    if not all(isinstance(key, str) for key in value):
        raise _SchemaError(f"{path}: object keys must be strings")
    return cast(Mapping[str, object], value)


def _array(value: object, path: str, minimum: int, maximum: int) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise _SchemaError(f"{path}: must be array")
    items = tuple(value)
    if len(items) < minimum:
        raise _SchemaError(f"{path}: has too few items")
    if len(items) > maximum:
        raise _SchemaError(f"{path}: has too many items")
    return items


def _unique_items(values: tuple[object, ...], path: str) -> None:
    seen: set[str] = set()
    for value in values:
        canonical = json.dumps(_normalize_json(value), sort_keys=True, separators=(",", ":"))
        if canonical in seen:
            raise _SchemaError(f"{path}: duplicate item")
        seen.add(canonical)


def _bounded_string(value: object, path: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, str):
        raise _SchemaError(f"{path}: must be string")
    if len(value) < minimum:
        raise _SchemaError(f"{path}: shorter than minLength")
    if len(value) > maximum:
        raise _SchemaError(f"{path}: longer than maxLength")


def _pattern(value: object, pattern: re.Pattern[str], path: str) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise _SchemaError(f"{path}: does not match pattern")


def _enum(value: object, allowed: set[object], path: str) -> None:
    if value not in allowed:
        raise _SchemaError(f"{path}: unknown enum value {value!r}")


def _const(value: object, expected: object, path: str) -> None:
    if value != expected:
        raise _SchemaError(f"{path}: must equal {expected!r}")


def _integer_range(value: object, path: str, minimum: int | None, maximum: int | None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _SchemaError(f"{path}: must be integer")
    if minimum is not None and value < minimum:
        raise _SchemaError(f"{path}: must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise _SchemaError(f"{path}: must be <= {maximum}")


def _nullable_decimal(value: object, path: str) -> None:
    if value is not None:
        _pattern(value, _DECIMAL, path)


def _date_time_z(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _SchemaError(f"{path}: must be UTC date-time ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _SchemaError(f"{path}: is not a valid date-time") from exc
    if "T" not in value or parsed.tzinfo is None:
        raise _SchemaError(f"{path}: is not a valid date-time")


def _date_value(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise _SchemaError(f"{path}: must be date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise _SchemaError(f"{path}: is not a valid date") from exc
