"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    sql = """
        SELECT s.schedule_id, s.line, s.service_type, s.direction, 
               TO_CHAR(s.first_train_time, 'HH24:MI') as first_train_time, 
               TO_CHAR(s.last_train_time, 'HH24:MI') as last_train_time, 
               s.frequency_min
        FROM national_rail_schedules s
        JOIN national_rail_schedule_stops o ON s.schedule_id = o.schedule_id
        JOIN national_rail_schedule_stops d ON s.schedule_id = d.schedule_id
        WHERE o.station_id = %s AND d.station_id = %s AND o.stop_order < d.stop_order
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]

def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    sql = "SELECT fare_classes FROM national_rail_schedules WHERE schedule_id = %s"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (schedule_id,))
            res = cur.fetchone()
            if not res or not res[0]: return None
            fares = res[0].get(fare_class)
            if not fares: return None
            base = float(fares['base_fare_usd'])
            per_stop = float(fares['per_stop_rate_usd'])
            return {
                "fare_class": fare_class,
                "base_fare_usd": base,
                "per_stop_rate_usd": per_stop,
                "total_fare_usd": round(base + (per_stop * stops_travelled), 2)
            }


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    sql = """
        SELECT s.schedule_id, s.line, s.direction, 
               TO_CHAR(s.first_train_time, 'HH24:MI') as first_train_time, 
               TO_CHAR(s.last_train_time, 'HH24:MI') as last_train_time, 
               s.frequency_min
        FROM metro_schedules s
        JOIN metro_schedule_stops o ON s.schedule_id = o.schedule_id
        JOIN metro_schedule_stops d ON s.schedule_id = d.schedule_id
        WHERE o.station_id = %s AND d.station_id = %s AND o.stop_order < d.stop_order
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    sql = "SELECT base_fare_usd, per_stop_rate_usd FROM metro_schedules WHERE schedule_id = %s"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            res = cur.fetchone()
            if not res: return None
            base = float(res['base_fare_usd'])
            per_stop = float(res['per_stop_rate_usd'])
            return {
                "base_fare_usd": base,
                "per_stop_rate_usd": per_stop,
                "total_fare_usd": round(base + (per_stop * stops_travelled), 2)
            }

# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    sql = """
        SELECT s.seat_id, s.coach, s.seat_row AS row, s.seat_column AS column
        FROM national_rail_seat_layouts l
        JOIN national_rail_seats s ON l.layout_id = s.layout_id
        WHERE l.schedule_id = %s AND s.fare_class = %s
        AND s.seat_id NOT IN (
            SELECT seat_id FROM national_rail_bookings
            WHERE schedule_id = %s AND travel_date = %s AND status IN ('completed', 'confirmed') AND seat_id IS NOT NULL
        )
        ORDER BY s.seat_row, s.seat_column
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class, schedule_id, travel_date))
            return [dict(row) for row in cur.fetchall()]


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email."""
    sql = """
        SELECT user_id, full_name, email, phone, date_of_birth, registered_at
        FROM registered_users
        WHERE email = %s AND is_active = true
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            result = cur.fetchone()
            if result:
                # 把日期時間轉換成字串，方便前端顯示
                profile = dict(result)
                if profile['date_of_birth']:
                    profile['date_of_birth'] = profile['date_of_birth'].strftime("%Y-%m-%d")
                if profile['registered_at']:
                    profile['registered_at'] = profile['registered_at'].strftime("%Y-%m-%d %H:%M:%S")
                return profile
            return None


def query_user_bookings(user_email: str) -> dict:
    sql_user = "SELECT user_id FROM registered_users WHERE email = %s"
    sql_nr = """
        SELECT booking_id, schedule_id, origin_station_id, destination_station_id, 
               TO_CHAR(travel_date, 'YYYY-MM-DD') as travel_date, ticket_type, fare_class, amount_usd, status
        FROM national_rail_bookings WHERE user_id = %s ORDER BY travel_date DESC
    """
    sql_mt = """
        SELECT trip_id as booking_id, schedule_id, origin_station_id, destination_station_id, 
               TO_CHAR(travel_date, 'YYYY-MM-DD') as travel_date, ticket_type, amount_usd, status
        FROM metro_travels WHERE user_id = %s ORDER BY travel_date DESC
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql_user, (user_email,))
            user = cur.fetchone()
            if not user: return {'national_rail': [], 'metro': []}
            
            cur.execute(sql_nr, (user['user_id'],))
            nr_bookings = [dict(r) for r in cur.fetchall()]
            
            cur.execute(sql_mt, (user['user_id'],))
            mt_bookings = [dict(r) for r in cur.fetchall()]
            
            return {'national_rail': nr_bookings, 'metro': mt_bookings}


def query_payment_info(booking_id: str) -> Optional[dict]:
    sql = "SELECT method, status, amount_usd, TO_CHAR(paid_at, 'YYYY-MM-DD HH24:MI:SS') as paid_at FROM payments WHERE booking_id = %s"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id,))
            res = cur.fetchone()
            return dict(res) if res else None

# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
   try:
        with _connect() as conn:
            with conn.cursor() as cur:
                # 簡單計算站數 (為了算錢)
                cur.execute("SELECT (d.stop_order - o.stop_order) FROM national_rail_schedule_stops o JOIN national_rail_schedule_stops d ON o.schedule_id = d.schedule_id WHERE o.schedule_id = %s AND o.station_id = %s AND d.station_id = %s", (schedule_id, origin_station_id, destination_station_id))
                stops_res = cur.fetchone()
                if not stops_res: return False, "Invalid stations."
                stops = stops_res[0]
                
                cur.execute("SELECT fare_classes FROM national_rail_schedules WHERE schedule_id = %s", (schedule_id,))
                fares = cur.fetchone()[0].get(fare_class)
                amount = float(fares['base_fare_usd']) + (float(fares['per_stop_rate_usd']) * stops)
                if ticket_type == "return": amount *= 2
                
                coach = None
                if seat_id != 'any':
                    cur.execute("SELECT coach FROM national_rail_seats WHERE layout_id = (SELECT layout_id FROM national_rail_seat_layouts WHERE schedule_id=%s) AND seat_id=%s", (schedule_id, seat_id))
                    coach_res = cur.fetchone()
                    if coach_res: coach = coach_res[0]
                
                booking_id = _gen_booking_id()
                now = datetime.now(timezone.utc)
                sql_insert = """
                    INSERT INTO national_rail_bookings (booking_id, user_id, schedule_id, origin_station_id, destination_station_id, travel_date, ticket_type, fare_class, coach, seat_id, stops_travelled, amount_usd, status, booked_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cur.execute(sql_insert, (booking_id, user_id, schedule_id, origin_station_id, destination_station_id, travel_date, ticket_type, fare_class, coach, seat_id if seat_id != 'any' else None, stops, amount, 'confirmed', now))
                return True, {"booking_id": booking_id, "amount_usd": amount, "status": "confirmed"}
   except Exception as e:
        return False, str(e)


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    sql_check = "SELECT status, amount_usd FROM national_rail_bookings WHERE booking_id = %s AND user_id = %s"
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_check, (booking_id, user_id))
                res = cur.fetchone()
                if not res: return False, "Booking not found."
                if res[0] == 'cancelled': return False, "Already cancelled."
                
                cur.execute("UPDATE national_rail_bookings SET status = 'cancelled' WHERE booking_id = %s", (booking_id,))
                return True, {"refund_amount_usd": float(res[1]), "note": "Cancelled successfully."}
    except Exception as e:
        return False, str(e)


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    sql = """
        INSERT INTO registered_users (user_id, full_name, email, password, date_of_birth, secret_question, secret_answer, registered_at, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true)
    """
    user_id = "RU" + "".join(random.choices(string.digits, k=4))
    dob = f"{year_of_birth}-01-01"
    now = datetime.now(timezone.utc)
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id, f"{first_name} {surname}", email, password, dob, secret_question, secret_answer, now))
                return True, user_id
    except Exception as e:
        return False, str(e)


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    sql = """
        SELECT user_id, email, full_name, phone, date_of_birth, is_active
        FROM registered_users
        WHERE email = %s AND password = %s AND is_active = true
    """
    
    # 呼叫檔案上方的 _connect() 來連線資料庫
    with _connect() as conn:
        # 使用 RealDictCursor，這樣撈出來的資料就會直接是字典格式
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email, password))
            result = cur.fetchone() # 抓取符合條件的第一筆資料
            
            if result:
                user_dict = dict(result)
                
               
                name_parts = user_dict["full_name"].split(" ", 1)
                user_dict["first_name"] = name_parts[0]
                user_dict["surname"] = name_parts[1] if len(name_parts) > 1 else ""
                
                return user_dict # 登入成功，回傳使用者資料
            
            return None # 登入失敗 (帳號密碼錯誤或找不到人)，回傳 None


def get_user_secret_question(email: str) -> Optional[str]:
    sql = "SELECT secret_question FROM registered_users WHERE email = %s"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            res = cur.fetchone()
            return res[0] if res else None


def verify_secret_answer(email: str, answer: str) -> bool:
    sql = "SELECT secret_answer FROM registered_users WHERE email = %s"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            res = cur.fetchone()
            return bool(res and res[0] and res[0].lower() == answer.lower())


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    sql = "UPDATE registered_users SET password = %s WHERE email = %s"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_password, email))
            return cur.rowcount > 0


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
