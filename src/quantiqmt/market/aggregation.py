"""Deterministic event-time Bar aggregation with immutable finality."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from quantiqmt.contracts.canonical import canonical_json, canonical_sha256
from quantiqmt.market.errors import (
    IdentityCollisionError,
    LateFinalizedDataError,
    MarketContractError,
)
from quantiqmt.market.validation import (
    BAR_PROJECTION,
    format_utc,
    parse_utc,
    projection_checksum,
    validate_bar,
    validate_market_dto,
    validate_trading_calendar,
)

BAR_NAMESPACE = uuid.UUID("9a41e905-11f3-5c30-8f02-5ba3f8ae8485")
BAR_IDENTITY_FIELDS = (
    "provider",
    "instrument_id",
    "calendar_version",
    "session_id",
    "timeframe_seconds",
    "window_start",
    "window_end",
    "aggregation_policy_version",
    "source_sequence_start",
    "source_sequence_end",
)


class BarAggregator:
    """One calendar/session policy projection; provider/instrument bind on first input."""

    def __init__(
        self,
        *,
        calendar_id: str,
        calendar_version: str,
        session_id: str,
        session_open_at: str,
        session_close_at: str,
        exchange: str,
        trading_day: str,
        timeframe_seconds: int,
        allowed_lateness_ms: int,
        aggregation_policy_version: str,
    ) -> None:
        if timeframe_seconds <= 0 or allowed_lateness_ms < 0:
            raise MarketContractError("invalid Bar aggregation policy")
        self._calendar_id = calendar_id
        self._calendar_version = calendar_version
        self._session_id = session_id
        self._session_open_text = session_open_at
        self._session_close_text = session_close_at
        self._session_open = parse_utc(session_open_at, field="session_open_at")
        self._session_close = parse_utc(session_close_at, field="session_close_at")
        if self._session_open >= self._session_close:
            raise MarketContractError("session interval is inverted")
        self._exchange = exchange
        self._trading_day = trading_day
        self._timeframe = timeframe_seconds
        self._lateness = allowed_lateness_ms
        self._policy_version = aggregation_policy_version
        self._windows: dict[datetime, list[dict[str, object]]] = {}
        self._fingerprints: dict[tuple[str, str, int], str] = {}
        self._finalized: set[datetime] = set()
        self._watermark: datetime | None = None
        self._gaps: dict[datetime, tuple[int, int]] = {}
        self._provider: str | None = None
        self._instrument: str | None = None

    @classmethod
    def from_reference_context(cls, context: Mapping[str, object]) -> BarAggregator:
        required = {"exchange", "trading_day"}
        if not required <= set(context):
            raise MarketContractError("calendar context must explicitly bind exchange/trading_day")
        return cls(
            calendar_id=cast(str, context["calendar_id"]),
            calendar_version=cast(str, context["calendar_version"]),
            session_id=cast(str, context["session_id"]),
            session_open_at=cast(str, context["session_open_at"]),
            session_close_at=cast(str, context["session_close_at"]),
            exchange=cast(str, context["exchange"]),
            trading_day=cast(str, context["trading_day"]),
            timeframe_seconds=cast(int, context["timeframe_seconds"]),
            allowed_lateness_ms=cast(int, context["allowed_lateness_ms"]),
            aggregation_policy_version=cast(str, context["aggregation_policy_version"]),
        )

    @classmethod
    def from_calendar(
        cls,
        calendar: Mapping[str, object],
        policy: Mapping[str, object],
        *,
        session_id: str,
    ) -> BarAggregator:
        validate_trading_calendar(calendar)
        validate_market_dto(policy)
        if policy["calendar_version"] != calendar["calendar_version"]:
            raise MarketContractError("aggregation policy/calendar version mismatch")
        sessions = cast(list[Mapping[str, object]], calendar["sessions"])
        session = next(
            (candidate for candidate in sessions if candidate["session_id"] == session_id),
            None,
        )
        if session is None:
            raise MarketContractError("aggregation session is not in TradingCalendar")
        return cls(
            calendar_id=cast(str, calendar["calendar_id"]),
            calendar_version=cast(str, calendar["calendar_version"]),
            session_id=session_id,
            session_open_at=cast(str, session["open_at"]),
            session_close_at=cast(str, session["close_at"]),
            exchange=cast(str, calendar["exchange"]),
            trading_day=cast(str, calendar["trading_day"]),
            timeframe_seconds=cast(int, policy["timeframe_seconds"]),
            allowed_lateness_ms=cast(int, policy["allowed_lateness_ms"]),
            aggregation_policy_version=cast(str, policy["policy_version"]),
        )

    def add(self, value: Mapping[str, object]) -> None:
        required = {
            "mode",
            "event_id",
            "provider",
            "instrument_id",
            "event_time",
            "source_sequence",
            "price",
            "quantity",
            "turnover",
            "quality",
        }
        if not required <= set(value):
            raise MarketContractError("Bar input is missing required facts")
        if value["mode"] not in {"LIVE", "REPLAY"}:
            raise MarketContractError("Bar input mode is invalid")
        if isinstance(value["price"], float) or isinstance(value["turnover"], float):
            raise MarketContractError("Bar precise values must be Decimal strings")
        provider = cast(str, value["provider"])
        instrument = cast(str, value["instrument_id"])
        if self._provider is None:
            self._provider, self._instrument = provider, instrument
        elif (provider, instrument) != (self._provider, self._instrument):
            raise MarketContractError("BarAggregator identity cannot change")
        sequence = cast(int, value["source_sequence"])
        identity = (provider, instrument, sequence)
        fingerprint = canonical_sha256({key: item for key, item in value.items() if key != "mode"})
        existing = self._fingerprints.get(identity)
        if existing is not None:
            if existing != fingerprint:
                raise IdentityCollisionError("Bar input identity collision")
            return
        event_time = parse_utc(value["event_time"], field="Bar input event_time")
        if not self._session_open <= event_time < self._session_close:
            raise MarketContractError("Bar input is outside bound half-open session")
        window_start = self._window_start(event_time)
        if window_start in self._finalized:
            raise LateFinalizedDataError(sequence)
        self._fingerprints[identity] = fingerprint
        self._windows.setdefault(window_start, []).append(dict(value))

    def record_gap(self, *, event_time: str, start_sequence: int, end_sequence: int) -> None:
        if start_sequence < 0 or start_sequence > end_sequence:
            raise MarketContractError("invalid aggregation gap range")
        window_start = self._window_start(parse_utc(event_time, field="gap event_time"))
        if window_start in self._finalized:
            raise LateFinalizedDataError(start_sequence)
        existing = self._gaps.get(window_start)
        if existing is not None and existing != (start_sequence, end_sequence):
            raise MarketContractError("conflicting aggregation gap evidence")
        self._gaps[window_start] = (start_sequence, end_sequence)

    def advance_watermark(
        self, watermark_event_time: str, *, watermark_sequence: int, received_at: str
    ) -> list[dict[str, object]]:
        watermark = parse_utc(watermark_event_time, field="watermark_event_time")
        if self._watermark is not None and watermark < self._watermark:
            raise MarketContractError("watermark regression")
        self._watermark = watermark
        output: list[dict[str, object]] = []
        for start in sorted(self._windows):
            end = start + timedelta(seconds=self._timeframe)
            if watermark < end + timedelta(milliseconds=self._lateness):
                continue
            ticks = self._windows[start]
            output.append(
                self._close(start, ticks, watermark_event_time, watermark_sequence, received_at)
            )
            self._finalized.add(start)
        for bar in output:
            self._windows.pop(parse_utc(bar["window_start"], field="window_start"), None)
        return output

    def _window_start(self, event_time: datetime) -> datetime:
        elapsed = int((event_time - self._session_open).total_seconds())
        start = self._session_open + timedelta(
            seconds=(elapsed // self._timeframe) * self._timeframe
        )
        if start + timedelta(seconds=self._timeframe) > self._session_close:
            raise MarketContractError("aggregation window would cross session boundary")
        return start

    def _close(
        self,
        start: datetime,
        ticks: list[dict[str, object]],
        watermark_event_time: str,
        watermark_sequence: int,
        received_at: str,
    ) -> dict[str, object]:
        ordered = sorted(
            ticks,
            key=lambda item: (
                parse_utc(item["event_time"], field="event_time"),
                cast(int, item["source_sequence"]),
                cast(str, item["event_id"]),
            ),
        )
        prices = [Decimal(cast(str, item["price"])) for item in ordered]
        sequences = [cast(int, item["source_sequence"]) for item in ordered]
        qualities = {cast(str, item["quality"]) for item in ordered}
        gap = self._gaps.get(start)
        if "GAP" in qualities and gap is None:
            raise MarketContractError("GAP Bar input requires exact recorded gap evidence")
        quality = "GAP" if gap is not None else "NORMAL"
        end = start + timedelta(seconds=self._timeframe)
        bar: dict[str, object] = {
            "partition_key": self._instrument,
            "provider": self._provider,
            "instrument_id": self._instrument,
            "exchange": self._exchange,
            "calendar_id": self._calendar_id,
            "calendar_version": self._calendar_version,
            "session_id": self._session_id,
            "trading_day": self._trading_day,
            "session_open_at": self._session_open_text,
            "session_close_at": self._session_close_text,
            "timeframe_seconds": self._timeframe,
            "allowed_lateness_ms": self._lateness,
            "window_start": format_utc(start),
            "window_end": format_utc(end),
            "event_time": format_utc(end),
            "received_at": received_at,
            "watermark_event_time": watermark_event_time,
            "open": ordered[0]["price"],
            "high": ordered[prices.index(max(prices))]["price"],
            "low": ordered[prices.index(min(prices))]["price"],
            "close": ordered[-1]["price"],
            "volume": sum(cast(int, item["quantity"]) for item in ordered),
            "turnover": str(
                sum((Decimal(cast(str, item["turnover"])) for item in ordered), Decimal(0))
            ),
            "source_sequence_start": min(sequences),
            "source_sequence_end": max(sequences),
            "watermark_sequence": watermark_sequence,
            "quality": quality,
            "gap_start_sequence": gap[0] if gap is not None else None,
            "gap_end_sequence": gap[1] if gap is not None else None,
            "partial": quality == "GAP",
            "final": True,
            "revision": 0,
            "aggregation_policy_version": self._policy_version,
        }
        identity = {field: bar[field] for field in BAR_IDENTITY_FIELDS}
        bar["event_id"] = str(uuid.uuid5(BAR_NAMESPACE, canonical_json(identity)))
        bar["content_checksum"] = projection_checksum(bar, BAR_PROJECTION)
        validate_bar(bar)
        return bar


__all__ = ["BarAggregator", "LateFinalizedDataError"]
