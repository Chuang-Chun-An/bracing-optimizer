# Proposal

## Why

Support Solver Dialog 與 Single Waler Solver Dialog 目前可在背景 Solver 執行中被直接關閉，造成 Dialog 的 UI callback bridge 被關閉、後續結果顯示或採用流程遭捨棄，但背景 worker 仍持續執行。Global Waler Solver Dialog 已具備執行中禁止關閉的行為，本 change 將三種 Solver Dialog 的關閉政策統一，避免 UI 關閉要求破壞既有 Solver lifecycle。

## What Changes

### In Scope

- 三種 Solver Dialog 統一採用 running-state close policy：Support、Single Waler、Global Waler 在 Solver 執行中均不得直接關閉。
- 執行中的 window close request 不得 destroy Dialog、關閉其 UI callback bridge、中斷 Solver lifecycle，或修改 Solver result／operation state。
- Solver 正常完成、失敗或 worker 啟動失敗並離開 running state 後，恢復既有的正常關閉行為。
- 保留 Global Waler 已符合目標的 close guard，並補足三種 Dialog 的 regression coverage。
- 實作完成後，更新 `docs/WORKFLOW.md` 中已成立的 current behavior 與 product gap。

### Out of Scope

- 不新增真正取消、中止、join 或強制終止背景 Solver worker 的功能。
- 不修改 Solver algorithms、Support Phase 1／Phase 2、Waler search、scoring、candidate generation 或 progress calculation。
- 不修改 result commit／rollback 或 result adoption semantics。
- 不進行大型 Solver Dialog UI framework 重構，也不為此 change 整理無關 technical debt。

## Capabilities

### New Capabilities

- `solver-dialog-running-close-policy`: 定義 Support、Single Waler 與 Global Waler Solver Dialog 在 running 與 non-running 狀態下的一致關閉政策，以及完成或失敗後恢復關閉權限的行為。

### Modified Capabilities

無。

## Impact

- 主要受影響範圍是 Presentation 層的三種 Solver Dialog 與其 UI lifecycle 測試。
- 不改變 Application、Domain、Algorithms、Infrastructure、公開 API、資料格式或外部依賴。
- Architecture、Domain 與 Solver 的長期 truth 不變；Workflow truth 會在實作與驗證完成後，由「Support／Single Waler 可於執行中關閉」改為三種 Dialog 一致禁止執行中關閉。
