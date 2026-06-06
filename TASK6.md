# TASK 6 EXTENSION — Combined Optional Extensions

本文件列出本組 Task 6 optional extension 的兩的加分項及其相關新增與修改內容，方便 TA 快速定位 extension code、資料庫變更、測試方式與預期結果。

1. **Graph Extension：即時車站封閉繞道系統**  
   讓系統可以將特定車站標記為關閉，並讓 Neo4j 路徑查詢避開已關閉車站。

2. **Vector / RAG Extension：Service Disruption Policy RAG Extension**  
   新增服務中斷相關政策文件，讓 `search_policy` 可以透過 pgvector similarity search 回答接駁巴士、嚴重服務中斷退款、替代交通補償等問題。

---

# Part A — Graph Extension: 即時車站封閉繞道系統

## 1. Motivation

真實世界的交通系統常會因為事故、停電、維修或其他突發狀況造成特定車站暫時關閉。原本的路線查詢只會根據固定圖形資料找路，無法反映「某站目前不可通行」的情況。

因此，本 extension 新增車站封閉狀態，讓系統可以：

- 透過 agent 呼叫 `toggle_station_closure` 工具，把指定車站標記為 open / closed。
- 在 Neo4j 的 `Station` 節點上使用 `is_closed` 屬性表示車站狀態。
- 修改路徑查詢邏輯，使路線規劃避開 `is_closed = true` 的車站。
- 讓 TransitFlow 更接近真實交通系統中的即時營運狀況。

---

## 2. Added / Modified Files

| File                              | Type     | Change                                                                              |
| --------------------------------- | -------- | ----------------------------------------------------------------------------------- |
| `skeleton/agent.py`               | Modified | 新增 / 保留 `toggle_station_closure` tool，讓 agent 可以呼叫 graph closure function |
| `databases/graph/queries.py`      | Modified | 新增 `execute_toggle_station_closure()`，並讓路徑查詢避開 closed station            |
| `skeleton/seed_neo4j.py`          | Modified | 在 `Station` 節點加入 `is_closed` 屬性，預設為 `false`                              |
| `databases/relational/schema.sql` | Modified | 新增 `station_closures` table，用於紀錄車站封閉事件與稽核資料                       |

---

## 3. Database / Graph Changes

### PostgreSQL: `station_closures`

新增 `station_closures` table，用於記錄車站封閉 / 重啟事件。

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

### Neo4j: `Station.is_closed`

所有 `Station` node 新增 `is_closed` 屬性：

```text
Station.is_closed = false
```

當使用者要求關閉車站時，系統會將該車站改為：

```text
Station.is_closed = true
```

---

## 4. Graph Query Changes

### `execute_toggle_station_closure(station_id, close_station)`

此 function 用於改變 Neo4j 中車站的營運狀態。

```cypher
MATCH (n:Station {id: $station_id})
SET n.is_closed = $status
RETURN n.name AS name, n.is_closed AS is_closed
```

當 `close_station = true` 時，車站會被標記為 closed；當 `close_station = false` 時，車站會被重新開啟。

### Route query avoids closed stations

路線查詢會避開已關閉車站，例如：

```cypher
WHERE ALL(n IN nodes(p) WHERE n.is_closed = false OR n.is_closed IS NULL)
```

或：

```cypher
WHERE NONE(n IN nodes(p)[1..-1] WHERE n.is_closed = true)
```

這代表只要某個路徑經過已關閉車站，該路徑就不會被選為有效路徑。

---

## 5. Agent Changes

在 `skeleton/agent.py` 中新增 / 保留 `toggle_station_closure` tool：

```text
toggle_station_closure(station_id, close_station)
```

此工具用於處理明確要求改變車站狀態的問題，例如：

```text
Old Town station (NR03) has an emergency. Please close this station.
```

---

## 6. Graph Extension Testing

### Test 1 — Normal route before closure

**Purpose:**  
確認在車站未關閉時，系統會走正常最短路徑。

**User query:**

```text
How do I get from Central (NR01) to Stonehaven (NR05)?
```

**Expected result:**  
系統應規劃出正常路徑，通常會經過 Old Town / Old Town Junction (`NR03`)。

---

### Test 2 — Close Old Town station

**Purpose:**  
確認 `toggle_station_closure` 可以被 agent 呼叫，並成功改變 Neo4j 中車站狀態。

**User query:**

```text
Old Town station (NR03) has an emergency. Please close this station.
```

**Expected tool call:**

```json
{
  "name": "toggle_station_closure",
  "params": {
    "station_id": "NR03",
    "close_station": true
  }
}
```

**Expected result:**

```text
Station Old Town / Old Town Junction (NR03) is now CLOSED.
```

---

### Test 3 — Re-route after closure

**Purpose:**  
確認路徑查詢會避開剛剛被關閉的車站。

**User query:**

```text
Now, how do I get from Central (NR01) to Stonehaven (NR05) again?
```

**Expected result:**  
系統應重新規劃一條不經過 `NR03` 的路線。這表示 Neo4j route query 已經正確使用 `is_closed` 狀態，並避開 closed station。

---

# Part B — Vector / RAG Extension: Service Disruption Policy RAG Extension

## 1. Motivation

原本的 RAG policy documents 已經能回答退票、延誤補償、票種、行李、寵物、腳踏車等一般政策問題，但對於服務中斷情境支援不足。

本 extension 新增 `service_disruption_policy.json`，補充以下政策：

- Replacement bus service policy
- Severe service disruption refund policy
- Alternative transport reimbursement policy
- Station closure policy

這些政策會被轉換成 embedding，並存入既有的 `policy_documents` pgvector table。當使用者詢問服務中斷相關政策時，agent 會透過 `search_policy` 進行 vector similarity search，找出最相關的政策文件。

---

## 2. Added / Modified Files

| File                                             | Type     | Change                                                                                              |
| ------------------------------------------------ | -------- | --------------------------------------------------------------------------------------------------- |
| `train-mock-data/service_disruption_policy.json` | Added    | 新增服務中斷政策資料                                                                                |
| `skeleton/seed_vectors.py`                       | Modified | 在 `build_documents()` 中讀取 `service_disruption_policy.json`，並將每筆政策轉成 vector document    |
| `skeleton/agent.py`                              | Modified | 更新 `search_policy` description 與 Ollama router prompt，使服務中斷類 policy 問題能導向 RAG search |

---

## 3. Database / Vector Changes

本 extension 沒有新增新的 vector table，而是使用既有的 pgvector table：

```sql
policy_documents(title, category, content, embedding, source_file)
```

新增的服務中斷政策會被 seed 成 `policy_documents` 中的新 vector entries：

| Policy ID | Title                                      | Category             |
| --------- | ------------------------------------------ | -------------------- |
| `SD001`   | Station Closure Policy                     | `service_disruption` |
| `SD002`   | Replacement Bus Service Policy             | `service_disruption` |
| `SD003`   | Severe Service Disruption Refund Policy    | `service_disruption` |
| `SD004`   | Alternative Transport Reimbursement Policy | `service_disruption` |

---

## 4. Vector Seeding Logic

在 `skeleton/seed_vectors.py` 的 `build_documents()` 中，新增讀取 `service_disruption_policy.json` 的邏輯：

```python
# TASK 6 EXTENSION:
# service_disruption_policy.json adds new vector/RAG knowledge entries for
# service disruption scenarios. Each policy is stored as one independent
# document so pgvector can retrieve the exact rule most relevant to a user
# question, such as station closures, replacement buses, severe disruption
# refunds, or alternative transport reimbursement.
for policy in _load("service_disruption_policy.json"):
    docs.append({
        "title": policy["label"],
        "category": "service_disruption",
        "source_file": "service_disruption_policy.json",
        "content": _text(policy),
    })
```

重新執行 seeding 後，這些 documents 會透過：

```python
embedding = llm.embed(doc["content"])
store_policy_document(...)
```

寫入 `policy_documents` table。

---

## 5. Agent Changes

在 `skeleton/agent.py` 中，`search_policy` tool description 已包含服務中斷相關政策類型，例如：

```text
service disruption, replacement buses, suspended routes,
alternative transport reimbursement
```

Ollama native tool router prompt 也加入服務中斷關鍵字，例如：

```text
Policy/rules/conduct/compensation/luggage/bicycle/replacement bus/refund/
service disruption/suspended service/alternative transport/reimbursement questions → search_policy.
```

因此，服務中斷「政策問題」會被導向 `search_policy`，而明確要求關閉 / 開啟車站的問題則由 graph extension 的 `toggle_station_closure` 處理。

---

## 6. How to Run / Seed

建議先清空舊的 policy vector documents，避免重複 insert：

```sql
TRUNCATE TABLE policy_documents RESTART IDENTITY;
```

接著重新執行 vector seeding：

```bash
python skeleton/seed_vectors.py
```

完成後，`policy_documents` 中應包含原本 policy documents，以及新增的 `service_disruption` 類別 documents。

---

## 7. Vector / RAG Testing

為避免與 graph extension 的 station closure command 衝突，Vector/RAG 測試問題主要避開「close this station」這類操作型語句，改測接駁巴士、服務中斷退款與替代交通補償政策。

### Test 1 — Replacement bus policy

**User query:**

```text
Can I use a replacement bus if metro service is suspended?
```

**Actual tool call observed:**

```json
{
  "name": "search_policy",
  "params": {
    "query": "can i use replacement bus if metro service is suspended"
  }
}
```

**Top retrieved document:**

| Title                            | Category             | Similarity |
| -------------------------------- | -------------------- | ---------: |
| `Replacement Bus Service Policy` | `service_disruption` |    `0.732` |

**Interpretation:**  
The new `SD002` policy was successfully embedded into `policy_documents` and retrieved through pgvector similarity search.

---

### Test 2 — Severe service disruption refund policy

**User query:**

```text
What is the service disruption refund policy?
```

**Expected tool call:**

```json
{
  "name": "search_policy",
  "params": {
    "query": "severe service disruption refund policy"
  }
}
```

**Expected retrieved document:**

| Title                                     | Category             |
| ----------------------------------------- | -------------------- |
| `Severe Service Disruption Refund Policy` | `service_disruption` |

---

### Test 3 — Alternative transport reimbursement policy

**User query:**

```text
What is the alternative transport reimbursement policy during severe service disruption?
```

**Expected tool call:**

```json
{
  "name": "search_policy",
  "params": {
    "query": "alternative transport reimbursement policy during severe service disruption"
  }
}
```

**Expected retrieved document:**

| Title                                        | Category             |
| -------------------------------------------- | -------------------- |
| `Alternative Transport Reimbursement Policy` | `service_disruption` |

---

## 8. Testing Summary

| Extension  | Test                                | Tool / Query             | Expected Result                                        |
| ---------- | ----------------------------------- | ------------------------ | ------------------------------------------------------ |
| Graph      | Normal route                        | `find_route`             | Route from `NR01` to `NR05` before closure             |
| Graph      | Close station                       | `toggle_station_closure` | `NR03` marked as closed                                |
| Graph      | Re-route                            | `find_route`             | New route avoids `NR03`                                |
| Vector/RAG | Replacement bus                     | `search_policy`          | Retrieves `Replacement Bus Service Policy`             |
| Vector/RAG | Severe disruption refund            | `search_policy`          | Retrieves `Severe Service Disruption Refund Policy`    |
| Vector/RAG | Alternative transport reimbursement | `search_policy`          | Retrieves `Alternative Transport Reimbursement Policy` |
