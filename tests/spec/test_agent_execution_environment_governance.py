"""Governance tests for tool-neutral agents and environment evidence (TASK-057)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
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


def _poetry_command_errors(command: str) -> list[str]:
    normalized = " ".join(command.strip().split())
    allowed = normalized.startswith("poetry run ") or normalized == "poetry build"
    if not allowed:
        return ["project verification must use an original poetry run/build command"]
    mutation_tokens = ("poetry install", "pip install", "poetry env remove", "--no-verify")
    return [token for token in mutation_tokens if token in normalized]


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
    assert (_poetry_command_errors(command) == []) is valid


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
