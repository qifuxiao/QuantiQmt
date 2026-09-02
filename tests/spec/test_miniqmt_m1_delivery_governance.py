from __future__ import annotations

from pathlib import Path

import yaml
from scripts.validate_specs import extract_front_matter

ROOT = Path(__file__).resolve().parents[2]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _yaml(relative_path: str) -> dict[str, object]:
    value = yaml.safe_load(_text(relative_path))
    assert isinstance(value, dict)
    return value


def test_tasks_054_055_056_057_are_completed_and_no_task_is_active() -> None:
    active = sorted((ROOT / "tasks" / "active").glob("TASK-*.md"))
    assert active == []

    completed = ROOT / "tasks/completed/TASK-054-miniqmt-m1-delivery-governance.md"
    task_054 = extract_front_matter(completed)
    assert task_054["status"] == "completed"
    assert task_054["delivery"]["implementation_status"] == "merged"
    assert task_054["delivery"]["acceptance_status"] == "passed"
    assert task_054["delivery"]["review_status"] == "approved"

    task_055_path = ROOT / "tasks/completed/TASK-055-miniqmt-readonly-environment-probe.md"
    task_055 = extract_front_matter(task_055_path)
    assert task_055["status"] == "completed"
    assert task_055["delivery"]["implementation_status"] == "merged"
    assert task_055["delivery"]["acceptance_status"] == "passed"
    assert task_055["delivery"]["review_status"] == "approved"
    assert task_055["delivery"]["release_status"] == "prohibited"

    task_056_path = ROOT / "tasks/completed/TASK-056-codex-cline-collaboration.md"
    task_056 = extract_front_matter(task_056_path)
    assert task_056["status"] == "completed"
    assert task_056["delivery"]["implementation_status"] == "merged"
    assert task_056["delivery"]["acceptance_status"] == "passed"
    assert task_056["delivery"]["review_status"] == "approved"
    assert task_056["delivery"]["release_status"] == "prohibited"

    task_057_path = (
        ROOT / "tasks/completed/TASK-057-tool-neutral-agents-windows-verification-poetry.md"
    )
    task_057 = extract_front_matter(task_057_path)
    assert task_057["status"] == "completed"
    assert task_057["delivery"]["implementation_status"] == "merged"
    assert task_057["delivery"]["acceptance_status"] == "passed"
    assert task_057["delivery"]["review_status"] == "approved"
    assert task_057["delivery"]["release_status"] == "prohibited"
    completion = task_057["delivery"]["completion_evidence"]
    assert completion["mode"] == "governance_closeout_after_independent_review"
    assert completion["change_pr"] == "https://github.com/qifuxiao/QuantiQmt/pull/100"
    assert completion["reviewed_head_sha"] == ("86b5a75585f646c7faf667645694776ac4273c20")
    assert completion["review_verdict"] == "APPROVE"
    assert completion["reviewer"] == "qifuxiao"
    assert completion["merge_commit_sha"] == ("40e73e6ada8f26494d2e39a4a46a7ec3e3971b31")
    assert "4/4 GitHub checks" in completion["ci_evidence"]
    assert "5507807554" in completion["human_authorization_evidence"]
    assert (
        "42211efc3b7e8bbb24238f2fc614bd1ce672de55f10a31256164d636edce5fa1"
        in (completion["human_authorization_evidence"])
    )

    paused = ROOT / "tasks/backlog/TASK-053-dependency-sequencing-governance.md"
    assert extract_front_matter(paused)["status"] == "blocked"

    entries = _yaml("tasks/index.yaml")["tasks"]
    assert isinstance(entries, list)
    indexed = {entry["id"]: entry for entry in entries}
    assert indexed["TASK-053"]["path"].startswith("backlog/")
    assert indexed["TASK-053"]["status"] == "blocked"
    assert indexed["TASK-054"]["path"].startswith("completed/")
    assert indexed["TASK-054"]["status"] == "completed"
    assert indexed["TASK-055"]["path"].startswith("completed/")
    assert indexed["TASK-055"]["status"] == "completed"
    assert indexed["TASK-056"]["path"].startswith("completed/")
    assert indexed["TASK-056"]["status"] == "completed"
    assert indexed["TASK-057"]["path"].startswith("completed/")
    assert indexed["TASK-057"]["status"] == "completed"


def test_product_rules_make_miniqmt_simulation_account_mandatory_for_m1() -> None:
    agents = _text("AGENTS.md")
    north_star = _text("docs/00-Architecture/06-Product-North-Star.md")
    milestone = _text("docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md")

    for content in (agents, north_star, milestone):
        assert "Mini QMT" in content
        assert "模拟账号" in content
        assert "OrderIntent" in content
        assert "Risk" in content
        assert "UNKNOWN" in content
        assert "真实资金" in content

    assert "Broker Simulator 不能替代 M1" in milestone
    assert "MINIQMT_SIM_READONLY" in milestone
    assert "MINIQMT_SIM_TRADING" in milestone
    assert "LIVE_PROHIBITED" in milestone
    assert "target interface" in milestone


def test_example_configuration_is_fail_closed_and_contains_no_broker_password() -> None:
    example = _text(".env.example")

    required = {
        "QUANTIQMT_PROFILE=MINIQMT_SIM_READONLY",
        "QUANTIQMT_QMT_USERDATA_PATH=",
        "QUANTIQMT_QMT_ACCOUNT_ID=",
        "QUANTIQMT_QMT_ACCOUNT_TYPE=STOCK",
        "QUANTIQMT_QMT_SESSION_ID=12001",
        "QUANTIQMT_QMT_ALLOWED_ACCOUNT_IDS=",
        "QUANTIQMT_QMT_ORDER_SEND_ENABLED=false",
        "QUANTIQMT_KILL_SWITCH_ENGAGED=true",
    }
    for line in required:
        assert line in example

    qmt_lines = [line for line in example.splitlines() if line.startswith("QUANTIQMT_QMT_")]
    assert all("PASSWORD" not in line and "SECRET" not in line for line in qmt_lines)


def test_backtest_and_miniqmt_share_semantics_without_sharing_external_assumptions() -> None:
    backtest = _text("docs/60-Backtest/Backtest-Architecture.md")
    milestone = _text("docs/00-Architecture/07-M1-MiniQMT-Simulation-Delivery.md")

    for content in (backtest, milestone):
        assert "不可变" in content
        assert "checksum" in content
        assert "VirtualClock" in content
        assert "OrderIntent" in content
        assert "OMS" in content
        assert "Risk" in content
        assert "Execution" in content
    assert "运行期间" in milestone
    assert "Mini QMT" in milestone


def test_codex_and_cline_use_one_tool_neutral_authority_chain() -> None:
    cline_rule = _text(".clinerules/00-quantiqmt-project.md")
    cline_adapter = _text("ai/adapters/cline.md")
    task_prompt = _text("ai/prompts/miniqmt-m1-task.md")

    for content in (cline_rule, cline_adapter, task_prompt):
        assert "AGENTS.md" in content
        assert "spec/manifest.yaml" in content
        assert "tasks/active/" in content
        assert "allowed_paths" in content
        assert "verification.commands" in content

    assert "不得复制" in cline_adapter
    assert "Task: TASK-XXX" in task_prompt
    assert "不得自行激活" in task_prompt
