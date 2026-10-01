# Project Schema Compatibility Spec Delta

## 閱讀導航

- **必讀**：修改後的 Requirement「以版本上限與現行結構共同判斷是否可載入」及 old-structure scenario。
- **處理錯誤與 UI 時必讀**：修改後的 Requirement「拒絕時提供可行的下一步並保留目前狀態」，包含 missing／older old-structure 與 current-version row schema mismatch scenarios。
- **可先跳過**：`schema_version` 型別規則、成功儲存版本與future-version行為未被本 change 修改，仍以主 spec 為準。

## MODIFIED Requirements

### Requirement: 以版本上限與現行結構共同判斷是否可載入

系統 SHALL 在 `schema_version` 通過型別與範圍驗證後，將版本標籤相容性與 Project 的實際資料結構相容性分開判斷。缺少版本號、版本號低於目前支援版本 `3`、或版本號等於 `3` 的 Project，只有在完整通過現行 schema 3 結構與 Domain 驗證時才能載入；系統 MUST NOT 因版本號缺少或較舊而跳過任何現行驗證，也 MUST NOT 在載入期間偵測舊格式特徵、猜測欄位、補值或轉換資料結構。高於 `3` 的版本 MUST 在採用任何 Project state 前被拒絕。

#### Scenario: missing — 缺少版本號但符合現行結構

- **WHEN** Project JSON 缺少 `schema_version`，且其餘內容完整通過現行 schema 3 結構與 Domain 驗證
- **THEN** 系統 SHALL 成功載入該 Project
- **AND** 系統 SHALL 將它視為版本標籤缺少的相容檔案，而非需要猜測轉換的舊結構

#### Scenario: older — 較舊版本號但符合現行結構

- **WHEN** Project JSON 的整數 `schema_version` 小於 `3`，且其餘內容完整通過現行 schema 3 結構與 Domain 驗證
- **THEN** 系統 SHALL 成功載入該 Project
- **AND** 系統 SHALL 不因較舊版本號修改或略過其內容驗證

#### Scenario: current — 現行版本正常驗證

- **WHEN** Project JSON 的 `schema_version` 等於 `3`
- **THEN** 系統 SHALL 使用完整的現行 schema 3 結構與 Domain 規則驗證該 Project
- **AND** 只有驗證成功時系統才 SHALL 載入該 Project

#### Scenario: future — 高於支援版本

- **WHEN** Project JSON 的整數 `schema_version` 大於 `3`
- **THEN** 系統 SHALL 拒絕載入該 Project
- **AND** 系統 SHALL 指出檔案版本高於目前支援版本並需要使用較新程式
- **AND** 系統 MUST NOT 嘗試以 schema 3 規則採用該 Project

#### Scenario: old-structure — 版本舊或缺少且無法通過現行格式驗證

- **WHEN** Project JSON 的 `schema_version` 缺少或小於 `3`，且內容無法通過現行 schema 3 結構或 Domain 驗證
- **THEN** 系統 SHALL 拒絕載入該 Project，並回報「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」
- **AND** 系統 SHALL 附上底層結構或 Domain 驗證錯誤
- **AND** 系統 MUST NOT 在載入流程中偵測舊格式特徵、猜測欄位、補建資料或自動執行 schema migration
- **AND** 系統 MUST NOT 提供 legacy Project schema upgrade tool 作為復原路徑

### Requirement: 拒絕時提供可行的下一步並保留目前狀態

系統 SHALL 讓拒絕原因可由使用者辨識：未來版本指向較新程式；missing／older payload 若無法通過現行結構驗證，或 missing／older／current payload 發生 row／table schema mismatch，均回報「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」並附上底層驗證錯誤。載入流程 MUST NOT 藉由特徵偵測宣稱檔案一定是舊格式，也 MUST NOT 提供 legacy Project schema upgrade tool。任一 schema compatibility failure MUST 遵守既有 Open transaction semantics，不得部分採用目標 Project 的 input、result、DXF state或path，也不得改變目前 Project 的dirty state。

#### Scenario: 未來版本拒絕不改變目前 Project

- **WHEN** 使用者嘗試開啟高於支援版本的 Project
- **THEN** 系統 SHALL 顯示需使用較新程式的拒絕資訊
- **AND** 目前已開啟的 Project state 與 dirty state SHALL 保持不變

#### Scenario: 無法以現行格式讀取時不改變目前 Project

- **WHEN** 使用者嘗試開啟 missing／older version、但無法通過現行結構驗證的 Project
- **THEN** 系統 SHALL 顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」及底層驗證錯誤
- **AND** 目前已開啟的 Project state 與dirty state SHALL 保持不變

#### Scenario: current version 的 row schema mismatch 使用相同復原指引

- **WHEN** 使用者嘗試開啟 `schema_version: 3`，但任一 Project row 或 table 無法通過現行 schema contract 的 Project
- **THEN** 系統 SHALL 顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」
- **AND** 系統 SHALL 附上指出 table、row及missing／unsupported field或unsupported table的底層驗證錯誤
- **AND** 目前已開啟的 Project state 與dirty state SHALL 保持不變

