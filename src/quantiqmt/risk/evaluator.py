"""Pure deterministic risk evaluator."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace
from decimal import ROUND_CEILING, Decimal
from types import MappingProxyType
from typing import Literal, cast

from quantiqmt.risk.model import (
    ERROR_BY_REASON,
    JsonValue,
    RiskContractError,
    RiskDecisionOutcome,
    RiskDecisionV1,
    RiskInputV1,
    RiskRuleSetV1,
    RuleOutcome,
    RulePhase,
    RuleResult,
    RuleScope,
    decimal_value,
    decision_id,
    hard_limit_policy_hash,
    hash_snapshot_without_metadata_checksum,
    hash_without,
    parse_utc,
    semantic_decision_hash,
    typed_boolean,
    typed_decimal,
    typed_integer,
    typed_string,
)

PHASE_ORDER: Mapping[str, int] = MappingProxyType(
    {
        "INPUT_VALIDITY": 0,
        "SNAPSHOT_VALIDITY": 1,
        "SYSTEM_HARD_LIMIT": 2,
        "SCOPED_RULE": 3,
        "TIMEOUT_GUARD": 4,
    }
)
SCOPE_ORDER: Mapping[str, int] = MappingProxyType(
    {
        "SYSTEM": 0,
        "ACCOUNT": 1,
        "PORTFOLIO": 2,
        "STRATEGY": 3,
        "INSTRUMENT": 4,
    }
)

INPUT_GUARDS: tuple[tuple[int, str], ...] = (
    (10, "RISK.INPUT.CANONICAL"),
    (20, "RISK.INPUT.IDENTITY"),
    (30, "RISK.INPUT.RULE_SET_BINDING"),
    (40, "RISK.INPUT.REDUCTION_EVIDENCE"),
    (50, "RISK.RULE_SET.VALIDITY"),
)
SNAPSHOT_GUARDS: tuple[tuple[int, str, str], ...] = (
    (10, "RISK.SNAPSHOT.ACCOUNT", "account"),
    (20, "RISK.SNAPSHOT.PORTFOLIO", "portfolio"),
    (30, "RISK.SNAPSHOT.MARKET", "market"),
    (40, "RISK.SNAPSHOT.CROSS_SOURCE", "cross_source"),
)
HARD_RULES: tuple[tuple[int, str, str, str, str], ...] = (
    (10, "SYSTEM.HARD.NEW_RISK_ENABLED", "TRADING_ENABLED", "BOOLEAN_TRUE", "allow_new_risk"),
    (20, "SYSTEM.HARD.ORDER_QUANTITY", "ORDER_QUANTITY", "MAX", "max_order_quantity"),
    (30, "SYSTEM.HARD.ORDER_NOTIONAL", "ORDER_NOTIONAL", "MAX", "max_order_notional"),
    (
        40,
        "SYSTEM.HARD.PRICE_DEVIATION_BPS",
        "PRICE_DEVIATION_BPS",
        "MAX",
        "max_price_deviation_bps",
    ),
    (
        50,
        "SYSTEM.HARD.GROSS_EXPOSURE",
        "PROJECTED_GROSS_EXPOSURE",
        "MAX",
        "max_projected_gross_exposure",
    ),
    (
        60,
        "SYSTEM.HARD.NET_EXPOSURE_ABS",
        "PROJECTED_NET_EXPOSURE_ABS",
        "MAX",
        "max_projected_net_exposure_abs",
    ),
    (70, "SYSTEM.HARD.LEVERAGE", "PROJECTED_LEVERAGE", "MAX", "max_projected_leverage"),
    (80, "SYSTEM.HARD.DAILY_LOSS", "DAILY_LOSS", "MAX", "max_daily_loss"),
    (
        90,
        "SYSTEM.HARD.ORDER_COUNT_WINDOW",
        "ORDER_COUNT_WINDOW",
        "MAX",
        "max_order_count_window",
    ),
    (
        100,
        "SYSTEM.HARD.CANCEL_RATIO_BPS",
        "CANCEL_RATIO_BPS",
        "MAX",
        "max_cancel_ratio_bps",
    ),
)
METRIC_OPERATOR: Mapping[str, str] = MappingProxyType(
    {
        "TRADING_ENABLED": "BOOLEAN_TRUE",
        "INSTRUMENT_ALLOWED": "IN_SET",
        "ORDER_QUANTITY": "MAX",
        "ORDER_NOTIONAL": "MAX",
        "PRICE_DEVIATION_BPS": "MAX",
        "AVAILABLE_CASH": "MIN",
        "POSITION_QUANTITY": "MAX",
        "PROJECTED_GROSS_EXPOSURE": "MAX",
        "PROJECTED_NET_EXPOSURE_ABS": "MAX",
        "PROJECTED_LEVERAGE": "MAX",
        "DAILY_LOSS": "MAX",
        "ORDER_COUNT_WINDOW": "MAX",
        "CANCEL_RATIO_BPS": "MAX",
    }
)
MONETARY_METRICS = frozenset(
    {
        "ORDER_NOTIONAL",
        "AVAILABLE_CASH",
        "PROJECTED_GROSS_EXPOSURE",
        "PROJECTED_NET_EXPOSURE_ABS",
        "DAILY_LOSS",
    }
)
INTEGER_METRICS = frozenset(
    {
        "ORDER_QUANTITY",
        "PRICE_DEVIATION_BPS",
        "POSITION_QUANTITY",
        "ORDER_COUNT_WINDOW",
        "CANCEL_RATIO_BPS",
    }
)


class DeterministicRiskEvaluator:
    """Synchronous, deterministic, side-effect-free risk evaluator."""

    def iter_rule_results(
        self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1
    ) -> Iterator[RuleResult]:
        context = _EvaluationContext(
            risk_input.to_primitive(),
            rule_set.to_primitive(),
            rule_set.accepted_hard_policy.to_policy_payload(),
        )
        results = _synthetic_results(context)
        for index, result in enumerate(results):
            yield replace(result, evaluation_index=index)
        if any(result.result == "REJECT" for result in results):
            return
        offset = len(results)
        business_results = [
            *_hard_rule_results(context),
            *[_dynamic_rule_result(context, rule) for rule in context.sorted_rules()],
        ]
        business_results.sort(key=_sort_key)
        for index, result in enumerate(business_results, start=offset):
            yield replace(result, evaluation_index=index)

    def decide(
        self,
        risk_input: RiskInputV1,
        rule_set: RiskRuleSetV1,
        results: tuple[RuleResult, ...],
    ) -> RiskDecisionV1:
        return _decision(risk_input.to_primitive(), rule_set.to_primitive(), results, "EVALUATOR")

    def evaluate(self, risk_input: RiskInputV1, rule_set: RiskRuleSetV1) -> RiskDecisionV1:
        results = tuple(self.iter_rule_results(risk_input, rule_set))
        return self.decide(risk_input, rule_set, results)


class _EvaluationContext:
    def __init__(
        self,
        risk_input: Mapping[str, object],
        rule_set: Mapping[str, object],
        accepted_hard_policy: Mapping[str, object],
    ) -> None:
        self.input = risk_input
        self.rule_set = rule_set
        self.accepted_hard_policy = accepted_hard_policy
        self.order = _mapping(risk_input.get("order"), "order")
        self.account = _mapping(risk_input.get("account"), "account")
        self.portfolio = _mapping(risk_input.get("portfolio"), "portfolio")
        self.market = _mapping(risk_input.get("market"), "market")
        self.hard = _mapping(rule_set.get("system_hard_limits"), "system_hard_limits")
        self.currency = _str(risk_input.get("valuation_currency"), "valuation_currency")
        self.effect = _str(self.order.get("risk_effect"), "risk_effect")

    def scope_id_for(self, scope: str) -> str | None:
        if scope == "SYSTEM":
            return None
        if scope == "ACCOUNT":
            return _str(self.order.get("account_id"), "account_id")
        if scope == "PORTFOLIO":
            return _str(self.order.get("portfolio_id"), "portfolio_id")
        if scope == "STRATEGY":
            return _str(self.order.get("strategy_id"), "strategy_id")
        if scope == "INSTRUMENT":
            return _str(self.order.get("instrument_id"), "instrument_id")
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "invalid scope")

    def metrics_for(self, scope: str) -> Mapping[str, object]:
        target = self.scope_id_for(scope)
        if scope == "SYSTEM":
            target = self.scope_id_for("ACCOUNT")
            scope = "ACCOUNT"
        rows = _sequence(self.portfolio.get("scope_metrics"), "scope_metrics")
        matches = [
            _mapping(row, "scope_metric")
            for row in rows
            if _mapping(row, "scope_metric").get("scope") == scope
            and _mapping(row, "scope_metric").get("scope_id") == target
        ]
        if len(matches) != 1:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"missing or duplicate {scope} metrics"
            )
        return matches[0]

    def sorted_rules(self) -> list[Mapping[str, object]]:
        rules = [_mapping(rule, "rule") for rule in _sequence(self.rule_set.get("rules"), "rules")]
        return sorted(
            rules,
            key=lambda item: (
                SCOPE_ORDER[_str(item.get("scope"), "scope")],
                _int(item.get("priority"), "priority"),
                _str(item.get("rule_id"), "rule_id"),
            ),
        )


def _synthetic_results(context: _EvaluationContext) -> list[RuleResult]:
    results: list[RuleResult] = []
    for priority, rule_id in INPUT_GUARDS:
        reason = _input_guard_reason(context, rule_id)
        results.append(
            _result(
                -1,
                rule_id,
                "INPUT_VALIDITY",
                "SYSTEM",
                None,
                priority,
                None,
                "PASS" if reason is None else "REJECT",
                "RISK_RULE_PASSED" if reason is None else reason,
                None,
                None,
            )
        )
    for priority, rule_id, source in SNAPSHOT_GUARDS:
        reason = _snapshot_guard_reason(context, source)
        results.append(
            _result(
                -1,
                rule_id,
                "SNAPSHOT_VALIDITY",
                "SYSTEM",
                None,
                priority,
                None,
                "PASS" if reason is None else "REJECT",
                "RISK_RULE_PASSED" if reason is None else reason,
                None,
                None,
            )
        )
    return results


def _input_guard_reason(context: _EvaluationContext, rule_id: str) -> str | None:
    try:
        if rule_id == "RISK.INPUT.CANONICAL":
            if hash_without(context.input, "input_version") != context.input.get("input_version"):
                return "RISK_INPUT_INVALID"
            _validate_order_checksum(context)
            _validate_snapshot_checksums(context)
            _validate_snapshot_quality_payloads(context)
            _validate_snapshot_versions(context)
            _validate_scope_metrics(context)
            _validate_currencies(context)
            _validate_order_price(context)
        elif rule_id == "RISK.INPUT.IDENTITY":
            _validate_identity(context)
        elif rule_id == "RISK.INPUT.RULE_SET_BINDING":
            if context.input.get("rule_set_version") != context.rule_set.get("rule_set_version"):
                return "RISK_RULE_SET_VERSION_MISMATCH"
            if context.input.get("rule_set_hash") != context.rule_set.get("content_hash"):
                return "RISK_RULE_SET_VERSION_MISMATCH"
        elif rule_id == "RISK.INPUT.REDUCTION_EVIDENCE":
            if context.effect == "REDUCE" and not _verified_reduce(context):
                return "RISK_REDUCTION_EVIDENCE_INVALID"
        elif rule_id == "RISK.RULE_SET.VALIDITY":
            _validate_rule_set(context)
    except RiskContractError as exc:
        return exc.reason_code
    return None


def _snapshot_guard_reason(context: _EvaluationContext, source: str) -> str | None:
    try:
        if source == "cross_source":
            _validate_cross_source(context)
            return None
        snapshot = {
            "account": context.account,
            "portfolio": context.portfolio,
            "market": context.market,
        }[source]
        metadata = _mapping(snapshot.get("metadata"), f"{source}.metadata")
        quality = _str(metadata.get("quality"), "quality")
        if quality == "FRESH":
            _age_ms(context, source)
            return None
        return {
            "STALE": "RISK_SNAPSHOT_STALE",
            "PARTIAL": "RISK_SNAPSHOT_PARTIAL",
            "TIMEOUT": "RISK_SNAPSHOT_TIMEOUT",
            "UNAVAILABLE": "RISK_SNAPSHOT_UNAVAILABLE",
            "VERSION_MISMATCH": "RISK_SNAPSHOT_VERSION_MISMATCH",
        }.get(quality, "RISK_INPUT_INVALID")
    except RiskContractError as exc:
        return exc.reason_code


def _hard_rule_results(context: _EvaluationContext) -> list[RuleResult]:
    return [
        _evaluate_metric(
            context,
            phase="SYSTEM_HARD_LIMIT",
            scope="SYSTEM",
            scope_id=None,
            priority=priority,
            rule_id=rule_id,
            metric=metric,
            operator=operator,
            limit=_hard_limit(context, metric, field),
            hard=True,
            reduction_exception=False,
        )
        for priority, rule_id, metric, operator, field in HARD_RULES
    ]


def _dynamic_rule_result(context: _EvaluationContext, rule: Mapping[str, object]) -> RuleResult:
    scope = cast(RuleScope, _str(rule.get("scope"), "scope"))
    scope_id = rule.get("scope_id")
    expected_scope_id = context.scope_id_for(scope)
    metric = _str(rule.get("metric"), "metric")
    limit = cast(Mapping[str, JsonValue], _mapping(rule.get("limit"), "limit"))
    if scope_id != expected_scope_id:
        return _result(
            -1,
            _str(rule.get("rule_id"), "rule_id"),
            "SCOPED_RULE",
            scope,
            cast(str | None, scope_id),
            _int(rule.get("priority"), "priority"),
            metric,
            "NOT_APPLICABLE",
            "RISK_RULE_NOT_APPLICABLE",
            None,
            limit,
        )
    return _evaluate_metric(
        context,
        phase="SCOPED_RULE",
        scope=scope,
        scope_id=expected_scope_id,
        priority=_int(rule.get("priority"), "priority"),
        rule_id=_str(rule.get("rule_id"), "rule_id"),
        metric=metric,
        operator=_str(rule.get("operator"), "operator"),
        limit=limit,
        hard=False,
        reduction_exception=_str(rule.get("reduction_exception"), "reduction_exception")
        == "ALLOW_IF_VERIFIED",
    )


def _evaluate_metric(
    context: _EvaluationContext,
    *,
    phase: RulePhase,
    scope: RuleScope,
    scope_id: str | None,
    priority: int,
    rule_id: str,
    metric: str,
    operator: str,
    limit: Mapping[str, JsonValue],
    hard: bool,
    reduction_exception: bool,
) -> RuleResult:
    if (
        rule_id == "SYSTEM.HARD.NEW_RISK_ENABLED"
        and context.effect == "REDUCE"
        and _verified_reduce(context)
    ):
        return _result(
            -1,
            rule_id,
            phase,
            scope,
            scope_id,
            priority,
            metric,
            "NOT_APPLICABLE",
            "RISK_RULE_NOT_APPLICABLE",
            typed_boolean(True),
            limit,
        )
    measured = _measured_value(context, scope, metric)
    passed = _compare(metric, operator, measured, limit)
    if passed:
        return _result(
            -1,
            rule_id,
            phase,
            scope,
            scope_id,
            priority,
            metric,
            "PASS",
            "RISK_RULE_PASSED",
            measured,
            limit,
        )
    if (
        not hard
        and reduction_exception
        and context.effect == "REDUCE"
        and _verified_reduce(context)
        and _reduce_exception_allowed(context, rule_id, metric)
    ):
        return _result(
            -1,
            rule_id,
            phase,
            scope,
            scope_id,
            priority,
            metric,
            "PASS",
            "RISK_REDUCE_ONLY_EXCEPTION_APPLIED",
            measured,
            limit,
            exception_applied=True,
        )
    return _result(
        -1,
        rule_id,
        phase,
        scope,
        scope_id,
        priority,
        metric,
        "REJECT",
        _breach_reason(metric, hard),
        measured,
        limit,
    )


def _reduce_exception_allowed(context: _EvaluationContext, rule_id: str, metric: str) -> bool:
    if metric in {"TRADING_ENABLED", "INSTRUMENT_ALLOWED"}:
        return False
    policy = _mapping(context.rule_set["reduce_only_policy"], "reduce_only_policy")
    if policy.get("enabled") is not True:
        return False
    exempt_rule_ids = set(_sequence(policy.get("exempt_rule_ids"), "exempt_rule_ids"))
    return rule_id in exempt_rule_ids


def _decision(
    risk_input: Mapping[str, object],
    rule_set: Mapping[str, object],
    results: tuple[RuleResult, ...],
    origin: Literal["EVALUATOR", "TIMEOUT_GUARD"],
) -> RiskDecisionV1:
    reject = next((result for result in results if result.result == "REJECT"), None)
    if origin == "TIMEOUT_GUARD":
        outcome: RiskDecisionOutcome = "REJECT"
        primary = "RISK_EVALUATION_TIMEOUT"
        error = "QQ-RISK-4005"
        decision_origin: Literal["TIMEOUT_GUARD", "INPUT_GUARD", "EVALUATOR"] = "TIMEOUT_GUARD"
    elif reject is None:
        outcome = "PASS"
        primary = "RISK_ALL_APPLICABLE_RULES_PASSED"
        error = None
        decision_origin = "EVALUATOR"
    else:
        outcome = "REJECT"
        primary = reject.reason_code
        error = ERROR_BY_REASON.get(primary, "QQ-RISK-4001")
        decision_origin = (
            "INPUT_GUARD"
            if reject.phase in {"INPUT_VALIDITY", "SNAPSHOT_VALIDITY"}
            else "EVALUATOR"
        )
    primitive: dict[str, object] = {
        "schema_version": 1,
        "decision_id": decision_id(
            _str(risk_input["input_version"], "input_version"),
            _str(rule_set["content_hash"], "content_hash"),
        ),
        "decision_origin": decision_origin,
        "input_version": risk_input["input_version"],
        "semantic_decision_hash": "0" * 64,
        "order_id": _mapping(risk_input["order"], "order")["order_id"],
        "expected_order_version": _mapping(risk_input["order"], "order")["aggregate_version"],
        "decision": outcome,
        "primary_reason_code": primary,
        "error_code": error,
        "rule_set_version": rule_set["rule_set_version"],
        "rule_set_hash": rule_set["content_hash"],
        "snapshot_states": _snapshot_states(risk_input, rule_set),
        "rule_results": [result.to_primitive() for result in results],
    }
    semantic_hash = semantic_decision_hash(primitive)
    return RiskDecisionV1(
        decision_id=cast(str, primitive["decision_id"]),
        decision_origin=decision_origin,
        input_version=cast(str, primitive["input_version"]),
        semantic_decision_hash=semantic_hash,
        order_id=cast(str, primitive["order_id"]),
        expected_order_version=cast(int, primitive["expected_order_version"]),
        decision=outcome,
        primary_reason_code=primary,
        error_code=error,
        rule_set_version=cast(str, primitive["rule_set_version"]),
        rule_set_hash=cast(str, primitive["rule_set_hash"]),
        snapshot_states=cast(Mapping[str, JsonValue], primitive["snapshot_states"]),
        rule_results=results,
    )


def timeout_decision(
    risk_input: RiskInputV1, rule_set: RiskRuleSetV1, results: tuple[RuleResult, ...]
) -> RiskDecisionV1:
    return _decision(risk_input.to_primitive(), rule_set.to_primitive(), results, "TIMEOUT_GUARD")


def timeout_result(index: int) -> RuleResult:
    return _result(
        index,
        "RISK.SYSTEM.EVALUATION_TIMEOUT",
        "TIMEOUT_GUARD",
        "SYSTEM",
        None,
        0,
        None,
        "REJECT",
        "RISK_EVALUATION_TIMEOUT",
        None,
        None,
    )


def _result(
    evaluation_index: int,
    rule_id: str,
    phase: RulePhase,
    scope: RuleScope,
    scope_id: str | None,
    priority: int,
    metric: str | None,
    result: RuleOutcome,
    reason_code: str,
    measured_value: Mapping[str, JsonValue] | None,
    limit_value: Mapping[str, JsonValue] | None,
    *,
    exception_applied: bool = False,
) -> RuleResult:
    return RuleResult(
        evaluation_index,
        rule_id,
        phase,
        scope,
        scope_id,
        priority,
        metric,
        result,
        reason_code,
        measured_value,
        limit_value,
        exception_applied,
    )


def _sort_key(result: RuleResult) -> tuple[int, int, int, str]:
    return (PHASE_ORDER[result.phase], SCOPE_ORDER[result.scope], result.priority, result.rule_id)


def _compare(
    metric: str, operator: str, measured: Mapping[str, JsonValue], limit: Mapping[str, JsonValue]
) -> bool:
    if operator == "BOOLEAN_TRUE":
        return (
            measured.get("kind") == "BOOLEAN"
            and measured.get("value") is True
            and limit.get("value") is True
        )
    if operator == "IN_SET":
        values = limit.get("values")
        return isinstance(values, tuple) and measured.get("value") in values
    if operator in {"MAX", "MIN"}:
        left = _numeric_typed(metric, measured)
        right = _numeric_typed(metric, limit)
        return left <= right if operator == "MAX" else left >= right
    raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "invalid operator")


def _numeric_typed(metric: str, value: Mapping[str, JsonValue]) -> Decimal:
    if metric in INTEGER_METRICS:
        return Decimal(_int(value.get("value"), "value"))
    return decimal_value(value.get("value"), field="value")


def _hard_limit(context: _EvaluationContext, metric: str, field: str) -> Mapping[str, JsonValue]:
    value = context.hard[field]
    if metric == "TRADING_ENABLED":
        return typed_boolean(cast(bool, value))
    if metric in INTEGER_METRICS:
        return typed_integer(_int(value, field))
    if metric == "PROJECTED_LEVERAGE":
        return typed_decimal(_str(value, field), None)
    return typed_decimal(_str(value, field), context.currency)


def _measured_value(
    context: _EvaluationContext, scope: RuleScope, metric: str
) -> Mapping[str, JsonValue]:
    if metric == "TRADING_ENABLED":
        if scope == "SYSTEM":
            return typed_boolean(cast(bool, context.hard["allow_new_risk"]))
        return typed_boolean(cast(bool, context.metrics_for(scope).get("enabled")))
    if metric == "INSTRUMENT_ALLOWED":
        return typed_string(_str(context.order.get("instrument_id"), "instrument_id"))
    if metric == "ORDER_QUANTITY":
        return typed_integer(_int(context.order.get("quantity"), "quantity"))
    if metric == "ORDER_NOTIONAL":
        price = decimal_value(context.market.get("risk_price"), field="risk_price")
        quantity = Decimal(_int(context.order.get("quantity"), "quantity"))
        notional = (abs(price) * quantity).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)
        return typed_decimal(notional, context.currency)
    if metric == "PRICE_DEVIATION_BPS":
        return typed_integer(_int(context.market.get("price_deviation_bps"), "price_deviation_bps"))
    if metric == "AVAILABLE_CASH":
        return typed_decimal(
            _str(context.account.get("projected_available_cash"), "cash"), context.currency
        )
    if metric == "DAILY_LOSS":
        daily_loss = max(
            decimal_value(context.account.get("daily_loss"), field="daily_loss"), Decimal("0")
        )
        return typed_decimal(daily_loss, context.currency)
    metrics = context.metrics_for(scope)
    if metric == "POSITION_QUANTITY":
        return typed_integer(abs(_int(metrics.get("projected_position_quantity"), metric)))
    if metric == "PROJECTED_GROSS_EXPOSURE":
        return typed_decimal(
            _str(metrics.get("projected_gross_exposure"), metric), context.currency
        )
    if metric == "PROJECTED_NET_EXPOSURE_ABS":
        value = abs(decimal_value(metrics.get("projected_net_exposure"), field=metric))
        return typed_decimal(value, context.currency)
    if metric == "PROJECTED_LEVERAGE":
        return typed_decimal(_str(metrics.get("projected_leverage"), metric), None)
    if metric == "ORDER_COUNT_WINDOW":
        return typed_integer(_int(metrics.get("order_count_window"), metric))
    if metric == "CANCEL_RATIO_BPS":
        return typed_integer(_int(metrics.get("cancel_ratio_bps"), metric))
    raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unknown metric")


def _breach_reason(metric: str, hard: bool) -> str:
    if metric == "TRADING_ENABLED":
        return "RISK_TRADING_DISABLED"
    if metric == "INSTRUMENT_ALLOWED":
        return "RISK_INSTRUMENT_NOT_ALLOWED"
    return "RISK_HARD_LIMIT_BREACH" if hard else "RISK_RULE_BREACH"


def _snapshot_states(
    risk_input: Mapping[str, object], rule_set: Mapping[str, object]
) -> Mapping[str, JsonValue]:
    limits = _mapping(rule_set["freshness_limits_ms"], "freshness_limits_ms")
    return {
        name: {
            "snapshot_version": _mapping(risk_input[name], name)["metadata"]["snapshot_version"],  # type: ignore[index]
            "quality": _snapshot_quality(risk_input, rule_set, name),
            "age_ms": _safe_age_ms(risk_input, name),
            "max_age_ms": _int(limits[name], "max_age_ms"),
        }
        for name in ("account", "portfolio", "market")
    }


def _snapshot_quality(
    risk_input: Mapping[str, object], rule_set: Mapping[str, object], name: str
) -> str:
    snapshot = _mapping(risk_input[name], name)
    metadata = _mapping(snapshot["metadata"], "metadata")
    quality = _str(metadata["quality"], "quality")
    if quality == "FRESH":
        age = _safe_age_ms(risk_input, name)
        limit = _int(
            _mapping(rule_set["freshness_limits_ms"], "freshness_limits_ms")[name], "max_age"
        )
        if age is not None and age > limit:
            return "STALE"
    return quality


def _safe_age_ms(risk_input: Mapping[str, object], name: str) -> int | None:
    try:
        snapshot = _mapping(risk_input[name], name)
        metadata = _mapping(snapshot["metadata"], "metadata")
        return int(
            (
                parse_utc(risk_input["evaluation_time"]) - parse_utc(metadata["as_of"])
            ).total_seconds()
            * 1000
        )
    except (RiskContractError, KeyError):
        return None


def _age_ms(context: _EvaluationContext, name: str) -> int:
    age = _safe_age_ms(context.input, name)
    if age is None or age < 0:
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "invalid snapshot age")
    limit = _int(
        _mapping(context.rule_set["freshness_limits_ms"], "freshness_limits_ms")[name], "max_age"
    )
    if age > limit:
        raise RiskContractError("QQ-RISK-4002", "RISK_SNAPSHOT_STALE", "snapshot stale")
    return age


def _validate_currencies(context: _EvaluationContext) -> None:
    currencies = {
        _str(context.input.get("valuation_currency"), "input.currency"),
        _str(context.rule_set.get("valuation_currency"), "ruleset.currency"),
        _str(context.account.get("currency"), "account.currency"),
        _str(context.portfolio.get("base_currency"), "portfolio.currency"),
        _str(context.market.get("currency"), "market.currency"),
    }
    if len(currencies) != 1:
        if context.input.get("valuation_currency") != context.rule_set.get("valuation_currency"):
            raise RiskContractError(
                "QQ-RISK-4011", "RISK_RULE_SET_VERSION_MISMATCH", "valuation currency mismatch"
            )
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "input currency mismatch")


def _validate_order_price(context: _EvaluationContext) -> None:
    market_quality = _str(
        _mapping(context.market.get("metadata"), "market.metadata").get("quality"), "quality"
    )
    if market_quality != "FRESH":
        return
    order_type = context.order.get("order_type")
    if order_type == "LIMIT":
        if context.market.get("risk_price_source") != "LIMIT_PRICE":
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "bad risk price source")
        if context.market.get("risk_price") != context.order.get("limit_price"):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "limit risk price mismatch"
            )
    elif context.market.get("risk_price_source") != "MARKET_WORST_CASE":
        raise RiskContractError(
            "QQ-RISK-4008", "RISK_INPUT_INVALID", "bad market risk price source"
        )
    risk_price = decimal_value(context.market.get("risk_price"), field="risk_price")
    reference_price = decimal_value(context.market.get("reference_price"), field="reference_price")
    if reference_price <= Decimal("0"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "bad reference price")
    recomputed = (
        (abs(risk_price - reference_price) / reference_price) * Decimal(10000)
    ).to_integral_value(rounding=ROUND_CEILING)
    if context.market.get("price_deviation_bps") != int(recomputed):
        raise RiskContractError(
            "QQ-RISK-4008", "RISK_INPUT_INVALID", "price deviation bps mismatch"
        )


def _validate_identity(context: _EvaluationContext) -> None:
    if context.order.get("account_id") != context.account.get("account_id"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "account mismatch")
    if context.order.get("account_id") != context.portfolio.get("account_id"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "portfolio account mismatch")
    if context.order.get("portfolio_id") != context.portfolio.get("portfolio_id"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "portfolio mismatch")
    if context.order.get("instrument_id") != context.market.get("instrument_id"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "instrument mismatch")
    if context.order.get("market_data_version") != _mapping(
        context.market["metadata"], "metadata"
    ).get("snapshot_version"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "market version mismatch")


def _validate_cross_source(context: _EvaluationContext) -> None:
    trading_days = {
        _mapping(context.account["metadata"], "metadata").get("trading_day"),
        _mapping(context.portfolio["metadata"], "metadata").get("trading_day"),
        _mapping(context.market["metadata"], "metadata").get("trading_day"),
    }
    if len(trading_days) != 1:
        raise RiskContractError(
            "QQ-RISK-4004", "RISK_SNAPSHOT_VERSION_MISMATCH", "trading day mismatch"
        )
    activity = _int(context.hard["activity_window_ms"], "activity_window_ms")
    for scope in ("ACCOUNT", "PORTFOLIO", "STRATEGY", "INSTRUMENT"):
        if (
            _int(context.metrics_for(scope).get("activity_window_ms"), "activity_window_ms")
            != activity
        ):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "activity window mismatch"
            )


def _validate_rule_set(context: _EvaluationContext) -> None:
    if hash_without(context.rule_set, "content_hash") != context.rule_set.get("content_hash"):
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "rule set hash mismatch")
    if hard_limit_policy_hash(context.rule_set) != context.rule_set.get("hard_limit_policy_hash"):
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "hard policy hash mismatch"
        )
    if context.rule_set.get("hard_limit_policy_version") != context.accepted_hard_policy.get(
        "hard_limit_policy_version"
    ):
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy version"
        )
    if context.rule_set.get("valuation_currency") != context.accepted_hard_policy.get(
        "valuation_currency"
    ):
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy currency"
        )
    if context.rule_set.get("system_hard_limits") != context.accepted_hard_policy.get(
        "system_hard_limits"
    ):
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "unaccepted hard policy content"
        )
    rules = context.sorted_rules()
    rule_ids = [_str(rule.get("rule_id"), "rule_id") for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "duplicate rule_id")
    policy = _mapping(context.rule_set["reduce_only_policy"], "reduce_only_policy")
    if not isinstance(policy.get("enabled"), bool):
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad reduce policy")
    exempt = set(_sequence(policy.get("exempt_rule_ids"), "exempt_rule_ids"))
    rules_by_id = {_str(rule.get("rule_id"), "rule_id"): rule for rule in rules}
    for rule_id in exempt:
        rule = rules_by_id.get(cast(str, rule_id))
        if rule is None or rule.get("reduction_exception") != "ALLOW_IF_VERIFIED":
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "invalid reduce exemption"
            )
        if rule.get("metric") in {"TRADING_ENABLED", "INSTRUMENT_ALLOWED"}:
            raise RiskContractError(
                "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "forbidden reduce exemption"
            )
    for rule in rules:
        metric = _str(rule.get("metric"), "metric")
        expected_operator = METRIC_OPERATOR.get(metric)
        if expected_operator is None or rule.get("operator") != expected_operator:
            raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad metric operator")
        _validate_limit_currency(context, metric, _mapping(rule.get("limit"), "limit"))
        _validate_limit_kind(metric, _mapping(rule.get("limit"), "limit"))
        _validate_hard_cap(context, metric, _mapping(rule.get("limit"), "limit"))


def _validate_order_checksum(context: _EvaluationContext) -> None:
    if context.order.get("checksum") != hash_without(context.order, "checksum"):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "order checksum mismatch")


def _validate_snapshot_checksums(context: _EvaluationContext) -> None:
    for name, snapshot in (
        ("account", context.account),
        ("portfolio", context.portfolio),
        ("market", context.market),
    ):
        metadata = _mapping(snapshot.get("metadata"), f"{name}.metadata")
        if metadata.get("checksum") != hash_snapshot_without_metadata_checksum(snapshot):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} checksum mismatch"
            )


def _validate_snapshot_quality_payloads(context: _EvaluationContext) -> None:
    for name, snapshot in (
        ("account", context.account),
        ("portfolio", context.portfolio),
        ("market", context.market),
    ):
        metadata = _mapping(snapshot.get("metadata"), f"{name}.metadata")
        quality = _str(metadata.get("quality"), "quality")
        missing = _sequence(metadata.get("missing_fields"), "missing_fields")
        if quality in {"FRESH", "STALE"} and missing:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} missing_fields mismatch"
            )
        if quality == "PARTIAL" and not missing:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} missing_fields required"
            )
    _validate_required_fields(context)


def _validate_snapshot_versions(context: _EvaluationContext) -> None:
    for name, snapshot in (("account", context.account), ("portfolio", context.portfolio)):
        metadata = _mapping(snapshot.get("metadata"), f"{name}.metadata")
        quality = _str(metadata.get("quality"), "quality")
        aggregate_version = metadata.get("aggregate_version")
        if quality in {"FRESH", "STALE", "PARTIAL"} and not isinstance(aggregate_version, int):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} aggregate version mismatch"
            )
    market_version = _mapping(context.market.get("metadata"), "market.metadata").get(
        "aggregate_version"
    )
    if market_version is not None:
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "market aggregate version")


def _validate_required_fields(context: _EvaluationContext) -> None:
    required = _required_field_paths(context)
    null_fields = {path for path, value in required.items() if value is None}
    if not null_fields:
        return
    for name, snapshot in (
        ("account", context.account),
        ("portfolio", context.portfolio),
        ("market", context.market),
    ):
        metadata = _mapping(snapshot.get("metadata"), f"{name}.metadata")
        quality = _str(metadata.get("quality"), "quality")
        missing = {
            cast(str, item) for item in _sequence(metadata.get("missing_fields"), "missing_fields")
        }
        relevant_nulls = {path for path in null_fields if path.startswith(f"{name}.")}
        if quality in {"FRESH", "STALE"} and relevant_nulls:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} required field is null"
            )
        if quality == "PARTIAL" and missing != relevant_nulls:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} missing_fields mismatch"
            )


def _required_field_paths(context: _EvaluationContext) -> Mapping[str, object]:
    fields: dict[str, object] = {}

    def add_metric(scope: str, metric: str) -> None:
        if metric in {"TRADING_ENABLED", "INSTRUMENT_ALLOWED", "ORDER_QUANTITY"}:
            return
        if metric in {"ORDER_NOTIONAL", "PRICE_DEVIATION_BPS"}:
            fields["market.risk_price"] = context.market.get("risk_price")
            fields["market.reference_price"] = context.market.get("reference_price")
            fields["market.price_deviation_bps"] = context.market.get("price_deviation_bps")
            return
        if metric == "AVAILABLE_CASH":
            fields["account.projected_available_cash"] = context.account.get(
                "projected_available_cash"
            )
            return
        if metric == "DAILY_LOSS":
            fields["account.daily_loss"] = context.account.get("daily_loss")
            return
        row = context.metrics_for(scope)
        scope_key = scope.lower()
        if metric == "POSITION_QUANTITY":
            fields[f"portfolio.scope_metrics.{scope_key}.projected_position_quantity"] = row.get(
                "projected_position_quantity"
            )
        elif metric == "PROJECTED_GROSS_EXPOSURE":
            fields[f"portfolio.scope_metrics.{scope_key}.projected_gross_exposure"] = row.get(
                "projected_gross_exposure"
            )
        elif metric == "PROJECTED_NET_EXPOSURE_ABS":
            fields[f"portfolio.scope_metrics.{scope_key}.projected_net_exposure"] = row.get(
                "projected_net_exposure"
            )
        elif metric == "PROJECTED_LEVERAGE":
            fields[f"portfolio.scope_metrics.{scope_key}.projected_leverage"] = row.get(
                "projected_leverage"
            )
        elif metric == "ORDER_COUNT_WINDOW":
            fields[f"portfolio.scope_metrics.{scope_key}.order_count_window"] = row.get(
                "order_count_window"
            )
        elif metric == "CANCEL_RATIO_BPS":
            fields[f"portfolio.scope_metrics.{scope_key}.cancel_ratio_bps"] = row.get(
                "cancel_ratio_bps"
            )

    for _, _, metric, _, _ in HARD_RULES:
        add_metric("SYSTEM", metric)
    for rule in context.sorted_rules():
        scope = _str(rule.get("scope"), "scope")
        if rule.get("scope_id") == context.scope_id_for(scope):
            add_metric(scope, _str(rule.get("metric"), "metric"))
    return fields


def _validate_scope_metrics(context: _EvaluationContext) -> None:
    expected = {
        ("ACCOUNT", context.order.get("account_id")),
        ("PORTFOLIO", context.order.get("portfolio_id")),
        ("STRATEGY", context.order.get("strategy_id")),
        ("INSTRUMENT", context.order.get("instrument_id")),
    }
    rows = _sequence(context.portfolio.get("scope_metrics"), "scope_metrics")
    actual: set[tuple[object, object]] = set()
    for row in rows:
        metric = _mapping(row, "scope_metric")
        actual.add((metric.get("scope"), metric.get("scope_id")))
    if actual != expected or len(rows) != 4:
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "scope metrics mismatch")


def _validate_limit_kind(metric: str, limit: Mapping[str, object]) -> None:
    kind = limit.get("kind")
    if metric in MONETARY_METRICS | {"PROJECTED_LEVERAGE"} and kind != "DECIMAL":
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad limit kind")
    if metric in INTEGER_METRICS and kind != "INTEGER":
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad limit kind")
    if metric == "TRADING_ENABLED" and kind != "BOOLEAN":
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad limit kind")
    if metric == "INSTRUMENT_ALLOWED" and kind != "STRING_SET":
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "bad limit kind")


def _validate_limit_currency(
    context: _EvaluationContext, metric: str, limit: Mapping[str, object]
) -> None:
    if metric in MONETARY_METRICS and limit.get("currency") != context.currency:
        raise RiskContractError("QQ-RISK-4007", "RISK_RULE_SET_INVALID", "limit currency mismatch")
    if metric == "PROJECTED_LEVERAGE" and limit.get("currency") is not None:
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "leverage currency forbidden"
        )


def _validate_hard_cap(
    context: _EvaluationContext, metric: str, limit: Mapping[str, object]
) -> None:
    caps = {metric_name: field for _, _, metric_name, _, field in HARD_RULES}
    field = caps.get(metric)
    if field is None or metric == "TRADING_ENABLED":
        return
    hard_limit = _hard_limit(context, metric, field)
    if _numeric_typed(metric, cast(Mapping[str, JsonValue], limit)) > _numeric_typed(
        metric, hard_limit
    ):
        raise RiskContractError(
            "QQ-RISK-4007", "RISK_RULE_SET_INVALID", "dynamic limit exceeds hard cap"
        )


def _verified_reduce(context: _EvaluationContext) -> bool:
    evidence = context.order.get("reduction_evidence")
    if context.effect != "REDUCE" or not isinstance(evidence, Mapping):
        return False
    instrument_metrics = context.metrics_for("INSTRUMENT")
    before = _int(evidence.get("position_quantity_before"), "position_quantity_before")
    reserved = _int(evidence.get("reserved_reduce_quantity"), "reserved_reduce_quantity")
    max_reducible = max(abs(before) - reserved, 0)
    quantity = _int(context.order.get("quantity"), "quantity")
    if evidence.get("position_snapshot_version") != _mapping(
        context.portfolio["metadata"], "metadata"
    ).get("snapshot_version"):
        return False
    if max_reducible != evidence.get("max_reducible_quantity") or quantity > max_reducible:
        return False
    if before != instrument_metrics.get("position_quantity"):
        return False
    signed_delta = quantity if context.order.get("side") == "BUY" else -quantity
    projected = before + signed_delta
    return (
        evidence.get("projected_position_quantity") == projected
        and instrument_metrics.get("projected_position_quantity") == projected
        and abs(projected) < abs(before)
        and evidence.get("would_flip_position") is False
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} must be object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} must be array")
    return tuple(value)


def _str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} must be string")
    return value


def _int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} must be integer")
    return value
