from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.order.application.persistence import (
    ClaimPolicy,
    IdempotencyConflict,
    JournalAppend,
    OrderCommit,
    OrderRegistration,
    PersistedOrder,
    PublishFailure,
    build_order_registered_envelope,
    build_order_status_changed_envelope,
    order_state_payload,
    registration_fingerprint,
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
DEADLINE = 1


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
    second = store.claim("worker-b", policy, deadline_monotonic_ns=DEADLINE)
    assert second[0].message_id == first[0].message_id
    assert second[0].claim_token != first[0].claim_token
    assert second[0].attempt_count == 2
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
