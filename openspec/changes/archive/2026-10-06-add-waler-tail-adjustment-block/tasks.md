# Tasks

## 實作前閱讀

- **Task Group 0**：讀 `proposal.md`「Archived baseline coordination」、`design.md` Decision 6、目前 main `waler-plan-evaluation` spec，以及 `openspec/changes/archive/2026-10-06-expand-global-waler-candidate-pool/` 的 proposal、design Decision 8 與兩份 delta specs。
- **Task Group 1**：讀 `design.md` Decision 1，及 spec「圍令以單一尾端 adjustment block 與 Gap 完成需求長度」的 `16450 mm`、多解、Gap 等號與無解 scenarios。
- **Task Group 2**：讀 `design.md` Decision 2／4，及兩個 MODIFIED Requirements；同時回讀 `docs/SOLVER.md` 的 Waler evaluation pipeline。
- **Task Group 3**：讀 `design.md` Decision 3／5，及 spec 的正式 pieces、Automatic／manual、既有結果 scenarios。
- **Task Group 4**：讀 `design.md` Decision 7 與 Backward Compatibility；只有對應 regression 失敗時才讀 export／adoption main specs。
- **Task Group 5**：讀 proposal「Expected recomputation difference」、`design.md` Decision 4／6，及已封存 `expand-global-waler-candidate-pool` 所建立的 retention contract；不得以本 change 改搜尋政策。
- **Task Group 6**：回讀 proposal「不變事項／Out of Scope」、design Architecture Alignment、兩個 MODIFIED Requirements，再更新 long-term docs 與執行完整驗證。

## 0. 確認已封存的 Global Waler 基線

- [x] 0.1 確認 `expand-global-waler-candidate-pool` 已位於 archive、其 delta 已同步 main spec，並檢查目前工作樹中的 `wales.py`、`solver_search.py`、`optimize_waler.py` 與相關 tests；這些既有 retention 修改 SHALL 作為整合基線，不得覆寫。（對應 Design D6）
- [x] 0.2 以目前 main `waler-plan-evaluation` spec 重新比對本 change 的兩個 MODIFIED Requirements，確認完整保留 `Global output retention 擴大`、Single Top 5、Global expanded retention 與 `搜尋政策與評估分離` 契約；執行 `openspec validate add-waler-tail-adjustment-block --strict`，通過後才修改 production code。（對應 Design D6）

## 1. 建立尾端 resolver 與數值邊界

- [x] 1.1 在 `tests/test_wales_tail_adjustment.py` 先加入 pure resolver tests：覆蓋 `required_length` 對 `500 mm` grid 的 `0～450 mm` residue 可完成、`451～499 mm` residue 無解、`12100／12000 → adjustment 0 + Gap 100`、`12180／12000 → adjustment 100 + Gap 80`、`12250／12000 → adjustment 100 + Gap 150`、`16450／16000 → adjustment 300 + Gap 150`、`11500 + 300 + 150 = 11950` 等號邊界、整長全零、fixed-Steel 無解與負值／非法參數；驗證結果依 `(tail_adjustment != 0, tail_adjustment, -steel_length)` deterministic 排序。（對應尾端 Requirement、Design D1）
- [x] 1.2 在 `bracing_optimizer/algorithms/wales.py` 實作具名常數與 pure tail resolver，讓 `Config.__post_init__()` 由 resolver 取得 `steel_target_length`、`tail_adjustment`、`tail_gap`，且 candidate joint endpoint 仍在既有 `500 mm` grid；執行 `tests.test_wales_tail_adjustment` 驗證 adjustment 不進 genes／joints、Gap 上限包含 `150` 且拒絕 `151`。（對應 Design D1）
- [x] 1.3 加入 automatic Config regression，比對變更前後相同 required lengths 的 `steel_target_length`、candidate joint positions 與搜尋預算 metadata，確認本 change 只新增 tail completion、不改 material-derived discretization。（對應「既有分數與排序相容」、Design D1／4）

## 2. 將尾端合法性收斂到共用 evaluator

- [x] 2.1 在 `tests/test_waler_plan_evaluator.py` 先加入 evaluation contract tests，驗證 `WalerPlanEvaluation` 對合法／無解／steel-too-long inputs 回傳 canonical `tail_adjustment`、Gap 與既有穩定 issue codes／必要 facts，且任何 hard issue 仍使 allocation、ratio 與 local score unavailable。（對應尾端 Requirement 的無解／超長 scenarios、Design D2）
- [x] 2.2 修改 `evaluate_waler_plan()` 與其 hard-rule scanner，使實際 `sum(segments)` 經同一 resolver 產生尾端結果；沿用 `steel-total-short`／`steel-total-long` 機器 code 並補足 facts，不在 Application 另建合法性判斷，執行 evaluator focused tests。（對應 Automatic／manual 相同解析、Design D2）
- [x] 2.3 擴充 exact scoring regression：同 Steel plan 在變更前後仍合法時，assignments、purchase count、ratio、under-4000、stock groups、length variation、joint count 與 local score 必須 exact-equal；含 adjustment 的 plan 不得新增 assignment、材料分類或 score component。（對應「既有分數與排序相容」、Design D4）
- [x] 2.4 驗證 repair boolean probe 與正式 evaluator 使用同一 hard-rule traversal：repair 可 short-circuit，但對相同 plan 的可行／不可行 verdict 必須一致，且 repair steps、chromosome 與 search metadata 不變。（對應既有共用 evaluator contract、Design D2／4）

## 3. 統一 Automatic／Manual 結果投影與 cache

- [x] 3.1 修改 Waler automatic result projection，從 evaluation 產生 `steel_length`、`tail_adjustment`、Gap 與 `pieces = Steel... + optional ("shim", adjustment)`；加入 invariant tests 驗證精確總長等式、最多一塊、固定尾端、`tail_adjustment = 0` 時無 `shim`。（對應正式 pieces scenarios、Design D3）
- [x] 3.2 修改 `bracing_optimizer/application/plan_editing.py`，讓 `WalerPlanEditing.recalculate()`／legality details 只投影 evaluation 的 canonical tail，不再固定歸零或以 `required - steel` 自行重算；在 `tests/test_plan_editing.py` 驗證 Automatic／manual 對 `16450 mm`、多解、無解與既有 legacy payload 得到相同結果。（對應 Automatic／manual 與既有結果 scenarios、Design D2／3）
- [x] 3.3 bump `OptimizeWaler.CACHE_SCHEMA` 並更新 cache-key tests，驗證舊「無 adjustment」memory 不會命中新規則，而 request tuple 的幾何／材料／ratio shape 與 Single memory workflow 不變。（對應 deterministic ordering、Design D5）
- [x] 3.4 在人工編輯 UI／service regression 驗證使用者仍只編輯 Steel segments，adjustment 自動顯示在尾端且不成為中間可編輯 segment；確認 invalid edit 不提交、既有 commit／dirty semantics 不變。（對應人工流程不得插入中間、proposal 不變事項）

## 4. 驗證結果生命週期與 terminal consumers

- [x] 4.1 在 `tests/test_project_results.py` 與相關 persistence tests 建立 canonical 非零 adjustment result，驗證 adoption、serialize／deserialize、save／load 完整保留 `tail_adjustment`、Gap 與尾端 `("shim", length)`，同時保留 legacy 任意尺寸結果的 load-as-is、recalculate-on-edit 行為；不得提升 schema。（對應既有結果重新計算、Design D3／Backward Compatibility）
- [x] 4.2 擴充 Main Preview／result details／材料摘要 tests，驗證畫面順序為 `Steel → adjustment → Gap`，調整塊以獨立項目顯示但不混入 Steel assignments、Short／Mid／Long／Out counts 或比例；只有測試證明現有 consumer 不符時才最小修改 owner module。（對應尾端位置與 scoring isolation、Design D7）
- [x] 4.3 在 `tests/test_excel_result_export.py`、`tests/test_dxf_result_export.py` 與 export validation tests 驗證 `16450 mm` canonical plan 的 pieces／Gap 總長正確、調整塊位於尾端、沒有額外 joint，且舊 payload fallback 仍可匯出；不得新增 export schema 或另算合法尺寸。（對應正式 pieces、Design D7）

## 5. 保護 Single／Global 搜尋與 operation semantics

- [x] 5.1 執行並擴充 `tests/test_optimize_waler.py`，驗證 Single 仍沿用既有 Top 5、stage escalation、population、generation、seed、repair、merge、tie-break 與 diagnostics；只允許因 adjustment 使候選合法而改變候選內容。（對應「既有分數與排序相容」、Design D4／6）
- [x] 5.2 執行並擴充 `tests/test_optimize_waler_global.py`、`tests/test_waler_global.py`，驗證 Global retention profile、rank > 5、material-signature merge、Exact DP objective、逐支選擇與 `shared_inventory_optimized` 語意維持已封存契約，且 adjustment 不進 material signature。（對應 proposal Archived baseline coordination、Design D4／6）
- [x] 5.3 擴充 no-legal-solution、exception 與 cancellation regressions，驗證新增 tail completion 不會讓 failed／cancelled Single 或 Global operation 採用部分 candidates、diagnostics 或 results；執行 `tests.test_solver_cancellation` 及相關 reliability suites。（對應不變的 failure／cancellation semantics）
- [x] 5.4 在 `tests/test_optimize_waler.py` 直接載入原始 `project_cases/Y05車站第一層支撐/project.json` 與 `project_cases/Y29車站第一層支撐/project.json`，經 `ProjectDataModel`／`WalerInputBuilder` 建立輸入，不得呼叫 `repair_test_lengths()`、改寫端點或修補 `total_length`。驗證 Y05 W2 `16950 → 16500 Steel + 300 adjustment + 150 Gap`、Y29 W4 `22400 → 22000 Steel + 300 adjustment + 100 Gap` 均由舊規則無解改為新規則可解；另以 Y29 W5 `12200 → 12000 Steel + 100 adjustment + 100 Gap` 鎖定短差 `200 mm` 原本可解但尾端 projection 預期改變。三案皆記錄並 assertion 實際採用的 adjustment、Gap 與正式 pieces 順序。（對應 proposal Expected recomputation difference、尾端 Requirement、Design D1／D3）

## 6. 文件、回歸與 OpenSpec 驗證

- [x] 6.1 在所有行為測試通過後最小更新 `docs/DOMAIN.md`：將「Waler 不使用 adjustment block」改為單一尾端 `100／150／200／300 mm`、完成長度等式、`0 <= Gap <= 150`、不形成 joint／不進 Steel allocation與 scoring；確認 Support Shim 規則維持獨立。（對應 long-term Domain truth）
- [x] 6.2 最小更新 `docs/SOLVER.md` 的 Waler target／evaluation／manual editing sections：記錄共用 resolver、automatic endpoint、canonical result fields、cache invalidation與 unchanged search／score／Global retention；Architecture／Workflow ownership未變時不得修改 `docs/ARCHITECTURE.md`／`docs/WORKFLOW.md`。（對應 long-term Solver truth、Design Architecture Alignment）
- [x] 6.3 執行 focused suites：`tests.test_wales_tail_adjustment`、`tests.test_waler_plan_evaluator`、`tests.test_plan_editing`、`tests.test_optimize_waler`、`tests.test_optimize_waler_global`、`tests.test_waler_global`、`tests.test_project_results`、Excel／DXF export與相關 Main tests；不得刪除測試或降低 assertion。（final focused regression）
- [x] 6.4 執行 Solver regression 與 boundary tests，至少包含 `tests.test_application_domain_boundaries`、`tests.test_solver_cancellation`、`tests.test_solver_dialog_operation_gate` 及受影響的 Global persistence／apply／reliability suites；確認 Algorithms 未依賴 Application／Presentation、Presentation 未複製 adjustment 規則。（final architecture／solver regression）
- [x] 6.5 執行 `openspec validate add-waler-tail-adjustment-block --strict`，再使用 OpenSpec verify workflow 對照 proposal、design、spec、tasks 與實作；確認沒有超出 Out of Scope、沒有遺失已協調的 Global retention requirement，且所有 tasks 完成或有明確核准例外後才宣告可 archive。（OpenSpec implementation verification）
