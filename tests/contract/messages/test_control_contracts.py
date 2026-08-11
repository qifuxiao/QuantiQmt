from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "spec" / "contracts"
FIXTURES = Path(__file__).with_name("fixtures")
EVENT_SCHEMAS = {
    "system.mode_changed.v1": "events/system.mode_changed.v1.schema.json",
    "system.component_health_changed.v1": "events/system.component_health_changed.v1.schema.json",
    "system.kill_switch_changed.v1": "events/system.kill_switch_changed.v1.schema.json",
    "config.version_activated.v1": "events/config.version_activated.v1.schema.json",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(relative: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_control_semantics(dto: dict[str, Any]) -> None:
    dto_type = dto["dto_type"]
    if dto_type == "OBSERVABILITY_CONTEXT":
        forbidden = {"secret", "credential", "password", "access_token", "private_key"}
        if dto["redaction_policy"] != "NO_SECRETS_OR_CREDENTIALS":
            raise ValueError("redaction policy is not fail-closed")
        redacted = {key: value for key, value in dto.items() if key != "redaction_policy"}
        if any(token in json.dumps(redacted).lower() for token in forbidden):
            raise ValueError("sensitive value in observability context")
    elif dto_type == "ALERT_DEFINITION":
        if any(
            field in {"order_id", "trade_id", "instrument_id", "account_id"}
            for field in dto["evidence_fields"]
        ):
            raise ValueError("high-cardinality alert evidence")
        if dto["severity"] in {"P0", "P1"} and not dto["runbook_uri"].startswith("runbook://"):
            raise ValueError("critical alert requires runbook")
    elif dto_type == "CONFIG_CANDIDATE":
        if any(not ref.startswith("secret://") for ref in dto["secret_references"]):
            raise ValueError("plaintext secret reference")
        if dto["activation_mode"] == "RESTART_REQUIRED" and dto["safe_boundary"] != "RESTART_ONLY":
            raise ValueError("restart-required config has unsafe boundary")
        if not dto["system_hard_limit_policy_checksum"]:
            raise ValueError("hard limit policy binding missing")
    elif dto_type == "CONFIG_ACTIVATION_RESULT":
        acks = set(dto["component_acks"].values())
        if dto["outcome"] == "APPLIED" and (
            acks != {"APPLIED"}
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
        if not dto["authorization_evidence"]["approver_ids"]:
            raise ValueError("kill switch authorization missing")
        if dto["reserved_capacity"]["cancel"] < 1 or dto["reserved_capacity"]["recovery"] < 1:
            raise ValueError("kill switch reserved capacity missing")
    elif dto_type == "KILL_SWITCH_RESULT":
        if dto["outcome"] == "APPLIED" and dto["effective_state"] == "UNKNOWN":
            raise ValueError("applied kill switch cannot be unknown")
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


def _validate_envelope_payload_binding(envelope: dict[str, Any]) -> None:
    payload = envelope["payload"]
    if envelope["message_type"] != "system.mode_changed.v1" or envelope["schema_version"] != 1:
        raise ValueError("envelope message binding mismatch")
    if (
        envelope["source"] != payload["source"]
        or envelope["aggregate_version"] != payload["aggregate_version"]
    ):
        raise ValueError("envelope payload binding mismatch")
    if envelope["idempotency_key"] != payload["event_id"]:
        raise ValueError("envelope identity binding mismatch")


def test_control_dtos_are_schema_and_semantic_valid() -> None:
    validator = _validator("control/control-plane.v1.schema.json")
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    for dto in document["dtos"]:
        validator.validate(dto)
        _validate_control_semantics(dto)


@pytest.mark.parametrize(
    "case", _load(FIXTURES / "control-plane.v1/invalid.json")["cases"], ids=lambda c: c["name"]
)
def test_control_semantic_invalid_matrix_is_fail_closed(case: dict[str, Any]) -> None:
    document = _load(FIXTURES / "control-plane.v1/valid.json")
    dto = deepcopy(next(item for item in document["dtos"] if item["dto_type"] == case["dto_type"]))
    dto[case["field"]] = case["value"]
    validator = _validator("control/control-plane.v1.schema.json")
    if validator.is_valid(dto):
        with pytest.raises(ValueError):
            _validate_control_semantics(dto)


@pytest.mark.parametrize("message_type", list(EVENT_SCHEMAS))
def test_control_public_events_have_registered_schema_and_valid_fixture(message_type: str) -> None:
    payload = _load(FIXTURES / "control-events.json")[message_type]
    validator = _validator(EVENT_SCHEMAS[message_type])
    validator.validate(payload)
    assert payload["source"] in {"TradingCore", "HealthService", "ControlPlane", "ConfigService"}


def test_control_events_reject_additional_properties_and_invalid_transitions() -> None:
    fixtures = _load(FIXTURES / "control-events.json")
    mode = deepcopy(fixtures["system.mode_changed.v1"])
    mode["unexpected"] = True
    assert not _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(mode)
    mode = deepcopy(fixtures["system.mode_changed.v1"])
    mode.update(from_mode="NORMAL", to_mode="HALTED", reason_code="SAFETY_UNCERTAIN")
    assert not _validator(EVENT_SCHEMAS["system.mode_changed.v1"]).is_valid(mode)


def test_control_event_envelope_binding_and_collision_are_fail_closed() -> None:
    payload = _load(FIXTURES / "control-events.json")["system.mode_changed.v1"]
    envelope = {
        "message_type": "system.mode_changed.v1",
        "schema_version": 1,
        "source": "TradingCore",
        "partition_key": "core",
        "aggregate_id": payload["system_id"],
        "aggregate_version": payload["aggregate_version"],
        "idempotency_key": payload["event_id"],
        "payload": payload,
    }
    _validate_envelope_payload_binding(envelope)
    collision = deepcopy(envelope)
    collision["payload"] = dict(payload, reason_code="PARTIAL_AVAILABILITY")
    assert collision["idempotency_key"] == envelope["idempotency_key"]
    assert collision["payload"] != envelope["payload"]
    with pytest.raises(ValueError, match="collision"):
        if (
            collision["payload"] != envelope["payload"]
            and collision["idempotency_key"] == envelope["idempotency_key"]
        ):
            raise ValueError("identity collision")


def test_manifest_and_nfr_register_control_contracts_and_forbid_high_cardinality_labels() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["specification"]["version"] == "0.11.0"
    assert manifest["change"]["previous_version"] == "0.10.0"
    catalog_text = (ROOT / "spec/contracts/catalog.yaml").read_text(encoding="utf-8")
    for message_type in EVENT_SCHEMAS:
        assert f"name: {message_type}" in catalog_text
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
    assert workflow["recovery_barrier"]["initial"] == "CLOSED"
    machine = yaml.safe_load(
        (ROOT / "spec/state-machines/system-mode.yaml").read_text(encoding="utf-8")
    )["machine"]
    assert machine["control_guards"]["stale_lease_or_fencing_token"] == "reject_without_side_effect"
    assert "dependency reconnect alone never restores NORMAL" in machine["invariants"]
