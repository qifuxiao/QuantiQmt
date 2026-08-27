"""MarketGateway protocol and adapter-neutral bounded in-memory implementation."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.canonical import canonical_sha256
from quantiqmt.market.errors import MarketContractError
from quantiqmt.market.normalization import TickNormalizer
from quantiqmt.market.observability import MarketObserver, NullMarketObserver
from quantiqmt.market.policy import AcceptedPolicyStore
from quantiqmt.market.quality import MarketQuality, QualityState, RecoveryEvidenceRegistry
from quantiqmt.market.validation import (
    QUALITY_PRIORITY,
    format_utc,
    parse_utc,
    validate_health_exchange,
    validate_market_dto,
    validate_snapshot_exchange,
)

LifecycleRequest = Mapping[str, object]
LifecycleResult = Mapping[str, object]
SubscriptionRequest = Mapping[str, object]
SubscriptionResult = Mapping[str, object]
SnapshotRequest = Mapping[str, object]
SnapshotResult = Mapping[str, object]
HealthRequest = Mapping[str, object]
MarketHealth = Mapping[str, object]


class Clock(Protocol):
    def now(self) -> datetime: ...


class MarketGateway(Protocol):
    def start(self, request: LifecycleRequest) -> LifecycleResult: ...
    def stop(self, request: LifecycleRequest) -> LifecycleResult: ...
    def subscribe(self, request: SubscriptionRequest) -> SubscriptionResult: ...
    def unsubscribe(self, request: SubscriptionRequest) -> SubscriptionResult: ...
    def snapshot(self, request: SnapshotRequest) -> SnapshotResult: ...
    def health(self, request: HealthRequest) -> MarketHealth: ...


@dataclass(frozen=True, slots=True)
class IngressResult:
    accepted: bool
    reason_code: str
    gap_start_sequence: int | None = None
    gap_end_sequence: int | None = None


@dataclass(slots=True)
class _Subscription:
    request: dict[str, object]
    fingerprint: str
    queue: deque[dict[str, object]]
    active: bool = True


class InMemoryMarketGateway:
    """Adapter-neutral core; vendor connectivity remains outside TASK-023."""

    def __init__(
        self,
        *,
        clock: Clock,
        policies: AcceptedPolicyStore,
        normalizer: TickNormalizer | None = None,
        observer: MarketObserver | None = None,
        registry: SchemaRegistry | None = None,
        recovery_registry: RecoveryEvidenceRegistry | None = None,
    ) -> None:
        self._clock = clock
        self._policies = policies
        self._registry = registry or SchemaRegistry()
        self._normalizer = normalizer or TickNormalizer(self._registry)
        self._observer = observer or NullMarketObserver()
        self._quality = MarketQuality(recovery_registry)
        self._subscriptions: dict[str, _Subscription] = {}
        self._operation_history: dict[tuple[str, int, str], tuple[str, dict[str, object]]] = {}
        self._lifecycle_history: dict[tuple[int, str], tuple[str, dict[str, object]]] = {}
        self._generation = 0
        self._fencing_token = 0
        self._running = False
        self._snapshots: dict[str, dict[str, object]] = {}
        self._last_received_at: dict[str, datetime] = {}

    def start(self, request: LifecycleRequest) -> dict[str, object]:
        return self._lifecycle(request, "START")

    def stop(self, request: LifecycleRequest) -> dict[str, object]:
        return self._lifecycle(request, "STOP")

    def subscribe(self, request: SubscriptionRequest) -> dict[str, object]:
        return self._subscription(request, "SUBSCRIBE")

    def unsubscribe(self, request: SubscriptionRequest) -> dict[str, object]:
        return self._subscription(request, "UNSUBSCRIBE")

    def on_tick(
        self,
        subscription_id: object,
        generation: int,
        fencing_token: int,
        raw: Mapping[str, object],
    ) -> IngressResult:
        if not self._running:
            return IngressResult(False, "UNAVAILABLE")
        if not isinstance(subscription_id, str):
            return IngressResult(False, "INVALID_REQUEST")
        subscription = self._subscriptions.get(subscription_id)
        if subscription is None or not subscription.active:
            return IngressResult(False, "UNAVAILABLE")
        request = subscription.request
        if generation != request["generation"] or generation < self._generation:
            return IngressResult(False, "STALE_GENERATION")
        if fencing_token != request["fencing_token"] or fencing_token < self._fencing_token:
            return IngressResult(False, "STALE_FENCING")
        try:
            payload = self._normalizer.normalize(raw, mode="LIVE")
        except (MarketContractError, ValueError):
            return IngressResult(False, "INVALID_REQUEST")
        instruments = cast(list[str], request["instruments"])
        if payload["instrument_id"] not in instruments:
            return IngressResult(False, "INVALID_REQUEST")
        for field in ("provider", "calendar_id", "calendar_version", "session_id"):
            if payload[field] != request[field]:
                return IngressResult(False, "INVALID_REQUEST")
        if "TICK" not in cast(list[str], request["event_types"]):
            return IngressResult(False, "INVALID_REQUEST")
        overflow = cast(int, request["overflow_watermark"])
        if len(subscription.queue) >= overflow:
            sequence = cast(int, payload["source_sequence"])
            return IngressResult(False, "OVERFLOW_REJECTED", sequence, sequence)
        subscription.queue.append(payload)
        return IngressResult(True, "ENQUEUED")

    def apply_gap_evidence(self, instrument_id: str, evidence: IngressResult) -> QualityState:
        if (
            evidence.accepted
            or evidence.gap_start_sequence is None
            or evidence.gap_end_sequence is None
        ):
            raise MarketContractError("exact rejected ingress gap evidence is required")
        if evidence.gap_start_sequence != evidence.gap_end_sequence:
            raise MarketContractError("overflow evidence must bind one rejected Tick")
        previous = self._quality.state(instrument_id)
        current = self._quality.overflow(instrument_id, evidence.gap_start_sequence)
        self._observer.increment(
            "market_overflow_rejected_total",
            {"provider": current.provider, "event_type": "TICK"},
        )
        self._observer.increment(
            "market_gap_total", {"provider": current.provider, "reason": current.reason_code}
        )
        self._observer.increment(
            "market_quality_transition_total",
            {
                "provider": current.provider,
                "from_state": previous.quality,
                "to_state": current.quality,
                "reason": current.reason_code,
            },
        )
        return current

    def drain(self, subscription_id: str, *, limit: int | None = None) -> list[dict[str, object]]:
        subscription = self._subscriptions[subscription_id]
        maximum = cast(int, subscription.request["batch_capacity"])
        count = maximum if limit is None else min(maximum, max(0, limit))
        drained: list[dict[str, object]] = []
        for _ in range(min(count, len(subscription.queue))):
            payload = subscription.queue[0]
            self._quality.observe_tick(payload)
            subscription.queue.popleft()
            drained.append(payload)
            instrument = cast(str, payload["instrument_id"])
            self._last_received_at[instrument] = parse_utc(
                payload["received_at"], field="received_at"
            )
            self._observer.increment(
                "market_ingress_total",
                {
                    "provider": cast(str, payload["provider"]),
                    "event_type": "TICK",
                    "outcome": "accepted",
                },
            )
        self._observer.observe(
            "market_queue_depth_ratio",
            len(subscription.queue) / cast(int, subscription.request["queue_capacity"]),
            {"provider": cast(str, subscription.request["provider"]), "event_type": "TICK"},
        )
        return drained

    def queue_depth(self, subscription_id: object) -> int:
        if not isinstance(subscription_id, str) or subscription_id not in self._subscriptions:
            return 0
        return len(self._subscriptions[subscription_id].queue)

    def quality(self, instrument_id: str) -> QualityState:
        return self._quality.state(instrument_id)

    def evaluate_staleness(self, instrument_id: str, *, observed_at: datetime) -> QualityState:
        state = self._quality.state(instrument_id)
        last_received = self._last_received_at.get(instrument_id)
        if last_received is None:
            return state
        subscription = next(
            (
                item
                for item in self._subscriptions.values()
                if instrument_id in cast(list[str], item.request["instruments"])
            ),
            None,
        )
        if subscription is None:
            return state
        threshold = cast(int, subscription.request["source_lag_stale_ms"])
        lag_ms = max(0, int((observed_at - last_received).total_seconds() * 1000))
        if lag_ms < threshold:
            return state
        current = self._quality.mark_stale(instrument_id, state.source_version)
        self._observer.increment(
            "market_quality_transition_total",
            {
                "provider": current.provider,
                "from_state": state.quality,
                "to_state": current.quality,
                "reason": current.reason_code,
            },
        )
        return current

    def put_snapshot(self, snapshot: Mapping[str, object]) -> None:
        instrument = snapshot.get("instrument_id")
        if not isinstance(instrument, str):
            raise MarketContractError("snapshot instrument_id is missing")
        self._snapshots[instrument] = dict(snapshot)

    def snapshot(self, request: SnapshotRequest) -> dict[str, object]:
        validate_market_dto(request, self._registry)
        policy = self._policies.resolve_snapshot(request)
        request_id = request.get("request_id")
        if self._deadline_exceeded(request):
            result = self._snapshot_rejection(request_id, "DEADLINE_EXCEEDED")
            validate_snapshot_exchange(request, result, policy, self._clock.now())
            return result
        instrument = request.get("instrument_id")
        snapshot = self._snapshots.get(cast(str, instrument))
        if snapshot is None:
            result = self._snapshot_rejection(request_id, "UNAVAILABLE")
            validate_snapshot_exchange(request, result, policy, self._clock.now())
            return result
        result = {
            "dto_type": "SNAPSHOT_RESULT",
            "schema_version": 1,
            "request_id": request_id,
            "outcome": "AVAILABLE",
            "reason_code": "AVAILABLE",
            "snapshot": dict(snapshot),
        }
        validate_snapshot_exchange(request, result, policy, self._clock.now())
        return result

    def health(self, request: HealthRequest) -> dict[str, object]:
        validate_market_dto(request, self._registry)
        now = self._clock.now()
        policy = self._policies.resolve(request)
        context = self._health_context(request)
        if context is None:
            return self._health_result(
                request,
                policy,
                now,
                quality="UNAVAILABLE",
                queue_depth=0,
                source_lag_ms=cast(int, policy["source_lag_stale_ms"]),
            )
        subscription, states = context
        source_version = max(state.source_version for state in states)
        quality_version = max(state.quality_version for state in states)
        if (
            request["source_version"] != source_version
            or request["quality_version"] != quality_version
        ):
            return self._health_result(
                request,
                policy,
                now,
                quality="UNAVAILABLE",
                queue_depth=0,
                source_lag_ms=cast(int, policy["source_lag_stale_ms"]),
            )
        quality = max(
            (state.quality for state in states), key=lambda value: QUALITY_PRIORITY[value]
        )
        source_lag_ms = max(
            (
                max(0, int((now - last_received).total_seconds() * 1000))
                if (last_received := self._last_received_at.get(state.instrument_id)) is not None
                else cast(int, policy["source_lag_stale_ms"])
            )
            for state in states
        )
        return self._health_result(
            request,
            policy,
            now,
            quality=quality,
            queue_depth=len(subscription.queue),
            source_lag_ms=source_lag_ms,
        )

    def _health_context(
        self, request: Mapping[str, object]
    ) -> tuple[_Subscription, tuple[QualityState, ...]] | None:
        if not self._running or request.get("generation") != self._generation:
            return None
        fields = ("provider", "generation", "calendar_id", "calendar_version", "session_id")
        candidates = [
            subscription
            for subscription in self._subscriptions.values()
            if subscription.active
            and subscription.request.get("fencing_token") == self._fencing_token
            and subscription.request.get("policy_version") == request.get("policy_version")
            and all(subscription.request.get(field) == request.get(field) for field in fields)
        ]
        if len(candidates) != 1:
            return None
        subscription = candidates[0]
        states: list[QualityState] = []
        for instrument_id in cast(list[str], subscription.request["instruments"]):
            try:
                state = self._quality.state(instrument_id)
            except MarketContractError:
                return None
            if any(
                getattr(state, field) != request.get(field)
                for field in fields
                if field != "generation"
            ):
                return None
            states.append(state)
        return (subscription, tuple(states)) if states else None

    @staticmethod
    def _health_result(
        request: Mapping[str, object],
        policy: Mapping[str, object],
        observed_at: datetime,
        *,
        quality: str,
        queue_depth: int,
        source_lag_ms: int,
    ) -> dict[str, object]:
        if quality == "UNAVAILABLE":
            status, reason = "DISCONNECTED", "UNAVAILABLE"
        elif quality == "GAP":
            status, reason = "DEGRADED", "GAP"
        elif quality == "STALE":
            status, reason = "DEGRADED", "STALE"
        elif quality == "RECOVERING":
            status, reason = "DEGRADED", "RECOVERING"
        elif source_lag_ms >= cast(int, policy["source_lag_stale_ms"]):
            status, reason, quality = "DEGRADED", "SOURCE_LAG", "DEGRADED"
        elif queue_depth >= cast(int, policy["warning_watermark"]):
            status, reason, quality = "DEGRADED", "BACKPRESSURE", "DEGRADED"
        elif quality == "DEGRADED":
            status, reason = "DEGRADED", "BACKPRESSURE"
        else:
            status, reason, quality = "HEALTHY", "OK", "NORMAL"
        result = {
            "dto_type": "MARKET_HEALTH",
            "schema_version": 1,
            "request_id": request["request_id"],
            "provider": request["provider"],
            "generation": request["generation"],
            "calendar_id": request["calendar_id"],
            "calendar_version": request["calendar_version"],
            "session_id": request["session_id"],
            "source_version": request["source_version"],
            "quality_version": request["quality_version"],
            "policy_version": request["policy_version"],
            "status": status,
            "quality": quality,
            "reason_code": reason,
            "observed_at": format_utc(observed_at),
            "queue_depth": queue_depth,
            "queue_capacity": policy["queue_capacity"],
            "warning_watermark": policy["warning_watermark"],
            "critical_watermark": policy["critical_watermark"],
            "overflow_watermark": policy["overflow_watermark"],
            "source_lag_ms": source_lag_ms,
            "source_lag_stale_ms": policy["source_lag_stale_ms"],
        }
        validate_health_exchange(request, result, policy, observed_at)
        return result

    def _lifecycle(self, request: Mapping[str, object], operation: str) -> dict[str, object]:
        try:
            validate_market_dto(request, self._registry)
        except ValueError:
            return self._lifecycle_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if request.get("operation") != operation:
            return self._lifecycle_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if self._deadline_exceeded(request):
            return self._lifecycle_result(request, operation, "REJECTED", "DEADLINE_EXCEEDED")
        generation = request.get("generation")
        fencing = request.get("fencing_token")
        if not isinstance(generation, int) or not isinstance(fencing, int):
            return self._lifecycle_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if generation < self._generation:
            return self._lifecycle_result(request, operation, "REJECTED", "STALE_GENERATION")
        if fencing < self._fencing_token:
            return self._lifecycle_result(request, operation, "REJECTED", "STALE_FENCING")
        identity = (generation, operation)
        fingerprint = canonical_sha256(dict(request))
        historical = self._lifecycle_history.get(identity)
        if historical is not None:
            if historical[0] == fingerprint:
                return self._lifecycle_result(
                    request, operation, "IDEMPOTENT_REPLAY", "ALREADY_APPLIED"
                )
            return self._lifecycle_result(request, operation, "REJECTED", "INVALID_REQUEST")
        self._generation, self._fencing_token = generation, fencing
        self._running = operation == "START"
        result = self._lifecycle_result(
            request, operation, "APPLIED", "STARTED" if operation == "START" else "STOPPED"
        )
        self._lifecycle_history[identity] = (fingerprint, result)
        return result

    def _subscription(self, request: Mapping[str, object], operation: str) -> dict[str, object]:
        try:
            validate_market_dto(request, self._registry)
        except ValueError:
            return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if request.get("operation") != operation:
            return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if self._deadline_exceeded(request):
            return self._subscription_result(request, operation, "REJECTED", "DEADLINE_EXCEEDED")
        subscription_id = request.get("subscription_id")
        generation = request.get("generation")
        fencing = request.get("fencing_token")
        if (
            not isinstance(subscription_id, str)
            or not isinstance(generation, int)
            or not isinstance(fencing, int)
        ):
            return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
        try:
            policy = self._policies.resolve(request)
            self._validate_subscription(request, policy)
        except MarketContractError:
            return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
        if generation < self._generation:
            return self._subscription_result(request, operation, "REJECTED", "STALE_GENERATION")
        if fencing < self._fencing_token:
            return self._subscription_result(request, operation, "REJECTED", "STALE_FENCING")
        identity = (subscription_id, generation, operation)
        fingerprint = canonical_sha256(dict(request))
        historical = self._operation_history.get(identity)
        if historical is not None:
            if historical[0] == fingerprint:
                return self._subscription_result(
                    request, operation, "IDEMPOTENT_REPLAY", "ALREADY_APPLIED"
                )
            return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
        existing = self._subscriptions.get(subscription_id)
        if operation == "UNSUBSCRIBE":
            if existing is None or existing.request["generation"] != generation:
                return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
            existing.active = False
            reason = "UNSUBSCRIBED"
        else:
            if existing is not None:
                return self._subscription_result(request, operation, "REJECTED", "INVALID_REQUEST")
            stored = dict(request)
            self._subscriptions[subscription_id] = _Subscription(stored, fingerprint, deque())
            for instrument in cast(list[str], request["instruments"]):
                self._quality.baseline(
                    provider=cast(str, request["provider"]),
                    instrument_id=instrument,
                    calendar_id=cast(str, request["calendar_id"]),
                    calendar_version=cast(str, request["calendar_version"]),
                    session_id=cast(str, request["session_id"]),
                    source_version=cast(int, request["source_version"]),
                    quality_version=cast(int, request["quality_version"]),
                )
            reason = "SUBSCRIBED"
        self._generation = max(self._generation, generation)
        self._fencing_token = max(self._fencing_token, fencing)
        result = self._subscription_result(request, operation, "APPLIED", reason)
        self._operation_history[identity] = (fingerprint, result)
        return result

    def _validate_subscription(
        self, request: Mapping[str, object], policy: Mapping[str, object]
    ) -> None:
        if request.get("overflow_policy") != "REJECT_NEW_WITH_GAP_EVIDENCE":
            raise MarketContractError("Tick coalescing is forbidden")
        for field in (
            "queue_capacity",
            "warning_watermark",
            "critical_watermark",
            "overflow_watermark",
            "source_lag_stale_ms",
        ):
            if request.get(field) != policy.get(field):
                raise MarketContractError("subscription thresholds do not match accepted policy")
        queue_capacity = cast(int, request["queue_capacity"])
        if not 0 < cast(int, request["batch_capacity"]) <= queue_capacity:
            raise MarketContractError("invalid batch capacity")
        if not (
            cast(int, request["warning_watermark"])
            < cast(int, request["critical_watermark"])
            < cast(int, request["overflow_watermark"])
            <= queue_capacity
        ):
            raise MarketContractError("invalid backpressure thresholds")

    def _deadline_exceeded(self, request: Mapping[str, object]) -> bool:
        try:
            return self._clock.now() > parse_utc(request["deadline_at"], field="deadline_at")
        except (KeyError, MarketContractError):
            return True

    def _lifecycle_result(
        self, request: Mapping[str, object], operation: str, outcome: str, reason: str
    ) -> dict[str, object]:
        return {
            "dto_type": "LIFECYCLE_RESULT",
            "schema_version": 1,
            "operation": operation,
            "request_id": request.get("request_id"),
            "generation": request.get("generation"),
            "outcome": outcome,
            "reason_code": reason,
            "effective_at": format_utc(self._clock.now()),
        }

    def _subscription_result(
        self, request: Mapping[str, object], operation: str, outcome: str, reason: str
    ) -> dict[str, object]:
        return {
            "dto_type": "SUBSCRIPTION_RESULT",
            "schema_version": 1,
            "operation": operation,
            "subscription_id": request.get("subscription_id"),
            "generation": request.get("generation"),
            "outcome": outcome,
            "reason_code": reason,
            "effective_at": format_utc(self._clock.now()),
        }

    @staticmethod
    def _snapshot_rejection(request_id: object, reason: str) -> dict[str, object]:
        return {
            "dto_type": "SNAPSHOT_RESULT",
            "schema_version": 1,
            "request_id": request_id,
            "outcome": "REJECTED",
            "reason_code": reason,
            "snapshot": None,
        }
