# Tasks

## 1. Characterize Existing Dialog Lifecycles

- [x] 1.1 在 `tests/test_solver_dialog_close_policy.py`（新增）建立三種 Dialog 的輕量測試 fixture／fake，明確觀察 running flag、`destroy()`、UI bridge close、結果／operation state 與提示，不啟動真實 Tk mainloop；以測試可重現 Global Waler 現有 close guard，並在實作前揭露 Support／Single Waler 缺少 guard 的差異為驗證。
- [x] 1.2 逐一核對 `bracing_optimizer/presentation/dialogs/support_solver_dialog.py`、`waler_solver_dialog.py`、`waler_global_solver_dialog.py` 的 worker start、success、failure、thread-start failure、cache/no-worker、close handler 與 result adoption 出口，並確認測試 fixture 覆蓋所有實際出口且未假設 worker cancellation。

## 2. Establish the Minimal Running Close Policy

- [x] 2.1 在三個 Dialog class 內採用 Design 定義的本地 `_calculation_running` contract，保留 Global Waler 現有實作為 reference，且不以 Run button 或 `WalerSolverBusyGuard` 作為 close source of truth；由 focused state-transition tests 驗證只有真正的背景 worker lifecycle 會進入 running。
- [x] 2.2 保持 close guard 為各 Dialog 的局部 Presentation lifecycle 邏輯；只有在確認完全無狀態且不改變各自 completion ordering 時才可在 `bracing_optimizer/presentation/dialogs/solver_dialog_base.py` 抽出微型 helper，並由 `tests/test_presentation_module_boundaries.py` 驗證未引入新的 layer dependency。

## 3. Apply Policy to Support Solver Dialog

- [x] 3.1 修改 `bracing_optimizer/presentation/dialogs/support_solver_dialog.py`，在 worker 實際啟動前進入 running、於 thread-start failure 回復 non-running，並讓 worker success／failure 透過 UI-thread finish handling 在既有結果／diagnostics／callback 處理完成後以 `finally` 回復 non-running 與 Run button；以 Support success、Solver failure、display/adoption exception 及 start failure tests 驗證。
- [x] 3.2 修改 Support `_on_close()`，在 running 時不呼叫 `_close_ui_bridge()`、不 destroy Dialog、不中斷 lifecycle 且不修改 result／operation state，non-running 時維持既有關閉行為；以 WM close 與既有 Close button 共用 policy、重複 close request 及完成／失敗後可關閉的 tests 驗證。

## 4. Apply Policy to Single Waler Solver Dialog

- [x] 4.1 修改 `bracing_optimizer/presentation/dialogs/waler_solver_dialog.py`，在前置檢查與 busy lease 成功後、worker 實際啟動前進入 running，於 thread-start failure 與 UI-thread success／failure finish handling 可靠回復 non-running，同時保留既有 lease release、result display/adoption 與 error semantics；以 success、Solver failure、display/adoption exception 及 start failure tests 驗證。
- [x] 4.2 修改 Single Waler `_on_close()`，在 running 時保留 Dialog、bridge、lease lifecycle 與 result／operation state，non-running 時維持既有關閉行為；以 running close、重複 close、完成／失敗後 close tests 驗證。
- [x] 4.3 保留 Single Waler 既有 solver-memory/cache-hit 同步路徑為 non-running，且不改其結果顯示／採用行為；以未建立 worker、close 仍可執行及 cache result 不變的 focused test 驗證。

## 5. Preserve Global Waler Reference Behavior

- [x] 5.1 檢查 `bracing_optimizer/presentation/dialogs/waler_global_solver_dialog.py`，保留現有 `_calculation_running` close guard、warning、worker finish 與自動採用順序，不因統一政策而重寫 lifecycle；以 `tests/test_waler_global_reliability.py::test_close_is_blocked_while_global_solver_is_running` 持續通過驗證。
- [x] 5.2 擴充 Global Waler regression coverage，驗證 success、Solver failure 與 thread-start failure 後恢復 close permission，且 running close request 不修改 result／operation state或 result adoption semantics；執行對應的 `tests/test_waler_global_reliability.py` 測試驗證。

## 6. Complete Cross-Dialog Close-Policy Coverage

- [x] 6.1 在 `tests/test_solver_dialog_close_policy.py` 以參數化或等價的小型案例驗證三種 Dialog 在 running 時都拒絕 close、non-running 時都正常 close，並驗證 running close 不關閉 UI bridge、不 destroy、不取消／join worker；執行該測試檔驗證。
- [x] 6.2 驗證三種 Dialog 從 running 進入 finished 或 failed 後均恢復 close permission，且 Support／Single Waler 的 UI completion callback 發生例外時仍解除 running；執行 `tests/test_solver_dialog_close_policy.py` 與 `tests/test_waler_global_reliability.py` 驗證。
- [x] 6.3 執行 `.venv\Scripts\python.exe -m unittest tests.test_solver_dialog_close_policy tests.test_waler_global_reliability tests.test_interface_presentation tests.test_presentation_module_boundaries -v`，確認 focused Presentation、thread bridge 與 boundary regression 全部通過。

## 7. Update Long-Term Workflow Truth

- [x] 7.1 在功能與測試完成後更新 `docs/WORKFLOW.md`，將 Support／Single Waler 執行中仍可關閉的 current behavior／gap 改為三種 Dialog 均在 running 時阻擋關閉，並明確保留「不提供 worker cancellation」；以文件內容與已通過的行為測試一致為驗證，且不修改 `docs/ARCHITECTURE.md`、`docs/DOMAIN.md` 或 `docs/SOLVER.md`。

## 8. Regression Verification

- [x] 8.1 執行 `.venv\Scripts\python.exe -m unittest discover -s tests -v` 完整 regression suite，確認 Solver algorithms、search、scoring、candidate generation、progress、result adoption 及其他既有行為未受影響。
- [x] 8.2 檢查最終 diff 僅包含本 change 的 Presentation lifecycle、測試與 `docs/WORKFLOW.md` 更新，並確認沒有 worker cancellation、Solver／result semantics 變更或大型 UI framework refactor。

## 9. OpenSpec Verification

- [x] 9.1 依 `prevent-closing-running-solver-dialogs` 的 Proposal、Spec、Design 與 Tasks 逐項核對實作，執行 OpenSpec implementation verification，確認所有 requirement scenario 有對應證據且無未完成 task。
- [x] 9.2 執行 `openspec validate prevent-closing-running-solver-dialogs --strict`，確認 implementation 完成後 change artifacts 仍通過 strict validation。
