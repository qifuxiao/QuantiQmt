from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Any

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.risk import (
    AcceptedHardPolicy,
    DeterministicRiskEvaluator,
    RiskAuditSemanticValidator,
    RiskContractError,
    RiskEvaluationRunner,
    RiskInputV1,
    RiskRuleSetV1,
    RuleResult,
    build_risk_v1_payload,
    build_risk_v2_envelope,
    hard_limit_policy_hash,
    hash_snapshot_without_metadata_checksum,
    hash_without,
    project_risk_v1_envelope,
)
from quantiqmt.risk.model import semantic_decision_hash

UUID1 = "550e8400-e29b-41d4-a716-446655440001"
UUID2 = "550e8400-e29b-41d4-a716-446655440002"
NOW = "2026-07-02T02:00:00Z"


def test_evaluator_is_deterministic_and_hash_excludes_runtime_fields() -> None:
    risk_input = RiskInputV1.create(valid_input())
    rule_set = rule_set_dto(valid_rule_set())
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
        RiskInputV1.create(with_input_hash(valid_input(), rules)), rule_set_dto(rules)
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
        RiskInputV1.create(payload), rule_set_dto(rule_set)
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
        RiskInputV1.create(payload), rule_set_dto(loose)
    )
    assert decision.error_code == "QQ-RISK-4007"

    mismatch = valid_input()
    mismatch["rule_set_hash"] = "a" * 64
    mismatch["input_version"] = hash_without(mismatch, "input_version")
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(mismatch), rule_set_dto(rule_set)
    )
    assert decision.error_code == "QQ-RISK-4011"


def test_hard_rules_cannot_be_relaxed_by_dynamic_priority() -> None:
    rule_set = valid_rule_set()
    payload = valid_input()
    payload["order"]["quantity"] = 501
    payload = with_input_hash(payload, rule_set)

    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(payload), rule_set_dto(rule_set)
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
        RiskInputV1.create(payload), rule_set_dto(rule_set)
    )

    exempt = next(result for result in decision.rule_results if result.rule_id == "RULE.POSITION")
    assert exempt.result == "PASS"
    assert exempt.exception_applied is True

    bad = deepcopy(payload)
    bad["order"]["reduction_evidence"]["position_snapshot_version"] = "wrong"
    bad["order"]["risk_effect"] = "REDUCE"
    bad = with_input_hash(bad, rule_set)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(bad), rule_set_dto(rule_set)
    )
    assert decision.error_code == "QQ-RISK-4009"


def test_audit_validator_and_v1_v2_projection_use_validated_audit() -> None:
    rule_set = valid_rule_set()
    audit = RiskEvaluationRunner(
        DeterministicRiskEvaluator(), FakeClock([0, 1000, 2000, 3000, 4000])
    ).run(RiskInputV1.create(with_input_hash(valid_input(), rule_set)), rule_set_dto(rule_set))

    RiskAuditSemanticValidator().validate(audit)
    v1 = build_risk_v1_payload(audit)
    assert v1["decision_id"] == audit.decision.decision_id
    assert v1["rule_results"][0]["latency_us"] == audit.rule_timings[0].latency_us  # type: ignore[index]

    registry = SchemaRegistry.project_default()
    risk_input = RiskInputV1.create(with_input_hash(valid_input(), rule_set))
    v1_envelope = project_risk_v1_envelope(
        audit, risk_input, registry=registry, causation_id="message-00000001"
    )
    v2_envelope = build_risk_v2_envelope(
        audit, risk_input, registry=registry, causation_id="message-00000001"
    )
    assert v1_envelope.to_primitive()["correlation_id"] == UUID2
    assert v2_envelope.to_primitive()["correlation_id"] == UUID2


def test_audit_validator_rejects_mismatched_timing_and_timeout_semantics() -> None:
    rule_set = valid_rule_set()
    audit = RiskEvaluationRunner(
        DeterministicRiskEvaluator(), FakeClock([0, 1000, 2000, 3000, 4000])
    ).run(RiskInputV1.create(with_input_hash(valid_input(), rule_set)), rule_set_dto(rule_set))
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
        RiskInputV1.create(with_input_hash(valid_input(), rule_set)), rule_set_dto(rule_set)
    )
    assert audit.decision.decision_origin == "TIMEOUT_GUARD"
    assert audit.decision.error_code == "QQ-RISK-4005"
    assert audit.decision.rule_results[-1].rule_id == "RISK.SYSTEM.EVALUATION_TIMEOUT"
    RiskAuditSemanticValidator().validate(audit)


def test_runner_uses_bounded_admission_saturation_and_same_input_version_fencing() -> None:
    rule_set = valid_rule_set()
    rule_set["evaluation_timeout_us"] = 1
    rule_set = with_hashes(rule_set)
    release = Event()
    observer = RecordingObserver()
    runner = RiskEvaluationRunner(
        BlockingEvaluator(release),
        FakeClock([0, 0, 0, 0, 0, 0, 0, 0, 0]),
        metrics_observer=observer,
    )
    risk_input = RiskInputV1.create(with_input_hash(valid_input(), rule_set))
    audit = runner.run(risk_input, rule_set_dto(rule_set))
    assert audit.decision.decision_origin == "TIMEOUT_GUARD"
    second_payload = valid_input(rule_set)
    second_payload["order"]["order_id"] = "550e8400-e29b-41d4-a716-446655440099"
    saturated = runner.run(
        RiskInputV1.create(with_input_hash(second_payload, rule_set)), rule_set_dto(rule_set)
    )
    assert saturated.decision.decision_origin == "TIMEOUT_GUARD"
    release.set()
    repeated = runner.run(risk_input, rule_set_dto(rule_set))
    assert repeated.decision.decision_origin == "TIMEOUT_GUARD"
    labels = [event[2] for event in observer.events if event[0] == "risk_decisions_total"]
    assert labels
    assert set(labels[0]) == {"decision", "origin", "error_code"}


def test_runner_fail_closed_when_audit_semantics_are_invalid() -> None:
    rule_set = valid_rule_set()
    audit_input = RiskInputV1.create(with_input_hash(valid_input(), rule_set))
    runner = RiskEvaluationRunner(DuplicateRuleEvaluator(), FakeClock([0, 1000, 2000, 3000, 4000]))
    with pytest.raises(RiskContractError):
        runner.run(audit_input, rule_set_dto(rule_set))


def test_float_is_rejected_before_evaluation() -> None:
    payload = valid_input()
    payload["market"]["risk_price"] = 10.0
    with pytest.raises(RiskContractError, match="float is forbidden"):
        RiskInputV1.create(payload)


def test_fail_closed_taxonomy_4001_through_4011_has_stable_examples() -> None:
    seen: set[str] = set()
    seen.add(
        DeterministicRiskEvaluator()
        .evaluate(
            RiskInputV1.create(with_input_hash(high_quantity_input(), valid_rule_set())),
            rule_set_dto(valid_rule_set()),
        )
        .error_code
        or ""
    )
    for quality, _code in {
        "STALE": "QQ-RISK-4002",
        "PARTIAL": "QQ-RISK-4003",
        "TIMEOUT": "QQ-RISK-4010",
        "UNAVAILABLE": "QQ-RISK-4006",
    }.items():
        payload = valid_input()
        payload["account"]["metadata"]["quality"] = quality
        if quality == "PARTIAL":
            payload["account"]["metadata"]["missing_fields"] = ["equity"]
        payload = with_input_hash(payload, valid_rule_set())
        seen.add(
            DeterministicRiskEvaluator()
            .evaluate(RiskInputV1.create(payload), rule_set_dto(valid_rule_set()))
            .error_code
            or ""
        )
    version_mismatch = valid_input()
    version_mismatch["portfolio"]["metadata"]["trading_day"] = "2026-07-03"
    version_mismatch = with_input_hash(version_mismatch, valid_rule_set())
    seen.add(
        DeterministicRiskEvaluator()
        .evaluate(RiskInputV1.create(version_mismatch), rule_set_dto(valid_rule_set()))
        .error_code
        or ""
    )
    timeout_rules = valid_rule_set()
    timeout_rules["evaluation_timeout_us"] = 1
    timeout_rules = with_hashes(timeout_rules)
    seen.add(
        RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0, 2000, 3000]))
        .run(
            RiskInputV1.create(with_input_hash(valid_input(), timeout_rules)),
            rule_set_dto(timeout_rules),
        )
        .decision.error_code
        or ""
    )
    with pytest.raises(RiskContractError) as rule_error:
        loose = valid_rule_set()
        loose["system_hard_limits"]["max_order_quantity"] = 999
        rule_set_dto(with_hashes(loose))
    seen.add(rule_error.value.code)
    payload = valid_input()
    payload["order"]["checksum"] = "0" * 64
    payload["input_version"] = hash_without(payload, "input_version")
    seen.add(
        DeterministicRiskEvaluator()
        .evaluate(RiskInputV1.create(payload), rule_set_dto(valid_rule_set()))
        .error_code
        or ""
    )
    bad_reduce = reduce_input(valid_rule_set())
    bad_reduce["order"]["reduction_evidence"]["position_snapshot_version"] = "bad"
    bad_reduce = with_input_hash(bad_reduce, valid_rule_set())
    seen.add(
        DeterministicRiskEvaluator()
        .evaluate(RiskInputV1.create(bad_reduce), rule_set_dto(valid_rule_set()))
        .error_code
        or ""
    )
    mismatch = valid_input()
    mismatch["rule_set_hash"] = "a" * 64
    mismatch["input_version"] = hash_without(mismatch, "input_version")
    seen.add(
        DeterministicRiskEvaluator()
        .evaluate(RiskInputV1.create(mismatch), rule_set_dto(valid_rule_set()))
        .error_code
        or ""
    )
    assert seen >= {f"QQ-RISK-{code}" for code in range(4001, 4012)}


def test_public_dto_constructors_and_unchecked_are_closed() -> None:
    payload = valid_input()
    rule_set = valid_rule_set()
    with pytest.raises(TypeError):
        RiskInputV1(payload)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RiskRuleSetV1(rule_set)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        RiskInputV1.unchecked(payload)
    with pytest.raises(TypeError):
        RiskRuleSetV1.unchecked(rule_set)


def test_schema_validation_and_deep_freeze_reject_mutation_and_extra_fields() -> None:
    payload = valid_input()
    dto = RiskInputV1.create(payload)
    payload["order"]["quantity"] = 999
    assert dto.to_primitive()["order"]["quantity"] == 100
    payload_with_extra = valid_input()
    payload_with_extra["order"]["unexpected"] = "bad"
    payload_with_extra = with_input_hash(payload_with_extra, valid_rule_set())
    with pytest.raises(RiskContractError) as exc:
        RiskInputV1.create(payload_with_extra)
    assert exc.value.code == "QQ-RISK-4008"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["account"].__setitem__("projected_available_cash", "1.00"),
        lambda payload: payload["portfolio"]["scope_metrics"][0].__setitem__(
            "projected_gross_exposure", "9999.00"
        ),
        lambda payload: payload["market"].__setitem__("risk_price", "10.10"),
        lambda payload: payload["portfolio"]["scope_metrics"][0].__setitem__(
            "scope_id", "wrong-account"
        ),
        lambda payload: payload["account"]["metadata"].__setitem__("aggregate_version", 0),
        lambda payload: payload["order"].__setitem__("checksum", "0" * 64),
    ],
)
def test_checksum_scope_version_and_price_recompute_fail_closed(mutation: Any) -> None:
    rule_set = valid_rule_set()
    payload = valid_input(rule_set)
    mutation(payload)
    payload["input_version"] = hash_without(payload, "input_version")
    try:
        risk_input = RiskInputV1.create(payload)
    except RiskContractError as exc:
        assert exc.code == "QQ-RISK-4008"
        return
    decision = DeterministicRiskEvaluator().evaluate(risk_input, rule_set_dto(rule_set))
    assert decision.decision == "REJECT"
    assert decision.error_code == "QQ-RISK-4008"


def test_reduce_exception_requires_policy_whitelist_rule_declaration_and_valid_evidence() -> None:
    rule_set = valid_rule_set()
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
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(reduce_input(rule_set)), rule_set_dto(rule_set)
    )
    assert next(r for r in decision.rule_results if r.rule_id == "RULE.POSITION").result == "REJECT"

    unlisted = deepcopy(rule_set)
    unlisted["reduce_only_policy"] = {"enabled": True, "exempt_rule_ids": []}
    unlisted = with_hashes(unlisted)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(reduce_input(unlisted)), rule_set_dto(unlisted)
    )
    assert next(r for r in decision.rule_results if r.rule_id == "RULE.POSITION").result == "REJECT"

    declared = deepcopy(rule_set)
    declared["rules"][0]["reduction_exception"] = "NEVER"
    declared["reduce_only_policy"] = {"enabled": True, "exempt_rule_ids": ["RULE.POSITION"]}
    declared = with_hashes(declared)
    decision = DeterministicRiskEvaluator().evaluate(
        RiskInputV1.create(reduce_input(declared)), rule_set_dto(declared)
    )
    assert decision.error_code == "QQ-RISK-4007"


@pytest.mark.parametrize(
    ("field", "relaxed"),
    [
        ("max_order_quantity", 1_000),
        ("max_order_notional", "100000.00"),
        ("max_projected_gross_exposure", "200000.00"),
        ("max_daily_loss", "999999.00"),
        ("activity_window_ms", 120000),
    ],
)
def test_candidate_cannot_relax_accepted_system_hard_baseline(field: str, relaxed: Any) -> None:
    candidate = valid_rule_set()
    candidate["system_hard_limits"][field] = relaxed
    candidate = with_hashes(candidate)
    with pytest.raises(RiskContractError) as exc:
        rule_set_dto(candidate)
    assert exc.value.code == "QQ-RISK-4007"


@dataclass
class FakeClock:
    monotonic_values: list[int]

    def monotonic_ns(self) -> int:
        if len(self.monotonic_values) == 1:
            return self.monotonic_values[0]
        return self.monotonic_values.pop(0)

    def utc_now(self) -> datetime:
        return datetime(2026, 7, 2, 2, 0, 0, tzinfo=UTC)


class BlockingEvaluator(DeterministicRiskEvaluator):
    def __init__(self, release: Event) -> None:
        self._release = release

    def iter_rule_results(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> Any:
        del risk_input, rule_set
        self._release.wait()
        return
        yield  # pragma: no cover


class DuplicateRuleEvaluator(DeterministicRiskEvaluator):
    def iter_rule_results(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> Any:
        del risk_input, rule_set
        result = RuleResult(
            0,
            "DUPLICATE",
            "INPUT_VALIDITY",
            "SYSTEM",
            None,
            1,
            None,
            "PASS",
            "RISK_RULE_PASSED",
            None,
            None,
        )
        yield result
        yield result


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, int, dict[str, str]]] = []

    def observe(self, name: str, value: int, labels: dict[str, str]) -> None:
        self.events.append((name, value, dict(labels)))


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
            "checksum": "0" * 64,
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


def high_quantity_input() -> dict[str, Any]:
    payload = valid_input()
    payload["order"]["quantity"] = 501
    return with_input_hash(payload, valid_rule_set())


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
        "checksum": "0" * 64,
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


def accepted_policy(rule_set: dict[str, Any] | None = None) -> AcceptedHardPolicy:
    rules = rule_set or valid_rule_set()
    return AcceptedHardPolicy.create(
        version=rules["hard_limit_policy_version"],
        valuation_currency=rules["valuation_currency"],
        system_hard_limits=rules["system_hard_limits"],
        policy_hash=hard_limit_policy_hash(rules),
    )


def rule_set_dto(rule_set: dict[str, Any]) -> RiskRuleSetV1:
    return RiskRuleSetV1.create(rule_set, accepted_hard_policy=accepted_policy())


def with_input_hash(payload: dict[str, Any], rule_set: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result["rule_set_version"] = rule_set["rule_set_version"]
    result["rule_set_hash"] = rule_set["content_hash"]
    result["order"]["checksum"] = hash_without(result["order"], "checksum")
    for name in ("account", "portfolio", "market"):
        result[name]["metadata"]["checksum"] = hash_snapshot_without_metadata_checksum(result[name])
    result["input_version"] = hash_without(result, "input_version")
    return result
