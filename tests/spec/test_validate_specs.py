from pathlib import Path

import pytest
import scripts.validate_specs as validator
import yaml
from scripts.validate_specs import (
    ROOT,
    bootstrap_allows_dependency,
    delivery_is_unlockable,
    extract_front_matter,
    has_cycle,
    main,
    manifest_entries,
    validate_delivery,
    validate_l4_successor_dependencies,
    validate_tasks,
    validate_waiver_entries,
)

import quantiqmt


@pytest.fixture
def isolated_task_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    task_root = tmp_path / "tasks"
    task_root.mkdir()
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(validator, "TASK_ROOT", task_root)
    return task_root


def indexed_task_path(task_id: str, *, root: Path = ROOT) -> Path:
    index = validator.load_yaml(root / "tasks" / "index.yaml")
    entries = index.get("tasks") if isinstance(index, dict) else None
    assert isinstance(entries, list), "tasks/index.yaml must contain a tasks list"
    matches = [entry for entry in entries if entry.get("id") == task_id]
    assert len(matches) == 1, f"{task_id} must have exactly one index entry"
    relative_path = matches[0].get("path")
    assert isinstance(relative_path, str) and relative_path, (
        f"{task_id} index path must be a non-empty string"
    )
    task_path = root / "tasks" / relative_path
    assert task_path.is_file(), f"{task_id} indexed task file is missing: {relative_path}"
    task = extract_front_matter(task_path)
    assert task.get("id") == task_id, f"{task_id} index path resolves to task {task.get('id')}"
    return task_path


def write_task047_index_fixture(
    root: Path, entries: list[dict[str, str]], *, task_id: str | None = None
) -> Path | None:
    task_root = root / "tasks"
    task_root.mkdir(parents=True)
    task_path = None
    if task_id is not None:
        task_path = task_root / "active" / "TASK-017.md"
        task_path.parent.mkdir()
        task_path.write_text(f"---\nid: {task_id}\n---\n", encoding="utf-8")
    (task_root / "index.yaml").write_text(
        yaml.safe_dump({"tasks": entries}, sort_keys=False), encoding="utf-8"
    )
    return task_path


def test_package_is_importable() -> None:
    assert quantiqmt.__name__ == "quantiqmt"


def test_repository_specs_are_valid() -> None:
    assert main() == 0


def test_cycle_detection() -> None:
    assert has_cycle({"A": ["B"], "B": ["A"]})
    assert not has_cycle({"A": ["B"], "B": []})


def test_manifest_paths_are_inside_spec() -> None:
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
        "lifecycle_status": "active",
    }
    before_expiry = validator.date.fromisoformat("2026-08-06")
    assert bootstrap_allows_dependency("TASK-014", "TASK-031", [waiver], today=before_expiry)
    assert not bootstrap_allows_dependency("TASK-014", "TASK-005", [waiver], today=before_expiry)
    assert not bootstrap_allows_dependency("TASK-016", "TASK-031", [waiver], today=before_expiry)
    assert not bootstrap_allows_dependency(
        "TASK-014",
        "TASK-031",
        [{**waiver, "lifecycle_status": "retired"}],
        today=before_expiry,
    )
    assert not bootstrap_allows_dependency(
        "TASK-014",
        "TASK-031",
        [{**waiver, "lifecycle_status": "expired"}],
        today=before_expiry,
    )
    expired = {**waiver, "expires_on": "2020-01-01"}
    assert not bootstrap_allows_dependency("TASK-014", "TASK-031", [expired], today=before_expiry)


@pytest.mark.parametrize(
    "today,allowed",
    [("2026-08-13", True), ("2026-08-14", False)],
)
def test_bootstrap_dependency_expiry_boundary(today: str, allowed: bool) -> None:
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
        "lifecycle_status": "active",
    }
    assert (
        bootstrap_allows_dependency(
            "TASK-014",
            "TASK-031",
            [waiver],
            today=validator.date.fromisoformat(today),
        )
        is allowed
    )


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


def test_l4_queue_uses_task046_successor_without_rewriting_task029_gate() -> None:
    successor_task_ids = (
        "TASK-017",
        "TASK-018",
        "TASK-019",
        "TASK-020",
        "TASK-021",
        "TASK-022",
    )
    for task_id in successor_task_ids:
        task = extract_front_matter(indexed_task_path(task_id))
        assert "TASK-046" in task["depends_on"]
        assert "TASK-014" not in task["depends_on"]

    task029 = extract_front_matter(indexed_task_path("TASK-029"))
    assert "TASK-030" in task029["depends_on"]
    assert "TASK-046" not in task029["depends_on"]


def test_indexed_task_path_supports_active_successor(tmp_path: Path) -> None:
    entry = {"id": "TASK-017", "path": "active/TASK-017.md", "status": "active"}
    fixture_root = tmp_path / "task047-index-fixture"
    active_task = write_task047_index_fixture(fixture_root, [entry], task_id="TASK-017")
    assert indexed_task_path("TASK-017", root=fixture_root) == active_task


@pytest.mark.parametrize("case", ["missing", "duplicate", "missing_file", "wrong_id"])
def test_indexed_task_path_fails_closed(case: str, tmp_path: Path) -> None:
    entry = {"id": "TASK-017", "path": "active/TASK-017.md", "status": "active"}
    entries = [] if case == "missing" else [entry]
    if case == "duplicate":
        entries.append(entry.copy())
    fixture_task_id = "TASK-018" if case == "wrong_id" else None
    fixture_root = tmp_path / "task047-index-fixture"
    write_task047_index_fixture(fixture_root, entries, task_id=fixture_task_id)
    with pytest.raises(AssertionError):
        indexed_task_path("TASK-017", root=fixture_root)


def test_l4_successor_policy_rejects_historical_and_risk_substitution_edges() -> None:
    errors: list[str] = []
    validate_l4_successor_dependencies(
        {
            "TASK-046": {"depends_on": []},
            "TASK-017": {"depends_on": ["TASK-014"]},
            "TASK-029": {"depends_on": ["TASK-015", "TASK-046", "TASK-031"]},
        },
        errors,
    )
    assert any("TASK-017: historical TASK-014" in error for error in errors)
    assert any("TASK-017: missing TASK-046" in error for error in errors)
    assert any("TASK-029: TASK-030 evidence dependency" in error for error in errors)
    assert any("TASK-029: TASK-046 cannot replace" in error for error in errors)


@pytest.mark.parametrize(
    "successor_state,activation_allowed",
    [
        ("active", False),
        ("reported_unverified", False),
        ("missing_evidence", False),
        ("trusted_completed", True),
    ],
)
def test_task046_successor_gate_requires_trusted_completed_delivery(
    monkeypatch, isolated_task_root, successor_state, activation_allowed
) -> None:
    fixture_root = isolated_task_root
    successor = fixture_root / "TASK-046.md"
    dependent = fixture_root / "TASK-017.md"
    trusted_evidence = (
        "  completion_evidence:\n"
        "    mode: fixture\n"
        "    change_pr: https://github.com/example/repo/pull/46\n"
        "    reviewed_head_sha: " + "a" * 40 + "\n"
        "    review_verdict: APPROVE\n"
        "    reviewer: independent-reviewer\n"
        "    evidence_url: https://github.com/example/review/46\n"
        "    merge_commit_sha: " + "b" * 40 + "\n"
        "    human_authorization_evidence: fixture authorization\n"
    )
    if successor_state == "active":
        successor_status = "active"
        successor_delivery = (
            "  implementation_status: in_progress\n"
            "  acceptance_status: not_run\n"
            "  review_status: pending\n"
        )
        successor_evidence = ""
    elif successor_state == "reported_unverified":
        successor_status = "completed"
        successor_delivery = (
            "  implementation_status: merged\n"
            "  acceptance_status: unverified\n"
            "  review_status: reported_unverified\n"
            "  remediation_task: TASK-031\n"
        )
        successor_evidence = (
            "  completion_evidence:\n"
            "    mode: historical\n"
            "    change_pr: unverifiable\n"
            "    reviewed_head_sha: unverifiable\n"
            "    review_verdict: reported_unverified\n"
            "    reviewer: unverifiable\n"
            "    evidence_url: unverifiable\n"
            "    merge_commit_sha: unverifiable\n"
            "    human_authorization_evidence: unverifiable\n"
        )
    else:
        successor_status = "completed"
        successor_delivery = (
            "  implementation_status: merged\n"
            "  acceptance_status: passed\n"
            "  review_status: approved\n"
        )
        successor_evidence = trusted_evidence if successor_state == "trusted_completed" else ""
    try:
        successor.write_text(
            f"---\nid: TASK-046\nstatus: {successor_status}\ndepends_on: []\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\ndelivery:\n"
            "  schema_version: 1\n  contract_status: not_applicable\n"
            + successor_delivery
            + "  release_status: prohibited\n"
            + successor_evidence
            + "---\n\n## Acceptance criteria\n- [x] fixture\n",
            encoding="utf-8",
        )
        dependent.write_text(
            "---\nid: TASK-017\nstatus: active\ndepends_on: [TASK-046]\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\ndelivery:\n"
            "  schema_version: 1\n  contract_status: not_applicable\n"
            "  implementation_status: in_progress\n  acceptance_status: not_run\n"
            "  review_status: pending\n  release_status: prohibited\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validator, "task_files", lambda: [successor, dependent])
        monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
        original_load_yaml = validator.load_yaml

        def fake_load_yaml(path):
            if path == validator.TASK_ROOT / "governance-waivers.yaml":
                return {"schema_version": 1, "waivers": []}
            if path == validator.TASK_ROOT / "index.yaml":
                return {
                    "tasks": [
                        {
                            "id": "TASK-046",
                            "path": "TASK-046.md",
                            "status": successor_status,
                        },
                        {"id": "TASK-017", "path": "TASK-017.md", "status": "active"},
                    ]
                }
            return original_load_yaml(path)

        monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
        errors: list[str] = []
        validate_tasks({}, errors)
        denied = any(
            "TASK-017: dependency TASK-046 lacks trusted completed delivery" in error
            for error in errors
        )
        assert denied is not activation_allowed
    finally:
        successor.unlink(missing_ok=True)
        dependent.unlink(missing_ok=True)
        fixture_root.rmdir()


@pytest.mark.parametrize(
    "delivery,allowed,bootstrap,ids",
    [
        ({"review_status": "pending"}, False, False, ("TASK-100", "TASK-101")),
        ({"review_status": "changes_requested"}, False, False, ("TASK-100", "TASK-101")),
        (
            {"review_status": "approved", "acceptance_status": "unverified"},
            False,
            False,
            ("TASK-100", "TASK-101"),
        ),
        (
            {"review_status": "reported_unverified", "acceptance_status": "passed"},
            False,
            False,
            ("TASK-100", "TASK-101"),
        ),
        (
            {
                "implementation_status": "merged",
                "acceptance_status": "passed",
                "review_status": "approved",
                "release_status": "prohibited",
            },
            True,
            False,
            ("TASK-100", "TASK-101"),
        ),
        (
            {
                "implementation_status": "merged",
                "acceptance_status": "passed",
                "review_status": "approved",
                "release_status": "eligible",
            },
            True,
            False,
            ("TASK-100", "TASK-101"),
        ),
        (
            {
                "implementation_status": "merged",
                "acceptance_status": "passed",
                "review_status": "approved",
                "release_status": "released",
            },
            True,
            False,
            ("TASK-100", "TASK-101"),
        ),
        (
            {"review_status": "reported_unverified", "acceptance_status": "unverified"},
            True,
            True,
            ("TASK-014", "TASK-031"),
        ),
    ],
)
def test_validate_tasks_dependency_gate(
    monkeypatch, isolated_task_root, delivery, allowed, bootstrap, ids
) -> None:
    fixture_root = isolated_task_root
    dependency_id, active_id = ids
    dependency = fixture_root / f"{dependency_id}.md"
    active = fixture_root / f"{active_id}.md"
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
    completion = ""
    acceptance = "## Acceptance criteria\n- [x] fixture evidence\n"
    if allowed and not bootstrap:
        completion = (
            "  completion_evidence:\n"
            "    mode: fixture\n"
            "    change_pr: https://github.com/example/repo/pull/100\n"
            "    reviewed_head_sha: " + "a" * 40 + "\n"
            "    review_verdict: APPROVE\n"
            "    reviewer: reviewer\n"
            "    evidence_url: https://github.com/example/review\n"
            "    merge_commit_sha: " + "b" * 40 + "\n"
            "    human_authorization_evidence: fixture\n"
        )
    dependency.write_text(
        f"---\nid: {dependency_id}\n{base}delivery:\n"
        + "\n".join(f"  {k}: {v}" for k, v in dep_delivery.items())
        + "\n"
        + completion
        + "---\n\n"
        + acceptance,
        encoding="utf-8",
    )
    active.write_text(
        f"---\nid: {active_id}\nstatus: active\ndepends_on: [{dependency_id}]\n"
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
                            "task_id": dependency_id,
                            "beneficiary_task": active_id,
                            "kind": "bootstrap_exception",
                            "one_time": True,
                            "deny_business_unlock": True,
                            "rule": "bootstrap",
                            "reason": "recovery",
                            "owner": "qfxyyy",
                            "expires_on": "2026-08-13",
                            "remediation_task": active_id,
                            "release_status": "prohibited",
                            "lifecycle_status": "active",
                        }
                    ]
                }
            return {"waivers": []}
        if path == validator.TASK_ROOT / "index.yaml":
            return {
                "tasks": [
                    {"id": dependency_id, "path": f"{dependency_id}.md", "status": "completed"},
                    {"id": active_id, "path": f"{active_id}.md", "status": "active"},
                ]
            }
        return original_load_yaml(path)

    monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
    errors: list[str] = []
    validate_tasks({}, errors, today=validator.date.fromisoformat("2026-08-06"))
    assert (not any("trusted completed delivery" in error for error in errors)) is allowed
    dependency.unlink(missing_ok=True)
    active.unlink(missing_ok=True)
    fixture_root.rmdir()


@pytest.mark.parametrize(
    "delivery_block",
    [
        "",
        (
            "delivery:\n  schema_version: 1\n  contract_status: accepted\n"
            "  implementation_status: merged\n  acceptance_status: partial\n"
            "  review_status: approved\n  release_status: prohibited\n"
        ),
        (
            "delivery:\n  schema_version: 1\n  contract_status: accepted\n"
            "  implementation_status: merged\n  acceptance_status: passed\n"
            "  review_status: approved\n  release_status: prohibited\n"
            "  completion_evidence: {review_verdict: BOGUS}\n"
        ),
    ],
)
def test_validate_tasks_rejects_non_governance_completed_delivery(
    monkeypatch, isolated_task_root, delivery_block
) -> None:
    fixture_root = isolated_task_root
    completed = fixture_root / "TASK-100.md"
    active = fixture_root / "TASK-101.md"
    try:
        completed.write_text(
            "---\nid: TASK-100\nstatus: completed\ndepends_on: []\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\n"
            + delivery_block
            + "---\n\n## Acceptance criteria\n- [x] fixture\n",
            encoding="utf-8",
        )
        active.write_text(
            "---\nid: TASK-101\nstatus: active\ndepends_on: [TASK-100]\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validator, "task_files", lambda: [completed, active])
        monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
        original_load_yaml = validator.load_yaml

        def fake_load_yaml(path):
            if path == validator.TASK_ROOT / "governance-waivers.yaml":
                return {"waivers": []}
            if path == validator.TASK_ROOT / "index.yaml":
                return {
                    "tasks": [
                        {"id": "TASK-100", "path": "TASK-100.md", "status": "completed"},
                        {"id": "TASK-101", "path": "TASK-101.md", "status": "active"},
                    ]
                }
            return original_load_yaml(path)

        monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
        errors: list[str] = []
        validate_tasks({}, errors)
        assert errors
        assert any("TASK-100" in error for error in errors)
    finally:
        completed.unlink(missing_ok=True)
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
        "lifecycle_status": "active",
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
    errors = []
    validate_waiver_entries([valid, valid], {"TASK-014", "TASK-031"}, errors)
    assert any("exactly one bootstrap_exception" in error for error in errors)
    errors = []
    validate_waiver_entries(
        [{**valid, "beneficiary_task": "TASK-005"}],
        {"TASK-005", "TASK-014", "TASK-031"},
        errors,
    )
    assert any("bootstrap field beneficiary_task" in error for error in errors)


@pytest.mark.parametrize(
    "lifecycle,extra,today,expected_error",
    [
        ("active", {}, "2026-08-06", False),
        ("active", {}, "2026-08-14", True),
        ("retired", {"retired_on": "2026-08-05"}, "2026-08-06", False),
        ("retired", {}, "2026-08-06", True),
        ("expired", {"expired_on": "2026-08-14"}, "2026-08-14", False),
        ("expired", {}, "2026-08-14", True),
    ],
)
def test_bootstrap_waiver_lifecycle_is_fail_closed(lifecycle, extra, today, expected_error) -> None:
    waiver = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "rule": "TASK031-only governance bootstrap for legacy dependency delivery",
        "reason": "recovery",
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
        "lifecycle_status": lifecycle,
        **extra,
    }
    errors: list[str] = []
    validate_waiver_entries(
        [waiver],
        {"TASK-014", "TASK-031"},
        errors,
        today=validator.date.fromisoformat(today),
    )
    assert bool(errors) is expected_error


def test_completed_bootstrap_remediation_requires_retirement() -> None:
    waiver = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "rule": "TASK031-only governance bootstrap for legacy dependency delivery",
        "reason": "recovery",
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
        "lifecycle_status": "active",
    }
    errors: list[str] = []
    validate_waiver_entries(
        [waiver],
        {"TASK-014", "TASK-031"},
        errors,
        today=validator.date.fromisoformat("2026-08-06"),
        task_statuses={"TASK-014": "completed", "TASK-031": "completed"},
    )
    assert any("completed remediation requires retired" in error for error in errors)


def test_ready_dependency_cannot_unlock_active_task(monkeypatch, isolated_task_root) -> None:
    fixture_root = isolated_task_root
    ready = fixture_root / "TASK-100.md"
    active = fixture_root / "TASK-101.md"
    try:
        ready.write_text(
            "---\nid: TASK-100\nstatus: ready\ndepends_on: []\nspec_refs: []\n"
            "allowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\n---\n",
            encoding="utf-8",
        )
        active.write_text(
            "---\nid: TASK-101\nstatus: active\ndepends_on: [TASK-100]\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validator, "task_files", lambda: [ready, active])
        monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
        original_load_yaml = validator.load_yaml

        def fake_load_yaml(path):
            if path == validator.TASK_ROOT / "governance-waivers.yaml":
                return {"schema_version": 1, "waivers": []}
            if path == validator.TASK_ROOT / "index.yaml":
                return {
                    "tasks": [
                        {"id": "TASK-100", "path": "TASK-100.md", "status": "ready"},
                        {"id": "TASK-101", "path": "TASK-101.md", "status": "active"},
                    ]
                }
            return original_load_yaml(path)

        monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
        errors: list[str] = []
        validate_tasks({}, errors)
        assert any(
            "TASK-101: dependency TASK-100 lacks trusted completed delivery" in error
            for error in errors
        )
    finally:
        ready.unlink(missing_ok=True)
        active.unlink(missing_ok=True)
        fixture_root.rmdir()


@pytest.mark.parametrize("variant", ["expired", "duplicate", "wrong_beneficiary", "retired"])
def test_invalid_or_terminal_bootstrap_cannot_unlock_via_validate_tasks(
    monkeypatch, isolated_task_root, variant
) -> None:
    fixture_root = isolated_task_root
    dependency = fixture_root / "TASK-014.md"
    active = fixture_root / "TASK-031.md"
    waiver = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "rule": "TASK031-only governance bootstrap for legacy dependency delivery",
        "reason": "recovery",
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
        "lifecycle_status": "active",
    }
    if variant == "expired":
        waiver["expires_on"] = "2020-01-01"
    elif variant == "wrong_beneficiary":
        waiver["beneficiary_task"] = "TASK-005"
    elif variant == "retired":
        waiver["lifecycle_status"] = "retired"
        waiver["retired_on"] = "2026-08-05"
    waivers = [waiver, waiver] if variant == "duplicate" else [waiver]
    try:
        dependency.write_text(
            "---\nid: TASK-014\nstatus: completed\ndepends_on: []\nspec_refs: []\n"
            "allowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\ndelivery:\n"
            "  schema_version: 1\n  contract_status: accepted\n"
            "  implementation_status: merged\n  acceptance_status: unverified\n"
            "  review_status: reported_unverified\n  release_status: prohibited\n"
            "  remediation_task: TASK-031\n  completion_evidence:\n"
            "    mode: historical\n    change_pr: unverifiable\n"
            "    reviewed_head_sha: unverifiable\n"
            "    review_verdict: reported_unverified\n    reviewer: unverifiable\n"
            "    evidence_url: unverifiable\n    merge_commit_sha: unverifiable\n"
            "    human_authorization_evidence: unverifiable\n"
            "---\n\n## Acceptance criteria\n- [ ] historical\n",
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
                return {"schema_version": 1, "waivers": waivers}
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
        validate_tasks({}, errors, today=validator.date.fromisoformat("2026-08-06"))
        assert any(
            "TASK-031: dependency TASK-014 lacks trusted completed delivery" in error
            for error in errors
        )
    finally:
        dependency.unlink(missing_ok=True)
        active.unlink(missing_ok=True)
        fixture_root.rmdir()
