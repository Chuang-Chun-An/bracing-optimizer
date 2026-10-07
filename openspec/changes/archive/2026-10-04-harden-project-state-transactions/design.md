# Design

## 閱讀導航

- **現在必讀（P0）**：Decision 1 的無副作用 commit、Decision 4 的 CAD ACK failure、Decision 5 的 managed DXF recovery，以及 Decision 6 的 projection guard／完整重新投影。
- **實作前閱讀（P1）**：Decision 2～3；`specs/project-state-transaction-consistency/spec.md`；`tasks.md` 第 1～5 節。
- **條件式閱讀（P2）**：修改 Material Spec 時讀 archived change `2026-10-01-move-material-spec-editing-to-application` 的 Decision 3；修改 CAD 時讀既有 CAD event validation／ACK tests；修改 save 時讀 Project persistence rollback tests。
- **可先跳過**：Solver scoring、DXF recognition、Project JSON schema migration 與其他 active changes。

## 方案摘要

每個受影響 use case 分為三段：stage 建立完整 outcome、commit 只替換無副作用的 plain runtime references、projection 將 committed state 顯示到 UI。property setter、collection mutation、Tkinter variable `.set()`、callback、filesystem operation 與可失敗轉換都不得出現在 commit。

流程為：

```text
stage（pure／可失敗，不改 live state）
  → commit（plain reference replacement，無 callback）
  → CAD ACK（如適用）
  → projection（可重試）
```

projection 失敗時，正式 state 不回滾；系統進入 `projection_stale`，鎖住資料修改並提供完整重新投影入口。CAD mutation 已 commit 但 ACK 失敗時，保留 mutation、停止 CAD 監聽並阻止 save，直到 pending event 被明確處理。managed DXF rollback 失敗時保留 `.rollback`；後續 save 若發現既有 recovery artifact，會在任何正式檔案替換前拒絕執行。

## 決策對照

| Decision | 對應 Requirement | 對應 task |
| --- | --- | --- |
| D1. stage → side-effect-free commit → projection | 所有 state consistency Requirements | 1.1～1.3、2.1 |
| D2. 完整 staged Project load | Project load 以完整 staged state 一次採用 | 3.1 |
| D3. typed result／material outcomes | Support／Single Waler、Material Spec Requirements | 3.2、3.3 |
| D4. commit 後 ACK；ACK failure 停止監聽 | CAD ACK 與同一事件不得重複套用 | 4.1 |
| D5. managed DXF recovery 不得遺失或覆蓋 | Save rollback 失敗時保留 recovery artifact | 5.1 |
| D6. projection failure 鎖住修改並完整重投影 | Projection failure editing guard | 2.2 |

## Context

`main.py` 同時持有 presentation state 與多個正式 runtime references。Global Waler 已區分 `committed`／`refreshed` outcome，可作為 failure semantics 的局部先例；但它目前仍使用 property setter 與 `_mark_results_updated()`，不能作為「無副作用 commit」的實作先例。

Project load、Support／Single Waler result adoption、Material Spec、CAD event 與 persistence rollback 的 failure boundary 尚未一致。已封存的 `move-material-spec-editing-to-application` 已完成 Application staging 與 structured outcome；本 change 不重開該 change，而是進一步收斂 Main adoption：移除 commit 內的 cache `clear()`，並把 dirty 納入 staged formal state。

### main.py commit surface 盤點（2026-10-04）

`main.py` 定義 `walers`、`struts`、`braces`、`inventory`、`material_specs`、`result_items`、`project_result` 與 `last_calculated_time` property setters。前五者呼叫 `ProjectDataModel.replace_table()`，會正規化、驗證且可拋錯；後三者修改既有 `ProjectResultModel`。這些 setter 一律不得出現在新 commit。

Repository 搜尋未發現 `main.py` 對受影響 state 註冊 `trace_add`、`trace_variable` 或舊式 `.trace()`；唯一找到的 Tk trace 位於不相關的 `dxf_import/dialog.py` overlay choice。雖無顯式 trace，`StringVar.set()`、widget method 與 title/status 更新仍是 UI side effect，必須留在 projection。

| 入口 | 現行 commit surface | Setter／trace 與副作用判定 |
| --- | --- | --- |
| Project load | plain attribute assignments 後呼叫 `solver_memory.clear()`、`support_candidate_cache.clear()`；`dirty=False` 由 `_clear_project_dirty()` 完成 | 未使用上述 property setter；兩個 `clear()` 是 collection mutation，`_clear_project_dirty()` 會更新 title／status UI |
| Support result adoption | `ProjectResultModel.store_item()`、`mark_updated()`、`_mark_project_dirty()` | 直接 mutation 既有 result model；dirty helper 呼叫 UI |
| Single Waler adoption | `self.result_items = ...`、`_mark_results_updated()` | `result_items` 有 property setter；後續 serialization／metadata／dirty 仍可失敗 |
| Material Spec adoption | 替換 Project／Result references，再呼叫兩個 cache `clear()`；dirty 在 `_handle_input_data_changed()` 才設定 | plain references 本身無 setter；cache 是 collection mutation，dirty 位於 projection 太晚 |
| CAD event | live table `append()`／`replace_row()`、DXF state assignment、filesystem ACK；result/cache/dirty 在 ACK 後 | 未使用 table property setter，但直接 mutation live model；ACK 刪除 event file，是外部不可逆副作用 |
| Global Waler 基準 | `result_items`、`project_result`、`last_calculated_time` setters 及 dirty helper | 只保留 committed／refreshed outcome 語意；現行 commit 實作不符合 D1 |

## Goals / Non-Goals

**Goals:**

- 讓每條 mutation path 明確知道何時正式資料已改變，且 commit 內沒有可呼叫或可注入的副作用邊界。
- UI failure 不再造成 dirty、metadata、cache 與正式 model 漂移，也不允許使用者在 stale projection 上修改資料。
- 提供單一完整重新投影入口，使 projection failure 可安全恢復。
- CAD ACK failure 不重複套用同一事件，也不把未確認的 mutation 持久化後留給 stale event 重播。
- managed DXF rollback 失敗時保住可人工救援的檔案，後續 save 不覆蓋既有 recovery artifact。

**Non-Goals:**

- 不把所有 `main.py` state 一次搬到新 framework。
- 不改 Global Waler 已成立的 committed／refreshed observable contract。
- 不改 Project JSON schema、CAD transport queue、Solver cancellation 或 DXF recognition。
- 不為 Project JSON 新增 `.rollback`；JSON 仍使用 temporary write、atomic replace 與 `.bak`。

## Architecture Alignment

本 change 強化既有 Architecture，不改 layer 定義。Application 建立 use-case outcome 與 transaction semantics；Infrastructure 管 managed DXF staging／replace／rollback；Presentation 只做 plain state adoption、projection guard 與 UI projection。因 brownfield 結構，`main.py` 仍負責最後 reference swap，但不得重新推導 Application outcome。

依賴方向維持 `Presentation → Application` 與 `Infrastructure → Application／Domain contract`。Application 不依賴 Tkinter；Infrastructure 不定義 Project mutation 規則。

## Decisions

### Decision 1: commit 只做無副作用的 plain reference replacement

每個 use case 建立 immutable／staged outcome，包含完整 Project／Result models、metadata、cache replacements、DXF state、current path、dirty value／reason，以及 projection 所需資訊。所有 validation、copy、serialization、summary input、calculated time 與 invalidation 都在 stage 完成。

commit 只允許直接指定 `SupportInputApp` 的 plain instance attributes；class 不得對這些欄位定義 property setter 或 custom `__setattr__`。commit 不得呼叫 method、property setter、Tk variable `.set()`、callback、widget API、filesystem API、`list.append()`、`dict.clear()` 或其他 collection mutation。cache 必須在 stage 建成新物件，commit 以 reference replacement 採用。

每個入口都要在 commit 可呼叫邊界注入例外。如果依本決策移除後沒有可注入點，測試必須以 spy／static inspection 證明 commit 僅含 direct assignments、目標欄位沒有 setter／trace／custom `__setattr__`，並證明所有可失敗工作已在 stage 或 projection。

拒絕自動 snapshot 整個 App：Tkinter objects、file handles 與不可 deep-copy runtime state 使通用 rollback 不可靠。也拒絕以「commit 失敗再逐欄 rollback」取代本決策，因 rollback 本身仍可能留下部分 state。

### Decision 2: Project load 在 swap 前完成所有可失敗準備

Project service 先建立完整 application state，Presentation 再 stage results、DXF report、path、cache replacements、`dirty=False` 與空 dirty reason。commit 只替換 plain references／values。Tree rebuild、case list、title、status variables、Preview 與 DXF workflow widgets 都在 projection。

Project formal state 是 load outcome；widgets 不是 source of truth。projection 失敗時 Project 仍已完整載入且保持 clean，但進入 Decision 6 的 editing guard。

### Decision 3: Support／Single result 與 Material Spec 先完成衍生資料

序列化、summary input、calculated time、需要 invalidation 的 result IDs、完整新 cache objects 與 dirty reason 在 commit 前建立。commit 不使用 `result_items`／`project_result`／`last_calculated_time` setters，也不對既有 `ProjectResultModel` 或 caches 做原地修改。

Manual editing、automatic Solver adoption 與 Material Spec dialog 必須沿用各自 Application outcome，不在 Presentation 複製 invalidation 規則。已封存的 Material Spec change 所定義之 rejected／confirmation／no-op／staged outcome 與 error-code mapping 維持；本 change 只強化其 Main adoption boundary。

### Decision 4: CAD ACK 在 commit 後；ACK failure 停止監聽

CAD stage 建立完整 Project、Result、cache、DXF status 與 dirty outcome，commit 以 Decision 1 採用，成功後才 ACK。ACK 成功後只做 UI projection 與 status 更新。

若 mutation 已 commit 但 ACK filesystem operation 失敗，採用已確認的停止策略：

- 不回滾已 commit mutation。
- 將該 event ID 標記為 ACK unresolved，立即停止 CAD polling，並顯示資料已更新但事件未清除。
- 在 pending event 未經 `SUPCLEAR` 或等價明確處理前，不得重新啟用 CAD 監聽，也不得自動重試或再次套用同一 event ID。
- ACK unresolved 期間阻止 Project save，避免 mutation 已持久化後，程式重啟又從殘留 event 重播。使用者處理 pending event 後才解除 save／monitor guard。
- 若程式在事件處理前結束而放棄 unsaved mutation，下一次啟動重播該事件不算重複持久化；若實作無法證明此 invariant，必須停止並回報，不得以 in-memory `last_event_id` 冒充跨重啟保證。

若 stage 或 commit 失敗，不 ACK，沿用既有重試／`SUPCLEAR` workflow，正式 state 保持不變。

拒絕「記錄 event ID 後自動略過並繼續監聽」：目前沒有 durable idempotency ledger，僅靠 watcher 的 in-memory `last_event_id` 無法涵蓋重啟。

### Decision 5: managed DXF recovery artifact 依 rollback 結果清理，既有 artifact 時拒絕 save

本決策只涵蓋 `source/source.dxf.rollback`；Project JSON 的 `.tmp`、atomic replace 與 `.bak` 不在此 recovery contract。

Persistence 將 recovery path 與 rollback outcome 保留到 exception handling 結束。只有舊 managed DXF 已成功復原，才刪除 `.rollback`；復原失敗時保留檔案，typed error 帶出絕對 recovery path，`finally` 不得無條件清理。

新的 save 在建立 temp file、複製來源或替換任何正式檔案前，先檢查目標 `.rollback`。若已存在，採用已確認的拒絕策略：立即停止 save，回報既有 recovery path 與 managed DXF path，不覆蓋、不刪除、不重新命名 recovery artifact，也不修改 Project JSON、managed DXF 或 runtime dirty state。

拒絕時間戳 recovery files：連續產生多份未知恢復狀態會增加人工判讀風險；本桌面工具在 unresolved filesystem incident 時優先停止。

### Decision 6: projection failure 鎖住資料修改，直到完整重新投影成功

任何受影響入口在 commit 後 projection 失敗時，設定 presentation-owned `projection_stale` guard。guard 生效期間，Project／Result／Material Spec 編輯、Solver result adoption 與 CAD mutation 等資料修改入口必須拒絕執行；唯讀狀態查看與完整重新投影仍可使用。

新增一個明確的使用者操作入口，從 committed state 重新建立全部相關 projection，至少包括：

- Waler／Strut／Brace／Inventory／Material Spec Treeviews；
- Results Tree 與材料摘要；
- Preview；
- Project、DXF workflow 與 CAD status；
- selection／action-state reconciliation。

只有上述步驟全部成功才清除 `projection_stale` 並解除編輯鎖定；任一步驟再失敗都維持 guard 並回報最新錯誤。現有「更新圖面」只重畫 Preview、「重新顯示狀態」只更新 CAD status，均不能當作這個完整入口。

拒絕允許 stale UI 繼續編輯並以 row identity／projection version 驗證：目前所有編輯 surface 尚未共同具備穩定 row identity 與 version contract，會使本 change 擴張成全面 optimistic concurrency 改造。

## Source of Truth

- Project/load state：Application load outcome 與 commit 後的 App references。
- Results：commit 後的 `ProjectResultModel` reference。
- Material mutation/invalidation：`MaterialSpecEditing` outcome；Main 不重算規則。
- Caches：Application outcome 建立的新 cache objects；不得原地清除舊 cache。
- Dirty：outcome 中的 value／reason，與 Project／Result state 同一次 commit。
- Projection health：Presentation 的 `projection_stale` guard；widgets 不是正式資料。
- CAD event completion：watcher ACK state；ACK unresolved guard 阻止 monitor／save，UI status 只是 projection。
- Filesystem recovery：實際 managed DXF `.rollback` file 與 persistence outcome。

## Backward Compatibility / Persistence

Project JSON schema 與成功路徑輸出不變，舊 Project 直接載入，不需 migration。新增的是 runtime failure semantics、完整重新投影入口、ACK unresolved guard，以及 managed DXF recovery collision rejection。

ACK unresolved 期間的 save guard 避免需要將 event ID 寫入 Project schema。若未來要求 ACK failure 後仍可持續監聽或跨重啟自動 deduplicate，應另立 change 設計 durable event ledger。

## Risks / Trade-offs

- [多個 plain assignments 仍被誤認為可注入 transaction] → 移除 commit 內所有 callable boundary；測試以 spy／static evidence 證明沒有 setter、trace、callback 或 mutation。
- [stage 漏掉延遲計算，commit 後仍拋錯] → fault-injection tests 覆蓋 stage 尾端、commit 邊界及 projection 開頭。
- [UI 失敗後使用者看到舊 widgets] → `projection_stale` 鎖住修改並提供完整重新投影，不回滾正式 state。
- [ACK failure 後 event 殘留] → 停止監聽並阻止 save，明確要求處理 pending event；不以 session-only dedupe 宣稱跨重啟安全。
- [拒絕 save 影響使用者工作] → 訊息提供 recovery 與 managed DXF 絕對路徑；先保護唯一救援檔，再由使用者處理。
- [Material Spec archived design 與新限制不同] → 保留 Application outcome／error semantics，只由本 change 更新 Main adoption；不重開或改寫 archived artifact。

## Migration Plan

1. 先建立 commit surface characterization、fault-injection 與不可拋錯證據。
2. 加入 typed outcomes、plain-reference commit helper、`projection_stale` guard 與完整重新投影入口。
3. 依序收斂 Project load、Support／Single Waler、Material Spec 與 CAD。
4. 實作 CAD ACK unresolved monitor／save guard 及相同 event 防重複測試。
5. 實作 managed DXF rollback preservation 與既有 `.rollback` save rejection。
6. focused tests 全部通過後更新長期 Architecture／Workflow 文件，再執行完整 regression 與 OpenSpec verification。
