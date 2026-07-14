"""Immutable DTOs for the Order persistence and transactional outbox ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Literal

from quantiqmt.contracts import MessageEnvelope
from quantiqmt.order.domain import Order
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity, require_utc

type JsonValue = None | bool | int | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]
type MutableJsonValue = (
    None | bool | int | str | list[MutableJsonValue] | dict[str, MutableJsonValue]
)


@dataclass(frozen=True, slots=True)
class OrderRegistrationDraft:
    order_id: Identifier
    intent_id: Identifier
    account_id: str
    instrument_id: InstrumentId
    side: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE", "AUTO"]
    order_type: Literal["LIMIT", "MARKET", "BEST"]
    quantity: Quantity
    limit_price: Price | None
    time_in_force: Literal["DAY", "IOC", "FOK"]
    owner_strategy_id: str
    owner_strategy_version: str
    registered_at: datetime

    def __post_init__(self) -> None:
        _validate_registration_common(self)
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("LIMIT order registration requires limit_price")


@dataclass(frozen=True, slots=True)
class OrderRegistration:
    order_id: Identifier
    intent_id: Identifier
    client_order_id: str
    account_id: str
    instrument_id: InstrumentId
    side: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE", "AUTO"]
    order_type: Literal["LIMIT", "MARKET", "BEST"]
    quantity: Quantity
    limit_price: Price | None
    time_in_force: Literal["DAY", "IOC", "FOK"]
    owner_strategy_id: str
    owner_strategy_version: str
    registered_at: datetime

    def __post_init__(self) -> None:
        _validate_registration_common(self)
        if not 1 <= len(self.client_order_id) <= 128:
            raise ValueError("client_order_id length must be between 1 and 128")
        if self.client_order_id != self.client_order_id.strip():
            raise ValueError("client_order_id must not contain surrounding whitespace")
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("LIMIT order registration requires limit_price")


@dataclass(frozen=True, slots=True)
class PersistedOrder:
    registration: OrderRegistration
    order: Order
    registration_fingerprint: str

    def __post_init__(self) -> None:
        if self.registration.order_id != self.order.order_id:
            raise ValueError("registration order_id must match aggregate order_id")
        if self.registration.quantity != self.order.quantity:
            raise ValueError("registration quantity must match aggregate quantity")
        _require_sha256_hex(self.registration_fingerprint, "registration_fingerprint")


@dataclass(frozen=True, slots=True)
class JournalAppend:
    journal_id: Identifier
    order_id: Identifier
    aggregate_version: int
    event_type: Literal["ORDER_REGISTERED", "ORDER_TRANSITION_APPLIED"]
    payload: Mapping[str, JsonValue]
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if self.aggregate_version < 1:
            raise ValueError("journal aggregate_version must be >= 1")
        object.__setattr__(self, "payload", _freeze_json_object(self.payload))
        require_utc(self.occurred_at)
        if not 16 <= len(self.correlation_id) <= 64:
            raise ValueError("correlation_id length must be between 16 and 64")
        if self.causation_id is not None and not 16 <= len(self.causation_id) <= 64:
            raise ValueError("causation_id length must be between 16 and 64")


@dataclass(frozen=True, slots=True)
class OrderCommit:
    persisted_order: PersistedOrder
    journal: JournalAppend
    outbox_messages: tuple[MessageEnvelope, ...]

    def __post_init__(self) -> None:
        if self.journal.order_id != self.persisted_order.registration.order_id:
            raise ValueError("journal order_id must match persisted order")
        if self.journal.aggregate_version != self.persisted_order.order.version:
            raise ValueError("journal version must match aggregate version")
        object.__setattr__(self, "outbox_messages", tuple(self.outbox_messages))


@dataclass(frozen=True, slots=True)
class RegisterOutcome:
    persisted_order: PersistedOrder
    created: bool


@dataclass(frozen=True, slots=True)
class RecoveryLoad:
    persisted_order: PersistedOrder
    source: Literal["SNAPSHOT_PLUS_JOURNAL", "FULL_JOURNAL"]
    snapshot_diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    snapshot_id: Identifier
    order_id: Identifier
    aggregate_version: int
    schema_version: int
    state_payload: Mapping[str, JsonValue]
    journal_head_checksum: str
    snapshot_checksum: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.aggregate_version < 1:
            raise ValueError("snapshot aggregate_version must be >= 1")
        if self.schema_version != 1:
            raise ValueError("snapshot schema_version must be 1")
        object.__setattr__(self, "state_payload", _freeze_json_object(self.state_payload))
        _require_sha256_hex(self.journal_head_checksum, "journal_head_checksum")
        _require_sha256_hex(self.snapshot_checksum, "snapshot_checksum")
        require_utc(self.created_at)


@dataclass(frozen=True, slots=True)
class RecoveryPage:
    order_ids: tuple[Identifier, ...]
    next_page_token: str | None
    complete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_ids", tuple(self.order_ids))


@dataclass(frozen=True, slots=True)
class SnapshotLookup:
    snapshot: OrderSnapshot | None
    status: Literal["VALID", "ABSENT", "INVALID_DISCARDED"]
    diagnostic_code: Literal["QQ-STORAGE-7003"] | None = None
    diagnostic_detail: str | None = None
    invalid_snapshot_id: Identifier | None = None
    invalid_aggregate_version: int | None = None

    def __post_init__(self) -> None:
        if self.status == "VALID" and self.snapshot is None:
            raise ValueError("VALID snapshot lookup requires snapshot")
        if self.status != "VALID" and self.snapshot is not None:
            raise ValueError("non-VALID snapshot lookup must not carry snapshot")
        if self.status == "INVALID_DISCARDED" and self.diagnostic_code != "QQ-STORAGE-7003":
            raise ValueError("invalid snapshot lookup must carry QQ-STORAGE-7003")


@dataclass(frozen=True, slots=True)
class ClientOrderIdCandidate:
    value: str
    broker: str
    account_id: str
    capability_version: str

    def __post_init__(self) -> None:
        for field, value in (
            ("value", self.value),
            ("broker", self.broker),
            ("account_id", self.account_id),
            ("capability_version", self.capability_version),
        ):
            if not value.strip():
                raise ValueError(f"{field} must be non-empty")
        if len(self.value) > 128:
            raise ValueError("client order id candidate exceeds 128 characters")


@dataclass(frozen=True, slots=True)
class ClaimPolicy:
    batch_size: int
    lease_duration_ms: int
    max_attempts: int
    initial_retry_delay_ms: int
    max_retry_delay_ms: int
    backoff_multiplier: str
    jitter_ratio: str

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if not 1000 <= self.lease_duration_ms <= 300000:
            raise ValueError("lease_duration_ms must be between 1000 and 300000")
        if not 1 <= self.max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        if not 10 <= self.initial_retry_delay_ms <= 60000:
            raise ValueError("initial_retry_delay_ms must be between 10 and 60000")
        if not 10 <= self.max_retry_delay_ms <= 3600000:
            raise ValueError("max_retry_delay_ms must be between 10 and 3600000")
        if self.max_retry_delay_ms < self.initial_retry_delay_ms:
            raise ValueError("retry delay bounds are invalid")
        multiplier = _decimal_config(self.backoff_multiplier, "backoff_multiplier")
        if not Decimal("1") < multiplier <= Decimal("10"):
            raise ValueError("backoff_multiplier must be > 1 and <= 10")
        jitter = _decimal_config(self.jitter_ratio, "jitter_ratio")
        if not Decimal("0") <= jitter <= Decimal("1"):
            raise ValueError("jitter_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ClaimedMessage:
    message_id: str
    message_type: str
    aggregate_id: str | None
    aggregate_version: int | None
    partition_key: str
    envelope: Mapping[str, JsonValue]
    claim_token: Identifier
    lease_until: datetime
    attempt_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "envelope", _freeze_json_object(self.envelope))
        require_utc(self.lease_until)
        if self.attempt_count < 1:
            raise ValueError("attempt_count must be positive after claim")


@dataclass(frozen=True, slots=True)
class PublishFailure:
    error_code: str
    error_detail: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.error_code.strip():
            raise ValueError("error_code must be non-empty")
        if len(self.error_detail) > 2048:
            raise ValueError("error_detail exceeds 2048 characters")


@dataclass(frozen=True, slots=True)
class OutboxMutationResult:
    applied: bool
    code: Literal["OK", "QQ-STORAGE-7004"]
    detail: str | None = None


def _validate_registration_common(value: OrderRegistration | OrderRegistrationDraft) -> None:
    value.quantity.require_positive()
    require_utc(value.registered_at)
    for field, text, maximum in (
        ("account_id", value.account_id, 128),
        ("owner_strategy_id", value.owner_strategy_id, 128),
        ("owner_strategy_version", value.owner_strategy_version, 64),
    ):
        if not 1 <= len(text) <= maximum or text != text.strip():
            raise ValueError(f"{field} must be non-empty and at most {maximum} characters")


def _require_sha256_hex(value: str, field: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field} must be lowercase sha256 hex")


def _decimal_config(value: str, field: str) -> Decimal:
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal string") from exc
    if not decimal.is_finite():
        raise ValueError(f"{field} must be finite")
    return decimal


def _freeze_json(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise TypeError("JSON value must not contain float")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return _freeze_json_object(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def _freeze_json_object(value: Mapping[str, object]) -> Mapping[str, JsonValue]:
    return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
