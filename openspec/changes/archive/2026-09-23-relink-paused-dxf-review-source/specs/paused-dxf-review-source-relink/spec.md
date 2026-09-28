# Spec Delta

## Purpose

讓使用者在 paused DXF Review 的原始來源被移動、改名或位於另一台電腦時，可以重新連結內容完全相同的 DXF，並在候選內容不同、失敗或取消時完整保留原 Review 與 Project 狀態。

## ADDED Requirements

### Requirement: Paused Review 提供專用來源重新連結

當 Project workflow 為 `REVIEW`、存在可恢復的 Review state，且目前來源缺失、不可讀或 fingerprint 不符時，系統 SHALL 提供 Review 專用 Relink。此流程 MUST 保持為 Review 恢復作業，不得改用完成匯入後的 Project Relink 語意。

#### Scenario: 缺少來源時可選擇候選 DXF
- **WHEN** 使用者嘗試繼續一個具有已保存 Review state、但目前來源不存在的 paused Review
- **THEN** 系統提供選擇候選 DXF、重試或取消的途徑，且不要求先建立或修改正式 Project geometry

#### Scenario: 非 REVIEW workflow 不進入專用流程
- **WHEN** 目前 workflow 不是 `REVIEW`
- **THEN** 系統不使用 paused Review Relink 行為，既有完成匯入後 Relink 行為維持不變

### Requirement: 候選來源必須是內容完全相同的有效 DXF

系統 SHALL 驗證候選檔案可讀、可解析為 DXF，且其 SHA-256 與 paused Review state 保存的 `source_fingerprint` 完全相同。驗證結果 MUST 明確區分 `EXACT_MATCH`、`SOURCE_CONTENT_MISMATCH` 與 `VALIDATION_FAILED`；檔案選擇器取消屬於未開始驗證，不得被回報成驗證失敗。

#### Scenario: 候選內容完全相同
- **WHEN** 候選 DXF 可正常解析，且 SHA-256 與保存的 Review fingerprint 相同
- **THEN** 系統回報 `EXACT_MATCH` 並建立可原子採用的新來源參照

#### Scenario: 候選內容不同
- **WHEN** 候選 DXF 可正常解析，但 SHA-256 與保存的 Review fingerprint 不同
- **THEN** 系統回報 `SOURCE_CONTENT_MISMATCH`，說明第一版不支援內容變更後的恢復，且不建立可提交的 recovery state

#### Scenario: 候選檔案驗證失敗
- **WHEN** 候選路徑不存在、不是有效檔案、DXF 無法解析或 fingerprint 計算失敗
- **THEN** 系統回報 `VALIDATION_FAILED` 與可顯示的原因，並允許使用者重試或取消

#### Scenario: Saved Review 缺少 fingerprint
- **WHEN** paused Review state 沒有可用的 `source_fingerprint`
- **THEN** 系統回報 `VALIDATION_FAILED`，不得以檔名、路徑、檔案大小、修改時間或其他 hash 猜測候選相同

### Requirement: 選擇檔案即授權採用 Exact Match

使用者在 Review Relink 檔案選擇器中選擇候選檔案 SHALL 視為授權系統在 `EXACT_MATCH` 驗證成功後採用該來源。系統 MUST NOT 為 Exact Match 再顯示第二個採用確認；若使用者在選檔前取消，系統 MUST 視為沒有開始 Relink。

#### Scenario: Exact Match 驗證成功後直接採用
- **WHEN** 使用者已選擇候選檔案，且驗證結果為 `EXACT_MATCH`
- **THEN** 系統直接進入原子提交，不要求額外的 Yes／No recovery confirmation

#### Scenario: 使用者取消檔案選擇
- **WHEN** 使用者在候選檔案選擇器中取消
- **THEN** 系統不呼叫來源驗證或提交流程，並完整保留目前 paused Review

### Requirement: Exact Match 完整保留既有 Review state

成功採用 `EXACT_MATCH` 時，系統 MUST 僅更新已驗證的來源參照，並完整保留現有 paused Review state 的工程資料、圖層分類、座標系、匯入模式、排除來源、人工端點、材料規格、Waler 接觸輸入、雙路支撐決策、確認與既有 pending issues。Relink 不得新增任何 requires-review 項目。

#### Scenario: 相同內容位於不同路徑
- **WHEN** 候選 DXF 路徑不同，但內容 fingerprint 完全相同
- **THEN** 提交後以新路徑作為來源，其他持久化 Review state 維持原值並可繼續 Review

#### Scenario: Exact Match 不重新辨識
- **WHEN** 系統採用 Exact Match 候選
- **THEN** 系統不重新執行 DXF recognition、不重新計算 association、不使確認或人工決策失效，也不產生 recovery summary

#### Scenario: Exact Match 不匯入正式 Project
- **WHEN** 系統採用 Exact Match 候選
- **THEN** 系統不執行 Review completion、不套用 Project geometry，且不改變任何既有 Solver result、Solver memory 或候選 cache

### Requirement: Exact Match 採用必須是原子操作

系統 MUST 在提交前再次確認候選仍為同一內容，並將來源參照與 paused Review state 視為單一提交單位。候選內容或目前 paused Review state 在驗證後發生變化時，系統 MUST 拒絕 stale commit；提交發生錯誤時 MUST 回復提交前狀態。

#### Scenario: 候選在驗證後被修改
- **WHEN** 候選通過 Exact Match 驗證後、提交前，其 fingerprint 發生改變
- **THEN** 系統回報 `VALIDATION_FAILED`，不採用候選路徑或任何候選資料

#### Scenario: Paused Review 在驗證後被修改
- **WHEN** Exact Match plan 建立後、提交前，目前 paused Review state 已不同於 plan 的基準
- **THEN** 系統拒絕 stale commit，並保留最新的 paused Review state

#### Scenario: 提交中發生錯誤
- **WHEN** 採用新來源參照或更新 UI runtime state 的過程發生錯誤
- **THEN** 系統回復提交前的完整狀態，不留下新路徑配舊 Review state或舊路徑配新 Review state的混合狀態

### Requirement: 不成功的 Relink 保持零副作用

`SOURCE_CONTENT_MISMATCH`、`VALIDATION_FAILED` 與檔案選擇取消 MUST 保留原 paused Review state、原來源參照、workflow 與正式 Project 資料。這些結果不得使 Project 成為 dirty、不得清除同工作階段 Review cache，亦不得改動 Solver result、Solver memory 或候選 cache。

#### Scenario: 內容不同後重試
- **WHEN** 第一個候選回報 `SOURCE_CONTENT_MISMATCH`，使用者選擇另一個候選重試
- **THEN** 第二次驗證仍以原 paused Review state 與原 fingerprint 為基準，不使用第一個候選留下的任何資料

#### Scenario: 驗證失敗後取消
- **WHEN** 候選驗證失敗後使用者取消
- **THEN** 下次繼續 Review 時仍可從提交前的 paused Review state 再次嘗試重新連結

### Requirement: 成功 Relink 後維持 paused Review lifecycle

成功提交 `EXACT_MATCH` 後，系統 SHALL 保持 workflow 為 `REVIEW`、將 Project 標記為需要保存新的來源關係，並透過既有 resume path 繼續 DXF Review。系統 MUST NOT 自動完成 Import，也 MUST NOT 將 workflow 轉為 `COMPLETED`。

#### Scenario: 成功後繼續 Review
- **WHEN** Exact Match 來源成功提交
- **THEN** 系統以原有 Review state 恢復 Review，原本待確認或有問題的項目維持原狀

#### Scenario: 保存後可再次載入
- **WHEN** 成功 Relink 的 paused Review 隨 Project 被保存並重新載入
- **THEN** 系統仍讀取為 `REVIEW`，並可由已保存的新來源關係繼續工作

### Requirement: 現有持久化格式保持相容

系統 SHALL 沿用現有 paused Review persistence 欄位與 Project schema。成功 Relink 不得為了本功能建立新的 Review state 格式；未持久化的 UI 頁籤或步驟位置不在恢復保證內。

#### Scenario: Exact Match 不升級 schema
- **WHEN** 一個現行合法的 paused Review 成功重新連結並保存
- **THEN** 系統使用既有 Project schema 與 Review state version 表示新的來源關係

#### Scenario: UI Step 未持久化
- **WHEN** paused Review state 沒有保存目前頁籤或步驟位置
- **THEN** Relink 只恢復既有持久化的工程與 Review 狀態，不保證返回原 UI Step
