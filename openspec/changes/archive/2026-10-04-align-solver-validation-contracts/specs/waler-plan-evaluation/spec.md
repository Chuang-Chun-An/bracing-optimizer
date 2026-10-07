# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：明確空集合與未提供材料規格的差異。
- **實作前閱讀（P1）**：`../../design.md` 的 resolved material context 決策。
- **需要時再讀（P2）**：主規格其餘 Waler hard rules、allocation 與 scoring；本 delta 不修改評分排序。

## ADDED Requirements

### Requirement: 明確空的可購買料長不得被核心預設值覆蓋

Waler evaluator SHALL 區分「呼叫端未提供可購買料長」與「resolved material context 明確提供空集合」。未提供或材料規格空白時 SHALL 沿用既有預設料長與每種材料 `99` 支的目前政策；明確空集合 SHALL 表示沒有任何 Steel segment 可購買，核心不得再自行補入預設料長。

#### Scenario: 材料規格未填

- **WHEN** Project 未填材料規格，且 application 依既有政策建立 Waler input
- **THEN** 系統 SHALL 使用既有預設可購買料長
- **AND** 每種預設材料數量 SHALL 以 `99` 支參與既有評分與 allocation

#### Scenario: 使用者將某材料數量改為 5

- **WHEN** resolved material context 對某可購買料長提供數量 `5`
- **THEN** Waler evaluation SHALL 以 `5` 支執行既有評分與 allocation
- **AND** SHALL NOT 因數量與預設 `99` 不同而產生警告或改回 `99`
- **AND** 既有庫存不足時的採購警告語意 SHALL 維持不變

#### Scenario: Resolved context 明確沒有可購買料長

- **WHEN** application 傳入明確空的 purchasable-length set
- **AND** plan 含有一段或以上 Steel segment
- **THEN** 每段 Steel SHALL 依既有 issue contract 判為不可購買
- **AND** plan SHALL 為 invalid
- **AND** evaluator SHALL NOT 補入任何預設料長

#### Scenario: 明確空集合的 allocation

- **WHEN** plan 因明確空的 purchasable-length set 而不合法
- **THEN** evaluator SHALL 遵守既有「hard issue 時不執行 allocation 或評分」契約
- **AND** automatic compatibility projection SHALL 沿用既有 invalid-candidate penalty 作為搜尋 fitness
- **AND** candidate score sort key、signature、去重與 tie-break 規則 SHALL 維持不變

#### Scenario: Single Waler 的全部自動候選皆 invalid

- **WHEN** 明確空的 purchasable-length set 使 Single Waler 的全部自動候選皆為 invalid
- **THEN** 每個 invalid candidate SHALL 依既有 invalid-candidate penalty 參與搜尋 fitness 與 deterministic 排序
- **AND** Single Waler SHALL 回報 `no_legal_solution` diagnostics 與空的合法解集合
- **AND** SHALL NOT 將正常的無合法方案結果拋出為 exception

#### Scenario: Global Waler 的任一必要 Waler 沒有合法候選

- **WHEN** Global Waler 執行時，任一必要的 non-RC Waler 因明確空集合而沒有合法 local candidate
- **THEN** Global Waler SHALL 回傳 invalid solution 與可辨識 failed Waler diagnostics
- **AND** SHALL NOT 進入需要該 Waler 合法候選的 Exact DP
- **AND** SHALL NOT 將正常的無合法方案結果拋出為 exception
