"""PostgreSQL implementation of Order Repository, SnapshotStore, and OutboxStore."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import Coroutine, Mapping
from datetime import UTC, datetime
from time import monotonic_ns
from types import MappingProxyType
from typing import Any, Literal, cast

from quantiqmt.order.application.persistence.errors import (
    IdempotencyConflict,
    JournalCommitFailed,
    OrderJournalCorrupted,
    UniqueIdentifierCollision,
)
from quantiqmt.order.application.persistence.model import (
    ClaimedMessage,
    ClaimPolicy,
    JournalAppend,
    JsonValue,
    OrderCommit,
    OrderRegistration,
    OrderSnapshot,
    OutboxMutationResult,
    PersistedOrder,
    PublishFailure,
    RecoveryLoad,
    RecoveryPage,
    RegisterOutcome,
    SnapshotLookup,
)
from quantiqmt.order.application.persistence.serialization import (
    canonical_json_bytes,
    journal_checksum,
    snapshot_checksum,
)
from quantiqmt.order.domain import (
    FactIdentity,
    Order,
    OrderState,
    OrderVersionConflict,
    ProcessedFact,
)
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity, parse_utc, require_utc


class PostgresOrderPersistence:
    """Synchronous port facade backed by short asyncpg transactions."""

    def __init__(self, dsn: str) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty")
        self._dsn = dsn

    def apply_migration(self, sql: str, *, deadline_monotonic_ns: int) -> None:
        _require_deadline(deadline_monotonic_ns)
        self._run(self._apply_migration(sql), deadline_monotonic_ns)

    def register(self, commit: OrderCommit, *, deadline_monotonic_ns: int) -> RegisterOutcome:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._register(commit), deadline_monotonic_ns)

    def get(self, order_id: Identifier, *, deadline_monotonic_ns: int) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._get_by("order_id", order_id.value), deadline_monotonic_ns)

    def get_by_intent(
        self, intent_id: Identifier, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._get_by("intent_id", intent_id.value), deadline_monotonic_ns)

    def get_by_client_order_id(
        self, client_order_id: str, *, deadline_monotonic_ns: int
    ) -> PersistedOrder | None:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._get_by("client_order_id", client_order_id), deadline_monotonic_ns)

    def save(
        self,
        commit: OrderCommit,
        *,
        expected_version: int,
        deadline_monotonic_ns: int,
    ) -> PersistedOrder:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._save(commit, expected_version), deadline_monotonic_ns)

    def load_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> RecoveryLoad:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._load_for_recovery(order_id), deadline_monotonic_ns)

    def list_recovery_order_ids(
        self,
        *,
        scope: Literal["ALL", "ACTIVE_OR_UNKNOWN"],
        page_size: int,
        page_token: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryPage:
        _require_deadline(deadline_monotonic_ns)
        return self._run(
            self._list_recovery_order_ids(scope, page_size, page_token),
            deadline_monotonic_ns,
        )

    def rebuild_projection_from_journal(
        self,
        order_id: Identifier,
        *,
        expected_journal_head_checksum: str | None,
        deadline_monotonic_ns: int,
    ) -> RecoveryLoad:
        _require_deadline(deadline_monotonic_ns)
        return self._run(
            self._rebuild_projection_from_journal(order_id, expected_journal_head_checksum),
            deadline_monotonic_ns,
        )

    def write(self, snapshot: OrderSnapshot, *, deadline_monotonic_ns: int) -> None:
        _require_deadline(deadline_monotonic_ns)
        self._run(self._write_snapshot(snapshot), deadline_monotonic_ns)

    def latest_for_recovery(
        self, order_id: Identifier, *, deadline_monotonic_ns: int
    ) -> SnapshotLookup:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._latest_for_recovery(order_id), deadline_monotonic_ns)

    def claim(
        self, worker_id: str, policy: ClaimPolicy, *, deadline_monotonic_ns: int
    ) -> tuple[ClaimedMessage, ...]:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._claim(worker_id, policy), deadline_monotonic_ns)

    def mark_published(
        self, message_id: str, claim_token: Identifier, *, deadline_monotonic_ns: int
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._mark_published(message_id, claim_token), deadline_monotonic_ns)

    def release_failed(
        self,
        message_id: str,
        claim_token: Identifier,
        failure: PublishFailure,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        return self._run(
            self._release_failed(message_id, claim_token, failure), deadline_monotonic_ns
        )

    def renew(
        self,
        message_id: str,
        claim_token: Identifier,
        policy: ClaimPolicy,
        *,
        deadline_monotonic_ns: int,
    ) -> OutboxMutationResult:
        _require_deadline(deadline_monotonic_ns)
        return self._run(self._renew(message_id, claim_token, policy), deadline_monotonic_ns)

    def _run[T](self, awaitable: Coroutine[Any, Any, T], deadline_monotonic_ns: int) -> T:
        timeout_seconds = _deadline_timeout_seconds(deadline_monotonic_ns)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(asyncio.wait_for(awaitable, timeout=timeout_seconds))
        raise RuntimeError("PostgresOrderPersistence sync facade cannot run inside an event loop")

    async def _connect(self) -> Any:
        asyncpg = _asyncpg()
        connection = await asyncpg.connect(self._dsn)
        await connection.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        await connection.set_type_codec(
            "json",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )
        return connection

    async def _apply_migration(self, sql: str) -> None:
        connection = await self._connect()
        try:
            await connection.execute(sql)
        finally:
            await connection.close()

    async def _register(self, commit: OrderCommit) -> RegisterOutcome:
        _validate_registration_commit(commit)
        connection = await self._connect()
        try:
            async with connection.transaction():
                existing = await self._fetch_by(
                    connection,
                    "intent_id",
                    commit.persisted_order.registration.intent_id.value,
                )
                if existing is not None:
                    if (
                        existing.registration_fingerprint
                        != commit.persisted_order.registration_fingerprint
                    ):
                        raise IdempotencyConflict(
                            "same intent_id has a different registration fingerprint"
                        )
                    return RegisterOutcome(existing, created=False)
                previous = await self._latest_journal_checksum(
                    connection, commit.journal.order_id.value
                )
                if previous is not None:
                    raise UniqueIdentifierCollision("order_id already exists without intent replay")
                await self._insert_order(connection, commit.persisted_order)
                await self._insert_journal(connection, commit.journal, None)
                await self._insert_outbox(connection, commit)
                return RegisterOutcome(commit.persisted_order, created=True)
        except Exception as exc:
            if _is_unique_violation(exc):
                return await self._resolve_register_unique_race(commit)
            raise
        finally:
            await connection.close()

    async def _resolve_register_unique_race(self, commit: OrderCommit) -> RegisterOutcome:
        existing = await self._get_by(
            "intent_id", commit.persisted_order.registration.intent_id.value
        )
        if existing is not None:
            if existing.registration_fingerprint == commit.persisted_order.registration_fingerprint:
                return RegisterOutcome(existing, created=False)
            raise IdempotencyConflict("same intent_id has a different registration fingerprint")
        raise UniqueIdentifierCollision("order_id or client_order_id already exists")

    async def _get_by(self, column: str, value: str) -> PersistedOrder | None:
        connection = await self._connect()
        try:
            return await self._fetch_by(connection, column, value)
        finally:
            await connection.close()

    async def _save(self, commit: OrderCommit, expected_version: int) -> PersistedOrder:
        if commit.journal.event_type != "ORDER_TRANSITION_APPLIED":
            raise JournalCommitFailed("save requires ORDER_TRANSITION_APPLIED journal entry")
        connection = await self._connect()
        try:
            async with connection.transaction():
                previous = await self._latest_journal_checksum(
                    connection, commit.persisted_order.registration.order_id.value
                )
                updated = await connection.execute(
                    """
                    UPDATE orders
                    SET state = $3,
                        cumulative_quantity = $4,
                        aggregate_version = $5,
                        state_payload = $6,
                        updated_at = $7
                    WHERE order_id = $1::uuid AND aggregate_version = $2
                    """,
                    commit.persisted_order.registration.order_id.value,
                    expected_version,
                    commit.persisted_order.order.state.value,
                    commit.persisted_order.order.cumulative_quantity.value,
                    commit.persisted_order.order.version,
                    _json(commit.persisted_order),
                    commit.journal.occurred_at,
                )
                if updated != "UPDATE 1":
                    raise OrderVersionConflict("expected version does not match stored projection")
                if commit.persisted_order.order.version != expected_version + 1:
                    raise JournalCommitFailed("commit version must equal expected_version + 1")
                await self._insert_journal(connection, commit.journal, previous)
                await self._insert_outbox(connection, commit)
                return commit.persisted_order
        except Exception as exc:
            if _is_unique_violation(exc):
                raise JournalCommitFailed("duplicate journal or outbox row") from exc
            raise
        finally:
            await connection.close()

    async def _load_for_recovery(self, order_id: Identifier) -> RecoveryLoad:
        connection = await self._connect()
        try:
            records = await self._verify_journal_chain(connection, order_id.value)
            persisted = await self._persisted_from_journal_records(connection, records)
            if persisted is None:
                raise JournalCommitFailed("order projection is missing")
            return RecoveryLoad(persisted, source="FULL_JOURNAL")
        finally:
            await connection.close()

    async def _list_recovery_order_ids(
        self, scope: Literal["ALL", "ACTIVE_OR_UNKNOWN"], page_size: int, page_token: str | None
    ) -> RecoveryPage:
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        active_states = (
            "REGISTERED",
            "RISK_PENDING",
            "APPROVED",
            "SUBMITTING",
            "SUBMIT_UNKNOWN",
            "SUBMITTED",
            "PARTIALLY_FILLED",
            "CANCEL_PENDING",
            "CANCEL_UNKNOWN",
            "SUSPENDED",
        )
        connection = await self._connect()
        try:
            if scope == "ALL":
                rows = await connection.fetch(
                    """
                    SELECT order_id::text AS order_id
                    FROM orders
                    WHERE ($1::uuid IS NULL OR order_id > $1::uuid)
                    ORDER BY order_id
                    LIMIT $2
                    """,
                    page_token,
                    page_size + 1,
                )
            else:
                rows = await connection.fetch(
                    """
                    SELECT order_id::text AS order_id
                    FROM orders
                    WHERE ($1::uuid IS NULL OR order_id > $1::uuid)
                      AND state = ANY($3::text[])
                    ORDER BY order_id
                    LIMIT $2
                    """,
                    page_token,
                    page_size + 1,
                    active_states,
                )
            values = [str(row["order_id"]) for row in rows]
            page_values = values[:page_size]
            next_token = page_values[-1] if len(values) > page_size and page_values else None
            return RecoveryPage(
                tuple(Identifier(value) for value in page_values),
                next_token,
                next_token is None,
            )
        finally:
            await connection.close()

    async def _rebuild_projection_from_journal(
        self, order_id: Identifier, expected_journal_head_checksum: str | None
    ) -> RecoveryLoad:
        connection = await self._connect()
        try:
            records = await self._verify_journal_chain(connection, order_id.value)
            if not records:
                raise JournalCommitFailed("journal is missing")
            head = str(records[-1]["entry_checksum"])
            if (
                expected_journal_head_checksum is not None
                and expected_journal_head_checksum != head
            ):
                raise OrderVersionConflict("journal head changed during projection rebuild")
            persisted = await self._persisted_from_journal_records(connection, records)
            if persisted is None:
                raise JournalCommitFailed("cannot rebuild without committed post-state payload")
            async with connection.transaction():
                await self._update_order_projection(connection, persisted)
            return RecoveryLoad(persisted, source="FULL_JOURNAL")
        finally:
            await connection.close()

    async def _write_snapshot(self, snapshot: OrderSnapshot) -> None:
        connection = await self._connect()
        try:
            await connection.execute(
                """
                INSERT INTO order_snapshots (
                    snapshot_id, order_id, aggregate_version, schema_version, state_payload,
                    journal_head_checksum, snapshot_checksum, created_at
                )
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (order_id, aggregate_version) DO NOTHING
                """,
                snapshot.snapshot_id.value,
                snapshot.order_id.value,
                snapshot.aggregate_version,
                snapshot.schema_version,
                _json_object(snapshot.state_payload),
                snapshot.journal_head_checksum,
                snapshot.snapshot_checksum,
                snapshot.created_at,
            )
        finally:
            await connection.close()

    async def _latest_for_recovery(self, order_id: Identifier) -> SnapshotLookup:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                SELECT snapshot_id::text AS snapshot_id, order_id::text AS order_id,
                       aggregate_version, schema_version, state_payload,
                       journal_head_checksum, snapshot_checksum, created_at
                FROM order_snapshots
                WHERE order_id = $1::uuid
                ORDER BY aggregate_version DESC
                LIMIT 1
                """,
                order_id.value,
            )
            if row is None:
                return SnapshotLookup(None, "ABSENT")
            snapshot = _snapshot_from_row(row)
            head = await self._journal_checksum_at_version(
                connection, order_id.value, snapshot.aggregate_version
            )
            if (
                snapshot_checksum(snapshot.state_payload) != snapshot.snapshot_checksum
                or head != snapshot.journal_head_checksum
            ):
                return SnapshotLookup(
                    None,
                    "INVALID_DISCARDED",
                    diagnostic_code="QQ-STORAGE-7003",
                    diagnostic_detail="snapshot checksum or journal head checksum mismatch",
                    invalid_snapshot_id=snapshot.snapshot_id,
                    invalid_aggregate_version=snapshot.aggregate_version,
                )
            return SnapshotLookup(snapshot, "VALID")
        finally:
            await connection.close()

    async def _claim(self, worker_id: str, policy: ClaimPolicy) -> tuple[ClaimedMessage, ...]:
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        connection = await self._connect()
        try:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE outbox_messages
                    SET status = 'DEAD_LETTER',
                        claimed_by = NULL,
                        claim_token = NULL,
                        lease_until = NULL,
                        last_error_code = 'MAX_ATTEMPTS_REACHED',
                        last_error_detail = 'outbox max_attempts reached before claim',
                        updated_at = transaction_timestamp()
                    WHERE status IN ('PENDING', 'CLAIMED')
                      AND attempt_count >= $1
                      AND (status = 'PENDING' OR lease_until <= transaction_timestamp())
                    """,
                    policy.max_attempts,
                )
                rows = await connection.fetch(
                    """
                    WITH selected AS (
                        SELECT message_id
                        FROM outbox_messages
                        WHERE (
                            status = 'PENDING'
                            AND attempt_count < $4
                            AND available_at <= transaction_timestamp()
                        )
                           OR (
                               status = 'CLAIMED'
                               AND attempt_count < $4
                               AND lease_until <= transaction_timestamp()
                           )
                        ORDER BY available_at, created_at, message_id
                        LIMIT $1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE outbox_messages AS outbox
                    SET status = 'CLAIMED',
                        attempt_count = outbox.attempt_count + 1,
                        claim_max_attempts = $4,
                        claim_initial_retry_delay_ms = $5,
                        claim_max_retry_delay_ms = $6,
                        claim_backoff_multiplier = $7,
                        claim_jitter_ratio = $8,
                        claimed_by = $2,
                        claim_token = gen_random_uuid(),
                        lease_until = transaction_timestamp()
                            + ($3::text || ' milliseconds')::interval,
                        updated_at = transaction_timestamp()
                    FROM selected
                    WHERE outbox.message_id = selected.message_id
                    RETURNING outbox.*
                    """,
                    policy.batch_size,
                    worker_id,
                    str(policy.lease_duration_ms),
                    policy.max_attempts,
                    policy.initial_retry_delay_ms,
                    policy.max_retry_delay_ms,
                    policy.backoff_multiplier,
                    policy.jitter_ratio,
                )
                return tuple(_claimed_from_row(row) for row in rows)
        finally:
            await connection.close()

    async def _mark_published(
        self, message_id: str, claim_token: Identifier
    ) -> OutboxMutationResult:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                UPDATE outbox_messages
                SET status = 'PUBLISHED',
                    claimed_by = NULL,
                    claim_token = NULL,
                    lease_until = NULL,
                    published_at = transaction_timestamp(),
                    updated_at = transaction_timestamp()
                WHERE message_id = $1
                  AND claim_token = $2::uuid
                  AND status = 'CLAIMED'
                  AND lease_until > transaction_timestamp()
                RETURNING message_id
                """,
                message_id,
                claim_token.value,
            )
            return _mutation_result(row is not None)
        finally:
            await connection.close()

    async def _release_failed(
        self, message_id: str, claim_token: Identifier, failure: PublishFailure
    ) -> OutboxMutationResult:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                UPDATE outbox_messages
                SET status = CASE
                        WHEN $3::boolean AND attempt_count < claim_max_attempts THEN 'PENDING'
                        ELSE 'DEAD_LETTER'
                    END,
                    claimed_by = NULL,
                    claim_token = NULL,
                    lease_until = NULL,
                    available_at = CASE
                        WHEN $3::boolean AND attempt_count < claim_max_attempts
                        THEN transaction_timestamp()
                            + (
                                LEAST(
                                    claim_max_retry_delay_ms,
                                    CEIL(
                                        claim_initial_retry_delay_ms
                                        * POWER(
                                            claim_backoff_multiplier::numeric,
                                            GREATEST(attempt_count - 1, 0)
                                        )
                                    )::integer
                                )::text || ' milliseconds'
                            )::interval
                        ELSE available_at
                    END,
                    last_error_code = CASE
                        WHEN $3::boolean AND attempt_count >= claim_max_attempts
                        THEN 'MAX_ATTEMPTS_REACHED'
                        ELSE $4
                    END,
                    last_error_detail = $5,
                    updated_at = transaction_timestamp()
                WHERE message_id = $1
                  AND claim_token = $2::uuid
                  AND status = 'CLAIMED'
                  AND lease_until > transaction_timestamp()
                  AND claim_max_attempts IS NOT NULL
                  AND claim_initial_retry_delay_ms IS NOT NULL
                  AND claim_max_retry_delay_ms IS NOT NULL
                  AND claim_backoff_multiplier IS NOT NULL
                RETURNING message_id
                """,
                message_id,
                claim_token.value,
                failure.retryable,
                failure.error_code,
                failure.error_detail,
            )
            return _mutation_result(row is not None)
        finally:
            await connection.close()

    async def _renew(
        self, message_id: str, claim_token: Identifier, policy: ClaimPolicy
    ) -> OutboxMutationResult:
        connection = await self._connect()
        try:
            row = await connection.fetchrow(
                """
                UPDATE outbox_messages
                SET lease_until = transaction_timestamp() + ($3::text || ' milliseconds')::interval,
                    updated_at = transaction_timestamp()
                WHERE message_id = $1
                  AND claim_token = $2::uuid
                  AND status = 'CLAIMED'
                  AND lease_until > transaction_timestamp()
                RETURNING message_id
                """,
                message_id,
                claim_token.value,
                str(policy.lease_duration_ms),
            )
            return _mutation_result(row is not None)
        finally:
            await connection.close()

    async def _fetch_by(self, connection: Any, column: str, value: str) -> PersistedOrder | None:
        if column not in {"order_id", "intent_id", "client_order_id"}:
            raise ValueError("unsupported lookup column")
        condition = (
            f"{column} = $1::uuid" if column in {"order_id", "intent_id"} else f"{column} = $1"
        )
        row = await connection.fetchrow(
            f"""
            SELECT order_id::text AS order_id, intent_id::text AS intent_id, client_order_id,
                   registration_fingerprint, state_payload
            FROM orders
            WHERE {condition}
            """,
            value,
        )
        return _persisted_from_row(row) if row is not None else None

    async def _latest_journal_checksum(self, connection: Any, order_id: str) -> str | None:
        row = await connection.fetchrow(
            """
            SELECT entry_checksum
            FROM order_journal
            WHERE order_id = $1::uuid
            ORDER BY aggregate_version DESC
            LIMIT 1
            """,
            order_id,
        )
        return str(row["entry_checksum"]) if row is not None else None

    async def _journal_checksum_at_version(
        self, connection: Any, order_id: str, aggregate_version: int
    ) -> str | None:
        row = await connection.fetchrow(
            """
            SELECT entry_checksum
            FROM order_journal
            WHERE order_id = $1::uuid AND aggregate_version = $2
            """,
            order_id,
            aggregate_version,
        )
        return str(row["entry_checksum"]) if row is not None else None

    async def _persisted_from_journal_records(
        self, connection: Any, records: list[Any]
    ) -> PersistedOrder | None:
        if not records:
            return None
        last = records[-1]
        payload = cast(Mapping[str, Any], last["payload"])
        post_state = payload.get("post_state")
        if not isinstance(post_state, Mapping):
            raise JournalCommitFailed("journal entry is missing committed post_state")
        current = await self._fetch_by(connection, "order_id", str(last["order_id"]))
        fingerprint = (
            current.registration_fingerprint
            if current is not None
            else str(post_state.get("registration_fingerprint", ""))
        )
        if not fingerprint:
            return None
        return _persisted_from_state_payload(post_state, fingerprint)

    async def _update_order_projection(self, connection: Any, persisted: PersistedOrder) -> None:
        registration = persisted.registration
        updated = await connection.execute(
            """
            UPDATE orders
            SET client_order_id = $2,
                registration_fingerprint = $3,
                account_id = $4,
                instrument_id = $5,
                owner_strategy_id = $6,
                owner_strategy_version = $7,
                order_type = $8,
                side = $9,
                position_effect = $10,
                time_in_force = $11,
                quantity = $12,
                limit_price = $13,
                state = $14,
                cumulative_quantity = $15,
                aggregate_version = $16,
                state_payload = $17,
                registered_at = $18,
                updated_at = transaction_timestamp()
            WHERE order_id = $1::uuid
            """,
            registration.order_id.value,
            registration.client_order_id,
            persisted.registration_fingerprint,
            registration.account_id,
            registration.instrument_id.value,
            registration.owner_strategy_id,
            registration.owner_strategy_version,
            registration.order_type,
            registration.side,
            registration.position_effect,
            registration.time_in_force,
            registration.quantity.value,
            (
                registration.limit_price.to_primitive()
                if registration.limit_price is not None
                else None
            ),
            persisted.order.state.value,
            persisted.order.cumulative_quantity.value,
            persisted.order.version,
            _json(persisted),
            registration.registered_at,
        )
        if updated != "UPDATE 1":
            raise JournalCommitFailed("order projection is missing")

    async def _insert_order(self, connection: Any, persisted: PersistedOrder) -> None:
        registration = persisted.registration
        await connection.execute(
            """
            INSERT INTO orders (
                order_id, intent_id, client_order_id, registration_fingerprint,
                account_id, instrument_id, owner_strategy_id, owner_strategy_version,
                order_type, side, position_effect, time_in_force, quantity, limit_price,
                state, cumulative_quantity, aggregate_version, state_payload,
                registered_at, updated_at
            )
            VALUES (
                $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            """,
            registration.order_id.value,
            registration.intent_id.value,
            registration.client_order_id,
            persisted.registration_fingerprint,
            registration.account_id,
            registration.instrument_id.value,
            registration.owner_strategy_id,
            registration.owner_strategy_version,
            registration.order_type,
            registration.side,
            registration.position_effect,
            registration.time_in_force,
            registration.quantity.value,
            (
                registration.limit_price.to_primitive()
                if registration.limit_price is not None
                else None
            ),
            persisted.order.state.value,
            persisted.order.cumulative_quantity.value,
            persisted.order.version,
            _json(persisted),
            registration.registered_at,
            registration.registered_at,
        )

    async def _insert_journal(
        self, connection: Any, append: JournalAppend, previous_entry_checksum: str | None
    ) -> None:
        await connection.execute(
            """
            INSERT INTO order_journal (
                journal_id, order_id, aggregate_version, event_type, schema_version,
                payload, occurred_at, recorded_at, correlation_id, causation_id,
                previous_entry_checksum, entry_checksum
            )
            VALUES (
                $1::uuid, $2::uuid, $3, $4, 1, $5, $6,
                transaction_timestamp(), $7, $8, $9, $10
            )
            """,
            append.journal_id.value,
            append.order_id.value,
            append.aggregate_version,
            append.event_type,
            _json_object(append.payload),
            append.occurred_at,
            append.correlation_id,
            append.causation_id,
            previous_entry_checksum,
            journal_checksum(append, previous_entry_checksum),
        )

    async def _insert_outbox(self, connection: Any, commit: OrderCommit) -> None:
        for message in commit.outbox_messages:
            primitive = message.to_primitive()
            await connection.execute(
                """
                INSERT INTO outbox_messages (
                    message_id, message_type, schema_version, aggregate_id, aggregate_version,
                    partition_key, envelope, status, attempt_count, available_at,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, 'PENDING', 0,
                    transaction_timestamp(), transaction_timestamp(), transaction_timestamp()
                )
                """,
                str(primitive["message_id"]),
                str(primitive["message_type"]),
                _required_int(primitive["schema_version"]),
                _optional_str(primitive.get("aggregate_id")),
                _optional_int(primitive.get("aggregate_version")),
                str(primitive["partition_key"]),
                primitive,
            )

    async def _verify_journal_chain(self, connection: Any, order_id: str) -> list[Any]:
        rows = await connection.fetch(
            """
            SELECT journal_id::text AS journal_id, order_id::text AS order_id,
                   aggregate_version, event_type, payload, occurred_at,
                   correlation_id, causation_id, previous_entry_checksum, entry_checksum
            FROM order_journal
            WHERE order_id = $1::uuid
            ORDER BY aggregate_version
            """,
            order_id,
        )
        previous: str | None = None
        for expected, row in enumerate(rows, start=1):
            append = JournalAppend(
                Identifier(str(row["journal_id"])),
                Identifier(str(row["order_id"])),
                int(row["aggregate_version"]),
                row["event_type"],
                row["payload"],
                _utc(row["occurred_at"]),
                str(row["correlation_id"]),
                _optional_str(row["causation_id"]),
            )
            if append.aggregate_version != expected:
                raise OrderJournalCorrupted("journal version gap detected")
            if _optional_str(row["previous_entry_checksum"]) != previous:
                raise OrderJournalCorrupted("journal previous checksum mismatch")
            if journal_checksum(append, previous) != str(row["entry_checksum"]):
                raise OrderJournalCorrupted("journal checksum mismatch")
            previous = str(row["entry_checksum"])
        return list(rows)


def _persisted_from_row(row: Any) -> PersistedOrder:
    payload = cast(Mapping[str, Any], row["state_payload"])
    return _persisted_from_state_payload(payload, str(row["registration_fingerprint"]))


def _persisted_from_state_payload(
    payload: Mapping[str, Any], registration_fingerprint: str
) -> PersistedOrder:
    registration_payload = cast(Mapping[str, Any], payload["registration"])
    registration = OrderRegistration(
        Identifier(str(registration_payload["order_id"])),
        Identifier(str(registration_payload["intent_id"])),
        str(registration_payload["client_order_id"]),
        str(registration_payload["account_id"]),
        InstrumentId(str(registration_payload["instrument_id"])),
        registration_payload["side"],
        registration_payload["position_effect"],
        registration_payload["order_type"],
        Quantity(int(registration_payload["quantity"])),
        Price(str(registration_payload["limit_price"]))
        if registration_payload["limit_price"] is not None
        else None,
        registration_payload["time_in_force"],
        str(registration_payload["owner_strategy_id"]),
        str(registration_payload["owner_strategy_version"]),
        parse_utc(str(registration_payload["registered_at"])),
    )
    order = Order(
        Identifier(str(payload["order_id"])),
        Quantity(int(payload["quantity"])),
        state=OrderState(str(payload["state"])),
        cumulative_quantity=Quantity(int(payload["cumulative_quantity"])),
        version=int(payload["aggregate_version"]),
        processed_facts=_processed_facts(payload.get("processed_facts", [])),
        fact_conflicts=_fact_conflicts(payload.get("fact_conflicts", [])),
        broker_sequences=_broker_sequences(payload.get("broker_sequences", [])),
    )
    return PersistedOrder(registration, order, registration_fingerprint)


def _processed_facts(values: object) -> dict[FactIdentity, ProcessedFact]:
    facts: dict[FactIdentity, ProcessedFact] = {}
    for item in cast(list[Mapping[str, Any]], values):
        quantity = item.get("trade_quantity")
        facts[FactIdentity(str(item["namespace"]), str(item["key"]))] = ProcessedFact(
            str(item["fingerprint"]),
            Quantity(int(quantity)) if quantity is not None else None,
        )
    return facts


def _fact_conflicts(values: object) -> dict[FactIdentity, frozenset[str]]:
    conflicts: dict[FactIdentity, frozenset[str]] = {}
    for item in cast(list[Mapping[str, Any]], values):
        conflicts[FactIdentity(str(item["namespace"]), str(item["key"]))] = frozenset(
            str(value) for value in cast(list[object], item["conflicting_fingerprints"])
        )
    return conflicts


def _broker_sequences(values: object) -> dict[str, int]:
    return {
        str(item["stream"]): int(item["last_observed_sequence"])
        for item in cast(list[Mapping[str, Any]], values)
    }


def _snapshot_from_row(row: Any) -> OrderSnapshot:
    return OrderSnapshot(
        Identifier(str(row["snapshot_id"])),
        Identifier(str(row["order_id"])),
        int(row["aggregate_version"]),
        int(row["schema_version"]),
        row["state_payload"],
        str(row["journal_head_checksum"]),
        str(row["snapshot_checksum"]),
        _utc(row["created_at"]),
    )


def _claimed_from_row(row: Any) -> ClaimedMessage:
    return ClaimedMessage(
        message_id=str(row["message_id"]),
        message_type=str(row["message_type"]),
        aggregate_id=_optional_str(row["aggregate_id"]),
        aggregate_version=_optional_int(row["aggregate_version"]),
        partition_key=str(row["partition_key"]),
        envelope=_strict_json_object(row["envelope"]),
        claim_token=Identifier(str(row["claim_token"])),
        lease_until=_utc(row["lease_until"]),
        attempt_count=int(row["attempt_count"]),
    )


def _mutation_result(applied: bool) -> OutboxMutationResult:
    if applied:
        return OutboxMutationResult(True, "OK")
    return OutboxMutationResult(False, "QQ-STORAGE-7004", "claim token missing or expired")


def _validate_registration_commit(commit: OrderCommit) -> None:
    if commit.persisted_order.order.version != 1 or commit.journal.aggregate_version != 1:
        raise JournalCommitFailed("register requires aggregate version 1")
    if commit.journal.event_type != "ORDER_REGISTERED":
        raise JournalCommitFailed("register requires ORDER_REGISTERED journal entry")
    if not commit.outbox_messages:
        raise JournalCommitFailed("register requires at least one outbox message")
    if not any(
        message.to_primitive().get("message_type") == "oms.order_registered.v1"
        for message in commit.outbox_messages
    ):
        raise JournalCommitFailed("register requires oms.order_registered.v1 outbox message")


def _json(persisted: PersistedOrder) -> Mapping[str, object]:
    from quantiqmt.order.application.persistence.serialization import order_state_payload

    return _json_object(order_state_payload(persisted))


def _json_object(value: Mapping[str, object]) -> Mapping[str, object]:
    decoded = json.loads(canonical_json_bytes(value))
    if not isinstance(decoded, dict):
        raise TypeError("canonical JSON object must decode to a dict")
    return cast(Mapping[str, object], decoded)


def _strict_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise TypeError("PostgreSQL JSON value must not contain float")
    if isinstance(value, list | tuple):
        return tuple(_strict_json_value(item) for item in value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("PostgreSQL JSON object keys must be strings")
        return MappingProxyType({str(key): _strict_json_value(item) for key, item in value.items()})
    raise TypeError(f"unsupported PostgreSQL JSON value {type(value).__name__}")


def _strict_json_object(value: Mapping[object, object]) -> Mapping[str, JsonValue]:
    if not all(isinstance(key, str) for key in value):
        raise TypeError("PostgreSQL JSON object keys must be strings")
    return MappingProxyType({str(key): _strict_json_value(item) for key, item in value.items()})


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return require_utc(value)


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("value must be an integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _require_deadline(deadline_monotonic_ns: int) -> None:
    if not isinstance(deadline_monotonic_ns, int) or deadline_monotonic_ns <= 0:
        raise ValueError("deadline_monotonic_ns is required and must be positive")
    if deadline_monotonic_ns <= monotonic_ns():
        raise TimeoutError("deadline_monotonic_ns has expired")


def _deadline_timeout_seconds(deadline_monotonic_ns: int) -> float:
    _require_deadline(deadline_monotonic_ns)
    return max((deadline_monotonic_ns - monotonic_ns()) / 1_000_000_000, 0.001)


def _is_unique_violation(exc: Exception) -> bool:
    return exc.__class__.__name__ == "UniqueViolationError"


def _asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        raise RuntimeError("asyncpg is required for PostgresOrderPersistence") from exc
