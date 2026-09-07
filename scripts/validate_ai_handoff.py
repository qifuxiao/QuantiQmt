#!/usr/bin/env python3
"""Validate AI Handoff Records against git state.

Checks (all fail-closed):
  1. Schema: required fields, SHA format, allowed_paths non-empty list,
     codex_only_paths non-empty list, expected_base == expected_pr_base.
  2. Base: --base-ref resolves to expected_base_sha; merge-base == expected_base_sha.
  3. PR base: --pr-base (if given) equals expected_pr_base_sha == expected_base_sha.
  4. Planning ancestry: planning_base_sha is ancestor of expected_base_sha.
  5. Task blob: frozen at expected_base_sha AND unchanged at supplied head.
  6. Handoff freeze topology: unique add-only introduction directly on Base, before repair.
  7. Path audit: all changed paths within Handoff allowed_paths AND task allowed_paths,
     none in forbidden_paths.
  8. Rename detection: both sides of renames must be in both allowed sets.

Usage:
    python scripts/validate_ai_handoff.py \\
        --task tasks/active/TASK-056-codex-cline-collaboration.md \\
        --handoff ai/handoffs/TASK-056-REPAIR-v2.yaml \\
        --base-ref origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PLAN_VERSION_RE = re.compile(
    r"^\s*-\s*Plan version:\s*`?([A-Za-z0-9][A-Za-z0-9._-]*)`?\s*$",
    re.MULTILINE,
)
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

REQUIRED_FIELDS = (
    "schema_version",
    "task_id",
    "packet_version",
    "plan_version",
    "planning_base_sha",
    "expected_base_sha",
    "expected_pr_base_sha",
    "task_blob_sha",
    "allowed_paths",
    "codex_only_paths",
    "repair_context",
)

SHA_FIELDS = ("planning_base_sha", "expected_base_sha", "expected_pr_base_sha", "task_blob_sha")

POST_IMPLEMENTATION_TOPOLOGY_IDENTITY = "post_implementation_repair_v1"
REVIEW_REPAIR_TOPOLOGY_IDENTITY = "task_029_review_repair_v1"
TASK029_TOPOLOGY_TUPLE: dict[str, object] = {
    "task_id": "TASK-029",
    "plan_version": "TASK-029-PLAN-v2",
    "packet_version": "TASK-029-EVIDENCE-REPAIR-v2",
    "handoff_path": "ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml",
    "pull_request_number": 110,
    "expected_base_sha": "b4b3f07c734c894032bd02f98e8cc914aa26f5d5",
    "planning_base_sha": "1bc232d367261302b397556b36a6b3284f8784d7",
}
TASK029_TOPOLOGY_CONTEXT: dict[str, object] = {
    "superseded_head_sha": "1bc232d367261302b397556b36a6b3284f8784d7",
    "current_pr_head_sha": "1bc232d367261302b397556b36a6b3284f8784d7",
    "initial_coordination_commit_sha": "33584e39a31b04b5a9d14a5c3b39c8c06a3889c0",
    "initial_coordination_parent_sha": "1bc232d367261302b397556b36a6b3284f8784d7",
    "final_coordination_commit_sha": "a4de3f396771808fb08ff10b9e29b0ad30efe328",
    "handoff_introduction_parent_sha": "a4de3f396771808fb08ff10b9e29b0ad30efe328",
    "coordination_allowed_paths": [
        "tasks/active/TASK-029-risk-runtime-schema-contract.md",
        "ai/packets/TASK-029-EVIDENCE-REPAIR-v2.md",
    ],
    "handoff_add_only_path": "ai/handoffs/TASK-029-EVIDENCE-REPAIR-v2.yaml",
    "implementation_pr_number": 110,
    "implementation_pr_base_sha": "b4b3f07c734c894032bd02f98e8cc914aa26f5d5",
    "repair_planning_base_sha": "1bc232d367261302b397556b36a6b3284f8784d7",
    "pr_base_historical_task_blob_sha": "131eadc3c966db0f2173539a040aaa45a02959fa",
    "plan_v2_task_blob_sha": "f6faf45767f01fdfe9038b8b00ed648a9f38820f",
    "protected_implementation_commits": [
        "9516147f69b6dccbc845ab5b1c557ee5f8fc54b8",
        "6283121945fab843af49ea096c6b006d386e0577",
        "6647ff9225610ae4c3dbb59e4fb50f6fb5ffdbb7",
        "1bc232d367261302b397556b36a6b3284f8784d7",
    ],
    "repair_targets": [
        "scripts/validate_ai_handoff.py",
        "scripts/validate_agent_environment.py",
        "tests/spec/test_validate_ai_handoff.py",
        "tests/spec/test_validate_agent_environment.py",
    ],
}
TASK029_REVIEW_TOPOLOGY_TUPLE: dict[str, object] = {
    "task_id": "TASK-029",
    "plan_version": "TASK-029-PLAN-v2",
    "packet_version": "TASK-029-REVIEW-REPAIR-v3",
    "handoff_path": "ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml",
    "pull_request_number": 110,
    "expected_base_sha": "b4b3f07c734c894032bd02f98e8cc914aa26f5d5",
    "planning_base_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
}
TASK029_REVIEW_TOPOLOGY_CONTEXT: dict[str, object] = {
    "reviewed_head_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "superseded_head_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "current_pr_head_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "coordinator_plan_packet_commit_sha": "55b2c1f38fcbf43796aa651c16b6d321b51b55ba",
    "coordinator_commit_parent_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "initial_coordination_commit_sha": "55b2c1f38fcbf43796aa651c16b6d321b51b55ba",
    "initial_coordination_parent_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "final_coordination_commit_sha": "55b2c1f38fcbf43796aa651c16b6d321b51b55ba",
    "handoff_introduction_parent_sha": "55b2c1f38fcbf43796aa651c16b6d321b51b55ba",
    "coordination_allowed_paths": [
        "tasks/active/TASK-029-risk-runtime-schema-contract.md",
        "ai/packets/TASK-029-REVIEW-REPAIR-v3.md",
    ],
    "handoff_add_only_path": "ai/handoffs/TASK-029-REVIEW-REPAIR-v3.yaml",
    "implementation_pr_number": 110,
    "implementation_pr_base_sha": "b4b3f07c734c894032bd02f98e8cc914aa26f5d5",
    "repair_planning_base_sha": "8b4c76d691849b126810be8953bfa7210ce18f43",
    "task_blob_sha": "66b2830c3f10c45f74e04c4f0246e1f62fd51f9d",
    "plan_v2_task_blob_sha": "66b2830c3f10c45f74e04c4f0246e1f62fd51f9d",
    "pr_base_historical_task_blob_sha": "131eadc3c966db0f2173539a040aaa45a02959fa",
    "repair_packet": {
        "identity": "TASK-029-REVIEW-REPAIR-v3",
        "path": "ai/packets/TASK-029-REVIEW-REPAIR-v3.md",
        "blob_sha": "0dc686d9521576a19d10f0e08eb25e9c344ad188",
    },
    "repair_targets": [
        "src/quantiqmt/contracts/bundle.py",
        "tests/unit/contracts/**",
        "scripts/validate_agent_environment.py",
        "tests/spec/test_validate_agent_environment.py",
        "scripts/validate_ai_handoff.py",
        "tests/spec/test_validate_ai_handoff.py",
    ],
}
TASK029_REVIEW_HANDOFF_BLOB = "bcac6fb5ce2daf6b7608bcef74d3b30a94c96085"


def git(*args: str, cwd: Path) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=True,
    )
    return result.stdout.strip()


def git_rev_parse(ref: str, cwd: Path) -> str:
    """Resolve a git ref to a SHA."""
    return git("rev-parse", ref, cwd=cwd)


def git_blob_at(ref: str, path: str, cwd: Path) -> str:
    """Get blob SHA for a path at a given ref."""
    return git("rev-parse", f"{ref}:{path}", cwd=cwd)


def git_merge_base(ref1: str, ref2: str, cwd: Path) -> str:
    """Get merge-base of two refs."""
    return git("merge-base", ref1, ref2, cwd=cwd)


def git_is_ancestor(ancestor: str, descendant: str, cwd: Path) -> bool:
    """Check if ancestor is an ancestor of (or equal to) descendant."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode == 0


def git_log_commits_touching(base: str, head: str, path: str, cwd: Path) -> list[str]:
    """Get every commit in base..head that touched path, without merge simplification."""
    output = git(
        "log",
        "--full-history",
        "--format=%H",
        f"{base}..{head}",
        "--",
        path,
        cwd=cwd,
    )
    candidates = [line for line in output.splitlines() if line]
    return [commit for commit in candidates if git_commit_authored_path_change(commit, path, cwd)]


def git_commit_parents(commit: str, cwd: Path) -> list[str]:
    """Return the parents of an exact commit."""
    output = git("rev-list", "--parents", "-n", "1", commit, cwd=cwd)
    parts = output.split()
    if not parts or parts[0] != commit:
        raise subprocess.CalledProcessError(128, ["git", "rev-list", commit])
    return parts[1:]


def git_optional_blob_at(ref: str, path: str, cwd: Path) -> str | None:
    """Return a path blob, or None when the path is absent at the exact ref."""
    try:
        return git_blob_at(ref, path, cwd)
    except subprocess.CalledProcessError:
        return None


def git_commit_authored_path_change(commit: str, path: str, cwd: Path) -> bool:
    """True when commit content for path differs from every parent.

    A synchronization merge may differ from its first parent while exactly
    preserving the Handoff parent's blob. It propagates existing content and
    is not a new Record touch. A merge resolution that differs from every
    parent is an authored touch and must fail immutability validation.
    """
    parents = git_commit_parents(commit, cwd)
    blob = git_optional_blob_at(commit, path, cwd)
    if not parents:
        return blob is not None
    parent_blobs = [git_optional_blob_at(parent, path, cwd) for parent in parents]
    return all(blob != parent_blob for parent_blob in parent_blobs)


def git_path_status(commit: str, path: str, cwd: Path) -> list[str]:
    """Return name-status lines for a path in an exact commit."""
    output = git(
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "-r",
        commit,
        "--",
        path,
        cwd=cwd,
    )
    return [line for line in output.splitlines() if line]


def git_commits_touching_paths(
    base: str,
    head: str,
    paths: list[str],
    cwd: Path,
) -> list[str]:
    """Return exact commits in base..head that touch any supplied path."""
    output = git(
        "rev-list",
        "--full-history",
        f"{base}..{head}",
        "--",
        *paths,
        cwd=cwd,
    )
    return [line for line in output.splitlines() if line]


def git_descendant_commits_in_head_ancestry(
    introduction: str,
    head: str,
    cwd: Path,
) -> list[str]:
    """Return every post-introduction commit on an ancestry path to exact head."""
    output = git(
        "rev-list",
        "--ancestry-path",
        f"{introduction}..{head}",
        cwd=cwd,
    )
    return [line for line in output.splitlines() if line]


def git_diff_name_only(base: str, head: str, cwd: Path) -> list[str]:
    """Get changed file names (no rename detection)."""
    output = git("diff", "--name-only", "--no-renames", f"{base}...{head}", cwd=cwd)
    return [line for line in output.splitlines() if line]


def git_diff_name_status(base: str, head: str, cwd: Path) -> list[tuple[str, str, str]]:
    """Get name-status with rename detection. Returns (status, old, new)."""
    output = git("diff", "--name-status", "-M", f"{base}...{head}", cwd=cwd)
    results: list[tuple[str, str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0][0]  # First char: A, M, D, R, C
        if status == "R" and len(parts) >= 3:
            results.append(("R", parts[1], parts[2]))
        elif len(parts) >= 2:
            results.append((status, parts[1], parts[1]))
    return results


def load_handoff(path: Path) -> dict[str, Any]:
    """Load and parse the Handoff Record YAML."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"handoff file must contain a YAML mapping, got {type(data).__name__}")
    return data


def extract_task_front_matter(path: Path) -> dict[str, Any]:
    """Extract YAML front matter from a task markdown file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if match is None:
        raise ValueError(f"missing YAML front matter in {path}")
    return yaml.safe_load(match.group(1)) or {}


def extract_task_plan_version(path: Path) -> str:
    """Extract the unique frozen Plan version from an active task."""
    versions = PLAN_VERSION_RE.findall(path.read_text(encoding="utf-8"))
    if len(versions) != 1:
        raise ValueError(
            f"expected exactly one '- Plan version:' entry in {path}; found {len(versions)}"
        )
    return str(versions[0])


def _repository_path_pattern_errors(value: object, *, label: str) -> list[str]:
    """Accept a repository-relative exact path or one terminal ``/**`` subtree."""

    if not isinstance(value, str) or not value:
        return [f"{label} must be a non-empty repository-relative path"]
    if "\\" in value:
        return [f"{label} must use forward slashes"]
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return [f"{label} must be repository-relative"]
    subtree = value.endswith("/**")
    exact = value[:-3] if subtree else value
    if not exact or exact.endswith("/"):
        return [f"{label} has an empty path segment"]
    segments = exact.split("/")
    if any(segment == "" for segment in segments):
        return [f"{label} has an empty path segment"]
    if any(segment in {".", ".."} for segment in segments):
        return [f"{label} contains a dot or parent-traversal segment"]
    if any(character in exact for character in "*?[]"):
        return [f"{label} has malformed glob syntax"]
    return []


def _path_matches(path: str, pattern: str) -> bool:
    if _repository_path_pattern_errors(path, label="changed path"):
        return False
    if _repository_path_pattern_errors(pattern, label="path pattern"):
        return False
    if pattern.endswith("/**"):
        return path.startswith(f"{pattern[:-3]}/")
    return path == pattern


def _repair_context(handoff: dict[str, Any]) -> dict[str, Any]:
    value = handoff.get("repair_context")
    return value if isinstance(value, dict) else {}


def _is_task029_post_implementation_repair(handoff: dict[str, Any]) -> bool:
    context = _repair_context(handoff)
    evidence_repair = (
        context.get("topology_identity") == POST_IMPLEMENTATION_TOPOLOGY_IDENTITY
        and context.get("allowlisted_topology_tuple") == TASK029_TOPOLOGY_TUPLE
        and handoff.get("task_id") == TASK029_TOPOLOGY_TUPLE["task_id"]
        and handoff.get("plan_version") == TASK029_TOPOLOGY_TUPLE["plan_version"]
        and handoff.get("packet_version") == TASK029_TOPOLOGY_TUPLE["packet_version"]
        and handoff.get("expected_base_sha") == TASK029_TOPOLOGY_TUPLE["expected_base_sha"]
        and handoff.get("planning_base_sha") == TASK029_TOPOLOGY_TUPLE["planning_base_sha"]
    )
    review_repair = (
        context.get("topology_identity") == REVIEW_REPAIR_TOPOLOGY_IDENTITY
        and context.get("allowlisted_topology_tuple") == TASK029_REVIEW_TOPOLOGY_TUPLE
        and handoff.get("task_id") == TASK029_REVIEW_TOPOLOGY_TUPLE["task_id"]
        and handoff.get("plan_version") == TASK029_REVIEW_TOPOLOGY_TUPLE["plan_version"]
        and handoff.get("packet_version") == TASK029_REVIEW_TOPOLOGY_TUPLE["packet_version"]
        and handoff.get("expected_base_sha") == TASK029_REVIEW_TOPOLOGY_TUPLE["expected_base_sha"]
        and handoff.get("planning_base_sha") == TASK029_REVIEW_TOPOLOGY_TUPLE["planning_base_sha"]
    )
    return evidence_repair or review_repair


def _is_task029_review_repair(handoff: dict[str, Any]) -> bool:
    context = _repair_context(handoff)
    return (
        context.get("topology_identity") == REVIEW_REPAIR_TOPOLOGY_IDENTITY
        and context.get("allowlisted_topology_tuple") == TASK029_REVIEW_TOPOLOGY_TUPLE
        and handoff.get("task_id") == TASK029_REVIEW_TOPOLOGY_TUPLE["task_id"]
        and handoff.get("plan_version") == TASK029_REVIEW_TOPOLOGY_TUPLE["plan_version"]
        and handoff.get("packet_version") == TASK029_REVIEW_TOPOLOGY_TUPLE["packet_version"]
        and handoff.get("expected_base_sha") == TASK029_REVIEW_TOPOLOGY_TUPLE["expected_base_sha"]
        and handoff.get("planning_base_sha") == TASK029_REVIEW_TOPOLOGY_TUPLE["planning_base_sha"]
    )


def _post_implementation_identity_errors(
    handoff: dict[str, Any], handoff_path: Path, cwd: Path
) -> list[str]:
    context = _repair_context(handoff)
    identity = context.get("topology_identity")
    if identity not in {
        POST_IMPLEMENTATION_TOPOLOGY_IDENTITY,
        REVIEW_REPAIR_TOPOLOGY_IDENTITY,
    }:
        return []
    errors: list[str] = []
    try:
        relative_path = handoff_path.relative_to(cwd).as_posix()
    except ValueError:
        relative_path = ""
    review_repair = identity == REVIEW_REPAIR_TOPOLOGY_IDENTITY
    expected_tuple = TASK029_REVIEW_TOPOLOGY_TUPLE if review_repair else TASK029_TOPOLOGY_TUPLE
    expected_context = (
        TASK029_REVIEW_TOPOLOGY_CONTEXT if review_repair else TASK029_TOPOLOGY_CONTEXT
    )
    if not _is_task029_post_implementation_repair(handoff):
        errors.append("post-implementation repair topology is not the frozen TASK-029 tuple")
    for field, expected in expected_context.items():
        if context.get(field) != expected:
            errors.append(f"post-implementation repair context field {field} is not frozen")
    if relative_path != expected_tuple["handoff_path"]:
        errors.append("post-implementation repair Handoff path is not the frozen TASK-029 path")
    if context.get("implementation_pr_number") != expected_tuple["pull_request_number"]:
        errors.append("post-implementation repair PR number is not frozen")
    return errors


def validate_schema(handoff: dict[str, Any]) -> list[str]:
    """Validate required fields, SHA format, and structural invariants."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in handoff:
            errors.append(f"missing required field: {field}")
    if "schema_version" in handoff:
        schema_version = handoff["schema_version"]
        if type(schema_version) is not int or schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(
                f"schema_version {schema_version!r} is unsupported; "
                f"supported versions are {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
    for field in SHA_FIELDS:
        if field in handoff:
            val = str(handoff[field])
            if not SHA_RE.match(val):
                errors.append(f"{field} is not a valid 40-char lowercase hex SHA: {val!r}")
    if "allowed_paths" in handoff:
        ap = handoff["allowed_paths"]
        if not isinstance(ap, list) or not ap:
            errors.append("allowed_paths must be a non-empty list")
        elif not all(isinstance(path, str) and path for path in ap):
            errors.append("allowed_paths must contain only non-empty strings")
        else:
            for index, path in enumerate(ap):
                errors.extend(
                    _repository_path_pattern_errors(path, label=f"allowed_paths[{index}]")
                )
    if "codex_only_paths" in handoff:
        cop = handoff["codex_only_paths"]
        if not isinstance(cop, list) or not cop:
            errors.append("codex_only_paths must be a non-empty list")
        elif not all(isinstance(p, str) for p in cop):
            errors.append("codex_only_paths must contain only strings")
        else:
            for index, path in enumerate(cop):
                errors.extend(
                    _repository_path_pattern_errors(path, label=f"codex_only_paths[{index}]")
                )
    if "forbidden_paths" in handoff:
        forbidden = handoff["forbidden_paths"]
        if not isinstance(forbidden, list):
            errors.append("forbidden_paths must be a list")
        else:
            for index, path in enumerate(forbidden):
                errors.extend(
                    _repository_path_pattern_errors(path, label=f"forbidden_paths[{index}]")
                )
    # Identity: expected_base_sha must equal expected_pr_base_sha
    if (
        "expected_base_sha" in handoff
        and "expected_pr_base_sha" in handoff
        and str(handoff["expected_base_sha"]) != str(handoff["expected_pr_base_sha"])
    ):
        errors.append(
            f"expected_base_sha {handoff['expected_base_sha']} != "
            f"expected_pr_base_sha {handoff['expected_pr_base_sha']}"
        )
    if "repair_context" in handoff:
        repair_context = handoff["repair_context"]
        if not isinstance(repair_context, dict):
            errors.append("repair_context must be a mapping")
        else:
            superseded = repair_context.get("superseded_head_sha")
            if superseded is None:
                errors.append("repair_context missing required field: superseded_head_sha")
            elif not isinstance(superseded, str) or not SHA_RE.match(superseded):
                errors.append(
                    "repair_context.superseded_head_sha is not a valid "
                    f"40-char lowercase hex SHA: {superseded!r}"
                )
    return errors


def validate_identity(
    handoff: dict[str, Any],
    task_fm: dict[str, Any],
    handoff_path: Path,
    task_plan_version: str,
) -> list[str]:
    """Bind the Handoff identity to its active task, filename, and frozen Plan."""
    errors: list[str] = []
    expected_task_id = task_fm.get("id")
    if not isinstance(expected_task_id, str) or not expected_task_id:
        errors.append("active task front matter must contain a non-empty string id")
    elif handoff.get("task_id") != expected_task_id:
        errors.append(
            f"task_id {handoff.get('task_id')!r} does not match active task id {expected_task_id!r}"
        )

    expected_packet_version = handoff_path.stem
    if handoff.get("packet_version") != expected_packet_version:
        errors.append(
            f"packet_version {handoff.get('packet_version')!r} does not match "
            f"Handoff filename identity {expected_packet_version!r}"
        )

    if handoff.get("plan_version") != task_plan_version:
        errors.append(
            f"plan_version {handoff.get('plan_version')!r} does not match "
            f"active task Plan version {task_plan_version!r}"
        )
    return errors


def validate_base(base_ref: str, head: str, handoff: dict[str, Any], cwd: Path) -> list[str]:
    """Check base-ref resolves to expected_base_sha and merge-base matches."""
    errors: list[str] = []
    expected_base = str(handoff["expected_base_sha"])
    try:
        resolved_base = git_rev_parse(base_ref, cwd)
    except subprocess.CalledProcessError:
        return [f"cannot resolve base-ref '{base_ref}'"]
    if resolved_base != expected_base:
        errors.append(
            f"base-ref '{base_ref}' resolves to {resolved_base}, "
            f"but expected_base_sha is {expected_base}"
        )
    try:
        merge_base = git_merge_base(expected_base, head, cwd)
    except subprocess.CalledProcessError:
        return [f"cannot compute merge-base of {expected_base} and {head}"]
    if merge_base != expected_base:
        errors.append(
            f"merge-base({expected_base}, {head}) = {merge_base}, expected {expected_base}"
        )
    return errors


def validate_pr_base(pr_base: str, handoff: dict[str, Any]) -> list[str]:
    """Check PR base SHA matches expected_pr_base_sha AND expected_base_sha."""
    expected_pr = str(handoff.get("expected_pr_base_sha", ""))
    expected_base = str(handoff.get("expected_base_sha", ""))
    errors: list[str] = []
    if pr_base != expected_pr:
        errors.append(f"PR base {pr_base} does not match expected_pr_base_sha {expected_pr}")
    if pr_base != expected_base:
        errors.append(f"PR base {pr_base} does not match expected_base_sha {expected_base}")
    return errors


def validate_planning_ancestor(handoff: dict[str, Any], cwd: Path) -> list[str]:
    """Check planning_base_sha is an ancestor of expected_base_sha."""
    planning = str(handoff["planning_base_sha"])
    base = str(handoff["expected_base_sha"])
    if _is_task029_post_implementation_repair(handoff):
        if not git_is_ancestor(base, planning, cwd):
            return [f"expected_base_sha {base} is not an ancestor of planning_base_sha {planning}"]
        return []
    if not git_is_ancestor(planning, base, cwd):
        return [f"planning_base_sha {planning} is not an ancestor of expected_base_sha {base}"]
    return []


def validate_task_blob(
    handoff: dict[str, Any],
    task_path: Path,
    base: str,
    head: str,
    cwd: Path,
) -> list[str]:
    """Check task blob at expected_base and at supplied head match the frozen blob."""
    errors: list[str] = []
    expected_blob = str(handoff["task_blob_sha"])
    rel_task = task_path.relative_to(cwd).as_posix()
    special = _is_task029_post_implementation_repair(handoff)
    context = _repair_context(handoff)

    try:
        blob_at_base = git_blob_at(base, rel_task, cwd)
        expected_base_blob = (
            context.get("pr_base_historical_task_blob_sha") if special else expected_blob
        )
        if blob_at_base != expected_base_blob:
            errors.append(
                f"task blob at base {base} is {blob_at_base}, expected frozen {expected_base_blob}"
            )
    except subprocess.CalledProcessError:
        errors.append(f"task file {rel_task} not found at base {base}")

    if special:
        handoff_parent = str(context.get("handoff_introduction_parent_sha", ""))
        try:
            blob_at_parent = git_blob_at(handoff_parent, rel_task, cwd)
            if blob_at_parent != expected_blob:
                errors.append(
                    f"task blob at Handoff parent {handoff_parent} is {blob_at_parent}, "
                    f"expected frozen {expected_blob}"
                )
        except subprocess.CalledProcessError:
            errors.append(f"task file {rel_task} not found at Handoff parent {handoff_parent}")

    try:
        blob_at_head = git_blob_at(head, rel_task, cwd)
        if blob_at_head != expected_blob:
            errors.append(f"task blob drift: {head} has {blob_at_head}, frozen is {expected_blob}")
    except subprocess.CalledProcessError:
        errors.append(f"task file {rel_task} not found at {head}")

    return errors


def validate_handoff_freeze_topology(
    handoff_path: Path,
    base: str,
    head: str,
    handoff: dict[str, Any],
    cwd: Path,
) -> list[str]:
    """Prove the supplied Head descends from an immutable pre-repair Handoff."""
    rel_handoff = handoff_path.relative_to(cwd).as_posix()
    special = _is_task029_post_implementation_repair(handoff)
    context = _repair_context(handoff)

    if special:
        planning = str(handoff["planning_base_sha"])
        initial = str(context["initial_coordination_commit_sha"])
        final = str(context["final_coordination_commit_sha"])
        if str(context.get("initial_coordination_parent_sha")) != planning:
            return ["initial coordination parent does not equal planning_base_sha"]
        try:
            if git_commit_parents(initial, cwd) != [planning]:
                return ["initial coordination commit is not the direct child of planning_base_sha"]
            if not _is_task029_review_repair(handoff) and git_commit_parents(final, cwd) != [
                initial
            ]:
                return ["final coordination commit is not the direct child of initial coordination"]
            coordination_paths = set(
                str(path) for path in context.get("coordination_allowed_paths", [])
            )
            changed_paths = set(git_diff_name_only(planning, final, cwd))
            if changed_paths != coordination_paths:
                return [
                    "planning-to-final coordination paths differ from the frozen exact set: "
                    f"{sorted(changed_paths)}"
                ]
            if not _is_task029_review_repair(handoff):
                protected = context.get("protected_implementation_commits")
                if not isinstance(protected, list) or not protected or protected[-1] != planning:
                    return [
                        "protected implementation commit list does not terminate at planning Base"
                    ]
                if any(not git_is_ancestor(str(commit), planning, cwd) for commit in protected):
                    return ["a protected implementation commit is not an ancestor of planning Base"]
        except subprocess.CalledProcessError as exc:
            return [f"cannot validate post-implementation coordination topology: {exc}"]

        if _is_task029_review_repair(handoff):
            packet = context["repair_packet"]
            assert isinstance(packet, dict)
            packet_path = str(packet["path"])
            packet_blob = str(packet["blob_sha"])
            task_path = "tasks/active/TASK-029-risk-runtime-schema-contract.md"
            task_blob = str(handoff["task_blob_sha"])
            try:
                for ref in (final, head):
                    if git_blob_at(ref, packet_path, cwd) != packet_blob:
                        return [f"review-repair Packet blob is not frozen at {ref}"]
                    if git_blob_at(ref, task_path, cwd) != task_blob:
                        return [f"review-repair task blob is not frozen at {ref}"]
            except subprocess.CalledProcessError as exc:
                return [f"cannot validate review-repair frozen blobs: {exc}"]

    # Discover all commits in base..head that touched the handoff file
    try:
        commits = git_log_commits_touching(base, head, rel_handoff, cwd)
    except subprocess.CalledProcessError as e:
        return [f"failed to discover handoff introduction for {rel_handoff}: {e}"]

    if not commits:
        return [
            f"handoff record {rel_handoff} has no introduction commit in {base}..{head}; "
            "it must be introduced after the expected Base"
        ]
    if len(commits) > 1:
        return [
            f"handoff record {rel_handoff} has ambiguous introduction: "
            f"{len(commits)} commits touch it in {base}..{head} "
            "(possible deletion + reintroduction or modification)"
        ]

    intro_commit = commits[0]

    try:
        parents = git_commit_parents(intro_commit, cwd)
    except subprocess.CalledProcessError as exc:
        return [f"cannot read parents for handoff introduction {intro_commit}: {exc}"]
    if len(parents) != 1:
        return [
            f"handoff introduction {intro_commit} must have exactly one parent; "
            f"found {len(parents)}"
        ]
    expected_intro_parent = str(context["handoff_introduction_parent_sha"]) if special else base
    if parents[0] != expected_intro_parent:
        expected_label = "expected parent" if special else "expected_base_sha"
        return [
            f"handoff introduction parent {parents[0]} does not equal "
            f"{expected_label} {expected_intro_parent}"
        ]

    try:
        path_status = git_path_status(intro_commit, rel_handoff, cwd)
    except subprocess.CalledProcessError as exc:
        return [f"cannot inspect handoff introduction diff {intro_commit}: {exc}"]
    if path_status != [f"A\t{rel_handoff}"]:
        return [
            f"handoff introduction {intro_commit} must add-only {rel_handoff}; "
            f"found {path_status!r}"
        ]

    if not git_is_ancestor(intro_commit, head, cwd):
        return [f"handoff introduction {intro_commit} is not an ancestor of supplied head {head}"]

    repair_context = handoff["repair_context"]
    assert isinstance(repair_context, dict)
    superseded = str(repair_context["superseded_head_sha"])
    if not git_is_ancestor(superseded, head, cwd):
        return [f"superseded_head_sha {superseded} is not an ancestor of supplied head {head}"]

    repair_paths = [
        str(path)
        for path in (context.get("repair_targets", []) if special else handoff["allowed_paths"])
    ]
    try:
        repair_commits = git_commits_touching_paths(superseded, head, repair_paths, cwd)
    except subprocess.CalledProcessError as exc:
        return [f"cannot audit repair-stage commit ordering for supplied head {head}: {exc}"]
    premature = [
        commit for commit in repair_commits if not git_is_ancestor(intro_commit, commit, cwd)
    ]
    if premature:
        return [
            "repair-stage path commit(s) are not descendants of the Handoff introduction "
            f"{intro_commit}: {premature}"
        ]

    # Blob at introduction commit
    try:
        blob_at_intro = git_blob_at(intro_commit, rel_handoff, cwd)
    except subprocess.CalledProcessError:
        return [f"handoff record {rel_handoff} not readable at introduction commit {intro_commit}"]
    if _is_task029_review_repair(handoff) and blob_at_intro != TASK029_REVIEW_HANDOFF_BLOB:
        return ["review-repair Handoff introduction blob does not match the frozen identity"]

    # Prove continuous immutability at every descendant commit state that is
    # also an ancestor of the supplied exact Head. This catches merge results
    # that select an external parent's absent/original state and would be
    # invisible to authored-change filtering.
    try:
        descendants = git_descendant_commits_in_head_ancestry(intro_commit, head, cwd)
    except subprocess.CalledProcessError as exc:
        return [
            f"cannot enumerate Handoff descendant states from {intro_commit} "
            f"to supplied head {head}: {exc}"
        ]
    for commit in descendants:
        blob_at_commit = git_optional_blob_at(commit, rel_handoff, cwd)
        if blob_at_commit != blob_at_intro:
            observed = "absent" if blob_at_commit is None else blob_at_commit
            return [
                f"handoff record {rel_handoff} is not continuously frozen at "
                f"descendant commit {commit}: observed {observed}, expected {blob_at_intro}"
            ]

    # Blob at supplied head
    try:
        blob_at_head = git_blob_at(head, rel_handoff, cwd)
    except subprocess.CalledProcessError:
        return [f"handoff record {rel_handoff} not found at head {head} (deleted?)"]

    if blob_at_intro != blob_at_head:
        return [
            f"handoff record {rel_handoff} modified after introduction: "
            f"blob at {intro_commit[:8]} = {blob_at_intro[:8]}, "
            f"blob at {head[:8]} = {blob_at_head[:8]}"
        ]

    return []


def _is_path_allowed(
    path: str,
    handoff_allowed: set[str],
    task_allowed: set[str],
    forbidden: list[str],
) -> list[str]:
    """Check a single path against both allowed sets and forbidden patterns."""
    errors: list[str] = []
    path_errors = _repository_path_pattern_errors(path, label=f"path {path!r}")
    if path_errors:
        return path_errors
    if not any(_path_matches(path, pattern) for pattern in handoff_allowed):
        errors.append(f"path {path!r} not in Handoff allowed_paths")
    if not any(_path_matches(path, pattern) for pattern in task_allowed):
        errors.append(f"path {path!r} not in task allowed_paths")
    for pattern in forbidden:
        if _path_matches(path, pattern):
            errors.append(f"path {path!r} matches forbidden pattern {pattern!r}")
    return errors


def validate_paths(
    base: str,
    head: str,
    handoff: dict[str, Any],
    task_fm: dict[str, Any],
    cwd: Path,
) -> list[str]:
    """Check all changed paths against Handoff AND task allowed/forbidden."""
    errors: list[str] = []
    handoff_allowed = set(str(p) for p in handoff["allowed_paths"])
    task_allowed = set(str(p) for p in task_fm.get("allowed_paths", []))
    forbidden = list(
        dict.fromkeys(
            str(path)
            for path in [
                *task_fm.get("forbidden_paths", []),
                *handoff.get("forbidden_paths", []),
            ]
        )
    )

    # No-rename diff
    try:
        changed = set(git_diff_name_only(base, head, cwd))
    except subprocess.CalledProcessError as e:
        return [f"failed to get diff name-only: {e}"]

    for path in sorted(changed):
        errors.extend(_is_path_allowed(path, handoff_allowed, task_allowed, forbidden))

    # Rename-aware diff: check both sides
    try:
        statuses = git_diff_name_status(base, head, cwd)
    except subprocess.CalledProcessError as e:
        return [*errors, f"failed to get diff name-status: {e}"]
    for status, old, new in statuses:
        if status != "R":
            continue
        for side, p in (("old", old), ("new", new)):
            for err in _is_path_allowed(p, handoff_allowed, task_allowed, forbidden):
                errors.append(f"rename {side}: {err}")

    return errors


def run_validation(
    task_path: Path,
    handoff: dict[str, Any],
    base_ref: str,
    head: str,
    pr_base: str | None,
    cwd: Path,
    task_fm: dict[str, Any],
    handoff_path: Path | None = None,
) -> list[str]:
    """Run all validation checks. Returns list of errors (empty = pass)."""
    errors: list[str] = []

    # 1. Schema (includes codex_only_paths and base/PR-base identity)
    schema_errors = validate_schema(handoff)
    if schema_errors:
        return schema_errors  # Cannot proceed without valid schema
    for field in ("allowed_paths", "forbidden_paths"):
        values = task_fm.get(field, [])
        if not isinstance(values, list):
            return [f"task {field} must be a list"]
        task_path_errors = [
            error
            for index, value in enumerate(values)
            for error in _repository_path_pattern_errors(value, label=f"task {field}[{index}]")
        ]
        if task_path_errors:
            return task_path_errors

    # 1b. codex_only_paths must contain the handoff record itself
    if handoff_path is not None:
        rel_handoff = handoff_path.relative_to(cwd).as_posix()
        codex_only = [str(p) for p in handoff.get("codex_only_paths", [])]
        if rel_handoff not in codex_only:
            return [
                f"codex_only_paths does not contain the handoff record itself: "
                f"{rel_handoff!r} not in {codex_only}"
            ]

        if not task_path.exists():
            return [f"task file not found: {task_path}"]
        try:
            task_plan_version = extract_task_plan_version(task_path)
        except (OSError, ValueError) as exc:
            return [f"cannot bind Handoff identity to active task Plan: {exc}"]
        identity_errors = validate_identity(
            handoff,
            task_fm,
            handoff_path,
            task_plan_version,
        )
        identity_errors.extend(_post_implementation_identity_errors(handoff, handoff_path, cwd))
        if identity_errors:
            return identity_errors

    # 2. Base validation
    errors.extend(validate_base(base_ref, head, handoff, cwd))

    # 3. PR base (if supplied)
    if pr_base:
        errors.extend(validate_pr_base(pr_base, handoff))

    # 4. Planning ancestry
    errors.extend(validate_planning_ancestor(handoff, cwd))

    # 5. Task blob (at base and at supplied head)
    if not task_path.exists():
        errors.append(f"task file not found: {task_path}")
    else:
        base = str(handoff["expected_base_sha"])
        errors.extend(validate_task_blob(handoff, task_path, base, head, cwd))

    # 6. Handoff freeze topology and immutability, all bound to supplied head
    if handoff_path is not None:
        base = str(handoff["expected_base_sha"])
        errors.extend(validate_handoff_freeze_topology(handoff_path, base, head, handoff, cwd))

    # 7. Path audit (Handoff allowed_paths AND task allowed_paths AND forbidden)
    base = str(handoff["expected_base_sha"])
    errors.extend(validate_paths(base, head, handoff, task_fm, cwd))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI Handoff Records against git state.")
    parser.add_argument("--task", required=True, help="Path to the active task file")
    parser.add_argument("--handoff", required=True, help="Path to the Handoff Record YAML")
    parser.add_argument("--base-ref", required=True, help="Git ref for the expected base")
    parser.add_argument("--head", required=True, help="Git ref for the head (e.g., HEAD)")
    parser.add_argument("--pr-base", default=None, help="GitHub PR base SHA (optional)")
    args = parser.parse_args()

    try:
        cwd = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd())).resolve()
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: current directory is not a readable Git repository: {exc}", file=sys.stderr)
        return 1
    task_path = Path(args.task)
    handoff_path = Path(args.handoff)
    if not task_path.is_absolute():
        task_path = cwd / task_path
    if not handoff_path.is_absolute():
        handoff_path = cwd / handoff_path

    # Load handoff
    if not handoff_path.exists():
        print(f"FAIL: handoff file not found: {handoff_path}", file=sys.stderr)
        return 1
    try:
        handoff = load_handoff(handoff_path)
    except Exception as e:
        print(f"FAIL: failed to parse handoff YAML: {e}", file=sys.stderr)
        return 1

    # Load task front matter
    if not task_path.exists():
        print(f"FAIL: task file not found: {task_path}", file=sys.stderr)
        return 1
    try:
        task_fm = extract_task_front_matter(task_path)
    except Exception as e:
        print(f"FAIL: cannot read task front matter: {e}", file=sys.stderr)
        return 1

    errors = run_validation(
        task_path=task_path,
        handoff=handoff,
        base_ref=args.base_ref,
        head=args.head,
        pr_base=args.pr_base,
        cwd=cwd,
        task_fm=task_fm,
        handoff_path=handoff_path,
    )

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s) found.", file=sys.stderr)
        return 1

    print("Handoff validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
