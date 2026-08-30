"""Executable tests for the AI Handoff validator (TASK-056 Plan v3 Repair).

These tests prove the validator fails-closed on:
- missing/malformed Handoff Record
- missing schema fields
- invalid SHA format
- base mismatch (base-ref != expected_base_sha)
- merge-base mismatch
- PR base mismatch
- planning base not an ancestor
- task blob drift
- Handoff Record modification
- paths outside allowed_paths
- forbidden path hits
- rename paths outside allowed
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_ai_handoff.py"
HANDOFF = ROOT / "ai" / "handoffs" / "TASK-056-REPAIR-v1.yaml"
TASK = ROOT / "tasks" / "active" / "TASK-056-codex-cline-collaboration.md"

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
SHA_E = "e" * 40


# ── Structure ──────────────────────────────────────────────────────────────


def test_validator_script_exists() -> None:
    """The validator script must exist at the expected path."""
    assert VALIDATOR.exists(), f"missing: {VALIDATOR}"


def test_validator_is_ruff_clean() -> None:
    """The validator must pass ruff check."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(VALIDATOR)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ── Integration: real frozen handoff ─────────────────────────────────────


def test_validator_passes_on_frozen_handoff() -> None:
    """Validator must pass on the real frozen Handoff Record in this repo."""
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--task",
            str(TASK),
            "--handoff",
            str(HANDOFF),
            "--base-ref",
            "origin/main",
            "--head",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"


# ── Negative: missing handoff file ──────────────────────────────────────


def test_validator_fails_on_missing_handoff_file() -> None:
    """Validator must fail-closed when the handoff file does not exist."""
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--task",
            str(TASK),
            "--handoff",
            str(ROOT / "nonexistent.yaml"),
            "--base-ref",
            "origin/main",
            "--head",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0
    combined = (result.stderr + result.stdout).lower()
    assert "not found" in combined or "error" in combined


# ── Unit: mocked git validation ─────────────────────────────────────────


def _mock_git_responses(
    rev_parse_map: dict[str, str] | None = None,
    merge_base_map: dict[tuple[str, str], str] | None = None,
    is_ancestor_map: dict[tuple[str, str], bool] | None = None,
    blob_map: dict[str, str] | None = None,
    diff_name_only: str = "",
    diff_name_status: str = "",
):
    """Create a mock for subprocess.run that simulates git commands."""
    rev_parse_map = rev_parse_map or {}
    merge_base_map = merge_base_map or {}
    is_ancestor_map = is_ancestor_map or {}
    blob_map = blob_map or {}

    def fake_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        if cmd[0] != "git":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        args = cmd[1:]

        # git rev-parse <ref>
        if args[0] == "rev-parse" and len(args) == 2:
            ref = args[1]
            if ":" in ref:
                if ref in blob_map:
                    return subprocess.CompletedProcess(cmd, 0, blob_map[ref] + "\n", "")
                return subprocess.CompletedProcess(cmd, 128, "", f"fatal: {ref}: not found")
            if ref in rev_parse_map:
                return subprocess.CompletedProcess(cmd, 0, rev_parse_map[ref] + "\n", "")
            return subprocess.CompletedProcess(cmd, 128, "", f"fatal: unknown ref {ref}")

        # git merge-base --is-ancestor <a> <b>
        if args[0] == "merge-base" and len(args) >= 4 and args[1] == "--is-ancestor":
            key = (args[2], args[3])
            if key in is_ancestor_map:
                rc = 0 if is_ancestor_map[key] else 1
                return subprocess.CompletedProcess(cmd, rc, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "not ancestor")

        # git merge-base <a> <b>
        if args[0] == "merge-base" and len(args) == 3:
            key = (args[1], args[2])
            if key in merge_base_map:
                return subprocess.CompletedProcess(cmd, 0, merge_base_map[key] + "\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "no merge base")

        # git diff --name-only --no-renames base...head
        if args[0] == "diff" and "--name-only" in args:
            return subprocess.CompletedProcess(cmd, 0, diff_name_only + "\n", "")

        # git diff --name-status -M base...head
        if args[0] == "diff" and "--name-status" in args:
            return subprocess.CompletedProcess(cmd, 0, diff_name_status + "\n", "")

        return subprocess.CompletedProcess(cmd, 128, "", f"unmocked: git {' '.join(args)}")

    return fake_run


def _make_valid_handoff() -> dict:
    """Return a valid handoff dict for testing."""
    return {
        "schema_version": 1,
        "task_id": "TASK-056",
        "packet_version": "TASK-056-REPAIR-v1",
        "plan_version": "TASK-056-PLAN-v3",
        "planning_base_sha": SHA_A,
        "expected_base_sha": SHA_B,
        "expected_pr_base_sha": SHA_B,
        "task_blob_sha": SHA_C,
        "allowed_paths": ["file1.md", "file2.py"],
        "codex_only_paths": ["file2.py"],
    }


def _load_validator():
    """Import the validator module."""
    spec = importlib.util.spec_from_file_location("validate_ai_handoff", VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_validator_func(handoff: dict, task_fm: dict, **git_kwargs) -> list[str]:
    """Run the validator's core logic with mocked git."""
    mod = _load_validator()
    with patch("subprocess.run", side_effect=_mock_git_responses(**git_kwargs)):
        return mod.run_validation(
            task_path=TASK,
            handoff=handoff,
            base_ref="origin/main",
            head="HEAD",
            pr_base=None,
            cwd=ROOT,
            task_fm=task_fm,
            handoff_path=HANDOFF,
        )


def _default_git_kwargs() -> dict:
    """Default git mock responses for a valid state."""
    rel_task = "tasks/active/TASK-056-codex-cline-collaboration.md"
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    return {
        "rev_parse_map": {"origin/main": SHA_B, "HEAD": SHA_D},
        "merge_base_map": {(SHA_B, "HEAD"): SHA_B},
        "is_ancestor_map": {(SHA_A, SHA_B): True},
        "blob_map": {
            f"{SHA_B}:{rel_task}": SHA_C,
            f"HEAD:{rel_task}": SHA_C,
            f"{SHA_B}:{rel_handoff}": SHA_D,
            f"HEAD:{rel_handoff}": SHA_D,
        },
        "diff_name_only": "file1.md\nfile2.py",
        "diff_name_status": "A\tfile1.md\tfile1.md\nA\tfile2.py\tfile2.py",
    }


# ── Negative tests: schema ──────────────────────────────────────────────


def test_schema_missing_field_fails() -> None:
    """Validator must fail when a required schema field is missing."""
    handoff = _make_valid_handoff()
    del handoff["planning_base_sha"]
    task_fm = {"forbidden_paths": []}
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("planning_base_sha" in e for e in errors)


def test_schema_invalid_sha_format_fails() -> None:
    """Validator must fail when a SHA field is not 40 hex chars."""
    handoff = _make_valid_handoff()
    handoff["expected_base_sha"] = "not-a-sha"
    task_fm = {"forbidden_paths": []}
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("sha" in e.lower() for e in errors)


# ── Negative tests: base / PR base ─────────────────────────────────────


def test_base_mismatch_fails() -> None:
    """Validator must fail when base-ref does not resolve to expected_base_sha."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["rev_parse_map"]["origin/main"] = SHA_E
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("base" in e.lower() for e in errors)


def test_merge_base_mismatch_fails() -> None:
    """Validator must fail when merge-base is not expected_base_sha."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["merge_base_map"] = {(SHA_B, "HEAD"): SHA_E}
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("merge-base" in e.lower() or "merge_base" in e.lower() for e in errors)


def test_pr_base_mismatch_fails() -> None:
    """Validator must fail when --pr-base differs from expected_pr_base_sha."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    mod = _load_validator()
    with patch("subprocess.run", side_effect=_mock_git_responses(**kwargs)):
        errors = mod.run_validation(
            task_path=TASK,
            handoff=handoff,
            base_ref="origin/main",
            head="HEAD",
            pr_base=SHA_E,
            cwd=ROOT,
            task_fm=task_fm,
            handoff_path=HANDOFF,
        )
    assert any("pr" in e.lower() and "base" in e.lower() for e in errors)


# ── Negative tests: ancestry, blob, handoff immutability ──────────────


def test_planning_base_not_ancestor_fails() -> None:
    """Validator must fail when planning_base is not ancestor of expected_base."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["is_ancestor_map"] = {(SHA_A, SHA_B): False}
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("ancestor" in e.lower() for e in errors)


def test_task_blob_drift_fails() -> None:
    """Validator must fail when task blob at HEAD differs from frozen blob."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["blob_map"]["HEAD:tasks/active/TASK-056-codex-cline-collaboration.md"] = SHA_E
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("drift" in e.lower() or "task blob" in e.lower() for e in errors)


def test_handoff_modified_fails() -> None:
    """Validator must fail when the Handoff Record was modified after introduction."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["blob_map"][f"{SHA_B}:ai/handoffs/TASK-056-REPAIR-v1.yaml"] = SHA_E
    kwargs["blob_map"]["HEAD:ai/handoffs/TASK-056-REPAIR-v1.yaml"] = "f" * 40
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    lowered = [e.lower() for e in errors]
    assert any("handoff" in e and ("modif" in e or "immut" in e or "changed" in e) for e in lowered)


# ── Negative tests: path audit ─────────────────────────────────────────


def test_path_outside_allowed_fails() -> None:
    """Validator must fail when a changed path is not in allowed_paths."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md\nfile2.py\nrogue.py"
    kwargs["diff_name_status"] = (
        "A\tfile1.md\tfile1.md\nA\tfile2.py\tfile2.py\nA\trogue.py\trogue.py"
    )
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("rogue.py" in e or "outside" in e.lower() for e in errors)


def test_forbidden_path_fails() -> None:
    """Validator must fail when a changed path matches a forbidden pattern."""
    handoff = _make_valid_handoff()
    handoff["allowed_paths"] = ["file1.md", "file2.py", "spec/something.md"]
    task_fm = {"forbidden_paths": ["spec/**"]}
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md\nspec/something.md"
    kwargs["diff_name_status"] = "A\tfile1.md\tfile1.md\nA\tspec/something.md\tspec/something.md"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("forbidden" in e.lower() for e in errors)


def test_rename_outside_allowed_fails() -> None:
    """Validator must fail when a rename target is not in allowed_paths."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md"
    kwargs["diff_name_status"] = "R100\tfile1.md\trenamed_outside.md"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("rename" in e.lower() or "renamed_outside" in e for e in errors)


# ── Positive: valid state ──────────────────────────────────────────────


def test_valid_state_passes() -> None:
    """Validator must pass when all checks are satisfied."""
    handoff = _make_valid_handoff()
    task_fm = {"forbidden_paths": []}
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert errors == [], f"unexpected errors: {errors}"
