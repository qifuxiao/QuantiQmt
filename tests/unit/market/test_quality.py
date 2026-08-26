from __future__ import annotations

import pytest

from quantiqmt.market.errors import MarketContractError
from quantiqmt.market.quality import MarketQuality, RecoveryEvidenceRegistry
from quantiqmt.market.validation import (
    CHECKPOINT_PROJECTION,
    SNAPSHOT_PROJECTION,
    projection_checksum,
)


def recovery_objects(quality_version: int) -> tuple[dict[str, object], dict[str, object]]:
    snapshot = {
        "dto_type": "MARKET_SNAPSHOT",
        "schema_version": 1,
        "provider": "SIM",
        "generation": 1,
        "instrument_id": "600000.XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "as_of": "2026-08-11T01:30:00Z",
        "source_version": 12,
        "source_sequence": 12,
        "quality_version": quality_version,
        "aggregation_policy_version": "bar-v1",
        "quality": "NORMAL",
        "stale": False,
        "unresolved_gap_count": 0,
        "checksum_verified": True,
    }
    snapshot["content_checksum"] = projection_checksum(snapshot, SNAPSHOT_PROJECTION)
    checkpoint = {
        "dto_type": "BAR_AGGREGATION_CHECKPOINT",
        "schema_version": 1,
        "provider": "SIM",
        "instrument_id": "600000.XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "source_version": 12,
        "quality_version": quality_version,
        "aggregation_policy_version": "bar-v1",
        "watermark_sequence": 12,
        "watermark_event_time": "2026-08-11T01:31:00Z",
        "last_final_sequence": 12,
    }
    checkpoint["checkpoint_checksum"] = projection_checksum(checkpoint, CHECKPOINT_PROJECTION)
    return snapshot, checkpoint


def evidence(
    quality_version: int, snapshot: dict[str, object], checkpoint: dict[str, object]
) -> dict[str, object]:
    return {
        "provider": "SIM",
        "instrument_id": "600000.XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "snapshot_identity": f"snapshot-{quality_version}",
        "snapshot_checksum": snapshot["content_checksum"],
        "checkpoint_identity": f"checkpoint-{quality_version}",
        "checkpoint_checksum": checkpoint["checkpoint_checksum"],
        "backfill_start_sequence": 11,
        "backfill_end_sequence": 11,
        "gap_start_sequence": 11,
        "gap_end_sequence": 11,
        "watermark_sequence": 12,
        "previous_source_version": 10,
        "source_version": 12,
        "previous_quality_version": quality_version - 1,
        "quality_version": quality_version,
    }


def subject() -> tuple[MarketQuality, dict[str, object], dict[str, object]]:
    registry = RecoveryEvidenceRegistry()
    evidence_by_version: dict[int, dict[str, object]] = {}
    for quality_version in (4, 5):
        snapshot, checkpoint = recovery_objects(quality_version)
        registry.register_snapshot(f"snapshot-{quality_version}", snapshot)
        registry.register_checkpoint(f"checkpoint-{quality_version}", checkpoint)
        evidence_by_version[quality_version] = evidence(quality_version, snapshot, checkpoint)
    quality = MarketQuality(registry)
    quality.baseline(
        provider="SIM",
        instrument_id="600000.XSHG",
        calendar_id="CN-A",
        calendar_version="cal-v1",
        session_id="am",
        source_version=10,
        quality_version=2,
    )
    return quality, evidence_by_version[4], evidence_by_version[5]


def tick(sequence: int, *, event_id: str | None = None) -> dict[str, object]:
    return {
        "provider": "SIM",
        "instrument_id": "600000.XSHG",
        "source_sequence": sequence,
        "event_id": event_id or f"550e8400-e29b-41d4-a716-{sequence:012d}",
    }


def gap_subject() -> MarketQuality:
    quality = MarketQuality()
    quality.baseline(
        provider="SIM",
        instrument_id="600000.XSHG",
        calendar_id="CN-A",
        calendar_version="cal-v1",
        session_id="am",
        source_version=0,
        quality_version=1,
    )
    return quality


def test_gap_backfill_keeps_continuous_watermark_separate_from_highest_sequence() -> None:
    quality = gap_subject()

    first = quality.observe_tick(tick(5))

    assert first.quality == "GAP"
    assert first.quality_version == 2
    assert first.source_version == first.highest_observed_sequence == 5
    assert first.contiguous_source_version == 0
    assert (first.gap_start_sequence, first.gap_end_sequence) == (1, 4)

    for sequence in range(1, 5):
        current = quality.observe_tick(tick(sequence))

    assert current.quality == "GAP"
    assert current.source_version == current.highest_observed_sequence == 5
    assert current.contiguous_source_version == 5


def test_gap_backfill_allows_out_of_order_recovery_only_after_every_missing_tick() -> None:
    quality = gap_subject()
    quality.observe_tick(tick(5))

    quality.observe_tick(tick(4))
    quality.observe_tick(tick(2))
    assert quality.state("600000.XSHG").contiguous_source_version == 0

    quality.observe_tick(tick(1))
    assert quality.state("600000.XSHG").contiguous_source_version == 2
    quality.observe_tick(tick(3))
    assert quality.state("600000.XSHG").contiguous_source_version == 5
    assert quality.state("600000.XSHG").quality == "GAP"


def test_gap_backfill_is_idempotent_and_rejects_conflicts_or_out_of_range_sequences() -> None:
    quality = gap_subject()
    quality.observe_tick(tick(5))

    assert quality.observe_tick(tick(5)) == quality.state("600000.XSHG")
    quality.observe_tick(tick(2))
    with pytest.raises(MarketContractError, match="identity collision"):
        quality.observe_tick(tick(2, event_id="550e8400-e29b-41d4-a716-446655449992"))
    with pytest.raises(MarketContractError, match="outside the unresolved gap"):
        quality.observe_tick(tick(6))
    with pytest.raises(MarketContractError, match="outside the unresolved gap"):
        quality.observe_tick(tick(0))


def recovery_for_gap(
    quality_version: int,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    snapshot, checkpoint = recovery_objects(quality_version)
    snapshot["source_version"] = 5
    snapshot["source_sequence"] = 5
    snapshot["quality_version"] = quality_version
    snapshot["content_checksum"] = projection_checksum(snapshot, SNAPSHOT_PROJECTION)
    checkpoint["source_version"] = 5
    checkpoint["quality_version"] = quality_version
    checkpoint["watermark_sequence"] = 5
    checkpoint["last_final_sequence"] = 5
    checkpoint["checkpoint_checksum"] = projection_checksum(checkpoint, CHECKPOINT_PROJECTION)
    recovery = evidence(quality_version, snapshot, checkpoint)
    recovery.update(
        {
            "backfill_start_sequence": 1,
            "backfill_end_sequence": 4,
            "gap_start_sequence": 1,
            "gap_end_sequence": 4,
            "watermark_sequence": 5,
            "previous_source_version": 0,
            "source_version": 5,
        }
    )
    return snapshot, checkpoint, recovery


def test_completed_backfill_requires_valid_recovery_evidence_before_normal() -> None:
    registry = RecoveryEvidenceRegistry()
    start_snapshot, start_checkpoint, start = recovery_for_gap(3)
    complete_snapshot, complete_checkpoint, complete = recovery_for_gap(4)
    registry.register_snapshot("gap-start", start_snapshot)
    registry.register_checkpoint("gap-start", start_checkpoint)
    registry.register_snapshot("gap-complete", complete_snapshot)
    registry.register_checkpoint("gap-complete", complete_checkpoint)
    start["snapshot_identity"] = start["checkpoint_identity"] = "gap-start"
    start["snapshot_checksum"] = start_snapshot["content_checksum"]
    start["checkpoint_checksum"] = start_checkpoint["checkpoint_checksum"]
    complete["snapshot_identity"] = complete["checkpoint_identity"] = "gap-complete"
    complete["snapshot_checksum"] = complete_snapshot["content_checksum"]
    complete["checkpoint_checksum"] = complete_checkpoint["checkpoint_checksum"]
    quality = MarketQuality(registry)
    quality.baseline(
        provider="SIM",
        instrument_id="600000.XSHG",
        calendar_id="CN-A",
        calendar_version="cal-v1",
        session_id="am",
        source_version=0,
        quality_version=1,
    )
    quality.observe_tick(tick(5))
    for sequence in range(1, 4):
        quality.observe_tick(tick(sequence))

    with pytest.raises(MarketContractError, match="backfill is incomplete"):
        quality.begin_recovery("600000.XSHG", start, reason="BACKFILL_STARTED")

    quality.observe_tick(tick(4))
    recovering = quality.begin_recovery("600000.XSHG", start, reason="BACKFILL_STARTED")
    assert (recovering.quality, recovering.quality_version) == ("RECOVERING", 3)
    bad_completion = dict(complete)
    bad_completion["source_version"] = 6
    with pytest.raises(MarketContractError, match="fully resolved gap"):
        quality.complete_recovery("600000.XSHG", bad_completion)
    normal = quality.complete_recovery("600000.XSHG", complete)
    assert (normal.quality, normal.quality_version, normal.source_version) == ("NORMAL", 4, 5)


def test_gap_dominates_new_ticks_until_verified_recovery() -> None:
    quality, start_evidence, completion_evidence = subject()
    quality.observe_tick(tick(12))
    quality.observe_tick(tick(11))
    assert quality.state("600000.XSHG").quality == "GAP"

    recovering = quality.begin_recovery("600000.XSHG", start_evidence, reason="BACKFILL_STARTED")
    assert recovering.quality == "RECOVERING"
    normal = quality.complete_recovery("600000.XSHG", completion_evidence)
    assert normal.quality == "NORMAL"
    assert normal.unresolved_gap_count == 0


def test_stale_is_visible_and_unverified_recovery_is_rejected() -> None:
    quality, start_evidence, _ = subject()
    assert quality.mark_stale("600000.XSHG", 10).quality == "DEGRADED"
    assert quality.mark_stale("600000.XSHG", 10).quality == "STALE"
    bad = dict(start_evidence)
    bad["watermark_sequence"] = 11
    with pytest.raises(MarketContractError, match="contiguous"):
        quality.begin_recovery("600000.XSHG", bad, reason="SNAPSHOT_VERIFYING")
