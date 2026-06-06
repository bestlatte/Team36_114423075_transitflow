---
name: live-testing-data-layer
description: >-
  Review and repair this train booking database project against the TA live
  testing rubric. Use when checking seed_postgres.py, seed_neo4j.py,
  PostgreSQL data completeness, pgvector policy data, Neo4j station links,
  query return formats, fare math, available-seat filtering, booking
  transaction atomicity, and cancellation refund behavior.
---

# Live Testing Data Layer Skill

Use this skill when editing, reviewing, or testing the IM2002 DBMGT train booking project for the live testing evaluation.

The priority is to make the project pass the TA's direct terminal and Python function tests. Treat exact return shapes, no-crash behavior, and transaction atomicity as grading-critical.

## Section A: Initialization And Data Integrity

The TA will directly run:

```bash
python seed_postgres.py
python seed_neo4j.py
```

Both scripts must finish without any `Traceback`.

PostgreSQL must contain reasonable test data in at least these tables:

- `metro_stations`
- `national_rail_stations`
- `metro_schedules`
- `users`
- `seat_layouts`

Data integrity requirements:

- Fare and money columns must be numeric database types, not strings.
- Foreign keys must point to rows that actually exist.
- `SELECT COUNT(*) FROM policy_documents;` must return a value greater than `0`.
- pgvector policy document data must actually be imported.

Neo4j requirements:

- Metro station nodes must exist.
- National rail station nodes must exist.
- `METRO_LINK` relationships must exist.
- `RAIL_LINK` relationships must exist.

## B1: National Rail Availability

Function:

```python
query_national_rail_availability(...)
```

Expected return:

```python
[
    {
        "schedule_id": ...,
        "available_seats": ...
    }
]
```

Rules:

- Return a list of dicts.
- If no train exists for the requested date, return `[]`.
- Never return `None` for a no-result case.
- Never raise an exception for normal no-match inputs.
- Exclude trains where both origin and destination exist but the direction is wrong.
- Wrong direction means destination appears before origin in the stop sequence.

## B2: Metro Schedules

Function:

```python
query_metro_schedules(...)
```

Rules:

- Find metro lines that serve both origin and destination.
- Return results according to the correct stop sequence.
- If the two stations do not share a metro line, return `[]`.
- Never crash for no-match inputs.

## B3 And B4: Fare Queries

Functions:

```python
query_national_rail_fare(...)
query_metro_fare(...)
```

Expected return shape:

```python
{
    "base_fare_usd": 0,
    "per_stop_rate_usd": 0,
    "total_fare_usd": 0
}
```

Rules:

- The dict must contain the fare keys `base_fare_usd`, `per_stop_rate_usd`, and `total_fare_usd`.
- All money values must be numeric Python values, not strings.
- The formula must be exactly:

```text
total_fare_usd = base_fare_usd + (per_stop_rate_usd * stops)
```

- Fare class must affect `per_stop_rate_usd`.
- Switching fare class, such as from `standard` to `first`, must change the per-stop rate and total fare.

## B5: Available Seats

Function:

```python
query_available_seats(...)
```

Rules:

- Return only seats for the requested fare class.
- Exclude seats already booked for the same date and same train or schedule.
- Do not exclude seats booked for a different date.
- Do not exclude seats booked for a different train or schedule.
- Return `[]` when no seats match.

## B6: User Profile

Function:

```python
query_user_profile(email)
```

Known email expected shape:

```python
{
    "email": "...",
    "name": "...",
    "year_of_birth": 2000
}
```

Rules:

- Known users must return a dict containing `email`, `name`, and `year_of_birth`.
- Unknown users must return `None`.
- Unknown users must not cause exceptions.

## B7: User Bookings

Function:

```python
query_user_bookings(...)
```

The return dict must always contain both keys:

```python
{
    "national_rail": [],
    "metro": []
}
```

Rules:

- Return existing national rail bookings under `national_rail`.
- Return existing metro bookings under `metro`.
- A new user with no bookings must still receive both keys with empty lists.
- Never return `None`.

## B8 And B9: Atomic Booking

Function:

```python
execute_booking(...)
```

Success shape:

```python
(True, result)
```

Failure shape:

```python
(False, "error message")
```

Transaction rules:

- Booking/order record and payment record must be created in the same database transaction.
- Use one transaction boundary for all writes required by a booking.
- Commit only after every required insert succeeds.
- Roll back if any insert or payment step fails.
- The database must never contain an orphan booking without payment.

Duplicate-seat rules:

- If the requested seat is already booked, return `(False, "error message")`.
- Do not crash.
- Do not create duplicate records.
- Prefer database constraints, row locks, or transaction-safe checks where appropriate.

## B10: Cancellation And Refund

Function:

```python
execute_cancellation(...)
```

Success shape:

```python
(True, {
    "refund_amount": 0
})
```

Failure shape:

```python
(False, "error message")
```

Rules:

- Successful cancellation must update the booking status to `cancelled`.
- The returned dict must include `refund_amount`.
- `refund_amount` must be numeric.
- Refunds must be calculated from the actual policy time window.
- Cancelling an already `cancelled` booking must return `(False, "error message")`.
- Invalid or already-cancelled bookings must not crash the function.

## Collaboration Workflow

When using this skill:

1. Inspect the schema before changing query logic.
2. Inspect seed data before assuming station names, route names, schedule IDs, or fare classes.
3. Preserve the exact Python return shapes required above.
4. Convert database numeric values to numeric Python values, not strings.
5. Treat empty result cases as normal behavior.
6. Add targeted tests or small manual checks for hidden-test edge cases.
7. Verify seed scripts before declaring the work complete.

## Hidden-Test Edge Cases To Check

- National rail schedule contains both stations but destination appears before origin.
- Date has no available train schedules.
- Metro origin and destination do not share a line.
- Fare class changes from `standard` to `first`.
- Seat is already booked for the same train and date.
- Seat is booked only on a different date.
- Existing user has no bookings.
- Unknown email is queried.
- Booking insert succeeds but payment insert fails.
- User tries to book an already-booked seat.
- User tries to cancel a booking that is already `cancelled`.

## Suggested Verification Queries

PostgreSQL:

```sql
SELECT COUNT(*) FROM metro_stations;
SELECT COUNT(*) FROM national_rail_stations;
SELECT COUNT(*) FROM metro_schedules;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM seat_layouts;
SELECT COUNT(*) FROM policy_documents;
```

Neo4j:

```cypher
MATCH (s) RETURN labels(s), count(*) LIMIT 20;
MATCH ()-[r:METRO_LINK]->() RETURN count(r);
MATCH ()-[r:RAIL_LINK]->() RETURN count(r);
```

## Final Report Checklist

Before finishing work, report:

- Whether `seed_postgres.py` runs without Traceback.
- Whether `seed_neo4j.py` runs without Traceback.
- Whether required PostgreSQL tables are populated.
- Whether `policy_documents` count is greater than `0`.
- Whether Neo4j station nodes and links exist.
- Whether fare functions return numeric values with the required keys.
- Whether no-result query functions return `[]` or `None` exactly where required.
- Whether booking and payment are atomic.
- Whether cancellation computes and returns a real refund amount.
