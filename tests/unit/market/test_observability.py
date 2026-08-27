from __future__ import annotations

import pytest

from quantiqmt.market.observability import NullMarketObserver


def test_market_metrics_reject_high_cardinality_labels() -> None:
    observer = NullMarketObserver()
    observer.increment("market_gap_total", {"provider": "SIM", "reason": "SOURCE_SEQUENCE_GAP"})
    with pytest.raises(ValueError, match="high-cardinality"):
        observer.increment("market_gap_total", {"provider": "SIM", "instrument_id": "x"})
