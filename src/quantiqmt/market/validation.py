"""Market schema and semantic validation shared by all runtime boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.canonical import canonical_sha256
from quantiqmt.contracts.model import MessageEnvelope
from quantiqmt.contracts.tzdb import FrozenTzdb
from quantiqmt.contracts.validation import validate
from quantiqmt.market.errors import MarketContractError

SAFE_INTEGER_MAX = 9_007_199_254_740_991
QUALITY_PRIORITY = {
    "NORMAL": 0,
    "DEGRADED": 1,
    "RECOVERING": 2,
    "STALE": 3,
    "GAP": 4,
    "UNAVAILABLE": 5,
}
POLICY_PROJECTION = (
    "dto_type",
    "schema_version",
    "provider",
    "generation",
    "calendar_id",
    "calendar_version",
    "session_id",
    "policy_version",
    "aggregation_policy_version",
    "activated_at",
    "snapshot_max_age_ms",
    "future_clock_skew_ms",
    "queue_capacity",
    "warning_watermark",
    "critical_watermark",
    "overflow_watermark",
    "source_lag_stale_ms",
    "tzdb_version",
)
SNAPSHOT_PROJECTION = (
    "dto_type",
    "schema_version",
    "provider",
    "generation",
    "instrument_id",
    "calendar_id",
    "calendar_version",
    "session_id",
    "as_of",
    "source_version",
    "source_sequence",
    "quality_version",
    "aggregation_policy_version",
    "quality",
    "stale",
    "unresolved_gap_count",
)
CHECKPOINT_PROJECTION = (
    "dto_type",
    "schema_version",
    "provider",
    "instrument_id",
    "calendar_id",
    "calendar_version",
    "session_id",
    "source_version",
    "quality_version",
    "aggregation_policy_version",
    "watermark_sequence",
    "watermark_event_time",
    "last_final_sequence",
)
CALENDAR_PROJECTION = (
    "dto_type",
    "schema_version",
    "calendar_id",
    "calendar_version",
    "exchange",
    "timezone",
    "tzdb_version",
    "trading_day",
    "sessions",
)
BAR_PROJECTION = (
    "partition_key",
    "provider",
    "instrument_id",
    "exchange",
    "calendar_id",
    "calendar_version",
    "session_id",
    "trading_day",
    "session_open_at",
    "session_close_at",
    "timeframe_seconds",
    "allowed_lateness_ms",
    "window_start",
    "window_end",
    "event_time",
    "received_at",
    "watermark_event_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "source_sequence_start",
    "source_sequence_end",
    "watermark_sequence",
    "quality",
    "gap_start_sequence",
    "gap_end_sequence",
    "partial",
    "final",
    "revision",
    "aggregation_policy_version",
)
QUALITY_TRANSITIONS = {
    ("UNAVAILABLE", "RECOVERING", "SNAPSHOT_VERIFYING"),
    ("UNAVAILABLE", "RECOVERING", "BACKFILL_STARTED"),
    ("GAP", "RECOVERING", "BACKFILL_STARTED"),
    ("STALE", "RECOVERING", "SNAPSHOT_VERIFYING"),
    ("RECOVERING", "NORMAL", "RECOVERY_VERIFIED"),
    ("UNAVAILABLE", "NORMAL", "INITIAL_BASELINE_VERIFIED"),
    ("NORMAL", "DEGRADED", "BACKPRESSURE"),
    ("NORMAL", "DEGRADED", "SOURCE_LAG"),
    ("DEGRADED", "STALE", "STALE_DEADLINE_EXCEEDED"),
    ("NORMAL", "GAP", "SOURCE_SEQUENCE_GAP"),
    ("DEGRADED", "GAP", "SOURCE_SEQUENCE_GAP"),
    ("STALE", "GAP", "SOURCE_SEQUENCE_GAP"),
    ("RECOVERING", "GAP", "SOURCE_SEQUENCE_GAP"),
    ("NORMAL", "UNAVAILABLE", "DISCONNECTED"),
    ("DEGRADED", "UNAVAILABLE", "DISCONNECTED"),
    ("STALE", "UNAVAILABLE", "DISCONNECTED"),
    ("GAP", "UNAVAILABLE", "DISCONNECTED"),
    ("RECOVERING", "UNAVAILABLE", "DISCONNECTED"),
}
SESSION_TRANSITIONS = {
    ("CLOSED", "PRE_OPEN", "CALENDAR_BOUNDARY"),
    ("PRE_OPEN", "OPEN", "CALENDAR_BOUNDARY"),
    ("OPEN", "BREAK", "CALENDAR_BOUNDARY"),
    ("BREAK", "OPEN", "CALENDAR_BOUNDARY"),
    ("OPEN", "CLOSING", "CALENDAR_BOUNDARY"),
    ("CLOSING", "CLOSED", "CALENDAR_BOUNDARY"),
    ("CLOSED", "CLOSED", "DUPLICATE_SUPPRESSED"),
}


def parse_utc(value: object, *, field: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MarketContractError(f"{field} must be canonical UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketContractError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise MarketContractError(f"{field} must be UTC")
    return parsed.astimezone(UTC)


def format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise MarketContractError("injected time must be timezone-aware UTC")
    rendered = value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    head, fraction = rendered[:-1].split(".")
    fraction = fraction.rstrip("0")
    return f"{head}.{fraction}Z" if fraction else f"{head}Z"


def projection_checksum(value: Mapping[str, object], fields: tuple[str, ...]) -> str:
    try:
        projection = {field: value[field] for field in fields}
    except KeyError as exc:
        raise MarketContractError(f"checksum projection is missing {exc.args[0]}") from exc
    return canonical_sha256(projection)


def validate_market_dto(
    value: Mapping[str, object], registry: SchemaRegistry | None = None
) -> None:
    validate(value, (registry or SchemaRegistry()).contract("CONTRACT-MARKET-DATA-V1"))


def validate_trading_calendar(
    calendar: Mapping[str, object],
    *,
    registry: SchemaRegistry | None = None,
    tzdb: FrozenTzdb | None = None,
) -> None:
    validate_market_dto(calendar, registry)
    if calendar.get("content_checksum") != projection_checksum(calendar, CALENDAR_PROJECTION):
        raise MarketContractError("TradingCalendar checksum mismatch")
    database = tzdb or FrozenTzdb.installed()
    if calendar.get("tzdb_version") != database.version:
        raise MarketContractError("TradingCalendar tzdb version mismatch")
    utc_zone = database.zone("UTC")
    sessions = calendar.get("sessions")
    if not isinstance(sessions, (list, tuple)):
        raise MarketContractError("TradingCalendar sessions are missing")
    previous_close: datetime | None = None
    for raw_session in sessions:
        if not isinstance(raw_session, Mapping):
            raise MarketContractError("TradingCalendar session is malformed")
        opened = parse_utc(raw_session["open_at"], field="session.open_at")
        closed = parse_utc(raw_session["close_at"], field="session.close_at")
        if opened >= closed or (previous_close is not None and previous_close > opened):
            raise MarketContractError("TradingCalendar sessions overlap or invert")
        previous_close = closed
        resolved_open = _resolve_local_boundary(
            raw_session["open_local"],
            cast(str, calendar["timezone"]),
            raw_session["open_fold"],
            database,
        )
        resolved_close = _resolve_local_boundary(
            raw_session["close_local"],
            cast(str, calendar["timezone"]),
            raw_session["close_fold"],
            database,
        )
        if (
            resolved_open.astimezone(utc_zone) != opened
            or resolved_close.astimezone(utc_zone) != closed
        ):
            raise MarketContractError("TradingCalendar local/UTC boundary mismatch")
        open_offset = cast(timedelta, resolved_open.utcoffset())
        close_offset = cast(timedelta, resolved_close.utcoffset())
        if raw_session["open_utc_offset_seconds"] != str(int(open_offset.total_seconds())):
            raise MarketContractError("TradingCalendar open offset mismatch")
        if raw_session["close_utc_offset_seconds"] != str(int(close_offset.total_seconds())):
            raise MarketContractError("TradingCalendar close offset mismatch")
        crosses = resolved_open.date() != resolved_close.date()
        if raw_session["crosses_local_midnight"] is not crosses:
            raise MarketContractError("TradingCalendar cross-midnight mismatch")
        trading_day = resolved_close.date() if crosses else resolved_open.date()
        if calendar["trading_day"] != trading_day.isoformat():
            raise MarketContractError("TradingCalendar trading-day mapping mismatch")


def validate_policy_shape(policy: Mapping[str, object]) -> None:
    _require_exact_fields(policy, set(POLICY_PROJECTION) | {"policy_checksum"})
    _require_safe_int(policy, "schema_version", minimum=1, maximum=1)
    for field in (
        "generation",
        "snapshot_max_age_ms",
        "future_clock_skew_ms",
        "queue_capacity",
        "warning_watermark",
        "critical_watermark",
        "overflow_watermark",
        "source_lag_stale_ms",
    ):
        minimum = (
            1
            if field
            in {
                "generation",
                "queue_capacity",
                "critical_watermark",
                "overflow_watermark",
                "source_lag_stale_ms",
            }
            else 0
        )
        _require_safe_int(policy, field, minimum=minimum)
    if policy.get("dto_type") != "MARKET_VALIDATION_POLICY":
        raise MarketContractError("invalid Market validation policy dto_type")
    if not (
        cast(int, policy["warning_watermark"])
        < cast(int, policy["critical_watermark"])
        < cast(int, policy["overflow_watermark"])
        <= cast(int, policy["queue_capacity"])
    ):
        raise MarketContractError("validation policy thresholds are invalid")
    parse_utc(policy["activated_at"], field="activated_at")
    expected = projection_checksum(policy, POLICY_PROJECTION)
    if policy.get("policy_checksum") != expected:
        raise MarketContractError("validation policy checksum mismatch")


def validate_tick(payload: Mapping[str, object], registry: SchemaRegistry | None = None) -> None:
    validate(payload, (registry or SchemaRegistry()).payload("market.tick_received.v1", 1))
    event_time = parse_utc(payload["event_time"], field="event_time")
    received_at = parse_utc(payload["received_at"], field="received_at")
    if event_time > received_at:
        raise MarketContractError("tick timestamp inversion")
    source = _require_safe_int(payload, "source_sequence")
    watermark = _require_safe_int(payload, "watermark_sequence")
    if watermark < source:
        raise MarketContractError("tick watermark regression")
    for field in ("last_price", "turnover", "bid_price", "ask_price"):
        value = payload.get(field)
        if isinstance(value, float):
            raise MarketContractError(f"{field} JSON float is forbidden")
    _require_safe_int(payload, "last_quantity")
    if payload["quality"] == "GAP":
        start = _require_safe_int(payload, "gap_start_sequence")
        end = _require_safe_int(payload, "gap_end_sequence")
        if start > end:
            raise MarketContractError("invalid tick gap range")
    elif (
        payload.get("gap_start_sequence") is not None or payload.get("gap_end_sequence") is not None
    ):
        raise MarketContractError("non-GAP tick cannot carry gap range")


def validate_bar(payload: Mapping[str, object], registry: SchemaRegistry | None = None) -> None:
    validate(payload, (registry or SchemaRegistry()).payload("market.bar_closed.v1", 1))
    opened = parse_utc(payload["session_open_at"], field="session_open_at")
    closed = parse_utc(payload["session_close_at"], field="session_close_at")
    start = parse_utc(payload["window_start"], field="window_start")
    end = parse_utc(payload["window_end"], field="window_end")
    event_time = parse_utc(payload["event_time"], field="event_time")
    watermark = parse_utc(payload["watermark_event_time"], field="watermark_event_time")
    received = parse_utc(payload["received_at"], field="received_at")
    timeframe = _require_safe_int(payload, "timeframe_seconds", minimum=1)
    lateness = _require_safe_int(payload, "allowed_lateness_ms")
    if not (opened <= start < end <= closed):
        raise MarketContractError("bar crosses session boundary")
    if end - start != timedelta(seconds=timeframe):
        raise MarketContractError("bar window length mismatch")
    if event_time != end:
        raise MarketContractError("final bar event_time must equal window_end")
    if watermark < end + timedelta(milliseconds=lateness):
        raise MarketContractError("bar finalized before allowed lateness watermark")
    if received < event_time:
        raise MarketContractError("bar received_at predates event_time")
    prices = {name: _decimal(payload[name], name) for name in ("open", "high", "low", "close")}
    if prices["low"] > min(prices["open"], prices["close"]):
        raise MarketContractError("invalid bar low")
    if prices["high"] < max(prices["open"], prices["close"]):
        raise MarketContractError("invalid bar high")
    if prices["high"] < prices["low"]:
        raise MarketContractError("invalid bar OHLC range")
    _decimal(payload["turnover"], "turnover")
    sequence_start = _require_safe_int(payload, "source_sequence_start")
    sequence_end = _require_safe_int(payload, "source_sequence_end")
    if (
        sequence_start > sequence_end
        or _require_safe_int(payload, "watermark_sequence") < sequence_end
    ):
        raise MarketContractError("invalid bar source sequence range")
    if payload["quality"] == "GAP":
        gap_start = _require_safe_int(payload, "gap_start_sequence")
        gap_end = _require_safe_int(payload, "gap_end_sequence")
        if gap_start > gap_end or payload.get("partial") is not True:
            raise MarketContractError("invalid partial GAP bar evidence")
    elif (
        payload.get("gap_start_sequence") is not None or payload.get("gap_end_sequence") is not None
    ):
        raise MarketContractError("non-GAP bar cannot carry gap range")
    if payload.get("final") is not True or payload.get("revision") != 0:
        raise MarketContractError("final bar history is immutable")
    if payload.get("content_checksum") != projection_checksum(payload, BAR_PROJECTION):
        raise MarketContractError("bar checksum mismatch")


def validate_quality_event(
    payload: Mapping[str, object], registry: SchemaRegistry | None = None
) -> None:
    validate(payload, (registry or SchemaRegistry()).payload("market.quality_changed.v1", 1))
    if parse_utc(payload["event_time"], field="event_time") > parse_utc(
        payload["received_at"], field="received_at"
    ):
        raise MarketContractError("quality timestamp inversion")
    previous_quality_version = _require_safe_int(payload, "previous_quality_version")
    quality_version = _require_safe_int(payload, "quality_version", minimum=1)
    if quality_version != previous_quality_version + 1:
        raise MarketContractError("quality version must increment exactly once")
    previous_source = _require_safe_int(payload, "previous_source_version")
    source = _require_safe_int(payload, "source_version")
    sequence = _require_safe_int(payload, "source_sequence")
    if source < previous_source or sequence != source:
        raise MarketContractError("quality source version regression or mismatch")
    transition = (
        cast(str, payload["previous_quality"]),
        cast(str, payload["quality"]),
        cast(str, payload["reason_code"]),
    )
    if transition not in QUALITY_TRANSITIONS:
        raise MarketContractError("illegal Market quality transition")
    quality = payload["quality"]
    evidence = payload.get("recovery_evidence")
    if quality == "GAP":
        start = _require_safe_int(payload, "gap_start_sequence")
        end = _require_safe_int(payload, "gap_end_sequence")
        if not (
            start == previous_source + 1
            and start <= end <= source
            and _require_safe_int(payload, "unresolved_gap_count", minimum=1) >= 1
            and evidence is None
        ):
            raise MarketContractError("quality gap evidence is not bound to source versions")
    elif (
        payload.get("gap_start_sequence") is not None or payload.get("gap_end_sequence") is not None
    ):
        raise MarketContractError("non-GAP quality cannot carry gap range")
    if quality in {"NORMAL", "RECOVERING"}:
        if not isinstance(evidence, Mapping):
            raise MarketContractError("recovery quality requires structured evidence")
        _validate_recovery_evidence(payload, evidence)
    elif evidence is not None:
        raise MarketContractError("non-recovery quality cannot carry recovery evidence")
    if quality == "NORMAL" and payload.get("unresolved_gap_count") != 0:
        raise MarketContractError("NORMAL quality cannot retain unresolved gaps")


def validate_session_event(
    payload: Mapping[str, object],
    registry: SchemaRegistry | None = None,
    tzdb: FrozenTzdb | None = None,
) -> None:
    validate(payload, (registry or SchemaRegistry()).payload("market.session_changed.v1", 1))
    event_time = parse_utc(payload["event_time"], field="event_time")
    received = parse_utc(payload["received_at"], field="received_at")
    opened = parse_utc(payload["session_open_at"], field="session_open_at")
    closed = parse_utc(payload["session_close_at"], field="session_close_at")
    if event_time > received or opened >= closed:
        raise MarketContractError("Session timestamp inversion")
    if payload["calendar_version"] != payload["session_calendar_version"]:
        raise MarketContractError("Session/calendar version mismatch")
    transition = (
        cast(str, payload["from_state"]),
        cast(str, payload["to_state"]),
        cast(str, payload["reason_code"]),
    )
    if transition not in SESSION_TRANSITIONS:
        raise MarketContractError("illegal Session transition")
    database = tzdb or FrozenTzdb.installed()
    if payload["tzdb_version"] != database.version:
        raise MarketContractError("Session tzdb version mismatch")
    zone = database.zone(cast(str, payload["timezone"]))
    local_open = opened.astimezone(zone)
    local_close = closed.astimezone(zone)
    if (
        payload["session_open_fold"] != local_open.fold
        or payload["session_close_fold"] != local_close.fold
    ):
        raise MarketContractError("Session fold binding mismatch")
    open_offset = cast(timedelta, local_open.utcoffset())
    close_offset = cast(timedelta, local_close.utcoffset())
    if payload["session_open_utc_offset_seconds"] != str(int(open_offset.total_seconds())):
        raise MarketContractError("Session open UTC offset mismatch")
    if payload["session_close_utc_offset_seconds"] != str(int(close_offset.total_seconds())):
        raise MarketContractError("Session close UTC offset mismatch")
    crosses = local_open.date() != local_close.date()
    if payload["crosses_local_midnight"] is not crosses:
        raise MarketContractError("Session cross-midnight flag mismatch")
    trading_day = local_close.date() if crosses else local_open.date()
    if payload["trading_day"] != trading_day.isoformat():
        raise MarketContractError("Session trading-day mapping mismatch")


class MarketEventValidator:
    """Combined Envelope/payload/semantic validator with collision fencing."""

    def __init__(
        self,
        registry: SchemaRegistry | None = None,
        tzdb: FrozenTzdb | None = None,
        recovery_resolver: RecoveryEvidenceResolver | None = None,
    ) -> None:
        self._registry = registry or SchemaRegistry()
        self._tzdb = tzdb or FrozenTzdb.installed()
        self._recovery_resolver = recovery_resolver
        self._fingerprints: dict[str, str] = {}

    def validate(self, envelope: Mapping[str, object]) -> bool:
        primitive = dict(envelope)
        MessageEnvelope.create(primitive, self._registry)
        message_type = envelope.get("message_type")
        payload = envelope.get("payload")
        if not isinstance(message_type, str) or not isinstance(payload, Mapping):
            raise MarketContractError("Market Envelope is malformed")
        expected = _expected_envelope(message_type, payload)
        if envelope.get("schema_version") != 1 or envelope.get("message_id") != payload.get(
            "event_id"
        ):
            raise MarketContractError("Market message identity/version binding mismatch")
        if envelope.get("occurred_at") != payload.get("event_time") or envelope.get(
            "received_at"
        ) != payload.get("received_at"):
            raise MarketContractError("Market Envelope timestamp binding mismatch")
        for field, value in expected.items():
            if envelope.get(field) != value:
                raise MarketContractError(f"Market Envelope {field} binding mismatch")
        if message_type == "market.tick_received.v1":
            validate_tick(payload, self._registry)
        elif message_type == "market.bar_closed.v1":
            validate_bar(payload, self._registry)
        elif message_type == "market.quality_changed.v1":
            validate_quality_event(payload, self._registry)
            evidence = payload.get("recovery_evidence")
            if payload.get("quality") in {"NORMAL", "RECOVERING"}:
                if self._recovery_resolver is None or not isinstance(evidence, Mapping):
                    raise MarketContractError("immutable recovery registry is unavailable")
                self._recovery_resolver.verify_event(payload, evidence)
        elif message_type == "market.session_changed.v1":
            validate_session_event(payload, self._registry, self._tzdb)
        else:
            raise MarketContractError("unknown Market message type")
        identity = cast(str, envelope["idempotency_key"])
        fingerprint = canonical_sha256(dict(payload))
        existing = self._fingerprints.setdefault(identity, fingerprint)
        if existing != fingerprint:
            raise MarketContractError("Market idempotency identity collision")
        return existing == fingerprint


class RecoveryEvidenceResolver(Protocol):
    def verify_event(
        self, payload: Mapping[str, object], evidence: Mapping[str, object]
    ) -> None: ...


def _validate_recovery_evidence(
    payload: Mapping[str, object], evidence: Mapping[str, object]
) -> None:
    for field in ("provider", "instrument_id", "calendar_id", "calendar_version", "session_id"):
        if evidence.get(field) != payload.get(field):
            raise MarketContractError("recovery evidence identity mismatch")
    for field in (
        "previous_source_version",
        "source_version",
        "previous_quality_version",
        "quality_version",
    ):
        if evidence.get(field) != payload.get(field):
            raise MarketContractError("recovery evidence version mismatch")
    start = _require_safe_int(evidence, "backfill_start_sequence")
    end = _require_safe_int(evidence, "backfill_end_sequence")
    gap_start = _require_safe_int(evidence, "gap_start_sequence")
    gap_end = _require_safe_int(evidence, "gap_end_sequence")
    watermark = _require_safe_int(evidence, "watermark_sequence")
    previous_source = cast(int, payload["previous_source_version"])
    source = cast(int, payload["source_version"])
    if not (
        start == gap_start == previous_source + 1
        and end == gap_end
        and start <= end <= source
        and watermark >= source
    ):
        raise MarketContractError("recovery range is not bound to source versions")
    for field in ("snapshot_checksum", "checkpoint_checksum"):
        checksum = evidence.get(field)
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise MarketContractError("recovery evidence checksum is malformed")


def _expected_envelope(message_type: str, payload: Mapping[str, object]) -> dict[str, object]:
    if message_type == "market.tick_received.v1":
        return {
            "source": f"MarketGateway/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": f"market:{payload['provider']}:{payload['instrument_id']}:tick",
            "aggregate_version": payload["source_sequence"],
            "idempotency_key": (
                f"market.tick:{payload['provider']}:{payload['instrument_id']}:"
                f"{payload['source_sequence']}"
            ),
        }
    if message_type == "market.bar_closed.v1":
        return {
            "source": f"BarAggregator/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": (
                f"market:{payload['provider']}:{payload['instrument_id']}:bar:"
                f"{payload['timeframe_seconds']}:{payload['calendar_version']}:"
                f"{payload['session_id']}"
            ),
            "aggregate_version": payload["source_sequence_end"],
            "idempotency_key": (
                f"market.bar:{payload['provider']}:{payload['instrument_id']}:"
                f"{payload['calendar_version']}:{payload['session_id']}:"
                f"{payload['timeframe_seconds']}:{payload['window_start']}"
            ),
        }
    if message_type == "market.quality_changed.v1":
        return {
            "source": f"MarketQuality/{payload['provider']}",
            "partition_key": payload["instrument_id"],
            "aggregate_id": f"market:{payload['provider']}:{payload['instrument_id']}:quality",
            "aggregate_version": payload["quality_version"],
            "idempotency_key": (
                f"market.quality:{payload['provider']}:{payload['instrument_id']}:"
                f"{payload['quality_version']}"
            ),
        }
    if message_type == "market.session_changed.v1":
        return {
            "source": f"SessionScheduler/{payload['calendar_id']}",
            "partition_key": payload["exchange"],
            "aggregate_id": (
                f"market:{payload['calendar_id']}:{payload['calendar_version']}:"
                f"{payload['exchange']}:{payload['session_id']}:session"
            ),
            "aggregate_version": payload["transition_sequence"],
            "idempotency_key": (
                f"market.session:{payload['calendar_id']}:{payload['calendar_version']}:"
                f"{payload['exchange']}:{payload['session_id']}:{payload['transition_sequence']}"
            ),
        }
    raise MarketContractError("unknown Market message type")


def validate_snapshot_exchange(
    request: Mapping[str, object],
    result: Mapping[str, object],
    policy: Mapping[str, object],
    evaluation_at: datetime,
) -> None:
    validate_market_dto(request)
    validate_market_dto(result)
    validate_policy_shape(policy)
    _bind_policy(request, policy, snapshot=True)
    if result.get("request_id") != request.get("request_id"):
        raise MarketContractError("snapshot request identity mismatch")
    if result.get("outcome") == "REJECTED":
        if result.get("snapshot") is not None or result.get("reason_code") not in {
            "DEADLINE_EXCEEDED",
            "UNAVAILABLE",
            "STALE",
            "GAP",
            "CHECKSUM_UNVERIFIED",
            "INVALID_REQUEST",
        }:
            raise MarketContractError("invalid rejected Snapshot result")
        return
    if result.get("outcome") != "AVAILABLE" or result.get("reason_code") != "AVAILABLE":
        raise MarketContractError("snapshot outcome/reason mismatch")
    snapshot = result.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise MarketContractError("AVAILABLE Snapshot requires evidence")
    for field in (
        "provider",
        "generation",
        "instrument_id",
        "calendar_id",
        "calendar_version",
        "session_id",
        "source_version",
        "quality_version",
        "aggregation_policy_version",
    ):
        if snapshot.get(field) != request.get(field):
            raise MarketContractError("snapshot request/version binding mismatch")
    if snapshot.get("source_sequence") != snapshot.get("source_version"):
        raise MarketContractError("snapshot source sequence/version mismatch")
    if snapshot.get("content_checksum") != projection_checksum(snapshot, SNAPSHOT_PROJECTION):
        raise MarketContractError("snapshot checksum mismatch")
    as_of = parse_utc(snapshot["as_of"], field="snapshot.as_of")
    future_ms = _milliseconds(as_of - evaluation_at)
    age_ms = _milliseconds(evaluation_at - as_of)
    if future_ms > cast(int, policy["future_clock_skew_ms"]):
        raise MarketContractError("snapshot future clock skew")
    stale = age_ms > cast(int, policy["snapshot_max_age_ms"])
    if snapshot.get("stale") is not stale:
        raise MarketContractError("snapshot stale evidence mismatch")
    if (
        stale
        or snapshot.get("quality") != "NORMAL"
        or snapshot.get("unresolved_gap_count") != 0
        or snapshot.get("checksum_verified") is not True
    ):
        raise MarketContractError("AVAILABLE snapshot is not trade-safe")


def validate_health_exchange(
    request: Mapping[str, object],
    health: Mapping[str, object],
    policy: Mapping[str, object],
    observed_at: datetime,
) -> None:
    validate_market_dto(request)
    validate_market_dto(health)
    validate_policy_shape(policy)
    _bind_policy(request, policy, snapshot=False)
    for field in (
        "request_id",
        "provider",
        "generation",
        "calendar_id",
        "calendar_version",
        "session_id",
        "source_version",
        "quality_version",
        "policy_version",
    ):
        if health.get(field) != request.get(field):
            raise MarketContractError("health request/version binding mismatch")
    if parse_utc(health["observed_at"], field="health.observed_at") != observed_at:
        raise MarketContractError("health observed_at does not match injected time")
    if observed_at < parse_utc(policy["activated_at"], field="policy.activated_at"):
        raise MarketContractError("health predates policy activation")
    for field in (
        "queue_capacity",
        "warning_watermark",
        "critical_watermark",
        "overflow_watermark",
        "source_lag_stale_ms",
    ):
        if health.get(field) != policy.get(field):
            raise MarketContractError("health response threshold mismatch")
    depth = _require_safe_int(health, "queue_depth")
    lag = _require_safe_int(health, "source_lag_ms")
    if depth > cast(int, policy["queue_capacity"]):
        raise MarketContractError("health queue depth exceeds capacity")
    quality = health.get("quality")
    expected = _health_tuple(cast(str, quality), depth, lag, policy)
    if (health.get("status"), health.get("reason_code")) != expected:
        raise MarketContractError("health status contradicts accepted policy")


def _health_tuple(
    quality: str, depth: int, lag: int, policy: Mapping[str, object]
) -> tuple[str, str]:
    if quality == "UNAVAILABLE":
        return ("DISCONNECTED", "UNAVAILABLE")
    if quality == "GAP":
        return ("DEGRADED", "GAP")
    if quality == "STALE":
        return ("DEGRADED", "STALE")
    if quality == "RECOVERING":
        return ("DEGRADED", "RECOVERING")
    if lag >= cast(int, policy["source_lag_stale_ms"]):
        return ("DEGRADED", "SOURCE_LAG")
    if depth >= cast(int, policy["warning_watermark"]):
        return ("DEGRADED", "BACKPRESSURE")
    if quality == "DEGRADED":
        return ("DEGRADED", "BACKPRESSURE")
    return ("HEALTHY", "OK")


def _bind_policy(
    request: Mapping[str, object], policy: Mapping[str, object], *, snapshot: bool
) -> None:
    for field in ("provider", "generation", "calendar_id", "calendar_version", "session_id"):
        if request.get(field) != policy.get(field):
            raise MarketContractError("validation policy identity mismatch")
    request_version = request.get("aggregation_policy_version" if snapshot else "policy_version")
    policy_version = policy.get("aggregation_policy_version" if snapshot else "policy_version")
    if request_version != policy_version:
        raise MarketContractError("validation policy version mismatch")


def _milliseconds(delta: timedelta) -> int:
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _resolve_local_boundary(
    value: object, zone_name: str, fold: object, tzdb: FrozenTzdb
) -> datetime:
    if not isinstance(value, str) or fold not in {0, 1}:
        raise MarketContractError("TradingCalendar local boundary/fold is invalid")
    try:
        local = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MarketContractError("TradingCalendar local boundary is malformed") from exc
    if local.tzinfo is not None:
        raise MarketContractError("TradingCalendar local boundary must be naive")
    zone = tzdb.zone(zone_name)
    resolved = local.replace(tzinfo=zone, fold=fold)
    if resolved.astimezone(tzdb.zone("UTC")).astimezone(zone).replace(tzinfo=None) != local:
        raise MarketContractError("TradingCalendar local boundary is nonexistent")
    return resolved


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise MarketContractError(f"{field} must be a Decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise MarketContractError(f"{field} is not Decimal") from exc


def _require_safe_int(
    value: Mapping[str, object], field: str, *, minimum: int = 0, maximum: int = SAFE_INTEGER_MAX
) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
        raise MarketContractError(f"{field} must be an I-JSON safe integer")
    return item


def _require_exact_fields(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        missing = expected - set(value)
        extra = set(value) - expected
        raise MarketContractError(
            f"contract fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
