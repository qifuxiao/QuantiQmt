from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource
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


def _parse_json_exact(text: str) -> Any:
    def reject_non_finite(token: str) -> Any:
        raise ValueError(f"non-finite JSON number is forbidden: {token}")

    return json.loads(
        text,
        parse_float=Decimal,
        parse_constant=reject_non_finite,
    )


def _load(path: Path) -> Any:
    return _parse_json_exact(path.read_text(encoding="utf-8"))


def _schema_store() -> dict[str, Any]:
    store = {
        "urn:quantiqmt:contract:message-envelope:v1": _load(
            SCHEMAS / "common/message-envelope.v1.schema.json"
        ),
        "urn:quantiqmt:contract:control-plane:v1": _load(
            SCHEMAS / "control/control-plane.v1.schema.json"
        ),
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
    registry = Registry().with_resources(
        (uri, Resource.from_contents(document)) for uri, document in _schema_store().items()
    )
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )


SAFE_INTEGER_MAX = 9_007_199_254_740_991
CONFIG_AUTHORITY_CHECKSUM = "a3022467272c3fda695728c1dd75e408258ff871dcedfbdc60d3c8f9f5dff03b"

MODE_TRANSITIONS = {
    ("STARTING", "NORMAL", "RECOVERY_PASSED"),
    ("STARTING", "SAFE", "PARTIAL_AVAILABILITY"),
    ("NORMAL", "DEGRADED", "NON_CRITICAL_DEGRADATION"),
    ("NORMAL", "SAFE", "SAFETY_UNCERTAIN"),
    ("DEGRADED", "SAFE", "SAFETY_UNCERTAIN"),
    ("SAFE", "HALTED", "SEVERE_INCONSISTENCY"),
    ("DEGRADED", "NORMAL", "HEALTHY_WINDOW_PASSED"),
    ("SAFE", "DEGRADED", "REPAIR_APPROVED"),
    ("HALTED", "SAFE", "DUAL_APPROVED_RECOVERY"),
}
HEALTH_TRANSITIONS = {
    ("HEALTHY", "DEGRADED"): {
        "DEPENDENCY_STALE",
        "PROBE_FAILED",
        "CAPACITY_EXHAUSTED",
        "AUDIT_UNAVAILABLE",
    },
    ("HEALTHY", "UNAVAILABLE"): {"PROBE_FAILED", "DISCONNECTED", "AUDIT_UNAVAILABLE"},
    ("DEGRADED", "HEALTHY"): {"PROBE_PASSED", "RECOVERY_VERIFIED"},
    ("DEGRADED", "UNAVAILABLE"): {
        "PROBE_FAILED",
        "DISCONNECTED",
        "CAPACITY_EXHAUSTED",
        "AUDIT_UNAVAILABLE",
    },
    ("DEGRADED", "RECOVERING"): {"RECOVERY_STARTED"},
    ("UNAVAILABLE", "RECOVERING"): {"RECOVERY_STARTED"},
    ("RECOVERING", "HEALTHY"): {"PROBE_PASSED", "RECOVERY_VERIFIED"},
    ("RECOVERING", "UNAVAILABLE"): {"PROBE_FAILED", "DISCONNECTED", "AUDIT_UNAVAILABLE"},
}


def _jcs(value: Any) -> str:
    """RFC 8785 JCS restricted to safe integers and decimal strings."""
    return _market_jcs(_normalize_checksum_number_domain(value))


def _normalize_checksum_number_domain(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("finite mathematically integral exact JSON number required")
        value = int(value)
    if isinstance(value, float):
        raise ValueError("binary float lacks exact JSON token provenance")
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > SAFE_INTEGER_MAX:
        raise ValueError("I-JSON safe integer required")
    if isinstance(value, list):
        return [_normalize_checksum_number_domain(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_checksum_number_domain(item) for key, item in value.items()}
    return value


RFC3339_INSTANT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
RFC3339_UTC_Z = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d{1,6})?Z$"
)


def _parse_rfc3339_instant(value: str) -> datetime:
    if (
        not isinstance(value, str)
        or not RFC3339_INSTANT.fullmatch(value)
        or value.endswith("-00:00")
    ):
        raise ValueError("strict RFC3339 UTC instant required")
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError("strict RFC3339 UTC instant required") from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("strict RFC3339 UTC instant required")
    return instant.astimezone(UTC)


def _canonical_utc_z(value: str) -> str:
    """Normalize an ingress RFC3339 instant before the control contract boundary."""
    instant = _parse_rfc3339_instant(value)
    base = instant.strftime("%Y-%m-%dT%H:%M:%S")
    if instant.microsecond:
        return f"{base}.{instant.microsecond:06d}".rstrip("0") + "Z"
    return f"{base}Z"


def _utc_instant(value: str) -> datetime:
    """Parse the canonical UTC-Z representation used at control boundaries."""
    if not isinstance(value, str) or not RFC3339_UTC_Z.fullmatch(value):
        raise ValueError("canonical RFC3339 UTC Z instant required")
    return _parse_rfc3339_instant(value)


def _canonical(value: Any) -> bytes:
    return _jcs(value).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _candidate_checksum_projection(
    candidate: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    def value(candidate_key: str, authority_key: str | None = None) -> Any:
        key = authority_key or candidate_key
        return candidate[candidate_key] if candidate_key in candidate else config[key]

    return {
        "config_domain": value("config_domain"),
        "candidate_version": value("candidate_version", "config_version"),
        "payload": value("payload", "candidate_payload"),
        "secret_references": sorted(value("secret_references")),
        "required_components": sorted(value("required_components")),
        "activation_mode": value("activation_mode"),
        "safe_boundary": value("safe_boundary"),
        "valuation_currency": value("valuation_currency"),
        "dynamic_limits": value("dynamic_limits"),
        "system_hard_limit_policy": {
            "version": value("system_hard_limit_policy_version"),
            "checksum": value("system_hard_limit_policy_checksum"),
            "content": value("system_hard_limit_policy"),
        },
        "component_authority": value("component_authority", "components"),
        "policy": {
            "version": value("policy_version"),
            "checksum": value("policy_checksum"),
        },
    }


def _hard_limit_policy_projection(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "valuation_currency": policy["valuation_currency"],
        "limits": policy["limits"],
    }


def _kill_command_fingerprint_projection(command: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in command.items() if key != "command_fingerprint"}


def _kill_result_fingerprint_projection(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "result_fingerprint"}


def _kill_command_identity(command: dict[str, Any]) -> str:
    return f"KILL_SWITCH_COMMAND:{command['command_id']}"


def _kill_result_identity(result: dict[str, Any]) -> str:
    return f"KILL_SWITCH_RESULT:{result['result_id']}"


def _kill_command_result_identity(result: dict[str, Any]) -> str:
    projection = {
        "command_id": result["command_id"],
        "idempotency_key": result["idempotency_key"],
        "scope": result["scope"],
    }
    return f"KILL_SWITCH_COMMAND_RESULT:{_sha(projection)}"


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

    def validate_control_message(
        self,
        message: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        required_context = {
            "evaluation_at",
            "accepted_policy",
            "known_messages",
            "identity_history",
            "accepted_state",
        }
        if not required_context <= set(context):
            raise ValueError("validation context is required")
        _validator("control/validation-context.v1.schema.json").validate(context)
        for barrier_id, barrier_authority in context.get("accepted_recovery_barriers", {}).items():
            if barrier_authority["barrier_id"] != barrier_id:
                raise ValueError("recovery barrier authority key mismatch")

        if "dto_type" in message:
            _validator("control/control-plane.v1.schema.json").validate(message)
            self._scan_forbidden_keys(message)
            dto_type = message["dto_type"]
            if dto_type == "CONFIG_CANDIDATE":
                identity_key = message["idempotency_key"]
                fingerprint = message["candidate_checksum"]
                if fingerprint != _sha(_candidate_checksum_projection(message, {})):
                    raise ValueError("config candidate checksum mismatch")
            elif dto_type == "KILL_SWITCH_COMMAND":
                identity_key = _kill_command_identity(message)
                fingerprint = message["command_fingerprint"]
                if fingerprint != _sha(_kill_command_fingerprint_projection(message)):
                    raise ValueError("kill command fingerprint mismatch")
            elif dto_type == "KILL_SWITCH_RESULT":
                fingerprint = message["result_fingerprint"]
                if fingerprint != _sha(_kill_result_fingerprint_projection(message)):
                    raise ValueError("kill result fingerprint mismatch")
                self._audit_kill_result_registry(context)
                decision = self._kill_result_identity_decision(message, context)
                if decision["status"] == "DUPLICATE":
                    self._validate_kill_result_duplicate_binding(message, context)
                    return decision
                self._validate_kill_result_binding(message, context)
                self._validate_kill_result(message, context)
                return decision
            else:
                raise ValueError("unsupported control DTO type")
            decision = self._identity_decision(identity_key, fingerprint, context)
            if decision["status"] == "DUPLICATE":
                return decision
            self._validate_control_dto(message, context)
            return decision

        _validator("control/combined-control-message.v1.schema.json").validate(message)
        payload = message["payload"]
        if message["payload_fingerprint"] != _sha(payload):
            raise ValueError("payload fingerprint mismatch")
        self._scan_forbidden_keys(message)
        self._validate_combined_immutable_binding(message)
        decision = self._identity_decision(
            message["message_id"],
            message["payload_fingerprint"],
            context,
            fallback_key=message["idempotency_key"],
        )
        if decision["status"] == "DUPLICATE":
            return decision
        recovery_authority = context["accepted_state"].get("recovery_barrier")
        if recovery_authority is not None:
            self._validate_recovery_authority_entry(
                recovery_authority["barrier_id"], recovery_authority, context
            )
        accepted_policy = context["accepted_policy"]
        policy_evidence = payload.get("evidence", payload)
        if (
            policy_evidence.get("policy_version") != accepted_policy["version"]
            or policy_evidence.get("policy_checksum") != accepted_policy["checksum"]
        ):
            raise ValueError("accepted policy binding mismatch")
        self._validate_lineage(message, context)
        self._validate_event_specific(message, context)
        return decision

    def _validate_combined_immutable_binding(self, message: dict[str, Any]) -> None:
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
        if payload["causation_id"] != message["causation_id"]:
            raise ValueError("payload causation mismatch")

    def _validate_lineage(self, message: dict[str, Any], context: dict[str, Any]) -> None:
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
        if _utc_instant(parent_message["occurred_at"]) > _utc_instant(message["occurred_at"]):
            raise ValueError("causation time regression")

    def _identity_decision(
        self,
        identity_key: str,
        fingerprint: str,
        context: dict[str, Any],
        *,
        fallback_key: str | None = None,
    ) -> dict[str, Any]:
        history = context["identity_history"]
        identity = history.get(identity_key) or (
            history.get(fallback_key) if fallback_key else None
        )
        if identity is None:
            return {"status": "ACCEPTED", "identity": identity_key}
        if identity["fingerprint"] != fingerprint:
            raise ValueError("identity fingerprint conflict")
        return {
            "status": "DUPLICATE",
            "identity": identity_key,
            "prior_decision": identity["decision"],
        }

    def _kill_result_identity_decision(
        self, result: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        history = context["identity_history"]
        result_key = _kill_result_identity(result)
        command_result_key = _kill_command_result_identity(result)
        result_record = history.get(result_key)
        command_result_record = history.get(command_result_key)
        fingerprint = result["result_fingerprint"]
        if command_result_record is not None:
            expected = {
                "command_identity": f"KILL_SWITCH_COMMAND:{result['command_id']}",
                "command_id": result["command_id"],
                "command_idempotency_key": result["idempotency_key"],
                "command_scope": result["scope"],
                "command_fingerprint": result["command_fingerprint"],
                "result_identity": result_key,
                "result_id": result["result_id"],
                "result_fingerprint": fingerprint,
                "command_result_identity": command_result_key,
            }
            if command_result_record["fingerprint"] != fingerprint:
                raise ValueError("command-result identity fingerprint conflict")
            if (
                result_record is None
                or result_record["fingerprint"] != fingerprint
                or result_record["decision"] != command_result_record["decision"]
                or any(result_record[field] != value for field, value in expected.items())
                or any(command_result_record[field] != value for field, value in expected.items())
            ):
                raise ValueError("command-result canonical result conflict")
            return {
                "status": "DUPLICATE",
                "identity": result_key,
                "command_result_identity": command_result_key,
                "prior_decision": command_result_record["decision"],
            }
        if result_record is not None:
            raise ValueError("orphan result identity without command-result authority")
        return {
            "status": "ACCEPTED",
            "identity": result_key,
            "command_result_identity": command_result_key,
        }

    def _audit_kill_result_registry(self, context: dict[str, Any]) -> None:
        history = context["identity_history"]
        result_records = {
            key: record for key, record in history.items() if key.startswith("KILL_SWITCH_RESULT:")
        }
        command_result_records = {
            key: record
            for key, record in history.items()
            if key.startswith("KILL_SWITCH_COMMAND_RESULT:")
        }
        command_to_results: dict[str, set[str]] = {}
        result_to_commands: dict[str, set[str]] = {}
        shared_fields = (
            "fingerprint",
            "decision",
            "command_identity",
            "command_id",
            "command_idempotency_key",
            "command_scope",
            "command_fingerprint",
            "result_identity",
            "result_id",
            "result_fingerprint",
            "command_result_identity",
        )
        required_record_fields = set(shared_fields) | {"record_type"}

        for key, record in (*result_records.items(), *command_result_records.items()):
            expected_type = (
                "KILL_SWITCH_RESULT"
                if key.startswith("KILL_SWITCH_RESULT:")
                else "KILL_SWITCH_COMMAND_RESULT"
            )
            if not required_record_fields <= set(record):
                raise ValueError("kill result registry record is incomplete")
            if record.get("record_type") != expected_type:
                raise ValueError("kill result registry record type mismatch")
            expected_result_identity = f"KILL_SWITCH_RESULT:{record['result_id']}"
            expected_command_identity = f"KILL_SWITCH_COMMAND:{record['command_id']}"
            expected_command_result_identity = _kill_command_result_identity(
                {
                    "command_id": record["command_id"],
                    "idempotency_key": record["command_idempotency_key"],
                    "scope": record["command_scope"],
                }
            )
            expected_key = (
                expected_result_identity
                if expected_type == "KILL_SWITCH_RESULT"
                else expected_command_result_identity
            )
            if (
                key != expected_key
                or record["result_identity"] != expected_result_identity
                or record["command_identity"] != expected_command_identity
                or record["command_result_identity"] != expected_command_result_identity
                or record["fingerprint"] != record["result_fingerprint"]
            ):
                raise ValueError("kill result registry pointer mismatch")
            command_record = history.get(expected_command_identity)
            if (
                command_record is None
                or command_record.get("record_type") != "KILL_SWITCH_COMMAND"
                or command_record.get("command_identity") != expected_command_identity
                or command_record.get("command_id") != record["command_id"]
                or command_record.get("command_idempotency_key")
                != record["command_idempotency_key"]
                or command_record.get("command_scope") != record["command_scope"]
                or command_record.get("command_fingerprint") != record["command_fingerprint"]
                or command_record.get("fingerprint") != record["command_fingerprint"]
            ):
                raise ValueError("kill result immutable command history mismatch")
            command_to_results.setdefault(expected_command_identity, set()).add(
                expected_result_identity
            )
            result_to_commands.setdefault(expected_result_identity, set()).add(
                expected_command_identity
            )

        for record in result_records.values():
            counterpart = command_result_records.get(record["command_result_identity"])
            if counterpart is None or any(
                record[field] != counterpart[field] for field in shared_fields
            ):
                raise ValueError("orphan or divergent kill result registry backlink")
        for command_result_identity, record in command_result_records.items():
            counterpart = result_records.get(record["result_identity"])
            if counterpart is None or any(
                record[field] != counterpart[field] for field in shared_fields
            ):
                raise ValueError("orphan or divergent command-result registry backlink")
            if record["command_result_identity"] != command_result_identity:
                raise ValueError("command-result registry key mismatch")
        if any(len(results) != 1 for results in command_to_results.values()) or any(
            len(commands) != 1 for commands in result_to_commands.values()
        ):
            raise ValueError("kill result registry cardinality violation")

    def _validate_kill_result_duplicate_binding(
        self, result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        history = context["identity_history"]
        result_record = history[_kill_result_identity(result)]
        command_record = history[result_record["command_identity"]]
        if (
            command_record["command_id"] != result["command_id"]
            or command_record["command_idempotency_key"] != result["idempotency_key"]
            or command_record["command_scope"] != result["scope"]
            or command_record["command_fingerprint"] != result["command_fingerprint"]
        ):
            raise ValueError("duplicate result immutable command history mismatch")

    def _validate_control_dto(self, message: dict[str, Any], context: dict[str, Any]) -> None:
        dto_type = message["dto_type"]
        if dto_type == "CONFIG_CANDIDATE":
            self._validate_config_candidate(message, context)
        elif dto_type == "KILL_SWITCH_COMMAND":
            self._validate_kill_command(message, context)
        elif dto_type == "KILL_SWITCH_RESULT":
            self._validate_kill_result(message, context)
        else:
            raise ValueError("unsupported control DTO type")

    def _validate_event_specific(self, message: dict[str, Any], context: dict[str, Any]) -> None:
        payload = message["payload"]
        event_type = message["message_type"]
        if event_type == "config.version_activated.v1":
            self._validate_config_event(payload, context)
        elif event_type == "system.kill_switch_changed.v1":
            self._validate_kill_event(payload, context)
        elif event_type == "system.mode_changed.v1":
            self._validate_mode_event(payload, context)
        elif event_type == "system.component_health_changed.v1":
            self._validate_health_event(payload, context)
        else:
            raise ValueError("unsupported control event type")

    def _validate_config_event(self, payload: dict[str, Any], context: dict[str, Any]) -> None:
        config = context["accepted_state"]["config"]
        if (
            _sha(_candidate_checksum_projection({}, config)) != config["config_checksum"]
            or payload["config_domain"] != config["config_domain"]
            or payload["candidate_version"] != config["config_version"]
            or payload["candidate_checksum"] != config["config_checksum"]
            or payload["policy_version"] != config["policy_version"]
            or payload["policy_checksum"] != config["policy_checksum"]
            or sorted(payload["secret_references"]) != sorted(config["secret_references"])
            or payload["activation_mode"] != config["activation_mode"]
            or payload["safe_boundary"] != config["safe_boundary"]
        ):
            raise ValueError("config policy/version authority mismatch")
        self._validate_hard_limits(config, config)
        required = set(config["required_components"])
        acks = payload["component_acks"]
        if (
            set(config["components"]) != required
            or set(payload["required_components"]) != required
            or set(acks) != required
        ):
            raise ValueError("component acknowledgement set mismatch")
        for component, ack in acks.items():
            component_authority = config["components"].get(component)
            if (
                component_authority is None
                or component_authority["component_id"] != component
                or ack["component_id"] != component
                or ack["candidate_version"] != payload["candidate_version"]
                or ack["candidate_checksum"] != payload["candidate_checksum"]
                or ack["generation"] != component_authority["generation"]
                or ack["capability_version"] != component_authority["capability_version"]
                or ack["activation_mode"] != component_authority["activation_mode"]
                or ack["safe_boundary"] != component_authority["safe_boundary"]
            ):
                raise ValueError("component acknowledgement binding mismatch")
            if (
                ack["activation_mode"] != payload["activation_mode"]
                or ack["safe_boundary"] != payload["safe_boundary"]
                or ack["generation"] < 1
                or not ack["capability_version"]
                or ack["prepare_result"] not in {"PREPARED", "APPLIED", "REJECTED"}
                or not ack["observed_at"]
                or ack["ack_sequence"] < 1
            ):
                raise ValueError("component acknowledgement mode mismatch")
            if _utc_instant(ack["observed_at"]) > _utc_instant(context["evaluation_at"]):
                raise ValueError("component acknowledgement observed in future")
        if (
            payload["activation_mode"] == "HOT_RELOAD"
            and payload["safe_boundary"] == "RESTART_ONLY"
        ):
            raise ValueError("hot reload cannot require restart boundary")
        if payload["outcome"] == "APPLIED":
            if (
                payload["active_version"] != payload["candidate_version"]
                or payload["active_checksum"] != payload["candidate_checksum"]
            ):
                raise ValueError("active config identity mismatch")
            if any(ack["prepare_result"] != "APPLIED" for ack in acks.values()):
                raise ValueError("partial silent activation")
        elif payload["active_version"] is not None or payload["active_checksum"] is not None:
            raise ValueError("non-applied config cannot claim active identity")
        elif payload["outcome"] == "REJECTED" and any(
            ack["prepare_result"] == "APPLIED" for ack in acks.values()
        ):
            raise ValueError("rejected config cannot contain applied acknowledgement")

    def _validate_config_candidate(
        self, candidate: dict[str, Any], context: dict[str, Any]
    ) -> None:
        config = context["accepted_state"]["config"]
        if (
            candidate["config_domain"] != config["config_domain"]
            or candidate["candidate_version"] != config["config_version"]
            or candidate["candidate_checksum"]
            != _sha(_candidate_checksum_projection(candidate, config))
            or candidate["candidate_checksum"] != config["config_checksum"]
            or set(candidate["required_components"]) != set(config["required_components"])
            or candidate["activation_mode"] != config["activation_mode"]
            or candidate["safe_boundary"] != config["safe_boundary"]
            or sorted(candidate["secret_references"]) != sorted(config["secret_references"])
            or candidate["system_hard_limit_policy_version"]
            != config["system_hard_limit_policy_version"]
            or candidate["system_hard_limit_policy_checksum"]
            != config["system_hard_limit_policy_checksum"]
            or candidate["valuation_currency"] != config["valuation_currency"]
            or candidate["dynamic_limits"] != config["dynamic_limits"]
            or candidate["system_hard_limit_policy"] != config["system_hard_limit_policy"]
            or candidate["component_authority"] != config["components"]
            or set(candidate["component_authority"]) != set(candidate["required_components"])
            or set(config["components"]) != set(config["required_components"])
            or any(
                component["component_id"] != component_id
                for component_id, component in candidate["component_authority"].items()
            )
            or candidate["policy_version"] != config["policy_version"]
            or candidate["policy_checksum"] != config["policy_checksum"]
        ):
            raise ValueError("config candidate checksum or authority mismatch")
        self._validate_hard_limits(candidate, config)
        if _utc_instant(candidate["deadline_at"]) <= _utc_instant(context["evaluation_at"]):
            raise ValueError("config candidate deadline expired")

    def _validate_hard_limits(self, candidate: dict[str, Any], authority: dict[str, Any]) -> None:
        policy = candidate["system_hard_limit_policy"]
        accepted_policy = authority["system_hard_limit_policy"]
        if (
            candidate["valuation_currency"] != policy["valuation_currency"]
            or authority["valuation_currency"] != accepted_policy["valuation_currency"]
            or candidate["valuation_currency"] != authority["valuation_currency"]
            or policy != accepted_policy
            or candidate["system_hard_limit_policy_checksum"]
            != _sha(_hard_limit_policy_projection(policy))
            or authority["system_hard_limit_policy_checksum"]
            != _sha(_hard_limit_policy_projection(accepted_policy))
        ):
            raise ValueError("hard limit policy currency/content/hash mismatch")
        hard_limits = accepted_policy["limits"]
        dynamic_limits = candidate["dynamic_limits"]
        if set(dynamic_limits) != set(hard_limits) or any(
            Decimal(dynamic_limits[name]) > Decimal(hard_limits[name]) for name in hard_limits
        ):
            raise ValueError("dynamic limit relaxes accepted hard limit")

    def _validate_kill_event(self, payload: dict[str, Any], context: dict[str, Any]) -> None:
        authority = context["accepted_state"]["kill_switch"]
        lease = context["accepted_state"]["lease"]
        command = authority["command"]
        if command["command_fingerprint"] != _sha(_kill_command_fingerprint_projection(command)):
            raise ValueError("accepted kill command fingerprint mismatch")
        for field in (
            "command_id",
            "idempotency_key",
            "command_fingerprint",
            "scope",
            "desired_state",
            "reason_code",
            "expected_version",
            "recovery_evidence_reference",
            "recovery_barrier_generation",
            "recovery_barrier_version",
            "recovery_barrier_checksum",
            "recovery_evidence_digest",
            "recovery_aggregate_evidence_digest",
        ):
            event_field = "command_fingerprint" if field == "command_fingerprint" else field
            if payload.get(event_field) != command[field]:
                raise ValueError("kill event command binding mismatch")
        self._validate_kill_outcome(payload, authority)
        evaluation_at = _utc_instant(context["evaluation_at"])
        if _utc_instant(payload["deadline_at"]) <= evaluation_at:
            raise ValueError("kill switch deadline expired")
        auth = payload["authorization_evidence"]
        if (
            auth["authorization_id"] != authority["authorization_id"]
            or auth["authorization_version"] != authority["authorization_version"]
            or auth["authorization_checksum"] != authority["authorization_checksum"]
        ):
            raise ValueError("kill switch authorization binding mismatch")
        if (
            payload["leader_lease_id"] != lease["lease_id"]
            or payload["fencing_token"] != lease["fencing_token"]
            or payload.get("leader_id") != lease.get("leader_id")
            or payload.get("lease_epoch") != lease.get("epoch")
        ):
            raise ValueError("kill switch fencing binding mismatch")
        if auth.get("revoked", False) or _utc_instant(auth["valid_until"]) <= evaluation_at:
            raise ValueError("kill switch authorization invalid")
        if _utc_instant(auth["approved_at"]) > evaluation_at:
            raise ValueError("kill switch authorization approved in future")
        if _utc_instant(lease["expires_at"]) <= evaluation_at:
            raise ValueError("kill switch leader lease expired")
        if payload["desired_state"] == "OFF" and (
            payload["recovery_evidence_reference"] is None or payload["restores_normal"]
        ):
            raise ValueError("disable requires recovery evidence and cannot restore NORMAL")
        if payload["desired_state"] == "OFF":
            self._validate_accepted_recovery_barrier(payload, context)
        if payload["desired_state"] == "ON" and payload["recovery_evidence_reference"] is not None:
            raise ValueError("enable cannot carry recovery evidence")
        self._validate_kill_effect_evidence(payload, authority, context)
        if (
            payload["policy_version"] != context["accepted_policy"]["version"]
            or payload["policy_checksum"] != context["accepted_policy"]["checksum"]
        ):
            raise ValueError("kill policy binding mismatch")

    def _validate_kill_command(self, command: dict[str, Any], context: dict[str, Any]) -> None:
        authority = context["accepted_state"]["kill_switch"]
        lease = context["accepted_state"]["lease"]
        expected = authority["command"]
        for field in (
            "command_id",
            "idempotency_key",
            "command_fingerprint",
            "scope",
            "desired_state",
            "reason_code",
            "expected_version",
            "recovery_evidence_reference",
            "recovery_barrier_generation",
            "recovery_barrier_version",
            "recovery_barrier_checksum",
            "recovery_evidence_digest",
            "recovery_aggregate_evidence_digest",
        ):
            if command[field] != expected[field]:
                raise ValueError("kill command authority mismatch")
        if command["expected_version"] != authority["current_version"]:
            raise ValueError("kill command expected version mismatch")
        auth = command["authorization_evidence"]
        evaluation_at = _utc_instant(context["evaluation_at"])
        if (
            auth["authorization_id"] != authority["authorization_id"]
            or auth["authorization_version"] != authority["authorization_version"]
            or auth["authorization_checksum"] != authority["authorization_checksum"]
            or auth["revoked"]
            or _utc_instant(auth["valid_until"]) <= evaluation_at
            or _utc_instant(auth["approved_at"]) > evaluation_at
        ):
            raise ValueError("kill command authorization mismatch")
        if (
            command["leader_lease_id"] != lease["lease_id"]
            or command["fencing_token"] != lease["fencing_token"]
        ):
            raise ValueError("kill command fencing mismatch")
        if _utc_instant(lease["expires_at"]) <= evaluation_at:
            raise ValueError("kill command leader lease expired")
        if _utc_instant(command["deadline_at"]) <= evaluation_at:
            raise ValueError("kill command deadline expired")
        if command["desired_state"] == "OFF":
            self._validate_accepted_recovery_barrier(command, context)

    def _validate_kill_result(self, result: dict[str, Any], context: dict[str, Any]) -> None:
        authority = context["accepted_state"]["kill_switch"]
        command = authority["command"]
        command_authorization = command["authorization_evidence"]
        lease = context["accepted_state"]["lease"]
        if (
            result["authorization_id"] != authority["authorization_id"]
            or command_authorization["authorization_version"] != authority["authorization_version"]
            or command_authorization["authorization_checksum"]
            != authority["authorization_checksum"]
        ):
            raise ValueError("kill result current authorization authority mismatch")
        if (
            result["leader_lease_id"] != lease["lease_id"]
            or result["fencing_token"] != lease["fencing_token"]
            or _utc_instant(lease["expires_at"]) <= _utc_instant(context["evaluation_at"])
        ):
            raise ValueError("kill result current lease authority mismatch")
        self._validate_kill_outcome(result, authority)
        self._validate_kill_effect_evidence(result, authority, context)
        if result["outcome"] == "APPLIED" and result["applied_at"] is None:
            raise ValueError("applied result requires applied_at")
        if result["outcome"] != "APPLIED" and result["applied_at"] is not None:
            raise ValueError("non-applied result cannot claim applied_at")
        if result["applied_at"] is not None and _utc_instant(result["applied_at"]) > _utc_instant(
            context["evaluation_at"]
        ):
            raise ValueError("kill result applied_at is in the future")

    def _validate_kill_result_binding(
        self, result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        authority = context["accepted_state"]["kill_switch"]
        command = authority["command"]
        if command["command_fingerprint"] != _sha(_kill_command_fingerprint_projection(command)):
            raise ValueError("accepted kill command fingerprint mismatch")
        for field in (
            "correlation_id",
            "command_id",
            "command_fingerprint",
            "idempotency_key",
            "scope",
            "desired_state",
            "reason_code",
            "expected_version",
        ):
            if result[field] != command[field]:
                raise ValueError("kill result command identity mismatch")
        if (
            result["authorization_id"] != command["authorization_evidence"]["authorization_id"]
            or result["leader_lease_id"] != command["leader_lease_id"]
            or result["fencing_token"] != command["fencing_token"]
        ):
            raise ValueError("kill result immutable command authority mismatch")

    def _validate_kill_outcome(self, result: dict[str, Any], authority: dict[str, Any]) -> None:
        if result["restores_normal"] is not False:
            raise ValueError("kill switch result cannot restore NORMAL")
        if (
            result["expected_version"] != authority["current_version"]
            or result["previous_version"] != authority["current_version"]
        ):
            raise ValueError("kill switch authority version mismatch")
        outcome = result["outcome"]
        expected = {
            "APPLIED": (
                result["desired_state"],
                result["previous_version"] + 1,
                False,
            ),
            "REJECTED": (authority["effective_state"], result["previous_version"], False),
            "PARTIAL": ("ON", result["previous_version"], True),
            "TIMEOUT": ("UNKNOWN", result["previous_version"], True),
            "UNKNOWN": ("UNKNOWN", result["previous_version"], True),
        }[outcome]
        if (
            result["effective_state"],
            result["current_version"],
            result["reconciliation_required"],
        ) != expected:
            raise ValueError("kill switch outcome matrix mismatch")

    def _validate_kill_effect_evidence(
        self,
        result: dict[str, Any],
        authority: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        expected_ack_ids = set(authority["effect_ack_ids"])
        acknowledged = set(result["effect_evidence"]["ack_ids"])
        if _utc_instant(result["effect_evidence"]["observed_at"]) > _utc_instant(
            context["evaluation_at"]
        ):
            raise ValueError("kill switch effect evidence observed in future")
        if not acknowledged <= expected_ack_ids:
            raise ValueError("kill switch effect evidence contains unknown acknowledgement")
        outcome = result["outcome"]
        if outcome == "APPLIED" and acknowledged != expected_ack_ids:
            raise ValueError("applied kill switch requires every expected effect acknowledgement")
        if outcome == "REJECTED" and acknowledged:
            raise ValueError("rejected kill switch cannot claim effect acknowledgement")
        if outcome == "PARTIAL" and (not acknowledged or acknowledged == expected_ack_ids):
            raise ValueError("partial kill switch requires a strict acknowledgement subset")
        if outcome in {"TIMEOUT", "UNKNOWN"} and acknowledged == expected_ack_ids:
            raise ValueError("uncertain kill switch outcome cannot claim complete effect evidence")

    def _validate_accepted_recovery_barrier(
        self, reference: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        recovery_id = reference["recovery_evidence_reference"]
        entry, barrier = self._validate_recovery_registry_entry(recovery_id, context)
        if entry["barrier_id"] != recovery_id or entry["state"] != "OPEN":
            raise ValueError("accepted barrier must be OPEN")
        bindings = {
            "generation": "recovery_barrier_generation",
            "barrier_version": "recovery_barrier_version",
            "barrier_checksum": "recovery_barrier_checksum",
            "evidence_digest": "recovery_evidence_digest",
            "aggregate_evidence_digest": "recovery_aggregate_evidence_digest",
        }
        if any(reference[field] != entry[key] for key, field in bindings.items()):
            raise ValueError("accepted barrier reference binding mismatch")
        return barrier

    def _validate_recovery_registry_entry(
        self, recovery_id: str, context: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        entry = context.get("accepted_recovery_barriers", {}).get(recovery_id)
        if entry is None:
            raise ValueError("recovery barrier reference is not an accepted barrier")
        return self._validate_recovery_authority_entry(recovery_id, entry, context)

    def _validate_recovery_authority_entry(
        self, recovery_id: str, entry: dict[str, Any], context: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        barrier = entry["barrier"]
        self._validate_recovery_barrier(barrier, context)
        authority = context["accepted_state"]["kill_switch"]
        evidence_digest = _sha(barrier["evidence"])
        aggregate_digest = _sha(
            {
                "barrier_id": barrier["barrier_id"],
                "generation": barrier["generation"],
                "state": barrier["state"],
                "opened_at": barrier["opened_at"],
                "required_evidence": sorted(barrier["required_evidence"]),
                "evidence_digest": evidence_digest,
            }
        )
        barrier_checksum = _sha(
            {
                "barrier_id": barrier["barrier_id"],
                "generation": barrier["generation"],
                "state": barrier["state"],
                "opened_at": barrier["opened_at"],
                "evidence": barrier["evidence"],
                "required_evidence": sorted(barrier["required_evidence"]),
                "invalidation_reason": barrier["invalidation_reason"],
            }
        )
        exact = {
            "barrier_id": barrier["barrier_id"],
            "generation": barrier["generation"],
            "barrier_checksum": barrier_checksum,
            "evidence_digest": evidence_digest,
            "aggregate_evidence_digest": aggregate_digest,
            "state": barrier["state"],
            "opened_at": barrier["opened_at"],
            "observed_at": barrier["evidence"]["observed_at"],
            "fresh_until": barrier["evidence"]["market_fresh_until"],
            "policy_version": context["accepted_policy"]["version"],
            "policy_checksum": context["accepted_policy"]["checksum"],
            "authorization_id": authority["authorization_id"],
            "authorization_version": authority["authorization_version"],
            "authorization_checksum": authority["authorization_checksum"],
            "kill_switch_version": authority["current_version"],
        }
        instant_fields = {"opened_at", "observed_at", "fresh_until"}
        if any(
            entry.get(key) != value for key, value in exact.items() if key not in instant_fields
        ):
            raise ValueError("accepted barrier metadata checksum/digest authority mismatch")
        for key in instant_fields:
            if entry.get(key) is None or exact[key] is None:
                if entry.get(key) != exact[key]:
                    raise ValueError("accepted barrier instant authority mismatch")
            elif _utc_instant(entry[key]) != _utc_instant(exact[key]):
                raise ValueError("accepted barrier instant authority mismatch")
        return entry, barrier

    def _validate_mode_event(self, payload: dict[str, Any], context: dict[str, Any]) -> None:
        if not payload.get("causation_id"):
            raise ValueError("control events are never root")
        state = context["accepted_state"]["system_mode"]
        if (
            payload["from_mode"],
            payload["to_mode"],
            payload["reason_code"],
        ) not in MODE_TRANSITIONS:
            raise ValueError("illegal system mode transition")
        if payload["from_mode"] != state["mode"] or payload["generation"] != state["generation"]:
            raise ValueError("system mode authority mismatch")
        if payload["reason_code"] == "RECOVERY_PASSED":
            entry = context["accepted_state"].get("recovery_barrier")
            if entry is None:
                recovery_id = payload["evidence"]["recovery_barrier_id"]
                _entry, barrier = self._validate_recovery_registry_entry(recovery_id, context)
            else:
                _entry, barrier = self._validate_recovery_authority_entry(
                    payload["evidence"]["recovery_barrier_id"], entry, context
                )
            if (
                barrier is None
                or barrier.get("state") != "OPEN"
                or barrier.get("opened_at") is None
            ):
                raise ValueError("RecoveryPassed requires an open recovery barrier")
            if payload["evidence"]["recovery_barrier_id"] != barrier["barrier_id"]:
                raise ValueError("recovery barrier identity mismatch")
        if (
            payload["evidence"]["policy_version"] != state["policy_version"]
            or payload["evidence"]["policy_checksum"] != state["policy_checksum"]
        ):
            raise ValueError("system mode policy mismatch")

    def _validate_health_event(self, payload: dict[str, Any], context: dict[str, Any]) -> None:
        component = context["accepted_state"]["components"].get(payload["component"])
        if (
            component is None
            or payload["component_version"] != component["version"]
            or payload["generation"] != component["generation"]
            or payload["previous_health"] != component["health"]
        ):
            raise ValueError("component generation/version mismatch")
        reasons = HEALTH_TRANSITIONS.get((payload["previous_health"], payload["health"]))
        if not reasons or payload["reason_code"] not in reasons:
            raise ValueError("illegal component health transition or reason")
        if (
            payload["evidence"]["policy_version"] != context["accepted_policy"]["version"]
            or payload["evidence"]["policy_checksum"] != context["accepted_policy"]["checksum"]
        ):
            raise ValueError("component policy mismatch")

    def _validate_recovery_barrier(self, barrier: dict[str, Any], context: dict[str, Any]) -> None:
        _validator("control/control-plane.v1.schema.json").validate(barrier)
        authority = context["accepted_state"]
        evidence = barrier["evidence"]
        if barrier["state"] == "OPEN" and barrier["opened_at"] is None:
            raise ValueError("open recovery barrier requires opened_at")
        if barrier["state"] in {"CLOSED", "INVALIDATED"} and barrier["opened_at"] is not None:
            raise ValueError("closed or invalidated recovery barrier opened_at mismatch")
        evaluation_at = _utc_instant(context["evaluation_at"])
        observed_at = _utc_instant(evidence["observed_at"])
        market_fresh_until = _utc_instant(evidence["market_fresh_until"])
        if barrier["opened_at"] is not None and _utc_instant(barrier["opened_at"]) > evaluation_at:
            raise ValueError("recovery barrier opened in future")
        if observed_at > evaluation_at:
            raise ValueError("barrier evidence observed in future")
        if market_fresh_until != _utc_instant(authority["market"]["fresh_until"]):
            raise ValueError("barrier market freshness authority mismatch")
        if market_fresh_until <= evaluation_at and not (
            barrier["state"] == "INVALIDATED" and barrier["invalidation_reason"] == "MARKET_STALE"
        ):
            raise ValueError("barrier evidence is stale")
        if barrier["state"] == "INVALIDATED":
            reason = barrier["invalidation_reason"]
            if reason is None:
                raise ValueError("invalidated barrier requires typed reason")
            if (
                reason == "MARKET_STALE"
                and authority["market"]["quality"] == "NORMAL"
                and authority["market"]["unresolved_gap_count"] == 0
                and _utc_instant(authority["market"]["fresh_until"]) > evaluation_at
            ):
                raise ValueError("invalidated reason has no market failure")
            if reason == "AUDIT_UNAVAILABLE" and authority["audit"]["healthy"]:
                raise ValueError("invalidated reason has no audit failure")
            if (
                reason == "LEASE_EXPIRED"
                and _utc_instant(authority["lease"]["expires_at"]) > evaluation_at
            ):
                raise ValueError("invalidated reason has no lease failure")
            if reason == "COMPONENT_UNHEALTHY" and all(
                item["health"] == "HEALTHY" for item in authority["components"].values()
            ):
                raise ValueError("invalidated reason has no component failure")
            if reason == "CONFIG_MISMATCH" and (
                evidence["config_version"] == authority["config"]["config_version"]
                and evidence["config_checksum"] == authority["config"]["config_checksum"]
            ):
                raise ValueError("invalidated reason has no config failure")
            if (
                reason == "RECONCILIATION_BLOCKED"
                and authority["reconciliation"]["open_blocking_case_count"] == 0
            ):
                raise ValueError("invalidated reason has no reconciliation failure")
            if reason == "MANUAL_AUTHORIZED":
                raise ValueError("manual invalidation requires explicit authorization evidence")
        if barrier["state"] == "CLOSED" and (
            barrier["opened_at"] is not None or barrier["invalidation_reason"] is not None
        ):
            raise ValueError("closed barrier state mismatch")
        required = {
            "CONFIG_VERIFIED",
            "MARKET_FRESH",
            "AUDIT_AVAILABLE",
            "RECONCILIATION_COMPLETE",
            "LEASE_FENCED",
            "OUTBOX_HEALTHY",
        }
        if barrier["state"] == "OPEN" and set(barrier["required_evidence"]) != required:
            raise ValueError("recovery barrier evidence incomplete")
        if (
            evidence["config_version"] != authority["config"]["config_version"]
            or evidence["config_checksum"] != authority["config"]["config_checksum"]
        ):
            raise ValueError("barrier config evidence mismatch")
        if barrier["state"] == "OPEN" and (
            evidence["market_watermark"] != authority["market"]["watermark"]
            or authority["market"]["quality"] != "NORMAL"
            or authority["market"]["unresolved_gap_count"] != 0
        ):
            raise ValueError("barrier market evidence mismatch")
        if barrier["state"] == "OPEN" and (
            evidence["audit_watermark"] != authority["audit"]["outbox_position"]
            or not authority["audit"]["healthy"]
            or authority["audit"]["lag"] > authority["critical_lag"]["threshold"]
            or authority["critical_lag"]["current"] >= authority["critical_lag"]["threshold"]
        ):
            raise ValueError("barrier audit evidence mismatch")
        if barrier["state"] == "OPEN" and (
            evidence["reconciliation_case_count"]
            != authority["reconciliation"]["open_blocking_case_count"]
            or evidence["reconciliation_case_count"] != 0
        ):
            raise ValueError("barrier reconciliation evidence mismatch")
        authority_components = authority["components"]
        component_ids = set(authority_components)
        if (
            set(evidence["component_versions"]) != component_ids
            or set(evidence["component_checksums"]) != component_ids
            or set(evidence["component_generations"]) != component_ids
            or set(evidence["component_health"]) != component_ids
        ):
            raise ValueError("barrier component evidence set mismatch")
        for component, version in evidence["component_versions"].items():
            accepted = authority["components"].get(component)
            if (
                accepted is None
                or accepted["version"] != version
                or accepted["checksum"] != evidence["component_checksums"].get(component)
                or (barrier["state"] == "OPEN" and accepted["health"] != "HEALTHY")
            ):
                raise ValueError("barrier component evidence mismatch")
            if "component_generations" in evidence and (
                evidence["component_generations"].get(component) != accepted["generation"]
                or evidence["component_health"].get(component) != accepted["health"]
            ):
                raise ValueError("barrier component generation/health mismatch")
        market = authority["market"]
        exact_market = {
            "market_calendar_version": market.get("calendar_version"),
            "market_calendar_checksum": market.get("calendar_checksum"),
            "market_session_id": market.get("session_id"),
            "market_session_state": market.get("session_state"),
            "market_policy_version": market.get("policy_version"),
            "market_policy_checksum": market.get("policy_checksum"),
            "market_tzdb_version": market.get("tzdb_version"),
            "market_tzdb_checksum": market.get("tzdb_checksum"),
            "market_source_version": market.get("source_version"),
            "market_quality": market.get("quality"),
            "unresolved_gap_count": market.get("unresolved_gap_count"),
            "market_fresh_until": market.get("fresh_until"),
        }
        if any(
            evidence[key] != value
            for key, value in exact_market.items()
            if key != "market_fresh_until"
        ) or _utc_instant(evidence["market_fresh_until"]) != _utc_instant(
            exact_market["market_fresh_until"]
        ):
            raise ValueError("barrier market authority mismatch")
        lease = authority["lease"]
        exact_lease = {
            "lease_id": lease.get("lease_id"),
            "leader_id": lease.get("leader_id"),
            "lease_authority_version": lease.get("authority_version"),
            "lease_epoch": lease.get("epoch"),
            "fencing_token": lease.get("fencing_token"),
            "lease_expires_at": lease.get("expires_at"),
        }
        if any(
            evidence[key] != value
            for key, value in exact_lease.items()
            if key != "lease_expires_at"
        ) or _utc_instant(evidence["lease_expires_at"]) != _utc_instant(
            exact_lease["lease_expires_at"]
        ):
            raise ValueError("barrier lease authority mismatch")
        audit = authority["audit"]
        if (
            evidence["audit_outbox_position"] != audit.get("outbox_position")
            or evidence["audit_inbox_position"] != audit.get("inbox_position")
            or evidence["audit_watermark"] != audit.get("watermark")
            or evidence["audit_checksum"] != audit.get("checksum")
            or evidence["audit_lag"] != audit.get("lag")
            or evidence["audit_healthy"] != audit.get("healthy")
        ):
            raise ValueError("barrier audit authority mismatch")
        reconciliation = authority["reconciliation"]
        if evidence["reconciliation_version"] != reconciliation.get("version") or evidence[
            "reconciliation_checksum"
        ] != reconciliation.get("checksum"):
            raise ValueError("barrier reconciliation authority mismatch")
        critical = authority["critical_lag"]
        if (
            evidence["critical_lag_policy_version"] != critical.get("policy_version")
            or evidence["critical_lag_policy_checksum"] != critical.get("checksum")
            or evidence["critical_lag_threshold"] != critical.get("threshold")
            or evidence["critical_lag_measurement_source"] != critical.get("measurement_source")
            or evidence["critical_lag_window_seconds"] != critical.get("window_seconds")
            or evidence["critical_lag_recovery_window_seconds"]
            != critical.get("recovery_window_seconds")
            or evidence["critical_lag_current"] != critical.get("current")
        ):
            raise ValueError("barrier critical lag authority mismatch")
        if (
            barrier["state"] == "OPEN"
            and _utc_instant(authority["lease"]["expires_at"]) <= evaluation_at
        ):
            raise ValueError("barrier lease expired")
        if barrier["state"] == "CLOSED":
            return
        if barrier["state"] == "INVALIDATED":
            if barrier["opened_at"] is not None or not barrier["invalidation_reason"]:
                raise ValueError("invalidated barrier state mismatch")
            return

    def _scan_forbidden_keys(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in self.FORBIDDEN_KEYS:
                    raise ValueError("sensitive field")
                self._scan_forbidden_keys(child)
        elif isinstance(value, list):
            for child in value:
                self._scan_forbidden_keys(child)


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


def _open_recovery_barrier_authority(
    context: dict[str, Any], correlation_id: str
) -> dict[str, Any]:
    authority = context["accepted_state"]
    barrier = {
        "dto_type": "RECOVERY_BARRIER",
        "schema_version": 1,
        "correlation_id": correlation_id,
        "created_at": "2026-08-11T01:00:00Z",
        "barrier_id": "barrier-1",
        "state": "OPEN",
        "generation": 1,
        "opened_at": "2026-08-11T00:59:00Z",
        "evidence": {
            "config_version": authority["config"]["config_version"],
            "config_checksum": authority["config"]["config_checksum"],
            "market_watermark": authority["market"]["watermark"],
            "audit_watermark": authority["audit"]["watermark"],
            "reconciliation_case_count": authority["reconciliation"]["open_blocking_case_count"],
            "component_versions": {
                key: value["version"] for key, value in authority["components"].items()
            },
            "component_checksums": {
                key: value["checksum"] for key, value in authority["components"].items()
            },
            "component_generations": {
                key: value["generation"] for key, value in authority["components"].items()
            },
            "component_health": {
                key: value["health"] for key, value in authority["components"].items()
            },
            "lease_id": authority["lease"]["lease_id"],
            "leader_id": authority["lease"]["leader_id"],
            "lease_authority_version": authority["lease"]["authority_version"],
            "lease_epoch": authority["lease"]["epoch"],
            "fencing_token": authority["lease"]["fencing_token"],
            "lease_expires_at": authority["lease"]["expires_at"],
            "audit_outbox_position": authority["audit"]["outbox_position"],
            "audit_inbox_position": authority["audit"]["inbox_position"],
            "audit_checksum": authority["audit"]["checksum"],
            "audit_lag": authority["audit"]["lag"],
            "audit_healthy": authority["audit"]["healthy"],
            "market_calendar_version": authority["market"]["calendar_version"],
            "market_calendar_checksum": authority["market"]["calendar_checksum"],
            "market_session_id": authority["market"]["session_id"],
            "market_session_state": authority["market"]["session_state"],
            "market_policy_version": authority["market"]["policy_version"],
            "market_policy_checksum": authority["market"]["policy_checksum"],
            "market_tzdb_version": authority["market"]["tzdb_version"],
            "market_tzdb_checksum": authority["market"]["tzdb_checksum"],
            "market_source_version": authority["market"]["source_version"],
            "market_quality": authority["market"]["quality"],
            "unresolved_gap_count": authority["market"]["unresolved_gap_count"],
            "market_fresh_until": authority["market"]["fresh_until"],
            "reconciliation_version": authority["reconciliation"]["version"],
            "reconciliation_checksum": authority["reconciliation"]["checksum"],
            "critical_lag_policy_version": authority["critical_lag"]["policy_version"],
            "critical_lag_policy_checksum": authority["critical_lag"]["checksum"],
            "critical_lag_threshold": authority["critical_lag"]["threshold"],
            "critical_lag_measurement_source": authority["critical_lag"]["measurement_source"],
            "critical_lag_window_seconds": authority["critical_lag"]["window_seconds"],
            "critical_lag_recovery_window_seconds": authority["critical_lag"][
                "recovery_window_seconds"
            ],
            "critical_lag_current": authority["critical_lag"]["current"],
            "observed_at": "2026-08-11T01:00:00Z",
        },
        "required_evidence": [
            "CONFIG_VERIFIED",
            "MARKET_FRESH",
            "AUDIT_AVAILABLE",
            "RECONCILIATION_COMPLETE",
            "LEASE_FENCED",
            "OUTBOX_HEALTHY",
        ],
        "invalidation_reason": None,
    }
    return _recovery_barrier_authority(context, barrier)


def _recovery_barrier_authority(context: dict[str, Any], barrier: dict[str, Any]) -> dict[str, Any]:
    authority = context["accepted_state"]
    evidence_digest = _sha(barrier["evidence"])
    return {
        "barrier_id": barrier["barrier_id"],
        "generation": barrier["generation"],
        "barrier_version": "barrier-v1",
        "barrier_checksum": _sha(
            {
                "barrier_id": barrier["barrier_id"],
                "generation": barrier["generation"],
                "state": barrier["state"],
                "opened_at": barrier["opened_at"],
                "evidence": barrier["evidence"],
                "required_evidence": sorted(barrier["required_evidence"]),
                "invalidation_reason": barrier["invalidation_reason"],
            }
        ),
        "evidence_digest": evidence_digest,
        "state": barrier["state"],
        "kill_switch_version": authority["kill_switch"]["current_version"],
        "opened_at": barrier["opened_at"],
        "observed_at": barrier["evidence"]["observed_at"],
        "fresh_until": barrier["evidence"]["market_fresh_until"],
        "policy_version": context["accepted_policy"]["version"],
        "policy_checksum": context["accepted_policy"]["checksum"],
        "aggregate_evidence_digest": _sha(
            {
                "barrier_id": barrier["barrier_id"],
                "generation": barrier["generation"],
                "state": barrier["state"],
                "opened_at": barrier["opened_at"],
                "required_evidence": sorted(barrier["required_evidence"]),
                "evidence_digest": evidence_digest,
            }
        ),
        "authorization_id": authority["kill_switch"]["authorization_id"],
        "authorization_version": authority["kill_switch"]["authorization_version"],
        "authorization_checksum": authority["kill_switch"]["authorization_checksum"],
        "barrier": barrier,
    }


def _validation_context(
    correlation_id: str,
    *,
    parent: str = "parent-message-0001",
    parent_time: str = "2026-08-11T00:59:59Z",
) -> dict[str, Any]:
    context = {
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
            "config": {
                "config_domain": "risk.rules",
                "config_version": "v2",
                "config_checksum": CONFIG_AUTHORITY_CHECKSUM,
                "candidate_payload": {"rules": "immutable"},
                "secret_references": ["secret://risk/api"],
                "required_components": ["OMS", "RiskEngine"],
                "components": {
                    "OMS": {
                        "component_id": "OMS",
                        "generation": 2,
                        "capability_version": "oms-cap-v1",
                        "activation_mode": "HOT_RELOAD",
                        "safe_boundary": "NEXT_ORDER_BOUNDARY",
                    },
                    "RiskEngine": {
                        "component_id": "RiskEngine",
                        "generation": 1,
                        "capability_version": "risk-cap-v1",
                        "activation_mode": "HOT_RELOAD",
                        "safe_boundary": "NEXT_ORDER_BOUNDARY",
                    },
                },
                "activation_mode": "HOT_RELOAD",
                "safe_boundary": "NEXT_ORDER_BOUNDARY",
                "system_hard_limit_policy_version": "hard-v1",
                "system_hard_limit_policy_checksum": "HARD_LIMIT_CHECKSUM",
                "valuation_currency": "CNY",
                "dynamic_limits": {
                    "maximum_order_notional": "500000",
                    "maximum_gross_exposure": "3000000",
                },
                "system_hard_limit_policy": {
                    "valuation_currency": "CNY",
                    "limits": {
                        "maximum_order_notional": "1000000",
                        "maximum_gross_exposure": "5000000",
                    },
                },
                "policy_version": "policy-v1",
                "policy_checksum": "a" * 64,
            },
            "market": {
                "calendar_version": "cal-v1",
                "calendar_checksum": "e" * 64,
                "session_id": "session-1",
                "session_state": "OPEN",
                "policy_version": "policy-v1",
                "policy_checksum": "a" * 64,
                "tzdb_version": "2026c",
                "tzdb_checksum": "f" * 64,
                "source_version": "source-v1",
                "watermark": 1,
                "unresolved_gap_count": 0,
                "quality": "NORMAL",
                "fresh_until": "2026-08-11T02:00:00Z",
            },
            "audit": {
                "outbox_position": 1,
                "inbox_position": 1,
                "watermark": 1,
                "lag": 0,
                "checksum": "9" * 64,
                "healthy": True,
            },
            "lease": {
                "lease_id": "lease-1",
                "leader_id": "oms-1",
                "epoch": 1,
                "authority_version": "lease-v1",
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
                "checksum": "1" * 64,
                "threshold": 10,
                "measurement_source": "source_received_watermark_delta",
                "window_seconds": 60,
                "current": 0,
                "recovery_window_seconds": 60,
            },
            "kill_switch": {
                "current_version": 1,
                "effective_state": "OFF",
                "authorization_id": "auth-1",
                "authorization_version": "v1",
                "authorization_checksum": "d" * 64,
                "command": {
                    "command_id": "command-kill-000001",
                    "idempotency_key": "idem-kill-event-1",
                    "command_fingerprint": "c" * 64,
                    "scope": "GLOBAL",
                    "desired_state": "ON",
                    "reason_code": "MANUAL_EMERGENCY",
                    "expected_version": 1,
                    "recovery_evidence_reference": None,
                    "recovery_barrier_generation": None,
                    "recovery_barrier_version": None,
                    "recovery_barrier_checksum": None,
                    "recovery_evidence_digest": None,
                    "recovery_aggregate_evidence_digest": None,
                },
                "effect_ack_ids": ["ack-kill-000001"],
            },
            "system_mode": {
                "mode": "STARTING",
                "generation": 1,
                "policy_version": "policy-v1",
                "policy_checksum": "a" * 64,
            },
        },
    }
    hard_policy = context["accepted_state"]["config"]["system_hard_limit_policy"]
    context["accepted_state"]["config"]["system_hard_limit_policy_checksum"] = _sha(
        _hard_limit_policy_projection(hard_policy)
    )
    context["accepted_state"]["config"]["config_checksum"] = _sha(
        _candidate_checksum_projection({}, context["accepted_state"]["config"])
    )
    command = {
        "dto_type": "KILL_SWITCH_COMMAND",
        "schema_version": 1,
        "correlation_id": correlation_id,
        "created_at": "2026-08-11T01:00:00Z",
        "command_id": "command-kill-000001",
        "command_fingerprint": "0" * 64,
        "scope": "GLOBAL",
        "desired_state": "ON",
        "reason_code": "MANUAL_EMERGENCY",
        "actor": "operator-1",
        "authorization_evidence": {
            "authorization_id": "auth-1",
            "authorization_version": "v1",
            "authorization_checksum": "d" * 64,
            "approver_ids": ["approver-1"],
            "approved_at": "2026-08-11T00:59:00Z",
            "valid_until": "2026-08-11T02:00:00Z",
            "revoked": False,
        },
        "expected_version": 1,
        "leader_lease_id": "lease-1",
        "fencing_token": "fence-token-000001",
        "deadline_at": "2026-08-11T01:01:00Z",
        "idempotency_key": "idem-kill-event-1",
        "reserved_capacity": {"cancel": 10, "recovery": 5},
        "recovery_evidence_reference": None,
        "recovery_barrier_generation": None,
        "recovery_barrier_version": None,
        "recovery_barrier_checksum": None,
        "recovery_evidence_digest": None,
        "recovery_aggregate_evidence_digest": None,
    }
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    context["accepted_state"]["kill_switch"]["command"] = command
    context["accepted_recovery_barriers"] = {
        "barrier-1": _open_recovery_barrier_authority(context, correlation_id)
    }
    return context


def test_control_dtos_are_structurally_schema_valid_only() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    schema_validator = _validator("control/control-plane.v1.schema.json")
    for dto in document["dtos"]:
        schema_validator.validate(dto)


def test_control_semantic_validator_has_one_public_entrypoint_and_private_dispatch() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    validator_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ControlSemanticValidator"
    )
    public_methods = [
        node.name
        for node in validator_class.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    assert public_methods == ["validate_control_message"]

    callers: dict[str, set[str]] = {}
    for method in validator_class.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                callers.setdefault(node.func.attr, set()).add(method.name)
    assert callers["_validate_event_specific"] == {"validate_control_message"}
    assert callers["_validate_recovery_barrier"] == {"_validate_recovery_authority_entry"}
    assert callers["_validate_recovery_authority_entry"] == {
        "validate_control_message",
        "_validate_mode_event",
        "_validate_recovery_registry_entry",
    }
    for branch in (
        "_validate_config_event",
        "_validate_kill_event",
        "_validate_mode_event",
        "_validate_health_event",
    ):
        assert callers[branch] == {"_validate_event_specific"}


def test_recovery_barrier_all_states_use_unified_entrypoint_and_freshness() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    context["accepted_state"]["recovery_barrier"] = deepcopy(
        context["accepted_recovery_barriers"]["barrier-1"]
    )
    checker.validate_control_message(message, context)

    context_stale = deepcopy(context)
    stale_barrier = context_stale["accepted_state"]["recovery_barrier"]["barrier"]
    stale_barrier["evidence"]["market_fresh_until"] = context_stale["evaluation_at"]
    context_stale["accepted_state"]["market"]["fresh_until"] = context_stale["evaluation_at"]
    context_stale["accepted_state"]["recovery_barrier"] = _recovery_barrier_authority(
        context_stale, stale_barrier
    )
    with pytest.raises(ValueError, match="stale"):
        checker.validate_control_message(message, context_stale)

    future_observed = deepcopy(context)
    future_observed["accepted_state"]["recovery_barrier"]["barrier"]["evidence"]["observed_at"] = (
        "2026-08-11T01:00:02Z"
    )
    with pytest.raises(ValueError, match="future"):
        checker.validate_control_message(message, future_observed)

    missing_freshness = deepcopy(context)
    missing_freshness["accepted_state"]["recovery_barrier"]["barrier"]["evidence"].pop(
        "market_fresh_until"
    )
    with pytest.raises(ValidationError):
        checker.validate_control_message(message, missing_freshness)

    duplicate_freshness = deepcopy(context)
    duplicate_freshness["accepted_state"]["recovery_barrier"]["barrier"]["evidence"][
        "fresh_until"
    ] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValidationError):
        checker.validate_control_message(message, duplicate_freshness)

    invalidated = deepcopy(context)
    barrier = invalidated["accepted_state"]["recovery_barrier"]["barrier"]
    barrier.update(state="INVALIDATED", opened_at=None, invalidation_reason="MARKET_STALE")
    barrier["evidence"].update(market_quality="STALE", market_fresh_until="2026-08-11T00:59:59Z")
    invalidated["accepted_state"]["market"]["quality"] = "STALE"
    invalidated["accepted_state"]["market"]["fresh_until"] = "2026-08-11T00:59:59Z"
    invalidated["accepted_state"]["recovery_barrier"] = _recovery_barrier_authority(
        invalidated, barrier
    )
    with pytest.raises(ValueError, match="open recovery barrier"):
        checker.validate_control_message(message, invalidated)

    forged = deepcopy(invalidated)
    forged_barrier = forged["accepted_state"]["recovery_barrier"]["barrier"]
    forged["accepted_state"]["market"]["quality"] = "NORMAL"
    forged["accepted_state"]["market"]["unresolved_gap_count"] = 0
    forged["accepted_state"]["market"]["fresh_until"] = "2026-08-11T02:00:00Z"
    forged_barrier["evidence"].update(
        market_quality="NORMAL", market_fresh_until="2026-08-11T02:00:00Z"
    )
    forged["accepted_state"]["recovery_barrier"] = _recovery_barrier_authority(
        forged, forged_barrier
    )
    with pytest.raises(ValueError, match="market failure"):
        checker.validate_control_message(message, forged)


@pytest.mark.parametrize(
    "case", _load(FIXTURES / "control-plane.v1/invalid.json")["cases"], ids=lambda c: c["name"]
)
def test_control_dto_schema_matrix_is_structural_only(case: dict[str, Any]) -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    dto = deepcopy(next(item for item in document["dtos"] if item["dto_type"] == case["dto_type"]))
    dto[case["field"]] = case["value"]
    schema_valid = _validator("control/control-plane.v1.schema.json").is_valid(dto)
    if case["name"] in {"alert_high_cardinality_evidence", "lease_expired_status_active"}:
        assert schema_valid, "cross-field semantics require the unified message validator"
    else:
        assert not schema_valid


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_control_public_events_have_registered_schema_and_valid_fixture(message_type: str) -> None:
    payload = _load(FIXTURES / "control-events.json")[message_type]
    _validator(EVENT_SCHEMAS[message_type]).validate(payload)
    assert payload["source"] in {"TradingCore", "HealthService", "ControlPlane", "ConfigService"}


def test_public_control_events_cannot_be_root() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.mode_changed.v1"])
    payload["causation_id"] = None
    with pytest.raises(ValidationError):
        _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).validate(payload)


def test_unified_kill_event_rejects_authorization_and_fence_mismatch() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.kill_switch_changed.v1"])
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    for field, value in (
        ("authorization_id", "other-auth"),
        ("fencing_token", "other-fence-token-000001"),
    ):
        invalid = deepcopy(payload)
        if field == "authorization_id":
            invalid["authorization_evidence"][field] = value
        else:
            invalid[field] = value
        message = _combined_fixture("system.kill_switch_changed.v1", invalid)
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(message, context)


def test_unified_kill_event_rejects_command_result_and_recovery_mutations() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.kill_switch_changed.v1"])
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    for mutate in (
        lambda item: item.update({"reason_code": "CONFIGURATION"}),
        lambda item: item.update({"previous_version": 0}),
        lambda item: item.update({"command_fingerprint": "0" * 64}),
        lambda item: item["effect_evidence"].update({"ack_ids": ["wrong-ack"]}),
        lambda item: item.update({"recovery_evidence_reference": "barrier-forged"}),
    ):
        invalid = deepcopy(payload)
        mutate(invalid)
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(
                _combined_fixture("system.kill_switch_changed.v1", invalid), context
            )


def test_kill_switch_disable_binds_strict_recovery_barrier_authority() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.kill_switch_changed.v1"])
    context = _validation_context(payload["correlation_id"])
    accepted_barrier = context["accepted_recovery_barriers"]["barrier-1"]
    payload.update(
        {
            "desired_state": "OFF",
            "effective_state": "OFF",
            "reason_code": "OPERATOR_RELEASE",
            "recovery_evidence_reference": "barrier-1",
            "recovery_barrier_generation": accepted_barrier["generation"],
            "recovery_barrier_version": accepted_barrier["barrier_version"],
            "recovery_barrier_checksum": accepted_barrier["barrier_checksum"],
            "recovery_evidence_digest": accepted_barrier["evidence_digest"],
            "recovery_aggregate_evidence_digest": accepted_barrier["aggregate_evidence_digest"],
        }
    )
    command = context["accepted_state"]["kill_switch"]["command"]
    for field in (
        "desired_state",
        "reason_code",
        "recovery_evidence_reference",
        "recovery_barrier_generation",
        "recovery_barrier_version",
        "recovery_barrier_checksum",
        "recovery_evidence_digest",
        "recovery_aggregate_evidence_digest",
    ):
        command[field] = payload[field]
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    payload["command_fingerprint"] = command["command_fingerprint"]
    checker = ControlSemanticValidator()
    checker.validate_control_message(
        _combined_fixture("system.kill_switch_changed.v1", payload), context
    )

    for event_field, value in (
        ("recovery_evidence_reference", "barrier-forged"),
        ("recovery_barrier_generation", 5),
        ("recovery_barrier_version", "barrier-v2"),
        ("recovery_barrier_checksum", "5" * 64),
        ("recovery_evidence_digest", "6" * 64),
        ("recovery_aggregate_evidence_digest", "7" * 64),
    ):
        invalid_payload = deepcopy(payload)
        invalid_context = deepcopy(context)
        invalid_payload[event_field] = value
        invalid_context["accepted_state"]["kill_switch"]["command"][event_field] = value
        invalid_context["accepted_state"]["kill_switch"]["command"]["command_fingerprint"] = _sha(
            _kill_command_fingerprint_projection(
                invalid_context["accepted_state"]["kill_switch"]["command"]
            )
        )
        invalid_payload["command_fingerprint"] = invalid_context["accepted_state"]["kill_switch"][
            "command"
        ]["command_fingerprint"]
        with pytest.raises(ValueError, match="accepted barrier"):
            checker.validate_control_message(
                _combined_fixture("system.kill_switch_changed.v1", invalid_payload),
                invalid_context,
            )

    for mutate in (
        lambda barrier: barrier.update({"state": "CLOSED"}),
        lambda barrier: barrier.update({"fresh_until": "2026-08-11T01:00:01Z"}),
        lambda barrier: barrier.update({"unexpected": True}),
        lambda barrier: barrier.pop("barrier_checksum"),
    ):
        invalid_context = deepcopy(context)
        mutate(invalid_context["accepted_recovery_barriers"]["barrier-1"])
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(
                _combined_fixture("system.kill_switch_changed.v1", payload), invalid_context
            )


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_combined_control_message_validator_binds_all_four_events(message_type: str) -> None:
    payload = _load(FIXTURES / "control-events.json")[message_type]
    message = _combined_fixture(message_type, payload)
    checker = ControlSemanticValidator()
    checker.validate_control_message(message, _validation_context(payload["correlation_id"]))
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
            checker.validate_control_message(
                invalid, _validation_context(payload["correlation_id"])
            )


def test_combined_message_rejects_sensitive_fields_and_lineage_errors() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    for _bad in ("message_id", "causation_id"):
        invalid = deepcopy(message)
        invalid["payload"]["secret"] = "do-not-log"
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(
                invalid, _validation_context(payload["correlation_id"])
            )
    invalid = deepcopy(message)
    invalid["causation_id"] = invalid["message_id"]
    invalid["payload"]["causation_id"] = invalid["message_id"]
    invalid["payload_fingerprint"] = _sha(invalid["payload"])
    with pytest.raises(ValueError, match="self"):
        checker.validate_control_message(invalid, _validation_context(payload["correlation_id"]))


def test_control_lineage_context_is_mandatory_and_collision_safe() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    with pytest.raises(ValueError, match="context"):
        checker.validate_control_message(message, {})
    empty = _validation_context(payload["correlation_id"])
    empty["known_messages"] = {}
    with pytest.raises(ValueError, match=r"context|unknown"):
        checker.validate_control_message(message, empty)
    unknown = _validation_context(payload["correlation_id"], parent="another-parent-0001")
    with pytest.raises(ValueError, match="unknown"):
        checker.validate_control_message(message, unknown)
    future = _validation_context(payload["correlation_id"])
    future["known_messages"]["parent-message-0001"]["sequence"] = message["aggregate_version"]
    with pytest.raises(ValueError, match="future"):
        checker.validate_control_message(message, future)
    time_regression = _validation_context(
        payload["correlation_id"], parent_time="2026-08-11T01:00:02Z"
    )
    with pytest.raises(ValueError, match="time"):
        checker.validate_control_message(message, time_regression)
    duplicate = _validation_context(payload["correlation_id"])
    duplicate["identity_history"][message["message_id"]] = {
        "fingerprint": message["payload_fingerprint"],
        "decision": "DUPLICATE",
    }
    assert checker.validate_control_message(message, duplicate)["status"] == "DUPLICATE"
    conflict = _validation_context(payload["correlation_id"])
    conflict["identity_history"][message["message_id"]] = {
        "fingerprint": "0" * 64,
        "decision": "CONFLICT",
    }
    with pytest.raises(ValueError, match="conflict"):
        checker.validate_control_message(message, conflict)
    rejected = _validation_context(payload["correlation_id"])
    rejected["identity_history"][message["message_id"]] = {
        "fingerprint": message["payload_fingerprint"],
        "decision": "REJECTED",
    }
    assert checker.validate_control_message(message, rejected)["status"] == "DUPLICATE"


def test_control_rfc8785_rejects_non_finite_and_unsafe_numbers() -> None:
    for value in (float("nan"), float("inf"), -float("inf"), SAFE_INTEGER_MAX + 1):
        with pytest.raises(ValueError):
            _canonical(value)
    assert _canonical({"𐀀": 1, "\ue000": 2}).decode("utf-8").startswith('{"𐀀":1')


def test_control_checksum_numeric_domain_rejects_nested_floats() -> None:
    candidate = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_CANDIDATE"
        )
    )
    candidate["payload"]["nested"] = {"unsafe_number": 1.25}
    assert not _validator("control/control-plane.v1.schema.json").is_valid(candidate)
    with pytest.raises(ValueError, match=r"integral|number domain|binary float"):
        _canonical({"payload": {"nested": [1.25]}})

    assert _canonical({"minimum": -SAFE_INTEGER_MAX, "maximum": SAFE_INTEGER_MAX})
    assert _canonical({"amount": "123.45"}) == _market_jcs({"amount": "123.45"}).encode("utf-8")


def test_control_checksum_integral_json_numbers_have_one_canonical_form() -> None:
    canonical = _canonical({"value": 1, "nested": [1, {"amount": "123.45"}]})
    for token in ("1", "1.0", "1e0"):
        parsed = _parse_json_exact(token)
        assert _canonical({"value": parsed, "nested": [parsed, {"amount": "123.45"}]}) == canonical

    for token in (
        "1.25",
        "1.0000000000000001",
        "1e-400",
        "9007199254740991.1",
        "1e400",
        "9007199254740992",
    ):
        value = _parse_json_exact(token)
        with pytest.raises(ValueError, match=r"number|integer|finite"):
            _canonical({"nested": [value]})
    for token in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match=r"non.finite|JSON number"):
            _parse_json_exact(token)
    for value in (-SAFE_INTEGER_MAX - 1, SAFE_INTEGER_MAX + 1):
        with pytest.raises(ValueError, match="safe integer"):
            _canonical({"nested": [value]})
    assert _canonical({"negative": _parse_json_exact("-1.0")}) == _canonical({"negative": -1})
    for direct_float in (1.0, 1.0000000000000001, 1e-400, float("nan"), float("inf")):
        with pytest.raises(ValueError, match=r"binary float|exact JSON"):
            _canonical({"nested": [{"value": direct_float}]})


def test_control_dtos_reject_arbitrary_and_high_cardinality_fields() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    validator = _validator("control/control-plane.v1.schema.json")
    for dto in document["dtos"]:
        invalid = deepcopy(dto)
        invalid["BOGUS"] = True
        assert not validator.is_valid(invalid)


def test_config_checksum_and_component_ack_binding_are_fail_closed() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["config.version_activated.v1"])
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    checker.validate_control_message(
        _combined_fixture("config.version_activated.v1", payload), context
    )
    for mutate in (
        lambda item: item["component_acks"].pop("OMS"),
        lambda item: item.update({"active_checksum": "0" * 64}),
    ):
        invalid = deepcopy(payload)
        mutate(invalid)
        invalid_message = _combined_fixture("config.version_activated.v1", invalid)
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(invalid_message, context)


def test_config_event_ack_mode_and_active_identity_bindings_are_fail_closed() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["config.version_activated.v1"])
    checker = ControlSemanticValidator()
    message = _combined_fixture("config.version_activated.v1", payload)
    context = _validation_context(payload["correlation_id"])
    checker.validate_control_message(message, context)
    for mutate in (
        lambda item: item["component_acks"]["OMS"].update({"activation_mode": "RESTART_REQUIRED"}),
        lambda item: item["component_acks"]["OMS"].update({"safe_boundary": "RESTART_ONLY"}),
        lambda item: item["component_acks"]["OMS"].update({"capability_version": ""}),
        lambda item: item["component_acks"]["OMS"].update({"generation": 0}),
        lambda item: item["component_acks"]["OMS"].update({"prepare_result": "PREPARED"}),
        lambda item: item.update({"active_version": "v1"}),
        lambda item: item.update({"active_checksum": "0" * 64}),
    ):
        invalid = deepcopy(payload)
        mutate(invalid)
        invalid_message = _combined_fixture("config.version_activated.v1", invalid)
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(invalid_message, context)


def test_config_authority_required_components_are_exact_and_versioned() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["config.version_activated.v1"])
    message = _combined_fixture("config.version_activated.v1", payload)
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    checker.validate_control_message(message, context)

    unknown_payload = deepcopy(payload)
    unknown_payload["required_components"].append("RISK")
    unknown_ack = deepcopy(unknown_payload["component_acks"]["RiskEngine"])
    unknown_ack["component_id"] = "RISK"
    unknown_payload["component_acks"]["RISK"] = unknown_ack
    with pytest.raises(ValueError, match="set mismatch"):
        checker.validate_control_message(
            _combined_fixture("config.version_activated.v1", unknown_payload), context
        )

    for mutate in (
        lambda config: config.pop("required_components"),
        lambda config: config["required_components"].append("OMS"),
        lambda config: config["components"].update(
            {
                "Unknown": {
                    "component_id": "Unknown",
                    "generation": 1,
                    "capability_version": "unknown-v1",
                    "activation_mode": "HOT_RELOAD",
                    "safe_boundary": "NEXT_ORDER_BOUNDARY",
                }
            }
        ),
        lambda config: config.update({"config_checksum": "0" * 64}),
        lambda config: config["components"]["OMS"].update({"capability_version": "oms-cap-v2"}),
    ):
        invalid_context = deepcopy(context)
        mutate(invalid_context["accepted_state"]["config"])
        with pytest.raises((ValueError, ValidationError)):
            checker.validate_control_message(message, invalid_context)


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


def test_recovery_passed_requires_an_open_verified_barrier() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    context.pop("accepted_recovery_barriers")

    with pytest.raises(ValueError, match="recovery barrier"):
        checker.validate_control_message(message, context)

    closed = deepcopy(context)
    closed["accepted_state"]["recovery_barrier"] = {
        "dto_type": "RECOVERY_BARRIER",
        "schema_version": 1,
        "correlation_id": payload["correlation_id"],
        "created_at": "2026-08-11T01:00:00Z",
        "barrier_id": "barrier-1",
        "state": "CLOSED",
        "generation": 1,
        "opened_at": None,
        "evidence": {},
        "required_evidence": [],
        "invalidation_reason": None,
    }
    with pytest.raises((ValueError, ValidationError), match=r"recovery barrier|evidence"):
        checker.validate_control_message(message, closed)


def test_open_recovery_barrier_requires_opened_at() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    barrier = deepcopy(
        next(item for item in document["dtos"] if item["dto_type"] == "RECOVERY_BARRIER")
    )
    barrier["state"] = "OPEN"
    barrier["opened_at"] = None
    assert not _validator("control/control-plane.v1.schema.json").is_valid(barrier)
    context = _validation_context("corr-mode-000001")
    context["accepted_recovery_barriers"]["barrier-1"]["opened_at"] = None
    with pytest.raises(ValidationError):
        _validator("control/validation-context.v1.schema.json").validate(context)


@pytest.mark.parametrize("dto_type", ["CONFIG_CANDIDATE", "KILL_SWITCH_COMMAND"])
def test_recovery_barrier_authority_embeds_only_recovery_barrier(dto_type: str) -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    context = _validation_context("corr-mode-000001")
    validator = _validator("control/validation-context.v1.schema.json")
    validator.validate(context)

    invalid = deepcopy(context)
    invalid["accepted_recovery_barriers"]["barrier-1"]["barrier"] = deepcopy(
        next(item for item in document["dtos"] if item["dto_type"] == dto_type)
    )
    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_kill_switch_authority_embeds_only_kill_switch_command() -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    context = _validation_context("corr-mode-000001")
    validator = _validator("control/validation-context.v1.schema.json")
    validator.validate(context)
    schema = _load(SCHEMAS / "control/validation-context.v1.schema.json")
    command_ref = schema["$defs"]["authority"]["properties"]["kill_switch"]["properties"][
        "command"
    ]["$ref"]
    assert command_ref == "urn:quantiqmt:contract:control-plane:v1#/$defs/killSwitchCommand"
    external_control_refs = []

    def collect_refs(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("urn:quantiqmt:contract:control-plane:v1"):
                external_control_refs.append(ref)
            for child in value.values():
                collect_refs(child)
        elif isinstance(value, list):
            for child in value:
                collect_refs(child)

    collect_refs(schema)
    assert set(external_control_refs) == {
        "urn:quantiqmt:contract:control-plane:v1#/$defs/killSwitchCommand",
        "urn:quantiqmt:contract:control-plane:v1#/$defs/recoveryBarrier",
    }

    for dto in document["dtos"]:
        if dto["dto_type"] == "KILL_SWITCH_COMMAND":
            continue
        invalid = deepcopy(context)
        invalid["accepted_state"]["kill_switch"]["command"] = deepcopy(dto)
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_same_identity_same_fingerprint_is_stable_duplicate_before_authority_checks() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    context = _validation_context(payload["correlation_id"])
    context["identity_history"][message["message_id"]] = {
        "fingerprint": message["payload_fingerprint"],
        "decision": "ACCEPTED",
    }
    context["accepted_policy"]["checksum"] = "0" * 64
    assert (
        ControlSemanticValidator().validate_control_message(message, context)["status"]
        == "DUPLICATE"
    )


def test_control_dispatch_includes_commands_and_all_side_effect_boundaries() -> None:
    document = yaml.safe_load(
        (ROOT / "spec/contracts/control/control-semantic-validation.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    contract = document["contract"]
    assert set(contract["boundaries"]) == {
        "schema_parse",
        "command_ingress",
        "envelope_publish",
        "outbox_persist",
        "event_publish",
        "consumer_apply",
        "command_dispatch",
        "control_transition",
        "state_transition",
        "recovery_restore",
        "external_side_effect",
    }
    assert {"CONFIG_CANDIDATE", "KILL_SWITCH_COMMAND", "KILL_SWITCH_RESULT"}.issubset(
        document["rules"]["event_specific_dispatch"]["exhaustive"]
    )
    kill_switch = document["rules"]["kill_switch"]
    assert kill_switch["result_identity"]["namespace"] == "KILL_SWITCH_RESULT"
    assert kill_switch["result_identity"]["identity_field"] == "result_id"
    assert kill_switch["result_identity"]["fingerprint_field"] == "result_fingerprint"
    assert kill_switch["command_identity"]["namespace"] == "KILL_SWITCH_COMMAND"
    assert kill_switch["command_result_identity"]["namespace"] == "KILL_SWITCH_COMMAND_RESULT"
    assert kill_switch["command_result_identity"]["atomic_registration"].endswith(
        "same_transaction"
    )


def test_config_candidate_checksum_covers_payload_boundary_and_hard_limit_policy() -> None:
    candidate = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_CANDIDATE"
        )
    )
    checker = ControlSemanticValidator()
    context = _validation_context(candidate["correlation_id"])
    checker.validate_control_message(candidate, context)
    for mutate in (
        lambda item: item["payload"].update({"rules": "tampered"}),
        lambda item: item.update({"safe_boundary": "RESTART_ONLY"}),
        lambda item: item.update({"system_hard_limit_policy_checksum": "0" * 64}),
    ):
        invalid = deepcopy(candidate)
        mutate(invalid)
        with pytest.raises((ValueError, ValidationError), match=r"checksum|authority|hard limit"):
            checker.validate_control_message(invalid, context)


def test_unified_dispatch_validates_kill_switch_command_dto() -> None:
    command = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "KILL_SWITCH_COMMAND"
        )
    )
    context = _validation_context(command["correlation_id"])
    context["accepted_state"]["kill_switch"]["current_version"] = command["expected_version"]
    context["accepted_state"]["kill_switch"]["command"] = deepcopy(command)
    ControlSemanticValidator().validate_control_message(command, context)


def test_kill_switch_outcome_binds_effect_and_reconciliation_identity() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.kill_switch_changed.v1"])
    schema = _validator(EVENT_SCHEMAS["system.kill_switch_changed.v1"])
    applied_wrong_effect = deepcopy(payload)
    applied_wrong_effect["effective_state"] = "OFF"
    assert not schema.is_valid(applied_wrong_effect)
    for outcome in ("TIMEOUT", "UNKNOWN"):
        invalid = deepcopy(payload)
        invalid.update(outcome=outcome, effective_state="UNKNOWN", reconciliation_required=False)
        assert not schema.is_valid(invalid)

    context = _validation_context(payload["correlation_id"])
    invalid = deepcopy(payload)
    invalid["idempotency_key"] = "different-kill-identity"
    with pytest.raises(ValueError, match=r"command binding|identity"):
        ControlSemanticValidator().validate_control_message(
            _combined_fixture("system.kill_switch_changed.v1", invalid), context
        )


def test_component_health_requires_authority_transition_and_reason_binding() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.component_health_changed.v1"]
    checker = ControlSemanticValidator()
    context = _validation_context(payload["correlation_id"])
    checker.validate_control_message(
        _combined_fixture("system.component_health_changed.v1", payload), context
    )
    for mutate in (
        lambda item: item.update({"previous_health": "RECOVERING"}),
        lambda item: item.update({"health": "HEALTHY"}),
        lambda item: item.update({"reason_code": "PROBE_PASSED"}),
    ):
        invalid = deepcopy(payload)
        mutate(invalid)
        with pytest.raises((ValueError, ValidationError), match=r"health|transition|reason"):
            checker.validate_control_message(
                _combined_fixture("system.component_health_changed.v1", invalid), context
            )


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_payload_causation_id_is_bound_to_envelope(message_type: str) -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")[message_type])
    message = _combined_fixture(message_type, payload)
    payload["causation_id"] = "other-parent-0001"
    message["payload"] = payload
    message["payload_fingerprint"] = _sha(payload)
    with pytest.raises((ValueError, ValidationError), match="causation"):
        ControlSemanticValidator().validate_control_message(
            message, _validation_context(payload["correlation_id"])
        )


def test_duplicate_fast_path_still_rejects_untrusted_event_content_and_bindings() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.mode_changed.v1"])
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()

    tampered = deepcopy(message)
    tampered["payload"]["evidence"]["recovery_barrier_id"] = "barrier-forged"
    duplicate = _validation_context(payload["correlation_id"])
    duplicate["identity_history"][message["message_id"]] = {
        "fingerprint": message["payload_fingerprint"],
        "decision": "ACCEPTED",
    }
    with pytest.raises(ValueError, match="fingerprint"):
        checker.validate_control_message(tampered, duplicate)

    misbound = deepcopy(message)
    misbound["payload"]["correlation_id"] = "other-correlation-0001"
    misbound["payload_fingerprint"] = _sha(misbound["payload"])
    duplicate["identity_history"][message["message_id"]]["fingerprint"] = misbound[
        "payload_fingerprint"
    ]
    with pytest.raises(ValueError, match="correlation"):
        checker.validate_control_message(misbound, duplicate)


@pytest.mark.parametrize("dto_type", ["CONFIG_CANDIDATE", "KILL_SWITCH_COMMAND"])
def test_duplicate_fast_path_recomputes_canonical_dto_fingerprint(dto_type: str) -> None:
    dto = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == dto_type
        )
    )
    fingerprint_field = (
        "candidate_checksum" if dto_type == "CONFIG_CANDIDATE" else "command_fingerprint"
    )
    identity_key = (
        dto["idempotency_key"] if dto_type == "CONFIG_CANDIDATE" else _kill_command_identity(dto)
    )
    context = _validation_context(dto["correlation_id"])
    context["identity_history"][identity_key] = {
        "fingerprint": dto[fingerprint_field],
        "decision": "ACCEPTED",
    }
    context["accepted_policy"]["checksum"] = "0" * 64
    assert (
        ControlSemanticValidator().validate_control_message(dto, context)["status"] == "DUPLICATE"
    )

    tampered = deepcopy(dto)
    if dto_type == "CONFIG_CANDIDATE":
        tampered["payload"]["rules"] = "tampered"
    else:
        tampered["actor"] = "forged-operator"
    with pytest.raises(ValueError, match=r"fingerprint|checksum"):
        ControlSemanticValidator().validate_control_message(tampered, context)

    conflicting = deepcopy(tampered)
    if dto_type == "CONFIG_CANDIDATE":
        conflicting[fingerprint_field] = _sha(_candidate_checksum_projection(conflicting, {}))
    else:
        conflicting[fingerprint_field] = _sha(_kill_command_fingerprint_projection(conflicting))
    with pytest.raises(ValueError, match="conflict"):
        ControlSemanticValidator().validate_control_message(conflicting, context)


def test_recovery_registry_uses_the_complete_barrier_validator() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    message = _combined_fixture("system.mode_changed.v1", payload)
    checker = ControlSemanticValidator()
    valid = _validation_context(payload["correlation_id"])
    valid["accepted_state"].pop("recovery_barrier", None)
    checker.validate_control_message(message, valid)

    stale = deepcopy(valid)
    stale["accepted_state"]["market"]["fresh_until"] = stale["evaluation_at"]
    stale["accepted_recovery_barriers"]["barrier-1"]["barrier"]["evidence"][
        "market_fresh_until"
    ] = stale["evaluation_at"]
    with pytest.raises(ValueError, match="stale"):
        checker.validate_control_message(message, stale)

    mutations = (
        lambda entry: entry["barrier"]["required_evidence"].remove("OUTBOX_HEALTHY"),
        lambda entry: entry["barrier"]["evidence"].update(
            {"market_fresh_until": "2026-08-11T01:00:01Z"}
        ),
        lambda entry: entry["barrier"]["evidence"].update({"config_checksum": "0" * 64}),
        lambda entry: entry["barrier"].update({"generation": entry["generation"] + 1}),
        lambda entry: entry.update({"aggregate_evidence_digest": "0" * 64}),
        lambda entry: entry.update({"fresh_until": "2026-08-11T01:00:01Z"}),
    )
    for mutate in mutations:
        invalid = deepcopy(valid)
        mutate(invalid["accepted_recovery_barriers"]["barrier-1"])
        with pytest.raises(
            (ValueError, ValidationError), match=r"barrier|evidence|fresh|config|generation|digest"
        ):
            checker.validate_control_message(message, invalid)


def test_kill_switch_off_command_uses_complete_recovery_barrier_authority() -> None:
    command = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "KILL_SWITCH_COMMAND"
        )
    )
    context = _validation_context(command["correlation_id"])
    barrier = context["accepted_recovery_barriers"]["barrier-1"]
    command.update(
        desired_state="OFF",
        reason_code="OPERATOR_RELEASE",
        recovery_evidence_reference="barrier-1",
        recovery_barrier_generation=barrier["generation"],
        recovery_barrier_version=barrier["barrier_version"],
        recovery_barrier_checksum=barrier["barrier_checksum"],
        recovery_evidence_digest=barrier["evidence_digest"],
        recovery_aggregate_evidence_digest=barrier["aggregate_evidence_digest"],
    )
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    context["accepted_state"]["kill_switch"]["command"] = {
        key: command[key] for key in context["accepted_state"]["kill_switch"]["command"]
    }
    context["accepted_state"]["kill_switch"]["current_version"] = command["expected_version"]
    context["accepted_recovery_barriers"] = {
        "barrier-1": _open_recovery_barrier_authority(context, command["correlation_id"])
    }
    ControlSemanticValidator().validate_control_message(command, context)

    for mutate in (
        lambda entry: entry["barrier"]["required_evidence"].remove("LEASE_FENCED"),
        lambda entry: entry["barrier"]["evidence"].update({"lease_epoch": 99}),
        lambda entry: entry.update({"authorization_checksum": "0" * 64}),
        lambda entry: entry.update({"policy_checksum": "0" * 64}),
        lambda entry: entry["barrier"]["evidence"].update({"observed_at": "2026-08-11T01:00:02Z"}),
        lambda entry: entry.update({"fresh_until": "2026-08-11T01:00:01Z"}),
    ):
        invalid = deepcopy(context)
        mutate(invalid["accepted_recovery_barriers"]["barrier-1"])
        with pytest.raises(
            (ValueError, ValidationError), match=r"barrier|lease|authorization|policy|future"
        ):
            ControlSemanticValidator().validate_control_message(command, invalid)


def test_config_checksum_is_single_source_deterministic_and_order_normalized() -> None:
    candidate = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_CANDIDATE"
        )
    )
    projection = _candidate_checksum_projection(candidate, {})
    assert candidate["candidate_checksum"] == _sha(projection)
    independent_ascii_jcs = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert candidate["candidate_checksum"] == hashlib.sha256(independent_ascii_jcs).hexdigest()
    reordered = deepcopy(candidate)
    reordered["secret_references"].append("secret://risk/secondary")
    expanded_checksum = _sha(_candidate_checksum_projection(reordered, {}))
    reordered["required_components"].reverse()
    reordered["secret_references"].reverse()
    assert _sha(_candidate_checksum_projection(reordered, {})) == expanded_checksum

    context = _validation_context(candidate["correlation_id"])
    authority = context["accepted_state"]["config"]
    candidate["secret_references"].append("secret://risk/secondary")
    authority["secret_references"].append("secret://risk/secondary")
    candidate["secret_references"].reverse()
    candidate["required_components"].reverse()
    candidate["candidate_checksum"] = _sha(_candidate_checksum_projection(candidate, {}))
    authority["config_checksum"] = candidate["candidate_checksum"]
    ControlSemanticValidator().validate_control_message(candidate, context)

    ordered_payload = deepcopy(candidate)
    ordered_payload["payload"]["priority"] = ["hard", "dynamic"]
    reversed_payload = deepcopy(ordered_payload)
    reversed_payload["payload"]["priority"].reverse()
    assert _sha(_candidate_checksum_projection(ordered_payload, {})) != _sha(
        _candidate_checksum_projection(reversed_payload, {})
    )

    for mutate in (
        lambda item: item["system_hard_limit_policy"]["limits"].update(
            {"maximum_order_notional": "1000001"}
        ),
        lambda item: item["dynamic_limits"].update({"maximum_order_notional": "1000001"}),
        lambda item: item["component_authority"]["OMS"].update({"generation": 99}),
        lambda item: item.update({"policy_checksum": "0" * 64}),
    ):
        tampered = deepcopy(candidate)
        mutate(tampered)
        assert _sha(_candidate_checksum_projection(tampered, {})) != candidate["candidate_checksum"]


def test_config_hard_limit_authority_rejects_currency_relaxation_and_hash_mismatch() -> None:
    candidate = deepcopy(
        next(
            item
            for item in _load(FIXTURES / "control-plane.v1/valid.json")["dtos"]
            if item["dto_type"] == "CONFIG_CANDIDATE"
        )
    )
    for mutate in (
        lambda item, authority: (
            item.update({"valuation_currency": "USD"}),
            authority.update({"valuation_currency": "USD"}),
        ),
        lambda item, authority: (
            item["dynamic_limits"].update({"maximum_order_notional": "1000001"}),
            authority["dynamic_limits"].update({"maximum_order_notional": "1000001"}),
        ),
        lambda item, authority: (
            item["system_hard_limit_policy"]["limits"].update({"maximum_order_notional": "999999"}),
            authority["system_hard_limit_policy"]["limits"].update(
                {"maximum_order_notional": "999999"}
            ),
        ),
        lambda item, authority: (
            item.update({"system_hard_limit_policy_checksum": "0" * 64}),
            authority.update({"system_hard_limit_policy_checksum": "0" * 64}),
        ),
    ):
        invalid = deepcopy(candidate)
        context = _validation_context(candidate["correlation_id"])
        authority = context["accepted_state"]["config"]
        mutate(invalid, authority)
        authority["config_checksum"] = _sha(_candidate_checksum_projection({}, authority))
        invalid["candidate_checksum"] = _sha(_candidate_checksum_projection(invalid, {}))
        with pytest.raises(ValueError, match=r"currency|limit|policy|authority"):
            ControlSemanticValidator().validate_control_message(invalid, context)


def test_config_event_binds_secret_references_and_all_candidate_security_fields() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["config.version_activated.v1"])
    context = _validation_context(payload["correlation_id"])
    payload["secret_references"] = ["secret://risk/forged"]
    with pytest.raises(ValueError, match=r"config|secret|authority"):
        ControlSemanticValidator().validate_control_message(
            _combined_fixture("config.version_activated.v1", payload), context
        )


@pytest.mark.parametrize(
    ("outcome", "effective_state", "current_version", "reconciliation_required", "ack_ids"),
    [
        ("APPLIED", "ON", 2, False, ["ack-kill-000001"]),
        ("REJECTED", "OFF", 1, False, []),
        ("PARTIAL", "ON", 1, True, ["ack-kill-000001"]),
        ("TIMEOUT", "UNKNOWN", 1, True, []),
        ("UNKNOWN", "UNKNOWN", 1, True, []),
    ],
)
def test_public_kill_switch_outcome_matrix(
    outcome: str,
    effective_state: str,
    current_version: int,
    reconciliation_required: bool,
    ack_ids: list[str],
) -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.kill_switch_changed.v1"])
    payload.update(
        outcome=outcome,
        effective_state=effective_state,
        current_version=current_version,
        reconciliation_required=reconciliation_required,
    )
    payload["effect_evidence"]["ack_ids"] = ack_ids
    context = _validation_context(payload["correlation_id"])
    if outcome == "PARTIAL":
        context["accepted_state"]["kill_switch"]["effect_ack_ids"] = [
            "ack-kill-000001",
            "ack-kill-000002",
        ]
    ControlSemanticValidator().validate_control_message(
        _combined_fixture("system.kill_switch_changed.v1", payload), context
    )
    for field, value in (
        ("current_version", current_version + 7),
        ("reconciliation_required", not reconciliation_required),
        ("restores_normal", True),
    ):
        invalid = deepcopy(payload)
        invalid[field] = value
        with pytest.raises((ValueError, ValidationError)):
            ControlSemanticValidator().validate_control_message(
                _combined_fixture("system.kill_switch_changed.v1", invalid), context
            )


def _prepared_kill_result(
    outcome: str = "APPLIED",
) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    result = deepcopy(
        next(item for item in document["dtos"] if item["dto_type"] == "KILL_SWITCH_RESULT")
    )
    command = deepcopy(
        next(item for item in document["dtos"] if item["dto_type"] == "KILL_SWITCH_COMMAND")
    )
    expected = {
        "APPLIED": ("ON", 3, False, "2026-08-11T01:00:00Z", ["ack-kill-000001", "ack-kill-000002"]),
        "REJECTED": ("OFF", 2, False, None, []),
        "PARTIAL": ("ON", 2, True, None, ["ack-kill-000001"]),
        "TIMEOUT": ("UNKNOWN", 2, True, None, []),
        "UNKNOWN": ("UNKNOWN", 2, True, None, []),
    }[outcome]
    result.update(
        result_id=f"kill-result-{outcome.lower()}-0001",
        result_fingerprint="0" * 64,
        outcome=outcome,
        effective_state=expected[0],
        current_version=expected[1],
        reconciliation_required=expected[2],
        applied_at=expected[3],
        effect_evidence={
            "ack_ids": expected[4],
            "observed_at": "2026-08-11T01:00:00Z",
        },
    )
    context = _validation_context(result["correlation_id"])
    command["correlation_id"] = result["correlation_id"]
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    result["command_fingerprint"] = command["command_fingerprint"]
    result["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(result))
    context["accepted_state"]["kill_switch"].update(
        current_version=2,
        effective_state="OFF",
        command=command,
        effect_ack_ids=["ack-kill-000001", "ack-kill-000002"],
    )
    return result, context


def _expected_command_result_identity(result: dict[str, Any]) -> str:
    projection = {
        "command_id": result["command_id"],
        "idempotency_key": result["idempotency_key"],
        "scope": result["scope"],
    }
    expected = f"KILL_SWITCH_COMMAND_RESULT:{_sha(projection)}"
    assert _kill_command_result_identity(result) == expected
    return expected


def _record_kill_result(context: dict[str, Any], result: dict[str, Any]) -> None:
    command = context["accepted_state"]["kill_switch"]["command"]
    command_identity = _kill_command_identity(command)
    result_identity = _kill_result_identity(result)
    command_result_identity = _expected_command_result_identity(result)
    context["identity_history"][command_identity] = {
        "record_type": "KILL_SWITCH_COMMAND",
        "fingerprint": command["command_fingerprint"],
        "decision": "ACCEPTED",
        "command_identity": command_identity,
        "command_id": command["command_id"],
        "command_idempotency_key": command["idempotency_key"],
        "command_scope": command["scope"],
        "command_fingerprint": command["command_fingerprint"],
    }
    common = {
        "fingerprint": result["result_fingerprint"],
        "decision": "ACCEPTED",
        "command_identity": command_identity,
        "command_id": result["command_id"],
        "command_idempotency_key": result["idempotency_key"],
        "command_scope": result["scope"],
        "command_fingerprint": result["command_fingerprint"],
        "result_identity": result_identity,
        "result_id": result["result_id"],
        "result_fingerprint": result["result_fingerprint"],
        "command_result_identity": command_result_identity,
    }
    context["identity_history"][result_identity] = {
        **deepcopy(common),
        "record_type": "KILL_SWITCH_RESULT",
    }
    context["identity_history"][command_result_identity] = {
        **deepcopy(common),
        "record_type": "KILL_SWITCH_COMMAND_RESULT",
    }


def test_kill_result_uses_independent_identity_and_canonical_fingerprint() -> None:
    result, context = _prepared_kill_result()
    context["identity_history"][f"KILL_SWITCH_COMMAND:{result['command_id']}"] = {
        "fingerprint": result["command_fingerprint"],
        "decision": "ACCEPTED",
    }
    checker = ControlSemanticValidator()
    assert checker.validate_control_message(result, context)["status"] == "ACCEPTED"

    duplicate = deepcopy(context)
    _record_kill_result(duplicate, result)
    duplicate["accepted_state"]["kill_switch"]["current_version"] = 99
    assert checker.validate_control_message(result, duplicate)["status"] == "DUPLICATE"

    forged_command = deepcopy(duplicate)
    forged_command["accepted_state"]["kill_switch"]["command"]["actor"] = "forged-operator"
    assert checker.validate_control_message(result, forged_command)["status"] == "DUPLICATE"

    forged_history = deepcopy(duplicate)
    forged_history["identity_history"][
        _kill_command_identity(forged_history["accepted_state"]["kill_switch"]["command"])
    ]["command_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match=r"command history|registry"):
        checker.validate_control_message(result, forged_history)

    tamper_mutations = (
        lambda item: item.update({"idempotency_key": "idem-kill-forged-01"}),
        lambda item: item.update(
            {
                "outcome": "UNKNOWN",
                "effective_state": "UNKNOWN",
                "current_version": 2,
                "applied_at": None,
                "reconciliation_required": True,
                "effect_evidence": {
                    "ack_ids": [],
                    "observed_at": "2026-08-11T01:00:00Z",
                },
            }
        ),
        lambda item: item.update({"previous_version": 8, "current_version": 9}),
        lambda item: item.update({"authorization_id": "forged-authorization"}),
        lambda item: item.update({"leader_lease_id": "forged-lease"}),
        lambda item: item["effect_evidence"].update({"ack_ids": ["forged-ack"]}),
    )
    for mutate in tamper_mutations:
        tampered = deepcopy(result)
        mutate(tampered)
        with pytest.raises(ValueError, match="result fingerprint"):
            checker.validate_control_message(tampered, duplicate)

    conflict = deepcopy(result)
    conflict["effect_evidence"]["ack_ids"] = ["forged-ack"]
    conflict["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(conflict))
    with pytest.raises(ValueError, match="conflict"):
        checker.validate_control_message(conflict, duplicate)


def test_one_command_identity_cannot_accept_a_second_kill_result() -> None:
    rejected, context = _prepared_kill_result("REJECTED")
    _record_kill_result(context, rejected)
    checker = ControlSemanticValidator()
    assert checker.validate_control_message(rejected, context)["status"] == "DUPLICATE"

    for missing_key in (
        f"KILL_SWITCH_RESULT:{rejected['result_id']}",
        _expected_command_result_identity(rejected),
    ):
        incomplete_restore = deepcopy(context)
        incomplete_restore["identity_history"].pop(missing_key)
        with pytest.raises(ValueError, match=r"atomically|orphan|restore"):
            checker.validate_control_message(rejected, incomplete_restore)
    divergent_restore = deepcopy(context)
    divergent_restore["identity_history"][f"KILL_SWITCH_RESULT:{rejected['result_id']}"][
        "decision"
    ] = "UNKNOWN"
    with pytest.raises(ValueError, match=r"atomically|restore|registry|backlink"):
        checker.validate_control_message(rejected, divergent_restore)

    same_result_new_id = deepcopy(rejected)
    same_result_new_id["result_id"] = "kill-result-rejected-0002"
    same_result_new_id["result_fingerprint"] = _sha(
        _kill_result_fingerprint_projection(same_result_new_id)
    )
    with pytest.raises(ValueError, match=r"command.result|conflict|identity"):
        checker.validate_control_message(same_result_new_id, context)

    contradictory = deepcopy(rejected)
    contradictory.update(
        result_id="kill-result-unknown-0002",
        outcome="UNKNOWN",
        effective_state="UNKNOWN",
        current_version=contradictory["previous_version"],
        reconciliation_required=True,
    )
    contradictory["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(contradictory))
    with pytest.raises(ValueError, match=r"command.result|conflict|identity"):
        checker.validate_control_message(contradictory, context)


def test_kill_command_result_namespaces_resist_external_prefix_collision() -> None:
    result, context = _prepared_kill_result()
    command = context["accepted_state"]["kill_switch"]["command"]
    result_id = "shared-kill-identity-0001"
    command["command_id"] = f"KILL_SWITCH_RESULT:{result_id}"
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    result.update(
        result_id=result_id,
        command_id=command["command_id"],
        command_fingerprint=command["command_fingerprint"],
    )
    result["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(result))
    context["identity_history"][f"KILL_SWITCH_COMMAND:{command['command_id']}"] = {
        "fingerprint": command["command_fingerprint"],
        "decision": "ACCEPTED",
    }
    _record_kill_result(context, result)
    context["accepted_state"]["kill_switch"]["current_version"] = 99

    checker = ControlSemanticValidator()
    assert checker.validate_control_message(command, context)["status"] == "DUPLICATE"
    assert checker.validate_control_message(result, context)["status"] == "DUPLICATE"

    same_raw_result, same_raw_context = _prepared_kill_result()
    same_raw_command = same_raw_context["accepted_state"]["kill_switch"]["command"]
    shared_raw_id = "shared-raw-kill-id-0001"
    same_raw_command["command_id"] = shared_raw_id
    same_raw_command["command_fingerprint"] = _sha(
        _kill_command_fingerprint_projection(same_raw_command)
    )
    same_raw_result.update(
        result_id=shared_raw_id,
        command_id=shared_raw_id,
        command_fingerprint=same_raw_command["command_fingerprint"],
    )
    same_raw_result["result_fingerprint"] = _sha(
        _kill_result_fingerprint_projection(same_raw_result)
    )
    same_raw_context["identity_history"][_kill_command_identity(same_raw_command)] = {
        "fingerprint": same_raw_command["command_fingerprint"],
        "decision": "ACCEPTED",
    }
    _record_kill_result(same_raw_context, same_raw_result)
    same_raw_context["accepted_state"]["kill_switch"]["current_version"] = 99
    assert checker.validate_control_message(same_raw_command, same_raw_context)["status"] == (
        "DUPLICATE"
    )
    assert checker.validate_control_message(same_raw_result, same_raw_context)["status"] == (
        "DUPLICATE"
    )


def test_utc_instant_comparison_handles_fraction_offsets_and_invalid_values() -> None:
    assert _canonical_utc_z("2026-08-11T09:00:01+08:00") == "2026-08-11T01:00:01Z"
    assert _utc_instant("2026-08-11T01:00:01Z") == _utc_instant(
        _canonical_utc_z("2026-08-11T09:00:01+08:00")
    )
    assert _utc_instant("2026-08-11T01:00:00.999999Z") < _utc_instant("2026-08-11T01:00:01Z")
    for value in (
        "2026-08-11T01:00:01",
        "2026-08-11 01:00:01Z",
        "2026-08-11T01:00:01-00:00",
        "2026-08-11T09:00:01+08:00",
        "2026-08-11T01:00:01.0000001Z",
        "2026-08-11T01:00:60Z",
        "not-a-time",
    ):
        with pytest.raises(ValueError, match=r"RFC3339|UTC|instant"):
            _utc_instant(value)


def test_fractional_future_effect_and_expired_deadline_are_rejected() -> None:
    equivalent, equivalent_context = _prepared_kill_result()
    equivalent["effect_evidence"]["observed_at"] = _canonical_utc_z("2026-08-11T09:00:01+08:00")
    equivalent["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(equivalent))
    equivalent_context["evaluation_at"] = "2026-08-11T01:00:01Z"
    ControlSemanticValidator().validate_control_message(equivalent, equivalent_context)

    result, context = _prepared_kill_result()
    context["evaluation_at"] = "2026-08-11T01:00:01Z"
    result["effect_evidence"]["observed_at"] = "2026-08-11T01:00:01.1Z"
    result["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(result))
    with pytest.raises(ValueError, match="future"):
        ControlSemanticValidator().validate_control_message(result, context)

    command = context["accepted_state"]["kill_switch"]["command"]
    command["deadline_at"] = "2026-08-11T01:00:01Z"
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    context["evaluation_at"] = "2026-08-11T01:00:01.1Z"
    with pytest.raises(ValueError, match="deadline"):
        ControlSemanticValidator().validate_control_message(command, context)


def test_fractional_future_config_ack_is_rejected() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["config.version_activated.v1"])
    payload["component_acks"]["OMS"]["observed_at"] = "2026-08-11T01:00:01.1Z"
    context = _validation_context(payload["correlation_id"])
    context["evaluation_at"] = "2026-08-11T01:00:01Z"
    with pytest.raises(ValueError, match=r"acknowledgement.*future|future.*acknowledgement"):
        ControlSemanticValidator().validate_control_message(
            _combined_fixture("config.version_activated.v1", payload), context
        )


def test_recovery_barrier_fractional_future_is_rejected_for_restore_and_off() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.mode_changed.v1"])
    context = _validation_context(payload["correlation_id"])
    context["evaluation_at"] = "2026-08-11T01:00:01Z"
    barrier = deepcopy(context["accepted_recovery_barriers"]["barrier-1"]["barrier"])
    barrier["evidence"]["observed_at"] = "2026-08-11T01:00:01.1Z"
    entry = _recovery_barrier_authority(context, barrier)
    context["accepted_recovery_barriers"] = {"barrier-1": entry}
    with pytest.raises(ValueError, match="future"):
        ControlSemanticValidator().validate_control_message(
            _combined_fixture("system.mode_changed.v1", payload), context
        )

    command = deepcopy(context["accepted_state"]["kill_switch"]["command"])
    command.update(
        desired_state="OFF",
        reason_code="OPERATOR_RELEASE",
        recovery_evidence_reference="barrier-1",
        recovery_barrier_generation=entry["generation"],
        recovery_barrier_version=entry["barrier_version"],
        recovery_barrier_checksum=entry["barrier_checksum"],
        recovery_evidence_digest=entry["evidence_digest"],
        recovery_aggregate_evidence_digest=entry["aggregate_evidence_digest"],
    )
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    context["accepted_state"]["kill_switch"]["command"] = command
    with pytest.raises(ValueError, match="future"):
        ControlSemanticValidator().validate_control_message(command, context)


@pytest.mark.parametrize("expired_authority", ["freshness", "lease"])
def test_fractional_evaluation_rejects_expired_barrier_authority(
    expired_authority: str,
) -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.mode_changed.v1"])
    context = _validation_context(payload["correlation_id"])
    context["evaluation_at"] = "2026-08-11T01:00:01.1Z"
    if expired_authority == "freshness":
        context["accepted_state"]["market"]["fresh_until"] = "2026-08-11T01:00:01Z"
    else:
        context["accepted_state"]["lease"]["expires_at"] = "2026-08-11T01:00:01Z"
    context["accepted_recovery_barriers"] = {
        "barrier-1": _open_recovery_barrier_authority(context, payload["correlation_id"])
    }
    with pytest.raises(ValueError, match=r"stale|expired"):
        ControlSemanticValidator().validate_control_message(
            _combined_fixture("system.mode_changed.v1", payload), context
        )


@pytest.mark.parametrize(
    "outcome",
    ["APPLIED", "REJECTED", "PARTIAL", "TIMEOUT", "UNKNOWN"],
)
def test_internal_kill_switch_result_outcome_and_effect_matrix(outcome: str) -> None:
    result, context = _prepared_kill_result(outcome)
    ControlSemanticValidator().validate_control_message(result, context)

    invalid_ack_sets = {
        "APPLIED": [[], ["ack-kill-000001"], ["forged-ack"]],
        "REJECTED": [["ack-kill-000001"], ["forged-ack"]],
        "PARTIAL": [
            ["ack-kill-000001", "ack-kill-000002"],
            ["ack-kill-000001", "forged-ack"],
        ],
        "TIMEOUT": [
            ["ack-kill-000001", "ack-kill-000002"],
            ["forged-ack"],
        ],
        "UNKNOWN": [
            ["ack-kill-000001", "ack-kill-000002"],
            ["forged-ack"],
        ],
    }[outcome]
    for ack_ids in invalid_ack_sets:
        invalid = deepcopy(result)
        invalid["effect_evidence"]["ack_ids"] = ack_ids
        invalid["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(invalid))
        with pytest.raises((ValueError, ValidationError), match=r"effect|ack|outcome"):
            ControlSemanticValidator().validate_control_message(invalid, context)

    invalid_version = deepcopy(result)
    invalid_version["current_version"] += 5
    invalid_version["result_fingerprint"] = _sha(
        _kill_result_fingerprint_projection(invalid_version)
    )
    with pytest.raises((ValueError, ValidationError), match=r"outcome|version"):
        ControlSemanticValidator().validate_control_message(invalid_version, context)


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_public_control_causation_length_matches_envelope(message_type: str) -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")[message_type])
    payload["causation_id"] = "c" * 64
    assert _validator(EVENT_SCHEMAS[message_type]).is_valid(payload)
    message = _combined_fixture(message_type, payload)
    message["causation_id"] = payload["causation_id"]
    assert _validator("control/combined-control-message.v1.schema.json").is_valid(message)

    payload["causation_id"] = "c" * 65
    assert not _validator(EVENT_SCHEMAS[message_type]).is_valid(payload)
    message = _combined_fixture(message_type, payload)
    message["causation_id"] = payload["causation_id"]
    assert not _validator("control/combined-control-message.v1.schema.json").is_valid(message)


def test_task022_verification_evidence_does_not_claim_full_suite_passed() -> None:
    task = (ROOT / "tasks/active/TASK-022-observability-control-contracts.md").read_text(
        encoding="utf-8"
    )
    assert "passes 563 tests" not in task
    assert "6 failed" in task
    assert "4 errors" in task
    assert "22 control-contract failures" in task
    assert "2026-08-13" in task
    assert "acceptance_status: partial" in task
    assert "review_status: pending" in task
    assert "release_status: prohibited" in task


def _advance_current_kill_command(context: dict[str, Any]) -> None:
    command = deepcopy(context["accepted_state"]["kill_switch"]["command"])
    command.update(
        command_id="command-kill-next-0002",
        idempotency_key="idem-kill-next-0002",
        created_at="2026-08-11T01:00:01Z",
    )
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    context["accepted_state"]["kill_switch"]["command"] = command


def test_result_registry_global_audit_rejects_orphans_before_new_result() -> None:
    old_result, complete = _prepared_kill_result("REJECTED")
    _record_kill_result(complete, old_result)
    command_result_key = _expected_command_result_identity(old_result)
    checker = ControlSemanticValidator()

    result_only = deepcopy(complete)
    result_only["identity_history"].pop(command_result_key)
    for outcome in ("REJECTED", "UNKNOWN"):
        new_result = deepcopy(old_result)
        new_result["result_id"] = f"kill-result-new-{outcome.lower()}-0002"
        if outcome == "UNKNOWN":
            new_result.update(
                outcome="UNKNOWN",
                effective_state="UNKNOWN",
                current_version=new_result["previous_version"],
                reconciliation_required=True,
            )
        new_result["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(new_result))
        with pytest.raises(ValueError, match=r"registry|orphan|restore|atomic"):
            checker.validate_control_message(new_result, result_only)

    command_result_only = deepcopy(complete)
    command_result_only["identity_history"].pop(_kill_result_identity(old_result))
    with pytest.raises(ValueError, match=r"registry|orphan|restore|atomic"):
        checker.validate_control_message(old_result, command_result_only)

    missing_command_history = deepcopy(complete)
    missing_command_history["identity_history"].pop(
        f"KILL_SWITCH_COMMAND:{old_result['command_id']}"
    )
    with pytest.raises(ValueError, match=r"command history|registry|restore"):
        checker.validate_control_message(old_result, missing_command_history)


def test_result_registry_global_audit_rejects_wrong_backlinks_and_multiple_results() -> None:
    result, context = _prepared_kill_result("REJECTED")
    _record_kill_result(context, result)
    checker = ControlSemanticValidator()
    assert checker.validate_control_message(result, context)["status"] == "DUPLICATE"

    wrong_backlink = deepcopy(context)
    wrong_backlink["identity_history"][_expected_command_result_identity(result)][
        "result_identity"
    ] = "KILL_SWITCH_RESULT:wrong-backlink-result"
    with pytest.raises(ValueError, match=r"registry|backlink|pointer|restore"):
        checker.validate_control_message(result, wrong_backlink)

    multiple = deepcopy(context)
    second = deepcopy(result)
    second["result_id"] = "kill-result-rejected-0002"
    second["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(second))
    _record_kill_result(multiple, second)
    with pytest.raises(ValueError, match=r"registry|multiple|unique|cardinality|restore"):
        checker.validate_control_message(second, multiple)


def test_trusted_late_result_duplicate_uses_immutable_command_history() -> None:
    result, context = _prepared_kill_result("APPLIED")
    _record_kill_result(context, result)
    _advance_current_kill_command(context)
    checker = ControlSemanticValidator()

    assert checker.validate_control_message(result, context)["status"] == "DUPLICATE"

    tampered = deepcopy(result)
    tampered.update(
        outcome="UNKNOWN",
        effective_state="UNKNOWN",
        current_version=tampered["previous_version"],
        applied_at=None,
        reconciliation_required=True,
        effect_evidence={"ack_ids": [], "observed_at": "2026-08-11T01:00:00Z"},
    )
    tampered["result_fingerprint"] = _sha(_kill_result_fingerprint_projection(tampered))
    with pytest.raises(ValueError, match=r"fingerprint|conflict|registry"):
        checker.validate_control_message(tampered, context)

    first_late_result, first_context = _prepared_kill_result("APPLIED")
    _advance_current_kill_command(first_context)
    with pytest.raises(ValueError, match=r"command identity|authority"):
        checker.validate_control_message(first_late_result, first_context)


def test_control_timestamp_wire_boundary_requires_canonical_utc_z() -> None:
    payload = deepcopy(_load(FIXTURES / "control-events.json")["system.mode_changed.v1"])
    for invalid_timestamp in (
        "2026-08-11T09:00:01+08:00",
        "2026-08-11T01:00:01",
        "2026-08-11T01:00:01.0000001Z",
        "2026-08-11T01:00:60Z",
    ):
        invalid = deepcopy(payload)
        invalid["occurred_at"] = invalid_timestamp
        assert not _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(invalid)
        assert not _validator("control/combined-control-message.v1.schema.json").is_valid(
            _combined_fixture("system.mode_changed.v1", invalid)
        )

    normalized = deepcopy(payload)
    normalized["occurred_at"] = _canonical_utc_z("2026-08-11T09:00:01+08:00")
    assert normalized["occurred_at"] == "2026-08-11T01:00:01Z"
    assert _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(normalized)
    fractional = deepcopy(payload)
    fractional["occurred_at"] = "2026-08-11T01:00:01.123456Z"
    assert _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(fractional)

    command = deepcopy(_validation_context(payload["correlation_id"])["accepted_state"])[
        "kill_switch"
    ]["command"]
    command["deadline_at"] = "2026-08-11T09:01:00+08:00"
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    assert not _validator("control/control-plane.v1.schema.json").is_valid(command)
    command["deadline_at"] = "2026-08-11T01:01:00.0000001Z"
    command["command_fingerprint"] = _sha(_kill_command_fingerprint_projection(command))
    assert not _validator("control/control-plane.v1.schema.json").is_valid(command)

    context = _validation_context(payload["correlation_id"])
    context["evaluation_at"] = "2026-08-11T09:00:01+08:00"
    assert not _validator("control/validation-context.v1.schema.json").is_valid(context)
    context["evaluation_at"] = "2026-08-11T01:00:01.0000001Z"
    assert not _validator("control/validation-context.v1.schema.json").is_valid(context)


def test_all_control_timestamp_schemas_share_the_canonical_utc_z_pattern() -> None:
    schemas = (
        "common/message-envelope.v1.schema.json",
        *EVENT_SCHEMAS.values(),
        "control/control-plane.v1.schema.json",
        "control/validation-context.v1.schema.json",
        "control/combined-control-message.v1.schema.json",
    )

    def timestamp_nodes(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            nodes = [value] if value.get("format") == "date-time" else []
            return nodes + [node for child in value.values() for node in timestamp_nodes(child)]
        if isinstance(value, list):
            return [node for child in value for node in timestamp_nodes(child)]
        return []

    for relative in schemas:
        nodes = timestamp_nodes(_load(SCHEMAS / relative))
        if relative != "control/combined-control-message.v1.schema.json":
            assert nodes, relative
        assert all(node.get("pattern") == RFC3339_UTC_Z.pattern for node in nodes), relative
