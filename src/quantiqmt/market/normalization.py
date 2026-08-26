"""Vendor-boundary normalization with no I/O, clock reads, or inferred calendar facts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.market.errors import MarketContractError
from quantiqmt.market.validation import validate_tick


class TickNormalizer:
    """Normalize an already mapped vendor record into public Tick V1."""

    _required: ClassVar[set[str]] = {
        "event_id",
        "provider",
        "instrument_id",
        "exchange",
        "calendar_id",
        "calendar_version",
        "session_id",
        "trading_day",
        "event_time",
        "received_at",
        "source_sequence",
        "watermark_sequence",
        "last_price",
        "last_quantity",
        "turnover",
    }

    def __init__(self, registry: SchemaRegistry | None = None) -> None:
        self._registry = registry or SchemaRegistry()

    def normalize(self, raw: Mapping[str, object], *, mode: str) -> dict[str, object]:
        if mode not in {"LIVE", "REPLAY"}:
            raise MarketContractError("normalization mode must be LIVE or REPLAY")
        missing = self._required - set(raw)
        if missing:
            raise MarketContractError(
                f"vendor mapping is missing explicit facts: {sorted(missing)}"
            )
        for field in ("last_price", "turnover", "bid_price", "ask_price"):
            if isinstance(raw.get(field), float):
                raise MarketContractError(f"{field} JSON float is forbidden")
        payload = {
            "event_id": raw["event_id"],
            "partition_key": raw["instrument_id"],
            "provider": raw["provider"],
            "instrument_id": raw["instrument_id"],
            "exchange": raw["exchange"],
            "calendar_id": raw["calendar_id"],
            "calendar_version": raw["calendar_version"],
            "session_id": raw["session_id"],
            "trading_day": raw["trading_day"],
            "event_time": raw["event_time"],
            "received_at": raw["received_at"],
            "source_sequence": raw["source_sequence"],
            "watermark_sequence": raw["watermark_sequence"],
            "last_price": raw["last_price"],
            "last_quantity": raw["last_quantity"],
            "turnover": raw["turnover"],
            "bid_price": raw.get("bid_price"),
            "ask_price": raw.get("ask_price"),
            "quality": raw.get("quality", "NORMAL"),
            "gap_start_sequence": raw.get("gap_start_sequence"),
            "gap_end_sequence": raw.get("gap_end_sequence"),
        }
        validate_tick(payload, self._registry)
        return payload
