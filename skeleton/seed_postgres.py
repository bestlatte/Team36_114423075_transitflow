"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""


import json
import os
import sys
from datetime import datetime, timezone

import bcrypt
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


def upsert_many(cur, table, columns, rows, conflict_columns):
    """Bulk insert/update so reseeding refreshes mock data changes."""
    if not rows:
        return 0
    update_columns = [c for c in columns if c not in conflict_columns]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {assignments}, "
        f"updated_at = NOW(), is_deleted = FALSE"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _normalize_secret_answer(answer: str) -> str:
    return answer.strip().lower()


def _service_time_at_utc(time_text: str) -> datetime:
    """Represent schedule-only times as UTC timestamps on a fixed service date."""
    parsed = datetime.strptime(time_text, "%H:%M").time()
    return datetime(2000, 1, 1, parsed.hour, parsed.minute, tzinfo=timezone.utc)


def _date_at_utc(date_text: str) -> datetime:
    parsed = datetime.strptime(date_text, "%Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc)


def _combine_date_time_at_utc(date_text: str, time_text: str) -> datetime:
    parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
    parsed_time = datetime.strptime(time_text, "%H:%M").time()
    return datetime(
        parsed_date.year,
        parsed_date.month,
        parsed_date.day,
        parsed_time.hour,
        parsed_time.minute,
        tzinfo=timezone.utc,
    )


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    columns = [
        "station_id", "name", "lines",
        "is_interchange_metro", "interchange_metro_lines",
        "is_interchange_national_rail", "interchange_national_rail_station_id",
    ]
    rows = [
        (
            d["station_id"],
            d["name"],
            d.get("lines", []),
            d.get("is_interchange_metro", False),
            d.get("interchange_metro_lines", []),
            d.get("is_interchange_national_rail", False),
            d.get("interchange_national_rail_station_id"),
        )
        for d in data
    ]
    n = insert_many(cur, "metro_stations", columns, rows)
    print(f"  metro_stations: {n} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    columns = [
        "station_id", "name", "lines",
        "is_interchange_national_rail", "interchange_national_rail_lines",
        "is_interchange_metro", "interchange_metro_station_id",
    ]
    rows = [
        (
            d["station_id"],
            d["name"],
            d.get("lines", []),
            d.get("is_interchange_national_rail", False),
            d.get("interchange_national_rail_lines", []),
            d.get("is_interchange_metro", False),
            d.get("interchange_metro_station_id"),
        )
        for d in data
    ]
    n = insert_many(cur, "national_rail_stations", columns, rows)
    print(f"  national_rail_stations: {n} rows")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")

    sched_cols = [
        "schedule_id", "line", "direction",
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time",
        "base_fare_usd", "per_stop_rate_usd",
        "frequency_min", "operates_on",
    ]
    sched_rows = [
        (
            d["schedule_id"], d["line"], d["direction"],
            d["origin_station_id"], d["destination_station_id"],
            _service_time_at_utc(d["first_train_time"]),
            _service_time_at_utc(d["last_train_time"]),
            d["base_fare_usd"], d["per_stop_rate_usd"],
            d["frequency_min"], d.get("operates_on", []),
        )
        for d in data
    ]
    n = insert_many(cur, "metro_schedules", sched_cols, sched_rows)
    print(f"  metro_schedules: {n} rows")

    stop_cols = ["schedule_id", "station_id",
                 "stop_order", "travel_time_from_origin_min"]
    stop_rows = []
    for d in data:
        times = d["travel_time_from_origin_min"]
        for order, sid in enumerate(d["stops_in_order"], start=1):
            stop_rows.append((d["schedule_id"], sid, order, times[sid]))
    n = insert_many(cur, "metro_schedule_stops", stop_cols, stop_rows)
    print(f"  metro_schedule_stops: {n} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")

    sched_cols = [
        "schedule_id", "line", "service_type", "direction",
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time",
        "frequency_min", "operates_on",
    ]
    sched_rows = [
        (
            d["schedule_id"], d["line"], d["service_type"], d["direction"],
            d["origin_station_id"], d["destination_station_id"],
            _service_time_at_utc(d["first_train_time"]),
            _service_time_at_utc(d["last_train_time"]),
            d["frequency_min"], d.get("operates_on", []),
        )
        for d in data
    ]
    n = upsert_many(
        cur,
        "national_rail_schedules",
        sched_cols,
        sched_rows,
        ["schedule_id"],
    )
    print(f"  national_rail_schedules: {n} rows")

    stop_cols = ["schedule_id", "station_id",
                 "stop_order", "travel_time_from_origin_min"]
    stop_rows = []
    for d in data:
        times = d["travel_time_from_origin_min"]
        for order, sid in enumerate(d["stops_in_order"], start=1):
            stop_rows.append((d["schedule_id"], sid, order, times[sid]))
    n = upsert_many(
        cur,
        "national_rail_schedule_stops",
        stop_cols,
        stop_rows,
        ["schedule_id", "stop_order"],
    )
    print(f"  national_rail_schedule_stops: {n} rows")

    fare_cols = ["schedule_id", "fare_class",
                 "base_fare_usd", "per_stop_rate_usd"]
    fare_rows = []
    for d in data:
        for fc, rates in d["fare_classes"].items():
            fare_rows.append((
                d["schedule_id"], fc,
                rates["base_fare_usd"], rates["per_stop_rate_usd"],
            ))
    n = upsert_many(
        cur,
        "national_rail_fare_classes",
        fare_cols,
        fare_rows,
        ["schedule_id", "fare_class"],
    )
    print(f"  national_rail_fare_classes: {n} rows")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    schedules = load("national_rail_schedules.json")
    cols = ["schedule_id", "coach", "fare_class",
            "seat_id", "seat_row", "seat_column"]
    rows = []

    layouts_by_schedule = {layout["schedule_id"]: layout for layout in data}
    default_coaches = data[0]["coaches"] if data else []
    for schedule in schedules:
        if schedule["schedule_id"] not in layouts_by_schedule:
            layouts_by_schedule[schedule["schedule_id"]] = {
                "schedule_id": schedule["schedule_id"],
                "coaches": default_coaches,
            }

    for layout in layouts_by_schedule.values():
        sid = layout["schedule_id"]
        for coach_info in layout["coaches"]:
            coach = coach_info["coach"]
            fc = coach_info["fare_class"]
            for seat in coach_info["seats"]:
                rows.append((
                    sid, coach, fc,
                    seat["seat_id"], seat["row"], seat["column"],
                ))
    n = upsert_many(cur, "seats", cols, rows, ["schedule_id", "seat_id"])
    print(f"  seats: {n} rows")


def seed_users(cur):
    data = load("registered_users.json")

    user_cols = [
        "user_id", "first_name", "surname", "full_name",
        "email", "phone", "date_of_birth", "is_active", "registered_at",
    ]
    cred_cols = ["user_id", "password_hash",
                 "secret_question", "secret_answer_hash"]

    user_rows = []
    cred_rows = []
    for d in data:
        parts = d["full_name"].split(" ", 1)
        first_name = parts[0]
        surname = parts[1] if len(parts) > 1 else ""

        user_rows.append((
            d["user_id"], first_name, surname, d["full_name"],
            d["email"], d.get("phone"),
            _date_at_utc(d["date_of_birth"]) if d.get(
                "date_of_birth") else None,
            d.get("is_active", True), d["registered_at"],
        ))

        cred_rows.append((
            d["user_id"],
            _hash_password(d["password"]),
            d["secret_question"],
            _hash_password(_normalize_secret_answer(d["secret_answer"])),
        ))

    n = insert_many(cur, "users", user_cols, user_rows)
    print(f"  users: {n} rows")

    n = insert_many(cur, "user_credentials", cred_cols, cred_rows)
    print(f"  user_credentials: {n} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    cols = [
        "booking_id", "user_id", "schedule_id",
        "origin_station_id", "destination_station_id",
        "travel_date", "departure_time", "ticket_type", "fare_class",
        "coach", "seat_id", "stops_travelled", "amount_usd",
        "status", "booked_at", "travelled_at",
    ]
    rows = [
        (
            d["booking_id"], d["user_id"], d["schedule_id"],
            d["origin_station_id"], d["destination_station_id"],
            _date_at_utc(d["travel_date"]),
            _combine_date_time_at_utc(d["travel_date"], d["departure_time"]),
            d["ticket_type"], d["fare_class"],
            d["coach"], d["seat_id"], d["stops_travelled"], d["amount_usd"],
            d["status"], d["booked_at"], d.get("travelled_at"),
        )
        for d in data
    ]
    n = insert_many(cur, "bookings", cols, rows)
    print(f"  bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    cols = [
        "trip_id", "user_id", "schedule_id",
        "origin_station_id", "destination_station_id",
        "travel_date", "ticket_type", "day_pass_ref",
        "stops_travelled", "amount_usd", "status",
        "purchased_at", "travelled_at",
    ]
    rows = [
        (
            d["trip_id"], d["user_id"], d["schedule_id"],
            d["origin_station_id"], d["destination_station_id"],
            _date_at_utc(d["travel_date"]), d["ticket_type"], d.get(
                "day_pass_ref"),
            d.get("stops_travelled"), d["amount_usd"], d["status"],
            d.get("purchased_at"), d.get("travelled_at"),
        )
        for d in data
    ]
    n = insert_many(cur, "metro_travel_history", cols, rows)
    print(f"  metro_travel_history: {n} rows")


def seed_payments(cur):
    data = load("payments.json")
    cols = ["payment_id", "booking_id", "trip_id",
            "amount_usd", "method", "status", "paid_at"]
    rows = []
    for d in data:
        transaction_id = d["booking_id"]
        booking_id = transaction_id if transaction_id.startswith(
            "BK") else None
        trip_id = transaction_id if transaction_id.startswith("MT") else None
        rows.append((
            d["payment_id"],
            booking_id,
            trip_id,
            d["amount_usd"],
            d["method"],
            d["status"],
            d["paid_at"],
        ))
    n = insert_many(cur, "payments", cols, rows)
    print(f"  payments: {n} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    cols = ["feedback_id", "booking_id", "user_id",
            "rating", "comment", "submitted_at"]
    rows = [
        (d["feedback_id"], d["booking_id"], d["user_id"],
         d["rating"], d.get("comment"), d["submitted_at"])
        for d in data
    ]
    n = insert_many(cur, "feedbacks", cols, rows)
    print(f"  feedbacks: {n} rows")


def seed_ticket_types(cur):
    data = load("ticket_types.json")
    cols = ["ticket_type", "display_name", "description", "available_on"]
    rows = [
        (d["ticket_type"], d["display_name"],
         d["description"], d.get("available_on", []))
        for d in data
    ]
    n = insert_many(cur, "ticket_types", cols, rows)
    print(f"  ticket_types: {n} rows")


def seed_refund_policies(cur):
    data = load("refund_policy.json")

    policy_cols = ["policy_id", "label",
                   "network_type", "service_type", "notes"]
    window_cols = [
        "policy_id", "window_id", "label", "condition_text",
        "hours_before_departure_min", "hours_before_departure_max",
        "refund_percent", "admin_fee_usd",
    ]

    policy_rows = []
    window_rows = []

    for d in data:
        applies = d.get("applies_to", {})
        notes_parts = []
        if d.get("return_ticket_notes"):
            notes_parts.append(d["return_ticket_notes"])
        if d.get("no_show_policy"):
            notes_parts.append(d["no_show_policy"])
        if d.get("notes"):
            notes_parts.append(d["notes"])

        policy_rows.append((
            d["policy_id"],
            d["label"],
            applies.get("network_type", "all"),
            applies.get("service_type"),
            " | ".join(notes_parts) if notes_parts else None,
        ))

        for w in d.get("cancellation_windows", []):
            window_rows.append((
                d["policy_id"],
                w["window_id"],
                w["label"],
                w.get("condition", w.get("condition_text", "")),
                w.get("hours_before_departure_min"),
                w.get("hours_before_departure_max"),
                w.get("refund_percent", 0),
                w.get("admin_fee_usd", 0.00),
            ))

    n = insert_many(cur, "refund_policies", policy_cols, policy_rows)
    print(f"  refund_policies: {n} rows")

    n = insert_many(cur, "refund_policy_windows", window_cols, window_rows)
    print(f"  refund_policy_windows: {n} rows")


def reset_id_sequences(cur):
    """Keep BIGSERIAL sequences aligned after conflict-heavy reseeding."""
    tables = [
        "metro_stations",
        "national_rail_stations",
        "metro_schedules",
        "metro_schedule_stops",
        "national_rail_schedules",
        "national_rail_schedule_stops",
        "national_rail_fare_classes",
        "seats",
        "ticket_types",
        "users",
        "user_credentials",
        "bookings",
        "metro_travel_history",
        "payments",
        "feedbacks",
        "refund_policies",
        "refund_policy_windows",
    ]
    for table in tables:
        cur.execute(
            sql.SQL(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE((SELECT MAX(id) FROM {}), 1),
                    COALESCE((SELECT MAX(id) FROM {}), 0) > 0
                )
                """
            ).format(sql.Identifier(table), sql.Identifier(table)),
            (table,),
        )
    print("  id sequences: reset to current MAX(id)")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_ticket_types(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        seed_refund_policies(cur)
        reset_id_sequences(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
