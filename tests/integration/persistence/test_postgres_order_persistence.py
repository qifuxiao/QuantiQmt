from __future__ import annotations

import asyncio
import importlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pytest
from tests.contract.persistence.test_order_persistence_contract import (
    DEADLINE,
    INTENT_ID,
    NOW,
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
    OrderCommit,
    OrderJournalCorrupted,
    OrderRegistration,
    OrderSnapshot,
    PersistedOrder,
    PublishFailure,
    UniqueIdentifierCollision,
    build_order_registered_envelope,
    order_state_payload,
    registration_fingerprint,
    snapshot_checksum,
)
from quantiqmt.order.domain import Order, OrderState, OrderVersionConflict
from quantiqmt.order.infrastructure.postgres import PostgresOrderPersistence
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity


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


def test_postgres_concurrent_register_replay_is_idempotent(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    commit = registered_commit(registry)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                PostgresOrderPersistence(os.environ["QUANTIQMT_POSTGRES_DSN"]).register,
                commit,
                deadline_monotonic_ns=DEADLINE,
            )
            for _ in range(2)
        ]
        outcomes = [future.result() for future in as_completed(futures)]

    assert sorted(outcome.created for outcome in outcomes) == [False, True]
    assert asyncio.run(_table_counts()) == (1, 1, 1)


def test_postgres_concurrent_register_unique_competition_fails_closed(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    first = registered_commit(registry)
    competing = _registered_commit_variant(
        registry,
        order_id=ORDER_ID,
        intent_id=Identifier("550e8400-e29b-41d4-a716-446655440101"),
        journal_id=Identifier("550e8400-e29b-41d4-a716-446655440102"),
        client_order_id="client-unique-competition",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                PostgresOrderPersistence(os.environ["QUANTIQMT_POSTGRES_DSN"]).register,
                commit,
                deadline_monotonic_ns=DEADLINE,
            )
            for commit in (first, competing)
        ]
        results: list[object] = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except UniqueIdentifierCollision as exc:
                results.append(exc)

    assert sum(isinstance(result, UniqueIdentifierCollision) for result in results) == 1
    assert asyncio.run(_table_counts()) == (1, 1, 1)

    stored = postgres_store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    assert stored is not None
    client_competing = _registered_commit_variant(
        registry,
        order_id=Identifier("550e8400-e29b-41d4-a716-446655440103"),
        intent_id=Identifier("550e8400-e29b-41d4-a716-446655440104"),
        journal_id=Identifier("550e8400-e29b-41d4-a716-446655440105"),
        client_order_id=stored.registration.client_order_id,
    )
    with pytest.raises(UniqueIdentifierCollision, match="QQ-STORAGE-7006"):
        postgres_store.register(client_competing, deadline_monotonic_ns=DEADLINE)
    assert asyncio.run(_table_counts()) == (1, 1, 1)


def test_postgres_concurrent_save_cas_allows_single_winner(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    commit = transition_commit(registry, registered.persisted_order)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                PostgresOrderPersistence(os.environ["QUANTIQMT_POSTGRES_DSN"]).save,
                commit,
                expected_version=1,
                deadline_monotonic_ns=DEADLINE,
            )
            for _ in range(2)
        ]
        results: list[object] = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except OrderVersionConflict as exc:
                results.append(exc)

    assert sum(isinstance(result, OrderVersionConflict) for result in results) == 1
    assert asyncio.run(_table_counts()) == (1, 2, 2)


def test_postgres_register_rolls_back_order_and_journal_when_outbox_insert_fails(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    valid = registered_commit(registry)
    duplicate_outbox = OrderCommit(
        valid.persisted_order,
        valid.journal,
        (valid.outbox_messages[0], valid.outbox_messages[0]),
    )

    with pytest.raises(UniqueIdentifierCollision, match="QQ-STORAGE-7006"):
        postgres_store.register(duplicate_outbox, deadline_monotonic_ns=DEADLINE)

    assert asyncio.run(_table_counts()) == (0, 0, 0)


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
            SET registration_fingerprint = $2,
                state = 'REGISTERED',
                cumulative_quantity = 0,
                aggregate_version = 1,
                state_payload = jsonb_set(state_payload, '{aggregate_version}', '1'::jsonb)
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
            "f" * 64,
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
    assert loaded.persisted_order.registration_fingerprint == (
        committed.persisted_order.registration_fingerprint
    )
    assert rebuilt.persisted_order.order.version == 2
    assert stored is not None
    assert stored.order.version == 2

    asyncio.run(_delete_order_projection_bypassing_fk(ORDER_ID.value))
    journal_only_page = postgres_store.list_recovery_order_ids(
        scope="ALL", page_size=10, page_token=None, deadline_monotonic_ns=DEADLINE
    )
    journal_only_active_page = postgres_store.list_recovery_order_ids(
        scope="ACTIVE_OR_UNKNOWN",
        page_size=10,
        page_token=None,
        deadline_monotonic_ns=DEADLINE,
    )
    assert ORDER_ID in journal_only_page.order_ids
    assert ORDER_ID in journal_only_active_page.order_ids

    recovered_order_id = journal_only_page.order_ids[0]
    missing_rebuilt = postgres_store.rebuild_projection_from_journal(
        recovered_order_id,
        expected_journal_head_checksum=asyncio.run(_journal_head_checksum(ORDER_ID.value)),
        deadline_monotonic_ns=DEADLINE,
    )
    assert missing_rebuilt.persisted_order.order.version == 2
    assert postgres_store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE) is not None


def test_postgres_snapshot_lookup_accepts_valid_older_snapshot_with_later_journal(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    payload = order_state_payload(registered.persisted_order)
    draft = OrderSnapshot(
        ORDER_ID,
        ORDER_ID,
        1,
        1,
        payload,
        asyncio.run(_journal_head_checksum(ORDER_ID.value)),
        "0" * 64,
        registered.persisted_order.registration.registered_at,
    )
    postgres_store.write(
        OrderSnapshot(
            draft.snapshot_id,
            draft.order_id,
            draft.aggregate_version,
            draft.schema_version,
            draft.state_payload,
            draft.journal_head_checksum,
            snapshot_checksum(draft),
            draft.created_at,
        ),
        deadline_monotonic_ns=DEADLINE,
    )
    postgres_store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )

    lookup = postgres_store.latest_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    loaded = postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)

    assert lookup.status == "VALID"
    assert lookup.snapshot is not None
    assert lookup.snapshot.aggregate_version == 1
    assert loaded.source == "SNAPSHOT_PLUS_JOURNAL"
    assert loaded.persisted_order.order.version == 2


@pytest.mark.parametrize("mode", ["checksum", "head", "schema", "state_version"])
def test_postgres_invalid_snapshot_fails_closed_and_load_falls_back_to_full_journal(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry, mode: str
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    draft = OrderSnapshot(
        Identifier("550e8400-e29b-41d4-a716-446655440030"),
        ORDER_ID,
        1,
        1,
        order_state_payload(registered.persisted_order),
        asyncio.run(_journal_head_checksum(ORDER_ID.value)),
        "0" * 64,
        registered.persisted_order.registration.registered_at,
    )
    postgres_store.write(
        OrderSnapshot(
            draft.snapshot_id,
            draft.order_id,
            draft.aggregate_version,
            draft.schema_version,
            draft.state_payload,
            draft.journal_head_checksum,
            snapshot_checksum(draft),
            draft.created_at,
        ),
        deadline_monotonic_ns=DEADLINE,
    )
    postgres_store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )
    state_version_checksum = None
    if mode == "state_version":
        bad_payload = {
            **order_state_payload(registered.persisted_order),
            "aggregate_version": 2,
        }
        bad_snapshot = OrderSnapshot(
            draft.snapshot_id,
            draft.order_id,
            draft.aggregate_version,
            draft.schema_version,
            bad_payload,
            draft.journal_head_checksum,
            "0" * 64,
            draft.created_at,
        )
        state_version_checksum = snapshot_checksum(bad_snapshot)
    constraint_to_restore = asyncio.run(_corrupt_snapshot(mode, state_version_checksum))
    try:
        lookup = postgres_store.latest_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
        loaded = postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)

        assert lookup.status == "INVALID_DISCARDED"
        assert lookup.diagnostic_code == "QQ-STORAGE-7003"
        assert loaded.source == "FULL_JOURNAL"
        assert loaded.snapshot_diagnostic == "QQ-STORAGE-7003"
        assert loaded.persisted_order.order.version == 2
    finally:
        if constraint_to_restore is not None:
            asyncio.run(_restore_snapshot_constraint(constraint_to_restore))


def test_postgres_journal_gap_or_checksum_corruption_fails_recovery_closed(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    postgres_store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )

    asyncio.run(
        _mutate_journal_bypassing_append_only(
            """
            UPDATE order_journal
            SET entry_checksum = $2
            WHERE order_id = $1::uuid AND aggregate_version = 2
            """,
            ORDER_ID.value,
            "b" * 64,
        )
    )
    with pytest.raises(OrderJournalCorrupted, match="QQ-RECOVERY-8002"):
        postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)


def test_postgres_journal_version_gap_fails_recovery_closed(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    registered = postgres_store.register(
        registered_commit(registry), deadline_monotonic_ns=DEADLINE
    )
    postgres_store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )

    asyncio.run(
        _mutate_journal_bypassing_append_only(
            """
            DELETE FROM order_journal
            WHERE order_id = $1::uuid AND aggregate_version = 1
            """,
            ORDER_ID.value,
        )
    )
    with pytest.raises(OrderJournalCorrupted, match="QQ-RECOVERY-8002"):
        postgres_store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)


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
    assert (
        postgres_store.renew(
            first[0].message_id,
            first[0].claim_token,
            policy,
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        postgres_store.release_failed(
            first[0].message_id,
            first[0].claim_token,
            PublishFailure("PUBLISH_FAILED", "old worker", retryable=True),
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )

    second = postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)
    assert second[0].message_id == first[0].message_id
    assert second[0].claim_token != first[0].claim_token
    assert second[0].attempt_count == 2
    assert (
        postgres_store.mark_published(
            first[0].message_id, first[0].claim_token, deadline_monotonic_ns=DEADLINE
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        postgres_store.renew(
            first[0].message_id,
            first[0].claim_token,
            policy,
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        postgres_store.release_failed(
            first[0].message_id,
            first[0].claim_token,
            PublishFailure("PUBLISH_FAILED", "reclaimed by other worker", retryable=True),
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
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
    policy = ClaimPolicy(10, 1000, 3, 50, 500, "2", "0.5")
    claimed = postgres_store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)[0]

    assert postgres_store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "temporary backbone outage", retryable=True),
        deadline_monotonic_ns=DEADLINE,
    ).applied
    assert postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    asyncio.run(_make_outbox_available(claimed.message_id, milliseconds_before_now=-5000))
    assert postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    asyncio.run(_make_outbox_available(claimed.message_id))
    assert len(postgres_store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)) == 1


def test_postgres_order_journal_rejects_update_and_delete(
    postgres_store: PostgresOrderPersistence, registry: SchemaRegistry
) -> None:
    postgres_store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)

    with pytest.raises(Exception, match="order_journal is append-only"):
        asyncio.run(
            _execute(
                """
                UPDATE order_journal
                SET payload = payload
                WHERE order_id = $1::uuid
                """,
                ORDER_ID.value,
            )
        )
    with pytest.raises(Exception, match="order_journal is append-only"):
        asyncio.run(
            _execute(
                """
                DELETE FROM order_journal
                WHERE order_id = $1::uuid
                """,
                ORDER_ID.value,
            )
        )


def _registered_commit_variant(
    registry: SchemaRegistry,
    *,
    order_id: Identifier,
    intent_id: Identifier,
    journal_id: Identifier,
    client_order_id: str,
) -> OrderCommit:
    registration = OrderRegistration(
        order_id=order_id,
        intent_id=intent_id,
        client_order_id=client_order_id,
        account_id="account-1",
        instrument_id=InstrumentId("600000.XSHG"),
        side="BUY",
        position_effect="AUTO",
        order_type="LIMIT",
        quantity=Quantity(100),
        limit_price=Price("10.01"),
        time_in_force="DAY",
        owner_strategy_id="strategy-1",
        owner_strategy_version="v1",
        registered_at=NOW,
    )
    persisted = PersistedOrder(
        registration,
        Order(order_id, Quantity(100)),
        registration_fingerprint(
            {"intent_id": intent_id.value, "client_order_id": client_order_id}
        ),
    )
    journal = JournalAppend(
        journal_id=journal_id,
        order_id=order_id,
        aggregate_version=1,
        event_type="ORDER_REGISTERED",
        payload={
            "order_id": order_id.value,
            "aggregate_version": 1,
            "registration": {"intent_id": intent_id.value},
            "post_state": order_state_payload(persisted),
        },
        occurred_at=NOW,
        correlation_id="correlation-0101",
    )
    return OrderCommit(
        persisted,
        journal,
        (build_order_registered_envelope(persisted, journal, registry),),
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


async def _table_counts() -> tuple[int, int, int]:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        orders = await connection.fetchval("SELECT count(*) FROM orders")
        journal = await connection.fetchval("SELECT count(*) FROM order_journal")
        outbox = await connection.fetchval("SELECT count(*) FROM outbox_messages")
        return int(orders), int(journal), int(outbox)
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


async def _corrupt_snapshot(mode: str, state_version_checksum: str | None = None) -> str | None:
    if mode == "checksum":
        await _execute(
            """
            UPDATE order_snapshots
            SET snapshot_checksum = $2
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
            "b" * 64,
        )
        return None
    if mode == "head":
        await _execute(
            """
            UPDATE order_snapshots
            SET journal_head_checksum = $2
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
            "c" * 64,
        )
        return None
    if mode == "schema":
        await _execute(
            "ALTER TABLE order_snapshots DROP CONSTRAINT order_snapshots_schema_version_v1"
        )
        await _execute(
            """
            UPDATE order_snapshots
            SET schema_version = 2
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
        )
        return "schema"
    if mode == "state_version":
        assert state_version_checksum is not None
        await _execute(
            """
            ALTER TABLE order_snapshots
            DROP CONSTRAINT order_snapshots_state_payload_version_matches
            """
        )
        await _execute(
            """
            UPDATE order_snapshots
            SET state_payload = jsonb_set(state_payload, '{aggregate_version}', '2'::jsonb),
                snapshot_checksum = $2
            WHERE order_id = $1::uuid
            """,
            ORDER_ID.value,
            state_version_checksum,
        )
        return "state_version"
    raise ValueError(f"unsupported snapshot corruption mode {mode}")


async def _restore_snapshot_constraint(kind: str) -> None:
    await _execute("DELETE FROM order_snapshots")
    if kind == "schema":
        await _execute(
            """
            ALTER TABLE order_snapshots
            ADD CONSTRAINT order_snapshots_schema_version_v1 CHECK (schema_version = 1)
            """
        )
        return
    if kind == "state_version":
        await _execute(
            """
            ALTER TABLE order_snapshots
            ADD CONSTRAINT order_snapshots_state_payload_version_matches
            CHECK ((state_payload->>'aggregate_version')::bigint = aggregate_version)
            """
        )
        return
    raise ValueError(f"unsupported snapshot constraint kind {kind}")


async def _mutate_journal_bypassing_append_only(sql: str, *args: object) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("SET session_replication_role = replica")
        await connection.execute(sql, *args)
    finally:
        await connection.execute("SET session_replication_role = origin")
        await connection.close()


async def _delete_order_projection_bypassing_fk(order_id: str) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("SET session_replication_role = replica")
        await connection.execute("DELETE FROM orders WHERE order_id = $1::uuid", order_id)
    finally:
        await connection.execute("SET session_replication_role = origin")
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


async def _make_outbox_available(message_id: str, *, milliseconds_before_now: int = 1) -> None:
    dsn = os.environ["QUANTIQMT_POSTGRES_DSN"]
    asyncpg = _asyncpg()
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            """
            UPDATE outbox_messages
            SET available_at = transaction_timestamp()
                - ($2::integer::text || ' milliseconds')::interval
            WHERE message_id = $1
            """,
            message_id,
            milliseconds_before_now,
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
