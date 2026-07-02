from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from quantiqmt.shared import Currency, Money, PositionDelta, Quantity, VirtualClock

CNY = Currency("CNY")


def _scaled_decimal(value: int, scale: int = 4) -> Decimal:
    return Decimal(value).scaleb(-scale)


@given(st.integers(min_value=-(10**12), max_value=10**12))
def test_money_primitive_round_trip_preserves_value_and_scale(units: int) -> None:
    original = Money(_scaled_decimal(units), CNY)
    primitive = original.to_primitive()

    restored = Money(primitive["amount"], Currency(primitive["currency"]))

    assert restored == original
    assert restored.to_primitive() == primitive


@given(
    st.integers(min_value=-(10**9), max_value=10**9),
    st.integers(min_value=-(10**9), max_value=10**9),
)
def test_same_currency_money_addition_is_commutative(left: int, right: int) -> None:
    first = Money(_scaled_decimal(left), CNY)
    second = Money(_scaled_decimal(right), CNY)

    assert first + second == second + first


@given(
    st.integers(min_value=0, max_value=10**12),
    st.integers(min_value=0, max_value=10**12),
)
def test_quantity_difference_is_signed_position_delta(left: int, right: int) -> None:
    assert Quantity(left) - Quantity(right) == PositionDelta(left - right)


@given(st.integers(min_value=0, max_value=86_400_000_000))
def test_virtual_clock_advance_is_monotonic(microseconds: int) -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    clock = VirtualClock(start)

    clock.advance(timedelta(microseconds=microseconds))

    assert clock.now() >= start
    assert clock.monotonic_ns() == microseconds * 1_000
