from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_risk_outputs_have_accepted_catalog_and_manifest_identities() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    catalog = yaml.safe_load((ROOT / "spec/contracts/catalog.yaml").read_text(encoding="utf-8"))

    assert manifest["specification"]["version"] == "0.15.0"
    indexed = {item["id"]: item["path"] for item in manifest["catalogs"]["contracts"]}
    expected = {
        "CONTRACT-RISK-RULE-RESULT-V1": "contracts/risk/rule-result.v1.schema.json",
        "CONTRACT-RISK-RULE-TIMING-V1": "contracts/risk/rule-timing.v1.schema.json",
        "CONTRACT-RISK-DECISION-V1": "contracts/risk/risk-decision.v1.schema.json",
        "CONTRACT-RISK-AUDIT-OUTPUT-V1": "contracts/risk/risk-audit-output.v1.schema.json",
        "CONTRACT-RISK-ORDER-EVALUATED-V2": (
            "contracts/events/risk.order_evaluated.v2.schema.json"
        ),
    }
    assert expected.items() <= indexed.items()

    internal = {item["id"]: item for item in catalog["internal_contracts"]}
    for contract_id in expected.keys() - {"CONTRACT-RISK-ORDER-EVALUATED-V2"}:
        assert internal[contract_id]["status"] == "accepted"
        assert internal[contract_id]["owner"] == "RiskEngine"

    route = next(item for item in catalog["messages"] if item["name"] == "risk.order_evaluated.v2")
    assert route["status"] == "active"
    assert route["schema"] == "events/risk.order_evaluated.v2.schema.json"

    for _contract_id, relative in expected.items():
        schema = json.loads((ROOT / "spec" / relative).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].startswith("urn:quantiqmt:")


def test_manifest_records_task_029_package_only_lifecycle() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    change = manifest["change"]

    assert change["id"] == "SPEC-0.15.0-RISK-RUNTIME-SCHEMA-BUNDLE"
    assert change["previous_version"] == "0.14.0"
    assert change["public_message_schema_changes"] == "none"
    assert "package" in change["migration"]["runtime_data"]
    assert "source" in change["rollback"]["runtime_data"]
    assert change["release"] == "prohibited"
