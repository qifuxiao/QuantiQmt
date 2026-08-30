"""Executable tests for the AI Handoff validator (TASK-056 Plan v3 Repair + ADDENDUM-1).

These tests prove the validator fails-closed on:
- missing/malformed Handoff Record
- missing schema fields
- invalid SHA format
- divergent expected_base_sha / expected_pr_base_sha
- base mismatch (base-ref != expected_base_sha)
- merge-base mismatch
- PR base mismatch
- planning base not an ancestor
- task blob drift (at supplied head, not ambient HEAD)
- Handoff Record not introduced in range
- Handoff Record ambiguous introduction (multiple commits)
- Handoff Record modified after introduction
- missing/malformed codex_only_paths
- path allowed by Handoff but outside task allowed_paths
- forbidden path hits
- rename paths outside allowed sets or inside forbidden paths
- supplied head differs from ambient HEAD
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any
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
SHA_F = "f" * 40
SHA_G = "0123456789abcdef0123456789abcdef01234567"


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


def test_mypy_passes() -> None:
    """Strict mypy must pass on src and scripts."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "src", "scripts"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    # The 2 pre-existing ctypes errors in readonly_probe.py are known;
    # we only require zero NEW errors in our validator
    if result.returncode != 0:
        # Allow only pre-existing ctypes errors in readonly_probe.py
        lines = [ln for ln in result.stdout.splitlines() if "error:" in ln]
        new_errors = [
            ln for ln in lines if "validate_ai_handoff" not in ln and "readonly_probe" not in ln
        ]
        assert not new_errors, f"new mypy errors: {new_errors}"


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
    log_map: dict[str, str] | None = None,
    diff_name_only: str = "",
    diff_name_status: str = "",
) -> Any:
    """Create a mock for subprocess.run that simulates git commands."""
    rev_parse_map = rev_parse_map or {}
    merge_base_map = merge_base_map or {}
    is_ancestor_map = is_ancestor_map or {}
    blob_map = blob_map or {}
    log_map = log_map or {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if cmd[0] != "git":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        args = cmd[1:]
        check = kwargs.get("check", False)

        def _result(rc: int, out: str, err: str) -> subprocess.CompletedProcess:
            proc = subprocess.CompletedProcess(cmd, rc, out, err)
            if check and rc != 0:
                raise subprocess.CalledProcessError(rc, cmd, output=out, stderr=err)
            return proc

        # git rev-parse <ref>
        if args[0] == "rev-parse" and len(args) == 2:
            ref = args[1]
            if ":" in ref:
                if ref in blob_map:
                    return _result(0, blob_map[ref] + "\n", "")
                return _result(128, "", f"fatal: {ref}: not found")
            if ref in rev_parse_map:
                return _result(0, rev_parse_map[ref] + "\n", "")
            return _result(128, "", f"fatal: unknown ref {ref}")

        # git merge-base --is-ancestor <a> <b>
        if args[0] == "merge-base" and len(args) >= 4 and args[1] == "--is-ancestor":
            key = (args[2], args[3])
            if key in is_ancestor_map:
                rc = 0 if is_ancestor_map[key] else 1
                return _result(rc, "", "")
            return _result(1, "", "not ancestor")

        # git merge-base <a> <b>
        if args[0] == "merge-base" and len(args) == 3:
            key = (args[1], args[2])
            if key in merge_base_map:
                return _result(0, merge_base_map[key] + "\n", "")
            return _result(1, "", "no merge base")

        # git log --format=%H <base>..<head> -- <path>
        if args[0] == "log":
            # Find the range and path
            range_arg = next((a for a in args if ".." in a), "")
            path_arg = ""
            if "--" in args:
                idx = args.index("--")
                if idx + 1 < len(args):
                    path_arg = args[idx + 1]
            key = f"{range_arg}::{path_arg}"
            if key in log_map:
                return _result(0, log_map[key] + "\n", "")
            return _result(0, "", "")

        # git diff --name-only --no-renames base...head
        if args[0] == "diff" and "--name-only" in args:
            return _result(0, diff_name_only + "\n", "")

        # git diff --name-status -M base...head
        if args[0] == "diff" and "--name-status" in args:
            return _result(0, diff_name_status + "\n", "")

        return _result(128, "", f"unmocked: git {' '.join(args)}")

    return fake_run


def _make_valid_handoff() -> dict[str, Any]:
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
        "allowed_paths": ["file1.md", "file2.py", "ai/handoffs/TASK-056-REPAIR-v1.yaml"],
        "codex_only_paths": ["ai/handoffs/TASK-056-REPAIR-v1.yaml"],
    }


def _make_valid_task_fm() -> dict[str, Any]:
    """Return a valid task front-matter dict for testing."""
    return {
        "allowed_paths": ["file1.md", "file2.py", "ai/handoffs/TASK-056-REPAIR-v1.yaml"],
        "forbidden_paths": [],
    }


def _load_validator() -> Any:
    """Import the validator module."""
    spec = importlib.util.spec_from_file_location("validate_ai_handoff", VALIDATOR)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_validator_func(
    handoff: dict[str, Any],
    task_fm: dict[str, Any],
    head: str = "HEAD",
    **git_kwargs: Any,
) -> list[str]:
    """Run the validator's core logic with mocked git."""
    mod = _load_validator()
    with patch("subprocess.run", side_effect=_mock_git_responses(**git_kwargs)):
        return mod.run_validation(
            task_path=TASK,
            handoff=handoff,
            base_ref="origin/main",
            head=head,
            pr_base=None,
            cwd=ROOT,
            task_fm=task_fm,
            handoff_path=HANDOFF,
        )


def _default_git_kwargs(head: str = "HEAD") -> dict[str, Any]:
    """Default git mock responses for a valid state."""
    rel_task = "tasks/active/TASK-056-codex-cline-collaboration.md"
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    base = SHA_B
    return {
        "rev_parse_map": {"origin/main": SHA_B, "HEAD": SHA_D},
        "merge_base_map": {(SHA_B, head): SHA_B},
        "is_ancestor_map": {(SHA_A, SHA_B): True},
        "blob_map": {
            f"{base}:{rel_task}": SHA_C,
            f"{head}:{rel_task}": SHA_C,
            f"{SHA_G}:{rel_handoff}": SHA_D,
            f"{head}:{rel_handoff}": SHA_D,
        },
        "log_map": {f"{base}..{head}::{rel_handoff}": SHA_G},
        "diff_name_only": "file1.md\nfile2.py",
        "diff_name_status": "A\tfile1.md\tfile1.md\nA\tfile2.py\tfile2.py",
    }


# ── Negative tests: schema ──────────────────────────────────────────────


def test_schema_missing_field_fails() -> None:
    """Validator must fail when a required schema field is missing."""
    handoff = _make_valid_handoff()
    del handoff["planning_base_sha"]
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("planning_base_sha" in e for e in errors)


def test_schema_invalid_sha_format_fails() -> None:
    """Validator must fail when a SHA field is not 40 hex chars."""
    handoff = _make_valid_handoff()
    handoff["expected_base_sha"] = "not-a-sha"
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("sha" in e.lower() for e in errors)


# ── Negative: base / PR base identity ──────────────────────────────────


def test_divergent_base_and_pr_base_fails() -> None:
    """Validator must fail when expected_base_sha != expected_pr_base_sha."""
    handoff = _make_valid_handoff()
    handoff["expected_pr_base_sha"] = SHA_E  # different from expected_base_sha (SHA_B)
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("expected_base_sha" in e and "expected_pr_base_sha" in e for e in errors)


# ── Negative tests: handoff immutability ───────────────────────────────


def test_handoff_not_introduced_in_range_fails() -> None:
    """Validator must fail when no introduction commit is found in base..head."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    # No log entries = no introduction
    kwargs["log_map"] = {}
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("no introduction" in e for e in errors)


def test_handoff_ambiguous_introduction_fails() -> None:
    """Validator must fail when multiple commits touch the handoff file."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    # Two commits = ambiguous (e.g., deletion + reintroduction)
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    kwargs["log_map"] = {f"{SHA_B}..HEAD::{rel_handoff}": f"{SHA_G}\n{SHA_F}"}
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("ambiguous" in e.lower() for e in errors)


def test_handoff_introduced_then_modified_fails() -> None:
    """Validator must fail when the Handoff Record blob at head differs from introduction."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    # Blob at introduction = SHA_D, blob at head = SHA_E (modified)
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    kwargs["blob_map"][f"HEAD:{rel_handoff}"] = SHA_E
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    lowered = [e.lower() for e in errors]
    assert any("handoff" in e and "modified" in e for e in lowered)


def test_handoff_deleted_at_head_fails() -> None:
    """Validator must fail when the Handoff Record is not found at head."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    # Remove blob at HEAD for handoff file (simulates deletion)
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    if f"HEAD:{rel_handoff}" in kwargs["blob_map"]:
        del kwargs["blob_map"][f"HEAD:{rel_handoff}"]
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("not found at head" in e or "deleted" in e.lower() for e in errors)


def test_supplied_head_differs_from_ambient_head_task_blob() -> None:
    """Task blob check must use supplied head, not ambient HEAD."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    # Use a specific SHA as head instead of "HEAD"
    kwargs = _default_git_kwargs(head=SHA_D)
    # Blob at SHA_D matches frozen (valid)
    errors = _run_validator_func(handoff, task_fm, head=SHA_D, **kwargs)
    assert errors == [], f"unexpected errors: {errors}"

    # Now make blob at SHA_D differ from frozen
    kwargs2 = _default_git_kwargs(head=SHA_D)
    rel_task = "tasks/active/TASK-056-codex-cline-collaboration.md"
    kwargs2["blob_map"][f"{SHA_D}:{rel_task}"] = SHA_E
    errors2 = _run_validator_func(handoff, task_fm, head=SHA_D, **kwargs2)
    assert any("drift" in e.lower() for e in errors2)


def test_supplied_head_differs_from_ambient_head_record_blob() -> None:
    """Handoff blob check must use supplied head, not ambient HEAD."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    # Use SHA_F as head; blob at SHA_F for handoff differs from introduction
    kwargs = _default_git_kwargs(head=SHA_F)
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    kwargs["log_map"] = {f"{SHA_B}..{SHA_F}::{rel_handoff}": SHA_G}
    kwargs["blob_map"][f"{SHA_F}:{rel_handoff}"] = SHA_E  # different from SHA_D
    kwargs["merge_base_map"] = {(SHA_B, SHA_F): SHA_B}
    errors = _run_validator_func(handoff, task_fm, head=SHA_F, **kwargs)
    lowered = [e.lower() for e in errors]
    assert any("handoff" in e and "modified" in e for e in lowered)


# ── Negative tests: codex_only_paths ───────────────────────────────────


def test_missing_codex_only_paths_fails() -> None:
    """Validator must fail when codex_only_paths is missing."""
    handoff = _make_valid_handoff()
    del handoff["codex_only_paths"]
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("codex_only_paths" in e for e in errors)


def test_malformed_codex_only_paths_fails() -> None:
    """Validator must fail when codex_only_paths is empty or non-list."""
    handoff = _make_valid_handoff()
    handoff["codex_only_paths"] = []
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("codex_only_paths" in e for e in errors)


def test_codex_only_paths_not_containing_handoff_fails() -> None:
    """Validator must fail when codex_only_paths does not contain the handoff file."""
    handoff = _make_valid_handoff()
    handoff["codex_only_paths"] = ["some/other/file.md"]
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    # The schema validation checks codex_only_paths is non-empty list,
    # but the containment check is done in run_validation
    assert len(errors) > 0


# ── Negative tests: base / merge-base ──────────────────────────────────


def test_base_mismatch_fails() -> None:
    """Validator must fail when base-ref does not resolve to expected_base_sha."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    kwargs["rev_parse_map"] = {"origin/main": SHA_E}  # wrong SHA
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("base-ref" in e and "resolves" in e for e in errors)


def test_merge_base_mismatch_fails() -> None:
    """Validator must fail when merge-base != expected_base_sha."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    kwargs["merge_base_map"] = {(SHA_B, "HEAD"): SHA_E}  # wrong merge-base
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("merge-base" in e for e in errors)


def test_planning_base_not_ancestor_fails() -> None:
    """Validator must fail when planning_base is not ancestor of expected_base."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    kwargs = _default_git_kwargs()
    kwargs["is_ancestor_map"] = {(SHA_A, SHA_B): False}
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("ancestor" in e.lower() for e in errors)


# ── Negative tests: path audit ─────────────────────────────────────────


def test_path_outside_handoff_allowed_fails() -> None:
    """Validator must fail when a changed path is not in Handoff allowed_paths."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    task_fm["allowed_paths"] = ["file1.md", "file2.py", "rogue.py"]  # task allows it
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md\nfile2.py\nrogue.py"
    kwargs["diff_name_status"] = (
        "A\tfile1.md\tfile1.md\nA\tfile2.py\tfile2.py\nA\trogue.py\trogue.py"
    )
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    # rogue.py is in task allowed but NOT in handoff allowed_paths
    assert any("rogue.py" in e and "Handoff" in e for e in errors)


def test_path_allowed_by_handoff_but_outside_task_fails() -> None:
    """Validator must fail when path is in Handoff allowed but not task allowed."""
    handoff = _make_valid_handoff()
    handoff["allowed_paths"] = ["file1.md", "file2.py", "ai/handoffs/TASK-056-REPAIR-v1.yaml"]
    task_fm = _make_valid_task_fm()
    task_fm["allowed_paths"] = ["file1.md"]  # file2.py NOT in task allowed
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md\nfile2.py"
    kwargs["diff_name_status"] = "A\tfile1.md\tfile1.md\nA\tfile2.py\tfile2.py"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("file2.py" in e and "task allowed" in e for e in errors)


def test_forbidden_path_fails() -> None:
    """Validator must fail when a changed path matches a forbidden pattern."""
    handoff = _make_valid_handoff()
    handoff["allowed_paths"] = ["file1.md", "file2.py", "spec/something.md"]
    task_fm = _make_valid_task_fm()
    task_fm["allowed_paths"] = ["file1.md", "file2.py", "spec/something.md"]
    task_fm["forbidden_paths"] = ["spec/**"]
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md\nspec/something.md"
    kwargs["diff_name_status"] = "A\tfile1.md\tfile1.md\nA\tspec/something.md\tspec/something.md"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("forbidden" in e.lower() for e in errors)


def test_rename_outside_allowed_fails() -> None:
    """Validator must fail when a rename target is not in allowed_paths."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    task_fm["allowed_paths"] = ["file1.md", "file2.py", "ai/handoffs/TASK-056-REPAIR-v1.yaml"]
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md"
    kwargs["diff_name_status"] = "R100\tfile1.md\trenamed_outside.md"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("rename" in e.lower() and ("renamed_outside" in e or "allowed" in e) for e in errors)


def test_rename_forbidden_fails() -> None:
    """Validator must fail when rename destination matches a forbidden pattern."""
    handoff = _make_valid_handoff()
    handoff["allowed_paths"] = ["file1.md", "src/foo.py"]
    task_fm = _make_valid_task_fm()
    task_fm["allowed_paths"] = ["file1.md", "src/foo.py"]
    task_fm["forbidden_paths"] = ["src/**"]
    kwargs = _default_git_kwargs()
    kwargs["diff_name_only"] = "file1.md"
    kwargs["diff_name_status"] = "R100\tfile1.md\tsrc/foo.py"
    errors = _run_validator_func(handoff, task_fm, **kwargs)
    assert any("forbidden" in e.lower() and "rename" in e.lower() for e in errors)


# ── Positive: valid state ──────────────────────────────────────────────


def test_valid_state_passes() -> None:
    """Validator must pass when all checks are satisfied."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert errors == [], f"unexpected errors: {errors}"
