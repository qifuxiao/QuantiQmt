from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _historical_manifest() -> dict:
    source = "3bee8766ab3bc5a14ea9e1367f7f973c3f9cc6eb:spec/manifest.yaml"
    assert (
        subprocess.check_output(
            ["git", "rev-parse", source], cwd=ROOT, timeout=10, text=True
        ).strip()
        == "1a72adc78638dc223fb263df8beb69a7e2586bb3"
    )
    return yaml.safe_load(subprocess.check_output(["git", "show", source], cwd=ROOT, timeout=10))


def test_risk_outputs_have_accepted_catalog_and_manifest_identities() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    catalog = yaml.safe_load((ROOT / "spec/contracts/catalog.yaml").read_text(encoding="utf-8"))

    assert _historical_manifest()["specification"]["version"] == "0.15.0"
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
    manifest = _historical_manifest()
    change = manifest["change"]

    assert change["id"] == "SPEC-0.15.0-RISK-RUNTIME-SCHEMA-BUNDLE"
    assert change["previous_version"] == "0.14.0"
    assert change["public_message_schema_changes"] == "none"
    assert "package" in change["migration"]["runtime_data"]
    assert "source" in change["rollback"]["runtime_data"]
    assert change["release"] == "prohibited"


def _nfr(name: str) -> dict:
    return yaml.safe_load((ROOT / f"spec/nfr/{name}.yaml").read_text(encoding="utf-8"))["nfr"]


def test_task_058_timing_preserves_deadline_and_full_validation_boundary() -> None:
    performance = _nfr("performance")
    assert performance["latency_p99_ms"]["risk_evaluation"] == 4
    timing = performance["risk_measurement"]
    assert (
        timing["total_latency_us"]
        == "max(ceil((sample_ns-start_ns)/1000),sum(rule_timings),timeout_floor)"
    )
    assert timing["completion_latency_us"] == "ceil((terminal_ns-start_ns)/1000)"
    assert timing["deadline_start"] == "before_admission_and_construction"
    assert timing["deadline_ns"] == "start_ns + evaluation_timeout_us * 1000"
    assert timing["expiry"] == "ceil((now_ns-start_ns)/1000) >= evaluation_timeout_us"
    assert timing["rounding_boundary"] == {
        "elapsed_ns": 3999001,
        "elapsed_us": 4000,
        "budget_us": 4000,
        "pass_eligible": False,
    }
    assert timing["finalization_chain"] == [
        "primitive_candidate",
        "draft_2020_12_schema",
        "PORTS_RISK_semantics",
        "deep_freeze",
    ]
    assert timing["deadline_covers"] == [
        "admission",
        "rules",
        "aggregation",
        "candidate",
        "schema",
        "semantics",
        "freeze",
        "handback",
    ]
    assert timing["post_validation_mutation"] == "forbidden"
    assert timing["late_pass_replacement"] == "forbidden"
    ports = (ROOT / "spec/interfaces/risk-ports.md").read_text(encoding="utf-8")
    for clause in (
        "sample_ns",
        "terminal_ns",
        "3,999,001ns",
        "timeout_floor",
        "RiskAuditSemanticValidator",
        "最终 candidate 固定后 MUST NOT 修改任何字段",
        "原始绝对 deadline",
    ):
        assert clause in ports
    assert "Runner MUST 产生 `CONTRACT-RISK-AUDIT-OUTPUT-V1`" not in ports


def test_task_058_resources_and_no_audit_failure_are_explicit() -> None:
    limits = _nfr("performance")["risk_resources"]
    assert limits["normal_workers"] == "fixed_positive_max_in_flight"
    assert limits["cleanup_workers"] == 1
    assert limits["cleanup_attempts_per_call"] == 1
    assert limits["waiting_backlog"] == 0
    assert limits["cleanup_wait_us"] == 4000
    assert limits["permit_release"] == "actual_worker_completion_or_proven_prestart_cancellation"
    assert (
        limits["host_runner_limit"] == "fixed_positive_including_retired_runners_with_live_workers"
    )
    assert limits["blocked_worker_replacement"] == "forbidden"
    workflow = yaml.safe_load(
        (ROOT / "spec/workflows/submit-order.yaml").read_text(encoding="utf-8")
    )["workflow"]
    failure = workflow["risk_audit"]["no_valid_audit"]
    assert failure["outcome"] == "local_failure_without_decision"
    assert failure["forbidden"] == [
        "fabricated_decision",
        "automatic_oms_rejected",
        "v1_projection",
        "v1_v2_publication",
        "approved_transition",
        "execution",
        "retry_by_exception_name_or_text",
    ]
    ports = (ROOT / "spec/interfaces/risk-ports.md").read_text(encoding="utf-8")
    for clause in (
        "RiskRunFailure",
        "ORIGINAL_FAILURE",
        "CLEANUP_CAPACITY",
        "CLEANUP_WAIT_EXHAUSTED",
        "CLEANUP_WORKER_EXCEPTION",
        "原异常对象及其 cause",
        "唯一终态",
        "CPython",
        "permit",
        "QQ-RISK-4008",
    ):
        assert clause in ports


def test_task_058_telemetry_bounds_and_lower_bound_diagnostics() -> None:
    telemetry = _nfr("observability")["risk_telemetry"]
    assert telemetry["admission"] == "try_only_before_batch_construction"
    assert telemetry["consumer_workers"] == 1
    assert telemetry["pending_slots"] == 1
    assert telemetry["buffer_count"] == 2
    assert telemetry["buffer_bytes"] == 524288
    assert telemetry["max_rule_samples"] == 8192
    assert telemetry["max_summary_samples"] == 4
    assert telemetry["numeric_encoding"] == "uint64_unsigned_fixed_8_bytes"
    assert telemetry["drop_reasons"] == ["FULL", "CONTENDED", "OBSERVER_EXCEPTION", "CLOSED"]
    assert telemetry["counter_semantics"] == "uint64_saturating_possibly_missed_LOWER_BOUND"
    assert telemetry["diagnostic_states"] == ["AVAILABLE", "BUSY"]
    assert (
        telemetry["observer_exception"]
        == "prefix_side_effects_possible_drop_remaining_batch_without_retry"
    )
    assert telemetry["observer_replacement"] == "forbidden"
    assert telemetry["authoritative_audit_or_outbox_loss"] == "forbidden"
    ports = (ROOT / "spec/interfaces/risk-ports.md").read_text(encoding="utf-8")
    for clause in (
        "try_diagnostics",
        "LOWER_BOUND",
        "BUSY",
        "AVAILABLE",
        "零下界不能证明零丢失",
        "非嵌套",
        "512KiB",
        "uint64",
        "close",
    ):
        assert clause in ports


def test_task_058_compatibility_does_not_relabel_published_runtime() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["specification"]["version"] == "0.16.0"
    change = manifest["change"]
    assert change["id"] == "SPEC-0.16.0-RISK-FINALIZATION-BOUNDARY"
    assert change["previous_version"] == "0.15.0"
    assert change["public_message_schema_changes"] == "none"
    assert change["error_catalog_change"] == "none"
    assert change["runtime_code_change"] == "none"
    assert change["runtime_bundle_version"] == "0.15.0"
    assert change["new_local_interfaces"] == [
        "RiskRunFailure",
        "RiskTelemetry.try_diagnostics",
        "RiskTelemetry.close",
    ]
    assert change["affected_tasks"] == ["TASK-005", "TASK-058"]
    assert change["deployment_order"] == [
        "independent_normative_review_and_human_acceptance",
        "adapt_callers_to_no_valid_audit_failure_and_lower_bound_diagnostics",
        "separate_TASK_005_replan_activation_and_runtime_implementation",
        "verify_runtime_deadline_resource_failure_and_performance_boundaries",
        "enable_new_runner_only_after_all_consumers_are_compatible",
    ]
    assert (
        change["rollback"]["trading_gates"]
        == "closed_until_compatible_consumers_and_runner_are_verified"
    )
    assert change["migration"]["destructive_backfill"] == "forbidden"
    assert change["release"] == "prohibited"
