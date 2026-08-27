from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _yaml(relative_path: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_storage_freezes_bound_and_legacy_unbound_matrix() -> None:
    storage = _yaml("spec/storage/order-persistence.yaml")["storage"]
    assert isinstance(storage, dict)
    binding = storage["registration_binding"]
    assert isinstance(binding, dict)

    assert binding["states"] == {
        "BOUND": {
            "broker": "non_empty_trimmed_string",
            "broker_capability_version": "non_empty_trimmed_string",
        },
        "UNBOUND": {"broker": None, "broker_capability_version": None},
    }
    assert binding["partial_binding"] == "forbidden"
    assert binding["new_registration"] == "BOUND_required_before_repository_write"

    legacy = binding["legacy"]
    assert isinstance(legacy, dict)
    assert legacy["missing_fields"] == "read_as_UNBOUND"
    assert legacy["null_pair"] == "read_as_UNBOUND"
    assert legacy["ambient_or_current_capability_inference"] == "forbidden"
    assert legacy["task_048_rebinding"] == "forbidden"
    assert legacy["future_rebinding"] == "requires_separate_reviewed_repair_contract"


def test_storage_adds_nullable_immutable_columns_without_backfill() -> None:
    storage = _yaml("spec/storage/order-persistence.yaml")["storage"]
    assert isinstance(storage, dict)
    tables = storage["tables"]
    assert isinstance(tables, dict)
    orders = tables["orders"]
    assert isinstance(orders, dict)
    columns = orders["columns"]
    assert isinstance(columns, dict)

    assert columns["broker"] == {"type": "varchar", "max_length": 64, "nullable": True}
    assert columns["broker_capability_version"] == {
        "type": "varchar",
        "max_length": 128,
        "nullable": True,
    }
    assert "broker_binding_complete_or_unbound" in orders["checks"]
    assert "broker_binding_non_empty_trimmed_when_bound" in orders["checks"]
    assert "broker" in orders["immutable_after_insert"]
    assert "broker_capability_version" in orders["immutable_after_insert"]

    migration = storage["registration_binding"]["migration"]
    assert migration["kind"] == "expand_only_idempotent"
    assert migration["historical_backfill"] == "forbidden"
    assert migration["existing_rows"] == "preserve_as_UNBOUND"
    assert migration["destructive_rollback"] == "forbidden"


def test_journal_snapshot_and_projection_compatibility_is_frozen() -> None:
    storage = _yaml("spec/storage/order-persistence.yaml")["storage"]
    assert isinstance(storage, dict)
    binding = storage["registration_binding"]
    assert isinstance(binding, dict)
    persistence = binding["persistence"]

    assert persistence["new_journal_and_snapshot"] == "write_complete_BOUND_fields"
    assert persistence["legacy_missing_fields"] == "parse_as_UNBOUND_without_payload_rewrite"
    assert persistence["legacy_checksum_input"] == "exact_stored_payload"
    assert persistence["checksum_recanonicalization_with_injected_nulls"] == "forbidden"
    assert persistence["projection_binding"] == "must_equal_authoritative_registration_fact"
    assert persistence["rebuild_binding_source"] == "journal_never_projection_or_adapter"


def test_order_registration_port_exposes_unbound_without_permitting_new_unbound_write() -> None:
    ports = _text("spec/interfaces/order-persistence-ports.md")
    assert "broker: str | None" in ports
    assert "broker_capability_version: str | None" in ports
    assert "`BOUND` requires both fields to be non-null" in ports
    assert "`UNBOUND` requires both fields to be null" in ports
    assert "A partial binding is invalid" in ports
    assert "`OrderRepository.register` MUST reject an `UNBOUND` registration" in ports
    assert "TASK-048 MUST NOT bind a legacy `UNBOUND` registration" in ports


def test_repository_and_workflows_fail_closed_for_unbound() -> None:
    repository = _text("spec/repositories/order-repository.md")
    assert "Legacy `UNBOUND` registrations remain readable for recovery" in repository
    assert "MUST NOT become eligible for submit or cancel dispatch" in repository
    assert "full Journal replay MUST preserve `UNBOUND`" in repository

    order_commit = _yaml("spec/workflows/order-commit.yaml")["workflow"]
    assert order_commit["registration"]["preconditions"]["broker_binding"] == "BOUND"
    assert order_commit["registration"]["legacy_unbound_write"] == "forbidden"

    submit = _yaml("spec/workflows/submit-order.yaml")["workflow"]
    register_step = next(step for step in submit["steps"] if step["id"] == "register_order")
    assert register_step["persisted_identity"] == [
        "order_id",
        "intent_id",
        "client_order_id",
        "broker",
        "broker_capability_version",
    ]
    broker_submit = next(step for step in submit["steps"] if step["id"] == "broker_submit")
    assert "persisted_broker_binding_BOUND" in broker_submit["pre_dispatch_guards"]
    assert broker_submit["unbound_registration"] == "reject_before_dispatch"

    cancel = _yaml("spec/workflows/cancel-order.yaml")["workflow"]
    broker_cancel = next(step for step in cancel["steps"] if step["id"] == "broker_cancel")
    assert broker_cancel["unbound_registration"] == "reject_before_dispatch"

    recovery = _yaml("spec/workflows/recovery.yaml")["workflow"]
    assert recovery["order_failure_rules"]["unbound_registration"] == (
        "preserve UNBOUND, prohibit Broker dispatch, keep SAFE and require reconciliation evidence"
    )


def test_manifest_and_task_handoff_record_spec_change() -> None:
    manifest = _yaml("spec/manifest.yaml")
    specification = manifest["specification"]
    assert specification["version"] == "0.14.0"
    change = manifest["change"]
    assert change["id"] == "SPEC-0.14.0-ORDER-REGISTRATION-BINDING-COMPATIBILITY"
    assert change["previous_version"] == "0.13.0"
    assert change["runtime_code_change"] == "none_in_TASK_050"
    assert "TASK-050" in change["affected_tasks"]
    assert "TASK-048" in change["affected_tasks"]
    assert change["migration"]["destructive_backfill"] == "forbidden"

    index = _text("tasks/index.yaml")
    assert "id: TASK-050" in index
    assert "status: active" in index.split("id: TASK-050", maxsplit=1)[1].splitlines()[0]
    task_048 = _text("tasks/backlog/TASK-048-order-registration-broker-capability-binding.md")
    assert "depends_on: [TASK-004, TASK-017, TASK-050]" in task_048
