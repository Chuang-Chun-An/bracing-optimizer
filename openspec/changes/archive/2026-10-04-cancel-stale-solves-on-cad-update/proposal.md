# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」「現況與目標」「主要流程」「不變事項」；`docs/WORKFLOW.md` 的「Solver Operations」「Result Lifecycle」「CAD Event Workflow」。
- **P0 現在必讀**：`openspec/specs/global-waler-result-adoption/spec.md` 的「合法全域結果須立即自動採用」；本 change 會為它加入 stale／cancelled 例外。
- **P1 實作前閱讀**：`design.md` 的 D1～D5；本 change 的 `solver-cad-update-cancellation` 全部 Requirements 與 `global-waler-result-adoption` 修改項目。
- **P2 需要時再讀**：加入 Support checkpoint 時讀 `docs/SOLVER.md` 第 3～7 節；加入 Single／Global Waler checkpoint 時讀第 8～10 節。
- **可以先跳過**：DXF recognition、Project schema compatibility、輸出與材料比例規格；本 change 不修改這些行為。

## 快速摘要

- Solver Dialog 在 worker 啟動前已持有 Project input snapshot；CAD add／update 可能讓「已開啟但尚未執行」的 Dialog 與正在背景執行的 worker 同時過期。
- 這次讓 Support、Single Waler、Global Waler 共用 snapshot lifecycle：先使所有已登記且尚未關閉的 handle 不可採用，並對 running worker 發出合作式取消，再沿用既有 CAD transaction 立即套用更新。
- worker 在安全 checkpoint 結束；即使 success callback 較晚到達，結果、診斷與 runtime cache 也一律丟棄。
- 取消後不自動重跑，且原 Dialog 不得再以更新前的 input snapshot 啟動第二次求解；使用者須由更新後的 Project 重新開啟 Solver。
- 不強制終止 Python thread，也不改變工程限制、scoring、候選數、Beam Width、Random Seed 或 Project persistence schema。

## 現況與目標

| 主題 | Before | After |
| --- | --- | --- |
| CAD mutation | 可在 Solver worker 執行中直接改變 Project | 先使所有已登記 snapshot handle stale，並只對 running worker 要求取消，再立即沿用既有 CAD commit／ACK 流程 |
| 已開啟但未執行 | Dialog 持有 snapshot，但沒有跨 Dialog 的失效機制 | CAD mutation 將 snapshot handle 標成 stale、停用 Run，要求關閉後重新開啟 |
| worker 停止 | 沒有取消 contract，可能繼續完整求解 | 在明確安全 checkpoint 合作式退出 |
| 晚到輸出 | callback 只依 Dialog 本地 running state 處理 | completion 先驗證 operation eligibility；stale result、diagnostics 與 cache 不得採用 |
| 取消後操作 | Dialog 可恢復 Run，但其 input snapshot 可能已過期 | stale Dialog 不可重跑；使用者從目前 Project 重新開啟 Solver |
| 後續求解 | 沒有明確政策 | 不自動重跑，由使用者決定是否再次求解 |

## 主要流程

1. Main 建立 Solver input snapshot 時登記 handle；Solver Dialog 開啟後即受 registry 管理，不必等使用者按 Run。
2. Main 讀取 CAD event，完成既有格式、WCS、mapping 與 no-op 判斷。
3. 若 event 是會改變 Project 的有效 add／update，Main 先把所有已登記且尚未關閉的 Solver snapshot handles 標成 stale，並對 running handles 發出 cancellation request；接著完成 CAD commit（包含 input／result／cache invalidation 與 dirty），commit 完成後才 ACK。
4. 尚未執行的 stale Dialog 立即停用 Run；Main 不等待 running worker 結束，繼續既有 CAD transaction。
5. worker 在下一個安全 checkpoint 以 cancelled outcome 結束；若 callback 晚到，callback gate 丟棄 result、diagnostics 與 cache，只執行 cleanup。
6. 系統不建立新的 Solver operation；使用者需要時，以更新後的 Project 重新開啟並啟動 Solver。

## 不變事項

- 無效 event、`SUPCLEAR` cancel event 與幾何 no-op 不改變 Project，因此不取消 Solver。
- 上述不改變 Project 的 event 也不會停用已開啟但尚未執行之 Dialog 的 Run。
- CAD row／DXF state、input／result／cache invalidation 與 dirty outcome 先 commit，之後才 ACK。ACK 失敗時不 rollback，而是沿用既有 unresolved guard：保留 committed mutation、標記 unresolved event、停止 CAD polling、阻止 save，且相同 event ID 不得重複套用。既有依據為 `docs/WORKFLOW.md`「10.3 Staging and commit」、`main.py::_mark_cad_ack_unresolved`／`_schedule_cad_event_poll`／`_ensure_mutation_allowed`／`_apply_cad_event`，以及 `tests/test_cad_builder_integration.py::test_ack_failure_keeps_project_row_and_blocks_replay`。
- 執行中按關閉仍依 `solver-dialog-running-close-policy` 被拒絕；使用者 close request 不是取消來源。
- Support、Single Waler、Global Waler 的 hard constraints、scoring、search stage、seed、candidate count 與 diagnostics 定義不變。
- 只使用合作式取消，不強制 terminate 或 join worker；不自動重跑。

## Why

CAD input mutation 與 Solver snapshot／worker 目前沒有共同的 lifecycle。已開啟但尚未執行的 Dialog 可以在 CAD 更新後用舊 snapshot 啟動，而 running worker 的晚到 callback 或背景 cache 寫入也可能把 stale 資料重新帶回已更新的 Project，造成正式結果、runtime cache 與目前工程資料不一致。

## What Changes

- 新增三種 Solver 共用的 runtime snapshot handle、operation identity、thread-safe cancellation token、stale adoption gate 與 cancelled outcome；handle 從 snapshot 建立起即受 registry 管理，而不是等 worker start 才登記。
- 在 Support、Single Waler 與 Global Waler 的既有安全搜尋邊界加入 cancellation checkpoint；未取消路徑必須維持相同結果與排序。
- 讓有效且非 no-op 的 CAD add／update 在 Project mutation 前 invalidate 所有已登記且未關閉的 Solver snapshot handle，並取消其中的 running worker，但不等待 worker 才套用更新。
- 將 Support candidate cache 與 Single Waler memory 的背景產出視為 operation-local staged output；只有registry仍判定operation可採用，且既有Project mutation guard允許正式state mutation時，才能寫回Main session cache。
- stale Dialog 完成 cleanup 後保持可關閉，但不得使用更新前 input 重新執行；不自動建立新 Dialog 或 operation。
- 已開啟但尚未執行的 stale Dialog 立即停用 Run並提示「請關閉後重新開啟 Solver」。舊 Waler worker 尚在停止時，`WalerSolverBusyGuard` 繼續持有 lease，新的 Single／Global Waler workflow 顯示「前一次計算正在停止，請稍後再試」。
- 修改 Global Waler 的 valid-result auto-adoption contract：只有仍屬 current、未因 CAD 更新失效，且未被既有unresolved guard拒絕的 valid result 才立即採用。
- 實作驗證完成後，更新 `docs/WORKFLOW.md`、`docs/SOLVER.md`，並在 `docs/ARCHITECTURE.md` 的 state ownership 補上 operation registry truth。

### In Scope

- Support、Single Waler、Global Waler 從 snapshot 建立到 Dialog 關閉的 handle registration、open／running／stale／terminal lifecycle、取消、checkpoint、cleanup 與 callback gate。
- CAD add／update 與 open／running snapshot operation lifecycle 的 UI-thread 協調。
- Solver result、diagnostics、Support candidate cache、Single Waler memory 的 stale-output與unresolved-adoption防護。
- ACK failure、late callback、callback/CAD ordering 與 stale Dialog 的測試。

### Out of Scope

- 使用者取消按鈕、把 Dialog close 解讀為取消、強制 thread termination 或同步等待 worker。
- 自動重新求解、在原 Dialog 重建 input、CAD transport 改成多事件 queue。
- 一般手動欄位編輯、New／Open／DXF Apply 等其他 input mutation 的 Solver 取消。
- Solver 演算法、評分、工程合法性、搜尋參數或 persistence schema 調整。

## Capabilities

### New Capabilities

- `solver-cad-update-cancellation`: 定義有效 CAD mutation 對三種已開啟或執行中 Solver 的 snapshot 失效、合作式取消、stale output 丟棄、Dialog 後續狀態與不自動重跑行為。

### Modified Capabilities

- `global-waler-result-adoption`: 將「valid solution 立即自動採用」限制為 operation 仍可採用；因 CAD 更新而 stale／cancelled 的 valid result 不得提交。

## Impact

- **Presentation**：`main.py` 的 snapshot 建立與 CAD apply 邊界，以及三個 Solver Dialog 的 pre-run stale、worker completion與 stale UI 狀態。
- **Application**：新增 runtime operation registry／handle contract，並調整 `OptimizeSupportZone`、`OptimizeWaler`、`OptimizeWalerGlobal` 接收 cancellation token 與隔離 staged cache。
- **Algorithms**：`support.py`、`wales.py`、`waler_global.py` 與相關搜尋迴圈加入不改變未取消結果的 checkpoint。
- **Tests／文件**：擴充 CAD integration、Dialog lifecycle、三種 optimize use case 與 Solver regression；實作後同步 Architecture／Solver／Workflow truth。
- 無新外部 dependency、無 Project JSON migration、無 Domain engineering rule 變更。

