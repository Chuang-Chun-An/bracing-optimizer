# Waler Plan Evaluation Specification

## 閱讀導航

### 必讀

- 「共用核心評估」：本 change 的主要契約，定義自動與人工路徑不得各自維護另一套工程判斷。
- 「既有路徑差異必須先報告並決策」：定義 Group 2 前的比較、A／B 分類與停線 gate。
- 「統一合法性與 allocation 語意」：定義先完整收集 hard issues，且 invalid plan 不進入 allocation／ratio／local score 的共同處理。
- 「Waler 總長使用 200 mm 閉區間且不使用 adjustment block」：這是使用者確認的 Engineering Hard Constraint 變更。
- 「既有分數與排序相容」：保護 score formula、automatic invalid penalty 與搜尋政策，並列出新總長規則造成的必要結果差異。
- 「具名問題識別與完整顯示」：定義 issue code 是機器識別依據，人工畫面完整列出每筆違規。

### 條件式閱讀

- 修改 GA、candidate merge 或 Global Waler 時，再讀「搜尋政策與評估分離」。
- 只調整人工編輯 UI layout 時，本 spec 可作為輸出契約參考，不需改動 requirement。

### 可先跳過

- Support plan evaluation、DXF recognition、Project persistence 與 RC eligibility 均不屬於本 capability。

## Purpose

定義 Waler 自動 Solver 與人工方案編輯對同一組 segments／joints 使用一致的合法性、材料 allocation、local score 與結構化問題識別，同時保護既有顯示、排序與搜尋政策相容性。

## Requirements

### Requirement: 自動與人工流程使用共用核心評估
系統 SHALL 以同一個核心評估契約處理自動 Waler 候選與人工編輯 Waler plan 的 segment legality、joint clearance、purchasable length、allocation 及 local score；任何一條流程 MUST NOT 另行維護可產生不同工程結論或分數的平行公式。

#### Scenario: 相同合法 plan 經兩條路徑評估
- **WHEN** 自動 Solver 與人工編輯提供相同的 segments、joints、Waler 長度、forbidden points、材料規格、可購買料長、庫存 Qty、空白規格 fallback 及比例目標
- **THEN** 兩條路徑 MUST 得到相同的核心合法性、allocation、local score components 與 local score

#### Scenario: 相同不合法 plan 經兩條路徑評估
- **WHEN** 自動 Solver 與人工編輯提供相同但違反工程限制的 segments／joints 與相同評估 context
- **THEN** 兩條路徑 MUST 得到相同的核心 issue codes 與對應結構化 issue facts
- **AND** 兩條路徑的 allocation、ratio analysis、score components 與 local score MUST 同樣標示為 unavailable

### Requirement: 既有路徑差異必須先報告並決策
在建立共用 evaluator 前，系統 SHALL 以相同 resolved context 對自動 Solver 與人工編輯執行 characterization comparison。只有訊息文字、順序或欄位名稱不同的結果 SHALL 分為 A 類顯示差異並由各自 compatibility projector 保留；合法性判斷、allocation、score components 或 issue 種類不同的結果 MUST 分為 B 類工程差異。任何 B 類差異 MUST 在完成差異報告後阻止 Group 2 實作，直到使用者明確確認統一規則。

#### Scenario: 只有顯示格式不同
- **WHEN** 相同 resolved context 的兩條既有路徑只有訊息文字、訊息順序或欄位名稱不同
- **THEN** 差異報告 SHALL 將該項分類為 A 類
- **AND** 各自 compatibility projector SHALL 保留原格式
- **AND** Group 2 實作 MUST NOT 只因該 A 類差異而被阻止

#### Scenario: 核心判斷不同
- **WHEN** 相同 resolved context 的兩條既有路徑在合法性、allocation、任一 score component、local score 或 issue 種類上不同
- **THEN** 差異報告 MUST 將每項差異分類為 B 類
- **AND** 每項 MUST 記錄差異名稱、具體 segments／joints／config／庫存輸入、自動結果、人工結果、來源程式位置、建議規則與理由，以及採用後會改變的既有行為
- **AND** Group 2 實作 MUST 停止，直到使用者確認統一規則

#### Scenario: 尚未取得統一規則決策
- **WHEN** B 類差異已被發現但使用者尚未確認統一規則
- **THEN** 實作者 MUST NOT 自行選擇任一邊、折衷規則或較寬鬆規則
- **AND** MUST NOT 為了讓測試通過而修改合法性、allocation、score 或 issue 行為

#### Scenario: 使用者確認統一規則
- **WHEN** 使用者對 B 類差異確認統一規則
- **THEN** 實作前 MUST 在本 spec 新增或修改對應 Requirement 與 Scenario，明確定義統一後規則
- **AND** MUST 在 proposal 的「不變事項」與 Impact 記錄哪一邊的哪些既有行為會改變
- **AND** 若統一規則屬工程規則變更，MUST 標註更新 `docs/DOMAIN.md` 或 `docs/SOLVER.md`

### Requirement: 統一合法性與 allocation 語意
共用評估 SHALL 對 automatic 與 manual plan 套用同一組 segment range、joint clearance、purchasable length、Waler 總長與 exact-length allocation 規則。每段長度必須在既有最小與最大範圍內、每個 joint 與 forbidden point 的距離必須 `>= joint_clearance`，且每段長度必須存在於 purchasable length set。Allocation MUST 保留 exact-length inventory matching；庫存不足但料長可購買時 SHALL 以採購補足而不使 plan invalid。

#### Scenario: Joint 位於 clearance 等號邊界
- **WHEN** joint 與最近 forbidden point 的距離恰好等於 `joint_clearance`
- **THEN** 共用評估 MUST NOT 因 joint clearance 將 plan 判為 invalid

#### Scenario: Joint 落入 clearance 範圍
- **WHEN** joint 與任一 forbidden point 的距離小於 `joint_clearance`
- **THEN** 共用評估 MUST 將 plan 判為 invalid 並產生 joint-clearance issue

#### Scenario: 可購買料長庫存不足
- **WHEN** segment 長度屬於 purchasable length set 但 exact-length inventory quantity 不足
- **THEN** allocation SHALL 先使用現有 exact-length inventory，再以同長度採購補足
- **AND** plan MUST NOT 只因庫存不足而變成 invalid

#### Scenario: Segment 不可購買
- **WHEN** 任一 segment 長度不在 purchasable length set
- **THEN** 共用評估 MUST 將 plan 判為 invalid
- **AND** MUST NOT 以較長庫存裁切或其他長度採購作為 fallback
- **AND** allocation、buy count、stock groups、length variation 與 local score MUST 標示為 unavailable，不得把不可購買 segment 虛構為採購

#### Scenario: 工程不合法時不執行 allocation 或評分
- **WHEN** plan 因總長、joint clearance 或 segment range issue 而 invalid
- **THEN** core MUST 在完成全部 hard-constraint issue 收集後停止
- **AND** assignments、allocation metrics、ratio analysis、score components 與 local score MUST 標示為 unavailable
- **AND** core MUST NOT 因 segment 看似可購買而先執行或補做 exact-length allocation
- **AND** automatic compatibility projector MUST 仍使用既有 invalid-candidate penalty 作為搜尋 score

#### Scenario: 多個 hard issues 仍完整回報
- **WHEN** 同一 plan 同時違反總長、joint clearance、segment range 或 purchasable-length 中的多項限制
- **THEN** core MUST 先依固定順序收集全部 issues，再停止 allocation 與評分
- **AND** 停止 allocation MUST NOT 造成任何 hard issue 遺失

#### Scenario: Allocation defensive failure
- **WHEN** plan 沒有 non-purchasable issue 但 exact-length allocation defensive path 回報 unavailable
- **THEN** plan MUST 為 invalid
- **AND** allocation metrics 與 local score MUST 標示為 unavailable
- **AND** automatic compatibility projector SHALL 保留既有 allocation-failure penalty

### Requirement: Waler 總長使用 200 mm 閉區間且不使用 adjustment block
Waler SHALL 不使用 adjustment block；Support Shim 規則不屬於此 Requirement 且 MUST 維持不變。對已解析的 `required_length`，Waler 鋼材總長 SHALL 滿足 `required_length - 200 <= steel_length <= required_length`，上下界均包含等號。Waler result MUST NOT 產生 `shim` piece，任何既有 `tail_adjustment` compatibility 欄位 MUST 為 `0`。

#### Scenario: 鋼材總長位於下界
- **WHEN** `required_length` 為 12000 mm 且 `steel_length` 為 11800 mm
- **THEN** plan MUST NOT 因總長限制而 invalid
- **AND** Waler result MUST NOT 產生 adjustment block 或 `shim` piece

#### Scenario: 鋼材總長位於上界
- **WHEN** `required_length` 為 12000 mm 且 `steel_length` 為 12000 mm
- **THEN** plan MUST NOT 因總長限制而 invalid

#### Scenario: 鋼材總長低於下界
- **WHEN** `required_length` 為 12000 mm 且 `steel_length < 11800 mm`
- **THEN** plan MUST 為 invalid
- **AND** core MUST 產生「鋼材總長不足」具名 issue，其 facts 至少包含 required length、minimum allowed steel length 與 actual steel length
- **AND** manual legality 顯示 MUST 使用「鋼材總長不足」，不得顯示「尾端調整量不合法」

#### Scenario: 鋼材總長高於上界
- **WHEN** `required_length` 為 12000 mm 且 `steel_length > 12000 mm`
- **THEN** plan MUST 為 invalid
- **AND** core MUST 產生「鋼材總長太長」具名 issue，其 facts 至少包含 required length 與 actual steel length
- **AND** manual legality 顯示 MUST 使用「鋼材總長太長」，不得顯示「尾端調整量不合法」

#### Scenario: 既有 Waler adjustment result 重新計算
- **WHEN** 既有專案載入含非零 Waler `tail_adjustment` 或 Waler `shim` piece 的舊結果
- **THEN** 載入本身 MUST NOT 觸發 persistence migration
- **AND** 下一次重新計算 MUST 依 200 mm 總長閉區間評估
- **AND** 新結果 MUST 將 `tail_adjustment` 投影為 `0` 且不得產生 Waler `shim` piece

### Requirement: 既有分數與排序相容
對在新總長規則下仍合法的相同 plan，共用評估 SHALL 使用現行 local score components、運算順序、數值型別與權重，並使 local score 及每個 component 與變更前完全相等；驗證 MUST 使用 exact equality，不得使用浮點容差。自動搜尋對 invalid candidate 的既有 penalty、候選去重與 tie-break SHALL 維持不變。因移除 Waler adjustment block 或套用 200 mm 總長閉區間而改變合法性的 candidate，Top N 與整體排序 MAY 隨確認後的工程規則改變，但 GA stage、population／candidate count、seed、repair、merge 與 tie-break policy MUST 不變。

#### Scenario: 合法 plan 評分
- **WHEN** 一個合法 plan 被共用評估
- **THEN** score MUST 仍由現行 purchase count、material ratio penalty、under-4000 segment count、distinct stock groups、length variation 與 joint count components 組成
- **AND** 每個既有 component 的權重 MUST 不變
- **AND** local score 與每個 component MUST 以 exact equality 與修改前結果完全相等，不得套用 rounding、近似比較或浮點容差

#### Scenario: 自動候選排序
- **WHEN** 相同候選集合在新總長規則下的合法性未改變，且以相同 config、庫存與 random seed 進入自動 Solver
- **THEN** 候選 score 與現有 deterministic 排序結果 MUST 不變
- **AND** 合法候選的 score 與各 component MUST 以 exact equality 驗證

#### Scenario: 新總長規則改變候選合法性
- **WHEN** 候選原本依 Waler adjustment block 合法，但不符合 `required_length - 200 <= steel_length <= required_length`
- **THEN** 候選 MUST 依新規則成為 invalid
- **AND** Solver 結果 MAY 因合法候選集合改變而不同
- **AND** 系統 MUST NOT 調整 GA stage、seed、candidate count 或其他搜尋參數補償

#### Scenario: Invalid candidate 相容投影
- **WHEN** 共用核心評估回報 invalid 自動候選
- **THEN** 自動搜尋輸出 MUST 保留既有 invalid-candidate penalty 語意
- **AND** 該相容 penalty MUST NOT 被當成另一套工程合法性或合法 plan 的 local score 公式

### Requirement: 具名問題識別與完整顯示
每個核心評估問題 MUST 帶有穩定、非空且不依賴顯示語言的具名 code。問題分類、篩選與去重 SHALL 使用 code 及必要的結構化 facts，MUST NOT 解析或比較中文顯示訊息。除人工畫面改為顯示全部 joint-clearance／non-purchasable issues，以及總長 issue 改為「鋼材總長不足／太長」外，既有使用者可見錯誤、警告、summary 與 details SHALL 維持相容。

#### Scenario: 同一問題有相同中文訊息
- **WHEN** 兩個 issues 的中文顯示訊息相同但 code 或結構化 facts 不同
- **THEN** 系統 MUST NOT 僅因訊息相同而將兩者視為同一問題

#### Scenario: 同一問題經不同流程產生
- **WHEN** 自動與人工路徑發現相同種類且相同 facts 的工程問題
- **THEN** 兩者 MUST 使用相同 issue code
- **AND** 下游流程 SHALL 能依 code 與 facts 穩定去重

#### Scenario: 顯示既有錯誤內容
- **WHEN** 評估結果投影到現有自動 diagnostics 或人工 legality 顯示
- **THEN** 未被已確認差異決策修改的錯誤、警告、summary 與 details MUST 維持既有語意與順序

#### Scenario: 人工畫面顯示全部接頭違規
- **WHEN** 同一 manual plan 有多個 joint-clearance issues
- **THEN** legality details MUST 依 joints 的既有輸入順序列出每一筆接頭位置與禁止區 facts
- **AND** summary MUST 顯示違規總數，不得只保留第一筆

#### Scenario: 人工畫面顯示全部不可購買料長
- **WHEN** 防禦性 manual evaluation 收到多個 non-purchasable segments
- **THEN** legality details MUST 依 segments 的既有輸入順序列出每一筆料長 issue
- **AND** 相同長度出現在不同 segment index 時 MUST 保留各自 facts，不得僅依中文訊息或 length 去重
- **AND** summary MUST 顯示違規總數，不得只保留第一筆

### Requirement: 搜尋政策與評估分離
共用 plan 評估 SHALL 只評估已給定的 segments／joints，不得改變或承擔 GA 候選生成、repair、stage escalation、random seed、population／candidate count、merge、停止條件或 tie-break 政策。

#### Scenario: Solver 執行既有搜尋流程
- **WHEN** 自動 Waler Solver 使用共用評估執行搜尋
- **THEN** GA stages、random seeds、candidate counts、repair 與停止條件 MUST 與變更前相同
- **AND** 共用評估 MUST NOT 產生額外候選或修改輸入候選

#### Scenario: Repair 只查詢 hard-rule 可行性
- **WHEN** GA repair 只需要判斷暫存 candidate 是否存在任一 hard issue
- **THEN** repair MAY 在第一個 hard issue 後停止該次內部可行性探測，且 MUST NOT materialize 未被使用的完整 issue list 或顯示訊息
- **AND** 該布林結果 MUST 與使用相同 hard-rule traversal 完整收集 issues 後的「issue list 是否為空」完全相同
- **AND** 正式 `evaluate_waler_plan()` 仍 MUST 收集並回傳全部 hard issues，不得套用 repair 的 short-circuit projection
- **AND** repair steps、輸出 chromosome、candidate count、stage、seed、score 與排序 MUST 維持不變

#### Scenario: 人工 plan 未經自動搜尋修補
- **WHEN** 使用者提交人工 segments
- **THEN** 系統 MUST 直接評估該 plan
- **AND** MUST NOT 套用 GA repair 或搜尋 heuristic 使人工 plan 自動變形


