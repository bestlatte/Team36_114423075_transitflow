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

import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

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


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    rows = []
    for s in data:
        rows.append((
            s["station_id"],
            s["name"],
            s["is_interchange_metro"],
            s["is_interchange_national_rail"],
            s.get("interchange_national_rail_station_id")
        ))
    n = insert_many(
        cur, 
        "metro_stations", 
        ["station_id", "name", "is_interchange_metro", "is_interchange_national_rail", "interchange_national_rail_station_id"],
        rows
    )
    
    print(f"  metro_stations: {n} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    rows = []
    for s in data:
        rows.append((
            s["station_id"],
            s["name"],
            s["is_interchange_national_rail"],
            s["is_interchange_metro"],
            s.get("interchange_metro_station_id")
        ))
        
    n = insert_many(
        cur, 
        "national_rail_stations", 
        ["station_id", "name", "is_interchange_national_rail", "is_interchange_metro", "interchange_metro_station_id"], 
        rows
    )
    
    print(f"  national_rail_stations: {n} rows")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    schedules_rows = []
    stops_rows = []
    for s in data:
        schedules_rows.append((
            s["schedule_id"],
            s["line"],
            s["direction"],
            s["origin_station_id"],
            s["destination_station_id"],
            s["first_train_time"],
            s["last_train_time"],
            s["base_fare_usd"],
            s["per_stop_rate_usd"],
            s["frequency_min"],
            s["operates_on"]
        ))
        
        for index, station_id in enumerate(s["stops_in_order"]):
            stop_order = index + 1
            travel_time = s["travel_time_from_origin_min"][station_id]
            
            stops_rows.append((
                s["schedule_id"], 
                station_id,
                stop_order,
                travel_time
            ))
            
    n_schedules = insert_many(
        cur, 
        "metro_schedules", 
        ["schedule_id", "line", "direction", "origin_station_id", "destination_station_id", 
         "first_train_time", "last_train_time", "base_fare_usd", "per_stop_rate_usd", 
         "frequency_min", "operates_on"], 
        schedules_rows
    )
    
    n_stops = insert_many(
        cur, 
        "metro_schedule_stops", 
        ["schedule_id", "station_id", "stop_order", "travel_time_min"], 
        stops_rows
    )
    
    print(f"  metro_schedules: {n_schedules} rows")
    print(f"  metro_schedule_stops: {n_stops} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    schedules_rows = []
    stops_rows = []
    for s in data:
        # 1. 整理主檔資料
        schedules_rows.append((
            s["schedule_id"],
            s["line"],
            s["service_type"],
            s["direction"],
            s["origin_station_id"],
            s["destination_station_id"],
            s["first_train_time"],
            s["last_train_time"],
            json.dumps(s["fare_classes"]), # 把字典轉換成 JSON 字串，才能存入 JSONB 欄位
            s["frequency_min"],
            s["operates_on"] 
        ))
        
        # 2. 整理明細檔資料
        for index, station_id in enumerate(s["stops_in_order"]):
            stop_order = index + 1
            travel_time = s["travel_time_from_origin_min"][station_id]
            
            stops_rows.append((
                s["schedule_id"],
                station_id,
                stop_order,
                travel_time
            ))
            
    # 3. 寫入資料庫
    n_schedules = insert_many(
        cur, 
        "national_rail_schedules", 
        ["schedule_id", "line", "service_type", "direction", "origin_station_id", "destination_station_id", 
         "first_train_time", "last_train_time", "fare_classes", "frequency_min", "operates_on"], 
        schedules_rows
    )
    
    n_stops = insert_many(
        cur, 
        "national_rail_schedule_stops", 
        ["schedule_id", "station_id", "stop_order", "travel_time_min"], 
        stops_rows
    )
    
    print(f"  national_rail_schedules: {n_schedules} rows")
    print(f"  national_rail_schedule_stops: {n_stops} rows")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    layouts_rows = []
    seats_rows = []
    for layout in data:
        # 1. 整理主檔資料
        layouts_rows.append((
            layout["layout_id"],
            layout["schedule_id"]
        ))
        
        # 2. 雙層迴圈：先拆車廂，再拆座位
        for coach in layout["coaches"]:
            for seat in coach["seats"]:
                seats_rows.append((
                    layout["layout_id"],
                    coach["coach"],
                    coach["fare_class"],
                    seat["seat_id"],
                    seat["row"],      # 對應 SQL 的 seat_row
                    seat["column"]    # 對應 SQL 的 seat_column
                ))
                
    # 3. 寫入資料庫
    n_layouts = insert_many(
        cur, 
        "national_rail_seat_layouts", 
        ["layout_id", "schedule_id"], 
        layouts_rows
    )
    
    n_seats = insert_many(
        cur, 
        "national_rail_seats", 
        ["layout_id", "coach", "fare_class", "seat_id", "seat_row", "seat_column"], 
        seats_rows
    )
    
    print(f"  national_rail_seat_layouts: {n_layouts} rows")
    print(f"  national_rail_seats: {n_seats} rows")


def seed_users(cur):
    data = load("registered_users.json")
    rows = []
    for u in data:
        rows.append((
            u["user_id"],
            u["full_name"],
            u["email"],
            u["password"],
            u.get("phone"),
            u.get("date_of_birth"),
            u.get("secret_question"),
            u.get("secret_answer"),
            u.get("registered_at"),
            u.get("is_active", True)
        ))
        
    n = insert_many(
        cur, 
        "registered_users", 
        ["user_id", "full_name", "email", "password", "phone", "date_of_birth", "secret_question", "secret_answer", "registered_at", "is_active"], 
        rows
    )
    
    print(f"  registered_users: {n} rows")

def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = []
    for b in data:
        rows.append((
            b["booking_id"],
            b["user_id"],
            b["schedule_id"],
            b["origin_station_id"],
            b["destination_station_id"],
            b["travel_date"],
            b.get("departure_time"),
            b["ticket_type"],
            b["fare_class"],
            b.get("coach"),
            b.get("seat_id"),
            b.get("stops_travelled"),
            b["amount_usd"],
            b["status"],
            b["booked_at"],
            b.get("travelled_at") # 有些被取消的票沒有搭乘時間，用 get() 讓它變成 None (也就是 SQL 的 NULL)
        ))
        
    n = insert_many(
        cur, 
        "national_rail_bookings", 
        ["booking_id", "user_id", "schedule_id", "origin_station_id", "destination_station_id", 
         "travel_date", "departure_time", "ticket_type", "fare_class", "coach", "seat_id", 
         "stops_travelled", "amount_usd", "status", "booked_at", "travelled_at"], 
        rows
    )
    
    print(f"  national_rail_bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = []
    for m in data:
        rows.append((
            m["trip_id"],
            m["user_id"],
            m["schedule_id"],
            m["origin_station_id"],
            m["destination_station_id"],
            m["travel_date"],
            m["ticket_type"],
            m.get("day_pass_ref"),
            m.get("stops_travelled"),
            m["amount_usd"],
            m["status"],
            m.get("purchased_at"), # 一日票的後續搭乘可能沒有購買時間，用 get() 處理
            m.get("travelled_at")
        ))
        
    n = insert_many(
        cur, 
        "metro_travels", 
        ["trip_id", "user_id", "schedule_id", "origin_station_id", "destination_station_id", 
         "travel_date", "ticket_type", "day_pass_ref", "stops_travelled", "amount_usd", 
         "status", "purchased_at", "travelled_at"], 
        rows
    )
    
    print(f"  metro_travels: {n} rows")


def seed_payments(cur):
    data = load("payments.json")
    rows = []
    for p in data:
        rows.append((
            p["payment_id"],
            p["booking_id"],
            p["amount_usd"],
            p["method"],
            p["status"],
            p.get("paid_at")
        ))
        
    n = insert_many(
        cur, 
        "payments", 
        ["payment_id", "booking_id", "amount_usd", "method", "status", "paid_at"], 
        rows
    )
    
    print(f"  payments: {n} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    rows = []
    for f in data:
        rows.append((
            f["feedback_id"],
            f["booking_id"],
            f["user_id"],
            f["rating"],
            f.get("comment"),
            f.get("submitted_at")
        ))
        
    n = insert_many(
        cur, 
        "feedback", 
        ["feedback_id", "booking_id", "user_id", "rating", "comment", "submitted_at"], 
        rows
    )
    
    print(f"  feedback: {n} rows")
    pass


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
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
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
