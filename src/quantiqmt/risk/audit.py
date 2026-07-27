"""Risk audit semantic validation and public event projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from quantiqmt.contracts import MessageEnvelope, SchemaRegistry
from quantiqmt.risk.model import (
    MutableJsonValue,
    RiskAuditOutputV1,
    RiskContractError,
    RiskInputV1,
    v2_message_id,
)


class RiskAuditSemanticValidator:
    """Executable PORTS-RISK semantic validator for RiskAuditOutputV1."""

    def validate(self, audit: RiskAuditOutputV1) -> None:
        payload = audit.to_primitive()
        decision = _mapping(payload["decision"], "decision")
        results = _sequence(decision["rule_results"], "rule_results")
        timings = _sequence(payload["rule_timings"], "rule_timings")
        if not results:
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "empty rule_results")

        seen: set[str] = set()
        for index, result_obj in enumerate(results):
            result = _mapping(result_obj, "result")
            if result["evaluation_index"] != index:
                raise RiskContractError(
                    "QQ-RISK-4008", "RISK_INPUT_INVALID", "non-contiguous result index"
                )
            rule_id = _str(result["rule_id"], "rule_id")
            if rule_id in seen:
                raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "duplicate rule_id")
            seen.add(rule_id)
        if len(timings) != len(results):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "timing/result count mismatch"
            )
        for index, (result_obj, timing_obj) in enumerate(zip(results, timings, strict=True)):
            result = _mapping(result_obj, "result")
            timing = _mapping(timing_obj, "timing")
            if timing["evaluation_index"] != index:
                raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "unsorted timing")
            if (timing["evaluation_index"], timing["rule_id"]) != (
                result["evaluation_index"],
                result["rule_id"],
            ):
                raise RiskContractError(
                    "QQ-RISK-4008", "RISK_INPUT_INVALID", "timing identity mismatch"
                )
        timing_sum = sum(
            _int(_mapping(item, "timing")["latency_us"], "latency_us") for item in timings
        )
        if _int(payload["total_latency_us"], "total_latency_us") < timing_sum:
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "latency sum mismatch")

        origin = decision["decision_origin"]
        timeout_positions = [
            index
            for index, result_obj in enumerate(results)
            if _mapping(result_obj, "result")["phase"] == "TIMEOUT_GUARD"
            or _mapping(result_obj, "result")["rule_id"] == "RISK.SYSTEM.EVALUATION_TIMEOUT"
        ]
        if origin in {"EVALUATOR", "INPUT_GUARD"}:
            if timeout_positions:
                raise RiskContractError(
                    "QQ-RISK-4008", "RISK_INPUT_INVALID", "unexpected timeout guard"
                )
            if _int(payload["completed_rule_count"], "completed_rule_count") != len(results):
                raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "bad completed count")
            if origin == "INPUT_GUARD" and decision["decision"] != "REJECT":
                raise RiskContractError(
                    "QQ-RISK-4008", "RISK_INPUT_INVALID", "input guard must reject"
                )
            return
        if origin != "TIMEOUT_GUARD":
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "unknown decision origin")
        if timeout_positions != [len(results) - 1]:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "timeout guard must be last"
            )
        timeout = _mapping(results[-1], "timeout")
        if (
            decision["decision"] != "REJECT"
            or decision["primary_reason_code"] != "RISK_EVALUATION_TIMEOUT"
            or decision["error_code"] != "QQ-RISK-4005"
            or timeout["result"] != "REJECT"
            or timeout["reason_code"] != "RISK_EVALUATION_TIMEOUT"
        ):
            raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "bad timeout semantics")
        if _int(payload["completed_rule_count"], "completed_rule_count") != len(results) - 1:
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "bad timeout completed count"
            )
        if _int(payload["total_latency_us"], "total_latency_us") < _int(
            payload["evaluation_timeout_us"], "evaluation_timeout_us"
        ):
            raise RiskContractError(
                "QQ-RISK-4008", "RISK_INPUT_INVALID", "timeout latency below budget"
            )


def validate_risk_audit_output(audit: RiskAuditOutputV1) -> None:
    """Run the shared formal-schema then semantic validation boundary."""
    registry = SchemaRegistry.runtime_default()
    registry.validator().validate_with_semantics(
        "risk.order_evaluated.v2",
        2,
        audit.to_primitive(),
        lambda _payload: RiskAuditSemanticValidator().validate(audit),
    )


def build_risk_v1_payload(audit: RiskAuditOutputV1) -> dict[str, MutableJsonValue]:
    validate_risk_audit_output(audit)
    payload = audit.to_primitive()
    decision = _mapping(payload["decision"], "decision")
    states = _mapping(decision["snapshot_states"], "snapshot_states")
    results = _sequence(decision["rule_results"], "rule_results")
    timings = _sequence(payload["rule_timings"], "rule_timings")
    projected_results: list[MutableJsonValue] = []
    for result_obj, timing_obj in zip(results, timings, strict=True):
        result = _mapping(result_obj, "result")
        timing = _mapping(timing_obj, "timing")
        projected_results.append(
            {
                "rule_id": _str(result["rule_id"], "rule_id"),
                "result": _str(result["result"], "result"),
                "reason_code": _str(result["reason_code"], "reason_code"),
                "latency_us": _int(timing["latency_us"], "latency_us"),
                "measured_value": _project_value(result["measured_value"]),
                "limit_value": _project_value(result["limit_value"]),
            }
        )
    return {
        "decision_id": cast(str, decision["decision_id"]),
        "order_id": cast(str, decision["order_id"]),
        "expected_order_version": cast(int, decision["expected_order_version"]),
        "decision": cast(str, decision["decision"]),
        "rule_set_version": cast(str, decision["rule_set_version"]),
        "snapshot_versions": {
            name: _str(_mapping(state, "snapshot")["snapshot_version"], "snapshot_version")
            for name, state in states.items()
        },
        "rule_results": projected_results,
        "evaluated_at": cast(str, payload["evaluated_at"]),
    }


def build_risk_v2_envelope(
    audit: RiskAuditOutputV1,
    risk_input: RiskInputV1,
    *,
    registry: SchemaRegistry,
    causation_id: str | None,
) -> MessageEnvelope:
    validate_risk_audit_output(audit)
    payload = audit.to_primitive()
    decision = _mapping(payload["decision"], "decision")
    input_payload = risk_input.to_primitive()
    _validate_input_audit_binding(input_payload, decision)
    order = _mapping(input_payload["order"], "order")
    envelope = _envelope(
        message_type="risk.order_evaluated.v2",
        message_id=v2_message_id(_str(decision["decision_id"], "decision_id")),
        schema_version=2,
        order_id=_str(decision["order_id"], "order_id"),
        expected_order_version=_int(decision["expected_order_version"], "expected_order_version"),
        occurred_at=_str(payload["evaluated_at"], "evaluated_at"),
        correlation_id=_str(order["intent_id"], "intent_id"),
        causation_id=causation_id,
        payload=payload,
    )
    return MessageEnvelope.create(envelope, registry)


def project_risk_v1_envelope(
    audit: RiskAuditOutputV1,
    risk_input: RiskInputV1,
    *,
    registry: SchemaRegistry,
    causation_id: str | None,
) -> MessageEnvelope:
    payload = build_risk_v1_payload(audit)
    audit_payload = audit.to_primitive()
    decision = _mapping(audit_payload["decision"], "decision")
    input_payload = risk_input.to_primitive()
    _validate_input_audit_binding(input_payload, decision)
    order = _mapping(input_payload["order"], "order")
    envelope = _envelope(
        message_type="risk.order_evaluated.v1",
        message_id=cast(str, payload["decision_id"]),
        schema_version=1,
        order_id=cast(str, payload["order_id"]),
        expected_order_version=cast(int, payload["expected_order_version"]),
        occurred_at=cast(str, payload["evaluated_at"]),
        correlation_id=_str(order["intent_id"], "intent_id"),
        causation_id=causation_id,
        payload=payload,
    )
    return MessageEnvelope.create(envelope, registry)


def _envelope(
    *,
    message_type: str,
    message_id: str,
    schema_version: int,
    order_id: str,
    expected_order_version: int,
    occurred_at: str,
    correlation_id: str,
    causation_id: str | None,
    payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "message_type": message_type,
        "schema_version": schema_version,
        "occurred_at": occurred_at,
        "received_at": occurred_at,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "aggregate_id": order_id,
        "aggregate_version": expected_order_version,
        "source": "RiskEngine",
        "partition_key": order_id,
        "idempotency_key": f"{order_id}:{expected_order_version}:{message_type}",
        "payload": payload,
    }


def _validate_input_audit_binding(
    risk_input: Mapping[str, object], decision: Mapping[str, object]
) -> None:
    order = _mapping(risk_input["order"], "order")
    expected = {
        "input_version": risk_input["input_version"],
        "order_id": order["order_id"],
        "expected_order_version": order["aggregate_version"],
        "rule_set_version": risk_input["rule_set_version"],
        "rule_set_hash": risk_input["rule_set_hash"],
    }
    actual = {
        "input_version": decision["input_version"],
        "order_id": decision["order_id"],
        "expected_order_version": decision["expected_order_version"],
        "rule_set_version": decision["rule_set_version"],
        "rule_set_hash": decision["rule_set_hash"],
    }
    if actual != expected:
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", "audit/input mismatch")


def _project_value(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    kind = value.get("kind")
    if kind == "DECIMAL":
        candidate = value.get("value")
        return candidate if isinstance(candidate, str) else None
    if kind == "INTEGER":
        candidate = value.get("value")
        if isinstance(candidate, int):
            text = str(candidate)
            return text if len(text.removeprefix("-")) <= 18 else None
    return None


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
        raise RiskContractError("QQ-RISK-4008", "RISK_INPUT_INVALID", f"{name} must be int")
    return value
