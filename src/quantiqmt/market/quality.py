"""Fail-visible Market quality state and immutable transition evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from quantiqmt.contracts.canonical import canonical_sha256
from quantiqmt.market.errors import IdentityCollisionError, MarketContractError
from quantiqmt.market.validation import (
    CHECKPOINT_PROJECTION,
    SNAPSHOT_PROJECTION,
    projection_checksum,
)


@dataclass(frozen=True, slots=True)
class QualityState:
    provider: str
    instrument_id: str
    calendar_id: str
    calendar_version: str
    session_id: str
    quality: str
    quality_version: int
    source_version: int
    unresolved_gap_count: int = 0
    gap_start_sequence: int | None = None
    gap_end_sequence: int | None = None
    reason_code: str = "INITIAL_BASELINE_VERIFIED"


class RecoveryEvidenceRegistry:
    """Immutable exact-identity Snapshot/Checkpoint evidence authority."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, object]] = {}
        self._checkpoints: dict[str, dict[str, object]] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}

    def register_snapshot(self, identity: str, snapshot: Mapping[str, object]) -> None:
        if (
            snapshot.get("content_checksum") != projection_checksum(snapshot, SNAPSHOT_PROJECTION)
            or snapshot.get("checksum_verified") is not True
        ):
            raise MarketContractError("recovery Snapshot checksum is invalid")
        self._register("snapshot", identity, snapshot, self._snapshots)

    def register_checkpoint(self, identity: str, checkpoint: Mapping[str, object]) -> None:
        if checkpoint.get("checkpoint_checksum") != projection_checksum(
            checkpoint, CHECKPOINT_PROJECTION
        ):
            raise MarketContractError("recovery Checkpoint checksum is invalid")
        self._register("checkpoint", identity, checkpoint, self._checkpoints)

    def verify(self, evidence: Mapping[str, object], state: QualityState) -> None:
        snapshot_id = evidence.get("snapshot_identity")
        checkpoint_id = evidence.get("checkpoint_identity")
        if not isinstance(snapshot_id, str) or not isinstance(checkpoint_id, str):
            raise MarketContractError("recovery evidence identities are missing")
        snapshot = self._snapshots.get(snapshot_id)
        checkpoint = self._checkpoints.get(checkpoint_id)
        if snapshot is None or checkpoint is None:
            raise MarketContractError("recovery evidence identity is unresolved")
        if evidence.get("snapshot_checksum") != snapshot.get("content_checksum"):
            raise MarketContractError("recovery Snapshot checksum mismatch")
        if evidence.get("checkpoint_checksum") != checkpoint.get("checkpoint_checksum"):
            raise MarketContractError("recovery Checkpoint checksum mismatch")
        for resolved in (snapshot, checkpoint):
            for field in (
                "provider",
                "instrument_id",
                "calendar_id",
                "calendar_version",
                "session_id",
            ):
                if resolved.get(field) != getattr(state, field):
                    raise MarketContractError("resolved recovery object identity mismatch")
            for field in ("source_version", "quality_version"):
                if resolved.get(field) != evidence.get(field):
                    raise MarketContractError("resolved recovery object version mismatch")

    def verify_event(self, payload: Mapping[str, object], evidence: Mapping[str, object]) -> None:
        state = QualityState(
            provider=cast(str, payload["provider"]),
            instrument_id=cast(str, payload["instrument_id"]),
            calendar_id=cast(str, payload["calendar_id"]),
            calendar_version=cast(str, payload["calendar_version"]),
            session_id=cast(str, payload["session_id"]),
            quality=cast(str, payload["previous_quality"]),
            quality_version=cast(int, payload["previous_quality_version"]),
            source_version=cast(int, payload["previous_source_version"]),
        )
        self.verify(evidence, state)

    def _register(
        self,
        kind: str,
        identity: str,
        value: Mapping[str, object],
        destination: dict[str, dict[str, object]],
    ) -> None:
        fingerprint = canonical_sha256(dict(value))
        key = (kind, identity)
        previous = self._fingerprints.get(key)
        if previous is not None:
            if previous != fingerprint:
                raise IdentityCollisionError(f"recovery {kind} identity collision")
            return
        self._fingerprints[key] = fingerprint
        destination[identity] = dict(value)


class MarketQuality:
    """Per-instrument monotonic quality pipeline."""

    def __init__(self, recovery_registry: RecoveryEvidenceRegistry | None = None) -> None:
        self._states: dict[str, QualityState] = {}
        self._fingerprints: dict[tuple[str, str, int], str] = {}
        self._recovery_registry = recovery_registry

    def baseline(
        self,
        *,
        provider: str,
        instrument_id: str,
        calendar_id: str,
        calendar_version: str,
        session_id: str,
        source_version: int,
        quality_version: int,
    ) -> QualityState:
        state = self._states.get(instrument_id)
        if state is None:
            state = QualityState(
                provider,
                instrument_id,
                calendar_id,
                calendar_version,
                session_id,
                "NORMAL",
                quality_version,
                source_version,
            )
            self._states[instrument_id] = state
        return state

    def state(self, instrument_id: str) -> QualityState:
        try:
            return self._states[instrument_id]
        except KeyError as exc:
            raise MarketContractError(f"quality baseline is missing: {instrument_id}") from exc

    @property
    def states(self) -> tuple[QualityState, ...]:
        return tuple(self._states.values())

    def observe_tick(self, payload: dict[str, object]) -> QualityState:
        instrument = str(payload["instrument_id"])
        state = self.state(instrument)
        sequence = _evidence_int(payload, "source_sequence")
        identity = (state.provider, instrument, sequence)
        fingerprint = canonical_sha256(payload)
        previous = self._fingerprints.get(identity)
        if previous is not None:
            if previous != fingerprint:
                raise IdentityCollisionError("market tick identity collision")
            return state
        if sequence < state.source_version:
            raise MarketContractError("source sequence regression")
        self._fingerprints[identity] = fingerprint
        if sequence > state.source_version + 1:
            return self._gap(state, state.source_version + 1, sequence - 1, sequence)
        self._states[instrument] = QualityState(
            state.provider,
            state.instrument_id,
            state.calendar_id,
            state.calendar_version,
            state.session_id,
            state.quality,
            state.quality_version,
            max(state.source_version, sequence),
            state.unresolved_gap_count,
            state.gap_start_sequence,
            state.gap_end_sequence,
            state.reason_code,
        )
        return self._states[instrument]

    def overflow(self, instrument_id: str, sequence: int) -> QualityState:
        return self._gap(self.state(instrument_id), sequence, sequence, sequence)

    def mark_stale(self, instrument_id: str, source_version: int) -> QualityState:
        state = self.state(instrument_id)
        if state.quality in {"GAP", "UNAVAILABLE", "RECOVERING"}:
            return state
        if state.quality == "NORMAL":
            state = QualityState(
                state.provider,
                state.instrument_id,
                state.calendar_id,
                state.calendar_version,
                state.session_id,
                "DEGRADED",
                state.quality_version + 1,
                max(state.source_version, source_version),
                state.unresolved_gap_count,
                state.gap_start_sequence,
                state.gap_end_sequence,
                "SOURCE_LAG",
            )
        elif state.quality == "DEGRADED":
            state = QualityState(
                state.provider,
                state.instrument_id,
                state.calendar_id,
                state.calendar_version,
                state.session_id,
                "STALE",
                state.quality_version + 1,
                max(state.source_version, source_version),
                state.unresolved_gap_count,
                state.gap_start_sequence,
                state.gap_end_sequence,
                "STALE_DEADLINE_EXCEEDED",
            )
        self._states[instrument_id] = state
        return state

    def begin_recovery(
        self, instrument_id: str, evidence: Mapping[str, object], *, reason: str
    ) -> QualityState:
        state = self.state(instrument_id)
        if (state.quality, reason) not in {
            ("UNAVAILABLE", "SNAPSHOT_VERIFYING"),
            ("UNAVAILABLE", "BACKFILL_STARTED"),
            ("GAP", "BACKFILL_STARTED"),
            ("STALE", "SNAPSHOT_VERIFYING"),
        }:
            raise MarketContractError("illegal recovery start transition")
        self._validate_recovery(state, evidence)
        self._verify_resolved_recovery(evidence, state)
        current = QualityState(
            state.provider,
            state.instrument_id,
            state.calendar_id,
            state.calendar_version,
            state.session_id,
            "RECOVERING",
            state.quality_version + 1,
            _evidence_int(evidence, "source_version"),
            state.unresolved_gap_count,
            None,
            None,
            reason,
        )
        self._states[instrument_id] = current
        return current

    def complete_recovery(self, instrument_id: str, evidence: Mapping[str, object]) -> QualityState:
        state = self.state(instrument_id)
        if state.quality != "RECOVERING":
            raise MarketContractError("only RECOVERING can enter NORMAL")
        self._validate_recovery(state, evidence, allow_previous_version=True)
        self._verify_resolved_recovery(evidence, state)
        if _evidence_int(evidence, "watermark_sequence") < _evidence_int(
            evidence, "source_version"
        ):
            raise MarketContractError("recovery watermark does not cover source version")
        current = QualityState(
            state.provider,
            state.instrument_id,
            state.calendar_id,
            state.calendar_version,
            state.session_id,
            "NORMAL",
            state.quality_version + 1,
            _evidence_int(evidence, "source_version"),
            0,
            None,
            None,
            "RECOVERY_VERIFIED",
        )
        self._states[instrument_id] = current
        return current

    def _verify_resolved_recovery(
        self, evidence: Mapping[str, object], state: QualityState
    ) -> None:
        if self._recovery_registry is None:
            raise MarketContractError("immutable recovery evidence registry is unavailable")
        self._recovery_registry.verify(evidence, state)

    def _gap(self, state: QualityState, start: int, end: int, source_version: int) -> QualityState:
        if state.quality == "UNAVAILABLE":
            return state
        if state.quality == "GAP":
            current = QualityState(
                state.provider,
                state.instrument_id,
                state.calendar_id,
                state.calendar_version,
                state.session_id,
                "GAP",
                state.quality_version,
                max(state.source_version, source_version),
                state.unresolved_gap_count + 1,
                min(cast(int, state.gap_start_sequence), start),
                max(cast(int, state.gap_end_sequence), end),
                "SOURCE_SEQUENCE_GAP",
            )
            self._states[state.instrument_id] = current
            return current
        current = QualityState(
            state.provider,
            state.instrument_id,
            state.calendar_id,
            state.calendar_version,
            state.session_id,
            "GAP",
            state.quality_version + 1,
            max(state.source_version, source_version),
            state.unresolved_gap_count + 1,
            start,
            end,
            "SOURCE_SEQUENCE_GAP",
        )
        self._states[state.instrument_id] = current
        return current

    @staticmethod
    def _validate_recovery(
        state: QualityState,
        evidence: Mapping[str, object],
        *,
        allow_previous_version: bool = False,
    ) -> None:
        for field in ("provider", "instrument_id", "calendar_id", "calendar_version", "session_id"):
            if evidence.get(field) != getattr(state, field):
                raise MarketContractError("recovery evidence identity mismatch")
        required_ints = (
            "backfill_start_sequence",
            "backfill_end_sequence",
            "gap_start_sequence",
            "gap_end_sequence",
            "watermark_sequence",
            "previous_source_version",
            "source_version",
            "previous_quality_version",
            "quality_version",
        )
        if any(
            isinstance(evidence.get(field), bool) or not isinstance(evidence.get(field), int)
            for field in required_ints
        ):
            raise MarketContractError("recovery evidence range is malformed")
        if not (
            evidence["backfill_start_sequence"] == evidence["gap_start_sequence"]
            and evidence["backfill_end_sequence"] == evidence["gap_end_sequence"]
            and _evidence_int(evidence, "gap_start_sequence")
            <= _evidence_int(evidence, "gap_end_sequence")
            and _evidence_int(evidence, "gap_end_sequence")
            <= _evidence_int(evidence, "source_version")
            and _evidence_int(evidence, "watermark_sequence")
            >= _evidence_int(evidence, "source_version")
        ):
            raise MarketContractError("recovery evidence is not contiguous")
        if (
            _evidence_int(evidence, "previous_quality_version") != state.quality_version
            or _evidence_int(evidence, "quality_version") != state.quality_version + 1
        ):
            raise MarketContractError("recovery quality version mismatch")
        if (
            not allow_previous_version
            and _evidence_int(evidence, "previous_source_version") > state.source_version
        ):
            raise MarketContractError("recovery evidence starts beyond current source version")
        for field in ("snapshot_checksum", "checkpoint_checksum"):
            value = evidence.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise MarketContractError("recovery checksum is malformed")


def _evidence_int(value: Mapping[str, object], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise MarketContractError(f"{field} must be an integer")
    return item
