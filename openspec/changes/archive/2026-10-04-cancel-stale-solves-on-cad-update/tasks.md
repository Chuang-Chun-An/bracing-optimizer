# Tasks

## 實作前閱讀

- **第 1 組**：先讀 proposal「主要流程／不變事項」、design D1～D2 與 spec「有效 CAD mutation 使已登記的 Solver snapshot 失效」「stale operation 不得採用任何輸出」。
- **第 2 組**：先讀 design D2／D4、spec「三種 Solver 合作式結束」，並依子任務選讀 `docs/SOLVER.md` 的 Support 第 3～7 節或 Waler 第 8～10 節。
- **第 3 組**：先讀 design D1／D4～D5、spec「stale Dialog 不得啟動或重用舊 input」與 modified `global-waler-result-adoption` Requirement。
- **第 4 組**：先讀 design D3／D5、`docs/WORKFLOW.md`「CAD Event Workflow」，以及 spec「不改變 Project 的 CAD event 不影響 Solver lifecycle」「取消後不自動重跑」。
- **第 5 組**：只在實作與 targeted tests 通過後進行；回看 proposal Out of Scope，確認沒有加入一般使用者取消或自動重跑。

## 1. 建立 snapshot／operation 與 cancellation 基礎 contract

- [x] 1.1 在 `bracing_optimizer/algorithms/` 新增不依賴 Application／Tkinter 的 read-only cancellation token、source 與 `SolverCancelled` control outcome；加入 thread-safe set、重複 set、未取消 no-op 與 raise checkpoint 單元測試，驗證 Algorithms dependency boundary。
- [x] 1.2 在 `bracing_optimizer/application/` 新增 `SolverOperationRegistry`／opaque snapshot handle／execution identity／completion disposition，涵蓋 `open → running → open／stale → closed`、`invalidate_open_and_running("cad_update")`、thread-start rollback與 idempotent cleanup；單元測試 open handle無 worker cancellation、running handle set token、多 handle、舊 execution與重複 completion，並執行 application boundary tests。
- [x] 1.3 在 Main session建立單一 registry，於 `build_all`／`build_zone` 成功產生 snapshot時立即註冊，再將同一 handle傳入 Solver Dialog；測試 Single Waler selection期間也已受 registry保護，selection取消、precheck失敗與Dialog未建立都會關閉 handle，且三個 Dialog不重複登記第二個 handle。

## 2. 讓三種 Solver 在安全 checkpoint 合作式退出

- [x] 2.1 修改 `OptimizeSupportZone`、`support.py` 與必要的 `solver_search.py` 呼叫邊界以傳遞 token，於 config／候選批次／Phase 2 stage與 beam外層加入 checkpoint；將 candidate cache 寫入改為 operation-local staged output，測試 cancelled outcome 無 partial solution／diagnostics／session cache mutation，並以既有 deterministic fixtures exact 比對未取消結果。
- [x] 2.2 修改 `OptimizeWaler` 與 `wales.py`，於 stage、initial-population 批次、generation與 result assembly 邊界加入 checkpoint；測試取消不回傳 partial Top 5，且未取消時 score、排序、seed history與 diagnostics 完全符合既有 regression。
- [x] 2.3 修改 `OptimizeWalerGlobal` 與 `waler_global.py`，把同一 token 傳入每個 local `OptimizeWaler`，並在 local Waler／exact-DP group邊界加入 checkpoint；測試 local與global階段都可 cancelled、沒有 partial adoption，且未取消 global solution／diagnostics不變。

## 3. 將 Dialog output 與 cache 接到 operation gate

- [x] 3.1 修改 `support_solver_dialog.py` 接收 Main已註冊的 snapshot handle，讓 Run啟動 execution且 progress／completion capture handle + execution identity；只在registry disposition為`adoptable`且既有Main mutation guard允許時提交solution、diagnostics與staged candidate cache，並測試opened-not-run CAD stale會立即停用Run、顯示重新開啟指引且不建立worker。
- [x] 3.2 修改 `waler_solver_dialog.py` 接收既有 snapshot handle，把 `_save_solver_memory` 移至同時通過registry disposition與既有Main mutation guard的UI-thread adoption boundary後執行，保留 worker `finally`才釋放 lease；測試 opened-not-run stale、late callback或unresolved guard拒絕時不寫result／memory、normal success仍採用Top 5、thread-start failure清理execution但不提前釋放其他lease。
- [x] 3.3 修改 `waler_global_solver_dialog.py` 接收既有 snapshot handle，在 valid solution進入 atomic apply前檢查registry disposition並保留既有Main mutation guard；測試 opened-not-run stale、stale或unresolved-blocked valid solution不commit、normal valid solution仍立即採用，且 Global local `OptimizeWaler` 執行前後 Single Waler `solver_memory` 完全不變。
- [x] 3.4 對三個 Dialog 統一 CAD-stale UI：open時立即停用 Run；running時等待 worker cleanup後恢復 close permission；兩者都顯示「請關閉後重新開啟 Solver」、保持 Run disabled且不自動 destroy／reopen。擴充 `test_solver_dialog_close_policy.py` 驗證一般 running close仍只阻擋關閉、不觸發 token。
- [x] 3.5 為 Single／Global Waler 補上 stopping busy提示：舊 worker尚未到 checkpoint與 `finally`前，Main workflow entry及Dialog `try_acquire()` failure均拒絕新 worker並顯示「前一次計算正在停止，請稍後再試」；測試 lease未被強制釋放、同時最多一個 Waler worker，且 worker `finally`後才可取得新 lease。

## 4. 接入 CAD mutation ordering 與交錯測試

- [x] 4.1 在 `main.py::_apply_cad_event` 的 validation／mapping／no-op 判斷後、第一次 Project row mutation前呼叫 registry invalidate；擴充 `test_cad_builder_integration.py` 驗證有效 add／update會 stale所有 open／running handles、只對 running handles set token且不等待 worker，invalid／control cancel／no-op完全不改變任一 handle或Dialog Run狀態。
- [x] 4.2 新增 CAD ACK failure integration test，驗證沿用既有 unresolved guard：Project row／DXF state、input／result／cache invalidation與dirty outcome保留，unresolved event被記錄、CAD polling停止、save被阻止、相同event ID不重複套用；另驗證已stale operation的cancellation token維持已設定、不恢復、不採用晚到output且不自動重跑。不得在本change重作既有guard規則。
- [x] 4.3 新增 deterministic ordering tests：success callback先於 CAD 時結果隨 input invalidation清除；CAD先於 callback時 result、diagnostics、calculated time、dirty、Support cache與Single memory均不變；兩條路徑最終都沒有舊 input result。
- [x] 4.4 新增 Support、Single Waler、Global Waler 各自的 opened-not-run CAD mutation tests，驗證 builder成功即完成 registration、三個 Dialog都不啟動 worker且Run disabled；另測 invalid／control cancel／no-op時三個 Dialog仍可Run。
- [x] 4.5 新增三種 Solver各自及可建立的多-handle交錯測試，驗證 running cancellation、open-handle invalidation、idempotent cleanup、舊 execution callback隔離與使用者重新開啟後才取得新 snapshot identity；確認沒有 background thread直接操作 Tk widget。
- [x] 4.6 新增Support、Single Waler、Global Waler在ACK unresolved期間開啟並完成計算的integration tests：驗證Dialog開啟與Run不被新增阻擋、registry disposition可為`adoptable`，但既有mutation guard拒絕後result、diagnostics、calculated time、dirty、Support candidate cache與Single solver memory全部不變；三個Dialog都完成terminal cleanup、沒有未處理例外，並顯示專用「計算完成，但CAD ACK尚未完成，結果未採用」狀態而非一般Solver failure。

## 5. 長期文件與整體驗證

- [x] 5.1 在所有行為測試通過後更新 `docs/ARCHITECTURE.md` 的 state ownership、`docs/SOLVER.md` 的 cooperative checkpoint、`docs/WORKFLOW.md` 的 Solver／CAD ordering與 stale-result lifecycle；同步將 `docs/WORKFLOW.md`「14.2 Commit／rollback summary」中 CAD ACK failure仍寫為rollback的殘留描述修正為既有unresolved模型。驗證文件只描述已實作行為，且明列不改scoring／search policy／close semantics。
- [x] 5.2 執行 operation registry、三個 optimize use case、三個 Dialog、CAD integration、Global Waler adoption與 boundary targeted tests，確認 spec 每個 Scenario至少有一個直接測試或明確既有 coverage。
- [x] 5.3 執行完整 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`，確認 Solver regression、DXF、persistence、UI contracts與 architecture boundary無回歸。
- [x] 5.4 執行 `openspec validate cancel-stale-solves-on-cad-update --strict`，再使用 `$openspec-verify-change` 逐項核對 proposal、兩份 delta specs、design與tasks；確認沒有實作使用者取消、等待 worker後才套用 CAD、原 Dialog stale rerun或自動重跑。

