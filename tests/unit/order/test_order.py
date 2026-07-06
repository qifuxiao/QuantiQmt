from pathlib import Path

import pytest
import yaml

from quantiqmt.order.domain import (
    InvalidOrderTransition,
    Order,
    OrderAction,
    OrderEvent,
    OrderState,
    transition_catalog,
)
from quantiqmt.shared import Identifier, Quantity


def order(quantity: int = 100) -> Order:
    return Order(Identifier("550e8400-e29b-41d4-a716-446655440000"), Quantity(quantity))


def test_transition_catalog_exactly_matches_normative_yaml() -> None:
    document = yaml.safe_load(Path("spec/state-machines/order.yaml").read_text(encoding="utf-8"))
    expected = {
        (OrderState(item["from"]), OrderEvent(item["event"]), OrderState(item["to"]))
        for item in document["machine"]["transitions"]
    }
    assert transition_catalog() == expected


def test_submit_unknown_only_schedules_reconciliation() -> None:
    aggregate = order()
    aggregate.transition(OrderEvent.START_RISK)
    aggregate.transition(OrderEvent.RISK_PASSED)
    aggregate.transition(OrderEvent.DISPATCH)
    result = aggregate.transition(OrderEvent.OUTCOME_UNKNOWN)
    assert result is not None
    assert result.current is OrderState.SUBMIT_UNKNOWN
    assert result.action is OrderAction.SCHEDULE_RECONCILIATION


def test_invalid_transition_and_failed_guard_use_canonical_error() -> None:
    aggregate = order()
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(OrderEvent.DISPATCH)
    with pytest.raises(InvalidOrderTransition, match="QQ-OMS-5002"):
        aggregate.transition(OrderEvent.START_RISK, guard_satisfied=False)


def test_trade_invariants_and_duplicate_fact_are_enforced() -> None:
    aggregate = order()
    aggregate.transition(OrderEvent.START_RISK)
    aggregate.transition(OrderEvent.RISK_PASSED)
    aggregate.transition(OrderEvent.DISPATCH)
    aggregate.transition(OrderEvent.BROKER_ACCEPTED)
    result = aggregate.transition(
        OrderEvent.PARTIAL_TRADE, cumulative_quantity=Quantity(40), fact_id="trade-1"
    )
    assert result is not None
    assert aggregate.cumulative_quantity == Quantity(40)
    assert (
        aggregate.transition(
            OrderEvent.PARTIAL_TRADE, cumulative_quantity=Quantity(40), fact_id="trade-1"
        )
        is None
    )
    with pytest.raises(InvalidOrderTransition):
        aggregate.transition(OrderEvent.FULL_TRADE, cumulative_quantity=Quantity(39))
    aggregate.transition(OrderEvent.FULL_TRADE, cumulative_quantity=Quantity(100))
    assert aggregate.state is OrderState.FILLED


def test_cancel_can_lose_race_to_full_trade() -> None:
    aggregate = order()
    for event in (
        OrderEvent.START_RISK,
        OrderEvent.RISK_PASSED,
        OrderEvent.DISPATCH,
        OrderEvent.BROKER_ACCEPTED,
        OrderEvent.REQUEST_CANCEL,
    ):
        aggregate.transition(event)
    aggregate.transition(OrderEvent.FULL_TRADE, cumulative_quantity=Quantity(100))
    assert aggregate.state is OrderState.FILLED
