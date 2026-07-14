"""Reference in-memory implementation of TASK-004 persistence semantics.

This adapter is intentionally deterministic and side-effect-free.  It is used by
contract tests to lock the required Repository/Outbox behavior before a concrete
PostgreSQL driver is wired underneath the same ports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from time import monotonic_ns
from types import MappingProxyType
from typing import Any, Literal, cast

from quantiqmt.order.application.persistence.errors import (
    IdempotencyConflict,
    JournalCommitFailed,
    OrderJournalCorrupted,
    UniqueIdentifierCollision,
)
from quantiqmt.order.application.persistence.model import (
    ClaimedMessage,
    ClaimPolicy,
    JournalAppend,
    JsonValue,
    OrderCommit,
    OrderRegistration,
    OrderSnapshot,
    OutboxMutationResult,
    PersistedOrder,
    PublishFailure,
    RecoveryLoad,
    RecoveryPage,
    RegisterOutcome,
    SnapshotLookup,
)
from quantiqmt.order.application.persistence.serialization import (
    journal_checksum,
    snapshot_checksum,
)
from quantiqmt.order.domain import OrderState, OrderVersionConflict
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity, parse_utc, require_utc


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    PUBLISHED = "PUBLISHED"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass(frozen=True, slots=True)
class JournalRecord:
    append: JournalAppend
    previous_entry_checksum: str | None
    entry_checksum: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    message_id: str
    message_type: str
    schema_version: int
    aggregate_id: str | None
    aggregate_version: int | None
    partition_key: str
    envelope: MappingProxyType[str, JsonValue]
    status: OutboxStatus
    attempt_count: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    claim_max_attempts: int | None = None
    claim_initial_retry_delay_ms: int | None = None
    claim_max_retry_delay_ms: int | None = None
    claim_backoff_multiplier: str | None = None
    claim_jitter_ratio: str | None = None
    claimed_by: str | None = None
    claim_token: Identifier | None = None
    lease_until: datetime | None = None
    published_at: datetime | None = None
    last_error_code: str | None = None
    last_error_detail: str | None = None


class InMemoryOrderPersistence:
    """Single-process reference adapter implementing OrderRepository and OutboxStore."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self._orders: dict[str, PersistedOrder] = {}
        self._intent_index: dict[str, str] = {}
        self._client_index: dict[str, str] = {}
        self._journal: dict[str, list[JournalRecord]] = {}
        self._outbox: dict[str, OutboxRecord] = {}
        self._snapshots: dict[str, list[OrderSnapshot]] = {}
        self._now = require_utc(now or datetime.now(UTC))

    @property
    def journal_records(self) -> tuple[JournalRecord, ...]:
        return tuple(record for records in self._journal.values() for record in records)

    @property
    def outbox_records(self) -> tuple[OutboxRecord, ...]:
        return tuple(sorted(self._outbox.values(), key=lambda item: item.message_id))

    def set_now(self, value: datetime) -> None:
        utc_value = require_utc(value)
        if utc_value < self._now:
            raise ValueError("storage transaction clock cannot move backwards")
        self._now = utc_value

    def advance(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            raise ValueError("storage transaction clock cannot move backwards")
        self._now += delta

    def register(self, commit: OrderCommit, *, deadline_monotonic_ns: int) -> RegisterOutcome:
        _require_deadline(deadline_monotonic_ns)
        persisted = commit.persisted_order
        registration = persisted.registration
        order_id = registration.order_id.value
        intent_id = registration.intent_id.value
        client_order_id = registration.client_order_id

        existing_order_id = self._intent_index.get(intent_id)
        if existing_order_id is not None:
            existing = self._orders[existing_order_id]
            if existing.registration_fingerprint != persisted.registration_fingerprint:
                raise IdempotencyConflict("same intent_id has a different registration fingerprint")
            return RegisterOutcome(existing, created=False)

        if order_id in self._orders or client_order_id in self._client_index:
            raise UniqueIdentifierCollision("order_id or client_order_id already exists")
        if persisted.order.version != 1 or commit.journal.aggregate_version != 1:
            raise JournalCommitFailed("register requires aggregate version 1")
        if commit.journal.event_type != "ORDER_REGISTERED":
            raise JournalCommitFailed("register requires ORDER_REGISTERED journal entry")
        if not commit.outbox_messages:
            raise JournalCommitFailed("register requires at least one outbox message")

        records = self._prepare_journal(order_id, commit.journal)
        outbox = self._prepare_outbox(commit)
        self._orders[order_id] = persisted
        self._intent_index[intent_id] = order_id
        self._client_index[client_order_id] = order_id
        self._journal[order_id] = records
        self._outbox.update(outbox)
        return RegisterOutcome(persisted, created=True)

    def get(self, order_id: Identifier, *, deadline_monotonic_ns: int) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        return self._orders.get(order_id.value)

    def get_by_intent(
        self, intent_id: Identifier, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        order_id = self._intent_index.get(intent_id.value)
        return self._orders.get(order_id) if order_id is not None else None

    def get_by_client_order_id(
        self, client_order_id: str, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        order_id = self._client_index.get(client_order_id)
        return self._orders.get(order_id) if order_id is not None else None

    def save(
        self,
        commit: OrderCommit,
        *,
        expected_version: int,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder:
        _require_deadline(deadline_monotonic_ns)
        persisted = commit.persisted_order
        order_id = persisted.registration.order_id.value
        existing = self._orders.get(order_id)
        if existing is None:
            raise JournalCommitFailed("cannot save unknown order")
        if existing.order.version != expected_version:
            raise OrderVersionConflict("expected version does not match stored projection")
        if persisted.order.version != expected_version + 1:
            raise JournalCommitFailed("commit version must equal expected_version + 1")
        if commit.journal.event_type != "ORDER_TRANSITION_APPLIED":
            raise JournalCommitFailed("save requires ORDER_TRANSITION_APPLIED journal entry")

        records = self._prepare_journal(order_id, commit.journal)
        outbox = self._prepare_outbox(commit)
        self._orders[order_id] = persisted
        self._journal[order_id] = records
        self._outbox.update(outbox)
        return persisted

    def load_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> RecoveryLoad:
        _require_deadline(deadline_monotonic_ns)
        records = self._verify_journal_chain(order_id.value)
        persisted = self._persisted_from_journal_records(order_id.value, records)
        if persisted is None:
            raise JournalCommitFailed("order projection is missing")
        return RecoveryLoad(persisted, source="FULL_JOURNAL")

    def list_recovery_order_ids(
        self,
        *,
        scope: Literal["ALL", "ACTIVE_OR_UNKNOWN"],
        page_size: int,
        page_token: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryPage:
        _require_deadline(deadline_monotonic_ns)
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        ids = sorted(self._orders)
        if scope == "ACTIVE_OR_UNKNOWN":
            ids = [
                order_id
                for order_id in ids
                if self._orders[order_id].order.state
                in {
                    OrderState.REGISTERED,
                    OrderState.RISK_PENDING,
                    OrderState.APPROVED,
                    OrderState.SUBMITTING,
                    OrderState.SUBMIT_UNKNOWN,
                    OrderState.SUBMITTED,
                    OrderState.PARTIALLY_FILLED,
                    OrderState.CANCEL_PENDING,
                    OrderState.CANCEL_UNKNOWN,
                    OrderState.SUSPENDED,
                }
            ]
        start = 0 if page_token is None else ids.index(page_token) + 1
        page = ids[start : start + page_size]
        next_token = page[-1] if start + page_size < len(ids) and page else None
        return RecoveryPage(
            tuple(Identifier(value) for value in page),
            next_token,
            next_token is None,
        )

    def rebuild_projection_from_journal(
        self,
        order_id: Identifier,
        *,
        expected_journal_head_checksum: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryLoad:
        _require_deadline(deadline_monotonic_ns)
        records = self._verify_journal_chain(order_id.value)
        if not records:
            raise JournalCommitFailed("journal is missing")
        head = records[-1].entry_checksum
        if expected_journal_head_checksum is not None and expected_journal_head_checksum != head:
            raise OrderVersionConflict("journal head changed during projection rebuild")
        persisted = self._persisted_from_journal_records(order_id.value, records)
        if persisted is None:
            raise JournalCommitFailed("cannot rebuild without committed post-state payload")
        self._orders[order_id.value] = persisted
        return RecoveryLoad(persisted, source="FULL_JOURNAL")

    def write(self, snapshot: OrderSnapshot, *, deadline_monotonic_ns: int) -> None:
        _require_deadline(deadline_monotonic_ns)
        self._snapshots.setdefault(snapshot.order_id.value, []).append(snapshot)

    def latest_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> SnapshotLookup:
        _require_deadline(deadline_monotonic_ns)
        candidates = sorted(
            self._snapshots.get(order_id.value, ()),
            key=lambda item: item.aggregate_version,
            reverse=True,
        )
        if not candidates:
            return SnapshotLookup(None, "ABSENT")
        records = self._journal.get(order_id.value, [])
        selected = candidates[0]
        head = next(
            (
                record.entry_checksum
                for record in records
                if record.append.aggregate_version == selected.aggregate_version
            ),
            None,
        )
        if (
            snapshot_checksum(selected.state_payload) != selected.snapshot_checksum
            or selected.journal_head_checksum != head
        ):
            return SnapshotLookup(
                None,
                "INVALID_DISCARDED",
                diagnostic_code="QQ-STORAGE-7003",
                diagnostic_detail="snapshot checksum or journal head checksum mismatch",
                invalid_snapshot_id=selected.snapshot_id,
                invalid_aggregate_version=selected.aggregate_version,
            )
        return SnapshotLookup(selected, "VALID")

    def claim(
        self, worker_id: str, policy: ClaimPolicy, *, deadline_monotonic_ns: int
    ) -> tuple[ClaimedMessage, ...]:
        _require_deadline(deadline_monotonic_ns)
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        for message_id, record in tuple(self._outbox.items()):
            if (
                record.status is OutboxStatus.PENDING
                or (
                    record.status is OutboxStatus.CLAIMED
                    and _expired(record.lease_until, self._now)
                )
            ) and record.attempt_count >= policy.max_attempts:
                self._outbox[message_id] = replace(
                    record,
                    status=OutboxStatus.DEAD_LETTER,
                    claimed_by=None,
                    claim_token=None,
                    lease_until=None,
                    last_error_code="MAX_ATTEMPTS_REACHED",
                    last_error_detail="outbox max_attempts reached before claim",
                    updated_at=self._now,
                )
        selected = [
            record
            for record in sorted(
                self._outbox.values(),
                key=lambda item: (item.available_at, item.created_at, item.message_id),
            )
            if (
                record.status is OutboxStatus.PENDING
                and record.attempt_count < policy.max_attempts
                and record.available_at <= self._now
            )
            or (
                record.status is OutboxStatus.CLAIMED
                and record.attempt_count < policy.max_attempts
                and _expired(record.lease_until, self._now)
            )
        ][: policy.batch_size]
        claimed: list[ClaimedMessage] = []
        for record in selected:
            token = Identifier.new()
            lease_until = self._now + timedelta(milliseconds=policy.lease_duration_ms)
            updated = replace(
                record,
                status=OutboxStatus.CLAIMED,
                attempt_count=record.attempt_count + 1,
                claim_max_attempts=policy.max_attempts,
                claim_initial_retry_delay_ms=policy.initial_retry_delay_ms,
                claim_max_retry_delay_ms=policy.max_retry_delay_ms,
                claim_backoff_multiplier=policy.backoff_multiplier,
                claim_jitter_ratio=policy.jitter_ratio,
                claimed_by=worker_id,
                claim_token=token,
                lease_until=lease_until,
                updated_at=self._now,
            )
            self._outbox[record.message_id] = updated
            claimed.append(_claimed_message(updated))
        return tuple(claimed)

    def mark_published(
        self, message_id: str, claim_token: Identifier, *, deadline_monotonic_ns: int
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        record = self._outbox.get(message_id)
        if not self._owns_live_claim(record, claim_token):
            return OutboxMutationResult(False, "QQ-STORAGE-7004", "claim token missing or expired")
        assert record is not None
        self._outbox[message_id] = replace(
            record,
            status=OutboxStatus.PUBLISHED,
            claimed_by=None,
            claim_token=None,
            lease_until=None,
            published_at=self._now,
            updated_at=self._now,
        )
        return OutboxMutationResult(True, "OK")

    def release_failed(
        self,
        message_id: str,
        claim_token: Identifier,
        failure: PublishFailure,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        record = self._outbox.get(message_id)
        if not self._owns_live_claim(record, claim_token):
            return OutboxMutationResult(False, "QQ-STORAGE-7004", "claim token missing or expired")
        assert record is not None
        max_attempts = record.claim_max_attempts or 1
        should_retry = failure.retryable and record.attempt_count < max_attempts
        status = OutboxStatus.PENDING if should_retry else OutboxStatus.DEAD_LETTER
        available_at = (
            self._now + timedelta(milliseconds=_retry_delay_ms(record))
            if should_retry
            else record.available_at
        )
        self._outbox[message_id] = replace(
            record,
            status=status,
            claimed_by=None,
            claim_token=None,
            lease_until=None,
            available_at=available_at,
            last_error_code=(
                "MAX_ATTEMPTS_REACHED"
                if failure.retryable and not should_retry
                else failure.error_code
            ),
            last_error_detail=failure.error_detail,
            updated_at=self._now,
        )
        return OutboxMutationResult(True, "OK")

    def renew(
        self,
        message_id: str,
        claim_token: Identifier,
        policy: ClaimPolicy,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        record = self._outbox.get(message_id)
        if not self._owns_live_claim(record, claim_token):
            return OutboxMutationResult(False, "QQ-STORAGE-7004", "claim token missing or expired")
        assert record is not None
        self._outbox[message_id] = replace(
            record,
            lease_until=self._now + timedelta(milliseconds=policy.lease_duration_ms),
            updated_at=self._now,
        )
        return OutboxMutationResult(True, "OK")

    def _prepare_journal(self, order_id: str, append: JournalAppend) -> list[JournalRecord]:
        current = list(self._journal.get(order_id, ()))
        expected_version = len(current) + 1
        if append.aggregate_version != expected_version:
            raise JournalCommitFailed("journal versions must be contiguous")
        previous = current[-1].entry_checksum if current else None
        current.append(
            JournalRecord(
                append,
                previous,
                journal_checksum(append, previous),
                recorded_at=self._now,
            )
        )
        return current

    def _prepare_outbox(self, commit: OrderCommit) -> dict[str, OutboxRecord]:
        prepared: dict[str, OutboxRecord] = {}
        for message in commit.outbox_messages:
            primitive = message.to_primitive()
            message_id = str(primitive["message_id"])
            if message_id in self._outbox or message_id in prepared:
                raise JournalCommitFailed("duplicate outbox message_id")
            prepared[message_id] = OutboxRecord(
                message_id=message_id,
                message_type=str(primitive["message_type"]),
                schema_version=_required_int(primitive["schema_version"]),
                aggregate_id=_optional_str(primitive.get("aggregate_id")),
                aggregate_version=_optional_int(primitive.get("aggregate_version")),
                partition_key=str(primitive["partition_key"]),
                envelope=MappingProxyType(
                    {key: _strict_json_value(value) for key, value in primitive.items()}
                ),
                status=OutboxStatus.PENDING,
                attempt_count=0,
                available_at=self._now,
                created_at=self._now,
                updated_at=self._now,
            )
        return prepared

    def _verify_journal_chain(self, order_id: str) -> list[JournalRecord]:
        records = self._journal.get(order_id, [])
        previous: str | None = None
        for expected, record in enumerate(records, start=1):
            if record.append.aggregate_version != expected:
                raise OrderJournalCorrupted("journal version gap detected")
            if record.previous_entry_checksum != previous:
                raise OrderJournalCorrupted("journal previous checksum mismatch")
            if journal_checksum(record.append, previous) != record.entry_checksum:
                raise OrderJournalCorrupted("journal checksum mismatch")
            previous = record.entry_checksum
        return records

    def _persisted_from_journal_records(
        self, order_id: str, records: list[JournalRecord]
    ) -> PersistedOrder | None:
        if not records:
            return None
        post_state = records[-1].append.payload.get("post_state")
        if not isinstance(post_state, Mapping):
            raise JournalCommitFailed("journal entry is missing committed post_state")
        current = self._orders.get(order_id)
        fingerprint = (
            current.registration_fingerprint
            if current is not None
            else str(post_state.get("registration_fingerprint", ""))
        )
        if not fingerprint:
            return None
        return _persisted_from_state_payload(post_state, fingerprint)

    def _owns_live_claim(self, record: OutboxRecord | None, claim_token: Identifier) -> bool:
        return bool(
            record
            and record.status is OutboxStatus.CLAIMED
            and record.claim_token == claim_token
            and record.lease_until is not None
            and record.lease_until > self._now
        )


def _require_deadline(deadline_monotonic_ns: int) -> None:
    if not isinstance(deadline_monotonic_ns, int) or deadline_monotonic_ns <= 0:
        raise ValueError("deadline_monotonic_ns is required and must be positive")
    if deadline_monotonic_ns <= monotonic_ns():
        raise TimeoutError("deadline_monotonic_ns has expired")


def _expired(value: datetime | None, now: datetime) -> bool:
    return value is None or value <= now


def _retry_delay_ms(record: OutboxRecord) -> int:
    initial = record.claim_initial_retry_delay_ms or 10
    maximum = record.claim_max_retry_delay_ms or initial
    multiplier = Decimal(record.claim_backoff_multiplier or "1")
    exponent = max(record.attempt_count - 1, 0)
    delay = Decimal(initial) * (multiplier**exponent)
    return int(min(delay, Decimal(maximum)).to_integral_value(rounding=ROUND_CEILING))


def _claimed_message(record: OutboxRecord) -> ClaimedMessage:
    assert record.claim_token is not None
    assert record.lease_until is not None
    return ClaimedMessage(
        message_id=record.message_id,
        message_type=record.message_type,
        aggregate_id=record.aggregate_id,
        aggregate_version=record.aggregate_version,
        partition_key=record.partition_key,
        envelope=record.envelope,
        claim_token=record.claim_token,
        lease_until=record.lease_until,
        attempt_count=record.attempt_count,
    )


def _persisted_from_state_payload(
    payload: Mapping[str, Any], registration_fingerprint: str
) -> PersistedOrder:
    registration_payload = cast(Mapping[str, Any], payload["registration"])
    registration = OrderRegistration(
        Identifier(str(registration_payload["order_id"])),
        Identifier(str(registration_payload["intent_id"])),
        str(registration_payload["client_order_id"]),
        str(registration_payload["account_id"]),
        InstrumentId(str(registration_payload["instrument_id"])),
        registration_payload["side"],
        registration_payload["position_effect"],
        registration_payload["order_type"],
        Quantity(int(registration_payload["quantity"])),
        Price(str(registration_payload["limit_price"]))
        if registration_payload["limit_price"] is not None
        else None,
        registration_payload["time_in_force"],
        str(registration_payload["owner_strategy_id"]),
        str(registration_payload["owner_strategy_version"]),
        parse_utc(str(registration_payload["registered_at"])),
    )
    from quantiqmt.order.domain import FactIdentity, Order, ProcessedFact

    order = Order(
        Identifier(str(payload["order_id"])),
        Quantity(int(payload["quantity"])),
        state=OrderState(str(payload["state"])),
        cumulative_quantity=Quantity(int(payload["cumulative_quantity"])),
        version=int(payload["aggregate_version"]),
        processed_facts={
            FactIdentity(str(item["namespace"]), str(item["key"])): ProcessedFact(
                str(item["fingerprint"]),
                Quantity(int(item["trade_quantity"]))
                if item.get("trade_quantity") is not None
                else None,
            )
            for item in cast(list[Mapping[str, Any]], payload.get("processed_facts", []))
        },
        fact_conflicts={
            FactIdentity(str(item["namespace"]), str(item["key"])): frozenset(
                str(value) for value in cast(list[object], item["conflicting_fingerprints"])
            )
            for item in cast(list[Mapping[str, Any]], payload.get("fact_conflicts", []))
        },
        broker_sequences={
            str(item["stream"]): int(item["last_observed_sequence"])
            for item in cast(list[Mapping[str, Any]], payload.get("broker_sequences", []))
        },
    )
    return PersistedOrder(registration, order, registration_fingerprint)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("value must be an integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _strict_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise TypeError("outbox envelope must not contain float")
    if isinstance(value, list | tuple):
        return tuple(_strict_json_value(item) for item in value)
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("outbox envelope object keys must be strings")
        return MappingProxyType({key: _strict_json_value(item) for key, item in value.items()})
    raise TypeError(f"unsupported outbox envelope value {type(value).__name__}")
