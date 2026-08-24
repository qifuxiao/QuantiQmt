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
        version = payload["state_version"]
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
    message_id = f"message-{name}-0001"
    idempotency_key = payload.get("idempotency_key", f"{name}:{aggregate}:{version}")
    return {
        "message_id": message_id,
        "message_type": name,
        "schema_version": 1,
        "occurred_at": occurred,
        "received_at": occurred,
        "correlation_id": message_id,
        "causation_id": None,
        "aggregate_id": aggregate,
        "aggregate_version": version,
        "source": source,
        "partition_key": partition,
        "idempotency_key": idempotency_key,
        "payload": payload,
    }


def _accepted_message_ref(parent_message: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": parent_message["message_id"],
        "correlation_id": parent_message["correlation_id"],
        "occurred_at": parent_message["occurred_at"],
        "accepted_at": parent_message["received_at"],
        "aggregate_id": parent_message["aggregate_id"],
        "aggregate_version": parent_message["aggregate_version"],
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


def _barrier_snapshot(
    *,
    scope_type: str = "GLOBAL",
    scope_id: str | None = None,
    barrier: dict[str, Any] | None = None,
) -> dict[str, Any]:
    barrier = deepcopy(barrier or _barrier())
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "barrier_version": 7,
        "stored_checksum": _sha(barrier),
        "barrier": barrier,
    }


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


def _validate_barrier_snapshot(
    snapshot: dict[str, Any], *, evaluation_at: str = CONTROL_TIME
) -> None:
    _scope_key(snapshot)
    barrier = snapshot["barrier"]
    _validate_barrier(barrier, evaluation_at=evaluation_at)
    if snapshot["barrier_version"] < 1:
        raise ValueError("recovery barrier version is invalid")
    if snapshot["stored_checksum"] != _sha(barrier):
        raise ValueError("recovery barrier stored checksum mismatch")


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
    snapshot = _barrier_snapshot(scope_type=scope_type, scope_id=scope_id)
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
    }
    if desired == "OFF":
        barrier = snapshot["barrier"]
        value.update(
            {
                "recovery_evidence_reference": barrier["barrier_id"],
                "recovery_barrier_generation": barrier["generation"],
                "recovery_barrier_version": snapshot["barrier_version"],
                "recovery_barrier_checksum": snapshot["stored_checksum"],
                "recovery_evidence_digest": _sha(barrier["evidence"]),
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


def _persisted_command(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_identity": {
            "operation_type": "KILL_SWITCH_COMMAND",
            "scope_type": command["scope_type"],
            "scope_id": command["scope_id"],
            "idempotency_key": command["idempotency_key"],
        },
        "stored_fingerprint": command["command_fingerprint"],
        "command": deepcopy(command),
    }


def _persisted_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_identity": {
            "operation_type": "KILL_SWITCH_COMMAND",
            "scope_type": result["scope_type"],
            "scope_id": result["scope_id"],
            "idempotency_key": result["idempotency_key"],
        },
        "result_id": result["result_id"],
        "stored_fingerprint": result["result_fingerprint"],
        "result": deepcopy(result),
    }


def _current_state(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope_type": command["scope_type"],
        "scope_id": command["scope_id"],
        "enabled": False,
        "version": command["expected_version"],
    }


def _same_content(left: dict[str, Any], right: dict[str, Any], fingerprint: str) -> bool:
    return left == right and left[fingerprint] == right[fingerprint]


def _kill_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation_type": "KILL_SWITCH_COMMAND",
        "scope_type": value["scope_type"],
        "scope_id": value["scope_id"],
        "idempotency_key": value["idempotency_key"],
    }


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
        if prior_fact["query_identity"] != _kill_identity(command):
            raise ValueError("persisted command query identity mismatch")
        prior = prior_fact["command"]
        if prior_fact["stored_fingerprint"] != prior["command_fingerprint"]:
            raise ValueError("persisted command stored fingerprint mismatch")
        if prior["command_fingerprint"] != _fingerprint(prior, COMMAND_FIELDS):
            raise ValueError("persisted command fingerprint mismatch")
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
        _validate_barrier_snapshot(barrier, evaluation_at=evaluation_at)
        barrier_snapshot = barrier["barrier"]
        if (barrier["scope_type"], barrier["scope_id"]) != (
            command["scope_type"],
            command["scope_id"],
        ):
            raise ValueError("recovery barrier scope mismatch")
        if command["recovery_evidence_reference"] != barrier_snapshot["barrier_id"]:
            raise ValueError("recovery barrier identity mismatch")
        if command["recovery_barrier_generation"] != barrier_snapshot["generation"]:
            raise ValueError("recovery barrier generation mismatch")
        if command["recovery_barrier_version"] != barrier["barrier_version"]:
            raise ValueError("recovery barrier version mismatch")
        if command["recovery_barrier_checksum"] != barrier["stored_checksum"]:
            raise ValueError("recovery barrier checksum mismatch")
        if command["recovery_evidence_digest"] != _sha(barrier_snapshot["evidence"]):
            raise ValueError("recovery barrier evidence mismatch")
        if command["leader_lease_id"] != barrier_snapshot["evidence"]["lease_id"]:
            raise ValueError("recovery barrier lease mismatch")
        if command["fencing_token"] != barrier_snapshot["evidence"]["fencing_token"]:
            raise ValueError("recovery barrier fence mismatch")
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
    if persisted_command_fact["query_identity"] != _kill_identity(result):
        raise ValueError("persisted command query identity mismatch")
    command = persisted_command_fact["command"]
    if persisted_command_fact["stored_fingerprint"] != command["command_fingerprint"]:
        raise ValueError("persisted command stored fingerprint mismatch")
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
        if prior_result_fact["query_identity"] != _kill_identity(result):
            raise ValueError("persisted result query identity mismatch")
        prior = prior_result_fact["result"]
        if prior_result_fact["result_id"] != prior["result_id"]:
            raise ValueError("persisted result identity binding mismatch")
        if prior_result_fact["stored_fingerprint"] != prior["result_fingerprint"]:
            raise ValueError("persisted result stored fingerprint mismatch")
        if prior["result_fingerprint"] != _fingerprint(prior, RESULT_FIELDS):
            raise ValueError("persisted result fingerprint mismatch")
        if _same_content(prior, result, "result_fingerprint"):
            return "DUPLICATE"
        raise ValueError("QQ-STORAGE-7001 persisted result conflict")
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
    message: dict[str, Any],
    *,
    barrier_snapshot: dict[str, Any] | None = None,
    parent_ref: dict[str, Any] | None = None,
) -> None:
    _validator("common/message-envelope.v1.schema.json").validate(message)
    _validator(COMBINED_SCHEMA).validate(message)
    payload = message["payload"]
    name = message["message_type"]
    if name == "system.mode_changed.v1":
        aggregate = partition = _scope_key(payload)
        version = payload["state_version"]
        source = "TradingCore"
        occurred_at = payload["changed_at"]
    elif name == "system.component_health_changed.v1":
        aggregate = partition = payload["component_id"]
        version = payload["state_version"]
        source = "HealthService"
        occurred_at = payload["changed_at"]
    elif name == "system.kill_switch_changed.v1":
        aggregate = partition = _scope_key(payload)
        version = payload["current_version"]
        source = "ControlPlane"
        occurred_at = payload["changed_at"]
    else:
        aggregate = partition = payload["config_domain"]
        version = payload["activation_sequence"]
        source = "ConfigService"
        occurred_at = payload["activated_at"]
    expected_idempotency = payload.get("idempotency_key", f"{name}:{aggregate}:{version}")
    bindings = {
        "message_type": name,
        "schema_version": 1,
        "source": source,
        "aggregate_id": aggregate,
        "partition_key": partition,
        "aggregate_version": version,
        "occurred_at": occurred_at,
        "idempotency_key": expected_idempotency,
    }
    for field, expected in bindings.items():
        if message[field] != expected:
            raise ValueError(f"event envelope {field} binding mismatch")
    if message["causation_id"] is None:
        if parent_ref is not None or message["correlation_id"] != message["message_id"]:
            raise ValueError("invalid root event identity")
    else:
        if parent_ref is None:
            raise ValueError("non-root event requires accepted parent reference")
        if message["causation_id"] != parent_ref["message_id"]:
            raise ValueError("event causation parent identity mismatch")
        if message["correlation_id"] != parent_ref["correlation_id"]:
            raise ValueError("event parent correlation mismatch")
        if _instant(parent_ref["occurred_at"]) > _instant(message["occurred_at"]):
            raise ValueError("event parent is later than child")
        if _instant(parent_ref["accepted_at"]) > _instant(message["received_at"]):
            raise ValueError("event parent was accepted after child")
        if (
            parent_ref["aggregate_id"] == message["aggregate_id"]
            and parent_ref["aggregate_version"] >= message["aggregate_version"]
        ):
            raise ValueError("event parent aggregate order is not earlier")
    if name == "system.mode_changed.v1":
        if payload["from_mode"] == "STARTING" and payload["to_mode"] == "NORMAL":
            if barrier_snapshot is None:
                raise ValueError("RecoveryPassed requires OPEN barrier")
            _validate_barrier_snapshot(barrier_snapshot)
            if (barrier_snapshot["scope_type"], barrier_snapshot["scope_id"]) != (
                payload["scope_type"],
                payload["scope_id"],
            ):
                raise ValueError("mode recovery barrier scope mismatch")
            if (
                payload["evidence"]["recovery_barrier_id"]
                != barrier_snapshot["barrier"]["barrier_id"]
            ):
                raise ValueError("mode recovery barrier mismatch")
    elif name == "system.kill_switch_changed.v1":
        if payload["current_version"] != payload["previous_version"] + 1:
            raise ValueError("changed event must advance exactly once")
    elif name == "config.version_activated.v1":
        previous = (payload["previous_version"], payload["previous_checksum"])
        if (previous[0] is None) != (previous[1] is None):
            raise ValueError("previous ActiveVersion reference is incomplete")
        trigger = (
            payload["trigger_candidate_version"],
            payload["trigger_candidate_checksum"],
        )
        active = (payload["active_version"], payload["active_checksum"])
        if payload["activation_kind"] == "CANDIDATE_COMMIT":
            if trigger != active or payload["rollback_cause_result_id"] is not None:
                raise ValueError("candidate commit authority binding mismatch")
        else:
            if trigger != previous or not payload["rollback_cause_result_id"]:
                raise ValueError("rollback restore authority binding mismatch")
            if active == previous:
                raise ValueError("rollback restore must change ActiveVersion")


def _validate_config_event_candidate_binding(
    payload: dict[str, Any], candidate: dict[str, Any]
) -> None:
    if payload["config_domain"] != candidate["config_domain"]:
        raise ValueError("activated event candidate domain mismatch")
    if (
        payload["trigger_candidate_version"],
        payload["trigger_candidate_checksum"],
    ) != (candidate["candidate_version"], candidate["candidate_checksum"]):
        raise ValueError("activated event trigger candidate mismatch")
    if payload["activation_kind"] != "CANDIDATE_COMMIT":
        return
    for field in ("activation_mode", "safe_boundary", "policy_version", "policy_checksum"):
        if payload[field] != candidate[field]:
            raise ValueError("candidate commit metadata mismatch")
    for field in ("secret_references", "required_components"):
        if set(payload[field]) != set(candidate[field]):
            raise ValueError("candidate commit set mismatch")


@pytest.mark.parametrize("name,relative", EVENT_SCHEMAS.items())
def test_public_event_golden_fixtures(name: str, relative: str) -> None:
    validator = _validator(relative)
    folder = FIXTURES / name
    validator.validate(_load_json(folder / "minimal.valid.json", exact=True))
    validator.validate(_load_json(folder / "maximal.valid.json", exact=True))
    for filename in (
        "invalid.missing-required.json",
        "invalid.additional-property.json",
        "invalid.precision.json",
        "invalid.unknown-enum.json",
    ):
        invalid = folder / filename
        assert invalid.exists(), invalid
        assert list(validator.iter_errors(_load_json(invalid, exact=True))), invalid
    for valid in sorted(folder.glob("condition.*.valid.json")):
        validator.validate(_load_json(valid, exact=True))
    for invalid in sorted(folder.glob("condition.*.invalid.json")):
        assert list(validator.iter_errors(_load_json(invalid, exact=True))), invalid


def test_internal_control_DTO_golden_fixture_matrix() -> None:
    validator = _validator(CONTROL_SCHEMA)
    document = _load_json(FIXTURES / "control-plane.v1" / "valid.json", exact=True)
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    command = _command()
    result = _result(command)
    config_result = _candidate_result()
    barrier = _barrier()
    generated = [config_result, command, result, _lease(), barrier]
    by_type.update({dto["dto_type"]: dto for dto in generated})
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
        message,
        barrier_snapshot=_barrier_snapshot() if name == "system.mode_changed.v1" else None,
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
    with pytest.raises(ValueError, match=r"identity|binding"):
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
    with pytest.raises(ValueError, match=r"scope|aggregate_id"):
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


def test_config_activated_event_represents_candidate_and_rollback_authority_commits() -> None:
    validator = _validator(EVENT_SCHEMAS["config.version_activated.v1"])
    candidate_commit = _event_payload("config.version_activated.v1")
    validator.validate(candidate_commit)
    assert "component_acks" not in candidate_commit
    _validate_event_semantics(_message("config.version_activated.v1", candidate_commit))

    rollback_restore = deepcopy(candidate_commit)
    rollback_restore.update(
        {
            "activation_kind": "ROLLBACK_RESTORE",
            "previous_version": candidate_commit["active_version"],
            "previous_checksum": candidate_commit["active_checksum"],
            "active_version": "v1",
            "active_checksum": CHECKSUM_B,
            "rollback_cause_result_id": "config-result-rollback-0001",
            "activation_sequence": candidate_commit["activation_sequence"] + 1,
        }
    )
    validator.validate(rollback_restore)
    rollback_message = _message("config.version_activated.v1", rollback_restore)
    _validator("common/message-envelope.v1.schema.json").validate(rollback_message)
    _validator(COMBINED_SCHEMA).validate(rollback_message)
    _validate_event_semantics(rollback_message)

    for field in ("component_acks", "candidate_effect", "rollback_effect"):
        invalid = deepcopy(candidate_commit)
        invalid[field] = {}
        assert list(validator.iter_errors(invalid))
    invalid = deepcopy(candidate_commit)
    invalid["rollback_cause_result_id"] = "config-result-rollback-0001"
    assert list(validator.iter_errors(invalid))
    invalid = deepcopy(rollback_restore)
    invalid["rollback_cause_result_id"] = None
    assert list(validator.iter_errors(invalid))
    for mutation in ("candidate_trigger", "rollback_trigger"):
        invalid = deepcopy(
            candidate_commit if mutation == "candidate_trigger" else rollback_restore
        )
        invalid["trigger_candidate_checksum"] = CHECKSUM_B
        with pytest.raises(ValueError, match="authority binding"):
            _validate_event_semantics(_message("config.version_activated.v1", invalid))


def test_config_result_binds_candidate_and_rollback_authority_event_references() -> None:
    result = _candidate_result(outcome="ROLLED_BACK")
    _validator(CONTROL_SCHEMA).validate(result)
    assert (
        result["rollback_restore_activation_sequence"]
        > result["candidate_commit_activation_sequence"]
    )

    missing_restore = deepcopy(result)
    missing_restore["rollback_restore_message_id"] = None
    missing_restore["rollback_restore_activation_sequence"] = None
    assert list(_validator(CONTROL_SCHEMA).iter_errors(missing_restore))

    forged_reference = _config_activation_event_refs(result)
    forged_reference["ROLLBACK_RESTORE"]["active_checksum"] = CHECKSUM_A
    with pytest.raises(ValueError, match="Event reference mismatch"):
        validate_config_result(
            result,
            current_active={"version": "v1", "checksum": CHECKSUM_B},
            activation_event_refs=forged_reference,
        )


def test_config_activation_workflow_orders_authority_events_around_component_effects() -> None:
    semantic = _semantic()["config_activation"]
    binding = semantic["activated_event_binding"]
    assert binding["CANDIDATE_COMMIT"]["order"] == (
        "after_prepare_before_swap_and_component_effect_ACKs"
    )
    assert binding["common"]["component_effect_fields"] == "forbidden"
    assert (
        semantic["result_outcome_matrix"]["APPLIED"]["additional_public_event_after_effects"]
        == "forbidden"
    )
    assert binding["ROLLBACK_RESTORE"]["prerequisite"] == (
        "complete_internal_rollback_effect_evidence"
    )
    partial = _candidate_result(outcome="PARTIAL")
    unknown = _candidate_result(outcome="UNKNOWN")
    for result in (partial, unknown):
        assert result["rollback_restore_message_id"] is None
        assert result["rollback_restore_activation_sequence"] is None


CONFIG_RESULT_FIELDS = [
    "dto_type",
    "schema_version",
    "result_id",
    "idempotency_key",
    "config_domain",
    "candidate_version",
    "candidate_checksum",
    "required_components",
    "outcome",
    "component_acks",
    "previous_active_version",
    "previous_active_checksum",
    "active_version",
    "active_checksum",
    "rollback_version",
    "rollback_checksum",
    "candidate_commit_message_id",
    "candidate_commit_activation_sequence",
    "rollback_restore_message_id",
    "rollback_restore_activation_sequence",
    "commit_state",
    "side_effect_state",
    "reconciliation_required",
    "safe_scope_required",
    "safe_scope_action",
]


def _candidate_result(*, outcome: str = "APPLIED") -> dict[str, Any]:
    candidate = _candidate()
    component_statuses = {
        "APPLIED": [("PREPARED", "APPLIED", "NOT_REQUIRED")] * 2,
        "REJECTED": [("REJECTED", "NOT_ATTEMPTED", "NOT_REQUIRED")] * 2,
        "PARTIAL": [
            ("PREPARED", "APPLIED", "UNKNOWN"),
            ("PREPARED", "REJECTED", "NOT_REQUIRED"),
        ],
        "ROLLED_BACK": [("PREPARED", "APPLIED", "APPLIED")] * 2,
        "UNKNOWN": [("PREPARED", "APPLIED", "NOT_REQUIRED")] * 2,
    }[outcome]
    ack: dict[str, Any] = {}
    for index, (component, authority) in enumerate(candidate["component_authority"].items()):
        prepare, candidate_status, rollback_status = component_statuses[index]
        ack[component] = {
            "component_id": component,
            "generation": authority["generation"],
            "capability_version": authority["capability_version"],
            "prepare_result": prepare,
            "candidate_effect": {
                "status": candidate_status,
                "target_version": (
                    None if candidate_status == "NOT_ATTEMPTED" else candidate["candidate_version"]
                ),
                "target_checksum": (
                    None if candidate_status == "NOT_ATTEMPTED" else candidate["candidate_checksum"]
                ),
            },
            "rollback_effect": {
                "status": rollback_status,
                "target_version": None if rollback_status == "NOT_REQUIRED" else "v1",
                "target_checksum": None if rollback_status == "NOT_REQUIRED" else CHECKSUM_B,
            },
            "activation_mode": authority["activation_mode"],
            "safe_boundary": authority["safe_boundary"],
            "observed_at": CONTROL_TIME,
            "ack_sequence": index + 1,
        }
    shapes = {
        "APPLIED": (
            candidate["candidate_version"],
            candidate["candidate_checksum"],
            None,
            None,
            "COMMITTED",
            "COMPLETE",
            False,
            False,
            "NONE",
        ),
        "REJECTED": (
            None,
            None,
            None,
            None,
            "NOT_COMMITTED",
            "NONE",
            False,
            False,
            "NONE",
        ),
        "PARTIAL": (
            candidate["candidate_version"],
            candidate["candidate_checksum"],
            None,
            None,
            "COMMITTED",
            "PARTIAL",
            True,
            True,
            "ENTER_SAFE_MODE",
        ),
        "ROLLED_BACK": (
            "v1",
            CHECKSUM_B,
            "v1",
            CHECKSUM_B,
            "COMMITTED",
            "COMPLETE",
            False,
            False,
            "NONE",
        ),
        "UNKNOWN": (
            None,
            None,
            None,
            None,
            "UNKNOWN",
            "UNKNOWN",
            True,
            True,
            "ENTER_SAFE_MODE",
        ),
    }
    (
        active_version,
        active_checksum,
        rollback_version,
        rollback_checksum,
        commit_state,
        side_effect_state,
        reconciliation_required,
        safe_scope_required,
        safe_scope_action,
    ) = shapes[outcome]
    value = {
        "dto_type": "CONFIG_ACTIVATION_RESULT",
        "schema_version": 1,
        "correlation_id": candidate["correlation_id"],
        "created_at": CONTROL_TIME,
        "result_id": "config-result-0001",
        "result_fingerprint": "0" * 64,
        "idempotency_key": candidate["idempotency_key"],
        "config_domain": candidate["config_domain"],
        "candidate_version": candidate["candidate_version"],
        "candidate_checksum": candidate["candidate_checksum"],
        "required_components": candidate["required_components"],
        "outcome": outcome,
        "component_acks": ack,
        "previous_active_version": "v1",
        "previous_active_checksum": CHECKSUM_B,
        "active_version": active_version,
        "active_checksum": active_checksum,
        "rollback_version": rollback_version,
        "rollback_checksum": rollback_checksum,
        "candidate_commit_message_id": (
            "config-candidate-event-0001"
            if outcome in {"APPLIED", "PARTIAL", "ROLLED_BACK"}
            else None
        ),
        "candidate_commit_activation_sequence": (
            10 if outcome in {"APPLIED", "PARTIAL", "ROLLED_BACK"} else None
        ),
        "rollback_restore_message_id": (
            "config-rollback-event-0001" if outcome == "ROLLED_BACK" else None
        ),
        "rollback_restore_activation_sequence": 11 if outcome == "ROLLED_BACK" else None,
        "commit_state": commit_state,
        "side_effect_state": side_effect_state,
        "reconciliation_required": reconciliation_required,
        "safe_scope_required": safe_scope_required,
        "safe_scope_action": safe_scope_action,
    }
    value["result_fingerprint"] = _fingerprint(value, CONFIG_RESULT_FIELDS)
    return value


def _persisted_config_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_identity": {
            "operation_type": "CONFIG_ACTIVATION",
            "config_domain": result["config_domain"],
            "candidate_version": result["candidate_version"],
            "idempotency_key": result["idempotency_key"],
        },
        "result_id": result["result_id"],
        "stored_fingerprint": result["result_fingerprint"],
        "result": deepcopy(result),
    }


def _config_activation_event_refs(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    if result["candidate_commit_message_id"] is not None:
        refs["CANDIDATE_COMMIT"] = {
            "message_id": result["candidate_commit_message_id"],
            "activation_kind": "CANDIDATE_COMMIT",
            "config_domain": result["config_domain"],
            "trigger_candidate_version": result["candidate_version"],
            "trigger_candidate_checksum": result["candidate_checksum"],
            "previous_version": result["previous_active_version"],
            "previous_checksum": result["previous_active_checksum"],
            "active_version": result["candidate_version"],
            "active_checksum": result["candidate_checksum"],
            "rollback_cause_result_id": None,
            "activation_sequence": result["candidate_commit_activation_sequence"],
        }
    if result["rollback_restore_message_id"] is not None:
        refs["ROLLBACK_RESTORE"] = {
            "message_id": result["rollback_restore_message_id"],
            "activation_kind": "ROLLBACK_RESTORE",
            "config_domain": result["config_domain"],
            "trigger_candidate_version": result["candidate_version"],
            "trigger_candidate_checksum": result["candidate_checksum"],
            "previous_version": result["candidate_version"],
            "previous_checksum": result["candidate_checksum"],
            "active_version": result["previous_active_version"],
            "active_checksum": result["previous_active_checksum"],
            "rollback_cause_result_id": result["result_id"],
            "activation_sequence": result["rollback_restore_activation_sequence"],
        }
    return refs


def validate_config_result(
    result: dict[str, Any],
    *,
    current_active: dict[str, str | None],
    prior_result_fact: dict[str, Any] | None = None,
    activation_event_refs: dict[str, dict[str, Any]] | None = None,
) -> str:
    _validator(CONTROL_SCHEMA).validate(result)
    if result["result_fingerprint"] != _fingerprint(result, CONFIG_RESULT_FIELDS):
        raise ValueError("config result fingerprint mismatch")
    identity = {
        "operation_type": "CONFIG_ACTIVATION",
        "config_domain": result["config_domain"],
        "candidate_version": result["candidate_version"],
        "idempotency_key": result["idempotency_key"],
    }
    if prior_result_fact is not None:
        if prior_result_fact["query_identity"] != identity:
            raise ValueError("persisted config result query identity mismatch")
        prior = prior_result_fact["result"]
        if prior_result_fact["result_id"] != prior["result_id"]:
            raise ValueError("persisted config result identity mismatch")
        if prior_result_fact["stored_fingerprint"] != prior["result_fingerprint"]:
            raise ValueError("persisted config result stored fingerprint mismatch")
        if prior["result_fingerprint"] != _fingerprint(prior, CONFIG_RESULT_FIELDS):
            raise ValueError("persisted config result fingerprint mismatch")
        if _same_content(prior, result, "result_fingerprint"):
            return "DUPLICATE"
        raise ValueError("QQ-STORAGE-7001 config result conflict")
    if result["previous_active_version"] != current_active["version"]:
        raise ValueError("previous active version authority mismatch")
    if result["previous_active_checksum"] != current_active["checksum"]:
        raise ValueError("previous active checksum authority mismatch")
    if set(result["component_acks"]) != set(result["required_components"]):
        raise ValueError("config result component set mismatch")
    candidate = _candidate()
    for component, ack in result["component_acks"].items():
        authority = candidate["component_authority"][component]
        for field in (
            "component_id",
            "generation",
            "capability_version",
            "activation_mode",
            "safe_boundary",
        ):
            expected = component if field == "component_id" else authority[field]
            if ack[field] != expected:
                raise ValueError("config result component binding mismatch")
        candidate_effect = ack["candidate_effect"]
        if ack["prepare_result"] == "REJECTED" and candidate_effect["status"] != "NOT_ATTEMPTED":
            raise ValueError("rejected prepare cannot attempt candidate")
        if ack["prepare_result"] == "UNKNOWN" and candidate_effect["status"] not in {
            "NOT_ATTEMPTED",
            "UNKNOWN",
        }:
            raise ValueError("unknown prepare has contradictory candidate effect")
        if (
            candidate_effect["status"] in {"APPLIED", "REJECTED"}
            and ack["prepare_result"] != "PREPARED"
        ):
            raise ValueError("candidate effect requires prepared component")
        if candidate_effect["status"] != "NOT_ATTEMPTED" and (
            candidate_effect["target_version"] != result["candidate_version"]
            or candidate_effect["target_checksum"] != result["candidate_checksum"]
        ):
            raise ValueError("candidate effect target mismatch")
        rollback_effect = ack["rollback_effect"]
        if rollback_effect["status"] != "NOT_REQUIRED" and (
            rollback_effect["target_version"] != result["previous_active_version"]
            or rollback_effect["target_checksum"] != result["previous_active_checksum"]
        ):
            raise ValueError("rollback effect target mismatch")
    candidate_statuses = {
        ack["candidate_effect"]["status"] for ack in result["component_acks"].values()
    }
    rollback_statuses = {
        ack["rollback_effect"]["status"] for ack in result["component_acks"].values()
    }
    if result["outcome"] == "APPLIED":
        if result["active_version"] != result["candidate_version"]:
            raise ValueError("APPLIED active version mismatch")
        if result["active_checksum"] != result["candidate_checksum"]:
            raise ValueError("APPLIED active checksum mismatch")
        if candidate_statuses != {"APPLIED"} or rollback_statuses != {"NOT_REQUIRED"}:
            raise ValueError("APPLIED requires complete candidate effects")
    elif result["outcome"] == "REJECTED":
        if not candidate_statuses <= {"NOT_ATTEMPTED", "REJECTED"} or rollback_statuses != {
            "NOT_REQUIRED"
        }:
            raise ValueError("REJECTED cannot claim applied effect")
    elif result["outcome"] == "PARTIAL":
        if (
            result["active_version"] != result["candidate_version"]
            or result["active_checksum"] != result["candidate_checksum"]
        ):
            raise ValueError("PARTIAL must retain committed candidate authority")
        if candidate_statuses == {"APPLIED"} or candidate_statuses <= {"NOT_ATTEMPTED", "REJECTED"}:
            raise ValueError("PARTIAL requires mixed or unknown effect evidence")
    elif result["outcome"] == "ROLLED_BACK":
        target = (current_active["version"], current_active["checksum"])
        if (result["active_version"], result["active_checksum"]) != target or (
            result["rollback_version"],
            result["rollback_checksum"],
        ) != target:
            raise ValueError("rollback target is not previous ActiveVersion")
        for ack in result["component_acks"].values():
            candidate_status = ack["candidate_effect"]["status"]
            rollback_status = ack["rollback_effect"]["status"]
            if candidate_status == "UNKNOWN" or rollback_status == "UNKNOWN":
                raise ValueError("completed rollback cannot contain unknown effect")
            if candidate_status == "APPLIED" and rollback_status != "APPLIED":
                raise ValueError("applied component was not rolled back")
            if candidate_status != "APPLIED" and rollback_status != "NOT_REQUIRED":
                raise ValueError("unapplied component must not claim rollback")
        if (
            result["rollback_restore_activation_sequence"]
            <= result["candidate_commit_activation_sequence"]
        ):
            raise ValueError("rollback restore authority must follow candidate commit")
    elif result["outcome"] == "UNKNOWN" and result["candidate_commit_message_id"] is not None:
        if (
            result["active_version"] != result["candidate_version"]
            or result["active_checksum"] != result["candidate_checksum"]
        ):
            raise ValueError("UNKNOWN must retain the last known candidate authority")
    expected_refs = _config_activation_event_refs(result)
    if activation_event_refs != expected_refs:
        raise ValueError("config result activation Event reference mismatch")
    return "ACCEPTED"


def test_starting_to_normal_requires_complete_fresh_open_barrier() -> None:
    message = _message("system.mode_changed.v1", _event_payload("system.mode_changed.v1"))
    with pytest.raises(ValueError, match="requires OPEN"):
        _validate_event_semantics(message)
    _validate_event_semantics(message, barrier_snapshot=_barrier_snapshot())
    for mutation in ("closed", "missing_gate", "future", "stale"):
        barrier_snapshot = _barrier(state="CLOSED" if mutation == "closed" else "OPEN")
        if mutation == "missing_gate":
            barrier_snapshot["required_evidence"].remove("MARKET_FRESH")
        elif mutation == "future":
            barrier_snapshot["evidence"]["observed_at"] = "2026-08-11T01:00:00.1Z"
        elif mutation == "stale":
            barrier_snapshot["evidence"]["market_fresh_until"] = CONTROL_TIME
        barrier = _barrier_snapshot(barrier=barrier_snapshot)
        with pytest.raises((ValueError, ValidationError)):
            _validate_event_semantics(message, barrier_snapshot=barrier)

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


def test_config_candidate_commit_binds_security_fields_without_component_effects() -> None:
    candidate = _candidate()
    payload = _event_payload("config.version_activated.v1")
    payload.update(
        {
            "config_domain": candidate["config_domain"],
            "activation_kind": "CANDIDATE_COMMIT",
            "trigger_candidate_version": candidate["candidate_version"],
            "trigger_candidate_checksum": candidate["candidate_checksum"],
            "active_version": candidate["candidate_version"],
            "active_checksum": candidate["candidate_checksum"],
            "activation_mode": candidate["activation_mode"],
            "safe_boundary": candidate["safe_boundary"],
            "required_components": candidate["required_components"],
            "secret_references": candidate["secret_references"],
            "policy_version": candidate["policy_version"],
            "policy_checksum": candidate["policy_checksum"],
            "rollback_cause_result_id": None,
        }
    )
    message = _message("config.version_activated.v1", payload)
    _validate_event_semantics(message)
    _validate_config_event_candidate_binding(payload, candidate)
    assert "component_acks" not in payload
    for mutation in ("wrong_trigger", "wrong_checksum", "wrong_secret", "wrong_boundary"):
        invalid = deepcopy(payload)
        if mutation == "wrong_trigger":
            invalid["trigger_candidate_checksum"] = CHECKSUM_B
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
            prior_result_fact=_persisted_result(result),
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
                prior_result_fact=_persisted_result(result),
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
    barrier = _barrier_snapshot()
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
    allowed = set(semantic["alert_definition_label_allowlist"])
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


def test_semantic_contract_defines_operation_specific_inputs() -> None:
    semantic = _semantic()
    assert set(semantic["operations"]) == {
        "ValidateControlEvent",
        "ValidateRecoveryPassed",
        "ValidateKillSwitchCommand",
        "ValidateKillSwitchResult",
        "ValidateConfigActivation",
    }
    result_inputs = semantic["operations"]["ValidateKillSwitchResult"]["inputs"]
    assert result_inputs == [
        "result",
        "committed_command_record",
        "optional_prior_committed_result_record",
        "current_scoped_state",
        "expected_effect_ACK_set",
        "injected_time",
    ]
    assert _semantic()["operations"]["ValidateConfigActivation"]["inputs"][-2:] == [
        "optional_committed_activation_event_references",
        "injected_time",
    ]


def test_round8_config_activation_result_rejects_impossible_outcome_shapes() -> None:
    validator = _validator(CONTROL_SCHEMA)
    cases: list[dict[str, Any]] = []

    applied = _candidate_result(outcome="APPLIED")
    applied["active_version"] = None
    cases.append(applied)

    rejected = _candidate_result(outcome="REJECTED")
    rejected["active_version"] = rejected["candidate_version"]
    rejected["active_checksum"] = rejected["candidate_checksum"]
    cases.append(rejected)

    unknown = _candidate_result(outcome="UNKNOWN")
    unknown["active_version"] = unknown["candidate_version"]
    unknown["active_checksum"] = unknown["candidate_checksum"]
    cases.append(unknown)

    rolled_back = _candidate_result(outcome="ROLLED_BACK")
    rolled_back["active_version"] = rolled_back["candidate_version"]
    rolled_back["active_checksum"] = rolled_back["candidate_checksum"]
    rolled_back["rollback_version"] = None
    cases.append(rolled_back)

    for case in cases:
        assert list(validator.iter_errors(case)), case["outcome"]


def test_round8_event_semantics_reject_complete_envelope_binding_counterexamples() -> None:
    health = _message(
        "system.component_health_changed.v1",
        _event_payload("system.component_health_changed.v1"),
    )
    health["aggregate_version"] = 999
    with pytest.raises(ValueError):
        _validate_event_semantics(health)

    health = _message(
        "system.component_health_changed.v1",
        _event_payload("system.component_health_changed.v1"),
    )
    health["occurred_at"] = "2026-08-11T00:59:59Z"
    with pytest.raises(ValueError):
        _validate_event_semantics(health)

    config = _message(
        "config.version_activated.v1",
        _event_payload("config.version_activated.v1"),
    )
    config["partition_key"] = "wrong-domain"
    with pytest.raises(ValueError):
        _validate_event_semantics(config)

    mode = _message("system.mode_changed.v1", _event_payload("system.mode_changed.v1"))
    mode["idempotency_key"] = "wrong-idempotency"
    with pytest.raises(ValueError):
        _validate_event_semantics(mode, barrier_snapshot=_barrier_snapshot())


def test_round8_component_health_has_independent_state_version() -> None:
    schema = _load_json(CONTRACTS / EVENT_SCHEMAS["system.component_health_changed.v1"])
    assert "state_version" in schema["required"]
    assert (
        _semantic()["public_events"]["bindings"]["system.component_health_changed.v1"][
            "aggregate_version"
        ]
        == "payload.state_version"
    )


def test_round8_alert_definition_and_runtime_metric_labels_are_separate() -> None:
    semantic = _semantic()["observability"]
    nfr = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "spec/nfr/observability.yaml").read_text(encoding="utf-8")),
    )["nfr"]["control_plane"]
    control_schema = _load_json(CONTRACTS / CONTROL_SCHEMA)
    schema_alert_labels = set(
        control_schema["$defs"]["alertDefinition"]["allOf"][1]["properties"]["label_keys"]["items"][
            "enum"
        ]
    )
    expected_alert_labels = {
        "severity",
        "component",
        "alert_code",
        "environment",
        "policy_version",
    }
    assert set(semantic["alert_definition_label_allowlist"]) == expected_alert_labels
    assert set(nfr["alert_definition_label_allowlist"]) == expected_alert_labels
    assert schema_alert_labels == expected_alert_labels
    runtime = semantic["runtime_metric_label_allowlists"]
    assert runtime == nfr["runtime_metric_label_allowlists"]
    assert runtime["kill_switch_transition_total"] == [
        "scope_type",
        "desired_state",
        "outcome",
    ]
    assert semantic["raw_scope_id_metric_label"] == "forbidden"
    assert nfr["scope_metric_label"] == "scope_type_only"
    assert "scope_id" in semantic["runtime_metric_forbidden_labels"]
    assert "scope_id" in nfr["metric_label_forbidden"]


def test_round8_stale_control_events_aggregate_fixture_is_removed() -> None:
    assert not (FIXTURES / "control-events.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("recovery_evidence_reference", "different-barrier"),
        ("recovery_barrier_generation", 5),
        ("recovery_barrier_version", 8),
        ("recovery_barrier_checksum", CHECKSUM_B),
        ("recovery_evidence_digest", CHECKSUM_B),
    ],
)
def test_off_command_rejects_barrier_reference_mismatch(field: str, value: Any) -> None:
    command = _command(desired="OFF")
    command[field] = value
    command["command_fingerprint"] = _fingerprint(command, COMMAND_FIELDS)
    with pytest.raises((ValueError, ValidationError)):
        validate_kill_command(
            command,
            current_state=_current_state(command),
            authorization=_authorization(),
            lease=_lease(),
            barrier=_barrier_snapshot(),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_scope",
        "wrong_generation",
        "wrong_lease",
        "wrong_fence",
        "missing_gate",
        "stale_gate",
        "closed",
        "stored_checksum_corruption",
    ],
)
def test_recovery_snapshot_reference_and_integrity_fail_closed(mutation: str) -> None:
    command = _command(desired="OFF")
    barrier = _barrier()
    snapshot = _barrier_snapshot(barrier=barrier)
    if mutation == "wrong_scope":
        snapshot.update({"scope_type": "ACCOUNT", "scope_id": "acct-1"})
    elif mutation == "wrong_generation":
        barrier["generation"] += 1
    elif mutation == "wrong_lease":
        barrier["evidence"]["lease_id"] = "other-lease"
    elif mutation == "wrong_fence":
        barrier["evidence"]["fencing_token"] = "other-fencing-token"
    elif mutation == "missing_gate":
        barrier["required_evidence"].remove("OUTBOX_HEALTHY")
    elif mutation == "stale_gate":
        barrier["evidence"]["market_fresh_until"] = CONTROL_TIME
    elif mutation == "closed":
        barrier["state"] = "CLOSED"
        barrier["opened_at"] = None
    else:
        snapshot["stored_checksum"] = CHECKSUM_B
    if mutation not in {"wrong_scope", "stored_checksum_corruption"}:
        snapshot = _barrier_snapshot(barrier=barrier)
    with pytest.raises((ValueError, ValidationError)):
        validate_kill_command(
            command,
            current_state=_current_state(command),
            authorization=_authorization(),
            lease=_lease(),
            barrier=snapshot,
        )


@pytest.mark.parametrize("outcome", ["APPLIED", "REJECTED", "PARTIAL", "ROLLED_BACK", "UNKNOWN"])
def test_round8_config_activation_result_complete_outcome_matrix(outcome: str) -> None:
    result = _candidate_result(outcome=outcome)
    assert (
        validate_config_result(
            result,
            current_active={"version": "v1", "checksum": CHECKSUM_B},
            activation_event_refs=_config_activation_event_refs(result),
        )
        == "ACCEPTED"
    )


def test_config_unknown_supports_commit_unknown_and_post_commit_reconciliation() -> None:
    current = {"version": "v1", "checksum": CHECKSUM_B}
    commit_unknown = _candidate_result(outcome="UNKNOWN")
    assert (
        validate_config_result(
            commit_unknown,
            current_active=current,
            activation_event_refs={},
        )
        == "ACCEPTED"
    )

    post_commit_unknown = _candidate_result(outcome="UNKNOWN")
    post_commit_unknown.update(
        {
            "active_version": post_commit_unknown["candidate_version"],
            "active_checksum": post_commit_unknown["candidate_checksum"],
            "candidate_commit_message_id": "config-candidate-event-0001",
            "candidate_commit_activation_sequence": 10,
        }
    )
    post_commit_unknown["result_fingerprint"] = _fingerprint(
        post_commit_unknown, CONFIG_RESULT_FIELDS
    )
    assert (
        validate_config_result(
            post_commit_unknown,
            current_active=current,
            activation_event_refs=_config_activation_event_refs(post_commit_unknown),
        )
        == "ACCEPTED"
    )


def test_config_component_effect_contradictions_fail_closed() -> None:
    current = {"version": "v1", "checksum": CHECKSUM_B}
    cases: list[dict[str, Any]] = []

    missing_rollback = _candidate_result(outcome="ROLLED_BACK")
    missing_rollback["component_acks"]["OMS"]["rollback_effect"] = {
        "status": "NOT_REQUIRED",
        "target_version": None,
        "target_checksum": None,
    }
    cases.append(missing_rollback)

    wrong_rollback_target = _candidate_result(outcome="ROLLED_BACK")
    wrong_rollback_target["component_acks"]["OMS"]["rollback_effect"].update(
        {"target_version": "wrong-version", "target_checksum": CHECKSUM_A}
    )
    cases.append(wrong_rollback_target)

    incomplete_applied = _candidate_result(outcome="APPLIED")
    incomplete_applied["component_acks"].pop("OMS")
    cases.append(incomplete_applied)

    wrong_candidate_target = _candidate_result(outcome="APPLIED")
    wrong_candidate_target["component_acks"]["OMS"]["candidate_effect"]["target_checksum"] = (
        CHECKSUM_B
    )
    cases.append(wrong_candidate_target)

    contradictory_prepare = _candidate_result(outcome="APPLIED")
    contradictory_prepare["component_acks"]["OMS"]["prepare_result"] = "REJECTED"
    cases.append(contradictory_prepare)

    rejected_unknown = _candidate_result(outcome="REJECTED")
    rejected_unknown["component_acks"]["OMS"].update(
        {
            "prepare_result": "UNKNOWN",
            "candidate_effect": {
                "status": "UNKNOWN",
                "target_version": rejected_unknown["candidate_version"],
                "target_checksum": rejected_unknown["candidate_checksum"],
            },
        }
    )
    cases.append(rejected_unknown)

    for result in cases:
        result["result_fingerprint"] = _fingerprint(result, CONFIG_RESULT_FIELDS)
        with pytest.raises((ValueError, ValidationError)):
            validate_config_result(
                result,
                current_active=current,
                activation_event_refs=_config_activation_event_refs(result),
            )

    partial = _candidate_result(outcome="PARTIAL")
    partial.update(
        {
            "safe_scope_required": False,
            "safe_scope_action": "NONE",
            "reconciliation_required": False,
        }
    )
    partial["result_fingerprint"] = _fingerprint(partial, CONFIG_RESULT_FIELDS)
    with pytest.raises((ValueError, ValidationError)):
        validate_config_result(
            partial,
            current_active=current,
            activation_event_refs=_config_activation_event_refs(partial),
        )


def test_round8_config_result_duplicate_conflict_unknown_and_rollback_authority() -> None:
    current = {"version": "v1", "checksum": CHECKSUM_B}
    applied = _candidate_result(outcome="APPLIED")
    assert (
        validate_config_result(
            applied,
            current_active={"version": "advanced", "checksum": CHECKSUM_A},
            prior_result_fact=_persisted_config_result(applied),
        )
        == "DUPLICATE"
    )
    conflict = _candidate_result(outcome="UNKNOWN")
    with pytest.raises(ValueError, match="QQ-STORAGE-7001"):
        validate_config_result(
            conflict,
            current_active=current,
            prior_result_fact=_persisted_config_result(applied),
        )
    unknown = _candidate_result(outcome="UNKNOWN")
    unknown["reconciliation_required"] = False
    unknown["result_fingerprint"] = _fingerprint(unknown, CONFIG_RESULT_FIELDS)
    with pytest.raises((ValueError, ValidationError)):
        validate_config_result(
            unknown,
            current_active=current,
            activation_event_refs=_config_activation_event_refs(unknown),
        )
    rolled_back = _candidate_result(outcome="ROLLED_BACK")
    rolled_back["active_version"] = rolled_back["candidate_version"]
    rolled_back["active_checksum"] = rolled_back["candidate_checksum"]
    rolled_back["result_fingerprint"] = _fingerprint(rolled_back, CONFIG_RESULT_FIELDS)
    with pytest.raises(ValueError, match="rollback target"):
        validate_config_result(
            rolled_back,
            current_active=current,
            activation_event_refs=_config_activation_event_refs(rolled_back),
        )


def test_non_root_event_requires_exact_accepted_message_reference() -> None:
    parent_message = _message(
        "system.component_health_changed.v1",
        _event_payload("system.component_health_changed.v1"),
    )
    parent = _accepted_message_ref(parent_message)
    child = _message(
        "system.component_health_changed.v1",
        deepcopy(parent_message["payload"]),
    )
    child["payload"].update(
        {
            "from_state": "HEALTHY",
            "to_state": "DEGRADED",
            "reason_code": "PROBE_FAILED",
            "state_version": 2,
        }
    )
    child["aggregate_version"] = 2
    child["occurred_at"] = "2026-08-11T01:00:01Z"
    child["received_at"] = child["occurred_at"]
    child["payload"]["changed_at"] = child["occurred_at"]
    child["idempotency_key"] = "system.component_health_changed.v1:OMS:2"
    child["correlation_id"] = parent["correlation_id"]
    child["causation_id"] = parent["message_id"]
    _validate_event_semantics(child, parent_ref=parent)

    with pytest.raises(ValueError, match="parent"):
        _validate_event_semantics(child)
    wrong_identity = deepcopy(child)
    wrong_identity["causation_id"] = "different-parent-message"
    with pytest.raises(ValueError, match="identity"):
        _validate_event_semantics(wrong_identity, parent_ref=parent)
    wrong_correlation = deepcopy(child)
    wrong_correlation["correlation_id"] = "different-correlation-id"
    with pytest.raises(ValueError, match="correlation"):
        _validate_event_semantics(wrong_correlation, parent_ref=parent)
    later_parent = deepcopy(parent)
    later_parent["occurred_at"] = "2026-08-11T01:00:02Z"
    with pytest.raises(ValueError, match="later"):
        _validate_event_semantics(child, parent_ref=later_parent)


def test_persisted_record_wrong_identity_and_stored_corruption_fail_closed() -> None:
    command = _command()
    kwargs = {
        "current_state": _current_state(command),
        "authorization": _authorization(),
        "lease": _lease(),
    }
    wrong_identity = _persisted_command(command)
    wrong_identity["query_identity"]["idempotency_key"] = "different-idempotency"
    with pytest.raises(ValueError, match="query identity"):
        validate_kill_command(command, prior_fact=wrong_identity, **kwargs)
    tampered = _persisted_command(command)
    tampered["command"]["reason"] = "tampered persisted command"
    with pytest.raises(ValueError, match="fingerprint"):
        validate_kill_command(command, prior_fact=tampered, **kwargs)
    result = _result(command)
    wrong_result_identity = _persisted_result(result)
    wrong_result_identity["query_identity"]["scope_type"] = "ACCOUNT"
    wrong_result_identity["query_identity"]["scope_id"] = "acct-1"
    with pytest.raises(ValueError, match="query identity"):
        validate_kill_result(
            result,
            persisted_command_fact=_persisted_command(command),
            prior_result_fact=wrong_result_identity,
            current_state=_current_state(command),
            expected_ack_ids={"ack-1"},
        )


def test_round8_health_generation_does_not_replace_transition_order() -> None:
    first = _event_payload("system.component_health_changed.v1")
    second = deepcopy(first)
    second.update(
        {
            "from_state": "HEALTHY",
            "to_state": "DEGRADED",
            "reason_code": "PROBE_FAILED",
            "state_version": 2,
        }
    )
    assert first["generation"] == second["generation"]
    assert second["state_version"] == first["state_version"] + 1
    assert _message("system.component_health_changed.v1", second)["aggregate_version"] == 2


def test_calibration_removes_self_authenticating_operation_fact_schemas() -> None:
    schema = _load_json(CONTRACTS / CONTROL_SCHEMA)
    assert schema["oneOf"] == [
        {"$ref": f"#/$defs/{name}"}
        for name in (
            "observabilityContext",
            "alertDefinition",
            "configCandidate",
            "configActivationResult",
            "killSwitchCommand",
            "killSwitchResult",
            "leaderLease",
            "recoveryBarrier",
        )
    ]


def test_calibration_parent_lineage_uses_minimal_accepted_message_reference() -> None:
    semantic = _semantic()["public_events"]["common"]["non_root_event"]
    assert semantic["authority"] == "trusted_Inbox_or_control_journal_AcceptedMessageRef"
    assert semantic["reference_fields"] == [
        "message_id",
        "correlation_id",
        "occurred_at",
        "accepted_at",
        "aggregate_id",
        "aggregate_version",
    ]
    assert "parent_fingerprint" not in semantic


def test_calibration_config_result_requires_explicit_phase_effect_evidence() -> None:
    result = _candidate_result(outcome="APPLIED")
    result.update({"safe_scope_required": False, "safe_scope_action": "NONE"})
    for ack in result["component_acks"].values():
        ack["prepare_result"] = "PREPARED"
        ack["candidate_effect"] = {
            "status": "APPLIED",
            "target_version": result["candidate_version"],
            "target_checksum": result["candidate_checksum"],
        }
        ack["rollback_effect"] = {
            "status": "NOT_REQUIRED",
            "target_version": None,
            "target_checksum": None,
        }
    _validator(CONTROL_SCHEMA).validate(result)


def test_calibration_health_wire_version_is_range_checked_not_prior_state_checked() -> None:
    payload = _event_payload("system.component_health_changed.v1")
    payload["state_version"] = 999
    _validator(EVENT_SCHEMAS["system.component_health_changed.v1"]).validate(payload)
    health = _semantic()["public_events"]["bindings"]["system.component_health_changed.v1"]
    assert health["producer_version"] == "persistence_CAS_allocates_previous_plus_one"
    assert health["consumer_version"] == "duplicate_stale_gap_policy_with_fail_visible_gap"
