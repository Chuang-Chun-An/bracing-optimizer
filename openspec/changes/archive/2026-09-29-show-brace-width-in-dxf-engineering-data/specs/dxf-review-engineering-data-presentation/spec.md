# Spec Delta

## 閱讀導航

- **必讀**：「斜撐與角撐寬度顯示」Requirement；定義右側工程資料的顯示值、格式與未知值行為。
- **條件式閱讀**：「顯示不得改變工程資料 contract」Requirement；修改 model、Project row、匯出、持久化或 Solver 邊界時必讀。
- **可先跳過**：斜撐與角撐的辨識、候選選擇及修補規格；本 capability 只消費既有可靠寬度，不定義寬度如何產生。

## Purpose

定義 DXF Review 右側工程資料對斜撐與角撐寬度的可見呈現，使使用者可在工程資料區直接檢核可靠尺寸，同時避免把未知寬度顯示成真實工程數值。

## ADDED Requirements

### Requirement: 斜撐與角撐寬度顯示

當使用者在 DXF Review 選取正式斜撐或正式角撐時，系統 SHALL 在右側「工程資料」區顯示「構件寬度（mm）」欄位。若該構件具有有限且大於 `0` 的可靠來源寬度，系統 MUST 使用該既有寬度並固定顯示至小數第 3 位；若寬度缺失、非有限或 `<= 0`，系統 SHALL 顯示「—」，且 MUST NOT 猜測、繼承或顯示為 `0.000`。

此 Requirement 是 Presentation 行為，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 顯示斜撐可靠寬度

- **WHEN** 使用者選取來源寬度為 `350.0` mm 的正式斜撐
- **THEN** 右側工程資料 SHALL 顯示「構件寬度（mm）：350.000」

#### Scenario: 顯示角撐可靠寬度

- **WHEN** 使用者選取來源寬度為 `300.0` mm 的正式角撐
- **THEN** 右側工程資料 SHALL 顯示「構件寬度（mm）：300.000」

#### Scenario: 未知寬度不產生工程數值

- **WHEN** 使用者選取來源寬度缺失、非有限或 `<= 0` 的正式斜撐或角撐
- **THEN** 右側工程資料 SHALL 在「構件寬度（mm）」顯示「—」
- **AND** 系統 MUST NOT 顯示 `0.000`、從其他構件繼承寬度或推定替代值

#### Scenario: 其他構件維持既有工程資料

- **WHEN** 使用者選取非斜撐且非角撐的構件
- **THEN** 本 change SHALL NOT 因該選取而新增「構件寬度（mm）」工程資料列
- **AND** 其既有工程資料顯示 SHALL 維持不變

### Requirement: 顯示不得改變工程資料 contract

寬度顯示 MUST 只讀取 DXF member 已保存的可靠來源寬度。系統 MUST NOT 為此顯示新增或修改 Project row、Project schema、序列化資料、匯出欄位、Solver input、材料規格、辨識結果、構件幾何或角撐修補結果；左側構件清單、DXF 預覽與角撐修補預覽 SHALL 維持既有行為。

#### Scenario: 顯示寬度不回寫資料

- **WHEN** 系統建立或刷新斜撐或角撐的右側工程資料
- **THEN** 顯示前後的 member 寬度、Project row、正式幾何與關聯 SHALL 相同
- **AND** 不得產生新的 persistence 或 Solver 欄位

#### Scenario: 人工修補角撐沒有可靠寬度

- **WHEN** 人工修補角撐的既有來源寬度為未知值
- **THEN** 右側工程資料 SHALL 顯示「—」
- **AND** 系統 MUST NOT 因顯示需求而從 reference template 或鄰近構件取得寬度
