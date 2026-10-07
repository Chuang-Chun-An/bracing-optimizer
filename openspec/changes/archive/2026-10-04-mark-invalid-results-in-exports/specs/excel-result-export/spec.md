# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：合法性欄位與 invalid reason 的兩項 Requirements。
- **實作前閱讀（P1）**：`../../design.md` 的共用 export projection 與 atomic write 決策。
- **需要時再讀（P2）**：既有 result mutation 與 Solver legality specs；本 change 不重新計算工程合法性。

## Purpose

定義 Excel 結果匯出的合法性標示，使合法與不合法的 Support／Waler 配置都可匯出，同時讓現場人員能直接辨識風險與原因。

## ADDED Requirements

### Requirement: 每筆匯出配置包含合法性欄位

Excel 匯出 SHALL 保留既有可匯出結果範圍，並為每筆 Support 或 Waler 配置輸出 `是否合法` 與 `不合法原因` 欄位。工程上不合法的結果 SHALL 仍可匯出，系統不得新增阻擋或確認 Dialog。

#### Scenario: 匯出合法配置

- **WHEN** 使用者匯出一筆合法配置
- **THEN** `是否合法` SHALL 明確標示為合法
- **AND** `不合法原因` SHALL 為空白

#### Scenario: 匯出不合法配置

- **WHEN** 使用者匯出一筆已 committed 的不合法配置
- **THEN** `是否合法` SHALL 明確標示為不合法
- **AND** `不合法原因` SHALL 包含該結果已知的工程違規原因
- **AND** 匯出 SHALL 不要求額外確認

#### Scenario: 不合法配置缺少可顯示原因

- **WHEN** 一筆已 committed 的配置為不合法，但其結果 payload 沒有可顯示的工程違規原因
- **THEN** `是否合法` SHALL 明確標示為不合法
- **AND** `不合法原因` SHALL 明確標示「未提供不合法原因」
- **AND** 系統 SHALL NOT 為此重新執行工程判斷或阻擋匯出

#### Scenario: 同一批同時包含合法與不合法配置

- **WHEN** 匯出範圍同時包含合法與不合法配置
- **THEN** 每筆配置 SHALL 依自己的 committed validity 分別標示

### Requirement: Excel 匯出沿用正式結果合法性

Excel exporter SHALL 使用正式結果模型提供的 validity 與 issues 作為 single source of truth，SHALL NOT 在 exporter 內另建一套工程判斷。合法性正規化 SHALL 沿用現行結果呈現語意：Support plan 的 `valid` 缺失視為 false，且只有 `valid` 為 true、`reason` 為空時才是合法；Waler plan 明確具有 `legality.valid` 時以該值為準，缺失時才 fallback 至 `plan.valid`，兩者皆缺失時視為 false。多個不合法原因 SHALL 以穩定且可閱讀的順序輸出。合法性狀態 SHALL NOT 改變既有可見方案的材料彙總或匯出範圍。

#### Scenario: Support plan 缺少 valid

- **WHEN** 一筆可見 Support plan 缺少 `valid` 欄位
- **THEN** Excel SHALL 將該配置標示為不合法
- **AND** 該配置的材料明細 SHALL 仍依既有可見範圍匯出

#### Scenario: Support valid 與 reason 不一致

- **WHEN** 一筆可見 Support plan 的 `valid` 為 true 但 `reason` 非空
- **THEN** Excel SHALL 沿用結果呈現語意將該配置標示為不合法
- **AND** `不合法原因` SHALL 包含該 `reason`

#### Scenario: Waler plan 缺少兩種 valid

- **WHEN** 一筆可見 Waler plan 同時缺少 `legality.valid` 與 `plan.valid`
- **THEN** Excel SHALL 將該配置標示為不合法
- **AND** 該配置 SHALL 仍依既有可見範圍匯出

#### Scenario: Waler legality 與 plan valid 矛盾

- **WHEN** 一筆可見 Waler plan 同時具有 `legality.valid` 與 `plan.valid`，且兩者值互相矛盾
- **THEN** Excel SHALL 以 `legality.valid` 判定是否合法
- **AND** SHALL NOT 因矛盾而重新執行 evaluator

#### Scenario: 結果含有多個工程問題

- **WHEN** 一筆結果的正式 legality contract 含有多個 issues
- **THEN** `不合法原因` SHALL 保留全部可顯示 issues
- **AND** 等價資料重複匯出 SHALL 產生相同順序

#### Scenario: 寫檔失敗

- **WHEN** Excel 輸出在寫入期間失敗
- **THEN** exporter SHALL 沿用既有 atomic failure semantics
- **AND** SHALL NOT 留下被誤認為成功的部分活頁簿

#### Scenario: 同一配置具有多筆材料明細

- **WHEN** 同一 Support 或 Waler 配置輸出多筆材料明細
- **THEN** 每筆明細的 `是否合法` 與 `不合法原因` SHALL 一致對應該配置
