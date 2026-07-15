from __future__ import annotations

from pathlib import Path

import yaml


def test_order_persistence_migration_is_expand_only_and_contains_required_tables() -> None:
    sql = Path("migrations/001_order_persistence_outbox.sql").read_text(encoding="utf-8")
    lowered = sql.lower()
    assert "drop table" not in lowered
    assert "delete from" not in lowered
    assert "create table if not exists orders" in lowered
    assert "create table if not exists order_journal" in lowered
    assert "create table if not exists order_snapshots" in lowered
    assert "create table if not exists outbox_messages" in lowered
    assert "unique (order_id, aggregate_version)" in lowered
    assert "outbox_pending_fields" in lowered
    assert "outbox_claimed_fields" in lowered
    assert "outbox_published_fields" in lowered
    assert "outbox_dead_letter_fields" in lowered


def test_ci_declares_postgresql_persistence_job_without_mutating_task_scope() -> None:
    document = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = document["jobs"]["persistence-postgresql"]
    assert job["services"]["postgres"]["image"].startswith("postgres:")
    assert job["env"]["QUANTIQMT_POSTGRES_DSN"].startswith("postgresql://")
    commands = [step.get("run", "") for step in job["steps"]]
    expected = "pytest tests/unit/order/application tests/contract/persistence"
    assert any(
        expected in command and "tests/integration/persistence" in command for command in commands
    )
