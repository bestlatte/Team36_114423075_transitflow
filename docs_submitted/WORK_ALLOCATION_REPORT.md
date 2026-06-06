# Work Allocation Report — [Team 36]

## 1. Team Members

| Full Name | Student ID | GitHub Username               | Email                        |
| --------- | ---------- | ----------------------------- | ---------------------------- |
| 李軒毅    | 114423075  | bestlatte                     | x123456789xxxxxxtw@gmail.com |
| 柳炫州    | 114423071  | tw1040407-sys                 | tw1040407@gmail.com          |
| 黃昱鈞    | 114423011  | SeanHuang110633、yahappylemon | sean02050923@gmail.com       |

---

## 2. Task Ownership

For each task, name the **primary owner** (the person most responsible for delivering it)
and any **supporting members** (who assisted but were not the lead). Leave the Notes column
for anything that deviates from the standard expectation (e.g., task was pair-programmed,
or reassigned mid-project).

### Code Repository

| Task                                                                                                                                                         | Primary Owner  | Supporting Member(s) | Notes |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------- | -------------------- | ----- |
| **Task 1** — Relational schema design (`schema.sql`)                                                                                                         | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 2a** — Core availability & fare queries (`query_national_rail_availability`, `query_metro_schedules`, `query_national_rail_fare`, `query_metro_fare`) | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 2b** — Seat & user queries (`query_available_seats`, `query_user_profile`, `query_user_bookings`, `query_payment_info`)                               | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 2c** — Write operations (`execute_booking`, `execute_cancellation`)                                                                                   | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 2d** — Authentication queries (`login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, `update_password`)                  | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 3** — PostgreSQL seeding (`seed_postgres.py`)                                                                                                         | 李軒毅         | 黃昱鈞、柳炫州       |       |
| **Task 4** — Neo4j graph design & seeding (`seed_neo4j.py`, `seed.cypher`)                                                                                   | 柳炫州         | 黃昱鈞、李軒毅       |       |
| **Task 5** — Neo4j query functions (`graph/queries.py`)                                                                                                      | 柳炫州         | 黃昱鈞、李軒毅       |       |
| **Task 6** _(if attempted)_ — Optional extension                                                                                                             | 黃昱鈞、柳炫周 | 李軒毅               |       |

### Design Document

| Section                                          | Primary Author | Supporting Member(s) | Notes |
| ------------------------------------------------ | -------------- | -------------------- | ----- |
| Section 1 — ER Diagram                           | 黃昱鈞         | 李軒毅、柳炫州       |       |
| Section 2 — Normalisation Justification          | 黃昱鈞         | 李軒毅、柳炫州       |       |
| Section 3 — Graph Database Design Rationale      | 柳炫州         | 黃昱鈞、李軒毅       |       |
| Section 4 — Vector / RAG Design                  | 黃昱鈞         | 李軒毅、柳炫州       |       |
| Section 5 — AI Tool Usage Evidence               | 李軒毅         | 黃昱鈞、柳炫州       |       |
| Section 6 — Reflection & Trade-offs              | 黃昱鈞         | 李軒毅、柳炫州       |       |
| Section 7 — Optional Extension _(if applicable)_ | 黃昱鈞         | 李軒毅、柳炫州       |       |

---

## 3. Estimated Contribution Percentages

Based on the task allocation above, what percentage of total team effort do you estimate each member contributed?
All members must sum to 100%.

| Member    | Estimated % | Brief justification                                       |
| --------- | ----------- | --------------------------------------------------------- |
| 李軒毅    | 40%         | 主責關聯式資料庫相關開發工作並撰寫相關文件                |
| 柳炫州    | 30%         | 主責圖形資料庫相關開發工作並撰寫相關文件                  |
| 黃昱鈞    | 30%         | 主責向量資料庫 & Optional extension開發工作並撰寫相關文件 |
| **Total** | **100%**    |                                                           |

---

## 4. Mid-Project Changes

If any tasks were reassigned or the original plan changed significantly, document it here.
If nothing changed, write "No changes."

| Change | Original plan | Revised plan | Reason |
| ------ | ------------- | ------------ | ------ |
|        |               |              |        |

---

## 5. Team Declaration

We confirm that this work allocation accurately reflects how responsibilities were divided within our team.

| Name | Signature / Typed name | Date |
| ---- | ---------------------- | ---- |
|      |                        |      |
|      |                        |      |
|      |                        |      |
