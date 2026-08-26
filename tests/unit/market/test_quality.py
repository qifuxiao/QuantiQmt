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
        "backfill_end_sequence": 12,
        "gap_start_sequence": 11,
        "gap_end_sequence": 12,
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


def test_gap_dominates_new_ticks_until_verified_recovery() -> None:
    quality, start_evidence, completion_evidence = subject()
    quality.overflow("600000.XSHG", 11)
    quality.observe_tick(
        {
            "provider": "SIM",
            "instrument_id": "600000.XSHG",
            "source_sequence": 12,
            "event_id": "550e8400-e29b-41d4-a716-446655440012",
        }
    )
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
