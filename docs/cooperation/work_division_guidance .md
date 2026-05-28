# Work Division Guide

本文件定義本專案三人分工方式、權責邊界與共同修改規則。目標是讓三位成員可以並行優化不同資料庫，提升協作效率、降低衝突。

## 分工原則

本專案採用「一人主責一個資料庫」的分工方式：

目前分工名單如下：

- 關聯式資料庫 : 李軒逸
- 圖資料庫 : 柳炫洲
- 向量資料庫 : 黃昱鈞

| 主責範圍                | 負責內容                                                                        |
| ----------------------- | ------------------------------------------------------------------------------- |
| Relational / PostgreSQL | schema、seed、CRUD/query、使用者、訂票、付款、feedback                          |
| Graph / Neo4j           | graph schema、seed、routing query、interchange、alternative route、delay ripple |
| Vector / pgvector       | policy JSON、embedding seed、policy search、RAG 驗證                            |

每位成員可以在自己主責範圍內進行優化，但必須維持整體系統可跑通。

## 文件規則

所有完成基本要求與後續優化的過程，都應記錄在對應資料庫的 docs 資料夾中：

- `docs/MISSION1_RELATIONAL`
- `docs/MISSION2_GRAPH`
- `docs/MISSION3_VECTOR`

文件應說明：

- 完成基本要求的方式。
- schema / graph model / vector schema 的設計理由。
- seed 流程。
- query 設計。
- 已驗證案例。
- 任何進一步調整或優化。

若某個資料庫的優化需要修改共用檔案，例如 `skeleton/agent.py`、`skeleton/config.py`、`skeleton/llm_provider.py`，也要在該資料庫的文件中記錄原因與影響。

## 共用檔案規則

以下檔案屬於共用層，修改前應特別小心：

- `skeleton/agent.py`
- `skeleton/ui.py`
- `skeleton/config.py`
- `skeleton/llm_provider.py`
- `.env.example`
- `docker-compose.yml`
- `databases/relational/schema.sql`

共用層修改規則：

- 修改前要確認影響哪個 mission。
- 修改後要在對應 mission docs 中記錄。
- 不應為單一功能破壞其他 mission 已完成的基礎。
- 若修改 tool routing，應重新測對應 debug panel。

## Relational Schema 權責

Relational 負責人擁有 PostgreSQL schema 的主要命名與結構決策權，包含：

- table name。
- column name。
- primary key / foreign key。
- constraint。
- index。
- seed 對應邏輯。

其他成員若需要依賴 relational table，應以 relational 負責人確認過的 schema 為基礎。

此權責的前提是：

- 既有功能不能被破壞。
- schema guide 必須同步更新。
- 破壞性變更需清楚說明 reset / reseed 步驟。

## 優化自由度

每位成員可以自由優化自己主責資料庫，例如：

- 改善 query correctness。
- 增加 index 或 constraint。
- 補充 mock data。
- 優化 seed script。
- 改善 debug output。
- 補充測試案例或文件。

但優化必須符合：

- 不刪除已完成的核心功能。
- 不讓 UI 無法啟動。
- 不讓其他資料庫任務失效。
- 不把 API key 或 private config 寫入文件或 commit。

## Baseline Smoke Test

每次重要修改後，至少應確認以下三個點可正常運作（含具體指令與作法）：

1. 重新建立容器與資料庫（確保乾淨環境）

```powershell
docker compose down -v
docker compose up -d
```

2. 重新 seed 三個資料庫（確保資料可正確載入）

```powershell
python skeleton\seed_postgres.py
python skeleton\seed_neo4j.py
python skeleton\seed_vectors.py
```

3. 啟動 UI 並跑三條代表性路徑（確保工具 routing 正常）

```powershell
python skeleton\ui.py
```

若只做單一資料庫的小修改，可至少執行該資料庫相關 seed / query 的局部測試。

建議保留三類 UI debug 測試（在 UI 輸入以下問題）：

### Relational

```text
What national rail trains run from Central (NR01) to Stonehaven (NR05)?
```

應呼叫：

```text
check_national_rail_availability
```

### Graph

```text
What is the fastest metro route from MS01 to MS14?
```

應呼叫：

```text
find_route
```

### Vector

```text
My train was delayed 45 minutes — what compensation am I entitled to?
```

應呼叫：

```text
search_policy
```

## Git 與貢獻紀錄

建議每位成員：

- 以自己負責的資料庫為主要 commit scope。
- 修改共用層時，在 commit message 中說明原因。
- 將重要設計決策同步寫入 docs。
- 避免混合大量無關修改在同一個 commit。

文件與 git 紀錄應能共同說明每位成員的貢獻。

## 最終原則

每個人負責自己的資料庫，但整個系統必須一起通過。
可以修改共用層，但必須留下清楚紀錄。
