-- =========================================================
-- SRM - SalesRequestManager - PostgreSQL 16
-- =========================================================
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE request_type   AS ENUM ('NUOVO', 'DR');
CREATE TYPE request_status AS ENUM ('DRAFT', 'SENT', 'REMINDED', 'CLOSED');
CREATE TYPE close_reason   AS ENUM ('WON', 'LOST', 'APPROVED', 'REJECTED', 'CANCELLED', 'NO_RESPONSE');
CREATE TYPE request_source AS ENUM ('MANUAL', 'EMAIL_AI');
CREATE TYPE user_role      AS ENUM ('ADMIN', 'OPERATOR');
CREATE TYPE inbound_status AS ENUM ('NEW', 'PARSED', 'NEEDS_REVIEW', 'ERROR', 'IGNORED');

CREATE TABLE app_users (
    id           BIGSERIAL PRIMARY KEY,
    entra_oid    UUID UNIQUE,
    email        CITEXT NOT NULL UNIQUE,
    full_name    TEXT NOT NULL,
    role         user_role NOT NULL DEFAULT 'OPERATOR',
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales_agents (
    id           BIGSERIAL PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        CITEXT NOT NULL UNIQUE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE vendors (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    website      TEXT,
    notes        TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE suppliers (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    notes        TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mapping vendor <-> supplier e indirizzi destinatari (lowercase, normalizzati dall'app)
CREATE TABLE vendor_supplier_map (
    id            BIGSERIAL PRIMARY KEY,
    vendor_id     BIGINT NOT NULL REFERENCES vendors(id)   ON DELETE CASCADE,
    supplier_id   BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    to_emails     TEXT[] NOT NULL CHECK (cardinality(to_emails) > 0),
    cc_emails     TEXT[] NOT NULL DEFAULT '{}',
    supports_dr   BOOLEAN NOT NULL DEFAULT TRUE,
    is_preferred  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (vendor_id, supplier_id)
);
CREATE UNIQUE INDEX uq_one_preferred_per_vendor
    ON vendor_supplier_map(vendor_id) WHERE is_preferred;

CREATE TABLE global_config (
    id                         SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    sender_email               CITEXT NOT NULL,
    inbound_mailbox            CITEXT NOT NULL,
    inbound_processed_folder   TEXT NOT NULL DEFAULT 'SRM-Processed',
    default_cc                 TEXT[] NOT NULL DEFAULT '{}',
    reminder_after_days        SMALLINT NOT NULL DEFAULT 3  CHECK (reminder_after_days BETWEEN 1 AND 60),
    reminder_max_count         SMALLINT NOT NULL DEFAULT 3  CHECK (reminder_max_count BETWEEN 1 AND 10),
    reminder_business_days     BOOLEAN NOT NULL DEFAULT TRUE,
    llm_model                  TEXT NOT NULL DEFAULT 'claude-sonnet-5-5',
    updated_by                 BIGINT REFERENCES app_users(id),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inbound_emails (
    id                BIGSERIAL PRIMARY KEY,
    graph_message_id  TEXT NOT NULL UNIQUE,
    internet_msg_id   TEXT,
    from_email        CITEXT NOT NULL,
    subject           TEXT,
    body_text         TEXT,
    received_at       TIMESTAMPTZ NOT NULL,
    status            inbound_status NOT NULL DEFAULT 'NEW',
    llm_raw_output    JSONB,
    error_message     TEXT,
    processed_at      TIMESTAMPTZ
);
CREATE INDEX ix_inbound_status ON inbound_emails(status);

CREATE SEQUENCE request_code_seq START 1;

CREATE TABLE requests (
    id                      BIGSERIAL PRIMARY KEY,
    code                    TEXT NOT NULL UNIQUE
                            DEFAULT ('SRM-' || to_char(now(),'YYYY') || '-' ||
                                     lpad(nextval('request_code_seq')::text, 5, '0')),
    request_type            request_type   NOT NULL,
    status                  request_status NOT NULL DEFAULT 'DRAFT',
    source                  request_source NOT NULL DEFAULT 'MANUAL',

    vendor_id               BIGINT REFERENCES vendors(id),
    supplier_id             BIGINT REFERENCES suppliers(id),
    sales_agent_id          BIGINT REFERENCES sales_agents(id),
    created_by              BIGINT REFERENCES app_users(id),

    subject                 TEXT NOT NULL,
    body                    TEXT,
    product_description     TEXT,
    quantity                INTEGER CHECK (quantity IS NULL OR quantity > 0),

    -- Deal Registration
    end_customer_name       TEXT,
    estimated_deal_value    NUMERIC(14,2),
    currency                CHAR(3) NOT NULL DEFAULT 'EUR',
    expected_close_date     DATE,
    vendor_dr_reference     TEXT,
    dr_approved_at          DATE,
    dr_expires_at           DATE,

    -- Tracking invio / risposta
    graph_message_id        TEXT,
    graph_conversation_id   TEXT,
    sent_at                 TIMESTAMPTZ,
    last_reminder_at        TIMESTAMPTZ,
    reminder_count          SMALLINT NOT NULL DEFAULT 0,
    first_vendor_reply_at   TIMESTAMPTZ,
    closed_at               TIMESTAMPTZ,
    close_reason            close_reason,

    -- AI
    inbound_email_id        BIGINT REFERENCES inbound_emails(id),
    ai_confidence           NUMERIC(3,2) CHECK (ai_confidence BETWEEN 0 AND 1),
    needs_review            BOOLEAN NOT NULL DEFAULT FALSE,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_dr_mandatory CHECK (
        request_type <> 'DR'
        OR status = 'DRAFT'
        OR (    end_customer_name IS NOT NULL AND btrim(end_customer_name) <> ''
            AND estimated_deal_value IS NOT NULL AND estimated_deal_value > 0
            AND expected_close_date IS NOT NULL)
    ),
    CONSTRAINT chk_sent_fields CHECK (
        status = 'DRAFT'
        OR (vendor_id IS NOT NULL AND supplier_id IS NOT NULL AND sent_at IS NOT NULL)
    ),
    CONSTRAINT chk_closed_fields CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL)),
    CONSTRAINT chk_dr_dates CHECK (
        dr_expires_at IS NULL OR dr_approved_at IS NULL OR dr_expires_at >= dr_approved_at
    )
);
CREATE INDEX ix_requests_status     ON requests(status);
CREATE INDEX ix_requests_vendor     ON requests(vendor_id);
CREATE INDEX ix_requests_created_at ON requests(created_at);
CREATE INDEX ix_requests_conv       ON requests(graph_conversation_id);
CREATE INDEX ix_requests_reminder_scan
    ON requests(last_reminder_at, sent_at) WHERE status IN ('SENT','REMINDED');

CREATE TABLE request_events (
    id          BIGSERIAL PRIMARY KEY,
    request_id  BIGINT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    actor       TEXT NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_events_request ON request_events(request_id, created_at);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_requests_updated BEFORE UPDATE ON requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
