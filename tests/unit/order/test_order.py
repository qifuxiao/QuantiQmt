from pathlib import Path

import pytest
import yaml

from quantiqmt.order.domain import (
    ExternalFact,
    FactIdentity,
    GuardEvidence,
    InvalidOrderTransition,
    Order,
    OrderAction,
    OrderEvent,
    OrderState,
    OrderVersionConflict,
    RiskSnapshotUnavailable,
    transition_catalog,
)
from quantiqmt.shared import Identifier, Quantity


def order(quantity: int = 100, **kwargs: object) -> Order:
    return Order(Identifier("550e8400-e29b-41d4-a716-446655440000"), Quantity(quantity), **kwargs)


def evidence(name: str = "true") -> GuardEvidence:
    return GuardEvidence.of(name)


def fact(key: str, *, fingerprint: str | None = None, trade: int | None = None) -> ExternalFact:
    return ExternalFact(
        FactIdentity("broker-trade" if trade is not None else "broker-report", key),
        fingerprint or f"sha256:{key}",
        Quantity(trade) if trade is not None else None,
    )


def submitted(quantity: int = 100) -> Order:
    aggregate = order(quantity)
    aggregate.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    aggregate.transition(OrderEvent.RISK_PASSED, GuardEvidence.expected_version(2))
    aggregate.transition(OrderEvent.DISPATCH, GuardEvidence.trading_authority())
    aggregate.transition(
        OrderEvent.BROKER_ACCEPTED,
        evidence("report_uniquely_correlated"),
        fact=fact("accepted"),
    )
    return aggregate


def snapshot(aggregate: Order) -> tuple[object, ...]:
    return (
        aggregate.state,
        aggregate.cumulative_quantity,
        aggregate.version,
        dict(aggregate.processed_facts),
        dict(aggregate.broker_sequences),
    )


def test_transition_catalog_exactly_matches_normative_yaml() -> None:
    document = yaml.safe_load(Path("spec/state-machines/order.yaml").read_text(encoding="utf-8"))
    expected = {
        (OrderState(item["from"]), OrderEvent(item["event"]), OrderState(item["to"]))
        for item in document["machine"]["transitions"]
    }
    assert transition_catalog() == expected


def test_submit_unknown_only_schedules_reconciliation() -> None:
    aggregate = order()
    aggregate.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    aggregate.transition(OrderEvent.RISK_PASSED, GuardEvidence.expected_version(2))
    aggregate.transition(OrderEvent.DISPATCH, GuardEvidence.trading_authority())
    result = aggregate.transition(OrderEvent.OUTCOME_UNKNOWN, evidence())
    assert result is not None
    assert result.current is OrderState.SUBMIT_UNKNOWN
    assert result.action is OrderAction.SCHEDULE_RECONCILIATION


def test_each_named_guard_requires_explicit_evidence_and_is_atomic() -> None:
    aggregate = order()
    before = snapshot(aggregate)
    with pytest.raises(RiskSnapshotUnavailable, match="QQ-RISK-4002"):
        aggregate.transition(OrderEvent.START_RISK, evidence())
    assert snapshot(aggregate) == before

    aggregate.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    before = snapshot(aggregate)
    with pytest.raises(OrderVersionConflict, match="QQ-COMMON-1003"):
        aggregate.transition(OrderEvent.RISK_PASSED, evidence())
    assert snapshot(aggregate) == before


def test_invalid_transition_and_missing_generic_guard_use_canonical_error() -> None:
    aggregate = order()
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(OrderEvent.DISPATCH, evidence("leader_and_trading_allowed"))
    aggregate.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    aggregate.transition(OrderEvent.RISK_PASSED, GuardEvidence.expected_version(2))
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(OrderEvent.DISPATCH, evidence())


def test_non_trade_event_cannot_mutate_cumulative_quantity() -> None:
    aggregate = order()
    before = snapshot(aggregate)
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(
            OrderEvent.START_RISK,
            evidence("snapshots_available"),
            fact=fact("not-a-trade", trade=10),
        )
    assert snapshot(aggregate) == before


def test_external_fact_identity_is_mandatory() -> None:
    aggregate = submitted()
    with pytest.raises(InvalidOrderTransition, match="requires authoritative fact identity"):
        aggregate.transition(
            OrderEvent.PARTIAL_TRADE,
            evidence("cum_between_zero_and_quantity"),
        )


def test_multiple_trades_derive_cumulative_and_duplicate_is_no_op() -> None:
    aggregate = submitted()
    first = fact("trade-1", trade=30)
    aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_between_zero_and_quantity"),
        fact=first,
    )
    version = aggregate.version
    assert (
        aggregate.transition(
            OrderEvent.PARTIAL_TRADE,
            evidence("cum_strictly_increases_below_quantity"),
            fact=first,
        )
        is None
    )
    assert aggregate.version == version
    aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_strictly_increases_below_quantity"),
        fact=fact("trade-2", trade=20),
    )
    aggregate.transition(
        OrderEvent.FULL_TRADE,
        evidence("cum_equals_quantity"),
        fact=fact("trade-3", trade=50),
    )
    assert aggregate.cumulative_quantity == Quantity(100)
    assert aggregate.state is OrderState.FILLED


def test_same_identity_with_different_content_suspends_and_opens_case() -> None:
    aggregate = submitted()
    original = fact("trade-1", fingerprint="sha256:a", trade=10)
    aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_between_zero_and_quantity"),
        fact=original,
    )
    result = aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_strictly_increases_below_quantity"),
        fact=fact("trade-1", fingerprint="sha256:b", trade=10),
    )
    assert result is not None
    assert result.current is OrderState.SUSPENDED
    assert result.action is OrderAction.OPEN_RECONCILIATION_CASE
    assert aggregate.cumulative_quantity == Quantity(10)


def test_cancel_pending_and_unknown_continue_recording_trades() -> None:
    aggregate = submitted()
    aggregate.transition(OrderEvent.REQUEST_CANCEL, evidence("order_not_terminal"))
    aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_strictly_increases_below_quantity"),
        fact=fact("trade-1", trade=20),
    )
    assert aggregate.state is OrderState.CANCEL_PENDING
    aggregate.transition(OrderEvent.OUTCOME_UNKNOWN, evidence())
    aggregate.transition(
        OrderEvent.PARTIAL_TRADE,
        evidence("cum_strictly_increases_below_quantity"),
        fact=fact("trade-2", trade=30),
    )
    assert aggregate.state is OrderState.CANCEL_UNKNOWN
    assert aggregate.cumulative_quantity == Quantity(50)


def test_fill_wins_cancel_race_and_late_cancel_confirmation_is_no_op() -> None:
    aggregate = submitted()
    aggregate.transition(OrderEvent.REQUEST_CANCEL, evidence())
    aggregate.transition(
        OrderEvent.FULL_TRADE,
        evidence(),
        fact=fact("trade-full", trade=100),
    )
    version = aggregate.version
    assert (
        aggregate.transition(
            OrderEvent.CANCEL_CONFIRMED,
            evidence("broker_confirms_canceled"),
            fact=fact("late-cancel"),
        )
        is None
    )
    assert aggregate.state is OrderState.FILLED
    assert aggregate.version == version


def test_excess_trade_rejected_atomically_with_canonical_code() -> None:
    aggregate = submitted()
    before = snapshot(aggregate)
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(
            OrderEvent.FULL_TRADE,
            evidence("cum_equals_quantity"),
            fact=fact("too-large", trade=101),
        )
    assert snapshot(aggregate) == before


@pytest.mark.parametrize("version", [0, -1])
def test_restored_version_must_be_positive(version: int) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        order(version=version)


def test_recovery_copies_fact_maps_and_restores_dedupe_state() -> None:
    identity = FactIdentity("broker-report", "r1")
    restored = {identity: "sha256:r1"}
    aggregate = order(processed_facts=restored, broker_sequences={"account": 7})
    restored.clear()
    assert dict(aggregate.processed_facts) == {identity: "sha256:r1"}
    # A replayed fact is a no-op before state-transition lookup.
    assert (
        aggregate.transition(
            OrderEvent.BROKER_ACCEPTED,
            evidence("report_uniquely_correlated"),
            fact=ExternalFact(identity, "sha256:r1"),
        )
        is None
    )
    assert aggregate.version == 1


def test_stale_non_trade_report_is_an_idempotent_no_op() -> None:
    aggregate = order(broker_sequences={"account": 7})
    stale = ExternalFact(
        FactIdentity("broker-report", "r2"),
        "sha256:r2",
        broker_sequence=6,
        stream="account",
    )
    assert (
        aggregate.transition(
            OrderEvent.BROKER_ACCEPTED,
            evidence("report_uniquely_correlated"),
            fact=stale,
        )
        is None
    )
    assert aggregate.version == 1
