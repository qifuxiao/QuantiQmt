from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from quantiqmt.contracts.errors import SchemaBundleError
from quantiqmt.contracts.registry import SchemaRegistry

SOURCE_BUNDLE = Path("src/quantiqmt/contracts/schema_bundle")


def bundle_copy(tmp_path: Path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(SOURCE_BUNDLE, target)
    return target


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    root = bundle_copy(tmp_path)
    (root / "runtime-manifest.json").unlink()
    from quantiqmt.contracts import registry as registry_module

    original = registry_module.resources.files
    registry_module.resources.files = lambda _: root  # type: ignore[assignment]
    try:
        with pytest.raises(SchemaBundleError):
            SchemaRegistry.runtime_default()
    finally:
        registry_module.resources.files = original


def test_runtime_registry_uses_packaged_bundle_not_source_spec() -> None:
    registry = SchemaRegistry.runtime_default()
    assert "spec" not in str(registry._root).split("schema_bundle")[0]
    assert "risk.order_evaluated.v2" in registry.message_types


def test_corrupt_schema_fails_closed(tmp_path: Path) -> None:
    root = bundle_copy(tmp_path)
    (root / "events/risk.order_evaluated.v2.schema.json").write_text("[]", encoding="utf-8")
    with pytest.raises((SchemaBundleError, ValueError)):
        SchemaRegistry(root)


@pytest.mark.parametrize("mutation", ["corrupt", "version", "route"])
def test_bundle_manifest_and_routes_fail_closed(tmp_path: Path, mutation: str) -> None:
    root = bundle_copy(tmp_path)
    manifest_path = root / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "corrupt":
        manifest_path.write_text("{", encoding="utf-8")
    elif mutation == "version":
        manifest["bundle_version"] = 99
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        manifest["required_routes"] = ["risk.order_evaluated.v2", "missing.v1"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    from quantiqmt.contracts import registry as registry_module

    original = registry_module.resources.files
    registry_module.resources.files = lambda _: root  # type: ignore[assignment]
    try:
        with pytest.raises(SchemaBundleError):
            SchemaRegistry.runtime_default()
    finally:
        registry_module.resources.files = original
