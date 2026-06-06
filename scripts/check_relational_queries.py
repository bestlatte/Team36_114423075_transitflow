"""
Smoke test for IM2002 TransitFlow relational queries.

Run from repo root:

    python scripts/check_relational_queries.py

or:

    PYTHONPATH=. python scripts/check_relational_queries.py

Purpose:
- Directly call databases.relational.queries functions.
- Print outputs for B1–B10 PostgreSQL live-test criteria.
- Do lightweight PASS/FAIL checks.
- Mutates DB only for execute_booking / execute_cancellation test.

Assumption:
- Docker PostgreSQL is already running.
- schema.sql has been applied.
- seed_postgres.py has already completed successfully.
"""

from __future__ import annotations
from databases.relational import queries as q
from skeleton.config import PG_DSN

import json
import sys
import traceback
from datetime import date, timedelta, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------------
# Make imports work when this script is placed under scripts/
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------
# JSON printer helpers
# ---------------------------------------------------------------------
def json_default(obj: Any):
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=json_default)


def print_section(title: str):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def print_case(name: str, input_data: dict | None, output: Any, passed: bool | None = None):
    print(f"\n--- {name} ---")
    if input_data is not None:
        print("INPUT:")
        print(pretty(input_data))
    print("OUTPUT:")
    print(pretty(output))
    if passed is not None:
        print("STATUS:", "PASS" if passed else "CHECK / FAIL")


def safe_call(name: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        return True, result, None
    except Exception as e:
        return False, None, e


# ---------------------------------------------------------------------
# DB helpers for dynamically finding valid test data
# ---------------------------------------------------------------------
def connect():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def fetchone(sql: str, params: tuple = ()):
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetchall(sql: str, params: tuple = ()):
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def pick_weekday_date(operates_on: list[str] | None) -> str:
    """
    queries.py limits supported dates to 2026.
    Pick a date in 2026 matching one of the schedule's operates_on values.
    """
    if not operates_on:
        return "2026-04-02"

    target_days = {str(d).lower()[:3] for d in operates_on}
    d = date(2026, 4, 1)

    for _ in range(366):
        if d.strftime("%a").lower()[:3] in target_days:
            return d.isoformat()
        d += timedelta(days=1)

    return "2026-04-02"


def get_known_user():
    row = fetchone("""
        SELECT user_id, email, full_name
        FROM users
        WHERE is_deleted = FALSE
        ORDER BY user_id
        LIMIT 1
    """)
    if not row:
        raise RuntimeError("No user found. Please check seed_postgres.py.")
    return row


def get_national_rail_case():
    """
    Pick one national rail schedule with at least two stops and one fare class.
    """
    row = fetchone("""
        WITH route AS (
            SELECT
                nrs.schedule_id,
                nrs.line,
                nrs.service_type,
                nrs.operates_on,
                ARRAY_AGG(st.station_id ORDER BY st.stop_order) AS stops
            FROM national_rail_schedules nrs
            JOIN national_rail_schedule_stops st
                ON st.schedule_id = nrs.schedule_id
               AND st.is_deleted = FALSE
            WHERE nrs.is_deleted = FALSE
            GROUP BY nrs.schedule_id, nrs.line, nrs.service_type, nrs.operates_on
            HAVING COUNT(*) >= 2
            ORDER BY nrs.schedule_id
            LIMIT 1
        )
        SELECT
            route.schedule_id,
            route.line,
            route.service_type,
            route.operates_on,
            route.stops[1] AS origin_id,
            route.stops[array_length(route.stops, 1)] AS destination_id
        FROM route
    """)
    if not row:
        raise RuntimeError(
            "No national rail route found. Please check national rail seed data.")

    fare = fetchone("""
        SELECT fare_class
        FROM national_rail_fare_classes
        WHERE schedule_id = %s AND is_deleted = FALSE
        ORDER BY fare_class
        LIMIT 1
    """, (row["schedule_id"],))
    if not fare:
        raise RuntimeError(
            f"No fare class found for schedule {row['schedule_id']}.")

    row["fare_class"] = fare["fare_class"]
    row["travel_date"] = pick_weekday_date(row.get("operates_on"))
    return row


def get_metro_case():
    row = fetchone("""
        WITH route AS (
            SELECT
                ms.schedule_id,
                ms.line,
                ms.operates_on,
                ARRAY_AGG(st.station_id ORDER BY st.stop_order) AS stops
            FROM metro_schedules ms
            JOIN metro_schedule_stops st
                ON st.schedule_id = ms.schedule_id
               AND st.is_deleted = FALSE
            WHERE ms.is_deleted = FALSE
            GROUP BY ms.schedule_id, ms.line, ms.operates_on
            HAVING COUNT(*) >= 2
            ORDER BY ms.schedule_id
            LIMIT 1
        )
        SELECT
            route.schedule_id,
            route.line,
            route.operates_on,
            route.stops[1] AS origin_id,
            route.stops[array_length(route.stops, 1)] AS destination_id
        FROM route
    """)
    if not row:
        raise RuntimeError(
            "No metro route found. Please check metro seed data.")
    return row


def get_known_payment_refs():
    """
    Try to find one national rail booking payment and one metro trip payment.
    """
    bk = fetchone("""
        SELECT booking_id AS ref_id
        FROM payments
        WHERE booking_id IS NOT NULL AND is_deleted = FALSE
        ORDER BY payment_id
        LIMIT 1
    """)
    mt = fetchone("""
        SELECT trip_id AS ref_id
        FROM payments
        WHERE trip_id IS NOT NULL AND is_deleted = FALSE
        ORDER BY payment_id
        LIMIT 1
    """)
    return {
        "booking_ref": bk["ref_id"] if bk else None,
        "metro_ref": mt["ref_id"] if mt else None,
    }


def get_existing_booking_for_cancellation():
    """
    Prefer a confirmed booking that can be cancelled.
    If none exists, execute_booking test will create one.
    """
    return fetchone("""
        SELECT booking_id, user_id
        FROM bookings
        WHERE status NOT IN ('cancelled', 'completed')
          AND is_deleted = FALSE
        ORDER BY booked_at DESC
        LIMIT 1
    """)


def get_available_seat_for_case(nr_case: dict) -> dict | None:
    seats = q.query_available_seats(
        nr_case["schedule_id"],
        nr_case["travel_date"],
        nr_case["fare_class"],
    )
    return seats[0] if seats else None


# ---------------------------------------------------------------------
# Minimal shape checks
# ---------------------------------------------------------------------
def has_keys(obj: dict, keys: list[str]) -> bool:
    return isinstance(obj, dict) and all(k in obj for k in keys)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal))


# ---------------------------------------------------------------------
# Main smoke tests
# ---------------------------------------------------------------------
def main():
    print_section("IM2002 TransitFlow — Relational Queries Smoke Test")

    try:
        user = get_known_user()
        nr_case = get_national_rail_case()
        metro_case = get_metro_case()
        payment_refs = get_known_payment_refs()
    except Exception:
        print("Failed to prepare dynamic test data.")
        traceback.print_exc()
        return

    print_case("Prepared test data", None, {
        "known_user": user,
        "national_rail_case": nr_case,
        "metro_case": metro_case,
        "payment_refs": payment_refs,
    })

    # -----------------------------------------------------------------
    # B1 query_national_rail_availability
    # -----------------------------------------------------------------
    print_section("B1 — query_national_rail_availability")

    ok, result, err = safe_call(
        "query_national_rail_availability valid",
        q.query_national_rail_availability,
        nr_case["origin_id"],
        nr_case["destination_id"],
        nr_case["travel_date"],
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        passed = (
            isinstance(result, list)
            and len(result) > 0
            and has_keys(result[0], ["schedule_id", "available_seats"])
        )
        print_case(
            "valid route/date",
            {
                "origin_id": nr_case["origin_id"],
                "destination_id": nr_case["destination_id"],
                "travel_date": nr_case["travel_date"],
            },
            result,
            passed,
        )

    ok, result, err = safe_call(
        "query_national_rail_availability reversed",
        q.query_national_rail_availability,
        nr_case["destination_id"],
        nr_case["origin_id"],
        nr_case["travel_date"],
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "reversed route should return valid opposite-direction services or []",
            {
                "origin_id": nr_case["destination_id"],
                "destination_id": nr_case["origin_id"],
                "travel_date": nr_case["travel_date"],
            },
            result,
            isinstance(result, list),
        )

    ok, result, err = safe_call(
        "query_national_rail_availability unsupported date",
        q.query_national_rail_availability,
        nr_case["origin_id"],
        nr_case["destination_id"],
        "2099-01-01",
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "unsupported/no-service date should return []",
            {
                "origin_id": nr_case["origin_id"],
                "destination_id": nr_case["destination_id"],
                "travel_date": "2099-01-01",
            },
            result,
            result == [],
        )

    # -----------------------------------------------------------------
    # B2 query_metro_schedules
    # -----------------------------------------------------------------
    print_section("B2 — query_metro_schedules")

    ok, result, err = safe_call(
        "query_metro_schedules valid",
        q.query_metro_schedules,
        metro_case["origin_id"],
        metro_case["destination_id"],
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        passed = (
            isinstance(result, list)
            and len(result) > 0
            and has_keys(result[0], ["schedule_id", "line", "origin_stop_order", "dest_stop_order"])
        )
        print_case(
            "valid metro route",
            {
                "origin_id": metro_case["origin_id"],
                "destination_id": metro_case["destination_id"],
            },
            result,
            passed,
        )

    ok, result, err = safe_call(
        "query_metro_schedules reversed",
        q.query_metro_schedules,
        metro_case["destination_id"],
        metro_case["origin_id"],
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "reversed metro route should return valid opposite-direction services or []",
            {
                "origin_id": metro_case["destination_id"],
                "destination_id": metro_case["origin_id"],
            },
            result,
            isinstance(result, list),
        )

    # -----------------------------------------------------------------
    # B3 query_national_rail_fare
    # -----------------------------------------------------------------
    print_section("B3 — query_national_rail_fare")

    stops = 3
    for fare_class in ["standard", "first", nr_case["fare_class"]]:
        ok, result, err = safe_call(
            f"query_national_rail_fare {fare_class}",
            q.query_national_rail_fare,
            nr_case["schedule_id"],
            fare_class,
            stops,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
            continue

        passed = (
            result is None
            or (
                has_keys(result, ["base_fare_usd",
                         "per_stop_rate_usd", "total_fare_usd"])
                and is_number(result["base_fare_usd"])
                and is_number(result["per_stop_rate_usd"])
                and is_number(result["total_fare_usd"])
                and round(result["base_fare_usd"] + result["per_stop_rate_usd"] * stops, 2)
                == result["total_fare_usd"]
            )
        )
        print_case(
            f"fare_class={fare_class}",
            {
                "schedule_id": nr_case["schedule_id"],
                "fare_class": fare_class,
                "stops_travelled": stops,
            },
            result,
            passed,
        )

    # -----------------------------------------------------------------
    # B4 query_metro_fare
    # -----------------------------------------------------------------
    print_section("B4 — query_metro_fare")

    stops = 3
    ok, result, err = safe_call(
        "query_metro_fare",
        q.query_metro_fare,
        metro_case["schedule_id"],
        stops,
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        passed = (
            result is not None
            and has_keys(result, ["base_fare_usd", "per_stop_rate_usd", "total_fare_usd"])
            and is_number(result["base_fare_usd"])
            and is_number(result["per_stop_rate_usd"])
            and is_number(result["total_fare_usd"])
            and round(result["base_fare_usd"] + result["per_stop_rate_usd"] * stops, 2)
            == result["total_fare_usd"]
        )
        print_case(
            "metro fare",
            {
                "schedule_id": metro_case["schedule_id"],
                "stops_travelled": stops,
            },
            result,
            passed,
        )

    # -----------------------------------------------------------------
    # B5 query_available_seats
    # -----------------------------------------------------------------
    print_section("B5 — query_available_seats")

    ok, result, err = safe_call(
        "query_available_seats",
        q.query_available_seats,
        nr_case["schedule_id"],
        nr_case["travel_date"],
        nr_case["fare_class"],
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        passed = (
            isinstance(result, list)
            and (len(result) == 0 or has_keys(result[0], ["seat_id"]))
        )
        print_case(
            "available seats",
            {
                "schedule_id": nr_case["schedule_id"],
                "travel_date": nr_case["travel_date"],
                "fare_class": nr_case["fare_class"],
            },
            result[:10] if isinstance(result, list) else result,
            passed,
        )
        print(
            f"Total available seats returned: {len(result) if isinstance(result, list) else 'N/A'}")

    # -----------------------------------------------------------------
    # B6 query_user_profile
    # -----------------------------------------------------------------
    print_section("B6 — query_user_profile")

    for email in [user["email"], "notfound@example.com"]:
        ok, result, err = safe_call(
            f"query_user_profile {email}",
            q.query_user_profile,
            email,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
            continue

        if email == user["email"]:
            passed = has_keys(result, ["email", "name", "year_of_birth"])
        else:
            passed = result is None

        print_case(
            f"user profile: {email}",
            {"user_email": email},
            result,
            passed,
        )

    # -----------------------------------------------------------------
    # B7 query_user_bookings
    # -----------------------------------------------------------------
    print_section("B7 — query_user_bookings")

    for email in [user["email"], "notfound@example.com"]:
        ok, result, err = safe_call(
            f"query_user_bookings {email}",
            q.query_user_bookings,
            email,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
            continue

        passed = (
            isinstance(result, dict)
            and "national_rail" in result
            and "metro" in result
            and isinstance(result["national_rail"], list)
            and isinstance(result["metro"], list)
        )

        print_case(
            f"user bookings: {email}",
            {"user_email": email},
            result,
            passed,
        )

    # -----------------------------------------------------------------
    # B8 query_payment_info
    # -----------------------------------------------------------------
    print_section("B8 — query_payment_info")

    refs_to_test = []
    if payment_refs["booking_ref"]:
        refs_to_test.append(payment_refs["booking_ref"])
    if payment_refs["metro_ref"]:
        refs_to_test.append(payment_refs["metro_ref"])
    refs_to_test.append("UNKNOWN_REF")

    for ref in refs_to_test:
        ok, result, err = safe_call(
            f"query_payment_info {ref}",
            q.query_payment_info,
            ref,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
            continue

        if ref == "UNKNOWN_REF":
            passed = result is None
        else:
            passed = (
                isinstance(result, dict)
                and any(k in result for k in ["amount_usd", "amount"])
                and "status" in result
                and "method" in result
            )

        print_case(
            f"payment info: {ref}",
            {"booking_id_or_trip_id": ref},
            result,
            passed,
        )

    # -----------------------------------------------------------------
    # B9 execute_booking
    # -----------------------------------------------------------------
    print_section("B9 — execute_booking")

    created_booking = None
    available_seat = None

    try:
        available_seat = get_available_seat_for_case(nr_case)
    except Exception:
        traceback.print_exc()

    if not available_seat:
        print_case(
            "execute_booking skipped",
            None,
            "No available seat found for dynamically selected national rail case.",
            False,
        )
    else:
        booking_input = {
            "user_id": user["user_id"],
            "schedule_id": nr_case["schedule_id"],
            "origin_station_id": nr_case["origin_id"],
            "destination_station_id": nr_case["destination_id"],
            "travel_date": nr_case["travel_date"],
            "fare_class": nr_case["fare_class"],
            "seat_id": available_seat["seat_id"],
            "ticket_type": "single",
        }

        ok, result, err = safe_call(
            "execute_booking success",
            q.execute_booking,
            **booking_input,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
        else:
            passed = (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] is True
                and isinstance(result[1], dict)
                and has_keys(result[1], ["booking_id", "user_id", "schedule_id", "seat_id"])
            )
            print_case("execute_booking success",
                       booking_input, result, passed)

            if passed:
                created_booking = result[1]
                payment = q.query_payment_info(created_booking["booking_id"])
                print_case(
                    "payment record after execute_booking",
                    {"booking_id": created_booking["booking_id"]},
                    payment,
                    payment is not None,
                )

        # Attempt duplicate booking on the same seat/date.
        ok, duplicate_result, err = safe_call(
            "execute_booking duplicate seat",
            q.execute_booking,
            **booking_input,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
        else:
            passed = (
                isinstance(duplicate_result, tuple)
                and len(duplicate_result) == 2
                and duplicate_result[0] is False
            )
            print_case(
                "duplicate seat booking should fail gracefully",
                booking_input,
                duplicate_result,
                passed,
            )

    # -----------------------------------------------------------------
    # B10 execute_cancellation
    # -----------------------------------------------------------------
    print_section("B10 — execute_cancellation")

    if created_booking:
        cancel_booking_id = created_booking["booking_id"]
        cancel_user_id = created_booking["user_id"]
    else:
        existing = get_existing_booking_for_cancellation()
        cancel_booking_id = existing["booking_id"] if existing else None
        cancel_user_id = existing["user_id"] if existing else None

    if not cancel_booking_id:
        print_case(
            "execute_cancellation skipped",
            None,
            "No cancellable booking found.",
            False,
        )
    else:
        ok, result, err = safe_call(
            "execute_cancellation success",
            q.execute_cancellation,
            cancel_booking_id,
            cancel_user_id,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
        else:
            passed = (
                isinstance(result, tuple)
                and len(result) == 2
                and result[0] is True
                and isinstance(result[1], dict)
                and "refund_amount" in result[1]
            )
            print_case(
                "execute_cancellation success",
                {
                    "booking_id": cancel_booking_id,
                    "user_id": cancel_user_id,
                },
                result,
                passed,
            )

        ok, second_result, err = safe_call(
            "execute_cancellation already cancelled",
            q.execute_cancellation,
            cancel_booking_id,
            cancel_user_id,
        )
        if not ok:
            print("ERROR:")
            traceback.print_exception(type(err), err, err.__traceback__)
        else:
            passed = (
                isinstance(second_result, tuple)
                and len(second_result) == 2
                and second_result[0] is False
            )
            print_case(
                "second cancellation should fail gracefully",
                {
                    "booking_id": cancel_booking_id,
                    "user_id": cancel_user_id,
                },
                second_result,
                passed,
            )

    # -----------------------------------------------------------------
    # Authentication smoke tests
    # -----------------------------------------------------------------
    print_section("Authentication — register/login/secret/update_password")

    test_email = f"smoke_test_{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
    test_password = "SmokePass123!"
    new_password = "SmokePass456!"
    secret_question = "What is the smoke test answer?"
    secret_answer = "TransitFlow"

    ok, result, err = safe_call(
        "register_user",
        q.register_user,
        test_email,
        "Smoke",
        "Tester",
        2000,
        test_password,
        secret_question,
        secret_answer,
    )
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        passed = isinstance(result, tuple) and len(
            result) == 2 and result[0] is True
        print_case(
            "register_user new user",
            {
                "email": test_email,
                "first_name": "Smoke",
                "surname": "Tester",
                "year_of_birth": 2000,
            },
            result,
            passed,
        )

    ok, login_result, err = safe_call(
        "login_user old password", q.login_user, test_email, test_password)
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "login_user with registered password",
            {"email": test_email},
            login_result,
            isinstance(login_result, dict) and login_result.get(
                "email") == test_email,
        )

    ok, question_result, err = safe_call(
        "get_user_secret_question", q.get_user_secret_question, test_email)
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "get_user_secret_question",
            {"email": test_email},
            question_result,
            question_result == secret_question,
        )

    ok, verify_result, err = safe_call(
        "verify_secret_answer", q.verify_secret_answer, test_email, " transitflow ")
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "verify_secret_answer case-insensitive",
            {"email": test_email, "answer": " transitflow "},
            verify_result,
            verify_result is True,
        )

    ok, update_result, err = safe_call(
        "update_password", q.update_password, test_email, new_password)
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "update_password",
            {"email": test_email},
            update_result,
            update_result is True,
        )

    ok, login_new_result, err = safe_call(
        "login_user new password", q.login_user, test_email, new_password)
    if not ok:
        print("ERROR:")
        traceback.print_exception(type(err), err, err.__traceback__)
    else:
        print_case(
            "login_user after password update",
            {"email": test_email},
            login_new_result,
            isinstance(login_new_result, dict) and login_new_result.get(
                "email") == test_email,
        )

    print_section("Smoke test finished")
    print("Please send me the full output if you want me to evaluate it against B1–B10.")


if __name__ == "__main__":
    main()
