"""Exact financial numeric value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from functools import total_ordering

from quantiqmt.shared.identifiers import Currency

type DecimalInput = Decimal | int | str

_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$", re.ASCII)
_MAX_DECIMAL_PLACES = 8


class CurrencyMismatchError(ValueError):
    """Raised when an operation mixes different currencies."""


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _coerce_decimal(value: DecimalInput, *, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError(f"{field} does not accept float or bool")
    if isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        if _CANONICAL_DECIMAL.fullmatch(value) is None:
            raise ValueError(f"{field} must be a canonical decimal string")
        decimal_value = Decimal(value)
    elif isinstance(value, Decimal):
        decimal_value = value
    else:
        raise TypeError(f"{field} must be Decimal, int, or canonical decimal string")
    if not decimal_value.is_finite():
        raise ValueError(f"{field} must be finite")
    if decimal_value.is_zero() and decimal_value.is_signed():
        raise ValueError(f"{field} must not be negative zero")
    if _decimal_places(decimal_value) > _MAX_DECIMAL_PLACES:
        raise ValueError(f"{field} supports at most 8 decimal places")
    return decimal_value


def _validate_scale(scale: int) -> None:
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise TypeError("scale must be an integer")
    if not 0 <= scale <= _MAX_DECIMAL_PLACES:
        raise ValueError("scale must be between 0 and 8")


def _required_precision(*values: Decimal, extra: int = 2) -> int:
    capacities: list[int] = []
    for value in values:
        places = _decimal_places(value)
        integer_digits = max(1, value.adjusted() + 1) if not value.is_zero() else 1
        capacities.append(max(len(value.as_tuple().digits), integer_digits + places))
    return max(28, sum(capacities) + extra)


def _add_exact(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _required_precision(left, right)
        return left + right


def _subtract_exact(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _required_precision(left, right)
        return left - right


def _multiply_exact(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _required_precision(left, right)
        return left * right


def _quantize(value: Decimal, *, scale: int, rounding: str) -> Decimal:
    _validate_scale(scale)
    quantum = Decimal(1).scaleb(-scale)
    with localcontext() as context:
        context.prec = _required_precision(value, extra=scale + 2)
        result = value.quantize(quantum, rounding=rounding)
    return result.copy_abs() if result.is_zero() and result.is_signed() else result


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


@total_ordering
@dataclass(frozen=True, slots=True, init=False)
class Money:
    """Exact monetary amount associated with one currency."""

    amount: Decimal
    currency: Currency

    def __init__(self, amount: DecimalInput, currency: Currency) -> None:
        if not isinstance(currency, Currency):
            raise TypeError("currency must be a Currency")
        object.__setattr__(self, "amount", _coerce_decimal(amount, field="money amount"))
        object.__setattr__(self, "currency", currency)

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"currency mismatch: {self.currency} != {other.currency}")

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(_add_exact(self.amount, other.amount), self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(_subtract_exact(self.amount, other.amount), self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount < other.amount

    def quantize(self, *, scale: int, rounding: str = ROUND_HALF_EVEN) -> Money:
        """Return this amount rounded to an explicit scale."""
        return Money(_quantize(self.amount, scale=scale, rounding=rounding), self.currency)

    def multiply(
        self,
        factor: DecimalInput,
        *,
        scale: int,
        rounding: str = ROUND_HALF_EVEN,
    ) -> Money:
        """Multiply by an exact factor and round to an explicit scale."""
        exact_factor = _coerce_decimal(factor, field="money factor")
        exact = _multiply_exact(self.amount, exact_factor)
        result = _quantize(exact, scale=scale, rounding=rounding)
        return Money(result, self.currency)

    def to_primitive(self) -> dict[str, str]:
        """Return the stable JSON-compatible representation."""
        return {"amount": _decimal_text(self.amount), "currency": str(self.currency)}

    def __str__(self) -> str:
        return f"{_decimal_text(self.amount)} {self.currency}"


@dataclass(frozen=True, slots=True, init=False)
class Price:
    """Positive exact price without an implicit currency."""

    value: Decimal

    def __init__(self, value: DecimalInput) -> None:
        decimal_value = _coerce_decimal(value, field="price")
        if decimal_value <= 0:
            raise ValueError("price must be greater than zero")
        object.__setattr__(self, "value", decimal_value)

    def notional(
        self,
        quantity: Quantity,
        currency: Currency,
        *,
        scale: int,
        rounding: str = ROUND_HALF_EVEN,
    ) -> Money:
        """Calculate a monetary notional using explicit currency and scale."""
        if not isinstance(quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        exact = _multiply_exact(self.value, Decimal(quantity.value))
        return Money(_quantize(exact, scale=scale, rounding=rounding), currency)

    def to_primitive(self) -> str:
        return _decimal_text(self.value)

    def __str__(self) -> str:
        return _decimal_text(self.value)


@dataclass(frozen=True, slots=True, init=False)
class Quantity:
    """Non-negative integral quantity."""

    value: int

    def __init__(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("quantity must be an integer")
        if value < 0:
            raise ValueError("quantity must be non-negative")
        object.__setattr__(self, "value", value)

    def require_positive(self) -> Quantity:
        """Validate that this quantity is suitable for a new order."""
        if self.value == 0:
            raise ValueError("order quantity must be positive")
        return self

    def __sub__(self, other: Quantity) -> PositionDelta:
        if not isinstance(other, Quantity):
            return NotImplemented
        return PositionDelta(self.value - other.value)

    def to_primitive(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True, init=False)
class PositionDelta:
    """Signed integral change in a position."""

    value: int

    def __init__(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("position delta must be an integer")
        object.__setattr__(self, "value", value)

    def to_primitive(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True, init=False)
class Ratio:
    """Unbounded exact ratio whose business range is defined by its mandate."""

    value: Decimal

    def __init__(self, value: DecimalInput) -> None:
        object.__setattr__(self, "value", _coerce_decimal(value, field="ratio"))

    def to_primitive(self) -> str:
        return _decimal_text(self.value)

    def __str__(self) -> str:
        return _decimal_text(self.value)


@dataclass(frozen=True, slots=True, init=False)
class Weight:
    """Long-only target weight in the inclusive range [0, 1]."""

    value: Decimal

    def __init__(self, value: DecimalInput) -> None:
        decimal_value = _coerce_decimal(value, field="weight")
        if not Decimal(0) <= decimal_value <= Decimal(1):
            raise ValueError("weight must be between 0 and 1")
        object.__setattr__(self, "value", decimal_value)

    def to_primitive(self) -> str:
        return _decimal_text(self.value)

    def __str__(self) -> str:
        return _decimal_text(self.value)
