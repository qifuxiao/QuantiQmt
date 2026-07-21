from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.risk import (
    DeterministicRiskEvaluator,
    RiskAuditSemanticValidator,
    RiskContractError,
    RiskEvaluationRunner,
    RiskInputV1,
    RiskRuleSetV1,
    build_risk_v1_payload,
    build_risk_v2_envelope,
    hard_limit_policy_hash,
    hash_without,
    project_risk_v1_envelope,
)
from quantiqmt.risk.model import semantic_decision_hash

UUID1 = "550e8400-e29b-41d4-a716-446655440001"
UUID2 = "550e8400-e29b-41d4-a716-446655440002"
NOW = "2026-07-02T02:00:00Z"


def test_evaluator_is_deterministic_and_hash_excludes_runtime_fields() -> None:
    risk_input = RiskInputV1.create(valid_input())
    rule_set = RiskRuleSetV1.create(valid_rule_set())
    evaluator = DeterministicRiskEvaluator()

    first = evaluator.evaluate(risk_input, rule_set)
    second = evaluator.evaluate(risk_input, rule_set)

    assert first.to_primitive() == second.to_primitive()
    assert first.decision == "PASS"
    assert first.decision_origin == "EVALUATOR"
    assert first.semantic_decision_hash == semantic_decision_hash(first.to_primitive())
    assert first.primary_reason_code == "RISK_ALL_APPLICABLE_RULES_PASSED"


def test_phase_scope_priority_rule_id_sorting_and_all_rules_are_evaluated() -> None:
    rules = valid_rule_set()
    rules["rules"] = [
        scoped_rule("RULE.Z", "INSTRUMENT", "600000.XSHG", 5, "ORDER_QUANTITY", 500),
        scoped_rule("RULE.A", "ACCOUNT", "acct-1", 5, "ORDER_QUANTITY", 500),
        scoped_rule("RULE.B", "ACCOUNT", "acct-1", 5, "ORDER_QUANTITY", 1),
    ]
    rules = with_hashes(rules)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(with_input_hash(valid_input(), rules)), RiskRuleSetV1.create(rules)
    )

    ids = [result.rule_id for result in decision.rule_results]
    assert ids[:9] == [
        "RISK.INPUT.CANONICAL",
        "RISK.INPUT.IDENTITY",
        "RISK.INPUT.RULE_SET_BINDING",
        "RISK.INPUT.REDUCTION_EVIDENCE",
        "RISK.RULE_SET.VALIDITY",
        "RISK.SNAPSHOT.ACCOUNT",
        "RISK.SNAPSHOT.PORTFOLIO",
        "RISK.SNAPSHOT.MARKET",
        "RISK.SNAPSHOT.CROSS_SOURCE",
    ]
    assert ids[-3:] == ["RULE.A", "RULE.B", "RULE.Z"]
    assert decision.decision == "REJECT"
    assert any(result.rule_id == "RULE.Z" for result in decision.rule_results)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (
            lambda payload: payload["account"]["metadata"].__setitem__("quality", "STALE"),
            "QQ-RISK-4002",
        ),
        (
            lambda payload: payload["portfolio"]["metadata"].__setitem__("quality", "PARTIAL"),
            "QQ-RISK-4003",
        ),
        (
            lambda payload: payload["market"]["metadata"].__setitem__("quality", "UNAVAILABLE"),
            "QQ-RISK-4006",
        ),
        (
            lambda payload: payload["market"]["metadata"].__setitem__("quality", "TIMEOUT"),
            "QQ-RISK-4010",
        ),
        (
            lambda payload: payload["market"].__setitem__("instrument_id", "000001.XSHE"),
            "QQ-RISK-4008",
        ),
    ],
)
def test_snapshot_and_input_fail_closed_taxonomy(mutation: Any, error: str) -> None:
    rule_set = valid_rule_set()
    payload = valid_input()
    mutation(payload)
    if payload["portfolio"]["metadata"]["quality"] == "PARTIAL":
        payload["portfolio"]["metadata"]["missing_fields"] = ["scope_metrics"]
    payload = with_input_hash(payload, rule_set)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.unchecked(payload), RiskRuleSetV1.create(rule_set)
    )

    assert decision.decision == "REJECT"
    assert decision.error_code == error
    assert decision.decision_origin == "INPUT_GUARD"


def test_rule_set_invalid_and_binding_mismatch_fail_closed() -> None:
    rule_set = valid_rule_set()
    loose = deepcopy(rule_set)
    loose["rules"] = [scoped_rule("RULE.LOOSE", "ACCOUNT", "acct-1", 1, "ORDER_QUANTITY", 20_000)]
    loose = with_hashes(loose)
    payload = with_input_hash(valid_input(), loose)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), RiskRuleSetV1.create(loose)
    )
    assert decision.error_code == "QQ-RISK-4007"

    mismatch = valid_input()
    mismatch["rule_set_hash"] = "a" * 64
    mismatch["input_version"] = hash_without(mismatch, "input_version")
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(mismatch), RiskRuleSetV1.create(rule_set)
    )
    assert decision.error_code == "QQ-RISK-4011"


def test_hard_rules_cannot_be_relaxed_by_dynamic_priority() -> None:
    rule_set = valid_rule_set()
    payload = valid_input()
    payload["order"]["quantity"] = 501
    payload = with_input_hash(payload, rule_set)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), RiskRuleSetV1.create(rule_set)
    )

    assert decision.decision == "REJECT"
    assert decision.primary_reason_code == "RISK_HARD_LIMIT_BREACH"
    assert decision.error_code == "QQ-RISK-4001"


def test_reduce_only_requires_explicit_evidence_and_never_bypasses_hard_limits() -> None:
    rule_set = valid_rule_set()
    rule_set["reduce_only_policy"]["enabled"] = True
    rule_set["reduce_only_policy"]["exempt_rule_ids"] = ["RULE.POSITION"]
    rule_set["rules"] = [
        scoped_rule(
            "RULE.POSITION",
            "INSTRUMENT",
            "600000.XSHG",
            1,
            "POSITION_QUANTITY",
            50,
            reduction_exception="ALLOW_IF_VERIFIED",
        )
    ]
    rule_set = with_hashes(rule_set)
    payload = reduce_input(rule_set)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), RiskRuleSetV1.create(rule_set)
    )

    exempt = next(result for result in decision.rule_results if result.rule_id == "RULE.POSITION")
    assert exempt.result == "PASS"
    assert exempt.exception_applied is True

    bad = deepcopy(payload)
    bad["order"]["reduction_evidence"] = None
    bad["order"]["risk_effect"] = "REDUCE"
    bad = with_input_hash(bad, rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(bad), RiskRuleSetV1.create(rule_set)
    )
    assert decision.error_code == "QQ-RISK-4009"


def test_audit_validator_and_v1_v2_projection_use_validated_audit() -> None:
    rule_set = valid_rule_set()
    audit = RiskEvaluationRunner(
        DeterministicRiskEvaluator(), FakeClock([0, 1000, 2000, 3000, 4000])
    ).run(
        RiskInputV1.create(with_input_hash(valid_input(), rule_set)), RiskRuleSetV1.create(rule_set)
    )

    RiskAuditSemanticValidator().validate(audit)
    v1 = build_risk_v1_payload(audit)
    assert v1["decision_id"] == audit.decision.decision_id
    assert v1["rule_results"][0]["latency_us"] == audit.rule_timings[0].latency_us  # type: ignore[index]

    registry = SchemaRegistry.project_default()
    assert project_risk_v1_envelope(audit, registry=registry, causation_id="message-00000001")
    assert build_risk_v2_envelope(audit, registry=registry, causation_id="message-00000001")


def test_audit_validator_rejects_mismatched_timing_and_timeout_semantics() -> None:
    rule_set = valid_rule_set()
    audit = RiskEvaluationRunner(
        DeterministicRiskEvaluator(), FakeClock([0, 1000, 2000, 3000, 4000])
    ).run(
        RiskInputV1.create(with_input_hash(valid_input(), rule_set)), RiskRuleSetV1.create(rule_set)
    )
    bad = audit.__class__(
        audit.decision,
        audit.evaluated_at,
        0,
        audit.evaluation_timeout_us,
        audit.completed_rule_count,
        audit.rule_timings,
    )
    with pytest.raises(RiskContractError):
        RiskAuditSemanticValidator().validate(bad)


def test_runner_timeout_fences_late_pass() -> None:
    rule_set = valid_rule_set()
    rule_set["evaluation_timeout_us"] = 1
    rule_set = with_hashes(rule_set)
    audit = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0, 2_000, 3_000])).run(
        RiskInputV1.create(with_input_hash(valid_input(), rule_set)), RiskRuleSetV1.create(rule_set)
    )
    assert audit.decision.decision_origin == "TIMEOUT_GUARD"
    assert audit.decision.error_code == "QQ-RISK-4005"
    assert audit.decision.rule_results[-1].rule_id == "RISK.SYSTEM.EVALUATION_TIMEOUT"
    RiskAuditSemanticValidator().validate(audit)


def test_float_is_rejected_before_evaluation() -> None:
    payload = valid_input()
    payload["market"]["risk_price"] = 10.0
    with pytest.raises(RiskContractError, match="float is forbidden"):
        RiskInputV1.create(payload)


@dataclass
class FakeClock:
    monotonic_values: list[int]

    def monotonic_ns(self) -> int:
        if len(self.monotonic_values) == 1:
            return self.monotonic_values[0]
        return self.monotonic_values.pop(0)

    def utc_now(self) -> datetime:
        return datetime(2026, 7, 2, 2, 0, 0, tzinfo=UTC)


def valid_input(rule_set: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rule_set or valid_rule_set()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "input_version": "0" * 64,
        "evaluation_time": NOW,
        "valuation_currency": "CNY",
        "rule_set_version": rules["rule_set_version"],
        "rule_set_hash": rules["content_hash"],
        "order": {
            "schema_version": 1,
            "checksum": "a" * 64,
            "order_id": UUID1,
            "aggregate_version": 1,
            "intent_id": UUID2,
            "account_id": "acct-1",
            "portfolio_id": "pf-1",
            "strategy_id": "strat-1",
            "strategy_version": "1",
            "instrument_id": "600000.XSHG",
            "side": "BUY",
            "position_effect": "AUTO",
            "order_type": "LIMIT",
            "quantity": 100,
            "limit_price": "10.00",
            "time_in_force": "DAY",
            "registered_at": NOW,
            "market_data_version": "m1",
            "risk_effect": "INCREASE",
            "reduction_evidence": None,
        },
        "account": {
            "metadata": metadata("account", "a1"),
            "account_id": "acct-1",
            "currency": "CNY",
            "equity": "100000.00",
            "available_cash": "100000.00",
            "projected_available_cash": "99000.00",
            "margin_used": "0",
            "daily_loss": "0",
            "open_order_notional": "1000.00",
        },
        "portfolio": {
            "metadata": metadata("portfolio", "p1"),
            "portfolio_id": "pf-1",
            "account_id": "acct-1",
            "base_currency": "CNY",
            "scope_metrics": [
                scope_metric("ACCOUNT", "acct-1"),
                scope_metric("PORTFOLIO", "pf-1"),
                scope_metric("STRATEGY", "strat-1"),
                scope_metric("INSTRUMENT", "600000.XSHG"),
            ],
        },
        "market": {
            "metadata": metadata("market", "m1", aggregate_version=None),
            "instrument_id": "600000.XSHG",
            "trading_status": "TRADING",
            "currency": "CNY",
            "risk_price": "10.00",
            "risk_price_source": "LIMIT_PRICE",
            "reference_price": "10.00",
            "price_deviation_bps": 0,
            "upper_price_limit": "11.00",
            "lower_price_limit": "9.00",
        },
    }
    return with_input_hash(payload, rules)


def reduce_input(rule_set: dict[str, Any]) -> dict[str, Any]:
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
    return with_input_hash(payload, rule_set)


def valid_rule_set() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "rule_set_id": "550e8400-e29b-41d4-a716-446655440010",
        "rule_set_version": "r1",
        "content_hash": "0" * 64,
        "valuation_currency": "CNY",
        "hard_limit_policy_version": "h1",
        "hard_limit_policy_hash": "0" * 64,
        "evaluation_timeout_us": 4000,
        "freshness_limits_ms": {"account": 1000, "portfolio": 1000, "market": 1000},
        "system_hard_limits": {
            "allow_new_risk": True,
            "max_order_quantity": 500,
            "max_order_notional": "10000.00",
            "max_price_deviation_bps": 100,
            "max_projected_gross_exposure": "100000.00",
            "max_projected_net_exposure_abs": "100000.00",
            "max_projected_leverage": "2.00",
            "max_daily_loss": "1000.00",
            "activity_window_ms": 60000,
            "max_order_count_window": 100,
            "max_cancel_ratio_bps": 5000,
        },
        "reduce_only_policy": {"enabled": False, "exempt_rule_ids": []},
        "rules": [scoped_rule("RULE.TRADING_ENABLED", "SYSTEM", None, 1, "TRADING_ENABLED", True)],
    }
    return with_hashes(payload)


def scoped_rule(
    rule_id: str,
    scope: str,
    scope_id: str | None,
    priority: int,
    metric: str,
    limit: int | str | bool,
    *,
    reduction_exception: str = "NEVER",
) -> dict[str, Any]:
    if metric == "TRADING_ENABLED":
        limit_value: dict[str, Any] = {"kind": "BOOLEAN", "value": limit}
        operator = "BOOLEAN_TRUE"
    elif metric == "INSTRUMENT_ALLOWED":
        limit_value = {"kind": "STRING_SET", "values": [str(limit)]}
        operator = "IN_SET"
    elif metric == "PROJECTED_LEVERAGE":
        limit_value = {"kind": "DECIMAL", "value": str(limit), "currency": None}
        operator = "MAX"
    elif metric in {
        "ORDER_NOTIONAL",
        "AVAILABLE_CASH",
        "PROJECTED_GROSS_EXPOSURE",
        "PROJECTED_NET_EXPOSURE_ABS",
        "DAILY_LOSS",
    }:
        limit_value = {"kind": "DECIMAL", "value": str(limit), "currency": "CNY"}
        operator = "MIN" if metric == "AVAILABLE_CASH" else "MAX"
    else:
        limit_value = {"kind": "INTEGER", "value": limit}
        operator = "MAX"
    return {
        "rule_id": rule_id,
        "scope": scope,
        "scope_id": scope_id,
        "priority": priority,
        "metric": metric,
        "operator": operator,
        "limit": limit_value,
        "reduction_exception": reduction_exception,
    }


def metadata(source: str, version: str, *, aggregate_version: int | None = 1) -> dict[str, Any]:
    return {
        "source": source,
        "snapshot_version": version,
        "schema_version": 1,
        "aggregate_version": aggregate_version,
        "as_of": NOW,
        "trading_day": "2026-07-02",
        "quality": "FRESH",
        "missing_fields": [],
        "checksum": "b" * 64,
    }


def scope_metric(scope: str, scope_id: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "scope_id": scope_id,
        "enabled": True,
        "position_quantity": 0,
        "projected_position_quantity": 100,
        "projected_gross_exposure": "1000.00",
        "projected_net_exposure": "1000.00",
        "projected_leverage": "0.10",
        "activity_window_ms": 60000,
        "order_count_window": 1,
        "cancel_ratio_bps": 0,
    }


def with_hashes(rule_set: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(rule_set)
    result["hard_limit_policy_hash"] = hard_limit_policy_hash(result)
    result["content_hash"] = hash_without(result, "content_hash")
    return result


def with_input_hash(payload: dict[str, Any], rule_set: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result["rule_set_version"] = rule_set["rule_set_version"]
    result["rule_set_hash"] = rule_set["content_hash"]
    result["input_version"] = hash_without(result, "input_version")
    return result
