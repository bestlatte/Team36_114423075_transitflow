-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
--  INFRASTRUCTURE: Stations
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_stations (
    id                                   BIGSERIAL    PRIMARY KEY,
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
    id                                   BIGSERIAL    PRIMARY KEY,
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
    id                     BIGSERIAL      PRIMARY KEY,
    schedule_id            VARCHAR(20)    NOT NULL UNIQUE,
    line                   VARCHAR(10)    NOT NULL,
    direction              VARCHAR(20)    NOT NULL,
    origin_station_id      VARCHAR(10)    NOT NULL,
    destination_station_id VARCHAR(10)    NOT NULL,
    first_train_time       TIME           NOT NULL,
    last_train_time        TIME           NOT NULL,
    base_fare_usd          DECIMAL(10,2)  NOT NULL,
    per_stop_rate_usd      DECIMAL(10,2)  NOT NULL,
    frequency_min          INTEGER        NOT NULL,
    operates_on            TEXT[]         NOT NULL DEFAULT '{}',
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    id                          BIGSERIAL    PRIMARY KEY,
    schedule_id                 VARCHAR(20)  NOT NULL REFERENCES metro_schedules(schedule_id),
    station_id                  VARCHAR(10)  NOT NULL,
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
    id                     BIGSERIAL      PRIMARY KEY,
    schedule_id            VARCHAR(20)    NOT NULL UNIQUE,
    line                   VARCHAR(10)    NOT NULL,
    service_type           VARCHAR(20)    NOT NULL,
    direction              VARCHAR(20)    NOT NULL,
    origin_station_id      VARCHAR(10)    NOT NULL,
    destination_station_id VARCHAR(10)    NOT NULL,
    first_train_time       TIME           NOT NULL,
    last_train_time        TIME           NOT NULL,
    frequency_min          INTEGER        NOT NULL,
    operates_on            TEXT[]         NOT NULL DEFAULT '{}',
    passed_through_stations TEXT[]        NOT NULL DEFAULT '{}',
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    id                          BIGSERIAL    PRIMARY KEY,
    schedule_id                 VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    station_id                  VARCHAR(10)  NOT NULL,
    stop_order                  INTEGER      NOT NULL,
    travel_time_from_origin_min INTEGER      NOT NULL DEFAULT 0,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, stop_order)
);

CREATE TABLE IF NOT EXISTS national_rail_fare_classes (
    id                BIGSERIAL      PRIMARY KEY,
    schedule_id       VARCHAR(20)    NOT NULL REFERENCES national_rail_schedules(schedule_id),
    fare_class        VARCHAR(20)    NOT NULL,
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
    id          BIGSERIAL    PRIMARY KEY,
    schedule_id VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    coach       VARCHAR(5)   NOT NULL,
    fare_class  VARCHAR(20)  NOT NULL,
    seat_id     VARCHAR(10)  NOT NULL,
    seat_row    INTEGER      NOT NULL,
    seat_column VARCHAR(5)   NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, seat_id)
);

-- ============================================================
--  USERS (profile only — passwords are NOT stored here)
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL    PRIMARY KEY,
    user_id       VARCHAR(10)  NOT NULL UNIQUE,
    first_name    VARCHAR(50)  NOT NULL,
    surname       VARCHAR(50)  NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(200) NOT NULL UNIQUE,
    phone         VARCHAR(20),
    date_of_birth DATE,
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
    id              BIGSERIAL    PRIMARY KEY,
    user_id         VARCHAR(10)  NOT NULL UNIQUE REFERENCES users(user_id),
    password_hash   VARCHAR(255) NOT NULL,
    secret_question VARCHAR(255) NOT NULL,
    secret_answer   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  TRANSACTIONS: National Rail Bookings
-- ============================================================

CREATE TABLE IF NOT EXISTS bookings (
    id                     BIGSERIAL      PRIMARY KEY,
    booking_id             VARCHAR(20)    NOT NULL UNIQUE,
    user_id                VARCHAR(10)    NOT NULL REFERENCES users(user_id),
    schedule_id            VARCHAR(20)    NOT NULL REFERENCES national_rail_schedules(schedule_id),
    origin_station_id      VARCHAR(10)    NOT NULL,
    destination_station_id VARCHAR(10)    NOT NULL,
    travel_date            DATE           NOT NULL,
    departure_time         TIME           NOT NULL,
    ticket_type            VARCHAR(20)    NOT NULL DEFAULT 'single',
    fare_class             VARCHAR(20)    NOT NULL,
    coach                  VARCHAR(5)     NOT NULL,
    seat_id                VARCHAR(10)    NOT NULL,
    stops_travelled        INTEGER        NOT NULL,
    amount_usd             DECIMAL(10,2)  NOT NULL,
    status                 VARCHAR(20)    NOT NULL DEFAULT 'confirmed',
    booked_at              TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    travelled_at           TIMESTAMPTZ,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted             BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ============================================================
--  TRANSACTIONS: Metro Travel History
-- ============================================================

CREATE TABLE IF NOT EXISTS metro_travel_history (
    id                     BIGSERIAL      PRIMARY KEY,
    trip_id                VARCHAR(20)    NOT NULL UNIQUE,
    user_id                VARCHAR(10)    NOT NULL REFERENCES users(user_id),
    schedule_id            VARCHAR(20)    NOT NULL REFERENCES metro_schedules(schedule_id),
    origin_station_id      VARCHAR(10)    NOT NULL,
    destination_station_id VARCHAR(10)    NOT NULL,
    travel_date            DATE           NOT NULL,
    ticket_type            VARCHAR(20)    NOT NULL DEFAULT 'single',
    day_pass_ref           VARCHAR(20),
    stops_travelled        INTEGER,
    amount_usd             DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    status                 VARCHAR(20)    NOT NULL DEFAULT 'completed',
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
    id         BIGSERIAL      PRIMARY KEY,
    payment_id VARCHAR(20)    NOT NULL UNIQUE,
    booking_id VARCHAR(20)    NOT NULL,
    amount_usd DECIMAL(10,2)  NOT NULL,
    method     VARCHAR(20)    NOT NULL,
    status     VARCHAR(20)    NOT NULL DEFAULT 'paid',
    paid_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN        NOT NULL DEFAULT FALSE
);

-- ============================================================
--  FEEDBACK
-- ============================================================

CREATE TABLE IF NOT EXISTS feedbacks (
    id           BIGSERIAL    PRIMARY KEY,
    feedback_id  VARCHAR(20)  NOT NULL UNIQUE,
    booking_id   VARCHAR(20)  NOT NULL,
    user_id      VARCHAR(10)  NOT NULL REFERENCES users(user_id),
    rating       INTEGER      NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment      TEXT,
    submitted_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  POLICIES: Ticket Types
-- ============================================================

CREATE TABLE IF NOT EXISTS ticket_types (
    id           BIGSERIAL    PRIMARY KEY,
    ticket_type  VARCHAR(20)  NOT NULL UNIQUE,
    display_name VARCHAR(50)  NOT NULL,
    description  TEXT         NOT NULL,
    available_on TEXT[]       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted   BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ============================================================
--  POLICIES: Refund
-- ============================================================

CREATE TABLE IF NOT EXISTS refund_policies (
    id           BIGSERIAL    PRIMARY KEY,
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
    id                         BIGSERIAL      PRIMARY KEY,
    policy_id                  VARCHAR(20)    NOT NULL REFERENCES refund_policies(policy_id),
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

CREATE INDEX IF NOT EXISTS idx_bookings_status
    ON bookings(status);

CREATE INDEX IF NOT EXISTS idx_metro_travel_user_id
    ON metro_travel_history(user_id);

CREATE INDEX IF NOT EXISTS idx_payments_booking_id
    ON payments(booking_id);

CREATE INDEX IF NOT EXISTS idx_feedbacks_booking_id
    ON feedbacks(booking_id);

CREATE INDEX IF NOT EXISTS idx_nr_stops_schedule_station
    ON national_rail_schedule_stops(schedule_id, station_id);

CREATE INDEX IF NOT EXISTS idx_ms_stops_schedule_station
    ON metro_schedule_stops(schedule_id, station_id);

CREATE INDEX IF NOT EXISTS idx_seats_schedule_class
    ON seats(schedule_id, fare_class);

-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
