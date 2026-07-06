from hypothesis import given
from hypothesis import strategies as st

from quantiqmt.order.domain import (
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
        GuardEvidence.of("report_uniquely_correlated"),
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
            GuardEvidence.of(
                "cum_between_zero_and_quantity"
                if aggregate.state is OrderState.SUBMITTED
                else "cum_strictly_increases_below_quantity"
            ),
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
        GuardEvidence.of("cum_equals_quantity"),
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
            GuardEvidence.of("cum_equals_quantity"),
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
