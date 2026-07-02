"""UTC business-time and monotonic-time abstractions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, runtime_checkable


def require_utc(value: datetime) -> datetime:
    """Require and return a timezone-aware UTC datetime."""
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def format_utc(value: datetime) -> str:
    """Serialize an aware UTC datetime as canonical ISO-8601 with Z."""
    utc_value = require_utc(value)
    return utc_value.isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    """Parse canonical ISO-8601 UTC text ending in Z."""
    if not isinstance(value, str):
        raise TypeError("timestamp text must be a string")
    if not value.endswith("Z"):
        raise ValueError("UTC timestamp must end with Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    return require_utc(parsed)


@dataclass(frozen=True, slots=True)
class TradingDay:
    """Trading-calendar-owned date, not inferred from UTC time."""

    value: date

    def __post_init__(self) -> None:
        if isinstance(self.value, datetime) or not isinstance(self.value, date):
            raise TypeError("trading day must be a date")

    @classmethod
    def parse(cls, value: str) -> TradingDay:
        try:
            return cls(date.fromisoformat(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("trading day must use YYYY-MM-DD") from exc

    def to_primitive(self) -> str:
        return self.value.isoformat()

    def __str__(self) -> str:
        return self.value.isoformat()


@runtime_checkable
class Clock(Protocol):
    """Business and latency time source."""

    def now(self) -> datetime:
        """Return the current aware UTC business time."""
        ...

    def monotonic_ns(self) -> int:
        """Return monotonic nanoseconds for duration measurement."""
        ...


@dataclass(frozen=True, slots=True)
class LiveClock:
    """Production clock backed by operating-system clocks."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class VirtualClock:
    """Deterministic forward-only clock for tests and backtests."""

    __slots__ = ("_monotonic_ns", "_now")

    def __init__(self, start: datetime) -> None:
        self._now = require_utc(start)
        self._monotonic_ns = 0

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return self._monotonic_ns

    def advance(self, delta: timedelta) -> None:
        if not isinstance(delta, timedelta):
            raise TypeError("clock delta must be a timedelta")
        if delta < timedelta(0):
            raise ValueError("virtual clock cannot move backwards")
        self._now += delta
        self._monotonic_ns += _timedelta_to_nanoseconds(delta)

    def set(self, value: datetime) -> None:
        utc_value = require_utc(value)
        if utc_value < self._now:
            raise ValueError("virtual clock cannot move backwards")
        self.advance(utc_value - self._now)


def _timedelta_to_nanoseconds(value: timedelta) -> int:
    return ((value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds) * 1_000
