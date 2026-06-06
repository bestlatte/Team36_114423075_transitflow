# Optional Extension

本組在 Task 6 中完成兩個 optional extensions。第一個是 **Graph Extension：即時車站封閉繞道系統**，讓系統可以將特定車站標記為關閉，並讓 Neo4j 路徑查詢避開已關閉車站。第二個是 **Vector / RAG Extension：Service Disruption Policy RAG Extension**，新增服務中斷相關政策文件，讓 `search_policy` 可以透過 pgvector similarity search 回答接駁巴士、嚴重服務中斷退款與替代交通補償等問題。

這兩個 extension 都有實際修改 database-related code 或 seed data，不是單純的 UI 或外觀修改。

---

## 1 Motivation

原本的 TransitFlow assistant 已經可以處理基本的路線查詢、票價查詢、訂票、取消訂票，以及一般政策查詢。然而，真實交通系統中常會發生突發狀況，例如車站因事故或維修暫時關閉、服務中斷、需要接駁巴士，或乘客需要申請替代交通費用補償。這些情境會同時影響「路線規劃」與「乘客權益政策」。

Graph extension 的目標是讓系統能處理即時營運狀態。當某個車站被標記為 closed 後，route query 不應該仍然規劃經過該車站的路線。因此，我們在 Neo4j 的 `Station` 節點加入 `is_closed` 屬性，並修改路徑查詢，使系統能避開已關閉車站。這讓 TransitFlow 更接近真實交通系統中的即時路線調整需求。

Vector / RAG extension 的目標則是補足服務中斷相關政策。原本的 RAG policy documents 已能回答退票、延誤補償、行李、寵物、腳踏車等一般政策問題，但對於 replacement bus、severe service disruption refund、alternative transport reimbursement 等情境支援不足。因此，我們新增 `service_disruption_policy.json`，並將其中的政策內容 seed 成 pgvector 中的 policy documents，使使用者詢問服務中斷相關政策時，系統可以透過 semantic search 找到正確政策文件。

---

## 2 Database and Graph Changes

### 2.1 Graph Extension — 車站封閉狀態

Graph extension 修改 Neo4j graph database，使每個 `Station` node 都可以記錄目前是否關閉。所有 `Station` node 在 seed 階段加入：

```text
Station.is_closed = false
```

當使用者要求關閉或重新開啟車站時，agent 會呼叫：

```text
toggle_station_closure(station_id, close_station)
```

底層會執行 Neo4j Cypher，將指定車站的 `is_closed` 狀態改為 `true` 或 `false`：

```cypher
MATCH (n:Station {id: $station_id})
SET n.is_closed = $status
RETURN n.name AS name, n.is_closed AS is_closed
```

當 `close_station = true` 時，代表車站被標記為 closed；當 `close_station = false` 時，代表車站重新開啟。

此外，route query 也被修改，使路徑規劃避開已關閉車站。例如 shortest route 查詢會過濾掉包含 closed station 的 path：

```cypher
WHERE ALL(n IN nodes(p) WHERE n.is_closed = false OR n.is_closed IS NULL)
```

或使用等價的 closed-station exclusion logic：

```cypher
WHERE NONE(n IN nodes(p)[1..-1] WHERE n.is_closed = true)
```

因此，如果 `NR03` 被標記為 closed，系統重新查詢 `NR01` 到 `NR05` 的路線時，就不應該再回傳經過 `NR03` 的 path。

若使用 PostgreSQL audit table 記錄封閉事件，schema 如下：

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

這個 table 用來保存車站封閉與重啟歷史；Neo4j 的 `Station.is_closed` 則負責即時路線查詢時的 operational status。

### 2.2 Vector / RAG Extension — 服務中斷政策文件

Vector / RAG extension 沒有新增新的 vector table，而是使用既有的 pgvector table：

```sql
policy_documents(title, category, content, embedding, source_file)
```

我們新增 `train-mock-data/service_disruption_policy.json` 作為新的 seed data，並在 `skeleton/seed_vectors.py` 的 `build_documents()` 中讀取該檔案。每一筆 service disruption policy 都會被轉成一個獨立的 RAG document，後續透過 `llm.embed()` 產生 embedding，再由 `store_policy_document()` 寫入 `policy_documents`。

新增的 vector entries 包含：

| Policy ID | Title                                        | Category             |
| --------- | -------------------------------------------- | -------------------- |
| `SD001`   | `Station Closure Policy`                     | `service_disruption` |
| `SD002`   | `Replacement Bus Service Policy`             | `service_disruption` |
| `SD003`   | `Severe Service Disruption Refund Policy`    | `service_disruption` |
| `SD004`   | `Alternative Transport Reimbursement Policy` | `service_disruption` |

在 `seed_vectors.py` 中，新增的 seeding logic 如下：

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

重新執行 vector seeding 時，這些 documents 會透過以下流程寫入 pgvector：

```python
embedding = llm.embed(doc["content"])

doc_id = store_policy_document(
    title=doc["title"],
    category=doc["category"],
    content=doc["content"],
    embedding=embedding,
    source_file=doc.get("source_file", ""),
)
```

這讓 `search_policy` 可以使用 query embedding 和 pgvector similarity search 找出服務中斷相關政策。

---

## 3 Example Queries and Expected Output

### 3.1 Graph Query Example — 關閉車站並重新繞道

第一組測試用來確認 station closure extension 是否能改變 graph 狀態，並影響後續路線查詢。

**Step 1 — 車站關閉前的正常路線**

User query:

```text
How do I get from Central (NR01) to Stonehaven (NR05)?
```

Expected result:

```text
系統回傳 NR01 到 NR05 的正常最短路徑。
在車站未關閉前，這條路線可能會經過 Old Town / Old Town Junction (NR03)。
```

**Step 2 — 關閉 Old Town station**

User query:

```text
Old Town station (NR03) has an emergency. Please close this station.
```

Expected tool call:

```json
{
  "name": "toggle_station_closure",
  "params": {
    "station_id": "NR03",
    "close_station": true
  }
}
```

Expected output:

```text
Station Old Town / Old Town Junction (NR03) is now CLOSED.
```

等價的 Neo4j 操作如下：

```cypher
MATCH (n:Station {id: 'NR03'})
SET n.is_closed = true
RETURN n.name, n.is_closed
```

Expected Cypher output:

| name                         | is_closed |
| ---------------------------- | --------- |
| Old Town / Old Town Junction | true      |

**Step 3 — 車站關閉後再次查詢路線**

User query:

```text
Now, how do I get from Central (NR01) to Stonehaven (NR05) again?
```

Expected result:

```text
系統回傳一條新的 NR01 到 NR05 路線，且該路線不會經過 NR03。
```

這可以驗證更新後的 route query 確實使用 `Station.is_closed` 狀態，並排除已關閉車站。

### 3.2 Vector / RAG Query Example — 接駁巴士政策

這個 query 用來測試新增的 service disruption policy documents 是否有被正確嵌入，並能從 pgvector 中被查回。

User query:

```text
Can I use a replacement bus if metro service is suspended?
```

實際觀察到的 tool call：

```json
{
  "name": "search_policy",
  "params": {
    "query": "can i use replacement bus if metro service is suspended"
  }
}
```

Expected retrieved document:

| Title                            | Category             | Similarity |
| -------------------------------- | -------------------- | ---------: |
| `Replacement Bus Service Policy` | `service_disruption` |    `0.732` |

這表示系統成功將使用者的政策問題導向 `search_policy`，並透過 query embedding 到 `policy_documents` 中找回新增的 `SD002` 政策。

### 3.3 Vector / RAG Query Example — 嚴重服務中斷退款政策

User query:

```text
What is the service disruption refund policy?
```

Expected tool call:

```json
{
  "name": "search_policy",
  "params": {
    "query": "severe service disruption refund policy"
  }
}
```

Expected retrieved document:

| Title                                     | Category             |
| ----------------------------------------- | -------------------- |
| `Severe Service Disruption Refund Policy` | `service_disruption` |

這個測試確認服務中斷相關的退款問題可以找回新增的 `SD003` policy document。

### 3.4 Vector / RAG Query Example — 替代交通補償政策

User query:

```text
What is the alternative transport reimbursement policy during severe service disruption?
```

Expected tool call:

```json
{
  "name": "search_policy",
  "params": {
    "query": "alternative transport reimbursement policy during severe service disruption"
  }
}
```

Expected retrieved document:

| Title                                        | Category             |
| -------------------------------------------- | -------------------- |
| `Alternative Transport Reimbursement Policy` | `service_disruption` |

這個測試確認替代交通費用補償相關問題可以找回新增的 `SD004` policy document。

---

## 4. Summary

Task6 的 extension 從兩個面向強化 TransitFlow。Graph extension 讓系統能反映即時營運狀態，支援將車站標記為 closed，並讓後續路線查詢避開已關閉車站。Vector / RAG extension 則擴充政策知識庫，將服務中斷相關政策嵌入 pgvector，使系統能回答接駁巴士、嚴重服務中斷退款與替代交通補償等自然語言政策問題。

整體而言，Graph extension 負責處理「交通網路狀態改變後如何重新規劃路線」，Vector / RAG extension 負責處理「服務中斷時乘客可以享有哪些政策權益」。兩者結合後，使 TransitFlow 在面對突發營運狀況時更完整、更接近真實交通服務系統。
