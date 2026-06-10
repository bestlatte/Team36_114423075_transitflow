# Reflection and Trade-offs

本節簡要回顧本系統中幾個主要設計決策，以及如果系統進入 production 環境時需要調整的部分。整體而言，本系統的設計目標是在資料結構清楚、功能容易實作、以及安全性之間取得平衡。

## 1. Design Decision 1: 將 schedule stops 拆成獨立資料表

第一個重要設計決策，是將班次的停靠站資料拆成 `metro_schedule_stops` 與 `national_rail_schedule_stops`，而不是直接把所有停靠站存在 `metro_schedules` 或 `national_rail_schedules` 的單一欄位中。

這樣設計的原因是，一個 schedule 會經過多個 stations，而每個 stop 又有自己的 `stop_order` 和 `travel_time_from_origin_min`。這些資料不是 schedule 本身的單一屬性，而是 schedule 和 station 之間的有序關係。將它們拆成獨立資料表後，每個 stop 都可以作為獨立 row 被查詢、更新與約束，也可以透過 foreign key 連接 schedule 和 station。

這個設計的好處是資料結構更清楚，也更容易查詢某一班次的完整停靠順序、計算兩站之間的站數與 travel time。它的 trade-off 是查詢時需要額外 join schedule table、station table 和 schedule stops table，但這個成本是可以接受的，因為換來的是更好的資料一致性與可維護性。

## 2. Design Decision 2: 使用 bcrypt 儲存使用者密碼

第二個重要設計決策，是使用 bcrypt 來儲存使用者密碼，而不是使用 MD5、SHA-1 或 Argon2。

這樣設計的原因是，密碼儲存需要抵抗 brute-force attack 和 rainbow-table attack。MD5 和 SHA-1 的計算速度很快，這在檔案完整性檢查等用途上是優點，但在密碼儲存上反而會讓攻擊者可以高速嘗試大量密碼。bcrypt 則是專門為 password hashing 設計的演算法，支援 cost factor 和 key stretching，可以增加每一次密碼猜測的計算成本。

我們也考慮過 Argon2。Argon2 是更現代的 password hashing algorithm，並且具有 memory-hard 的特性，可以提高 GPU 或專用硬體暴力破解的成本。不過，本系統是一個課程 prototype，主要目標是清楚展示安全的 password hashing 流程，而 bcrypt 在 Python 中有成熟、穩定且容易使用的 library 支援，並且已經能滿足本系統對 salt、cost factor 與 password verification 的需求。因此，我們選擇 bcrypt 作為較簡單、穩定、容易實作與說明的方案。若系統未來進入更高安全需求的 production 環境，Argon2id 會是值得重新評估的選項。

## 3. Production Difference: 使用 connection pooling 管理資料庫連線

目前的 prototype 中，每次資料庫操作都會透過 `_connect()` 或 `_tx_connect()` 建立新的 PostgreSQL connection，並在操作結束後關閉。這種 per-operation connection 的做法簡單、清楚，適合課程專案、低流量測試與展示 SQL query 的執行流程。

不過，如果系統進入 production 環境，這種連線方式應該改成 **connection pooling**。在真實使用情境中，可能會有多個使用者同時查詢路線、票價、座位、訂票紀錄或政策文件。如果每一次操作都重新建立與關閉 PostgreSQL connection，會增加額外成本，也可能在高併發下耗盡資料庫可用連線數。

因此，在 production system 中，可以使用 `psycopg2.pool`、PgBouncer，或部署平台提供的 database connection pool。這樣應用程式就可以重複使用既有連線，而不是每次 request 都重新建立連線。這會讓系統在多使用者同時使用時，有更好的效能與穩定性。
