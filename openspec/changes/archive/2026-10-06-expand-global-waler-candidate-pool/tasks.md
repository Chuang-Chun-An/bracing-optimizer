# Tasks

## 實作前閱讀

- **Task Group 1**：讀 `proposal.md`「現況與目標」「不變事項」、`design.md` Decision 1，以及 `global-waler-candidate-pool` spec「Single Waler 候選輸出維持不變」。
- **Task Group 2**：讀 `design.md` Decision 2，以及 spec「Global Waler 必須保留材料多樣性的候選」中 stage／跨 stage scenarios；同時讀 `docs/SOLVER.md` 的 Waler staged search 與 candidate merge。
- **Task Group 3**：讀 `design.md` Decision 3，以及 spec 的 rank 6、8 signatures 與同-signature dominance scenarios。
- **Task Group 4**：讀 `design.md` Decision 4／6，以及 spec「全域流程仍須逐支生成與選擇」「Global 候選擴大不得改變既有選擇規則」與 rank 6+ 成果生命週期 scenario。
- **Task Group 5**：讀 `design.md` Decision 5，以及 spec「候選池範圍必須可診斷」。
- **Task Group 6**：僅在使用者明確接受 Task 5.3 數據後開始；讀 `design.md` Decision 7／8、spec「部分候選池不得進入全域選擇」，以及 `waler-plan-evaluation` delta 的兩個 MODIFIED Requirements。
- **Task Group 7**：回讀 proposal 完整 In／Out of Scope、兩份 delta specs、design Risks；不需閱讀等價鍵／template reuse、Support cache、DXF recognition 或其他無關 specs。

## 1. 建立明確的 Single／Global retention profile

- [x] 1.1 在 `tests/test_optimize_waler.py` 先加入 retention contract tests，以同一組超過 5 個合法 unique stage results 驗證預設 Single 仍輸出 Top 5、Global profile 可輸出超過 5 個，且現有 callers 不傳 profile 時行為完全不變。（驗證：Single Waler 候選輸出維持不變；Design D1）
- [x] 1.2 在 `bracing_optimizer/application/optimize_waler.py` 新增具型別的 `SINGLE_TOP_5`／`GLOBAL_FINAL_POPULATION` execution profile，設為 keyword-only 且預設 Single；保持 `OptimizeWalerRequest`、`build_cache_key()` tuple shape 與 Single memory contract 不變，執行 `tests.test_optimize_waler`。（驗證：waler-plan-evaluation「搜尋政策與評估分離」）
- [x] 1.3 在 `bracing_optimizer/application/optimize_waler_global.py` 明確以 Global profile 呼叫每支 `OptimizeWaler`，並加入 mock assertion 證明 Global caller opt-in、Single Dialog／其他 callers 不會取得 Global profile。（驗證：profile ownership 位於 Application，不由 Presentation 推導）

## 2. 收集已執行 stages 的完整 final-population 候選

- [x] 2.1 在 `tests/test_optimize_waler.py` 建立至少 8 個合法完整-signature unique results 的 stage fixture，先驗證 Global stage output 不受 `top_n=5` 截斷，而 Single 同 fixture 仍只有 5 個。（驗證：Global 取得超過五個不同材料組成；Design D2）
- [x] 2.2 調整 `bracing_optimizer/algorithms/wales.py` 的 final-result projection，使呼叫端可選擇既有 Top N 或 final population 的全部合法完整-signature unique results；不得修改 population、generations、seed、repair、evaluator、fitness 或 generation loop，並執行 Waler algorithm focused tests。（驗證：只改 retention、不改 search budget）
- [x] 2.3 調整 `bracing_optimizer/algorithms/solver_search.py`／`OptimizeWaler._run_search()` 的跨 stage merge，讓 Global 依完整 solution signature union 所有已執行 stages、保留較低 score 代表並以既有 tie-break deterministic 排名；Single 仍切成 5。（驗證：STANDARD＋ENHANCED union、未執行 DEEP 不計入、rank 可大於 5）
- [x] 2.4 加入 stage escalation regression，確認 retention profile 不改 `assess_waler_stage()`、停止條件、實際執行 stage 清單、random seeds 或 diagnostics 的搜尋品質判定。（驗證：既有 staged-search policy 不變）

## 3. 建立 Global material-diverse candidate groups

- [x] 3.1 在 `tests/test_optimize_waler_global.py` 建立 rank 1～5 不含目標 signature、rank 6 含目標 signature 的 fixture，先驗證 Global group 保留 rank 6 且既有 Exact DP 可選中它。（驗證：Local rank 6 改善全場材料比例）
- [x] 3.2 在 `bracing_optimizer/application/optimize_waler_global.py` 以跨 stage deterministic order 建立 `WalerGlobalCandidate`，rank 1 的 score 作為 local regret 基準，沿用 `merge_equivalent_candidates()` 對相同 material signature 保留最低 regret 代表；不得新增固定 Top N。（驗證：Design D3）
- [x] 3.3 擴充 `tests/test_waler_global.py`／`tests/test_optimize_waler_global.py`：8 個不同 signatures 全部保留、同 signature 較差候選被移除、Out distance 不同不得誤合併、tie 時沿用 deterministic rank。（驗證：material-signature dominance 唯一性）

## 4. 維持逐支搜尋與既有 Exact DP

- [x] 4.1 在 `tests/test_optimize_waler_global.py` 加入兩支有效輸入完全相同的 Waler，驗證 optimizer factory／`execute()` call count 仍為 2、local records 與 candidate groups 各為 2；production code 不得加入等價 key、group、template 或 reuse cache。（驗證：全域流程仍須逐支生成與選擇；Design D4）
- [x] 4.2 新增 N 支 Waler、每支超過 5 個候選的整合測試，確認 `waler_order`、DP stage 數、selected count 均為 N，材料 counts、Out distance、local regret、changed count 與 rank path 逐支累計。（驗證：逐支 DP contract）
- [x] 4.3 鎖定 `solve_global_waler_candidates()` objective tuple、state key／merge、tie-break 與 `shared_inventory_optimized is False`，確認擴池只改輸入選項，不改 Algorithms 的全域選擇規則。（驗證：Global 候選擴大不得改變既有選擇規則）
- [x] 4.4 在 `tests/test_waler_global_apply.py`、`tests/test_waler_global_persistence.py` 與 `tests/test_waler_global_reliability.py`（或同責任的 Presentation test）加入 Exact DP 選中 rank 6 以上候選的端到端 regression：驗證正式採用後 `result_id`、`option_index`、`global_candidate_rank` 與 selected plan 正確；保存並重新載入後完全保留；Global Dialog 與成果樹顯示原 rank；人工 visibility 切換、材料摘要及 Excel／DXF export projection 均使用該 selected plan。另加入同一支 Waler 先執行並採用 Single、再執行 Global 選中 rank 6 以上候選的順序情境：精確比對該 Waler 的 result-ID key set，確認 Global ID 不與 Single 結果衝突且舊 Single IDs 已依既有 replacement semantics 移除；再以另一個 rank 6 以上結果重新執行 Global，確認前一個 Global rank ID 完整移除、只保留本次 Global ID，且其他 Waler／Support 結果不受影響。不得修改 Single `top_results[:5]`；若 regression 發現 ID 格式可能衝突、錯誤覆寫或舊 rank ID 殘留，先回報並暫停，不得自行修改 ID 格式或 replacement semantics。（驗證：Rank 6 以上候選完成成果生命週期；Design D6）

## 5. 補足候選池 diagnostics 與效能證據

- [x] 5.1 在 local diagnostics／stage records 增加具向後相容 default 的 `retention_profile`、每 stage solution-merge 後 count、跨 stage solution-merge 後 count，更新 serialization／formatter tests；不得從 log 文字反推。（驗證：Design D5）
- [x] 5.2 明確維持 Global `raw_candidate_count` 為 material merge 前 per-Waler 總數、`retained_candidate_count_after_signature_merge` 為 DP input 總數；必要時增加 per-Waler structured counts，並以多 stage／重複 solution／重複 material signature fixture 驗證三個邊界。（驗證：候選池範圍必須可診斷）
- [x] 5.3 以 `tests/sample_dxf_assets.py` 指向的 Y05、Y29、Y1A 等既有 fixture 執行 Global Waler，在相同輸入、搜尋政策與可重現條件下，分別記錄修改前基線（每支 Top 5）與修改後 profile 的：每支 Waler 候選數、送入 Exact DP 的候選總數、`transition_count`、`max_active_state_count` 與執行時間；附量測命令、環境、重複次數及 fixture × profile 對照表。每個 fixture 另列修改後候選數最多的前 3 支 Waler，包含 WalerID、Top 5 基線候選數、修改後候選數與差值；同數時依既有 `waler_order`。以每支 Waler 的完整 selected-plan signature 判斷修改後 Global 結果是否與基線不同，不得只比 local rank；若不同，列出 changed Waler IDs，並以 `total_short + total_mid + total_long + total_out` 為分母，列出全場 Short／Mid／Long／Out counts 與四分類比例的前後比較，且不得改變現有 objective ratio 定義。量測完成後不論結果如何，必須先回報全部數據並暫停，等待使用者判斷是否接受；未取得明確接受前不得開始 Task 6／7、宣告 change 完成，或自行加入固定 Top N、beam pruning、state truncation 等任何截斷。（驗證：Design D5 mandatory user decision gate）

## 6. 維持 failure、cancellation 與 evaluator 邊界（須先通過 Task 5.3 人工決策 gate）

- [x] 6.1 加入任一 Waler 無合法候選、stage projection exception、跨 stage merge exception 的測試，確認回傳既有 invalid／failure diagnostics、不呼叫 Exact DP、不發布或採用部分 groups。（驗證：部分候選池不得進入全域選擇）
- [x] 6.2 在 stage result projection、跨 stage merge、material-signature merge、每支 group 完成後與 Exact DP 前保留 cancellation checkpoints；擴充 `tests/test_solver_cancellation.py`，確認 cancelled operation 不採用部分 candidates／diagnostics／results。（驗證：既有 cancellation capability）
- [x] 6.3 擴充 `tests/test_waler_plan_evaluator.py`／`tests/test_optimize_waler.py`，以 exact equality 驗證合法性、allocation、score components、local score、invalid penalty 與相同候選集合排序不變；人工編輯與 evaluator 不取得 Global profile。（驗證：waler-plan-evaluation 兩個 MODIFIED Requirements；Design D8）

## 7. 文件、回歸與 OpenSpec 驗證（須先通過 Task 5.3 人工決策 gate）

- [x] 7.1 更新 `docs/SOLVER.md` 的 Single／Global Waler sections：Single 仍 Top 5；Global 收集各已執行 stage final population、跨 stage完整 signature union、每 material signature 最佳代表及 rank > 5；每支仍獨立搜尋，Exact DP objective 與 shared inventory 狀態不變。（驗證：long-term Solver truth）
- [x] 7.2 執行 focused regression：`tests/test_optimize_waler.py`、`tests/test_optimize_waler_global.py`、`tests/test_waler_global.py`、`tests/test_waler_global_reliability.py`、`tests/test_waler_plan_evaluator.py`、`tests/test_waler_global_persistence.py`、`tests/test_waler_global_apply.py`、`tests/test_solver_cancellation.py`，不得刪除測試或降低 assertion。（驗證：retention、DP、evaluation、persistence、adoption、cancellation）
- [x] 7.3 執行 `tests/test_application_domain_boundaries.py` 與 `tests/test_solver_dialog_operation_gate.py`，再依實際影響範圍擴大 Solver regression；確認 Presentation 未新增 profile／材料分類規則、Main 未新增 cache、Algorithms 未取得 Project／UI state。（驗證：Architecture Alignment）
- [x] 7.4 執行 `openspec validate expand-global-waler-candidate-pool --strict`，再使用 `$openspec-verify-change` 對照 proposal、兩份 delta specs、design、tasks 與測試證據；特別核對「Single Top 5、Global rank > 5、不同 signature 全保留、每支各算一次、DP 規則不變」後才標記完成。（驗證：OpenSpec implementation verification）
