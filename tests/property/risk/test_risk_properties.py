from __future__ import annotations

from copy import deepcopy

from hypothesis import given
from hypothesis import strategies as st
from tests.unit.risk.test_risk_engine import (
    rule_set_dto,
    scoped_rule,
    valid_input,
    valid_rule_set,
    with_hashes,
    with_input_hash,
)

from quantiqmt.risk import DeterministicRiskEvaluator, RiskContractError, RiskInputV1


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
