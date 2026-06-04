我覺得九、十、十一比較還好，其他的部分你斟酌看看，至少目前跑seed會報錯這點需要修改。

---

# 關聯式資料庫 schema / seed 工具問題說明

## 一、整體結論

目前這份 relational database 設計的優點是：
它有嘗試把 station、schedule、schedule stops、fare classes、seat layouts、users、bookings、metro travel、payments、feedback、ticket types、refund policies 拆成不同資料表，方向上符合關聯式資料庫設計。

但是對照 `train-mock-data` 後，可以看出幾個明顯問題：

| 優先度 | 問題                                                                                 | 影響                                            |
| ------ | ------------------------------------------------------------------------------------ | ----------------------------------------------- |
| P0     | `policy_documents` index 語法錯誤                                                    | PostgreSQL 初始化可能直接失敗                   |
| P0     | `payments.booking_id` 只能 FK 到 `bookings`，但 JSON 裡有 `MTxxx` metro trip payment | seed payments 一定會因 FK 失敗                  |
| P1     | 日期 / 時間型別大量使用 `TIMESTAMPTZ`                                                | 查詢、顯示、比對都容易出錯                      |
| P1     | 座位唯一性沒有包含 `departure_time`                                                  | 同一天不同發車時間可能不能賣同一座位            |
| P1     | `bookings` 沒有真正 FK 到 `seats`                                                    | 可能訂到不存在、不匹配的座位                    |
| P2     | `status`、`ticket_type`、`fare_class` 等缺少 CHECK / FK                              | 資料品質不穩                                    |
| P2     | `ticket_types` 有表，但沒有和 booking / metro trip 建立關聯                          | ticket rules 很難被資料庫保證                   |
| P2     | secret answer 明文儲存                                                               | 資安設計不一致                                  |
| P3     | soft delete 與 UNIQUE constraint 可能衝突                                            | 未來重新註冊或恢復資料會卡住                    |
| P3     | `updated_at` 不會自動更新                                                            | audit 欄位可信度不足                            |
| P3     | station closure 缺少 network type / FK                                               | 無法分辨 metro station 或 national rail station |

---

# 二、P0 問題：`policy_documents` index 語法錯誤

## 問題說明

目前 schema 裡的 vector index 是：

```sql
CREATE INDEX IF NOT EXISTS policy_documents_hnsw idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

這行 SQL 語法不正確。`CREATE INDEX IF NOT EXISTS` 後面只能接一個 index name，但這裡同時放了：

```text
policy_documents_hnsw idx_policy_documents_embedding
```

也就是兩個 index 名稱。schema 檔案中確實是這樣寫的。

## 影響

這個錯誤會造成 PostgreSQL 初始化時執行 `schema.sql` 失敗。
如果這份 schema 是被 Docker container 初始化時自動執行，整份 schema 後半段可能不會成功完成。

## 建議修正

改成只保留一個 index name：

```sql
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

或：

```sql
CREATE INDEX IF NOT EXISTS policy_documents_hnsw
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

---

# 三、P0 問題：`payments` 表設計與 JSON 資料不相容

這是參考 JSON 後最重要的校正。

## 原本 schema 的設計

目前 `payments` 表是這樣設計的：

```sql
CREATE TABLE IF NOT EXISTS payments (
    id         BIGSERIAL      PRIMARY KEY,
    payment_id VARCHAR(20)    NOT NULL UNIQUE,
    booking_id VARCHAR(20)    NOT NULL REFERENCES bookings(booking_id) ON DELETE RESTRICT,
    amount_usd DECIMAL(10,2)  NOT NULL,
    method     VARCHAR(20)    NOT NULL,
    status     VARCHAR(20)    NOT NULL DEFAULT 'paid',
    paid_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    ...
);
```

也就是說，`payments.booking_id` **只能指向 national rail 的 `bookings.booking_id`**。

## 但是 JSON 不是這樣

`train-mock-data/readme.md` 明確說：

> All transactions are associated with a payment record.

也就是 national rail booking 和 metro travel 都應該有 payment。資料集說明也列出 `payments.json` 是「Payment records for all transactions」。([GitHub][1])

而 `payments.json` 裡也真的混合了兩種交易 ID：

```json
{ "payment_id": "PM001", "booking_id": "BK001", ... }
{ "payment_id": "PM002", "booking_id": "MT001", ... }
{ "payment_id": "PM003", "booking_id": "BK002", ... }
{ "payment_id": "PM004", "booking_id": "MT002", ... }
```

其中 `BKxxx` 是 national rail booking，`MTxxx` 是 metro trip。([GitHub][2])

## seed 工具也會因此失敗

seed 工具目前是直接把 `payments.json` 的 `booking_id` 放進 `payments.booking_id`：

```python
cols = ["payment_id", "booking_id", "amount_usd", "method", "status", "paid_at"]
rows = [
    (d["payment_id"], d["booking_id"], d["amount_usd"], d["method"], d["status"], d["paid_at"])
    for d in data
]
```

所以當它遇到：

```json
"booking_id": "MT001"
```

資料庫會檢查：

```sql
REFERENCES bookings(booking_id)
```

但 `MT001` 不存在於 `bookings`，而是存在於 `metro_travel_history.trip_id`。因此 seed 到 `PM002` 時就會 FK violation，整個 transaction rollback。

## 建議修正方向

### 方案 A：保留單一 payments 表，加入交易類型

比較適合這個作業：

```sql
CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    payment_id VARCHAR(20) NOT NULL UNIQUE,
    transaction_type VARCHAR(20) NOT NULL CHECK (
        transaction_type IN ('national_rail_booking', 'metro_trip')
    ),
    transaction_id VARCHAR(20) NOT NULL,
    amount_usd DECIMAL(10,2) NOT NULL CHECK (amount_usd >= 0),
    method VARCHAR(20) NOT NULL CHECK (method IN ('credit_card', 'debit_card', 'ewallet')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('paid', 'refunded', 'failed')),
    paid_at TIMESTAMPTZ NOT NULL
);
```

seed 時根據 ID 前綴判斷：

```python
transaction_type = (
    "national_rail_booking"
    if d["booking_id"].startswith("BK")
    else "metro_trip"
)
```

這樣可以相容目前 JSON。

### 方案 B：拆成兩張 payment 表

```sql
booking_payments
metro_trip_payments
```

這樣 FK 最乾淨，但查詢「使用者所有付款紀錄」時會比較麻煩，需要 `UNION`。

### 方案 C：保留 `booking_id` 欄位名稱，但移除 FK

不建議。雖然 seed 可以過，但資料庫失去 referential integrity，跟關聯式資料庫要求不合。

---

# 四、P1 問題：日期 / 時間型別不適合

## 問題說明

目前很多欄位都使用 `TIMESTAMPTZ`：

```sql
first_train_time TIMESTAMPTZ
last_train_time  TIMESTAMPTZ
travel_date      TIMESTAMPTZ
departure_time   TIMESTAMPTZ
date_of_birth    TIMESTAMPTZ
```

在 schema 裡，metro schedule、national rail schedule、users、bookings、metro travel 都是這種設計。

seed 工具為了把 `"07:00"` 這種純時間塞入 `TIMESTAMPTZ`，使用固定日期 `2000-01-01`：

```python
def _service_time_at_utc(time_text: str) -> datetime:
    """Represent schedule-only times as UTC timestamps on a fixed service date."""
    parsed = datetime.strptime(time_text, "%H:%M").time()
    return datetime(2000, 1, 1, parsed.hour, parsed.minute, tzinfo=timezone.utc)
```

而 `travel_date` 也被轉成 UTC timestamp。

## 對照 JSON 後的判斷

JSON 裡的資料其實分成三種：

| JSON 欄位                                 | 範例                     | 正確型別                              |
| ----------------------------------------- | ------------------------ | ------------------------------------- |
| `first_train_time` / `last_train_time`    | `"07:00"`                | `TIME`                                |
| `departure_time`                          | `"07:00"`                | `TIME`，或搭配 `travel_date` 組合使用 |
| `travel_date`                             | `"2026-04-02"`           | `DATE`                                |
| `date_of_birth`                           | `"1990-03-14"`           | `DATE`                                |
| `booked_at` / `paid_at` / `registered_at` | `"2026-04-01T10:15:00Z"` | `TIMESTAMPTZ`                         |

例如 `bookings.json` 中同時有 `travel_date: "2026-04-02"`、`departure_time: "07:00"`、`booked_at: "2026-04-01T10:15:00Z"`，這代表日期、服務時間、實際事件時間是不同語意。([GitHub][3])

## 影響

目前設計會造成：

| 問題                     | 例子                                                      |
| ------------------------ | --------------------------------------------------------- |
| 查詢日期麻煩             | 查 `travel_date = '2026-04-02'` 可能要處理 timestamp cast |
| 時區轉換可能混淆         | UTC midnight 在台灣顯示會變成早上 08:00                   |
| schedule time 語意怪     | `2000-01-01 07:00 UTC` 其實不是實際發車日期               |
| AI query function 較難寫 | 使用者問「7 點出發」時，要比對 timestamp 而不是 time      |

## 建議修正

```sql
first_train_time TIME NOT NULL
last_train_time TIME NOT NULL
travel_date DATE NOT NULL
departure_time TIME NOT NULL
date_of_birth DATE
booked_at TIMESTAMPTZ NOT NULL
paid_at TIMESTAMPTZ NOT NULL
registered_at TIMESTAMPTZ NOT NULL
```

seed 工具也應該改成：

```python
def _parse_time(time_text):
    return datetime.strptime(time_text, "%H:%M").time()

def _parse_date(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").date()
```

---

# 五、P1 問題：座位唯一性沒有包含 `departure_time`

## 問題說明

目前 schema 的座位防重複訂票 index 是：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_seat_date
    ON bookings(schedule_id, travel_date, seat_id)
    WHERE status != 'cancelled' AND is_deleted = FALSE;
```

這代表同一個：

```text
schedule_id + travel_date + seat_id
```

只能出現一次。

## 對照 JSON 後的判斷

`bookings.json` 裡有：

```json
"schedule_id": "NR_SCH01",
"travel_date": "2026-04-02",
"departure_time": "07:00",
"seat_id": "B05"
```

而 national rail schedules 是一種「固定營運班次模板」，有 `first_train_time`、`last_train_time`、`frequency_min`，代表同一個 schedule 在一天內可能產生多個實際發車時間。schema 也確實有 `frequency_min` 欄位。

所以真正唯一的座位使用，應該至少是：

```text
schedule_id + travel_date + departure_time + coach + seat_id
```

不是只有：

```text
schedule_id + travel_date + seat_id
```

## 影響

假設同一天：

| 發車時間 | 座位 | 合理嗎？       |
| -------- | ---- | -------------- |
| 07:00    | B05  | 可以被訂       |
| 07:30    | B05  | 也應該可以被訂 |
| 08:00    | B05  | 也應該可以被訂 |

但目前 unique index 會把後兩筆擋掉。

## 建議修正

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_seat_departure
ON bookings(schedule_id, travel_date, departure_time, coach, seat_id)
WHERE status != 'cancelled' AND is_deleted = FALSE;
```

---

# 六、P1 問題：`bookings` 沒有真正約束座位存在與座位等級

## 問題說明

目前 `seats` 表有：

```sql
schedule_id
coach
fare_class
seat_id
seat_row
seat_column
UNIQUE (schedule_id, seat_id)
```

但 `bookings` 表裡的：

```sql
schedule_id
fare_class
coach
seat_id
```

沒有 composite FK 指向 `seats`。

## 影響

資料庫目前無法阻止這些錯誤：

| 錯誤情境                              | 目前 DB 會擋嗎？ |
| ------------------------------------- | ---------------- |
| 訂不存在的 seat_id                    | 不會             |
| `seat_id` 存在，但 coach 錯           | 不會             |
| seat 是 standard，但 booking 填 first | 不會             |
| fare_class 不存在於該 schedule        | 不會             |

`ticket_types.json` 也明確說 national rail 有 `standard` / `first`，而且有 seat assignment；metro 則沒有 seat assignment。([GitHub][4])

## 建議修正

先讓 `seats` 有更完整的唯一鍵：

```sql
ALTER TABLE seats
ADD CONSTRAINT uq_seats_schedule_coach_seat_class
UNIQUE (schedule_id, coach, seat_id, fare_class);
```

再讓 `bookings` 指向它：

```sql
ALTER TABLE bookings
ADD CONSTRAINT fk_bookings_seat
FOREIGN KEY (schedule_id, coach, seat_id, fare_class)
REFERENCES seats(schedule_id, coach, seat_id, fare_class);
```

同時 `bookings(schedule_id, fare_class)` 也應該 FK 到 `national_rail_fare_classes(schedule_id, fare_class)`。

---

# 七、P2 問題：`ticket_type` 有表，但 booking / metro trip 沒有 FK

## 問題說明

schema 有建立 `ticket_types`：

```sql
CREATE TABLE IF NOT EXISTS ticket_types (
    ticket_type VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    available_on TEXT[] NOT NULL DEFAULT '{}'
);
```

但 `bookings.ticket_type` 和 `metro_travel_history.ticket_type` 沒有 FK 到 `ticket_types.ticket_type`。

## 對照 JSON 後的判斷

`ticket_types.json` 只有三種：

| ticket type | 可用網路             |
| ----------- | -------------------- |
| `single`    | metro、national_rail |
| `return`    | national_rail        |
| `day_pass`  | metro                |

JSON 也明確描述：metro 沒有 seat assignment，national rail 有 seat assignment。([GitHub][4])

## 影響

目前資料庫會允許：

```text
bookings.ticket_type = 'day_pass'
metro_travel_history.ticket_type = 'return'
ticket_type = 'abc'
```

這些都不符合資料集規則。

## 建議修正

至少加基本 FK：

```sql
ALTER TABLE bookings
ADD CONSTRAINT fk_bookings_ticket_type
FOREIGN KEY (ticket_type)
REFERENCES ticket_types(ticket_type);

ALTER TABLE metro_travel_history
ADD CONSTRAINT fk_metro_ticket_type
FOREIGN KEY (ticket_type)
REFERENCES ticket_types(ticket_type);
```

但這只能確保 ticket type 存在，不能保證網路適用性。
更完整做法是拆出 `ticket_type_networks`：

```sql
CREATE TABLE ticket_type_networks (
    ticket_type VARCHAR(20) REFERENCES ticket_types(ticket_type),
    network_type VARCHAR(20) CHECK (network_type IN ('metro', 'national_rail')),
    PRIMARY KEY (ticket_type, network_type)
);
```

然後 booking / metro travel 透過 application 或 trigger 檢查。

---

# 八、P2 問題：`status`、`method`、`fare_class` 缺少 CHECK constraint

## 問題說明

目前很多欄位是自由文字：

```sql
status VARCHAR(20)
method VARCHAR(20)
fare_class VARCHAR(20)
service_type VARCHAR(20)
direction VARCHAR(20)
```

只有 `feedback.rating` 有做 `CHECK (rating >= 1 AND rating <= 5)`。

## 對照 JSON 後可以推導的合理 enum

### bookings.status

從 `bookings.json` 可以看到：

```text
completed
cancelled
confirmed
```

([GitHub][3])

建議：

```sql
CHECK (status IN ('confirmed', 'completed', 'cancelled'))
```

### payments.status

從 `payments.json` 可以看到：

```text
paid
refunded
```

([GitHub][2])

建議：

```sql
CHECK (status IN ('paid', 'refunded', 'failed'))
```

### payments.method

從 `payments.json` 可以看到：

```text
credit_card
debit_card
ewallet
```

([GitHub][2])

建議：

```sql
CHECK (method IN ('credit_card', 'debit_card', 'ewallet'))
```

### fare_class

`ticket_types.json` 和 national rail ticket rules 顯示 national rail 有：

```text
standard
first
```

([GitHub][4])

建議：

```sql
CHECK (fare_class IN ('standard', 'first'))
```

---

# 九、P2 問題：secret answer 明文儲存

## 問題說明

目前 `user_credentials` 表是：

```sql
password_hash
secret_question
secret_answer
```

`password_hash` 有 hash，但 `secret_answer` 是明文。

seed 工具也是這樣：

```python
cred_rows.append((
    d["user_id"],
    _hash_password(d["password"]),
    d["secret_question"],
    d["secret_answer"],
))
```

## 對照 JSON 後的判斷

`registered_users.json` 裡有 password、secret question、secret answer，例如：

```json
"password": "alice1990",
"secret_question": "What was the name of your first pet?",
"secret_answer": "Biscuit"
```

([GitHub][5])

password 有 hash 是正確的，但 secret answer 同樣可用於帳號恢復，也應該 hash。

## 建議修正

schema：

```sql
secret_answer_hash VARCHAR(255) NOT NULL
```

seed：

```python
_hash_password(d["secret_answer"].lower().strip())
```

驗證時也要做同樣 normalize：

```python
input_answer.lower().strip()
```

---

# 十、P3 問題：soft delete 與 UNIQUE constraint 可能衝突

## 問題說明

schema 註解說 relational application tables 使用 soft delete，也就是每張表都有：

```sql
is_deleted BOOLEAN NOT NULL DEFAULT FALSE
```

但有些欄位仍然使用一般 unique：

```sql
email VARCHAR(200) NOT NULL UNIQUE
booking_id VARCHAR(20) NOT NULL UNIQUE
payment_id VARCHAR(20) NOT NULL UNIQUE
```

## 影響

如果 user 被 soft delete，之後想用同一個 email 重新註冊，仍然會被 unique constraint 擋住。

這不一定是錯，因為有些系統會希望 email 永遠不能重複。
但如果 soft delete 的語意是「邏輯刪除後可重新建立」，那目前設計就不一致。

## 建議修正

針對 email 可改成 partial unique index：

```sql
CREATE UNIQUE INDEX ux_users_email_active
ON users(email)
WHERE is_deleted = FALSE;
```

但 `booking_id`、`payment_id` 這種交易 ID，我反而建議維持永久唯一，不要因 soft delete 重用。

---

# 十一、P3 問題：`updated_at` 不會自動更新

## 問題說明

幾乎每張表都有：

```sql
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

但 schema 沒有 trigger，所以 update 資料時，`updated_at` 不會自動變。

## 影響

例如取消訂票：

```sql
UPDATE bookings
SET status = 'cancelled'
WHERE booking_id = 'BK001';
```

`updated_at` 不會跟著更新。
這會讓 audit 欄位失去意義。

## 建議修正

加入 trigger function：

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

對主要資料表加 trigger：

```sql
CREATE TRIGGER trg_bookings_updated_at
BEFORE UPDATE ON bookings
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
```

---

# 十二、P3 問題：station closure 無法分辨 metro / national rail

## 問題說明

目前 `station_closures` 是：

```sql
CREATE TABLE IF NOT EXISTS station_closures (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(10) NOT NULL,
    reason TEXT NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reopened_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

但系統有兩張 station table：

```text
metro_stations
national_rail_stations
```

因此單靠 `station_id` 無法知道封閉的是哪個 network 的站。

## 建議修正

```sql
CREATE TABLE station_closures (
    id SERIAL PRIMARY KEY,
    network_type VARCHAR(20) NOT NULL CHECK (
        network_type IN ('metro', 'national_rail')
    ),
    station_id VARCHAR(10) NOT NULL,
    reason TEXT NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reopened_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

如果想要 FK 最嚴謹，就拆成：

```text
metro_station_closures
national_rail_station_closures
```

---

# 十三、修正後建議的資料表方向

根據 JSON，建議 relational schema 至少要對應成這樣：

| JSON                              | 建議資料表                                                                              |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| `metro_stations.json`             | `metro_stations`                                                                        |
| `national_rail_stations.json`     | `national_rail_stations`                                                                |
| `metro_schedules.json`            | `metro_schedules`, `metro_schedule_stops`                                               |
| `national_rail_schedules.json`    | `national_rail_schedules`, `national_rail_schedule_stops`, `national_rail_fare_classes` |
| `national_rail_seat_layouts.json` | `seats`                                                                                 |
| `registered_users.json`           | `users`, `user_credentials`                                                             |
| `bookings.json`                   | `bookings`                                                                              |
| `metro_travel_history.json`       | `metro_travel_history`                                                                  |
| `payments.json`                   | `payments`，但必須支援 BK / MT 兩種交易                                                 |
| `feedback.json`                   | `feedbacks`                                                                             |
| `ticket_types.json`               | `ticket_types`, optional `ticket_type_networks`                                         |
| `refund_policy.json`              | `refund_policies`, `refund_policy_windows`                                              |
| `booking_rules.json`              | 可放 vector，也可正規化成 `booking_rules`                                               |
| `travel_policies.json`            | 通常放 vector/RAG 即可                                                                  |

資料集本身也說它包含 city metro、national rail、users、transactions、policies and rules，並且列出各 JSON 的用途。

---

# 十四、建議修正順序

## 第一階段：先讓 DB 能成功初始化與 seed

這些要先修：

1. 修掉 `policy_documents` index 語法。
2. 修 `payments` 表，讓它能支援 `BKxxx` 和 `MTxxx`。
3. 修改 `seed_payments()`，不要再假設所有 payment 都指向 booking。
4. 重新執行：

```bash
docker compose down -v
docker compose up -d
python skeleton/seed_postgres.py
```

---

## 第二階段：修正查詢會受影響的資料型別

建議改：

```sql
first_train_time TIME
last_train_time TIME
travel_date DATE
departure_time TIME
date_of_birth DATE
```

這會讓 `queries.py` 之後比較好寫，尤其是：

| query function                       | 會受影響的欄位                        |
| ------------------------------------ | ------------------------------------- |
| `query_national_rail_availability()` | `travel_date`, `departure_time`       |
| `query_metro_schedules()`            | `first_train_time`, `last_train_time` |
| `query_user_bookings()`              | `travel_date`, `booked_at`            |
| `query_payment_info()`               | `paid_at`                             |

---

## 第三階段：補強資料一致性

補：

1. booking seat FK。
2. booking fare class FK。
3. ticket type FK。
4. status / method / fare class CHECK。
5. updated_at trigger。
6. secret answer hash。

---
