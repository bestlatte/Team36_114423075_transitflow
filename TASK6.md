# TASK 6 EXTENSION: 即時車站封閉繞道系統 (Real-time Station Closure System)

## 1. Motivation (動機)
真實世界的交通系統常因突發狀況（如停電、事故）導致特定車站關閉。本擴充功能結合 PostgreSQL 紀錄封閉事件與 Neo4j 的即時圖形路徑運算，讓系統能即時封閉車站，並使所有導航與路徑規劃自動避開災區，提升系統的真實性與韌性。

## 2. Database Changes
**PostgreSQL (schema.sql):**
新增 `station_closures` 表格，用於稽核與紀錄車站的封閉/重啟時間與原因。
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

**Neo4j (seed_neo4j.py):**
在所有 `Station` 節點新增 `is_closed` 布林值屬性，預設為 `false`。

**Graph Queries (queries.py):**
新增 `execute_toggle_station_closure` 函數改變節點狀態，並修改路徑查詢的 Cypher 語法：

Cypher

```
WHERE NONE(n IN nodes(p)[1..-1] WHERE n.is_closed = true)
```

## 3. Example Queries
**關閉車站 (Cypher):**

Cypher

```
MATCH (n:Station {id: 'NR03'}) SET n.is_closed = true RETURN n.name, n.is_closed
```

**預期結果:** 回傳 Old Town 車站，且 is_closed 為 true。此時再去查詢 NR01 到 NR05，系統將自動規劃繞過 NR03 的全新路徑。
