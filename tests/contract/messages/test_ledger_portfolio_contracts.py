from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from collections import defaultdict
from copy import deepcopy
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).with_name("fixtures") / "internal"
SCHEMAS = ROOT / "spec" / "contracts"
TRADE_NAMESPACE = uuid.UUID("6ea9f94d-16c3-5c7a-8c4f-ec1883388613")
REPAIR_FACT_NAMESPACE = uuid.UUID("8b7f1c2a-7c49-5b44-9dc8-5d0e11d3e760")
CASE_NAMESPACE = uuid.UUID("a679b9f2-0619-58dd-8a36-d5bb7c211540")
ZERO_CHECKSUM = "0" * 64


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _set_path(value: object, path: str, replacement: object) -> None:
    cursor = value
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]  # type: ignore[index]
    if isinstance(cursor, list):
        cursor[int(parts[-1])] = replacement
    else:
        cursor[parts[-1]] = replacement  # type: ignore[index]


def _delete_path(value: object, path: str) -> None:
    cursor = value
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]  # type: ignore[index]
    if isinstance(cursor, list):
        del cursor[int(parts[-1])]
    else:
        del cast(dict[str, object], cursor)[parts[-1]]


def _case_document(domain: str, case: dict[str, Any]) -> dict[str, Any]:
    document = deepcopy(_load(FIXTURES / f"{domain}/valid.json"))
    if "append_copy_index" in case:
        document["dtos"].append(deepcopy(document["dtos"][case["append_copy_index"]]))
    for path, replacement in case["changes"].items():
        _set_path(document, path, replacement)
    for path in case.get("remove_paths", []):
        _delete_path(document, path)
    return document


def _validator(relative_path: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / relative_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _canonical_json(value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, list):
            return [normalize(value) for value in item]
        if isinstance(item, dict):
            return {
                unicodedata.normalize("NFC", str(key)): normalize(value)
                for key, value in item.items()
            }
        return item

    return json.dumps(
        normalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


BROKER_TRADE_FINGERPRINT_FIELDS = (
    "account_id",
    "broker",
    "broker_order_id",
    "broker_sequence",
    "client_order_id",
    "commission",
    "fee",
    "instrument_id",
    "order_id",
    "position_effect",
    "price",
    "quantity",
    "received_at",
    "side",
    "tax",
    "trade_id",
    "trade_time",
    "trading_day",
)


def _source_fingerprint(trade: dict[str, Any]) -> str:
    projection = {field: trade[field] for field in BROKER_TRADE_FINGERPRINT_FIELDS}
    return hashlib.sha256(_canonical_json(projection).encode("utf-8")).hexdigest()


def _projection_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    position_fields = (
        "account_id",
        "availability_policy_version",
        "available_quantity",
        "average_cost",
        "cost_basis_method",
        "cost_basis_total",
        "currency",
        "dto_type",
        "instrument_id",
        "portfolio_version",
        "position_id",
        "position_version",
        "quantity",
        "realized_pnl",
        "schema_version",
        "scope_id",
        "side",
        "source_ledger_transaction_id",
        "source_sequence",
    )
    positions = [
        {field: position[field] for field in position_fields} for position in snapshot["positions"]
    ]
    positions.sort(key=lambda item: (item["account_id"], item["instrument_id"], item["currency"]))
    cash = sorted(snapshot["cash"], key=lambda item: item["currency"])
    return {
        "account_id": snapshot["account_id"],
        "cash": cash,
        "portfolio_id": snapshot["portfolio_id"],
        "portfolio_version": snapshot["portfolio_version"],
        "positions": positions,
        "realized_pnl": snapshot["realized_pnl"],
        "schema_version": snapshot["schema_version"],
        "scope_id": snapshot["scope_id"],
        "snapshot_currency": snapshot["snapshot_currency"],
        "source_checkpoint": snapshot["source_checkpoint"],
    }


def _projection_state_checksum(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_projection_state(snapshot)).encode("utf-8")).hexdigest()


def _repair_command_fingerprint(command: dict[str, Any]) -> str:
    evidence = command["evidence"]
    authorization = command["authorization"]
    approval = command["approval"]
    projection = {
        "actions": command["actions"],
        "approval": (
            None
            if approval is None
            else {
                field: approval[field]
                for field in (
                    "approval_id",
                    "approved_case_version",
                    "approved_evidence_id",
                    "approver_id",
                    "decision",
                    "policy_version",
                )
            }
        ),
        "authorization": {
            field: authorization[field]
            for field in (
                "authorized",
                "fencing_token",
                "policy_version",
                "principal_id",
                "role",
            )
        },
        "case_id": command["case_id"],
        "case_key": command["case_key"],
        "case_severity": command["case_severity"],
        "command_id": command["command_id"],
        "evidence": {
            field: evidence[field]
            for field in (
                "broker_sequence",
                "broker_snapshot_id",
                "case_version",
                "evidence_id",
                "internal_checkpoint",
                "internal_checksum",
                "internal_snapshot_id",
            )
        },
        "expected_case_version": command["expected_case_version"],
        "expected_portfolio_version": command["expected_portfolio_version"],
        "fencing_token": command["fencing_token"],
        "idempotency_key": command["idempotency_key"],
        "mode": command["mode"],
        "schema_version": command["schema_version"],
    }
    return hashlib.sha256(_canonical_json(projection).encode("utf-8")).hexdigest()


def _accounting_request_fingerprint(request: dict[str, Any]) -> str:
    projection = {
        field: request[field]
        for field in (
            "account_mapping_version",
            "account_id",
            "account_selections",
            "accounting_policy_version",
            "cost_basis_method",
            "currency",
            "fee_policy",
            "idempotency_key",
            "rounding_policy_version",
            "scope_id",
            "source_fingerprint",
        )
    }
    return hashlib.sha256(_canonical_json(projection).encode("utf-8")).hexdigest()


def _adjustment_identity(source: dict[str, Any]) -> str:
    identity = {
        field: source[field]
        for field in ("action_id", "case_id", "command_id", "fact_id", "fact_type")
    }
    return str(uuid.uuid5(REPAIR_FACT_NAMESPACE, _canonical_json(identity)))


def _repair_fact_checksum(source: dict[str, Any]) -> str:
    material = {key: value for key, value in source.items() if key != "repair_fact_checksum"}
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def _settlement_release_identity(request: dict[str, Any]) -> str:
    name = f"settlement:{request['trading_day']}:{request['availability_policy_version']}"
    return str(uuid.uuid5(uuid.UUID(request["position_id"]), name))


def _settlement_release_fingerprint(request: dict[str, Any]) -> str:
    projection = {
        field: request[field]
        for field in (
            "account_id",
            "availability_policy_version",
            "calendar_evidence",
            "currency",
            "expected_portfolio_version",
            "expected_position_version",
            "fencing_token",
            "idempotency_key",
            "portfolio_id",
            "position_id",
            "quantity_to_release",
            "release_id",
            "schema_version",
            "scope_id",
            "source_checkpoint",
            "trading_day",
        )
    }
    return hashlib.sha256(_canonical_json(projection).encode("utf-8")).hexdigest()


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
    account_items = [item for item in document["dtos"] if item["dto_type"] == "LEDGER_ACCOUNT"]
    accounts = {item["ledger_account_id"]: item for item in account_items}
    selection_index: dict[tuple[str, str, str, str, str | None], dict[str, Any]] = {}
    for account in account_items:
        key = (
            account["scope_id"],
            account["account_id"],
            account["currency"],
            account["account_type"],
            account["instrument_id"],
        )
        if key in selection_index:
            raise ValueError("duplicate account selection")
        selection_index[key] = account

    for request in (
        dto for dto in document["dtos"] if dto["dto_type"] == "TRADE_ACCOUNTING_REQUEST"
    ):
        if request["account_id"] != request["source_trade"]["account_id"]:
            raise ValueError("request account identity mismatch")
        fee = request["source_trade"]["fee"]
        if fee["currency"] != request["currency"]:
            raise ValueError("fee currency mismatch")
        if fee["rounding_policy_version"] != request["rounding_policy_version"]:
            raise ValueError("fee rounding policy mismatch")
        for selection in request["account_selections"]:
            if selection["account_id"] != request["account_id"]:
                raise ValueError("account selection account identity mismatch")
            selected_account = accounts.get(selection["ledger_account_id"])
            if (
                selected_account is not None
                and selected_account["account_id"] != request["account_id"]
            ):
                raise ValueError("ledger account identity mismatch")
        if request["source_fingerprint"] != _source_fingerprint(request["source_trade"]):
            raise ValueError("source fingerprint mismatch")
        fee_policy = request["fee_policy"]
        if Decimal(fee_policy["commission_amount"]) != Decimal(
            request["source_trade"]["commission"] or "0"
        ):
            raise ValueError("fee policy commission mismatch")
        if Decimal(fee_policy["tax_amount"]) != Decimal(request["source_trade"]["tax"] or "0"):
            raise ValueError("fee policy tax mismatch")
        if Decimal(fee_policy["fee_amount"]) != Decimal(fee["amount"]):
            raise ValueError("fee policy amount mismatch")
        if fee_policy["fee_currency"] != fee["currency"]:
            raise ValueError("fee policy currency mismatch")
        if fee_policy["fee_rounding_policy_version"] != fee["rounding_policy_version"]:
            raise ValueError("fee policy rounding mismatch")
        if request["request_fingerprint"] != _accounting_request_fingerprint(request):
            raise ValueError("accounting request fingerprint mismatch")
        request_keys: set[tuple[str, str, str, str, str | None]] = set()
        for selection in request["account_selections"]:
            if selection["account_id"] != request["account_id"]:
                raise ValueError("account selection account identity mismatch")
            key = (
                selection["scope_id"],
                selection["account_id"],
                selection["currency"],
                selection["account_type"],
                selection["instrument_id"],
            )
            if key in request_keys:
                raise ValueError("duplicate account selection")
            request_keys.add(key)
            account = selection_index.get(key)
            if account is None:
                raise ValueError("ledger account missing")
            if account["active"] is not True or selection["account_active"] is not True:
                raise ValueError("ledger account inactive")
            if selection["ledger_account_id"] != account["ledger_account_id"]:
                raise ValueError("account selection identity mismatch")
            if selection["account_classification"] != account["classification"]:
                raise ValueError("account classification mismatch")
            if selection["account_normal_balance"] != account["normal_balance"]:
                raise ValueError("account normal balance mismatch")

    seen_transactions: dict[str, str] = {}
    expected_sequence = 1
    previous_checksum: str | None = None
    for dto in document["dtos"]:
        if dto["dto_type"] != "LEDGER_TRANSACTION":
            continue
        if dto["transaction_kind"] == "TRADE":
            if dto["account_id"] != dto["source_trade"]["account_id"]:
                raise ValueError("transaction account identity mismatch")
            transaction_id = _trade_identity(dto["source_trade"])
            expected_fingerprint = _source_fingerprint(dto["source_trade"])
        else:
            if dto["account_id"] != dto["adjustment_source"]["account_id"]:
                raise ValueError("adjustment account identity mismatch")
            if dto["adjustment_source"]["repair_fact_checksum"] != _repair_fact_checksum(
                dto["adjustment_source"]
            ):
                raise ValueError("repair fact checksum mismatch")
            transaction_id = _adjustment_identity(dto["adjustment_source"])
            expected_fingerprint = hashlib.sha256(
                _canonical_json(dto["adjustment_source"]).encode("utf-8")
            ).hexdigest()
        if dto["transaction_id"] != transaction_id:
            raise ValueError("transaction identity mismatch")
        fingerprint = dto["source_fingerprint"]
        if fingerprint != expected_fingerprint:
            raise ValueError("source fingerprint mismatch")
        previous = seen_transactions.setdefault(transaction_id, fingerprint)
        if previous != fingerprint:
            raise ValueError("duplicate identity fingerprint conflict")
        entry_ids: set[str] = set()
        balances: defaultdict[tuple[str, str], dict[str, Decimal]] = defaultdict(
            lambda: {"DEBIT": Decimal(0), "CREDIT": Decimal(0)}
        )
        ordinals: set[int] = set()
        entry_account_types = {
            "CASH": "CASH",
            "POSITION_COST": "POSITION_COST",
            "COMMISSION": "COMMISSION_EXPENSE",
            "FEE": "FEE_EXPENSE",
            "TAX": "TAX_EXPENSE",
            "REALIZED_PNL": "REALIZED_PNL",
            "ROUNDING_RESIDUAL": "ROUNDING_RESIDUAL",
            "CAPITAL": "CAPITAL",
        }
        for entry in dto["entries"]:
            ordinal = entry["entry_ordinal"]
            if ordinal in ordinals:
                raise ValueError("duplicate entry ordinal")
            ordinals.add(ordinal)
            if entry["entry_id"] != _entry_identity(transaction_id, ordinal):
                raise ValueError("entry identity mismatch")
            if entry["entry_id"] in entry_ids:
                raise ValueError("duplicate entry identity")
            entry_ids.add(entry["entry_id"])
            account = accounts.get(entry["ledger_account_id"])
            if account is None:
                raise ValueError("ledger account missing")
            if account["active"] is not True:
                raise ValueError("ledger account inactive")
            if account["account_type"] != entry_account_types[entry["entry_type"]]:
                raise ValueError("account type mismatch")
            if account["scope_id"] != dto["scope_id"]:
                raise ValueError("account scope mismatch")
            if account["account_id"] != dto["account_id"]:
                raise ValueError("ledger account identity mismatch")
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

        if dto["transaction_kind"] != "TRADE":
            continue
        quantize = Decimal("0.01")
        trade = dto["source_trade"]
        gross = (Decimal(trade["price"]) * trade["quantity"]).quantize(
            quantize, rounding=ROUND_HALF_EVEN
        )
        commission = Decimal(trade["commission"] or "0").quantize(
            quantize, rounding=ROUND_HALF_EVEN
        )
        fee = Decimal(trade["fee"]["amount"]).quantize(quantize, rounding=ROUND_HALF_EVEN)
        tax = Decimal(trade["tax"]).quantize(quantize, rounding=ROUND_HALF_EVEN)
        sums: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for entry in dto["entries"]:
            sums[(entry["entry_type"], entry["direction"])] += Decimal(entry["amount"])
        if trade["side"] == "BUY":
            if sums[("POSITION_COST", "DEBIT")] != gross:
                raise ValueError("buy position cost formula mismatch")
            if sums[("FEE", "DEBIT")] != fee:
                raise ValueError("buy fee formula mismatch")
            if sums[("CASH", "CREDIT")] != gross + commission + fee + tax:
                raise ValueError("buy cash formula mismatch")
        else:
            released = sums[("POSITION_COST", "CREDIT")]
            trade_pnl = gross - released
            realized = sums[("REALIZED_PNL", "CREDIT")] - sums[("REALIZED_PNL", "DEBIT")]
            if realized != trade_pnl:
                raise ValueError("sell realized pnl formula mismatch")
            if sums[("FEE", "DEBIT")] != fee:
                raise ValueError("sell fee formula mismatch")
            if sums[("CASH", "DEBIT")] != gross - commission - fee - tax:
                raise ValueError("sell cash formula mismatch")


def _validate_portfolio_semantics(document: dict[str, Any]) -> None:
    release_requests = {
        dto["release_id"]: dto
        for dto in document["dtos"]
        if dto["dto_type"] == "SETTLEMENT_RELEASE_REQUEST"
    }
    release_changes: dict[str, dict[str, Any]] = {}
    for dto in document["dtos"]:
        if dto["dto_type"] == "POSITION_PROJECTION_CHANGE":
            before, after = dto["before"], dto["after"]
            if after["position_version"] != before["position_version"] + 1:
                raise ValueError("position version must increment exactly once")
            if after["portfolio_version"] != before["portfolio_version"] + 1:
                raise ValueError("portfolio version must increment exactly once")
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
            if effect["available_quantity_delta"] != (
                after["available_quantity"] - before["available_quantity"]
            ):
                raise ValueError("available quantity delta mismatch")
            if dto["source_kind"] == "TRADE":
                if after["source_sequence"] != before["source_sequence"] + 1:
                    raise ValueError("source sequence must advance contiguously")
                if dto["source_sequence"] != after["source_sequence"]:
                    raise ValueError("projection source sequence mismatch")
                if before["availability_policy_version"] == "IMMEDIATE_V1":
                    expected_available = before["available_quantity"] + effect["quantity_delta"]
                elif effect["quantity_delta"] > 0:
                    expected_available = before["available_quantity"]
                else:
                    expected_available = before["available_quantity"] + effect["quantity_delta"]
            else:
                release_id = dto["source_settlement_release_id"]
                release_changes[release_id] = dto
                if before["availability_policy_version"] != "T_PLUS_ONE_V1":
                    raise ValueError("settlement release policy mismatch")
                if effect["quantity_delta"] != 0:
                    raise ValueError("settlement release quantity changed")
                if after["source_sequence"] != before["source_sequence"]:
                    raise ValueError("settlement release advanced checkpoint")
                if dto["source_sequence"] != before["source_sequence"]:
                    raise ValueError("settlement release checkpoint mismatch")
                expected_available = (
                    before["available_quantity"] + effect["available_quantity_delta"]
                )
            if after["available_quantity"] != expected_available:
                raise ValueError("available quantity policy mismatch")
            expense = Decimal(effect["expense_total"])
            gross = Decimal(effect["gross"])
            released = Decimal(effect["released_cost"])
            trade_pnl = Decimal(effect["trade_pnl"])
            net_increment = Decimal(effect["net_realized_pnl_increment"])
            if effect["effect_type"] == "SETTLEMENT_RELEASE":
                if any(
                    value != 0 for value in (expense, gross, released, trade_pnl, net_increment)
                ):
                    raise ValueError("settlement release has monetary effect")
            elif effect["quantity_delta"] > 0:
                if released != 0 or trade_pnl != 0 or net_increment != -expense:
                    raise ValueError("realized pnl formula mismatch")
            elif trade_pnl != gross - released or net_increment != trade_pnl - expense:
                raise ValueError("realized pnl formula mismatch")
            if Decimal(after["realized_pnl"]) != Decimal(before["realized_pnl"]) + net_increment:
                raise ValueError("cumulative realized pnl mismatch")
            expected_cost = Decimal(before["cost_basis_total"])
            if effect["effect_type"] == "TRADE":
                expected_cost += gross if effect["quantity_delta"] > 0 else -released
            if Decimal(after["cost_basis_total"]) != expected_cost:
                raise ValueError("cost basis formula mismatch")
            if after["quantity"] > 0:
                expected_average = (
                    Decimal(after["cost_basis_total"]) / after["quantity"]
                ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
                if Decimal(after["average_cost"]) != expected_average:
                    raise ValueError("weighted average cost mismatch")
        elif dto["dto_type"] == "SETTLEMENT_RELEASE_REQUEST":
            if dto["release_id"] != _settlement_release_identity(dto):
                raise ValueError("settlement release identity mismatch")
            if dto["calendar_evidence"]["verification_status"] != "VERIFIED":
                raise ValueError("settlement calendar is not verified")
            if dto["calendar_evidence"]["trading_day"] != dto["trading_day"]:
                raise ValueError("settlement calendar trading day mismatch")
        elif dto["dto_type"] == "PORTFOLIO_SNAPSHOT":
            currencies = {item["currency"] for item in dto["cash"]}
            currencies.update(position["currency"] for position in dto["positions"])
            currencies.update(item["currency"] for item in dto["market_observations"])
            if currencies != {dto["snapshot_currency"]}:
                raise ValueError("mixed snapshot currency")
            if dto["projection_state_checksum"] != _projection_state_checksum(dto):
                raise ValueError("snapshot projection state checksum mismatch")
            if any(
                position["account_id"] != dto["account_id"]
                or position["scope_id"] != dto["scope_id"]
                or position["portfolio_version"] != dto["portfolio_version"]
                for position in dto["positions"]
            ):
                raise ValueError("snapshot position scope or version mismatch")
            if dto["quality"] == "COMPLETE":
                if dto["risk_usable"] is not True:
                    raise ValueError("complete snapshot must be risk usable")
                if any(position["valuation_quality"] != "FRESH" for position in dto["positions"]):
                    raise ValueError("complete snapshot requires fresh valuations")
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
            if dto["status"] == "VERIFIED":
                if (
                    dto["actual_projection_state_checksum"] is None
                    or dto["expected_projection_state_checksum"] is None
                ):
                    raise ValueError("verified replay checksum missing")
                if (
                    dto["actual_projection_state_checksum"]
                    != dto["expected_projection_state_checksum"]
                ):
                    raise ValueError("verified replay checksum mismatch")

    for release_id, request in release_requests.items():
        change = release_changes.get(release_id)
        if change is None:
            raise ValueError("settlement release projection missing")
        before, after = change["before"], change["after"]
        if request["quantity_to_release"] > before["quantity"] - before["available_quantity"]:
            raise ValueError("settlement release exceeds unavailable quantity")
        if request["expected_position_version"] != before["position_version"]:
            raise ValueError("settlement position version conflict")
        if request["expected_portfolio_version"] != before["portfolio_version"]:
            raise ValueError("settlement portfolio version conflict")
        checkpoint = request["source_checkpoint"]
        if checkpoint["last_sequence"] != before["source_sequence"]:
            raise ValueError("settlement release checkpoint mismatch")
        if request["quantity_to_release"] != change["effect"]["available_quantity_delta"]:
            raise ValueError("settlement release quantity mismatch")
        if request["request_fingerprint"] != _settlement_release_fingerprint(request):
            raise ValueError("settlement release fingerprint mismatch")
        for result in (
            dto
            for dto in document["dtos"]
            if dto["dto_type"] == "SETTLEMENT_RELEASE_RESULT" and dto["release_id"] == release_id
        ):
            if (
                result["idempotency_key"] != request["idempotency_key"]
                or result["request_fingerprint"] != request["request_fingerprint"]
                or result["source_checkpoint"] != request["source_checkpoint"]
            ):
                raise ValueError("settlement release result identity mismatch")


def _transition_pairs() -> set[tuple[str, str, str]]:
    machine = yaml.safe_load(
        (ROOT / "spec/state-machines/reconciliation-case.yaml").read_text(encoding="utf-8")
    )["machine"]
    return {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}


def _validate_reconciliation_semantics(document: dict[str, Any]) -> None:
    legal = _transition_pairs()
    seen_repairs: dict[str, str] = {}
    cases: dict[str, dict[str, Any]] = {}
    transitions: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    commands: dict[str, dict[str, Any]] = {}
    for dto in document["dtos"]:
        if dto["dto_type"] == "RECONCILIATION_CASE":
            expected_case_id = str(uuid.uuid5(CASE_NAMESPACE, _canonical_json(dto["case_key"])))
            if dto["case_id"] != expected_case_id:
                raise ValueError("reconciliation case identity mismatch")
            cases[dto["case_id"]] = dto
        elif dto["dto_type"] == "CASE_TRANSITION":
            if (dto["from_state"], dto["event"], dto["to_state"]) not in legal:
                raise ValueError("illegal reconciliation state transition")
            if dto["resulting_case_version"] != dto["expected_case_version"] + 1:
                raise ValueError("case transition version mismatch")
            transitions[dto["case_id"]].append(dto)
        elif dto["dto_type"] == "REPAIR_COMMAND":
            expected_case_id = str(uuid.uuid5(CASE_NAMESPACE, _canonical_json(dto["case_key"])))
            if dto["case_id"] != expected_case_id:
                raise ValueError("reconciliation case identity mismatch")
            if dto["requested_at"] >= dto["evidence"]["expires_at"]:
                raise ValueError("repair evidence is stale")
            if dto["expected_case_version"] != dto["evidence"]["case_version"]:
                raise ValueError("stale repair version")
            if dto["fencing_token"] != dto["authorization"]["fencing_token"]:
                raise ValueError("stale repair fencing token")
            if dto["authorization"]["authorized"] is not True:
                raise ValueError("repair is not authorized")
            if dto["case_severity"] in {"P0", "P1"} and dto["mode"] != "MANUAL":
                raise ValueError("P0/P1 automatic repair is forbidden")
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
            fingerprint = _repair_command_fingerprint(dto)
            if dto["command_fingerprint"] != fingerprint:
                raise ValueError("repair command fingerprint mismatch")
            previous = seen_repairs.setdefault(dto["idempotency_key"], fingerprint)
            if previous != fingerprint:
                raise ValueError("duplicate repair identity fingerprint conflict")
            commands[dto["command_id"]] = dto
        elif dto["dto_type"] == "REPAIR_RESULT":
            command = commands.get(dto["command_id"])
            if command is None:
                raise ValueError("repair result command missing")
            if (
                dto["idempotency_key"] != command["idempotency_key"]
                or dto["command_fingerprint"] != command["command_fingerprint"]
            ):
                raise ValueError("repair result operation identity mismatch")
            if dto["outcome"] == "UNKNOWN" and (
                dto["failure_code"] != "QQ-RECOVERY-8007"
                or dto["reconciliation_required"] is not True
            ):
                raise ValueError("unknown repair result is not fail closed")

    for case_id, case_transitions in transitions.items():
        expected_version = cases[case_id]["case_version"]
        expected_state = cases[case_id]["state"]
        for transition in case_transitions:
            if transition["expected_case_version"] != expected_version:
                raise ValueError("case transition version chain mismatch")
            if transition["from_state"] != expected_state:
                raise ValueError("case transition state chain mismatch")
            expected_version = transition["resulting_case_version"]
            expected_state = transition["to_state"]
        results = [
            dto
            for dto in document["dtos"]
            if dto["dto_type"] == "REPAIR_RESULT" and dto["case_id"] == case_id
        ]
        if results and any(result["case_version"] != expected_version for result in results):
            raise ValueError("repair result case version mismatch")


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

    assert ledger["coverage"] == [
        "BUY",
        "COMMISSION",
        "FEE",
        "TAX",
        "PARTIAL_CLOSE",
        "OUT_OF_ORDER",
        "ADJUSTMENT_FACT",
    ]
    assert portfolio["coverage"] == [
        "SECOND_BUY_WEIGHTED_AVERAGE",
        "REALIZED_PNL",
        "UNREALIZED_PNL",
        "IMMEDIATE",
        "T_PLUS_ONE_RELEASE",
        "OUT_OF_ORDER",
        "SNAPSHOT",
        "INVALID_SNAPSHOT_FALLBACK",
        "REPLAY",
    ]
    assert reconciliation["coverage"] == [
        "DIFFERENCE",
        "P1_MANUAL_APPROVAL",
        "P2_AUTOMATIC_POLICY",
        "QUANTITY_CORRECTION",
        "MONETARY_ADJUSTMENT",
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
        if expected_validator := case.get("expected_validator"):
            pending = list(errors)
            observed_validators: set[str] = set()
            while pending:
                error = pending.pop()
                observed_validators.add(error.validator)
                pending.extend(error.context)
            assert expected_validator in observed_validators, case["name"]
        else:
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


def test_projection_state_checksum_is_canonical_and_sensitive_to_scale_and_checkpoint() -> None:
    snapshot = next(
        dto
        for dto in _load(FIXTURES / "portfolio-projection.v1/valid.json")["dtos"]
        if dto["dto_type"] == "PORTFOLIO_SNAPSHOT"
    )
    assert snapshot["projection_state_checksum"] == _projection_state_checksum(snapshot)
    changed_scale = deepcopy(snapshot)
    changed_scale["cash"][0]["amount"] = "9000.0"
    assert _projection_state_checksum(changed_scale) != snapshot["projection_state_checksum"]
    changed_checkpoint = deepcopy(snapshot)
    changed_checkpoint["source_checkpoint"]["last_sequence"] += 1
    assert _projection_state_checksum(changed_checkpoint) != snapshot["projection_state_checksum"]


def test_identity_algorithms_are_deterministic_and_namespaced() -> None:
    ledger = _load(FIXTURES / "ledger-accounting.v1/valid.json")
    transaction = next(
        dto
        for dto in ledger["dtos"]
        if dto["dto_type"] == "LEDGER_TRANSACTION" and dto["transaction_kind"] == "TRADE"
    )
    assert transaction["transaction_id"] == _trade_identity(transaction["source_trade"])
    assert [entry["entry_id"] for entry in transaction["entries"]] == [
        _entry_identity(transaction["transaction_id"], entry["entry_ordinal"])
        for entry in transaction["entries"]
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
    assert "additive optional fee" in change["public_message_schema_changes"]
    assert "historical unbound input" in change["public_message_schema_changes"]
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
        "QQ-STORAGE-7011",
        "QQ-STORAGE-7012",
        "QQ-STORAGE-7013",
        "QQ-STORAGE-7014",
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
