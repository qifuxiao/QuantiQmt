-- TASK-004 Order persistence, journal, snapshots, and transactional outbox.
--
-- Expand-only migration.  Downgrade safety: production rollback must stop
-- writers/workers and keep all rows for audit/recovery; this file intentionally
-- contains no destructive DROP/DELETE downgrade section.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS orders (
    order_id uuid PRIMARY KEY,
    intent_id uuid NOT NULL UNIQUE,
    client_order_id varchar(128) NOT NULL UNIQUE,
    registration_fingerprint char(64) NOT NULL,
    account_id varchar(128) NOT NULL,
    instrument_id varchar(64) NOT NULL,
    owner_strategy_id varchar(128) NOT NULL,
    owner_strategy_version varchar(64) NOT NULL,
    order_type varchar(16) NOT NULL,
    side varchar(8) NOT NULL,
    position_effect varchar(8) NOT NULL,
    time_in_force varchar(8) NOT NULL,
    quantity bigint NOT NULL,
    limit_price varchar(64),
    state varchar(32) NOT NULL,
    cumulative_quantity bigint NOT NULL,
    aggregate_version bigint NOT NULL,
    state_payload jsonb NOT NULL,
    registered_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT orders_registration_fingerprint_sha256
        CHECK (registration_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT orders_quantity_positive CHECK (quantity >= 1),
    CONSTRAINT orders_cumulative_quantity_valid
        CHECK (cumulative_quantity >= 0 AND cumulative_quantity <= quantity),
    CONSTRAINT orders_aggregate_version_positive CHECK (aggregate_version >= 1),
    CONSTRAINT orders_limit_price_required_for_limit
        CHECK ((order_type = 'LIMIT' AND limit_price IS NOT NULL) OR order_type <> 'LIMIT'),
    CONSTRAINT orders_state_payload_version_matches
        CHECK ((state_payload->>'aggregate_version')::bigint = aggregate_version),
    CONSTRAINT orders_order_type_enum CHECK (order_type IN ('LIMIT', 'MARKET', 'BEST')),
    CONSTRAINT orders_side_enum CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT orders_position_effect_enum CHECK (position_effect IN ('OPEN', 'CLOSE', 'AUTO')),
    CONSTRAINT orders_time_in_force_enum CHECK (time_in_force IN ('DAY', 'IOC', 'FOK'))
);

CREATE INDEX IF NOT EXISTS orders_account_state_idx ON orders (account_id, state);
CREATE INDEX IF NOT EXISTS orders_updated_at_idx ON orders (updated_at);

CREATE TABLE IF NOT EXISTS order_journal (
    journal_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES orders(order_id),
    aggregate_version bigint NOT NULL,
    event_type varchar(32) NOT NULL,
    schema_version integer NOT NULL DEFAULT 1,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    correlation_id varchar(64) NOT NULL,
    causation_id varchar(64),
    previous_entry_checksum char(64),
    entry_checksum char(64) NOT NULL,
    CONSTRAINT order_journal_order_version_unique UNIQUE (order_id, aggregate_version),
    CONSTRAINT order_journal_aggregate_version_positive CHECK (aggregate_version >= 1),
    CONSTRAINT order_journal_event_type_enum
        CHECK (event_type IN ('ORDER_REGISTERED', 'ORDER_TRANSITION_APPLIED')),
    CONSTRAINT order_journal_schema_version_v1 CHECK (schema_version = 1),
    CONSTRAINT order_journal_entry_checksum_sha256 CHECK (entry_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT order_journal_previous_checksum_sha256
        CHECK (previous_entry_checksum IS NULL OR previous_entry_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT order_journal_first_entry_rule
        CHECK (
            (aggregate_version = 1 AND event_type = 'ORDER_REGISTERED' AND previous_entry_checksum IS NULL)
            OR aggregate_version > 1
        )
);

CREATE TABLE IF NOT EXISTS order_snapshots (
    snapshot_id uuid PRIMARY KEY,
    order_id uuid NOT NULL REFERENCES orders(order_id),
    aggregate_version bigint NOT NULL,
    schema_version integer NOT NULL DEFAULT 1,
    state_payload jsonb NOT NULL,
    journal_head_checksum char(64) NOT NULL,
    snapshot_checksum char(64) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT order_snapshots_order_version_unique UNIQUE (order_id, aggregate_version),
    CONSTRAINT order_snapshots_aggregate_version_positive CHECK (aggregate_version >= 1),
    CONSTRAINT order_snapshots_schema_version_v1 CHECK (schema_version = 1),
    CONSTRAINT order_snapshots_journal_head_checksum_sha256
        CHECK (journal_head_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT order_snapshots_snapshot_checksum_sha256
        CHECK (snapshot_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT order_snapshots_state_payload_version_matches
        CHECK ((state_payload->>'aggregate_version')::bigint = aggregate_version)
);

CREATE TABLE IF NOT EXISTS outbox_messages (
    message_id varchar(64) PRIMARY KEY,
    message_type varchar(128) NOT NULL,
    schema_version integer NOT NULL,
    aggregate_id varchar(128),
    aggregate_version bigint,
    partition_key varchar(256) NOT NULL,
    envelope jsonb NOT NULL,
    status varchar(16) NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL,
    claimed_by varchar(128),
    claim_token uuid,
    lease_until timestamptz,
    published_at timestamptz,
    last_error_code varchar(128),
    last_error_detail varchar(2048),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT outbox_message_type_pattern
        CHECK (message_type ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.v[1-9][0-9]*$'),
    CONSTRAINT outbox_schema_version_positive CHECK (schema_version >= 1),
    CONSTRAINT outbox_aggregate_version_positive
        CHECK (aggregate_version IS NULL OR aggregate_version >= 1),
    CONSTRAINT outbox_status_enum CHECK (status IN ('PENDING', 'CLAIMED', 'PUBLISHED', 'DEAD_LETTER')),
    CONSTRAINT outbox_attempt_count_non_negative CHECK (attempt_count >= 0),
    CONSTRAINT outbox_pending_fields
        CHECK (status <> 'PENDING' OR (
            claimed_by IS NULL AND claim_token IS NULL AND lease_until IS NULL AND published_at IS NULL
        )),
    CONSTRAINT outbox_claimed_fields
        CHECK (status <> 'CLAIMED' OR (
            claimed_by IS NOT NULL AND claim_token IS NOT NULL AND lease_until IS NOT NULL
        )),
    CONSTRAINT outbox_published_fields
        CHECK (status <> 'PUBLISHED' OR (
            published_at IS NOT NULL AND claimed_by IS NULL AND claim_token IS NULL AND lease_until IS NULL
        )),
    CONSTRAINT outbox_dead_letter_fields
        CHECK (status <> 'DEAD_LETTER' OR (
            last_error_code IS NOT NULL AND claimed_by IS NULL AND claim_token IS NULL AND lease_until IS NULL
        ))
);

CREATE INDEX IF NOT EXISTS outbox_claim_scan_idx
    ON outbox_messages (status, available_at, created_at, message_id);
CREATE INDEX IF NOT EXISTS outbox_aggregate_audit_idx
    ON outbox_messages (aggregate_id, aggregate_version);
