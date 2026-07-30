from pathlib import Path

import pytest
import scripts.validate_specs as validator
from scripts.validate_specs import (
    ROOT,
    bootstrap_allows_dependency,
    delivery_is_unlockable,
    has_cycle,
    main,
    manifest_entries,
    validate_delivery,
    validate_tasks,
    validate_waiver_entries,
)

import quantiqmt


def test_package_is_importable() -> None:
    assert quantiqmt.__name__ == "quantiqmt"


def test_repository_specs_are_valid() -> None:
    assert main() == 0


def test_cycle_detection() -> None:
    assert has_cycle({"A": ["B"], "B": ["A"]})
    assert not has_cycle({"A": ["B"], "B": []})


def test_manifest_paths_are_inside_spec() -> None:
    import yaml

    manifest_path = ROOT / "spec" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for path in manifest_entries(manifest).values():
        assert path.is_file()
        assert Path("spec") in path.relative_to(ROOT).parents


def test_reported_unverified_delivery_is_fail_closed() -> None:
    errors: list[str] = []
    validate_delivery(
        "TASK-029",
        {
            "status": "blocked",
            "delivery": {
                "schema_version": 1,
                "contract_status": "accepted",
                "implementation_status": "not_started",
                "acceptance_status": "unverified",
                "review_status": "reported_unverified",
                "release_status": "eligible",
            },
        },
        ROOT / "tasks" / "backlog" / "TASK-029-risk-runtime-schema-contract.md",
        errors,
    )
    assert any("prohibited release" in error for error in errors)


def test_completed_delivery_requires_completion_evidence() -> None:
    errors: list[str] = []
    validate_delivery(
        "TASK-016",
        {
            "status": "completed",
            "delivery": {
                "schema_version": 1,
                "contract_status": "accepted",
                "implementation_status": "merged",
                "acceptance_status": "passed",
                "review_status": "approved",
                "release_status": "prohibited",
            },
        },
        ROOT / "tasks" / "completed" / "TASK-016-strategy-runtime-contracts.md",
        errors,
    )
    assert any("completion_evidence" in error for error in errors)


def test_only_bootstrap_waiver_allows_task031_dependency() -> None:
    waiver = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "rule": "bootstrap",
        "reason": "recovery",
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
    }
    assert bootstrap_allows_dependency("TASK-014", "TASK-031", [waiver])
    assert not bootstrap_allows_dependency("TASK-014", "TASK-005", [waiver])
    assert not bootstrap_allows_dependency("TASK-016", "TASK-031", [waiver])
    expired = {**waiver, "expires_on": "2020-01-01"}
    assert not bootstrap_allows_dependency("TASK-014", "TASK-031", [expired])


def test_reported_unverified_or_missing_delivery_cannot_unlock() -> None:
    assert not delivery_is_unlockable({})
    assert not delivery_is_unlockable(
        {
            "delivery": {
                "schema_version": 1,
                "acceptance_status": "passed",
                "review_status": "reported_unverified",
                "release_status": "prohibited",
            }
        }
    )


@pytest.mark.parametrize(
    "delivery,allowed,bootstrap",
    [
        ({"review_status": "pending"}, False, False),
        ({"review_status": "changes_requested"}, False, False),
        ({"review_status": "approved", "acceptance_status": "unverified"}, False, False),
        ({"review_status": "reported_unverified", "acceptance_status": "passed"}, False, False),
        (
            {
                "implementation_status": "merged",
                "acceptance_status": "passed",
                "review_status": "approved",
                "release_status": "prohibited",
            },
            True,
            False,
        ),
        (
            {"review_status": "reported_unverified", "acceptance_status": "unverified"},
            True,
            True,
        ),
    ],
)
def test_validate_tasks_dependency_gate(monkeypatch, delivery, allowed, bootstrap) -> None:
    fixture_root = ROOT / "tasks" / ".validator-fixture"
    fixture_root.mkdir(exist_ok=True)
    dependency = fixture_root / "TASK-014.md"
    active = fixture_root / "TASK-031.md"
    base = (
        "status: completed\ndepends_on: []\nspec_refs: []\n"
        "allowed_paths: []\nforbidden_paths: []\n"
        "verification: {commands: [check]}\n"
    )
    dep_delivery = {
        "schema_version": 1,
        "contract_status": "accepted",
        "implementation_status": "not_applicable",
        "acceptance_status": "unverified",
        "review_status": "reported_unverified",
        "release_status": "prohibited",
    }
    dep_delivery.update(delivery)
    dependency.write_text(
        f"---\nid: TASK-014\n{base}delivery:\n"
        + "\n".join(f"  {k}: {v}" for k, v in dep_delivery.items())
        + "\n---\n",
        encoding="utf-8",
    )
    active.write_text(
        "---\nid: TASK-031\nstatus: active\ndepends_on: [TASK-014]\n"
        "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
        "verification: {commands: [check]}\ndelivery:\n"
        "  schema_version: 1\n  contract_status: not_applicable\n"
        "  implementation_status: in_progress\n  acceptance_status: not_run\n"
        "  review_status: pending\n  release_status: prohibited\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "task_files", lambda: [dependency, active])
    monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
    original_load_yaml = validator.load_yaml

    def fake_load_yaml(path):
        if path == validator.TASK_ROOT / "governance-waivers.yaml":
            if bootstrap:
                return {
                    "waivers": [
                        {
                            "task_id": "TASK-014",
                            "beneficiary_task": "TASK-031",
                            "kind": "bootstrap_exception",
                            "one_time": True,
                            "deny_business_unlock": True,
                            "rule": "bootstrap",
                            "reason": "recovery",
                            "owner": "qfxyyy",
                            "expires_on": "2026-08-13",
                            "remediation_task": "TASK-031",
                            "release_status": "prohibited",
                        }
                    ]
                }
            return {"waivers": []}
        if path == validator.TASK_ROOT / "index.yaml":
            return {
                "tasks": [
                    {"id": "TASK-014", "path": "TASK-014.md", "status": "completed"},
                    {"id": "TASK-031", "path": "TASK-031.md", "status": "active"},
                ]
            }
        return original_load_yaml(path)

    monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
    errors: list[str] = []
    validate_tasks({}, errors)
    assert (not any("trusted completed delivery" in error for error in errors)) is allowed
    dependency.unlink(missing_ok=True)
    active.unlink(missing_ok=True)
    fixture_root.rmdir()


def test_waiver_semantics_reject_empty_unknown_expired_and_release() -> None:
    valid = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "rule": "bootstrap",
        "reason": "recovery",
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
    }
    for invalid in (
        {**valid, "owner": ""},
        {**valid, "remediation_task": "TASK-999"},
        {**valid, "expires_on": "2020-01-01"},
        {**valid, "release_status": "released"},
        {key: value for key, value in valid.items() if key != "reason"},
    ):
        errors: list[str] = []
        validate_waiver_entries([invalid], {"TASK-014", "TASK-031"}, errors)
        assert errors
