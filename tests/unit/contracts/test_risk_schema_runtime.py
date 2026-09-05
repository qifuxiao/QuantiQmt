from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from quantiqmt.contracts import ContractValidationError, SchemaBundle, SchemaRegistry
from quantiqmt.contracts.bundle import BundleIntegrityError
from quantiqmt.contracts.validation import validate_contract_candidate

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = (
    ROOT / "tests/contract/messages/fixtures/risk.order_evaluated.v2/semantic-evaluator.valid.json"
)


def _audit() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_schema_validation_precedes_semantic_validation() -> None:
    calls: list[str] = []

    validate_contract_candidate(
        "CONTRACT-RISK-RULE-RESULT-V1",
        _audit()["decision"]["rule_results"][0],
        semantic_validator=lambda _: calls.append("semantic"),
    )
    assert calls == ["semantic"]

    invalid = deepcopy(_audit()["decision"]["rule_results"][0])
    invalid["priority"] = -1
    with pytest.raises(ContractValidationError):
        validate_contract_candidate(
            "CONTRACT-RISK-RULE-RESULT-V1",
            invalid,
            semantic_validator=lambda _: calls.append("invalid-semantic"),
        )
    assert calls == ["semantic"]


def test_registry_resolves_risk_urn_references_from_verified_bundle() -> None:
    registry = SchemaRegistry.project_default()
    assert registry.schema("CONTRACT-RISK-DECISION-V1")["$id"].endswith("risk-decision:v1")

    registry.validate_contract("CONTRACT-RISK-DECISION-V1", _audit()["decision"], path="$.decision")


def test_loaded_bundle_rechecks_references_after_all_digests_are_recomputed() -> None:
    document = json.loads(SchemaBundle.installed().to_bytes())
    entry = next(
        item for item in document["contracts"] if item["id"] == "CONTRACT-RISK-DECISION-V1"
    )
    changed = dict(entry["document"])
    changed["$ref"] = "urn:quantiqmt:event:missing:v1"
    content = json.dumps(changed, indent=2) + "\n"
    entry["content"] = content
    entry["document"] = changed
    entry["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    entry["document_sha256"] = _digest(changed)
    projection = dict(document)
    projection.pop("bundle_digest")
    document["bundle_digest"] = _digest(projection)

    with pytest.raises(BundleIntegrityError, match="unresolved schema reference"):
        SchemaBundle.from_bytes(json.dumps(document).encode("utf-8"))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("manifest_version", "0.14.0"), "manifest version"),
        (lambda value: value.__setitem__("bundle_schema_version", 2), "bundle version"),
        (lambda value: value.__setitem__("contracts", []), "partial"),
        (lambda value: value.__setitem__("bundle_digest", "0" * 64), "bundle digest"),
    ],
)
def test_bundle_version_partial_and_digest_fail_closed(mutation: Any, message: str) -> None:
    document = json.loads(SchemaBundle.installed().to_bytes())
    mutation(document)
    with pytest.raises(BundleIntegrityError, match=message):
        SchemaBundle.from_bytes(json.dumps(document).encode("utf-8"))


def test_task_029_wheel_validates_risk_graph_main_package_only_without_source(
    tmp_path: Path,
) -> None:
    wheel_candidates = sorted((ROOT / "dist").glob("**/quantiqmt-*.whl"))
    wheel: Path | None = None
    for candidate in reversed(wheel_candidates):
        with zipfile.ZipFile(candidate) as archive:
            resource = next(
                (
                    name
                    for name in archive.namelist()
                    if name.endswith("quantiqmt/contracts/resources/schema-bundle.v1.json")
                ),
                None,
            )
            if resource is not None and json.loads(archive.read(resource))["manifest_version"] == (
                "0.15.0"
            ):
                wheel = candidate
                break
    if wheel is None:
        pytest.skip("TASK-029 wheel is built by the preceding prescribed `poetry build` command")

    environment = tmp_path / "main-only"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    clean_environment = dict(os.environ)
    clean_environment.pop("PYTHONPATH", None)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    fixture = tmp_path / "audit.json"
    fixture.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    probe = (
        "import json; "
        "from quantiqmt.contracts import SchemaBundle,validate_contract_candidate; "
        f"a=json.load(open({str(fixture)!r},encoding='utf-8')); "
        "noop=lambda _:None; "
        "validate_contract_candidate('CONTRACT-RISK-RULE-RESULT-V1',"
        "a['decision']['rule_results'][0],semantic_validator=noop); "
        "validate_contract_candidate('CONTRACT-RISK-RULE-TIMING-V1',"
        "a['rule_timings'][0],semantic_validator=noop); "
        "validate_contract_candidate('CONTRACT-RISK-DECISION-V1',"
        "a['decision'],semantic_validator=noop); "
        "validate_contract_candidate('CONTRACT-RISK-AUDIT-OUTPUT-V1',"
        "a,semantic_validator=noop); "
        "assert SchemaBundle.installed().manifest_version=='0.15.0'"
    )
    subprocess.run(
        [str(python), "-I", "-c", probe],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    locate = (
        "import importlib.resources; "
        "print(importlib.resources.files('quantiqmt.contracts.resources').joinpath("
        "'schema-bundle.v1.json'))"
    )
    bundle = Path(
        subprocess.run(
            [str(python), "-I", "-c", locate],
            cwd=tmp_path,
            env=clean_environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    original = bundle.read_bytes()
    failure_probe = (
        "from quantiqmt.contracts.bundle import SchemaBundle,BundleIntegrityError; "
        "\ntry: SchemaBundle.installed()\nexcept BundleIntegrityError: raise SystemExit(0)\n"
        "raise SystemExit(1)"
    )
    hidden = bundle.with_suffix(".hidden")
    bundle.replace(hidden)
    try:
        subprocess.run(
            [str(python), "-I", "-c", failure_probe],
            cwd=tmp_path,
            env=clean_environment,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        hidden.replace(bundle)
    wrong_version = original.replace(b'"manifest_version":"0.15.0"', b'"manifest_version":"9.9.9"')
    for damaged in (b"not-json", wrong_version):
        bundle.write_bytes(damaged)
        try:
            subprocess.run(
                [str(python), "-I", "-c", failure_probe],
                cwd=tmp_path,
                env=clean_environment,
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            bundle.write_bytes(original)
