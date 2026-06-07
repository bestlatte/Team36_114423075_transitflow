# AI Collaboration Examples

本文件記錄我在 TransitFlow 專案中如何使用 AI 工具（例如 Cursor、Gemini、Codex 等）協助完成資料庫設計、查詢實作、Graph extension、Vector/RAG extension，以及除錯修正。每個例子都包含 Context、Prompt、Outcome 三個欄位。

---


## Example 1: 使用 Rules / Skills 規範讓 AI 生成程式碼與修改 SQL

### Context（上下文）

在實作 `schema.sql`、`databases/relational/queries.py` 和 seeding scripts 時，我發現如果只對 AI 說「幫我寫 SQL」或「幫我實作這個 function」，AI 很容易產生看起來合理但不符合本專案的 code，例如使用不存在的 table name、改掉 function signature、沒有用 `%s` parameter、或回傳格式和 agent tool contract 不一致。

所以我把專案規範整理成 rules / skills 的md檔，再讓 AI 依照這些規範生成程式碼或修改 SQL。這些規範包含 coding style、資料庫命名、SQL 安全規則、固定 function signature、回傳格式、以及「不能發明不存在的表或欄位」，以及專案強制必須遵守的規範。


### Prompt（提示詞）

```text
你現在要依照我的 rules / skills 來協助我寫 code (會用@的方式夾帶我的skill跟rules的規範讓AI讀取)
請先告訴我如何實施這個過程，再產生專案程式碼的 Python / SQL / Cypher 修改。

```

### Outcome（結果）

AI 在 rules / skills 限制下產生的 code 比單純請它「幫我寫 function」更可用，可以更精準快速的產生出符合規範的內容，不用每次下prompt都要從新說明我目前需要遵守的底層規範，。

這種做法有用的地方是：

- AI 會遵守 `_connect()` 和 `RealDictCursor` 的既有 pattern。
- AI 會使用 `%s` parameter，降低 SQL injection 風險。
- AI 比較不會發明 `routes`、`fares`、`stations` 這種不存在於 schema 的 table。
- AI 會保留原本 function signature，不會讓 `skeleton/agent.py` 的 tool call 失效。

後續做的人工優化包括：

- 對照 `databases/relational/schema.sql` 檢查每個 table / column 是否真的存在。
- 補上 `is_deleted = FALSE` 條件，避免查到 soft-deleted records。
- 檢查回傳欄位是否包含 agent 後續會用到的 `schedule_id`、`stops_travelled`、station names 和時間資訊。
- 用 `scripts/check_relational_queries.py` 檢查 function 是否能被測試腳本正常呼叫。

用同樣的 rules / skills 方法讓 AI 修改 SQL schema，不是直接接受 AI code，而是先用 SKILL限制輸出規範並且告知如何更改，不要先動專案內容，再來才去修改裡面的程式碼，

---

## Example 2: 翻車案例 (2) — 空陣列導致正常查詢中斷

### Context（上下文）

在修復完繞道邏輯後，我重置資料庫，將所有車站設為未封閉，並進行正常路徑查詢。理論上，沒有任何車站被封閉時，系統應該回傳正常 route；結果系統卻莫名其妙回傳：

```json
{"found": false}
```

這導致正常導航完全癱瘓。也就是說，原本為了支援 station closure / rerouting 的邏輯，反而讓「沒有封閉車站」這個最基本的情境壞掉。

### Prompt（提示詞）

```text
我已經把所有 station 都 reset 成 open / not closed。
現在我在 Debug 面板輸入正常起終點，理論上應該找得到 route，
但結果回傳 {"found": false}。

我附上 Debug 面板截圖，裡面可以看到：
- 起點和終點都是存在的 station。
- 沒有任何 station 被關閉。
- route query 卻回傳 found: false。

這樣是對的嗎？
```

### Outcome（結果）

AI 再次給出爛答案。AI 先前設計的備用 Cypher 中有一行：

```cypher
MATCH (closed:Station {is_closed: true})
```

這行原本是用來抓取被封閉車站的黑名單，但它沒有考慮到當系統內「無封閉車站」時，這個 `MATCH` 會回傳空結果，並直接中斷整個查詢。換句話說，查詢還沒有走到真正找路的部分，就因為 closed station blacklist 是空的而失敗。

我透過 Debug 面板截圖發現問題：所有車站都已 reset 成 open，但正常路徑仍然回傳 `found: false`。這代表錯誤不是 station 狀態本身，而是 Cypher 查詢邏輯在「沒有封閉車站」時處理錯誤。

AI 後來捨棄了容易出錯的黑名單變數寫法，改用更直接的原生 path filtering：

```cypher
WHERE ALL(n IN nodes(p) WHERE n.is_closed = false OR n.is_closed IS NULL)
```

這個修正不需要先建立 closed station blacklist，而是直接檢查候選路徑上的每一個 node。只要路徑上的 station 沒有被標記為 closed，就允許這條路徑通過；如果舊資料沒有 `is_closed` 屬性，也視為 open。最後這才徹底解決了空陣列 / 空結果導致正常查詢中斷的問題。

---

## Example 3: 翻車案例 — AI 產生錯誤 Booking Constraint

### Context（上下文）

當我用 AI 協助整理 booking schema 時，AI 一開始給出了一個看起來合理、但不符合實際訂票需求的 constraint。問題不是 SQL 不能執行，而是它會讓「已取消的訂位」仍然永久佔用座位。

錯誤初稿類似：

```sql
ALTER TABLE bookings
    ADD CONSTRAINT uq_booking_seat_date
    UNIQUE (schedule_id, travel_date, seat_id);
```

這段 SQL 的問題是它沒有考慮 `status = 'cancelled'` 和 `is_deleted = TRUE` 的資料。只要某個座位曾經被訂過，即使後來取消，這個 unique constraint 仍然會阻止同一天同一班車再次賣出該座位。

### Prompt（提示詞）

```text

ALTER TABLE bookings
    ADD CONSTRAINT uq_booking_seat_date
    UNIQUE (schedule_id, travel_date, seat_id);

當我cancelled booking 之後，座位不應該繼續佔用；
也有 is_deleted 欄位，soft-deleted booking 不應該被視為 active。

請幫我檢查這個 constraint 是否符合需求。
如果不符合，請幫我修改已達成需求。
```

### Outcome（結果）

AI review 後指出一般 `UNIQUE` constraint 無法加上 `WHERE` 條件，因此不適合這個需求。這次應該使用 PostgreSQL 的 partial unique index，只限制 active bookings。

如何發現錯誤：

- 我取消一筆 booking 後，發現同一日期同一座位理論上應該可以再次被訂走。
- 但一般 `UNIQUE (schedule_id, travel_date, seat_id)` 會把 cancelled records 也算進去。
- 我把 booking table 的 `status`、`is_deleted` 欄位和需求一起貼回 AI，要求它只修正 constraint，不要重寫整個 schema。

最後修正為目前 `databases/relational/schema.sql` 中的版本：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_seat_date
    ON bookings(schedule_id, travel_date, seat_id)
    WHERE status != 'cancelled' AND is_deleted = FALSE;
```


---
