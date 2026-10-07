# dxf-result-export Specification

## Purpose

定義支撐配置成果 DXF 的模式、座標語意、可輸出內容與失敗安全，使有來源圖面的 Project 與純手動 Project 都能得到範圍清楚且可驗證的成果檔。

## 閱讀導航

- **必讀**：匯出模式判定、共同的結果範圍與失敗安全，以及「不合法配置在專用警告圖層標示」。
- **條件式閱讀**：使用手動 Project 時閱讀 result-only Requirements；使用來源圖面時閱讀來源支援匯出相容性。
- **可先跳過**：未使用 invalid Support／Waler 結果時，可先跳過 warning 的中文字型與定位細節。

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

### Requirement: 不合法配置在專用警告圖層標示

DXF 匯出 SHALL 允許工程上不合法的 Support／Waler 結果，並在 `SD_WARNING_INVALID_RESULT` warning layer 以有效紅色文字於對應構件附近標示不合法。每個不合法構件 SHALL 恰好有一筆 warning text；文字 SHALL 至少能辨識構件與全部已知不合法原因。合法構件 SHALL NOT 產生此警告；匯出範圍全部合法時 SHALL NOT 建立空的 warning layer。

#### Scenario: 匯出一筆不合法 Support

- **WHEN** 匯出範圍含有不合法 Support 結果
- **THEN** DXF SHALL 在該 Support 附近建立紅色 warning text
- **AND** warning SHALL 位於 `SD_WARNING_INVALID_RESULT` 圖層
- **AND** 文字 SHALL 包含可辨識的不合法原因

#### Scenario: 匯出一筆不合法 Waler

- **WHEN** 匯出範圍含有不合法 Waler 結果
- **THEN** DXF SHALL 在該 Waler 附近建立紅色 warning text
- **AND** warning SHALL 位於與工程幾何分離的 `SD_WARNING_INVALID_RESULT` 圖層

#### Scenario: 不合法配置缺少可顯示原因

- **WHEN** 一筆已 committed 的配置為不合法，但其結果 payload 沒有可顯示的工程違規原因
- **THEN** warning text SHALL 以「未提供不合法原因」明確標示原因資料缺失
- **AND** exporter SHALL NOT 重新推導 Solver 合法性或阻擋該筆結果匯出

#### Scenario: 匯出合法結果

- **WHEN** 匯出範圍內的構件全部合法
- **THEN** DXF SHALL NOT 因本 capability 新增 invalid warning text
- **AND** DXF SHALL NOT 建立 `SD_WARNING_INVALID_RESULT` 圖層

### Requirement: 兩種 DXF 匯出模式使用相同警告契約

Source-backed 與 result-only DXF 匯出 SHALL 使用相同的 committed validity、warning layer、顏色與文字內容契約。合法性正規化 SHALL 沿用現行結果呈現語意：Support plan 的 `valid` 缺失視為 false，且只有 `valid` 為 true、`reason` 為空時才是合法；Waler plan 明確具有 `legality.valid` 時以該值為準，缺失時才 fallback 至 `plan.valid`，兩者皆缺失時視為 false。合法性狀態 SHALL NOT 改變既有可見方案的匯出範圍。Exporter SHALL NOT 重新推導 Solver 合法性。

#### Scenario: Support plan 缺少 valid

- **WHEN** 任一模式匯出一筆缺少 `valid` 欄位的可見 Support plan
- **THEN** DXF SHALL 將該配置視為不合法並建立 warning
- **AND** 該配置成果 SHALL 仍依既有可見範圍匯出

#### Scenario: Support valid 與 reason 不一致

- **WHEN** 任一模式匯出一筆 `valid` 為 true 但 `reason` 非空的可見 Support plan
- **THEN** DXF SHALL 沿用結果呈現語意將該配置視為不合法
- **AND** warning SHALL 包含該 `reason`

#### Scenario: Waler plan 缺少兩種 valid

- **WHEN** 任一模式匯出一筆同時缺少 `legality.valid` 與 `plan.valid` 的可見 Waler plan
- **THEN** DXF SHALL 將該配置視為不合法並建立 warning
- **AND** 該配置成果 SHALL 仍依既有可見範圍匯出

#### Scenario: Waler legality 與 plan valid 矛盾

- **WHEN** 任一模式匯出一筆同時具有 `legality.valid` 與 `plan.valid` 且兩者值互相矛盾的 Waler plan
- **THEN** DXF SHALL 以 `legality.valid` 判定是否建立 warning
- **AND** SHALL NOT 因矛盾而重新執行 evaluator

#### Scenario: Source-backed 模式含不合法結果

- **WHEN** source-backed export 含有不合法結果
- **THEN** warning SHALL 疊加到輸出副本
- **AND** SHALL NOT 修改來源 DXF

#### Scenario: Result-only 模式含不合法結果

- **WHEN** result-only export 含有不合法結果
- **THEN** warning SHALL 與輸出結果幾何一起建立
- **AND** 內容 SHALL 與 source-backed 模式等價

### Requirement: Warning 文字使用可驗證的中文字型與穩定位置

每筆 warning SHALL 使用可顯示繁體中文的 `SD_WARNING_CJK` text style；該 style SHALL 引用新細明體（`PMingLiU`／`mingliu.ttc`）。Warning SHALL 以對應 member 工程線中點為基準、依相同的 deterministic 偏移規則放置。多筆 warning 發生位置衝突時 SHALL 以穩定順序逐筆移開，不得合併或遺漏。字型檔不嵌入 DXF，開檔環境需提供新細明體。

#### Scenario: Warning 包含繁體中文

- **WHEN** warning 內容含有繁體中文構件資訊或不合法原因
- **THEN** warning entity SHALL 使用 `SD_WARNING_CJK` text style
- **AND** 該 style SHALL 引用 `mingliu.ttc`

#### Scenario: 雙路支撐中的兩支 Strut 都不合法

- **WHEN** 同一雙路群組中的兩支實體 Strut 都具有可見的 invalid plan
- **THEN** DXF SHALL 依兩支 Strut 各自的 member identity 與工程線各建立一筆 warning
- **AND** warnings SHALL NOT 因 shared-layout group 而合併
- **AND** 任一支 Strut 的 warning SHALL NOT 遺漏

#### Scenario: 多筆 warning 的候選位置衝突

- **WHEN** 兩筆或以上 warning 的初始候選位置落入既定的碰撞距離
- **THEN** 系統 SHALL 依穩定的 member 排序與固定偏移方向逐筆移開 warning
- **AND** 等價資料重複匯出 SHALL 產生相同位置

#### Scenario: Warning 維持在對應構件附近

- **WHEN** 暫存 DXF 重讀 warning entity
- **THEN** warning insertion point SHALL 在具名 anchor tolerance 內符合該 member 的預期偏移位置
- **AND** 驗證 SHALL NOT 使用散落的匿名數值作為 offset 或 tolerance

#### Scenario: 警告驗證失敗

- **WHEN** 暫存 DXF 重讀後的 warning 圖層、有效顏色、構件 identity、文字內容、數量、位置、entity text style 或 style font reference 未符合預期
- **THEN** 匯出 SHALL 失敗並保留既有目的檔
- **AND** Project input、Solver results、visibility 與 dirty state SHALL 維持不變
