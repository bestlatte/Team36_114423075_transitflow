# Design Document — Section 3 圖形資料庫設計原理

## 1. 結構定義與設計動機

在本專案中，我們將交通網路模型化為圖形結構。

- **Nodes (節點):** 將「車站」定義為節點（標籤為 `MetroStation` 或 `NationalRailStation`），以 `station_id` 作為 Unique Identity。
- **Relationships (關係):** 站與站之間的行駛路線定義為關係（`METRO_LINK`, `RAIL_LINK`），跨系統轉乘則使用 `INTERCHANGE_TO`。
- **Properties (屬性):** 將 `travel_time_min` (行駛時間) 與 `standard_fare` (票價) 等數值作為關係的屬性（Edge Weights）。

**動機：** 交通路網本質上就是由點（車站）與線（軌道）構成的拓樸結構。將其儲存於圖形資料庫，能最直觀地反映真實世界的地理與營運樣貌，避免關聯式資料庫中複雜且不直觀的多對多關聯表設計。

## 2. 演算法正面對決：Neo4j vs PostgreSQL

面對複雜的路徑規劃任務（如：尋找最短路徑或延誤連鎖效應），Neo4j 具備絕對的演算法優勢：

- **Neo4j 的優勢：** 透過內建的 APOC 函式庫，我們能直接呼叫高效的 **Dijkstra 演算法** (`apoc.algo.dijkstra`)。圖形資料庫在底層使用「Index-Free Adjacency (無索引相鄰)」，在遍歷節點尋找路徑時，查詢時間僅與圖形的局部複雜度有關，與整體資料量無關，效能極高。
- **PostgreSQL 的劣勢：** 若堅持使用 SQL，必須依賴 **Recursive CTEs (遞迴公用表運算式)**。在計算路徑時，SQL 需要不斷執行昂貴的 JOIN 操作，並持續累積與過濾龐大的 Path Sets 以避免無限迴圈。在節點超過百個的真實路網中，效能將呈現指數級衰退。

## 3. 核心查詢情境展示

- **情境 A：跨網路轉乘路徑 (`query_interchange_path`)**
透過簡單的 Cypher 語法 `MATCH p=shortestPath((start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*]->(end))`，系統能自動跨越不同標籤的邊，輕鬆找出一條包含捷運與台鐵的混合路徑。這在 SQL 中需要極其複雜的 UNION 與多層 JOIN 才能勉強實現。
- **情境 B：避開特定車站 (`query_alternative_routes`)**
圖形結構讓我們能輕易地在遍歷過程中加入條件過濾。透過 `WHERE NONE(n IN nodes(p) WHERE n.id = $avoid_station_id)`，演算法在搜索路徑時，只要遇到該故障站點就會自動剪枝（Pruning），高效找出完美的替代路線。
