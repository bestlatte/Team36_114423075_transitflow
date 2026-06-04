這裡有排除schema-refactor-suggestions的結構問題，只聚焦在"在還沒修改schemas前， `queries.py` 本身已存在的問題"。後續改完schemas後，或是修改schemas時可以一併參考，兩者在設計上有一定的相依性。

---

# `queries.py` 關鍵問題說明文件

## 一、整體結論

目前這份 `queries.py` 基本上有把官方 skeleton 要求的函式都補上，也有區分：

| 類型       | 說明                                         |
| ---------- | -------------------------------------------- |
| `query_`   | read-only lookup，給 agent 查資料            |
| `execute_` | write operation，例如 booking / cancellation |

這和官方 `queries.py` 的設計方向一致。官方也明確說這個 relational layer 要處理 dual-network transit、availability、fares、bookings、seat selection，而 vector functions 不應修改。([GitHub][1])

但是目前實作仍有幾個會直接影響系統正常問答與訂票流程的問題：

| 優先度 | 問題                                                                           | 影響                                                   |
| ------ | ------------------------------------------------------------------------------ | ------------------------------------------------------ |
| P1     | `query_national_rail_availability()` 回傳資訊太少                              | agent 查到班次後，無法完整回答班次、時間、票價相關問題 |
| P1     | `execute_booking()` 永遠使用 `first_train_time` 作為 departure time            | 使用者不能選實際發車時間，訂票結果容易錯               |
| P1     | `query_available_seats()` / `execute_booking()` 沒有用 departure time 區分座位 | 同一天同 schedule 不同班次會錯誤共用座位狀態           |
| P1     | `execute_booking()` 沒檢查 `operates_on`                                       | 可能訂到該 schedule 不營運的日期                       |
| P2     | `ticket_type` 沒有限制 national rail 只能用 `single` / `return`                | 可能讓 national rail 訂單塞入 `day_pass` 或非法票種    |
| P2     | `return` ticket 被當成 single ticket 計價                                      | 和 ticket type 語意不完整相符                          |

---

# 二、P1：`query_national_rail_availability()` 回傳資訊太少

## 1. 官方要求

官方 skeleton 對這個函式的描述是：

> Return national rail schedules that serve both origin and destination stations in the correct order, along with seat occupancy for the requested travel date.

也就是它不是只要查「有沒有班次」，而是要查出：

1. 哪些 national rail schedules 可以服務 origin → destination。
2. origin / destination 的順序正確。
3. travel date 當天的座位占用或剩餘狀態。([GitHub][1])

---

## 2. 目前實作

目前 `query_national_rail_availability()` 查詢後只回傳：

```python
{
    "schedule_id": row["schedule_id"],
    "available_seats": int(row["available_seats"]),
}
```

也就是只有：

| 欄位              | 說明         |
| ----------------- | ------------ |
| `schedule_id`     | 班次 ID      |
| `available_seats` | 總剩餘座位數 |

---

## 3. 問題

這會導致 agent 很難回答完整問題。

例如使用者問：

> I want to travel from NR01 to NR05. What trains are available?

目前 agent 只會拿到：

```json
[
  {
    "schedule_id": "NR_SCH01",
    "available_seats": 24
  }
]
```

但它不知道：

| 應該知道的資訊                | 目前是否回傳 |
| ----------------------------- | ------------ |
| line                          | 沒有         |
| service_type                  | 沒有         |
| direction                     | 沒有         |
| first_train_time              | 沒有         |
| last_train_time               | 沒有         |
| frequency_min                 | 沒有         |
| origin station name           | 沒有         |
| destination station name      | 沒有         |
| stops_travelled               | 沒有         |
| journey_time_min              | 沒有         |
| standard / first class 座位數 | 沒有         |

其中最重要的是：
`query_national_rail_fare()` 需要 `stops_travelled` 才能算票價，官方函式簽名也要求傳入 `stops_travelled`。([GitHub][1])

但 availability 沒有回傳 `stops_travelled`，所以 agent 查到可用 schedule 後，還是不知道要怎麼正確呼叫 fare function。

---

## 4. 建議修正

`query_national_rail_availability()` 應該至少回傳：

```python
{
    "schedule_id": "...",
    "line": "...",
    "service_type": "...",
    "direction": "...",
    "origin_station_id": "...",
    "destination_station_id": "...",
    "origin_name": "...",
    "destination_name": "...",
    "first_train_time": "...",
    "last_train_time": "...",
    "frequency_min": 30,
    "operates_on": ["mon", "tue", "wed", "thu", "fri"],
    "origin_stop_order": 1,
    "dest_stop_order": 5,
    "stops_travelled": 4,
    "journey_time_min": 48,
    "available_seats": 24
}
```

更完整的話，可以再加：

```python
"available_seats_by_class": {
    "standard": 20,
    "first": 4
}
```

---

# 三、P1：`execute_booking()` 永遠使用第一班車時間

## 1. 目前實作

目前 `execute_booking()` 沒有讓使用者指定實際發車時間，而是直接查：

```sql
SELECT first_train_time FROM national_rail_schedules
WHERE schedule_id = %s AND is_deleted = FALSE
```

接著把 `first_train_time` 和 `travel_date` 合成 `departure_time`。

也就是說，不管使用者實際想訂 07:30、08:00、09:15，系統都會自動塞成該 schedule 的第一班車時間。

---

## 2. 為什麼這是問題？

`bookings.json` 裡的資料明確有 `departure_time`，而且同一個 schedule 可能出現不同發車時間，例如 `NR_SCH01` 有 07:00、07:30 等不同紀錄。([GitHub][2])

這代表資料模型中的 booking 不是只訂：

```text
schedule_id + travel_date
```

而是應該訂：

```text
schedule_id + travel_date + departure_time
```

---

## 3. 影響

這會直接造成幾個系統錯誤：

| 問題                       | 說明                               |
| -------------------------- | ---------------------------------- |
| 使用者不能選實際發車時間   | 所有新訂單都會變成第一班車         |
| 訂票結果與使用者期待不一致 | 使用者想訂 09:15，但系統回傳 07:00 |
| 後續取消票退款時間會錯     | refund 根據 `departure_time` 計算  |
| 座位判斷會跟實際班次不一致 | 不同時間的列車應該有各自的座位狀態 |

---

## 4. 建議修正

理想上，`execute_booking()` 應該新增 `departure_time` 參數：

```python
def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
    departure_time: str | None = None,
) -> tuple[bool, dict | str]:
```

如果不想改官方函式簽名，至少也應該在 availability 回傳可用 departure times，並在 agent 層明確處理。不過從系統正確性來看，`execute_booking()` 本身最好還是要接收實際 departure time。

---

# 四、P1：座位可用性沒有區分 departure time

## 1. 目前實作

`query_available_seats()` 目前排除已訂座位時，只看：

```sql
b.schedule_id = %s
AND b.travel_date::date = %s::date
AND b.status != 'cancelled'
```

沒有比對 `departure_time`。

`execute_booking()` 裡面檢查座位是否被訂走時，也同樣只看：

```sql
schedule_id + seat_id + travel_date
```

沒有納入 `departure_time`。

---

## 2. 為什麼這是問題？

National rail schedule 看起來是「班次模板」，不是單一列車。
因為 schedule 有：

| 欄位               | 意義         |
| ------------------ | ------------ |
| `first_train_time` | 第一班時間   |
| `last_train_time`  | 最後一班時間 |
| `frequency_min`    | 幾分鐘一班   |

所以同一個 schedule 在同一天內會有多個實際發車時間。

因此座位是否可用，應該看：

```text
schedule_id + travel_date + departure_time + coach + seat_id
```

而不是只看：

```text
schedule_id + travel_date + seat_id
```

---

## 3. 具體錯誤情境

假設：

| 日期       | schedule | departure_time | seat |
| ---------- | -------- | -------------- | ---- |
| 2026-04-20 | NR_SCH01 | 07:00          | B04  |
| 2026-04-20 | NR_SCH01 | 07:30          | B04  |

這是合理的，因為它們是兩班不同列車。
但目前程式會認為：

> 只要 2026-04-20 的 NR_SCH01 有人訂過 B04，這一天全部 NR_SCH01 的 B04 都不能再訂。

這會讓系統低估座位數，也會造成很多原本可以訂的票被錯誤擋掉。

---

## 4. 建議修正

### `query_available_seats()` 建議改成：

```python
def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
    departure_time: str,
) -> list[dict]:
```

SQL 裡面補上：

```sql
AND b.departure_time::time = %s::time
```

### `execute_booking()` 裡面的 seat conflict check 也要改成：

```sql
SELECT booking_id
FROM bookings
WHERE schedule_id = %s
  AND seat_id = %s
  AND coach = %s
  AND travel_date::date = %s::date
  AND departure_time::time = %s::time
  AND status != 'cancelled'
  AND is_deleted = FALSE
```

---

# 五、P1：`execute_booking()` 沒有檢查營運日期 `operates_on`

## 1. 目前狀況

`query_national_rail_availability()` 有使用 `travel_date` 算 weekday，並檢查該 weekday 是否存在於 `nrs.operates_on`。

但是 `execute_booking()` 沒有再次檢查。

---

## 2. 為什麼這是問題？

查詢函式有檢查，不代表寫入函式就可以不檢查。
因為 agent 或測試程式可能直接呼叫：

```python
execute_booking(...)
```

如果 `execute_booking()` 沒有檢查 `operates_on`，就可能把訂單寫進一個該 schedule 根本不營運的日期。

---

## 3. 影響

| 情境                         | 結果               |
| ---------------------------- | ------------------ |
| 使用者查詢後再訂票           | 可能正常           |
| agent 直接呼叫訂票           | 可能訂到非營運日   |
| 測試直接呼叫 execute_booking | 可能通過錯誤資料   |
| 資料庫後續查詢               | 出現不合理 booking |

---

## 4. 建議修正

在 `execute_booking()` 裡查 schedule 時，不要只查 `first_train_time`，應該一起查：

```sql
SELECT first_train_time, last_train_time, frequency_min, operates_on
FROM national_rail_schedules
WHERE schedule_id = %s AND is_deleted = FALSE
```

然後檢查：

```python
weekday = _weekday_code(travel_date)

if weekday not in sched_row["operates_on"]:
    return _fail_transaction(
        conn,
        f"Schedule {schedule_id} does not operate on {weekday}."
    )
```

如果有提供 `departure_time`，也應該檢查它是否落在 `first_train_time` 到 `last_train_time` 之間，並符合 `frequency_min` 的間隔規則。

---

# 六、P2：`ticket_type` 沒有限制 national rail 票種

## 1. 官方語意

官方 `execute_booking()` 的 docstring 明確寫：

```text
ticket_type: "single" (default) or "return"
```

所以 national rail booking 預期只支援 `single` 或 `return`。([GitHub][1])

---

## 2. 目前實作

目前 `execute_booking()` 沒有檢查 `ticket_type`，直接把傳入值 insert 進 `bookings`。

所以理論上這些都會被接受：

```python
ticket_type="single"      # 合理
ticket_type="return"      # 合理
ticket_type="day_pass"    # 不合理，這是 metro 用
ticket_type="abc"         # 不合理
```

---

## 3. 對照 mock data

`ticket_types.json` 裡可以看到：

| ticket_type | 適用範圍              |
| ----------- | --------------------- |
| `single`    | metro / national rail |
| `return`    | national rail         |
| `day_pass`  | metro                 |

也就是 `day_pass` 不應該進入 national rail booking。([GitHub][3])

---

## 4. 建議修正

最小修正：

```python
if ticket_type not in ("single", "return"):
    return _fail_transaction(
        conn,
        "National rail ticket_type must be 'single' or 'return'."
    )
```

如果 schema 之後有 `ticket_types` / `ticket_type_networks`，則可以改用資料庫查詢判斷。

---

# 七、P2：`return` ticket 目前被當成 single ticket 計價

## 1. 目前實作

目前票價計算邏輯是：

```python
amount = base_fare_usd + stops_travelled * per_stop_rate_usd
```

不管 `ticket_type` 是 `single` 還是 `return`，都是同一套算法。

---

## 2. 為什麼要注意？

`bookings.json` 裡確實存在 `ticket_type = "return"` 的 national rail booking。([GitHub][2])

所以如果系統允許 return ticket，但金額仍然當 single ticket 算，會有語意不一致：

| ticket_type | 目前處理         |
| ----------- | ---------------- |
| `single`    | 單程票價         |
| `return`    | 仍然單程票價     |
| `day_pass`  | 也可能被錯誤塞入 |

---

## 3. 建議處理方式

這點可以分成兩種策略。

### 策略 A：先限制只支援 single

如果短期不想處理 return ticket，就明確限制：

```python
if ticket_type != "single":
    return _fail_transaction(
        conn,
        "Only single tickets are currently supported for booking."
    )
```

這樣比較保守，但不會產生錯誤資料。

### 策略 B：支援 return，但明確定義規則

例如：

```python
if ticket_type == "return":
    amount = single_amount * 2
```

或根據 `booking_rules.json` / policy data 做折扣。
不過這會牽涉更多規則，不一定是目前最優先。

---

# 八、建議優先修正順序

如果只挑最影響系統運行的部分，我會建議照這個順序修：

## 第一優先：讓 agent 查得到足夠資料

先修：

```python
query_national_rail_availability()
```

讓它回傳：

| 必要欄位                                                 | 原因                                |
| -------------------------------------------------------- | ----------------------------------- |
| `line` / `service_type` / `direction`                    | 用來描述班次                        |
| `first_train_time` / `last_train_time` / `frequency_min` | 用來回答時間                        |
| `origin_name` / `destination_name`                       | 用來回答自然語言                    |
| `stops_travelled`                                        | 用來接 `query_national_rail_fare()` |
| `journey_time_min`                                       | 用來回答旅程時間                    |
| `available_seats`                                        | 用來回答是否可訂                    |

這是最直接影響 AI assistant 回答品質的地方。

---

## 第二優先：修正訂票的 departure time

接著修：

```python
execute_booking()
query_available_seats()
```

讓訂票與座位查詢可以區分：

```text
schedule_id + travel_date + departure_time
```

否則 national rail booking 的核心邏輯會不準。

---

## 第三優先：補上 execute_booking 的防呆

至少補：

| 檢查                                  | 原因                             |
| ------------------------------------- | -------------------------------- |
| `operates_on`                         | 避免訂到非營運日                 |
| `ticket_type in ("single", "return")` | 避免 national rail 出現 day_pass |
| departure time 是否在營運時間內       | 避免訂到不存在的發車時間         |

---

# 九、精簡版結論

最關鍵的問題，可以濃縮成三句：

1. **`query_national_rail_availability()` 回傳資訊太少，導致 agent 查到 schedule_id 之後，仍然無法完整回答班次時間、旅程站數、票價計算所需資訊。**

2. **`execute_booking()` 目前永遠使用 `first_train_time` 當 departure time，沒有支援 mock data 中實際存在的不同 `departure_time`，因此訂票結果會和真實班次不一致。**

3. **`query_available_seats()` 和 `execute_booking()` 都沒有用 `departure_time` 區分座位狀態，會把同一天同 schedule 的不同班次錯誤視為共用同一份座位。**

所以最建議優先修的是：

```text
availability 回傳內容不足
→ departure_time 訂票語意缺失
→ seat availability 沒有區分 departure_time
```
