"""Immutable identifiers shared by all bounded contexts."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$", re.ASCII)


@dataclass(frozen=True, slots=True)
class Identifier:
    """Canonical internal UUID identifier.

    New identifiers are UUID4. Construction accepts canonical UUID text so
    persisted identifiers can be restored without coupling to a generator.
    """

    value: str

    def __post_init__(self) -> None:
        try:
            parsed = uuid.UUID(self.value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("identifier must be a valid UUID") from exc
        if str(parsed) != self.value:
            raise ValueError("identifier must be a canonical lowercase UUID")

    @classmethod
    def new(cls) -> Identifier:
        """Generate a new UUID4 identifier."""
        return cls(str(uuid.uuid4()))

    @property
    def version(self) -> int | None:
        """Return the UUID version."""
        return uuid.UUID(self.value).version

    def to_primitive(self) -> str:
        """Return the stable JSON-compatible representation."""
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Opaque, normalized identifier from the reference-data context."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("instrument id must be a string")
        if not 1 <= len(self.value) <= 64:
            raise ValueError("instrument id length must be between 1 and 64")
        if self.value != self.value.strip():
            raise ValueError("instrument id must not contain surrounding whitespace")

    def to_primitive(self) -> str:
        """Return the stable JSON-compatible representation."""
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Currency:
    """ISO-4217-style uppercase currency code."""

    code: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str):
            raise TypeError("currency must be a string")
        if _CURRENCY_PATTERN.fullmatch(self.code) is None:
            raise ValueError("currency must be three uppercase ASCII letters")

    def to_primitive(self) -> str:
        """Return the stable JSON-compatible representation."""
        return self.code

    def __str__(self) -> str:
        return self.code
