# Tasks

## 實作前閱讀

- 第 1 組先確認 `align-support-shim-joint-validation` 與 `unify-waler-plan-evaluation` 的 archive artifacts 及兩份主規格 Requirement 已存在，再讀 proposal 的「不變事項」、兩份 delta specs、design Decision 1～4 與 docs/SOLVER.md 對應段落。
- 第 2 組先讀 waler-plan-evaluation 的 explicit empty／missing scenarios 與 solver_input_builder inventory policy。
- 第 3 組先讀 support-shim-joint-validation 的尺寸與 issue priority，以及既有 scoring compatibility Requirement。
- 第 4～5 組只在 exact regression 通過後更新長期文件與驗證。

## 1. 鎖定 scoring 與 caller 語意

- [x] 1.1 Audit 所有 Waler Config.purchasable_lengths callers，分類 omitted、預設材料與明確空集合，並以 characterization tests 鎖定各 caller 目前 intent 及合法 plan score／排序。
- [x] 1.2 為 Support 自動候選、合法 direct-call、Jack 700、Shim 145 與多 issue layouts 建立 automatic／manual／direct-call 基準，記錄 candidate signatures、排序、score、penalty、breakdown、reason 與 valid；驗證自動候選只含 JACK_LENGTH／SHIM_LENGTHS 且修改前後集合、分數、排序 exact 不變，並明確鎖定人工或 direct-call 錯誤尺寸 layout 的預期差異只為 valid → invalid、加入既有 invalid penalty 及其 total score 變化，其餘 score components 必須 exact 不變。若自動候選可產生錯誤尺寸，立即停止並回報，不進入 Task 3。

## 2. 修正 Waler resolved material context

- [x] 2.1 在 bracing_optimizer/application/solver_input_builder.py 明確解析未填材料規格為既有預設料長與每種 99 支，保留使用者輸入數量（例如 5），並以 tests/test_solver_input_builder.py 驗證三種情境。
- [x] 2.2 在 bracing_optimizer/algorithms/wales.py 將 omitted 與 explicit empty 分開，確保空集合不被 __post_init__ fallback 覆蓋；以 tests/test_waler_plan_evaluator.py 驗證 core 不執行 allocation／local score、automatic candidate 沿用既有 invalid penalty 與排序規則，以 tests/test_optimize_waler.py 驗證全部候選 invalid 時 Single Waler 回報 no_legal_solution 而不拋例外，並以 tests/test_optimize_waler_global.py 驗證 Global Waler 回傳 invalid solution／failed-Waler diagnostics 且不進入 Exact DP；另驗證 omitted 與空白 Material Spec 保持既有結果。

## 3. 統一 Support 尺寸 verdict

- [x] 3.1 在 bracing_optimizer/algorithms/support.py 使用既有 JACK_LENGTH／SHIM_LENGTHS 新增具名 size issues，並於 tests/test_support_waler_type_rules.py 測試 600 Jack、100／150／200／300 Shim 合法，700 Jack 與 145 Shim invalid，0 Shim 仍表示 absent；錯誤尺寸須套用既有 invalid-candidate penalty，不得新增權重或公式。
- [x] 3.2 將 Jack count → Jack size → Shim count → Shim size → placement → gap → forbidden joint → Steel length 的 issue composition 集中到共用 evaluator，驗證 gate 只影響 reason；自動候選與不涉及新 size issue 的 layouts 之 score／penalty／breakdown／排序及 iteration-order 結果 exact 不變，錯誤尺寸 layout 則只允許既有 invalid penalty 與 total score 的預期變化。
- [x] 3.3 在 bracing_optimizer/application/plan_editing.py 移除 Jack／Shim 尺寸的平行 verdict 分支，改由 shared core issues 投影 SupportPieceValidation；保留 basic normalization rejection，並以 tests/test_plan_editing.py 與 tests/test_optimize_support_zone.py 驗證人工 invalid plan 仍可保存、automatic／manual／headless verdict 一致且 Presentation 不覆寫結果。

## 4. 同步長期文件

- [x] 4.1 在行為驗證完成後更新 docs/SOLVER.md 的 Waler material context 與 Support size／priority 說明；若 docs/DOMAIN.md 已把尺寸列為 hard constraint則只校正連結，避免建立第二份數值 truth。

## 5. 整體驗證

- [x] 5.1 執行 solver_input_builder、Waler plan editing／Single optimization／Global optimization、Support plan editing／optimization 與 real drawing fixture targeted tests，確認所有新增 scenarios、Support 自動候選 exact regression、錯誤尺寸 invalid penalty，以及 Waler 空集合無合法方案但不拋例外的 failure contract。
- [x] 5.2 執行完整 Solver regression 與 full test suite，確認材料比例、數量評分、candidate count、Beam Width、Random Seed、搜尋階段與 persistence 無回歸。
- [x] 5.3 執行 openspec validate align-solver-validation-contracts --strict 與 openspec verify，確認只新增尺寸合法性及空集合 contract，沒有建立採購／庫存功能、修改既有 invalid penalty 公式或調整搜尋評分政策。
