# Proposal

## 閱讀導航

- **P0 現在必讀**：本 proposal 的前五節；`docs/WORKFLOW.md` 的 Result Lifecycle、CAD Event Workflow、Save／Load、Commit／rollback summary。
- **P1 實作前閱讀**：`design.md` 的無副作用 commit、projection guard／完整重新投影、CAD ACK failure 與 managed DXF rollback 決策；本 change 的 `project-state-transaction-consistency` spec。
- **P2 需要時再讀**：修改 Global Waler 對照行為時讀 `global-waler-result-adoption`；修改 navigation 時讀 `unsaved-changes-navigation-guard`。
- **可以先跳過**：Solver scoring、DXF recognition、材料比例與 Project schema migration。

## 快速摘要

- 多個流程先修改正式 model，之後才更新 metadata、dirty 或清除舊結果；中途 UI 失敗會留下混合狀態。
- Project load、Support／Single result adoption、CAD／Material Spec 修改都改為 stage → 無副作用 commit → projection；commit 只替換 plain runtime references。
- UI projection 失敗後鎖住所有資料修改，提供完整重新投影入口；只有重新投影全部成功才解除鎖定。
- CAD mutation 已 commit 但 ACK 失敗時停止監聽並阻止 save，直到 pending event 被明確處理；同一事件不得重複套用。
- Project save 的 managed DXF rollback 若失敗，保留 `.rollback`；下一次 save 發現既有救援檔時直接拒絕，不得覆蓋或刪除。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| Model commit | 可能與 metadata／dirty 分多步完成，且呼叫 setter、`clear()` 或 helper | Application outcome 預先建立完整 state；commit 只做 plain reference replacement |
| UI refresh failure | 可能中斷 dirty／invalidation，使用者仍可在舊畫面上編輯 | 正式 state 保持一致，鎖住修改並提供完整重新投影入口 |
| Load adoption failure | 可能混合新 Project 與舊 DXF status | 採用前完整 stage，採用後狀態不可混合 |
| CAD ACK failure | 可能 rollback 部分 state 或讓 pending event 再次套用 | 保留已 commit mutation、停止監聽並阻止 save，直到事件被明確處理 |
| Managed DXF rollback failure | cleanup 仍可刪除或下一次 save 覆蓋 recovery copy | 保留 recovery artifact；既有 `.rollback` 未處理前拒絕下一次 save |

## 主要流程

1. Application 先建立完整 staged outcome，包含 model、results、metadata、cache replacements、dirty／invalidation effects。
2. Main 以不經 property setter、Tk variable trace、callback 或 collection mutation 的 plain assignments 採用正式 state。
3. UI projection 只讀 committed state；失敗時設為 projection-stale、鎖住資料修改，使用者可執行完整重新投影。
4. CAD mutation commit 後才 ACK；ACK 失敗時保留 mutation、停止監聽並阻止 save，直到 pending event 被處理。
5. Persistence 只有在 managed DXF rollback 成功時才清理 recovery copy；rollback 失敗則保留，且後續 save 在既有 `.rollback` 未處理前拒絕執行。

## 不變事項

- Global Waler 既有 committed／refreshed outcome 語意維持；它只作 failure-semantics 先例，不代表現行 setter-based commit 已符合本 change 的新限制。
- CAD event transport 仍維持 single-slot；不新增 queue 或自動重播。
- Invalid manual result 可正式保存；Project schema 不升版。
- 不把所有 UI refresh 搬入 Application，也不展開全面 Main 重構。
- Project JSON 仍使用 temporary write、atomic replace 與 `.bak`；本 change 的 `.rollback` 契約只涵蓋 managed DXF asset。

## Why

健康檢查已在數個入口重現正式資料更新後仍可能留下舊 metadata、錯誤 dirty、舊結果／cache 或舊 DXF status。現行 commit 也仍呼叫 property setter、collection mutation 與可能觸發 UI 的 helper，無法證明中途不會部分完成。另有 managed DXF save 在 rollback 自身失敗時刪除或於下一次 save 覆蓋 recovery copy 的風險，這些都破壞既有 workflow 對 commit／rollback 的承諾。

## What Changes

- 定義 Project load、Support／Single result adoption、CAD input mutation 與 Material Spec mutation 的一致 transaction outcome，並禁止 commit 呼叫 setter、trace、callback、filesystem 或 collection mutation。
- 將結果失效、metadata、cache replacement 與 dirty finalization 納入 staged state；projection 失敗後鎖住修改，新增完整重新投影入口。
- CAD mutation 已 commit 但 ACK 失敗時停止監聽並阻止 save，直到 pending event 被明確處理；相同 event ID 不得重複套用。
- 修正 managed DXF persistence cleanup：rollback 失敗時保留 `.rollback` 並回報；既有 recovery artifact 未處理前拒絕下一次 save。
- 增加各入口 commit 中途的 fault-injection 或不可拋錯證據，並以 Global Waler 的 committed／refreshed outcome 作為語意相容性基準。

### In Scope

- 上述四種 runtime mutation、Project load adoption 與 managed DXF save rollback。
- committed state、results、metadata、cache、DXF status、dirty 與 projection-stale guard 的一致性。
- projection 失敗後的資料修改鎖定及完整重新投影入口。
- CAD ACK unresolved 與既有 `.rollback` 的安全停止行為。

### Out of Scope

- CAD transport queue、Solver cancellation、Project schema migration。
- 大規模拆分 `main.py`、新增第二種 persistence backend。
- 自動修復使用者磁碟或外部程式持續鎖定的檔案。
- Project JSON `.bak`／atomic replace 的新 rollback 格式；`.rollback` recovery contract 只屬於 managed DXF。

## Capabilities

### New Capabilities

- `project-state-transaction-consistency`: 定義 Project mutation、result adoption、load 與 persistence rollback 的一致 commit／failure semantics。

### Modified Capabilities

- 無；既有 capability 的產品行為不重新定義，這個 capability補足跨流程共同契約。

## Impact

- 影響 `main.py`、Project／Result Application models、MaterialSpecEditing outcomes、CAD event integration、完整 UI projection orchestration 與 `project_persistence.py`。
- 不改 persistence schema，但修改 filesystem failure handling 與錯誤回報。
- Architecture 沿用既有 layer；Application transaction responsibility 會更完整，`docs/WORKFLOW.md` 與必要的 `docs/ARCHITECTURE.md` 將在實作後更新。

