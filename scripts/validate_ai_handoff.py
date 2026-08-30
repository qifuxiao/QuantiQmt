#!/usr/bin/env python3
"""Validate AI Handoff Records against git state.

Checks (all fail-closed):
  1. Schema: required fields, SHA format, allowed_paths non-empty list.
  2. Base: --base-ref resolves to expected_base_sha; merge-base == expected_base_sha.
  3. PR base: --pr-base (if given) equals expected_pr_base_sha.
  4. Planning ancestry: planning_base_sha is ancestor of expected_base_sha.
  5. Task blob: frozen at expected_base_sha AND unchanged at HEAD.
  6. Handoff immutability: Handoff Record not modified after introduction.
  7. Path audit: all changed paths within allowed_paths, none in forbidden_paths.
  8. Rename detection: both sides of renames must be in allowed_paths.

Usage:
    python scripts/validate_ai_handoff.py \\
        --task tasks/active/TASK-056-codex-cline-collaboration.md \\
        --handoff ai/handoffs/TASK-056-REPAIR-v1.yaml \\
        --base-ref origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import yaml

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

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
)

SHA_FIELDS = ("planning_base_sha", "expected_base_sha", "expected_pr_base_sha", "task_blob_sha")


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


def load_handoff(path: Path) -> dict:
    """Load and parse the Handoff Record YAML."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"handoff file must contain a YAML mapping, got {type(data).__name__}")
    return data


def extract_task_front_matter(path: Path) -> dict:
    """Extract YAML front matter from a task markdown file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if match is None:
        raise ValueError(f"missing YAML front matter in {path}")
    return yaml.safe_load(match.group(1)) or {}


def validate_schema(handoff: dict) -> list[str]:
    """Validate required fields and SHA format. Returns list of errors."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in handoff:
            errors.append(f"missing required field: {field}")
    for field in SHA_FIELDS:
        if field in handoff:
            val = str(handoff[field])
            if not SHA_RE.match(val):
                errors.append(f"{field} is not a valid 40-char lowercase hex SHA: {val!r}")
    if "allowed_paths" in handoff:
        ap = handoff["allowed_paths"]
        if not isinstance(ap, list) or not ap:
            errors.append("allowed_paths must be a non-empty list")
    return errors


def validate_base(base_ref: str, head: str, handoff: dict, cwd: Path) -> list[str]:
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


def validate_pr_base(pr_base: str, handoff: dict) -> list[str]:
    """Check PR base SHA matches expected_pr_base_sha."""
    expected = str(handoff.get("expected_pr_base_sha", handoff.get("expected_base_sha", "")))
    if pr_base != expected:
        return [f"PR base {pr_base} does not match expected_pr_base_sha {expected}"]
    return []


def validate_planning_ancestor(handoff: dict, cwd: Path) -> list[str]:
    """Check planning_base_sha is an ancestor of expected_base_sha."""
    planning = str(handoff["planning_base_sha"])
    base = str(handoff["expected_base_sha"])
    if not git_is_ancestor(planning, base, cwd):
        return [f"planning_base_sha {planning} is not an ancestor of expected_base_sha {base}"]
    return []


def validate_task_blob(handoff: dict, task_path: Path, cwd: Path) -> list[str]:
    """Check task blob at expected_base and at HEAD match the frozen blob."""
    errors: list[str] = []
    expected_blob = str(handoff["task_blob_sha"])
    base = str(handoff["expected_base_sha"])
    rel_task = str(task_path.relative_to(cwd))

    try:
        blob_at_base = git_blob_at(base, rel_task, cwd)
        if blob_at_base != expected_blob:
            errors.append(
                f"task blob at base {base} is {blob_at_base}, expected frozen {expected_blob}"
            )
    except subprocess.CalledProcessError:
        errors.append(f"task file {rel_task} not found at base {base}")

    try:
        blob_at_head = git_blob_at("HEAD", rel_task, cwd)
        if blob_at_head != expected_blob:
            errors.append(f"task blob drift: HEAD has {blob_at_head}, frozen is {expected_blob}")
    except subprocess.CalledProcessError:
        errors.append(f"task file {rel_task} not found at HEAD")

    return errors


def validate_handoff_immutable(handoff_path: Path, base: str, cwd: Path) -> list[str]:
    """Check Handoff Record was not modified after introduction."""
    errors: list[str] = []
    rel_handoff = str(handoff_path.relative_to(cwd))

    try:
        blob_at_head = git_blob_at("HEAD", rel_handoff, cwd)
    except subprocess.CalledProcessError:
        return [f"handoff file {rel_handoff} not found at HEAD"]

    try:
        blob_at_base = git_blob_at(base, rel_handoff, cwd)
        if blob_at_base != blob_at_head:
            errors.append(
                f"handoff file modified: base blob {blob_at_base} != HEAD blob {blob_at_head}"
            )
    except subprocess.CalledProcessError:
        # File didn't exist at base — it was newly added, which is expected
        pass

    return errors


def validate_paths(
    base: str,
    head: str,
    handoff: dict,
    task_fm: dict,
    cwd: Path,
) -> list[str]:
    """Check all changed paths are within allowed and not forbidden."""
    errors: list[str] = []
    allowed = set(str(p) for p in handoff["allowed_paths"])
    forbidden: list[str] = [str(p) for p in task_fm.get("forbidden_paths", [])]

    # No-rename diff
    try:
        changed = set(git_diff_name_only(base, head, cwd))
    except subprocess.CalledProcessError as e:
        return [f"failed to get diff name-only: {e}"]

    outside = sorted(p for p in changed if p not in allowed)
    if outside:
        errors.append(f"paths outside allowed_paths: {outside}")

    for path in sorted(changed):
        for pattern in forbidden:
            if fnmatch.fnmatchcase(path, pattern):
                errors.append(f"path {path!r} matches forbidden pattern {pattern!r}")

    # Rename-aware diff: check both sides
    try:
        statuses = git_diff_name_status(base, head, cwd)
    except subprocess.CalledProcessError as e:
        return [*errors, f"failed to get diff name-status: {e}"]

    for status, old, new in statuses:
        if status != "R":
            continue
        for side, p in (("old", old), ("new", new)):
            if p not in allowed:
                errors.append(f"rename {side} path {p!r} not in allowed_paths")
            for pattern in forbidden:
                if fnmatch.fnmatchcase(p, pattern):
                    errors.append(f"rename {side} path {p!r} matches forbidden pattern {pattern!r}")

    return errors


def run_validation(
    task_path: Path,
    handoff: dict,
    base_ref: str,
    head: str,
    pr_base: str | None,
    cwd: Path,
    task_fm: dict,
    handoff_path: Path | None = None,
) -> list[str]:
    """Run all validation checks. Returns list of errors (empty = pass)."""
    errors: list[str] = []

    # 1. Schema
    schema_errors = validate_schema(handoff)
    if schema_errors:
        return schema_errors  # Cannot proceed without valid schema
    errors.extend(schema_errors)

    # 2. Base validation
    errors.extend(validate_base(base_ref, head, handoff, cwd))

    # 3. PR base
    if pr_base:
        errors.extend(validate_pr_base(pr_base, handoff))

    # 4. Planning ancestry
    errors.extend(validate_planning_ancestor(handoff, cwd))

    # 5. Task blob (at base and at HEAD)
    if not task_path.exists():
        errors.append(f"task file not found: {task_path}")
    else:
        errors.extend(validate_task_blob(handoff, task_path, cwd))

    # 6. Handoff immutability
    base = str(handoff["expected_base_sha"])
    if handoff_path is not None:
        errors.extend(validate_handoff_immutable(handoff_path, base, cwd))

    # 7+8. Path audit
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

    cwd = Path(__file__).resolve().parents[1]
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
