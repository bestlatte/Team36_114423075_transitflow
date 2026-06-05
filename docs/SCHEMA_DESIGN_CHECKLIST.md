下面這份可以直接拿去給 AI agent，用來檢查 `schema.sql` 是否大致符合專案要求。
目標不是追求滿分，而是評估是否達到 **80–90% 完成度**，並找出是否有「可能導致嚴重扣分或功能壞掉」的問題。

---

# Relational Schema Checklist for IM2002 TransitFlow

## 評估目標

請根據 `databases/relational/schema.sql` 檢查 relational database schema 是否符合 IM2002 TransitFlow 專案要求。

請特別注意：

1. 不需要追求完美滿分。
2. 評估目標是判斷 schema 是否達到約 **80–90% 完成度**。
3. 請優先找出會造成嚴重問題的地方，例如：
   - 主要資料表缺失
   - PK / FK 錯誤
   - queries.py 需要的欄位不存在
   - seed 雖成功但資料關聯明顯不合理
   - 密碼未 hash
   - schedule stops 沒有拆成獨立表

4. 小問題可以標記為「低風險」，不需要過度扣分。

官方靜態檢查中，Relational Schema Design 佔 40 分，重點包含 table completeness、PK/FK、data types、password storage、normalisation、delete strategy、FK cascade behavior 等。

---

# 一、輸出格式要求

請依照以下格式輸出：

```text
## Overall Result

Estimated completion: XX%
Risk level: Low / Medium / High
Pass-risk assessment: Safe / Needs minor fixes / Risky

## Critical Blockers

- [列出會導致 seed/query/live test 嚴重失敗的問題]
- 如果沒有，寫：None

## Checklist Detail

逐項列出：
- Status: Pass / Partial / Fail
- Evidence: schema 中看到的表、欄位、constraint
- Risk: Low / Medium / High
- Suggested fix: 如果需要修正，簡短說明

## Final Recommendation

用 3–5 句總結目前 schema 是否足夠應付專案要求。
```

---

# 二、評分級距

請用以下標準估算完成度：

|  完成度 | 判斷                                                 |
| ------: | ---------------------------------------------------- |
| 90–100% | 接近高分，schema 完整，PK/FK/型別/註解都相當齊全     |
|  80–89% | 大致符合專案要求，可能有小扣分，但不太會影響主要功能 |
|  70–79% | 可以跑，但 static code 或 live test 可能有明顯扣分   |
|  60–69% | 有明顯缺口，可能影響查詢或交易功能                   |
|    <60% | 風險高，可能被認定 relational DB 未完成              |

目標標準：

```text
80% 以上：可以接受
70–79%：建議修幾個主要問題
70% 以下：有被大幅扣分或 live test 失敗風險
```

---

# 三、Checklist 權重總表

| 類別                                     |     權重 |
| ---------------------------------------- | -------: |
| A. Table Completeness                    |      20% |
| B. Primary Key / Foreign Key Correctness |      20% |
| C. Data Types                            |      15% |
| D. Password Storage                      |      10% |
| E. Normalisation                         |      10% |
| F. Delete Strategy / Cascade Behavior    |      10% |
| G. PK Design Comment                     |       5% |
| H. Query Compatibility                   |      10% |
| **Total**                                | **100%** |

---

# A. Table Completeness — 20%

檢查是否有足夠資料表支撐 TransitFlow 的主要 relational entities。

| 檢查項目                           | 滿足條件                                           | 權重 | Status                |
| ---------------------------------- | -------------------------------------------------- | ---: | --------------------- |
| Metro stations table               | 有 `metro_stations` 或等價表                       |   2% | Pass / Partial / Fail |
| National rail stations table       | 有 `national_rail_stations` 或等價表               |   2% | Pass / Partial / Fail |
| Metro schedules table              | 有 `metro_schedules` 或等價表                      |   2% | Pass / Partial / Fail |
| Metro schedule stops table         | 有獨立 stops table，且包含 `stop_order`            |   3% | Pass / Partial / Fail |
| National rail schedules table      | 有 `national_rail_schedules` 或等價表              |   2% | Pass / Partial / Fail |
| National rail schedule stops table | 有獨立 stops table，且包含 `stop_order`            |   3% | Pass / Partial / Fail |
| National rail fare class table     | 有 fare class / fare rate 資料表或清楚欄位         |   2% | Pass / Partial / Fail |
| Seat layout / seats table          | 有 seats / seat layout table，可依 schedule 查座位 |   2% | Pass / Partial / Fail |
| Users / credentials tables         | 有 users 與登入憑證相關資料表                      |   2% | Pass / Partial / Fail |
| Bookings / metro trips / payments  | 有 national rail bookings、metro trips、payments   |   2% | Pass / Partial / Fail |

## A 類判斷標準

|   得分 | 判斷                                 |
| -----: | ------------------------------------ |
| 18–20% | 表格完整，可支撐主要功能             |
| 14–17% | 大致完整，少數輔助表不足             |
| 10–13% | 有主要表，但關係建模偏弱             |
|   <10% | 表格缺太多，queries 可能無法正常支援 |

---

# B. Primary Key / Foreign Key Correctness — 20%

檢查 PK/FK 是否足以維持資料一致性。官方標準要求每張表有明確 PK，FK 要正確 reference parent table。

| 檢查項目               | 滿足條件                                                          | 權重 | Status                |
| ---------------------- | ----------------------------------------------------------------- | ---: | --------------------- |
| 每張主要表有 PK        | stations、schedules、users、bookings、payments 等都有 primary key |   4% | Pass / Partial / Fail |
| Schedule stops FK 正確 | stops table FK 到 schedule 與 station                             |   4% | Pass / Partial / Fail |
| Bookings FK 正確       | booking FK 到 user、schedule、origin station、destination station |   4% | Pass / Partial / Fail |
| Seat consistency       | booking 可關聯到合法 seat / coach / fare_class                    |   3% | Pass / Partial / Fail |
| Payment relation 合理  | payment 可關聯 national rail booking 或 metro trip                |   3% | Pass / Partial / Fail |
| FK target 有 PK/UNIQUE | FK reference 的 parent column 是 PK 或 UNIQUE                     |   2% | Pass / Partial / Fail |

## B 類判斷標準

|   得分 | 判斷                            |
| -----: | ------------------------------- |
| 18–20% | FK 設計完整，資料一致性高       |
| 14–17% | 主要 FK 都有，少數細節不完美    |
| 10–13% | 能跑，但資料一致性保護不足      |
|   <10% | FK 缺太多，容易出現 orphan data |

---

# C. Data Types — 15%

官方標準要求 fare 使用 `NUMERIC/DECIMAL`，datetime 使用 `TIMESTAMPTZ`，flags 使用 `BOOLEAN`。

| 檢查項目                              | 滿足條件                                                                      | 權重 | Status                |
| ------------------------------------- | ----------------------------------------------------------------------------- | ---: | --------------------- |
| Fare / amount 使用 numeric            | `base_fare_usd`、`per_stop_rate_usd`、`amount_usd` 使用 `NUMERIC` / `DECIMAL` |   4% | Pass / Partial / Fail |
| Datetime 使用合理型別                 | `booked_at`、`paid_at`、`registered_at` 等使用 `TIMESTAMPTZ`                  |   3% | Pass / Partial / Fail |
| Boolean flags 使用 BOOLEAN            | `is_active`、`is_deleted`、interchange flags 等使用 `BOOLEAN`                 |   3% | Pass / Partial / Fail |
| Order / count / duration 使用 integer | `stop_order`、`frequency_min`、`travel_time_from_origin_min` 使用 integer     |   3% | Pass / Partial / Fail |
| 不濫用 TEXT 儲存結構化資料            | fare、status、IDs、數字欄位不應全部用 TEXT                                    |   2% | Pass / Partial / Fail |

## C 類判斷標準

|   得分 | 判斷                                     |
| -----: | ---------------------------------------- |
| 13–15% | 型別大致正確，live test 不太會因型別出錯 |
| 10–12% | 少數欄位不完美，但不影響主要查詢         |
|   7–9% | 多個欄位型別不合理，可能影響計算         |
|    <7% | fare / datetime / boolean 型別明顯錯誤   |

---

# D. Password Storage — 10%

這項是高風險項目。官方明確寫：plain-text password = 0，MD5/SHA = 0；必須使用 bcrypt / argon2 / scrypt / PBKDF2。

| 檢查項目                    | 滿足條件                                                                   | 權重 | Status                |
| --------------------------- | -------------------------------------------------------------------------- | ---: | --------------------- |
| schema 不存 plain password  | 沒有直接保存明文 `password` 欄位                                           |   3% | Pass / Partial / Fail |
| 有 password hash 欄位       | 例如 `password_hash`                                                       |   3% | Pass / Partial / Fail |
| register_user 真的呼叫 hash | `queries.py` 的 `register_user()` 有呼叫 bcrypt / argon2 / scrypt / PBKDF2 |   4% | Pass / Partial / Fail |

## D 類判斷標準

| 得分 | 判斷                                       |
| ---: | ------------------------------------------ |
|  10% | 符合 password hashing 要求                 |
| 6–9% | schema 有 hash 欄位，但 queries 實作需確認 |
| 0–5% | 有明文或弱 hash，高風險                    |

---

# E. Normalisation — 10%

官方明確要求 schedule stops 要拆成 separate junction table，不能只用 array column 存停靠站順序。

| 檢查項目                 | 滿足條件                                                                          | 權重 | Status                |
| ------------------------ | --------------------------------------------------------------------------------- | ---: | --------------------- |
| Metro stops 拆表         | 有 `metro_schedule_stops`，包含 `schedule_id`、`station_id`、`stop_order`         |   3% | Pass / Partial / Fail |
| National rail stops 拆表 | 有 `national_rail_schedule_stops`，包含 `schedule_id`、`station_id`、`stop_order` |   3% | Pass / Partial / Fail |
| Fare class 可 SQL 查詢   | national rail fare class 不只是塞 JSON / TEXT                                     |   2% | Pass / Partial / Fail |
| Seat layout 可 SQL 查詢  | 可依 schedule / fare_class 查 seats                                               |   2% | Pass / Partial / Fail |

## E 類判斷標準

|  得分 | 判斷                                |
| ----: | ----------------------------------- |
| 9–10% | 正規化符合要求                      |
|  7–8% | 大致符合，少數資料仍較 denormalized |
|  5–6% | 有拆部分表，但查詢會不方便          |
|   <5% | 明顯不符合 normalisation 要求       |

---

# F. Delete Strategy / Cascade Behavior — 10%

官方要求 delete strategy 要一致並有註解，FK cascade behavior 要明確指定。

| 檢查項目                   | 滿足條件                                                   | 權重 | Status                |
| -------------------------- | ---------------------------------------------------------- | ---: | --------------------- |
| Delete strategy 一致       | 大多數 relational tables 採一致 soft delete 或 hard delete |   3% | Pass / Partial / Fail |
| 有註解說明 delete strategy | schema comment 說明為什麼用 soft/hard delete               |   2% | Pass / Partial / Fail |
| FK 有明確 ON DELETE        | FK 都明確使用 `CASCADE` / `RESTRICT` / `SET NULL`          |   4% | Pass / Partial / Fail |
| 不會誤刪重要交易資料       | booking/payment 不應因 cascade 被輕易刪掉                  |   1% | Pass / Partial / Fail |

## F 類判斷標準

|  得分 | 判斷                                          |
| ----: | --------------------------------------------- |
| 9–10% | delete / FK cascade 設計清楚                  |
|  7–8% | 主要 FK 有 ON DELETE，少數缺漏                |
|  5–6% | 有 delete strategy，但註解或 ON DELETE 不完整 |
|   <5% | 策略不清楚，可能 static check 被扣分          |

---

# G. PK Design Comment — 5%

官方要求 UUID vs SERIAL 的選擇要在 PK 附近用 comment justify。

| 檢查項目        | 滿足條件                                                            | 權重 | Status                |
| --------------- | ------------------------------------------------------------------- | ---: | --------------------- |
| PK 型別選擇清楚 | 使用 SERIAL / BIGSERIAL / UUID / mock-data business key，且一致合理 |   2% | Pass / Partial / Fail |
| 有註解說明原因  | 例如說明為何保留 mock data 的 stable IDs、或為何使用 surrogate key  |   3% | Pass / Partial / Fail |

## G 類判斷標準

| 得分 | 判斷                     |
| ---: | ------------------------ |
|   5% | 有清楚 PK 設計註解       |
| 3–4% | PK 合理，但註解不足      |
| 1–2% | PK 可用但混亂            |
|   0% | PK 設計不清楚或多表缺 PK |

---

# H. Query Compatibility — 10%

這項不是官方 schema 條目原文，但很適合你的目標：避免 live test 時 queries 直接壞掉。Live test 會測 PostgreSQL queries 是否回傳正確 shape、不 crash。

| 檢查項目                        | 滿足條件                                                                        | 權重 | Status                |
| ------------------------------- | ------------------------------------------------------------------------------- | ---: | --------------------- |
| queries 使用的 table 都存在     | `queries.py` 中 SQL 查詢的表都在 schema 中                                      |   2% | Pass / Partial / Fail |
| queries 使用的 column 都存在    | 不會出現 `column does not exist`                                                |   3% | Pass / Partial / Fail |
| availability 查詢支援           | schema 支援 route stop order、available seats、date filter                      |   2% | Pass / Partial / Fail |
| execute_booking 支援            | schema 支援 booking insert + payment insert                                     |   2% | Pass / Partial / Fail |
| cancellation / payment 查詢支援 | schema 支援 booking status update、payment status update、refund policy windows |   1% | Pass / Partial / Fail |

## H 類判斷標準

|  得分 | 判斷                              |
| ----: | --------------------------------- |
| 9–10% | schema 和 queries 高度相容        |
|  7–8% | 大多相容，少數功能要實測          |
|  5–6% | 可能有 table/column mismatch 風險 |
|   <5% | queries 很可能 runtime error      |

---

# 四、Critical Blocker 判斷規則

如果出現以下任一問題，請直接標記為 **Critical Blocker**：

```text
1. schema.sql 無法成功執行，例如 SQL syntax error。
2. 主要表缺失，例如沒有 users / bookings / schedules。
3. queries.py 使用的 table 或 column 在 schema 中不存在。
4. seed 雖然能跑，但 key relational tables 幾乎沒資料。
5. password 明文儲存，且 register_user 沒有 hash。
6. schedule stops 沒有獨立表，導致 stop order 無法查。
7. bookings 或 payments 的 schema 無法支援 execute_booking。
8. payment 無法支援 query_payment_info 查詢 known booking ID。
```

如果沒有上述問題，即使有一些設計不完美，也可以判斷為：

```text
No critical blockers.
```

---

# 五、低風險問題範例

如果發現以下問題，可以標記為 **Low Risk**，不要過度扣分：

```text
1. TIMESTAMPTZ 用在純日期或純時間，但 queries 能正常處理。
2. return ticket 沒有完整特殊計價。
3. station_closures / delay_records 等 extension table 不完整。
4. updated_at 沒有 trigger 自動更新。
5. user_id 用 MAX + 1，而不是 sequence。
6. soft delete 與 unique constraint 有些邊界情境不完美。
7. 註解不足但主要 schema 可運行。
```

這些會影響高分，但通常不會導致 live test 主功能直接失敗。

---

# 六、最終判斷模板

請 AI agent 最後用這個格式總結：

```text
## Final Score Estimate

A. Table Completeness: __ / 20
B. PK/FK Correctness: __ / 20
C. Data Types: __ / 15
D. Password Storage: __ / 10
E. Normalisation: __ / 10
F. Delete Strategy / Cascade Behavior: __ / 10
G. PK Design Comment: __ / 5
H. Query Compatibility: __ / 10

Estimated Schema Completion: __%

## Critical Blockers

- None / list blockers

## Main Risks

- Risk 1
- Risk 2
- Risk 3

## Recommendation

Safe enough for 80–90% target: Yes / No

Reason:
[簡短說明]
```

---

# 七、可直接貼給 AI agent 的完整 prompt

你可以直接複製下面這段：

```text
You are evaluating the relational database schema for the IM2002 TransitFlow final project.

Please inspect `databases/relational/schema.sql` and evaluate whether it satisfies the project requirements at an 80–90% target level. We do not need a perfect full-score design. Focus on whether there are serious issues that could cause static evaluation failure, seed/query incompatibility, or live testing failure.

Use the following weighted checklist:

A. Table Completeness — 20%
- metro_stations or equivalent table exists: 2%
- national_rail_stations or equivalent table exists: 2%
- metro_schedules table exists: 2%
- metro_schedule_stops table exists and includes stop_order: 3%
- national_rail_schedules table exists: 2%
- national_rail_schedule_stops table exists and includes stop_order: 3%
- national rail fare class / fare rate table exists: 2%
- seats / seat layout table exists: 2%
- users / credentials tables exist: 2%
- bookings / metro trips / payments tables exist: 2%

B. Primary Key / Foreign Key Correctness — 20%
- every major table has a primary key: 4%
- schedule stops correctly reference schedule and station tables: 4%
- bookings correctly reference user, schedule, origin station, destination station: 4%
- bookings can be tied to valid seat / coach / fare class data: 3%
- payments can be tied to national rail bookings or metro trips: 3%
- FK target columns are PK or UNIQUE: 2%

C. Data Types — 15%
- fare / amount fields use NUMERIC or DECIMAL: 4%
- datetime event fields use TIMESTAMPTZ or equivalent reasonable type: 3%
- boolean flags use BOOLEAN: 3%
- order / count / duration fields use integer types: 3%
- structured data is not over-stored as TEXT: 2%

D. Password Storage — 10%
- schema does not store plain-text passwords: 3%
- password_hash or equivalent field exists: 3%
- register_user actually calls bcrypt / argon2 / scrypt / PBKDF2 before storing passwords: 4%

E. Normalisation — 10%
- metro schedule stops are in a separate table with schedule_id, station_id, stop_order: 3%
- national rail schedule stops are in a separate table with schedule_id, station_id, stop_order: 3%
- fare classes are queryable with SQL, not hidden only inside JSON/TEXT: 2%
- seat layout is queryable by schedule and fare class: 2%

F. Delete Strategy / Cascade Behavior — 10%
- delete strategy is consistent across main tables: 3%
- schema comments explain the delete strategy: 2%
- foreign keys explicitly specify ON DELETE CASCADE / RESTRICT / SET NULL: 4%
- important transaction records such as bookings/payments are not easily deleted accidentally: 1%

G. PK Design Comment — 5%
- PK type choices are clear and reasonable: 2%
- comments explain why SERIAL / UUID / business keys are used: 3%

H. Query Compatibility — 10%
- all tables used by `databases/relational/queries.py` exist: 2%
- all columns used by `queries.py` exist: 3%
- schema supports national rail availability queries with route order, date filter, and seat counts: 2%
- schema supports execute_booking inserting both booking and payment: 2%
- schema supports cancellation, payment lookup, and refund policy windows: 1%

Please output:

1. Overall estimated completion percentage.
2. Risk level: Low / Medium / High.
3. Whether the schema is safe enough for an 80–90% target.
4. A score breakdown for A–H.
5. Critical blockers, if any.
6. Main risks.
7. Recommended fixes, but only for issues that could meaningfully affect grading or live testing.

Do not over-penalize small design imperfections that do not break seed, queries, or live testing.
```
