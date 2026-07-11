"""Runtime-checkable Protocols for Order persistence ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol, runtime_checkable

from quantiqmt.order.application.persistence.model import (
    ClaimedMessage,
    ClaimPolicy,
    ClientOrderIdCandidate,
    JsonValue,
    OrderCommit,
    OrderRegistrationDraft,
    OrderSnapshot,
    OutboxMutationResult,
    PersistedOrder,
    PublishFailure,
    RecoveryLoad,
    RecoveryPage,
    RegisterOutcome,
    SnapshotLookup,
)
from quantiqmt.shared import Identifier


@runtime_checkable
class OrderRepository(Protocol):
    def register(self, commit: OrderCommit, *, deadline_monotonic_ns: int) -> RegisterOutcome: ...
    def get(self, order_id: Identifier, *, deadline_monotonic_ns: int) -> PersistedOrder | None: ...
    def get_by_intent(
        self, intent_id: Identifier, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None: ...
    def get_by_client_order_id(
        self, client_order_id: str, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None: ...
    def save(
        self,
        commit: OrderCommit,
        *,
        expected_version: int,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder: ...
    def load_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> RecoveryLoad: ...
    def list_recovery_order_ids(
        self,
        *,
        scope: Literal["ALL", "ACTIVE_OR_UNKNOWN"],
        page_size: int,
        page_token: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryPage: ...
    def rebuild_projection_from_journal(
        self,
        order_id: Identifier,
        *,
        expected_journal_head_checksum: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryLoad: ...


@runtime_checkable
class ClientOrderIdFactory(Protocol):
    def create(
        self,
        draft: OrderRegistrationDraft,
        *,
        broker: str,
        broker_capability_snapshot: Mapping[str, JsonValue],
        deadline_monotonic_ns: int,
    ) -> ClientOrderIdCandidate: ...
    def validate(
        self,
        client_order_id: str,
        *,
        broker: str,
        broker_capability_snapshot: Mapping[str, JsonValue],
        deadline_monotonic_ns: int,
    ) -> None: ...


@runtime_checkable
class OrderSnapshotStore(Protocol):
    def write(self, snapshot: OrderSnapshot, *, deadline_monotonic_ns: int) -> None: ...
    def latest_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> SnapshotLookup: ...


@runtime_checkable
class OutboxStore(Protocol):
    def claim(
        self, worker_id: str, policy: ClaimPolicy, *, deadline_monotonic_ns: int
    ) -> tuple[ClaimedMessage, ...]: ...
    def mark_published(
        self, message_id: str, claim_token: Identifier, *, deadline_monotonic_ns: int
    ) -> OutboxMutationResult: ...
    def release_failed(
        self,
        message_id: str,
        claim_token: Identifier,
        failure: PublishFailure,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult: ...
    def renew(
        self,
        message_id: str,
        claim_token: Identifier,
        policy: ClaimPolicy,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult: ...
