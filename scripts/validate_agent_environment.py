"""Validate ordered assignments and exact environment evidence against frozen authority.

TASK-057 treats task and Repair Handoff command strings as opaque, exact values.  This
module deliberately does not parse or reinterpret PowerShell/POSIX command text.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = PurePosixPath(
    "tasks/active/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
)
HANDOFF_PATH = PurePosixPath("ai/handoffs/TASK-057-REPAIR-v2.yaml")
ASSIGNMENT_SCHEMA = ROOT / "ai/schemas/agent-assignment.schema.yaml"
EVIDENCE_SCHEMA = ROOT / "ai/schemas/agent-environment-evidence.schema.yaml"
SUPPORTED_LANES = {"portable", "windows", "windows_miniqmt"}
TASK057_REQUIRED_LANES = ("portable", "windows")
TASK057_PROHIBITED_LANES = ("windows_miniqmt",)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SENSITIVE_VERSION_RE = re.compile(
    r"(?:userdata_mini|account|acct|credential|secret|token|password|passwd|pwd|api[-_]?key)",
    re.IGNORECASE,
)
OPAQUE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class LaneRequirement:
    lane: str
    capability: str
    minimum_records: int
    commands: tuple[str, ...]


@dataclass(frozen=True)
class Authority:
    task_id: str
    expected_base: str
    expected_pr_base: str
    task_blob: str
    verification_commands: list[str]
    required_lanes: tuple[LaneRequirement, ...]
    prohibited_lanes: tuple[str, ...]


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _parse_front_matter(text: str) -> dict[str, Any]:
    match = FRONT_MATTER_RE.match(text.replace("\r\n", "\n"))
    if match is None:
        raise ValueError("active task is missing YAML front matter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("active task front matter must be a mapping")
    return value


def _load_yaml_text(text: str, label: str) -> dict[str, Any]:
    value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a YAML mapping")
    return value


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _schema_errors(document: object, path: Path) -> list[str]:
    schema = _load_yaml_text(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
    validator = Draft202012Validator(schema)
    return [
        f"schema {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(document), key=lambda item: list(item.absolute_path)
        )
    ]


def _required_lane_errors(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    names: list[str] = []
    for index, raw_lane in enumerate(value):
        lane = _mapping(raw_lane)
        if lane is None:
            errors.append(f"{label}[{index}] must be a mapping")
            continue
        name = lane.get("lane")
        if not isinstance(name, str) or name not in SUPPORTED_LANES:
            errors.append(f"{label}[{index}] has an unknown lane")
        else:
            names.append(name)
        capability = lane.get("capability")
        if capability != name:
            errors.append(f"{label}[{index}] capability must match lane")
        minimum_records = lane.get("minimum_records")
        if type(minimum_records) is not int or minimum_records < 1:
            errors.append(f"{label}[{index}] minimum_records must be a positive integer")
        commands = lane.get("commands")
        if not isinstance(commands, list) or not commands:
            errors.append(f"{label}[{index}] commands must be a non-empty list")
        elif any(not isinstance(command, str) or not command for command in commands):
            errors.append(f"{label}[{index}] commands must contain exact non-empty strings")
        elif len(commands) != len(set(commands)):
            errors.append(f"{label}[{index}] commands contain duplicates")
    if len(names) != len(set(names)):
        errors.append(f"{label} contains duplicate lanes")
    return errors


def authority_errors(task: Mapping[str, Any], handoff: Mapping[str, Any]) -> list[str]:
    """Validate frozen task/Handoff authority without accepting caller command input."""

    errors: list[str] = []
    task_id = task.get("id")
    if task_id != "TASK-057" or task.get("status") != "active":
        errors.append("the exact active task must be TASK-057")
    if handoff.get("task_id") != task_id or handoff.get("plan_version") != "TASK-057-PLAN-v2":
        errors.append("Repair Handoff identity does not match TASK-057 Plan v2")
    for field in ("expected_base_sha", "expected_pr_base_sha", "task_blob_sha"):
        if not isinstance(handoff.get(field), str) or SHA_RE.fullmatch(handoff[field]) is None:
            errors.append(f"Handoff {field} must be an exact SHA")
    if handoff.get("expected_base_sha") != handoff.get("expected_pr_base_sha"):
        errors.append("Handoff Base and PR Base must be identical")

    verification = _mapping(task.get("verification"))
    if verification is None:
        return [*errors, "task verification must be a mapping"]
    commands = verification.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("verification.commands must be a non-empty list")
        commands = []
    elif any(not isinstance(command, str) or not command for command in commands):
        errors.append("verification.commands must contain exact non-empty strings")
    elif len(commands) != len(set(commands)):
        errors.append("verification.commands must not contain duplicates")

    task_lanes = verification.get("required_lanes")
    handoff_lanes = handoff.get("required_lanes")
    errors.extend(_required_lane_errors(task_lanes, label="task required_lanes"))
    errors.extend(_required_lane_errors(handoff_lanes, label="Handoff required_lanes"))
    if task_lanes != handoff_lanes:
        errors.append("task and Handoff required_lanes must be deep-equal")

    task_prohibited = verification.get("prohibited_lanes")
    handoff_prohibited = handoff.get("prohibited_lanes")
    if not isinstance(task_prohibited, list) or not task_prohibited:
        errors.append("task prohibited_lanes must be a non-empty list")
        task_prohibited = []
    if not isinstance(handoff_prohibited, list) or not handoff_prohibited:
        errors.append("Handoff prohibited_lanes must be a non-empty list")
        handoff_prohibited = []
    if task_prohibited != handoff_prohibited:
        errors.append("task and Handoff prohibited_lanes must be deep-equal")
    if any(lane not in SUPPORTED_LANES for lane in task_prohibited):
        errors.append("prohibited_lanes contains an unknown lane")
    if len(task_prohibited) != len(set(task_prohibited)):
        errors.append("prohibited_lanes contains duplicates")

    valid_task_lanes = task_lanes if isinstance(task_lanes, list) else []
    lane_names = tuple(
        raw_lane.get("lane")
        for raw_lane in valid_task_lanes
        if isinstance(raw_lane, Mapping) and isinstance(raw_lane.get("lane"), str)
    )
    if task_id == "TASK-057" and lane_names != TASK057_REQUIRED_LANES:
        errors.append("TASK-057 required lanes must be exactly portable and windows")
    if task_id == "TASK-057" and tuple(task_prohibited) != TASK057_PROHIBITED_LANES:
        errors.append("TASK-057 must prohibit windows_miniqmt")

    lane_commands: list[str] = []
    for raw_lane in valid_task_lanes:
        if isinstance(raw_lane, Mapping) and isinstance(raw_lane.get("commands"), list):
            lane_commands.extend(
                command for command in raw_lane["commands"] if isinstance(command, str)
            )
    if Counter(lane_commands) != Counter(
        command for command in commands if isinstance(command, str)
    ):
        errors.append("required-lane commands must exactly partition verification.commands")
    if len(lane_commands) != len(set(lane_commands)):
        errors.append("required-lane command partition contains duplicates")
    return errors


def build_authority(task: Mapping[str, Any], handoff: Mapping[str, Any]) -> Authority:
    errors = authority_errors(task, handoff)
    if errors:
        raise ValueError("; ".join(errors))
    verification = task["verification"]
    lanes = tuple(
        LaneRequirement(
            lane=raw_lane["lane"],
            capability=raw_lane["capability"],
            minimum_records=raw_lane["minimum_records"],
            commands=tuple(raw_lane["commands"]),
        )
        for raw_lane in verification["required_lanes"]
    )
    return Authority(
        task_id=task["id"],
        expected_base=handoff["expected_base_sha"],
        expected_pr_base=handoff["expected_pr_base_sha"],
        task_blob=handoff["task_blob_sha"],
        verification_commands=list(verification["commands"]),
        required_lanes=lanes,
        prohibited_lanes=tuple(verification["prohibited_lanes"]),
    )


def load_authority_from_git(
    repo: Path,
    *,
    head: str,
    task_path: Path | PurePosixPath,
    handoff_path: Path | PurePosixPath,
) -> Authority:
    """Read the unique active task and Handoff from an exact Git tree."""

    repo = repo.resolve()
    resolved_head = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}")
    task_posix = PurePosixPath(task_path).as_posix()
    handoff_posix = PurePosixPath(handoff_path).as_posix()
    task_files = _git(repo, "ls-tree", "-r", "--name-only", resolved_head, "--", "tasks/active")
    active: list[str] = []
    for path in task_files.splitlines():
        if not path.endswith(".md") or path.endswith("/README.md"):
            continue
        candidate = _parse_front_matter(_git(repo, "show", f"{resolved_head}:{path}"))
        if candidate.get("status") == "active":
            active.append(path)
    if active != [task_posix]:
        raise ValueError(
            f"exact Git Head must contain one active task at {task_posix}; got {active}"
        )
    task = _parse_front_matter(_git(repo, "show", f"{resolved_head}:{task_posix}"))
    handoff = _load_yaml_text(
        _git(repo, "show", f"{resolved_head}:{handoff_posix}"), "Repair Handoff"
    )
    authority = build_authority(task, handoff)
    actual_blob = _git(repo, "rev-parse", f"{resolved_head}:{task_posix}")
    if actual_blob != authority.task_blob:
        raise ValueError("active task blob does not match the frozen Repair Handoff")
    merge_base = _git(repo, "merge-base", authority.expected_base, resolved_head)
    if merge_base != authority.expected_base:
        raise ValueError("expected Base is not the exact merge-base of the validated Head")
    return authority


def xtquant_provenance_errors(value: object) -> list[str]:
    provenance = _mapping(value)
    if provenance is None:
        return ["xtquant provenance must be a mapping"]
    errors: list[str] = []
    if provenance.get("source") not in {"package_metadata", "vendor_api"}:
        errors.append("xtquant provenance source is not trusted")
    opaque = provenance.get("value")
    if not isinstance(opaque, str) or OPAQUE_VERSION_RE.fullmatch(opaque) is None:
        errors.append("xtquant provenance value must be an opaque sanitized token")
    elif SENSITIVE_VERSION_RE.search(opaque) or (opaque.isdigit() and len(opaque) >= 6):
        errors.append("xtquant provenance value may contain sensitive or account data")
    if provenance.get("verified") is not True:
        errors.append("xtquant provenance must be verified")
    return errors


def validate_assignments(document: object, *, task_id: str, pr: int, branch: str) -> list[str]:
    errors = _schema_errors(document, ASSIGNMENT_SCHEMA)
    root = _mapping(document)
    if root is None:
        return errors
    events = root.get("events")
    if not isinstance(events, list) or not events:
        return errors or ["assignment events must be non-empty"]
    active_agent: str | None = None
    last_sequence = 0
    stopped_agent: str | None = None
    stopped_head: str | None = None
    assigned_agents: set[str] = set()
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event)
        if event is None:
            continue
        prefix = f"assignment event {index}"
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence <= last_sequence:
            errors.append(f"{prefix}: sequence must be strictly increasing")
        elif sequence > last_sequence:
            last_sequence = sequence
        for field, expected in (("task", task_id), ("pr", pr), ("branch", branch)):
            if event.get(field) != expected:
                errors.append(f"{prefix}: {field} identity does not match")
        agent = event.get("agent")
        expected_agent = f"{event.get('tool')}/{event.get('os')}"
        if agent != expected_agent:
            errors.append(f"{prefix}: agent identity must equal tool/os")
        kind = event.get("event")
        if kind == "ASSIGN":
            if active_agent is not None:
                errors.append(f"{prefix}: ASSIGN would create two active writers")
            if assigned_agents:
                errors.append(f"{prefix}: later writers must use SWITCH")
            if event.get("starting_head") != event.get("pr_head"):
                errors.append(f"{prefix}: ASSIGN starting Head must equal PR Head")
            if isinstance(agent, str):
                active_agent = agent
                assigned_agents.add(agent)
        elif kind == "STOP":
            if active_agent != agent:
                errors.append(f"{prefix}: STOP must name the active writer")
            if event.get("stop_head") != event.get("pr_head"):
                errors.append(f"{prefix}: STOP Head must equal the then-current PR Head")
            stopped_agent = agent if isinstance(agent, str) else None
            stopped_head = (
                event.get("stop_head") if isinstance(event.get("stop_head"), str) else None
            )
            active_agent = None
        elif kind == "SWITCH":
            if active_agent is not None:
                errors.append(f"{prefix}: SWITCH requires the previous writer to be stopped")
            if stopped_agent is None or stopped_head is None:
                errors.append(f"{prefix}: SWITCH requires a preceding STOP event")
            if event.get("previous_agent") != stopped_agent:
                errors.append(f"{prefix}: SWITCH previous agent must match the stopped writer")
            if event.get("next_agent") != agent:
                errors.append(f"{prefix}: SWITCH next agent must match tool/os identity")
            if not (
                stopped_head
                == event.get("previous_agent_stop_head")
                == event.get("starting_head")
                == event.get("pr_head")
            ):
                errors.append(f"{prefix}: STOP, SWITCH starting, and current PR Heads must match")
            if isinstance(agent, str):
                if agent in assigned_agents:
                    errors.append(f"{prefix}: agent identity cannot be reused")
                active_agent = agent
                assigned_agents.add(agent)
            stopped_agent = None
            stopped_head = None
    if active_agent is None:
        errors.append("assignment event collection must end with exactly one active writer")
    return errors


def _timestamp_errors(value: object) -> list[str]:
    if not isinstance(value, str):
        return ["timestamp must be RFC3339 with an explicit timezone"]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ["timestamp must be a real RFC3339 datetime"]
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ["timestamp must include an explicit timezone"]
    return []


def validate_evidence(
    document: object,
    *,
    authority: Authority,
    expected_head: str,
    pr: int,
    branch: str,
    pr_head: str,
    assignments: object | None,
) -> list[str]:
    """Validate a complete required-lane record set using only frozen commands."""

    errors = _schema_errors(document, EVIDENCE_SCHEMA)
    if assignments is None:
        errors.append("ordered assignment events are required")
    else:
        errors.extend(
            validate_assignments(assignments, task_id=authority.task_id, pr=pr, branch=branch)
        )
    if pr_head != expected_head:
        errors.append("validated Head must equal the current PR Head")
    root = _mapping(document)
    if root is None:
        return errors
    records = root.get("records")
    if not isinstance(records, list) or not records:
        return errors or ["environment evidence collection must be non-empty"]

    lane_by_name = {lane.lane: lane for lane in authority.required_lanes}
    observed_by_lane: dict[str, list[str]] = {lane: [] for lane in lane_by_name}
    for index, raw_record in enumerate(records):
        record = _mapping(raw_record)
        if record is None:
            continue
        prefix = f"evidence record {index}"
        expected_identity = {
            "task": authority.task_id,
            "base": authority.expected_base,
            "head": expected_head,
            "pr": pr,
            "branch": branch,
        }
        for field, expected in expected_identity.items():
            if record.get(field) != expected:
                errors.append(f"{prefix}: {field} identity does not match frozen authority")
        lane = record.get("lane")
        if lane in authority.prohibited_lanes:
            errors.append(f"{prefix}: prohibited lane {lane} cannot satisfy TASK-057")
        if lane not in lane_by_name:
            errors.append(f"{prefix}: lane is not required by frozen authority")
        else:
            observed_by_lane[lane].append(str(record.get("command", "")))
        if record.get("requirement") != "required":
            errors.append(f"{prefix}: required-lane evidence must say required")

        capabilities = _mapping(record.get("capabilities")) or {}
        if lane == "portable" and capabilities.get("portable") is not True:
            errors.append(f"{prefix}: portable capability is missing")
        if lane in {"windows", "windows_miniqmt"} and (
            record.get("os") != "Windows" or capabilities.get("windows") is not True
        ):
            errors.append(f"{prefix}: Windows evidence requires actual Windows capability")
        if lane == "windows_miniqmt":
            for capability in (
                "miniqmt_available",
                "userdata_mini_verified",
                "unique_session_verified",
                "simulation_account_allowlisted",
            ):
                if capabilities.get(capability) is not True:
                    errors.append(f"{prefix}: Mini QMT capability {capability} is missing")
            errors.extend(
                f"{prefix}: {error}" for error in xtquant_provenance_errors(record.get("xtquant"))
            )
        elif record.get("xtquant") is not None:
            errors.extend(
                f"{prefix}: {error}" for error in xtquant_provenance_errors(record.get("xtquant"))
            )

        counts: dict[str, int] = {}
        for field in ("executed", "passed", "failed", "skipped"):
            value = record.get(field)
            if type(value) is int and value >= 0:
                counts[field] = value
        if len(counts) == 4:
            if counts["executed"] <= 0:
                errors.append(f"{prefix}: executed count must be positive")
            if counts["executed"] != counts["passed"] + counts["failed"] + counts["skipped"]:
                errors.append(f"{prefix}: result counts are inconsistent")
            if counts["failed"] != 0:
                errors.append(f"{prefix}: failed count must be zero")
            if counts["skipped"] != 0:
                errors.append(f"{prefix}: skip is not allowed by the frozen TASK-057 lanes")
        if record.get("exit_code") != 0:
            errors.append(f"{prefix}: exit code must be zero")
        errors.extend(f"{prefix}: {error}" for error in _timestamp_errors(record.get("timestamp")))
        if record.get("real_money") is not False:
            errors.append(f"{prefix}: real-money activity is always prohibited")
        if authority.task_id == "TASK-057":
            for field in ("miniqmt_connection", "account_query", "simulation_order"):
                if record.get(field) is not False:
                    errors.append(f"{prefix}: TASK-057 prohibits {field}")

    for lane_name, requirement in lane_by_name.items():
        observed = observed_by_lane[lane_name]
        expected = list(requirement.commands)
        if len(observed) < requirement.minimum_records:
            errors.append(f"lane {lane_name}: insufficient evidence records")
        if Counter(observed) != Counter(expected):
            missing = list((Counter(expected) - Counter(observed)).elements())
            unexpected = list((Counter(observed) - Counter(expected)).elements())
            if missing:
                errors.append(f"lane {lane_name}: missing exact commands: {missing}")
            if unexpected:
                errors.append(f"lane {lane_name}: unexpected or duplicate commands: {unexpected}")
        if len(observed) != len(set(observed)):
            errors.append(f"lane {lane_name}: duplicate command evidence is forbidden")
    return errors


def _load_yaml_file(path: Path, label: str) -> dict[str, Any]:
    return _load_yaml_text(path.read_text(encoding="utf-8"), label)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate frozen TASK-057 assignment and environment evidence."
    )
    parser.add_argument("--task", type=Path, default=Path(TASK_PATH.as_posix()))
    parser.add_argument("--handoff", type=Path, default=Path(HANDOFF_PATH.as_posix()))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-head", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--branch", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        resolved_head = _git(ROOT, "rev-parse", "--verify", f"{args.head}^{{commit}}")
        resolved_pr_head = _git(ROOT, "rev-parse", "--verify", f"{args.pr_head}^{{commit}}")
        authority = load_authority_from_git(
            ROOT,
            head=resolved_head,
            task_path=args.task,
            handoff_path=args.handoff,
        )
        resolved_base = _git(ROOT, "rev-parse", "--verify", f"{args.base_ref}^{{commit}}")
        if resolved_base != authority.expected_base:
            raise ValueError("base-ref does not resolve to the frozen expected Base")
        evidence = _load_yaml_file(args.evidence, "environment evidence")
        assignments = _load_yaml_file(args.assignments, "assignment events")
        errors = validate_evidence(
            evidence,
            authority=authority,
            expected_head=resolved_head,
            pr=args.pr,
            branch=args.branch,
            pr_head=resolved_pr_head,
            assignments=assignments,
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Agent environment validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Agent environment validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Agent environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
