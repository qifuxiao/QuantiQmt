from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from quantiqmt.contracts import ContractValidationError, validate_contract_candidate

FIXTURE = Path(__file__).parent / "fixtures/risk.order_evaluated.v2/semantic-evaluator.valid.json"


def _audit() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("contract_id", "candidate"),
    [
        ("CONTRACT-RISK-RULE-RESULT-V1", lambda value: value["decision"]["rule_results"][0]),
        ("CONTRACT-RISK-RULE-TIMING-V1", lambda value: value["rule_timings"][0]),
        ("CONTRACT-RISK-DECISION-V1", lambda value: value["decision"]),
        ("CONTRACT-RISK-AUDIT-OUTPUT-V1", lambda value: value),
    ],
)
def test_each_risk_output_identity_resolves_one_formal_schema_graph(
    contract_id: str, candidate: Any
) -> None:
    value = _audit()
    validate_contract_candidate(contract_id, candidate(value), semantic_validator=lambda _: None)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["decision"]["rule_results"][0].__setitem__("priority", -1),
        lambda value: value["decision"]["rule_results"][0].__setitem__("reason_code", "UNKNOWN"),
        lambda value: value["decision"].__setitem__("decision_id", "not-a-uuid"),
        lambda value: value["decision"].__setitem__("input_version", "A" * 64),
        lambda value: value.__setitem__("evaluated_at", "2026-07-02T02:00:00+08:00"),
        lambda value: value["decision"]["rule_results"][0].__setitem__(
            "measured_value", {"kind": "INTEGER", "value": True}
        ),
        lambda value: value["decision"]["rule_results"][0].__setitem__("unexpected", True),
        lambda value: value["decision"].__setitem__("rule_results", []),
    ],
)
def test_formal_audit_graph_rejects_output_boundary_mutations(mutation: Any) -> None:
    candidate = deepcopy(_audit())
    mutation(candidate)

    with pytest.raises(ContractValidationError):
        validate_contract_candidate(
            "CONTRACT-RISK-AUDIT-OUTPUT-V1",
            candidate,
            semantic_validator=lambda _: None,
        )
