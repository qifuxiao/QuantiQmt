"""Governance tests for tool-neutral agents and environment evidence (TASK-057)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
GITHUB_EVIDENCE_RE = re.compile(
    r"^https://github\.com/[^/]+/[^/]+/(?:pull|issues)/\d+#(?:issuecomment|pullrequestreview)-\d+$"
)

SHARED_GOVERNANCE_FILES = (
    "AGENTS.md",
    "ai/workflows/team-collaboration.md",
    "tasks/templates/task-template.md",
    "ai/prompts/miniqmt-m1-task.md",
)

PERSISTENT_AUTHORITY_FILES = (
    *SHARED_GOVERNANCE_FILES,
    "ai/adapters/codex.md",
    "ai/adapters/cline.md",
    "ai/workflows/poetry-verification.md",
)


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _assignment_errors(record: Mapping[str, object], *, switching: bool = False) -> list[str]:
    required = {
        "role",
        "tool",
        "os",
        "starting_head",
        "human_evidence_url",
        "single_writer",
    }
    if switching:
        required.update({"previous_agent", "next_agent", "previous_agent_stop_head"})
    errors = [f"missing {field}" for field in sorted(required - record.keys())]
    if record.get("role") != "Implementation Agent":
        errors.append("role must be Implementation Agent")
    if not SHA_RE.fullmatch(str(record.get("starting_head", ""))):
        errors.append("starting_head must be an exact SHA")
    if not GITHUB_EVIDENCE_RE.fullmatch(str(record.get("human_evidence_url", ""))):
        errors.append("assignment must use a durable GitHub evidence URL")
    if record.get("single_writer") is not True:
        errors.append("single_writer must be true")
    if switching and record.get("previous_agent_stop_head") != record.get("starting_head"):
        errors.append("previous agent must stop at the new starting Head")
    return errors


def _lane_errors(record: Mapping[str, object], *, pr_head: str) -> list[str]:
    errors: list[str] = []
    lane = record.get("lane")
    os_name = str(record.get("os", "")).lower()
    required = {
        "task",
        "base",
        "head",
        "role",
        "tool",
        "os",
        "python_version",
        "poetry_version",
        "command",
        "exit_code",
        "executed",
        "passed",
        "failed",
        "skipped",
        "evidence_url",
    }
    errors.extend(f"missing {field}" for field in sorted(required - record.keys()))
    if re.fullmatch(r"TASK-\d{3}", str(record.get("task", ""))) is None:
        errors.append("invalid task identity")
    if not SHA_RE.fullmatch(str(record.get("base", ""))):
        errors.append("Base must be an exact SHA")
    if not SHA_RE.fullmatch(str(record.get("head", ""))):
        errors.append("Head must be an exact SHA")
    if not GITHUB_EVIDENCE_RE.fullmatch(str(record.get("evidence_url", ""))):
        errors.append("environment evidence requires a durable GitHub URL")
    if lane not in {"portable", "windows", "windows_miniqmt"}:
        errors.append("unknown lane")
    if record.get("head") != pr_head:
        errors.append("environment evidence Head does not match PR Head")
    if lane in {"windows", "windows_miniqmt"} and os_name != "windows":
        errors.append("Windows evidence requires an actual Windows agent")
    if lane == "portable" and (
        int(record.get("executed", 0)) == 0
        or int(record.get("executed", 0)) == int(record.get("skipped", 0))
    ):
        errors.append("portable lane cannot skip every supported command")
    if lane == "windows_miniqmt":
        capabilities = {
            "miniqmt_available",
            "xtquant_task_approved",
            "userdata_mini_verified",
            "unique_session_verified",
            "simulation_account_allowlisted",
        }
        for capability in capabilities:
            if record.get(capability) is not True:
                errors.append(f"Mini QMT evidence requires {capability}")
    if record.get("real_money") is True:
        errors.append("real-money authority is always prohibited")
    if record.get("simulation_order") is True and not (
        record.get("separate_active_task") is True
        and GITHUB_EVIDENCE_RE.fullmatch(str(record.get("human_evidence_url", "")))
    ):
        errors.append("simulation order requires a separate active task and human evidence")
    return errors


def _valid_lane_record(lane: str, os_name: str, head: str) -> dict[str, object]:
    record: dict[str, object] = {
        "task": "TASK-057",
        "base": "c" * 40,
        "head": head,
        "lane": lane,
        "role": "Environment Verification Agent",
        "tool": "Codex",
        "os": os_name,
        "python_version": "3.12.10",
        "poetry_version": "2.4.1",
        "command": "poetry run pytest tests/spec",
        "exit_code": 0,
        "executed": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "evidence_url": "https://github.com/example/repo/pull/3#issuecomment-4",
        "simulation_order": False,
        "real_money": False,
    }
    if lane == "windows_miniqmt":
        record.update(
            {
                "miniqmt_available": True,
                "xtquant_task_approved": True,
                "userdata_mini_verified": True,
                "unique_session_verified": True,
                "simulation_account_allowlisted": True,
            }
        )
    return record


def _complete_evidence_record(
    command: str,
    *,
    base: str = "c" * 40,
    head: str = "d" * 40,
    role: str = "Implementation Agent",
) -> dict[str, object]:
    return {
        "task": "TASK-057",
        "base": base,
        "head": head,
        "lane": "portable",
        "requirement": "required",
        "role": role,
        "tool": "Codex",
        "os": "Windows",
        "python_version": "3.12.10",
        "poetry_version": "2.4.1",
        "command": command,
        "exit_code": 0,
        "executed": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "timestamp": "2026-09-01T09:00:00Z",
        "sanitized_evidence": True,
        "unverified_scope": "",
        "evidence_url": "https://github.com/example/repo/pull/3#issuecomment-4",
    }


def _environment_evidence_schema_errors(
    record: Mapping[str, object],
    *,
    expected_task: str,
    expected_base: str,
    expected_head: str,
) -> list[str]:
    required = {
        "task",
        "base",
        "head",
        "lane",
        "requirement",
        "role",
        "tool",
        "os",
        "python_version",
        "poetry_version",
        "command",
        "exit_code",
        "executed",
        "passed",
        "failed",
        "skipped",
        "timestamp",
        "sanitized_evidence",
        "unverified_scope",
        "evidence_url",
    }
    errors = [f"missing {field}" for field in sorted(required - record.keys())]
    if record.get("task") != expected_task:
        errors.append("evidence task does not match expected task")
    if not SHA_RE.fullmatch(str(record.get("base", ""))):
        errors.append("Base must be an exact SHA")
    elif record.get("base") != expected_base:
        errors.append("evidence Base does not match expected Base")
    if not SHA_RE.fullmatch(str(record.get("head", ""))):
        errors.append("Head must be an exact SHA")
    elif record.get("head") != expected_head:
        errors.append("evidence Head does not match expected Head")
    if record.get("lane") not in {"portable", "windows", "windows_miniqmt"}:
        errors.append("unknown lane")
    if record.get("requirement") not in {
        "required",
        "optional",
        "not_applicable",
    }:
        errors.append("invalid lane requirement")
    if record.get("role") not in {
        "Implementation Agent",
        "Environment Verification Agent",
    }:
        errors.append("role may not produce environment evidence")
    if (
        record.get("lane") in {"windows", "windows_miniqmt"}
        and str(record.get("os", "")).lower() != "windows"
    ):
        errors.append("Windows evidence requires an actual Windows agent")
    for field in ("tool", "os", "python_version", "poetry_version", "command"):
        if not isinstance(record.get(field), str) or not str(record.get(field)).strip():
            errors.append(f"{field} must be a non-empty string")
    if record.get("lane") == "windows_miniqmt" and (
        not isinstance(record.get("xtquant_version"), str)
        or not str(record.get("xtquant_version")).strip()
    ):
        errors.append("xtquant_version is required for Windows/Mini QMT evidence")
    if type(record.get("exit_code")) is not int:
        errors.append("exit_code must be an integer")
    if not RFC3339_RE.fullmatch(str(record.get("timestamp", ""))):
        errors.append("timestamp must be RFC3339")
    if record.get("sanitized_evidence") is not True:
        errors.append("sanitized_evidence must be true")
    if "unverified_scope" in record and not isinstance(record.get("unverified_scope"), str):
        errors.append("unverified_scope must be an explicit string")
    if not GITHUB_EVIDENCE_RE.fullmatch(str(record.get("evidence_url", ""))):
        errors.append("environment evidence requires a durable GitHub URL")
    return errors


def _required_lane_satisfaction_errors(
    records: list[Mapping[str, object]],
    *,
    expected_task: str,
    expected_base: str,
    expected_head: str,
    lane: str,
    expected_commands: set[str],
    skip_allowances: Mapping[str, int],
) -> list[str]:
    errors: list[str] = []
    normalized_expected = {" ".join(command.split()) for command in expected_commands}
    normalized_allowances = {
        " ".join(command.split()): allowance for command, allowance in skip_allowances.items()
    }
    observed: list[str] = []
    for index, record in enumerate(records):
        schema_errors = _environment_evidence_schema_errors(
            record,
            expected_task=expected_task,
            expected_base=expected_base,
            expected_head=expected_head,
        )
        errors.extend(f"record {index}: {error}" for error in schema_errors)
        if record.get("lane") != lane:
            errors.append(f"record {index}: lane does not match required lane")
        if record.get("requirement") != "required":
            errors.append(f"record {index}: lane record is not required")
        command = " ".join(str(record.get("command", "")).split())
        observed.append(command)
        counts: dict[str, int] = {}
        for field in ("executed", "passed", "failed", "skipped"):
            value = record.get(field)
            if type(value) is not int or value < 0:
                errors.append(f"record {index}: {field} must be a non-negative integer")
            else:
                counts[field] = value
        if len(counts) == 4:
            if counts["executed"] <= 0:
                errors.append(f"record {index}: executed work must be nonzero")
            if counts["executed"] != (counts["passed"] + counts["failed"] + counts["skipped"]):
                errors.append(f"record {index}: result counts are inconsistent")
            if counts["failed"] != 0:
                errors.append(f"record {index}: failed count must be zero")
            allowance = normalized_allowances.get(command, 0)
            if counts["skipped"] > allowance:
                errors.append(f"record {index}: skipped count exceeds allowance")
            if counts["skipped"] > 0 and not str(record.get("unverified_scope", "")).strip():
                errors.append(f"record {index}: skipped scope must be explicit")
        if record.get("exit_code") != 0:
            errors.append(f"record {index}: exit code must be zero")

    observed_set = set(observed)
    missing = normalized_expected - observed_set
    unexpected = observed_set - normalized_expected
    if missing:
        errors.append(f"missing expected commands: {sorted(missing)}")
    if unexpected:
        errors.append(f"unexpected commands: {sorted(unexpected)}")
    if len(observed) != len(observed_set):
        errors.append("duplicate command evidence is not exact coverage")
    return errors


def _poetry_command_errors(
    command: str,
    *,
    expected_commands: set[str],
    build_reason: str | None = None,
) -> list[str]:
    normalized = " ".join(command.strip().split())
    normalized_expected = {" ".join(item.strip().split()) for item in expected_commands}
    errors: list[str] = []
    if normalized not in normalized_expected:
        errors.append("command is not in the task-supplied expected command set")
    lower = normalized.lower()
    if not lower.startswith("poetry "):
        errors.append("project verification must use the original Poetry entrypoint")
    mutation_patterns = (
        r"(?:^| )(?:python -m )?(?:venv|virtualenv)(?: |$)",
        r"(?:^| )(?:python -m )?pip (?:install|uninstall)(?: |$)",
        r"^poetry (?:add|install|update|remove|lock)(?: |$)",
        r"^poetry run poetry (?:add|install|update|remove|lock)(?: |$)",
        r"^poetry env (?:use|remove)(?: |$)",
    )
    errors.extend(
        f"mutation command is forbidden: {pattern}"
        for pattern in mutation_patterns
        if re.search(pattern, lower)
    )
    if "bundled" in lower:
        errors.append("bundled Python is forbidden")
    if "--no-verify" in lower:
        errors.append("--no-verify is forbidden")
    if normalized == "poetry build" and build_reason not in {
        "task_required",
        "missing_wheel_only_skip",
    }:
        errors.append("poetry build requires an allowed reason")
    return errors


def _worktree_reuse_errors(decision: Mapping[str, object]) -> list[str]:
    required_true = (
        "existing_environment_valid",
        "dependency_complete",
        "python_compatible",
        "pyproject_identity_compatible",
        "lock_identity_compatible",
        "original_poetry_entrypoint",
        "compatibility_verifiable",
    )
    required_false = ("create_environment", "install_dependencies")
    errors = [field for field in required_true if decision.get(field) is not True]
    errors.extend(field for field in required_false if decision.get(field) is not False)
    return errors


def _dist_transition_errors(
    before: Mapping[str, Mapping[str, object]],
    after: Mapping[str, Mapping[str, object]],
    *,
    cleanup: set[str],
    build_reason: str | None,
) -> list[str]:
    errors: list[str] = []
    if build_reason not in {"task_required", "missing_wheel_only_skip"}:
        errors.append("build reason is not allowed")
    for inventory_name, inventory in (("before", before), ("after", after)):
        for path, metadata in inventory.items():
            if not isinstance(path, str) or not path:
                errors.append(f"{inventory_name} inventory path must be explicit")
            for field in ("checksum", "ignored", "ownership"):
                if field not in metadata:
                    errors.append(f"{inventory_name} inventory {path} is missing {field}")
    for path, metadata in before.items():
        if path not in after:
            errors.append(f"existing artifact was deleted or moved: {path}")
        elif after[path].get("checksum") != metadata.get("checksum"):
            errors.append(f"existing artifact was overwritten: {path}")
    attributable: set[str] = set()
    for path in after.keys() - before.keys():
        metadata = after[path]
        if (
            metadata.get("ignored") is True
            and metadata.get("ownership") == "build"
            and metadata.get("produced_by_build") is True
        ):
            attributable.add(path)
        else:
            errors.append(f"new artifact cannot be attributed to this build: {path}")
    if not cleanup <= attributable:
        errors.append("cleanup contains existing, user-owned, or unattributable artifacts")
    return errors


def _assignment_collection_errors(
    records: list[Mapping[str, object]], *, pr: int, branch: str
) -> list[str]:
    errors: list[str] = []
    scoped = [
        record for record in records if record.get("pr") == pr and record.get("branch") == branch
    ]
    active = [record for record in scoped if record.get("active") is True]
    if len(active) > 1:
        errors.append("PR and branch have more than one active writer")
    by_agent = {str(record.get("agent")): record for record in scoped}
    for index, record in enumerate(scoped):
        switching = "previous_agent" in record
        errors.extend(
            f"record {index}: {error}" for error in _assignment_errors(record, switching=switching)
        )
        if record.get("active") not in {True, False}:
            errors.append(f"record {index}: active must be explicit")
        if switching:
            previous = by_agent.get(str(record.get("previous_agent")))
            if previous is None:
                errors.append(f"record {index}: previous writer record is missing")
            elif previous.get("active") is not False:
                errors.append(f"record {index}: previous writer must be inactive")
            if record.get("next_agent") != record.get("agent"):
                errors.append(f"record {index}: next agent identity does not match")
    return errors


def test_shared_governance_uses_tool_neutral_roles() -> None:
    for relative_path in SHARED_GOVERNANCE_FILES:
        text = _text(relative_path)
        assert "Implementation Agent" in text, relative_path
        assert "Environment Verification Agent" in text, relative_path
        assert "Independent Review Agent" in text, relative_path
        assert "Human" in text, relative_path

    workflow = _text("ai/workflows/team-collaboration.md")
    assert "Cline" in _text("ai/adapters/cline.md")
    assert "Codex" in _text("ai/adapters/codex.md")
    assert "Cline | Implementation Agent" not in workflow
    assert "Codex | Implementation Agent" not in workflow


def test_assignment_schema_accepts_a_single_writer_record() -> None:
    record = {
        "role": "Implementation Agent",
        "tool": "Codex",
        "os": "Windows",
        "starting_head": "a" * 40,
        "human_evidence_url": "https://github.com/example/repo/pull/1#issuecomment-2",
        "single_writer": True,
    }
    assert _assignment_errors(record) == []


@pytest.mark.parametrize(
    ("removed", "replacement"),
    (
        ("tool", None),
        ("os", None),
        ("starting_head", "moving-HEAD"),
        ("human_evidence_url", "chat-only"),
        ("single_writer", False),
    ),
)
def test_assignment_schema_fails_closed(removed: str, replacement: object) -> None:
    record: dict[str, object] = {
        "role": "Implementation Agent",
        "tool": "Codex",
        "os": "Windows",
        "starting_head": "a" * 40,
        "human_evidence_url": "https://github.com/example/repo/pull/1#issuecomment-2",
        "single_writer": True,
    }
    if replacement is None:
        del record[removed]
    else:
        record[removed] = replacement
    assert _assignment_errors(record), removed


def test_agent_switch_requires_old_writer_stop_evidence() -> None:
    record = {
        "role": "Implementation Agent",
        "tool": "Cline",
        "os": "Linux",
        "starting_head": "b" * 40,
        "human_evidence_url": "https://github.com/example/repo/pull/2#issuecomment-3",
        "single_writer": True,
        "previous_agent": "Codex/Windows",
        "next_agent": "Cline/Linux",
        "previous_agent_stop_head": "b" * 40,
    }
    assert _assignment_errors(record, switching=True) == []
    record["previous_agent_stop_head"] = "c" * 40
    assert _assignment_errors(record, switching=True)


def test_workflow_freezes_assignment_and_switch_fields() -> None:
    workflow = _text("ai/workflows/team-collaboration.md")
    for field in (
        "tool",
        "OS",
        "Starting Head",
        "human evidence URL",
        "single writer",
        "previous agent",
        "next agent",
        "stop Head",
    ):
        assert field.lower() in workflow.lower(), field


def test_lane_evidence_accepts_capable_agents_on_exact_head() -> None:
    head = "d" * 40
    portable = _valid_lane_record("portable", "Linux", head)
    windows = _valid_lane_record("windows", "Windows", head)
    miniqmt = _valid_lane_record("windows_miniqmt", "Windows", head)
    assert _lane_errors(portable, pr_head=head) == []
    assert _lane_errors(windows, pr_head=head) == []
    assert _lane_errors(miniqmt, pr_head=head) == []


@pytest.mark.parametrize(
    ("lane", "field", "replacement"),
    (
        ("windows", "os", "Linux"),
        ("windows_miniqmt", "os", "Linux"),
        ("portable", "skipped", 3),
        ("portable", "head", "f" * 40),
        ("windows_miniqmt", "miniqmt_available", False),
        ("windows_miniqmt", "xtquant_task_approved", False),
        ("windows_miniqmt", "userdata_mini_verified", False),
        ("windows_miniqmt", "unique_session_verified", False),
        ("windows_miniqmt", "simulation_account_allowlisted", False),
        ("windows_miniqmt", "real_money", True),
        ("portable", "evidence_url", "chat-only"),
    ),
)
def test_lane_evidence_fails_closed(lane: str, field: str, replacement: object) -> None:
    os_name = "Windows" if lane != "portable" else "Linux"
    record = _valid_lane_record(lane, os_name, "e" * 40)
    record[field] = replacement
    assert _lane_errors(record, pr_head="e" * 40)


def test_simulation_order_requires_separate_task_and_human_evidence() -> None:
    record = _valid_lane_record("windows_miniqmt", "Windows", "e" * 40)
    record.update(
        {
            "simulation_order": True,
            "separate_active_task": False,
            "human_evidence_url": "chat-only",
        }
    )
    assert _lane_errors(record, pr_head="e" * 40)


def test_workflow_defines_capability_lanes_and_head_invalidation() -> None:
    workflow = _text("ai/workflows/team-collaboration.md")
    for lane in ("portable", "windows", "windows_miniqmt"):
        assert lane in workflow
    for field in (
        "task",
        "Base",
        "Head",
        "role",
        "tool",
        "OS",
        "Python",
        "Poetry",
        "command",
        "exit code",
        "passed",
        "failed",
        "skipped",
        "evidence URL",
    ):
        assert field.lower() in workflow.lower(), field
    assert "Head changes" in workflow or "Head 改变" in workflow
    assert "BLOCKED" in workflow


def test_human_only_side_effect_and_lifecycle_authority() -> None:
    combined = "\n".join(_text(path) for path in PERSISTENT_AUTHORITY_FILES)
    assert "human-only" in combined.lower() or "人类独占" in combined
    assert "separate active task" in combined.lower() or "独立 active task" in combined
    assert "real-money" in combined.lower() or "真实资金" in combined
    assert "forbidden" in combined.lower() or "禁止" in combined

    contradictions = (
        re.compile(r"human\s+or\s+(?:reviewer|review agent|automation)", re.IGNORECASE),
        re.compile(r"人类或(?:Reviewer|Review Agent|自动化)", re.IGNORECASE),
    )
    for pattern in contradictions:
        assert pattern.search(combined) is None, pattern.pattern


def test_poetry_workflow_requires_original_commands_and_minimum_escalation() -> None:
    workflow = _text("ai/workflows/poetry-verification.md")
    assert "['poetry', 'run']" in workflow
    assert "['poetry', 'build']" in workflow
    assert "bundled Python" in workflow
    assert "direct pytest" in workflow
    assert "second environment" in workflow
    assert "reinstall" in workflow.lower()
    assert "SymbolicLink" in workflow
    assert "access denied" in workflow.lower()


@pytest.mark.parametrize(
    ("command", "valid"),
    (
        ("poetry run pytest tests/spec", True),
        ("poetry run mypy src scripts", True),
        ("poetry build", True),
        ("pytest tests/spec", False),
        ("python -m pytest tests/spec", False),
        ("bundled/python pytest tests/spec", False),
        ("poetry install", False),
        ("poetry run pip install extra", False),
        ("poetry run pytest --no-verify", False),
    ),
)
def test_poetry_command_allow_structure_is_fail_closed(command: str, valid: bool) -> None:
    build_reason = "task_required" if command == "poetry build" else None
    assert (
        _poetry_command_errors(command, expected_commands={command}, build_reason=build_reason)
        == []
    ) is valid


def test_worktree_reuse_checks_python_project_and_lock_compatibility() -> None:
    workflow = _text("ai/workflows/poetry-verification.md")
    for token in ("Python", "pyproject.toml", "poetry.lock", "worktree", "PLAN_BLOCKED"):
        assert token in workflow
    assert "do not create" in workflow.lower() or "不得创建" in workflow
    assert "do not install" in workflow.lower() or "不得安装" in workflow


def test_build_flow_protects_existing_dist_and_requires_zero_contract_skips() -> None:
    workflow = _text("ai/workflows/poetry-verification.md")
    for token in (
        "dist/ before",
        "dist/ after",
        "attributable",
        "existing",
        "poetry build",
        "0 skipped",
        "clean worktree",
    ):
        assert token.lower() in workflow.lower(), token


def test_task022_keeps_history_and_appends_environment_erratum() -> None:
    task = _text("tasks/completed/TASK-022-observability-control-contracts.md")
    assert "On 2026-08-17" in task
    assert "On 2026-08-24" in task
    assert "574 passed / 6 failed" in task
    assert "614 passed / 6 failed" in task
    assert "2026-09-01 environment evidence erratum" in task.lower()
    assert "sandbox access boundary" in task.lower()
    assert "does not prove Poetry is damaged" in task


def test_template_prompt_workflow_share_environment_evidence_fields() -> None:
    files = (
        "tasks/templates/task-template.md",
        "ai/prompts/miniqmt-m1-task.md",
        "ai/workflows/team-collaboration.md",
    )
    for relative_path in files:
        text = _text(relative_path).lower()
        for token in (
            "implementation assignment",
            "verification lanes",
            "environment evidence",
            "exact head",
            "unverified scope",
            "expected base",
            "requirement",
            "timestamp",
            "sanitized_evidence",
            "expected command set",
            "required-lane satisfaction",
            "pr/branch single-writer",
        ):
            assert token in text, f"{relative_path}: {token}"


def test_codex_and_cline_adapters_report_only_actual_capabilities() -> None:
    codex = _text("ai/adapters/codex.md")
    cline = _text("ai/adapters/cline.md")
    assert "Implementation Agent" in codex
    assert "Environment Verification Agent" in codex
    assert "['poetry', 'run']" in codex
    assert "['poetry', 'build']" in codex
    assert "Linux" in cline
    assert "portable" in cline
    assert "Windows" in cline
    assert "Mini QMT" in cline
    assert "不得声称" in cline or "must not claim" in cline.lower()


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("base", "a" * 40),
        ("head", "b" * 40),
        ("timestamp", None),
        ("sanitized_evidence", None),
        ("unverified_scope", None),
        ("role", "Independent Review Agent"),
    ),
)
def test_environment_evidence_schema_and_identity_fail_closed(
    field: str, replacement: object
) -> None:
    record = _complete_evidence_record("poetry run pytest tests/spec")
    if replacement is None:
        del record[field]
    else:
        record[field] = replacement
    assert _environment_evidence_schema_errors(
        record,
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
    )


def test_environment_evidence_schema_accepts_complete_current_identity() -> None:
    record = _complete_evidence_record("poetry run pytest tests/spec")
    assert (
        _environment_evidence_schema_errors(
            record,
            expected_task="TASK-057",
            expected_base="c" * 40,
            expected_head="d" * 40,
        )
        == []
    )


def test_windows_miniqmt_evidence_requires_applicable_version() -> None:
    record = _complete_evidence_record("poetry run pytest tests/integration")
    record["lane"] = "windows_miniqmt"
    assert _environment_evidence_schema_errors(
        record,
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
    )
    record["xtquant_version"] = "sanitized-version"
    assert (
        _environment_evidence_schema_errors(
            record,
            expected_task="TASK-057",
            expected_base="c" * 40,
            expected_head="d" * 40,
        )
        == []
    )


def test_required_lane_satisfaction_accepts_exact_successful_command_set() -> None:
    commands = {
        "poetry run pytest tests/spec",
        "poetry run mypy src scripts",
    }
    records = [_complete_evidence_record(command) for command in sorted(commands)]
    assert (
        _required_lane_satisfaction_errors(
            records,
            expected_task="TASK-057",
            expected_base="c" * 40,
            expected_head="d" * 40,
            lane="portable",
            expected_commands=commands,
            skip_allowances={},
        )
        == []
    )


@pytest.mark.parametrize(
    ("mutation", "value"),
    (
        ("exit_code", 1),
        ("failed", 1),
        ("skipped", 1),
        ("executed", 0),
        ("passed", -1),
    ),
)
def test_required_lane_satisfaction_rejects_unsuccessful_records(
    mutation: str, value: object
) -> None:
    command = "poetry run pytest tests/spec"
    record = _complete_evidence_record(command)
    record[mutation] = value
    assert _required_lane_satisfaction_errors(
        [record],
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
        lane="portable",
        expected_commands={command},
        skip_allowances={},
    )


def test_required_lane_satisfaction_rejects_missing_expected_command() -> None:
    assert _required_lane_satisfaction_errors(
        [_complete_evidence_record("poetry run pytest tests/spec")],
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
        lane="portable",
        expected_commands={
            "poetry run pytest tests/spec",
            "poetry run mypy src scripts",
        },
        skip_allowances={},
    )


def test_required_lane_satisfaction_rejects_unexpected_substitute_command() -> None:
    assert _required_lane_satisfaction_errors(
        [_complete_evidence_record("pytest tests/spec")],
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
        lane="portable",
        expected_commands={"poetry run pytest tests/spec"},
        skip_allowances={},
    )


def test_allowed_skip_requires_explicit_scope() -> None:
    command = "poetry run pytest tests/contract"
    record = _complete_evidence_record(command)
    record["executed"] = 2
    record["skipped"] = 1
    assert _required_lane_satisfaction_errors(
        [record],
        expected_task="TASK-057",
        expected_base="c" * 40,
        expected_head="d" * 40,
        lane="portable",
        expected_commands={command},
        skip_allowances={command: 1},
    )
    record["unverified_scope"] = "one missing-wheel-only contract case"
    assert (
        _required_lane_satisfaction_errors(
            [record],
            expected_task="TASK-057",
            expected_base="c" * 40,
            expected_head="d" * 40,
            lane="portable",
            expected_commands={command},
            skip_allowances={command: 1},
        )
        == []
    )


@pytest.mark.parametrize(
    "command",
    (
        "poetry run python -m venv .second-env",
        "poetry run poetry add requests",
        "poetry run python -m pip install requests",
        "poetry run python -m pip uninstall requests",
        "poetry run poetry install",
        "poetry run poetry update",
        "poetry run poetry remove requests",
        "poetry run poetry lock",
        "pytest tests/spec",
        "python -m pytest tests/spec",
        "ruff check .",
        "mypy src scripts",
        "bundled/python pytest tests/spec",
        "poetry run pytest tests/spec --no-verify",
    ),
)
def test_poetry_gate_rejects_mutation_and_substitute_commands(command: str) -> None:
    expected = {"poetry run pytest tests/spec"}
    assert _poetry_command_errors(command, expected_commands=expected)


def test_poetry_gate_uses_exact_normalized_expected_command_set() -> None:
    expected = {"poetry run pytest tests/spec"}
    assert (
        _poetry_command_errors("  poetry   run pytest   tests/spec  ", expected_commands=expected)
        == []
    )
    assert _poetry_command_errors("poetry run pytest tests/contract", expected_commands=expected)


@pytest.mark.parametrize("reason", (None, "unrelated failure", "always build"))
def test_poetry_build_requires_an_allowed_reason(reason: str | None) -> None:
    assert _poetry_command_errors(
        "poetry build", expected_commands={"poetry build"}, build_reason=reason
    )


@pytest.mark.parametrize("reason", ("task_required", "missing_wheel_only_skip"))
def test_poetry_build_accepts_only_contractual_reasons(reason: str) -> None:
    assert (
        _poetry_command_errors(
            "poetry build", expected_commands={"poetry build"}, build_reason=reason
        )
        == []
    )


def test_worktree_reuse_accepts_only_compatible_existing_environment() -> None:
    decision = {
        "existing_environment_valid": True,
        "dependency_complete": True,
        "python_compatible": True,
        "pyproject_identity_compatible": True,
        "lock_identity_compatible": True,
        "original_poetry_entrypoint": True,
        "create_environment": False,
        "install_dependencies": False,
        "compatibility_verifiable": True,
    }
    assert _worktree_reuse_errors(decision) == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("existing_environment_valid", False),
        ("dependency_complete", False),
        ("python_compatible", False),
        ("pyproject_identity_compatible", False),
        ("lock_identity_compatible", False),
        ("original_poetry_entrypoint", False),
        ("create_environment", True),
        ("install_dependencies", True),
        ("compatibility_verifiable", False),
    ),
)
def test_worktree_reuse_fails_closed(field: str, value: bool) -> None:
    decision = {
        "existing_environment_valid": True,
        "dependency_complete": True,
        "python_compatible": True,
        "pyproject_identity_compatible": True,
        "lock_identity_compatible": True,
        "original_poetry_entrypoint": True,
        "create_environment": False,
        "install_dependencies": False,
        "compatibility_verifiable": True,
    }
    decision[field] = value
    assert _worktree_reuse_errors(decision)


def test_dist_inventory_accepts_only_new_ignored_attributable_cleanup() -> None:
    before = {
        "dist/user.whl": {
            "checksum": "old",
            "ignored": True,
            "ownership": "user-owned",
        }
    }
    after = {
        **before,
        "dist/new.whl": {
            "checksum": "new",
            "ignored": True,
            "ownership": "build",
            "produced_by_build": True,
        },
    }
    assert (
        _dist_transition_errors(
            before,
            after,
            cleanup={"dist/new.whl"},
            build_reason="missing_wheel_only_skip",
        )
        == []
    )


def test_dist_inventory_rejects_incomplete_metadata() -> None:
    before = {
        "dist/user.whl": {
            "checksum": "old",
            "ignored": True,
        }
    }
    assert _dist_transition_errors(
        before,
        before,
        cleanup=set(),
        build_reason="task_required",
    )


@pytest.mark.parametrize("case", ("overwrite", "delete", "move", "cleanup_existing"))
def test_dist_inventory_rejects_destructive_existing_artifact_changes(case: str) -> None:
    before = {
        "dist/user.whl": {
            "checksum": "old",
            "ignored": True,
            "ownership": "user-owned",
        }
    }
    after: dict[str, dict[str, object]] = {
        "dist/user.whl": dict(before["dist/user.whl"]),
        "dist/new.whl": {
            "checksum": "new",
            "ignored": True,
            "ownership": "build",
            "produced_by_build": True,
        },
    }
    cleanup = {"dist/new.whl"}
    if case == "overwrite":
        after["dist/user.whl"]["checksum"] = "changed"
    elif case == "delete":
        del after["dist/user.whl"]
    elif case == "move":
        moved = after.pop("dist/user.whl")
        after["dist/moved-user.whl"] = moved
    else:
        cleanup.add("dist/user.whl")
    assert _dist_transition_errors(
        before,
        after,
        cleanup=cleanup,
        build_reason="missing_wheel_only_skip",
    )


def _writer_record(
    agent: str,
    *,
    active: bool,
    starting_head: str,
    previous_agent: str | None = None,
    previous_agent_stop_head: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "role": "Implementation Agent",
        "tool": agent.split("/")[0],
        "os": agent.split("/")[1],
        "agent": agent,
        "pr": 100,
        "branch": "codex/task-057-implementation",
        "starting_head": starting_head,
        "human_evidence_url": "https://github.com/example/repo/pull/100#issuecomment-2",
        "single_writer": True,
        "active": active,
    }
    if previous_agent is not None:
        record.update(
            {
                "previous_agent": previous_agent,
                "next_agent": agent,
                "previous_agent_stop_head": previous_agent_stop_head,
            }
        )
    return record


def test_assignment_collection_accepts_a_sequential_human_switch() -> None:
    stop_head = "a" * 40
    records = [
        _writer_record("Codex/Windows", active=False, starting_head="9" * 40),
        _writer_record(
            "Cline/Linux",
            active=True,
            starting_head=stop_head,
            previous_agent="Codex/Windows",
            previous_agent_stop_head=stop_head,
        ),
    ]
    assert (
        _assignment_collection_errors(records, pr=100, branch="codex/task-057-implementation") == []
    )


def test_assignment_collection_rejects_two_active_writers() -> None:
    records = [
        _writer_record("Codex/Windows", active=True, starting_head="a" * 40),
        _writer_record("Cline/Linux", active=True, starting_head="a" * 40),
    ]
    assert _assignment_collection_errors(records, pr=100, branch="codex/task-057-implementation")


def test_assignment_collection_rejects_switch_while_old_writer_is_active() -> None:
    stop_head = "a" * 40
    records = [
        _writer_record("Codex/Windows", active=True, starting_head="9" * 40),
        _writer_record(
            "Cline/Linux",
            active=True,
            starting_head=stop_head,
            previous_agent="Codex/Windows",
            previous_agent_stop_head=stop_head,
        ),
    ]
    assert _assignment_collection_errors(records, pr=100, branch="codex/task-057-implementation")


def test_assignment_collection_rejects_switch_head_mismatch() -> None:
    records = [
        _writer_record("Codex/Windows", active=False, starting_head="9" * 40),
        _writer_record(
            "Cline/Linux",
            active=True,
            starting_head="a" * 40,
            previous_agent="Codex/Windows",
            previous_agent_stop_head="b" * 40,
        ),
    ]
    assert _assignment_collection_errors(records, pr=100, branch="codex/task-057-implementation")
