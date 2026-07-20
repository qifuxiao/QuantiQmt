from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.messaging.outbox import CriticalOutboxLagPolicy
from quantiqmt.order.application.persistence import (
    ClaimPolicy,
    IdempotencyConflict,
    JournalAppend,
    OrderCommit,
    OrderJournalCorrupted,
    OrderRegistration,
    OrderSnapshot,
    PersistedOrder,
    PublishFailure,
    build_order_registered_envelope,
    build_order_status_changed_envelope,
    order_state_payload,
    registration_fingerprint,
    snapshot_checksum,
)
from quantiqmt.order.domain import (
    GuardEvidence,
    Order,
    OrderEvent,
    OrderState,
    OrderVersionConflict,
)
from quantiqmt.order.infrastructure.memory import InMemoryOrderPersistence, OutboxStatus
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity

ORDER_ID = Identifier("550e8400-e29b-41d4-a716-446655440000")
INTENT_ID = Identifier("550e8400-e29b-41d4-a716-446655440001")
JOURNAL_ID_1 = Identifier("550e8400-e29b-41d4-a716-446655440002")
JOURNAL_ID_2 = Identifier("550e8400-e29b-41d4-a716-446655440003")
NOW = datetime(2026, 7, 10, 1, 2, 3, tzinfo=UTC)
DEADLINE = 2**63


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.project_default()


def registration(*, client_order_id: str = "client-1") -> OrderRegistration:
    return OrderRegistration(
        order_id=ORDER_ID,
        intent_id=INTENT_ID,
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


def registered_commit(registry: SchemaRegistry, *, fingerprint: str | None = None) -> OrderCommit:
    reg = registration()
    persisted = PersistedOrder(
        reg,
        Order(ORDER_ID, Quantity(100)),
        fingerprint
        or registration_fingerprint({"intent_id": INTENT_ID.value, "limit_price": "10.01"}),
    )
    journal = JournalAppend(
        journal_id=JOURNAL_ID_1,
        order_id=ORDER_ID,
        aggregate_version=1,
        event_type="ORDER_REGISTERED",
        payload={
            "order_id": ORDER_ID.value,
            "aggregate_version": 1,
            "registration": {"intent_id": INTENT_ID.value},
            "post_state": order_state_payload(persisted),
        },
        occurred_at=NOW,
        correlation_id="correlation-0001",
    )
    return OrderCommit(
        persisted,
        journal,
        (build_order_registered_envelope(persisted, journal, registry),),
    )


def transition_commit(registry: SchemaRegistry, persisted: PersistedOrder) -> OrderCommit:
    order = Order(
        persisted.order.order_id,
        persisted.order.quantity,
        state=persisted.order.state,
        cumulative_quantity=persisted.order.cumulative_quantity,
        version=persisted.order.version,
        processed_facts=persisted.order.processed_facts,
        fact_conflicts=persisted.order.fact_conflicts,
        broker_sequences=persisted.order.broker_sequences,
    )
    result = order.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    assert result is not None
    updated = PersistedOrder(persisted.registration, order, persisted.registration_fingerprint)
    journal = JournalAppend(
        journal_id=JOURNAL_ID_2,
        order_id=ORDER_ID,
        aggregate_version=2,
        event_type="ORDER_TRANSITION_APPLIED",
        payload={
            "order_id": ORDER_ID.value,
            "aggregate_version": 2,
            "previous_state": result.previous.value,
            "current_state": result.current.value,
            "order_event": result.event.value,
            "order_action": result.action.value,
            "accepted_fact_delta": [],
            "conflict_delta": [],
            "post_state": order_state_payload(updated),
        },
        occurred_at=NOW + timedelta(seconds=1),
        correlation_id="correlation-0001",
        causation_id="causation-000001",
    )
    return OrderCommit(
        updated,
        journal,
        (
            build_order_status_changed_envelope(
                order_id=ORDER_ID.value,
                aggregate_version=2,
                from_status=result.previous,
                to_status=result.current,
                reason_code=result.event,
                cumulative_quantity=order.cumulative_quantity.value,
                total_quantity=order.quantity.value,
                journal=journal,
                registry=registry,
            ),
        ),
    )


def test_register_is_atomic_and_intent_replay_is_idempotent(registry: SchemaRegistry) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    commit = registered_commit(registry)
    outcome = store.register(commit, deadline_monotonic_ns=DEADLINE)
    assert outcome.created is True
    assert len(store.journal_records) == 1
    assert len(store.outbox_records) == 1

    replay = store.register(commit, deadline_monotonic_ns=DEADLINE)
    assert replay.created is False
    assert replay.persisted_order == outcome.persisted_order
    assert len(store.journal_records) == 1
    assert len(store.outbox_records) == 1


def test_register_same_intent_different_fingerprint_rejects_without_partial_write(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    with pytest.raises(IdempotencyConflict, match="QQ-STORAGE-7001"):
        store.register(
            registered_commit(registry, fingerprint="a" * 64),
            deadline_monotonic_ns=DEADLINE,
        )
    assert len(store.journal_records) == 1
    assert len(store.outbox_records) == 1


def test_save_uses_compare_and_swap_and_preserves_atomicity(registry: SchemaRegistry) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    registered = store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    commit = transition_commit(registry, registered.persisted_order)
    with pytest.raises(OrderVersionConflict, match="QQ-COMMON-1003"):
        store.save(commit, expected_version=99, deadline_monotonic_ns=DEADLINE)
    stored = store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    assert stored is not None
    assert stored.order.version == 1
    assert len(store.journal_records) == 1

    saved = store.save(commit, expected_version=1, deadline_monotonic_ns=DEADLINE)
    assert saved.order.state is OrderState.RISK_PENDING
    assert len(store.journal_records) == 2
    assert len(store.outbox_records) == 2


def test_recovery_paging_and_journal_checksum_chain(registry: SchemaRegistry) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    page = store.list_recovery_order_ids(
        scope="ALL", page_size=1, page_token=None, deadline_monotonic_ns=DEADLINE
    )
    assert page.order_ids == (ORDER_ID,)
    recovered = store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    assert recovered.source == "FULL_JOURNAL"

    head = store.journal_records[-1].entry_checksum
    rebuilt = store.rebuild_projection_from_journal(
        ORDER_ID, expected_journal_head_checksum=head, deadline_monotonic_ns=DEADLINE
    )
    assert rebuilt.persisted_order.registration.intent_id == INTENT_ID


def test_recovery_rebuilds_projection_from_journal_post_state(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    registered = store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    committed = transition_commit(registry, registered.persisted_order)
    store.save(committed, expected_version=1, deadline_monotonic_ns=DEADLINE)
    corrupted_projection = PersistedOrder(
        committed.persisted_order.registration,
        Order(ORDER_ID, Quantity(100)),
        "f" * 64,
    )
    store._orders[ORDER_ID.value] = corrupted_projection

    loaded = store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    rebuilt = store.rebuild_projection_from_journal(
        ORDER_ID,
        expected_journal_head_checksum=store.journal_records[-1].entry_checksum,
        deadline_monotonic_ns=DEADLINE,
    )

    assert loaded.persisted_order.order.version == 2
    assert loaded.persisted_order.order.state is OrderState.RISK_PENDING
    assert loaded.persisted_order.registration_fingerprint == (
        committed.persisted_order.registration_fingerprint
    )
    assert rebuilt.persisted_order.order.version == 2
    assert store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE).order.version == 2  # type: ignore[union-attr]

    del store._orders[ORDER_ID.value]
    journal_only_page = store.list_recovery_order_ids(
        scope="ALL", page_size=10, page_token=None, deadline_monotonic_ns=DEADLINE
    )
    journal_only_active_page = store.list_recovery_order_ids(
        scope="ACTIVE_OR_UNKNOWN",
        page_size=10,
        page_token=None,
        deadline_monotonic_ns=DEADLINE,
    )
    assert ORDER_ID in journal_only_page.order_ids
    assert ORDER_ID in journal_only_active_page.order_ids

    missing_rebuilt = store.rebuild_projection_from_journal(
        ORDER_ID,
        expected_journal_head_checksum=store.journal_records[-1].entry_checksum,
        deadline_monotonic_ns=DEADLINE,
    )
    assert missing_rebuilt.persisted_order.order.version == 2
    assert store.get(ORDER_ID, deadline_monotonic_ns=DEADLINE) is not None


def test_empty_journal_fails_recovery_closed_with_recovery_error(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    store._journal[ORDER_ID.value] = []

    with pytest.raises(OrderJournalCorrupted, match="QQ-RECOVERY-8002"):
        store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    with pytest.raises(OrderJournalCorrupted, match="QQ-RECOVERY-8002"):
        store.rebuild_projection_from_journal(
            ORDER_ID, expected_journal_head_checksum=None, deadline_monotonic_ns=DEADLINE
        )


def test_snapshot_lookup_accepts_valid_older_snapshot_with_later_journal(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    registered = store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    payload = order_state_payload(registered.persisted_order)
    draft = OrderSnapshot(
        Identifier("550e8400-e29b-41d4-a716-446655440010"),
        ORDER_ID,
        1,
        1,
        payload,
        store.journal_records[-1].entry_checksum,
        "0" * 64,
        NOW,
    )
    store.write(
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
    store.save(
        transition_commit(registry, registered.persisted_order),
        expected_version=1,
        deadline_monotonic_ns=DEADLINE,
    )

    lookup = store.latest_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    loaded = store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)

    assert lookup.status == "VALID"
    assert lookup.snapshot is not None
    assert lookup.snapshot.aggregate_version == 1
    assert loaded.source == "SNAPSHOT_PLUS_JOURNAL"
    assert loaded.persisted_order.order.version == 2


def test_invalid_snapshot_is_discarded_and_recovery_falls_back_to_full_journal(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    registered = store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    corrupted_payload = {
        **order_state_payload(registered.persisted_order),
        "aggregate_version": 2,
    }
    draft = OrderSnapshot(
        Identifier("550e8400-e29b-41d4-a716-446655440020"),
        ORDER_ID,
        1,
        1,
        corrupted_payload,
        store.journal_records[-1].entry_checksum,
        "0" * 64,
        NOW,
    )
    store.write(
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

    lookup = store.latest_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)
    loaded = store.load_for_recovery(ORDER_ID, deadline_monotonic_ns=DEADLINE)

    assert lookup.status == "INVALID_DISCARDED"
    assert lookup.diagnostic_code == "QQ-STORAGE-7003"
    assert loaded.source == "FULL_JOURNAL"
    assert loaded.snapshot_diagnostic == "QQ-STORAGE-7003"
    assert loaded.persisted_order.order.version == 1


def test_outbox_claim_publish_reclaim_and_expired_token_fencing(registry: SchemaRegistry) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 3, 10, 100, "2", "0")

    first = store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)
    assert len(first) == 1
    assert first[0].attempt_count == 1

    store.advance(timedelta(milliseconds=1001))
    assert (
        store.mark_published(
            first[0].message_id, first[0].claim_token, deadline_monotonic_ns=DEADLINE
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        store.renew(
            first[0].message_id,
            first[0].claim_token,
            policy,
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        store.release_failed(
            first[0].message_id,
            first[0].claim_token,
            PublishFailure("PUBLISH_FAILED", "old worker", retryable=True),
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    second = store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)
    assert second[0].message_id == first[0].message_id
    assert second[0].claim_token != first[0].claim_token
    assert second[0].attempt_count == 2
    assert (
        store.mark_published(
            first[0].message_id, first[0].claim_token, deadline_monotonic_ns=DEADLINE
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        store.renew(
            first[0].message_id,
            first[0].claim_token,
            policy,
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        store.release_failed(
            first[0].message_id,
            first[0].claim_token,
            PublishFailure("PUBLISH_FAILED", "reclaimed by other worker", retryable=True),
            deadline_monotonic_ns=DEADLINE,
        ).code
        == "QQ-STORAGE-7004"
    )
    assert (
        store.mark_published(
            second[0].message_id, second[0].claim_token, deadline_monotonic_ns=DEADLINE
        ).applied
        is True
    )
    assert store.outbox_records[0].status is OutboxStatus.PUBLISHED


def test_release_failed_dead_letters_non_retryable_failures(registry: SchemaRegistry) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    claimed = store.claim(
        "worker-a", ClaimPolicy(10, 1000, 3, 10, 100, "2", "0"), deadline_monotonic_ns=DEADLINE
    )[0]
    result = store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "broker unavailable", retryable=False),
        deadline_monotonic_ns=DEADLINE,
    )
    assert result.applied is True
    assert store.outbox_records[0].status is OutboxStatus.DEAD_LETTER
    action = store.evaluate_outbox_safety(
        CriticalOutboxLagPolicy(critical_lag_ms=10_000, critical_dead_letter_count=0),
        deadline_monotonic_ns=DEADLINE,
    )
    assert action.critical is True
    assert action.reject_new_risk is True
    assert action.keep_recovery_barrier_closed is True
    assert action.emit_health_alert is True
    assert action.reason_code == "ORDER_OUTBOX_DEAD_LETTER_CRITICAL"


def test_retryable_failure_reaches_max_attempts_before_next_claim(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 1, 10, 100, "2", "0")
    claimed = store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)[0]

    result = store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "temporary backbone outage", retryable=True),
        deadline_monotonic_ns=DEADLINE,
    )

    assert result.applied is True
    assert store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    assert store.outbox_records[0].status is OutboxStatus.DEAD_LETTER
    assert store.outbox_records[0].last_error_code == "MAX_ATTEMPTS_REACHED"


def test_retryable_failure_waits_until_backoff_available_at(
    registry: SchemaRegistry,
) -> None:
    store = InMemoryOrderPersistence(now=NOW)
    store.register(registered_commit(registry), deadline_monotonic_ns=DEADLINE)
    policy = ClaimPolicy(10, 1000, 3, 50, 500, "2", "0.5")
    claimed = store.claim("worker-a", policy, deadline_monotonic_ns=DEADLINE)[0]

    assert store.release_failed(
        claimed.message_id,
        claimed.claim_token,
        PublishFailure("PUBLISH_FAILED", "temporary backbone outage", retryable=True),
        deadline_monotonic_ns=DEADLINE,
    ).applied

    assert store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    store.advance(timedelta(milliseconds=50))
    assert store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE) == ()
    store.advance(timedelta(milliseconds=25))
    assert len(store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)) == 1
