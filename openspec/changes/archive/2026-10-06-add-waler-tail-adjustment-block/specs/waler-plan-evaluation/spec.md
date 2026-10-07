# Spec Delta

## 閱讀導航

### 必讀

- 「圍令以單一尾端 adjustment block 與 Gap 完成需求長度」：定義尺寸、位置、Gap 等號邊界、deterministic 選擇與 failure semantics。
- 「既有分數與排序相容」：定義 adjustment 不進入 Steel allocation／比例／local score，並保護搜尋政策。

### 條件式閱讀

- 修改人工編輯、結果顯示或匯出時，讀第一個 Requirement 的「人工重算」「正式 pieces 順序」「既有結果重新計算」scenarios。
- 修改 Global Waler retention 相關路徑時，以已封存並同步至 main spec 的 Single Top 5／Global expanded retention 契約為基線；本 delta 不撤銷或重新定義該契約。

### 可先跳過

- 「明確空的可購買料長」「joint clearance」「具名問題識別」等未列入本 delta 的既有 Requirements 維持不變。
- Support Jack／Shim placement、DXF recognition、RC Waler exclusion、Project schema 與 result adoption 可先跳過；本 change 不修改那些契約。

## MODIFIED Requirements

### Requirement: 圍令以單一尾端 adjustment block 與 Gap 完成需求長度

Waler 的 Engineering Hard Constraint SHALL 允許每個 plan 使用零或一塊尾端 adjustment block；非零合法尺寸 MUST 恰為 `100 mm`、`150 mm`、`200 mm` 或 `300 mm`，`0` SHALL 表示沒有 adjustment block。正式完成長度 MUST 滿足：

```text
steel_length + tail_adjustment + gap = required_length
0 <= gap <= 150 mm
```

上下界均包含等號。Adjustment block MUST 位於全部 Steel pieces 之後、Gap 之前，不得位於兩段 Steel 之間，不得形成 Waler joint，且每個 plan MUST NOT 產生兩塊以上 adjustment blocks。正式 result MUST 將解析出的尺寸寫入 `tail_adjustment`；非零時 `pieces` MUST 在所有 `("steel", length)` 後附加恰好一筆既有相容格式 `("shim", tail_adjustment)`，為零時 MUST NOT 附加該 piece。

令 `shortfall = required_length - steel_length`。若 `0 <= shortfall <= 150 mm`，系統 SHALL 不使用 adjustment block，並令 `gap = shortfall`。只有 `shortfall > 150 mm` 時，系統才 SHALL 從合法非零尺寸中選擇「能使 `0 <= gap <= 150 mm` 成立的最小 adjustment block」，再以完成長度等式推導 Gap。Automatic Solver 與人工重算 MUST 使用同一選擇結果。若 `shortfall > 450 mm` 或不存在合法尾端組合，plan MUST 為 invalid，且共用 evaluator MUST 產生可辨識的具名 issue；不得放寬 Gap、產生任意尺寸 adjustment、加入第二塊 adjustment 或修改 Steel segments 來掩蓋該問題。

Adjustment block 不是 Steel segment，也不是 Support Shim placement。它 MUST NOT 參與 Waler Steel 的 purchasable-length validation、joint positions、exact-length inventory allocation、Short／Mid／Long／Out 分類或 Steel material ratio。

#### Scenario: 16450 mm 圍令以尾端調整塊完成

- **WHEN** `required_length = 16450 mm` 且合法 Steel segments 的總長為 `16000 mm`
- **THEN** plan SHALL 使用一塊 `300 mm` adjustment block
- **AND** Gap SHALL 為 `150 mm`
- **AND** plan MUST NOT 因總長限制而 invalid

#### Scenario: Adjustment block 固定在最後

- **WHEN** 合法 Steel segments 為 `[8000, 8000]`，解析結果需要 `300 mm` adjustment block 與 `150 mm` Gap
- **THEN** 正式 pieces SHALL 依序為兩段 Steel、單一 `300 mm` adjustment block
- **AND** Gap SHALL 位於所有 pieces 之後
- **AND** adjustment block MUST NOT 出現在兩段 Steel 之間或產生新的 joint

#### Scenario: 多個合法尾端組合採能不用就不用與最小調整塊

- **WHEN** 系統解析下列 `required_length`／`steel_length` 組合
- **THEN** 尾端結果 MUST 如下：

| required_length | steel_length | tail_adjustment | Gap |
| --- | --- | --- | --- |
| `12100 mm` | `12000 mm` | `0 mm` | `100 mm` |
| `12180 mm` | `12000 mm` | `100 mm` | `80 mm` |
| `12250 mm` | `12000 mm` | `100 mm` | `150 mm` |
| `16450 mm` | `16000 mm` | `300 mm` | `150 mm` |

- **AND** `12100／12000` MUST NOT 為了縮小 Gap 而使用 adjustment block
- **AND** 其他三個短差大於 `150 mm` 的組合 MUST 使用能使 Gap 合法的最小 adjustment block

#### Scenario: 鋼材總長位於下界

- **WHEN** `required_length = 11950 mm` 且 `steel_length = 11500 mm`
- **THEN** 系統 SHALL 解析為 `300 mm` adjustment block 與 `150 mm` Gap
- **AND** plan MUST NOT 因短差等於最大可完成值 `450 mm` 或 Gap 等於上限 `150 mm` 而 invalid

#### Scenario: 鋼材總長位於上界

- **WHEN** `required_length = 12000 mm` 且 `steel_length = 12000 mm`
- **THEN** plan MUST NOT 因尾端完成限制而 invalid
- **AND** `tail_adjustment` 與 Gap SHALL 均為 `0`
- **AND** 正式 pieces MUST NOT 產生 adjustment block

#### Scenario: 鋼材總長低於下界

- **WHEN** `required_length - steel_length > 450 mm`
- **THEN** 即使使用最大 `300 mm` adjustment block 與最大 `150 mm` Gap，plan 仍 MUST 為 invalid
- **AND** core MUST 產生「鋼材總長不足」具名 issue，其 facts 至少包含 required length、最大可完成短差、合法 adjustment set、max Gap 與 actual Steel length
- **AND** manual legality 顯示 MUST 使用「鋼材總長不足」

#### Scenario: 鋼材總長高於上界

- **WHEN** `required_length = 12000 mm` 且 `steel_length > 12000 mm`
- **THEN** plan MUST 為 invalid
- **AND** core MUST 產生「鋼材總長太長」具名 issue，其 facts 至少包含 required length 與 actual Steel length
- **AND** manual legality 顯示 MUST 使用「鋼材總長太長」

#### Scenario: 沒有合法尾端組合

- **WHEN** `required_length = 16451 mm` 且 `steel_length = 16000 mm`
- **THEN** 系統 MUST NOT 產生 `301 mm` adjustment block 或 `151 mm` Gap
- **AND** plan MUST 為 invalid
- **AND** evaluator MUST 回傳可由 code 與 facts 辨識的尾端完成 issue

#### Scenario: 鋼材總長超過需求長度

- **WHEN** `steel_length > required_length`
- **THEN** plan MUST 為 invalid
- **AND** 系統 MUST NOT 以負 adjustment 或負 Gap 使 plan 合法

#### Scenario: Automatic 與 manual 使用相同尾端解析

- **WHEN** Automatic Solver 與人工重算提供相同的 `required_length`、Steel segments 及相同 resolved evaluation context
- **THEN** 兩條路徑 MUST 得到相同的 `tail_adjustment`、Gap、pieces 順序、合法性與具名 issues
- **AND** 人工流程 MUST NOT 要求使用者把 adjustment block 當成可編輯 Steel segment 插入中間

#### Scenario: 正式結果只產生一塊合法調整塊

- **WHEN** 任一 Automatic 或 manual plan 重算完成
- **THEN** 非零 `tail_adjustment` MUST 為 `100`、`150`、`200` 或 `300 mm`
- **AND** 正式 pieces MUST 恰有一塊同尺寸 adjustment block 且位於最後一段 Steel 之後
- **AND** `tail_adjustment = 0` 時正式 pieces MUST NOT 含 adjustment block

#### Scenario: 既有 Waler adjustment result 重新計算

- **WHEN** 既有專案載入含非零 Waler `tail_adjustment` 或 Waler adjustment piece 的舊結果
- **THEN** 載入本身 MUST NOT 觸發 persistence migration 或靜默改寫結果
- **AND** 下一次完整 Solver 或人工重算 MUST 依目前的合法尺寸、尾端位置、Gap 與 deterministic 選擇規則重新推導尾端組合
- **AND** 新結果 MUST NOT 因舊 payload 的 adjustment 值而繞過目前規則

### Requirement: 既有分數與排序相容

對 Steel segments／joints、resolved material context 與既有 score inputs 相同，且依新尾端完成規則仍合法的 plan，共用評估 SHALL 使用現行 local score components、運算順序、數值型別與權重；adjustment block 與 Gap MUST NOT 新增 score component，也 MUST NOT 計入 Steel allocation、Short／Mid／Long／Out counts、material ratio、under-4000 count、stock groups、length variation 或 joint count。驗證 MUST 對未受合法性變更影響的既有 components 使用 exact equality，不得使用浮點容差。

自動搜尋對 invalid candidate 的既有 penalty、候選去重與 tie-break SHALL 維持不變。因新增 adjustment block 而使候選由 invalid 變為 valid，或使正式 `tail_adjustment`／Gap projection 改變時，Top N 與整體排序 MAY 隨合法候選集合改變；GA stage、population／candidate count、seed、repair、merge、retention profile、停止條件與 Global Exact DP objective MUST 不變。

已封存 `global-waler-candidate-pool` capability 所建立的 Global output-retention 契約 SHALL 繼續成立：Single Waler candidate count MUST 維持既有 Top 5；Global Waler MAY 保留超過 5 個候選，但每個候選的尾端解析、合法性、score components、local score 及相同候選集合的 deterministic ordering MUST 仍符合本 Requirement。Single／Global retention 差異 MUST 由 Solver search／Application contract 決定，不得由 evaluator、人工編輯流程或 Presentation 推導。

#### Scenario: 合法 plan 評分

- **WHEN** 一個依新尾端完成規則合法、含或不含 adjustment block 的 plan 被共用評估
- **THEN** score MUST 仍由現行 purchase count、Steel material ratio penalty、under-4000 Steel segment count、distinct Steel stock groups、Steel length variation 與 Steel joint count components 組成
- **AND** 每個既有 component 的權重 MUST 不變
- **AND** adjustment block 與 Gap MUST NOT 產生額外 component、材料分類或庫存 assignment

#### Scenario: 相同 Steel plan 的既有 components 保持一致

- **WHEN** 變更前合法且變更後仍合法的 plan 具有相同 Steel segments、joints、材料 context 與 ratio targets
- **THEN** 每個既有 score component 與 local score MUST 與變更前以 exact equality 完全相等
- **AND** 尾端 adjustment／Gap projection 的改變 MUST NOT 回頭改寫 Steel score components

#### Scenario: 自動候選排序

- **WHEN** 相同候選集合在新尾端規則下的合法性未改變，且以相同 config、庫存與 random seed 進入自動 Solver
- **THEN** 每個候選的尾端組合 MUST 可重現，候選 score 與現有 deterministic ordering MUST 不變
- **AND** 合法候選的 score 與各 component MUST 以 exact equality 驗證
- **AND** adjustment block MUST NOT 作為隱藏的新 scoring weight

#### Scenario: Global output retention 擴大

- **WHEN** Global Waler 使用核准的專用候選保留政策
- **THEN** Global output candidate count MAY 大於 5
- **AND** 此變更 MUST NOT 改變任一候選的尾端解析、合法性、score components、local score 或既有 tie-break
- **AND** Single Waler SHALL 仍只輸出既有 Top 5

#### Scenario: 新總長規則改變候選合法性

- **WHEN** 候選原本因 `required_length - steel_length > 200 mm` 而 invalid，但可由一塊合法 adjustment block 與 `0～150 mm` Gap 完成
- **THEN** 候選 MUST 依新規則成為 valid
- **AND** Solver 結果 MAY 因合法候選集合改變而不同
- **AND** 系統 MUST NOT 調整 GA stage、seed、candidate count、retention profile 或其他搜尋參數補償

#### Scenario: Invalid candidate 相容投影

- **WHEN** 共用核心評估回報 invalid 自動候選
- **THEN** 自動搜尋輸出 MUST 保留既有 invalid-candidate penalty 語意
- **AND** 該相容 penalty MUST NOT 被當成另一套工程合法性或合法 plan 的 local score 公式

## RENAMED Requirements

- FROM: `### Requirement: Waler 總長使用 200 mm 閉區間且不使用 adjustment block`
- TO: `### Requirement: 圍令以單一尾端 adjustment block 與 Gap 完成需求長度`
