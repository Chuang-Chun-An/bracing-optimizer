# Design

## 閱讀導航

### 現在必讀

- **Decision 1**：以 Algorithms 的單一 pure resolver 決定 Steel endpoint、adjustment 與 Gap，避免自動／人工漂移。
- **Decision 2**：共用 evaluator 擁有尾端合法性與結構化結果；Application／Presentation 只投影。
- **Decision 3**：沿用既有 `tail_adjustment`、`gap` 與 `("shim", length)` result contract，調整塊固定附加在最後。
- **Decision 4**：搜尋與 scoring 不變；只改合法尾端解析及因此形成的合法候選集合。

### 條件式閱讀

- 修改 cache 或同時整合 Global candidate retention 時讀 **Decision 5／6**。
- 修改材料摘要、Preview、Excel／DXF export 或 persistence regression 時讀 **Decision 7**。
- 只有發現既有 consumer 不能承接非零 `tail_adjustment` 時才讀 Backward Compatibility、Risks 與 Migration Plan；不得先擴大 schema。

## 方案摘要

```text
Algorithms tail resolver（唯一工程 truth）
  ├─ Config：由 required length 推導 automatic steel endpoint
  └─ Evaluator：由 required length + 實際 Steel total 推導 adjustment／Gap／issue
          ↓
  Automatic projector / WalerPlanEditing projector
          ↓
  canonical result：segments + joints + tail_adjustment + gap + pieces
          ↓
  既有 adoption / persistence / preview / summary / Excel / DXF consumers
```

「尾端調整塊」在工程語意上是 Steel segments 之後、Gap 之前的單一固定尺寸構件；結果 payload 為維持相容，仍以 piece kind `shim` 表示。這個字串相容格式不會把它變成 Support Shim，也不會讓 Support placement 規則介入 Waler evaluation。

## 決策對照

| Decision | 影響的 spec Requirement／Scenario | 對應 task group |
| --- | --- | --- |
| D1 單一 deterministic resolver | 「圍令以單一尾端 adjustment block 與 Gap 完成需求長度」全部數值與多解 scenarios | 1、2 |
| D2 evaluator 擁有合法性與結果 | Automatic／manual 相同尾端解析、無解與超長 scenarios | 2、3 |
| D3 沿用 result contract 並固定尾端順序 | Adjustment 固定在最後、正式結果只產生一塊、既有結果重算 scenarios | 3、4 |
| D4 scoring／search isolation | 「既有分數與排序相容」全部 scenarios | 2、5 |
| D5 cache policy versioning | 相同輸入 deterministic ordering | 3、5 |
| D6 archived baseline coordination | Global retention 不變、proposal Archived baseline coordination | 0、5、7 |
| D7 consumer verification before edits | 正式 pieces 順序、既有結果重算與不計 Steel allocation | 4、6 |

## Context

動機見 `proposal.md` 的 Why。現況 `wales.Config` 先把 `required_length` 向下解析到 `500 mm` grid 的 `steel_target_length`，`evaluate_waler_plan()` 再以 `required_length - 200 <= steel_length <= required_length` 判斷總長；result projector 固定輸出 `tail_adjustment = 0`。`WalerPlanEditing` 雖共用 evaluator，仍自行重建 `tail_adjustment`、Gap 與 pieces 顯示，因此新規則若只改 automatic projector 會再次形成兩套 truth。

Repository 已有可追溯的舊 resolver，尺寸為 `0／100／150／200／300 mm` 且曾以 `(gap, adjustment, -steel_length)` deterministic 排序；也已有非零 `tail_adjustment` 的 save/load、Preview 與 export 相容程式。本 change 改採「能不用就不用」且 Gap 上限為 `150 mm`，因此不可直接整段復原舊 resolver 或沿用它的 Gap 最小優先順序。

`expand-global-waler-candidate-pool` 已於 `2026-10-06` 封存並同步 main spec；其 `wales.py`、`solver_search.py`、`optimize_waler.py`、Single Top 5／Global expanded retention 與同一 capability Requirements 已成為本 change 的既有基線，不得覆寫或降回封存前行為。

## Goals / Non-Goals

**Goals:**

- 以一份 pure、deterministic 的尾端解析規則同時服務 automatic Config 與 fixed-Steel manual／core evaluation。
- 讓 evaluator 的合法性、issue facts、`tail_adjustment` 與 Gap 成為正式計算結果，兩個 projector 不重算。
- 沿用既有結果與 consumer contract，不新增 Project schema 或另一種 piece kind。
- 以 exact regression 證明 Steel score components、search budget、retention 與 Global objective 未被改寫。

**Non-Goals:**

- 不建立一般化 piece-layout engine，也不把 Waler 轉成 Support ordered-piece validator。
- 不替 adjustment block 建 inventory、Material Spec、採購或 scoring model。
- 不讓使用者直接編輯 adjustment block；人工編輯仍只提交 Steel segments，由 evaluator 推導尾端。
- 不重新設計已封存的 `expand-global-waler-candidate-pool` retention policy。

## Decisions

### Decision 1：Algorithms 提供唯一的 deterministic 尾端 resolver

在 `bracing_optimizer/algorithms/wales.py` 恢復小型 pure resolver，輸入為：

- `required_length`；
- optional fixed `steel_length`（manual／evaluator 使用）；
- adjustment set，預設 `(0, 100, 150, 200, 300)`；
- `max_gap = 150`；
- automatic endpoint 使用的 `steel_step = 500`。

輸出為具名、不可變的 `steel_length`、`tail_adjustment`、`gap`。令短差 `shortfall = required_length - steel_length`：若 `0 <= shortfall <= 150`，resolver MUST 直接回傳 `tail_adjustment = 0`、`gap = shortfall`；只有 `shortfall > 150` 時，才從非零 adjustment set 依尺寸遞增找出第一個使 `0 <= shortfall - adjustment <= 150` 的選項。等價的 deterministic option key 為 `(tail_adjustment != 0, tail_adjustment, -steel_length)`；Gap 由等式推導，不再作為優先排序欄位。`Config.__post_init__()` 不傳 fixed Steel，取得 GA 的 `steel_target_length`；正式 evaluator 傳入 `sum(segments)`，驗證該實際 plan。對 production 預設值，automatic endpoint 維持既有 `500 mm` grid，不將 adjustment 納入 genes 或 joints。預設 adjustment set 與 Gap 最多可補足 `450 mm` 短差，因此 `500 mm` grid 的 residue `0～450 mm` 可完成，`451～499 mm` 必須回報無合法尾端組合。

此規則的代表結果為：`12100／12000 → adjustment 0、Gap 100`；`12180／12000 → adjustment 100、Gap 80`；`12250／12000 → adjustment 100、Gap 150`；`16450／16000 → adjustment 300、Gap 150`。

`required_length = 0` 仍回傳全零；負需求長度、負 Gap 上限、非正 steel step 等 programmer errors 繼續以 exception fail fast。正常工程無解不得靠 exception 穿過 use-case boundary；evaluator 將它轉為具名 hard issue。

**Rejected alternative：**只在 `_top_results()` 尾端補 `shim`。這會讓 repair／evaluation 先把 candidate 判 invalid，`16450 mm` 仍進不了合法結果。

**Rejected alternative：**把 adjustment block 加入 GA chromosome 或 candidate joint grid。調整塊固定在尾端，不形成 joint；加入搜尋只會擴大狀態、讓它可能出現在中間並改變 search policy。

### Decision 2：共用 evaluator 擁有尾端合法性與結構化結果

`evaluate_waler_plan()` 使用 D1 resolver 評估實際 `sum(segments)`，並讓 `WalerPlanEvaluation` 帶出 `tail_adjustment` 與 `gap`。既有 hard-rule traversal 順序保持：總長／尾端完成、joint clearance、segment range、purchasable length；有任一 hard issue 時仍不進 allocation／ratio／local score。

Issue compatibility 優先沿用既有穩定 code：

- `steel_length > required_length` 繼續是 `steel-total-long`；
- Steel 不足且無任一合法 adjustment＋Gap 時，繼續以 `steel-total-short` 表達，但 facts 增加或更新為足以顯示 required length、actual Steel、合法 adjustment set 與 max Gap；
- 不新增只供中文文案解析的平行判斷。

Automatic projector 與 `WalerPlanEditing` 都直接讀 evaluation fields。Application 只負責把 issue 投影成既有 legality details，不得再次枚舉 adjustment 或自行相減決定 Gap。

**Rejected alternative：**由 `WalerPlanEditing` 恢復舊 `resolve_tail_adjustment()`，automatic 繼續用 Config fields。這正是共用 evaluator 已消除的雙軌風險。

### Decision 3：沿用 `tail_adjustment`／`gap`／`pieces` contract

Canonical Waler result 的一致性條件為：

```text
steel_length == sum(segments)
required_length == steel_length + tail_adjustment + gap
pieces == [("steel", segment)...] + optional [("shim", tail_adjustment)]
```

`tail_adjustment = 0` 時不輸出 `shim` piece；非零時恰有一筆且永遠最後。`gap` 不屬於 pieces，位於最後一個 piece 之後。`joints` 仍只由 Steel segments 的累積邊界建立，因此 adjustment 與 Gap 都不新增 forbidden-point check。

piece kind 沿用 `shim` 是 persistence／export compatibility choice；Domain 與顯示文字稱「圍令調整塊」，避免與 Support Shim placement 混淆。正式新結果同時寫入三個欄位，consumer 應優先使用 `pieces`；legacy fallback 才由 `segments + tail_adjustment` 重建。

**Rejected alternative：**改成新 kind `adjustment` 或新增 payload object。這會擴大 persistence、export 與所有 result consumers，對本次固定尾端需求沒有收益。

### Decision 4：Adjustment 不進入 Steel scoring 或搜尋政策

Adjustment resolver 是 Engineering Hard Constraint 的完成長度判斷，不是新的 score preference。Allocation、ratio、under-4000、stock groups、length variation 與 joint count仍只接收 `segments`。合法 plan 的相同 Steel inputs 必須 exact-equal；新規則讓原 invalid plan 成為 valid 時，候選集合與 Top N 可合理改變。

不得修改 GA stages、population、generations、seeds、repair steps、candidate counts、Single／Global retention profile、merge、tie-break 或 Exact DP objective。Performance 驗證以 focused timing／diagnostics sanity check 為主，不以新規則為理由重新 tuning。

**Rejected alternative：**以 Gap 或 adjustment 尺寸新增 penalty。使用者只確認合法配置，沒有確認材料成本或偏好；新增權重會把未決政策偷偷放進 scoring。

### Decision 5：以 cache schema 隔離新舊尾端語意

Single Waler memory 的 cache key 已包含 `CACHE_SCHEMA`。實作應 bump schema 值，讓同一 session 或相容載入路徑不會把「固定 `tail_adjustment = 0`」的舊結果當成新規則結果。幾何、材料與 ratio tuple shape 不因本 change 改寫；schema marker 是唯一必要的 cache invalidation。

**Rejected alternative：**把 adjustment options 逐項附加到既有 tuple。它們是程式版本固定的工程規則，不是 Project input；schema marker 已是現有 policy version boundary。

### Decision 6：以已封存 Global candidate-pool 契約為實作基線

`expand-global-waler-candidate-pool` 已封存且 main spec 已同步。Apply 開始時 SHALL：

1. 以目前 main spec 的 `既有分數與排序相容`、`Global output retention 擴大` 與 `搜尋政策與評估分離` 為完整基線。
2. 在本 delta 的 MODIFIED Requirement 中保留 Single Top 5、Global 可超過 5、retention 由 Solver／Application 決定且 evaluator 不承擔 retention 的契約。
3. 保留工作樹中已成立的 retention code／tests，逐一整合本 change；不得回復 `wales.py`、`solver_search.py` 或 `optimize_waler.py` 的封存前版本。

最終回歸必須同時覆蓋 Single Top 5 與 Global retention profile；本 change 只允許因候選合法性改變而改變內容，不允許重新截斷候選。

### Decision 7：先驗證既有 consumers，再做最小修正

現況 `project_results.py`、Main Preview、Excel／DXF projection 已能從 `pieces` 或 legacy `tail_adjustment` 建立 `shim` piece。實作先用 canonical nonzero adjustment fixture 驗證：

- adoption／serialization round-trip 保留 `tail_adjustment`、Gap 與尾端 pieces；
- Preview 依 `Steel → adjustment → Gap` 畫在 member 尾端；
- 材料摘要將 adjustment 顯示為獨立 `shim`／調整塊，不混入 Steel assignments 或比例；
- Excel／DXF export 使用 canonical pieces 並保持總長一致。

只有 regression 證明 consumer 不符合 spec 時才最小修改 owner module。不得為統一命名而重寫所有 legacy `shim` consumer。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility 或 dependency direction：

| Layer | 責任 | 本 change 的影響 |
| --- | --- | --- |
| Algorithms | Engineering legality、search、evaluation | 擁有 pure tail resolver、hard issue 與 canonical evaluation fields |
| Application | Use-case orchestration、人工編輯 projection、cache policy | 讀 evaluator 結果、bump cache schema；不重算工程規則 |
| Presentation | 顯示與使用者操作 | 顯示既有 result fields；不決定 adjustment 尺寸或位置 |
| Infrastructure | persistence／Excel／DXF | 沿用既有 pieces contract；不定義合法尺寸 |
| Domain docs | long-term engineering truth | 實作驗證後更新，不提前宣稱已成立 |

依賴方向仍為 `Presentation → Application → Algorithms`，Infrastructure 消費 Application／result contract；Algorithms 不依賴 Application、Presentation 或 Infrastructure。唯一工程 truth 是 Algorithms resolver＋evaluator；`tail_adjustment`／`gap`／`pieces` 是同一 evaluation 的投影，不是三份可獨立修改的 truth。

Architecture boundary 未新增，因此預期不修改 `docs/ARCHITECTURE.md`；仍執行 boundary tests 防止 Application／Presentation 複製規則。

## Backward Compatibility 與 Persistence

- Project schema 與 result serialization 格式不變；不新增 migration。
- 舊結果無論 `tail_adjustment = 0` 或非零，load-as-is；載入不等於重新驗證。
- 下一次完整 Solver 或人工重算忽略舊 tail fields，從目前 `required_length + segments` 重新推導 canonical tail。
- 舊版任意尺寸（例如 `75 mm`）可為歷史顯示而載入，但不得由新 evaluator 重新產生。
- `CACHE_SCHEMA` bump 只淘汰 runtime Solver memory，不改 Project persistence。
- 新結果沿用 `shim` piece kind，既有 exporters 不需 schema branch。

## Risks / Trade-offs

- **[Risk] 實作仍沿用現行 `Gap = 200` 或舊 `0..199` 邊界** → 以 `11500 + 300 + 150 = 11950` 精確邊界 test 鎖定 `150 mm` inclusive 上限，並以 `16451 - 16000 = 451` 驗證無解。
- **[Risk] automatic 與 manual 各自重算 tail 而漂移** → evaluator 回傳 canonical fields，兩個 projector 只讀取並做 exact-equivalence tests。
- **[Risk] adjustment 被算成 Steel、joint 或 score** → 以 allocation／ratio／under-4000／joint component exact tests及 material summary tests隔離。
- **[Risk] `pieces`、`tail_adjustment`、Gap 不一致** → 建立單一 projector helper或在同一結果投影點原子產生，並用 invariant tests驗證總長等式與唯一尾端 piece。
- **[Risk] 尾端規則實作覆寫已封存 Global retention 行為** → D6 main-spec baseline check、完整 delta replacement 與 retention regression。
- **[Trade-off] 選擇最小調整塊不保證 Gap 最小** → 例如 `12250／12000` 選 `100 mm` adjustment 與 `150 mm` Gap，而不是 `200 mm` adjustment 與 `50 mm` Gap；這是「能不用就不用、必須使用時取最小調整塊」的明確產品規則，不是 scoring 權重。
- **[Trade-off] Adjustment 沒有庫存／成本模型** → 先解決可施工長度離散問題；未經產品決策不虛構庫存與權重。

## Migration Plan

1. 先完成 D6 archived-baseline preflight，確認 main spec 與本 delta 均保留 Global retention／搜尋政策契約。
2. 以 focused tests 鎖定 resolver 的 `0～450 mm` 可完成 residue、`451～499 mm` 無解 residue、四個代表選擇案例與 Gap inclusive 邊界。
3. 實作 resolver 與 evaluator canonical tail fields，再讓 automatic／manual projectors消費同一結果。
4. bump runtime cache schema，驗證 Single／Global search與 scoring不變範圍。
5. 驗證 existing consumers；只對失敗的 owner做最小修正。
6. 完成 Solver／consumer／architecture regressions後，更新 `docs/DOMAIN.md`、`docs/SOLVER.md`。
7. 執行 strict OpenSpec validation與 implementation verification。

Rollback 可將 resolver與 evaluator恢復為同步前版本、還原 cache schema及相關 docs；因無 persistence migration，已保存的 result payload仍可由既有 compatibility loader讀取。若 rollback後載入含新規則非零 adjustment的結果，仍依目前既有政策 load-as-is，下一次重算才回到 rollback後規則。

## Open Questions

無；會改變規格或 task breakdown 的數值與選擇規則已在本 change 關閉。尾端選擇已確認為「能不用就不用；必須使用時取最小合法調整塊」，Gap 上限已確認為含等號的 `150 mm`；若使用者再次調整任一規則，需先更新 proposal、spec 與本 design，再進入 apply。
