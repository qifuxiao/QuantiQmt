from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.bundle import (
    BundleIntegrityError,
    SchemaBundle,
    build_schema_bundle,
    verify_schema_bundle_parity,
)

ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_COMMIT = "3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb"


@pytest.fixture
def historical_spec(tmp_path: Path) -> Path:
    source = f"{HISTORICAL_COMMIT}:spec/manifest.yaml"
    assert (
        subprocess.check_output(
            ["git", "rev-parse", source], cwd=ROOT, timeout=10, text=True
        ).strip()
        == "1a72adc78638dc223fb263df8beb69a7e2586bb3"
    )
    paths = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            HISTORICAL_COMMIT,
            "--",
            "spec/manifest.yaml",
            "spec/contracts",
        ],
        cwd=ROOT,
        timeout=10,
        text=True,
    ).splitlines()
    destination = tmp_path / "frozen"
    for relative in paths:
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            subprocess.check_output(
                ["git", "show", f"{HISTORICAL_COMMIT}:{relative}"], cwd=ROOT, timeout=10
            )
        )
    return destination / "spec"


def test_installed_schema_bundle_matches_reviewed_manifest(historical_spec: Path) -> None:
    installed = SchemaBundle.installed()
    generated = build_schema_bundle(historical_spec)

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


def test_current_contract_index_file_set_and_bytes_match_frozen_source(
    historical_spec: Path,
) -> None:
    current = ROOT / "spec"
    current_manifest = yaml.safe_load((current / "manifest.yaml").read_bytes())
    historical_manifest = yaml.safe_load((historical_spec / "manifest.yaml").read_bytes())
    assert current_manifest["catalogs"]["contracts"] == historical_manifest["catalogs"]["contracts"]
    current_files = {
        path.relative_to(current) for path in (current / "contracts").rglob("*") if path.is_file()
    }
    historical_files = {
        path.relative_to(historical_spec)
        for path in (historical_spec / "contracts").rglob("*")
        if path.is_file()
    }
    assert current_files == historical_files
    for relative in historical_files:
        assert (current / relative).read_bytes() == (historical_spec / relative).read_bytes(), (
            relative
        )


def test_old_builder_rejects_current_new_manifest_without_downgrade() -> None:
    with pytest.raises(
        BundleIntegrityError, match="spec manifest version does not match installed runtime"
    ):
        build_schema_bundle(ROOT / "spec")


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
    historical_spec: Path,
) -> None:
    duplicate = tmp_path / "duplicate"
    shutil.copytree(historical_spec, duplicate)
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
    shutil.copytree(historical_spec, missing)
    (missing / "contracts/events/market.tick_received.v1.schema.json").unlink()
    with pytest.raises(BundleIntegrityError, match="missing"):
        build_schema_bundle(missing)

    unresolved = tmp_path / "unresolved"
    shutil.copytree(historical_spec, unresolved)
    schema_path = unresolved / "contracts/events/market.tick_received.v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["broken"] = {"$ref": "#/does/not/exist"}
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(BundleIntegrityError, match="unresolved schema reference"):
        build_schema_bundle(unresolved)


def test_schema_bundle_parity_check_rejects_reviewed_source_drift(
    tmp_path: Path, historical_spec: Path
) -> None:
    drifted = tmp_path / "spec"
    shutil.copytree(historical_spec, drifted)
    path = drifted / "contracts/events/market.tick_received.v1.schema.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BundleIntegrityError, match="parity mismatch"):
        verify_schema_bundle_parity(drifted)
