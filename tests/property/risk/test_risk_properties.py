from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.unit.risk.test_risk_engine import (
    FakeClock,
    GateEvaluator,
    rule_set_dto,
    scoped_rule,
    valid_input,
    valid_rule_set,
    with_hashes,
    with_input_hash,
)

from quantiqmt.risk import (
    DeterministicRiskEvaluator,
    RiskContractError,
    RiskEvaluationRunner,
    RiskInputV1,
    RuleResult,
    RuleTiming,
)


@given(st.permutations(["RULE.A", "RULE.B", "RULE.C"]))
def test_rule_permutation_does_not_change_semantic_decision(rule_ids: tuple[str, ...]) -> None:
    base = valid_rule_set()
    base["rules"] = [
        scoped_rule(rule_id, "ACCOUNT", "acct-1", 10, "ORDER_QUANTITY", 500) for rule_id in rule_ids
    ]
    ordered = with_hashes(base)
    reverse = deepcopy(base)
    reverse["rules"] = list(reversed(reverse["rules"]))
    reverse = with_hashes(reverse)

    first = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), ordered)), rule_set_dto(ordered)
    )
    second = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), reverse)), rule_set_dto(reverse)
    )

    assert [r.rule_id for r in first.rule_results] == [r.rule_id for r in second.rule_results]


@given(st.integers(min_value=1, max_value=99), st.integers(min_value=100, max_value=500))
def test_same_metric_multiple_rules_strictest_rejects(strict_limit: int, loose_limit: int) -> None:
    rule_set = valid_rule_set()
    rule_set["rules"] = [
        scoped_rule("RULE.LOOSE", "ACCOUNT", "acct-1", 1, "ORDER_QUANTITY", loose_limit),
        scoped_rule("RULE.STRICT", "ACCOUNT", "acct-1", 2, "ORDER_QUANTITY", strict_limit),
    ]
    rule_set = with_hashes(rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), rule_set)), rule_set_dto(rule_set)
    )

    assert decision.decision == "REJECT"
    assert any(
        result.rule_id == "RULE.STRICT" and result.result == "REJECT"
        for result in decision.rule_results
    )
    assert any(result.rule_id == "RULE.LOOSE" for result in decision.rule_results)


@given(st.integers(min_value=501, max_value=10_000))
def test_hard_cap_cannot_be_relaxed(quantity: int) -> None:
    rule_set = valid_rule_set()
    payload = valid_input(rule_set)
    payload["order"]["quantity"] = quantity
    payload = with_input_hash(payload, rule_set)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), rule_set_dto(rule_set)
    )

    assert decision.error_code == "QQ-RISK-4001"


@given(st.sampled_from(["STALE", "PARTIAL", "TIMEOUT", "UNAVAILABLE"]))
def test_each_snapshot_fail_closed_quality_rejects(quality: str) -> None:
    rule_set = valid_rule_set()
    payload = valid_input(rule_set)
    payload["account"]["metadata"]["quality"] = quality
    if quality == "PARTIAL":
        payload["account"]["metadata"]["missing_fields"] = ["equity"]
    payload = with_input_hash(payload, rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), rule_set_dto(rule_set)
    )
    assert decision.decision == "REJECT"
    assert decision.error_code in {"QQ-RISK-4002", "QQ-RISK-4003", "QQ-RISK-4006", "QQ-RISK-4010"}


@given(st.integers(min_value=101, max_value=500))
def test_reduce_evidence_boundary(quantity: int) -> None:
    rule_set = valid_rule_set()
    payload = valid_input(rule_set)
    payload["order"]["risk_effect"] = "REDUCE"
    payload["order"]["side"] = "SELL"
    payload["order"]["quantity"] = quantity
    payload["order"]["reduction_evidence"] = {
        "classification": "VERIFIED_REDUCE_ONLY",
        "position_snapshot_version": "p1",
        "position_quantity_before": 100,
        "reserved_reduce_quantity": 0,
        "max_reducible_quantity": 100,
        "projected_position_quantity": 100 - quantity,
        "would_flip_position": False,
    }
    payload = with_input_hash(payload, rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), rule_set_dto(rule_set)
    )
    assert decision.error_code == "QQ-RISK-4009"


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_float_rejected(value: float) -> None:
    payload = valid_input()
    payload["account"]["equity"] = value
    try:
        RiskInputV1.create(payload)
    except RiskContractError as exc:
        assert exc.code == "QQ-RISK-4008"
    else:  # pragma: no cover - Hypothesis should never reach this branch
        raise AssertionError("float accepted")


@given(st.sampled_from(["STALE", "PARTIAL", "TIMEOUT", "UNAVAILABLE", "VERSION_MISMATCH"]))
def test_generated_snapshot_consistency_taxonomy(quality: str) -> None:
    rule_set = valid_rule_set()
    payload = valid_input(rule_set)
    if quality == "VERSION_MISMATCH":
        payload["portfolio"]["metadata"]["trading_day"] = "2026-07-03"
        expected = "QQ-RISK-4004"
    else:
        payload["account"]["metadata"]["quality"] = quality
        expected = {
            "STALE": "QQ-RISK-4002",
            "PARTIAL": "QQ-RISK-4003",
            "TIMEOUT": "QQ-RISK-4010",
            "UNAVAILABLE": "QQ-RISK-4006",
        }[quality]
        if quality == "PARTIAL":
            payload["account"]["daily_loss"] = None
            payload["account"]["metadata"]["missing_fields"] = ["account.daily_loss"]
        if quality in {"TIMEOUT", "UNAVAILABLE"}:
            payload["account"]["metadata"]["aggregate_version"] = None
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(payload, rule_set)), rule_set_dto(rule_set)
    )
    assert decision.error_code == expected


@given(
    st.sampled_from(
        [
            ("ACCOUNT", "acct-other"),
            ("PORTFOLIO", "pf-other"),
            ("STRATEGY", "strat-other"),
            ("INSTRUMENT", "000001.XSHE"),
        ]
    )
)
def test_generated_scope_identity_mismatch_is_not_applicable(scope_case: tuple[str, str]) -> None:
    scope, scope_id = scope_case
    rule_set = valid_rule_set()
    rule_set["rules"] = [
        scoped_rule("RULE.SHARED", scope, scope_id, 1, "ORDER_QUANTITY", 1),
        scoped_rule("RULE.CURRENT", "ACCOUNT", "acct-1", 2, "ORDER_QUANTITY", 500),
    ]
    rule_set = with_hashes(rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(rule_set), rule_set)),
        rule_set_dto(rule_set),
    )
    assert (
        next(result for result in decision.rule_results if result.rule_id == "RULE.SHARED").result
        == "NOT_APPLICABLE"
    )
    assert decision.error_code is None


@given(
    st.sampled_from(
        [
            ("policy_disabled", False, [], "ALLOW_IF_VERIFIED", "REJECT"),
            ("unlisted", True, [], "ALLOW_IF_VERIFIED", "REJECT"),
            ("enabled_listed", True, ["RULE.POSITION"], "ALLOW_IF_VERIFIED", "PASS"),
        ]
    )
)
def test_generated_reduce_policy_matrix(case: tuple[str, bool, list[str], str, str]) -> None:
    _name, enabled, exempt, declaration, expected = case
    rule_set = valid_rule_set()
    rule_set["reduce_only_policy"] = {"enabled": enabled, "exempt_rule_ids": exempt}
    rule_set["rules"] = [
        scoped_rule(
            "RULE.POSITION",
            "INSTRUMENT",
            "600000.XSHG",
            1,
            "POSITION_QUANTITY",
            50,
            reduction_exception=declaration,
        )
    ]
    rule_set = with_hashes(rule_set)
    payload = valid_input(rule_set)
    payload["order"]["risk_effect"] = "REDUCE"
    payload["order"]["side"] = "SELL"
    payload["order"]["quantity"] = 100
    payload["order"]["reduction_evidence"] = {
        "classification": "VERIFIED_REDUCE_ONLY",
        "position_snapshot_version": "p1",
        "position_quantity_before": 200,
        "reserved_reduce_quantity": 0,
        "max_reducible_quantity": 200,
        "projected_position_quantity": 100,
        "would_flip_position": False,
    }
    for row in payload["portfolio"]["scope_metrics"]:
        if row["scope"] == "INSTRUMENT":
            row["position_quantity"] = 200
            row["projected_position_quantity"] = 100
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(payload, rule_set)), rule_set_dto(rule_set)
    )
    assert (
        next(result for result in decision.rule_results if result.rule_id == "RULE.POSITION").result
        == expected
    )


@given(st.integers(min_value=0, max_value=20))
def test_generated_input_version_filter_remains_bounded(index: int) -> None:
    rule_set = valid_rule_set()
    runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0] * 500))
    for offset in range(index + 1):
        payload = valid_input(rule_set)
        payload["order"]["order_id"] = f"550e8400-e29b-41d4-a716-44665545{offset:04d}"
        runner.run(RiskInputV1.create(with_input_hash(payload, rule_set)), rule_set_dto(rule_set))
    assert runner._seen_filter.storage_bit_length <= runner._seen_filter.bounded_bit_count


@given(st.booleans())
def test_generated_timeout_saturation_does_not_invalidate_admitted_result(_: bool) -> None:
    rule_set = valid_rule_set()
    release = Event()
    entered = Event()
    runner = RiskEvaluationRunner(GateEvaluator(entered, release), FakeClock([0] * 100))
    first = RiskInputV1.create(with_input_hash(valid_input(rule_set), rule_set))
    second_payload = valid_input(rule_set)
    second_payload["order"]["order_id"] = "550e8400-e29b-41d4-a716-446655450999"
    second = RiskInputV1.create(with_input_hash(second_payload, rule_set))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runner.run, first, rule_set_dto(rule_set))
        assert entered.wait(timeout=1)
        saturated = runner.run(second, rule_set_dto(rule_set))
        release.set()
        audit = future.result(timeout=1)
    assert saturated.decision.decision_origin == "TIMEOUT_GUARD"
    assert audit.decision.decision_origin == "EVALUATOR"


@given(st.integers(min_value=-3, max_value=3), st.sampled_from(["PASS", "REJECT", "BAD"]))
def test_generated_public_output_construction_is_always_closed(index: int, outcome: str) -> None:
    with pytest.raises(TypeError):
        RuleResult(
            index,
            "RULE",
            "SCOPED_RULE",
            "ACCOUNT",
            "acct-1",
            1,
            None,
            outcome,
            "RISK_RULE_PASSED",
            {"kind": "INTEGER", "value": index},
            None,
        )
    with pytest.raises(TypeError):
        RuleTiming(index, "RULE", index)
