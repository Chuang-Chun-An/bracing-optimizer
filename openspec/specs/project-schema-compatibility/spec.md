# Project Schema Compatibility Specification

## 閱讀導航

- **必讀**：Requirement「schema_version 必須是有效整數」、「以版本上限與現行結構共同判斷是否可載入」，以及 missing、older、current、future、old-structure 五個相容 Scenario。
- **實作儲存時必讀**：Requirement「成功儲存一律寫入現行版本」。
- **處理錯誤與 UI 時條件式閱讀**：Requirement「拒絕時提供可行的下一步並保留目前狀態」。
- **可先跳過**：DXF lifecycle、Solver、案例 JSON 與其他子系統版本規格；它們不屬於本 capability。

## Purpose

本 capability 定義 Project JSON 在版本標籤與資料結構不同步時的相容邊界，使可安全讀取的檔案能開啟，未知未來格式與無法通過現行格式驗證的內容則被明確拒絕。

## Requirements

### Requirement: schema_version 必須是有效整數

Project JSON 的 `schema_version` 欄位不存在時，系統 SHALL 將其分類為 missing。欄位存在時，系統 SHALL 只接受大於等於 `1` 的 JSON 整數，且 MUST 明確排除布林值；字串、浮點數、`null`、`true`、`false`、`0` 與負整數一律是格式錯誤，系統 MUST 在版本分類、結構驗證及採用任何 Project state 前拒絕載入。`schema_version: null` MUST NOT 被視為 missing。

#### Scenario: 非正常 schema_version 一律拒絕

- **WHEN** Project JSON 存在 `schema_version`，且其值為 `"3"`、`3.0`、`true`、`false`、`null`、`0` 或 `-1` 中任一值
- **THEN** 系統 SHALL 以 `schema_version` 格式錯誤拒絕載入
- **AND** 系統 MUST NOT 將該值轉型、視為 missing、進入版本分類或採用任何 Project state

#### Scenario: 只有欄位不存在才是 missing

- **WHEN** Project JSON 完全不存在 `schema_version` 欄位
- **THEN** 系統 SHALL 將其分類為 missing 並繼續執行現行結構驗證

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

### Requirement: 成功儲存一律寫入現行版本

系統 SHALL 對每次成功的新存檔、另存新檔與再次儲存輸出 `schema_version: 3`。從缺少或較舊版本號的相容檔案載入後，只有在使用者實際執行且成功完成儲存時，系統才 SHALL 將輸出改寫為 schema 3；僅開啟或關閉 Project MUST NOT 改寫來源檔。成功儲存後的輸出 SHALL 是通過現行 schema 3 驗證的 Project。

#### Scenario: 相容舊標籤檔案再次儲存

- **WHEN** 使用者開啟缺少版本號或版本號小於 `3`、但結構符合現行 schema 的 Project，之後成功儲存
- **THEN** 儲存輸出的 `schema_version` SHALL 等於 `3`
- **AND** 輸出 SHALL 通過完整的現行 schema 3 驗證

#### Scenario: 僅開啟或關閉而未儲存

- **WHEN** 系統成功載入缺少版本號或版本號小於 `3` 的相容 Project，且使用者只開啟或關閉而未實際執行成功儲存
- **THEN** 系統 MUST NOT 覆寫來源檔案或將其 `schema_version` 改寫為 `3`

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
