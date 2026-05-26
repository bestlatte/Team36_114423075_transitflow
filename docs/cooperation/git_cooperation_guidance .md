# Git協作規範

### 專案分支管理與工作流規範

為了確保代碼品質與本地驗證的嚴謹性，採用以下模式：

#### 1. `main` 分支：正式穩定版本 (Stable Release)

- **定位**：存放已完成所有功能測試、最穩定的程式碼。
- **操作限制**：**嚴禁直接 Commit。** 禁止強制推送，只能透過 Pull Request，由 repo 所有者審核並 merge。

#### 2. `feature/` 分支：任務導向開發 (Task-Oriented)

- **定義**：一個分支代表一個獨立的「任務」或「功能」。
- **使用流程**：從 `main` 切出 -> 在 `feature/XXX` 分支完成開發 -> 在本地 Docker 環境驗證 -> 推送到 GitHub 並發起針對 `main` 的 PR。

---

### 💡 備忘錄

- **開工前 (同步遠端進度)**：

1. `git checkout main`。
2. `git pull origin main`：確保基於最新的代碼進行開發。
3. `git checkout -b feature/[你的任務名稱]`：從最新的 `main` 開出功能分支。

- **收工前**：將進度 `commit` 並 `push` 到自己的 `feature/` 分支。
- **發 PR 時**：請詳細說明改動範圍。

---

### 📝 Commit 提交規範

請遵守 **「前綴 + 簡短描述」** 的格式。

- `feat:` 新增功能
- `fix:` 修復 Bug
- `style:` 介面樣式調整
- `refactor:` 程式碼重構
- `chore:` 依賴更新或設定調整
- `doc:` 新增修改文件

---

### 💡 小提醒

#### 1. 頻繁 Commit

- **觀念：** 「早點提交，經常提交 (Commit early, commit often)」。
- **進度存檔：** 就像打遊戲存檔，寫壞了可以輕易回到 10 分鐘前的狀態。
- **原子提交 (Atomic Commits)：** 每次 Commit 只做一件事，不要累積一天才 Commit 一次。

#### 2. 當你剛按下 Commit 才發現有錯字 (Amend)

- **專業作法：** 使用 `--amend`，讓你的紀錄看起來一次到位。

```bash
git add .
git commit --amend -m "fix: 修正提交訊息的錯字"

```

#### 3. 當你與同伴改到同一個檔案時 (Rebase)

- **規範：==嚴禁在 feature 分支執行 `git merge main`==。這會產生雜亂的 Merge Commits，破壞提交歷史的線性。**
- **專業作法：** 使用 `rebase` 把你的改動「接」在同事的最新進度之後。

```bash
git fetch origin
git rebase origin/main

```

_這會讓歷史紀錄看起來像是一條直線，而不是糾結在一起的毛線球。_
==不知道rebase怎麼用的話YT有很多影片 !==

---

### 🚩 檢查清單

1. **Docker 環境驗證**：發起 PR 前，確保啟動 Docker 服務且確定系統運行無誤。

2. **環境變數規範**：

- \*\*嚴禁上傳自己的 `.env`：避免 api key等敏感資洩漏。
