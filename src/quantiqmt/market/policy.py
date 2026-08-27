"""Immutable checksum-bound Market validation policy authority."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any, cast

from quantiqmt.contracts.tzdb import FrozenTzdb
from quantiqmt.market.errors import IdentityCollisionError, MarketContractError
from quantiqmt.market.validation import (
    POLICY_PROJECTION,
    projection_checksum,
    validate_policy_shape,
)


class AcceptedPolicyStore:
    """In-memory view of a reviewed immutable configuration authority."""

    def __init__(self, tzdb: FrozenTzdb | None = None) -> None:
        self._policies: dict[str, Mapping[str, object]] = {}
        self._tzdb = tzdb or FrozenTzdb.installed()

    @staticmethod
    def refresh_checksum(policy: MutableMapping[str, object]) -> None:
        policy["policy_checksum"] = projection_checksum(policy, POLICY_PROJECTION)

    def activate(self, policy: Mapping[str, object]) -> None:
        validate_policy_shape(policy)
        if policy["tzdb_version"] != self._tzdb.version:
            raise MarketContractError("policy tzdb version is unavailable")
        version = cast(str, policy["policy_version"])
        frozen = _freeze_mapping(deepcopy(dict(policy)))
        existing = self._policies.get(version)
        if existing is not None:
            if existing["policy_checksum"] != frozen["policy_checksum"]:
                raise IdentityCollisionError("policy version checksum collision")
            return
        self._policies[version] = frozen

    def get(self, version: str) -> Mapping[str, object]:
        try:
            policy = self._policies[version]
        except KeyError as exc:
            raise MarketContractError(f"accepted Market policy is missing: {version}") from exc
        validate_policy_shape(policy)
        return policy

    def resolve(self, request: Mapping[str, object]) -> Mapping[str, object]:
        version = request.get("policy_version")
        if not isinstance(version, str):
            raise MarketContractError("request policy_version is missing")
        policy = self.get(version)
        for field in ("provider", "generation", "calendar_id", "calendar_version", "session_id"):
            if request.get(field) != policy.get(field):
                raise MarketContractError("request does not bind the accepted policy identity")
        return policy

    def resolve_snapshot(self, request: Mapping[str, object]) -> Mapping[str, object]:
        aggregation_version = request.get("aggregation_policy_version")
        candidates = [
            policy
            for policy in self._policies.values()
            if policy.get("aggregation_policy_version") == aggregation_version
        ]
        if len(candidates) != 1:
            raise MarketContractError("accepted Snapshot policy is missing or ambiguous")
        policy = candidates[0]
        for field in ("provider", "generation", "calendar_id", "calendar_version", "session_id"):
            if request.get(field) != policy.get(field):
                raise MarketContractError("Snapshot does not bind the accepted policy identity")
        return policy


def _freeze_mapping(value: dict[str, Any]) -> Mapping[str, object]:
    def freeze(item: Any) -> object:
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        return cast(object, item)

    return cast(Mapping[str, object], freeze(value))
