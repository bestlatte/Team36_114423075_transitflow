"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import json
import random
import string
from contextlib import contextmanager
from datetime import datetime, time, timezone
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


@contextmanager
def _connect():
    """Yield a new psycopg2 connection with autocommit enabled, then close it."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def _tx_connect():
    """Return a new psycopg2 connection with autocommit OFF for transactions."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    return conn


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


def _fail_transaction(conn, message: str) -> tuple[bool, str]:
    conn.rollback()
    return False, message


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _date_at_utc(date_text: str) -> datetime:
    parsed = datetime.strptime(date_text, "%Y-%m-%d")
    return parsed.replace(tzinfo=timezone.utc)


def _combine_travel_date_and_service_time(date_text: str, service_time) -> datetime:
    parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
    if isinstance(service_time, datetime):
        parsed_time = service_time.timetz()
    else:
        parsed_time = datetime.strptime(str(service_time)[:5], "%H:%M").time()
    return datetime(
        parsed_date.year,
        parsed_date.month,
        parsed_date.day,
        parsed_time.hour,
        parsed_time.minute,
        tzinfo=timezone.utc,
    )


def _time_text(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    return str(value)


def _date_text(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _weekday_code(date_text: str) -> str:
    return _date_at_utc(date_text).strftime("%a").lower()


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """Return schedules that serve both stations in the correct direction."""
    sql = """
        SELECT
            nrs.schedule_id,
            COUNT(s.seat_id) - COUNT(b.booking_id) AS available_seats
        FROM national_rail_schedules nrs
        JOIN national_rail_schedule_stops o_stop
            ON o_stop.schedule_id = nrs.schedule_id
            AND o_stop.station_id = %s
            AND o_stop.is_deleted = FALSE
        JOIN national_rail_schedule_stops d_stop
            ON d_stop.schedule_id = nrs.schedule_id
            AND d_stop.station_id = %s
            AND d_stop.is_deleted = FALSE
        JOIN national_rail_stations origin_st
            ON origin_st.station_id = %s
            AND origin_st.is_deleted = FALSE
        JOIN national_rail_stations dest_st
            ON dest_st.station_id = %s
            AND dest_st.is_deleted = FALSE
        LEFT JOIN seats s
            ON s.schedule_id = nrs.schedule_id
            AND s.is_deleted = FALSE
        LEFT JOIN bookings b
            ON b.schedule_id = nrs.schedule_id
            AND b.seat_id = s.seat_id
            AND b.status != 'cancelled'
            AND b.is_deleted = FALSE
            AND (%s::date IS NOT NULL AND b.travel_date::date = %s::date)
        WHERE o_stop.stop_order < d_stop.stop_order
            AND nrs.is_deleted = FALSE
            AND (%s IS NULL OR %s = ANY(nrs.operates_on))
        GROUP BY nrs.schedule_id
        ORDER BY nrs.schedule_id
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            weekday = _weekday_code(travel_date) if travel_date else None
            cur.execute(
                sql,
                (
                    origin_id,
                    destination_id,
                    origin_id,
                    destination_id,
                    travel_date,
                    travel_date,
                    weekday,
                    weekday,
                ),
            )
            return [
                {
                    "schedule_id": row["schedule_id"],
                    "available_seats": int(row["available_seats"]),
                }
                for row in cur.fetchall()
            ]


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.
    """
    stops_travelled = int(stops_travelled)
    sql = """
        SELECT fare_class, base_fare_usd, per_stop_rate_usd
        FROM national_rail_fare_classes
        WHERE schedule_id = %s AND fare_class = %s AND is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class))
            row = cur.fetchone()
            if not row:
                return None
            row = dict(row)
            base = float(row["base_fare_usd"])
            rate = float(row["per_stop_rate_usd"])
            total = base + stops_travelled * rate
            return {
                "fare_class": row["fare_class"],
                "base_fare_usd": base,
                "per_stop_rate_usd": rate,
                "total_fare_usd": round(total, 2),
            }


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.
    """
    sql = """
        SELECT
            ms.schedule_id,
            ms.line,
            ms.direction,
            ms.origin_station_id   AS sched_origin,
            ms.destination_station_id AS sched_destination,
            ms.first_train_time,
            ms.last_train_time,
            ms.base_fare_usd,
            ms.per_stop_rate_usd,
            ms.frequency_min,
            ms.operates_on,
            o_stop.stop_order       AS origin_stop_order,
            d_stop.stop_order       AS dest_stop_order,
            o_stop.travel_time_from_origin_min AS origin_travel_min,
            d_stop.travel_time_from_origin_min AS dest_travel_min,
            (d_stop.stop_order - o_stop.stop_order) AS stops_travelled,
            (d_stop.travel_time_from_origin_min - o_stop.travel_time_from_origin_min) AS journey_time_min,
            origin_st.name          AS origin_name,
            dest_st.name            AS destination_name
        FROM metro_schedules ms
        JOIN metro_schedule_stops o_stop
            ON o_stop.schedule_id = ms.schedule_id
            AND o_stop.station_id = %s
            AND o_stop.is_deleted = FALSE
        JOIN metro_schedule_stops d_stop
            ON d_stop.schedule_id = ms.schedule_id
            AND d_stop.station_id = %s
            AND d_stop.is_deleted = FALSE
        JOIN metro_stations origin_st
            ON origin_st.station_id = %s
            AND origin_st.is_deleted = FALSE
        JOIN metro_stations dest_st
            ON dest_st.station_id = %s
            AND dest_st.is_deleted = FALSE
        WHERE o_stop.stop_order < d_stop.stop_order
            AND ms.is_deleted = FALSE
        ORDER BY ms.schedule_id
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id, origin_id, destination_id))
            results = []
            for row in cur.fetchall():
                d = dict(row)
                d["first_train_time"] = _time_text(d["first_train_time"])
                d["last_train_time"] = _time_text(d["last_train_time"])
                d["base_fare_usd"] = float(d["base_fare_usd"])
                d["per_stop_rate_usd"] = float(d["per_stop_rate_usd"])
                total = d["base_fare_usd"] + d["stops_travelled"] * d["per_stop_rate_usd"]
                d["total_fare_usd"] = round(total, 2)
                results.append(d)
            return results


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.
    """
    sql = """
        SELECT base_fare_usd, per_stop_rate_usd
        FROM metro_schedules
        WHERE schedule_id = %s AND is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None
            row = dict(row)
            base = float(row["base_fare_usd"])
            rate = float(row["per_stop_rate_usd"])
            total = base + stops_travelled * rate
            return {
                "base_fare_usd": base,
                "per_stop_rate_usd": rate,
                "total_fare_usd": round(total, 2),
            }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.
    """
    sql = """
        SELECT s.seat_id, s.coach, s.seat_row AS row, s.seat_column AS column
        FROM seats s
        WHERE s.schedule_id = %s
            AND s.fare_class = %s
            AND s.is_deleted = FALSE
            AND s.seat_id NOT IN (
                SELECT b.seat_id
                FROM bookings b
                WHERE b.schedule_id = %s
                    AND b.travel_date::date = %s::date
                    AND b.status != 'cancelled'
                    AND b.is_deleted = FALSE
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
        SELECT user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active
        FROM users
        WHERE email = %s AND is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            dob = d.get("date_of_birth")
            return {
                "user_id": d["user_id"],
                "email": d["email"],
                "full_name": d["full_name"],
                "name": d["full_name"],
                "first_name": d.get("first_name"),
                "surname": d.get("surname"),
                "phone": d.get("phone"),
                "date_of_birth": _date_text(dob) if dob else None,
                "year_of_birth": dob.year if dob else None,
                "is_active": d.get("is_active"),
            }


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE email = %s AND is_deleted = FALSE",
                (user_email,),
            )
            user_row = cur.fetchone()
            if not user_row:
                return {"national_rail": [], "metro": []}
            uid = user_row["user_id"]

            cur.execute("""
                SELECT b.booking_id, b.schedule_id,
                       b.origin_station_id, b.destination_station_id,
                       o_st.name AS origin_name, d_st.name AS destination_name,
                       b.travel_date, b.departure_time,
                       b.ticket_type, b.fare_class, b.coach, b.seat_id,
                       b.stops_travelled, b.amount_usd, b.status,
                       b.booked_at, b.travelled_at
                FROM bookings b
                LEFT JOIN national_rail_stations o_st
                    ON o_st.station_id = b.origin_station_id AND o_st.is_deleted = FALSE
                LEFT JOIN national_rail_stations d_st
                    ON d_st.station_id = b.destination_station_id AND d_st.is_deleted = FALSE
                WHERE b.user_id = %s AND b.is_deleted = FALSE
                ORDER BY b.booked_at DESC
            """, (uid,))
            nr_bookings = []
            for row in cur.fetchall():
                d = dict(row)
                d["travel_date"] = _date_text(d["travel_date"])
                d["departure_time"] = _time_text(d["departure_time"])
                d["amount_usd"] = float(d["amount_usd"])
                if d.get("booked_at"):
                    d["booked_at"] = d["booked_at"].isoformat()
                if d.get("travelled_at"):
                    d["travelled_at"] = d["travelled_at"].isoformat()
                nr_bookings.append(d)

            cur.execute("""
                SELECT m.trip_id, m.schedule_id,
                       m.origin_station_id, m.destination_station_id,
                       o_st.name AS origin_name, d_st.name AS destination_name,
                       m.travel_date, m.ticket_type, m.day_pass_ref,
                       m.stops_travelled, m.amount_usd, m.status,
                       m.purchased_at, m.travelled_at
                FROM metro_travel_history m
                LEFT JOIN metro_stations o_st
                    ON o_st.station_id = m.origin_station_id AND o_st.is_deleted = FALSE
                LEFT JOIN metro_stations d_st
                    ON d_st.station_id = m.destination_station_id AND d_st.is_deleted = FALSE
                WHERE m.user_id = %s AND m.is_deleted = FALSE
                ORDER BY m.travel_date DESC
            """, (uid,))
            metro_trips = []
            for row in cur.fetchall():
                d = dict(row)
                d["travel_date"] = _date_text(d["travel_date"])
                d["amount_usd"] = float(d["amount_usd"])
                if d.get("purchased_at"):
                    d["purchased_at"] = d["purchased_at"].isoformat()
                if d.get("travelled_at"):
                    d["travelled_at"] = d["travelled_at"].isoformat()
                metro_trips.append(d)

            return {"national_rail": nr_bookings, "metro": metro_trips}


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    sql = """
        SELECT payment_id, booking_id, amount_usd, method, status, paid_at
        FROM payments
        WHERE booking_id = %s AND is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["amount_usd"] = float(d["amount_usd"])
            if d.get("paid_at"):
                d["paid_at"] = d["paid_at"].isoformat()
            return d


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
    """
    Create a national rail booking for a logged-in user.
    """
    conn = _tx_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE user_id = %s AND is_deleted = FALSE",
                (user_id,),
            )
            if not cur.fetchone():
                return _fail_transaction(conn, "User not found.")

            cur.execute("""
                SELECT o.stop_order AS o_order, d.stop_order AS d_order
                FROM national_rail_schedule_stops o
                JOIN national_rail_schedule_stops d
                    ON d.schedule_id = o.schedule_id
                WHERE o.schedule_id = %s
                    AND o.station_id = %s AND d.station_id = %s
                    AND o.is_deleted = FALSE AND d.is_deleted = FALSE
            """, (schedule_id, origin_station_id, destination_station_id))
            stop_row = cur.fetchone()
            if not stop_row:
                return _fail_transaction(
                    conn,
                    "Schedule does not serve both origin and destination stations.",
                )
            if stop_row["o_order"] >= stop_row["d_order"]:
                return _fail_transaction(
                    conn,
                    "Origin must come before destination on this schedule.",
                )
            stops_travelled = stop_row["d_order"] - stop_row["o_order"]

            cur.execute("""
                SELECT base_fare_usd, per_stop_rate_usd
                FROM national_rail_fare_classes
                WHERE schedule_id = %s AND fare_class = %s AND is_deleted = FALSE
            """, (schedule_id, fare_class))
            fare_row = cur.fetchone()
            if not fare_row:
                return _fail_transaction(
                    conn,
                    f"Fare class '{fare_class}' not found for schedule {schedule_id}.",
                )
            amount = float(fare_row["base_fare_usd"]) + stops_travelled * float(fare_row["per_stop_rate_usd"])
            amount = round(amount, 2)

            if seat_id == "any":
                available = query_available_seats(schedule_id, travel_date, fare_class)
                selected = auto_select_adjacent_seats(available, 1)
                if not selected:
                    return _fail_transaction(
                        conn,
                        "No seats available for this schedule, date, and fare class.",
                    )
                seat_id = selected[0]
            else:
                cur.execute("""
                    SELECT seat_id, coach FROM seats
                    WHERE schedule_id = %s AND seat_id = %s
                        AND fare_class = %s AND is_deleted = FALSE
                    FOR UPDATE
                """, (schedule_id, seat_id, fare_class))
                seat_row = cur.fetchone()
                if not seat_row:
                    return _fail_transaction(
                        conn,
                        f"Seat {seat_id} not found for this schedule and fare class.",
                    )

                cur.execute("""
                    SELECT booking_id FROM bookings
                    WHERE schedule_id = %s AND seat_id = %s
                        AND status != 'cancelled' AND is_deleted = FALSE
                        AND travel_date::date = %s::date
                """, (schedule_id, seat_id, travel_date))
                if cur.fetchone():
                    return _fail_transaction(
                        conn,
                        f"Seat {seat_id} is already booked for {travel_date}.",
                    )

            cur.execute("""
                SELECT coach FROM seats
                WHERE schedule_id = %s AND seat_id = %s
                    AND fare_class = %s AND is_deleted = FALSE
                FOR UPDATE
            """, (schedule_id, seat_id, fare_class))
            coach_row = cur.fetchone()
            if not coach_row:
                return _fail_transaction(
                    conn,
                    f"Seat {seat_id} not found for this schedule and fare class.",
                )
            coach = coach_row["coach"]

            cur.execute("""
                SELECT booking_id FROM bookings
                WHERE schedule_id = %s AND seat_id = %s
                    AND status != 'cancelled' AND is_deleted = FALSE
                    AND travel_date::date = %s::date
            """, (schedule_id, seat_id, travel_date))
            if cur.fetchone():
                return _fail_transaction(
                    conn,
                    f"Seat {seat_id} is already booked for {travel_date}.",
                )

            cur.execute("""
                SELECT first_train_time FROM national_rail_schedules
                WHERE schedule_id = %s AND is_deleted = FALSE
            """, (schedule_id,))
            sched_row = cur.fetchone()
            departure_time = (
                _combine_travel_date_and_service_time(travel_date, sched_row["first_train_time"])
                if sched_row else _combine_travel_date_and_service_time(travel_date, "07:00")
            )
            travel_date_ts = _date_at_utc(travel_date)

            booking_id = _gen_booking_id()
            payment_id = _gen_payment_id()
            now = datetime.now(timezone.utc)

            cur.execute("""
                INSERT INTO bookings (
                    booking_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date, departure_time, ticket_type, fare_class,
                    coach, seat_id, stops_travelled, amount_usd,
                    status, booked_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed', %s)
            """, (
                booking_id, user_id, schedule_id,
                origin_station_id, destination_station_id,
                travel_date_ts, departure_time, ticket_type, fare_class,
                coach, seat_id, stops_travelled, amount,
                now,
            ))

            cur.execute("""
                INSERT INTO payments (
                    payment_id, booking_id, amount_usd, method, status, paid_at
                ) VALUES (%s, %s, %s, 'credit_card', 'paid', %s)
            """, (payment_id, booking_id, amount, now))

        conn.commit()
        return True, {
            "booking_id": booking_id,
            "payment_id": payment_id,
            "user_id": user_id,
            "schedule_id": schedule_id,
            "origin_station_id": origin_station_id,
            "destination_station_id": destination_station_id,
            "travel_date": travel_date,
            "departure_time": _time_text(departure_time),
            "ticket_type": ticket_type,
            "fare_class": fare_class,
            "coach": coach,
            "seat_id": seat_id,
            "stops_travelled": stops_travelled,
            "amount_usd": amount,
            "status": "confirmed",
        }
    except Exception as e:
        conn.rollback()
        return False, f"Booking failed: {e}"
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)
    """
    conn = _tx_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT booking_id, user_id, schedule_id, travel_date,
                       departure_time, amount_usd, status, fare_class
                FROM bookings
                WHERE booking_id = %s AND is_deleted = FALSE
                FOR UPDATE
            """, (booking_id,))
            bk = cur.fetchone()
            if not bk:
                return _fail_transaction(conn, "Booking not found.")
            bk = dict(bk)

            if bk["user_id"] != user_id:
                return _fail_transaction(conn, "You do not own this booking.")
            if bk["status"] == "cancelled":
                return _fail_transaction(conn, "Booking is already cancelled.")
            if bk["status"] == "completed":
                return _fail_transaction(conn, "Cannot cancel a completed booking.")

            cur.execute("""
                SELECT service_type FROM national_rail_schedules
                WHERE schedule_id = %s AND is_deleted = FALSE
            """, (bk["schedule_id"],))
            sched = cur.fetchone()
            if not sched:
                return _fail_transaction(conn, "Schedule not found.")
            service_type = sched["service_type"]

            policy_id = "RF001" if service_type == "normal" else "RF002"

            departure_dt = bk["departure_time"]
            if isinstance(departure_dt, time):
                travel_date = bk["travel_date"]
                travel_day = travel_date.date() if isinstance(travel_date, datetime) else travel_date
                departure_dt = datetime.combine(travel_day, departure_dt)
            if departure_dt.tzinfo is None:
                departure_dt = departure_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_until = (departure_dt - now).total_seconds() / 3600.0

            cur.execute("""
                SELECT window_id, label, refund_percent, admin_fee_usd,
                       hours_before_departure_min, hours_before_departure_max
                FROM refund_policy_windows
                WHERE policy_id = %s AND is_deleted = FALSE
                ORDER BY hours_before_departure_min DESC
            """, (policy_id,))
            windows = [dict(w) for w in cur.fetchall()]

            refund_percent = 0
            admin_fee = 0.0
            matched_label = "No refund"
            for w in windows:
                w_min = w["hours_before_departure_min"] or 0
                w_max = w["hours_before_departure_max"]
                if w_max is None:
                    if hours_until >= w_min:
                        refund_percent = w["refund_percent"]
                        admin_fee = float(w["admin_fee_usd"])
                        matched_label = w["label"]
                        break
                else:
                    if w_min <= hours_until < w_max:
                        refund_percent = w["refund_percent"]
                        admin_fee = float(w["admin_fee_usd"])
                        matched_label = w["label"]
                        break

            original_amount = float(bk["amount_usd"])
            refund_amount = round(original_amount * refund_percent / 100.0 - admin_fee, 2)
            if refund_amount < 0:
                refund_amount = 0.0

            cur.execute("""
                UPDATE bookings
                SET status = 'cancelled', updated_at = NOW()
                WHERE booking_id = %s
            """, (booking_id,))

            if refund_amount > 0:
                cur.execute("""
                    UPDATE payments
                    SET status = 'refunded', updated_at = NOW()
                    WHERE booking_id = %s AND is_deleted = FALSE
                """, (booking_id,))

        conn.commit()
        return True, {
            "booking_id": booking_id,
            "status": "cancelled",
            "policy_id": policy_id,
            "refund_window": matched_label,
            "original_amount_usd": original_amount,
            "refund_percent": refund_percent,
            "admin_fee_usd": admin_fee,
            "refund_amount": refund_amount,
            "refund_amount_usd": refund_amount,
        }
    except Exception as e:
        conn.rollback()
        return False, f"Cancellation failed: {e}"
    finally:
        conn.close()


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
    """
    Register a new user.
    Returns (True, user_id) on success or (False, error_message) on failure.
    """
    conn = _tx_connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE email = %s AND is_deleted = FALSE",
                (email,),
            )
            if cur.fetchone():
                return False, "Email is already registered."

            cur.execute("""
                SELECT COALESCE(
                    MAX(CAST(SUBSTRING(user_id FROM 3) AS INTEGER)), 0
                ) AS max_num
                FROM users
            """)
            max_num = cur.fetchone()["max_num"]
            new_user_id = f"RU{max_num + 1:02d}"

            full_name = f"{first_name} {surname}"
            dob = _date_at_utc(f"{year_of_birth}-01-01")
            now = datetime.now(timezone.utc)
            password_hash = _hash_password(password)

            cur.execute("""
                INSERT INTO users (
                    user_id, first_name, surname, full_name,
                    email, date_of_birth, is_active, registered_at
                ) VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
            """, (new_user_id, first_name, surname, full_name, email, dob, now))

            cur.execute("""
                INSERT INTO user_credentials (
                    user_id, password_hash, secret_question, secret_answer
                ) VALUES (%s, %s, %s, %s)
            """, (new_user_id, password_hash, secret_question, secret_answer))

        conn.commit()
        return True, new_user_id
    except Exception as e:
        conn.rollback()
        return False, f"Registration failed: {e}"
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.user_id, u.email, u.full_name, u.first_name, u.surname,
                       u.phone, u.date_of_birth, u.is_active,
                       uc.password_hash
                FROM users u
                JOIN user_credentials uc ON uc.user_id = u.user_id AND uc.is_deleted = FALSE
                WHERE u.email = %s AND u.is_deleted = FALSE
            """, (email,))
            row = cur.fetchone()
            if not row:
                return None
            row = dict(row)

            if not _verify_password(password, row["password_hash"]):
                return None

            if row.get("date_of_birth"):
                row["date_of_birth"] = _date_text(row["date_of_birth"])
            del row["password_hash"]
            return row


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = """
        SELECT uc.secret_question
        FROM user_credentials uc
        JOIN users u ON u.user_id = uc.user_id AND u.is_deleted = FALSE
        WHERE u.email = %s AND uc.is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row["secret_question"] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = """
        SELECT uc.secret_answer
        FROM user_credentials uc
        JOIN users u ON u.user_id = uc.user_id AND u.is_deleted = FALSE
        WHERE u.email = %s AND uc.is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return False
            return row["secret_answer"].strip().lower() == answer.strip().lower()


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    new_hash = _hash_password(new_password)
    sql = """
        UPDATE user_credentials
        SET password_hash = %s, updated_at = NOW()
        WHERE user_id = (
            SELECT user_id FROM users
            WHERE email = %s AND is_deleted = FALSE
        ) AND is_deleted = FALSE
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_hash, email))
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
