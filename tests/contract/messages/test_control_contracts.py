from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "spec" / "contracts"
FIXTURES = Path(__file__).with_name("fixtures")
SEMANTIC_PATH = CONTRACTS / "control" / "control-semantic-validation.v1.yaml"
CONTROL_SCHEMA = "control/control-plane.v1.schema.json"
COMBINED_SCHEMA = "control/combined-control-message.v1.schema.json"
EVENT_SCHEMAS = {
    "system.mode_changed.v1": "events/system.mode_changed.v1.schema.json",
    "system.component_health_changed.v1": "events/system.component_health_changed.v1.schema.json",
    "system.kill_switch_changed.v1": "events/system.kill_switch_changed.v1.schema.json",
    "config.version_activated.v1": "events/config.version_activated.v1.schema.json",
}
SAFE_INTEGER_MAX = 9_007_199_254_740_991
CONTROL_TIME = "2026-08-11T01:00:00Z"
CHECKSUM_A = "a" * 64
CHECKSUM_B = "b" * 64
GATES = {
    "CONFIG_VERIFIED",
    "MARKET_FRESH",
    "AUDIT_AVAILABLE",
    "RECONCILIATION_COMPLETE",
    "LEASE_FENCED",
    "OUTBOX_HEALTHY",
}


def _load_json(path: Path, *, exact: bool = False) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if exact:
        kwargs = {"parse_float": Decimal, "parse_int": int, "parse_constant": _reject_constant}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8"), **kwargs))


def _loads_exact(document: str) -> Any:
    return json.loads(
        document,
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_reject_constant,
    )


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value} is forbidden")


def _schema_documents() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for path in CONTRACTS.rglob("*.schema.json"):
        document = _load_json(path)
        if "$id" in document:
            documents[document["$id"]] = document
    return documents


def _validator(relative: str) -> Draft202012Validator:
    schema = _load_json(CONTRACTS / relative)
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources(
        (uri, Resource.from_contents(document)) for uri, document in _schema_documents().items()
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _semantic() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(SEMANTIC_PATH.read_text(encoding="utf-8")))


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        raise ValueError("binary float input is forbidden")
    if isinstance(value, int):
        if not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
            raise ValueError("number outside I-JSON safe integer domain")
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("exact JSON number must be a mathematical integer")
        integer = int(value)
        if not -SAFE_INTEGER_MAX <= integer <= SAFE_INTEGER_MAX:
            raise ValueError("number outside I-JSON safe integer domain")
        return str(integer)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical object keys must be strings")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_canonical(key)}:{_canonical(value[key])}" for key in keys) + "}"
    raise ValueError(f"unsupported canonical value {type(value).__name__}")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _instant(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("control timestamp must be canonical UTC Z")
    if value.count(".") and len(value.rsplit(".", 1)[1][:-1]) > 6:
        raise ValueError("control timestamp precision exceeds six digits")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid control timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("naive timestamp is forbidden")
    return parsed.astimezone(UTC)


def _scope_key(value: dict[str, Any]) -> str:
    scope_type = value["scope_type"]
    scope_id = value["scope_id"]
    if scope_type == "GLOBAL":
        if scope_id is not None:
            raise ValueError("GLOBAL scope_id must be null")
        return "GLOBAL"
    if not isinstance(scope_id, str) or not scope_id:
        raise ValueError("non-GLOBAL scope_id is required")
    return f"{scope_type}:{scope_id}"


def _event_payload(name: str) -> dict[str, Any]:
    return _load_json(FIXTURES / name / "minimal.valid.json", exact=True)


def _message(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "system.mode_changed.v1":
        aggregate = partition = _scope_key(payload)
        version = payload["state_version"]
        source = "TradingCore"
        occurred = payload["changed_at"]
    elif name == "system.component_health_changed.v1":
        aggregate = partition = payload["component_id"]
        version = payload["generation"]
        source = "HealthService"
        occurred = payload["changed_at"]
    elif name == "system.kill_switch_changed.v1":
        aggregate = partition = _scope_key(payload)
        version = payload["current_version"]
        source = "ControlPlane"
        occurred = payload["changed_at"]
    else:
        aggregate = partition = payload["config_domain"]
        version = payload["activation_sequence"]
        source = "ConfigService"
        occurred = payload["activated_at"]
    return {
        "message_id": f"message-{name}-0001",
        "message_type": name,
        "schema_version": 1,
        "occurred_at": occurred,
        "received_at": occurred,
        "correlation_id": f"correlation-{name}-0001",
        "causation_id": f"causation-{name}-0001",
        "aggregate_id": aggregate,
        "aggregate_version": version,
        "source": source,
        "partition_key": partition,
        "idempotency_key": payload.get("idempotency_key", f"{name}:{aggregate}:{version}"),
        "payload": payload,
    }


def _authorization() -> dict[str, Any]:
    return {
        "authorization_id": "authorization-1",
        "authorization_version": "v1",
        "authorization_checksum": "d" * 64,
        "approver_ids": ["operator-approver-1"],
        "approved_at": "2026-08-11T00:59:00Z",
        "valid_until": "2026-08-11T02:00:00Z",
        "revoked": False,
    }


def _lease() -> dict[str, Any]:
    return {
        "dto_type": "LEADER_LEASE",
        "schema_version": 1,
        "correlation_id": "correlation-lease-0001",
        "created_at": CONTROL_TIME,
        "lease_id": "leader-lease-1",
        "holder_id": "control-1",
        "epoch": 4,
        "fencing_token": "fencing-token-0001",
        "issued_at": "2026-08-11T00:59:00Z",
        "expires_at": "2026-08-11T02:00:00Z",
        "renew_deadline_at": "2026-08-11T01:30:00Z",
        "status": "ACTIVE",
    }


def _barrier(*, state: str = "OPEN") -> dict[str, Any]:
    value = {
        "dto_type": "RECOVERY_BARRIER",
        "schema_version": 1,
        "correlation_id": "correlation-barrier-0001",
        "created_at": CONTROL_TIME,
        "barrier_id": "recovery-barrier-1",
        "state": state,
        "generation": 4,
        "opened_at": "2026-08-11T00:59:59Z" if state == "OPEN" else None,
        "evidence": {
            "config_version": "v2",
            "config_checksum": CHECKSUM_A,
            "market_watermark": 100,
            "audit_watermark": 100,
            "reconciliation_case_count": 0,
            "component_versions": {"OMS": "v2"},
            "component_checksums": {"OMS": CHECKSUM_B},
            "lease_id": "leader-lease-1",
            "leader_id": "control-1",
            "lease_authority_version": "lease-v1",
            "lease_epoch": 4,
            "fencing_token": "fencing-token-0001",
            "lease_expires_at": "2026-08-11T02:00:00Z",
            "audit_outbox_position": 100,
            "audit_inbox_position": 100,
            "audit_checksum": "9" * 64,
            "audit_lag": 0,
            "audit_healthy": True,
            "market_calendar_version": "calendar-v1",
            "market_calendar_checksum": "e" * 64,
            "market_session_id": "session-1",
            "market_session_state": "OPEN",
            "market_policy_version": "market-policy-v1",
            "market_policy_checksum": "f" * 64,
            "market_tzdb_version": "2026c",
            "market_tzdb_checksum": "1" * 64,
            "market_source_version": "source-v1",
            "market_quality": "NORMAL",
            "unresolved_gap_count": 0,
            "market_fresh_until": "2026-08-11T01:05:00Z",
            "reconciliation_version": "reconciliation-v1",
            "reconciliation_checksum": "2" * 64,
            "critical_lag_policy_version": "lag-v1",
            "critical_lag_policy_checksum": "3" * 64,
            "critical_lag_threshold": 10,
            "critical_lag_measurement_source": "source_received_watermark_delta",
            "critical_lag_window_seconds": 60,
            "critical_lag_recovery_window_seconds": 60,
            "critical_lag_current": 0,
            "component_generations": {"OMS": 2},
            "component_health": {"OMS": "HEALTHY"},
            "observed_at": "2026-08-11T00:59:59.5Z",
        },
        "required_evidence": sorted(GATES),
        "invalidation_reason": None,
    }
    return value


def _validate_barrier(value: dict[str, Any], *, evaluation_at: str = CONTROL_TIME) -> None:
    _validator(CONTROL_SCHEMA).validate(value)
    if value["state"] != "OPEN" or value["opened_at"] is None:
        raise ValueError("complete OPEN recovery barrier is required")
    if set(value["required_evidence"]) != GATES:
        raise ValueError("complete recovery gate set is required")
    evidence = value["evidence"]
    evaluation = _instant(evaluation_at)
    if _instant(evidence["observed_at"]) > evaluation:
        raise ValueError("future recovery observation")
    if _instant(evidence["market_fresh_until"]) <= evaluation:
        raise ValueError("recovery evidence is stale")
    if not evidence["audit_healthy"] or evidence["reconciliation_case_count"] != 0:
        raise ValueError("recovery authority is not healthy")
    if evidence["market_quality"] != "NORMAL" or evidence["unresolved_gap_count"] != 0:
        raise ValueError("market recovery authority is not verified")
    if set(evidence["component_versions"]) != set(evidence["component_checksums"]):
        raise ValueError("component recovery authority mismatch")
    if set(evidence["component_versions"]) != set(evidence["component_generations"]):
        raise ValueError("component recovery authority mismatch")
    if any(status != "HEALTHY" for status in evidence["component_health"].values()):
        raise ValueError("component recovery authority is unhealthy")


COMMAND_FIELDS = [
    "dto_type",
    "schema_version",
    "command_id",
    "scope_type",
    "scope_id",
    "desired_state",
    "cancel_active_orders",
    "reason",
    "reason_code",
    "operator_id",
    "approval_id",
    "authorization_evidence",
    "expected_version",
    "leader_lease_id",
    "fencing_token",
    "deadline_at",
    "idempotency_key",
    "recovery_evidence_reference",
    "recovery_barrier_generation",
    "recovery_barrier_version",
    "recovery_barrier_checksum",
    "recovery_evidence_digest",
    "recovery_aggregate_evidence_digest",
]
RESULT_FIELDS = [
    "dto_type",
    "schema_version",
    "result_id",
    "command_id",
    "command_fingerprint",
    "idempotency_key",
    "scope_type",
    "scope_id",
    "expected_version",
    "desired_state",
    "effective_state",
    "outcome",
    "previous_version",
    "current_version",
    "reason_code",
    "applied_at",
    "reconciliation_required",
    "effect_evidence",
    "authorization_id",
    "leader_lease_id",
    "fencing_token",
    "restores_normal",
]


def _fingerprint(value: dict[str, Any], fields: list[str]) -> str:
    return _sha({field: value[field] for field in fields})


def _command(
    *, scope_type: str = "GLOBAL", scope_id: str | None = None, desired: str = "ON"
) -> dict[str, Any]:
    barrier = _barrier()
    value = {
        "dto_type": "KILL_SWITCH_COMMAND",
        "schema_version": 1,
        "correlation_id": "correlation-kill-command-0001",
        "created_at": CONTROL_TIME,
        "command_id": "kill-command-0001",
        "command_fingerprint": "0" * 64,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "desired_state": desired,
        "cancel_active_orders": True,
        "reason": "operator requested emergency control",
        "reason_code": "MANUAL_EMERGENCY" if desired == "ON" else "OPERATOR_RELEASE",
        "operator_id": "operator-1",
        "approval_id": None,
        "authorization_evidence": _authorization(),
        "expected_version": 2,
        "leader_lease_id": "leader-lease-1",
        "fencing_token": "fencing-token-0001",
        "deadline_at": "2026-08-11T01:01:00Z",
        "idempotency_key": "kill-idempotency-0001",
        "recovery_evidence_reference": None,
        "recovery_barrier_generation": None,
        "recovery_barrier_version": None,
        "recovery_barrier_checksum": None,
        "recovery_evidence_digest": None,
        "recovery_aggregate_evidence_digest": None,
    }
    if desired == "OFF":
        value.update(
            {
                "recovery_evidence_reference": barrier["barrier_id"],
                "recovery_barrier_generation": barrier["generation"],
                "recovery_barrier_version": "barrier-v1",
                "recovery_barrier_checksum": "4" * 64,
                "recovery_evidence_digest": _sha(barrier["evidence"]),
                "recovery_aggregate_evidence_digest": _sha(barrier),
            }
        )
    value["command_fingerprint"] = _fingerprint(value, COMMAND_FIELDS)
    return value


def _result(command: dict[str, Any], *, outcome: str = "APPLIED") -> dict[str, Any]:
    previous_version = command["expected_version"]
    current_version = previous_version + 1 if outcome == "APPLIED" else previous_version
    effective = command["desired_state"] if outcome == "APPLIED" else "OFF"
    if outcome == "UNKNOWN":
        effective = "UNKNOWN"
    value = {
        "dto_type": "KILL_SWITCH_RESULT",
        "schema_version": 1,
        "correlation_id": command["correlation_id"],
        "created_at": CONTROL_TIME,
        "result_id": "kill-result-0001",
        "result_fingerprint": "0" * 64,
        "command_id": command["command_id"],
        "command_fingerprint": command["command_fingerprint"],
        "idempotency_key": command["idempotency_key"],
        "scope_type": command["scope_type"],
        "scope_id": command["scope_id"],
        "expected_version": command["expected_version"],
        "desired_state": command["desired_state"],
        "effective_state": effective,
        "outcome": outcome,
        "previous_version": previous_version,
        "current_version": current_version,
        "reason_code": command["reason_code"],
        "applied_at": CONTROL_TIME if outcome == "APPLIED" else None,
        "reconciliation_required": outcome == "UNKNOWN",
        "effect_evidence": {
            "ack_ids": ["ack-1"] if outcome == "APPLIED" else [],
            "observed_at": CONTROL_TIME,
        },
        "authorization_id": command["authorization_evidence"]["authorization_id"],
        "leader_lease_id": command["leader_lease_id"],
        "fencing_token": command["fencing_token"],
        "restores_normal": False,
    }
    value["result_fingerprint"] = _fingerprint(value, RESULT_FIELDS)
    return value


def _persisted_command(command: dict[str, Any], *, decision: str = "ACCEPTED") -> dict[str, Any]:
    return {"decision": decision, "command": deepcopy(command)}


def _current_state(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope_type": command["scope_type"],
        "scope_id": command["scope_id"],
        "enabled": False,
        "version": command["expected_version"],
    }


def _same_content(left: dict[str, Any], right: dict[str, Any], fingerprint: str) -> bool:
    return left == right and left[fingerprint] == right[fingerprint]


def validate_kill_command(
    command: dict[str, Any],
    *,
    current_state: dict[str, Any],
    authorization: dict[str, Any],
    lease: dict[str, Any],
    barrier: dict[str, Any] | None = None,
    prior_fact: dict[str, Any] | None = None,
    evaluation_at: str = CONTROL_TIME,
) -> str:
    _validator(CONTROL_SCHEMA).validate(command)
    _scope_key(command)
    if command["command_fingerprint"] != _fingerprint(command, COMMAND_FIELDS):
        raise ValueError("command fingerprint mismatch")
    if prior_fact is not None:
        prior = prior_fact["command"]
        same_identity = (prior["scope_type"], prior["scope_id"], prior["idempotency_key"]) == (
            command["scope_type"],
            command["scope_id"],
            command["idempotency_key"],
        )
        if same_identity:
            if prior_fact.get("decision") != "ACCEPTED":
                raise ValueError("only accepted persisted command is authority")
            if _same_content(prior, command, "command_fingerprint"):
                return "DUPLICATE"
            raise ValueError("QQ-STORAGE-7001 IDEMPOTENCY_CONFLICT")
    if (current_state["scope_type"], current_state["scope_id"]) != (
        command["scope_type"],
        command["scope_id"],
    ):
        raise ValueError("scoped current authority mismatch")
    if current_state["version"] != command["expected_version"]:
        raise ValueError("QQ-COMMON-1003 VERSION_CONFLICT")
    if authorization != command["authorization_evidence"] or authorization["revoked"]:
        raise ValueError("authorization mismatch")
    now = _instant(evaluation_at)
    if not (_instant(authorization["approved_at"]) <= now < _instant(authorization["valid_until"])):
        raise ValueError("authorization is stale")
    if lease["status"] != "ACTIVE" or lease["lease_id"] != command["leader_lease_id"]:
        raise ValueError("lease authority mismatch")
    if lease["fencing_token"] != command["fencing_token"] or now >= _instant(lease["expires_at"]):
        raise ValueError("stale fencing authority")
    if now >= _instant(command["deadline_at"]):
        raise ValueError("command deadline expired")
    if command["desired_state"] == "OFF":
        if barrier is None:
            raise ValueError("recovery barrier required")
        _validate_barrier(barrier, evaluation_at=evaluation_at)
        if command["recovery_evidence_reference"] != barrier["barrier_id"]:
            raise ValueError("recovery barrier identity mismatch")
        if command["recovery_barrier_generation"] != barrier["generation"]:
            raise ValueError("recovery barrier generation mismatch")
        if command["recovery_evidence_digest"] != _sha(barrier["evidence"]):
            raise ValueError("recovery evidence digest mismatch")
        if command["recovery_aggregate_evidence_digest"] != _sha(barrier):
            raise ValueError("recovery aggregate digest mismatch")
    return "ACCEPTED"


def validate_kill_result(
    result: dict[str, Any],
    *,
    persisted_command_fact: dict[str, Any],
    current_state: dict[str, Any],
    expected_ack_ids: set[str],
    prior_result_fact: dict[str, Any] | None = None,
    evaluation_at: str = CONTROL_TIME,
) -> str:
    _validator(CONTROL_SCHEMA).validate(result)
    _scope_key(result)
    if result["result_fingerprint"] != _fingerprint(result, RESULT_FIELDS):
        raise ValueError("result fingerprint mismatch")
    if persisted_command_fact.get("decision") != "ACCEPTED":
        raise ValueError("result requires an accepted persisted command")
    command = persisted_command_fact["command"]
    if command["command_fingerprint"] != _fingerprint(command, COMMAND_FIELDS):
        raise ValueError("persisted command fingerprint mismatch")
    bindings = {
        "command_id": "command_id",
        "command_fingerprint": "command_fingerprint",
        "idempotency_key": "idempotency_key",
        "scope_type": "scope_type",
        "scope_id": "scope_id",
        "expected_version": "expected_version",
        "desired_state": "desired_state",
        "reason_code": "reason_code",
        "leader_lease_id": "leader_lease_id",
        "fencing_token": "fencing_token",
    }
    for result_field, command_field in bindings.items():
        if result[result_field] != command[command_field]:
            raise ValueError("result command binding mismatch")
    if result["authorization_id"] != command["authorization_evidence"]["authorization_id"]:
        raise ValueError("result authorization binding mismatch")
    if prior_result_fact is not None:
        if _same_content(prior_result_fact, result, "result_fingerprint"):
            return "DUPLICATE"
        raise ValueError("persisted result conflict")
    if (current_state["scope_type"], current_state["scope_id"]) != (
        result["scope_type"],
        result["scope_id"],
    ):
        raise ValueError("result scope authority mismatch")
    if current_state["version"] != result["previous_version"]:
        raise ValueError("first result is stale against current scoped state")
    if result["previous_version"] != command["expected_version"]:
        raise ValueError("result previous version mismatch")
    observed = _instant(result["effect_evidence"]["observed_at"])
    if observed > _instant(evaluation_at):
        raise ValueError("future effect evidence")
    ack_ids = set(result["effect_evidence"]["ack_ids"])
    if not ack_ids <= expected_ack_ids:
        raise ValueError("forged effect ACK")
    if result["outcome"] == "APPLIED":
        if result["current_version"] != result["previous_version"] + 1:
            raise ValueError("APPLIED version must advance exactly once")
        if ack_ids != expected_ack_ids:
            raise ValueError("APPLIED requires complete effect ACK authority")
    elif result["outcome"] == "REJECTED":
        if result["current_version"] != result["previous_version"]:
            raise ValueError("REJECTED cannot advance version")
        expected_effective = "ON" if current_state["enabled"] else "OFF"
        if result["effective_state"] != expected_effective or ack_ids:
            raise ValueError("REJECTED must preserve current authority")
    else:
        if result["current_version"] != result["previous_version"]:
            raise ValueError("UNKNOWN cannot fabricate current version")
        if ack_ids == expected_ack_ids and expected_ack_ids:
            raise ValueError("UNKNOWN cannot claim complete effect")
    return "ACCEPTED"


def _candidate() -> dict[str, Any]:
    hard_policy = {
        "valuation_currency": "CNY",
        "limits": {"maximum_order_notional": "1000000", "maximum_gross_exposure": "5000000"},
    }
    value = {
        "dto_type": "CONFIG_CANDIDATE",
        "schema_version": 1,
        "correlation_id": "correlation-config-0001",
        "created_at": CONTROL_TIME,
        "config_domain": "risk.rules",
        "candidate_version": "v2",
        "candidate_checksum": "0" * 64,
        "payload": {"mode": "strict", "retry_budget": 1},
        "secret_references": ["secret://risk/api"],
        "required_components": ["OMS", "RiskEngine"],
        "activation_mode": "HOT_RELOAD",
        "safe_boundary": "NEXT_ORDER_BOUNDARY",
        "system_hard_limit_policy_version": "hard-v1",
        "system_hard_limit_policy_checksum": _sha(hard_policy),
        "valuation_currency": "CNY",
        "dynamic_limits": {"maximum_order_notional": "500000", "maximum_gross_exposure": "3000000"},
        "system_hard_limit_policy": hard_policy,
        "component_authority": {
            "OMS": {
                "component_id": "OMS",
                "generation": 2,
                "capability_version": "oms-v1",
                "activation_mode": "HOT_RELOAD",
                "safe_boundary": "NEXT_ORDER_BOUNDARY",
            },
            "RiskEngine": {
                "component_id": "RiskEngine",
                "generation": 1,
                "capability_version": "risk-v1",
                "activation_mode": "HOT_RELOAD",
                "safe_boundary": "NEXT_ORDER_BOUNDARY",
            },
        },
        "policy_version": "control-policy-v1",
        "policy_checksum": CHECKSUM_A,
        "deadline_at": "2026-08-11T01:01:00Z",
        "idempotency_key": "config-idempotency-0001",
    }
    value["candidate_checksum"] = _candidate_checksum(value)
    return value


def _candidate_checksum(candidate: dict[str, Any]) -> str:
    fields = _semantic()["config_activation"]["candidate_checksum"]["projection_order"]
    projection = {field: deepcopy(candidate[field]) for field in fields}
    for field in _semantic()["config_activation"]["candidate_checksum"]["set_sorted_fields"]:
        projection[field] = sorted(projection[field])
    return _sha(projection)


def validate_candidate(candidate: dict[str, Any]) -> None:
    _validator(CONTROL_SCHEMA).validate(candidate)
    if candidate["candidate_checksum"] != _candidate_checksum(candidate):
        raise ValueError("candidate checksum mismatch")
    hard_policy = candidate["system_hard_limit_policy"]
    if candidate["system_hard_limit_policy_checksum"] != _sha(hard_policy):
        raise ValueError("hard-limit policy checksum mismatch")
    if candidate["valuation_currency"] != hard_policy["valuation_currency"]:
        raise ValueError("valuation currency mismatch")
    for name, value in candidate["dynamic_limits"].items():
        if name not in hard_policy["limits"]:
            raise ValueError("dynamic limit lacks hard authority")
        if Decimal(value) > Decimal(hard_policy["limits"][name]):
            raise ValueError("dynamic limit relaxes system hard limit")
    if set(candidate["required_components"]) != set(candidate["component_authority"]):
        raise ValueError("required component authority mismatch")


def _validate_event_semantics(
    message: dict[str, Any], *, barrier: dict[str, Any] | None = None
) -> None:
    _validator("common/message-envelope.v1.schema.json").validate(message)
    _validator(COMBINED_SCHEMA).validate(message)
    payload = message["payload"]
    name = message["message_type"]
    if name in {"system.mode_changed.v1", "system.kill_switch_changed.v1"}:
        key = _scope_key(payload)
        if message["aggregate_id"] != key or message["partition_key"] != key:
            raise ValueError("scope envelope binding mismatch")
    if name == "system.mode_changed.v1":
        if message["aggregate_version"] != payload["state_version"]:
            raise ValueError("mode version binding mismatch")
        if payload["from_mode"] == "STARTING" and payload["to_mode"] == "NORMAL":
            if barrier is None:
                raise ValueError("RecoveryPassed requires OPEN barrier")
            _validate_barrier(barrier)
            if payload["evidence"]["recovery_barrier_id"] != barrier["barrier_id"]:
                raise ValueError("mode recovery barrier mismatch")
    elif name == "system.component_health_changed.v1":
        if message["aggregate_id"] != payload["component_id"]:
            raise ValueError("health aggregate binding mismatch")
    elif name == "system.kill_switch_changed.v1":
        if message["aggregate_version"] != payload["current_version"]:
            raise ValueError("kill version binding mismatch")
        if payload["current_version"] != payload["previous_version"] + 1:
            raise ValueError("changed event must advance exactly once")
    else:
        if message["aggregate_id"] != payload["config_domain"]:
            raise ValueError("config aggregate binding mismatch")
        if payload["active_version"] != payload["candidate_version"]:
            raise ValueError("activated version mismatch")
        if payload["active_checksum"] != payload["candidate_checksum"]:
            raise ValueError("activated checksum mismatch")
        if set(payload["required_components"]) != set(payload["component_acks"]):
            raise ValueError("activation ACK set mismatch")
        for component, ack in payload["component_acks"].items():
            if ack["component_id"] != component or ack["result"] != "APPLIED":
                raise ValueError("activation ACK is not an applied fact")


def _validate_config_event_candidate_binding(
    payload: dict[str, Any], candidate: dict[str, Any]
) -> None:
    for field in (
        "config_domain",
        "candidate_version",
        "candidate_checksum",
        "activation_mode",
        "safe_boundary",
        "policy_version",
        "policy_checksum",
    ):
        if payload[field] != candidate[field]:
            raise ValueError("activated event candidate binding mismatch")
    for field in ("secret_references", "required_components"):
        if set(payload[field]) != set(candidate[field]):
            raise ValueError("activated event candidate set mismatch")
    if payload["active_version"] != candidate["candidate_version"]:
        raise ValueError("activated version mismatch")
    if payload["active_checksum"] != candidate["candidate_checksum"]:
        raise ValueError("activated checksum mismatch")
    if set(payload["component_acks"]) != set(candidate["component_authority"]):
        raise ValueError("activated component authority mismatch")
    for component, authority in candidate["component_authority"].items():
        ack = payload["component_acks"][component]
        expected = {
            "component_id": component,
            "candidate_version": candidate["candidate_version"],
            "candidate_checksum": candidate["candidate_checksum"],
            "generation": authority["generation"],
            "capability_version": authority["capability_version"],
            "result": "APPLIED",
            "activation_mode": authority["activation_mode"],
            "safe_boundary": authority["safe_boundary"],
        }
        if any(ack[field] != value for field, value in expected.items()):
            raise ValueError("activated ACK authority mismatch")


@pytest.mark.parametrize("name,relative", EVENT_SCHEMAS.items())
def test_public_event_golden_fixtures(name: str, relative: str) -> None:
    validator = _validator(relative)
    folder = FIXTURES / name
    validator.validate(_load_json(folder / "minimal.valid.json", exact=True))
    validator.validate(_load_json(folder / "maximal.valid.json", exact=True))
    for invalid in sorted(folder.glob("invalid.*.json")):
        assert list(validator.iter_errors(_load_json(invalid, exact=True))), invalid


def test_internal_control_DTO_golden_fixture_matrix() -> None:
    validator = _validator(CONTROL_SCHEMA)
    document = _load_json(FIXTURES / "control-plane.v1" / "valid.json", exact=True)
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    assert set(by_type) == {
        "OBSERVABILITY_CONTEXT",
        "ALERT_DEFINITION",
        "CONFIG_CANDIDATE",
        "CONFIG_ACTIVATION_RESULT",
        "KILL_SWITCH_COMMAND",
        "KILL_SWITCH_RESULT",
        "LEADER_LEASE",
        "RECOVERY_BARRIER",
    }
    for dto in by_type.values():
        validator.validate(dto)
    invalid = _load_json(FIXTURES / "control-plane.v1" / "invalid.json", exact=True)
    for case in invalid["cases"]:
        dto = deepcopy(by_type[case["dto_type"]])
        dto[case["field"]] = case["value"]
        assert list(validator.iter_errors(dto)), case["name"]


@pytest.mark.parametrize("name", EVENT_SCHEMAS)
def test_full_combined_message_is_unchanged_canonical_envelope(name: str) -> None:
    message = _message(name, _event_payload(name))
    _validator("common/message-envelope.v1.schema.json").validate(message)
    _validator(COMBINED_SCHEMA).validate(message)
    _validate_event_semantics(
        message, barrier=_barrier() if name == "system.mode_changed.v1" else None
    )
    assert set(message) == set(
        _load_json(CONTRACTS / "common/message-envelope.v1.schema.json")["properties"]
    )


def test_combined_rejects_extra_wire_fields_and_preserves_shared_offset_compatibility() -> None:
    message = _message(
        "system.kill_switch_changed.v1", _event_payload("system.kill_switch_changed.v1")
    )
    for field in ("publisher", "aggregate_type", "payload_fingerprint"):
        invalid = deepcopy(message)
        invalid[field] = "forbidden"
        assert list(_validator(COMBINED_SCHEMA).iter_errors(invalid))
    offset = deepcopy(message)
    offset["occurred_at"] = "2026-08-11T09:00:00+08:00"
    offset["received_at"] = "2026-08-11T09:00:00+08:00"
    _validator("common/message-envelope.v1.schema.json").validate(offset)
    assert list(_validator(COMBINED_SCHEMA).iter_errors(offset))
    high_precision = deepcopy(message)
    high_precision["occurred_at"] = "2026-08-11T01:00:00.123456789Z"
    high_precision["received_at"] = "2026-08-11T01:00:00.123456789Z"
    _validator("common/message-envelope.v1.schema.json").validate(high_precision)
    assert list(_validator(COMBINED_SCHEMA).iter_errors(high_precision))


@pytest.mark.parametrize(
    "scope_type,scope_id,key",
    [
        ("GLOBAL", None, "GLOBAL"),
        ("ACCOUNT", "acct-1", "ACCOUNT:acct-1"),
        ("STRATEGY", "strat-1", "STRATEGY:strat-1"),
        ("INSTRUMENT", "600000.XSHG", "INSTRUMENT:600000.XSHG"),
    ],
)
def test_scope_types_are_addressable_and_shared_by_command_result_event(
    scope_type: str, scope_id: str | None, key: str
) -> None:
    command = _command(scope_type=scope_type, scope_id=scope_id)
    result = _result(command)
    event = _event_payload("system.kill_switch_changed.v1")
    event.update({"scope_type": scope_type, "scope_id": scope_id})
    assert _scope_key(command) == _scope_key(result) == _scope_key(event) == key
    _validator(CONTROL_SCHEMA).validate(command)
    _validator(CONTROL_SCHEMA).validate(result)
    _validator(EVENT_SCHEMAS["system.kill_switch_changed.v1"]).validate(event)


@pytest.mark.parametrize(
    "scope_type,scope_id",
    [("GLOBAL", "bad"), ("ACCOUNT", None), ("STRATEGY", None), ("INSTRUMENT", None)],
)
def test_invalid_scope_pairs_fail_schema(scope_type: str, scope_id: str | None) -> None:
    for value, relative in [
        (_command(scope_type=scope_type, scope_id=scope_id), CONTROL_SCHEMA),
        (
            _event_payload("system.kill_switch_changed.v1"),
            EVENT_SCHEMAS["system.kill_switch_changed.v1"],
        ),
    ]:
        value["scope_type"] = scope_type
        value["scope_id"] = scope_id
        assert list(_validator(relative).iter_errors(value))


def test_scope_mismatch_between_command_result_and_event_fails_closed() -> None:
    command = _command()
    result = _result(command)
    result["scope_type"] = "ACCOUNT"
    result["scope_id"] = "acct-1"
    result["result_fingerprint"] = _fingerprint(result, RESULT_FIELDS)
    with pytest.raises(ValueError, match="binding"):
        validate_kill_result(
            result,
            persisted_command_fact=_persisted_command(command),
            current_state=_current_state(command),
            expected_ack_ids={"ack-1"},
        )
    message = _message(
        "system.kill_switch_changed.v1", _event_payload("system.kill_switch_changed.v1")
    )
    message["aggregate_id"] = "ACCOUNT:acct-1"
    with pytest.raises(ValueError, match="scope"):
        _validate_event_semantics(message)


def test_changed_and_activated_events_cannot_encode_unsuccessful_outcome() -> None:
    for name in ("system.kill_switch_changed.v1", "config.version_activated.v1"):
        payload = _event_payload(name)
        for outcome in ("REJECTED", "PARTIAL", "UNKNOWN", "ROLLED_BACK"):
            invalid = deepcopy(payload)
            invalid["outcome"] = outcome
            assert list(_validator(EVENT_SCHEMAS[name]).iter_errors(invalid))
    result = _candidate_result(outcome="REJECTED")
    _validator(CONTROL_SCHEMA).validate(result)


def _candidate_result(*, outcome: str = "APPLIED") -> dict[str, Any]:
    candidate = _candidate()
    ack = {
        component: {
            "component_id": component,
            "candidate_version": candidate["candidate_version"],
            "candidate_checksum": candidate["candidate_checksum"],
            "generation": authority["generation"],
            "capability_version": authority["capability_version"],
            "prepare_result": "APPLIED" if outcome == "APPLIED" else "REJECTED",
            "activation_mode": authority["activation_mode"],
            "safe_boundary": authority["safe_boundary"],
            "observed_at": CONTROL_TIME,
            "ack_sequence": index + 1,
        }
        for index, (component, authority) in enumerate(candidate["component_authority"].items())
    }
    return {
        "dto_type": "CONFIG_ACTIVATION_RESULT",
        "schema_version": 1,
        "correlation_id": candidate["correlation_id"],
        "created_at": CONTROL_TIME,
        "config_domain": candidate["config_domain"],
        "candidate_version": candidate["candidate_version"],
        "candidate_checksum": candidate["candidate_checksum"],
        "required_components": candidate["required_components"],
        "outcome": outcome,
        "component_acks": ack,
        "active_version": candidate["candidate_version"] if outcome == "APPLIED" else None,
        "active_checksum": candidate["candidate_checksum"] if outcome == "APPLIED" else None,
        "rollback_version": None,
    }


def test_starting_to_normal_requires_complete_fresh_open_barrier() -> None:
    message = _message("system.mode_changed.v1", _event_payload("system.mode_changed.v1"))
    with pytest.raises(ValueError, match="requires OPEN"):
        _validate_event_semantics(message)
    _validate_event_semantics(message, barrier=_barrier())
    for mutation in ("closed", "missing_gate", "future", "stale"):
        barrier = _barrier(state="CLOSED" if mutation == "closed" else "OPEN")
        if mutation == "missing_gate":
            barrier["required_evidence"].remove("MARKET_FRESH")
        elif mutation == "future":
            barrier["evidence"]["observed_at"] = "2026-08-11T01:00:00.1Z"
        elif mutation == "stale":
            barrier["evidence"]["market_fresh_until"] = CONTROL_TIME
        with pytest.raises((ValueError, ValidationError)):
            _validate_event_semantics(message, barrier=barrier)

    approval_required = deepcopy(message["payload"])
    approval_required.update(
        {
            "from_mode": "HALTED",
            "to_mode": "SAFE",
            "reason_code": "DUAL_APPROVED_RECOVERY",
            "approval_id": None,
        }
    )
    assert list(_validator(EVENT_SCHEMAS["system.mode_changed.v1"]).iter_errors(approval_required))


def test_health_transition_and_reason_are_schema_bound() -> None:
    payload = _event_payload("system.component_health_changed.v1")
    _validator(EVENT_SCHEMAS["system.component_health_changed.v1"]).validate(payload)
    for field, value in [
        ("from_state", "UNAVAILABLE"),
        ("to_state", "HEALTHY"),
        ("reason_code", "PROBE_PASSED"),
    ]:
        invalid = deepcopy(payload)
        invalid[field] = value
        assert list(
            _validator(EVENT_SCHEMAS["system.component_health_changed.v1"]).iter_errors(invalid)
        )


def test_candidate_checksum_exact_number_domain_and_determinism() -> None:
    checksums = []
    for token in ("1", "1.0", "1e0"):
        candidate = _candidate()
        candidate["payload"] = _loads_exact('{"nested":{"value":' + token + "}}")
        candidate["candidate_checksum"] = _candidate_checksum(candidate)
        validate_candidate(candidate)
        checksums.append(candidate["candidate_checksum"])
    assert len(set(checksums)) == 1
    for token in ("1.0000000000000001", "1e-400", "9007199254740991.1", "1.25", "9007199254740992"):
        candidate = _candidate()
        candidate["payload"] = _loads_exact('{"nested":[{"value":' + token + "}]}")
        with pytest.raises((ValueError, ValidationError)):
            candidate["candidate_checksum"] = _candidate_checksum(candidate)
            validate_candidate(candidate)
    candidate = _candidate()
    candidate["payload"] = {"direct_float": 1.0}
    with pytest.raises(ValueError, match="binary float"):
        _candidate_checksum(candidate)
    with pytest.raises(ValueError, match="non-finite"):
        _loads_exact('{"value":NaN}')


@pytest.mark.parametrize(
    "field",
    [
        "payload",
        "secret_references",
        "required_components",
        "activation_mode",
        "safe_boundary",
        "dynamic_limits",
        "system_hard_limit_policy",
        "component_authority",
        "policy_version",
    ],
)
def test_candidate_security_fields_are_checksum_bound(field: str) -> None:
    candidate = _candidate()
    if isinstance(candidate[field], dict):
        candidate[field]["tampered"] = "1"
    elif isinstance(candidate[field], list):
        candidate[field].append("tampered")
    else:
        candidate[field] = "RESTART_ONLY" if field == "safe_boundary" else "tampered"
    with pytest.raises((ValueError, ValidationError)):
        validate_candidate(candidate)


def test_candidate_hard_limit_currency_content_and_relaxation_fail_closed() -> None:
    for mutation in ("currency", "content_hash", "relax"):
        candidate = _candidate()
        if mutation == "currency":
            candidate["valuation_currency"] = "USD"
        elif mutation == "content_hash":
            candidate["system_hard_limit_policy"]["limits"]["maximum_order_notional"] = "900000"
        else:
            candidate["dynamic_limits"]["maximum_order_notional"] = "1000001"
            candidate["candidate_checksum"] = _candidate_checksum(candidate)
        with pytest.raises((ValueError, ValidationError)):
            validate_candidate(candidate)


def test_config_activated_event_binds_applied_ACKs_and_security_fields() -> None:
    candidate = _candidate()
    payload = _event_payload("config.version_activated.v1")
    payload.update(
        {
            "config_domain": candidate["config_domain"],
            "candidate_version": candidate["candidate_version"],
            "candidate_checksum": candidate["candidate_checksum"],
            "active_version": candidate["candidate_version"],
            "active_checksum": candidate["candidate_checksum"],
            "activation_mode": candidate["activation_mode"],
            "safe_boundary": candidate["safe_boundary"],
            "required_components": candidate["required_components"],
            "secret_references": candidate["secret_references"],
            "policy_version": candidate["policy_version"],
            "policy_checksum": candidate["policy_checksum"],
            "component_acks": {
                component: {
                    "component_id": component,
                    "candidate_version": candidate["candidate_version"],
                    "candidate_checksum": candidate["candidate_checksum"],
                    "generation": authority["generation"],
                    "capability_version": authority["capability_version"],
                    "result": "APPLIED",
                    "activation_mode": authority["activation_mode"],
                    "safe_boundary": authority["safe_boundary"],
                    "observed_at": CONTROL_TIME,
                    "ack_sequence": index + 1,
                }
                for index, (component, authority) in enumerate(
                    candidate["component_authority"].items()
                )
            },
        }
    )
    message = _message("config.version_activated.v1", payload)
    _validate_event_semantics(message)
    _validate_config_event_candidate_binding(payload, candidate)
    for mutation in ("missing_ack", "wrong_checksum", "wrong_secret", "wrong_boundary"):
        invalid = deepcopy(payload)
        if mutation == "missing_ack":
            invalid["component_acks"].pop(next(iter(invalid["component_acks"])))
        elif mutation == "wrong_checksum":
            invalid["active_checksum"] = CHECKSUM_B
        elif mutation == "wrong_secret":
            invalid["secret_references"] = ["secret://different/reference"]
        else:
            invalid["safe_boundary"] = "NEXT_BAR_BOUNDARY"
        invalid_message = _message("config.version_activated.v1", invalid)
        with pytest.raises((ValueError, ValidationError)):
            _validate_event_semantics(invalid_message)
            _validate_config_event_candidate_binding(invalid, candidate)


def test_kill_command_duplicate_conflict_and_error_codes_use_one_prior_fact() -> None:
    command = _command()
    state = _current_state(command)
    kwargs = {"current_state": state, "authorization": _authorization(), "lease": _lease()}
    assert validate_kill_command(command, **kwargs) == "ACCEPTED"
    assert (
        validate_kill_command(command, prior_fact=_persisted_command(command), **kwargs)
        == "DUPLICATE"
    )
    conflict = deepcopy(command)
    conflict["reason"] = "different canonical content"
    conflict["command_fingerprint"] = _fingerprint(conflict, COMMAND_FIELDS)
    with pytest.raises(ValueError, match="QQ-STORAGE-7001"):
        validate_kill_command(conflict, prior_fact=_persisted_command(command), **kwargs)
    stale = deepcopy(state)
    stale["version"] += 1
    with pytest.raises(ValueError, match="QQ-COMMON-1003"):
        validate_kill_command(
            command, current_state=stale, authorization=_authorization(), lease=_lease()
        )


def test_rejected_command_fact_cannot_authorize_result() -> None:
    command = _command()
    with pytest.raises(ValueError, match="accepted persisted command"):
        validate_kill_result(
            _result(command),
            persisted_command_fact=_persisted_command(command, decision="REJECTED"),
            current_state=_current_state(command),
            expected_ack_ids={"ack-1"},
        )


@pytest.mark.parametrize("outcome", ["APPLIED", "REJECTED", "UNKNOWN"])
def test_kill_result_outcome_matrix(outcome: str) -> None:
    command = _command()
    result = _result(command, outcome=outcome)
    expected = {"ack-1"}
    assert (
        validate_kill_result(
            result,
            persisted_command_fact=_persisted_command(command),
            current_state=_current_state(command),
            expected_ack_ids=expected,
        )
        == "ACCEPTED"
    )
    if outcome == "APPLIED":
        missing = deepcopy(result)
        missing["effect_evidence"]["ack_ids"] = []
        missing["result_fingerprint"] = _fingerprint(missing, RESULT_FIELDS)
        with pytest.raises((ValueError, ValidationError)):
            validate_kill_result(
                missing,
                persisted_command_fact=_persisted_command(command),
                current_state=_current_state(command),
                expected_ack_ids=expected,
            )
    forged = deepcopy(result)
    forged["effect_evidence"]["ack_ids"] = ["forged-ack"]
    forged["result_fingerprint"] = _fingerprint(forged, RESULT_FIELDS)
    with pytest.raises((ValueError, ValidationError)):
        validate_kill_result(
            forged,
            persisted_command_fact=_persisted_command(command),
            current_state=_current_state(command),
            expected_ack_ids=expected,
        )


def test_one_prior_result_fact_gives_stable_duplicate_and_conflict() -> None:
    command = _command()
    result = _result(command)
    persisted_command = _persisted_command(command)
    advanced = _current_state(command)
    advanced["version"] = result["current_version"] + 10
    advanced["enabled"] = True
    assert (
        validate_kill_result(
            result,
            persisted_command_fact=persisted_command,
            prior_result_fact=deepcopy(result),
            current_state=advanced,
            expected_ack_ids={"ack-1"},
        )
        == "DUPLICATE"
    )
    for field, value in [
        ("result_id", "different-result-0001"),
        ("outcome", "UNKNOWN"),
        ("current_version", 99),
        ("authorization_id", "forged"),
    ]:
        changed = deepcopy(result)
        changed[field] = value
        if field == "outcome":
            changed.update(
                {
                    "effective_state": "UNKNOWN",
                    "applied_at": None,
                    "reconciliation_required": True,
                    "current_version": changed["previous_version"],
                    "effect_evidence": {"ack_ids": [], "observed_at": CONTROL_TIME},
                }
            )
        changed["result_fingerprint"] = _fingerprint(changed, RESULT_FIELDS)
        with pytest.raises(ValueError, match=r"conflict|binding"):
            validate_kill_result(
                changed,
                persisted_command_fact=persisted_command,
                prior_result_fact=result,
                current_state=advanced,
                expected_ack_ids={"ack-1"},
            )


def test_first_late_result_is_not_duplicate() -> None:
    command = _command()
    advanced = _current_state(command)
    advanced["version"] += 1
    with pytest.raises(ValueError, match="stale"):
        validate_kill_result(
            _result(command),
            persisted_command_fact=_persisted_command(command),
            current_state=advanced,
            expected_ack_ids={"ack-1"},
        )


def test_kill_command_authorization_lease_deadline_fence_and_off_barrier() -> None:
    command = _command(desired="OFF")
    state = _current_state(command)
    barrier = _barrier()
    assert (
        validate_kill_command(
            command,
            current_state=state,
            authorization=_authorization(),
            lease=_lease(),
            barrier=barrier,
        )
        == "ACCEPTED"
    )
    cases: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]] = []
    revoked = _authorization()
    revoked["revoked"] = True
    cases.append(("authorization", revoked, _lease(), barrier))
    stale_lease = _lease()
    stale_lease["expires_at"] = CONTROL_TIME
    cases.append(("fencing", _authorization(), stale_lease, barrier))
    cases.append(("barrier", _authorization(), _lease(), None))
    for expected, authorization, lease, candidate_barrier in cases:
        with pytest.raises(ValueError, match=expected):
            validate_kill_command(
                command,
                current_state=state,
                authorization=authorization,
                lease=lease,
                barrier=candidate_barrier,
            )
    expired = deepcopy(command)
    expired["deadline_at"] = CONTROL_TIME
    expired["command_fingerprint"] = _fingerprint(expired, COMMAND_FIELDS)
    with pytest.raises(ValueError, match="deadline"):
        validate_kill_command(
            expired,
            current_state=state,
            authorization=_authorization(),
            lease=_lease(),
            barrier=barrier,
        )


def test_time_comparisons_use_instants_and_reject_fractional_future() -> None:
    barrier = _barrier()
    barrier["evidence"]["observed_at"] = "2026-08-11T01:00:00.1Z"
    with pytest.raises(ValueError, match="future"):
        _validate_barrier(barrier)
    assert _instant("2026-08-11T01:00:00Z") == _instant("2026-08-11T01:00:00.000000Z")
    for invalid in (
        "2026-08-11T01:00:00+00:00",
        "2026-08-11T01:00:00",
        "2026-08-11T01:00:60Z",
        "2026-08-11T01:00:00.0000001Z",
    ):
        with pytest.raises(ValueError):
            _instant(invalid)


def test_redaction_and_low_cardinality_label_contracts() -> None:
    semantic = _semantic()["observability"]
    allowed = set(semantic["metric_label_allowlist"])
    assert allowed == {"severity", "component", "alert_code", "environment", "policy_version"}
    assert not {"account_id", "order_id", "message_id", "command_id"} & allowed
    forbidden = set(semantic["recursive_redaction_forbidden_keys"])

    def scan(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden & set(value):
                raise ValueError("sensitive key")
            for nested in value.values():
                scan(nested)
        elif isinstance(value, list):
            for nested in value:
                scan(nested)

    scan({"evidence": {"policy_version": "v1"}})
    with pytest.raises(ValueError, match="sensitive"):
        scan({"nested": [{"credential": "raw"}]})


def test_recovery_and_storage_authority_references_are_explicit_without_physical_model() -> None:
    semantic_text = SEMANTIC_PATH.read_text(encoding="utf-8")
    workflow = (ROOT / "spec" / "workflows" / "control-plane.yaml").read_text(encoding="utf-8")
    ports = (ROOT / "spec" / "interfaces" / "control-ports.md").read_text(encoding="utf-8")
    for value in (semantic_text, workflow, ports):
        assert "control_journal" in value
        assert "WF-RECOVERY" in value
    assert "restore_before_barrier" in semantic_text
    assert "physical_storage_contract: deferred" in semantic_text


def test_semantic_contract_defines_typed_minimal_fact_operations() -> None:
    semantic = _semantic()
    assert set(semantic["operations"]) == {
        "ValidateControlEvent",
        "ValidateKillSwitchCommand",
        "ValidateKillSwitchResult",
        "ValidateConfigActivation",
    }
    result_inputs = semantic["operations"]["ValidateKillSwitchResult"]["inputs"]
    assert result_inputs == [
        "result",
        "persisted_command_fact",
        "optional_prior_persisted_result_fact",
        "current_scoped_state",
        "expected_effect_ack_authority",
        "injected_time",
    ]
