"""Bounded RiskEvaluationRunner using only an injected Clock port."""

from __future__ import annotations

import concurrent.futures
import hashlib
import threading
from collections.abc import Mapping
from typing import Any, Literal, Protocol

from quantiqmt.risk.audit import RiskAuditSemanticValidator
from quantiqmt.risk.evaluator import DeterministicRiskEvaluator, timeout_decision, timeout_result
from quantiqmt.risk.model import (
    RiskAuditOutputV1,
    RiskInputV1,
    RiskRuleSetV1,
    RuleResult,
    RuleTiming,
    ceil_div_us,
    rfc3339_z,
)

MetricName = Literal[
    "risk_evaluation_latency_us",
    "risk_rule_latency_us",
    "risk_decisions_total",
    "risk_fail_closed_total",
]


class RiskMetricsObserver(Protocol):
    def observe(self, name: MetricName, value: int, labels: Mapping[str, str]) -> None: ...


class NullRiskMetricsObserver:
    def observe(self, name: MetricName, value: int, labels: Mapping[str, str]) -> None:
        del name, value, labels


class Clock(Protocol):
    def monotonic_ns(self) -> int: ...
    def utc_now(self) -> object: ...


class RiskEvaluationRunner:
    """Run a pure evaluator with bounded timeout fencing and audit timings."""

    def __init__(
        self,
        evaluator: DeterministicRiskEvaluator,
        clock: Clock,
        *,
        max_workers: int = 1,
        max_in_flight: int = 1,
        metrics_observer: RiskMetricsObserver | None = None,
    ) -> None:
        if max_workers != 1:
            raise ValueError("RiskEvaluationRunner requires exactly one bounded worker")
        if max_in_flight != 1:
            raise ValueError("RiskEvaluationRunner supports exactly one in-flight evaluation")
        self._evaluator = evaluator
        self._clock = clock
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._attempt = 0
        self._admission = threading.BoundedSemaphore(value=1)
        self._seen_filter = _InputVersionFilter()
        self._metrics = metrics_observer or NullRiskMetricsObserver()

    def run(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> RiskAuditOutputV1:
        if not self._admission.acquire(blocking=False):
            return self._validate_and_record(
                self._saturation_audit(risk_input, rule_set),
                reason="RISK_EVALUATION_TIMEOUT",
            )
        ownership = _AdmissionOwnership(self._admission)
        try:
            input_version = risk_input.to_primitive()["input_version"]
            if not isinstance(input_version, str) or self._seen_filter.contains(input_version):
                return self._validate_and_record(
                    self._saturation_audit(risk_input, rule_set),
                    reason="RISK_EVALUATION_TIMEOUT",
                )
            self._seen_filter.add(input_version)
            self._attempt += 1
            attempt = self._attempt
            timeout_us = _timeout_us(rule_set)
            start_ns = self._clock.monotonic_ns()
            deadline_ns = start_ns + timeout_us * 1000
            results: list[RuleResult] = []
            timings: list[RuleTiming] = []
            iterator = self._evaluator.iter_rule_results(risk_input, rule_set)
            while True:
                before_ns = self._clock.monotonic_ns()
                remaining_ns = deadline_ns - before_ns
                if remaining_ns <= 0:
                    return self._validate_and_record(
                        self._timeout_audit(
                            risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                        ),
                        reason="RISK_EVALUATION_TIMEOUT",
                    )
                future = self._executor.submit(next, iterator, None)
                try:
                    result = future.result(timeout=remaining_ns / 1_000_000_000)
                except concurrent.futures.TimeoutError:
                    ownership.transfer_to_future(future)
                    return self._validate_and_record(
                        self._timeout_audit(
                            risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                        ),
                        reason="RISK_EVALUATION_TIMEOUT",
                    )
                after_ns = self._clock.monotonic_ns()
                if attempt != self._attempt:
                    return self._validate_and_record(
                        self._timeout_audit(
                            risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                        ),
                        reason="RISK_EVALUATION_TIMEOUT",
                    )
                if result is None:
                    break
                results.append(result)
                timings.append(
                    RuleTiming._validated(
                        result.evaluation_index,
                        result.rule_id,
                        max(1, ceil_div_us(after_ns - before_ns)),
                    )
                )
                if after_ns >= deadline_ns:
                    return self._validate_and_record(
                        self._timeout_audit(
                            risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                        ),
                        reason="RISK_EVALUATION_TIMEOUT",
                    )
            end_ns = self._clock.monotonic_ns()
            decision = self._evaluator.decide(risk_input, rule_set, tuple(results))
            return self._validate_and_record(
                RiskAuditOutputV1._validated(
                    decision=decision,
                    evaluated_at=rfc3339_z(self._clock.utc_now()),  # type: ignore[arg-type]
                    total_latency_us=max(
                        sum(t.latency_us for t in timings), ceil_div_us(end_ns - start_ns)
                    ),
                    evaluation_timeout_us=timeout_us,
                    completed_rule_count=len(results),
                    rule_timings=tuple(timings),
                )
            )
        finally:
            ownership.release_from_caller()

    def _timeout_audit(
        self,
        risk_input: RiskInputV1,
        rule_set: RiskRuleSetV1,
        results: list[RuleResult],
        timings: list[RuleTiming],
        start_ns: int,
        timeout_us: int,
        attempt: int,
    ) -> RiskAuditOutputV1:
        del attempt
        index = len(results)
        guard = timeout_result(index)
        results.append(guard)
        timings.append(RuleTiming._validated(index, guard.rule_id, 1))
        decision = timeout_decision(risk_input, rule_set, tuple(results))
        total = max(
            timeout_us,
            sum(t.latency_us for t in timings),
            ceil_div_us(self._clock.monotonic_ns() - start_ns),
        )
        return RiskAuditOutputV1._validated(
            decision=decision,
            evaluated_at=rfc3339_z(self._clock.utc_now()),  # type: ignore[arg-type]
            total_latency_us=total,
            evaluation_timeout_us=timeout_us,
            completed_rule_count=len(results) - 1,
            rule_timings=tuple(timings),
        )

    def _saturation_audit(
        self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1
    ) -> RiskAuditOutputV1:
        timeout_us = _timeout_us(rule_set)
        guard = timeout_result(0)
        decision = timeout_decision(risk_input, rule_set, (guard,))
        return RiskAuditOutputV1._validated(
            decision=decision,
            evaluated_at=rfc3339_z(self._clock.utc_now()),  # type: ignore[arg-type]
            total_latency_us=timeout_us,
            evaluation_timeout_us=timeout_us,
            completed_rule_count=0,
            rule_timings=(RuleTiming._validated(0, guard.rule_id, 1),),
        )

    def _validate_and_record(
        self, audit: RiskAuditOutputV1, *, reason: str | None = None
    ) -> RiskAuditOutputV1:
        RiskAuditSemanticValidator().validate(audit)
        self._metrics.observe("risk_evaluation_latency_us", audit.total_latency_us, {})
        for timing in audit.rule_timings:
            self._metrics.observe("risk_rule_latency_us", timing.latency_us, {})
        labels = {
            "decision": audit.decision.decision,
            "origin": audit.decision.decision_origin,
            "error_code": audit.decision.error_code or "NONE",
        }
        self._metrics.observe("risk_decisions_total", 1, labels)
        if audit.decision.decision == "REJECT":
            self._metrics.observe(
                "risk_fail_closed_total",
                1,
                {"reason": reason or audit.decision.primary_reason_code},
            )
        return audit


def _timeout_us(rule_set: RiskRuleSetV1) -> int:
    value = rule_set.to_primitive()["evaluation_timeout_us"]
    if not isinstance(value, int):
        raise ValueError("evaluation_timeout_us must be int")
    return value


class _AdmissionOwnership:
    """Release one admitted permit exactly once across caller/future handoff races."""

    def __init__(self, admission: threading.BoundedSemaphore) -> None:
        self._admission = admission
        self._lock = threading.Lock()
        self._state: Literal["caller", "registering", "callback", "released"] = "caller"

    def transfer_to_future(self, future: concurrent.futures.Future[Any]) -> None:
        with self._lock:
            if self._state != "caller":
                raise RuntimeError("admission ownership can only be transferred by its caller")
            self._state = "registering"
        try:
            future.add_done_callback(self._release_from_callback)
        except BaseException:
            with self._lock:
                if self._state == "registering":
                    self._state = "caller"
            raise
        with self._lock:
            if self._state == "registering":
                self._state = "callback"

    def release_from_caller(self) -> None:
        with self._lock:
            if self._state == "caller":
                self._release_locked()

    def _release_from_callback(self, _future: concurrent.futures.Future[Any]) -> None:
        with self._lock:
            if self._state in {"registering", "callback"}:
                self._release_locked()

    def _release_locked(self) -> None:
        self._admission.release()
        self._state = "released"


class _InputVersionFilter:
    """Fixed-size no-delete membership filter.

    False positives fail closed, but inserted input_version values are never forgotten by
    eviction, so same-input retries are not reopened by bounded-state maintenance.
    """

    _BITS = 16_384
    _MASKS = (0, 8, 16, 24)

    def __init__(self) -> None:
        self._bits = 0

    def add(self, input_version: str) -> None:
        for index in self._indexes(input_version):
            self._bits |= 1 << index

    def contains(self, input_version: str) -> bool:
        return all(self._bits & (1 << index) for index in self._indexes(input_version))

    @property
    def bounded_bit_count(self) -> int:
        return self._BITS

    @property
    def storage_bit_length(self) -> int:
        return self._bits.bit_length()

    def _indexes(self, input_version: str) -> tuple[int, ...]:
        digest = hashlib.sha256(input_version.encode("ascii")).digest()
        return tuple(
            int.from_bytes(digest[offset : offset + 2], "big") % self._BITS
            for offset in self._MASKS
        )
