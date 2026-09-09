"""TASK-005 acceptance regressions against PORTS-RISK."""

from decimal import localcontext
from typing import Any

import pytest
from tests.unit.risk.test_risk_engine import (
    FakeClock,
    accepted_policy,
    rule_set_dto,
    scoped_rule,
    valid_input,
    valid_rule_set,
    with_hashes,
    with_input_hash,
)

from quantiqmt.risk import (
    DeterministicRiskEvaluator,
    RiskAuditSemanticValidator,
    RiskContractError,
    RiskEvaluationRunner,
    RiskInputV1,
    RiskRuleSetV1,
)
from quantiqmt.risk.model import canonical_json_bytes


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "unsorted",
        "identity",
        "index",
        "count",
        "sum",
        "multiple_timeout",
        "early_timeout",
    ],
)
def test_audit_rejects_every_cross_array_corruption(mutation: str) -> None:
    from copy import deepcopy

    from quantiqmt.risk.evaluator import timeout_result

    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0] * 100))
    try:
        payload = runner.run(
            RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set())
        ).to_primitive()
    finally:
        runner._executor.shutdown(wait=True)
    results = payload["decision"]["rule_results"]
    timings = payload["rule_timings"]
    if mutation == "missing":
        timings.pop()
    elif mutation == "extra":
        timings.append(deepcopy(timings[-1]))
    elif mutation == "duplicate":
        results[1]["rule_id"] = results[0]["rule_id"]
    elif mutation == "unsorted":
        timings.reverse()
    elif mutation == "identity":
        timings[-1]["rule_id"] = "RULE.OTHER"
    elif mutation == "index":
        results[-1]["evaluation_index"] = 100
    elif mutation == "count":
        payload["completed_rule_count"] -= 1
    elif mutation == "sum":
        timings[-1]["latency_us"] = payload["total_latency_us"] + 1
    else:
        payload["decision"].update(
            decision_origin="TIMEOUT_GUARD",
            decision="REJECT",
            primary_reason_code="RISK_EVALUATION_TIMEOUT",
            error_code="QQ-RISK-4005",
        )
        payload["total_latency_us"] = payload["evaluation_timeout_us"]
        indices = [0, len(results) - 1] if mutation == "multiple_timeout" else [0]
        for i in indices:
            results[i] = timeout_result(i).to_primitive()
            timings[i]["rule_id"] = results[i]["rule_id"]
        payload["completed_rule_count"] -= 1
    with pytest.raises(RiskContractError):
        RiskAuditSemanticValidator().validate(payload)


def evaluate(payload: dict[str, Any], rules: dict[str, Any]) -> Any:
    return DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(payload, rules)), rule_set_dto(rules)
    )


@pytest.mark.parametrize("instrument, outcome", [("600000.XSHG", "PASS"), ("OTHER", "REJECT")])
def test_instrument_set_has_real_membership(instrument: str, outcome: str) -> None:
    rules = valid_rule_set()
    rules["rules"] = [scoped_rule("RULE.SET", "SYSTEM", None, 1, "INSTRUMENT_ALLOWED", instrument)]
    rules = with_hashes(rules)
    assert evaluate(valid_input(), rules).decision == outcome


@pytest.mark.parametrize("effect", ["INCREASE", "UNKNOWN"])
def test_reduction_guard_is_not_applicable_without_reduce(effect: str) -> None:
    payload = valid_input()
    payload["order"]["risk_effect"] = effect
    guard = evaluate(payload, valid_rule_set()).rule_results[3]
    assert (guard.result, guard.reason_code) == ("NOT_APPLICABLE", "RISK_RULE_NOT_APPLICABLE")


@pytest.mark.parametrize("case", ["scope", "reserved", "boolean", "exception", "set_order"])
def test_invalid_rule_configuration_rejects_before_business_rules(case: str) -> None:
    rules = valid_rule_set()
    rule = scoped_rule("RULE.BAD", "SYSTEM", None, 1, "ORDER_QUANTITY", 100)
    if case == "scope":
        rule = scoped_rule("RULE.BAD", "STRATEGY", "strat-1", 1, "DAILY_LOSS", "100")
    elif case == "reserved":
        rule["rule_id"] = "SYSTEM.HARD.ORDER_QUANTITY"
    elif case == "boolean":
        rule = scoped_rule("RULE.BAD", "SYSTEM", None, 1, "TRADING_ENABLED", False)
    elif case == "exception":
        rule["reduction_exception"] = "ALLOW_IF_VERIFIED"
        rule["rule_id"] = "RISK.INPUT.CANONICAL"
        rules["reduce_only_policy"] = {"enabled": True, "exempt_rule_ids": [rule["rule_id"]]}
    else:
        rule = scoped_rule("RULE.BAD", "SYSTEM", None, 1, "INSTRUMENT_ALLOWED", "A")
        rule["limit"]["values"] = ["Z", "A"]
    rules["rules"] = [rule]
    rules = with_hashes(rules)
    decision = evaluate(valid_input(), rules)
    assert decision.error_code == "QQ-RISK-4007"
    assert decision.decision_origin == "INPUT_GUARD"
    assert len(decision.rule_results) == 9


def test_business_rules_are_evaluated_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    import quantiqmt.risk.evaluator as module

    original = module._evaluate_metric
    calls: list[str] = []

    def observe(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs["rule_id"])
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "_evaluate_metric", observe)
    iterator = DeterministicRiskEvaluator().iter_rule_results(
        RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set())
    )
    for _ in range(9):
        next(iterator)
    assert calls == []
    first = next(iterator)
    assert calls == [first.rule_id]
    next(iterator)
    assert len(calls) == 2


def test_decimal_context_cannot_change_semantic_decision() -> None:
    risk_input = RiskInputV1.create(valid_input())
    rules = rule_set_dto(valid_rule_set())
    evaluator = DeterministicRiskEvaluator()
    expected = evaluator.evaluate(risk_input, rules).to_primitive()
    with localcontext() as ctx:
        ctx.prec = 3
        actual = evaluator.evaluate(risk_input, rules).to_primitive()
    assert actual == expected


@pytest.mark.parametrize("source", ["account", "portfolio", "market"])
def test_future_snapshot_returns_auditable_input_reject(source: str) -> None:
    payload = valid_input()
    payload[source]["metadata"]["as_of"] = "2026-07-02T02:00:01Z"
    decision = evaluate(payload, valid_rule_set())
    assert decision.error_code == "QQ-RISK-4008"
    assert decision.snapshot_states[source]["age_ms"] is None


def test_partial_cannot_claim_missing_data_that_is_present() -> None:
    payload = valid_input()
    payload["account"]["metadata"].update(quality="PARTIAL", missing_fields=["account.daily_loss"])
    assert evaluate(payload, valid_rule_set()).error_code == "QQ-RISK-4008"


@pytest.mark.parametrize("quality", ["FRESH", "STALE", "TIMEOUT", "UNAVAILABLE"])
def test_version_mismatch_dominates_source_quality(quality: str) -> None:
    payload = valid_input()
    payload["market"]["metadata"].update(quality=quality, trading_day="2026-07-03")
    decision = evaluate(payload, valid_rule_set())
    assert decision.error_code == "QQ-RISK-4004"
    assert decision.snapshot_states["market"]["quality"] == "VERSION_MISMATCH"


def test_valid_rule_currency_is_independent_of_input_currency() -> None:
    rules = valid_rule_set()
    rules["valuation_currency"] = "USD"
    rules["rules"] = [scoped_rule("RULE.CASH", "ACCOUNT", "acct-1", 1, "AVAILABLE_CASH", "0")]
    rules["rules"][0]["limit"]["currency"] = "USD"
    rules = with_hashes(rules)
    dto = RiskRuleSetV1.create(rules, accepted_hard_policy=accepted_policy(rules))
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), rules)), dto
    )
    assert decision.error_code == "QQ-RISK-4011"
    assert decision.rule_results[4].result == "PASS"


def test_runner_times_out_when_exhaustion_crosses_deadline() -> None:
    class LastBoundaryEvaluator(DeterministicRiskEvaluator):
        def iter_rule_results(self, risk_input: Any, rule_set: Any) -> Any:
            yield next(super().iter_rule_results(risk_input, rule_set))

    runner = RiskEvaluationRunner(LastBoundaryEvaluator(), FakeClock([0, 0, 0, 0, 4_000_000]))
    try:
        audit = runner.run(RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set()))
        assert audit.decision.error_code == "QQ-RISK-4005"
    finally:
        runner._executor.shutdown(wait=True)


def test_runner_records_zero_elapsed_as_zero_latency() -> None:
    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0] * 100))
    try:
        audit = runner.run(RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set()))
        assert audit.total_latency_us == 0
        assert all(t.latency_us == 0 for t in audit.rule_timings)
    finally:
        runner._executor.shutdown(wait=True)


@pytest.mark.parametrize("field,value", [("phase", "SCOPED_RULE"), ("rule_id", "RULE.OTHER")])
def test_timeout_guard_requires_both_exact_phase_and_identity(field: str, value: str) -> None:
    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0, 4_000_000]))
    try:
        payload = runner.run(
            RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set())
        ).to_primitive()
    finally:
        runner._executor.shutdown(wait=True)
    payload["decision"]["rule_results"][-1][field] = value
    if field == "rule_id":
        payload["rule_timings"][-1]["rule_id"] = value
    with pytest.raises(RiskContractError):
        RiskAuditSemanticValidator().validate(payload)


def test_canonical_json_uses_utf16_property_order() -> None:
    assert (
        canonical_json_bytes({"\ue000": 1, "\U00010000": 2})
        == '{"\U00010000":2,"\ue000":1}'.encode()
    )
