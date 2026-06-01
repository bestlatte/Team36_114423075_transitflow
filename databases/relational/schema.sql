-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================


-- 1. 建立捷運車站資料表 (metro_stations)
CREATE TABLE metro_stations (
    station_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    is_interchange_metro BOOLEAN DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN DEFAULT FALSE,
    interchange_national_rail_station_id VARCHAR(10)
);

-- 2. 建立英國鐵路車站資料表 (national_rail_stations)
CREATE TABLE national_rail_stations (
    station_id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    is_interchange_national_rail BOOLEAN DEFAULT FALSE,
    is_interchange_metro BOOLEAN DEFAULT FALSE,
    interchange_metro_station_id VARCHAR(10)
);

-- 3. 建立捷運時刻表主檔 (metro_schedules)
CREATE TABLE metro_schedules (
    schedule_id VARCHAR(30) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    direction VARCHAR(20),
    origin_station_id VARCHAR(10),
    destination_station_id VARCHAR(10),
    first_train_time TIME,
    last_train_time TIME,
    base_fare_usd NUMERIC(5,2),
    per_stop_rate_usd NUMERIC(5,2),
    frequency_min INTEGER,
    operates_on TEXT[] 
);

-- 4. 建立捷運時刻表明細 (metro_schedule_stops)
CREATE TABLE metro_schedule_stops (
    schedule_id VARCHAR(30) REFERENCES metro_schedules(schedule_id),
    station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    stop_order INTEGER NOT NULL,
    travel_time_min INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

-- 5. 建立英國鐵路時刻表主檔 (national_rail_schedules)
CREATE TABLE national_rail_schedules (
    schedule_id VARCHAR(30) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    service_type VARCHAR(20),
    direction VARCHAR(20),
    origin_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    first_train_time TIME,
    last_train_time TIME,
    fare_classes JSONB, -- 使用 JSONB 型態來儲存複雜的票價結構
    frequency_min INTEGER,
    operates_on TEXT[]
);

-- 6. 建立英國鐵路時刻表停靠站明細 (national_rail_schedule_stops)
CREATE TABLE national_rail_schedule_stops (
    schedule_id VARCHAR(30) REFERENCES national_rail_schedules(schedule_id),
    station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    stop_order INTEGER NOT NULL,
    travel_time_min INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

-- 7. 建立英國鐵路座位配置主檔 (national_rail_seat_layouts)
CREATE TABLE national_rail_seat_layouts (
    layout_id VARCHAR(10) PRIMARY KEY,
    schedule_id VARCHAR(30) REFERENCES national_rail_schedules(schedule_id)
);

-- 8. 建立英國鐵路座位明細 (national_rail_seats)
CREATE TABLE national_rail_seats (
    layout_id VARCHAR(10) REFERENCES national_rail_seat_layouts(layout_id),
    coach VARCHAR(5) NOT NULL,
    fare_class VARCHAR(20) NOT NULL,
    seat_id VARCHAR(10) NOT NULL,
    seat_row INTEGER NOT NULL,
    seat_column VARCHAR(5) NOT NULL,
    PRIMARY KEY (layout_id, coach, seat_id)
);

-- 9. 建立註冊使用者資料表 (registered_users)
CREATE TABLE registered_users (
    user_id VARCHAR(10) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL, -- 信箱通常不能重複，所以加上 UNIQUE
    password VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    date_of_birth DATE, -- 只有日期 (例如 1990-03-14)
    secret_question VARCHAR(255),
    secret_answer VARCHAR(255),
    registered_at TIMESTAMP WITH TIME ZONE, -- 包含精確時間與時區 (例如 2023-01-10T09:00:00Z)
    is_active BOOLEAN DEFAULT TRUE
);

-- 10. 建立英國鐵路訂票紀錄 (national_rail_bookings)
CREATE TABLE national_rail_bookings (
    booking_id VARCHAR(10) PRIMARY KEY,
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    schedule_id VARCHAR(30) REFERENCES national_rail_schedules(schedule_id),
    origin_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id),
    travel_date DATE NOT NULL,
    departure_time TIME,
    ticket_type VARCHAR(20),
    fare_class VARCHAR(20),
    coach VARCHAR(5),
    seat_id VARCHAR(10),
    stops_travelled INTEGER,
    amount_usd NUMERIC(8,2),
    status VARCHAR(20),
    booked_at TIMESTAMP WITH TIME ZONE,
    travelled_at TIMESTAMP WITH TIME ZONE
);

-- 11. 建立捷運搭乘紀錄 (metro_travels)
CREATE TABLE metro_travels (
    trip_id VARCHAR(10) PRIMARY KEY,
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    schedule_id VARCHAR(30) REFERENCES metro_schedules(schedule_id),
    origin_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(10) REFERENCES metro_stations(station_id),
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(20) NOT NULL,
    day_pass_ref VARCHAR(10), 
    stops_travelled INTEGER,
    amount_usd NUMERIC(8,2),
    status VARCHAR(20),
    purchased_at TIMESTAMP WITH TIME ZONE,
    travelled_at TIMESTAMP WITH TIME ZONE
);

-- 12. 建立付款紀錄表 (payments)
CREATE TABLE payments (
    payment_id VARCHAR(10) PRIMARY KEY,
    booking_id VARCHAR(10) NOT NULL, -- 這裡不設 REFERENCES 是因為它可能對應到鐵路(BK開頭)或捷運(MT開頭)
    amount_usd NUMERIC(8,2) NOT NULL,
    method VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    paid_at TIMESTAMP WITH TIME ZONE
);

-- 13. 建立使用者回饋表 (feedback)
CREATE TABLE feedback (
    feedback_id VARCHAR(10) PRIMARY KEY,
    booking_id VARCHAR(10) NOT NULL,
    user_id VARCHAR(10) REFERENCES registered_users(user_id),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5), -- 設定檢查條件，分數只能在 1 到 5 之間
    comment TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE
);
-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS policy_documents_hnsw ON policy_documents USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- # TASK 6 EXTENSION: Station Closures Log (即時車站封閉紀錄)
-- ============================================================

CREATE TABLE IF NOT EXISTS station_closures (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(10) NOT NULL,
    reason TEXT NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reopened_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_station_closures_active 
    ON station_closures(is_active);
