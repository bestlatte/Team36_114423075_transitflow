---
name: static-code-evaluation
description: >-
  Review and repair this train booking database project against the student
  guide static evaluation rubric. Use when checking schema.sql, queries.py,
  PostgreSQL seed functions, Neo4j seed logic, password hashing, idempotency,
  transaction atomicity, or scaffold boundaries.
---

# Static Code Evaluation Skill

Use this skill when editing or reviewing the IM2002 DBMGT train project for the `/100` static code evaluation.

## Scope

Primary targets:

- `databases/relational/schema.sql`
- `databases/relational/queries.py`
- PostgreSQL seed files, especially seed functions in the skeleton
- Neo4j seed files

Do not implement scaffold-owned objects unless the assignment explicitly asks for them. Treat these as off-limits examples:

- `policy_documents`
- `auto_select_adjacent_seats`
- `query_policy_vector_search`

## Evaluation Workflow

1. Check fatal issues first.
   - Verify `register_user()` hashes passwords before storage.
   - Confirm password hashing uses bcrypt, argon2, scrypt, or PBKDF2.
   - Reject plaintext, MD5, SHA-only, or imported-but-unused hashing.
   - Confirm PostgreSQL seeds are idempotent with `ON CONFLICT` or upsert.
   - Confirm Neo4j seeds use `MERGE`, not `CREATE`.

2. Check `schema.sql` for Task 1.
   - Required entities exist: schedules, fares, bookings, seat layouts, users, and related junction tables.
   - Fare and money columns use `NUMERIC` or `DECIMAL`.
   - Date/time columns use `TIMESTAMPTZ`.
   - Status columns use `BOOLEAN`.
   - Schedule stops are normalized into a separate table with `stop_order`.
   - No schedule stop array column is used.
   - PK fields include comments explaining UUID or SERIAL choice.
   - Deletion strategy is documented and consistent.
   - Every FK explicitly defines `ON DELETE CASCADE`, `ON DELETE RESTRICT`, or `ON DELETE SET NULL`.

3. Check `queries.py` for Task 2.
   - Remove all `raise NotImplementedError` and placeholder-only `pass` in required functions.
   - Verify core query functions return the expected structures.
   - Verify national rail and metro fare calculations use base fare plus per-station increment.
   - Ensure `query_available_seats` filters out booked seats.
   - Ensure `query_user_profile` returns `None` for an unknown email.
   - Ensure `query_user_bookings` always returns both `national_rail` and `metro` keys.
   - Ensure `execute_booking` inserts booking and payment inside one transaction with a single final `conn.commit()`.
   - Ensure login checks use the same hash algorithm as registration.
   - Ensure security-question answers are compared case-insensitively.

4. Check PostgreSQL seeding for Task 3.
   - Confirm all 10 PostgreSQL seed functions are implemented.
   - Confirm every seed function uses conflict handling.
   - Confirm repeated execution does not create duplicates.

## Implementation Notes

- Prefer small, targeted edits in the relevant files.
- Preserve existing scaffold code.
- Use parameterized SQL in Python query functions.
- When changing transaction logic, keep booking and payment writes in the same success path and commit once.
- When adding password hashing, store only the encoded hash and verify with the matching library function.

## Final Verification Checklist

Before finishing, report:

- Password hashing status.
- Seed idempotency status for PostgreSQL and Neo4j.
- Whether scaffold-owned objects were left untouched.
- Schema type and normalization compliance.
- Query function placeholder status.
- Booking transaction atomicity status.
