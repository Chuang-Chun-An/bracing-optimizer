# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件「快速摘要」「現況與目標」「主要流程」「不變事項」；先確認本 change 只擴大 Global Waler 候選池，不處理等價圍令重用。
- **P0 現在必讀**：`specs/global-waler-candidate-pool/spec.md` 的「Global Waler 必須保留材料多樣性的候選」與「Single Waler 候選輸出維持不變」。
- **P1 實作前閱讀**：`design.md` 的 Decision 1（Single／Global retention profile）、Decision 2（跨 stage 候選合併）與 Decision 3（material-signature dominance）。
- **P2 需要時再讀**：修改 evaluator 邊界時讀 `specs/waler-plan-evaluation/spec.md`；處理 cancellation 時讀 `openspec/specs/solver-cad-update-cancellation/spec.md` 的 Global Waler scenarios。
- **本次可先跳過**：等價圍令 computation key、candidate pool template reuse、跨 operation cache、共享 inventory、result adoption 與 Project persistence；本 change 不改這些行為。

## 快速摘要

- 現況 Global Waler 直接沿用 Single Waler 的 Top 5，可能在全場材料比例計算前淘汰 local rank 較後、但材料組成有價值的候選。
- Single Waler 維持 Top 5；Global Waler 改用專用候選保留 profile，不在 stage 或跨 stage merge 套用 Single Top 5。
- Global 收集所有實際執行搜尋層級最終 population 中的合法 unique candidates；材料 signature 相同時只留 local score 最佳代表，不同 signature 全部保留。
- 每支 Waler 仍各自執行 local search；本 change 不判定等價圍令、不共用候選計算，也不新增 cache。
- 不改工程合法性、local scoring、GA stages／population／seed、Global Exact DP objective、共享 inventory policy 或正式結果採用流程。

## 現況與目標

本文件中的 **搜尋層級（stage）** 是 STANDARD／ENHANCED／DEEP 等 GA 搜尋預算；**材料 signature** 是 Global objective 使用的 Short／Mid／Long／Out counts 與 Out distance 組合。

| 行為 | Before | After |
| --- | --- | --- |
| Single Waler 候選 | 搜尋後最多 Top 5 | 完全相同：仍最多 Top 5 |
| Global stage 輸出 | 每個已執行 stage 最多先取 5 個 | 收集該 stage 最終 population 的全部合法、完整 solution-signature unique candidates |
| Global 跨 stage 合併 | 合併後再次取 Top 5 | 合併所有已執行 stages，依完整 solution signature 去重並 deterministic 排名，不套用固定 Top N |
| Global 材料候選 | 只從前 5 名再做 material-signature merge | 每個不同材料 signature 都保留；同 signature 只留 local score 最佳代表 |
| Local rank | Global 只能看到 1～5 | Global 可看到並選取 rank 6 以後候選 |
| 各支 Waler 搜尋 | 每支各算一次 | 完全相同：仍逐支各算一次，不做等價重用 |

## 主要流程

```text
每支 eligible non-RC Waler（仍逐支各自搜尋）
  → 依既有規則執行 STANDARD，必要時升級 ENHANCED／DEEP
  → 收集每個已執行 stage 最終 population 的合法 unique candidates
  → 跨 stage 依完整 Waler solution signature 去重並排定 local rank
  → 依 Global material signature 分組，同 signature 只留最佳代表
  → 將所有不同 signature 交給該 Waler 的 Global candidate group
  → Exact DP 仍依 waler_order 一支一支選擇並累計全場 objective
  → 既有 atomic result adoption
```

驗收例：若一支 Waler 的 local rank 1～5 未包含某種材料 signature，而 rank 6 包含該 signature，且它能讓全場材料比例更接近目標，rank 6 SHALL 進入 Global candidate group 並可被 Exact DP 選取。

## 不變事項

- Single Waler 的 Top 5、顯示、result adoption 與 `solver_memory` 不變。
- 每支 Global Waler 仍獨立執行 local search；不建立等價鍵、不分組、不重用其他 Waler 的 results。
- Global pool 只包含 GA 實際發現的候選，不宣稱窮舉所有可能 segmentation。
- GA stage 名稱、escalation、population、generations、Random Seed、repair 與停止條件不變。
- Waler evaluator、工程合法性、allocation、local score components／weights 與 deterministic tie-break 不變。
- Global Exact DP 的逐支 stage、state merge、objective ordering 與每支各選一個 candidate 的語意不變。
- 本 change 只擴大 Short／Mid／Long／Out 材料組成選項，不做跨 Waler 共享庫存配置；`shared_inventory_optimized` 仍為 `false`。
- Project schema、persistence、atomic adoption、rollback、refresh 與 UI operation lifecycle 不變。

## Why

Global Waler 必須從每支 Waler 的多種材料組成中選出全場較佳組合，但目前在進入全域選擇前就被 Single Top 5 截斷。擴大 Global 專用候選池可讓 Exact DP 看見搜尋已經找到的材料多樣性，而不為低機率的等價圍令重複情境增加額外機制。

## What Changes

### In Scope

- 為 `OptimizeWaler` 定義明確的 Single／Global candidate retention profile，預設仍是 Single Top 5。
- Global profile 收集每個實際執行 stage 最終 population 中所有合法且完整 solution signature 不重複的候選。
- 跨已執行 stages 合併候選、依既有 deterministic local ordering 排定可能大於 5 的 rank。
- 以既有 Global material signature 合併 globally equivalent candidates，同 signature 保留 local regret 最低代表，不同 signature 全部保留。
- 讓 Global Exact DP 可選取 rank 6 以後候選，同時維持既有 objective 與逐支計算。
- 增加 stage merge 前、完整 solution merge 後、material-signature merge 後的 candidate-count diagnostics。
- 新增 Single Top 5 相容、Global rank > 5、跨 stage union、material diversity、無共享 inventory、failure 與 cancellation regression tests。
- 實作完成後更新 `docs/SOLVER.md` 的 Single／Global candidate retention truth。

### Out of Scope

- 等價 Waler 判定、computation key、candidate pool template、跨 Waler local-result reuse 或相關 diagnostics。
- 跨 Run、Dialog 或 Project 的 candidate cache。
- 固定 Global Top 20／Top 50，或其他只依 local score 的二次截斷。
- 歷代所有 generation 的完整 candidate archive；本次邊界是各已執行 stage 的 final population。
- 調整 GA stage、population、generations、Random Seed、repair、escalation、local scoring 或工程合法性。
- 修改 Global Exact DP objective、state key／merge、Waler order 或每支選一個 candidate 的規則。
- 跨 Waler shared-inventory optimization。
- Project schema、persistence、result adoption、rollback 或 UI workflow 變更。

## Capabilities

### New Capabilities

- `global-waler-candidate-pool`: 定義 Global Waler 專用候選保留範圍、跨 stage 合併、材料 signature dominance、候選數 diagnostics 與效能安全邊界。

### Modified Capabilities

- `waler-plan-evaluation`: 明確區分 evaluator 相容性與本 change 經核准的 Global output-retention 變更；Single candidate count、合法性、score 與排序契約維持不變。

## Impact

- **Application**：修改 `bracing_optimizer/application/optimize_waler.py` 與 `optimize_waler_global.py`，傳遞 retention profile、收集跨 stage candidates、建立 Global groups 與 diagnostics。
- **Algorithms**：調整 `bracing_optimizer/algorithms/wales.py`／`solver_search.py` 的結果 projection，使 Global profile 可取得 final population 的完整合法 unique set；`waler_global.py` 的 material-signature merge 與 Exact DP objective 原則上沿用。
- **Presentation**：不新增候選規則；最多投影新增 diagnostics。
- **Domain／Infrastructure**：不修改工程規則、材料分類或 persistence schema。
- **Tests**：主要擴充 `tests/test_optimize_waler.py`、`tests/test_optimize_waler_global.py`、`tests/test_waler_global.py` 與 reliability／cancellation regressions。
- **Long-term truth**：更新 `docs/SOLVER.md` 的 Waler candidate-retention 與 Exact scope；Architecture、Domain 與 Workflow truth 不變。

## 尚未決定事項與重新評估條件

- Global 不另設固定候選上限；候選探索仍受既有 stage population 限制，material-signature merge 後才進 Exact DP。
- **取捨**：只收集每個已執行 stage 結束時的 final population；GA 過程中曾出現、但在 stage 結束前已被淘汰的方案不會保留。這次擴大的是既有搜尋結果的輸出保留範圍，不建立跨 generation archive。
- 以 Y05、Y29、Y1A 等既有 fixture 完成修改前 Top 5 與修改後的效能量測後，不論數據好壞都必須先回報並暫停，由使用者判斷是否接受；不得自行繼續後續工作，也不得自行加入固定 Top N、beam pruning 或其他截斷。
