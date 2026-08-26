"""Fail-closed Market contract errors."""


class MarketContractError(ValueError):
    """A Market DTO or semantic invariant is invalid."""


class IdentityCollisionError(MarketContractError):
    """The same immutable identity was reused with different canonical content."""


class LateFinalizedDataError(MarketContractError):
    """A tick attempted to mutate an already-final bar."""

    def __init__(self, sequence: int) -> None:
        self.gap_start_sequence = sequence
        self.gap_end_sequence = sequence
        super().__init__(f"late data after final bar at source sequence {sequence}")
