from hypothesis import given
from hypothesis import strategies as st

from quantiqmt.order.domain import Order, OrderEvent, OrderState
from quantiqmt.shared import Identifier, Quantity


@given(st.integers(min_value=2, max_value=1_000), st.data())
def test_monotonic_trade_sequences_preserve_quantity_invariants(
    total: int, data: st.DataObject
) -> None:
    values = sorted(set(data.draw(st.lists(st.integers(1, total - 1), max_size=20))))
    aggregate = Order(Identifier("550e8400-e29b-41d4-a716-446655440000"), Quantity(total))
    for event in (
        OrderEvent.START_RISK,
        OrderEvent.RISK_PASSED,
        OrderEvent.DISPATCH,
        OrderEvent.BROKER_ACCEPTED,
    ):
        aggregate.transition(event)
    for index, value in enumerate(values):
        if aggregate.state is OrderState.SUBMITTED:
            aggregate.transition(
                OrderEvent.PARTIAL_TRADE, cumulative_quantity=Quantity(value), fact_id=f"t{index}"
            )
    aggregate.transition(OrderEvent.FULL_TRADE, cumulative_quantity=Quantity(total), fact_id="full")
    assert 0 <= aggregate.cumulative_quantity.value <= aggregate.quantity.value
    assert aggregate.state is OrderState.FILLED
