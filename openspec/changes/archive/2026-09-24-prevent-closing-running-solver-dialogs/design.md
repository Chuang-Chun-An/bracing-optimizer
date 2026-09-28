# Design

## Context

See `proposal.md` for the motivation and `specs/solver-dialog-running-close-policy/spec.md` for the observable contract.

目前三種 Dialog 都由 Presentation 層啟動背景 worker，並透過 `SolverDialogThreadBridge` 將 worker 結果送回 Tk UI thread，但關閉生命週期不一致：

- `SupportSolverDialog`：`WM_DELETE_WINDOW` 與 Close button 都進入 `_on_close()`；目前沒有明確的本地 running flag。`_run_solver()` 停用 Run button 後啟動 worker，worker 分別排入結果／diagnostics／錯誤 UI callback，最後再排入 Run button 恢復 callback。`_on_close()` 會無條件關閉 bridge 並 destroy Dialog。
- `WalerSolverDialog`（Single Waler）：`WM_DELETE_WINDOW` 進入 `_on_close()`；目前沒有明確的本地 running flag。背景執行前會取得共用 `WalerSolverBusyGuard` lease，worker 結束時釋放 lease並分別排入結果或錯誤 callback。快取命中路徑不啟動 worker。`_on_close()` 目前同樣無條件關閉 bridge 並 destroy Dialog。
- `WalerGlobalSolverDialog`：已有本地 `_calculation_running`。啟動 worker 前設為 `True`，thread start failure 與 UI-thread `_finish_worker()` 會恢復為 `False`；`_on_close()` 在 running 時顯示警告並 return，否則才關閉 bridge 與 destroy Dialog。這是本 change 的 reference behavior。

共用的 `WalerSolverBusyGuard` 表示跨 Waler Dialog 的 Solver 使用權，不表示某個 Dialog 是否仍等待其 UI completion／failure handoff。它會在 worker thread 中、UI result callback 執行前釋放，因此不能作為 close permission 的 source of truth。

## Goals / Non-Goals

**Goals:**

- 讓三種 Dialog 以相同、明確且可測試的本地 running-state gate 決定能否關閉。
- 在 Support 與 Single Waler 的成功、失敗及 thread start failure 路徑上可靠恢復關閉權限。
- 保持 Global Waler 現有符合需求的 close guard 與 result adoption lifecycle。
- 將變更限制在 Presentation lifecycle 與相應測試。

**Non-Goals:**

- 不建立可取消、終止或 join worker 的機制。
- 不改變 busy guard、Solver、result adoption、commit／rollback、progress 或搜尋語意。
- 不將三種 Dialog 重構成新的共同 UI framework 或統一全部 worker 實作細節。

## Architecture Alignment

本 change 沿用而不修改既有 Architecture。Dialog running state、window close event 與使用者提示屬於 Presentation responsibility；Application use case 與 Algorithms 不需要知道視窗是否可關閉。依賴方向維持 Presentation → Application → Algorithms／Domain，沒有新增反向依賴。

受影響 layer 僅為：

- Presentation：三種 Solver Dialog 的 runtime UI state 與 close guard。
- Presentation tests：驗證 close request 與 worker UI handoff 的可觀察行為。
- 長期 workflow 文件：實作完成後更新已成立的 current behavior。

Domain rule、Solver preference、temporary heuristic 與 engineering hard constraint 均不受影響。

## Decisions

### 1. 每個 Dialog 的本地 running flag 是 close gate 的唯一 source of truth

Support 與 Single Waler 將採用 Global Waler 已使用的明確本地 running state；Global Waler 保留現有 `_calculation_running` 行為。close handler 只讀取該 Dialog 的本地 flag：running 時立即拒絕關閉，non-running 時執行既有 bridge close 與 destroy 流程。

本地 flag 與共用 busy guard 分工如下：

- 本地 running flag：該 Dialog 是否仍在一次背景 Solver lifecycle 中，唯一決定 close permission。
- `WalerSolverBusyGuard`：Single／Global Waler 之間是否可再啟動另一個 Waler Solver，維持既有跨 Dialog concurrency contract。
- Run button state：純 UI affordance，不作為狀態真相。

這樣可避免 busy guard 提前釋放或 widget state 變動形成第二份 close truth。

**Rejected alternatives:**

- 以 Run button 是否 disabled 判定 running：widget state 不是 lifecycle contract，且測試、錯誤恢復與未顯示狀態容易造成 drift。
- 以 `WalerSolverBusyGuard` 判定 Single Waler running：guard 是共享狀態，且 worker 結束後會早於 UI result callback 釋放，無法表示 Dialog 自身的完整 handoff。

### 2. running state 涵蓋 worker 啟動至既有 UI completion／failure handoff 完成

Support 與 Single Waler 僅在輸入驗證、前置檢查與必要 lease acquisition 成功後，準備實際啟動背景 worker 時進入 running。flag 在呼叫 thread start 前先設為 `True`，避免啟動與狀態設定之間出現可關閉窗口；若 thread start 拋出例外，既有控制項／lease recovery 完成時一併恢復為 `False`。

worker thread 不直接修改 Tk 相關 state，也不直接切換 running flag。worker 仍透過現有 bridge 將 completion 或 failure 交回 UI thread。Support 與 Single Waler 需以小型、各自局部的 finish wrapper／handler 保留目前結果顯示、callback、錯誤顯示與 lease 行為，並在 UI-thread `finally` 中恢復 Run button 及將 running 設為 `False`。如此即使既有顯示或 result adoption callback 拋出例外，Dialog 也不會永久卡在 running。

Single Waler 的既有 cache-hit 同步路徑不建立 worker，因此不進入 running。Global Waler 保留既有 `_finish_worker()` 結構；Tk callback 執行期間不會穿插另一個 close event，所以 completion／failure handler 返回後，下一個 close request 才會觀察到 non-running。

**Rejected alternatives:**

- 在 worker thread 的 `finally` 直接清除 running：會讓 UI completion／result adoption 尚未執行時就允許關閉，並跨 thread 修改 Presentation lifecycle state。
- 只在成功路徑清除 running：失敗或顯示 callback 例外會使 Dialog 永久無法關閉。
- 將三種 worker pipeline 全面改成同一基底：超出需求且會增加 result adoption semantics 的 regression risk。

### 3. close guard 位於既有 Dialog close handler

既有 `WM_DELETE_WINDOW` 與 Dialog Close button（若有）繼續路由至各自 `_on_close()`。handler 在任何 `_close_ui_bridge()` 或 `destroy()` 前檢查本地 running flag；running 時僅記錄／提示並 return，不能釋放 lease、改 result、改 operation state 或關閉 bridge。

使用者提示可沿用 Global Waler 的 warning pattern與相同語意，但不是 correctness source。測試以 Dialog 未被 destroy、bridge 未關閉及 lifecycle state 未被 close request 改變為主，不綁定必須出現特定 message box。

### 4. 直接重用小型模式，不先抽出大型共用 abstraction

三種 Dialog 的啟動條件、lease ownership、completion callback 與 result adoption 次序不同。第一版直接在 Support／Single Waler 套用 Global Waler 的本地 flag + close-handler guard 模式，並保留 Global Waler 實作。只有在實作時確認存在完全相同、無狀態且不改變各自 lifecycle 的微型判定／提示碼時，才可放入既有 Presentation helper；不得為此 change 建立新的 Dialog framework 或把 worker lifecycle 搬進共用 base。

### 5. UI thread 與 worker interaction 不改變

Solver 仍在既有 daemon worker 執行；Tk UI、結果顯示與 running-state completion transition 仍由 UI thread 處理。close request 不會取消、join 或等待 worker，也不改變 shared busy guard 的取得／釋放時機。變更只防止 Dialog 在仍需接收 worker callback 時關閉。

### 6. Long-term documentation impact

實作與測試完成後，`docs/WORKFLOW.md` 中 Support／Single Waler 可於執行中關閉的 current behavior 與已確認 gap 應更新為三種 Dialog 均以 running state 阻擋關閉。`docs/ARCHITECTURE.md`、`docs/DOMAIN.md` 與 `docs/SOLVER.md` 的 long-term truth 不變，不應為此 change 修改。

## Risks / Trade-offs

- [UI completion handler 未涵蓋所有出口，running flag 無法恢復] → 將成功、Solver failure、display/adoption exception 與 thread start failure 納入 focused tests，並以 UI-thread `finally` 統一恢復本地 state。
- [過早清除 flag，結果尚未採用即可關閉] → flag 只在既有 completion／failure UI handoff 完成時清除，不在 worker thread 結束或 busy lease 釋放時清除。
- [message box 使 headless test 脆弱] → correctness tests 驗證 close 被阻擋；提示只做可選 stub／spy，不把精確提示形式納入 requirement。
- [局部重複一小段 close guard] → 接受小型 Presentation 重複以保留三種不同 lifecycle；不以大型抽象換取表面一致。
- [Dialog 在 worker 長時間執行時無法退出] → 這是已確認的產品政策；worker cancellation 明確留在本 change 之外。

## Migration Plan

1. 先以測試固定 Global Waler reference behavior 與三種 Dialog 的 lifecycle transition。
2. 對 Support 與 Single Waler 加入本地 running state、close guard 與可靠的 UI-thread finish transition。
3. 執行 focused Presentation tests、boundary tests 與完整 regression。
4. 驗證後更新 `docs/WORKFLOW.md` 的 current truth。

本 change 不涉及 persistence schema、Project data、外部 API 或資料 migration。若需 rollback，可回復 Presentation lifecycle 變更與對應測試／文件；不需轉換任何使用者資料。

## Backward Compatibility

non-running close behavior、Solver inputs/outputs、result adoption、busy guard 與 persistence 格式維持不變。唯一刻意的 user-visible 行為差異是 Support 與 Single Waler 在背景 Solver running 時不再允許直接關閉；Global Waler 保持既有行為。
