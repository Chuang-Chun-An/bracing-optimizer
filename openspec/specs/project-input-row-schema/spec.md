# Project Input Row Schema Specification

## 閱讀導航

- **必讀**：Requirement「Project input 必須符合現行 table contract」、「結構驗證必須先於 hydration」及「已載入資料不得再做 legacy migration」。
- **儲存與 runtime ingress 條件式閱讀**：Requirement「正式儲存輸出必須可原樣重新驗證」。
- **可先跳過**：版本號分類請讀 `project-schema-compatibility`；Solver、DXF recognition、CAD transport 與 export 不屬於本 capability。

## Purpose

定義 persisted Project `input_data` 的 canonical table／row shape，以及 validation、hydration 與 Presentation 之間的責任邊界，使不符合現行格式的資料被一致拒絕，而不是在載入後由 legacy migration 修補。本 spec 的完全比對只適用於目前固定的 schema 3 contract；既有政策未定義未來新增 row 欄位時的版本、預設值或拒絕策略，本 spec 不補定該政策。

## Requirements

### Requirement: Project input 必須符合現行 table contract

Project `input_data` SHALL 以系統目前正式的 table contract 驗證。既有必要 tables MUST 存在且為陣列；允許但非必要的現行 tables MAY 缺少；`input_data` MUST NOT 包含現行 contract 未定義的 table。每個已提供 table 的每筆 row SHALL 完整包含該 table 的正式欄位，且 MUST NOT 包含 contract 未定義的欄位。驗證 SHALL 使用同一份正式 table／column contract，不得為已知 legacy table 或 field 建立個別接受、轉換或黑名單規則。

#### Scenario: Canonical Project rows pass structure validation

- **WHEN** Project `input_data` 含所有必要 tables，且每個已提供 row 的欄位集合完全符合其現行 table contract
- **THEN** 系統 SHALL 讓該 payload 繼續進入既有 Domain 與其他 Project validation

#### Scenario: Missing current field rejects the row generically

- **WHEN** 任一 persisted Project row 缺少其現行 table contract 的必要欄位
- **THEN** 系統 SHALL 以 Project row schema mismatch 拒絕整個 payload
- **AND** 錯誤資訊 SHALL 指出 table、row及缺少欄位

#### Scenario: Unsupported field rejects the row generically

- **WHEN** 任一 persisted Project row 含有現行 table contract 未定義的欄位
- **THEN** 系統 SHALL 以 Project row schema mismatch 拒絕整個 payload
- **AND** 錯誤資訊 SHALL 指出 table、row及不支援欄位
- **AND** 系統 MUST NOT 依欄位名稱推測其歷史版本或轉換方式

#### Scenario: Unsupported input table is rejected

- **WHEN** Project `input_data` 含有現行 Project table contract 未定義的 table
- **THEN** 系統 SHALL 拒絕整個 payload並指出不支援的 table
- **AND** 系統 MUST NOT 刪除該 table 後繼續載入

### Requirement: Row schema mismatch 必須提供通用復原指引

任一 Project row 或 table schema mismatch SHALL 回報「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並 SHALL 附上底層驗證錯誤。底層錯誤 SHALL 保留足以辨識 table、row，以及 missing／unsupported field 或 unsupported table 的資訊；系統 MUST NOT 以特定 legacy 欄位名稱建立例外訊息或轉換分支。

#### Scenario: Generic row mismatch reports actionable error

- **WHEN** Project 因 missing field、unsupported field 或 unsupported table 無法通過現行 row schema validation
- **THEN** 系統 SHALL 顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」
- **AND** 系統 SHALL 附上該次失敗的底層驗證錯誤

### Requirement: 結構驗證必須先於 hydration

Project row shape validation SHALL 在建立任何 staged Application model之前完成。任一 table／row schema mismatch MUST 拒絕整個 Project，且 MUST NOT 建立可被採用的部分 Project input、result、DXF state 或 path。結構驗證通過後，系統才 MAY 執行既有 Domain validation與 hydration。

#### Scenario: Invalid row cannot be repaired by hydration defaults

- **WHEN** persisted Project row 缺少現行欄位，而 Application runtime model對同名欄位具有建立新 row 時使用的 default
- **THEN** load SHALL 在 hydration 前拒絕該 payload
- **AND** MUST NOT 以 runtime default補足 persisted row

#### Scenario: Row mismatch preserves current Project state

- **WHEN** 使用者在已有 committed Project 時開啟含 row schema mismatch 的 Project
- **THEN** 目前 Project input、results、DXF state、path與dirty state SHALL 保持不變

### Requirement: 已載入資料不得再做 legacy migration

通過 Project validation並完成 hydration 的 rows SHALL 已符合現行欄位契約。Application hydration、Tree refresh、Preview rendering與detail loading MUST NOT 將舊欄位轉為現行欄位，也 MUST NOT 因讀取或顯示而新增、覆寫或刪除 Project row fields。

#### Scenario: Strut consumers only use current position fields

- **WHEN** 已載入 Strut row 進入 Tree、Preview或detail loading
- **THEN** 系統 SHALL 只使用 `BeamPositions` 與 `ColumnPositions` 表達位置
- **AND** 操作前後的 Project rows SHALL 深度相等

#### Scenario: Repeated display is side-effect free

- **WHEN** 使用者重複刷新 Strut Tree、重畫 Preview或切換 Strut detail
- **THEN** Project row內容與dirty state SHALL 保持不變

### Requirement: 正式儲存輸出必須可原樣重新驗證

每次成功儲存的 Project SHALL 使其 `input_data` tables與rows符合相同的現行 table contract，且不需要 legacy normalization即可通過後續 load structure validation。DXF、CAD或manual runtime ingress MAY 使用 Application defaults建立新 row，但在 persisted payload產生前 MUST 已成為 canonical row。

#### Scenario: Saved Project round-trips without migration

- **WHEN** 使用者成功儲存由 DXF、CAD或manual workflow建立的 Project，之後重新載入該檔案
- **THEN** persisted `input_data` SHALL 原樣通過現行 table／row shape validation
- **AND** load MUST NOT 執行任何 legacy field conversion
