# Design

## 閱讀導航

- **現在必讀（P0）**：D1 operation registry、D2 cancellation token／checkpoint、D3 CAD mutation ordering、D4 output staging／adoption gate、D5 stale Dialog lifecycle。
- **實作 Support 時再讀（P1）**：D2 的 Support checkpoint 與 D4 的 candidate cache staging；另讀 `docs/SOLVER.md` 第 3～7 節。
- **實作 Single／Global Waler 時再讀（P1）**：D2 的 generation／local／DP checkpoint 與 D4 的 solver memory gate；另讀 `docs/SOLVER.md` 第 8～10 節。
- **處理 CAD ACK failure 時再讀（P1）**：D3 的 committed mutation 與既有 unresolved guard ordering。
- **可以先跳過**：persistence migration、Domain engineering rules 與 DXF recognition；本 change 不改它們。

## 方案摘要

以 Application 層的 runtime `SolverOperationRegistry` 作為三種 Solver snapshot／operation lifecycle 的唯一 truth。Main 一建立可供 Solver workflow 使用的 input snapshot，就註冊 snapshot handle；handle 具有唯一 identity、solver kind、`open／running／stale／closed` state 與目前 worker execution（若有）。有效且非 no-op 的 CAD add／update 在 Project mutation 前，先將 registry 內所有尚未關閉的 snapshot handles 原子標成 stale，並只對其中 running executions set cancellation signal；然後不等待 worker，立即完成既有 CAD transaction。

尚未執行的 stale Dialog 立即停用 Run並提示關閉後重新開啟。running worker 只讀 token，在安全 checkpoint 以專用 `SolverCancelled` control outcome unwind。所有 UI progress、result、diagnostics 與 cache adoption 都帶回 snapshot handle與本次 execution identity；UI callback先取得registry completion disposition，再通過Main既有mutation guard，兩者都允許時才可commit。stale callback只cleanup，Dialog保持Run disabled；registry雖為`adoptable`但unresolved guard拒絕時則回報專用`adoption_blocked`狀態，不寫入任何正式output。

```text
Snapshot built
  → registry.register_snapshot() → handle: open
  → Solver Dialog opens with handle
  → Run → registry.start_execution(handle) → handle: running
  → worker(snapshot, execution_id, cancellation_token)
                         CAD mutation ready
                           → registry.invalidate_open_and_running()
                           → open handles: stale / Run disabled
                           → running handles: stale / cancellation set
                           → existing CAD commit / ACK / invalidation
  → safe checkpoint raises SolverCancelled
  → queued UI completion
  → registry.complete_execution(handle, execution_id)
      ├─ adoptable → existing mutation guard
      │                 ├─ allowed → result/cache/memory commit
      │                 └─ blocked → adoption_blocked; no formal output
      └─ stale     → cleanup only; no rerun
```

名詞：

- **snapshot handle**：一份 Solver input snapshot 從建立、Dialog 開啟、零到多次正常執行，直到 stale 或關閉的 runtime identity。
- **operation identity**：snapshot handle 下的一次實際 background Solver 執行；用來阻止舊 callback 影響後續 execution。
- **adoption eligibility**：該 operation 的 output 是否仍可改變 Main session result、cache 或 UI success state。
- **stale**：operation 的 input snapshot 已因即將發生的 CAD mutation 過期；即使 worker 產生 valid result 也不可採用。
- **safe checkpoint**：只讀取消 signal、尚未把 partial worker state提交至 Main 的搜尋邊界。

## 決策對照

| Decision | 對應 Requirement | 對應 task |
| --- | --- | --- |
| D1. Application runtime registry 是 snapshot／operation lifecycle truth | 有效 CAD mutation 使已登記的 Solver snapshot 失效；stale operation 不得採用任何輸出 | 1.1～1.3 |
| D2. token + `SolverCancelled` 在安全 checkpoint unwind | 三種 Solver 合作式結束 | 2.1～2.3 |
| D3. validate／map／no-op 後、Project mutation 前 invalidate；不等待 worker | 有效 CAD mutation使已登記的 Solver snapshot 失效；不改變 Project 的 CAD event 不影響 Solver lifecycle | 4.1～4.3 |
| D4. result、diagnostics、progress 與 runtime cache 一律經 registry + mutation雙重 gate | stale operation 不得採用任何輸出；unresolved期間完成的operation不得寫入正式輸出；Global valid result eligibility | 3.1～3.3、4.6 |
| D5. open／running stale Dialog 都不得使用舊 snapshot | stale Dialog 不得啟動或重用舊 input；取消後不自動重跑 | 3.1～3.5、4.3～4.4 |

## Context

動機見 `proposal.md#why`。目前三個 Dialog 各自用 `_calculation_running` 管理 close gate，worker 完成後經 `SolverDialogThreadBridge` 回到 Tk UI thread並立即採用 output。Main 的 CAD polling 也在 Tk UI thread；Dialog 使用 nested `wait_window` 時 polling 仍會運作。

現有關鍵差異：

- Support worker 使用 Main session 的 `support_candidate_cache`；若 CAD input invalidation 先 clear，未結束 worker 仍可能再寫入 stale cache。
- Single Waler worker 在 UI result gate 前寫入 `solver_memory`。
- Global Waler valid completion 會立即進入 atomic apply；既有 `global-waler-result-adoption` 沒有 stale exception。
- Single／Global Waler 共用 `WalerSolverBusyGuard`，但它只限制並行 Waler execution，不代表 operation identity、取消或 result eligibility。
- Solver input 已在開啟 Dialog 前建立為 snapshot；CAD 更新後不能安全地在原 Dialog 再按 Run。

實際 snapshot 建立時機不是按 Run，也不完全等同於 Solver Dialog constructor：

- **Single Waler**：`main.py::_open_waler_solver` 在 `main.py:8174` 呼叫 `waler_builder.build_all(self.project_data)`，發生在 `WalerSelectionDialog` 開啟之前；選定 snapshot 於 `main.py:8211` 取出，並由 `WalerSolverDialog.__init__` 在 `bracing_optimizer/presentation/dialogs/waler_solver_dialog.py:43` 保存。
- **Global Waler**：`main.py::_open_waler_global_solver` 在 `main.py:8240` 建立全部 snapshots，之後於 `main.py:8287` 傳入 Dialog；`WalerGlobalSolverDialog.__init__` 在 `bracing_optimizer/presentation/dialogs/waler_global_solver_dialog.py:74` 保存 tuple。
- **Support**：`main.py::_open_support_solver` 在使用者完成 Zoning 選擇後，於 `main.py:8399` 呼叫 `support_builder.build_zone(...)`，之後於 `main.py:8424` 傳入 Dialog；`SupportSolverDialog.__init__` 在 `bracing_optimizer/presentation/dialogs/support_solver_dialog.py:84` 保存 snapshot。

因此 registration boundary 必須落在 Main 成功建立 snapshot 的位置，而非 worker start。Single Waler 尤其必須涵蓋 selection Dialog 的 nested event-loop 窗口；若 selection取消、precheck失敗或 Solver Dialog 未建立，Main 必須關閉該 snapshot handle。選定的 handle再傳入 Solver Dialog，不重新登記第二份 truth。

## Goals / Non-Goals

**Goals:**

- 用一份 runtime lifecycle truth 協調 Main CAD mutation與三個 Dialog，而不把 CAD 或 Tkinter 依賴帶進 Algorithms。
- 讓取消快速落在既有可證明安全的搜尋邊界，且未取消時結果、排序與 diagnostics 完全相容。
- 將所有可污染 Main session 的 output 納入同一 adoption gate。
- 保留既有 CAD transaction、Global atomic apply 與 Dialog close policy。

**Non-Goals:**

- 不建立適用所有 Project mutation 的全域 revision framework；本次只處理 CAD add／update。
- 不提供一般使用者 cancel API，不等待或強制終止 thread。
- 不在 stale Dialog 內重建 Solver input；重新求解以重新開啟 workflow 為邊界。
- 不修改 Solver search policy、工程規則或 persistence payload。

## Architecture Alignment

本 change 沿用既有 Architecture 與 dependency direction，未修改 layer boundary：

```text
Presentation (Main / Dialog)
    → Application (operation registry / optimize use cases)
        → Algorithms (cancellation token / checkpoints)
            → Domain
```

- **Presentation**：Main 在 input builder成功後註冊 snapshot，決定 CAD event 何時確定會 mutation並呼叫 registry invalidate；Dialog 接收既有 handle、開始 execution、傳遞 token並依 completion disposition 更新 UI。
- **Application**：registry 擁有 snapshot handle、operation identity與 lifecycle state；optimize use cases協調 cancellation outcome與 operation-local cache output。
- **Algorithms**：只理解通用 token 與 `SolverCancelled`，不理解 CAD、Project、Dialog 或 Tkinter。
- **Infrastructure**：CAD watcher／ACK contract 不變。
- **Domain**：無變更。

Architecture 本身不改變，但 state ownership 的 long-term truth 會新增「Solver operation registry」一列，因此實作完成後更新 `docs/ARCHITECTURE.md`；Solver checkpoint 與 CAD/result lifecycle 分別更新 `docs/SOLVER.md`、`docs/WORKFLOW.md`。

## Decisions

### D1. Application runtime registry 是唯一 snapshot／operation lifecycle truth

新增小型 `SolverOperationRegistry` 與 opaque snapshot handle。registry 至少提供：

- Main 在 input builder成功產生 snapshot時註冊 handle；初始 state為 `open`，即使尚未按 Run也能被 CAD mutation invalidate。
- `start_execution(handle)` 只允許 `open` handle，產生唯一 execution identity與 cancellation source，並轉為 `running`。
- 原子取得所有 `open／running` handles並標記 `stale`；只有 `running` handles需要 set token。
- UI completion以 handle + execution identity完成 worker，回傳 `adoptable` 或 stale reason；正常 success／failure可回到 `open`供同一未過期 snapshot重跑，stale則保持不可啟動直到 Dialog關閉。
- selection取消、Dialog正常關閉、thread start failure、success、failure、cancelled與重複 cleanup均有 idempotent transition；`closed` handle從 registry移除。

`_calculation_running` 繼續作為 Dialog close／button projection，但不再判定正式 output 是否可採用。每個 worker、progress callback 與 completion callback 都 capture 自己的 handle，避免舊 callback 改到較新的 execution。

registry 由 Main application session 建立。Main 將建立 snapshot時取得的同一 handle連同 snapshot一起交給 Dialog；它不持久化，也不成為 `ProjectDataModel` 或 `ProjectResultModel` 的第二份 truth。

**拒絕方案：等 worker start 才註冊或只檢查 Dialog 的 `_calculation_running`。** 這會漏掉已持有 snapshot但未按 Run的 Dialog，也無法分辨兩次 execution或讓 Main找到 running worker發出取消。

**拒絕方案：為所有 Project mutation新增 persisted 或 global input revision。** 本次需求只涵蓋 CAD；全面 revision 會擴張手動編輯、Open／New、DXF Apply 與 persistence scope。CAD mutation 前原子 invalidate handle 已足以建立 callback ordering。

### D2. Algorithms 提供通用 token，checkpoint 以專用 control outcome unwind

在不依賴 Application／Presentation 的 Algorithms boundary 提供 read-only cancellation token 與 `SolverCancelled`。Application registry 持有對應 cancellation source；worker 只取得 token。checkpoint 執行 `token.raise_if_cancelled()`，觸發專用 exception 向上 unwind；Dialog 將它分類為 cancelled，不顯示一般 Solver failure。

checkpoint 放在既有 deterministic 邊界：

- Support：每個 config／unit 前後、Phase 1 候選批次、Phase 2 search stage 與 beam expansion 外層邊界。
- Single Waler：initial population 建立批次、每個 search stage 與每個 generation 邊界。
- Global Waler：每個 local Waler 前後，以及 exact DP 每個 Waler group 的外層邊界；local `OptimizeWaler` 接收同一 token。
- result／diagnostics 組裝前再檢查一次，縮小「搜尋完成但 callback 尚未產生」的窗口。

checkpoint 不修改 collection、random state、排序 key 或 score。token 未 set 時只能多出只讀 branch；exact regression 必須證明結果不變。

**拒絕方案：thread termination 或 join 後才處理 CAD。** Python worker 無安全強制終止，join 會阻塞 Tk UI 並延後 CAD transaction。

**拒絕方案：只在 use case stage 間檢查。** Single Waler generation、Support candidate generation 或 Global exact DP 可能長時間無回應，不能滿足合作式停止的實際目的。

### D3. CAD 只在確定 mutation 後取消，並維持立即 apply

Main 沿用 `_apply_cad_event` 的既有 validation、mapping、binding staging與 no-op 判斷。對 control cancel、invalid event 或 no-op update，不接觸 registry，因此 `open` Dialog仍可 Run、`running` worker繼續。對確定會 add／replace Project row 的 event，在第一次正式 Project mutation 前呼叫 `invalidate_open_and_running(reason="cad_update")`：`open` handles只轉成 stale，`running` handles同時 set cancellation token。

Main 與 Dialog completion 都在 Tk UI thread，因此 ordering 可完整定義：

1. completion 先執行：正常 commit；後續有效 CAD mutation 先使 handle stale，再 commit Project row／DXF state，以及 input／result／cache invalidation 與 dirty outcome，最後才 ACK。因此舊 Solver result 與 cache 在 CAD commit 時清除，不以 ACK 成功為前提。
2. CAD invalidation 先執行：handle 先 stale；後續 completion gate 不採用 output。
3. ACK 失敗：不 rollback 已完成的 CAD commit，而是沿用既有 unresolved guard，保留 Project row／DXF state、input／result／cache invalidation 與 dirty outcome，記錄 unresolved event、停止 CAD polling、阻止 save，並防止相同 event ID 重複套用。Solver handle 仍 stale，cancellation token 維持已設定；被取消的 worker不能安全恢復，系統也不自動重跑。

上述 unresolved guard 已由 `docs/WORKFLOW.md`「10.3 Staging and commit」、`main.py::_mark_cad_ack_unresolved`／`_schedule_cad_event_poll`／`_ensure_mutation_allowed`／`_apply_cad_event`，以及 `tests/test_cad_builder_integration.py::test_ack_failure_keeps_project_row_and_blocks_replay` 建立；本 change 只沿用，不新增停止 polling、阻止 save或 duplicate-event handling 規則。

現行 unresolved guard **不阻止開啟 Solver Dialog，也不阻止在已開啟的 Dialog 按 Run**：`main.py::_open_waler_solver`、`_open_waler_global_solver`、`_open_support_solver` 沒有呼叫 `_ensure_mutation_allowed()`，三個 Dialog 的 `waler_solver_dialog.py::_run_solver`、`waler_global_solver_dialog.py::_run`、`support_solver_dialog.py::_run_solver` 也沒有該 guard。工具列的 Solver actions 亦未依 `cad_ack_unresolved_event_id` 停用。因此 ACK unresolved 期間仍可從目前已 committed 的 Project 建立新 snapshot並啟動 worker；本 change 記錄並保留此實際行為，不自行新增 unresolved-only 的 Dialog／Run 阻擋。正式 result adoption仍受既有 Main mutation guard與本 change 的 operation gate各自約束。

CAD apply 不等待 registry active count 歸零。這保留現行 CAD responsiveness與 transaction ordering，也讓「丟棄晚到結果」成為必要的第二道防線。

**拒絕方案：先等待所有 worker terminal 再套用 CAD。** 這會把 checkpoint latency直接轉成 CAD mutation latency，並改變現行 CAD transaction，需求沒有要求此阻塞行為。

### D4. 所有 Main session output 都先 staging，再經同一 handle gate

completion disposition 是 result adoption 的唯一 gate，涵蓋：

- Support／Single／Global正式 result 與 diagnostics。
- calculated time、dirty state、result tree、preview 與 success summary。
- Support candidate cache 的新增項目。
- Single Waler solver memory。
- Global Waler atomic apply 的入口。
- queued progress callback；stale progress 不得覆蓋「因 CAD 更新停止」狀態。

這裡的「唯一 gate」是指所有 Solver output 必須經過同一個 UI-thread adoption boundary，不代表 registry 的 `adoptable` 單獨構成充分條件。正式 adoption 必須同時通過：

1. registry 對該 handle + execution identity 回傳 `adoptable`；以及
2. Main 既有 `_ensure_mutation_allowed()` guard，包括 ACK unresolved與 `projection_stale`。

任一條件不通過，result、diagnostics、Support candidate cache與Single Waler solver memory都不得寫入 Main session。registry `adoptable`只表示 operation未因 CAD mutation等 lifecycle事件變成 stale；它不覆蓋既有 unresolved guard。Dialog開啟與Run入口仍不新增 `_ensure_mutation_allowed()`，所以 unresolved期間可以建立並執行新operation；雙重gate只作用在completion adoption。

若 registry為 `adoptable`，但既有 unresolved guard拒絕 adoption，UI-thread completion須把它分類為專用的 `adoption_blocked` control outcome：不得讓例外逸出Tk callback，也不得顯示成一般Solver failure。Dialog完成既有terminal cleanup、離開running state並恢復可關閉；因本change不新增unresolved期間的Run阻擋，Run維持既有可用狀態。Dialog顯示「計算完成，但CAD ACK尚未完成，結果未採用」，可以保留worker log，但不得把result或diagnostics呈現為已正式採用。系統不自動重跑。

目前code與此目標仍有下列差距，後續implementation必須在本change內收斂，但不得把guard前移到Dialog開啟或Run入口：

- Support formal result走 `main.py::_store_support_solution → _store_result_item`，後者有 `_ensure_mutation_allowed()`；但 `OptimizeSupportZone.adopt_candidate_cache_updates()`直接更新session cache且沒有guard，Dialog目前也尚未接線該staged cache adoption。guard拒絕formal result時，`SupportSolverDialog._finish_worker()`會捕捉例外並顯示一般「計算結果處理發生錯誤」。
- Single Waler formal result走 `main.py::_store_waler_result`，入口有 `_ensure_mutation_allowed()`；但 `_save_solver_memory()`直接寫入dict，且目前由worker在formal result callback前呼叫，因此ACK unresolved期間memory仍可能先被寫入。後續formal result拒絕會被`WalerSolverDialog._finish_worker()`轉成一般「計算結果處理發生錯誤」。
- Global Waler formal result走 `main.py::_apply_waler_global_result`，既有guard拒絕時回傳`committed=False` outcome，沒有未處理例外或正式result寫入；但Dialog目前顯示一般「套用失敗」error，不是專用`adoption_blocked`狀態。

Support `OptimizeSupportZone.execute` 使用 operation-local working cache：可從 session cache snapshot 讀取既有合法 entries，但新增／更新只回傳為 staged cache output；Dialog 在 handle 可採用時才呼叫 Application cache-adoption API。Single Waler 把目前 worker 內的 `_save_solver_memory` 移到通過 gate 的 UI completion。

Global Waler 的 local `OptimizeWaler` **不會寫入 Single Waler 的 `solver_memory`**：`solver_memory` 只由 `WalerSolverDialog` 保存（constructor assignment：`waler_solver_dialog.py:51`；寫入：`_save_solver_memory()` 及 worker call `waler_solver_dialog.py:302-319,454`）。Global path 的 `WalerGlobalSolverDialog` 沒有接收 memory；`OptimizeWalerGlobal.execute()` 只在 `optimize_waler_global.py:120` 透過 factory建立純 `OptimizeWaler`並把 local outputs保存在 `local_results`／global candidate staging。實作不得為此次 cancellation改變此邊界；新增 regression test鎖定 Global execution前後 Main `solver_memory` 完全不變。Global valid solution仍須先過 handle gate才呼叫 atomic apply callback。

worker log 可繼續排入其 Dialog 的文字區域，因為它不是 Main session truth；任何 success／failure summary 則必須經 gate。

**拒絕方案：CAD apply 後只 clear cache。** Support worker 可能在 clear 之後繼續寫入，無法防止 stale cache 復活。

### D5. open／running stale Dialog 都不能啟動或重跑舊 snapshot

`open` handle（Dialog已持有 snapshot、尚未按 Run）收到 CAD invalidation時，不存在 worker需要取消。Dialog須立即顯示「CAD 已更新；請關閉後重新開啟 Solver」，停用 Run並保持可關閉。invalid、control cancel或no-op event不改變 handle或Run狀態。

stale completion 仍須：

- idempotently terminal registry handle。
- 將 `_calculation_running` 設為 false，恢復既有 close permission。
- 釋放既有 Waler lease（worker finally path維持）。
- 顯示「CAD 更新，計算已停止；請關閉後重新開啟 Solver」。
- 保持 Run disabled，不呼叫 result display／adoption callback，也不自動 destroy Dialog。

正常 success／failure 仍依既有行為恢復 Run；只有 CAD-stale Dialog 被鎖定。這避免原 Dialog 使用建立時的 `SupportZoneInput`／`WalerProblemInput` snapshot 再次求解，也不引入 Dialog 內重建 input 的第二條 workflow。

Waler cancellation期間，busy lease語意維持不變：Single在 `waler_solver_dialog.py:391`、Global在 `waler_global_solver_dialog.py:210` 成功 `try_acquire()` 後持有 lease；CAD cancellation只 set token，不釋放 lease。lease只在 thread start failure（Single `:422`、Global `:242`）或 worker `finally`（Single `:462`、Global `:270`）釋放。因此舊 worker抵達 checkpoint並 unwind之前，`WalerSolverBusyGuard.is_busy` 必須持續為 true。

若此期間使用者嘗試重新開啟 Single／Global Waler，Main既有 workflow-entry guard（`main.py:8166`／`:8232`）仍先阻擋；當 registry顯示 active Waler handle已因 CAD進入 stale／cancelling，提示改為「前一次計算正在停止，請稍後再試」。若已有另一個 Waler Dialog並在其 Run path競爭 lease，`try_acquire()` failure也顯示相同提示。不得為了讓新 workflow通過而強制 release lease；worker `finally`釋放後才允許新的 Waler worker取得 lease，確保不會同時執行兩個 Waler workers。

**拒絕方案：取消後重新 enable Run。** 三個 Dialog 的 request 都由開啟前的 Project 建立，重跑會再次使用 stale input。

**拒絕方案：自動關閉並重新開啟。** 這會改變使用者視窗 lifecycle，且等同隱含自動 workflow；需求只要求不自動重跑。

## Source of Truth

| State／contract | Single source of truth |
| --- | --- |
| snapshot identity、open／running／stale／closed與 execution identity | `SolverOperationRegistry` |
| worker 是否應停止 | handle 對應 cancellation source；worker只持 read-only token |
| Dialog running／button projection | Dialog，從 operation lifecycle 投影，不作 adoption authority |
| committed Project input | `ProjectDataModel` |
| committed Solver result | `ProjectResultModel` |
| Support／Single session cache | Main application session；operation-local output 在採用前不是正式 cache |

registry 不複製 Project input；token 不代表結果是否已 commit。completion disposition 與既有 Project/result owners 分工，避免形成第二份工程 truth。

## Backward Compatibility / Persistence

- 所有 operation state、token 與 staged cache 都是 runtime-only；Project JSON schema 不變，無 migration。
- 正常未取消執行的 public result shape、排序、diagnostics與 auto-adoption行為保持相容。
- `WalerSolverBusyGuard` 繼續限制 Single／Global Waler concurrency；registry 不取代它。
- CAD cancellation不提前釋放 Waler lease；stopping期間的重新開啟請求被拒絕並顯示專用提示。
- running close policy 保持相容：使用者 close request 不 set token。
- CAD control cancel、invalid／no-op，以及 ACK failure 後保留 committed mutation並進入既有 unresolved guard 的 Project transaction語意保持不變。

## Risks / Trade-offs

- [checkpoint 太稀疏，worker 停止仍慢] → 在長迴圈的外層 deterministic boundary 加入檢查，並以可控制 token 的 targeted test證明各主要階段可退出。
- [checkpoint 插入改變 random sequence或結果] → token 未 set 時不得修改資料或呼叫 random；執行三種 Solver exact regression。
- [stale progress callback 覆蓋取消提示] → progress callback capture handle並在 UI 執行時 gate。
- [snapshot 在 Solver Dialog前建立，registration太晚仍會漏接 CAD] → 在 Main builder成功時立即註冊；selection取消／precheck失敗時 idempotently close handle。
- [取消後提前釋放 Waler lease造成兩個 workers重疊] → lease仍只在現有 thread-start failure或worker `finally` path釋放，registry只用來選擇 stopping提示。
- [Support cache staging 漏掉寫入路徑] → characterization test證明 CAD clear 後 worker不能重新填入 session cache。
- [registry cleanup 遺漏造成永遠 active] → thread start failure與所有 worker terminal path放在 finally，completion transition idempotent。
- [CAD ACK 失敗後使用者以為被 stale 的 Solver 仍會完成] → Dialog明確顯示已停止，且不自動 resume／rerun；既有 unresolved guard另外負責停止 CAD polling、阻止 save與防止相同 event重複套用。
- [checkpoint 增加少量 hot-loop成本] → 只在批次／generation／beam unit等外層檢查，不在每次 score primitive檢查。

## Migration Plan

1. 先加入 registry、token與單元測試，建立 `open → running → open／stale → closed` lifecycle，不接線 CAD。
2. 將三個 use case逐一接入 cancellation並確認未取消 regression。
3. 在三個 Main input-builder success boundary註冊 snapshot handle並傳入 Dialog；將 pre-run stale UI、result／progress／cache adoption接到 handle gate。
4. 最後在 CAD mutation boundary呼叫 invalidate／cancel，補齊 ordering與ACK unresolved integration tests。
5. 行為全部驗證後更新三份 long-term docs。若需撤除此 change，移除 registry wiring即可；沒有 persisted state需要轉換。

## Open Questions

無。規格會受影響的行為已在本 design 固定；checkpoint 的精確函式位置可在不改變 contract 下依 profiling與既有迴圈結構調整。

