# Spec Delta

## 閱讀導航

- **必讀**：「Global Waler 必須保留材料多樣性的候選」「全域流程仍須逐支生成與選擇」「Single Waler 候選輸出維持不變」。
- **條件式閱讀**：實作 diagnostics 或效能驗證時讀「候選池範圍必須可診斷」；處理無合法候選或取消時讀「部分候選池不得進入全域選擇」。
- **可先跳過**：本 capability 不修改工程合法性、local score、GA stages／population／seed、Exact DP objective、shared inventory、result adoption 或 persistence。

## Purpose

定義 Global Waler 專用候選池如何保留搜尋已發現的材料組成多樣性，使全域選擇不再受 Single Top 5 提前截斷，同時維持逐支搜尋與既有 Exact DP 語意。

## ADDED Requirements

### Requirement: Global Waler 必須保留材料多樣性的候選

Global Waler MUST 使用與 Single Waler 分離的候選保留範圍。對每個實際執行的搜尋 stage，系統 SHALL 收集該 stage 最終 population 中所有合法且完整 Waler solution signature 不重複的候選，並 MUST NOT 在 stage 輸出或跨 stage 合併時套用 Single Waler 的 Top 5。

若搜尋執行多個 stages，系統 SHALL 合併所有已執行 stages 的候選，再依完整 Waler solution signature 去重，並以既有 deterministic local score 與 tie-break 排定 local rank。未實際執行的 stage MUST NOT 貢獻候選；Global local rank MAY 大於 5。

進入 Exact DP 前，系統 SHALL 依 Global material signature 合併候選。Material signature MUST 至少涵蓋 Short／Mid／Long／Out counts 與 Out distance；相同 signature 只保留 local regret 最低的 deterministic 代表，不同 signature MUST 全部保留，不得再套用固定 Top 5、Top 20、Top 50 或其他只依 local score 的截斷。

#### Scenario: Global 取得超過五個不同材料組成

- **WHEN** 一支 Waler 的已執行 stages 發現 8 個合法且不同的 material signatures
- **THEN** 該 Waler 的 Global candidate group SHALL 包含 8 個代表候選
- **AND** 系統 MUST NOT 因其中候選的 local rank 大於 5 而移除它

#### Scenario: Local rank 6 改善全場材料比例

- **WHEN** local rank 1 至 5 未包含目標所需的 material signature
- **AND** rank 6 具有不同 signature，且既有 Global objective 判定包含 rank 6 的全場組合較佳
- **THEN** rank 6 SHALL 進入 Global candidate group
- **AND** Exact DP SHALL 能選取 rank 6

#### Scenario: Rank 6 以上候選完成成果生命週期

- **WHEN** Exact DP 選中一個 local rank 大於等於 6 的 Global Waler candidate
- **THEN** 系統 SHALL 以原 rank 與 selected plan 正式採用該候選
- **AND** Project persistence SHALL 保存並重新載入相同 rank、result identity 與 selected plan
- **AND** Global Dialog 與成果樹 SHALL 正確顯示該 rank，不得拒絕、截為 5、改寫或誤標為 Single candidate
- **AND** 人工顯示切換、材料摘要與匯出 SHALL 依重新載入後的 selected plan 正常運作

#### Scenario: 搜尋升級後合併多個 stages

- **WHEN** 搜尋從 STANDARD 升級至 ENHANCED，且兩個已執行 stages 發現不同完整 solution signatures 或 material signatures
- **THEN** Global pool SHALL 合併 STANDARD 與 ENHANCED 的候選
- **AND** ENHANCED MUST NOT 覆蓋或移除 STANDARD 已發現的不同 signature
- **AND** 未執行的 DEEP stage MUST NOT 被計入候選池

#### Scenario: 相同材料 signature 有多個候選

- **WHEN** 跨 stage 合併後有多個候選具相同 Short／Mid／Long／Out counts 與 Out distance
- **THEN** Global candidate group SHALL 只保留 local regret 最低的 deterministic 代表
- **AND** 此 dominance merge MUST NOT 移除任何不同 material signature

### Requirement: Single Waler 候選輸出維持不變

Single Waler SHALL 維持搜尋後最多輸出 local Top 5 的既有行為。Global 專用候選保留範圍 MUST NOT 改變 Single Waler 的 result count、deterministic ordering、顯示、正式採用或 `solver_memory` contract。

#### Scenario: 相同搜尋結果分別供 Single 與 Global 使用

- **WHEN** 相同搜尋輸入產生超過 5 個合法 unique candidates
- **THEN** Single Waler SHALL 仍只對外輸出 local Top 5
- **AND** Global Waler SHALL 依本 capability 保留所有不同 material signatures 的最佳代表

#### Scenario: Single Waler cache 與結果採用

- **WHEN** 使用者執行 Single Waler Solver
- **THEN** Global candidate-pool policy MUST NOT 改變既有 cache key、memory prompt、result IDs 或 adoption behavior

### Requirement: 全域流程仍須逐支生成與選擇

Global Waler SHALL 對每支 eligible non-RC Waler 分別執行既有 local search，並為每支建立自己的 Global candidate group。系統 MUST NOT 為本 capability 建立跨 Waler 等價鍵、候選生成群組、candidate pool template、local-result reuse 或跨 operation cache。

Global Exact DP MUST 依完整 `waler_order` 一支一支處理，每支各選恰好一個 candidate，並逐支累計材料 counts、Out distance、local regret、changed-Waler count 與 rank path。

#### Scenario: 兩支輸入相同的 Waler

- **WHEN** 同一次 Global operation 包含兩支 local-search 有效輸入完全相同的 eligible Waler
- **THEN** 系統 SHALL 仍為兩支 Waler 各執行一次 local candidate generation
- **AND** SHALL 建立兩個各自具有 WalerID 的 candidate groups
- **AND** Exact DP SHALL 仍處理兩個 Waler stages

#### Scenario: 每支選擇自己的候選

- **WHEN** 多支 Waler 進入 Global Exact DP
- **THEN** valid solution SHALL 為每支 Waler 各包含恰好一個 selected candidate
- **AND** 每支 selected candidate 的材料與 objective 貢獻 SHALL 分別累計

### Requirement: Global 候選擴大不得改變既有選擇規則

Global 專用候選池只 SHALL 擴大 Exact DP 的輸入選項，不得修改既有 material classification、Exact DP state key／merge、objective ordering、Waler order、local regret 定義或 deterministic tie-break。此 capability 不執行跨 Waler shared-inventory optimization，`shared_inventory_optimized` MUST 維持 `false`。

#### Scenario: 擴大候選池後執行 Exact DP

- **WHEN** 一支或多支 Waler 提供超過 5 個 Global candidates
- **THEN** Exact DP SHALL 使用既有 objective ordering 比較所有保留候選形成的 states
- **AND** SHALL NOT 因候選數增加而改寫 objective 權重或優先順序

#### Scenario: 不共享跨 Waler 庫存

- **WHEN** Global Exact DP 從擴大候選池選擇全場組合
- **THEN** 系統 SHALL 依既有行為累計材料分類與 objective
- **AND** SHALL NOT 將不同 Waler 的 inventory 合併為共享數量限制
- **AND** diagnostics 的 `shared_inventory_optimized` SHALL 為 `false`

### Requirement: 候選池範圍必須可診斷

Global Waler diagnostics SHALL 能區分各已執行 stages 在 stage 內去重後的候選數、跨 stage 完整 solution merge 後的候選數，以及 material-signature merge 後實際送入 Exact DP 的候選數。Counts MUST 以每支 Waler 分別記錄或可由結構化 diagnostics 明確還原，不得只提供無法區分截斷位置的單一總數。

#### Scenario: 候選經過三個保留邊界

- **WHEN** 一支 Waler 執行多個 stages，且候選先發生完整 solution 重複、再發生 material-signature dominance merge
- **THEN** diagnostics SHALL 分別呈現 stage outputs、跨 stage unique solutions 與送入 DP 的 material representatives 數量
- **AND** 測試 SHALL 能由 diagnostics 確認 Global pool 未被截為 5 個

### Requirement: 部分候選池不得進入全域選擇

若任一必要 Waler 沒有合法 candidate、候選收集或 merge 發生 exception，或在 candidate generation／merge 期間偵測 cancellation，Global operation SHALL 沿用既有 failure／cancelled semantics。系統 MUST NOT 將已完成 Waler 的部分 candidate groups 送入 Exact DP 或正式採用。

#### Scenario: 任一 Waler 沒有合法候選

- **WHEN** 一支 eligible Waler 的所有已執行 stages 都沒有合法 candidate
- **THEN** Global operation SHALL 回傳 invalid solution 與可辨識 failed-Waler diagnostics
- **AND** SHALL NOT 進入 Exact DP

#### Scenario: 候選合併期間取消

- **WHEN** Global candidate collection 或跨 stage／material-signature merge 期間收到 cancellation request
- **THEN** operation SHALL 以 cancelled outcome 結束
- **AND** SHALL NOT 發佈部分 candidate groups、Global solution 或正式 result
