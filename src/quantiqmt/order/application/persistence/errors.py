"""Canonical storage/recovery errors for the Order persistence boundary."""

from __future__ import annotations


class PersistenceError(RuntimeError):
    """Base error carrying a stable catalog code."""

    code: str

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


class IdempotencyConflict(PersistenceError):
    code = "QQ-STORAGE-7001"


class JournalCommitFailed(PersistenceError):
    code = "QQ-STORAGE-7002"


class SnapshotInvalid(PersistenceError):
    code = "QQ-STORAGE-7003"


class OutboxClaimLost(PersistenceError):
    code = "QQ-STORAGE-7004"


class UniqueIdentifierCollision(PersistenceError):
    code = "QQ-STORAGE-7006"


class OrderJournalCorrupted(PersistenceError):
    code = "QQ-RECOVERY-8002"
