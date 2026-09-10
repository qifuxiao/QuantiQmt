"""Generated status, version/checksum precedence and finalization deadline cases."""

from hypothesis import given
from hypothesis import strategies as st
from pytest import MonkeyPatch
from tests.unit.risk.execution_helpers import ImmediateExecutor
from tests.unit.risk.test_review_repairs import (
    MutableClock,
    install_finalization_hook,
)
from tests.unit.risk.test_risk_engine import (
    reduce_input,
    rule_set_dto,
    valid_input,
    valid_rule_set,
    with_input_hash,
)

from quantiqmt.risk import (
    DeterministicRiskEvaluator,
    RiskEvaluationRunner,
    RiskInputV1,
    hash_without,
)


@given(
    st.sampled_from(["TRADING", "HALTED", "SUSPENDED", "CLOSED", "UNKNOWN"]),
    st.booleans(),
    st.booleans(),
    st.booleans(),
)
def test_status_and_version_failures_preserve_checksum_precedence(
    status: str, reduce: bool, mismatch: bool, corrupt: bool
) -> None:
    rules = valid_rule_set()
    payload = reduce_input(rules) if reduce else valid_input(rules)
    payload["market"]["trading_status"] = status
    if mismatch:
        payload["market"]["metadata"]["snapshot_version"] = "other"
    payload = with_input_hash(payload, rules)
    if corrupt:
        payload["market"]["metadata"]["checksum"] = "0" * 64
        payload["input_version"] = hash_without(payload, "input_version")
    risk_input = RiskInputV1.create(payload)
    before = risk_input.to_primitive()
    result = DeterministicRiskEvaluator().evaluate(risk_input, rule_set_dto(rules))
    expected = (
        "QQ-RISK-4008"
        if corrupt
        else "QQ-RISK-4004"
        if mismatch
        else "QQ-RISK-4001"
        if status != "TRADING"
        else None
    )
    assert result.error_code == expected
    assert (result.decision == "PASS") == (expected is None)
    assert risk_input.to_primitive() == before


@given(
    st.sampled_from(["decide", "audit_factory", "audit_validation"]),
    st.integers(min_value=0, max_value=6_000_000),
)
def test_finalization_elapsed_cannot_escape_timeout(stage: str, elapsed_ns: int) -> None:
    clock = MutableClock()
    with MonkeyPatch.context() as patch:
        install_finalization_hook(patch, stage, lambda: setattr(clock, "ns", elapsed_ns))
        runner = RiskEvaluationRunner(DeterministicRiskEvaluator(), clock)
        runner._executor.shutdown()
        patch.setattr(runner, "_executor", ImmediateExecutor())
        audit = runner.run(RiskInputV1.create(valid_input()), rule_set_dto(valid_rule_set()))
    elapsed_us = (elapsed_ns + 999) // 1000
    assert audit.total_latency_us == elapsed_us
    assert (audit.decision.error_code == "QQ-RISK-4005") == (elapsed_us >= 4000)
    assert audit.total_latency_us >= sum(t.latency_us for t in audit.rule_timings)
