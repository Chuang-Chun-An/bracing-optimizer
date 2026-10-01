# Proposal：校準 Repository 文件與真相來源

## 閱讀導航

### P0｜現在必讀

1. 本文件「快速摘要」、「現況與目標」及「In Scope／Out of Scope」：確認這次只維護文件，不改變系統行為。
2. `README.md` 的第 1～3、10、15、16 節：本次主要清理範圍。
3. `docs/ARCHITECTURE.md`「Purpose and Architecture Goals」與 `README.md`「文件分層」：確認各文件的責任。
4. `docs/DEVELOPMENT_HISTORY.md` 開頭近期封存紀錄：區分歷史事實與現行規格。

### P1｜實作前閱讀

- `design.md`：閱讀保留／刪除內容的判準，以及 README 不再維護逐函式鏡像的決定。
- `tasks.md`：依「入口文件、長期文件、驗證」順序執行。
- 與待修文字直接相關的程式入口及測試；只用來驗證現況，不修改程式。

### P2｜需要時再讀

- `docs/DOMAIN.md`、`docs/SOLVER.md`、`docs/WORKFLOW.md` 中與被修改段落直接相關的章節。
- 已封存的 2026-10-01 changes；只有追溯決策來源時才讀。
- `openspec/specs/` 其餘 capability、DXF recognition 全部細節與 Solver 全部 call chain 本次可先跳過。

## 快速摘要

- 目前 README 同時扮演入口、API 索引、架構文件、歷史紀錄及技術債清單，部分內容已落後實作。
- 本 change 將 README 收斂為可維護的專案入口與現況導覽，移除已不存在或已解決的敘述。
- `docs/*` 繼續保存長期 Architecture／Domain／Solver／Workflow truth；OpenSpec main specs 繼續保存精確行為要求。
- 不修改程式、測試、工程規則、Solver 行為、Project schema 或 UI workflow，也不藉文件整理決定尚有歧義的產品規則。

## 現況與目標

| 項目 | Before：目前 | After：本 change 完成後 |
|---|---|---|
| README 角色 | 同時保存高階導覽、逐函式索引、完整 call graph、歷史測試快照及待重構清單 | 作為專案入口、閱讀地圖、主要功能與操作／開發入口；詳細規則連結至既有長期文件與 specs |
| UI 描述 | 仍列出已移除的「測試案例」頁籤與相關方法 | 對齊目前 Engineering／Materials／Analysis 三個 workspace 及其子頁籤 |
| Legacy schema | 仍提到 `_migrate_strut_position_fields()` 與離線升級舊專案 | 對齊目前 schema 3：只接受現行 row contract，不提供 legacy 欄位轉換工具 |
| Waler 評估 | 技術債段落仍稱自動與人工評分重複 | 記錄兩者已共用 `evaluate_waler_plan()`，不再把已完成工作列為待辦 |
| 測試狀態 | 保留 2026-07-30 的 12 tests／1 failed 快照及過時 UCS 說明 | 提供可重跑的驗證指令，不把易過期的測試數量與歷史失敗當成現況 |
| 歷史資料 | 現況與歷史資訊混在 README | 歷史變更保留於 `docs/DEVELOPMENT_HISTORY.md` 與 archived changes，不作為現行行為來源 |

## 主要流程

```text
已提交的程式、tests、main specs
        ↓ 只讀比對
辨識「現況說明／長期規則／歷史紀錄」
        ↓
更新 README 入口與直接受影響的長期文件
        ↓
檢查連結、符號引用、OpenSpec strict validation 與文件 diff
        ↓
確認沒有程式行為或 normative requirement 變更
```

## 不變事項

- `AGENTS.md` 仍是 Agent 工作規則與閱讀順序的最高專案指引。
- `docs/ARCHITECTURE.md`、`DOMAIN.md`、`SOLVER.md`、`WORKFLOW.md` 分別保存各自的長期真相。
- `openspec/specs/` 仍是已成立 capability 的精確行為規格；archive 只保存決策歷程。
- `docs/DEVELOPMENT_HISTORY.md` 的歷史紀錄不因現況文件重寫而刪除或改寫成現行要求。
- 所有程式、資料格式、Solver scoring、UI 行為與測試 assertion 維持不變。

## Why

1～7 的架構與規則修正已完成並提交，但入口文件仍保留舊 UI、legacy migration、重複評分及早期測試失敗等敘述。若直接繼續開發，接手者會同時看到互相衝突的現況，因此需要先校準文件角色與內容。

## What Changes

- 將 README 的定位從「程式碼完整鏡像」收斂為 repository 入口、系統概覽、操作／開發導覽與真相來源索引。
- 修正已確認的過時內容：測試案例 UI、移除的方法、legacy schema 升級、Waler 評分重複、舊測試失敗、過時 UI 結構及可由程式自動取得而不應手寫維護的數量。
- 對齊這次已完成的 Support Shim、暫時庫存政策、schema compatibility、manual Project result-only DXF、Material Spec editing ownership、legacy normalization 移除及 Waler evaluator 共用狀態。
- 檢查長期文件與 main specs 的交叉引用；只修正可由已成立程式、tests、main specs 明確判定的描述。
- 將仍需產品決策的 CornerBrace repair candidate authority 留在獨立待澄清項目，不在本 change 中選邊修改 normative spec。

## In Scope

- `README.md` 的文件角色、閱讀順序、系統／UI 現況、資料格式、開發入口、技術債及測試說明。
- `docs/ARCHITECTURE.md`、`docs/DOMAIN.md`、`docs/SOLVER.md`、`docs/WORKFLOW.md` 的直接交叉引用與少量一致性修正。
- 文件中指向已移除 class、method、module、tool、workflow 或 active change 的引用。
- 文件驗證：符號搜尋、連結／路徑檢查、OpenSpec strict validation，以及確認 diff 只含規劃與文件。

## Out of Scope

- 修改任何 Python、LISP、資料檔、測試或應用程式行為。
- 改變 Domain rule、Solver scoring／搜尋參數、材料比例、庫存計算、schema compatibility 或 DXF contract。
- 重新設計 CornerBrace repair requirements；其 template authority 矛盾需要使用者另行決定。
- 把所有 archived change 內容搬回 README，或逐一重述所有 OpenSpec scenarios。
- 為了讓文件看起來簡潔而進行程式重構、重新命名或刪除 compatibility code。

## Capabilities

### New Capabilities

無。本 change 是純文件維護，`.openspec.yaml` 使用 `skip_specs: true`。

### Modified Capabilities

無。不修改任何已成立 requirement 或 scenario。

## Architecture／Domain／Solver／Workflow Truth

- **Architecture**：不改變依賴方向或 state ownership，只讓入口文件正確指向既有 owner。
- **Domain**：不新增或修改工程規則。
- **Solver**：不修改合法性、評分、比例、候選或搜尋政策，只移除已過期的重複評分描述。
- **Workflow**：不修改 runtime 流程，只讓 README 對齊已成立的 Project、Material Spec 與 DXF export workflow。

## 尚未決定的事項

`dxf-corner-brace-repair-tool` 一處要求每個可 Apply candidate 都必須有 automatic-primary template，另一處允許 unique body 的 `body_relationship_selection` 建立 candidate。程式目前支援後者，但文件本身無法決定產品規則。此項不納入本次文字校正；只有使用者確認兩條路徑是否都應存在及各自 provenance 要求後，才另立 spec change。

## Impact

- 主要影響 `README.md`。
- 視交叉檢查結果，可能小幅修改 `docs/ARCHITECTURE.md`、`docs/DOMAIN.md`、`docs/SOLVER.md`、`docs/WORKFLOW.md`。
- 不影響 code、public API、Project JSON、dependencies、tests 或部署產物。
