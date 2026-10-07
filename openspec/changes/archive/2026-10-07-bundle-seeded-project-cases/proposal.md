# Proposal

## 閱讀導航

- **P0／現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認正式包將預置兩個可開啟、可儲存、可刪除的 Project，且不封裝 `.bak`。
- **P0／現在必讀**：本 change 對 `release-package-assets` 的 delta spec，尤其「正式發行包預置兩個 Project 案例」與「正式 Project 素材來源必須可重現」Requirements。
- **P1／實作前閱讀**：`design.md` 的 D1～D4，以及 `SupportSolver.spec`、`tests/test_dxf_assets.py` 與 `docs/WORKFLOW.md`「Save / Load Persistence」。
- **P2／需要時再讀**：若修改 Project schema 或 load transaction，才讀 `project-schema-compatibility` 與 `project-state-transaction-consistency`；本案不修改這些 contract。Solver、Domain、DXF recognition 與成果匯出可以先跳過。

## 快速摘要

- 現行正式包刻意不含任何 Project，因此新安裝的 Project 清單為空；本案改為固定提供 `Y05車站第一層支撐` 與 `Y29車站第一層支撐`。
- 每個案例只交付正式 `project.json` 與 managed `source/source.dxf`，明確排除 `project.json.bak`、測試 fixture 與其他 runtime Project。
- 兩個案例會出現在既有 Project repository／開啟流程中，並沿用一般 Project 的儲存、另存與刪除行為。
- Repository 以獨立、tracked 的 release asset 快照作為 build input；被 Git 忽略的 runtime `project_cases/` 不成為正式來源。
- 本案只改發行資產邊界與長期 workflow 說明，不改 Project schema、persistence transaction、Domain 或 Solver。

## 現況與目標

| 面向 | Before | After |
| --- | --- | --- |
| 首次 Project 清單 | 空白 | 顯示 `Y05車站第一層支撐`、`Y29車站第一層支撐` |
| 正式包 Project | 不含 `project_cases/` | `project_cases/` 精確包含兩個核准案例 |
| 每個案例內容 | 無 | `project.json` 與 `source/source.dxf` |
| 備份檔 | 不適用 | 初始正式包不含 `project.json.bak`；使用者日後儲存時仍由既有流程產生 |
| Build source | runtime `project_cases/` 被忽略且不可重現 | tracked release asset 快照，透過明確 allowlist 複製 |

## 主要流程

```text
目前兩個 Project 的核准快照
  -> tracked release asset 來源
  -> SupportSolver.spec 精確 allowlist
  -> dist/SupportOptimizer/project_cases/<案例>/
  -> 既有 Project repository 列舉
  -> 使用者以既有 Open／Save／Save As／Delete 流程操作
```

## 不變事項

- `project.json` schema version、managed DXF relative path 與載入驗證不變。
- Save 仍以 `.tmp` 驗證、atomic replace 及 `.bak` 備份完成；本案只是不預置 `.bak`。
- `sample_dxf/` 的三份使用者 DXF、runtime assets、軟體歷程資源及其既有 allowlist 不變。
- `project_cases/` 仍是成品執行期的可寫 Project repository；預置案例不新增唯讀或保護語意。
- 進行中的 `simplify-main-window-project-controls` 可繼續使用同一 repository 列舉結果；本案不修改其選單或 Open dialog 行為。

## Why

正式發行版本需要讓使用者安裝後即可開啟兩個現有工程案例，不必先自行匯入或建立 Project。現行 release contract 明確禁止預置 Project，因此必須先修訂發行資產邊界，並用可重現的精確 allowlist 避免重新引入整包 runtime／測試資料。

## What Changes

- 將目前 `Y05車站第一層支撐` 與 `Y29車站第一層支撐` 的正式內容建立為 tracked release asset 快照。
- 修改 `SupportSolver.spec`，把兩個案例的 `project.json` 與 `source/source.dxf` 複製到成品 `project_cases/` 的相同 managed layout。
- 明確禁止將兩個案例的 `project.json.bak`、其他 Project、`test_cases/` 或 `tests/fixtures/` 帶入正式包。
- 更新 package contract tests，驗證來源 allowlist、Project JSON 可載入、DXF 可讀、輸出 layout 與禁止項目。
- 實際建置乾淨的 Windows onedir 成品，驗證兩個案例能從既有 Project 清單開啟。
- 更新 README 與 `docs/WORKFLOW.md`，將「首次清單為空」改為兩個預置案例的新 long-term truth。

## In Scope

- 兩個指定 Project 的 release snapshot 與封裝 layout。
- 發行包首次 Project 清單、既有開啟／儲存／刪除流程的相容性。
- `release-package-assets` capability、封裝測試與發行文件。

## Out of Scope

- 自動還原、版本化或 UI 開啟 `project.json.bak`。
- 將預置案例設為唯讀、不可刪除或每次啟動自動補回。
- 修改 Project schema、DXF recognition、Solver、Domain 或 persistence transaction。
- 合併、改寫或完成 `simplify-main-window-project-controls` change。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `release-package-assets`：正式包由「不預置任何 Project」改為精確預置兩個指定 Project 案例，同時保留 regression-only 資料排除與可重現 build 邊界。

## Impact

- **Release**：`SupportSolver.spec`、tracked release assets、`dist/SupportOptimizer/project_cases/` layout 與成品大小（不含 `.bak` 時約增加 41.6 MiB）。
- **Tests**：`tests/test_dxf_assets.py` 及必要的 release asset helper／Project load validation。
- **Documentation**：README、`docs/WORKFLOW.md`、`release-package-assets` main spec（sync／archive 時）。
- **Architecture**：沿用現有 filesystem／persistence boundary，不新增 layer 或反轉 dependency。
- **Domain／Solver**：無變更。

## 尚未決定事項與重新評估條件

目前沒有未關閉的需求問題。若實作盤點發現任一 `project.json` 無法由現行 schema／load contract 驗證，或其 managed DXF 不等於案例內的 `source/source.dxf`，必須停止並重新評估核准快照，不得在 build 階段靜默修補 payload。
