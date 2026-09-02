"""Document and template integration tests for TASK-057 governance."""

from __future__ import annotations

from pathlib import Path

import yaml
from scripts import validate_agent_environment
from scripts.validate_specs import extract_front_matter

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
HANDOFF = ROOT / "ai/handoffs/TASK-057-REPAIR-v2.yaml"

SHARED_GOVERNANCE_FILES = (
    "AGENTS.md",
    "ai/workflows/team-collaboration.md",
    "tasks/templates/task-template.md",
    "ai/prompts/miniqmt-m1-task.md",
)


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_shared_governance_uses_tool_neutral_roles() -> None:
    for relative_path in SHARED_GOVERNANCE_FILES:
        text = _text(relative_path)
        assert "Implementation Agent" in text, relative_path
        assert "Environment Verification Agent" in text, relative_path
        assert "Independent Review Agent" in text, relative_path
        assert "Human" in text, relative_path
    workflow = _text("ai/workflows/team-collaboration.md")
    assert "Cline、Codex" in workflow or "Codex、Cline" in workflow
    assert "tool/adapter" in workflow


def test_workflow_and_template_name_the_only_formal_machine_gate() -> None:
    workflow = _text("ai/workflows/team-collaboration.md")
    template = _text("tasks/templates/task-template.md")
    for text in (workflow, template):
        assert "scripts/validate_agent_environment.py" in text
        assert "ai/schemas/agent-assignment.schema.yaml" in text
        assert "ai/schemas/agent-environment-evidence.schema.yaml" in text
        assert "ASSIGN" in text
        assert "STOP" in text
        assert "SWITCH" in text
        assert "opaque exact" in text
    assert "唯一" in workflow or "only formal" in workflow.lower()


def test_workflow_freezes_capability_lanes_and_head_invalidation() -> None:
    workflow = _text("ai/workflows/team-collaboration.md")
    for lane in ("portable", "windows", "windows_miniqmt"):
        assert lane in workflow
    for phrase in (
        "required lane",
        "exact Head",
        "BLOCKED",
        "real_money: false",
        "simulation_order",
        "Mini QMT",
    ):
        assert phrase in workflow
    assert "capability" in workflow
    assert "authorization" in workflow


def test_poetry_workflow_requires_original_commands_and_minimum_escalation() -> None:
    workflow = _text("ai/workflows/poetry-verification.md")
    for phrase in (
        "poetry --version",
        "poetry env info",
        "poetry run",
        "['poetry', 'run']",
        "['poetry', 'build']",
        "SymbolicLink",
        "pyproject.toml",
        "poetry.lock",
        "checksum",
        "0 skipped",
    ):
        assert phrase in workflow
    assert "不得重装 Poetry" in workflow
    assert "不得创建 second environment" in workflow


def test_template_prompt_workflow_share_evidence_identity_and_side_effect_fields() -> None:
    texts = {
        path: _text(path)
        for path in (
            "tasks/templates/task-template.md",
            "ai/prompts/miniqmt-m1-task.md",
            "ai/workflows/team-collaboration.md",
        )
    }
    for relative_path, text in texts.items():
        for phrase in (
            "implementation assignment",
            "verification lanes",
            "environment evidence",
            "Base",
            "Head",
            "tool",
            "OS",
            "evidence URL",
            "unverified scope",
            "real_money",
            "simulation_order",
        ):
            assert phrase.lower() in text.lower(), (relative_path, phrase)


def test_codex_and_cline_adapters_report_only_actual_capabilities() -> None:
    codex = _text("ai/adapters/codex.md")
    cline = _text("ai/adapters/cline.md")
    for text in (codex, cline):
        assert "Implementation Agent" in text
        assert "portable" in text
        assert "windows" in text
        assert "windows_miniqmt" in text
        assert "actual" in text.lower() or "实际" in text
    assert "['poetry', 'run']" in codex
    assert "Linux" in cline
    assert "不得" in cline


def test_task022_keeps_history_and_appends_environment_erratum() -> None:
    text = _text("tasks/completed/TASK-022-observability-control-contracts.md")
    assert "2026-09-01" in text
    assert "勘误" in text or "erratum" in text.lower()
    assert "sandbox" in text.lower()
    assert "SymbolicLink" in text
    assert "Poetry" in text


def test_formal_validator_is_integrated_with_frozen_task_and_handoff() -> None:
    task = extract_front_matter(TASK)
    handoff = yaml.safe_load(HANDOFF.read_text(encoding="utf-8"))
    authority = validate_agent_environment.build_authority(task, handoff)
    assert authority.task_id == "TASK-057"
    assert [lane.lane for lane in authority.required_lanes] == ["portable", "windows"]
    assert authority.prohibited_lanes == ("windows_miniqmt",)
    assert (ROOT / "ai/schemas/agent-assignment.schema.yaml").is_file()
    assert (ROOT / "ai/schemas/agent-environment-evidence.schema.yaml").is_file()
