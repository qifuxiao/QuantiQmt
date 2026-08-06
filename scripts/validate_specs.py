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


def delivery_is_unlockable(task: dict[str, Any]) -> bool:
    delivery = task.get("delivery")
    return (
        isinstance(delivery, dict)
        and delivery.get("schema_version") == 1
        and delivery.get("implementation_status") in {"merged", "not_applicable"}
        and delivery.get("acceptance_status") == "passed"
        and delivery.get("review_status") in {"approved", "not_required"}
        and delivery.get("release_status") in {"prohibited", "eligible", "released"}
        and completion_evidence_is_trusted(delivery)
    )


def completion_evidence_is_trusted(delivery: dict[str, Any]) -> bool:
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
    return (
        SHA_RE.fullmatch(str(evidence.get("reviewed_head_sha"))) is not None
        and SHA_RE.fullmatch(str(evidence.get("merge_commit_sha"))) is not None
        and PR_RE.fullmatch(str(evidence.get("change_pr"))) is not None
        and URL_RE.fullmatch(str(evidence.get("evidence_url"))) is not None
        and evidence.get("reviewer") not in {"unverifiable", "reported_unverified"}
    )


def bootstrap_allows_dependency(
    dependency: str, beneficiary: str, waivers: list[dict[str, Any]]
) -> bool:
    today = date.today()
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
            and expires >= today
            and waiver.get("remediation_task") == "TASK-031"
            and waiver.get("release_status") == "prohibited"
        ):
            return True
    return False


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


def validate_tasks(specs: dict[str, Path], errors: list[str]) -> None:
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
                    not delivery_is_unlockable(dependency_task)
                    and not bootstrap_allows_dependency(
                        dependency, task_id, trusted_bootstrap_waivers
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
