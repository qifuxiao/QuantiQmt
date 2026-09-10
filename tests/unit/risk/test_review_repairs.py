"""Regression evidence for the three PR #117 independent Review findings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from typing import Any

import pytest
from tests.unit.risk.execution_helpers import ImmediateExecutor
from tests.unit.risk.test_risk_engine import (
    reduce_input,
    rule_set_dto,
    valid_input,
    valid_rule_set,
    with_input_hash,
)

from quantiqmt.risk import (
    DeterministicRiskEvaluator,
    RiskAuditOutputV1,
    RiskEvaluationRunner,
    RiskInputV1,
    hash_without,
)


@pytest.mark.parametrize("effect", ["INCREASE", "UNKNOWN", "REDUCE"])
@pytest.mark.parametrize("status", ["TRADING", "HALTED", "SUSPENDED", "CLOSED", "UNKNOWN"])
def test_market_status_cannot_be_bypassed(effect: str, status: str) -> None:
    rules = valid_rule_set()
    payload = reduce_input(rules) if effect == "REDUCE" else valid_input(rules)
    payload["order"]["risk_effect"] = effect
    payload["market"]["trading_status"] = status
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(payload, rules)), rule_set_dto(rules)
    )
    market_guard = decision.rule_results[7]
    if status == "TRADING":
        assert decision.decision == "PASS"
    else:
        assert decision.decision == "REJECT"
        assert decision.error_code == "QQ-RISK-4001"
        assert market_guard.reason_code == "RISK_TRADING_DISABLED"
        assert market_guard.result == "REJECT"
        assert not market_guard.exception_applied
        assert len(decision.rule_results) == 9


@pytest.mark.parametrize("quality", ["FRESH", "STALE", "TIMEOUT", "UNAVAILABLE"])
@pytest.mark.parametrize("corrupt_checksum", [False, True])
def test_market_version_taxonomy_preserves_first_failure(
    quality: str, corrupt_checksum: bool
) -> None:
    rules = valid_rule_set()
    payload = valid_input(rules)
    payload["market"]["metadata"].update(snapshot_version="other-version", quality=quality)
    payload = with_input_hash(payload, rules)
    if corrupt_checksum:
        payload["market"]["metadata"]["checksum"] = "0" * 64
        payload["input_version"] = hash_without(payload, "input_version")
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), rule_set_dto(rules)
    )
    assert decision.error_code == ("QQ-RISK-4008" if corrupt_checksum else "QQ-RISK-4004")
    assert decision.snapshot_states["market"]["quality"] == "VERSION_MISMATCH"
    assert decision.rule_results[0].result == ("REJECT" if corrupt_checksum else "PASS")


class MutableClock:
    ns = 0

    def monotonic_ns(self) -> int:
        return self.ns

    def utc_now(self) -> datetime:
        return datetime(2026, 7, 2, 2, tzinfo=UTC)


def install_finalization_hook(monkeypatch: Any, stage: str, hook: Any) -> None:
    import quantiqmt.risk.runner as module

    if stage == "decide":
        original = DeterministicRiskEvaluator.decide

        def decide(self: Any, *args: Any) -> Any:
            result = original(self, *args)
            hook()
            return result

        monkeypatch.setattr(DeterministicRiskEvaluator, "decide", decide)
    elif stage == "audit_factory":
        original_factory = RiskAuditOutputV1._validated

        def factory(**kwargs: Any) -> Any:
            result = original_factory(**kwargs)
            if result.decision.decision_origin != "TIMEOUT_GUARD":
                hook()
            return result

        monkeypatch.setattr(RiskAuditOutputV1, "_validated", factory)
    else:
        original_validate = module.validate_risk_audit_output

        def validate(audit: Any) -> None:
            original_validate(audit)
            if audit.decision.decision_origin != "TIMEOUT_GUARD":
                hook()

        monkeypatch.setattr(module, "validate_risk_audit_output", validate)


@pytest.mark.parametrize("stage", ["decide", "audit_factory", "audit_validation"])
@pytest.mark.parametrize("elapsed_ns", [1_000_000, 3_999_000, 3_999_001, 4_000_000, 5_000_000])
def test_finalization_budget_and_recorded_elapsed(
    monkeypatch: pytest.MonkeyPatch, stage: str, elapsed_ns: int
) -> None:
    clock = MutableClock()
    install_finalization_hook(monkeypatch, stage, lambda: setattr(clock, "ns", elapsed_ns))
    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), clock)
    runner._executor.shutdown()
    monkeypatch.setattr(runner, "_executor", ImmediateExecutor())
    audit = runner.run(RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set()))
    expected_us = (elapsed_ns + 999) // 1000
    assert audit.total_latency_us == expected_us
    if expected_us >= 4000:
        assert audit.decision.error_code == "QQ-RISK-4005"
        assert audit.decision.decision_origin == "TIMEOUT_GUARD"
        assert audit.rule_timings[-1].rule_id == "RISK.SYSTEM.EVALUATION_TIMEOUT"
        assert audit.completed_rule_count == len(audit.decision.rule_results) - 1
    else:
        assert audit.decision.decision == "PASS"
        assert audit.completed_rule_count == len(audit.decision.rule_results)


@pytest.mark.parametrize("final_ns", [3_000_000, 4_000_000, 5_000_000])
def test_finalization_stages_share_one_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch, final_ns: int
) -> None:
    clock = MutableClock()
    called: set[str] = set()

    def advance_once(stage: str, ns: int) -> None:
        if stage not in called:
            called.add(stage)
            clock.ns = ns

    for stage, ns in (
        ("decide", 1_000_000),
        ("audit_factory", 2_000_000),
        ("audit_validation", final_ns),
    ):
        install_finalization_hook(
            monkeypatch, stage, lambda stage=stage, ns=ns: advance_once(stage, ns)
        )
    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), clock)
    runner._executor.shutdown()
    monkeypatch.setattr(runner, "_executor", ImmediateExecutor())
    audit = runner.run(RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set()))
    assert called == {"decide", "audit_factory", "audit_validation"}
    assert audit.total_latency_us == final_ns // 1000
    assert (audit.decision.error_code == "QQ-RISK-4005") == (final_ns >= 4_000_000)


@pytest.mark.parametrize("stage", ["decide", "audit_factory", "audit_validation"])
def test_blocked_finalization_is_bounded_and_late_pass_is_discarded(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    entered, release, exited = Event(), Event(), Event()

    def block() -> None:
        entered.set()
        try:
            assert release.wait(timeout=2), "test cleanup did not release finalization"
        finally:
            exited.set()

    # Precompute rule results so this regression isolates finalization, not rule cost.
    risk_input = RiskInputV1.create(valid_input())
    rules = rule_set_dto(valid_rule_set())
    evaluator = DeterministicRiskEvaluator()
    results = tuple(evaluator.iter_rule_results(risk_input, rules))
    decision = evaluator.decide(risk_input, rules, results)
    preparation = RiskEvaluationRunner(evaluator, MutableClock())
    preparation._executor.shutdown()
    monkeypatch.setattr(preparation, "_executor", ImmediateExecutor())
    prepared_audit = preparation.run(risk_input, rules)
    original_factory = RiskAuditOutputV1._validated
    import quantiqmt.risk.runner as module

    original_validate = module.validate_risk_audit_output

    # Isolate host scheduling of the blocking stage from contract validation cost.
    # Semantic/elapsed tests above still run the real factories and validators.
    monkeypatch.setattr(DeterministicRiskEvaluator, "decide", lambda *_: decision)
    monkeypatch.setattr(
        RiskAuditOutputV1,
        "_validated",
        lambda **kw: (
            original_factory(**kw)
            if kw["decision"].decision_origin == "TIMEOUT_GUARD"
            else prepared_audit
        ),
    )
    monkeypatch.setattr(
        module,
        "validate_risk_audit_output",
        lambda audit: (
            original_validate(audit) if audit.decision.decision_origin == "TIMEOUT_GUARD" else None
        ),
    )
    monkeypatch.setattr(evaluator, "iter_rule_results", lambda *_: iter(results))
    install_finalization_hook(monkeypatch, stage, block)
    runner = RiskEvaluationRunner(evaluator, MutableClock())
    metrics: list[tuple[Any, ...]] = []
    monkeypatch.setattr(runner._metrics, "observe", lambda *args: metrics.append(args))
    callers = ThreadPoolExecutor(max_workers=1)
    try:
        call = callers.submit(runner.run, risk_input, rules)
        assert entered.wait(timeout=1)
        audit = call.result(timeout=1)
        assert not release.is_set()
        assert audit.decision.error_code == "QQ-RISK-4005"
        assert audit.completed_rule_count == len(results)
        assert audit.total_latency_us >= 4000
        saved = audit.to_primitive()
        for index in range(5):
            payload = valid_input()
            payload["order"]["strategy_version"] = f"new-{index}"
            saturated = runner.run(
                RiskInputV1.create(with_input_hash(payload, valid_rule_set())), rules
            )
            assert saturated.decision.error_code == "QQ-RISK-4005"
            assert saturated.completed_rule_count == 0
        assert runner._executor._max_workers == 1
        assert runner._executor._work_queue.qsize() == 0
        release.set()
        assert exited.wait(timeout=1)
        runner._executor.shutdown(wait=True)
        assert audit.to_primitive() == saved
        decisions = [
            labels["decision"] for name, _, labels in metrics if name == "risk_decisions_total"
        ]
        assert decisions == ["REJECT"] * 6
        assert runner.run(risk_input, rules).decision.error_code == "QQ-RISK-4005"
    finally:
        release.set()
        callers.shutdown(wait=True)
        runner._executor.shutdown(wait=True)
