from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from quantiqmt.contracts import SchemaBundleError, SchemaRegistry


def test_runtime_registry_uses_packaged_bundle_and_routes() -> None:
    registry = SchemaRegistry.runtime_default()
    assert "risk.order_evaluated.v2" in registry.message_types
    assert registry.payload("risk.order_evaluated.v2", 2)["$id"] == (
        "urn:quantiqmt:event:risk.order_evaluated:v2"
    )


def test_runtime_validator_rejects_schema_invalid_output() -> None:
    registry = SchemaRegistry.runtime_default()
    payload = {
        "schema_version": 1,
        "decision": {},
        "evaluated_at": "not-a-dateZ",
        "total_latency_us": 0,
        "evaluation_timeout_us": 1,
        "completed_rule_count": 0,
        "rule_timings": [],
    }
    with pytest.raises(ValueError):
        registry.validator().validate_payload("risk.order_evaluated.v2", 2, payload)


def test_catalog_version_mismatch_fails_startup(tmp_path: Path) -> None:
    (tmp_path / "catalog.yaml").write_text(
        "catalog:\n  id: CONTRACT-CATALOG\n  version: 2\n", encoding="utf-8"
    )
    with pytest.raises(SchemaBundleError, match="version mismatch"):
        SchemaRegistry(tmp_path)


def test_corrupt_schema_fails_startup(tmp_path: Path) -> None:
    source = Path("src/quantiqmt/contracts/schema_bundle")
    shutil.copytree(source, tmp_path, dirs_exist_ok=True)
    (tmp_path / "events/risk.order_evaluated.v2.schema.json").write_text("{", encoding="utf-8")
    with pytest.raises(SchemaBundleError, match="missing or corrupt"):
        SchemaRegistry(tmp_path)


def test_runtime_manifest_is_immutable_and_versioned() -> None:
    registry = SchemaRegistry.runtime_default()
    with pytest.raises(TypeError):
        registry.payload("risk.order_evaluated.v2", 2)["$id"] = "tampered"  # type: ignore[index]
