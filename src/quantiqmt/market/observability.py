"""Low-cardinality Market observability boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

PROHIBITED_LABELS = frozenset(
    {
        "instrument_id",
        "message_id",
        "correlation_id",
        "order_id",
        "account_id",
        "subscription_id",
    }
)


class MarketObserver(Protocol):
    def increment(self, metric: str, labels: Mapping[str, str]) -> None: ...
    def observe(self, metric: str, value: int | float, labels: Mapping[str, str]) -> None: ...


class NullMarketObserver:
    """Non-blocking default observer for the pure adapter-neutral core."""

    def increment(self, metric: str, labels: Mapping[str, str]) -> None:
        del metric
        _validate_labels(labels)

    def observe(self, metric: str, value: int | float, labels: Mapping[str, str]) -> None:
        del metric, value
        _validate_labels(labels)


def _validate_labels(labels: Mapping[str, str]) -> None:
    forbidden = set(labels) & PROHIBITED_LABELS
    if forbidden:
        raise ValueError(
            f"high-cardinality Market metric labels are forbidden: {sorted(forbidden)}"
        )
