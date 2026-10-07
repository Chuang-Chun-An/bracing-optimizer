# Proposal

## 閱讀導航

- **P0／現在必讀**：本文件的「快速摘要」、「現況與目標」、「In Scope／Out of Scope」；`specs/software-information-presentation/spec.md` 的「可從主視窗開啟軟體資訊」與「顯示可辨識的軟體身分」。
- **P1／實作前閱讀**：`design.md` 的 Decision 1～3；`docs/ARCHITECTURE.md` 的「3.1 Presentation」；`main.py` 的 `_build_project_menu_and_toolbar()`；`SupportSolver.spec` 的 release data 清單。
- **P2／需要時再讀**：若調整歷程來源或封裝驗證，再讀 `openspec/specs/archive-development-history/spec.md` 與 `openspec/specs/release-package-assets/spec.md`。
- **可先跳過**：`docs/DOMAIN.md`、`docs/SOLVER.md`、Project persistence、DXF recognition 與所有 Solver capability；本次不改變工程規則、最佳化或專案資料格式。

## 快速摘要

- 現在使用者無法在程式內確認產品名稱、版本、作者與開發歷程。
- 新增一個固定的「說明 → 軟體資訊」入口，開啟可捲動且不會修改 Project 的資訊視窗。
- 視窗集中顯示產品名稱、版本、作者「莊竣安（Chuang Chun An）」，以及 `docs/DEVELOPMENT_HISTORY.md` 的完整「起始歷史紀錄」；版本與作者不散落硬編碼於 widget。
- 正式封裝必須與原始碼執行環境呈現相同資訊；歷程不可依賴 repository 路徑或網路連線。
- Project、DXF、Solver、材料規則與既有儲存流程維持不變。

## 現況與目標

| 面向 | Before／現況 | After／目標 |
|---|---|---|
| 入口 | 主視窗只有「檔案」選單 | 主視窗增加「說明」選單及「軟體資訊」命令 |
| 軟體身分 | 版本只存在於 `pyproject.toml`，作者沒有產品 UI | 資訊視窗集中顯示產品名稱、版本與作者 |
| 開發歷程 | 「起始歷史紀錄」只在 `docs/DEVELOPMENT_HISTORY.md`，成品使用者看不到 | 資訊視窗只顯示該區段的全部紀錄，維持文件原始順序與內容 |
| 執行環境 | source 與 PyInstaller 成品沒有共同的可見契約 | 兩種環境均能顯示相同的必要資訊；資源異常時給出明確替代訊息 |

「開發歷程」在本 change 專指 `docs/DEVELOPMENT_HISTORY.md` 中「起始歷史紀錄（截至 2026/09/28 早上）」標題下、下一個同層標題前的全部表格紀錄。UI 不顯示「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或「AI 對話統計」，也不把歷程視為可編輯的 Project state。

## 主要流程

```text
主視窗
  → 說明
    → 軟體資訊
      → 顯示產品名稱／版本／作者
      → 顯示可捲動的開發歷程
      → 關閉後返回原 Project，無狀態變更
```

## 不變事項

- 不修改 Architecture 的 dependency direction；這是 Presentation 與產品 metadata 的新增行為。
- 不修改 Domain、Solver、DXF、材料政策、Project schema、dirty state 或 save/load truth。
- 不改變 `docs/DEVELOPMENT_HISTORY.md` 既有 archive workflow 與人工內容保護規則。
- 不引入網路查詢、自動更新、授權檢查或遙測。

## Why

目前程式缺少統一的產品資訊入口，使用者與維護者無法在執行中的正式成品確認版本、作者或主要變更。集中提供唯讀資訊可降低回報問題時的版本辨識成本，也讓 release 的開發歷程能直接被使用者看到。

## What Changes

- 在主視窗增加「說明」選單，並提供「軟體資訊」命令。
- 新增獨立、可重複開啟的軟體資訊視窗，集中顯示產品名稱、版本、作者與開發歷程。
- 建立不依賴 Tkinter 的產品資訊模型／provider，讓 UI 與測試共用同一份顯示資料。
- 將「起始歷史紀錄」的精確結構化投影作為正式 runtime resource 隨 PyInstaller 成品交付，並定義來源一致性與資源缺漏／無法讀取時的降級顯示。
- 新增 focused tests，驗證 metadata、選單入口、視窗內容、唯讀行為與 release resource。

## In Scope

- 「說明 → 軟體資訊」選單與唯讀視窗。
- 產品名稱、版本、作者「莊竣安（Chuang Chun An）」與「起始歷史紀錄」的集中顯示契約。
- source run 與 PyInstaller onedir 的資源解析及缺漏 fallback。
- 版本 `3.0.0` 與作者顯示名稱 `莊竣安（Chuang Chun An）` 的正式 metadata。
- 完整保留起始歷史紀錄的每筆日期文字、紀錄文字與文件原始順序；允許 UI 改用適合閱讀的排版，但不得摘要、刪減或加入其他區段。

## Out of Scope

- 自動檢查更新、下載新版、網路連結或 GitHub／外部服務整合。
- 在 UI 編輯版本、作者或開發歷程。
- 顯示 `docs/DEVELOPMENT_HISTORY.md` 的「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或獨立的「AI 對話統計」區段。
- 在「起始歷史紀錄」之外自行補入新的 release notes、OpenSpec artifacts 或其他歷史來源。
- 變更 Project 檔案版本、DXF 版本、Solver policy version 或任何工程規則。
- 為了此功能重構 `main.py` 其他既有 UI workflow。

## Capabilities

### New Capabilities

- `software-information-presentation`: 定義主視窗入口、軟體身分欄位、使用者可讀開發歷程、唯讀／無副作用行為與資源異常 fallback。

### Modified Capabilities

- `release-package-assets`: 正式發行包新增只含「起始歷史紀錄」精確投影的 runtime resource，並持續排除完整工程歷程、Project 與 regression-only fixtures。

`archive-development-history` 不修改：既有 `docs/DEVELOPMENT_HISTORY.md` 仍是長期歷程的 authoritative source；本 change 只讀取其已受保護且不由 archive workflow 改寫的「起始歷史紀錄」，並產生供成品顯示的精確投影。

## Impact

- **Presentation**：`main.py` 的 menu wiring，以及 `bracing_optimizer/presentation/dialogs/` 下的新資訊視窗。
- **產品資訊**：新增小型、無 Tkinter 依賴的 metadata／history provider；`pyproject.toml` 的 release version 必須與 runtime version 一致，作者完整字串必須有精確值測試。
- **Release**：`SupportSolver.spec` 納入起始歷史紀錄的精確投影資源，並擴充內容一致性與封裝資產測試。
- **Tests**：增加 provider、dialog/menu contract 與 package asset focused tests；現有 architecture boundary tests 必須維持通過。
- **長期文件**：預期不改變 Architecture、Domain、Solver 或 Workflow truth；若實作後 runtime resource 清單成為新的長期 release truth，只更新 README／release capability，不提前改寫其他長期文件。

