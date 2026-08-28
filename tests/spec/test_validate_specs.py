from inspect import signature
from pathlib import Path

import pytest
import scripts.validate_specs as validator
import yaml
from scripts.validate_specs import (
    ROOT,
    bootstrap_allows_dependency,
    completion_evidence_is_trusted,
    delivery_is_unlockable,
    extract_front_matter,
    has_cycle,
    main,
    manifest_entries,
    validate_delivery,
    validate_l4_successor_dependencies,
    validate_risk_scope_successor_dependencies,
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


def write_governance_task_fixture(
    path: Path,
    task_id: str,
    status: str,
    depends_on: list[str],
    delivery: dict,
) -> None:
    task = {
        "id": task_id,
        "status": status,
        "depends_on": depends_on,
        "spec_refs": [],
        "allowed_paths": [],
        "forbidden_paths": [],
        "verification": {"commands": ["check"]},
        "delivery": delivery,
    }
    path.write_text(
        "---\n"
        + yaml.safe_dump(task, sort_keys=False)
        + "---\n\n## Acceptance criteria\n- [x] fixture\n",
        encoding="utf-8",
    )


def trusted_delivery(
    *,
    change_pr: str = "https://github.com/qifuxiao/QuantiQmt/pull/87",
    reviewed_head_sha: str = "0123456789abcdef0123456789abcdef01234567",
    reviewer: str = "independent-reviewer",
    evidence_url: str = ("https://github.com/qifuxiao/QuantiQmt/pull/87#pullrequestreview-99999"),
) -> dict:
    return {
        "schema_version": 1,
        "contract_status": "not_applicable",
        "implementation_status": "merged",
        "acceptance_status": "passed",
        "review_status": "approved",
        "release_status": "prohibited",
        "completion_evidence": {
            "mode": "governance_closeout_after_independent_review",
            "change_pr": change_pr,
            "reviewed_head_sha": reviewed_head_sha,
            "review_verdict": "APPROVE",
            "reviewer": reviewer,
            "evidence_url": evidence_url,
            "merge_commit_sha": "89abcdef0123456789abcdef0123456789abcdef",
            "human_authorization_evidence": (
                "github-merge:qifuxiao/QuantiQmt#87:"
                "89abcdef0123456789abcdef0123456789abcdef:qifuxiao"
            ),
        },
    }


def risk_scope_evidence_binding() -> dict:
    return {
        "schema_version": 1,
        "audit_task": "TASK-051",
        "successor_evidence_binding": {
            "task_id": "TASK-051",
            "beneficiary_task": "TASK-029",
            "repository": "qifuxiao/QuantiQmt",
            "pull_request_number": 87,
            "change_pr": "https://github.com/qifuxiao/QuantiQmt/pull/87",
            "implementation_identity": {
                "agent": "codex-task-051-implementing-agent",
                "pull_request_author": "qifuxiao",
            },
            "required_review": {
                "verdict": "APPROVE",
                "reviewer": "independent-reviewer",
                "reviewed_head_sha": "0123456789abcdef0123456789abcdef01234567",
                "evidence_url": (
                    "https://github.com/qifuxiao/QuantiQmt/pull/87#pullrequestreview-99999"
                ),
            },
            "required_merge": {"merge_commit_sha": "89abcdef0123456789abcdef0123456789abcdef"},
            "human_authorization_evidence": (
                "github-merge:qifuxiao/QuantiQmt#87:"
                "89abcdef0123456789abcdef0123456789abcdef:qifuxiao"
            ),
            "external_fact_status": "recorded_after_github_and_human_verification",
            "static_validator_boundary": {
                "verifies": [
                    "completion evidence exactly matches this TASK-051 binding",
                    "repository and change PR are qifuxiao/QuantiQmt PR 87",
                    "Review evidence URL is a PR 87 pullrequestreview URL",
                    (
                        "reviewer is a valid bound GitHub login distinct from implementation "
                        "agent and PR author"
                    ),
                    (
                        "reviewed Head and merge commit are non-placeholder 40-character "
                        "hexadecimal SHAs"
                    ),
                    "external facts have been recorded as verified before dependency unlock",
                ],
                "does_not_verify": [
                    (
                        "GitHub Review existence, verdict, reviewer identity or reviewed Head "
                        "via network"
                    ),
                    "GitHub merge existence or merge commit ancestry via network",
                    "human closeout authorization authenticity outside the repository",
                ],
                "external_confirmation_required": [
                    "independent reviewer verifies APPROVE on the exact current PR Head in GitHub",
                    "human verifies merge and authorizes active-to-completed closeout",
                ],
            },
            "production_external_verifier": {
                "adapter": "fixed_github_public_api_task_051_verifier",
                "endpoints": [
                    "https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/87",
                    "https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/87/reviews",
                ],
                "timeout_seconds": 2,
                "verifies": [
                    "closed_merged_PR_87_on_main",
                    "exact_PR_head_and_merge_commit",
                    "APPROVED_review_URL_reviewer_and_commit",
                    "reviewer_independent_from_PR_author_and_implementer",
                    "human_authorization_bound_to_merged_by_and_merge_commit",
                    "local_git_merge_ancestry",
                ],
                "failure_policy": "network_timeout_rate_limit_404_invalid_json_or_mismatch_denies",
            },
        },
    }


class FixtureGitHubTransport:
    """Deterministic API fixture used below the production verifier boundary."""

    def __init__(self, payloads: dict[str, object], failure: Exception | None = None) -> None:
        self.payloads = payloads
        self.failure = failure
        self.calls: list[tuple[str, float]] = []

    def get_json(self, url: str, timeout_seconds: float) -> object:
        self.calls.append((url, timeout_seconds))
        if self.failure is not None:
            raise self.failure
        return self.payloads[url]


class FixtureGitHubVerifier(validator.GitHubRiskScopeVerifier):
    transport: FixtureGitHubTransport

    def __init__(self, transport: FixtureGitHubTransport) -> None:
        self.transport = transport
        super().__init__(transport=transport)

    def _verify_merge_ancestry(self, reviewed_head: str, merge_commit: str) -> bool:
        return reviewed_head != merge_commit


def install_fixture_verifier(
    monkeypatch: pytest.MonkeyPatch, transport: FixtureGitHubTransport
) -> None:
    class BoundFixtureVerifier(FixtureGitHubVerifier):
        def __init__(self) -> None:
            super().__init__(transport)

    monkeypatch.setattr(validator, "GitHubRiskScopeVerifier", BoundFixtureVerifier)


def github_fixture_transport(delivery: dict) -> FixtureGitHubTransport:
    evidence = delivery["completion_evidence"]
    review_url = evidence["evidence_url"]
    api_pr = "https://api.github.com/repos/qifuxiao/QuantiQmt/pulls/87"
    api_reviews = f"{api_pr}/reviews"
    return FixtureGitHubTransport(
        {
            api_pr: {
                "html_url": "https://github.com/qifuxiao/QuantiQmt/pull/87",
                "number": 87,
                "state": "closed",
                "merged": True,
                "base": {"ref": "main", "repo": {"full_name": "qifuxiao/QuantiQmt"}},
                "head": {"sha": evidence["reviewed_head_sha"]},
                "merge_commit_sha": evidence["merge_commit_sha"],
                "user": {"login": "qifuxiao", "type": "User"},
                "merged_by": {"login": "qifuxiao", "type": "User"},
            },
            api_reviews: [
                {
                    "html_url": review_url,
                    "pull_request_url": api_pr,
                    "state": "APPROVED",
                    "commit_id": evidence["reviewed_head_sha"],
                    "user": {"login": evidence["reviewer"], "type": "User"},
                }
            ],
        }
    )


def run_risk_scope_validate_tasks_fixture(
    monkeypatch: pytest.MonkeyPatch,
    task_root: Path,
    *,
    task029_dependencies: list[str] | None = None,
    task051_delivery: dict | None = None,
    task030_delivery_overrides: dict | None = None,
    include_task030: bool = True,
    governance_binding: dict | None = None,
    task029_status: str = "active",
) -> list[str]:
    task029_dependencies = task029_dependencies or ["TASK-015", "TASK-031", "TASK-051"]
    task051_delivery = task051_delivery or trusted_delivery()
    governance_binding = governance_binding or risk_scope_evidence_binding()
    completed_dependency = {
        "schema_version": 1,
        "contract_status": "not_applicable",
        "implementation_status": "merged",
        "acceptance_status": "passed",
        "review_status": "approved",
        "release_status": "prohibited",
        "completion_evidence": {
            "mode": "fixture",
            "change_pr": "https://github.com/example/repo/pull/1",
            "reviewed_head_sha": "a" * 40,
            "review_verdict": "APPROVE",
            "reviewer": "reviewer",
            "evidence_url": "https://github.com/example/repo/pull/1#pullrequestreview-1",
            "merge_commit_sha": "b" * 40,
            "human_authorization_evidence": "fixture",
        },
    }
    task030_delivery = {
        "schema_version": 1,
        "contract_status": "accepted",
        "implementation_status": "merged",
        "acceptance_status": "unverified",
        "review_status": "reported_unverified",
        "release_status": "prohibited",
        "remediation_task": "TASK-031",
        "completion_evidence": {
            "mode": "historical_git_verified_review_unavailable",
            "change_pr": "https://github.com/qifuxiao/QuantiQmt/pull/44",
            "reviewed_head_sha": "e7c087fc1292f1c57d8352112802ed60f99e9466",
            "review_verdict": "reported_unverified",
            "reviewer": "unverifiable",
            "evidence_url": "unverifiable",
            "merge_commit_sha": "238b0ac2c3c82de88c59a900feca8cbb71d38863",
            "human_authorization_evidence": "unverifiable",
        },
    }
    task030_delivery.update(task030_delivery_overrides or {})
    task_documents = {
        "TASK-015": ("completed", [], completed_dependency),
        "TASK-031": ("completed", [], completed_dependency),
        "TASK-044": ("completed", [], completed_dependency),
        "TASK-051": ("completed", ["TASK-015", "TASK-031", "TASK-044"], task051_delivery),
        "TASK-029": (
            task029_status,
            task029_dependencies,
            {
                "schema_version": 1,
                "contract_status": "accepted",
                "implementation_status": "in_progress",
                "acceptance_status": "unverified",
                "review_status": "pending",
                "release_status": "prohibited",
            },
        ),
    }
    if include_task030:
        task_documents["TASK-030"] = ("completed", ["TASK-015"], task030_delivery)

    paths = []
    index_entries = []
    for task_id, (status, dependencies, delivery) in task_documents.items():
        path = task_root / f"{task_id}.md"
        write_governance_task_fixture(path, task_id, status, dependencies, delivery)
        paths.append(path)
        index_entries.append(
            {"id": task_id, "path": path.name, "status": status, "depends_on": dependencies}
        )

    monkeypatch.setattr(validator, "task_files", lambda: paths)
    monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
    original_load_yaml = validator.load_yaml

    def fake_load_yaml(path):
        if path == validator.TASK_ROOT / "governance-waivers.yaml":
            return {"schema_version": 1, "waivers": []}
        if path == validator.TASK_ROOT / "index.yaml":
            return {"tasks": index_entries}
        if path == validator.RISK_SCOPE_GOVERNANCE_PATH:
            return governance_binding
        return original_load_yaml(path)

    monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
    errors: list[str] = []
    validate_tasks({}, errors)
    return errors


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


def test_l4_queue_and_risk_scope_use_independent_successor_gates() -> None:
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
    assert "TASK-051" in task029["depends_on"]
    assert "TASK-030" not in task029["depends_on"]
    assert "TASK-046" not in task029["depends_on"]

    task030 = extract_front_matter(indexed_task_path("TASK-030"))
    assert task030["delivery"]["review_status"] == "reported_unverified"
    assert task030["delivery"]["release_status"] == "prohibited"

    task051 = extract_front_matter(indexed_task_path("TASK-051"))
    assert task051["delivery"]["schema_version"] == 1
    assert task051["delivery"]["release_status"] == "prohibited"
    if task051["status"] == "active":
        assert task051["delivery"]["review_status"] == "pending"
        assert not delivery_is_unlockable(task051)
    else:
        assert task051["status"] == "completed"
        assert delivery_is_unlockable(task051)


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
        },
        errors,
    )
    assert any("TASK-017: historical TASK-014" in error for error in errors)
    assert any("TASK-017: missing TASK-046" in error for error in errors)


@pytest.mark.parametrize("replacement", ["TASK-030", "TASK-046"])
def test_risk_scope_successor_policy_rejects_historical_or_unrelated_gate(
    replacement: str,
) -> None:
    errors: list[str] = []
    validate_risk_scope_successor_dependencies(
        {
            "TASK-029": {"depends_on": ["TASK-015", replacement, "TASK-031"]},
            "TASK-030": {
                "status": "completed",
                "delivery": {
                    "review_status": "reported_unverified",
                    "release_status": "prohibited",
                },
            },
        },
        errors,
    )
    assert any("TASK-029: missing TASK-051" in error for error in errors)
    assert any(
        f"TASK-029: {replacement} cannot replace or bypass TASK-051" in error for error in errors
    )


@pytest.mark.parametrize(
    "review_status,release_status",
    [("approved", "prohibited"), ("reported_unverified", "eligible")],
)
def test_risk_scope_successor_policy_preserves_task030_history(
    review_status: str, release_status: str
) -> None:
    errors: list[str] = []
    validate_risk_scope_successor_dependencies(
        {
            "TASK-029": {"depends_on": ["TASK-015", "TASK-031", "TASK-051"]},
            "TASK-030": {
                "status": "completed",
                "delivery": {
                    "review_status": review_status,
                    "release_status": release_status,
                },
            },
            "TASK-051": {"depends_on": ["TASK-015", "TASK-031", "TASK-044"]},
        },
        errors,
    )
    review_history_changed = any(
        "TASK-030 historical review must remain reported_unverified" in error for error in errors
    )
    release_history_changed = any(
        "TASK-030 historical release must remain prohibited" in error for error in errors
    )
    assert review_history_changed is (review_status != "reported_unverified")
    assert release_history_changed is (release_status != "prohibited")


@pytest.mark.parametrize(
    "forgery",
    [
        "wrong_pr",
        "fabricated_shas",
        "implementing_reviewer",
        "pr_author_reviewer",
        "invalid_review_url",
    ],
)
def test_task051_forged_evidence_is_rejected_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
    forgery: str,
) -> None:
    delivery = trusted_delivery()
    evidence = delivery["completion_evidence"]
    binding = risk_scope_evidence_binding()
    bound_evidence = binding["successor_evidence_binding"]
    if forgery == "wrong_pr":
        evidence["change_pr"] = "https://github.com/example/repo/pull/999"
        bound_evidence["change_pr"] = "https://github.com/example/repo/pull/999"
    elif forgery == "fabricated_shas":
        evidence["reviewed_head_sha"] = "deadbeef" * 5
        evidence["merge_commit_sha"] = "0123456789" * 4
        bound_evidence["required_review"]["reviewed_head_sha"] = "deadbeef" * 5
        bound_evidence["required_merge"]["merge_commit_sha"] = "0123456789" * 4
    elif forgery == "implementing_reviewer":
        evidence["reviewer"] = "codex-task-051-implementing-agent"
        bound_evidence["required_review"]["reviewer"] = "codex-task-051-implementing-agent"
    elif forgery == "pr_author_reviewer":
        evidence["reviewer"] = "qifuxiao"
        bound_evidence["required_review"]["reviewer"] = "qifuxiao"
    else:
        evidence["evidence_url"] = "https://github.com/example/review/87"
        bound_evidence["required_review"]["evidence_url"] = "https://github.com/example/review/87"

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task051_delivery=delivery,
        governance_binding=binding,
    )

    assert any(
        "TASK-051 evidence does not match its governance binding" in error for error in errors
    )
    assert any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )
    assert not completion_evidence_is_trusted(
        delivery,
        task_id="TASK-051",
        evidence_binding=binding["successor_evidence_binding"],
    )


def test_task051_placeholder_reviewer_is_rejected_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    delivery = trusted_delivery(reviewer="pending-reviewer")
    binding = risk_scope_evidence_binding()
    binding["successor_evidence_binding"]["required_review"]["reviewer"] = "pending-reviewer"

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task051_delivery=delivery,
        governance_binding=binding,
    )

    assert any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )


def test_task051_completed_delivery_is_denied_without_external_verifier(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(monkeypatch, isolated_task_root)

    assert any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )


def test_task051_simultaneous_local_binding_forgery_is_denied(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    delivery = trusted_delivery(reviewer="mallory-reviewer")
    evidence = delivery["completion_evidence"]
    evidence["reviewed_head_sha"] = "0123456789abcdef0123456789abcdef01234567"
    evidence["evidence_url"] = (
        "https://github.com/qifuxiao/QuantiQmt/pull/87#pullrequestreview-999999"
    )
    evidence["human_authorization_evidence"] = "forged local authorization"
    binding = risk_scope_evidence_binding()
    required_review = binding["successor_evidence_binding"]["required_review"]
    required_review["reviewer"] = evidence["reviewer"]
    required_review["reviewed_head_sha"] = evidence["reviewed_head_sha"]
    required_review["evidence_url"] = evidence["evidence_url"]
    binding["successor_evidence_binding"]["human_authorization_evidence"] = evidence[
        "human_authorization_evidence"
    ]

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task051_delivery=delivery,
        governance_binding=binding,
    )

    assert any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )


def test_task051_completed_delivery_and_human_active_task029_use_github_verifier(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    delivery = trusted_delivery()
    transport = github_fixture_transport(delivery)
    install_fixture_verifier(monkeypatch, transport)

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task051_delivery=delivery,
        task029_status="active",
    )

    assert not any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )
    assert transport.calls
    assert all(
        timeout <= validator.RISK_SCOPE_EXTERNAL_TIMEOUT_SECONDS for _, timeout in transport.calls
    )


def test_validate_tasks_has_no_public_boolean_verifier_injection() -> None:
    assert "external_fact_verifier" not in signature(validate_tasks).parameters


def test_task029_blocked_does_not_auto_activate_after_trusted_closeout(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    delivery = trusted_delivery()
    transport = github_fixture_transport(delivery)
    install_fixture_verifier(monkeypatch, transport)
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task051_delivery=delivery,
        task029_status="blocked",
    )
    assert not any("TASK-029: dependency" in error for error in errors)
    assert transport.calls


@pytest.mark.parametrize(
    "failure",
    [
        OSError("network down"),
        TimeoutError("timed out"),
        ValueError("invalid JSON"),
        validator.urllib.error.HTTPError("url", 404, "not found", {}, None),
        validator.urllib.error.HTTPError("url", 429, "rate limited", {}, None),
    ],
)
def test_github_verifier_external_failures_are_fail_closed(failure: Exception) -> None:
    delivery = trusted_delivery()
    binding = risk_scope_evidence_binding()["successor_evidence_binding"]
    transport = FixtureGitHubTransport({}, failure=failure)
    verifier = validator.GitHubRiskScopeVerifier(transport=transport, timeout_seconds=0.1)
    assert not verifier.verify(binding, delivery["completion_evidence"])
    assert transport.calls
    assert all(timeout <= 0.1 for _, timeout in transport.calls)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_pr",
        "wrong_head",
        "wrong_merge",
        "wrong_reviewer",
        "wrong_author",
        "wrong_review_url",
        "not_approved",
        "wrong_human_authorization",
        "ancestry",
    ],
)
def test_github_verifier_rejects_external_fact_mutations(mutation: str) -> None:
    delivery = trusted_delivery()
    binding = risk_scope_evidence_binding()["successor_evidence_binding"]
    transport = github_fixture_transport(delivery)
    pull_url = validator.RISK_SCOPE_GITHUB_API_PR_URL
    reviews_url = f"{pull_url}/reviews"
    if mutation == "wrong_pr":
        transport.payloads[pull_url]["number"] = 86
    elif mutation == "wrong_head":
        transport.payloads[pull_url]["head"]["sha"] = "f" * 40
    elif mutation == "wrong_merge":
        transport.payloads[pull_url]["merge_commit_sha"] = "e" * 40
    elif mutation == "wrong_reviewer":
        transport.payloads[reviews_url][0]["user"]["login"] = "mallory"
    elif mutation == "wrong_author":
        transport.payloads[pull_url]["user"]["login"] = "mallory"
    elif mutation == "wrong_review_url":
        transport.payloads[reviews_url][0]["html_url"] = (
            validator.RISK_SCOPE_PR_URL + "#pullrequestreview-1"
        )
    elif mutation == "not_approved":
        transport.payloads[reviews_url][0]["state"] = "CHANGES_REQUESTED"
    elif mutation == "wrong_human_authorization":
        binding["human_authorization_evidence"] = "local-admin-approved"
    else:

        class AncestryFailureVerifier(FixtureGitHubVerifier):
            def _verify_merge_ancestry(self, reviewed_head: str, merge_commit: str) -> bool:
                return False

        verifier = AncestryFailureVerifier(transport)
        assert not verifier.verify(binding, delivery["completion_evidence"])
        return
    verifier = FixtureGitHubVerifier(transport)
    assert not verifier.verify(binding, delivery["completion_evidence"])


def test_task051_boundary_must_explicitly_model_external_facts(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    binding = risk_scope_evidence_binding()
    boundary = binding["successor_evidence_binding"]["static_validator_boundary"]
    boundary["does_not_verify"] = ["external facts"]

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        governance_binding=binding,
    )

    assert any("static validator boundary" in error for error in errors)


@pytest.mark.parametrize("removed_dependency", ["TASK-015", "TASK-031"])
def test_task029_required_dependencies_are_enforced_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
    removed_dependency: str,
) -> None:
    dependencies = ["TASK-015", "TASK-031", "TASK-051"]
    dependencies.remove(removed_dependency)

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task029_dependencies=dependencies,
    )

    assert any(
        "TASK-029: required scope dependencies must be TASK-015, TASK-031, TASK-051" in error
        for error in errors
    )


def test_task030_history_record_is_required_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        include_task030=False,
    )

    assert any("TASK-030 historical record must remain present" in error for error in errors)


def test_task030_acceptance_cannot_be_promoted_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task030_delivery_overrides={"acceptance_status": "passed"},
    )

    assert any("TASK-030 historical acceptance must remain unverified" in error for error in errors)


def test_task030_historical_review_evidence_cannot_be_promoted_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task030_delivery_overrides={
            "completion_evidence": {
                "mode": "historical_git_verified_review_unavailable",
                "change_pr": "https://github.com/qifuxiao/QuantiQmt/pull/44",
                "reviewed_head_sha": "e7c087fc1292f1c57d8352112802ed60f99e9466",
                "review_verdict": "APPROVE",
                "reviewer": "independent-reviewer",
                "evidence_url": "https://github.com/qifuxiao/QuantiQmt/pull/44#pullrequestreview-1",
                "merge_commit_sha": "238b0ac2c3c82de88c59a900feca8cbb71d38863",
                "human_authorization_evidence": "human-authorized",
            }
        },
    )

    assert any("TASK-030 historical completion evidence" in error for error in errors)


@pytest.mark.parametrize("field", ["change_pr", "reviewed_head_sha", "merge_commit_sha"])
def test_task030_all_historical_completion_facts_are_frozen_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
    field: str,
) -> None:
    historical = {
        "mode": "historical_git_verified_review_unavailable",
        "change_pr": "https://github.com/qifuxiao/QuantiQmt/pull/44",
        "reviewed_head_sha": "e7c087fc1292f1c57d8352112802ed60f99e9466",
        "review_verdict": "reported_unverified",
        "reviewer": "unverifiable",
        "evidence_url": "unverifiable",
        "merge_commit_sha": "238b0ac2c3c82de88c59a900feca8cbb71d38863",
        "human_authorization_evidence": "unverifiable",
    }
    historical[field] = {
        "change_pr": "https://github.com/example/repo/pull/999",
        "reviewed_head_sha": "0123456789012345678901234567890123456789",
        "merge_commit_sha": "abcdef0123456789abcdef0123456789abcdef01",
    }[field]

    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task030_delivery_overrides={"completion_evidence": historical},
    )

    assert any(
        f"TASK-030 historical completion evidence {field} must remain" in error for error in errors
    )


def test_task029_human_activation_without_external_facts_is_denied(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task029_dependencies=["TASK-015", "TASK-031", "TASK-051"],
    )
    assert any(
        "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
        for error in errors
    )


@pytest.mark.parametrize("replacement", ["TASK-030", "TASK-046"])
def test_risk_scope_bypass_is_rejected_via_validate_tasks(
    monkeypatch: pytest.MonkeyPatch,
    isolated_task_root: Path,
    replacement: str,
) -> None:
    errors = run_risk_scope_validate_tasks_fixture(
        monkeypatch,
        isolated_task_root,
        task029_dependencies=["TASK-015", "TASK-031", replacement],
    )

    assert any(
        f"TASK-029: {replacement} cannot replace or bypass TASK-051" in error for error in errors
    )


@pytest.mark.parametrize(
    "successor_state,activation_allowed",
    [
        ("active", False),
        ("reported_unverified", False),
        ("missing_evidence", False),
        ("trusted_completed", True),
    ],
)
def test_task051_risk_scope_gate_requires_trusted_completed_delivery(
    monkeypatch, isolated_task_root, successor_state, activation_allowed
) -> None:
    fixture_root = isolated_task_root
    successor = fixture_root / "TASK-051.md"
    dependent = fixture_root / "TASK-029.md"
    historical = fixture_root / "TASK-030.md"
    trusted_evidence = (
        "  completion_evidence:\n"
        "    mode: governance_closeout_after_independent_review\n"
        "    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/87\n"
        "    reviewed_head_sha: 0123456789abcdef0123456789abcdef01234567\n"
        "    review_verdict: APPROVE\n"
        "    reviewer: independent-reviewer\n"
        "    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/87"
        "#pullrequestreview-99999\n"
        "    merge_commit_sha: 89abcdef0123456789abcdef0123456789abcdef\n"
        "    human_authorization_evidence: github-merge:qifuxiao/QuantiQmt#87:"
        "89abcdef0123456789abcdef0123456789abcdef:qifuxiao\n"
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
            "  remediation_task: TASK-051\n"
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
            f"---\nid: TASK-051\nstatus: {successor_status}\ndepends_on: []\n"
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
            "---\nid: TASK-029\nstatus: active\ndepends_on: [TASK-051]\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\ndelivery:\n"
            "  schema_version: 1\n  contract_status: accepted\n"
            "  implementation_status: in_progress\n  acceptance_status: not_run\n"
            "  review_status: pending\n  release_status: prohibited\n---\n",
            encoding="utf-8",
        )
        historical.write_text(
            "---\nid: TASK-030\nstatus: completed\ndepends_on: []\n"
            "spec_refs: []\nallowed_paths: []\nforbidden_paths: []\n"
            "verification: {commands: [check]}\ndelivery:\n"
            "  schema_version: 1\n  contract_status: accepted\n"
            "  implementation_status: merged\n  acceptance_status: unverified\n"
            "  review_status: reported_unverified\n  release_status: prohibited\n"
            "  remediation_task: TASK-051\n  completion_evidence:\n"
            "    mode: historical\n    change_pr: unverifiable\n"
            "    reviewed_head_sha: unverifiable\n"
            "    review_verdict: reported_unverified\n    reviewer: unverifiable\n"
            "    evidence_url: unverifiable\n    merge_commit_sha: unverifiable\n"
            "    human_authorization_evidence: unverifiable\n"
            "---\n\n## Acceptance criteria\n- [ ] historical\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validator, "task_files", lambda: [successor, dependent, historical])
        monkeypatch.setattr(validator, "validate_active_readme", lambda tasks, errors: None)
        original_load_yaml = validator.load_yaml

        def fake_load_yaml(path):
            if path == validator.TASK_ROOT / "governance-waivers.yaml":
                return {"schema_version": 1, "waivers": []}
            if path == validator.TASK_ROOT / "index.yaml":
                return {
                    "tasks": [
                        {"id": "TASK-051", "path": "TASK-051.md", "status": successor_status},
                        {"id": "TASK-029", "path": "TASK-029.md", "status": "active"},
                        {"id": "TASK-030", "path": "TASK-030.md", "status": "completed"},
                    ]
                }
            if path == validator.RISK_SCOPE_GOVERNANCE_PATH:
                return risk_scope_evidence_binding()
            return original_load_yaml(path)

        monkeypatch.setattr(validator, "load_yaml", fake_load_yaml)
        if successor_state == "trusted_completed":
            transport = github_fixture_transport(trusted_delivery())

            class StateFixtureVerifier(FixtureGitHubVerifier):
                def __init__(self) -> None:
                    super().__init__(transport)

            monkeypatch.setattr(validator, "GitHubRiskScopeVerifier", StateFixtureVerifier)
        errors: list[str] = []
        validate_tasks({}, errors)
        denied = any(
            "TASK-029: dependency TASK-051 lacks trusted completed delivery" in error
            for error in errors
        )
        assert denied is not activation_allowed
    finally:
        successor.unlink(missing_ok=True)
        dependent.unlink(missing_ok=True)
        historical.unlink(missing_ok=True)
        fixture_root.rmdir()


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
