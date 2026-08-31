"""Executable tests for the AI Handoff validator (TASK-056 Repair Addendum 2).

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

import pytest
import yaml

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
    assert result.returncode == 0, result.stdout + result.stderr


# ── Integration: real frozen handoff ─────────────────────────────────────


def test_optional_checkout_smoke_validator_passes_on_frozen_handoff() -> None:
    """Optionally smoke-test the real checkout when its remote history is available."""
    # Skip if origin/main is not available (shallow CI checkout)
    probe = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if probe.returncode != 0:
        pytest.skip("origin/main not available (shallow clone)")
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


# ── Non-skipping real-Git topology acceptance tests ────────────────────


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git in a constructed repository."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=check,
    )


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _handoff_data(base: str, task_blob: str, superseded: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": "TASK-056",
        "packet_version": "TASK-056-REPAIR-v1",
        "plan_version": "TASK-056-PLAN-v3",
        "planning_base_sha": base,
        "expected_base_sha": base,
        "expected_pr_base_sha": base,
        "task_blob_sha": task_blob,
        "allowed_paths": [
            "repair.txt",
            "ai/handoffs/TASK-056-REPAIR-v1.yaml",
        ],
        "codex_only_paths": ["ai/handoffs/TASK-056-REPAIR-v1.yaml"],
        "repair_context": {"superseded_head_sha": superseded},
    }


def _create_real_git_topology(tmp_path: Path, scenario: str = "valid") -> dict[str, Any]:
    """Create real Base/Handoff/superseded/sync/repair history for CLI tests."""
    repo = tmp_path / scenario
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Topology Test")
    _git(repo, "config", "user.email", "topology@example.invalid")
    task_rel = "tasks/active/TASK-056-codex-cline-collaboration.md"
    handoff_rel = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    _write(
        repo,
        task_rel,
        """---
id: TASK-056
status: active
allowed_paths:
  - repair.txt
  - ai/handoffs/TASK-056-REPAIR-v1.yaml
forbidden_paths:
  - forbidden/**
---
\n# Constructed task\n""",
    )
    _write(repo, "baseline.txt", "base\n")
    base = _commit_all(repo, "base")
    _git(repo, "branch", "frozen-base", base)
    task_blob = _git(repo, "rev-parse", f"{base}:{task_rel}").stdout.strip()

    _git(repo, "checkout", "-b", "superseded", base)
    _write(repo, "repair.txt", "superseded implementation\n")
    superseded = _commit_all(repo, "superseded implementation")

    if scenario in {"late_introduction", "wrong_parent"}:
        if scenario == "late_introduction":
            _write(repo, "repair.txt", "late repair before handoff\n")
            _commit_all(repo, "repair before handoff")
        else:
            _git(repo, "commit", "--allow-empty", "-m", "non-repair parent")
        record = _handoff_data(base, task_blob, superseded)
        _write(repo, handoff_rel, yaml.safe_dump(record, sort_keys=False))
        intro = _commit_all(repo, "late handoff")
        return {
            "repo": repo,
            "base": base,
            "superseded": superseded,
            "intro": intro,
            "head": intro,
            "task": task_rel,
            "handoff": handoff_rel,
        }

    _git(repo, "checkout", "-b", "handoff", base)
    record = _handoff_data(base, task_blob, superseded)
    _write(repo, handoff_rel, yaml.safe_dump(record, sort_keys=False))
    intro = _commit_all(repo, "Codex add-only handoff")

    _git(repo, "checkout", "superseded")
    if scenario == "pre_handoff_repair":
        _write(repo, "repair.txt", "repair created before handoff incorporation\n")
        _commit_all(repo, "pre-handoff repair")
    _git(repo, "merge", "--no-ff", "handoff", "-m", "synchronize handoff")

    if scenario != "pre_handoff_repair":
        _write(repo, "repair.txt", "post-handoff repair\n")
        _commit_all(repo, "post-handoff repair")

    if scenario == "record_modified":
        with (repo / handoff_rel).open("a", encoding="utf-8") as stream:
            stream.write("tampered: true\n")
        _commit_all(repo, "modify handoff")
    elif scenario == "record_reintroduced":
        original = (repo / handoff_rel).read_text(encoding="utf-8")
        (repo / handoff_rel).unlink()
        _commit_all(repo, "delete handoff")
        _write(repo, handoff_rel, original)
        _commit_all(repo, "reintroduce handoff")
    elif scenario == "path_violation":
        _write(repo, "forbidden/rogue.txt", "out of scope\n")
        _commit_all(repo, "forbidden path")
    elif scenario == "merge_tamper_restore":
        original = (repo / handoff_rel).read_text(encoding="utf-8")
        _git(repo, "checkout", "-b", "record-tamper-side")
        with (repo / handoff_rel).open("a", encoding="utf-8") as stream:
            stream.write("tampered: true\n")
        _commit_all(repo, "tamper handoff on side branch")
        _write(repo, handoff_rel, original)
        _commit_all(repo, "restore handoff blob on side branch")
        _git(repo, "checkout", "superseded")
        _git(
            repo,
            "merge",
            "--no-ff",
            "record-tamper-side",
            "-m",
            "merge restored handoff side branch",
        )

    return {
        "repo": repo,
        "base": base,
        "superseded": superseded,
        "intro": intro,
        "head": _git(repo, "rev-parse", "HEAD").stdout.strip(),
        "task": task_rel,
        "handoff": handoff_rel,
    }


def _run_real_git_cli(
    topology: dict[str, Any], pr_base: str | None = None
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(VALIDATOR),
        "--task",
        str(topology["task"]),
        "--handoff",
        str(topology["handoff"]),
        "--base-ref",
        "frozen-base",
        "--head",
        str(topology["head"]),
    ]
    if pr_base is not None:
        args.extend(["--pr-base", pr_base])
    return subprocess.run(
        args,
        cwd=topology["repo"],
        capture_output=True,
        text=True,
    )


def test_real_git_topology_success(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path)
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_git_topology_rejects_late_introduction(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path, "late_introduction")
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "parent" in result.stderr.lower() or "before" in result.stderr.lower()


def test_real_git_topology_rejects_wrong_parent(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path, "wrong_parent")
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "parent" in result.stderr.lower()


def test_real_git_topology_rejects_pre_handoff_repair(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path, "pre_handoff_repair")
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "repair" in result.stderr.lower() and "descendant" in result.stderr.lower()


@pytest.mark.parametrize("scenario", ["record_modified", "record_reintroduced"])
def test_real_git_topology_rejects_record_touch(tmp_path: Path, scenario: str) -> None:
    topology = _create_real_git_topology(tmp_path, scenario)
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "handoff record" in result.stderr.lower()


def test_real_git_topology_rejects_wrong_pr_base(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path)
    result = _run_real_git_cli(topology, topology["intro"])
    assert result.returncode != 0
    assert "pr base" in result.stderr.lower()


def test_real_git_topology_rejects_path_violation(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path, "path_violation")
    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "forbidden" in result.stderr.lower() or "allowed_paths" in result.stderr


def test_real_git_topology_binds_all_queries_to_supplied_head(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path)
    supplied_head = topology["head"]
    _write(topology["repo"], "forbidden/ambient-only.txt", "must be ignored\n")
    _commit_all(topology["repo"], "ambient head moves after supplied head")
    result = _run_real_git_cli(topology, topology["base"])
    assert topology["head"] == supplied_head
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_git_topology_rejects_merge_dag_tamper_restore(tmp_path: Path) -> None:
    topology = _create_real_git_topology(tmp_path, "merge_tamper_restore")
    path = str(topology["handoff"])
    commit_range = f"{topology['base']}..{topology['head']}"
    simplified = _git(
        topology["repo"],
        "log",
        "--format=%H",
        commit_range,
        "--",
        path,
    ).stdout.splitlines()
    full_history = _git(
        topology["repo"],
        "log",
        "--full-history",
        "--format=%H",
        commit_range,
        "--",
        path,
    ).stdout.splitlines()
    assert len(simplified) == 1, simplified
    assert len(full_history) >= 3, full_history

    result = _run_real_git_cli(topology, topology["base"])
    assert result.returncode != 0
    assert "handoff record" in result.stderr.lower()


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
    parent_map: dict[str, list[str]] | None = None,
    path_status_map: dict[tuple[str, str], str] | None = None,
    repair_log_map: dict[str, str] | None = None,
    diff_name_only: str = "",
    diff_name_status: str = "",
) -> Any:
    """Create a mock for subprocess.run that simulates git commands."""
    rev_parse_map = rev_parse_map or {}
    merge_base_map = merge_base_map or {}
    is_ancestor_map = is_ancestor_map or {}
    blob_map = blob_map or {}
    log_map = log_map or {}
    parent_map = parent_map or {}
    path_status_map = path_status_map or {}
    repair_log_map = repair_log_map or {}

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

        # git rev-list --parents -n 1 <commit>
        if args[0] == "rev-list" and "--parents" in args:
            commit = args[-1]
            if commit in parent_map:
                return _result(0, " ".join([commit, *parent_map[commit]]) + "\n", "")
            return _result(128, "", f"unknown commit {commit}")

        # git rev-list --full-history <base>..<head> -- <paths...>
        if args[0] == "rev-list" and "--full-history" in args:
            range_arg = next((arg for arg in args if ".." in arg), "")
            if range_arg in repair_log_map:
                return _result(0, repair_log_map[range_arg] + "\n", "")
            return _result(0, "", "")

        # git diff-tree ... <commit> -- <path>
        if args[0] == "diff-tree":
            separator = args.index("--")
            commit = args[separator - 1]
            path_arg = args[separator + 1]
            key = (commit, path_arg)
            if key in path_status_map:
                return _result(0, path_status_map[key] + "\n", "")
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
        "repair_context": {"superseded_head_sha": SHA_E},
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
    pr_base: str | None = None,
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
            pr_base=pr_base,
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
        "is_ancestor_map": {
            (SHA_A, SHA_B): True,
            (SHA_G, head): True,
            (SHA_E, head): True,
            (SHA_G, SHA_G): True,
        },
        "blob_map": {
            f"{base}:{rel_task}": SHA_C,
            f"{head}:{rel_task}": SHA_C,
            f"{SHA_G}:{rel_handoff}": SHA_D,
            f"{head}:{rel_handoff}": SHA_D,
        },
        "log_map": {f"{base}..{head}::{rel_handoff}": SHA_G},
        "parent_map": {SHA_G: [SHA_B]},
        "path_status_map": {(SHA_G, rel_handoff): f"A\t{rel_handoff}"},
        "repair_log_map": {f"{SHA_E}..{head}": SHA_G},
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


@pytest.mark.parametrize(
    ("repair_context", "expected_fragment"),
    [
        (None, "repair_context"),
        ({}, "superseded_head_sha"),
        ({"superseded_head_sha": "not-a-sha"}, "superseded_head_sha"),
    ],
)
def test_repair_context_structure_fails_closed(
    repair_context: Any,
    expected_fragment: str,
) -> None:
    handoff = _make_valid_handoff()
    if repair_context is None:
        del handoff["repair_context"]
    else:
        handoff["repair_context"] = repair_context
    errors = _run_validator_func(handoff, _make_valid_task_fm(), **_default_git_kwargs())
    assert any(expected_fragment in error for error in errors)


# ── Negative: base / PR base identity ──────────────────────────────────


def test_divergent_base_and_pr_base_fails() -> None:
    """Validator must fail when expected_base_sha != expected_pr_base_sha."""
    handoff = _make_valid_handoff()
    handoff["expected_pr_base_sha"] = SHA_E  # different from expected_base_sha (SHA_B)
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(handoff, task_fm, **_default_git_kwargs())
    assert any("expected_base_sha" in e and "expected_pr_base_sha" in e for e in errors)


def test_supplied_pr_base_different_from_both_frozen_bases_fails() -> None:
    """Core validation must reject an external PR Base distinct from frozen Base."""
    handoff = _make_valid_handoff()
    task_fm = _make_valid_task_fm()
    errors = _run_validator_func(
        handoff,
        task_fm,
        pr_base=SHA_F,
        **_default_git_kwargs(),
    )
    assert any("PR base" in error and SHA_F in error for error in errors)


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
    kwargs["parent_map"][SHA_F] = [SHA_G]
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


def test_handoff_introduction_parent_must_equal_expected_base() -> None:
    kwargs = _default_git_kwargs()
    kwargs["parent_map"] = {SHA_G: [SHA_F]}
    errors = _run_validator_func(_make_valid_handoff(), _make_valid_task_fm(), **kwargs)
    assert any("parent" in error.lower() and "expected_base_sha" in error for error in errors)


def test_handoff_introduction_must_have_exactly_one_parent() -> None:
    kwargs = _default_git_kwargs()
    kwargs["parent_map"] = {SHA_G: [SHA_B, SHA_F]}
    errors = _run_validator_func(_make_valid_handoff(), _make_valid_task_fm(), **kwargs)
    assert any("exactly one parent" in error for error in errors)


def test_handoff_introduction_must_be_add_only() -> None:
    kwargs = _default_git_kwargs()
    rel_handoff = "ai/handoffs/TASK-056-REPAIR-v1.yaml"
    kwargs["path_status_map"] = {(SHA_G, rel_handoff): f"M\t{rel_handoff}"}
    errors = _run_validator_func(_make_valid_handoff(), _make_valid_task_fm(), **kwargs)
    assert any("add-only" in error for error in errors)


def test_superseded_head_must_be_ancestor_of_supplied_head() -> None:
    kwargs = _default_git_kwargs()
    kwargs["is_ancestor_map"] = {
        (SHA_A, SHA_B): True,
        (SHA_G, "HEAD"): True,
        (SHA_E, "HEAD"): False,
    }
    errors = _run_validator_func(_make_valid_handoff(), _make_valid_task_fm(), **kwargs)
    assert any("superseded_head_sha" in error and "supplied head" in error for error in errors)


def test_pre_handoff_repair_stage_commit_fails() -> None:
    kwargs = _default_git_kwargs()
    kwargs["repair_log_map"] = {f"{SHA_E}..HEAD": SHA_F}
    kwargs["is_ancestor_map"] = {
        (SHA_A, SHA_B): True,
        (SHA_G, "HEAD"): True,
        (SHA_E, "HEAD"): True,
        (SHA_G, SHA_F): False,
    }
    errors = _run_validator_func(_make_valid_handoff(), _make_valid_task_fm(), **kwargs)
    assert any("repair-stage" in error and "descendants" in error for error in errors)


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
