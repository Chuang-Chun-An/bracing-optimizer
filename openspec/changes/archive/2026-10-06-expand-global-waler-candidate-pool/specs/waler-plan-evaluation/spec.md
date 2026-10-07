# Spec Delta

## 閱讀導航

- **必讀**：「既有分數與排序相容」中的 Global output-retention 例外，以及「搜尋政策與評估分離」。
- **條件式閱讀**：修改 automatic compatibility projector、candidate merge 或 evaluator diagnostics 時閱讀兩個 Requirements 的全部 scenarios。
- **可先跳過**：本 delta 不修改 Waler 總長、joint clearance、purchasable length、allocation、issue code、人工編輯或 local score formula。

## 既有規則來源確認

本 delta 中「Waler adjustment block」與 `required_length - 200 <= steel_length <= required_length` 的文字，來自已封存的 change `openspec/changes/archive/2026-10-01-unify-waler-plan-evaluation/`。該 change 已將 `waler-plan-evaluation` 同步為主規格；現行來源是 `openspec/specs/waler-plan-evaluation/spec.md` 的「Waler 總長使用 200 mm 閉區間且不使用 adjustment block」與「既有分數與排序相容」。因此本 change 是以已成立主規格為基線補充 Global output-retention 例外，不與未封存 change 競爭同一條 Requirement，也不調整該工程規則。

## MODIFIED Requirements

### Requirement: 既有分數與排序相容
對在新總長規則下仍合法的相同 plan，共用評估 SHALL 使用現行 local score components、運算順序、數值型別與權重，並使 local score 及每個 component 與變更前完全相等；驗證 MUST 使用 exact equality，不得使用浮點容差。自動搜尋對 invalid candidate 的既有 penalty、完整 solution 去重與 tie-break SHALL 維持不變。因移除 Waler adjustment block 或套用 200 mm 總長閉區間而改變合法性的 candidate，Top N 與整體排序 MAY 隨確認後的工程規則改變，但 GA stage、population、seed、repair 與 tie-break policy MUST 不變。

`global-waler-candidate-pool` capability 明確核准的 Global output-retention 變更 SHALL 視為搜尋輸出政策，而不是 evaluator 行為：Single Waler candidate count MUST 維持既有 Top 5；Global Waler MAY 保留超過 5 個候選，但每個候選的合法性、score components、local score 及相同候選集合的 deterministic ordering MUST 仍符合本 Requirement。

#### Scenario: 合法 plan 評分
- **WHEN** 一個合法 plan 被共用評估
- **THEN** score MUST 仍由現行 purchase count、material ratio penalty、under-4000 segment count、distinct stock groups、length variation 與 joint count components 組成
- **AND** 每個既有 component 的權重 MUST 不變
- **AND** local score 與每個 component MUST 以 exact equality 與修改前結果完全相等，不得套用 rounding、近似比較或浮點容差

#### Scenario: 自動候選排序
- **WHEN** 相同候選集合在新總長規則下的合法性未改變，且以相同 config、庫存與 random seed 進入自動 Solver
- **THEN** 每個候選 score 與現有 deterministic ordering MUST 不變
- **AND** 合法候選的 score 與各 component MUST 以 exact equality 驗證

#### Scenario: Global output retention 擴大
- **WHEN** Global Waler 使用核准的專用候選保留政策
- **THEN** Global output candidate count MAY 大於 5
- **AND** 此變更 MUST NOT 改變任一候選的合法性、score components、local score 或既有 tie-break
- **AND** Single Waler SHALL 仍只輸出既有 Top 5

#### Scenario: 新總長規則改變候選合法性
- **WHEN** 候選原本依 Waler adjustment block 合法，但不符合 `required_length - 200 <= steel_length <= required_length`
- **THEN** 候選 MUST 依新規則成為 invalid
- **AND** Solver 結果 MAY 因合法候選集合改變而不同
- **AND** 系統 MUST NOT 調整 GA stage、seed、population 或其他搜尋預算補償

#### Scenario: Invalid candidate 相容投影
- **WHEN** 共用核心評估回報 invalid 自動候選
- **THEN** 自動搜尋輸出 MUST 保留既有 invalid-candidate penalty 語意
- **AND** 該相容 penalty MUST NOT 被當成另一套工程合法性或合法 plan 的 local score 公式

### Requirement: 搜尋政策與評估分離
共用 plan 評估 SHALL 只評估已給定的 segments／joints，不得改變或承擔 GA 候選生成、repair、stage escalation、random seed、population、候選輸出 retention、merge、停止條件或 tie-break 政策。Single／Global retention 差異 MUST 由 Solver search／Application contract 明確決定，不得由 evaluator、人工編輯流程或 Presentation 推導。

#### Scenario: Solver 執行既有搜尋流程
- **WHEN** 自動 Waler Solver 使用共用評估執行搜尋
- **THEN** GA stages、random seeds、population、repair 與停止條件 MUST 與變更前相同
- **AND** 只有 `global-waler-candidate-pool` 明確定義的 Global output retention MAY 改變對外 candidate count
- **AND** 共用評估 MUST NOT 產生額外候選、截斷候選或修改輸入候選

#### Scenario: Repair 只查詢 hard-rule 可行性
- **WHEN** GA repair 只需要判斷暫存 candidate 是否存在任一 hard issue
- **THEN** repair MAY 在第一個 hard issue 後停止該次內部可行性探測，且 MUST NOT materialize 未被使用的完整 issue list 或顯示訊息
- **AND** 該布林結果 MUST 與使用相同 hard-rule traversal 完整收集 issues 後的「issue list 是否為空」完全相同
- **AND** 正式 `evaluate_waler_plan()` 仍 MUST 收集並回傳全部 hard issues，不得套用 repair 的 short-circuit projection
- **AND** repair steps、輸出 chromosome、stage、seed、score 與排序 MUST 維持不變

#### Scenario: 人工 plan 未經自動搜尋修補
- **WHEN** 使用者提交人工 segments
- **THEN** 系統 MUST 直接評估該 plan
- **AND** MUST NOT 套用 GA repair、Global retention profile 或搜尋 heuristic 使人工 plan 自動變形
