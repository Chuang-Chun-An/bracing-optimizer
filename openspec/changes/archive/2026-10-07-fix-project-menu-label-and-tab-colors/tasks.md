# Tasks

## 實作前閱讀

- **Group 1 前**：讀 [proposal.md](./proposal.md) 的「現況與目標／不變事項」、[design.md](./design.md) 的 D1／D2／D3，以及 `main-window-project-controls` delta 的兩項 Requirements；確認測試要先重現 menu index 缺陷，且配色不得切換全域 theme。
- **Group 2 前**：重讀 design D1 與 spec「主視窗專案操作必須集中於選單列」的「Project 狀態更新只改變 Project cascade」Scenario；只修改 `main.py` menu construction／projection 與相鄰 tests。
- **Group 3 前**：重讀 design D2 與 spec「主、次工作區頁籤必須具有可辨識的視覺層級」；主 `self.notebook` 用 Primary，`engineering_notebook`／`materials_notebook`／`analysis_notebook` 用 Secondary。
- **Group 4 前**：讀 design D3、Risks／Trade-offs 與 Migration Plan；可先跳過 Domain、Solver、DXF recognition、persistence 及其他不相關 specs，本 change 不修改其行為。

## 1. 建立可重現缺陷與樣式契約的測試

- [x] 1.1 擴充 `tests/test_main_window_project_controls.py` 的 menu construction／projection 測試，讓 fake 或 real Tk 語意包含 tear-off index、驗證 `project_menu_index` 來自建立後的實際 entry、normal／pending-save／warning 只更新 Project cascade，並確認舊的固定 `entryconfigure(1, ...)` 實作會失敗；執行 `.\.venv\Scripts\python.exe -m unittest tests.test_main_window_project_controls -v` 驗證測試可辨識缺陷。
- [x] 1.2 在同一 focused test module 增加 Notebook style contract，驗證 palette 只設定 `Primary.TNotebook(.Tab)` 與 `Secondary.TNotebook(.Tab)`、未呼叫 `theme_use()`，且一個主 Notebook 與三個次 Notebook 使用正確 style；執行該 test module 確認新增 assertions 可執行。
- [x] 1.3 增加或擴充 Windows Tk smoke test，使用 withdrawn real root 讀回三個 cascade labels 與兩組 style 的 default／`selected`／padding；無圖形環境依既有測試慣例 skip，Windows Tk 可用時必須驗證狀態刷新後仍為「檔案／Project 狀態／說明」。

## 2. 修正 Project cascade identity 與 recovery 位置

- [x] 2.1 修改 `main.py` 的 `_build_project_menu_and_toolbar()`：最上層 menu bar 明確使用 `tearoff=False`，加入 Project cascade 後由 widget 取得並保存 `project_menu_index`；以 Group 1 menu tests 驗證 File／Project／Help 初始順序不變。
- [x] 2.2 修改 `_sync_main_menu_projection()`：以保存的 `project_menu_index` 更新三類 Project label，並以 `project_menu_index + 1` 插入／刪除 stale recovery command；執行 `tests.test_main_window_project_controls` 與 `tests.test_project_state_transactions`，驗證無重複 command、File／Help label 不變及既有 stale transaction semantics 通過。

## 3. 套用雙層藍灰 Notebook 樣式

- [x] 3.1 在 `main.py` 新增具名且集中的 Primary／Secondary palette 與小型 style 初始化 helper，依 design D2 設定 default、`selected`、`active`、`disabled` 與 padding，且不修改全域 `TNotebook`／`TNotebook.Tab`、不呼叫 `theme_use()`；以 Group 1 style tests 驗證色值與隔離範圍。
- [x] 3.2 將 `self.notebook` 指定為 `Primary.TNotebook`，並將 `self.engineering_notebook`、`self.materials_notebook`、`self.analysis_notebook` 指定為 `Secondary.TNotebook`；執行 focused tests確認頁籤文字、順序、bind handler與下方 `context_toolbar` wiring 未變。
- [x] 3.3 在 Windows 啟動主程式進行 UI smoke，確認畫面顯示單一「檔案／專案／說明」結構、主頁籤深藍灰選取與次頁籤較淡層級可辨識、hover／disabled 文字可讀，且 Treeview、Button、Entry、Dialog 與原生 menu bar 未被全域換色；若目前 theme 忽略背景，只依 design D2 採局部 foreground／padding／字重 fallback並重新 smoke。

## 4. 回歸與 OpenSpec 驗證

- [x] 4.1 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_main_window_project_controls tests.test_project_state_transactions tests.test_software_information tests.test_project_navigation_guard -v`，驗證 menu、Project transaction、Help 與 navigation 相鄰行為全部通過。
- [x] 4.2 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_application_domain_boundaries -v`，確認純 Presentation 變更未新增跨層依賴。
- [x] 4.3 執行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 完成全套 regression；不得刪除測試、降低 assertion 或忽略非本 change 造成的失敗，任何既有失敗都需在回報中區分。
- [x] 4.4 對照 proposal In／Out of Scope、delta specs 與 design Decisions 檢查無不相關修改，執行 `openspec validate fix-project-menu-label-and-tab-colors --strict` 及 `$openspec-verify-change fix-project-menu-label-and-tab-colors`，確認 implementation 與兩項 Requirements 一致後才標記完成。
