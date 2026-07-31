---
id: TASK-000
title: Establish engineering toolchain and executable spec validation
status: completed
depends_on: []
spec_refs: [INV-TRADING, INV-CONSISTENCY, INV-RISK]
allowed_paths: [pyproject.toml, poetry.lock, .python-version, .gitignore, .gitattributes, .pre-commit-config.yaml, .github/**, .env.example, scripts/**, tests/spec/**, spec/**, tasks/**, AGENTS.md, README.md, docs/README.md, docs/ADR/README.md, docs/ADR/ADR-0008-Python-Technical-Stack.md]
forbidden_paths: [src/quantiqmt/order/**, src/quantiqmt/risk/**, src/quantiqmt/broker/**, strategies/**]
verification:
  commands: ["poetry check", "poetry run python scripts/validate_specs.py", "poetry run ruff check scripts tests/spec", "poetry run mypy scripts", "poetry run pytest tests/spec"]
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: unverified
  review_status: reported_unverified
  release_status: prohibited
  remediation_task: TASK-031
  completion_evidence: {mode: historical_evidence_unverifiable, change_pr: unverifiable, reviewed_head_sha: unverifiable, review_verdict: reported_unverified, reviewer: unverifiable, evidence_url: unverifiable, merge_commit_sha: unverifiable, human_authorization_evidence: TASK-031 governance recovery authorization}
---

# Objective

建立 Python 3.12、开发依赖、CI、Lint/Type/Test 配置和可执行的 spec/task 验证器，使后续任务的验证命令真实可运行。

## Acceptance criteria

- [x] Python 基线与 pyproject/docs 一致。
- [x] pytest、mypy、ruff、Hypothesis、JSON Schema 和 YAML 工具被锁定。
- [x] CI 执行 metadata、spec、lint、format、type 和 test 门禁。
- [x] 验证器检查 JSON/YAML、manifest 路径、task spec_refs/index/DAG、错误码和状态机结构。
- [x] TASK-001 依赖 TASK-000，未完成前不能激活。
- [x] 不开发任何交易业务模块。

## Evidence

- Python: CPython 3.12.10, Poetry environment `py3.12`.
- `poetry check`: passed.
- `poetry run python scripts/validate_specs.py`: passed.
- `poetry run ruff check .`: passed.
- `poetry run ruff format --check .`: passed.
- `poetry run mypy src scripts`: passed.
- `poetry run pytest tests/spec`: passed.
- Approved by the Project Owner on 2026-07-02; all acceptance criteria and verification commands passed.
