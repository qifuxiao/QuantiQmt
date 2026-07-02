from dataclasses import FrozenInstanceError

import pytest

from quantiqmt.shared import Currency, Identifier, InstrumentId


def test_identifier_new_is_canonical_uuid4() -> None:
    identifier = Identifier.new()

    assert str(identifier) == identifier.value
    assert identifier.value == identifier.value.lower()
    assert identifier.version == 4


def test_identifier_accepts_only_canonical_lowercase_uuid() -> None:
    value = "123e4567-e89b-42d3-a456-426614174000"

    assert Identifier(value).value == value
    with pytest.raises(ValueError, match="canonical lowercase UUID"):
        Identifier(value.upper())
    with pytest.raises(ValueError, match="valid UUID"):
        Identifier("not-a-uuid")


def test_identifier_is_immutable_hashable_and_serializable() -> None:
    identifier = Identifier("123e4567-e89b-42d3-a456-426614174000")

    assert {identifier} == {Identifier(identifier.value)}
    assert identifier.to_primitive() == identifier.value
    with pytest.raises(FrozenInstanceError):
        identifier.value = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", " SH:600000", "SH:600000 ", "x" * 65])
def test_instrument_id_rejects_invalid_boundaries(value: str) -> None:
    with pytest.raises(ValueError):
        InstrumentId(value)


def test_instrument_id_is_opaque_and_case_sensitive() -> None:
    upper = InstrumentId("600000.SH")
    lower = InstrumentId("600000.sh")

    assert upper != lower
    assert str(upper) == "600000.SH"
    assert upper.to_primitive() == "600000.SH"


def test_instrument_id_rejects_non_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        InstrumentId(600000)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["cny", "CN", "CNY1", " CNY"])
def test_currency_requires_three_uppercase_ascii_letters(value: str) -> None:
    with pytest.raises(ValueError, match="three uppercase"):
        Currency(value)


def test_currency_supports_cny_and_serializes_stably() -> None:
    currency = Currency("CNY")

    assert str(currency) == "CNY"
    assert currency.to_primitive() == "CNY"


def test_currency_rejects_non_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        Currency(156)  # type: ignore[arg-type]
