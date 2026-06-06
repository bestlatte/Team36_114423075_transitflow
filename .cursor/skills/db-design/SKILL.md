---
name: db-design
description: >-
  Guide database schema design including entity identification, normalization,
  indexing optimization, and scaling strategies. Use when designing database
  schemas, creating tables, defining relationships, optimizing queries,
  planning indexes, or discussing data modeling and database architecture.
---

# 資料庫設計方法論 (Database Design Methodology)

## 1. 需求解析與實體識別 (Entity Identification)

**操作：** 從業務邏輯中抽離出「名詞」（如：使用者、商品、訂單），將其定義為實體 (Entity)；抽離出「動態行為」（如：購買、追蹤），將其定義為關係 (Relationship)。

**產出：** 概念模型清單（實體與其屬性）。

## 2. 關係建模與正規化 (Normalization)

**操作：** 釐清實體之間的關係（1:1, 1:N, M:N），並進行資料正規化。

- **1NF：** 確保欄位原子性（不可再分）。
- **2NF：** 確保非主鍵欄位完全相依於主鍵。
- **3NF：** 消除遞移相依（非主鍵欄位不能相依於其他非主鍵欄位）。
- **反正規化時機：** 針對高併發、讀多寫少的場景，主動設計冗餘欄位以減少 JOIN 操作，提升查詢效能。

## 3. 索引優化策略 (Indexing Strategy)

**操作：** 依據查詢情境（Query Patterns）精準建立索引。

- 在常作為 WHERE、JOIN、ORDER BY 的欄位上建立索引。
- 高基數（High Cardinality，如 UUID、Email）欄位適合建立索引；低基數（如性別、狀態）則否。
- 善用複合索引，並遵循最左匹配原則 (Leftmost Prefix Rule)。

## 4. 效能與擴充性設計 (Scaling Strategy)

**操作：** 針對大數據量場景，設計資料分流機制。

- **垂直拆分：** 將一張大表依欄位活躍度拆分成主表與擴充表。
- **水平拆分 (Sharding/Partitioning)：** 依時間、ID 範圍或 Hash 值將資料分散到不同分區或資料庫。
