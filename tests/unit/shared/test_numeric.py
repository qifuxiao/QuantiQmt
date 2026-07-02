from dataclasses import FrozenInstanceError
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, localcontext

import pytest

from quantiqmt.shared import (
    Currency,
    CurrencyMismatchError,
    Money,
    PositionDelta,
    Price,
    Quantity,
    Ratio,
    Weight,
)

CNY = Currency("CNY")
USD = Currency("USD")


@pytest.mark.parametrize("value", [1.0, -0.0, float("nan"), float("inf")])
def test_money_and_price_reject_float(value: float) -> None:
    with pytest.raises(TypeError, match="float"):
        Money(value, CNY)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        Price(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "-0", "-0.00"])
def test_decimal_values_reject_non_finite_and_negative_zero(value: str) -> None:
    with pytest.raises(ValueError):
        Money(value, CNY)


@pytest.mark.parametrize("value", ["1e2", "+1.00", "01.00", ".5", "1."])
def test_decimal_string_must_be_canonical(value: str) -> None:
    with pytest.raises(ValueError, match="canonical decimal string"):
        Money(value, CNY)


def test_money_preserves_decimal_scale_in_serialization() -> None:
    money = Money("12.3400", CNY)

    assert money.amount == Decimal("12.3400")
    assert str(money) == "12.3400 CNY"
    assert money.to_primitive() == {"amount": "12.3400", "currency": "CNY"}


def test_money_accepts_integer_and_decimal_inputs() -> None:
    assert Money(12, CNY) == Money(Decimal("12"), CNY)


def test_money_rejects_unsupported_input_and_currency_types() -> None:
    with pytest.raises(TypeError, match="Decimal, int"):
        Money(object(), CNY)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a Currency"):
        Money("1.00", "CNY")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be finite"):
        Money(Decimal("NaN"), CNY)


def test_money_rejects_more_than_eight_decimal_places() -> None:
    with pytest.raises(ValueError, match="at most 8 decimal places"):
        Money("1.123456789", CNY)


def test_money_arithmetic_requires_matching_currency() -> None:
    assert Money("2.00", CNY) + Money("3.00", CNY) == Money("5.00", CNY)
    assert Money("5.00", CNY) - Money("3.00", CNY) == Money("2.00", CNY)

    with pytest.raises(CurrencyMismatchError):
        _ = Money("1.00", CNY) + Money("1.00", USD)
    with pytest.raises(CurrencyMismatchError):
        _ = Money("1.00", CNY) < Money("1.00", USD)


def test_money_quantize_uses_explicit_scale_and_rounding() -> None:
    money = Money("1.235", CNY)

    assert money.quantize(scale=2) == Money("1.24", CNY)
    assert money.quantize(scale=2, rounding=ROUND_DOWN) == Money("1.23", CNY)
    assert money.quantize(scale=2, rounding=ROUND_HALF_EVEN) == Money("1.24", CNY)


@pytest.mark.parametrize("scale", [-1, 9])
def test_money_quantize_rejects_scale_outside_supported_range(scale: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 8"):
        Money("1.00", CNY).quantize(scale=scale)


def test_money_quantize_rejects_non_integer_scale() -> None:
    with pytest.raises(TypeError, match="scale must be an integer"):
        Money("1.00", CNY).quantize(scale=True)


def test_money_multiply_requires_scale_and_returns_money() -> None:
    money = Money("10.00", CNY)

    assert money.multiply("1.234", scale=2) == Money("12.34", CNY)
    with pytest.raises(TypeError, match="float"):
        money.multiply(1.2, scale=2)  # type: ignore[arg-type]


def test_money_comparison_and_foreign_operands() -> None:
    assert Money("1.00", CNY) < Money("2.00", CNY)
    with pytest.raises(TypeError):
        _ = Money("1.00", CNY) + 1  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Money("1.00", CNY) - 1  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Money("1.00", CNY) < 1


def test_financial_arithmetic_uses_local_decimal_context() -> None:
    with localcontext() as outer_context:
        outer_context.prec = 6

        total = Money("123456789.12", CNY) + Money("0.88", CNY)
        product = Money("123456789.12", CNY).multiply("2", scale=2)

        assert total == Money("123456790.00", CNY)
        assert product == Money("246913578.24", CNY)
        assert outer_context.prec == 6


def test_rounding_negative_value_to_zero_canonicalizes_negative_zero() -> None:
    rounded = Money("-0.004", CNY).quantize(scale=2)

    assert rounded == Money("0.00", CNY)
    assert rounded.to_primitive()["amount"] == "0.00"


@pytest.mark.parametrize("value", ["0", "-0.01", "-1"])
def test_price_must_be_positive(value: str) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Price(value)


def test_price_notional_requires_currency_scale_and_rounding() -> None:
    price = Price("3.859")
    quantity = Quantity(100)

    assert price.notional(quantity, CNY, scale=2) == Money("385.90", CNY)
    assert price.to_primitive() == "3.859"
    assert str(price) == "3.859"
    with pytest.raises(TypeError, match="must be a Quantity"):
        price.notional(100, CNY, scale=2)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, True, 1.0, "1"])
def test_quantity_rejects_invalid_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Quantity(value)  # type: ignore[arg-type]


def test_quantity_supports_zero_but_can_require_positive() -> None:
    assert Quantity(0).value == 0
    assert Quantity(0).to_primitive() == 0
    assert Quantity(10).require_positive() == Quantity(10)
    with pytest.raises(ValueError, match="must be positive"):
        Quantity(0).require_positive()


def test_quantity_subtraction_returns_position_delta() -> None:
    assert Quantity(3) - Quantity(5) == PositionDelta(-2)
    assert PositionDelta(-2).to_primitive() == -2
    assert int(Quantity(3)) == 3
    assert int(PositionDelta(-2)) == -2
    with pytest.raises(TypeError):
        _ = Quantity(3) - 1  # type: ignore[operator]


def test_position_delta_rejects_non_integer() -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        PositionDelta(True)


def test_ratio_and_weight_use_decimal_without_float() -> None:
    assert Ratio("-0.25").to_primitive() == "-0.25"
    assert Weight("0.25").to_primitive() == "0.25"
    assert str(Ratio("-0.25")) == "-0.25"
    assert str(Weight("0.25")) == "0.25"
    with pytest.raises(TypeError, match="float"):
        Ratio(0.25)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["-0.01", "1.01"])
def test_weight_defaults_to_long_only_range(value: str) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Weight(value)


def test_numeric_value_objects_are_immutable_and_hashable() -> None:
    money = Money("1.00", CNY)

    assert {money} == {Money("1.00", CNY)}
    with pytest.raises(FrozenInstanceError):
        money.amount = Decimal("2.00")  # type: ignore[misc]
