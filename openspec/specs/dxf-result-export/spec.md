# dxf-result-export Specification

## Purpose

定義支撐配置成果 DXF 的模式、座標語意、可輸出內容與失敗安全，使有來源圖面的 Project 與純手動 Project 都能得到範圍清楚且可驗證的成果檔。

## Requirements

### Requirement: 匯出模式判定

系統 SHALL 只依 `dxf_import_state` 欄位是否存在且其值是否為 `None` 判定模式，不得依 `dxf_workflow_status` 判定。欄位不存在或值為 `None` 的手動 Project SHALL 判定為 `result-only export`；任何已存在且非 `None` 的值均 SHALL 進入 `source-backed export` 座標解析，其中空 Mapping `{}` 或其他不完整、不合法的 state MUST 回報座標錯誤。系統 MUST NOT 將存在但不完整或不合法的 `dxf_import_state` 靜默降級為 result-only。

#### Scenario: 手動 Project 使用 result-only 模式
- **WHEN** 使用者從完全沒有 `dxf_import_state` 的 Project 匯出目前可見的 Solver 結果
- **THEN** 系統選擇 `result-only export`

#### Scenario: 合法來源狀態使用 source-backed 模式
- **WHEN** Project 具有可用 `dxf_import_state` 與合法 Project → WCS 座標資訊
- **THEN** 系統選擇 `source-backed export`

#### Scenario: 不完整來源狀態不使用 identity fallback
- **WHEN** Project 具有 `dxf_import_state` 但缺少或包含不合法的 Project → WCS 座標資訊
- **THEN** 系統拒絕匯出並顯示座標資訊錯誤
- **THEN** 系統不改以 result-only 模式輸出

#### Scenario: 空 Mapping 視為存在但不完整
- **WHEN** Project 的 `dxf_import_state` 明確為空 Mapping `{}`
- **THEN** 系統將該 state 視為存在並嘗試 source-backed 座標解析
- **THEN** 系統回報缺少 Project → WCS 座標資訊且不走 result-only

#### Scenario: REVIEW 不改變模式判定
- **WHEN** Project 的 `dxf_workflow_status` 為 `REVIEW` 且 `dxf_import_state` 存在
- **THEN** 座標資訊完整時系統選擇 source-backed export
- **THEN** 座標資訊不完整時系統回報座標錯誤且不走 result-only

### Requirement: 輸出前模式提示

系統 SHALL 在正式寫入成果檔之前，向使用者清楚標示本次匯出是 `result-only export` 或 `source-backed export`。Result-only 提示 MUST 說明成果檔不包含來源背景與 Project geometry；source-backed 提示 MUST 表示沿用來源支援的既有輸出內容。

#### Scenario: Result-only 模式在寫檔前可辨識
- **WHEN** 手動 Project 已進入成果 DXF 匯出流程且尚未正式寫入目的檔
- **THEN** 使用者可從匯出介面辨識本次為 result-only 模式
- **THEN** 介面說明成果檔不含來源背景與 Project geometry

#### Scenario: Source-backed 模式在寫檔前可辨識
- **WHEN** 有來源 DXF 的 Project 已進入成果 DXF 匯出流程且尚未正式寫入目的檔
- **THEN** 使用者可從匯出介面辨識本次為 source-backed 模式

### Requirement: Result-only 使用 Project 圖面座標

在 result-only 模式中，系統 SHALL 將目前 Project 的 X／Y 座標直接視為 WCS／圖面座標，並以 identity transform 放置所有成果實體。系統 MUST NOT 因缺少來源圖面而平移、旋轉、縮放或猜測座標原點。

#### Scenario: 水平構件維持原座標
- **WHEN** 手動 Project 的可見結果對應到起點 `(1000, 2000)`、終點 `(4000, 2000)` 的構件
- **THEN** 匯出的成果實體以相同 WCS 端點作為配置基準

#### Scenario: 斜向構件不套用推測轉換
- **WHEN** 手動 Project 的可見結果對應到任意合法斜向構件
- **THEN** 匯出結果保留 Project 座標的方向與長度
- **THEN** 系統不加入任何來源座標 offset、rotation 或 scale

### Requirement: Result-only DXF 內容

Result-only DXF SHALL 只包含目前可見 Solver 結果所需的結果圖層、結果尺寸、結果標註，以及結果實際需要的 `SUPPORT_JACK` block definition／reference。只有至少一個可見 Waler 結果時才 SHALL 建立 `SD_RESULT_WALER`；只有至少一個可見 Support 結果時才 SHALL 建立 `SD_RESULT_SUPPORT`。Result-only DXF MUST NOT 建立沒有對應結果的 `SD_RESULT_*` 圖層，MUST NOT 包含任何來源背景實體，且 MUST NOT 建立 `SD_PROJECT_WALER`、`SD_PROJECT_STRUT`、`SD_PROJECT_BRACE` 圖層或其 Project geometry 實體。

#### Scenario: Result-only 檔案只有結果內容
- **WHEN** 手動 Project 成功匯出同時包含圍令與支撐的可見方案
- **THEN** 成果檔包含對應的 `SD_RESULT_WALER` 與 `SD_RESULT_SUPPORT` 結果實體
- **THEN** 成果檔不包含背景實體或 `SD_PROJECT_WALER`、`SD_PROJECT_STRUT`、`SD_PROJECT_BRACE` 圖層

#### Scenario: Result-only 只有 Waler 結果
- **WHEN** result-only 匯出只有 Waler 結果而沒有 Support 結果
- **THEN** 成果檔建立 `SD_RESULT_WALER` 且不建立 `SD_RESULT_SUPPORT`

#### Scenario: Result-only 只有 Support 結果
- **WHEN** result-only 匯出只有 Support 結果而沒有 Waler 結果
- **THEN** 成果檔建立 `SD_RESULT_SUPPORT` 且不建立 `SD_RESULT_WALER`

#### Scenario: 沒有千斤頂時不需要結果圖塊
- **WHEN** result-only 匯出的所有可見結果都不含 jack piece
- **THEN** 成果檔不需要建立 `SUPPORT_JACK` block definition 或 reference

#### Scenario: 有千斤頂時包含必要結果圖塊
- **WHEN** result-only 匯出的可見支撐結果含 jack piece
- **THEN** 成果檔包含合法的 `SUPPORT_JACK` block definition 與位於 `SD_RESULT_SUPPORT` 的 reference

#### Scenario: Result-only 完成摘要說明定位責任
- **WHEN** result-only DXF 成功建立
- **THEN** 完成摘要說明檔案使用 Project 座標輸出且未對齊任何來源圖面
- **THEN** 完成摘要提醒合併至其他圖面時需由使用者自行定位
- **THEN** 完成摘要不顯示背景或 Project geometry 計數

### Requirement: 來源支援匯出相容性

Source-backed export SHALL 保持既有行為：使用已保存的 Project → WCS metadata，輸出目前 Project 的 Waler／Strut／Brace geometry，並在可用時重建來源背景。新增 result-only 模式 MUST NOT 改變 source-backed 成果的座標、既有圖層建立行為、背景、Project geometry、結果符號或驗證規則。

#### Scenario: 既有 local 座標來源維持轉換
- **WHEN** 具有合法 local origin 的 source-backed Project 匯出成果 DXF
- **THEN** Project geometry 與 Solver 結果仍依既有 Project → WCS transform 放置

#### Scenario: 來源背景與 Project geometry 維持輸出
- **WHEN** source-backed Project 具有可用背景資料並成功匯出
- **THEN** 成果檔仍包含既有背景內容與 `SD_PROJECT_WALER`、`SD_PROJECT_STRUT`、`SD_PROJECT_BRACE` 中適用的 Project geometry

### Requirement: 共同的結果範圍與失敗安全

兩種模式 SHALL 只匯出目前可見且每個構件唯一的 Solver 方案，並沿用 R2018、毫米單位、成果長度驗證、磁碟重讀、audit 與原子替換規則。匯出失敗或使用者取消時，系統 MUST preserve 既有目的檔與 Project state，且 MUST NOT 改變 dirty state。

#### Scenario: 同一構件有多個可見方案
- **WHEN** 任一模式下同一構件同時有多個可見方案
- **THEN** 系統拒絕匯出並要求使用者只保留一個可見方案

#### Scenario: Result-only 驗證失敗
- **WHEN** result-only 暫存檔未通過結構、座標、成果數量、圖層、block 或 audit 驗證
- **THEN** 系統不建立或覆寫正式目的檔
- **THEN** Project input、Solver results、visibility 與 dirty state 維持不變

#### Scenario: 使用者取消任一模式匯出
- **WHEN** 使用者在選擇目的檔時取消
- **THEN** 系統不寫入成果檔
- **THEN** Project state 維持不變
