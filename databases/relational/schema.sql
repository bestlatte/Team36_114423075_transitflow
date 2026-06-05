-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Deletion strategy: relational application tables use soft delete via is_deleted
-- so historical bookings, payments, and audit-sensitive data are preserved.
-- Foreign keys therefore use ON DELETE RESTRICT to prevent hard deletion of
-- referenced rows while dependent records still exist.

-- ============================================================
--  INFRASTRUCTURE: Stations
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_stations (
    id                                   BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    station_id                           VARCHAR(10)  NOT NULL UNIQUE,
    name                                 VARCHAR(100) NOT NULL,
    lines                                TEXT[]       NOT NULL DEFAULT '{}',
    is_interchange_metro                 BOOLEAN      NOT NULL DEFAULT FALSE,
    interchange_metro_lines              TEXT[]       NOT NULL DEFAULT '{}',
    is_interchange_national_rail         BOOLEAN      NOT NULL DEFAULT FALSE,
    interchange_national_rail_station_id VARCHAR(10),
    created_at                           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted                           BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS national_rail_stations (
    id                                   BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    station_id                           VARCHAR(10)  NOT NULL UNIQUE,
    name                                 VARCHAR(100) NOT NULL,
    lines                                TEXT[]       NOT NULL DEFAULT '{}',
    is_interchange_national_rail         BOOLEAN      NOT NULL DEFAULT FALSE,
    interchange_national_rail_lines      TEXT[]       NOT NULL DEFAULT '{}',
    is_interchange_metro                 BOOLEAN      NOT NULL DEFAULT FALSE,
    interchange_metro_station_id         VARCHAR(10),
    created_at                           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted                           BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  INFRASTRUCTURE: Metro Schedules
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_schedules (
    id                     BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id            VARCHAR(20)    NOT NULL UNIQUE,
    line                   VARCHAR(10)    NOT NULL,
    direction              VARCHAR(20)    NOT NULL CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound')),
    origin_station_id      VARCHAR(10)    NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10)    NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    first_train_time       TIMESTAMPTZ    NOT NULL,
    last_train_time        TIMESTAMPTZ    NOT NULL,
    base_fare_usd          DECIMAL(10,2)  NOT NULL,
    per_stop_rate_usd      DECIMAL(10,2)  NOT NULL,
    frequency_min          INTEGER        NOT NULL,
    operates_on            TEXT[]         NOT NULL DEFAULT '{}',
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    id                          BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id                 VARCHAR(20)  NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE RESTRICT,
    station_id                  VARCHAR(10)  NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    stop_order                  INTEGER      NOT NULL,
    travel_time_from_origin_min INTEGER      NOT NULL DEFAULT 0,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, stop_order)
);

-- ============================================================
--  INFRASTRUCTURE: National Rail Schedules
-- ============================================================

CREATE TABLE IF NOT EXISTS national_rail_schedules (
    id                     BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id            VARCHAR(20)    NOT NULL UNIQUE,
    line                   VARCHAR(10)    NOT NULL,
    service_type           VARCHAR(20)    NOT NULL CHECK (service_type IN ('normal', 'express')),
    direction              VARCHAR(20)    NOT NULL CHECK (direction IN ('northbound', 'southbound', 'eastbound', 'westbound')),
    origin_station_id      VARCHAR(10)    NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10)    NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    first_train_time       TIMESTAMPTZ    NOT NULL,
    last_train_time        TIMESTAMPTZ    NOT NULL,
    frequency_min          INTEGER        NOT NULL,
    operates_on            TEXT[]         NOT NULL DEFAULT '{}',
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    id                          BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id                 VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    station_id                  VARCHAR(10)  NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    stop_order                  INTEGER      NOT NULL,
    travel_time_from_origin_min INTEGER      NOT NULL DEFAULT 0,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, stop_order)
);

CREATE TABLE IF NOT EXISTS national_rail_fare_classes (
    id                BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id       VARCHAR(20)    NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    fare_class        VARCHAR(20)    NOT NULL CHECK (fare_class IN ('standard', 'first')),
    base_fare_usd     DECIMAL(10,2)  NOT NULL,
    per_stop_rate_usd DECIMAL(10,2)  NOT NULL,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted        BOOLEAN        NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, fare_class)
);

-- ============================================================
--  INFRASTRUCTURE: Seat Layouts (National Rail only)
-- ============================================================

CREATE TABLE IF NOT EXISTS seats (
    id          BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    schedule_id VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    coach       VARCHAR(5)   NOT NULL,
    fare_class  VARCHAR(20)  NOT NULL CHECK (fare_class IN ('standard', 'first')),
    seat_id     VARCHAR(10)  NOT NULL,
    seat_row    INTEGER      NOT NULL,
    seat_column VARCHAR(5)   NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, seat_id),
    UNIQUE (schedule_id, coach, seat_id, fare_class)
);

CREATE OR REPLACE VIEW seat_layouts AS
SELECT
    schedule_id,
    coach,
    fare_class,
    seat_id,
    seat_row,
    seat_column
FROM seats
WHERE is_deleted = FALSE;

-- ============================================================
--  POLICIES: Ticket Types
-- ============================================================

CREATE TABLE IF NOT EXISTS ticket_types (
    id           BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    ticket_type  VARCHAR(20)  NOT NULL UNIQUE,
    display_name VARCHAR(50)  NOT NULL,
    description  TEXT         NOT NULL,
    available_on TEXT[]       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  USERS (profile only — passwords are NOT stored here)
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    user_id       VARCHAR(10)  NOT NULL UNIQUE,
    first_name    VARCHAR(50)  NOT NULL,
    surname       VARCHAR(50)  NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(200) NOT NULL UNIQUE,
    phone         VARCHAR(20),
    date_of_birth TIMESTAMPTZ,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted    BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  AUTHENTICATION (separated from users per security rules)
--  Password hashed with bcrypt (salt embedded in hash)
-- ============================================================

CREATE TABLE IF NOT EXISTS user_credentials (
    id              BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    user_id         VARCHAR(10)  NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE RESTRICT,
    password_hash   VARCHAR(255) NOT NULL,
    secret_question VARCHAR(255) NOT NULL,
    secret_answer_hash VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  TRANSACTIONS: National Rail Bookings
-- ============================================================

CREATE TABLE IF NOT EXISTS bookings (
    id                     BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    booking_id             VARCHAR(20)    NOT NULL UNIQUE,
    user_id                VARCHAR(10)    NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    schedule_id            VARCHAR(20)    NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id      VARCHAR(10)    NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10)    NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    travel_date            TIMESTAMPTZ    NOT NULL,
    departure_time         TIMESTAMPTZ    NOT NULL,
    ticket_type            VARCHAR(20)    NOT NULL DEFAULT 'single' REFERENCES ticket_types(ticket_type) ON DELETE RESTRICT,
    fare_class             VARCHAR(20)    NOT NULL CHECK (fare_class IN ('standard', 'first')),
    coach                  VARCHAR(5)     NOT NULL,
    seat_id                VARCHAR(10)    NOT NULL,
    stops_travelled        INTEGER        NOT NULL,
    amount_usd             DECIMAL(10,2)  NOT NULL,
    status                 VARCHAR(20)    NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'completed', 'cancelled')),
    booked_at              TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    travelled_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE,
    FOREIGN KEY (schedule_id, fare_class)
        REFERENCES national_rail_fare_classes(schedule_id, fare_class) ON DELETE RESTRICT,
    FOREIGN KEY (schedule_id, coach, seat_id, fare_class)
        REFERENCES seats(schedule_id, coach, seat_id, fare_class) ON DELETE RESTRICT
);

-- ============================================================
--  TRANSACTIONS: Metro Travel History
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_travel_history (
    id                     BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    trip_id                VARCHAR(20)    NOT NULL UNIQUE,
    user_id                VARCHAR(10)    NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    schedule_id            VARCHAR(20)    NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id      VARCHAR(10)    NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(10)    NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_date            TIMESTAMPTZ    NOT NULL,
    ticket_type            VARCHAR(20)    NOT NULL DEFAULT 'single' REFERENCES ticket_types(ticket_type) ON DELETE RESTRICT,
    day_pass_ref           VARCHAR(20),
    stops_travelled        INTEGER,
    amount_usd             DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    status                 VARCHAR(20)    NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'cancelled', 'refunded')),
    purchased_at           TIMESTAMPTZ,
    travelled_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ============================================================
--  TRANSACTIONS: Payments
-- ============================================================

CREATE TABLE IF NOT EXISTS payments (
    id         BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    payment_id VARCHAR(20)    NOT NULL UNIQUE,
    booking_id VARCHAR(20)    REFERENCES bookings(booking_id) ON DELETE RESTRICT,
    trip_id    VARCHAR(20)    REFERENCES metro_travel_history(trip_id) ON DELETE RESTRICT,
    amount_usd DECIMAL(10,2)  NOT NULL CHECK (amount_usd >= 0),
    method     VARCHAR(20)    NOT NULL CHECK (method IN ('credit_card', 'debit_card', 'ewallet')),
    status     VARCHAR(20)    NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'refunded', 'failed')),
    paid_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN        NOT NULL DEFAULT FALSE,
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL)
        OR (booking_id IS NULL AND trip_id IS NOT NULL)
    )
);

-- ============================================================
--  FEEDBACK
-- ============================================================

CREATE TABLE IF NOT EXISTS feedbacks (
    id           BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    feedback_id  VARCHAR(20)  NOT NULL UNIQUE,
    booking_id   VARCHAR(20)  NOT NULL,
    user_id      VARCHAR(10)  NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    rating       INTEGER      NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment      TEXT,
    submitted_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  POLICIES: Refund
-- ============================================================

CREATE TABLE IF NOT EXISTS refund_policies (
    id           BIGSERIAL    PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    policy_id    VARCHAR(20)  NOT NULL UNIQUE,
    label        VARCHAR(200) NOT NULL,
    network_type VARCHAR(20)  NOT NULL,
    service_type VARCHAR(20),
    notes        TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS refund_policy_windows (
    id                         BIGSERIAL      PRIMARY KEY, -- BIGSERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    policy_id                  VARCHAR(20)    NOT NULL REFERENCES refund_policies(policy_id) ON DELETE RESTRICT,
    window_id                  VARCHAR(20)    NOT NULL UNIQUE,
    label                      VARCHAR(100)   NOT NULL,
    condition_text             TEXT           NOT NULL,
    hours_before_departure_min INTEGER,
    hours_before_departure_max INTEGER,
    refund_percent             INTEGER        NOT NULL DEFAULT 0,
    admin_fee_usd              DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    created_at                 TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted                 BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ============================================================
--  INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_bookings_user_id
    ON bookings(user_id);

CREATE INDEX IF NOT EXISTS idx_bookings_schedule_date
    ON bookings(schedule_id, travel_date);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_seat_date
    ON bookings(schedule_id, travel_date, seat_id)
    WHERE status != 'cancelled' AND is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_bookings_status
    ON bookings(status);

CREATE INDEX IF NOT EXISTS idx_metro_travel_user_id
    ON metro_travel_history(user_id);

CREATE INDEX IF NOT EXISTS idx_payments_booking_id
    ON payments(booking_id);

CREATE INDEX IF NOT EXISTS idx_payments_trip_id
    ON payments(trip_id);

CREATE INDEX IF NOT EXISTS idx_feedbacks_booking_id
    ON feedbacks(booking_id);

CREATE INDEX IF NOT EXISTS idx_nr_stops_schedule_station
    ON national_rail_schedule_stops(schedule_id, station_id);

CREATE INDEX IF NOT EXISTS idx_ms_stops_schedule_station
    ON metro_schedule_stops(schedule_id, station_id);

CREATE INDEX IF NOT EXISTS idx_seats_schedule_class
    ON seats(schedule_id, fare_class);

-- ============================================================
--  UPDATED_AT MAINTENANCE
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_metro_stations_updated_at ON metro_stations;
CREATE TRIGGER trg_metro_stations_updated_at
BEFORE UPDATE ON metro_stations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_national_rail_stations_updated_at ON national_rail_stations;
CREATE TRIGGER trg_national_rail_stations_updated_at
BEFORE UPDATE ON national_rail_stations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_metro_schedules_updated_at ON metro_schedules;
CREATE TRIGGER trg_metro_schedules_updated_at
BEFORE UPDATE ON metro_schedules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_metro_schedule_stops_updated_at ON metro_schedule_stops;
CREATE TRIGGER trg_metro_schedule_stops_updated_at
BEFORE UPDATE ON metro_schedule_stops
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_national_rail_schedules_updated_at ON national_rail_schedules;
CREATE TRIGGER trg_national_rail_schedules_updated_at
BEFORE UPDATE ON national_rail_schedules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_national_rail_schedule_stops_updated_at ON national_rail_schedule_stops;
CREATE TRIGGER trg_national_rail_schedule_stops_updated_at
BEFORE UPDATE ON national_rail_schedule_stops
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_national_rail_fare_classes_updated_at ON national_rail_fare_classes;
CREATE TRIGGER trg_national_rail_fare_classes_updated_at
BEFORE UPDATE ON national_rail_fare_classes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_seats_updated_at ON seats;
CREATE TRIGGER trg_seats_updated_at
BEFORE UPDATE ON seats
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_ticket_types_updated_at ON ticket_types;
CREATE TRIGGER trg_ticket_types_updated_at
BEFORE UPDATE ON ticket_types
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_user_credentials_updated_at ON user_credentials;
CREATE TRIGGER trg_user_credentials_updated_at
BEFORE UPDATE ON user_credentials
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_bookings_updated_at ON bookings;
CREATE TRIGGER trg_bookings_updated_at
BEFORE UPDATE ON bookings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_metro_travel_history_updated_at ON metro_travel_history;
CREATE TRIGGER trg_metro_travel_history_updated_at
BEFORE UPDATE ON metro_travel_history
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_payments_updated_at ON payments;
CREATE TRIGGER trg_payments_updated_at
BEFORE UPDATE ON payments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_feedbacks_updated_at ON feedbacks;
CREATE TRIGGER trg_feedbacks_updated_at
BEFORE UPDATE ON feedbacks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_refund_policies_updated_at ON refund_policies;
CREATE TRIGGER trg_refund_policies_updated_at
BEFORE UPDATE ON refund_policies
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_refund_policy_windows_updated_at ON refund_policy_windows;
CREATE TRIGGER trg_refund_policy_windows_updated_at
BEFORE UPDATE ON refund_policy_windows
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY, -- SERIAL is reasonable for a single-database system with non-extreme data volume and no cross-service ID generation/exposure needs.
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);