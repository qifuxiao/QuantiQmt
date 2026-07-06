from hypothesis import given
from hypothesis import strategies as st

from quantiqmt.order.domain import (
    BrokerReportEvidence,
    BrokerStatus,
    ExternalFact,
    FactIdentity,
    GuardEvidence,
    InvalidOrderTransition,
    Order,
    OrderEvent,
    OrderState,
)
from quantiqmt.shared import Identifier, Quantity


def external(key: str, quantity: int | None = None) -> ExternalFact:
    namespace = "trade" if quantity is not None else "report"
    return ExternalFact(
        FactIdentity(namespace, key),
        f"sha256:{key}:{quantity}",
        Quantity(quantity) if quantity is not None else None,
    )


def submitted(total: int) -> Order:
    aggregate = Order(Identifier("550e8400-e29b-41d4-a716-446655440000"), Quantity(total))
    aggregate.transition(OrderEvent.START_RISK, GuardEvidence.risk_snapshots("a", "p", "m"))
    aggregate.transition(OrderEvent.RISK_PASSED, GuardEvidence.expected_version(2))
    aggregate.transition(OrderEvent.DISPATCH, GuardEvidence.trading_authority())
    aggregate.transition(
        OrderEvent.BROKER_ACCEPTED,
        GuardEvidence(
            broker_report=BrokerReportEvidence(
                1, BrokerStatus.ACCEPTED, Quantity(0), Quantity(total)
            )
        ),
        fact=external("accepted"),
    )
    return aggregate


@given(st.integers(min_value=2, max_value=10_000), st.data())
def test_unique_trade_sequences_with_arbitrary_duplicates_preserve_invariants(
    total: int, data: st.DataObject
) -> None:
    parts = data.draw(
        st.lists(st.integers(min_value=1, max_value=total - 1), min_size=1, max_size=20)
    )
    running = 0
    accepted: list[ExternalFact] = []
    for index, part in enumerate(parts):
        if running + part >= total:
            break
        running += part
        accepted.append(external(f"t-{index}", part))

    aggregate = submitted(total)
    replay_stream = data.draw(
        st.lists(st.integers(min_value=0, max_value=len(accepted) - 1), max_size=30)
    )
    processed: set[int] = set()
    for index in replay_stream:
        trade = accepted[index]
        result = aggregate.transition(
            OrderEvent.PARTIAL_TRADE,
            GuardEvidence(),
            fact=trade,
        )
        if index in processed:
            assert result is None
        processed.add(index)
        assert 0 <= aggregate.cumulative_quantity.value < total

    expected = sum(accepted[index].trade_quantity.value for index in processed)  # type: ignore[union-attr]
    assert aggregate.cumulative_quantity == Quantity(expected)
    aggregate.transition(
        OrderEvent.FULL_TRADE,
        GuardEvidence(),
        fact=external("final", total - expected),
    )
    assert aggregate.cumulative_quantity == aggregate.quantity
    assert aggregate.state is OrderState.FILLED


@given(st.integers(min_value=1, max_value=10_000), st.integers(min_value=1, max_value=10_000))
def test_invalid_trade_never_partially_mutates_aggregate(total: int, excess: int) -> None:
    aggregate = submitted(total)
    before = (
        aggregate.state,
        aggregate.cumulative_quantity,
        aggregate.version,
        dict(aggregate.processed_facts),
    )
    try:
        aggregate.transition(
            OrderEvent.FULL_TRADE,
            GuardEvidence(),
            fact=external("invalid", total + excess),
        )
    except InvalidOrderTransition as error:
        assert error.code == "QQ-OMS-5002"
    after = (
        aggregate.state,
        aggregate.cumulative_quantity,
        aggregate.version,
        dict(aggregate.processed_facts),
    )
    assert after == before


@given(st.integers(min_value=2, max_value=10_000), st.data())
def test_conflict_replay_and_cancel_fill_race_are_idempotent(
    total: int, data: st.DataObject
) -> None:
    partial = data.draw(st.integers(min_value=1, max_value=total - 1))
    aggregate = submitted(total)
    first = external("partial", partial)
    aggregate.transition(OrderEvent.REQUEST_CANCEL, GuardEvidence())
    aggregate.transition(OrderEvent.PARTIAL_TRADE, GuardEvidence(), fact=first)
    if data.draw(st.booleans()):
        aggregate.transition(OrderEvent.OUTCOME_UNKNOWN, GuardEvidence())
    aggregate.transition(
        OrderEvent.FULL_TRADE,
        GuardEvidence(),
        fact=external("remainder", total - partial),
    )
    version = aggregate.version
    late_cancel = external("late-cancel")
    assert (
        aggregate.transition(OrderEvent.CANCEL_CONFIRMED, GuardEvidence(), fact=late_cancel) is None
    )
    assert aggregate.version == version
    assert aggregate.state is OrderState.FILLED


@given(st.integers(min_value=2, max_value=10_000), st.text(min_size=1, max_size=30))
def test_same_conflicting_fact_replay_is_no_op(total: int, suffix: str) -> None:
    aggregate = submitted(total)
    original = external("trade", 1)
    aggregate.transition(OrderEvent.PARTIAL_TRADE, GuardEvidence(), fact=original)
    conflict = ExternalFact(
        original.identity,
        f"different:{suffix}",
        original.trade_quantity,
    )
    aggregate.transition(OrderEvent.PARTIAL_TRADE, GuardEvidence(), fact=conflict)
    version = aggregate.version
    assert aggregate.transition(OrderEvent.PARTIAL_TRADE, GuardEvidence(), fact=conflict) is None
    assert aggregate.version == version
    assert aggregate.state is OrderState.SUSPENDED
