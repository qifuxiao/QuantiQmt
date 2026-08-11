from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, RefResolver, ValidationError
from test_market_data_contracts import _jcs as _market_jcs

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "spec" / "contracts"
FIXTURES = Path(__file__).with_name("fixtures")
EVENT_SCHEMAS = {
    "system.mode_changed.v1": "events/system.mode_changed.v1.schema.json",
    "system.component_health_changed.v1": "events/system.component_health_changed.v1.schema.json",
    "system.kill_switch_changed.v1": "events/system.kill_switch_changed.v1.schema.json",
    "config.version_activated.v1": "events/config.version_activated.v1.schema.json",
}
EVENT_IDS = {
    "system.mode_changed.v1": "urn:quantiqmt:event:system.mode_changed:v1",
    "system.component_health_changed.v1": "urn:quantiqmt:event:system.component_health_changed:v1",
    "system.kill_switch_changed.v1": "urn:quantiqmt:event:system.kill_switch_changed:v1",
    "config.version_activated.v1": "urn:quantiqmt:event:config.version_activated:v1",
}
EVENT_BINDINGS = {
    "system.mode_changed.v1": ("TradingCore", "SYSTEM_MODE", "system", "core"),
    "system.component_health_changed.v1": ("HealthService", "SYSTEM_COMPONENT", "component", "OMS"),
    "system.kill_switch_changed.v1": ("ControlPlane", "KILL_SWITCH", "kill_switch", "GLOBAL"),
    "config.version_activated.v1": ("ConfigService", "CONFIG_VERSION", "config", "risk.rules"),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_store() -> dict[str, Any]:
    store = {
        "urn:quantiqmt:contract:message-envelope:v1": _load(
            SCHEMAS / "common/message-envelope.v1.schema.json"
        )
    }
    for relative, urn in EVENT_IDS.items():
        store[urn] = _load(SCHEMAS / EVENT_SCHEMAS[relative])
    return store


def _validator(relative: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative)
    if relative == "control/combined-control-message.v1.schema.json":
        store = _schema_store()
        envelope = deepcopy(store["urn:quantiqmt:contract:message-envelope:v1"])
        envelope.pop("$id", None)
        schema["$defs"]["common"]["allOf"][0] = envelope
        for name, message_type in (
            ("mode", "system.mode_changed.v1"),
            ("component", "system.component_health_changed.v1"),
            ("kill", "system.kill_switch_changed.v1"),
            ("config", "config.version_activated.v1"),
        ):
            schema["$defs"][name]["allOf"][1]["properties"]["payload"] = deepcopy(
                store[EVENT_IDS[message_type]]
            )
    Draft202012Validator.check_schema(schema)
    store = _schema_store()
    store[""] = schema
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        resolver=RefResolver.from_schema(schema, store=store),
    )


SAFE_INTEGER_MAX = 9_007_199_254_740_991


def _jcs(value: Any) -> str:
    """Small RFC 8785-compatible reference for the contract test vectors."""
    _validate_safe_integers(value)
    if not _contains_float(value):
        return _market_jcs(value)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError("I-JSON safe integer required")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        if value == 0:
            return "0"
        text = repr(value).lower()
        if "e" not in text:
            return text
        mantissa, exponent = text.split("e")
        exponent_value = int(exponent)
        absolute = abs(value)
        if 1e-6 <= absolute < 1e21:
            fixed = format(value, ".15f").rstrip("0").rstrip(".")
            return fixed
        sign = "+" if exponent_value >= 0 else "-"
        return f"{mantissa}e{sign}{abs(exponent_value)}"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_jcs(key)}:{_jcs(value[key])}" for key in keys) + "}"
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    return False


def _validate_safe_integers(value: Any) -> None:
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > SAFE_INTEGER_MAX:
        raise ValueError("I-JSON safe integer required")
    if isinstance(value, list):
        for item in value:
            _validate_safe_integers(item)
    if isinstance(value, dict):
        for item in value.values():
            _validate_safe_integers(item)


def _canonical(value: Any) -> bytes:
    return _jcs(value).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class ControlSemanticValidator:
    """Normative reference order: envelope, payload, binding, cross-object rules."""

    LABEL_ALLOWLIST: ClassVar[set[str]] = {
        "severity",
        "component",
        "alert_code",
        "environment",
        "policy_version",
    }
    FORBIDDEN_KEYS: ClassVar[set[str]] = {
        "password",
        "secret",
        "credential",
        "token",
        "access_token",
        "private_key",
        "raw_account_id",
        "raw_account_identifier",
    }

    def validate_dto(self, dto: dict[str, Any]) -> None:
        _validator("control/control-plane.v1.schema.json").validate(dto)
        self._semantic_dto(dto)

    def validate_message(
        self,
        message: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        required_context = {
            "evaluation_at",
            "accepted_policy",
            "known_messages",
            "identity_history",
            "accepted_state",
        }
        if not required_context <= set(context) or not context["known_messages"]:
            raise ValueError("validation context is required")
        _validator("control/validation-context.v1.schema.json").validate(context)
        _validator("control/combined-control-message.v1.schema.json").validate(message)
        message_type = message["message_type"]
        payload = message["payload"]
        source, aggregate_type, partition, _aggregate = EVENT_BINDINGS[message_type]
        if (
            message["source"],
            message["publisher"],
            message["aggregate_type"],
            message["partition_key"],
        ) != (
            source,
            source,
            aggregate_type,
            partition,
        ):
            raise ValueError("combined envelope binding mismatch")
        expected_aggregate = payload.get(
            "system_id",
            payload.get("component", payload.get("scope", payload.get("config_domain"))),
        )
        expected_version = payload.get("aggregate_version", payload.get("generation", 1))
        if (
            message["aggregate_id"] != expected_aggregate
            or message["aggregate_version"] != expected_version
            or message["idempotency_key"] != payload["event_id"]
        ):
            raise ValueError("combined identity binding mismatch")
        if message["correlation_id"] != payload["correlation_id"]:
            raise ValueError("correlation mismatch")
        if message["payload_fingerprint"] != _sha(payload):
            raise ValueError("payload fingerprint mismatch")
        self._scan_forbidden_keys(message)
        parent = message["causation_id"]
        if parent == message["message_id"]:
            raise ValueError("self causation")
        parent_message = context["known_messages"].get(parent)
        if parent_message is None:
            raise ValueError("unknown causation parent")
        if parent_message["correlation_id"] != message["correlation_id"]:
            raise ValueError("cross-correlation causation")
        if int(parent_message["sequence"]) >= int(message["aggregate_version"]):
            raise ValueError("future causation parent")
        if parent_message["occurred_at"] > message["occurred_at"]:
            raise ValueError("causation time regression")
        identity = context["identity_history"].get(message["message_id"]) or context[
            "identity_history"
        ].get(message["idempotency_key"])
        if identity is not None and identity["fingerprint"] != message["payload_fingerprint"]:
            raise ValueError("identity fingerprint conflict")

    def validate_config_activation(self, candidate: dict[str, Any], result: dict[str, Any]) -> None:
        projection = {key: candidate[key] for key in candidate if key != "candidate_checksum"}
        if candidate["candidate_checksum"] != _sha(projection):
            raise ValueError("candidate checksum mismatch")
        if set(result["component_acks"]) != set(candidate["required_components"]):
            raise ValueError("component acknowledgement set mismatch")
        for component, ack in result["component_acks"].items():
            if (
                not isinstance(ack, dict)
                or ack.get("candidate_version") != candidate["candidate_version"]
                or ack.get("candidate_checksum") != candidate["candidate_checksum"]
                or ack.get("component_id") != component
                or not ack.get("generation")
                or not ack.get("capability_version")
                or ack.get("prepare_result") not in {"PREPARED", "APPLIED"}
            ):
                raise ValueError("component acknowledgement binding mismatch")
        if result["outcome"] == "APPLIED" and any(
            ack["prepare_result"] != "APPLIED" for ack in result["component_acks"].values()
        ):
            raise ValueError("partial silent activation")

    def validate_kill_switch(
        self, command: dict[str, Any], result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        self.validate_dto(command)
        self.validate_dto(result)
        authority = context["accepted_state"]["kill_switch"]
        lease = context["accepted_state"]["lease"]
        evaluation_at = context["evaluation_at"]
        if command["expected_version"] != authority["current_version"]:
            raise ValueError("stale expected version")
        if (
            command["leader_lease_id"] != lease["lease_id"]
            or command["fencing_token"] != lease["fencing_token"]
        ):
            raise ValueError("stale fencing")
        if lease["expires_at"] <= evaluation_at or command["deadline_at"] <= evaluation_at:
            raise ValueError("expired lease or deadline")
        auth = command["authorization_evidence"]
        if auth["revoked"] or auth["valid_until"] <= evaluation_at:
            raise ValueError("authorization expired or revoked")
        if (
            result["command_id"] != command["command_id"]
            or result["command_fingerprint"] != command["command_fingerprint"]
        ):
            raise ValueError("kill switch identity mismatch")
        if result["outcome"] == "APPLIED":
            if (
                result["previous_version"] != command["expected_version"]
                or result["current_version"] != result["previous_version"] + 1
            ):
                raise ValueError("kill switch version jump")
            if result["reconciliation_required"] or result["effective_state"] == "UNKNOWN":
                raise ValueError("applied kill switch cannot be unknown")
        elif result["outcome"] == "UNKNOWN":
            if not result["reconciliation_required"]:
                raise ValueError("unknown outcome requires reconciliation")
        if command["desired_state"] == "OFF" and (
            command["recovery_evidence_reference"] is None or result["restores_normal"]
        ):
            raise ValueError("disable requires recovery evidence and cannot restore NORMAL")

    def validate_kill_switch_result(self, command: dict[str, Any], result: dict[str, Any]) -> None:
        if (
            result["outcome"] == "APPLIED"
            and result["current_version"] != command["expected_version"] + 1
        ):
            raise ValueError("kill switch version jump")
        if result["current_version"] < command["expected_version"]:
            raise ValueError("stale expected version")
        if command["desired_state"] == "OFF" and result.get("restores_normal", False):
            raise ValueError("disable cannot restore NORMAL")

    def validate_recovery_barrier(self, barrier: dict[str, Any], context: dict[str, Any]) -> None:
        self.validate_dto(barrier)
        authority = context["accepted_state"]
        if barrier["state"] == "INVALIDATED":
            if not barrier["invalidation_reason"]:
                raise ValueError("invalidated barrier requires reason")
            return
        if barrier["state"] != "OPEN":
            return
        required = {
            "CONFIG_VERIFIED",
            "MARKET_FRESH",
            "AUDIT_AVAILABLE",
            "RECONCILIATION_COMPLETE",
            "LEASE_FENCED",
            "OUTBOX_HEALTHY",
        }
        if set(barrier["required_evidence"]) != required:
            raise ValueError("recovery barrier evidence incomplete")
        evidence = barrier["evidence"]
        if (
            evidence["config_version"] != authority["config"]["version"]
            or evidence["config_checksum"] != authority["config"]["checksum"]
        ):
            raise ValueError("barrier config evidence mismatch")
        if (
            evidence["market_watermark"] != authority["market"]["watermark"]
            or authority["market"]["quality"] != "NORMAL"
            or authority["market"]["unresolved_gap_count"] != 0
        ):
            raise ValueError("barrier market evidence mismatch")
        if (
            evidence["audit_watermark"] != authority["audit"]["outbox_position"]
            or not authority["audit"]["healthy"]
            or authority["audit"]["lag"] > authority["critical_lag"]["threshold"]
            or authority["critical_lag"]["current"] >= authority["critical_lag"]["threshold"]
        ):
            raise ValueError("barrier audit evidence mismatch")
        if (
            evidence["reconciliation_case_count"]
            != authority["reconciliation"]["open_blocking_case_count"]
            or evidence["reconciliation_case_count"] != 0
        ):
            raise ValueError("barrier reconciliation evidence mismatch")
        for component, version in evidence["component_versions"].items():
            accepted = authority["components"].get(component)
            if (
                accepted is None
                or accepted["version"] != version
                or accepted["checksum"] != evidence["component_checksums"].get(component)
                or accepted["health"] != "HEALTHY"
            ):
                raise ValueError("barrier component evidence mismatch")
        if authority["lease"]["expires_at"] <= context["evaluation_at"]:
            raise ValueError("barrier lease expired")

    def _scan_forbidden_keys(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in self.FORBIDDEN_KEYS:
                    raise ValueError("sensitive field")
                self._scan_forbidden_keys(child)
        elif isinstance(value, list):
            for child in value:
                self._scan_forbidden_keys(child)

    def _semantic_dto(self, dto: dict[str, Any]) -> None:
        dto_type = dto["dto_type"]
        self._scan_forbidden_keys(dto)
        if dto_type == "OBSERVABILITY_CONTEXT":
            if dto["redaction_policy"] != "NO_SECRETS_OR_CREDENTIALS":
                raise ValueError("redaction policy is not fail-closed")
        elif dto_type == "ALERT_DEFINITION":
            labels = set(dto.get("label_keys", []))
            if not labels <= self.LABEL_ALLOWLIST:
                raise ValueError("forbidden metric label")
            if any(
                field in {"order_id", "trade_id", "instrument_id", "account_id", "strategy_id"}
                for field in dto["evidence_fields"]
            ):
                raise ValueError("high-cardinality alert evidence")
        elif dto_type == "CONFIG_CANDIDATE":
            if any(not ref.startswith("secret://") for ref in dto["secret_references"]):
                raise ValueError("plaintext secret reference")
            if (
                dto["activation_mode"] == "RESTART_REQUIRED"
                and dto["safe_boundary"] != "RESTART_ONLY"
            ):
                raise ValueError("restart-required config has unsafe boundary")
        elif dto_type == "CONFIG_ACTIVATION_RESULT":
            acks = dto["component_acks"]
            if not dto.get("required_components") or set(dto["required_components"]) != set(acks):
                raise ValueError("component acknowledgement set mismatch")
            ack_results = set()
            for component, ack in acks.items():
                if not isinstance(ack, dict) or ack.get("component_id") != component:
                    raise ValueError("component acknowledgement identity mismatch")
                if (
                    ack.get("candidate_version") != dto["candidate_version"]
                    or ack.get("candidate_checksum") != dto["candidate_checksum"]
                ):
                    raise ValueError("component acknowledgement candidate mismatch")
                if (
                    not ack.get("generation")
                    or not ack.get("capability_version")
                    or not ack.get("observed_at")
                    or not ack.get("ack_sequence")
                ):
                    raise ValueError("component acknowledgement evidence missing")
                ack_results.add(ack["prepare_result"])
            if dto["outcome"] == "APPLIED" and (
                ack_results != {"APPLIED"}
                or dto["active_version"] is None
                or dto["rollback_version"] is not None
            ):
                raise ValueError("partial config activation")
            if (
                dto["outcome"] in {"PARTIAL", "UNKNOWN", "ROLLED_BACK"}
                and dto["rollback_version"] is None
            ):
                raise ValueError("ambiguous config activation requires rollback")
        elif dto_type == "KILL_SWITCH_COMMAND":
            if (
                not dto["authorization_evidence"]["approver_ids"]
                or min(dto["reserved_capacity"].values()) < 1
            ):
                raise ValueError("kill switch authorization missing")
        elif dto_type == "KILL_SWITCH_RESULT":
            if dto["outcome"] == "APPLIED" and dto["effective_state"] == "UNKNOWN":
                raise ValueError("applied kill switch cannot be unknown")
            if dto["outcome"] == "APPLIED" and dto["current_version"] < 1:
                raise ValueError("invalid applied version")
        elif dto_type == "LEADER_LEASE":
            if dto["status"] == "ACTIVE" and dto["expires_at"] <= dto["issued_at"]:
                raise ValueError("active lease is expired")
            if dto["renew_deadline_at"] >= dto["expires_at"]:
                raise ValueError("renew deadline must precede expiry")
        elif dto_type == "RECOVERY_BARRIER":
            required = {
                "CONFIG_VERIFIED",
                "MARKET_FRESH",
                "AUDIT_AVAILABLE",
                "RECONCILIATION_COMPLETE",
                "LEASE_FENCED",
                "OUTBOX_HEALTHY",
            }
            if dto["state"] == "OPEN" and set(dto["required_evidence"]) != required:
                raise ValueError("recovery barrier evidence incomplete")
            if dto["state"] == "CLOSED" and dto["opened_at"] is not None:
                raise ValueError("closed barrier cannot have opened_at")
            if dto["state"] == "INVALIDATED" and not dto["invalidation_reason"]:
                raise ValueError("invalidated barrier requires reason")


def _combined_fixture(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    source, aggregate_type, partition, aggregate = EVENT_BINDINGS[message_type]
    message_id = f"message-{message_type.split('.')[1]}-0001"
    message = {
        "message_id": message_id,
        "message_type": message_type,
        "schema_version": 1,
        "occurred_at": payload.get("occurred_at", payload.get("observed_at")),
        "received_at": "2026-08-11T01:00:01Z",
        "correlation_id": payload["correlation_id"],
        "causation_id": "parent-message-0001",
        "source": source,
        "publisher": source,
        "partition_key": partition,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate,
        "aggregate_version": payload.get("aggregate_version", payload.get("generation", 1)),
        "idempotency_key": payload["event_id"],
        "payload_fingerprint": _sha(payload),
        "payload": payload,
    }
    if message_type == "system.component_health_changed.v1":
        message["aggregate_id"] = payload["component"]
    return message


def _validation_context(
    correlation_id: str,
    *,
    parent: str = "parent-message-0001",
    parent_time: str = "2026-08-11T00:59:59Z",
) -> dict[str, Any]:
    return {
        "evaluation_at": "2026-08-11T01:00:01Z",
        "accepted_policy": {"version": "policy-v1", "checksum": "a" * 64},
        "known_messages": {
            parent: {
                "message_id": parent,
                "fingerprint": "b" * 64,
                "sequence": 0,
                "occurred_at": parent_time,
                "correlation_id": correlation_id,
            }
        },
        "identity_history": {},
        "accepted_state": {
            "config": {"version": "v2", "checksum": "a" * 64},
            "market": {
                "calendar_version": "cal-v1",
                "policy_version": "policy-v1",
                "tzdb_version": "2026c",
                "watermark": 1,
                "unresolved_gap_count": 0,
                "quality": "NORMAL",
            },
            "audit": {"outbox_position": 1, "inbox_position": 1, "lag": 0, "healthy": True},
            "lease": {
                "lease_id": "lease-1",
                "epoch": 1,
                "fencing_token": "fence-token-000001",
                "expires_at": "2026-08-11T02:00:00Z",
            },
            "components": {
                "OMS": {"generation": 1, "version": "v1", "checksum": "b" * 64, "health": "HEALTHY"}
            },
            "reconciliation": {
                "version": "recon-v1",
                "checksum": "c" * 64,
                "open_blocking_case_count": 0,
            },
            "critical_lag": {
                "policy_version": "lag-v1",
                "threshold": 10,
                "window_seconds": 60,
                "current": 0,
                "recovery_window_seconds": 60,
            },
            "kill_switch": {"current_version": 2, "effective_state": "OFF"},
        },
    }


def test_control_dtos_are_schema_and_semantic_valid() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    checker = ControlSemanticValidator()
    for dto in document["dtos"]:
        checker.validate_dto(dto)


@pytest.mark.parametrize(
    "case", _load(FIXTURES / "control-plane.v1/invalid.json")["cases"], ids=lambda c: c["name"]
)
def test_control_semantic_invalid_matrix_is_fail_closed(case: dict[str, Any]) -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    dto = deepcopy(next(item for item in document["dtos"] if item["dto_type"] == case["dto_type"]))
    dto[case["field"]] = case["value"]
    with pytest.raises((ValueError, Exception)):
        ControlSemanticValidator().validate_dto(dto)


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_control_public_events_have_registered_schema_and_valid_fixture(message_type: str) -> None:
    payload = _load(FIXTURES / "control-events.json")[message_type]
    _validator(EVENT_SCHEMAS[message_type]).validate(payload)
    assert payload["source"] in {"TradingCore", "HealthService", "ControlPlane", "ConfigService"}


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_combined_control_message_validator_binds_all_four_events(message_type: str) -> None:
    payload = _load(FIXTURES / "control-events.json")[message_type]
    message = _combined_fixture(message_type, payload)
    checker = ControlSemanticValidator()
    checker.validate_message(message, _validation_context(payload["correlation_id"]))
    for field, value in (
        ("source", "WrongSource"),
        ("partition_key", "wrong"),
        ("aggregate_version", 2),
        ("idempotency_key", "other-idempotency"),
        ("payload_fingerprint", "0" * 64),
        ("correlation_id", "other-correlation-0001"),
        ("causation_id", "unknown-parent-0001"),
    ):
        invalid = deepcopy(message)
        invalid[field] = value
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_message(invalid, _validation_context(payload["correlation_id"]))


def test_combined_message_rejects_sensitive_fields_and_lineage_errors() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    for _bad in ("message_id", "causation_id"):
        invalid = deepcopy(message)
        invalid["payload"]["secret"] = "do-not-log"
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_message(invalid, _validation_context(payload["correlation_id"]))
    invalid = deepcopy(message)
    invalid["causation_id"] = invalid["message_id"]
    with pytest.raises(ValueError, match="self"):
        checker.validate_message(invalid, _validation_context(payload["correlation_id"]))


def test_control_lineage_context_is_mandatory_and_collision_safe() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    with pytest.raises(ValueError, match="context"):
        checker.validate_message(message, {})
    empty = _validation_context(payload["correlation_id"])
    empty["known_messages"] = {}
    with pytest.raises(ValueError, match="context"):
        checker.validate_message(message, empty)
    unknown = _validation_context(payload["correlation_id"], parent="another-parent-0001")
    with pytest.raises(ValueError, match="unknown"):
        checker.validate_message(message, unknown)
    future = _validation_context(payload["correlation_id"])
    future["known_messages"]["parent-message-0001"]["sequence"] = message["aggregate_version"]
    with pytest.raises(ValueError, match="future"):
        checker.validate_message(message, future)
    time_regression = _validation_context(
        payload["correlation_id"], parent_time="2026-08-11T01:00:02Z"
    )
    with pytest.raises(ValueError, match="time"):
        checker.validate_message(message, time_regression)
    duplicate = _validation_context(payload["correlation_id"])
    duplicate["identity_history"][message["message_id"]] = {
        "fingerprint": message["payload_fingerprint"],
        "decision": "DUPLICATE",
    }
    checker.validate_message(message, duplicate)
    conflict = _validation_context(payload["correlation_id"])
    conflict["identity_history"][message["message_id"]] = {
        "fingerprint": "0" * 64,
        "decision": "CONFLICT",
    }
    with pytest.raises(ValueError, match="conflict"):
        checker.validate_message(message, conflict)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1e-7, "1e-7"),
        (1e-6, "0.000001"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (-0.0, "0"),
    ],
)
def test_control_rfc8785_reference_number_vectors(value: float, expected: str) -> None:
    assert _jcs(value) == expected


def test_control_rfc8785_rejects_non_finite_and_unsafe_numbers() -> None:
    for value in (float("nan"), float("inf"), -float("inf"), SAFE_INTEGER_MAX + 1):
        with pytest.raises(ValueError):
            _canonical(value)
    assert _canonical({"𐀀": 1, "\ue000": 2}).decode("utf-8").startswith('{"𐀀":1')


def test_control_dtos_reject_arbitrary_and_high_cardinality_fields() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    validator = _validator("control/control-plane.v1.schema.json")
    for dto in document["dtos"]:
        invalid = deepcopy(dto)
        invalid["BOGUS"] = True
        assert not validator.is_valid(invalid)


def test_config_checksum_and_component_ack_binding_are_fail_closed() -> None:
    candidate = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_CANDIDATE"
        )
    )
    candidate["candidate_checksum"] = _sha(
        {key: candidate[key] for key in candidate if key != "candidate_checksum"}
    )
    result = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_ACTIVATION_RESULT"
        )
    )
    result["component_acks"] = {
        component: {
            "component_id": component,
            "candidate_version": candidate["candidate_version"],
            "candidate_checksum": candidate["candidate_checksum"],
            "generation": 1,
            "capability_version": "cap-v1",
            "prepare_result": "APPLIED",
        }
        for component in candidate["required_components"]
    }
    ControlSemanticValidator().validate_config_activation(candidate, result)
    bad = deepcopy(result)
    bad["component_acks"].pop("OMS")
    with pytest.raises(ValueError, match="set"):
        ControlSemanticValidator().validate_config_activation(candidate, bad)
    bad_candidate = deepcopy(candidate)
    bad_candidate["payload"] = {"rules": "changed"}
    with pytest.raises(ValueError, match="checksum"):
        ControlSemanticValidator().validate_config_activation(bad_candidate, result)


def test_kill_switch_version_and_recovery_barrier_matrices_are_fail_closed() -> None:
    checker = ControlSemanticValidator()
    command = {"expected_version": 3, "desired_state": "ON"}
    checker.validate_kill_switch_result(command, {"outcome": "APPLIED", "current_version": 4})
    for result in (
        {"outcome": "APPLIED", "current_version": 3},
        {"outcome": "APPLIED", "current_version": 5},
    ):
        with pytest.raises(ValueError):
            checker.validate_kill_switch_result(command, result)
    with pytest.raises(ValueError, match="NORMAL"):
        checker.validate_kill_switch_result(
            {"expected_version": 1, "desired_state": "OFF"},
            {"outcome": "APPLIED", "current_version": 2, "restores_normal": True},
        )
    barrier = {
        "dto_type": "RECOVERY_BARRIER",
        "schema_version": 1,
        "correlation_id": "corr-000000000099",
        "created_at": "2026-08-11T01:00:00Z",
        "barrier_id": "barrier-2",
        "state": "INVALIDATED",
        "generation": 1,
        "opened_at": None,
        "evidence": {
            "config_version": "v1",
            "config_checksum": "a" * 64,
            "market_watermark": 1,
            "audit_watermark": 1,
            "reconciliation_case_count": 0,
            "component_versions": {"OMS": "v1"},
            "component_checksums": {"OMS": "b" * 64},
        },
        "required_evidence": [],
        "invalidation_reason": None,
    }
    with pytest.raises((ValueError, ValidationError)):
        checker.validate_dto(barrier)


def test_kill_switch_command_result_requires_authority_and_reconciliation_context() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    command = next(item for item in document["dtos"] if item["dto_type"] == "KILL_SWITCH_COMMAND")
    result = next(item for item in document["dtos"] if item["dto_type"] == "KILL_SWITCH_RESULT")
    context = _validation_context(command["correlation_id"])
    checker = ControlSemanticValidator()
    checker.validate_kill_switch(command, result, context)
    stale = deepcopy(command)
    stale["expected_version"] = 1
    with pytest.raises(ValueError, match="stale"):
        checker.validate_kill_switch(stale, result, context)
    unknown = deepcopy(result)
    unknown["outcome"] = "UNKNOWN"
    unknown["reconciliation_required"] = False
    with pytest.raises(ValueError, match="reconciliation"):
        checker.validate_kill_switch(command, unknown, context)
    expired = deepcopy(command)
    expired["authorization_evidence"]["valid_until"] = "2026-08-11T00:00:00Z"
    with pytest.raises(ValueError, match="expired"):
        checker.validate_kill_switch(expired, result, context)


def test_recovery_barrier_open_requires_authority_bound_evidence() -> None:
    context = _validation_context("corr-000000000099")
    barrier = {
        "dto_type": "RECOVERY_BARRIER",
        "schema_version": 1,
        "correlation_id": "corr-000000000099",
        "created_at": "2026-08-11T01:00:00Z",
        "barrier_id": "barrier-open-1",
        "state": "OPEN",
        "generation": 1,
        "opened_at": "2026-08-11T01:00:00Z",
        "required_evidence": [
            "CONFIG_VERIFIED",
            "MARKET_FRESH",
            "AUDIT_AVAILABLE",
            "RECONCILIATION_COMPLETE",
            "LEASE_FENCED",
            "OUTBOX_HEALTHY",
        ],
        "invalidation_reason": None,
        "evidence": {
            "config_version": "v2",
            "config_checksum": "a" * 64,
            "market_watermark": 1,
            "audit_watermark": 1,
            "reconciliation_case_count": 0,
            "component_versions": {"OMS": "v1"},
            "component_checksums": {"OMS": "b" * 64},
        },
    }
    checker = ControlSemanticValidator()
    checker.validate_recovery_barrier(barrier, context)
    tampered = deepcopy(barrier)
    tampered["evidence"]["config_checksum"] = "0" * 64
    with pytest.raises(ValueError, match="config"):
        checker.validate_recovery_barrier(tampered, context)
    lagged = deepcopy(barrier)
    lagged_context = deepcopy(context)
    lagged_context["accepted_state"]["critical_lag"]["current"] = 11
    with pytest.raises(ValueError, match="audit"):
        checker.validate_recovery_barrier(lagged, lagged_context)


def test_control_events_reject_additional_properties_and_invalid_transitions() -> None:
    fixtures = _load(FIXTURES / "control-events.json")
    mode = deepcopy(fixtures["system.mode_changed.v1"])
    mode["unexpected"] = True
    assert not _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(mode)
    mode = deepcopy(fixtures["system.mode_changed.v1"])
    mode.update(from_mode="NORMAL", to_mode="HALTED", reason_code="SAFETY_UNCERTAIN")
    assert not _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(mode)


def test_manifest_nfr_and_workflow_register_control_contracts() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["specification"]["version"] == "0.11.0"
    assert manifest["change"]["previous_version"] == "0.10.0"
    catalog_text = (ROOT / "spec/contracts/catalog.yaml").read_text(encoding="utf-8")
    for message_type in EVENT_SCHEMAS:
        assert f"name: {message_type}" in catalog_text
    assert "CONTRACT-CONTROL-COMBINED-MESSAGE-V1" in catalog_text
    nfr = yaml.safe_load((ROOT / "spec/nfr/observability.yaml").read_text(encoding="utf-8"))["nfr"][
        "control_plane"
    ]
    assert "order_id" in nfr["metric_label_forbidden"]
    assert nfr["critical_lag_policy"]["threshold_version_required"] is True


def test_control_workflow_and_state_machine_freeze_fail_closed_guards() -> None:
    workflow = yaml.safe_load(
        (ROOT / "spec/workflows/control-plane.yaml").read_text(encoding="utf-8")
    )["workflow"]
    assert workflow["config_activation"]["forbidden"] == [
        "partial_silent_activation",
        "plaintext_secret_persistence",
        "active_version_side_channel",
    ]
    assert "consumer_apply" in workflow["boundaries"]
    assert workflow["recovery_barrier"]["initial"] == "CLOSED"
    machine = yaml.safe_load(
        (ROOT / "spec/state-machines/system-mode.yaml").read_text(encoding="utf-8")
    )["machine"]
    assert machine["control_guards"]["stale_lease_or_fencing_token"] == "reject_without_side_effect"
    assert "dependency reconnect alone never restores NORMAL" in machine["invariants"]
