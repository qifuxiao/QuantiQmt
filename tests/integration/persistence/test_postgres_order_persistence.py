from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path
from typing import Any

import pytest
from tests.contract.persistence.test_order_persistence_contract import (
    DEADLINE,
    INTENT_ID,
    ORDER_ID,
    registered_commit,
    transition_commit,
)

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.order.application.persistence import (
    ClaimPolicy,
    IdempotencyConflict,
    PublishFailure,
)
from quantiqmt.order.domain import OrderState, OrderVersionConflict
from quantiqmt.order.infrastructure.postgres import PostgresOrderPersistence


@pytest.fixture()
def postgres_store() -> PostgresOrderPersistence:
    dsn = os.environ.get("QUANTIQMT_POSTGRES_DSN")
    if not dsn:
        pytest.fail("QUANTIQMT_POSTGRES_DSN is required for PostgreSQL integration tests")
    _asyncpg()
    store = PostgresOrderPersistence(dsn)
    store.apply_migration(
        Path("migrations/001_order_persistence_outbox.sql").read_text(encoding="utf-8"),
        deadline_monotonic_ns=DEADLINE,
    )
    asyncio.run(_truncate_tables(dsn))
    return store


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.project_default()


def test_postgres_register_is_atomic_and_idempotent(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    commit = registered_commit(registry)
    outcome = postgres_store.register(commit, deadline_monotonic_ns=DEADLINE)
    assert outcome.created is True
    assert postgres_store.get_by_intent(INTENT_ID, deadline_monotonic_ns=DEADLINE) is not None

    replay = postgres_store.register(commit, deadline_monotonic_ns=DEADLINE)
    assert replay.created is False
    assert replay.persisted_order.registration.order_id == ORDER_ID

    with pytest.raises(IdempotencyConflict, match="QQ-STORAGE-7001"):
        postgres_store.register(
            registered_commit(registry, fingerprint="b" * 64),
            deadline_monotonic_ns=DEADLINE,
        )


def test_postgres_save_cas_journal_and_outbox_are_committed_together(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    commit = transition_commit(registry, registered.persisted_order)
    with pytest.raises(OrderVersionConflict, match="QQ-COMMON-1003"):
        postgres_store.save(commit, expected_version=99, deadline_monotonic_ns=DEADLINE)

    stored = postgres_store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    assert stored is not None
    assert stored.order.version == 1

    saved = postgres_store.save(commit, expected_version=1, deadline_monotonic_ns=DEADLINE)
    assert saved.order.state is OrderState.RISK_PENDING
    recovered = postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    assert recovered.persisted_order.order.version == 2


def test_postgres_outbox_claim_lease_fencing_and_dead_letter(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    postgres_store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 3, 10, 100, "2", "0")

    first = postgres_store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)
    assert len(first) == 1
    assert first[0].attempt_count == 1

    asyncio.run(_expire_claim(first[0].message_id))
    assert (
        postgres_store.mark_published(
            first[0].message_id, first[0].claim_token, deadline_monotonic_ns=DEADLINE
        ).code
        == "QQ-STORAGE-7004"
    )

    second = postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)
    assert second[0].message_id == first[0].message_id
    assert second[0].claim_token != first[0].claim_token
    assert second[0].attempt_count == 2
    assert postgres_store.release_failed(
        second[0].message_id,
        second[0].claim_token,
        PublishFailure("PUBLISH_FAILED", "backbone unavailable", retryable=False),
        deadline_monotonic_ns=DEADLINE,
    ).applied


def test_postgres_retryable_failure_reaches_max_attempts_before_next_claim(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    postgres_store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 1, 10, 100, "2", "0")
    claimed = postgres_store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)[0]

    assert postgres_store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "temporary backbone outage", retryable=True),
        deadline_monotonic_ns=DEADLINE,
    ).applied

    assert postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    assert asyncio.run(_outbox_status(claimed.message_id)) == (
        "DEAD_LETTER",
        "MAX_ATTEMPTS_REACHED",
    )


async def _truncate_tables(dsn: str) -> None:
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            """
            TRUNCATE outbox_messages, order_snapshots, order_journal, orders
            RESTART IDENTITY
            """
        )
    finally:
        await connection.close()


async def _outbox_status(message_id: str) -> tuple[str, str | None]:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            """
            SELECT status, last_error_code
            FROM outbox_messages
            WHERE message_id = $1
            """,
            message_id,
        )
        assert row is not None
        return str(row["status"]), row["last_error_code"]
    finally:
        await connection.close()


async def _expire_claim(message_id: str) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            """
            UPDATE outbox_messages
            SET lease_until = transaction_timestamp() - interval '1 millisecond'
            WHERE message_id = $1
            """,
            message_id,
        )
    finally:
        await connection.close()


def _asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        pytest.fail("asyncpg storage extra is required for PostgreSQL integration tests")
        raise AssertionError from exc
