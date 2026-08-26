from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantiqmt.contracts import SchemaRegistry
from quantiqmt.contracts.validation import validate
from quantiqmt.market.errors import IdentityCollisionError, MarketContractError
from quantiqmt.market.policy import AcceptedPolicyStore
from quantiqmt.market.validation import (
    validate_health_exchange,
    validate_snapshot_exchange,
    validate_trading_calendar,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/contract/messages/fixtures/internal/market-data.v1"


def document() -> dict[str, object]:
    return json.loads((FIXTURE / "valid.json").read_text(encoding="utf-8"))


def by_type() -> dict[str, dict[str, object]]:
    return {dto["dto_type"]: dto for dto in document()["dtos"]}  # type: ignore[index,union-attr]


def policy() -> dict[str, object]:
    return json.loads((FIXTURE / "validation-policy.valid.json").read_text(encoding="utf-8"))


def test_every_frozen_market_dto_is_validated_from_installed_bundle() -> None:
    schema = SchemaRegistry().contract("CONTRACT-MARKET-DATA-V1")
    for dto in document()["dtos"]:  # type: ignore[index,union-attr]
        validate(dto, schema)


def test_snapshot_and_health_recompute_authoritative_policy_evidence() -> None:
    values = by_type()
    accepted = policy()
    validate_snapshot_exchange(
        values["SNAPSHOT_REQUEST"],
        values["SNAPSHOT_RESULT"],
        accepted,
        datetime(2026, 8, 11, 1, 30, 0, 500_000, tzinfo=UTC),
    )
    validate_health_exchange(
        values["HEALTH_REQUEST"],
        values["MARKET_HEALTH"],
        accepted,
        datetime(2026, 8, 11, 1, 30, tzinfo=UTC),
    )

    false_health = deepcopy(values["MARKET_HEALTH"])
    false_health["warning_watermark"] = 900
    with pytest.raises(MarketContractError, match="threshold mismatch"):
        validate_health_exchange(
            values["HEALTH_REQUEST"],
            false_health,
            accepted,
            datetime(2026, 8, 11, 1, 30, tzinfo=UTC),
        )


def test_policy_version_checksum_collision_and_stale_snapshot_fail_closed() -> None:
    store = AcceptedPolicyStore()
    accepted = policy()
    store.activate(accepted)
    changed = deepcopy(accepted)
    changed["snapshot_max_age_ms"] = 2000
    AcceptedPolicyStore.refresh_checksum(changed)
    with pytest.raises(IdentityCollisionError):
        store.activate(changed)

    values = by_type()
    with pytest.raises(MarketContractError, match=r"stale evidence mismatch|not trade-safe"):
        validate_snapshot_exchange(
            values["SNAPSHOT_REQUEST"],
            values["SNAPSHOT_RESULT"],
            accepted,
            datetime(2026, 8, 11, 1, 30, 2, tzinfo=UTC),
        )


def test_trading_calendar_is_checksum_tzdb_fold_and_offset_bound() -> None:
    calendar = by_type()["TRADING_CALENDAR"]
    validate_trading_calendar(calendar)

    tampered = deepcopy(calendar)
    tampered["sessions"][0]["open_utc_offset_seconds"] = "0"  # type: ignore[index]
    with pytest.raises(MarketContractError, match=r"checksum|offset"):
        validate_trading_calendar(tampered)
