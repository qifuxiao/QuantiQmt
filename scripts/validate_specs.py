"""Validate normative specifications and AI task metadata."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "spec"
TASK_ROOT = ROOT / "tasks"
TASK_STATES = {"blocked", "ready", "active", "completed"}
DELIVERY_AXES = {
    "contract_status": {"not_applicable", "draft", "accepted", "superseded"},
    "implementation_status": {"not_applicable", "not_started", "in_progress", "merged"},
    "acceptance_status": {"not_run", "partial", "passed", "unverified"},
    "review_status": {
        "not_required",
        "pending",
        "changes_requested",
        "approved",
        "reported_unverified",
    },
    "release_status": {"not_applicable", "prohibited", "eligible", "released"},
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"^https?://[^\s]+$")
PR_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/\d+$")
GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
COMPLETION_FIELDS = {
    "mode",
    "change_pr",
    "reviewed_head_sha",
    "review_verdict",
    "reviewer",
    "evidence_url",
    "merge_commit_sha",
    "human_authorization_evidence",
}
WAIVER_LIFECYCLE_STATES = {"active", "retired", "expired"}
L4_READINESS_SUCCESSOR = "TASK-046"
L4_SUCCESSOR_TASKS = frozenset(
    {"TASK-017", "TASK-018", "TASK-019", "TASK-020", "TASK-021", "TASK-022"}
)
RISK_SCOPE_SUCCESSOR = "TASK-051"
RISK_HISTORICAL_SCOPE_TASK = "TASK-030"
RISK_SCOPE_REQUIRED_DEPENDENCIES = frozenset({"TASK-015", "TASK-031", "TASK-051"})
RISK_SCOPE_GOVERNANCE_PATH = (
    ROOT / "ai" / "governance" / "risk-validator-integration-scope-task-051.yaml"
)
RISK_SCOPE_REPOSITORY = "qifuxiao/QuantiQmt"
RISK_SCOPE_PR_NUMBER = 87
RISK_SCOPE_PR_URL = "https://github.com/qifuxiao/QuantiQmt/pull/87"
RISK_SCOPE_IMPLEMENTING_AGENT = "codex-task-051-implementing-agent"
RISK_SCOPE_PR_AUTHOR = "qifuxiao"
RISK_SCOPE_EXTERNAL_FACT_STATUS = "recorded_after_github_and_human_verification"
RISK_SCOPE_COMPLETION_MODE = "governance_closeout_after_independent_review"
RISK_SCOPE_PENDING_REVIEWER = "pending_independent_github_reviewer"
RISK_SCOPE_PENDING_REVIEWED_HEAD = "pending_exact_reviewed_head"
RISK_SCOPE_PENDING_REVIEW_URL = "pending_github_pull_request_review_url"
RISK_SCOPE_PENDING_MERGE = "pending_merge_commit"
RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION = "pending_human_closeout_authorization"
RISK_SCOPE_BOUNDARY_REQUIREMENTS = {
    "verifies": {
        "completion evidence exactly matches this TASK-051 binding",
        "repository and change PR are qifuxiao/QuantiQmt PR 87",
        "Review evidence URL is a PR 87 pullrequestreview URL",
        "reviewer is a valid bound GitHub login distinct from implementation agent and PR author",
        "reviewed Head and merge commit are non-placeholder 40-character hexadecimal SHAs",
        "external facts have been recorded as verified before dependency unlock",
    },
    "does_not_verify": {
        "GitHub Review existence, verdict, reviewer identity or reviewed Head via network",
        "GitHub merge existence or merge commit ancestry via network",
        "human closeout authorization authenticity outside the repository",
    },
    "external_confirmation_required": {
        "independent reviewer verifies APPROVE on the exact current PR Head in GitHub",
        "human verifies merge and authorizes active-to-completed closeout",
    },
}
RISK_HISTORICAL_DELIVERY = {
    "schema_version": 1,
    "contract_status": "accepted",
    "implementation_status": "merged",
    "acceptance_status": "unverified",
    "review_status": "reported_unverified",
    "release_status": "prohibited",
    "remediation_task": "TASK-031",
}


def load_yaml(path: Path) -> Any:
    """Load one YAML document."""
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_json(path: Path) -> Any:
    """Load one JSON document."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def extract_front_matter(path: Path) -> dict[str, Any]:
    """Parse YAML front matter from a Markdown task."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if match is None:
        raise ValueError("missing YAML front matter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("front matter must be a mapping")
    return value


def manifest_entries(manifest: dict[str, Any]) -> dict[str, Path]:
    """Return all manifest IDs and their resolved paths."""
    result: dict[str, Path] = {}
    catalogs = manifest.get("catalogs")
    if not isinstance(catalogs, dict):
        return result
    for entries in catalogs.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            spec_id = entry.get("id")
            relative_path = entry.get("path")
            if isinstance(spec_id, str) and isinstance(relative_path, str):
                result[spec_id] = SPEC_ROOT / relative_path
    return result


def has_cycle(graph: dict[str, list[str]]) -> bool:
    """Return True when a dependency graph contains a cycle."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def task_files() -> Iterable[Path]:
    """Yield executable task Markdown files."""
    for state in ("backlog", "active", "completed"):
        yield from sorted((TASK_ROOT / state).glob("TASK-*.md"))


def validate_delivery(task_id: str, task: dict[str, Any], path: Path, errors: list[str]) -> None:
    """Validate the independent governance delivery axes and evidence."""
    delivery = task.get("delivery")
    if delivery is None:
        if task.get("status") == "completed":
            errors.append(f"{path.relative_to(ROOT)}: completed task requires delivery metadata")
        return
    if not isinstance(delivery, dict) or delivery.get("schema_version") != 1:
        errors.append(f"{path.relative_to(ROOT)}: delivery.schema_version must be 1")
        return
    for axis, allowed in DELIVERY_AXES.items():
        if delivery.get(axis) not in allowed:
            errors.append(f"{path.relative_to(ROOT)}: invalid delivery {axis}")
    status = task.get("status")
    review = delivery.get("review_status")
    release = delivery.get("release_status")
    if (
        status == "completed"
        and review != "reported_unverified"
        and (
            delivery.get("acceptance_status") != "passed"
            or delivery.get("review_status") not in {"approved", "not_required"}
            or delivery.get("implementation_status") not in {"merged", "not_applicable"}
        )
    ):
        errors.append(f"{path.relative_to(ROOT)}: completed task has invalid delivery combination")
    if review == "reported_unverified":
        if release != "prohibited":
            errors.append(
                f"{path.relative_to(ROOT)}: reported_unverified requires prohibited release"
            )
        if not delivery.get("remediation_task") and not delivery.get("waiver_id"):
            errors.append(
                f"{path.relative_to(ROOT)}: reported_unverified requires remediation_task "
                "or waiver_id"
            )
    if release in {"eligible", "released"} and review == "reported_unverified":
        errors.append(f"{path.relative_to(ROOT)}: unverifiable review cannot unlock or release")
    if status == "completed":
        body = path.read_text(encoding="utf-8")
        if "## Acceptance criteria" not in body:
            errors.append(f"{path.relative_to(ROOT)}: completed task lacks Acceptance criteria")
        elif review != "reported_unverified" and "[x]" not in body:
            errors.append(
                f"{path.relative_to(ROOT)}: completed task lacks checked acceptance evidence"
            )
        evidence = delivery.get("completion_evidence")
        if not isinstance(evidence, dict) or not COMPLETION_FIELDS.issubset(evidence):
            errors.append(f"{path.relative_to(ROOT)}: incomplete completion_evidence")
        else:
            for field in COMPLETION_FIELDS:
                if not isinstance(evidence.get(field), str) or not evidence[field].strip():
                    errors.append(f"{path.relative_to(ROOT)}: empty completion evidence {field}")
            if review == "reported_unverified":
                if evidence.get("review_verdict") != "reported_unverified":
                    errors.append(
                        f"{path.relative_to(ROOT)}: unverified evidence requires "
                        "reported_unverified verdict"
                    )
            else:
                if evidence.get("review_verdict") not in {"APPROVE", "NOT_REQUIRED"}:
                    errors.append(
                        f"{path.relative_to(ROOT)}: review_verdict must be APPROVE or NOT_REQUIRED"
                    )
                for field in ("reviewed_head_sha", "merge_commit_sha"):
                    if not SHA_RE.fullmatch(str(evidence.get(field))):
                        errors.append(f"{path.relative_to(ROOT)}: invalid evidence SHA {field}")
                if not PR_RE.fullmatch(str(evidence.get("change_pr"))):
                    errors.append(f"{path.relative_to(ROOT)}: change_pr must be a GitHub PR URL")
                if not URL_RE.fullmatch(str(evidence.get("evidence_url"))):
                    errors.append(f"{path.relative_to(ROOT)}: evidence_url must be an HTTP(S) URL")
                if evidence.get("reviewer") in {"unverifiable", "reported_unverified"}:
                    errors.append(
                        f"{path.relative_to(ROOT)}: approved evidence requires a reviewer"
                    )


def validate_waiver_entries(
    waivers: list[Any],
    known_task_ids: set[str],
    errors: list[str],
    today: date | None = None,
    task_statuses: dict[str, str] | None = None,
) -> None:
    today = today or date.today()
    required = {
        "task_id",
        "beneficiary_task",
        "rule",
        "reason",
        "owner",
        "expires_on",
        "remediation_task",
        "release_status",
        "kind",
        "one_time",
        "deny_business_unlock",
        "lifecycle_status",
    }
    bootstrap_count = sum(
        isinstance(waiver, dict) and waiver.get("kind") == "bootstrap_exception"
        for waiver in waivers
    )
    if bootstrap_count != 1:
        errors.append("tasks/governance-waivers.yaml: exactly one bootstrap_exception is required")
    expected_bootstrap = {
        "task_id": "TASK-014",
        "beneficiary_task": "TASK-031",
        "kind": "bootstrap_exception",
        "one_time": True,
        "deny_business_unlock": True,
        "owner": "qfxyyy",
        "expires_on": "2026-08-13",
        "remediation_task": "TASK-031",
        "release_status": "prohibited",
    }
    for waiver in waivers:
        if not isinstance(waiver, dict) or not required.issubset(waiver):
            errors.append("tasks/governance-waivers.yaml: waiver missing required fields")
            continue
        for field in required - {"one_time", "deny_business_unlock"}:
            if not isinstance(waiver.get(field), str) or not waiver[field].strip():
                errors.append(
                    f"tasks/governance-waivers.yaml: waiver field {field} must be non-empty"
                )
        if waiver.get("task_id") not in known_task_ids:
            errors.append(f"tasks/governance-waivers.yaml: unknown task_id {waiver.get('task_id')}")
        if waiver.get("remediation_task") not in known_task_ids:
            errors.append(
                "tasks/governance-waivers.yaml: unknown remediation_task "
                f"{waiver.get('remediation_task')}"
            )
        if waiver.get("beneficiary_task") not in known_task_ids:
            errors.append(
                "tasks/governance-waivers.yaml: unknown beneficiary_task "
                f"{waiver.get('beneficiary_task')}"
            )
        if not isinstance(waiver.get("one_time"), bool) or not isinstance(
            waiver.get("deny_business_unlock"), bool
        ):
            errors.append("tasks/governance-waivers.yaml: bootstrap flags must be boolean")
        if waiver.get("release_status") != "prohibited":
            errors.append("tasks/governance-waivers.yaml: waiver release_status must be prohibited")
        try:
            expires = date.fromisoformat(str(waiver["expires_on"]))
        except ValueError:
            errors.append(
                f"tasks/governance-waivers.yaml: invalid expires_on for {waiver.get('task_id')}"
            )
            expires = None
        lifecycle = waiver.get("lifecycle_status")
        if lifecycle not in WAIVER_LIFECYCLE_STATES:
            errors.append(
                "tasks/governance-waivers.yaml: lifecycle_status must be active, retired, "
                "or expired"
            )
        elif lifecycle == "active":
            if expires is not None and expires < today:
                errors.append(
                    "tasks/governance-waivers.yaml: active waiver is past expires_on and "
                    "must transition to expired"
                )
            if "retired_on" in waiver or "expired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: active waiver cannot have terminal dates"
                )
            if task_statuses is not None and any(
                task_statuses.get(str(waiver.get(field))) == "completed"
                for field in ("beneficiary_task", "remediation_task")
            ):
                errors.append(
                    "tasks/governance-waivers.yaml: completed remediation requires retired "
                    "waiver lifecycle"
                )
        elif lifecycle == "retired":
            retired_on = parse_waiver_transition_date(waiver, "retired_on", errors)
            if retired_on is not None and retired_on > today:
                errors.append("tasks/governance-waivers.yaml: retired_on cannot be in the future")
            if "expired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: retired waiver cannot have expired_on"
                )
            if (
                task_statuses is not None
                and task_statuses.get(str(waiver.get("remediation_task"))) != "completed"
            ):
                errors.append(
                    "tasks/governance-waivers.yaml: retired waiver remediation_task must be "
                    "completed"
                )
        elif lifecycle == "expired":
            expired_on = parse_waiver_transition_date(waiver, "expired_on", errors)
            if expired_on is not None:
                if expires is not None and expired_on <= expires:
                    errors.append(
                        "tasks/governance-waivers.yaml: expired_on must be after expires_on"
                    )
                if expired_on > today:
                    errors.append(
                        "tasks/governance-waivers.yaml: expired_on cannot be in the future"
                    )
            if "retired_on" in waiver:
                errors.append(
                    "tasks/governance-waivers.yaml: expired waiver cannot have retired_on"
                )
        if waiver.get("release_status") in {"eligible", "released"}:
            errors.append("tasks/governance-waivers.yaml: waiver cannot permit release")
        if waiver.get("kind") == "bootstrap_exception":
            for field, expected in expected_bootstrap.items():
                if waiver.get(field) != expected:
                    errors.append(
                        "tasks/governance-waivers.yaml: bootstrap field "
                        f"{field} must equal {expected}"
                    )
        elif any(
            field in waiver for field in ("beneficiary_task", "one_time", "deny_business_unlock")
        ):
            errors.append(
                "tasks/governance-waivers.yaml: ordinary waiver cannot carry bootstrap fields"
            )


def parse_waiver_transition_date(
    waiver: dict[str, Any], field: str, errors: list[str]
) -> date | None:
    """Parse a required terminal waiver date without accepting empty or invalid values."""
    value = waiver.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"tasks/governance-waivers.yaml: {field} is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"tasks/governance-waivers.yaml: invalid {field}")
        return None


def validate_waivers(errors: list[str]) -> None:
    path = TASK_ROOT / "governance-waivers.yaml"
    if not path.is_file():
        errors.append("tasks/governance-waivers.yaml: required governance waiver registry missing")
        return
    document = load_yaml(path)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        errors.append("tasks/governance-waivers.yaml: schema_version must be 1")
        return
    waivers = document.get("waivers", [])
    if not isinstance(waivers, list):
        errors.append("tasks/governance-waivers.yaml: waivers must be a list")
        return
    task_statuses: dict[str, str] = {}
    for task_path in task_files():
        task = extract_front_matter(task_path)
        task_id = task.get("id")
        status = task.get("status")
        if isinstance(task_id, str) and isinstance(status, str):
            task_statuses[task_id] = status
    validate_waiver_entries(waivers, set(task_statuses), errors, task_statuses=task_statuses)


def validate_active_readme(tasks: dict[str, dict[str, Any]], errors: list[str]) -> None:
    path = TASK_ROOT / "active" / "README.md"
    if not path.is_file():
        errors.append("tasks/active/README.md: missing active projection")
        return
    text = path.read_text(encoding="utf-8")
    listed = set(re.findall(r"当前 active task.\s*(TASK-\d{3})", text))
    listed.update(re.findall(r"(?m)^\s*[-*]\s*(TASK-\d{3})\b", text))
    expected = {task_id for task_id, task in tasks.items() if task.get("status") == "active"}
    if listed != expected:
        errors.append(
            "tasks/active/README.md: active projection mismatch "
            f"(listed={sorted(listed)}, expected={sorted(expected)})"
        )


def delivery_is_unlockable(
    task: dict[str, Any],
    *,
    task_id: str | None = None,
    evidence_binding: dict[str, Any] | None = None,
) -> bool:
    delivery = task.get("delivery")
    resolved_task_id = task_id or task.get("id")
    generally_unlockable = (
        isinstance(delivery, dict)
        and delivery.get("schema_version") == 1
        and delivery.get("implementation_status") in {"merged", "not_applicable"}
        and delivery.get("acceptance_status") == "passed"
        and delivery.get("review_status") in {"approved", "not_required"}
        and delivery.get("release_status") in {"prohibited", "eligible", "released"}
        and completion_evidence_is_trusted(
            delivery,
            task_id=resolved_task_id,
            evidence_binding=evidence_binding,
        )
    )
    if not generally_unlockable:
        return False
    if resolved_task_id == RISK_SCOPE_SUCCESSOR:
        if not isinstance(delivery, dict):
            return False
        return task051_completion_evidence_is_bound(delivery, evidence_binding)
    return True


def completion_evidence_is_trusted(
    delivery: dict[str, Any],
    *,
    task_id: str | None = None,
    evidence_binding: dict[str, Any] | None = None,
) -> bool:
    evidence = delivery.get("completion_evidence")
    if not isinstance(evidence, dict) or not COMPLETION_FIELDS.issubset(evidence):
        return False
    if any(
        not isinstance(evidence.get(field), str) or not evidence[field].strip()
        for field in COMPLETION_FIELDS
    ):
        return False
    if evidence.get("review_verdict") not in {"APPROVE", "NOT_REQUIRED"}:
        return False
    generally_trusted = (
        SHA_RE.fullmatch(str(evidence.get("reviewed_head_sha"))) is not None
        and SHA_RE.fullmatch(str(evidence.get("merge_commit_sha"))) is not None
        and PR_RE.fullmatch(str(evidence.get("change_pr"))) is not None
        and URL_RE.fullmatch(str(evidence.get("evidence_url"))) is not None
        and evidence.get("reviewer") not in {"unverifiable", "reported_unverified"}
    )
    if not generally_trusted:
        return False
    if task_id == RISK_SCOPE_SUCCESSOR:
        return task051_completion_evidence_is_bound(delivery, evidence_binding)
    return True


def load_risk_scope_evidence_binding(errors: list[str]) -> dict[str, Any] | None:
    """Load the static TASK-051 evidence binding without claiming external verification."""
    try:
        document = load_yaml(RISK_SCOPE_GOVERNANCE_PATH)
    except Exception as exc:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            f"required TASK-051 evidence binding is unavailable: {exc}"
        )
        return None
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: schema_version must be 1"
        )
        return None
    if document.get("audit_task") != RISK_SCOPE_SUCCESSOR:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "audit_task must be TASK-051"
        )
        return None
    binding = document.get("successor_evidence_binding")
    if not isinstance(binding, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "successor_evidence_binding must be present"
        )
        return None
    expected = {
        "task_id": RISK_SCOPE_SUCCESSOR,
        "beneficiary_task": "TASK-029",
        "repository": RISK_SCOPE_REPOSITORY,
        "pull_request_number": RISK_SCOPE_PR_NUMBER,
        "change_pr": RISK_SCOPE_PR_URL,
    }
    for field, value in expected.items():
        if binding.get(field) != value:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"successor evidence binding {field} must equal {value}"
            )
    identity = binding.get("implementation_identity")
    if not isinstance(identity, dict) or identity.get("agent") != RISK_SCOPE_IMPLEMENTING_AGENT:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "implementation agent identity is not bound"
        )
    if not isinstance(identity, dict) or identity.get("pull_request_author") != (
        RISK_SCOPE_PR_AUTHOR
    ):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "pull request author identity is not bound"
        )
    review = binding.get("required_review")
    merge = binding.get("required_merge")
    if not isinstance(review, dict) or not isinstance(merge, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "required_review and required_merge bindings must be present"
        )
        return binding
    for field in ("verdict", "reviewer", "reviewed_head_sha", "evidence_url"):
        if field not in review:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"required_review.{field} must be present"
            )
    if "merge_commit_sha" not in merge:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "required_merge.merge_commit_sha must be present"
        )
    if binding.get("external_fact_status") not in {
        "pending_github_and_human_verification",
        RISK_SCOPE_EXTERNAL_FACT_STATUS,
    }:
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "external_fact_status must remain pending or recorded-after-verification"
        )
    boundary = binding.get("static_validator_boundary")
    if not isinstance(boundary, dict):
        errors.append(
            "ai/governance/risk-validator-integration-scope-task-051.yaml: "
            "static validator boundary must declare verifies and external facts"
        )
    else:
        for field, required_values in RISK_SCOPE_BOUNDARY_REQUIREMENTS.items():
            values = boundary.get(field)
            if not isinstance(values, list) or not required_values.issubset(values):
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"static validator boundary {field} is incomplete"
                )
    external_status = binding.get("external_fact_status")
    if external_status == "pending_github_and_human_verification":
        pending_values = {
            "reviewer": RISK_SCOPE_PENDING_REVIEWER,
            "reviewed_head_sha": RISK_SCOPE_PENDING_REVIEWED_HEAD,
            "evidence_url": RISK_SCOPE_PENDING_REVIEW_URL,
        }
        for field, expected_value in pending_values.items():
            if review.get(field) != expected_value:
                errors.append(
                    "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                    f"pending required_review.{field} must remain {expected_value}"
                )
        if review.get("verdict") != "APPROVE":
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "required_review.verdict must remain APPROVE"
            )
        if merge.get("merge_commit_sha") != RISK_SCOPE_PENDING_MERGE:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                f"pending required_merge.merge_commit_sha must remain {RISK_SCOPE_PENDING_MERGE}"
            )
        if binding.get("human_authorization_evidence") != RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION:
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "pending human authorization evidence must remain the explicit placeholder"
            )
    elif external_status == RISK_SCOPE_EXTERNAL_FACT_STATUS:
        if review.get("verdict") != "APPROVE":
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded required_review.verdict must be APPROVE"
            )
        if not isinstance(review.get("reviewer"), str) or not github_reviewer_is_independent(
            review.get("reviewer"), identity
        ):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded reviewer must be a non-placeholder independent GitHub login"
            )
        if not plausible_evidence_sha(review.get("reviewed_head_sha")):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded reviewed_head_sha must be a non-placeholder SHA"
            )
        if not plausible_evidence_sha(merge.get("merge_commit_sha")):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded merge_commit_sha must be a non-placeholder SHA"
            )
        review_url_re = re.compile(
            rf"^{re.escape(RISK_SCOPE_PR_URL)}#pullrequestreview-[1-9][0-9]*$"
        )
        evidence_url = review.get("evidence_url")
        if not isinstance(evidence_url, str) or not review_url_re.fullmatch(evidence_url):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded evidence_url must identify a PR 87 review"
            )
        if not isinstance(binding.get("human_authorization_evidence"), str) or is_placeholder_text(
            binding.get("human_authorization_evidence")
        ):
            errors.append(
                "ai/governance/risk-validator-integration-scope-task-051.yaml: "
                "recorded human authorization evidence must not be a placeholder"
            )
    return binding


def task051_completion_evidence_is_bound(
    delivery: dict[str, Any], evidence_binding: dict[str, Any] | None
) -> bool:
    """Check TASK-051's recorded evidence against its immutable local PR/review binding."""
    if (
        delivery.get("contract_status") != "not_applicable"
        or delivery.get("implementation_status") != "merged"
        or delivery.get("acceptance_status") != "passed"
        or delivery.get("review_status") != "approved"
        or delivery.get("release_status") != "prohibited"
    ):
        return False
    if not isinstance(evidence_binding, dict):
        return False
    if any(
        evidence_binding.get(field) != expected
        for field, expected in {
            "task_id": RISK_SCOPE_SUCCESSOR,
            "beneficiary_task": "TASK-029",
            "repository": RISK_SCOPE_REPOSITORY,
            "pull_request_number": RISK_SCOPE_PR_NUMBER,
            "change_pr": RISK_SCOPE_PR_URL,
        }.items()
    ):
        return False
    if not completion_evidence_is_trusted(delivery):
        return False
    evidence = delivery.get("completion_evidence")
    review = evidence_binding.get("required_review")
    merge = evidence_binding.get("required_merge")
    identity = evidence_binding.get("implementation_identity")
    if not all(isinstance(value, dict) for value in (evidence, review, merge, identity)):
        return False
    assert isinstance(evidence, dict)
    assert isinstance(review, dict)
    assert isinstance(merge, dict)
    assert isinstance(identity, dict)
    if (
        identity.get("agent") != RISK_SCOPE_IMPLEMENTING_AGENT
        or identity.get("pull_request_author") != RISK_SCOPE_PR_AUTHOR
    ):
        return False
    if review.get("verdict") != "APPROVE":
        return False
    if evidence_binding.get("external_fact_status") != RISK_SCOPE_EXTERNAL_FACT_STATUS:
        return False
    reviewer = review.get("reviewer")
    reviewed_head_sha = review.get("reviewed_head_sha")
    merge_commit_sha = merge.get("merge_commit_sha")
    evidence_url = review.get("evidence_url")
    human_authorization = evidence_binding.get("human_authorization_evidence")
    if not github_reviewer_is_independent(reviewer, identity):
        return False
    if not plausible_evidence_sha(reviewed_head_sha) or not plausible_evidence_sha(
        merge_commit_sha
    ):
        return False
    review_url_re = re.compile(rf"^{re.escape(RISK_SCOPE_PR_URL)}#pullrequestreview-[1-9][0-9]*$")
    if not isinstance(evidence_url, str) or review_url_re.fullmatch(evidence_url) is None:
        return False
    if not isinstance(human_authorization, str) or is_placeholder_text(human_authorization):
        return False
    expected_evidence = {
        "mode": RISK_SCOPE_COMPLETION_MODE,
        "change_pr": RISK_SCOPE_PR_URL,
        "reviewed_head_sha": reviewed_head_sha,
        "review_verdict": "APPROVE",
        "reviewer": reviewer,
        "evidence_url": evidence_url,
        "merge_commit_sha": merge_commit_sha,
        "human_authorization_evidence": human_authorization,
    }
    return all(evidence.get(field) == value for field, value in expected_evidence.items())


def plausible_evidence_sha(value: Any) -> bool:
    """Reject malformed and obvious repeated-pattern placeholder SHAs."""
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        return False
    return not any(value == value[:size] * (40 // size) for size in range(1, 21) if 40 % size == 0)


def is_placeholder_text(value: Any) -> bool:
    """Return whether governance text still carries an unresolved placeholder."""
    return (
        not isinstance(value, str)
        or not value.strip()
        or value
        in {
            "unverifiable",
            "reported_unverified",
            RISK_SCOPE_PENDING_REVIEWER,
            RISK_SCOPE_PENDING_REVIEWED_HEAD,
            RISK_SCOPE_PENDING_REVIEW_URL,
            RISK_SCOPE_PENDING_MERGE,
            RISK_SCOPE_PENDING_HUMAN_AUTHORIZATION,
        }
        or value.startswith("pending_")
        or value.startswith("pending-")
    )


def github_reviewer_is_independent(value: Any, identity: Any) -> bool:
    """Validate reviewer syntax and keep implementation identities out of review evidence."""
    return (
        isinstance(value, str)
        and GITHUB_LOGIN_RE.fullmatch(value) is not None
        and not is_placeholder_text(value)
        and isinstance(identity, dict)
        and value not in {identity.get("agent"), identity.get("pull_request_author")}
    )


def bootstrap_allows_dependency(
    dependency: str,
    beneficiary: str,
    waivers: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> bool:
    evaluation_date = today or date.today()
    for waiver in waivers:
        try:
            expires = date.fromisoformat(str(waiver.get("expires_on")))
        except (TypeError, ValueError):
            continue
        if (
            waiver.get("kind") == "bootstrap_exception"
            and waiver.get("lifecycle_status") == "active"
            and waiver.get("one_time") is True
            and waiver.get("deny_business_unlock") is True
            and waiver.get("task_id") == dependency == "TASK-014"
            and waiver.get("beneficiary_task") == beneficiary == "TASK-031"
            and isinstance(waiver.get("rule"), str)
            and bool(waiver["rule"].strip())
            and isinstance(waiver.get("reason"), str)
            and bool(waiver["reason"].strip())
            and waiver.get("owner") == "qfxyyy"
            and expires >= evaluation_date
            and waiver.get("remediation_task") == "TASK-031"
            and waiver.get("release_status") == "prohibited"
        ):
            return True
    return False


def validate_l4_successor_dependencies(tasks: dict[str, dict[str, Any]], errors: list[str]) -> None:
    """Keep the general L4 queue on its fresh readiness gate."""
    present_successors = L4_SUCCESSOR_TASKS.intersection(tasks)
    if present_successors and L4_READINESS_SUCCESSOR not in tasks:
        errors.append(
            f"tasks: {L4_READINESS_SUCCESSOR} successor gate missing for L4 contract queue"
        )
    for task_id in sorted(present_successors):
        dependencies = tasks[task_id].get("depends_on")
        if not isinstance(dependencies, list):
            continue
        if "TASK-014" in dependencies:
            errors.append(
                f"{task_id}: historical TASK-014 readiness dependency must not remain; "
                f"use {L4_READINESS_SUCCESSOR}"
            )
        if L4_READINESS_SUCCESSOR not in dependencies:
            errors.append(
                f"{task_id}: missing {L4_READINESS_SUCCESSOR} readiness successor dependency"
            )


def validate_risk_scope_successor_dependencies(
    tasks: dict[str, dict[str, Any]],
    errors: list[str],
    evidence_binding: dict[str, Any] | None = None,
) -> None:
    """Require the fresh Risk scope gate without rewriting its historical predecessor."""
    task029 = tasks.get("TASK-029")
    if isinstance(task029, dict):
        if task029.get("status") != "blocked":
            errors.append("TASK-029 queue status must remain blocked")
        if RISK_SCOPE_SUCCESSOR not in tasks:
            errors.append(f"tasks: {RISK_SCOPE_SUCCESSOR} successor gate missing for TASK-029")
        dependencies = task029.get("depends_on")
        if isinstance(dependencies, list):
            if len(dependencies) != len(RISK_SCOPE_REQUIRED_DEPENDENCIES) or set(
                dependencies
            ) != set(RISK_SCOPE_REQUIRED_DEPENDENCIES):
                errors.append(
                    "TASK-029: required scope dependencies must be TASK-015, TASK-031, TASK-051"
                )
            if RISK_SCOPE_SUCCESSOR not in dependencies:
                errors.append(
                    f"TASK-029: missing {RISK_SCOPE_SUCCESSOR} scope successor dependency"
                )
            for rejected in (RISK_HISTORICAL_SCOPE_TASK, L4_READINESS_SUCCESSOR):
                if rejected in dependencies:
                    errors.append(
                        f"TASK-029: {rejected} cannot replace or bypass {RISK_SCOPE_SUCCESSOR}"
                    )

    task030 = tasks.get(RISK_HISTORICAL_SCOPE_TASK)
    if not isinstance(task030, dict):
        errors.append("TASK-030 historical record must remain present")
    else:
        if task030.get("status") != "completed":
            errors.append("TASK-030 historical queue status must remain completed")
        delivery = task030.get("delivery")
        if not isinstance(delivery, dict):
            errors.append("TASK-030 historical delivery metadata must remain present")
        else:
            for field, expected in RISK_HISTORICAL_DELIVERY.items():
                if delivery.get(field) != expected:
                    errors.append(
                        f"TASK-030 historical {field.removesuffix('_status')} must remain "
                        f"{expected}"
                    )
            evidence = delivery.get("completion_evidence")
            historical_evidence = {
                "mode": "historical_git_verified_review_unavailable",
                "review_verdict": "reported_unverified",
                "reviewer": "unverifiable",
                "evidence_url": "unverifiable",
                "human_authorization_evidence": "unverifiable",
            }
            if not isinstance(evidence, dict):
                errors.append("TASK-030 historical completion evidence must remain present")
            else:
                for field, expected in historical_evidence.items():
                    if evidence.get(field) != expected:
                        errors.append(
                            "TASK-030 historical completion evidence "
                            f"{field} must remain {expected}"
                        )

    task005 = tasks.get("TASK-005")
    if isinstance(task005, dict) and task005.get("status") != "blocked":
        errors.append("TASK-005 queue status must remain blocked")

    task051 = tasks.get(RISK_SCOPE_SUCCESSOR)
    if isinstance(task051, dict) and task051.get("status") == "completed":
        delivery = task051.get("delivery")
        if (
            isinstance(delivery, dict)
            and delivery.get("review_status") in {"approved", "not_required"}
            and not task051_completion_evidence_is_bound(delivery, evidence_binding)
        ):
            errors.append("TASK-051 evidence does not match its governance binding")


def validate_json_schemas(errors: list[str]) -> None:
    for path in sorted(SPEC_ROOT.rglob("*.schema.json")):
        try:
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # validation boundary intentionally reports every file
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON Schema: {exc}")


def validate_yaml_files(errors: list[str]) -> None:
    for base in (SPEC_ROOT, TASK_ROOT):
        for path in sorted(base.rglob("*.yaml")):
            try:
                load_yaml(path)
            except Exception as exc:
                errors.append(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")


def validate_manifest(errors: list[str]) -> dict[str, Path]:
    manifest = load_yaml(SPEC_ROOT / "manifest.yaml")
    if not isinstance(manifest, dict):
        errors.append("spec/manifest.yaml: root must be a mapping")
        return {}
    entries = manifest_entries(manifest)
    if not entries:
        errors.append("spec/manifest.yaml: no catalog entries")
    for spec_id, path in entries.items():
        if not path.is_file():
            errors.append(f"spec/manifest.yaml: {spec_id} path does not exist: {path}")
    return entries


def validate_tasks(specs: dict[str, Path], errors: list[str], *, today: date | None = None) -> None:
    evaluation_date = today or date.today()
    tasks: dict[str, dict[str, Any]] = {}
    task_paths: dict[str, Path] = {}
    waiver_document = load_yaml(TASK_ROOT / "governance-waivers.yaml")
    waivers = waiver_document.get("waivers", []) if isinstance(waiver_document, dict) else []
    if not isinstance(waivers, list):
        waivers = []
    for path in task_files():
        try:
            task = extract_front_matter(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or re.fullmatch(r"TASK-\d{3}", task_id) is None:
            errors.append(f"{path.relative_to(ROOT)}: invalid task id")
            continue
        if task_id in tasks:
            errors.append(f"duplicate task id: {task_id}")
        tasks[task_id] = task
        task_paths[task_id] = path
        status = task.get("status")
        expected_dir = (
            {
                "blocked": "backlog",
                "ready": "backlog",
                "active": "active",
                "completed": "completed",
            }.get(status)
            if isinstance(status, str)
            else None
        )
        if status not in TASK_STATES or expected_dir != path.parent.name:
            errors.append(f"{path.relative_to(ROOT)}: status must match its queue directory")
        for field in ("status", "depends_on", "spec_refs", "allowed_paths", "forbidden_paths"):
            if field not in task:
                errors.append(f"{path.relative_to(ROOT)}: missing {field}")
        for spec_id in task.get("spec_refs", []):
            if spec_id not in specs:
                errors.append(f"{path.relative_to(ROOT)}: unknown spec ref {spec_id}")
        verification = task.get("verification")
        if not isinstance(verification, dict) or not verification.get("commands"):
            errors.append(f"{path.relative_to(ROOT)}: verification.commands must not be empty")
        validate_delivery(task_id, task, path, errors)

    graph: dict[str, list[str]] = {}
    for task_id, task in tasks.items():
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{task_paths[task_id].relative_to(ROOT)}: depends_on must be a list")
            continue
        graph[task_id] = [str(value) for value in dependencies]
        for dependency in graph[task_id]:
            if dependency not in tasks:
                unknown_dep_path = task_paths[task_id].relative_to(ROOT)
                errors.append(f"{unknown_dep_path}: unknown dependency {dependency}")
    if has_cycle(graph):
        errors.append("tasks: dependency graph contains a cycle")
    validate_l4_successor_dependencies(tasks, errors)
    risk_scope_binding = None
    if "TASK-029" in tasks or RISK_SCOPE_SUCCESSOR in tasks:
        risk_scope_binding = load_risk_scope_evidence_binding(errors)
    validate_risk_scope_successor_dependencies(tasks, errors, risk_scope_binding)

    bootstrap_entries = [
        waiver
        for waiver in waivers
        if isinstance(waiver, dict) and waiver.get("kind") == "bootstrap_exception"
    ]
    trusted_bootstrap_waivers: list[dict[str, Any]] = []
    if bootstrap_entries:
        waiver_errors: list[str] = []
        validate_waiver_entries(
            waivers,
            set(tasks),
            waiver_errors,
            today=evaluation_date,
            task_statuses={task_id: str(task.get("status")) for task_id, task in tasks.items()},
        )
        errors.extend(waiver_errors)
        if not waiver_errors:
            trusted_bootstrap_waivers = bootstrap_entries

    index = load_yaml(TASK_ROOT / "index.yaml")
    indexed = index.get("tasks", []) if isinstance(index, dict) else []
    indexed_ids: set[str] = set()
    for entry in indexed:
        if not isinstance(entry, dict):
            errors.append("tasks/index.yaml: each task entry must be a mapping")
            continue
        task_id = entry.get("id")
        indexed_path = entry.get("path")
        if isinstance(task_id, str):
            if task_id in indexed_ids:
                errors.append(f"tasks/index.yaml: duplicate task id {task_id}")
            indexed_ids.add(task_id)
        if not isinstance(indexed_path, str) or not (TASK_ROOT / indexed_path).is_file():
            errors.append(f"tasks/index.yaml: missing path for {task_id}: {indexed_path}")
        if task_id in task_paths and indexed_path != str(
            task_paths[task_id].relative_to(TASK_ROOT)
        ).replace("\\", "/"):
            errors.append(f"tasks/index.yaml: path mismatch for {task_id}")
        if task_id in tasks and entry.get("status") != tasks[task_id].get("status"):
            errors.append(f"tasks/index.yaml: status mismatch for {task_id}")
    missing = set(tasks) - indexed_ids
    extra = indexed_ids - set(tasks)
    if missing:
        errors.append(f"tasks/index.yaml: unindexed tasks: {sorted(missing)}")
    if extra:
        errors.append(f"tasks/index.yaml: entries without task files: {sorted(extra)}")
    for task_id, task in tasks.items():
        for dependency in task.get("depends_on", []):
            dependency_task = tasks.get(dependency)
            if task.get("status") == "active" and (
                not isinstance(dependency_task, dict)
                or dependency_task.get("status") != "completed"
                or (
                    not delivery_is_unlockable(
                        dependency_task,
                        task_id=dependency,
                        evidence_binding=risk_scope_binding,
                    )
                    and not bootstrap_allows_dependency(
                        dependency,
                        task_id,
                        trusted_bootstrap_waivers,
                        today=evaluation_date,
                    )
                )
            ):
                errors.append(
                    f"{task_id}: dependency {dependency} lacks trusted completed delivery; "
                    "activation denied"
                )
    validate_active_readme(tasks, errors)


def validate_error_catalog(errors: list[str]) -> None:
    catalog = load_yaml(SPEC_ROOT / "contracts" / "errors" / "catalog.yaml")
    entries = catalog.get("errors", []) if isinstance(catalog, dict) else []
    codes: set[str] = set()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("error catalog: each entry must be a mapping")
            continue
        code = entry.get("code")
        name = entry.get("name")
        if not isinstance(code, str) or re.fullmatch(r"QQ-[A-Z]+-\d{4}", code) is None:
            errors.append(f"error catalog: invalid code {code}")
        elif code in codes:
            errors.append(f"error catalog: duplicate code {code}")
        else:
            codes.add(code)
        if not isinstance(name, str) or not name:
            errors.append(f"error catalog: invalid name {name}")
        elif name in names:
            errors.append(f"error catalog: duplicate name {name}")
        else:
            names.add(name)


def validate_message_catalog(errors: list[str]) -> None:
    catalog_path = SPEC_ROOT / "contracts" / "catalog.yaml"
    catalog = load_yaml(catalog_path)
    messages = catalog.get("messages", []) if isinstance(catalog, dict) else []
    names: set[str] = set()
    for entry in messages:
        if not isinstance(entry, dict):
            errors.append("contract catalog: each message must be a mapping")
            continue
        name = entry.get("name")
        status = entry.get("status")
        schema = entry.get("schema")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.v[1-9][0-9]*", name) is None
        ):
            errors.append(f"contract catalog: invalid message name {name}")
        elif name in names:
            errors.append(f"contract catalog: duplicate message name {name}")
        else:
            names.add(name)
        if status not in {"active", "planned", "deprecated"}:
            errors.append(f"contract catalog: invalid status for {name}: {status}")
        if status == "active":
            if not isinstance(schema, str):
                errors.append(f"contract catalog: active message {name} requires schema")
            elif not (catalog_path.parent / schema).is_file():
                errors.append(f"contract catalog: schema does not exist for {name}: {schema}")


def validate_state_machines(errors: list[str]) -> None:
    for path in sorted((SPEC_ROOT / "state-machines").glob("*.yaml")):
        document = load_yaml(path)
        machine = document.get("machine") if isinstance(document, dict) else None
        if not isinstance(machine, dict):
            errors.append(f"{path.relative_to(ROOT)}: missing machine mapping")
            continue
        states = machine.get("states")
        initial = machine.get("initial")
        transitions = machine.get("transitions")
        if not isinstance(states, dict) or initial not in states:
            errors.append(f"{path.relative_to(ROOT)}: invalid initial state")
            continue
        if not isinstance(transitions, list):
            errors.append(f"{path.relative_to(ROOT)}: transitions must be a list")
            continue
        seen: set[tuple[str, str, str]] = set()
        for transition in transitions:
            if not isinstance(transition, dict):
                errors.append(f"{path.relative_to(ROOT)}: transition must be a mapping")
                continue
            source = transition.get("from")
            event = transition.get("event")
            target = transition.get("to")
            if source not in states or target not in states or not isinstance(event, str):
                errors.append(f"{path.relative_to(ROOT)}: invalid transition {transition}")
                continue
            key = (str(source), event, str(target))
            if key in seen:
                errors.append(f"{path.relative_to(ROOT)}: duplicate transition {key}")
            seen.add(key)


def validate_markdown_links(errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if re.match(r"^(https?://|mailto:)", target):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link {target}")


def main() -> int:
    errors: list[str] = []
    validate_yaml_files(errors)
    validate_json_schemas(errors)
    specs = validate_manifest(errors)
    validate_tasks(specs, errors)
    validate_waivers(errors)
    validate_error_catalog(errors)
    validate_message_catalog(errors)
    validate_state_machines(errors)
    validate_markdown_links(errors)
    if errors:
        print("Specification validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Specification validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
