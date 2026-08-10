from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
import yaml
from tests.contract.messages.test_ledger_portfolio_contracts import (
    BROKER_TRADE_FINGERPRINT_FIELDS,
    FIXTURES,
    ROOT,
    _accounting_request_fingerprint,
    _entry_identity,
    _load,
    _projection_state_checksum,
    _repair_command_fingerprint,
    _repair_fact_checksum,
    _source_fingerprint,
    _validate_ledger_semantics,
    _validator,
)


def test_full_account_taxonomy_and_request_resolution_are_machine_frozen() -> None:
    validator = _validator("ledger/ledger-accounting.v1.schema.json")
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    exemplar = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "LEDGER_ACCOUNT")
    taxonomy = {
        "CASH": ("ASSET", "DEBIT", None),
        "POSITION_COST": ("ASSET", "DEBIT", "600000.XSHG"),
        "COMMISSION_EXPENSE": ("EXPENSE", "DEBIT", None),
        "FEE_EXPENSE": ("EXPENSE", "DEBIT", None),
        "TAX_EXPENSE": ("EXPENSE", "DEBIT", None),
        "REALIZED_PNL": ("INCOME", "CREDIT", None),
        "ROUNDING_RESIDUAL": ("EXPENSE", "DEBIT", None),
        "CAPITAL": ("EQUITY", "CREDIT", None),
    }
    for account_type, (classification, normal_balance, instrument_id) in taxonomy.items():
        candidate = deepcopy(exemplar)
        candidate.update(
            account_type=account_type,
            classification=classification,
            normal_balance=normal_balance,
            instrument_id=instrument_id,
        )
        assert validator.is_valid(candidate), account_type
        wrong = deepcopy(candidate)
        wrong["classification"] = "EXPENSE" if classification != "EXPENSE" else "ASSET"
        assert not validator.is_valid(wrong), account_type

    request = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST")
    assert request["accounting_policy_version"] == "TRADE_ACCOUNTING_V1"
    assert request["fee_policy"]["version"] == "BROKER_CHARGES_V1"
    assert Decimal(request["fee_policy"]["fee_amount"]) > 0
    assert request["request_fingerprint"] == _accounting_request_fingerprint(request)
    assert (
        request["request_fingerprint"]
        == fixture["reference_vectors"]["accounting_request_fingerprint"]
    )
    time_changed = deepcopy(request)
    time_changed["requested_at"] = "2026-08-07T01:01:59Z"
    assert _accounting_request_fingerprint(time_changed) == request["request_fingerprint"]
    fee_changed = deepcopy(request)
    fee_changed["fee_policy"]["fee_amount"] = "0.26"
    assert _accounting_request_fingerprint(fee_changed) != request["request_fingerprint"]
    keys = {
        (item["scope_id"], item["currency"], item["account_type"], item["instrument_id"])
        for item in request["account_selections"]
    }
    assert len(keys) == len(request["account_selections"])
    assert all(item["account_active"] is True for item in request["account_selections"])


def test_source_fingerprint_uses_authoritative_projection_and_unicode_nfc() -> None:
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    transaction = next(
        dto
        for dto in fixture["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "TRADE"
    )
    assert set(transaction["source_trade"]) == set(BROKER_TRADE_FINGERPRINT_FIELDS)
    assert transaction["source_fingerprint"] == _source_fingerprint(transaction["source_trade"])
    assert fixture["reference_vectors"]["source_fingerprint"] == transaction["source_fingerprint"]
    decomposed = deepcopy(transaction["source_trade"])
    decomposed["broker_order_id"] = "ord-e\u0301-1"
    composed = deepcopy(decomposed)
    composed["broker_order_id"] = "ord-é-1"
    assert _source_fingerprint(decomposed) == _source_fingerprint(composed)
    assert (
        _source_fingerprint(decomposed)
        == fixture["reference_vectors"]["unicode_nfc_source_fingerprint"]
    )


def test_fee_policy_and_fixed_entry_ordinals_are_executable() -> None:
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    transaction = next(
        dto
        for dto in fixture["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION"
        and any(entry["entry_type"] == "FEE" for entry in dto["entries"])
    )
    ordinals = {entry["entry_type"]: entry["entry_ordinal"] for entry in transaction["entries"]}
    assert ordinals == {"POSITION_COST": 0, "COMMISSION": 1, "FEE": 2, "CASH": 4}
    assert [entry["entry_id"] for entry in transaction["entries"]] == [
        _entry_identity(transaction["transaction_id"], entry["entry_ordinal"])
        for entry in transaction["entries"]
    ]


def test_settlement_release_is_explicit_checkpoint_preserving_versioned_operation() -> None:
    fixture = _load(FIXTURES / "portfolio-projection.v1/valid.json")
    request = next(
        dto for dto in fixture["dtos"] if dto["dto_type"] == "SETTLEMENT_RELEASE_REQUEST"
    )
    change = next(
        dto
        for dto in fixture["dtos"]
        if dto["dto_type"] == "POSITION_PROJECTION_CHANGE"
        and dto["effect"]["effect_type"] == "SETTLEMENT_RELEASE"
    )
    result = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "SETTLEMENT_RELEASE_RESULT")
    assert request["calendar_evidence"]["verification_status"] == "VERIFIED"
    assert (
        request["request_fingerprint"]
        == fixture["reference_vectors"]["settlement_release_fingerprint"]
    )
    assert change["effect"]["quantity_delta"] == 0
    assert change["effect"]["available_quantity_delta"] > 0
    assert change["after"]["source_sequence"] == change["before"]["source_sequence"]
    assert change["after"]["position_version"] == change["before"]["position_version"] + 1
    assert change["after"]["portfolio_version"] == change["before"]["portfolio_version"] + 1
    assert result["outcome"] in {"RELEASED", "DUPLICATE"}


def test_single_currency_snapshot_and_projection_state_checksum_are_frozen() -> None:
    fixture = _load(FIXTURES / "portfolio-projection.v1/valid.json")
    snapshot = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "PORTFOLIO_SNAPSHOT")
    assert all(item["currency"] == snapshot["snapshot_currency"] for item in snapshot["cash"])
    assert all(
        position["currency"] == snapshot["snapshot_currency"] for position in snapshot["positions"]
    )
    assert (
        snapshot["projection_state_checksum"]
        == fixture["reference_vectors"]["projection_state_checksum"]
    )
    envelope_changed = deepcopy(snapshot)
    envelope_changed["snapshot_id"] = "99999999-9999-4999-8999-999999999998"
    envelope_changed["created_at"] = "2026-08-07T01:03:59Z"
    envelope_changed["valuation_time"] = "2026-08-07T01:03:58Z"
    assert _projection_state_checksum(envelope_changed) == snapshot["projection_state_checksum"]
    state_changed = deepcopy(snapshot)
    state_changed["cash"][0]["amount"] = "9477.51"
    assert _projection_state_checksum(state_changed) != snapshot["projection_state_checksum"]


def test_repair_fingerprint_excludes_time_noise_and_adjustment_is_not_trade() -> None:
    reconciliation = _load(FIXTURES / "reconciliation.v1/valid.json")
    command = next(dto for dto in reconciliation["dtos"] if dto["dto_type"] == "REPAIR_COMMAND")
    assert command["command_fingerprint"] == _repair_command_fingerprint(command)
    assert (
        command["command_fingerprint"]
        == reconciliation["reference_vectors"]["repair_command_fingerprint"]
    )
    time_changed = deepcopy(command)
    time_changed["requested_at"] = "2026-08-07T01:04:20Z"
    time_changed["deadline_at"] = "2026-08-07T01:05:20Z"
    time_changed["authorization"]["authorized_at"] = "2026-08-07T01:04:10Z"
    time_changed["approval"]["approved_at"] = "2026-08-07T01:04:11Z"
    assert _repair_command_fingerprint(time_changed) == command["command_fingerprint"]

    ledger = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    adjustment = next(
        dto
        for dto in ledger["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "ADJUSTMENT"
    )
    assert "source_trade" not in adjustment
    assert adjustment["adjustment_source"]["fact_type"] in {
        "QUANTITY_CORRECTION",
        "MONETARY_ADJUSTMENT",
        "COMPENSATING_FACT",
    }


def test_result_schemas_reject_illegal_outcome_code_combinations() -> None:
    fixtures = {
        "ledger/ledger-accounting.v1.schema.json": _load(
            FIXTURES / "ledger-accounting.v1/valid.json"
        ),
        "portfolio/portfolio-projection.v1.schema.json": _load(
            FIXTURES / "portfolio-projection.v1/valid.json"
        ),
        "reconciliation/reconciliation.v1.schema.json": _load(
            FIXTURES / "reconciliation.v1/valid.json"
        ),
    }
    result_types = {
        "POST_RESULT",
        "PROJECTION_RESULT",
        "SETTLEMENT_RELEASE_RESULT",
        "REPLAY_RESULT",
        "REPAIR_RESULT",
    }
    for schema_name, fixture in fixtures.items():
        validator = _validator(schema_name)
        for result in (dto for dto in fixture["dtos"] if dto["dto_type"] in result_types):
            assert validator.is_valid(result), result["dto_type"]
            illegal = deepcopy(result)
            illegal["failure_code"] = (
                None if result["failure_code"] is not None else "QQ-RECOVERY-8007"
            )
            assert not validator.is_valid(illegal), result["dto_type"]


def test_negative_fixture_matrix_covers_every_requested_guard() -> None:
    names: set[str] = set()
    for path in FIXTURES.glob("*/semantic-invalid.json"):
        names.update(case["name"] for case in _load(path)["cases"])
    for path in FIXTURES.glob("*/schema-invalid.json"):
        names.update(case["name"] for case in _load(path)["cases"])
    assert {
        "cash_wrong_classification",
        "inactive_cash_account",
        "duplicate_account_selection",
        "instrument_account_mismatch",
        "account_type_mismatch",
        "weighted_average_cost_mismatch",
        "portfolio_version_not_incremented",
        "out_of_order_projection",
        "unverified_settlement_calendar",
        "settlement_checkpoint_mismatch",
        "settlement_release_exceeds_unavailable",
        "mixed_snapshot_currency",
        "complete_snapshot_with_stale_position",
        "complete_snapshot_with_missing_position",
        "verified_replay_missing_checksum",
        "p1_automatic_repair",
        "p0_automatic_repair",
        "unknown_repair_missing_failure_code",
        "unknown_repair_not_reconciliation_required",
    } <= names


def test_case_transition_versions_link_to_unknown_result() -> None:
    fixture = _load(FIXTURES / "reconciliation.v1/valid.json")
    case = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "RECONCILIATION_CASE")
    transitions = [dto for dto in fixture["dtos"] if dto["dto_type"] == "CASE_TRANSITION"]
    result = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "REPAIR_RESULT")
    expected = case["case_version"]
    for transition in transitions:
        assert transition["expected_case_version"] == expected
        assert transition["resulting_case_version"] == expected + 1
        expected += 1
    assert result["case_version"] == expected == 5


def test_ledger_replay_reconstructs_every_projection_state_checksum_field() -> None:
    ledger = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    portfolio = _load(FIXTURES / "portfolio-projection.v1/valid.json")
    snapshot = next(dto for dto in portfolio["dtos"] if dto["dto_type"] == "PORTFOLIO_SNAPSHOT")
    cash = Decimal("10000.00")
    quantity = 0
    cost_basis = Decimal("0")
    realized_pnl = Decimal("0")
    for transaction in (
        dto
        for dto in ledger["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["ledger_sequence"] <= 2
    ):
        trade = transaction["source_trade"]
        quantity += trade["quantity"] if trade["side"] == "BUY" else -trade["quantity"]
        for entry in transaction["entries"]:
            amount = Decimal(entry["amount"])
            if entry["entry_type"] == "CASH":
                cash += amount if entry["direction"] == "DEBIT" else -amount
            elif entry["entry_type"] == "POSITION_COST":
                cost_basis += amount if entry["direction"] == "DEBIT" else -amount
            elif entry["entry_type"] in {"COMMISSION", "FEE", "TAX"}:
                realized_pnl -= amount
            elif entry["entry_type"] == "REALIZED_PNL":
                realized_pnl += amount if entry["direction"] == "CREDIT" else -amount

    position = snapshot["positions"][0]
    assert cash == Decimal(snapshot["cash"][0]["amount"])
    assert quantity == position["quantity"]
    assert cost_basis == Decimal(position["cost_basis_total"])
    assert cost_basis / quantity == Decimal(position["average_cost"])
    assert realized_pnl == Decimal(position["realized_pnl"]) == Decimal(snapshot["realized_pnl"])
    assert snapshot["source_checkpoint"]["last_transaction_checksum"] == next(
        dto["transaction_checksum"]
        for dto in ledger["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["ledger_sequence"] == 2
    )
    assert _projection_state_checksum(snapshot) == snapshot["projection_state_checksum"]
    market_only_change = deepcopy(snapshot)
    market_only_change["positions"][0]["market_price"] = "12.00"
    market_only_change["positions"][0]["market_value"] = "720.00"
    market_only_change["market_value"] = "720.00"
    market_only_change["total_equity"] = "10197.25"
    market_only_change["valuation_time"] = "2026-08-07T01:03:30Z"
    assert _projection_state_checksum(market_only_change) == snapshot["projection_state_checksum"]


def _result_pairs(
    schema: dict[str, Any], definition: str, outcome_field: str
) -> set[tuple[str, str | None]]:
    pairs: set[tuple[str, str | None]] = set()
    result = schema["$defs"][definition]
    for branch in result["oneOf"]:
        outcome_schema = branch["properties"][outcome_field]
        outcomes = outcome_schema.get("enum", [outcome_schema.get("const")])
        code_schema = branch["properties"]["failure_code"]
        codes = code_schema.get("enum", [code_schema.get("const")])
        if code_schema.get("type") == "null":
            codes = [None]
        pairs.update((outcome, code) for outcome in outcomes for code in codes)
    return pairs


def test_every_operation_has_an_exhaustive_canonical_outcome_code_matrix() -> None:
    ledger = _load(ROOT / "spec/contracts/ledger/ledger-accounting.v1.schema.json")
    portfolio = _load(ROOT / "spec/contracts/portfolio/portfolio-projection.v1.schema.json")
    reconciliation = _load(ROOT / "spec/contracts/reconciliation/reconciliation.v1.schema.json")
    assert _result_pairs(ledger, "postResult", "outcome") == {
        ("POSTED", None),
        ("DUPLICATE", None),
        *(
            ("REJECTED", code)
            for code in {
                "QQ-COMMON-1003",
                "QQ-STORAGE-7001",
                "QQ-STORAGE-7005",
                "QQ-STORAGE-7007",
                "QQ-STORAGE-7008",
                "QQ-STORAGE-7009",
                "QQ-STORAGE-7010",
                "QQ-STORAGE-7011",
                "QQ-RECOVERY-8001",
            }
        ),
        ("UNKNOWN", "QQ-STORAGE-7012"),
    }
    assert _result_pairs(portfolio, "projectionResult", "outcome") == {
        ("APPLIED", None),
        ("DUPLICATE", None),
        ("REJECTED", "QQ-COMMON-1003"),
        ("REJECTED", "QQ-STORAGE-7009"),
        ("REJECTED", "QQ-STORAGE-7010"),
        ("REJECTED", "QQ-RECOVERY-8001"),
        ("UNKNOWN", "QQ-STORAGE-7013"),
    }
    assert _result_pairs(portfolio, "settlementReleaseResult", "outcome") == {
        ("RELEASED", None),
        ("DUPLICATE", None),
        ("REJECTED", "QQ-COMMON-1003"),
        ("REJECTED", "QQ-STORAGE-7001"),
        ("REJECTED", "QQ-STORAGE-7010"),
        ("REJECTED", "QQ-RECOVERY-8001"),
        ("REJECTED", "QQ-RECOVERY-8005"),
        ("UNKNOWN", "QQ-STORAGE-7014"),
    }
    assert _result_pairs(portfolio, "replayResult", "status") == {
        ("VERIFIED", None),
        ("FALLBACK_FULL_REPLAY", "QQ-STORAGE-7003"),
        ("REJECTED", "QQ-COMMON-1003"),
        ("REJECTED", "QQ-STORAGE-7010"),
        ("REJECTED", "QQ-RECOVERY-8003"),
    }
    assert _result_pairs(reconciliation, "repairResult", "outcome") == {
        ("APPLIED", None),
        ("DUPLICATE", None),
        *(
            ("REJECTED", code)
            for code in {
                "QQ-COMMON-1003",
                "QQ-STORAGE-7001",
                "QQ-STORAGE-7005",
                "QQ-RECOVERY-8001",
                "QQ-RECOVERY-8004",
                "QQ-RECOVERY-8005",
                "QQ-RECOVERY-8006",
            }
        ),
        ("UNKNOWN", "QQ-RECOVERY-8007"),
    }


def test_task_governance_remains_active_draft_pending_and_release_prohibited() -> None:
    task_text = (ROOT / "tasks/active/TASK-018-ledger-portfolio-contracts.md").read_text(
        encoding="utf-8"
    )
    task = yaml.safe_load(task_text.split("---", 2)[1])
    assert task["status"] == "active"
    assert task["delivery"] == {
        "schema_version": 1,
        "contract_status": "draft",
        "implementation_status": "in_progress",
        "acceptance_status": "passed",
        "review_status": "pending",
        "release_status": "prohibited",
    }
    index = yaml.safe_load((ROOT / "tasks/index.yaml").read_text(encoding="utf-8"))
    tasks = {item["id"]: item for item in index["tasks"]}
    assert tasks["TASK-018"]["status"] == "active"
    assert tasks["TASK-007"]["status"] == "blocked"


def test_adjustment_transaction_route_is_complete_and_trade_exclusive() -> None:
    validator = _validator("ledger/ledger-accounting.v1.schema.json")
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    trade = next(
        dto
        for dto in fixture["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "TRADE"
    )
    adjustment = next(
        dto
        for dto in fixture["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "ADJUSTMENT"
    )
    validator.validate(adjustment)
    assert "source_trade" not in adjustment
    assert {
        "case_id",
        "case_version",
        "command_id",
        "command_fingerprint",
        "repair_fact_checksum",
        "source_checkpoint",
    } <= adjustment["adjustment_source"].keys()
    assert adjustment["adjustment_source"]["repair_fact_checksum"] == _repair_fact_checksum(
        adjustment["adjustment_source"]
    )

    for field in (
        "case_id",
        "case_version",
        "command_id",
        "command_fingerprint",
        "repair_fact_checksum",
        "source_checkpoint",
    ):
        missing = deepcopy(adjustment)
        missing["adjustment_source"].pop(field)
        assert not validator.is_valid(missing), field

    fabricated_trade = deepcopy(adjustment)
    fabricated_trade["source_trade"] = trade["source_trade"]
    assert not validator.is_valid(fabricated_trade)
    trade_with_repair_fields = deepcopy(trade)
    trade_with_repair_fields["adjustment_source"] = adjustment["adjustment_source"]
    assert not validator.is_valid(trade_with_repair_fields)


def test_account_identity_is_canonical_and_mismatch_fails_closed() -> None:
    normative_paths = (
        "spec/contracts/ledger/ledger-accounting.v1.schema.json",
        "spec/interfaces/ledger-portfolio-ports.md",
        "spec/repositories/ledger-portfolio-repositories.md",
        "spec/storage/ledger-portfolio.yaml",
        "spec/workflows/trade-accounting.yaml",
    )
    for path in normative_paths:
        assert "trading_account_id" not in (ROOT / path).read_text(encoding="utf-8"), path

    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    _validate_ledger_semantics(fixture)
    mutations: dict[str, Callable[[dict[str, Any]], object]] = {
        "request_account_mismatch": lambda document: next(
            dto for dto in document["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST"
        ).update(account_id="acct-other"),
        "transaction_account_mismatch": lambda document: next(
            dto
            for dto in document["dtos"]
            if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "TRADE"
        ).update(account_id="acct-other"),
        "selection_account_mismatch": lambda document: next(
            dto for dto in document["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST"
        )["account_selections"][0].update(account_id="acct-other"),
        "ledger_account_mismatch": lambda document: next(
            dto for dto in document["dtos"] if dto["dto_type"] == "LEDGER_ACCOUNT"
        ).update(account_id="acct-other"),
    }
    for _name, mutate in mutations.items():
        invalid = deepcopy(fixture)
        mutate(invalid)
        with pytest.raises(ValueError, match="account identity"):
            _validate_ledger_semantics(invalid)


def test_fee_is_authoritative_typed_currency_bound_and_identity_bearing() -> None:
    validator = _validator("ledger/ledger-accounting.v1.schema.json")
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    request = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST")
    assert request["source_trade"]["fee"] == {
        "amount": "0.25",
        "currency": "CNY",
        "rounding_policy_version": "CURRENCY_MINOR_UNIT_HALF_EVEN_V1",
    }
    assert "fee" in BROKER_TRADE_FINGERPRINT_FIELDS

    missing = deepcopy(request)
    missing["source_trade"].pop("fee")
    assert not validator.is_valid(missing)
    float_amount = deepcopy(request)
    float_amount["source_trade"]["fee"]["amount"] = 0.25
    assert not validator.is_valid(float_amount)
    wrong_rounding = deepcopy(request)
    wrong_rounding["source_trade"]["fee"]["rounding_policy_version"] = "OTHER"
    assert not validator.is_valid(wrong_rounding)

    wrong_currency = deepcopy(fixture)
    next(dto for dto in wrong_currency["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST")[
        "source_trade"
    ]["fee"]["currency"] = "USD"
    with pytest.raises(ValueError, match="fee currency"):
        _validate_ledger_semantics(wrong_currency)


def test_ledger_entry_is_only_an_embedded_transaction_structure() -> None:
    validator = _validator("ledger/ledger-accounting.v1.schema.json")
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    transaction = next(dto for dto in fixture["dtos"] if dto["dto_type"] == "LEDGER_TRANSACTION")
    assert not validator.is_valid(transaction["entries"][0])
    ports = (ROOT / "spec/interfaces/ledger-portfolio-ports.md").read_text(encoding="utf-8")
    assert "LedgerEntry is an embedded-only structure" in ports
