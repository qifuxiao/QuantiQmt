from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from quantiqmt.shared import (
    Clock,
    LiveClock,
    TradingDay,
    VirtualClock,
    format_utc,
    parse_utc,
    require_utc,
)


def test_require_utc_rejects_naive_and_non_utc_datetimes() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        require_utc("2026-07-01T00:00:00Z")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        require_utc(datetime(2026, 7, 1, 9, 30))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        require_utc(datetime(2026, 7, 1, 9, 30, tzinfo=timezone(timedelta(hours=8))))


def test_utc_format_and_parse_are_stable() -> None:
    value = datetime(2026, 7, 1, 1, 30, 0, 123456, tzinfo=UTC)

    assert format_utc(value) == "2026-07-01T01:30:00.123456Z"
    assert parse_utc(format_utc(value)) == value
    with pytest.raises(ValueError, match="must end with Z"):
        parse_utc("2026-07-01T01:30:00+00:00")
    with pytest.raises(TypeError, match="must be a string"):
        parse_utc(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid UTC timestamp"):
        parse_utc("not-a-timeZ")


@pytest.mark.parametrize(
    "clock",
    [
        pytest.param(LiveClock(), id="live-clock"),
        pytest.param(
            VirtualClock(datetime(2026, 7, 1, tzinfo=UTC)),
            id="virtual-clock",
        ),
    ],
)
def test_clock_contract_returns_utc_and_monotonic_nanoseconds(clock: Clock) -> None:
    """Every Clock implementation must pass this shared behavioral contract."""

    first = clock.monotonic_ns()
    now = clock.now()
    second = clock.monotonic_ns()

    assert isinstance(clock, Clock)
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert isinstance(first, int)
    assert second >= first


def test_virtual_clock_advances_business_and_monotonic_time_together() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    clock = VirtualClock(start)

    clock.advance(timedelta(seconds=1, microseconds=2))

    assert clock.now() == start + timedelta(seconds=1, microseconds=2)
    assert clock.monotonic_ns() == 1_000_002_000


def test_virtual_clock_cannot_move_backwards() -> None:
    clock = VirtualClock(datetime(2026, 7, 1, tzinfo=UTC))

    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance(timedelta(microseconds=-1))
    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.set(datetime(2026, 6, 30, tzinfo=UTC))


def test_virtual_clock_set_moves_forward_and_rejects_invalid_delta_type() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    clock = VirtualClock(start)

    clock.set(start + timedelta(seconds=2))

    assert clock.now() == start + timedelta(seconds=2)
    assert clock.monotonic_ns() == 2_000_000_000
    with pytest.raises(TypeError, match="must be a timedelta"):
        clock.advance(1)  # type: ignore[arg-type]


def test_trading_day_is_calendar_owned_and_serializes_as_iso_date() -> None:
    trading_day = TradingDay.parse("2026-07-01")

    assert trading_day.value == date(2026, 7, 1)
    assert str(trading_day) == "2026-07-01"
    assert trading_day.to_primitive() == "2026-07-01"


def test_trading_day_rejects_datetime_and_invalid_text() -> None:
    with pytest.raises(TypeError, match="must be a date"):
        TradingDay(datetime(2026, 7, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        TradingDay.parse("2026/07/01")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        TradingDay.parse(20260701)  # type: ignore[arg-type]
