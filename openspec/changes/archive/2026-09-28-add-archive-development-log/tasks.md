# Tasks

## 實作前閱讀

### 1. 建立文件與更新器前

- 閱讀 `proposal.md` 的「已確認決策」。
- 閱讀 `archive-development-history` spec 的「建立並保留起始歷史紀錄」與「成功封存必須新增可追溯條目」。
- 閱讀 `design.md` 的「受管理的文件區塊」與「唯一識別與冪等更新」。

### 2. 整合 archive workflow 前

- 閱讀 `archive-development-history` spec 的「寫入失敗不得撤銷已完成封存」。
- 閱讀 `design.md` 的「由 Codex archive skill 觸發」與「失敗與修復紀錄」。
- 閱讀現有 `.agents/skills/openspec-archive-change/SKILL.md`，保留既有 archive checks、sync 與使用者確認流程。

## 1. 建立開發歷程基準文件

- [x] 1.1 建立 `docs/DEVELOPMENT_HISTORY.md`，在受管理的「Codex／OpenSpec 封存紀錄」區塊下方保留使用者提供、截至 2026/09/28 早上的完整起始時間線與 AI 對話統計；驗證起始歷史內容未被改寫且區塊順序符合 spec。
- [x] 1.2 建立人工補充區與受管理區塊標記，並驗證 Markdown Preview 可正確呈現且手動內容位於更新器可寫入範圍之外。

## 2. 實作封存條目更新器

- [x] 2.1 在專案內新增 development-history updater，從 archived change 的 planning artifacts 與 archive workflow 已知驗證結果產生條目；驗證條目包含日期、change 名稱、archive 路徑、摘要、capability 與驗證狀態。
- [x] 2.2 實作以 archived change 相對路徑為 key 的倒序插入與去重；新增 focused tests，驗證新條目位於管理區塊最上方且重跑不產生第二筆。
- [x] 2.3 實作管理區塊完整性檢查與原子檔案寫入；新增 focused tests，驗證人工補充、起始歷史與不成對標記不會被覆寫。
- [x] 2.4 實作補寫與 pending marker 行為；新增 focused tests，驗證寫入失敗不破壞既有開發歷程，並可由 archived change 路徑成功重跑補寫。

## 3. 整合 Codex archive workflow

- [x] 3.1 依 skill-creator 規範更新 `.agents/skills/openspec-archive-change/SKILL.md`：在 archive move 成功後呼叫 updater，且不改變既有 completion、task、spec sync 或使用者確認流程；驗證 skill 指令明確區分 archive 成功、歷程已更新與「開發歷程待補寫」。
- [x] 3.2 更新 `openspec/config.yaml` 的 archive guidance 與 `docs/WORKFLOW.md`，說明此自動更新由 Codex archive workflow 保證、原生 `openspec archive` CLI 不含此 hook；驗證不宣稱外部平台或 Git 操作會自動執行。
- [x] 3.3 以測試用 archived change 執行 archive 後更新流程或等價的整合測試；驗證成功路徑只產生一筆可追溯條目，失敗路徑仍回報 archive 成功與待補寫線索。

## 4. 驗證與交付

- [x] 4.1 執行 development-history focused tests，驗證起始內容、排序、去重、人工內容保護與補寫行為皆通過。
- [x] 4.2 執行 `openspec validate --all --strict` 與 `git diff --check`，驗證 OpenSpec artifacts、設定與 Markdown 格式無錯誤。
- [x] 4.3 以 OpenSpec implementation verification 對照 `archive-development-history` spec，確認每個 Requirement 都有實作與測試證據。
