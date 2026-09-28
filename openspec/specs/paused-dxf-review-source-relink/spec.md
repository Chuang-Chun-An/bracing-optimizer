# paused-dxf-review-source-relink Specification

## Purpose

讓使用者在 paused DXF Review 的原始來源被移動、改名或位於另一台電腦時，可以重新連結內容完全相同的 DXF，並在候選內容不同、失敗或取消時完整保留原 Review 與 Project 狀態。

## Requirements

### Requirement: Paused Review 提供專用來源重新連結

當 Project workflow 為 `REVIEW`、存在可恢復的 Review state，且目前來源缺失、不可讀或 fingerprint 不符時，系統 SHALL 提供 Review 專用 Relink。此流程 MUST 保持為 Review 恢復作業，不得改用完成匯入後的 Project Relink 語意。

#### Scenario: 缺少來源時可選擇候選 DXF
- **WHEN** 使用者嘗試繼續一個具有已保存 Review state、但目前來源不存在的 paused Review
- **THEN** 系統提供選擇候選 DXF、重試或取消的途徑，且不要求先建立或修改正式 Project geometry

#### Scenario: 非 REVIEW workflow 不進入專用流程
- **WHEN** 目前 workflow 不是 `REVIEW`
- **THEN** 系統不使用 paused Review Relink 行為，既有完成匯入後 Relink 行為維持不變

### Requirement: 候選來源必須是可驗證的有效 DXF

系統 SHALL 驗證候選檔案可讀、可解析為 DXF，並計算其 SHA-256。候選 SHA-256 與 paused Review state 保存的 `source_fingerprint` 完全相同時，系統 MUST 回報 `EXACT_MATCH`；兩者不同時，系統 MUST 將候選送入 staged compatible recovery，不得直接修改目前 paused Review。staged recovery 完成後，結果 MUST 明確區分 `COMPATIBLE_RECOVERY_AVAILABLE`、`INCOMPATIBLE_SOURCE` 與 `VALIDATION_FAILED`。檔案選擇器取消屬於未開始驗證，不得被回報成驗證失敗。

#### Scenario: 候選內容完全相同
- **WHEN** 候選 DXF 可正常解析，且 SHA-256 與保存的 Review fingerprint 相同
- **THEN** 系統回報 `EXACT_MATCH` 並建立可原子採用的新來源參照

#### Scenario: 候選內容不同
- **WHEN** 候選 DXF 可正常解析，但 SHA-256 與保存的 Review fingerprint 不同
- **THEN** 系統只建立隔離的 staged recovery，且在 compatibility 判定與使用者接受完成前不修改目前 paused Review

#### Scenario: 內容不同但可建立 recovery plan
- **WHEN** 候選 DXF 可正常解析、SHA-256 與保存的 Review fingerprint 不同，且 staged recovery 通過 compatibility gate
- **THEN** 系統回報 `COMPATIBLE_RECOVERY_AVAILABLE`，並提供尚未提交的 recovered Review state 與 recovery summary

#### Scenario: 內容不同且無法安全恢復
- **WHEN** 候選 DXF 可正常解析、SHA-256 與保存的 Review fingerprint 不同，但 staged recovery 無法證明與既有 Review 相容
- **THEN** 系統回報 `INCOMPATIBLE_SOURCE` 與可顯示的原因，且不建立可提交的 recovered Review state

#### Scenario: 候選檔案驗證失敗
- **WHEN** 候選路徑不存在、不是有效檔案、DXF 無法解析、重新辨識失敗或 fingerprint 計算失敗
- **THEN** 系統回報 `VALIDATION_FAILED` 與可顯示的原因，並允許使用者重試或取消

#### Scenario: Saved Review 缺少 fingerprint
- **WHEN** paused Review state 沒有可用的 `source_fingerprint`
- **THEN** 系統回報 `VALIDATION_FAILED`，不得以檔名、路徑、檔案大小、修改時間或其他 hash 猜測候選相同或相容

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

### Requirement: 不成功或未接受的 Relink 保持零副作用

`INCOMPATIBLE_SOURCE`、`VALIDATION_FAILED`、檔案選擇取消，以及 compatible recovery 被拒絕或取消，MUST 保留原 paused Review state、原來源參照、workflow 與正式 Project 資料。staged recovery 在使用者接受前 MUST NOT 使 Project 成為 dirty、不得替換同工作階段 Review cache，亦不得改動 Solver result、Solver memory 或候選 cache。

#### Scenario: 內容不同後重試
- **WHEN** 第一個候選回報 `INCOMPATIBLE_SOURCE`，使用者選擇另一個候選重試
- **THEN** 第二次驗證仍以原 paused Review state 與原 fingerprint 為基準，不使用第一個候選留下的任何資料

#### Scenario: 驗證失敗後取消
- **WHEN** 候選驗證失敗後使用者取消
- **THEN** 下次繼續 Review 時仍可從提交前的 paused Review state 再次嘗試重新連結

#### Scenario: 拒絕 compatible recovery
- **WHEN** 系統已建立 compatible recovery plan，但使用者拒絕或取消採用
- **THEN** 系統丟棄 staged recovery，並完整保留原 paused Review、來源參照與 runtime cache

### Requirement: 成功 Relink 後維持 paused Review lifecycle

成功提交 `EXACT_MATCH` 或使用者已接受的 compatible recovery 後，系統 SHALL 保持 workflow 為 `REVIEW`、將 Project 標記為需要保存新的來源關係，並透過既有 resume path 繼續 DXF Review。系統 MUST NOT 自動完成 Import，也 MUST NOT 將 workflow 轉為 `COMPLETED`。Compatible recovery 後需重新確認或已停用的項目 MUST 留在 Review 中供使用者處理。

#### Scenario: 成功後繼續 Review
- **WHEN** Exact Match 來源成功提交
- **THEN** 系統以原有 Review state 恢復 Review，原本待確認或有問題的項目維持原狀

#### Scenario: Compatible recovery 成功後繼續 Review
- **WHEN** 使用者接受 compatible recovery，且系統成功提交 recovered Review state
- **THEN** 系統以候選來源與 recovered Review state 恢復 Review，並顯示需要重新確認或已停用的項目

#### Scenario: 保存後可再次載入
- **WHEN** 成功 Relink 的 paused Review 隨 Project 被保存並重新載入
- **THEN** 系統仍讀取為 `REVIEW`，並可由已保存的新來源關係與 Review state 繼續工作

### Requirement: 現有持久化格式保持相容

系統 SHALL 沿用現有 paused Review persistence 欄位、Review state version 與 Project schema。成功 Relink 不得為了本功能建立新的持久化格式；recovery plan、recovery summary 與未提交的候選辨識結果屬於暫存資料，不得成為新的 Project truth。未持久化的 UI 頁籤或步驟位置不在恢復保證內。

#### Scenario: Exact Match 不升級 schema
- **WHEN** 一個現行合法的 paused Review 成功以 Exact Match 重新連結並保存
- **THEN** 系統使用既有 Project schema 與 Review state version 表示新的來源關係

#### Scenario: Compatible recovery 不升級 schema
- **WHEN** 一個 compatible recovery 成功提交並隨 Project 保存
- **THEN** 系統以既有 Review state 欄位保存已採用的候選來源與恢復後狀態，不保存 recovery plan 或 summary 作為新的 schema 欄位

#### Scenario: UI Step 未持久化
- **WHEN** paused Review state 沒有保存目前頁籤或步驟位置
- **THEN** Relink 只恢復既有持久化的工程與 Review 狀態，不保證返回原 UI Step

### Requirement: 內容不同的候選必須在隔離狀態重新辨識

候選 fingerprint 與保存值不同時，系統 MUST 以候選 DXF、可重用且在候選 context 中仍有效的 layer classification、coordinate system 與 import mode 建立隔離的 staged Review 基底，並重新執行候選辨識、candidate 建立、association 與 validation。系統 MUST NOT 將舊候選點、舊 association、舊 validation 結果或舊辨識物件直接當作候選來源的結果。既有 setting 通過現行 validator 時 MUST 分類為 `preserved`；不再有效時 MUST 使用既有 safe/default behavior，並分類為 `requires_review`，不得強制沿用。

#### Scenario: 候選仍存在已知圖層
- **WHEN** 保存的 layer classification 所指圖層仍存在於候選 DXF，且其分類值仍有效
- **THEN** recovered Review 沿用該分類，並在 recovery summary 將其列為 `preserved`

#### Scenario: 候選新增圖層
- **WHEN** 候選 DXF 包含保存的 layer classification 未涵蓋的新圖層
- **THEN** 系統不得自動信任新圖層為既有工程角色，並在 recovery summary 將該 layer-classification subject 列為 `requires_review`

#### Scenario: 候選缺少原有圖層
- **WHEN** 保存的 layer classification 指向候選 DXF 已不存在的圖層
- **THEN** 系統不得因不存在的圖層直接套用錯誤分類，並在 recovery summary 將該 layer-classification subject 列為 `requires_review` 及說明影響

#### Scenario: Coordinate system 與 import mode 仍有效
- **WHEN** 保存的 coordinate system 或 import mode 通過候選 context 的現行 validator
- **THEN** recovered Review 沿用該 setting，並在 recovery summary 將其列為 `preserved`

#### Scenario: Coordinate system 或 import mode 不再有效
- **WHEN** 保存的 coordinate system 或 import mode 未通過候選 context 的現行 validator
- **THEN** 系統不得強制沿用該 setting，MUST 使用既有 safe/default behavior，並在 recovery summary 將該 setting 列為 `requires_review`

#### Scenario: 舊辨識快取不得跨內容沿用
- **WHEN** 候選 DXF fingerprint 與保存值不同
- **THEN** staged recovery 使用候選重新辨識的結果，且在使用者接受前不替換目前 Review session 的辨識快取

### Requirement: Compatible recovery 必須通過關鍵構件唯一配對

系統 MUST 將 saved Review 中每一支既有 Waler、Strut 與 Brace 配對至候選重新辨識結果中的唯一構件。系統 MUST 先以相同構件角色與既有幾何容差建立可接受候選，再依既有 evidence priority 選擇唯一配對：shared source handle、same source layer、changed source layer；同一 evidence priority 內依幾何誤差排序並沿用既有 ambiguity 規則。任一既有關鍵構件缺少配對或存在歧義時，系統 MUST 回報 `INCOMPATIBLE_SOURCE`；候選來源新增的構件 SHALL 不阻止 recovery，但 MUST 列為 `requires_review`。不同構件角色之間不得互相配對。

#### Scenario: Handle 改變但幾何唯一對應
- **WHEN** 既有構件在候選中的 source handle 已改變，但同角色幾何可依既有配對規則唯一對應
- **THEN** 系統允許該構件通過 compatibility gate，並將 recovered Review 的來源 identity 綁定至候選構件

#### Scenario: 候選增加關鍵構件
- **WHEN** 所有既有 Waler、Strut 與 Brace 都能唯一配對，但候選另有新增構件
- **THEN** 系統允許建立 recovery plan，且將新增構件列為 `requires_review`

#### Scenario: 既有關鍵構件缺少配對
- **WHEN** 任一既有 Waler、Strut 或 Brace 在候選結果中沒有可接受的同角色配對
- **THEN** 系統拒絕建立可提交的 recovery plan，並指出缺少配對的既有構件

#### Scenario: 既有關鍵構件配對歧義
- **WHEN** 任一既有 Waler、Strut 或 Brace 有多個候選符合既有配對規則，且無法得到唯一結果
- **THEN** 系統拒絕建立可提交的 recovery plan，不得任意選擇其中一個候選

### Requirement: Recovery summary categories 必須互斥且由 entries 推導

每一個 recovery summary entry MUST 恰好屬於 `preserved`、`requires_review` 或 `disabled` 其中一類，不得同時屬於多類。`preserved` SHALL 表示舊人工 state 已安全 replay 到 candidate-based recovered Review，且在 recovered state 中保持有效。`requires_review` SHALL 表示候選中仍存在可處理的工程 subject，但舊 decision、setting 或 confirmation 已不能視為有效；系統保留 candidate-based Review state，並要求使用者重新檢查、設定或確認。`disabled` SHALL 表示舊人工 decision 不得套用到 recovered Review；該 decision 只保留為 recovery summary 的失效紀錄，MUST NOT 對 recovered engineering state 產生效果。各 category count MUST 由其 entries 推導，不得維護可與 entries 分離的第二份計數。

#### Scenario: Entry 只能屬於一個 category
- **WHEN** 系統建立任一 recovery summary entry
- **THEN** 該 entry 恰好具有一個正式 category，且不會同時被計入其他 category

#### Scenario: Counts 由 entries 推導
- **WHEN** 系統顯示 preserved、requires-review 與 disabled counts
- **THEN** 每一 count 等於對應 category entries 的實際數量

#### Scenario: Disabled decision 不影響 recovered state
- **WHEN** 一個舊人工 decision 被分類為 `disabled`
- **THEN** recovered engineering state 不包含該 decision 的效果，summary 只保留其失效紀錄與原因

### Requirement: Recovered Review 必須以候選結果為基底選擇性恢復人工狀態

系統 MUST 以候選重新辨識結果作為 recovered Review 的工程基底，並依本 Requirement 的逐項規則恢復人工 state。材料規格、人工端點與 Waler 接觸輸入 replay 成功時 MUST 分類為 `preserved`，replay 失敗時 MUST 分類為 `requires_review`。Source exclusion 只有在 exact excluded source identity 仍存在且對相同 role 有效時才可分類為 `preserved`；critical-member 的 geometry-only rebind MUST NOT 轉移 exclusion，exact identity 不再存在時 exclusion MUST 分類為 `disabled`。雙路支撐 decision 只有在兩支 Strut 均唯一 rebind 且候選 pair 唯一存在時才可分類為 `preserved`，否則 MUST 分類為 `requires_review`。Confirmation 只有在 candidate current-state signature 仍有效時才可分類為 `preserved`，否則 MUST 從 recovered state 移除並分類為 `requires_review`。任何項目均不得靜默套用至其他物件。

#### Scenario: Material replay 成功
- **WHEN** 舊材料規格已對唯一重新綁定的候選構件成功 replay 並保持有效
- **THEN** recovered Review 保留該材料規格，並將 summary entry 分類為 `preserved`

#### Scenario: Material replay 失敗
- **WHEN** 舊材料規格無法對候選構件安全 replay 或 replay 後不再有效
- **THEN** recovered Review 使用 candidate-based state，並將該材料 subject 分類為 `requires_review`

#### Scenario: Manual endpoint replay 成功
- **WHEN** 舊人工端點已對唯一重新綁定的候選構件成功 replay 並保持有效
- **THEN** recovered Review 保留該人工端點，並將 summary entry 分類為 `preserved`

#### Scenario: Manual endpoint replay 失敗
- **WHEN** 舊人工端點無法對候選構件安全 replay 或 replay 後不再有效
- **THEN** recovered Review 使用 candidate-based geometry，並將該 endpoint subject 分類為 `requires_review`

#### Scenario: Waler contact replay 成功
- **WHEN** 舊 Waler contact input 已對唯一重新綁定的候選 Waler 成功 replay 並保持有效
- **THEN** recovered Review 保留該 contact input，並將 summary entry 分類為 `preserved`

#### Scenario: Waler contact replay 失敗
- **WHEN** 舊 Waler contact input 無法對候選 Waler 安全 replay 或 replay 後不再有效
- **THEN** recovered Review 使用 candidate-based contact state，並將該 contact subject 分類為 `requires_review`

#### Scenario: Source exclusion exact identity 仍有效
- **WHEN** 舊 source exclusion 的 exact source identity 在候選中仍存在，且對相同 role 仍有效
- **THEN** recovered Review 保留該 exclusion，並將 summary entry 分類為 `preserved`

#### Scenario: Source exclusion 只有 geometry match
- **WHEN** 被排除來源的 exact source identity 已不存在，但某個 critical member 可用 geometry-only 規則重新配對
- **THEN** 系統不得把 exclusion 轉移至該 geometry-matched member，MUST 不套用舊 exclusion 並將其分類為 `disabled`

#### Scenario: Source exclusion exact identity 不再存在
- **WHEN** 舊 source exclusion 的 exact source identity 在候選中不再存在或不再對相同 role 有效
- **THEN** 系統不得套用該 exclusion，並將 summary entry 分類為 `disabled`

#### Scenario: 雙路支撐決策仍可辨識
- **WHEN** 雙路支撐 decision 所涉及的兩支 Strut 均已唯一重新綁定，且候選結果仍存在同一組可判定配對
- **THEN** recovered Review 保留該 decision，以候選來源 identity 表示，並將 summary entry 分類為 `preserved`

#### Scenario: 雙路支撐決策失去有效配對
- **WHEN** 雙路支撐 decision 的任一 Strut 無法安全重新綁定，或候選結果不再存在該組配對
- **THEN** 系統不保留該 decision，並將對應 candidate-based double-support subject 分類為 `requires_review`

#### Scenario: Confirmation 簽章仍有效
- **WHEN** 一個既有 confirmation 在 recovered Review 的候選工程狀態下重新計算後仍具相同有效簽章
- **THEN** recovered Review 保留該 confirmation，並將 summary entry 分類為 `preserved`

#### Scenario: Confirmation 因候選內容失效
- **WHEN** 一個既有 confirmation 的工程簽章在 recovered Review 中已不再有效
- **THEN** 系統移除該 confirmation，保留 candidate-based Review subject，並將 summary entry 分類為 `requires_review`

### Requirement: Compatible recovery 必須先摘要並取得明確接受

系統 SHALL 在提交 compatible recovery 前顯示 recovery summary，至少分別列出 `preserved`、`requires_review` 與 `disabled` 的數量和原因。只有使用者明確接受該 recovery plan 後，系統才可進入提交；檔案選擇本身不構成 compatible recovery 的接受。Exact Match 仍沿用選檔即授權，MUST NOT 顯示 compatible recovery summary 或第二次確認。

#### Scenario: 顯示完整分類後接受
- **WHEN** 系統建立 `COMPATIBLE_RECOVERY_AVAILABLE` plan
- **THEN** 使用者在接受前可看見 preserved、requires-review 與 disabled 摘要及其原因

#### Scenario: 使用者接受 recovery plan
- **WHEN** 使用者在檢視 recovery summary 後明確選擇接受
- **THEN** 系統進入 compatible recovery 的原子提交流程

#### Scenario: 使用者拒絕 recovery plan
- **WHEN** 使用者在檢視 recovery summary 後選擇拒絕或關閉確認
- **THEN** 系統不提交 recovered Review state，並依零副作用規則保留原狀態

#### Scenario: Exact Match 不增加確認
- **WHEN** 候選驗證結果為 `EXACT_MATCH`
- **THEN** 系統不建立 recovery summary，並依既有選檔授權規則直接進入原子提交

### Requirement: Compatible recovery 採用必須是原子操作

系統 MUST 在 compatible recovery 提交前再次確認候選 fingerprint 與 plan 建立時相同，並確認目前 paused Review state 仍等於 plan 的基準。提交成功時，候選來源參照、recovered Review state 與候選重新辨識 cache MUST 作為單一狀態轉換採用；提交失敗時 MUST 回復提交前完整狀態。該操作 MUST NOT 套用正式 Project geometry，亦不得改變 Solver result、Solver memory 或候選 cache。

#### Scenario: 候選在 recovery plan 建立後改變
- **WHEN** 候選通過 compatibility gate 後、提交前，其 fingerprint 發生改變
- **THEN** 系統回報 `VALIDATION_FAILED` 並拒絕提交，不採用候選路徑、recovered Review state 或候選辨識 cache

#### Scenario: Paused Review 在 recovery plan 建立後改變
- **WHEN** recovery plan 建立後、提交前，目前 paused Review state 已不同於 plan 的基準
- **THEN** 系統拒絕 stale commit，保留最新 paused Review state，且不採用 plan 中的任何候選資料

#### Scenario: Compatible recovery 提交成功
- **WHEN** 使用者已接受 recovery plan，且提交前重新驗證全部通過
- **THEN** 系統同時採用候選來源參照、recovered Review state 與候選重新辨識 cache，淘汰與舊 fingerprint 綁定的 Review cache，workflow 維持 `REVIEW`

#### Scenario: Compatible recovery 提交中發生錯誤
- **WHEN** 更新來源參照、Review state 或 runtime cache 的任何步驟發生錯誤
- **THEN** 系統回復提交前的來源參照、paused Review state、workflow、dirty state 與 runtime cache，不留下混合狀態

### Requirement: 角撐修補決策不得跨內容靜默轉移

系統 SHALL 將已採用的角撐修補視為與 exact target source identity、人工採用工程線及明確 Waler／Strut 關係綁定的人工決策。`EXACT_MATCH` Relink MUST 完整保留該修補 state。候選 DXF fingerprint 不同時，compatible recovery MUST 以候選重新辨識結果為基底，且 MUST NOT 依一般 critical-member geometry matching 或相同／相近位置，自動把舊角撐修補效果轉移到候選來源。

若 changed-content 候選仍存在相同角色與 exact source identity 的可處理角撐 subject，舊修補決策 SHALL 不套用並分類為 `requires_review`；若 exact source identity 不再存在、角色改變或無法定位可處理 subject，該舊修補決策 SHALL 分類為 `disabled`。兩種分類都不得讓舊修補幾何影響 recovered engineering state。

任何在 compatible recovery 中分類為 `requires_review` 或 `disabled` 的 repaired CornerBrace decision MUST NOT 成為其他 CornerBrace repair 的 primary 或 secondary reference。只有使用者在 recovered Review 重新完成修補、明確採用並使其符合現行 secondary eligibility 後，它才可作為 secondary reference；compatible recovery 不得自動恢復 reference eligibility。

#### Scenario: Exact Match 保留角撐修補
- **WHEN** paused Review 透過 `EXACT_MATCH` 候選重新連結來源
- **THEN** 系統 SHALL 與其他既有 Review state 一起完整保留已採用的角撐修補
- **AND** SHALL NOT 重新辨識或要求第二次修補確認

#### Scenario: changed-content 候選保留 exact subject
- **WHEN** compatible recovery 的候選內容不同，但相同角色與 exact source identity 的角撐 subject 仍存在
- **THEN** 系統 MUST 以候選辨識幾何保留該 subject
- **AND** MUST NOT 套用舊修補效果
- **AND** SHALL 將該修補 decision 分類為 `requires_review`

#### Scenario: changed-content 候選失去 exact subject
- **WHEN** compatible recovery 的候選內容不同，且角撐修補的 exact source identity 不再存在、角色改變或無法定位可處理 subject
- **THEN** 系統 MUST 不套用舊修補效果
- **AND** SHALL 將該修補 decision 分類為 `disabled`

#### Scenario: geometry-only match 不轉移修補
- **WHEN** 舊修補來源可在候選中找到幾何相近但 source identity 不同的角撐
- **THEN** 系統 MUST NOT 將舊 repaired axis、目標 Waler／Strut 或 reference provenance 轉移至該角撐
- **AND** recovered Review SHALL 維持 candidate-based engineering state

#### Scenario: Requires-review repair 不得提供 reference evidence
- **WHEN** compatible recovery 將一筆舊 CornerBrace repair 分類為 `requires_review`
- **THEN** recovered Review MUST NOT 將該舊 repair 當作後續 repair 的 primary 或 secondary reference
- **AND** 使用者必須先在 recovered Review 重新建立並確認合法 repair，才能恢復 secondary eligibility
