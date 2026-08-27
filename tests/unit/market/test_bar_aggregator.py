from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from quantiqmt.market.aggregation import BarAggregator, LateFinalizedDataError

ROOT = Path(__file__).resolve().parents[3]
VECTOR = ROOT / "tests/contract/messages/fixtures/internal/market-data.v1/bar-reference-vector.json"


def test_live_and_replay_emit_the_reviewed_byte_identical_bar_vector() -> None:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    outputs = []
    for mode in ("LIVE", "REPLAY"):
        aggregator = BarAggregator.from_reference_context(
            {**vector["context"], "exchange": "XSHG", "trading_day": "2026-08-11"}
        )
        for item in vector["inputs"]:
            aggregator.add({**item, "mode": mode, "quality": "NORMAL"})
        outputs.append(
            aggregator.advance_watermark(
                vector["context"]["watermark_event_time"],
                watermark_sequence=4,
                received_at="2026-08-11T01:31:00.001Z",
            )
        )

    assert outputs[0] == outputs[1] == [vector["expected_bar"]]


def test_duplicate_collision_and_late_final_mutation_fail_closed() -> None:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    aggregator = BarAggregator.from_reference_context(
        {**vector["context"], "exchange": "XSHG", "trading_day": "2026-08-11"}
    )
    first = {**vector["inputs"][0], "mode": "LIVE", "quality": "NORMAL"}
    aggregator.add(first)
    aggregator.add({**first, "mode": "REPLAY"})
    aggregator.add(first)
    collision = deepcopy(first)
    collision["price"] = "10.02"
    with pytest.raises(ValueError, match="identity collision"):
        aggregator.add(collision)

    for item in vector["inputs"][1:]:
        aggregator.add({**item, "mode": "LIVE", "quality": "NORMAL"})
    aggregator.advance_watermark(
        vector["context"]["watermark_event_time"],
        watermark_sequence=4,
        received_at="2026-08-11T01:31:00.001Z",
    )
    with pytest.raises(LateFinalizedDataError) as raised:
        aggregator.add(
            {
                **first,
                "event_id": "550e8400-e29b-41d4-a716-446655440099",
                "source_sequence": 5,
            }
        )
    assert raised.value.gap_start_sequence == raised.value.gap_end_sequence == 5
