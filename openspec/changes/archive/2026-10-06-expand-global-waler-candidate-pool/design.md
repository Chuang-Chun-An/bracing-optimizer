# Design

## 閱讀導航

- **現在必讀**：Decision 1「明確區分 Single／Global retention profile」、Decision 2「Global 收集各已執行 stage 的 final population」、Decision 3「不同 material signature 全部保留」。
- **現在必讀**：Decision 4「每支 Waler 仍獨立搜尋並逐支進 Exact DP」；這是排除舊等價重用方向的核心邊界。
- **實作 diagnostics／效能時閱讀**：Decision 5；處理 rank 大於 5 的採用、顯示、保存與重載時閱讀 Decision 6。
- **需要時再讀**：實作 failure／cancellation 時閱讀 Decision 7；修改 evaluator 或人工編輯旁路時讀 Decision 8。本 change 不應讓這些路徑取得 Global retention 邏輯。

## 方案摘要

```text
Single Waler
  → 既有 staged search → 每 stage Top 5 → 跨 stage Top 5 → 對外 Top 5

Global Waler（每支 Waler 都獨立執行）
  → 既有 staged search
  → 每個已執行 stage 的 final population：合法 + 完整 solution signature 去重
  → 跨 stage union：完整 solution signature 去重 + deterministic local rank
  → material signature 分組：同 signature 留最佳、不同 signature 全保留
  → 該支 Waler 的 candidate group
  → Exact DP 依 waler_order 逐支選擇
```

**retention profile** 只決定搜尋完成後保留哪些已評估候選，不改候選如何生成或評分。**完整 solution signature** 用於判定相同 segmentation／正式結果；**material signature** 則是 Global objective 所需的 Short／Mid／Long／Out counts 與 Out distance，兩者不得混用。

## 決策對照

| Decision | 對應 Spec Requirement | 對應 Tasks |
| --- | --- | --- |
| D1 Single／Global retention profile | Single Waler 候選輸出維持不變、搜尋政策與評估分離 | 1.1～1.3 |
| D2 Stage final-population union | Global Waler 必須保留材料多樣性的候選 | 2.1～2.3 |
| D3 Material-signature dominance | Global Waler 必須保留材料多樣性的候選 | 3.1～3.3 |
| D4 每支獨立搜尋與逐支 DP | 全域流程仍須逐支生成與選擇 | 4.1～4.3 |
| D5 Diagnostics 與效能 | 候選池範圍必須可診斷 | 5.1～5.3 |
| D6 Rank > 5 下游相容 | Rank 6 以上候選完成成果生命週期 | 4.4、7.2 |
| D7 Failure／cancellation | 部分候選池不得進入全域選擇 | 6.1～6.2 |
| D8 Evaluator／旁路隔離 | 既有分數與排序相容、搜尋政策與評估分離 | 6.3、7.2 |

## Context

動機與目標見 `proposal.md`。現況 `OptimizeWaler._build_config()` 固定 `top_n=5`；每個 `wales.evolve()` stage 在 final population 完整 solution 去重後只回傳前 5 名，`OptimizeWaler._run_search()` 合併 stages 時又以 `limit=cfg.top_n` 再截為 5。`OptimizeWalerGlobal.execute()` 呼叫相同 use case，因此 `merge_equivalent_candidates()` 只能在這 5 個候選內保留 material signatures，無法取回較後名次。

既有 `solve_global_waler_candidates()` 已依 `waler_order` 逐支執行 Exact DP，並以 `(out_count, out_distance, ratio_deviation, local_regret, changed_count, rank_path)` 排序。它的 exact scope 是呼叫端提供的 retained candidate groups，且 `shared_inventory_optimized=False`。本 change 應擴大輸入 group，不應改寫 DP。

現有 Architecture 將 staged search／result merge 歸 `OptimizeWaler`，Global orchestration 歸 `OptimizeWalerGlobal`，材料 signature 與 Exact DP 歸 `algorithms/waler_global.py`。本設計沿用這些 ownership。

## Goals / Non-Goals

**Goals:**

- 讓 Single 與 Global 明確選擇不同候選保留策略，且 Single 預設與外部 contract 完全相容。
- 讓 Global 看見各已執行 stage final population 已發現的全部合法 unique solutions。
- 在進入 DP 前只移除對 Global objective 可證明被同 material signature 更低 local regret 候選支配的方案。
- 保持逐支搜尋、逐支 candidate group 與逐支 Exact DP。

**Non-Goals:**

- 不建立 Waler 等價判定、跨 Waler result reuse 或 cache。
- 不保存每一代所有歷史 individuals；只使用各 stage final population。
- 不調整搜尋預算、評分、工程限制、Exact DP objective 或 shared inventory。
- 不建立新的通用 candidate framework；只擴充既有 Waler use-case contract。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer responsibility 或 dependency direction**。

| Layer | 影響 | 責任 |
| --- | --- | --- |
| Application | 主要修改 | 選擇 retention profile、協調 staged results、逐支建立 Global candidate groups、組裝 diagnostics |
| Algorithms | 局部修改 | 依 profile 投影 final-population results、執行既有完整 signature merge、material-signature dominance 與 Exact DP |
| Presentation | 不修改規則 | 只讀 Application／Algorithms diagnostics；不得決定 profile 或候選截斷 |
| Domain | 不修改 | 工程合法性、材料分類邊界與 ratio targets 維持既有 single source of truth |
| Infrastructure | 不修改 | 無 persistence schema、file format 或 adapter 變更 |

Dependency direction 維持 `Presentation → Application → Algorithms / Domain`。

Single source of truth：

- retention profile：`OptimizeWaler.execute()` 的具型別 keyword contract，預設為 Single。
- stage budget 與 escalation：`SolverSearchPolicy.waler_search_stages` 與既有 assessment helpers。
- 完整 solution signature／deterministic ordering：既有 `solver_search`／Waler result merge contract。
- material signature：`waler_global.analyze_candidate_materials()`／`WalerMaterialMetadata.signature`。
- Global objective 與 state merge：`solve_global_waler_candidates()`。

## Decisions

### Decision 1：以明確 retention profile 區分 Single 與 Global

在 `OptimizeWaler.execute()` 增加具型別、keyword-only 的 retention profile，預設值為 `SINGLE_TOP_5`；`OptimizeWalerGlobal` 明確傳入 `GLOBAL_FINAL_POPULATION`。Profile 不由 WalerID、caller type、Dialog state 或 result slicing 推測。

- `SINGLE_TOP_5`：每個 stage 與跨 stage merge 都沿用 `top_n=5`。
- `GLOBAL_FINAL_POPULATION`：每個已執行 stage 回傳 final population 中所有合法、完整 signature unique candidates；跨 stage merge 不設固定 Top N。

`OptimizeWalerRequest` 的幾何／材料輸入與既有 Single `build_cache_key()` tuple shape 不變；Global profile 是 execution policy，不寫入 Single memory。Diagnostics 記錄 profile，避免 result count 與 config 中舊 `top_n` 欄位形成兩個 truth。

**Rejected alternative：**讓 Global 先呼叫 Single，再另外要求更多候選。這會執行兩次搜尋或依賴被截斷結果，既浪費時間也無法取回 rank 6 以後方案。

**Rejected alternative：**直接把全域預設 Top N 改為 20 或 50。不同 material signature 的價值只有與其他 Waler 組合後才知道，固定 local-score cutoff 仍可能提前丟失必要選項。

### Decision 2：Global profile 收集每個已執行 stage 的 final population

`wales.evolve()` 的搜尋流程維持不變，但 result projection 必須能選擇「Top N」或「所有合法完整-signature unique results」。Global profile 使用後者；Single 繼續使用前者。不得為取得更多結果而增加 generations、population、seed、repair 或 stage 數。

`OptimizeWaler._run_search()` 將各 stage results 加入 ordered aggregate；stage escalation assessment 繼續使用原本 diagnostics 與停止條件。跨 stage merge：

1. 若任一合法候選存在，只保留合法候選。
2. 以完整 Waler solution signature 去重，同 signature 保留 score 最低者。
3. 以既有 rounded score 與完整 signature deterministic 排序。
4. Single 取前 5；Global 不再切片並依此順序指派 local rank。

候選探索仍是有限集合：STANDARD 最多來自其 120 個 final-population members；若實際執行 ENHANCED／DEEP，才分別再加入其 180／240 個 members。這些數字是既有 search budget，不是新 candidate cap。

**Rejected alternative：**保存歷代所有 evaluated individuals。現有 GA 沒有跨 generation archive，新增它會改變記憶體與搜尋 instrumentation；使用者需求只要求 Global 保留足夠候選，本次以各 stage final population 為明確邊界。

### Decision 3：Material signature 是 Global pool 唯一的 dominance merge

跨 stage 完整 solution merge 後，`OptimizeWalerGlobal` 依 deterministic local order 建立 `WalerGlobalCandidate`，再沿用 `merge_equivalent_candidates()`：相同 material signature 保留 local regret 最低者；tie 時沿用較前 rank。不同 signature 不存在可由 local score 單獨證明的全域 dominance，因此全部保留。

Material signature 使用既有 `(short_count, mid_count, long_count, out_count, out_distance_mm)`，不新增另一份分類公式。Global rank 可以大於 5，rank 1 的 local-best score 與 regret 基準仍取跨 stage完整 solution merge 的第一名。

**Rejected alternative：**先依 local score 取較大 Top N，再做 material merge。這只是放寬原本缺陷，仍無法保證搜尋已發現的不同材料組成會進入 DP。

### Decision 4：每支 Waler 仍獨立搜尋並逐支進 Exact DP

`OptimizeWalerGlobal.execute()` 保留現有 per-Waler loop；每支 eligible Waler 都建立自己的 optimizer、執行 Global profile、建立 `WalerLocalOptimizationRecord` 與 `candidates_by_waler[waler_id]`。不建立等價 key、group plan、template table、deep-copy projection 或 reuse diagnostics。

`solve_global_waler_candidates()` 繼續接收完整 `waler_order` 與每支 candidate group。若有 N 支 eligible Waler，就有 N 次 local executions、N 個 groups、N 個 DP stages 與 N 個 selected candidates。Algorithms 不接收或推導跨 Waler generation group。

這也避免低機率重複情境引入 key 完整性、mutable template identity、failure fan-out 與 cache invalidation 風險。

### Decision 5：Diagnostics 區分三個候選邊界並量測 DP 成長

每支 local diagnostics 增加或明確投影：

- `retention_profile`
- 各已執行 stage 的 `result_count_after_stage_solution_merge`
- `candidate_count_after_cross_stage_solution_merge`

Global diagnostics 保留既有 `raw_candidate_count` 與 `retained_candidate_count_after_signature_merge`，並明確定義前者為所有 per-Waler groups 在 material merge 前的總數、後者為送入 DP 的 material representatives 總數。必要時加入 per-Waler structured counts，不從 log 文字反推。

效能量測使用 Y05、Y29、Y1A 等既有 fixture 執行完整 Global Waler。每個 fixture 都必須使用相同輸入、相同搜尋政策與可重現條件，分別量測修改前基線（每支 Waler 最多 Top 5）及修改後 Global final-population retention，並記錄：

- 每支 Waler 經 material-signature merge 後的候選數；
- 送入 Exact DP 的候選總數；
- `transition_count`；
- `max_active_state_count`；
- Global Waler 執行時間。

每個 fixture 另列修改後候選數最多的前 3 支 Waler，依修改後候選數遞減、同數時依既有 `waler_order` 排序；每列同時呈現 WalerID、Top 5 基線候選數、修改後候選數與差值。另以每支 Waler 的完整 selected-plan signature 比較修改前後 Global 結果，不得只比較可能因候選池擴大而重排的 local rank。若任一 selected plan 不同，回報 changed Waler IDs，並列出修改前後全場 Short／Mid／Long／Out counts 與四分類比例。此處四分類比例僅供效能報告比較，分母定義為 `total_short + total_mid + total_long + total_out`；不得改寫現有 Global objective 中「Out 不進入 Short／Mid／Long ratio 分母」的規則。

量測結果必須以 fixture × Top 5／修改後 profile 的對照表回報，並附量測命令、環境與重複次數，避免只給百分比或主觀結論。Task 5.3 是強制人工決策 gate：量測完成後不論結果好壞都必須暫停，不得自行判定可接受、繼續 Task 6／7、完成 change，或加入任何固定 Top N、beam pruning、state truncation 等截斷。只有使用者明確接受量測後才能繼續；若使用者不接受，後續方案需另行提案，任何 pruning 都必須由新 spec 定義 global-aware preservation contract。

### Decision 6：Global rank 是無固定上限的正整數，下游不得假設最多為 5

現況程式盤點如下；位置以本 change 提案時的檔案與 symbol 為準：

| 範圍 | 程式位置 | 現況與 rank > 5 影響 |
| --- | --- | --- |
| Global candidate／Exact DP | `bracing_optimizer/algorithms/waler_global.py:51`、`:202`、`:260`、`:380` | `candidate_rank` 只驗證為大於 0 的整數；material merge、changed count、`rank_path` 與 objective 均無上限。 |
| Global local result 轉換 | `bracing_optimizer/application/optimize_waler_global.py:147`～`:175` | 依完整 `raw_solutions` 從 1 排 rank，再交給 material merge；此處沒有 Global `[:5]`。 |
| 正式採用／result identity | `bracing_optimizer/application/project_results.py:416`～`:467` | 將原 rank 寫入 `selected_plan.global_candidate_rank`、`result.option_index` 與 `{WalerID}-方案{rank}`；沒有上限或五格資料結構。 |
| Global Dialog | `bracing_optimizer/presentation/dialogs/waler_global_solver_dialog.py:432`～`:456` | 直接以 `#{candidate_rank}` 顯示 DP 選中的候選；沒有截斷或候選索引表。 |
| 成果樹與結果詳細顯示 | `main.py:4593`～`:4643`、`:4936` 起 | `option_index` 轉成整數排序並格式化為「全域方案 N」；rank 6 以上可直接顯示。 |
| 人工切換／編輯 | `main.py:4237`～`:4250`、`:4748`～`:4757` | 編輯器以一般 `option_index` 命名；成果切換是對 `result_id` 的 generic visibility toggle，不以 1～5 建立選項。Global Dialog 本身只採用 DP 選中方案，不提供 local candidate picker。 |
| Solver memory | `bracing_optimizer/presentation/dialogs/waler_solver_dialog.py:325`～`:418`、`:636`；`main.py:8291`、`:8371` | `solver_memory` 只傳入 Single Dialog；Global Dialog 不讀寫它，因此沒有 Global rank 上限。Single Top 5 contract 維持不變。 |
| Persistence | `bracing_optimizer/application/project_results.py:153`～`:287`、`bracing_optimizer/application/project_service.py:351`～`:365`、`:501`～`:525` | Waler result dict 以 deep copy 完整序列化／反序列化，`option_index` 與 `global_candidate_rank` 沒有範圍驗證或 schema cap。 |
| Excel／DXF 匯出 | `bracing_optimizer/application/project_results.py:586`～`:625`、`:743`～`:802`；`main.py:3402`～`:3452`、`:3486`～`:3555`、`:3575`～`:3592` | 匯出只讀可見結果的 `selected_plan`、pieces、合法性與 member identity，不以 rank 取陣列或限制方案數。 |
| 材料摘要 | `bracing_optimizer/application/project_results.py:852`～`:893`；`main.py:3104`～`:3121`、`:5246` 起 | 摘要由可見 `selected_plan` 的 steel pieces 聚合，不讀 rank。 |

盤點未發現 Global rank 最多為 5 的假設。`bracing_optimizer/application/project_results.py:476`～`:555` 中的 `top_results[:5]` 僅屬 Single Waler 保存路徑；Global 採用走 `stage_waler_global_result()`，不得因新增 rank 6+ regression 而修改 Single slice。雖然現況結構可容納 rank 6 以上，仍需以採用、保存、重載、Dialog／成果樹顯示、人工 visibility、材料摘要及匯出的端到端 regression 鎖定。

Result ID lifecycle 盤點也未發現現行格式的衝突：Single 在尚無 Global 結果時使用 `{WalerID}-方案1..5`；`stage_waler_global_result()` 會先透過明確 `waler_id` 移除該支 Waler 的所有舊成果，再建立 `{WalerID}-方案{global rank}`。因此 Single 後執行 rank 6+ Global 時，舊 Single IDs 會在新 ID 插入前移除；重新執行 Global 時，舊 Global rank ID 也會先被移除，不應殘留。Regression 必須比對該 Waler 的完整 result-ID key set，而不只檢查新 ID 存在；若測試發現格式衝突、覆寫錯誤或舊 rank 殘留，先回報並暫停，不得自行修改 ID 格式或 replacement semantics。

### Decision 7：Failure 與 cancellation 維持全有或全無

每個 stage 搜尋、stage result projection、跨 stage merge、material-signature merge、每支 group 完成後與進入 Exact DP 前保留 cancellation checkpoints。`SolverCancelled` 繼續向上拋出交由既有 operation lifecycle 處理。

任一必要 Waler 沒有合法 rank 1、候選合併失敗或發生 exception 時，Global operation 在 Exact DP 前回傳既有 invalid／failure outcome；已完成的其他 Waler groups 不進入部分 DP，也不正式採用。

### Decision 8：Evaluator、人工編輯與 Presentation 不取得 retention 責任

共用 Waler evaluator 仍只評估給定 segments／joints；它不知 Single／Global profile，也不生成或截斷候選。人工編輯直接評估使用者方案，不套用 Global profile。Presentation 不傳候選數或重建 material signatures，只顯示 diagnostics。

因此本 change 修改 `waler-plan-evaluation` 的相容文字，只是明確記錄經核准的 Global output-retention 例外；合法性、allocation、score components／weights、invalid penalty 與相同候選集合的 deterministic ordering 均不變。

## Risks / Trade-offs

- **[Risk] Global profile 仍在 stage 內被 `top_n=5` 提前截斷** → 以至少 8 個 final-population unique candidates 的 focused test，直接驗證 stage output、跨 stage output 與 DP input。
- **[Risk] 候選擴大造成 DP active states、時間或記憶體成長** → 依 D5 量測 Y05／Y29／Y1A；無論結果好壞都先回報並暫停，由使用者決定是否接受，Agent 不得自行加入截斷。
- **[Risk] 完整 solution signature 與 material signature 被混用** → 分開測試兩個 merge 邊界；只有 material signature 相同且 local regret 不佳者可在 Global boundary 被支配移除。
- **[Risk] Single 路徑誤用 Global profile** → profile 預設 Single、Global caller 顯式 opt-in，並以現有 Single result／memory tests鎖定 Top 5。
- **[Trade-off] 每支 Waler 仍各自搜尋** → 接受重複機率低時可能存在的少量多算，換取更小 scope 與更低正確性風險。
- **[Trade-off] Global selected result 可能改變** → 這是預期改善；候選集擴大，但 local score 與 Global objective 均不變。

## Backward Compatibility 與 Persistence

- Single Waler request、cache key、Top 5、result IDs、memory prompt 與 adoption 不變。
- Global selected rank 可能大於 5；D6 盤點顯示現有 result payload／persistence 使用一般整數 rank，可直接保存，不需 schema migration；仍以 rank 6+ 端到端 regression 驗證。
- `solve_global_waler_candidates()` API、objective、diagnostics既有欄位與 persisted results 保持相容；新增 diagnostics 使用 defaults。
- 不保存 retention profile 或候選池本身；重新執行 Solver 依目前 input 重新搜尋。
- Atomic apply、rollback、refresh、visibility 與 Project dirty semantics 不變。

## Migration Plan

1. 先用 tests 鎖定 Single Top 5 與 Global stage output 可超過 5。
2. 實作 retention profile 與 final-population result projection。
3. 實作跨 stage完整 solution merge、Global rank 與 material-signature dominance。
4. 鎖定每支獨立 local execution 與既有 Exact DP contract。
5. 補 diagnostics，依 D5 完成 Top 5／修改後 performance characterization；回報所有數據後無條件暫停，等待使用者決定是否接受。
6. 僅在使用者明確接受 Task 5.3 數據後，補 failure／cancellation、rank 6+ lifecycle tests 與 `docs/SOLVER.md`，再執行 focused、Solver regression、architecture boundary 與 strict OpenSpec validation。

Rollback 只需讓 Global caller恢復使用 `SINGLE_TOP_5`，並移除新增 profile／diagnostics projection；沒有 persisted data migration 需要回復。
