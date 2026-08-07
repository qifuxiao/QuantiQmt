from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from copy import deepcopy
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).with_name("fixtures") / "internal"
SCHEMAS = ROOT / "spec" / "contracts"
TRADE_NAMESPACE = uuid.UUID("6ea9f94d-16c3-5c7a-8c4f-ec1883388613")
CASE_NAMESPACE = uuid.UUID("a679b9f2-0619-58dd-8a36-d5bb7c211540")
ZERO_CHECKSUM = "0" * 64


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _set_path(value: object, path: str, replacement: object) -> None:
    cursor = value
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]  # type: ignore[index]
    if isinstance(cursor, list):
        cursor[int(parts[-1])] = replacement
    else:
        cursor[parts[-1]] = replacement  # type: ignore[index]


def _case_document(domain: str, case: dict[str, Any]) -> dict[str, Any]:
    document = deepcopy(_load(FIXTURES / f"{domain}/valid.json"))
    if "append_copy_index" in case:
        document["dtos"].append(deepcopy(document["dtos"][case["append_copy_index"]]))
    for path, replacement in case["changes"].items():
        _set_path(document, path, replacement)
    return document


def _validator(relative_path: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _checksum(value: dict[str, Any], field: str = "checksum") -> str:
    material = {key: item for key, item in value.items() if key != field}
    return hashlib.sha256(_canonical_json(material).encode()).hexdigest()


def _trade_identity(trade: dict[str, Any]) -> str:
    identity = {
        "account_id": trade["account_id"],
        "broker": trade["broker"],
        "trade_id": trade["trade_id"],
        "trading_day": trade["trading_day"],
    }
    return str(uuid.uuid5(TRADE_NAMESPACE, _canonical_json(identity)))


def _entry_identity(transaction_id: str, ordinal: int) -> str:
    return str(uuid.uuid5(uuid.UUID(transaction_id), f"entry:{ordinal}"))


def _ledger_checksum(transaction: dict[str, Any]) -> str:
    previous = transaction["previous_transaction_checksum"] or ZERO_CHECKSUM
    material = {key: item for key, item in transaction.items() if key != "transaction_checksum"}
    serialized = previous + "\n" + _canonical_json(material)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _validate_ledger_semantics(document: dict[str, Any]) -> None:
    accounts = {
        item["ledger_account_id"]: item
        for item in document["dtos"]
        if item["dto_type"] == "LEDGER_ACCOUNT"
    }
    seen_transactions: dict[str, str] = {}
    expected_sequence = 1
    previous_checksum: str | None = None
    for dto in document["dtos"]:
        if dto["dto_type"] != "LEDGER_TRANSACTION":
            continue
        transaction_id = _trade_identity(dto["source_trade"])
        if dto["transaction_id"] != transaction_id:
            raise ValueError("transaction identity mismatch")
        fingerprint = dto["source_fingerprint"]
        expected_fingerprint = hashlib.sha256(
            _canonical_json(dto["source_trade"]).encode()
        ).hexdigest()
        if fingerprint != expected_fingerprint:
            raise ValueError("source fingerprint mismatch")
        previous = seen_transactions.setdefault(transaction_id, fingerprint)
        if previous != fingerprint:
            raise ValueError("duplicate identity fingerprint conflict")
        entry_ids: set[str] = set()
        balances: defaultdict[tuple[str, str], dict[str, Decimal]] = defaultdict(
            lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
        )
        for ordinal, entry in enumerate(dto["entries"]):
            if entry["entry_id"] != _entry_identity(transaction_id, ordinal):
                raise ValueError("entry identity mismatch")
            if entry["entry_id"] in entry_ids:
                raise ValueError("duplicate entry identity")
            entry_ids.add(entry["entry_id"])
            account = accounts.get(entry["ledger_account_id"])
            if account is None:
                raise ValueError("ledger account missing")
            if account["scope_id"] != dto["scope_id"]:
                raise ValueError("account scope mismatch")
            if account["currency"] != entry["currency"]:
                raise ValueError("entry currency mismatch")
            if entry["currency"] != dto["currency"]:
                raise ValueError("transaction currency mismatch")
            if account["instrument_id"] != entry["instrument_id"]:
                raise ValueError("entry instrument mismatch")
            balances[(dto["scope_id"], entry["currency"])][entry["direction"]] += Decimal(
                entry["amount"]
            )
        if any(totals["DEBIT"] != totals["CREDIT"] for totals in balances.values()):
            raise ValueError("ledger transaction is unbalanced")
        if dto["ledger_sequence"] != expected_sequence:
            raise ValueError("ledger sequence is not contiguous")
        if dto["previous_transaction_checksum"] != previous_checksum:
            raise ValueError("ledger checksum chain mismatch")
        if dto["transaction_checksum"] != _ledger_checksum(dto):
            raise ValueError("ledger transaction checksum mismatch")
        expected_sequence += 1
        previous_checksum = dto["transaction_checksum"]

        quantize = Decimal("0.01")
        trade = dto["source_trade"]
        gross = (Decimal(trade["price"]) * trade["quantity"]).quantize(
            quantize, rounding=ROUND_HALF_EVEN
        )
        commission = Decimal(trade["commission"]).quantize(quantize, rounding=ROUND_HALF_EVEN)
        tax = Decimal(trade["tax"]).quantize(quantize, rounding=ROUND_HALF_EVEN)
        sums: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for entry in dto["entries"]:
            sums[(entry["entry_type"], entry["direction"])] += Decimal(entry["amount"])
        if trade["side"] == "BUY":
            if sums[("POSITION_COST", "DEBIT")] != gross:
                raise ValueError("buy position cost formula mismatch")
            if sums[("CASH", "CREDIT")] != gross + commission + tax:
                raise ValueError("buy cash formula mismatch")
        else:
            released = sums[("POSITION_COST", "CREDIT")]
            trade_pnl = gross - released
            realized = sums[("REALIZED_PNL", "CREDIT")] - sums[("REALIZED_PNL", "DEBIT")]
            if realized != trade_pnl:
                raise ValueError("sell realized pnl formula mismatch")
            if sums[("CASH", "DEBIT")] != gross - commission - tax:
                raise ValueError("sell cash formula mismatch")


def _validate_portfolio_semantics(document: dict[str, Any]) -> None:
    for dto in document["dtos"]:
        if dto["dto_type"] == "POSITION_PROJECTION_CHANGE":
            before, after = dto["before"], dto["after"]
            if after["position_version"] != before["position_version"] + 1:
                raise ValueError("position version must increment exactly once")
            if after["source_sequence"] <= before["source_sequence"]:
                raise ValueError("source sequence must advance")
            if after["quantity"] < after["available_quantity"]:
                raise ValueError("available quantity exceeds position")
            if after["availability_policy_version"] != before["availability_policy_version"]:
                raise ValueError("availability policy changed in place")
            expected_side = "FLAT" if after["quantity"] == 0 else "LONG"
            if after["side"] != expected_side:
                raise ValueError("position side disagrees with quantity")
            effect = dto["effect"]
            if effect["quantity_delta"] != after["quantity"] - before["quantity"]:
                raise ValueError("quantity delta mismatch")
            if before["availability_policy_version"] == "IMMEDIATE_V1":
                expected_available = before["available_quantity"] + effect["quantity_delta"]
            elif effect["quantity_delta"] > 0:
                expected_available = before["available_quantity"]
            else:
                expected_available = before["available_quantity"] + effect["quantity_delta"]
            if after["available_quantity"] != expected_available:
                raise ValueError("available quantity policy mismatch")
            expense = Decimal(effect["expense_total"])
            gross = Decimal(effect["gross"])
            released = Decimal(effect["released_cost"])
            trade_pnl = Decimal(effect["trade_pnl"])
            net_increment = Decimal(effect["net_realized_pnl_increment"])
            if effect["quantity_delta"] > 0:
                if released != 0 or trade_pnl != 0 or net_increment != -expense:
                    raise ValueError("realized pnl formula mismatch")
            elif trade_pnl != gross - released or net_increment != trade_pnl - expense:
                raise ValueError("realized pnl formula mismatch")
            if Decimal(after["realized_pnl"]) != Decimal(before["realized_pnl"]) + net_increment:
                raise ValueError("cumulative realized pnl mismatch")
            expected_cost = Decimal(before["cost_basis_total"])
            expected_cost += gross if effect["quantity_delta"] > 0 else -released
            if Decimal(after["cost_basis_total"]) != expected_cost:
                raise ValueError("cost basis formula mismatch")
        elif dto["dto_type"] == "PORTFOLIO_SNAPSHOT":
            if dto["checksum"] != _checksum(dto):
                raise ValueError("snapshot checksum mismatch")
            if dto["quality"] == "COMPLETE":
                if dto["risk_usable"] is not True:
                    raise ValueError("complete snapshot must be risk usable")
                if any(position["market_value"] is None for position in dto["positions"]):
                    raise ValueError("complete snapshot requires valuations")
            elif dto["risk_usable"] is not False:
                raise ValueError("degraded snapshot cannot increase risk")
            if dto["market_value"] is not None:
                expected_market = sum(
                    (Decimal(position["market_value"]) for position in dto["positions"]),
                    Decimal(0),
                )
                if Decimal(dto["market_value"]) != expected_market:
                    raise ValueError("snapshot market value mismatch")
                cash = sum((Decimal(item["amount"]) for item in dto["cash"]), Decimal(0))
                if Decimal(dto["total_equity"]) != cash + expected_market:
                    raise ValueError("snapshot equity formula mismatch")
        elif dto["dto_type"] == "REPLAY_RESULT":
            if dto["status"] == "VERIFIED" and dto["actual_checksum"] != dto["expected_checksum"]:
                raise ValueError("verified replay checksum mismatch")


def _transition_pairs() -> set[tuple[str, str, str]]:
    machine = yaml.safe_load(
        (ROOT / "spec/state-machines/reconciliation-case.yaml").read_text(encoding="utf-8")
    )["machine"]
    return {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}


def _validate_reconciliation_semantics(document: dict[str, Any]) -> None:
    legal = _transition_pairs()
    seen_repairs: dict[str, str] = {}
    for dto in document["dtos"]:
        if dto["dto_type"] == "RECONCILIATION_CASE":
            expected_case_id = str(uuid.uuid5(CASE_NAMESPACE, _canonical_json(dto["case_key"])))
            if dto["case_id"] != expected_case_id:
                raise ValueError("reconciliation case identity mismatch")
        elif dto["dto_type"] == "CASE_TRANSITION":
            if (dto["from_state"], dto["event"], dto["to_state"]) not in legal:
                raise ValueError("illegal reconciliation state transition")
        elif dto["dto_type"] == "REPAIR_COMMAND":
            expected_case_id = str(uuid.uuid5(CASE_NAMESPACE, _canonical_json(dto["case_key"])))
            if dto["case_id"] != expected_case_id:
                raise ValueError("reconciliation case identity mismatch")
            fingerprint = hashlib.sha256(_canonical_json(dto).encode()).hexdigest()
            previous = seen_repairs.setdefault(dto["idempotency_key"], fingerprint)
            if previous != fingerprint:
                raise ValueError("duplicate repair identity fingerprint conflict")
            if dto["requested_at"] >= dto["evidence"]["expires_at"]:
                raise ValueError("repair evidence is stale")
            if dto["expected_case_version"] != dto["evidence"]["case_version"]:
                raise ValueError("stale repair version")
            if dto["fencing_token"] != dto["authorization"]["fencing_token"]:
                raise ValueError("stale repair fencing token")
            if dto["authorization"]["authorized"] is not True:
                raise ValueError("repair is not authorized")
            if dto["mode"] == "MANUAL" and dto["approval"] is None:
                raise ValueError("manual repair requires approval")
            approval = dto["approval"]
            if approval is not None and (
                approval["approved_case_version"] != dto["expected_case_version"]
                or approval["approved_evidence_id"] != dto["evidence"]["evidence_id"]
                or approval["policy_version"] != dto["authorization"]["policy_version"]
            ):
                raise ValueError("repair approval binding mismatch")
            if any(
                action["operation"] not in {"APPEND_ADJUSTMENT", "APPEND_COMPENSATING_FACT"}
                for action in dto["actions"]
            ):
                raise ValueError("repair may only append facts")
            for action in dto["actions"]:
                balances: defaultdict[str, dict[str, Decimal]] = defaultdict(
                    lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
                )
                for entry in action["payload"]["entries"]:
                    balances[entry["currency"]][entry["direction"]] += Decimal(entry["amount"])
                if any(value["DEBIT"] != value["CREDIT"] for value in balances.values()):
                    raise ValueError("repair adjustment is unbalanced")


@pytest.mark.parametrize(
    ("schema_path", "fixture_path"),
    [
        ("ledger/ledger-accounting.v1.schema.json", "ledger-accounting.v1/valid.json"),
        ("portfolio/portfolio-projection.v1.schema.json", "portfolio-projection.v1/valid.json"),
        ("reconciliation/reconciliation.v1.schema.json", "reconciliation.v1/valid.json"),
    ],
)
def test_internal_contract_fixtures_are_schema_valid(schema_path: str, fixture_path: str) -> None:
    validator = _validator(schema_path)
    fixture = _load(FIXTURES / fixture_path)
    for dto in fixture["dtos"]:
        validator.validate(dto)


def test_valid_fixtures_cover_trade_fees_tax_partial_close_pnl_snapshot_and_repair() -> None:
    ledger = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    portfolio = _load(FIXTURES / "portfolio-projection.v1/valid.json")
    reconciliation = _load(FIXTURES / "reconciliation.v1/valid.json")

    _validate_ledger_semantics(ledger)
    _validate_portfolio_semantics(portfolio)
    _validate_reconciliation_semantics(reconciliation)

    assert ledger["coverage"] == ["BUY", "COMMISSION", "TAX", "PARTIAL_CLOSE"]
    assert portfolio["coverage"] == [
        "WEIGHTED_AVERAGE_COST",
        "REALIZED_PNL",
        "UNREALIZED_PNL",
        "FLAT",
        "SNAPSHOT",
        "REPLAY",
    ]
    assert reconciliation["coverage"] == [
        "DIFFERENCE",
        "APPROVAL",
        "APPEND_ONLY_REPAIR",
        "AUDIT",
        "UNKNOWN",
    ]


@pytest.mark.parametrize(
    ("domain", "validator"),
    [
        ("ledger-accounting.v1", _validate_ledger_semantics),
        ("portfolio-projection.v1", _validate_portfolio_semantics),
        ("reconciliation.v1", _validate_reconciliation_semantics),
    ],
)
def test_semantic_negative_matrix_has_one_machine_reason_per_complete_case(
    domain: str, validator: Any
) -> None:
    fixture = _load(FIXTURES / f"{domain}/semantic-invalid.json")
    schema_name = {
        "ledger-accounting.v1": "ledger/ledger-accounting.v1.schema.json",
        "portfolio-projection.v1": "portfolio/portfolio-projection.v1.schema.json",
        "reconciliation.v1": "reconciliation/reconciliation.v1.schema.json",
    }[domain]
    schema = _validator(schema_name)
    for case in fixture["cases"]:
        document = _case_document(domain, case)
        for dto in document["dtos"]:
            schema.validate(dto)
        with pytest.raises(ValueError, match=case["error_match"]):
            validator(document)


@pytest.mark.parametrize(
    ("domain", "schema_name"),
    [
        ("ledger-accounting.v1", "ledger/ledger-accounting.v1.schema.json"),
        ("portfolio-projection.v1", "portfolio/portfolio-projection.v1.schema.json"),
        ("reconciliation.v1", "reconciliation/reconciliation.v1.schema.json"),
    ],
)
def test_schema_negative_matrix_rejects_target_without_missing_field_masking(
    domain: str, schema_name: str
) -> None:
    validator = _validator(schema_name)
    fixture = _load(FIXTURES / f"{domain}/schema-invalid.json")
    for case in fixture["cases"]:
        document = _case_document(domain, case)
        errors = list(validator.iter_errors(document["dtos"][case["dto_index"]]))
        assert errors, case["name"]
        assert all(error.validator != "required" for error in errors), case["name"]


def test_required_failure_matrix_is_exhaustive() -> None:
    cases: set[str] = set()
    for path in FIXTURES.glob("*/semantic-invalid.json"):
        cases.update(case["name"] for case in _load(path)["cases"])
    for path in FIXTURES.glob("*/schema-invalid.json"):
        cases.update(case["name"] for case in _load(path)["cases"])
    assert {
        "unbalanced_transaction",
        "float_amount",
        "currency_mismatch",
        "duplicate_identity_conflict",
        "illegal_debit_credit",
        "position_version_regression",
        "invalid_snapshot_checksum",
        "illegal_reconciliation_transition",
        "unauthorized_repair",
        "repair_overwrites_history",
        "stale_fencing_version",
    } <= cases


def test_public_ledger_and_position_events_keep_decimal_strings() -> None:
    ledger = _load(SCHEMAS / "events/ledger.trade_posted.v1.schema.json")
    position = _load(SCHEMAS / "events/portfolio.position_changed.v1.schema.json")
    assert ledger["properties"]["price"]["type"] == "string"
    assert ledger["properties"]["entries"]["items"]["properties"]["amount"]["type"] == "string"
    assert position["properties"]["average_cost"]["type"] == ["string", "null"]


def test_snapshot_checksum_is_canonical_and_sensitive_to_scale_and_checkpoint() -> None:
    snapshot = next(
        dto
        for dto in _load(FIXTURES / "portfolio-projection.v1/valid.json")["dtos"]
        if dto["dto_type"] == "PORTFOLIO_SNAPSHOT"
    )
    assert snapshot["checksum"] == _checksum(snapshot)
    changed_scale = deepcopy(snapshot)
    changed_scale["cash"][0]["amount"] = "9000.0"
    assert _checksum(changed_scale) != snapshot["checksum"]
    changed_checkpoint = deepcopy(snapshot)
    changed_checkpoint["source_checkpoint"]["last_sequence"] += 1
    assert _checksum(changed_checkpoint) != snapshot["checksum"]


def test_identity_algorithms_are_deterministic_and_namespaced() -> None:
    ledger = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    transaction = next(dto for dto in ledger["dtos"] if dto["dto_type"] == "LEDGER_TRANSACTION")
    assert transaction["transaction_id"] == _trade_identity(transaction["source_trade"])
    assert [entry["entry_id"] for entry in transaction["entries"]] == [
        _entry_identity(transaction["transaction_id"], ordinal)
        for ordinal in range(len(transaction["entries"]))
    ]
    assert ZERO_CHECKSUM == "0" * 64


def test_manifest_catalogs_every_new_contract_and_defers_runtime_migration() -> None:
    manifest = yaml.safe_load((ROOT / "spec/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["specification"]["version"] == "0.9.0"
    ids = {entry["id"] for entries in manifest["catalogs"].values() for entry in entries}
    assert {
        "CONTRACT-LEDGER-ACCOUNTING-V1",
        "CONTRACT-PORTFOLIO-PROJECTION-V1",
        "CONTRACT-RECONCILIATION-V1",
        "PORTS-LEDGER-PORTFOLIO",
        "REPO-LEDGER-PORTFOLIO",
        "STORAGE-LEDGER-PORTFOLIO",
        "WF-RECONCILIATION-REPAIR",
    } <= ids
    change = manifest["change"]
    assert change["public_message_schema_changes"] == "none"
    assert "no migration" in change["storage_schema_changes"]
    assert change["rollback"]["release"] == "prohibited"


def test_account_classification_fixes_normal_balance_and_position_scope() -> None:
    validator = _validator("ledger/ledger-accounting.v1.schema.json")
    fixture = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    cash = deepcopy(fixture["dtos"][0])
    cash["normal_balance"] = "CREDIT"
    assert not validator.is_valid(cash)
    position = deepcopy(fixture["dtos"][1])
    position["instrument_id"] = None
    assert not validator.is_valid(position)


def test_storage_and_workflows_freeze_append_only_atomic_fail_closed_rules() -> None:
    storage = yaml.safe_load(
        (ROOT / "spec/storage/ledger-portfolio.yaml").read_text(encoding="utf-8")
    )["storage"]
    assert storage["tables"]["ledger_transactions"]["append_only"] is True
    assert storage["tables"]["ledger_entries"]["mutation"] == ["INSERT"]
    assert storage["transaction_rules"]["atomic"] is True
    assert storage["transaction_rules"]["partial_commit"] == "forbidden"
    assert storage["recovery"]["snapshot_invalid_or_incompatible"] == (
        "discard_for_attempt_then_full_ledger_replay"
    )

    trade = yaml.safe_load(
        (ROOT / "spec/workflows/trade-accounting.yaml").read_text(encoding="utf-8")
    )["workflow"]
    assert trade["posting"]["sell"][-1] == "post_trade_pnl_directionally"
    assert trade["retry"]["commit_unknown"] == ("query_same_identity_never_generate_replacement")
    repair = yaml.safe_load(
        (ROOT / "spec/workflows/reconciliation-repair.yaml").read_text(encoding="utf-8")
    )["workflow"]
    assert repair["allowed_actions"] == ["APPEND_ADJUSTMENT", "APPEND_COMPENSATING_FACT"]
    assert repair["unknown_outcome"]["blind_retry"] == "forbidden"


def test_error_catalog_exposes_every_new_fail_closed_reason() -> None:
    catalog = yaml.safe_load(
        (ROOT / "spec/contracts/errors/catalog.yaml").read_text(encoding="utf-8")
    )
    codes = {entry["code"] for entry in catalog["errors"]}
    assert {
        "QQ-STORAGE-7007",
        "QQ-STORAGE-7008",
        "QQ-STORAGE-7009",
        "QQ-STORAGE-7010",
        "QQ-RECOVERY-8003",
        "QQ-RECOVERY-8004",
        "QQ-RECOVERY-8005",
        "QQ-RECOVERY-8006",
        "QQ-RECOVERY-8007",
    } <= codes
    assert catalog["compatibility"]["existing_code_meanings_changed"] is False


def test_task_007_remains_blocked_and_can_only_implement_frozen_contracts() -> None:
    task = (ROOT / "tasks/backlog/TASK-007-ledger-portfolio.md").read_text(encoding="utf-8")
    front_matter = yaml.safe_load(task.split("---", 2)[1])
    assert front_matter["status"] == "blocked"
    assert front_matter["depends_on"] == ["TASK-004", "TASK-006", "TASK-018"]
    assert {
        "CONTRACT-LEDGER-ACCOUNTING-V1",
        "CONTRACT-PORTFOLIO-PROJECTION-V1",
        "CONTRACT-RECONCILIATION-V1",
        "PORTS-LEDGER-PORTFOLIO",
        "REPO-LEDGER-PORTFOLIO",
        "STORAGE-LEDGER-PORTFOLIO",
    } <= set(front_matter["spec_refs"])
    assert "不得自行发明或改变账户分类" in task
    assert "Repair 只能追加 adjustment/compensating facts" in task
