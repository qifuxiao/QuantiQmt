from __future__ import annotations

from quantiqmt.market.normalization import TickNormalizer


def test_live_and_replay_normalization_have_no_mode_or_clock_dependency() -> None:
    raw = {
        "event_id": "550e8400-e29b-41d4-a716-446655440001",
        "provider": "SIM",
        "instrument_id": "600000.XSHG",
        "exchange": "XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "trading_day": "2026-08-11",
        "event_time": "2026-08-11T01:30:00Z",
        "received_at": "2026-08-11T01:30:00.001Z",
        "source_sequence": 1,
        "watermark_sequence": 1,
        "last_price": "10.01",
        "last_quantity": 100,
        "turnover": "1001.00",
        "bid_price": None,
        "ask_price": None,
    }
    normalizer = TickNormalizer()

    assert normalizer.normalize(raw, mode="LIVE") == normalizer.normalize(raw, mode="REPLAY")
