from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise, product
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from quantiqmt.contracts import MessageEnvelope, SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "spec" / "contracts"
SEMANTIC_CONTRACT = SCHEMAS / "market" / "market-data.semantic-validation.v1.yaml"
FIXTURES = Path(__file__).with_name("fixtures")
TZDB_FIXTURE = FIXTURES / "internal/market-data.v1/tzdb"
EVENTS = {
    "market.tick_received.v1": "events/market.tick_received.v1.schema.json",
    "market.bar_closed.v1": "events/market.bar_closed.v1.schema.json",
    "market.quality_changed.v1": "events/market.quality_changed.v1.schema.json",
    "market.session_changed.v1": "events/market.session_changed.v1.schema.json",
}
SESSION_TRANSITIONS = {
    ("CLOSED", "PRE_OPEN"): "CALENDAR_BOUNDARY",
    ("PRE_OPEN", "OPEN"): "CALENDAR_BOUNDARY",
    ("OPEN", "BREAK"): "CALENDAR_BOUNDARY",
    ("BREAK", "OPEN"): "CALENDAR_BOUNDARY",
    ("OPEN", "CLOSING"): "CALENDAR_BOUNDARY",
    ("CLOSING", "CLOSED"): "CALENDAR_BOUNDARY",
    ("CLOSED", "CLOSED"): "DUPLICATE_SUPPRESSED",
}
SAFE_INTEGER_MAX = 9_007_199_254_740_991
ACCEPTED_POLICY_REGISTRY = {
    "market-policy-v1": "d31191dd8fbba15144a133d0d663b3c7cf80cdc0843de7587256d17eda828e9d"
}


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validator(relative: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _semantic_contract() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(SEMANTIC_CONTRACT.read_text(encoding="utf-8")))


def _recovery_evidence_registry() -> dict[str, dict[str, Any]]:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    return {
        "SIM:600000.XSHG:10": by_type["MARKET_SNAPSHOT"],
        "SIM:600000.XSHG:am:10": by_type["BAR_AGGREGATION_CHECKPOINT"],
    }


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("timestamp must be canonical UTC Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iana_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        path = TZDB_FIXTURE / Path(*name.split("/"))
        if not path.is_file():
            raise ValueError("calendar timezone is not IANA or tzdb is unavailable") from exc
        with path.open("rb") as stream:
            return ZoneInfo.from_file(stream, key=name)


def _resolve_local_boundary(value: str, zone_name: str, fold: int) -> datetime:
    local = datetime.fromisoformat(value)
    if local.tzinfo is not None or fold not in {0, 1}:
        raise ValueError("local boundary/fold is invalid")
    zone = _iana_zone(zone_name)
    resolved = local.replace(tzinfo=zone, fold=fold)
    if resolved.astimezone(ZoneInfo("UTC")).astimezone(zone).replace(tzinfo=None) != local:
        raise ValueError("nonexistent local boundary")
    return resolved


def _jcs(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("float is forbidden in canonical market values")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_jcs(key)}:{_jcs(value[key])}" for key in keys) + "}"
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_jcs(value).encode("utf-8")).hexdigest()


def _projection(value: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: value[field] for field in fields}


def _assert_checksum(kind: str, value: dict[str, Any]) -> None:
    rule = _semantic_contract()["semantic_validation"]["checksums"][kind]
    expected = _canonical_hash(_projection(value, rule["projection"]))
    if value[rule["checksum_field"]] != expected:
        raise ValueError(f"{kind} checksum mismatch")


def _refresh_checksum(kind: str, value: dict[str, Any]) -> None:
    rule = _semantic_contract()["semantic_validation"]["checksums"][kind]
    value[rule["checksum_field"]] = _canonical_hash(_projection(value, rule["projection"]))


def _refresh_bar_identity_and_checksum(value: dict[str, Any]) -> None:
    rule = _semantic_contract()["semantic_validation"]["bar_identity"]
    value["event_id"] = str(
        uuid.uuid5(
            uuid.UUID(rule["namespace"]),
            _jcs(_projection(value, rule["name_projection"])),
        )
    )
    _refresh_checksum("market.bar_closed.v1", value)


def validate_unsigned_integer_token(token: str) -> int:
    if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
        raise ValueError("canonical unsigned safe integer token required")
    value = int(token)
    if value > SAFE_INTEGER_MAX:
        raise ValueError("canonical unsigned safe integer token required")
    return value


def _validate_accepted_policy(
    request: dict[str, Any], policy: dict[str, Any], *, snapshot: bool
) -> None:
    _validator("market/market-data.v1.schema.json").validate(policy)
    accepted_checksum = ACCEPTED_POLICY_REGISTRY.get(policy["policy_version"])
    if accepted_checksum is None:
        raise ValueError("validation policy identity mismatch")
    for field in ("provider", "generation", "calendar_id", "calendar_version", "session_id"):
        if request[field] != policy[field]:
            raise ValueError("validation policy identity mismatch")
    request_policy_version = (
        request["aggregation_policy_version"] if snapshot else request["policy_version"]
    )
    expected_policy_version = (
        policy["aggregation_policy_version"] if snapshot else policy["policy_version"]
    )
    if request_policy_version != expected_policy_version:
        raise ValueError("validation policy identity mismatch")
    try:
        _assert_checksum("MARKET_VALIDATION_POLICY", policy)
    except ValueError as exc:
        raise ValueError("validation policy checksum mismatch") from exc
    if policy["policy_checksum"] != accepted_checksum:
        raise ValueError("validation policy checksum mismatch")
    if not (
        policy["warning_watermark"]
        < policy["critical_watermark"]
        < policy["overflow_watermark"]
        <= policy["queue_capacity"]
    ):
        raise ValueError("validation policy thresholds invalid")


def validate_snapshot_exchange(
    request: dict[str, Any],
    result: dict[str, Any],
    policy: dict[str, Any],
    evaluation_at: str,
) -> None:
    _validator("market/market-data.v1.schema.json").validate(request)
    _validate_accepted_policy(request, policy, snapshot=True)
    if result.get("request_id") != request["request_id"]:
        raise ValueError("snapshot request identity mismatch")
    rejected_reasons = {
        "DEADLINE_EXCEEDED",
        "UNAVAILABLE",
        "STALE",
        "GAP",
        "CHECKSUM_UNVERIFIED",
        "INVALID_REQUEST",
    }
    if result.get("outcome") == "REJECTED":
        if result.get("reason_code") not in rejected_reasons:
            raise ValueError("snapshot outcome/reason mismatch")
        if result.get("snapshot") is not None:
            raise ValueError("REJECTED snapshot must be null")
        _validator("market/market-data.v1.schema.json").validate(result)
        return
    if result.get("outcome") != "AVAILABLE" or result.get("reason_code") != "AVAILABLE":
        raise ValueError("snapshot outcome/reason mismatch")
    snapshot = result.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("AVAILABLE snapshot payload required")
    _validator("market/market-data.v1.schema.json").validate(result)
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
        if snapshot[field] != request[field]:
            raise ValueError("snapshot request/version binding mismatch")
    if snapshot["source_sequence"] != snapshot["source_version"]:
        raise ValueError("snapshot source sequence/version mismatch")
    _assert_checksum("MARKET_SNAPSHOT", snapshot)
    as_of = _utc(snapshot["as_of"])
    evaluated = _utc(evaluation_at)
    age_delta = evaluated - as_of
    future_delta = as_of - evaluated
    age_ms = age_delta.days * 86_400_000 + age_delta.seconds * 1000 + age_delta.microseconds // 1000
    future_ms = (
        future_delta.days * 86_400_000
        + future_delta.seconds * 1000
        + future_delta.microseconds // 1000
    )
    if future_ms > policy["future_clock_skew_ms"]:
        raise ValueError("snapshot future clock skew")
    recomputed_stale = age_ms > policy["snapshot_max_age_ms"]
    if snapshot["stale"] is not recomputed_stale:
        if recomputed_stale:
            raise ValueError("snapshot freshness policy violation")
        raise ValueError("snapshot stale flag contradicts trusted policy")
    if recomputed_stale or snapshot["quality"] != "NORMAL":
        raise ValueError("snapshot freshness policy violation")
    if snapshot["unresolved_gap_count"] != 0 or not snapshot["checksum_verified"]:
        raise ValueError("AVAILABLE snapshot is not trade-safe")


def validate_health_exchange(
    request: dict[str, Any],
    health: dict[str, Any],
    policy: dict[str, Any],
    observed_at: str,
) -> None:
    _validator("market/market-data.v1.schema.json").validate(request)
    _validator("market/market-data.v1.schema.json").validate(health)
    _validate_accepted_policy(request, policy, snapshot=False)
    if health["observed_at"] != observed_at or _utc(observed_at) < _utc(policy["activated_at"]):
        raise ValueError("health observed_at context mismatch")
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
        if health[field] != request[field]:
            raise ValueError("health version/policy binding mismatch")
    threshold_fields = (
        "queue_capacity",
        "warning_watermark",
        "critical_watermark",
        "overflow_watermark",
        "source_lag_stale_ms",
    )
    if any(health[field] != policy[field] for field in threshold_fields):
        raise ValueError("health thresholds do not match accepted policy")
    if health["queue_depth"] > policy["queue_capacity"]:
        raise ValueError("queue depth exceeds capacity")
    if health["source_lag_ms"] >= policy["source_lag_stale_ms"]:
        expected = ("DEGRADED", "STALE", "STALE")
    elif health["queue_depth"] >= policy["overflow_watermark"]:
        expected = ("DEGRADED", "GAP", "GAP")
    elif health["queue_depth"] >= policy["warning_watermark"]:
        expected = ("DEGRADED", "DEGRADED", "BACKPRESSURE")
    else:
        expected = ("HEALTHY", "NORMAL", "OK")
    actual = (health["status"], health["quality"], health["reason_code"])
    if actual != expected:
        raise ValueError("health status does not match accepted policy")


def validate_market_event_semantics(message_type: str, payload: dict[str, Any]) -> None:
    if _utc(payload["received_at"]) < _utc(payload["event_time"]):
        raise ValueError("received_at precedes event_time")
    if payload["partition_key"] != payload.get("instrument_id", payload.get("exchange")):
        raise ValueError("partition identity mismatch")

    quality = payload.get("quality")
    gap_start = payload.get("gap_start_sequence")
    gap_end = payload.get("gap_end_sequence")
    if quality == "GAP":
        if not isinstance(gap_start, int) or not isinstance(gap_end, int) or gap_start > gap_end:
            raise ValueError("GAP requires an ordered range")
    elif gap_start is not None or gap_end is not None:
        raise ValueError("non-GAP event cannot claim a gap range")

    if message_type == "market.tick_received.v1":
        if payload["source_sequence"] < payload["watermark_sequence"]:
            raise ValueError("tick source sequence is behind watermark")
        if quality == "GAP" and not (
            gap_start == payload["watermark_sequence"] + 1 and gap_end < payload["source_sequence"]
        ):
            raise ValueError("tick gap is not bound to watermark/source sequence")
        return

    if message_type == "market.bar_closed.v1":
        window_start = _utc(payload["window_start"])
        window_end = _utc(payload["window_end"])
        session_open = _utc(payload["session_open_at"])
        session_close = _utc(payload["session_close_at"])
        if not (window_start < window_end):
            raise ValueError("bar window is inverted")
        if window_end - window_start != timedelta(seconds=payload["timeframe_seconds"]):
            raise ValueError("bar window/timeframe mismatch")
        if not (session_open <= window_start < window_end <= session_close):
            raise ValueError("bar crosses session boundary")
        if (window_start - session_open).total_seconds() % payload["timeframe_seconds"]:
            raise ValueError("bar window is not aligned to session open")
        if _utc(payload["event_time"]) != window_end:
            raise ValueError("final bar event_time must equal window_end")
        final_gate = window_end + timedelta(milliseconds=payload["allowed_lateness_ms"])
        if _utc(payload["watermark_event_time"]) < final_gate:
            raise ValueError("bar finalized before allowed lateness watermark")
        prices = [Decimal(payload[name]) for name in ("open", "high", "low", "close")]
        if prices[1] < prices[2] or max(prices[0], prices[3]) > prices[1]:
            raise ValueError("invalid OHLC")
        if min(prices[0], prices[3]) < prices[2]:
            raise ValueError("invalid OHLC")
        if payload["source_sequence_start"] > payload["source_sequence_end"]:
            raise ValueError("bar sequence range is inverted")
        if payload["watermark_sequence"] < payload["source_sequence_end"]:
            raise ValueError("bar closed before watermark")
        if quality == "GAP" and not (
            payload["source_sequence_start"]
            <= gap_start
            <= gap_end
            <= payload["source_sequence_end"]
        ):
            raise ValueError("bar gap is outside source sequence range")
        identity_rule = _semantic_contract()["semantic_validation"]["bar_identity"]
        expected_id = str(
            uuid.uuid5(
                uuid.UUID(identity_rule["namespace"]),
                _jcs(_projection(payload, identity_rule["name_projection"])),
            )
        )
        if payload["event_id"] != expected_id:
            raise ValueError("bar UUIDv5 identity mismatch")
        _assert_checksum(message_type, payload)
        return

    if message_type == "market.quality_changed.v1":
        transitions = {
            tuple(item)
            for item in _semantic_contract()["semantic_validation"]["quality"]["transitions"]
        }
        transition = (
            payload["previous_quality"],
            payload["quality"],
            payload["reason_code"],
        )
        if transition not in transitions:
            raise ValueError("illegal quality transition/reason")
        if payload["quality_version"] != payload["previous_quality_version"] + 1:
            raise ValueError("quality version must increase exactly once")
        if payload["source_version"] < payload["previous_source_version"]:
            raise ValueError("source version regressed")
        if payload["source_sequence"] != payload["source_version"]:
            raise ValueError("source sequence/version mismatch")
        if payload["quality"] == "NORMAL" and payload["unresolved_gap_count"] != 0:
            raise ValueError("NORMAL cannot retain unresolved gaps")
        evidence = payload["recovery_evidence"]
        if payload["quality"] in {"NORMAL", "RECOVERING"}:
            if not isinstance(evidence, dict):
                raise ValueError("recovery requires structured evidence")
            for field in (
                "provider",
                "instrument_id",
                "calendar_id",
                "calendar_version",
                "session_id",
            ):
                if evidence[field] != payload[field]:
                    raise ValueError("recovery identity binding mismatch")
            for field in (
                "previous_source_version",
                "source_version",
                "previous_quality_version",
                "quality_version",
            ):
                if evidence[field] != payload[field]:
                    raise ValueError("recovery version binding mismatch")
            if not (
                evidence["backfill_start_sequence"]
                == evidence["gap_start_sequence"]
                == payload["previous_source_version"] + 1
                and evidence["backfill_end_sequence"]
                == evidence["gap_end_sequence"]
                <= payload["source_version"]
                and evidence["watermark_sequence"] >= payload["source_version"]
            ):
                raise ValueError("recovery range is not bound to source versions")
            registry = _recovery_evidence_registry()
            snapshot = registry.get(evidence["snapshot_identity"])
            checkpoint = registry.get(evidence["checkpoint_identity"])
            if snapshot is None or checkpoint is None:
                raise ValueError("recovery evidence identity is unresolved")
            _assert_checksum("MARKET_SNAPSHOT", snapshot)
            _assert_checksum("BAR_AGGREGATION_CHECKPOINT", checkpoint)
            if (
                evidence["snapshot_checksum"] != snapshot["content_checksum"]
                or evidence["checkpoint_checksum"] != checkpoint["checkpoint_checksum"]
            ):
                raise ValueError("recovery evidence checksum mismatch")
            for resolved in (snapshot, checkpoint):
                for field in (
                    "provider",
                    "instrument_id",
                    "calendar_id",
                    "calendar_version",
                    "session_id",
                    "source_version",
                    "quality_version",
                ):
                    if resolved[field] != payload[field]:
                        raise ValueError("recovery resolved-object binding mismatch")
        elif evidence is not None:
            raise ValueError("non-recovery transition cannot carry recovery evidence")
        if payload["quality"] == "GAP" and not (
            gap_start == payload["previous_source_version"] + 1
            and gap_end == payload["source_version"] - 1
            and gap_end < payload["source_sequence"]
        ):
            raise ValueError("quality gap is not bound to source versions")
        return

    transition = (payload["from_state"], payload["to_state"])
    if SESSION_TRANSITIONS.get(transition) != payload["reason_code"]:
        raise ValueError("illegal session transition")
    if payload["calendar_version"] != payload["session_calendar_version"]:
        raise ValueError("session/calendar version mismatch")
    if not (_utc(payload["session_open_at"]) < _utc(payload["session_close_at"])):
        raise ValueError("session interval is inverted")
    market_timezone = _iana_zone(payload["timezone"])
    local_open = _utc(payload["session_open_at"]).astimezone(market_timezone)
    local_close = _utc(payload["session_close_at"]).astimezone(market_timezone)
    if not payload["tzdb_version"]:
        raise ValueError("calendar tzdb version is missing")
    if (
        payload["session_open_fold"] != local_open.fold
        or payload["session_close_fold"] != local_close.fold
    ):
        raise ValueError("session fold binding mismatch")
    if payload["session_open_utc_offset_seconds"] != str(
        int(cast(timedelta, local_open.utcoffset()).total_seconds())
    ) or payload["session_close_utc_offset_seconds"] != str(
        int(cast(timedelta, local_close.utcoffset()).total_seconds())
    ):
        raise ValueError("session UTC offset binding mismatch")
    crosses = local_open.date() != local_close.date()
    if crosses != payload["crosses_local_midnight"]:
        raise ValueError("cross-midnight declaration mismatch")
    trading_day = local_close.date() if crosses else local_open.date()
    if payload["trading_day"] != trading_day.isoformat():
        raise ValueError("session/trading-day mapping mismatch")


def validate_market_contract_semantics(document: dict[str, Any]) -> None:
    dtos = document["dtos"]
    by_type = {dto["dto_type"]: dto for dto in dtos}
    validation_policy = _load(FIXTURES / "internal/market-data.v1/validation-policy.valid.json")
    calendar = by_type["TRADING_CALENDAR"]
    market_timezone = _iana_zone(calendar["timezone"])
    if calendar["tzdb_version"] != validation_policy["tzdb_version"]:
        raise ValueError("calendar/policy tzdb version mismatch")
    intervals = calendar["sessions"]
    if any(
        _utc(current["close_at"]) > _utc(following["open_at"])
        for current, following in pairwise(intervals)
    ):
        raise ValueError("calendar sessions overlap")
    for interval in intervals:
        opened = _utc(interval["open_at"])
        closed = _utc(interval["close_at"])
        resolved_open = _resolve_local_boundary(
            interval["open_local"], calendar["timezone"], interval["open_fold"]
        )
        resolved_close = _resolve_local_boundary(
            interval["close_local"], calendar["timezone"], interval["close_fold"]
        )
        if (
            resolved_open.astimezone(ZoneInfo("UTC")) != opened
            or resolved_close.astimezone(ZoneInfo("UTC")) != closed
        ):
            raise ValueError("calendar local/UTC boundary mismatch")
        if interval["open_utc_offset_seconds"] != str(
            int(cast(timedelta, resolved_open.utcoffset()).total_seconds())
        ) or interval["close_utc_offset_seconds"] != str(
            int(cast(timedelta, resolved_close.utcoffset()).total_seconds())
        ):
            raise ValueError("calendar UTC offset binding mismatch")
        if opened >= closed:
            raise ValueError("calendar session interval is inverted")
        crosses = (
            opened.astimezone(market_timezone).date() != closed.astimezone(market_timezone).date()
        )
        if crosses != interval["crosses_local_midnight"]:
            raise ValueError("calendar cross-midnight declaration mismatch")
        trading_day = (
            closed.astimezone(market_timezone).date()
            if crosses
            else opened.astimezone(market_timezone).date()
        )
        if calendar["trading_day"] != trading_day.isoformat():
            raise ValueError("calendar trading-day mapping mismatch")
    _assert_checksum("TRADING_CALENDAR", calendar)

    request = by_type["SUBSCRIPTION_REQUEST"]
    if request["queue_capacity"] < request["batch_capacity"]:
        raise ValueError("unbounded/invalid capacity")
    if request["warning_watermark"] >= request["critical_watermark"]:
        raise ValueError("watermark order invalid")
    if not (
        request["warning_watermark"]
        < request["critical_watermark"]
        < request["overflow_watermark"]
        <= request["queue_capacity"]
    ):
        raise ValueError("backpressure thresholds invalid")
    if request["overflow_policy"] != "REJECT_NEW_WITH_GAP_EVIDENCE":
        raise ValueError("tick coalescing is forbidden in V1")

    result = by_type["SUBSCRIPTION_RESULT"]
    if result["operation"] != request["operation"]:
        raise ValueError("subscription operation mismatch")
    if result["subscription_id"] != request["subscription_id"]:
        raise ValueError("subscription identity mismatch")
    if result["generation"] != request["generation"]:
        raise ValueError("subscription generation mismatch")

    lifecycle_request = by_type["LIFECYCLE_REQUEST"]
    lifecycle_result = by_type["LIFECYCLE_RESULT"]
    if lifecycle_result["request_id"] != lifecycle_request["request_id"]:
        raise ValueError("lifecycle request identity mismatch")
    if lifecycle_result["operation"] != lifecycle_request["operation"]:
        raise ValueError("lifecycle operation mismatch")
    if lifecycle_result["generation"] != lifecycle_request["generation"]:
        raise ValueError("lifecycle generation mismatch")

    snapshot = by_type["MARKET_SNAPSHOT"]
    snapshot_request = by_type["SNAPSHOT_REQUEST"]
    snapshot_result = by_type["SNAPSHOT_RESULT"]
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
        if snapshot_request[field] != snapshot[field]:
            raise ValueError("snapshot request/version binding mismatch")
    if snapshot["calendar_version"] != calendar["calendar_version"]:
        raise ValueError("snapshot/calendar version mismatch")
    if snapshot["quality"] == "NORMAL" and (
        snapshot["stale"] or snapshot["unresolved_gap_count"] != 0
    ):
        raise ValueError("AVAILABLE snapshot is not trade-safe")
    if snapshot_result["request_id"] != snapshot_request["request_id"]:
        raise ValueError("snapshot request identity mismatch")
    if snapshot_result["snapshot"] != snapshot:
        raise ValueError("snapshot result payload mismatch")
    _assert_checksum("MARKET_SNAPSHOT", snapshot)
    if snapshot_result["outcome"] == "AVAILABLE" and not (
        snapshot["quality"] == "NORMAL"
        and snapshot["stale"] is False
        and snapshot["unresolved_gap_count"] == 0
        and snapshot["checksum_verified"] is True
    ):
        raise ValueError("AVAILABLE snapshot is not trade-safe")
    validate_snapshot_exchange(
        snapshot_request,
        snapshot_result,
        validation_policy,
        "2026-08-11T01:30:01.000Z",
    )

    health = by_type["MARKET_HEALTH"]
    health_request = by_type["HEALTH_REQUEST"]
    if health["request_id"] != health_request["request_id"]:
        raise ValueError("health request identity mismatch")
    for field in (
        "provider",
        "generation",
        "calendar_id",
        "calendar_version",
        "session_id",
        "source_version",
        "quality_version",
        "policy_version",
    ):
        if health[field] != health_request[field]:
            raise ValueError("health version/policy binding mismatch")
    if not (
        health["warning_watermark"]
        < health["critical_watermark"]
        < health["overflow_watermark"]
        <= health["queue_capacity"]
    ):
        raise ValueError("health thresholds invalid")
    if health["queue_depth"] > health["queue_capacity"]:
        raise ValueError("queue depth exceeds capacity")
    if health["status"] == "HEALTHY" and health["quality"] != "NORMAL":
        raise ValueError("health/quality mismatch")
    if health["status"] == "HEALTHY" and (
        health["queue_depth"] >= health["warning_watermark"]
        or health["source_lag_ms"] >= health["source_lag_stale_ms"]
    ):
        raise ValueError("false HEALTHY under queue/lag threshold")
    validate_health_exchange(health_request, health, validation_policy, health["observed_at"])

    policy = by_type["BAR_AGGREGATION_POLICY"]
    checkpoint = by_type["BAR_AGGREGATION_CHECKPOINT"]
    if policy["provider"] != checkpoint["provider"]:
        raise ValueError("aggregator provider mismatch")
    if policy["calendar_version"] != calendar["calendar_version"]:
        raise ValueError("policy/calendar version mismatch")
    if checkpoint["calendar_version"] != calendar["calendar_version"]:
        raise ValueError("aggregator/calendar version mismatch")
    if checkpoint["watermark_sequence"] < checkpoint["last_final_sequence"]:
        raise ValueError("watermark regressed")
    if policy["allowed_lateness_ms"] < 0 or policy["timeframe_seconds"] <= 0:
        raise ValueError("invalid aggregation policy")
    if policy["late_after_final"] != "REJECT_AND_EMIT_GAP_EVIDENCE":
        raise ValueError("late-after-final cannot rewrite history")
    _assert_checksum("BAR_AGGREGATION_CHECKPOINT", checkpoint)

    inputs = [dto for dto in dtos if dto["dto_type"] == "BAR_AGGREGATION_INPUT"]
    identities: dict[tuple[str, int], str] = {}
    for item in inputs:
        if item["calendar_version"] != calendar["calendar_version"]:
            raise ValueError("input/calendar version mismatch")
        if item["calendar_id"] != calendar["calendar_id"]:
            raise ValueError("input/calendar identity mismatch")
        if item["provider"] != policy["provider"]:
            raise ValueError("input/provider mismatch")
        if item["session_id"] != checkpoint["session_id"]:
            raise ValueError("cross-session aggregation")
        session = next(
            interval for interval in intervals if interval["session_id"] == item["session_id"]
        )
        if not (_utc(session["open_at"]) <= _utc(item["event_time"]) < _utc(session["close_at"])):
            raise ValueError("input event_time outside bound session")
        identity = (item["instrument_id"], item["source_sequence"])
        content_hash = _canonical_hash({key: value for key, value in item.items() if key != "mode"})
        if identity in identities and identities[identity] != content_hash:
            raise ValueError("duplicate identity with different payload")
        identities[identity] = content_hash

    live = [item for item in inputs if item["mode"] == "LIVE"]
    replay = [item for item in inputs if item["mode"] == "REPLAY"]
    if [{k: v for k, v in item.items() if k != "mode"} for item in live] != [
        {k: v for k, v in item.items() if k != "mode"} for item in replay
    ]:
        raise ValueError("live/replay normalized inputs differ")


def _expected_envelope_fields(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
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


def _market_envelope(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    expected = _expected_envelope_fields(message_type, payload)
    return {
        "message_id": payload["event_id"],
        "message_type": message_type,
        "schema_version": 1,
        "occurred_at": payload["event_time"],
        "received_at": payload["received_at"],
        "correlation_id": "correlation-market-0001",
        "causation_id": None,
        **expected,
        "payload": payload,
    }


def validate_market_message(
    envelope: dict[str, Any], collision_guard: dict[str, str] | None = None
) -> None:
    message_type = envelope["message_type"]
    if message_type not in EVENTS:
        raise ValueError("unknown market message type")
    payload = cast(dict[str, Any], envelope["payload"])
    MessageEnvelope.create(envelope, SchemaRegistry.project_default())
    _validator(EVENTS[message_type]).validate(payload)
    if envelope["schema_version"] != 1 or envelope["message_id"] != payload["event_id"]:
        raise ValueError("message identity/version binding mismatch")
    if envelope["occurred_at"] != payload["event_time"]:
        raise ValueError("envelope event-time binding mismatch")
    if envelope["received_at"] != payload["received_at"]:
        raise ValueError("envelope receive-time binding mismatch")
    expected = _expected_envelope_fields(message_type, payload)
    for field, value in expected.items():
        if envelope[field] != value:
            raise ValueError(f"envelope {field} binding mismatch")
    validate_market_event_semantics(message_type, payload)
    if collision_guard is not None:
        identity = envelope["idempotency_key"]
        fingerprint = _canonical_hash(payload)
        existing = collision_guard.setdefault(identity, fingerprint)
        if existing != fingerprint:
            raise ValueError("idempotency identity collision")


def test_catalog_registry_and_manifest_register_all_market_contracts() -> None:
    registry = SchemaRegistry.project_default()
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in manifest["catalogs"]["contracts"]}
    assert set(EVENTS).issubset(registry.message_types)
    assert {
        "CONTRACT-MARKET-TICK-RECEIVED-V1",
        "CONTRACT-MARKET-BAR-CLOSED-V1",
        "CONTRACT-MARKET-QUALITY-CHANGED-V1",
        "CONTRACT-MARKET-SESSION-CHANGED-V1",
        "CONTRACT-MARKET-DATA-V1",
        "CONTRACT-MARKET-SEMANTIC-VALIDATION-V1",
    }.issubset(ids)
    for message_type in EVENTS:
        registered = registry.payload(message_type, 1)
        assert registered["$id"] == _load(SCHEMAS / EVENTS[message_type])["$id"]
        _validator(EVENTS[message_type]).validate(
            _load(FIXTURES / message_type / "minimal.valid.json")
        )


def test_review_safety_rules_are_normative_and_machine_indexed() -> None:
    contract = _semantic_contract()["semantic_validation"]
    assert contract["mandatory_boundaries"] == [
        "publish",
        "persist",
        "quality_transition",
        "snapshot_restore",
        "strategy_risk_delivery",
    ]
    assert contract["health_backpressure"]["coalesce"] == "forbidden_v1"
    assert contract["canonicalization"]["algorithm"] == "RFC8785_JCS"
    assert set(contract["event_envelope_binding"]) == set(EVENTS)
    assert set(contract["checksums"]) == {
        "TRADING_CALENDAR",
        "MARKET_SNAPSHOT",
        "MARKET_VALIDATION_POLICY",
        "BAR_AGGREGATION_CHECKPOINT",
        "market.bar_closed.v1",
    }
    vector = contract["canonicalization"]["non_bmp_reference"]
    assert _jcs(vector["input"]) == vector["canonical_json"]
    assert _canonical_hash(vector["input"]) == vector["sha256"]


def test_checksum_reference_vectors_reject_every_projected_field_mutation() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    for kind in ("TRADING_CALENDAR", "MARKET_SNAPSHOT", "BAR_AGGREGATION_CHECKPOINT"):
        value = by_type[kind]
        _assert_checksum(kind, value)
        fields = _semantic_contract()["semantic_validation"]["checksums"][kind]["projection"]
        for field in fields:
            changed = deepcopy(value)
            changed[field] = _different_value(changed[field])
            with pytest.raises(ValueError, match="checksum mismatch"):
                _assert_checksum(kind, changed)

    bar = _load(FIXTURES / "market.bar_closed.v1/minimal.valid.json")
    _assert_checksum("market.bar_closed.v1", bar)
    fields = _semantic_contract()["semantic_validation"]["checksums"]["market.bar_closed.v1"][
        "projection"
    ]
    for field in fields:
        changed = deepcopy(bar)
        changed[field] = _different_value(changed[field])
        with pytest.raises(ValueError, match="checksum mismatch"):
            _assert_checksum("market.bar_closed.v1", changed)

    policy = _market_policy()
    _assert_checksum("MARKET_VALIDATION_POLICY", policy)
    policy_fields = _semantic_contract()["semantic_validation"]["checksums"][
        "MARKET_VALIDATION_POLICY"
    ]["projection"]
    for field in policy_fields:
        changed = deepcopy(policy)
        changed[field] = _different_value(changed[field])
        with pytest.raises(ValueError, match="checksum mismatch"):
            _assert_checksum("MARKET_VALIDATION_POLICY", changed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timezone", "Asia/Tokyo"),
        ("tzdb_version", "2025b"),
        ("open_fold", 1),
        ("close_fold", 1),
        ("open_utc_offset_seconds", "32400"),
        ("close_utc_offset_seconds", "32400"),
    ],
)
def test_calendar_timezone_tzdb_fold_and_offset_are_checksum_bound(
    field: str, value: object
) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    calendar = next(dto for dto in document["dtos"] if dto["dto_type"] == "TRADING_CALENDAR")
    changed = deepcopy(calendar)
    if field in {"timezone", "tzdb_version"}:
        changed[field] = value
    else:
        changed["sessions"][0][field] = value
    with pytest.raises(ValueError, match="checksum mismatch"):
        _assert_checksum("TRADING_CALENDAR", changed)


def test_bar_window_finality_identity_and_checksum_guards() -> None:
    base = _load(FIXTURES / "market.bar_closed.v1/minimal.valid.json")
    validate_market_event_semantics("market.bar_closed.v1", base)

    cases: list[tuple[str, dict[str, object], str]] = [
        (
            "timeframe",
            {"window_end": "2026-08-11T01:30:30Z"},
            "bar window/timeframe mismatch",
        ),
        (
            "alignment",
            {
                "window_start": "2026-08-11T01:30:30Z",
                "window_end": "2026-08-11T01:31:30Z",
                "event_time": "2026-08-11T01:31:30Z",
                "received_at": "2026-08-11T01:31:30.501Z",
                "watermark_event_time": "2026-08-11T01:31:31.000Z",
            },
            "bar window is not aligned",
        ),
        (
            "cross-session",
            {
                "window_start": "2026-08-11T03:29:00Z",
                "window_end": "2026-08-11T03:31:00Z",
                "timeframe_seconds": 120,
                "event_time": "2026-08-11T03:31:00Z",
                "received_at": "2026-08-11T03:31:00.501Z",
                "watermark_event_time": "2026-08-11T03:31:00.500Z",
            },
            "bar crosses session boundary",
        ),
        (
            "event-time",
            {"event_time": "2026-08-11T01:30:59Z"},
            "final bar event_time must equal window_end",
        ),
        (
            "watermark-time",
            {"watermark_event_time": "2026-08-11T01:31:00.499Z"},
            "bar finalized before allowed lateness watermark",
        ),
    ]
    for _, changes, error in cases:
        candidate = deepcopy(base)
        candidate.update(changes)
        _refresh_bar_identity_and_checksum(candidate)
        with pytest.raises(ValueError, match=error):
            validate_market_event_semantics("market.bar_closed.v1", candidate)

    bad_id = deepcopy(base)
    bad_id["event_id"] = "550e8400-e29b-41d4-a716-446655449999"
    with pytest.raises(ValueError, match="UUIDv5 identity mismatch"):
        validate_market_event_semantics("market.bar_closed.v1", bad_id)

    bad_checksum = deepcopy(base)
    bad_checksum["content_checksum"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_market_event_semantics("market.bar_closed.v1", bad_checksum)


def _different_value(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return f"{value}-changed"
    if isinstance(value, list):
        return [*value, {"changed": True}]
    if value is None:
        return 1
    raise TypeError(type(value).__name__)


def _schema_error_messages(errors: list[Any]) -> str:
    messages: list[str] = []

    def visit(error: Any) -> None:
        messages.append(error.message)
        for child in error.context:
            visit(child)

    for error in errors:
        visit(error)
    return " ".join(messages)


@pytest.mark.parametrize("message_type", EVENTS)
def test_market_event_payloads_fit_the_canonical_message_envelope(
    message_type: str,
) -> None:
    payload = _load(FIXTURES / message_type / "minimal.valid.json")
    validate_market_message(_market_envelope(message_type, payload))


@pytest.mark.parametrize("message_type", EVENTS)
@pytest.mark.parametrize(
    "field,replacement",
    [
        ("source", "WrongPublisher"),
        ("partition_key", "wrong-partition"),
        ("aggregate_id", "wrong-aggregate"),
        ("aggregate_version", 999999),
        ("message_id", "wrong-message-id-0001"),
        ("idempotency_key", "unrelated-idempotency-key"),
        ("schema_version", 2),
    ],
)
def test_combined_validator_rejects_individually_valid_envelope_misbinding(
    message_type: str, field: str, replacement: object
) -> None:
    payload = _load(FIXTURES / message_type / "minimal.valid.json")
    envelope = _market_envelope(message_type, payload)
    envelope[field] = replacement
    with pytest.raises(ValueError):
        validate_market_message(envelope)


def test_idempotency_identity_is_separate_from_payload_fingerprint() -> None:
    payload = _load(FIXTURES / "market.tick_received.v1/minimal.valid.json")
    envelope = _market_envelope("market.tick_received.v1", payload)
    guard: dict[str, str] = {}
    validate_market_message(envelope, guard)
    validate_market_message(deepcopy(envelope), guard)

    collision = deepcopy(envelope)
    collision["payload"]["received_at"] = "2026-08-11T01:30:00.002Z"
    collision["received_at"] = "2026-08-11T01:30:00.002Z"
    with pytest.raises(ValueError, match="idempotency identity collision"):
        validate_market_message(collision, guard)


@pytest.mark.parametrize(
    "mutator,error",
    [
        (
            lambda payload: payload.update(previous_quality="NORMAL"),
            "illegal quality transition/reason",
        ),
        (
            lambda payload: payload.update(quality_version=payload["previous_quality_version"]),
            "quality version must increase exactly once",
        ),
        (
            lambda payload: payload.update(
                source_version=payload["previous_source_version"] - 1,
                source_sequence=payload["previous_source_version"] - 1,
            ),
            "source version regressed",
        ),
        (
            lambda payload: payload["recovery_evidence"].update(provider="FORGED"),
            "recovery identity binding mismatch",
        ),
        (
            lambda payload: payload["recovery_evidence"].update(snapshot_checksum="f" * 64),
            "recovery evidence checksum mismatch",
        ),
        (
            lambda payload: payload["recovery_evidence"].update(
                checkpoint_identity="missing:checkpoint"
            ),
            "recovery evidence identity is unresolved",
        ),
        (
            lambda payload: payload["recovery_evidence"].update(
                backfill_start_sequence=100,
                gap_start_sequence=100,
                backfill_end_sequence=200,
                gap_end_sequence=200,
            ),
            "recovery range is not bound to source versions",
        ),
    ],
)
def test_quality_transition_and_recovery_evidence_fail_closed(mutator: Any, error: str) -> None:
    payload = _load(FIXTURES / "market.quality_changed.v1/minimal.valid.json")
    mutator(payload)
    with pytest.raises(ValueError, match=error):
        validate_market_event_semantics("market.quality_changed.v1", payload)


def test_quality_gap_range_is_bound_to_source_versions() -> None:
    payload = _load(FIXTURES / "market.quality_changed.v1/maximal.valid.json")
    validate_market_event_semantics("market.quality_changed.v1", payload)
    payload["gap_start_sequence"] = 100
    payload["gap_end_sequence"] = 200
    with pytest.raises(ValueError, match="quality gap is not bound"):
        validate_market_event_semantics("market.quality_changed.v1", payload)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("timezone", "Not/AZone", "calendar timezone is not IANA"),
        ("trading_day", "2026-08-12", "calendar trading-day mapping mismatch"),
    ],
)
def test_calendar_timezone_and_trading_day_mapping_are_validated(
    field: str, value: object, error: str
) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    calendar = next(dto for dto in document["dtos"] if dto["dto_type"] == "TRADING_CALENDAR")
    calendar[field] = value
    _refresh_checksum("TRADING_CALENDAR", calendar)
    with pytest.raises(ValueError, match=error):
        validate_market_contract_semantics(document)


def test_aggregation_input_must_fall_inside_bound_session() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    item = next(dto for dto in document["dtos"] if dto["dto_type"] == "BAR_AGGREGATION_INPUT")
    item["event_time"] = "2026-08-11T04:00:00Z"
    with pytest.raises(ValueError, match="outside bound session"):
        validate_market_contract_semantics(document)


def test_same_quality_version_different_payload_is_a_collision() -> None:
    payload = _load(FIXTURES / "market.quality_changed.v1/minimal.valid.json")
    envelope = _market_envelope("market.quality_changed.v1", payload)
    guard: dict[str, str] = {}
    validate_market_message(envelope, guard)
    collision = deepcopy(envelope)
    collision["payload"]["received_at"] = "2026-08-11T01:30:00.002Z"
    collision["received_at"] = "2026-08-11T01:30:00.002Z"
    with pytest.raises(ValueError, match="idempotency identity collision"):
        validate_market_message(collision, guard)


@pytest.mark.parametrize("message_type", EVENTS)
@pytest.mark.parametrize("fixture_name", ["minimal.valid.json", "maximal.valid.json"])
def test_market_event_valid_fixtures_pass_schema_and_semantics(
    message_type: str, fixture_name: str
) -> None:
    payload = _load(FIXTURES / message_type / fixture_name)
    _validator(EVENTS[message_type]).validate(payload)
    validate_market_event_semantics(message_type, payload)


@pytest.mark.parametrize("message_type", EVENTS)
@pytest.mark.parametrize(
    "fixture_name",
    [
        "invalid.missing-required.json",
        "invalid.additional-property.json",
        "invalid.enum.json",
        "invalid.precision.json",
        "semantic-invalid.cross-field.json",
    ],
)
def test_market_event_invalid_fixture_matrix_is_rejected(
    message_type: str, fixture_name: str
) -> None:
    payload = _load(FIXTURES / message_type / fixture_name)
    errors = list(_validator(EVENTS[message_type]).iter_errors(payload))
    if errors:
        return
    with pytest.raises(ValueError):
        validate_market_event_semantics(message_type, payload)


def test_internal_market_gateway_and_aggregator_contract_is_machine_valid() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    for dto in document["dtos"]:
        validator.validate(dto)
    validate_market_contract_semantics(document)


def test_gateway_idempotency_snapshot_failure_and_health_matrix_are_exhaustive() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}

    replay = deepcopy(by_type["SUBSCRIPTION_RESULT"])
    replay["outcome"] = "IDEMPOTENT_REPLAY"
    replay["reason_code"] = "ALREADY_APPLIED"
    validator.validate(replay)

    rejected_snapshot = deepcopy(by_type["SNAPSHOT_RESULT"])
    rejected_snapshot["outcome"] = "REJECTED"
    rejected_snapshot["reason_code"] = "STALE"
    rejected_snapshot["snapshot"] = None
    validator.validate(rejected_snapshot)

    health = by_type["MARKET_HEALTH"]
    for status, quality, reason in [
        ("HEALTHY", "NORMAL", "OK"),
        ("DEGRADED", "DEGRADED", "BACKPRESSURE"),
        ("DEGRADED", "STALE", "STALE"),
        ("DEGRADED", "GAP", "GAP"),
        ("DEGRADED", "RECOVERING", "RECOVERING"),
        ("DISCONNECTED", "UNAVAILABLE", "DISCONNECTED"),
    ]:
        candidate = deepcopy(health)
        candidate.update(status=status, quality=quality, reason_code=reason)
        validator.validate(candidate)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("quality", "STALE", "AVAILABLE snapshot is not trade-safe"),
        ("stale", True, "AVAILABLE snapshot is not trade-safe"),
        ("unresolved_gap_count", 1, "AVAILABLE snapshot is not trade-safe"),
        ("checksum_verified", False, "AVAILABLE snapshot is not trade-safe"),
        ("provider", "WRONG", "snapshot request/version binding mismatch"),
        ("generation", 2, "snapshot request/version binding mismatch"),
        ("calendar_version", "cal-v2", "snapshot request/version binding mismatch"),
        ("session_id", "pm", "snapshot request/version binding mismatch"),
        ("source_version", 11, "snapshot request/version binding mismatch"),
        ("quality_version", 3, "snapshot request/version binding mismatch"),
        ("aggregation_policy_version", "bar-v2", "snapshot request/version binding mismatch"),
    ],
)
def test_available_snapshot_fails_closed_for_unsafe_or_unbound_evidence(
    field: str, value: object, expected: str
) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    snapshot = next(dto for dto in document["dtos"] if dto["dto_type"] == "MARKET_SNAPSHOT")
    snapshot[field] = value
    _refresh_checksum("MARKET_SNAPSHOT", snapshot)
    result = next(dto for dto in document["dtos"] if dto["dto_type"] == "SNAPSHOT_RESULT")
    result["snapshot"] = deepcopy(snapshot)
    with pytest.raises(ValueError, match=expected):
        validate_market_contract_semantics(document)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("queue_depth", 614, "false HEALTHY under queue/lag threshold"),
        ("source_lag_ms", 2000, "false HEALTHY under queue/lag threshold"),
        ("queue_depth", 1025, "queue depth exceeds capacity"),
        ("warning_watermark", 900, "health thresholds invalid"),
        ("critical_watermark", 980, "health thresholds invalid"),
        ("overflow_watermark", 1025, "health thresholds invalid"),
        ("provider", "WRONG", "health version/policy binding mismatch"),
        ("generation", 2, "health version/policy binding mismatch"),
        ("policy_version", "market-policy-v2", "health version/policy binding mismatch"),
    ],
)
def test_health_and_backpressure_thresholds_reject_false_healthy(
    field: str, value: object, error: str
) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    health = next(dto for dto in document["dtos"] if dto["dto_type"] == "MARKET_HEALTH")
    health[field] = value
    with pytest.raises(ValueError, match=error):
        validate_market_contract_semantics(document)


def test_v1_rejects_tick_coalescing_policy() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    request = next(dto for dto in document["dtos"] if dto["dto_type"] == "SUBSCRIPTION_REQUEST")
    request["overflow_policy"] = "COALESCE_WITH_GAP_EVIDENCE"
    assert not _validator("market/market-data.v1.schema.json").is_valid(request)
    with pytest.raises(ValueError, match="tick coalescing is forbidden"):
        validate_market_contract_semantics(document)


def test_market_health_rejects_every_contradictory_status_combination() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    validator = _validator("market/market-data.v1.schema.json")
    health = next(dto for dto in document["dtos"] if dto["dto_type"] == "MARKET_HEALTH")
    allowed = {
        ("HEALTHY", "NORMAL", "OK"),
        ("DEGRADED", "DEGRADED", "BACKPRESSURE"),
        ("DEGRADED", "DEGRADED", "SOURCE_LAG"),
        ("DEGRADED", "STALE", "STALE"),
        ("DEGRADED", "GAP", "GAP"),
        ("DEGRADED", "RECOVERING", "RECOVERING"),
        ("DISCONNECTED", "UNAVAILABLE", "UNAVAILABLE"),
        ("DISCONNECTED", "UNAVAILABLE", "DISCONNECTED"),
    }
    statuses = ["HEALTHY", "DEGRADED", "DISCONNECTED"]
    qualities = ["NORMAL", "DEGRADED", "STALE", "GAP", "UNAVAILABLE", "RECOVERING"]
    reasons = [
        "OK",
        "BACKPRESSURE",
        "SOURCE_LAG",
        "STALE",
        "GAP",
        "RECOVERING",
        "UNAVAILABLE",
        "DISCONNECTED",
    ]
    for status, quality, reason in product(statuses, qualities, reasons):
        candidate = deepcopy(health)
        candidate.update(status=status, quality=quality, reason_code=reason)
        assert validator.is_valid(candidate) is ((status, quality, reason) in allowed)


def test_internal_schema_invalid_matrix_is_rejected() -> None:
    validator = _validator("market/market-data.v1.schema.json")
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    cases = _load(FIXTURES / "internal/market-data.v1/schema_invalid.json")["cases"]
    for case in cases:
        candidate = deepcopy(by_type[case["dto_type"]])
        target = candidate
        path = case["field"].split(".")
        for part in path[:-1]:
            target = target[part]
        if case["operation"] == "remove":
            target.pop(path[-1])
        else:
            target[path[-1]] = case["value"]
        errors = list(validator.iter_errors(candidate))
        assert errors, case["name"]
        assert case["error"] in _schema_error_messages(errors), case["name"]


def test_internal_semantic_invalid_matrix_is_rejected() -> None:
    base = _load(FIXTURES / "internal/market-data.v1/valid.json")
    for case in _load(FIXTURES / "internal/market-data.v1/semantic-invalid.json")["cases"]:
        document = deepcopy(base)
        dto = next(item for item in document["dtos"] if item["dto_type"] == case["dto_type"])
        dto[case["field"]] = case["value"]
        with pytest.raises(ValueError, match=case["error"]):
            validate_market_contract_semantics(document)


def test_live_and_replay_inputs_share_schema_identity_and_deterministic_order() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    inputs = [dto for dto in document["dtos"] if dto["dto_type"] == "BAR_AGGREGATION_INPUT"]
    live = [
        {k: v for k, v in dto.items() if k != "mode"} for dto in inputs if dto["mode"] == "LIVE"
    ]
    replay = [
        {k: v for k, v in dto.items() if k != "mode"} for dto in inputs if dto["mode"] == "REPLAY"
    ]
    assert live == replay
    assert [_canonical_hash(item) for item in live] == [_canonical_hash(item) for item in replay]


def _aggregate_reference_vector(
    inputs: list[dict[str, Any]], expected_shape: dict[str, Any]
) -> dict[str, Any]:
    ordered = sorted(
        inputs,
        key=lambda item: (
            _utc(item["event_time"]),
            item["source_sequence"],
            item["event_id"],
        ),
    )
    result = deepcopy(expected_shape)
    prices = [Decimal(item["price"]) for item in ordered]
    result.update(
        open=ordered[0]["price"],
        close=ordered[-1]["price"],
        high=format(max(prices), "f"),
        low=format(min(prices), "f"),
        volume=sum(item["quantity"] for item in ordered),
        turnover=format(sum(Decimal(item["turnover"]) for item in ordered), "f"),
        source_sequence_start=min(item["source_sequence"] for item in ordered),
        source_sequence_end=max(item["source_sequence"] for item in ordered),
        watermark_sequence=max(item["source_sequence"] for item in ordered),
    )
    _refresh_bar_identity_and_checksum(result)
    return result


def test_live_and_replay_reference_vector_computes_identical_complete_bar() -> None:
    vector = _load(FIXTURES / "internal/market-data.v1/bar-reference-vector.json")
    inputs = cast(list[dict[str, Any]], vector["inputs"])
    expected = cast(dict[str, Any], vector["expected_bar"])
    live = _aggregate_reference_vector(inputs, expected)
    replay = _aggregate_reference_vector(list(reversed(inputs)), expected)
    assert live == expected
    assert replay == expected
    validate_market_event_semantics("market.bar_closed.v1", live)


def _market_policy() -> dict[str, Any]:
    return _load(FIXTURES / "internal/market-data.v1/validation-policy.valid.json")


def _snapshot_exchange() -> tuple[dict[str, Any], dict[str, Any]]:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    return by_type["SNAPSHOT_REQUEST"], by_type["SNAPSHOT_RESULT"]


@pytest.mark.parametrize(
    "evaluation_at,valid",
    [
        ("2026-08-11T01:30:00.999Z", True),
        ("2026-08-11T01:30:01.000Z", True),
        ("2026-08-11T01:30:01.001Z", False),
    ],
)
def test_snapshot_freshness_uses_trusted_policy_millisecond_boundary(
    evaluation_at: str, valid: bool
) -> None:
    request, result = _snapshot_exchange()
    if valid:
        validate_snapshot_exchange(request, result, _market_policy(), evaluation_at)
    else:
        with pytest.raises(ValueError, match="snapshot freshness policy violation"):
            validate_snapshot_exchange(request, result, _market_policy(), evaluation_at)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda request, result, policy: result["snapshot"].update(
                as_of="2000-01-01T00:00:00Z", stale=False
            ),
            "snapshot freshness policy violation",
        ),
        (
            lambda request, result, policy: result["snapshot"].update(
                as_of="2026-08-11T01:30:01.101Z", stale=False
            ),
            "snapshot future clock skew",
        ),
        (
            lambda request, result, policy: result["snapshot"].update(
                source_sequence=11, source_version=10
            ),
            "snapshot source sequence/version mismatch",
        ),
        (
            lambda request, result, policy: policy.update(
                queue_capacity=1_000_000,
                warning_watermark=900_000,
                critical_watermark=950_000,
                overflow_watermark=999_000,
                source_lag_stale_ms=999_999,
            ),
            "validation policy checksum mismatch",
        ),
        (
            lambda request, result, policy: policy.update(policy_version="other"),
            "validation policy identity mismatch",
        ),
        (
            lambda request, result, policy: policy.update(policy_checksum="f" * 64),
            "validation policy checksum mismatch",
        ),
    ],
)
def test_snapshot_policy_context_rejects_untrusted_or_forged_inputs(
    mutation: Any, error: str
) -> None:
    request, result = _snapshot_exchange()
    policy = _market_policy()
    mutation(request, result, policy)
    snapshot = result.get("snapshot")
    if isinstance(snapshot, dict):
        _refresh_checksum("MARKET_SNAPSHOT", snapshot)
    with pytest.raises(ValueError, match=error):
        validate_snapshot_exchange(request, result, policy, "2026-08-11T01:30:01.000Z")


@pytest.mark.parametrize(
    "reason",
    [
        "DEADLINE_EXCEEDED",
        "UNAVAILABLE",
        "STALE",
        "GAP",
        "CHECKSUM_UNVERIFIED",
        "INVALID_REQUEST",
    ],
)
def test_every_rejected_snapshot_reason_uses_same_request_context_validator(
    reason: str,
) -> None:
    request, result = _snapshot_exchange()
    result.update(outcome="REJECTED", reason_code=reason, snapshot=None)
    _validator("market/market-data.v1.schema.json").validate(result)
    validate_snapshot_exchange(request, result, _market_policy(), "2026-08-11T01:30:01.000Z")


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda result: result.update(
                outcome="REJECTED", reason_code="AVAILABLE", snapshot=None
            ),
            "snapshot outcome/reason mismatch",
        ),
        (
            lambda result: result.update(
                outcome="REJECTED",
                reason_code="STALE",
                snapshot={"forbidden": True},
            ),
            "REJECTED snapshot must be null",
        ),
        (
            lambda result: result.update(request_id="550e8400-e29b-41d4-a716-446655449999"),
            "snapshot request identity mismatch",
        ),
    ],
)
def test_rejected_snapshot_reason_payload_and_identity_mismatches_fail_closed(
    mutation: Any, error: str
) -> None:
    request, result = _snapshot_exchange()
    result.update(outcome="REJECTED", reason_code="STALE", snapshot=None)
    mutation(result)
    with pytest.raises(ValueError, match=error):
        validate_snapshot_exchange(request, result, _market_policy(), "2026-08-11T01:30:01.000Z")


@pytest.mark.parametrize(
    "queue_depth,source_lag_ms,status,quality,reason",
    [
        (613, 1999, "HEALTHY", "NORMAL", "OK"),
        (614, 1999, "DEGRADED", "DEGRADED", "BACKPRESSURE"),
        (819, 1999, "DEGRADED", "DEGRADED", "BACKPRESSURE"),
        (972, 1999, "DEGRADED", "GAP", "GAP"),
        (10, 2000, "DEGRADED", "STALE", "STALE"),
    ],
)
def test_health_status_is_recomputed_from_accepted_policy(
    queue_depth: int,
    source_lag_ms: int,
    status: str,
    quality: str,
    reason: str,
) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    health = by_type["MARKET_HEALTH"]
    health.update(
        queue_depth=queue_depth,
        source_lag_ms=source_lag_ms,
        status=status,
        quality=quality,
        reason_code=reason,
    )
    validate_health_exchange(
        by_type["HEALTH_REQUEST"],
        health,
        _market_policy(),
        "2026-08-11T01:30:00Z",
    )


def test_health_cannot_inflate_all_self_reported_thresholds() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    health = by_type["MARKET_HEALTH"]
    health.update(
        queue_capacity=1_000_000,
        warning_watermark=900_000,
        critical_watermark=950_000,
        overflow_watermark=999_000,
        source_lag_stale_ms=999_999,
    )
    with pytest.raises(ValueError, match="health thresholds do not match accepted policy"):
        validate_health_exchange(
            by_type["HEALTH_REQUEST"],
            health,
            _market_policy(),
            "2026-08-11T01:30:00Z",
        )


def test_health_observed_at_must_match_injected_context() -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    by_type = {dto["dto_type"]: dto for dto in document["dtos"]}
    with pytest.raises(ValueError, match="health observed_at context mismatch"):
        validate_health_exchange(
            by_type["HEALTH_REQUEST"],
            by_type["MARKET_HEALTH"],
            _market_policy(),
            "2026-08-11T01:30:00.001Z",
        )


def _integer_schema_nodes(value: object) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") == "integer":
            nodes.append(value)
        for child in value.values():
            nodes.extend(_integer_schema_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_integer_schema_nodes(child))
    return nodes


def test_every_market_json_integer_schema_is_i_json_safe() -> None:
    schema_paths = [SCHEMAS / relative for relative in EVENTS.values()]
    schema_paths.append(SCHEMAS / "market/market-data.v1.schema.json")
    for path in schema_paths:
        for node in _integer_schema_nodes(_load(path)):
            assert node.get("maximum", SAFE_INTEGER_MAX) <= SAFE_INTEGER_MAX
            assert "maximum" in node, f"unbounded integer in {path}"


@pytest.mark.parametrize(
    "value,valid",
    [
        (SAFE_INTEGER_MAX, True),
        (SAFE_INTEGER_MAX + 1, False),
        (SAFE_INTEGER_MAX + 2, False),
        (10**30, False),
        (-SAFE_INTEGER_MAX - 1, False),
        (1.5, False),
    ],
)
def test_market_integer_safe_boundary_is_schema_enforced(value: object, valid: bool) -> None:
    document = _load(FIXTURES / "internal/market-data.v1/valid.json")
    item = next(dto for dto in document["dtos"] if dto["dto_type"] == "BAR_AGGREGATION_INPUT")
    item["source_sequence"] = value
    assert _validator("market/market-data.v1.schema.json").is_valid(item) is valid


@pytest.mark.parametrize("token", ["1e3", "1E+3", "1.0", "-1"])
def test_noncanonical_integer_wire_tokens_are_rejected(token: str) -> None:
    with pytest.raises(ValueError, match="canonical unsigned safe integer token"):
        validate_unsigned_integer_token(token)


def test_safe_integer_jcs_cross_language_reference_vector() -> None:
    value = {"safe": SAFE_INTEGER_MAX, "decimal": "9007199254740991.00"}
    expected = '{"decimal":"9007199254740991.00","safe":9007199254740991}'
    assert _jcs(value).encode("utf-8") == expected.encode("utf-8")
    assert (
        _canonical_hash(value) == "841b22f8ce183dafb48820ed983911baf3c2c33d6fde00b3bfb737aa2d64ef36"
    )
    assert (
        str(uuid.uuid5(uuid.UUID("9a41e905-11f3-5c30-8f02-5ba3f8ae8485"), expected))
        == "ef05fe42-6716-5f00-b484-7769ceafed5a"
    )


def test_zoneinfo_reference_vectors_cover_tokyo_new_york_dst_and_midnight() -> None:
    shanghai = _resolve_local_boundary("2026-08-11T09:30:00", "Asia/Shanghai", 0)
    tokyo = _resolve_local_boundary("2026-08-11T09:30:00", "Asia/Tokyo", 0)
    fold_zero = _resolve_local_boundary("2026-11-01T01:30:00", "America/New_York", 0)
    fold_one = _resolve_local_boundary("2026-11-01T01:30:00", "America/New_York", 1)
    assert shanghai.utcoffset() == timedelta(hours=8)
    assert tokyo.utcoffset() == timedelta(hours=9)
    assert fold_zero.utcoffset() != fold_one.utcoffset()
    opened = _resolve_local_boundary("2026-08-11T23:00:00", "Asia/Tokyo", 0)
    closed = _resolve_local_boundary("2026-08-12T01:00:00", "Asia/Tokyo", 0)
    assert opened.date() != closed.date()


def test_frozen_tzdb_reference_bundle_version_and_digests() -> None:
    reference = _load(FIXTURES / "internal/market-data.v1/tzdb-reference.json")
    assert reference["iana_version"] == _market_policy()["tzdb_version"]
    for name, expected in reference["files"].items():
        path = TZDB_FIXTURE / Path(*name.split("/"))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_zoneinfo_rejects_unknown_and_nonexistent_dst_boundary() -> None:
    with pytest.raises(ValueError, match="not IANA or tzdb is unavailable"):
        _iana_zone("Not/AZone")
    with pytest.raises(ValueError, match="nonexistent local boundary"):
        _resolve_local_boundary("2026-03-08T02:30:00", "America/New_York", 0)
    with pytest.raises(ValueError, match="local boundary/fold is invalid"):
        _resolve_local_boundary("2026-11-01T01:30:00", "America/New_York", 2)


def test_public_session_semantics_cover_tokyo_midnight_and_new_york_dst_fold() -> None:
    base = _load(FIXTURES / "market.session_changed.v1/minimal.valid.json")
    tokyo = deepcopy(base)
    tokyo.update(
        timezone="Asia/Tokyo",
        session_open_at="2026-08-11T14:00:00Z",
        session_close_at="2026-08-11T16:00:00Z",
        session_open_fold=0,
        session_close_fold=0,
        session_open_utc_offset_seconds="32400",
        session_close_utc_offset_seconds="32400",
        trading_day="2026-08-12",
        crosses_local_midnight=True,
    )
    validate_market_event_semantics("market.session_changed.v1", tokyo)

    new_york = deepcopy(base)
    new_york.update(
        timezone="America/New_York",
        event_time="2026-11-01T05:15:00Z",
        received_at="2026-11-01T05:15:00.001Z",
        session_open_at="2026-11-01T05:30:00Z",
        session_close_at="2026-11-01T06:30:00Z",
        session_open_fold=0,
        session_close_fold=1,
        session_open_utc_offset_seconds="-14400",
        session_close_utc_offset_seconds="-18000",
        trading_day="2026-11-01",
        crosses_local_midnight=False,
    )
    validate_market_event_semantics("market.session_changed.v1", new_york)
    new_york["session_close_fold"] = 0
    with pytest.raises(ValueError, match="session fold binding mismatch"):
        validate_market_event_semantics("market.session_changed.v1", new_york)
