from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.bundle import (
    BundleIntegrityError,
    SchemaBundle,
    build_schema_bundle,
    verify_schema_bundle_parity,
)

ROOT = Path(__file__).resolve().parents[3]


def test_installed_schema_bundle_matches_reviewed_manifest() -> None:
    installed = SchemaBundle.installed()
    generated = build_schema_bundle(ROOT / "spec")

    assert installed.manifest_version == "0.15.0"
    assert installed.to_bytes() == generated.to_bytes()
    assert {
        "CONTRACT-MARKET-TICK-RECEIVED-V1",
        "CONTRACT-MARKET-BAR-CLOSED-V1",
        "CONTRACT-MARKET-QUALITY-CHANGED-V1",
        "CONTRACT-MARKET-SESSION-CHANGED-V1",
        "CONTRACT-MARKET-DATA-V1",
        "CONTRACT-MARKET-SEMANTIC-VALIDATION-V1",
        "CONTRACT-RISK-RULE-RESULT-V1",
        "CONTRACT-RISK-RULE-TIMING-V1",
        "CONTRACT-RISK-DECISION-V1",
        "CONTRACT-RISK-AUDIT-OUTPUT-V1",
    } <= set(installed.contract_ids)


def test_registry_uses_installed_resource_even_when_legacy_path_is_supplied() -> None:
    registry = SchemaRegistry(Path("a/source/checkout/that/does/not/exist"))

    assert registry.payload("market.tick_received.v1", 1)["$id"] == (
        "urn:quantiqmt:event:market.tick_received:v1"
    )
    assert (
        registry.contract("CONTRACT-MARKET-SEMANTIC-VALIDATION-V1")["semantic_validation"]["id"]
        == "CONTRACT-MARKET-SEMANTIC-VALIDATION-V1"
    )


def test_schema_bundle_rejects_content_and_overall_digest_tampering() -> None:
    document = json.loads(SchemaBundle.installed().to_bytes())
    document["contracts"][0]["content"] += "\n"

    with pytest.raises(BundleIntegrityError, match="content digest"):
        SchemaBundle.from_bytes(json.dumps(document).encode())

    document = json.loads(SchemaBundle.installed().to_bytes())
    document["bundle_digest"] = "0" * 64
    with pytest.raises(BundleIntegrityError, match="bundle digest"):
        SchemaBundle.from_bytes(json.dumps(document).encode())


def test_schema_bundle_generation_rejects_duplicate_missing_and_unresolved_contracts(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate"
    shutil.copytree(ROOT / "spec", duplicate)
    manifest = duplicate / "manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace(
            "    - id: CONTRACT-VALUE-TYPES",
            "    - id: CONTRACT-CATALOG\n      path: contracts/common/value-types.md\n"
            "    - id: CONTRACT-VALUE-TYPES",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(BundleIntegrityError, match="duplicate contract id"):
        build_schema_bundle(duplicate)

    missing = tmp_path / "missing"
    shutil.copytree(ROOT / "spec", missing)
    (missing / "contracts/events/market.tick_received.v1.schema.json").unlink()
    with pytest.raises(BundleIntegrityError, match="missing"):
        build_schema_bundle(missing)

    unresolved = tmp_path / "unresolved"
    shutil.copytree(ROOT / "spec", unresolved)
    schema_path = unresolved / "contracts/events/market.tick_received.v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["broken"] = {"$ref": "#/does/not/exist"}
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="unresolved schema reference"):
        build_schema_bundle(unresolved)


def test_schema_bundle_parity_check_rejects_reviewed_source_drift(tmp_path: Path) -> None:
    drifted = tmp_path / "spec"
    shutil.copytree(ROOT / "spec", drifted)
    path = drifted / "contracts/events/market.tick_received.v1.schema.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BundleIntegrityError, match="parity mismatch"):
        verify_schema_bundle_parity(drifted)
