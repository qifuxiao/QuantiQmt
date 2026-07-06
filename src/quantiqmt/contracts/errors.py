"""Message contract boundary errors."""


class ContractError(ValueError):
    """Base class for deterministic contract failures."""


class UnknownMessageTypeError(ContractError):
    """Raised when no approved contract exists for a message type."""


class UnsupportedSchemaVersionError(ContractError):
    """Raised when a message requests an unsupported schema version."""


class ContractValidationError(ContractError):
    """Raised when an envelope or payload violates its JSON Schema."""
