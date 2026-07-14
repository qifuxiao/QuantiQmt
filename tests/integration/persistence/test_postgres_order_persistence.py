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
    JournalAppend,
    JournalCommitFailed,
    OrderSnapshot,
    PublishFailure,
    order_state_payload,
    snapshot_checksum,
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


def test_postgres_register_rejects_malformed_initial_commit(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    valid = registered_commit(registry)
    wrong_journal = JournalAppend(
        valid.journal.journal_id,
        valid.journal.order_id,
        1,
        "ORDER_TRANSITION_APPLIED",
        valid.journal.payload,
        valid.journal.occurred_at,
        valid.journal.correlation_id,
        valid.journal.causation_id,
    )

    with pytest.raises(JournalCommitFailed, match="ORDER_REGISTERED"):
        postgres_store.register(
            type(valid)(valid.persisted_order, wrong_journal, valid.outbox_messages),
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


def test_postgres_rebuilds_corrupted_projection_from_journal(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    committed = transition_commit(registry, registered.persisted_order)
    postgres_store.save(committed, expected_version=1, deadline_monotonic_ns=DEADLINE)
    asyncio.run(
        _execute(
            """
            UPDATE orders
            SET state = 'REGISTERED',
                cumulative_quantity = 0,
                aggregate_version = 1,
                state_payload = jsonb_set(state_payload, '{aggregate_version}', '1'::jsonb)
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
        )
    )

    loaded = postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    rebuilt = postgres_store.rebuild_projection_from_journal(
        ORDER_ID,
        expected_journal_head_checksum=asyncio.run(_journal_head_checksum(ORDER_ID.value)),
        deadline_monotonic_ns=DEADLINE,
    )
    stored = postgres_store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE)

    assert loaded.persisted_order.order.version == 2
    assert rebuilt.persisted_order.order.version == 2
    assert stored is not None
    assert stored.order.version == 2


def test_postgres_snapshot_lookup_accepts_valid_older_snapshot_with_later_journal(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    payload = order_state_payload(registered.persisted_order)
    postgres_store.write(
        OrderSnapshot(
            ORDER_ID,
            ORDER_ID,
            1,
            1,
            payload,
            asyncio.run(_journal_head_checksum(ORDER_ID.value)),
            snapshot_checksum(payload),
            registered.persisted_order.registration.registered_at,
        ),
        deadline_monotonic_ns=DEADLINE,
    )
    postgres_store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )

    lookup = postgres_store.latest_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)

    assert lookup.status == "VALID"
    assert lookup.snapshot is not None
    assert lookup.snapshot.aggregate_version == 1


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


def test_postgres_retryable_failure_waits_until_backoff_available_at(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    postgres_store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 3, 50, 500, "2", "0")
    claimed = postgres_store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)[0]

    assert postgres_store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "temporary backbone outage", retryable=True),
        deadline_monotonic_ns=DEADLINE,
    ).applied
    assert postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    asyncio.run(_make_outbox_available(claimed.message_id))
    assert len(postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)) == 1


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


async def _execute(sql: str, *args: object) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(sql, *args)
    finally:
        await connection.close()


async def _journal_head_checksum(order_id: str) -> str:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            """
            SELECT entry_checksum
            FROM order_journal
            WHERE order_id = $1::uuid
            ORDER BY aggregate_version DESC
            LIMIT 1
            """,
            order_id,
        )
        assert row is not None
        return str(row["entry_checksum"])
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


async def _make_outbox_available(message_id: str) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            """
            UPDATE outbox_messages
            SET available_at = transaction_timestamp() - interval '1 millisecond'
            WHERE message_id = $1
            """,
            message_id,
        )
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
