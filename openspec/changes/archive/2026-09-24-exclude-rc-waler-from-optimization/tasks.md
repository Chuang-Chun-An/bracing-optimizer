# Tasks

## 1. 建立一致的 Application eligibility policy

- [x] 1.1 在 `bracing_optimizer/application/optimize_waler.py`（或同層最小共用模組）加入單向 RC Waler exclusion／partition policy，使用 trim + case-insensitive `RC` 判定，並在 `tests/test_optimize_waler.py` 驗證 RC、大小寫／空白、blank、自訂規格與已知 Steel 規格邊界；測試不得把所有 not-RC 自動分類為 Steel。
- [x] 1.2 在 `OptimizeWaler.execute()` 的 algorithm config／search 之前套用防禦性 RC rejection，並以 mock/spy 驗證 RC request 不會呼叫 `wales.evolve()`、Steel request 行為不變。

## 2. 排除 Global Waler use case 中的 RC

- [x] 2.1 修改 `bracing_optimizer/application/optimize_waler_global.py`，以共用 policy 將 RC 從 `waler_order`、local optimization、candidate groups、diagnostics scope 與 selected results 排除，並在 `tests/test_optimize_waler_global.py` 驗證混合集合只呼叫 non-RC local optimizer且既有 validation 語意不變。
- [x] 2.2 為全 RC input 建立 algorithm-free no-op／invalid application result，並驗證不建立 local optimizer、不執行 global selector且不產生可提交結果。
- [x] 2.3 執行 `python -m unittest tests.test_optimize_waler tests.test_optimize_waler_global tests.test_waler_global tests.test_waler_global_reliability`，確認 eligibility 與既有 Steel global behavior 通過。

## 3. 對齊 Main 的 Single／Global workflow 與 result adoption

- [x] 3.1 修改 `main.py::_open_waler_solver()`，讓 `WalerSelectionDialog` 僅收到 eligible non-RC IDs；全 RC 時提供明確訊息並在開 Dialog／worker 前返回，以 UI workflow test 驗證 results 與 operation state 不變。
- [x] 3.2 修改 `main.py::_open_waler_global_solver()`，讓 missing-inventory check、人工修改覆蓋確認與 `WalerGlobalSolverDialog` inputs 僅涵蓋 eligible non-RC Waler；以混合 RC／non-RC 測試驗證 RC 無庫存不阻擋其他 Waler，且覆蓋確認不列 RC。
- [x] 3.3 補上全 RC Global workflow regression，驗證不開 Dialog、不啟動 worker、不呼叫結果採用，並保留既有 Project results／busy state。
- [x] 3.4 擴充 `ProjectResultModel.stage_waler_global_result()` 與 `main.py::_apply_waler_global_result()` 的 staging contract，傳入目前 Project 的 RC Waler IDs，於 staged copy 同時移除 selected non-RC 舊結果與全部 historical RC Waler results；在 `tests/test_waler_global_apply.py` 驗證 W1／W3 被取代且 W2 RC 舊結果被清除。
- [x] 3.5 在 `tests/test_waler_global_apply.py` 補齊 atomic failure regression：Solver invalid／staging failure／commit failure 保留 historical RC result，commit 後 UI refresh failure 不恢復已清除的 RC result。

## 4. 驗證結果失效與 Support contract

- [x] 4.1 在 `tests/test_main_project_editing.py` 補齊 Steel→RC、RC→Steel 與 no-op／失敗 material edit 測試，驗證成功變更會沿用現有完整 results、`solver_memory`、`support_candidate_cache` 失效，未成立的編輯不清除狀態。
- [x] 4.2 在 `tests/test_solver_input_builder.py` 與 `tests/test_support_waler_type_rules.py` 補齊 regression，驗證 RC Waler 仍存在於正式 Project／Waler build output，且 Support input 仍收到正確 RC 端部類型。
- [x] 4.3 執行 `python -m unittest tests.test_main_project_editing tests.test_solver_input_builder tests.test_support_waler_type_rules tests.test_project_service tests.test_project_results`，確認 result lifecycle 與 Support RC 行為未退化。

## 5. 文件與整體驗證

- [x] 5.1 在實作與測試成立後更新 `docs/DOMAIN.md`、`docs/SOLVER.md` 與 `docs/WORKFLOW.md`，記錄 RC 是正式構件但不參與 Waler 材料配置、Single／Global non-RC solve scope、Global adoption 的 historical RC result cleanup，以及材料切換的完整結果失效；檢查未把 exclusion 誤寫成 algorithm scoring 規則。
- [x] 5.2 執行 `python -m unittest discover -s tests` 與專案既有 boundary tests，確認 Steel Waler、Support Solver、Global result adoption、材料統計及 persistence regression 全部通過。
- [x] 5.3 執行 `openspec validate exclude-rc-waler-from-optimization --strict` 及 OpenSpec implementation verification，逐項核對 proposal、spec、design、tasks 與實作結果一致，且 `bracing_optimizer/algorithms/` 無本 change 的修改。
