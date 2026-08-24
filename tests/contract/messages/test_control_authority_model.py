from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec"
CONTROL = SPEC / "contracts" / "control"
EVENTS = SPEC / "contracts" / "events"


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def _catalog_internal_ids() -> set[str]:
    catalog = _yaml(SPEC / "contracts" / "catalog.yaml")
    return {item["id"] for item in catalog["internal_contracts"]}


def _manifest_contract_ids() -> set[str]:
    manifest = _yaml(SPEC / "manifest.yaml")
    return {item["id"] for item in manifest["catalogs"]["contracts"]}


def test_obsolete_control_context_contract_is_removed() -> None:
    assert {path.name for path in CONTROL.iterdir()} == {
        "combined-control-message.v1.schema.json",
        "control-plane.v1.schema.json",
        "control-semantic-validation.v1.yaml",
    }
    expected = {
        "CONTRACT-CONTROL-PLANE-V1",
        "CONTRACT-CONTROL-SEMANTIC-VALIDATION-V1",
        "CONTRACT-CONTROL-COMBINED-MESSAGE-V1",
    }
    assert {
        value for value in _catalog_internal_ids() if value.startswith("CONTRACT-CONTROL-")
    } == expected
    assert {
        value for value in _manifest_contract_ids() if value.startswith("CONTRACT-CONTROL-")
    } == expected


def test_combined_control_message_is_a_canonical_envelope_refinement() -> None:
    schema = _json(CONTROL / "combined-control-message.v1.schema.json")
    encoded = json.dumps(schema, sort_keys=True)
    assert "urn:quantiqmt:contract:message-envelope:v1" in encoded
    for forbidden in ("publisher", "aggregate_type", "payload_fingerprint"):
        assert forbidden not in encoded

    allowed = {
        "message_id",
        "message_type",
        "schema_version",
        "occurred_at",
        "received_at",
        "correlation_id",
        "causation_id",
        "aggregate_id",
        "aggregate_version",
        "source",
        "partition_key",
        "idempotency_key",
        "payload",
    }
    for definition in schema["$defs"].values():
        for fragment in definition.get("allOf", []):
            properties = fragment.get("properties", {})
            assert set(properties) <= allowed


def test_public_changed_events_are_occurred_facts_not_result_multiplexers() -> None:
    kill = _json(EVENTS / "system.kill_switch_changed.v1.schema.json")
    config = _json(EVENTS / "config.version_activated.v1.schema.json")
    for schema in (kill, config):
        assert "outcome" not in schema["properties"]
        assert "correlation_id" not in schema["properties"]
        assert "causation_id" not in schema["properties"]
        assert "source" not in schema["properties"]

    assert {"enabled", "previous_enabled", "changed_at"} <= set(kill["properties"])
    assert {"active_version", "active_checksum", "activated_at"} <= set(config["properties"])


def test_scoped_control_contract_uses_addressable_scope_pair() -> None:
    internal = _json(CONTROL / "control-plane.v1.schema.json")["$defs"]
    mode = _json(EVENTS / "system.mode_changed.v1.schema.json")
    kill = _json(EVENTS / "system.kill_switch_changed.v1.schema.json")

    for properties in (
        mode["properties"],
        kill["properties"],
        internal["killSwitchCommand"]["allOf"][1]["properties"],
        internal["killSwitchResult"]["allOf"][1]["properties"],
    ):
        assert "scope_type" in properties
        assert "scope_id" in properties
        assert "scope" not in properties


def test_task_022_references_existing_control_authorities() -> None:
    candidates = [
        ROOT / "tasks" / state / "TASK-022-observability-control-contracts.md"
        for state in ("active", "completed")
    ]
    existing = [path for path in candidates if path.is_file()]
    assert len(existing) == 1
    task = existing[0].read_text(encoding="utf-8")
    for authority in (
        "CONTRACT-MESSAGE-ENVELOPE-V1",
        "CONTRACT-ERROR-CATALOG",
        "PORTS-CORE",
        "SM-SYSTEM-MODE",
        "WF-RECOVERY",
        "STORAGE-SOT",
        "NFR-PERFORMANCE",
    ):
        assert authority in task
