# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：所有 ADDED Requirements 與各自 Scenarios；它們是本 change 的驗收契約。
- **實作前閱讀（P1）**：`../../design.md` 的 Decision 1～5 與 `../../tasks.md`。
- **需要時再讀（P2）**：主規格 `openspec/specs/support-editor-result-mutation/spec.md` 與 `openspec/specs/dxf-double-support-recognition/spec.md`。本 delta 不修改其既有 commit 或雙路辨識契約。

## Purpose

定義 Support ordered pieces 的 Shim 數量與位置、Waler 類型正規化、RC terminal joint 唯一例外、錯誤優先順序，以及自動 Solver 與人工 Support 編輯的共用 observable behavior。

## ADDED Requirements

### Requirement: Support layout SHALL contain at most one nonzero Shim

每個 Support ordered layout SHALL 包含零塊或一塊非零 Shim。`shim = 0` SHALL 表示沒有 Shim piece；零長或負長 piece SHALL NOT 進入 normalized ordered pieces。含有超過一塊非零 Shim 的可解析排列 SHALL 被判定為 engineering invalid，而非 parse failure。

#### Scenario: No Shim

- **WHEN** Support 的 Shim 設定為 `0`
- **THEN** normalized ordered pieces SHALL 不包含 Shim piece
- **AND** validator SHALL NOT 產生 Shim count 或 placement issue

#### Scenario: One nonzero Shim

- **WHEN** ordered pieces 恰有一塊長度大於 `0` 的 Shim
- **THEN** validator SHALL 依 Waler 類型與所在位置檢查該 Shim
- **AND** SHALL NOT 單因 Shim 數量將 layout 判為 invalid

#### Scenario: More than one nonzero Shim

- **WHEN** ordered pieces 含有兩塊或以上非零 Shim
- **THEN** validator SHALL 將 layout 判為 invalid
- **AND** reason SHALL 可辨識為 Shim 數量問題
- **AND** reason SHALL NOT 再回報 Shim placement issue
- **AND** 此 reason gate SHALL NOT 略過任何修改前既有的 score／penalty 計算

#### Scenario: Zero-length manual piece

- **WHEN** 人工輸入含有長度為 `0` 或負數的 Shim piece
- **THEN** normalization SHALL 依既有 basic input validation 拒絕該 piece
- **AND** 該輸入 SHALL NOT 被當成可保存的 engineering-invalid ordered layout

### Requirement: Shim placement SHALL follow normalized endpoint Waler types

在 Jack 數量正確且 Shim 數量不超過一塊時，Shim placement SHALL 依 normalized From／To Waler 類型判斷：Steel／Steel 的 Shim SHALL 緊鄰 Jack；只有一端為 RC 時，Shim SHALL 位於該 RC terminal；兩端皆為 RC 時，Shim SHALL 位於任一 terminal。沒有 Shim 時 SHALL 不產生 placement issue。

#### Scenario: Steel to Steel Shim adjacent to Jack

- **WHEN** normalized From／To Waler 類型皆為 Steel
- **AND** 唯一 Shim 緊鄰唯一 Jack
- **THEN** Shim placement SHALL 為 valid

#### Scenario: Steel to Steel Shim away from Jack

- **WHEN** normalized From／To Waler 類型皆為 Steel
- **AND** 唯一 Shim 未緊鄰 Jack
- **THEN** layout SHALL 為 invalid
- **AND** reason SHALL 可辨識為 Shim placement 問題

#### Scenario: From RC terminal Shim

- **WHEN** normalized From 類型為 RC 且 To 類型為 Steel
- **AND** 唯一 Shim 是 ordered pieces 的第一個 piece
- **THEN** Shim placement SHALL 為 valid

#### Scenario: To RC terminal Shim

- **WHEN** normalized From 類型為 Steel 且 To 類型為 RC
- **AND** 唯一 Shim 是 ordered pieces 的最後一個 piece
- **THEN** Shim placement SHALL 為 valid

#### Scenario: Both endpoints are RC

- **WHEN** normalized From／To 類型皆為 RC
- **AND** 唯一 Shim 位於 ordered pieces 的任一 terminal
- **THEN** Shim placement SHALL 為 valid
- **AND** 非 terminal Shim SHALL 為 invalid

### Requirement: Missing or unrecognized Waler type SHALL normalize to Steel

Waler 類型為缺失、空白或無法辨識的值時，Shim placement 驗證與 RC terminal 例外判定 SHALL 一律視為 Steel。只有可辨識的 RC 類型 SHALL 啟用 RC terminal 規則。

#### Scenario: Missing endpoint type follows Steel placement

- **WHEN** 某端 Waler 類型缺失或為空白
- **THEN** 該端 SHALL 以 Steel 參與 Shim placement 判斷
- **AND** 該端 SHALL NOT 取得 RC terminal 例外

#### Scenario: Unrecognized endpoint type follows Steel placement

- **WHEN** 某端 Waler 類型不是可辨識的 RC 或 Steel 表示
- **THEN** 該端 SHALL 以 Steel 參與 Shim placement 判斷
- **AND** 該端 SHALL NOT 取得 RC terminal 例外

#### Scenario: Explicit RC endpoint keeps RC behavior

- **WHEN** 某端 Waler 類型可辨識為 RC
- **THEN** 該端 SHALL 依 RC terminal placement 與 joint exception 規則判斷

### Requirement: RC terminal Shim to first Steel boundary SHALL be the only 1600 mm exception

一般 Support material joint 在兩端各 `1600 mm` 範圍內 SHALL 為 forbidden。唯一例外 SHALL 是 normalized RC 端的 terminal Shim 與朝 Strut 內部第一段相鄰 Steel 之 boundary，且只忽略該 RC 端對應的 end zone。例外 SHALL NOT 套用至 Shim／Jack、Shim／Shim、非 terminal Shim、其他 joints、Column `±830 mm` 或 Beam `±550 mm` 禁區。`1600 mm` 邊界 SHALL 採 inclusive forbidden semantics。

#### Scenario: From RC terminal Shim to first Steel

- **WHEN** From 端 normalized 類型為 RC
- **AND** ordered pieces 以 terminal Shim 接第一段 Steel 開始
- **AND** 該 boundary 位於 From 端 `1600 mm` end zone 且不在 Column／Beam 禁區
- **THEN** 該 boundary SHALL NOT 因 From end zone 被判 invalid

#### Scenario: To RC first Steel to terminal Shim

- **WHEN** To 端 normalized 類型為 RC
- **AND** ordered pieces 以第一段 Steel 接 terminal Shim 結束
- **AND** 該 boundary 位於 To 端 `1600 mm` end zone 且不在 Column／Beam 禁區
- **THEN** 該 boundary SHALL NOT 因 To end zone 被判 invalid

#### Scenario: Terminal Shim adjacent to Jack

- **WHEN** RC terminal Shim 的相鄰 piece 是 Jack 而非 Steel
- **THEN** boundary SHALL 仍受 `1600 mm` end zone 限制
- **AND** layout SHALL 為 invalid

#### Scenario: Other joint in the same end zone

- **WHEN** RC terminal Shim 與第一段 Steel boundary 以外的 joint 位於相同 `1600 mm` end zone
- **THEN** 該 joint SHALL 仍被判為 forbidden

#### Scenario: Column or Beam overlaps the exception boundary

- **WHEN** 合格的 RC terminal Shim／Steel boundary 同時位於 Column 或 Beam 禁區
- **THEN** 該 boundary SHALL 仍被判為 forbidden

#### Scenario: Missing type cannot use the exception

- **WHEN** terminal Shim 所在端的 Waler 類型缺失、空白或無法辨識
- **AND** Shim／Steel boundary 位於該端 `1600 mm` end zone
- **THEN** 該端 SHALL 視為 Steel
- **AND** 該 boundary SHALL 為 forbidden

#### Scenario: Joint exactly at 1600 mm

- **WHEN** 非豁免 joint 位於距端點恰好 `1600 mm` 的 station
- **THEN** 該 joint SHALL 被判為 forbidden

### Requirement: Validation issues SHALL follow a deterministic priority

Support validation reason SHALL 使用固定優先順序：Jack count、Shim count、Shim placement、gap、forbidden joint、Steel length。高優先 gate 未通過時 SHALL 只限制 reason 要回報哪些 issues；gate SHALL NOT 中止完整 candidate evaluation、scoring 或 penalty 計算。既有扣分輸入與計算（包含 `count_forbidden_piece_joints` 等既有項目）SHALL 仍完整執行。其餘可同時回報的 issues SHALL 依固定順序組成 reason，且不受 piece iteration、collection 或執行順序影響。

#### Scenario: Invalid Jack count suppresses later issues

- **WHEN** ordered pieces 的 Jack 數量不符合既有規則
- **THEN** reason SHALL 只包含 Jack 數量問題
- **AND** reason builder SHALL NOT 回報 Shim count、Shim placement、gap、forbidden joint 或 Steel length issue
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score／penalty 項目

#### Scenario: Multiple Shims suppress placement and later issues

- **WHEN** Jack 數量正確
- **AND** ordered pieces 含有超過一塊非零 Shim
- **THEN** reason SHALL 只包含 Shim 數量問題
- **AND** reason builder SHALL NOT 回報 Shim placement、gap、forbidden joint 或 Steel length issue
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score／penalty 項目

#### Scenario: Remaining issues have stable order

- **WHEN** Jack 與 Shim 數量 gate 均通過
- **AND** layout 同時觸發兩個或以上其餘 issues
- **THEN** reason SHALL 依 Shim placement、gap、forbidden joint、Steel length 的順序組成
- **AND** 等價 pieces 或 checks 以不同 iteration／execution order 執行時 SHALL 產生相同 reason

### Requirement: Automatic and manual Support validation SHALL share the same contract

自動 Solver evaluation 與人工 Support editor staged recalculation SHALL 使用相同的 Waler type normalization、Shim count、Shim placement、RC terminal exception 與 issue priority。Presentation SHALL NOT 複製這些工程規則。

#### Scenario: Automatic candidate violates Shim rule

- **WHEN** 自動求解評估的 ordered pieces 違反本 capability
- **THEN** Support evaluation SHALL 將候選判為 invalid
- **AND** 候選 SHALL NOT 以合法方案進入後續選擇

#### Scenario: Manual edit violates Shim rule

- **WHEN** 人工編輯產生可解析但違反本 capability 的 ordered pieces
- **THEN** staged Support plan SHALL 使用與自動 evaluation 相同的 invalid verdict 與 issue priority

### Requirement: Parseable manual invalid layouts SHALL remain saveable

可解析且通過 basic piece normalization 的人工 ordered pieces，即使因 Shim count、placement 或 joint rule 失敗，SHALL 沿用既有 staged invalid 保存語意，更新 calculated time、result metadata 與 dirty state。不可解析或含非正長 piece 的輸入 SHALL 繼續依既有流程拒絕，且不得改變已 committed result。

#### Scenario: Save an engineering-invalid edit

- **WHEN** 人工 ordered pieces 可解析但違反本 capability
- **THEN** staged recalculation SHALL 保存 invalid Support result 與可辨識 reason
- **AND** SHALL 沿用既有 result mutation semantics

#### Scenario: Reject an unparseable edit

- **WHEN** 人工輸入無法解析或未通過 basic piece normalization
- **THEN** edit SHALL 被拒絕
- **AND** committed Support result SHALL 保持不變

### Requirement: Saved legacy results SHALL be revalidated only on recalculation

載入 Project 中既有已保存 Support result 時，系統 SHALL NOT 因本 capability 自動重新驗證或改寫該結果。下一次 Support 重算或人工 staged recalculation SHALL 套用本 capability。

#### Scenario: Load a legacy saved result

- **WHEN** Project 載入一筆在本 change 前保存的 Support result
- **THEN** 系統 SHALL 保留該結果及其 metadata
- **AND** SHALL NOT 僅因載入而改寫 valid／invalid 狀態

#### Scenario: Recalculate after loading

- **WHEN** 使用者對已載入 Project 執行 Support 重算或 staged recalculation
- **THEN** 新結果 SHALL 套用本 capability 的全部規則

### Requirement: Optimization behavior outside legality SHALL remain unchanged

本 capability SHALL NOT 修改合法或不合法 Support candidate 的 scoring、penalty、score breakdown、相對排序、材料比例、候選數、Beam Width、Random Seed、搜尋階段、Jack adjacency、SharedLayoutGroup identity 或 DXF 雙路支撐辨識。Phase 1 cache SHALL 維持 runtime-only 且不因本 change 提升 persisted policy version。若 reason gate 與既有扣分路徑無法解耦，implementation SHALL 停止並回報，而不得自行改變 scoring 行為。

#### Scenario: Legal layout keeps existing score

- **WHEN** ordered pieces 在修改前後皆符合 hard constraints
- **THEN** Support score 與 score breakdown SHALL 保持既有計算方式

#### Scenario: Invalid candidate keeps existing score and ordering

- **WHEN** 某個不合法 candidate 在修改前已有 score、penalty 與 score breakdown
- **THEN** 修改後的 score、penalty 與 score breakdown SHALL 與修改前完全相同，不使用容差
- **AND** 該 candidate 相對於其他既有 candidates 的排序 SHALL 保持不變
- **AND** reason gate SHALL NOT 略過 `count_forbidden_piece_joints` 或任何修改前會執行的扣分計算

#### Scenario: Existing real drawing remains stable

- **WHEN** 既有實際圖面 fixture 的 Waler identity 與類型一致，且 layouts 符合本 capability
- **THEN** 完整 Support 求解的候選集合與最終結果 SHALL 與修改前一致
- **AND** 不得為通過此回歸而調整 scoring 或 search 參數

#### Scenario: Reversed double-support members keep exact identity behavior

- **WHEN** 兩支幾何合格的 Strut 方向相反但對應相同精確 Waler ID pair
- **THEN** 既有 DXF canonical endpoint mapping SHALL 維持原雙路辨識結果
- **AND** 本 capability SHALL NOT 以 Waler chain 或 type-only 比對取代 exact identity contract
