# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：invalid warning layer 與兩種 DXF 模式一致性的 Requirements。
- **實作前閱讀（P1）**：`../../design.md` 的 warning projection、圖層設定與定位決策。
- **需要時再讀（P2）**：主規格其餘 source-backed／result-only 與 atomic export 契約；本 delta 不改變它們。

## ADDED Requirements

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
