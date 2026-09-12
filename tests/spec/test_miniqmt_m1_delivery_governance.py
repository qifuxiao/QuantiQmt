from __future__ import annotations

from pathlib import Path

import yaml
from scripts.validate_specs import delivery_is_unlockable, extract_front_matter

ROOT = Path(__file__).resolve().parents[2]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _yaml(relative_path: str) -> dict[str, object]:
    value = yaml.safe_load(_text(relative_path))
    assert isinstance(value, dict)
    return value


def test_tasks_029_054_055_056_057_completed_task005_paused_only_task058_active() -> None:
    active = sorted((ROOT / "tasks" / "active").glob("TASK-*.md"))
    task_029_path = ROOT / "tasks/completed/TASK-029-risk-runtime-schema-contract.md"
    assert active == [ROOT / "tasks/active/TASK-058-risk-finalization-boundary.md"]

    task_029 = extract_front_matter(task_029_path)
    assert task_029["status"] == "completed"
    assert task_029["depends_on"] == ["TASK-015", "TASK-030", "TASK-031"]
    assert {
        key: value for key, value in task_029["delivery"].items() if key != "completion_evidence"
    } == {
        "schema_version": 1,
        "contract_status": "accepted",
        "implementation_status": "merged",
        "acceptance_status": "passed",
        "review_status": "approved",
        "release_status": "prohibited",
    }
    assert "remediation_task" not in task_029["delivery"]
    assert delivery_is_unlockable(task_029)
    evidence = task_029["delivery"]["completion_evidence"]
    assert evidence["change_pr"] == "https://github.com/qifuxiao/QuantiQmt/pull/110"
    assert evidence["reviewed_head_sha"] == "e76ed9c4faacfa3d9521dfd1185f3a62b93f86ac"
    assert evidence["merge_commit_sha"] == "7681530fa835e28bb17db9ad19eb9cf61bfdcd18"
    assert evidence["review_verdict"] == "APPROVE"
    assert evidence["reviewer"] == "qfxyyy"
    assert evidence["evidence_url"].endswith("pullrequestreview-5133890761")
    assert "5573292852" in evidence["human_authorization_evidence"]
    assert "5573098781" in evidence["environment_evidence"]
    for authorized_path in (
        "ai/packets/TASK-029-IMPLEMENTATION-v1.md",
        "ai/handoffs/TASK-029-IMPLEMENTATION-v1.yaml",
        "tasks/completed/TASK-029-risk-runtime-schema-contract.md",
    ):
        assert authorized_path in task_029["allowed_paths"]

    task_029_text = _text("tasks/completed/TASK-029-risk-runtime-schema-contract.md")
    assert "TASK-029-PLAN-v2" in task_029_text
    assert "286c3901b3801fd752feaaf615167cef248a9494" in task_029_text
    assert "无需读取源码 `spec/**`" in task_029_text
    assert "Schema validation → semantic validation → freeze" in task_029_text

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
    assert completion["change_pr"] == "https://github.com/qifuxiao/QuantiQmt/pull/106"
    assert completion["reviewed_head_sha"] == ("07c3abd29fd1d7b5feffa5c8b5845c2c4d057d1c")
    assert completion["review_verdict"] == "APPROVE"
    assert completion["merge_commit_sha"] == ("56b1655780b0917fcef1e2016796d5b4efe3c8ef")
    assert "4/4 exact-Head GitHub jobs" in completion["ci_evidence"]
    assert "WAIVED_BY_HUMAN" in completion["waiver_evidence"]
    assert "exit 1" in completion["waiver_evidence"]
    assert "5526914844" in completion["environment_evidence"]
    assert "5527455377" in completion["human_authorization_evidence"]
    assert (
        "34c3b51f8e4a99f7ea6b6e510cce12edfd713bcd366b103e19b58a66d95c53c4"
        in completion["human_authorization_evidence"]
    )

    paused = ROOT / "tasks/backlog/TASK-053-dependency-sequencing-governance.md"
    assert extract_front_matter(paused)["status"] == "blocked"
    task_005_path = ROOT / "tasks/backlog/TASK-005-risk-engine.md"
    task_005 = extract_front_matter(task_005_path)
    assert task_005["status"] == "blocked"
    assert task_005["depends_on"] == ["TASK-003", "TASK-015", "TASK-029"]
    assert task_005["delivery"]["implementation_status"] == "not_started"
    assert task_005["delivery"]["acceptance_status"] == "not_run"
    assert task_005["delivery"]["review_status"] == "pending"
    assert task_005["delivery"]["release_status"] == "prohibited"
    for dependency in task_005["depends_on"]:
        path = next((ROOT / "tasks/completed").glob(f"{dependency}-*.md"))
        assert delivery_is_unlockable(extract_front_matter(path))

    task_058 = extract_front_matter(active[0])
    assert task_058["status"] == "active"
    assert task_058["depends_on"] == task_005["depends_on"]
    assert task_058["delivery"] == {
        "schema_version": 1,
        "contract_status": "draft",
        "implementation_status": "not_started",
        "acceptance_status": "not_run",
        "review_status": "pending",
        "release_status": "prohibited",
    }
    assert task_058["allowed_paths"] == [
        "spec/interfaces/risk-ports.md",
        "spec/nfr/performance.yaml",
        "spec/nfr/observability.yaml",
        "spec/workflows/submit-order.yaml",
        "spec/manifest.yaml",
        "tests/spec/test_order_registration_binding_contracts.py",
        "tests/spec/test_risk_runtime_schema_contract.py",
        "tests/unit/contracts/test_schema_bundle.py",
        "ai/packets/TASK-058-IMPLEMENTATION-v2.md",
        "ai/handoffs/TASK-058-IMPLEMENTATION-v2.yaml",
    ]
    verification = task_058["verification"]
    assert verification["commands"] == [
        "poetry run python scripts/validate_specs.py",
        "poetry run pytest tests/spec tests/contract",
        "poetry run pytest tests/unit/contracts",
    ]
    assert verification["required_lanes"] == [
        {
            "lane": "portable",
            "capability": "portable",
            "minimum_records": 1,
            "commands": verification["commands"],
        }
    ]
    assert verification["prohibited_lanes"] == ["windows_miniqmt"]
    paused_text = task_005_path.read_text(encoding="utf-8")
    for frozen in ("5628617915", "5629435266", "88d217661f6d6c127758fc245336a9f806788ab9"):
        assert frozen in paused_text
    assert "TASK-058" in paused_text
    task_text = active[0].read_text(encoding="utf-8")
    assert "- Plan version: `TASK-058-PLAN-v2`" in task_text
    assert "5646729029" in task_text
    assert "02fc1857a2fa885ba59477de37a7e20ca965fc3f" in task_text
    assert "poetry build" in task_text
    assert task_058["forbidden_paths"] == [
        "src/**",
        "tests/contract/**",
        "tests/property/**",
        "tests/integration/**",
        "scripts/**",
        "tasks/**",
        ".github/**",
        "migrations/**",
        "spec/contracts/**",
        "spec/invariants/**",
        "spec/state-machines/**",
        "ai/packets/TASK-058-IMPLEMENTATION-v1.md",
        "ai/handoffs/TASK-058-IMPLEMENTATION-v1.yaml",
        "pyproject.toml",
        "poetry.lock",
        "poetry.toml",
    ]

    entries = _yaml("tasks/index.yaml")["tasks"]
    assert isinstance(entries, list)
    indexed = {entry["id"]: entry for entry in entries}
    assert indexed["TASK-005"]["path"] == "backlog/TASK-005-risk-engine.md"
    assert indexed["TASK-005"]["status"] == "blocked"
    assert indexed["TASK-058"]["path"] == "active/TASK-058-risk-finalization-boundary.md"
    assert indexed["TASK-058"]["status"] == "active"
    assert indexed["TASK-029"]["path"] == ("completed/TASK-029-risk-runtime-schema-contract.md")
    assert indexed["TASK-029"]["status"] == "completed"
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
