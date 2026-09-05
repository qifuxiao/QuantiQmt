from __future__ import annotations

from typing import Any

import pytest
from tests.unit.risk.test_risk_engine import (
    FakeClock,
    rule_set_dto,
    valid_input,
    valid_rule_set,
)

from quantiqmt.contracts import ContractValidationError
from quantiqmt.contracts.validation import validate_contract_candidate as formal_validate
from quantiqmt.risk import DeterministicRiskEvaluator, RiskEvaluationRunner, RiskInputV1


def test_factories_runner_and_audit_paths_share_formal_contract_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def recording_validate(
        contract_id: str,
        candidate: Any,
        *,
        semantic_validator: Any,
        registry: Any = None,
    ) -> None:
        calls.append(contract_id)
        formal_validate(
            contract_id,
            candidate,
            semantic_validator=semantic_validator,
            registry=registry,
        )

    monkeypatch.setattr("quantiqmt.risk.model.validate_contract_candidate", recording_validate)
    monkeypatch.setattr("quantiqmt.risk.audit.validate_contract_candidate", recording_validate)

    rules = valid_rule_set()
    risk_input = RiskInputV1.create(valid_input(rules))
    audit = RiskEvaluationRunner(DeterministicRiskEvaluator(), FakeClock([0] * 500)).run(
        risk_input, rule_set_dto(rules)
    )

    from quantiqmt.risk.audit import build_risk_v1_payload

    build_risk_v1_payload(audit)
    assert "CONTRACT-RISK-RULE-RESULT-V1" in calls
    assert "CONTRACT-RISK-RULE-TIMING-V1" in calls
    assert "CONTRACT-RISK-DECISION-V1" in calls
    assert calls.count("CONTRACT-RISK-AUDIT-OUTPUT-V1") >= 2


def test_invalid_schema_candidate_never_reaches_semantics_or_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_called = False

    def forbidden_semantics(_candidate: Any) -> None:
        nonlocal semantic_called
        semantic_called = True

    with pytest.raises(ContractValidationError):
        formal_validate(
            "CONTRACT-RISK-RULE-RESULT-V1",
            {
                "evaluation_index": -1,
                "rule_id": "RULE",
                "phase": "SCOPED_RULE",
                "scope": "SYSTEM",
                "scope_id": None,
                "priority": 1,
                "metric": None,
                "result": "PASS",
                "reason_code": "RISK_RULE_PASSED",
                "measured_value": None,
                "limit_value": None,
                "exception_applied": False,
            },
            semantic_validator=forbidden_semantics,
        )
    assert semantic_called is False
