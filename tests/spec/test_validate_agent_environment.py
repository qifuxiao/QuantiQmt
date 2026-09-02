"""Formal environment-evidence validator tests for TASK-057 Plan v2."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema.validators import Draft202012Validator
from scripts import validate_agent_environment as validator
from scripts.validate_specs import extract_front_matter

ROOT = Path(__file__).resolve().parents[2]
TASK_PATH = ROOT / "tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
HANDOFF_PATH = ROOT / "ai/handoffs/TASK-057-REPAIR-v2.yaml"
ASSIGNMENT_SCHEMA_PATH = ROOT / "ai/schemas/agent-assignment.schema.yaml"
EVIDENCE_SCHEMA_PATH = ROOT / "ai/schemas/agent-environment-evidence.schema.yaml"
PR = 100
BRANCH = "codex/task-057-implementation"
HEAD = "d" * 40
SWITCH_HEAD = "c" * 40


def _task() -> dict[str, Any]:
    return copy.deepcopy(extract_front_matter(TASK_PATH))


def _handoff() -> dict[str, Any]:
    value = yaml.safe_load(HANDOFF_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return copy.deepcopy(value)


def _authority() -> validator.Authority:
    return validator.build_authority(_task(), _handoff())


def _github_url(suffix: int) -> str:
    return f"https://github.com/example/repo/pull/100#issuecomment-{suffix}"


def _assignment_event(
    event: str,
    sequence: int,
    agent: str,
    *,
    tool: str,
    os_name: str,
    pr_head: str,
    starting_head: str | None = None,
    stop_head: str | None = None,
    previous_agent: str | None = None,
    previous_agent_stop_head: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event": event,
        "sequence": sequence,
        "task": "TASK-057",
        "pr": PR,
        "branch": BRANCH,
        "role": "Implementation Agent",
        "agent": agent,
        "tool": tool,
        "os": os_name,
        "human_evidence_url": _github_url(sequence),
        "single_writer": True,
        "pr_head": pr_head,
    }
    if starting_head is not None:
        record["starting_head"] = starting_head
    if stop_head is not None:
        record["stop_head"] = stop_head
    if previous_agent is not None:
        record["previous_agent"] = previous_agent
        record["next_agent"] = agent
    if previous_agent_stop_head is not None:
        record["previous_agent_stop_head"] = previous_agent_stop_head
    return record


def _assignments() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "events": [
            _assignment_event(
                "ASSIGN",
                1,
                "cline-windows-plan-v1",
                tool="Cline",
                os_name="Windows",
                pr_head="b" * 40,
                starting_head="b" * 40,
            ),
            _assignment_event(
                "STOP",
                2,
                "cline-windows-plan-v1",
                tool="Cline",
                os_name="Windows",
                pr_head=SWITCH_HEAD,
                stop_head=SWITCH_HEAD,
            ),
            _assignment_event(
                "SWITCH",
                3,
                "codex-windows-plan-v2",
                tool="Codex",
                os_name="Windows",
                pr_head=SWITCH_HEAD,
                starting_head=SWITCH_HEAD,
                previous_agent="cline-windows-plan-v1",
                previous_agent_stop_head=SWITCH_HEAD,
            ),
        ],
    }


def _evidence_record(command: str, lane: str, authority: validator.Authority) -> dict[str, Any]:
    return {
        "task": authority.task_id,
        "base": authority.expected_base,
        "head": HEAD,
        "pr": PR,
        "branch": BRANCH,
        "lane": lane,
        "requirement": "required",
        "role": "Implementation Agent",
        "tool": "Codex",
        "os": "Windows",
        "python_version": "3.12.10",
        "poetry_version": "2.4.1",
        "xtquant": None,
        "command": command,
        "exit_code": 0,
        "executed": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "timestamp": "2026-09-02T09:00:00+08:00",
        "sanitized_evidence": True,
        "unverified_scope": "",
        "evidence_url": _github_url(20),
        "capabilities": {
            "portable": True,
            "windows": True,
            "miniqmt_available": False,
            "userdata_mini_verified": False,
            "unique_session_verified": False,
            "simulation_account_allowlisted": False,
        },
        "miniqmt_connection": False,
        "account_query": False,
        "simulation_order": False,
        "real_money": False,
    }


def _evidence() -> dict[str, Any]:
    authority = _authority()
    records = [
        _evidence_record(command, lane.lane, authority)
        for lane in authority.required_lanes
        for command in lane.commands
    ]
    return {"schema_version": 1, "records": records}


def _validate_evidence(document: dict[str, Any]) -> list[str]:
    return validator.validate_evidence(
        document,
        authority=_authority(),
        expected_head=HEAD,
        pr=PR,
        branch=BRANCH,
        pr_head=HEAD,
        assignments=_assignments(),
    )


def test_formal_schemas_are_valid_draft_2020_12() -> None:
    for path in (ASSIGNMENT_SCHEMA_PATH, EVIDENCE_SCHEMA_PATH):
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_git_loader_reads_the_exact_active_task_and_repair_handoff() -> None:
    authority = validator.load_authority_from_git(
        ROOT,
        head="HEAD",
        task_path=TASK_PATH.relative_to(ROOT),
        handoff_path=HANDOFF_PATH.relative_to(ROOT),
    )
    assert authority.task_id == "TASK-057"
    assert [lane.lane for lane in authority.required_lanes] == ["portable", "windows"]
    assert authority.prohibited_lanes == ("windows_miniqmt",)


def test_task_and_handoff_required_lanes_are_deep_equal_and_partition_commands() -> None:
    authority = _authority()
    assert validator.authority_errors(_task(), _handoff()) == []
    assert [lane.lane for lane in authority.required_lanes] == ["portable", "windows"]
    assert Counter(
        command for lane in authority.required_lanes for command in lane.commands
    ) == Counter(authority.verification_commands)


@pytest.mark.parametrize("location", ("task", "handoff"))
def test_required_lane_drift_fails_closed(location: str) -> None:
    task = _task()
    handoff = _handoff()
    target = (
        task["verification"]["required_lanes"] if location == "task" else handoff["required_lanes"]
    )
    target[0]["minimum_records"] = 99
    assert validator.authority_errors(task, handoff)


@pytest.mark.parametrize("case", ("missing", "empty", "duplicate", "unknown", "empty_commands"))
def test_invalid_required_lane_declarations_fail_closed(case: str) -> None:
    task = _task()
    handoff = _handoff()
    if case == "missing":
        del task["verification"]["required_lanes"]
    elif case == "empty":
        task["verification"]["required_lanes"] = []
        handoff["required_lanes"] = []
    elif case == "duplicate":
        duplicate = copy.deepcopy(task["verification"]["required_lanes"][0])
        task["verification"]["required_lanes"].append(duplicate)
        handoff["required_lanes"].append(copy.deepcopy(duplicate))
    elif case == "unknown":
        task["verification"]["required_lanes"][0]["lane"] = "remote_magic"
        handoff["required_lanes"][0]["lane"] = "remote_magic"
    else:
        task["verification"]["required_lanes"][0]["commands"] = []
        handoff["required_lanes"][0]["commands"] = []
    assert validator.authority_errors(task, handoff)


def test_empty_top_level_verification_commands_fail_closed() -> None:
    task = _task()
    task["verification"]["commands"] = []
    assert validator.authority_errors(task, _handoff())


@pytest.mark.parametrize("case", ("omitted", "duplicated"))
def test_required_lane_commands_must_exactly_partition_top_level_commands(case: str) -> None:
    task = _task()
    handoff = _handoff()
    if case == "omitted":
        task["verification"]["required_lanes"][0]["commands"].pop()
        handoff["required_lanes"][0]["commands"].pop()
    else:
        duplicate = task["verification"]["required_lanes"][0]["commands"][0]
        task["verification"]["required_lanes"][1]["commands"].append(duplicate)
        handoff["required_lanes"][1]["commands"].append(duplicate)
    assert validator.authority_errors(task, handoff)


def test_exact_complete_evidence_and_ordered_assignment_events_pass() -> None:
    assert (
        validator.validate_assignments(_assignments(), task_id="TASK-057", pr=PR, branch=BRANCH)
        == []
    )
    assert _validate_evidence(_evidence()) == []


def test_empty_evidence_collection_fails_closed() -> None:
    assert _validate_evidence({"schema_version": 1, "records": []})


@pytest.mark.parametrize("location", ("envelope", "record"))
def test_evidence_cannot_supply_or_override_expected_commands(location: str) -> None:
    evidence = _evidence()
    if location == "envelope":
        evidence["expected_commands"] = ["poetry run pytest -q"]
    else:
        evidence["records"][0]["expected_commands"] = ["poetry run pytest -q"]
    assert _validate_evidence(evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("task", "TASK-999"),
        ("base", "a" * 40),
        ("head", "a" * 40),
        ("pr", 999),
        ("branch", "other/branch"),
    ),
)
def test_mixed_record_identity_fails_closed(field: str, value: Any) -> None:
    evidence = _evidence()
    evidence["records"][0][field] = value
    assert _validate_evidence(evidence)


@pytest.mark.parametrize("case", ("missing", "duplicate", "substitute"))
def test_command_coverage_is_opaque_exact_and_complete(case: str) -> None:
    evidence = _evidence()
    if case == "missing":
        evidence["records"].pop(0)
    elif case == "duplicate":
        evidence["records"].append(copy.deepcopy(evidence["records"][0]))
    else:
        evidence["records"][0]["command"] += " "
    assert _validate_evidence(evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("exit_code", 1),
        ("executed", 0),
        ("failed", 1),
        ("skipped", 1),
    ),
)
def test_unsuccessful_or_inconsistent_command_results_fail(field: str, value: int) -> None:
    evidence = _evidence()
    evidence["records"][0][field] = value
    assert _validate_evidence(evidence)


def test_windows_lane_requires_actual_windows_capability() -> None:
    evidence = _evidence()
    record = next(item for item in evidence["records"] if item["lane"] == "windows")
    record["capabilities"]["windows"] = False
    assert _validate_evidence(evidence)


def test_task057_prohibits_windows_miniqmt_and_every_broker_side_effect() -> None:
    for field in ("miniqmt_connection", "account_query", "simulation_order", "real_money"):
        evidence = _evidence()
        evidence["records"][0][field] = True
        assert _validate_evidence(evidence), field
    evidence = _evidence()
    evidence["records"][0]["lane"] = "windows_miniqmt"
    assert _validate_evidence(evidence)


@pytest.mark.parametrize(
    "provenance",
    (
        {"source": "unknown", "value": "2026.vendor-r7", "verified": True},
        {"source": "package_metadata", "value": "", "verified": True},
        {"source": "vendor_api", "value": r"C:\\userdata_mini\\account-123", "verified": True},
        {"source": "vendor_api", "value": "secret-token", "verified": True},
        {"source": "vendor_api", "value": "123456789012", "verified": True},
        {"source": "vendor_api", "value": "2026.vendor-r7", "verified": False},
    ),
)
def test_xtquant_unknown_or_sensitive_provenance_fails(provenance: dict[str, Any]) -> None:
    assert validator.xtquant_provenance_errors(provenance)


@pytest.mark.parametrize(
    "provenance",
    (
        {"source": "package_metadata", "value": "2026.vendor-r7", "verified": True},
        {"source": "vendor_api", "value": "release_2026+broker.4", "verified": True},
    ),
)
def test_xtquant_trusted_opaque_provenance_passes(provenance: dict[str, Any]) -> None:
    assert validator.xtquant_provenance_errors(provenance) == []


@pytest.mark.parametrize("case", ("sequence", "double_writer", "bad_switch_url"))
def test_assignment_event_order_and_single_writer_fail_closed(case: str) -> None:
    assignments = _assignments()
    if case == "sequence":
        assignments["events"][2]["sequence"] = 2
    elif case == "double_writer":
        assignments["events"].insert(
            1,
            _assignment_event(
                "ASSIGN",
                2,
                "codex-windows-concurrent",
                tool="Codex",
                os_name="Windows",
                pr_head=SWITCH_HEAD,
                starting_head=SWITCH_HEAD,
            ),
        )
        assignments["events"][2]["sequence"] = 3
        assignments["events"][3]["sequence"] = 4
    else:
        assignments["events"][2]["human_evidence_url"] = "chat://not-durable"
    assert validator.validate_assignments(assignments, task_id="TASK-057", pr=PR, branch=BRANCH)


def test_switch_allows_distinct_agent_sessions_with_the_same_tool_and_os() -> None:
    assignments = _assignments()
    for event in assignments["events"][:2]:
        event.update(
            {
                "agent": "codex-windows-plan-v1",
                "tool": "Codex",
                "os": "Windows",
            }
        )
    assignments["events"][2].update(
        {
            "agent": "codex-windows-plan-v2",
            "tool": "Codex",
            "os": "Windows",
            "previous_agent": "codex-windows-plan-v1",
            "next_agent": "codex-windows-plan-v2",
        }
    )
    assert (
        validator.validate_assignments(assignments, task_id="TASK-057", pr=PR, branch=BRANCH) == []
    )


@pytest.mark.parametrize("field", ("stop_head", "starting_head", "pr_head"))
def test_assignment_switch_heads_must_match_exactly(field: str) -> None:
    assignments = _assignments()
    if field == "stop_head":
        assignments["events"][1][field] = "e" * 40
    else:
        assignments["events"][2][field] = "e" * 40
    assert validator.validate_assignments(assignments, task_id="TASK-057", pr=PR, branch=BRANCH)


def test_evidence_head_must_equal_current_pr_head() -> None:
    errors = validator.validate_evidence(
        _evidence(),
        authority=_authority(),
        expected_head=HEAD,
        pr=PR,
        branch=BRANCH,
        pr_head="e" * 40,
        assignments=_assignments(),
    )
    assert errors
