"""Bounded RiskEvaluationRunner using only an injected Clock port."""

from __future__ import annotations

import concurrent.futures
from typing import Protocol

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
    ) -> None:
        if max_workers != 1:
            raise ValueError("RiskEvaluationRunner requires exactly one bounded worker")
        self._evaluator = evaluator
        self._clock = clock
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._attempt = 0

    def run(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> RiskAuditOutputV1:
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
                return self._timeout_audit(
                    risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                )
            future = self._executor.submit(next, iterator, None)
            try:
                result = future.result(timeout=remaining_ns / 1_000_000_000)
            except concurrent.futures.TimeoutError:
                future.cancel()
                return self._timeout_audit(
                    risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                )
            after_ns = self._clock.monotonic_ns()
            if attempt != self._attempt:
                return self._timeout_audit(
                    risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                )
            if result is None:
                break
            results.append(result)
            timings.append(
                RuleTiming(
                    result.evaluation_index,
                    result.rule_id,
                    max(1, ceil_div_us(after_ns - before_ns)),
                )
            )
            if after_ns >= deadline_ns:
                return self._timeout_audit(
                    risk_input, rule_set, results, timings, start_ns, timeout_us, attempt
                )
        end_ns = self._clock.monotonic_ns()
        decision = self._evaluator.decide(risk_input, rule_set, tuple(results))
        return RiskAuditOutputV1(
            decision=decision,
            evaluated_at=rfc3339_z(self._clock.utc_now()),  # type: ignore[arg-type]
            total_latency_us=max(
                sum(t.latency_us for t in timings), ceil_div_us(end_ns - start_ns)
            ),
            evaluation_timeout_us=timeout_us,
            completed_rule_count=len(results),
            rule_timings=tuple(timings),
        )

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
        timings.append(RuleTiming(index, guard.rule_id, 1))
        decision = timeout_decision(risk_input, rule_set, tuple(results))
        total = max(
            timeout_us,
            sum(t.latency_us for t in timings),
            ceil_div_us(self._clock.monotonic_ns() - start_ns),
        )
        return RiskAuditOutputV1(
            decision=decision,
            evaluated_at=rfc3339_z(self._clock.utc_now()),  # type: ignore[arg-type]
            total_latency_us=total,
            evaluation_timeout_us=timeout_us,
            completed_rule_count=len(results) - 1,
            rule_timings=tuple(timings),
        )


def _timeout_us(rule_set: RiskRuleSetV1) -> int:
    value = rule_set.to_primitive()["evaluation_timeout_us"]
    if not isinstance(value, int):
        raise ValueError("evaluation_timeout_us must be int")
    return value
