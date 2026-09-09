"""Generated evidence for the ten TASK-005 acceptance criteria."""

from decimal import localcontext

from hypothesis import given
from hypothesis import strategies as st
from tests.unit.risk.test_risk_engine import (
    reduce_input,
    rule_set_dto,
    scoped_rule,
    valid_input,
    valid_rule_set,
    with_hashes,
    with_input_hash,
)

from quantiqmt.risk import DeterministicRiskEvaluator, RiskInputV1, hash_without
from quantiqmt.risk.model import canonical_json_bytes, decision_id, semantic_decision_hash


@given(st.permutations(range(5)), st.integers(0, 1000000))
def test_all_scope_order_and_reject_dominance(order: list[int], priority: int) -> None:
    scopes = [
        ("SYSTEM", None),
        ("ACCOUNT", "acct-1"),
        ("PORTFOLIO", "pf-1"),
        ("STRATEGY", "strat-1"),
        ("INSTRUMENT", "600000.XSHG"),
    ]
    rules = valid_rule_set()
    rules["rules"] = [
        scoped_rule(f"RULE.{i}", *scopes[i], priority, "ORDER_QUANTITY", 99 if i == 2 else 500)
        for i in order
    ]
    rules = with_hashes(rules)
    result = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), rules)), rule_set_dto(rules)
    )
    assert [r.rule_id for r in result.rule_results[-5:]] == [f"RULE.{i}" for i in range(5)]
    assert result.error_code == "QQ-RISK-4001"
    assert [r.evaluation_index for r in result.rule_results] == list(range(24))
    assert result.rule_results[-3].result == "REJECT"
    assert result.rule_results[-1].result == "PASS"


@given(st.integers(3, 60), st.integers(1, 500))
def test_semantic_bytes_identity_and_hash_ignore_decimal_context(
    precision: int, quantity: int
) -> None:
    rules = valid_rule_set()
    payload = valid_input()
    payload["order"]["quantity"] = quantity
    risk_input = RiskInputV1.create(with_input_hash(payload, rules))
    rule_set = rule_set_dto(rules)
    evaluator = DeterministicRiskEvaluator()
    expected = evaluator.evaluate(risk_input, rule_set)
    with localcontext() as ctx:
        ctx.prec = precision
        actual = evaluator.evaluate(risk_input, rule_set)
    assert canonical_json_bytes(expected.to_primitive()) == canonical_json_bytes(
        actual.to_primitive()
    )
    assert actual.decision_id == decision_id(actual.input_version, actual.rule_set_hash)
    assert actual.semantic_decision_hash == semantic_decision_hash(actual.to_primitive())


@given(st.integers(1, 500), st.booleans(), st.integers(0, 500))
def test_signed_reduction_reservations_and_no_flip(
    quantity: int, short: bool, reserved: int
) -> None:
    rules = valid_rule_set()
    payload = reduce_input(rules)
    before = -300 if short else 300
    projected = before + quantity if short else before - quantity
    payload["order"].update(quantity=quantity, side="BUY" if short else "SELL")
    payload["order"]["reduction_evidence"].update(
        position_quantity_before=before,
        reserved_reduce_quantity=reserved,
        max_reducible_quantity=max(300 - reserved, 0),
        projected_position_quantity=projected,
    )
    payload["portfolio"]["scope_metrics"][-1].update(
        position_quantity=before,
        projected_position_quantity=projected,
    )
    result = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(payload, rules)), rule_set_dto(rules)
    )
    valid = quantity <= max(300 - reserved, 0)
    assert (result.error_code is None) == valid
    if not valid:
        assert result.error_code == "QQ-RISK-4009"


@given(
    st.sampled_from(
        ["stale", "partial", "timeout", "unavailable", "version", "binding", "input", "rules"]
    )
)
def test_exact_fail_closed_taxonomy(case: str) -> None:
    rules = valid_rule_set()
    payload = valid_input()
    expected = {
        "stale": "4002",
        "partial": "4003",
        "timeout": "4010",
        "unavailable": "4006",
        "version": "4004",
        "binding": "4011",
        "input": "4008",
        "rules": "4007",
    }[case]
    if case in {"stale", "partial", "timeout", "unavailable"}:
        payload["account"]["metadata"]["quality"] = case.upper()
        if case == "partial":
            payload["account"]["daily_loss"] = None
            payload["account"]["metadata"]["missing_fields"] = ["account.daily_loss"]
    elif case == "version":
        payload["market"]["metadata"]["trading_day"] = "2026-07-03"
    elif case == "input":
        payload["account"]["currency"] = "USD"
    elif case == "rules":
        rules["rules"].append(
            scoped_rule("RULE.BAD", "ACCOUNT", "acct-1", 0, "ORDER_QUANTITY", 501)
        )
        rules = with_hashes(rules)
    payload = with_input_hash(payload, rules)
    if case == "binding":
        payload["rule_set_version"] = "other"
        payload["input_version"] = hash_without(payload, "input_version")
    result = DeterministicRiskEvaluator().evaluate(RiskInputV1.create(payload), rule_set_dto(rules))
    assert result.error_code == f"QQ-RISK-{expected}"
    assert result.decision_origin == "INPUT_GUARD"
    assert len(result.rule_results) == 9
