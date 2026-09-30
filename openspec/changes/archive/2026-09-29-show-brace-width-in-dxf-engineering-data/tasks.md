# Tasks

## 實作前閱讀

- **Task group 1 前**：讀 `proposal.md` 的 In Scope／Out of Scope、`design.md` Decision 1～4，以及 spec「斜撐與角撐寬度顯示」；確認只改右側工程資料、只讀既有 `source_width`。
- **Task group 2 前**：讀 `design.md` 的 Architecture Alignment／Backward Compatibility，以及 spec「顯示不得改變工程資料 contract」；確認不修改 `to_project_row()`、Project schema 或其他角色。
- **Task group 3 前**：回讀完整 spec 與 `tasks.md`，確認所有 Scenario 都有測試或明確驗證證據。
- 可先跳過其他斜撐／角撐辨識與 Solver 文件；只有實作被迫修改 recognition、repair、persistence 或 Solver 時才停止並重新評估 scope。

## 1. 右側工程資料寬度顯示

- [x] 1.1 在 `dxf_import/dialog.py` 的工程資料列組裝中，僅針對 `Brace` 與 `CornerBrace` 加入 UI-only「構件寬度（mm）」列，放在既有工程欄位之後、構件長度之前；以 code review 或 focused assertion 驗證其他 member roles 不新增此列。
- [x] 1.2 在 Presentation 層加入有限且 `> 0` 的寬度顯示判定：有效值固定三位小數，其餘回傳「—」；以 `350.0`、`300.0`、`0`、負值、`NaN` 與 `Infinity` 測試驗證格式與 fallback。

## 2. 行為與 contract 測試

- [x] 2.1 在 `tests/test_dxf_review_layout.py` 或相鄰 DXF Review presentation test 中新增斜撐、角撐與非目標構件案例，驗證標籤、三位小數、未知值、「構件長度」仍為最後一列，以及其他角色顯示不變；執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_layout -v` 並確認通過。
- [x] 2.2 新增或補強 contract assertion，確認顯示工程資料前後的 member／`to_project_row()` 不變，且未新增 Project、persistence、export 或 Solver 欄位；執行相關 DXF review/model focused tests 並確認通過。

## 3. 完整驗證

- [x] 3.1 執行 DXF Review 相關測試（至少涵蓋 `test_dxf_review_layout.py`、`test_dxf_review_items.py` 與 `test_dxf_review_application.py`），確認既有選取、工程資料與 Review 行為沒有回歸。
- [x] 3.2 執行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 作為 final regression test，記錄通過結果與任何已知且確認無關的既有失敗。
- [x] 3.3 對 `show-brace-width-in-dxf-engineering-data` 執行 OpenSpec strict validation／implementation verification，逐項核對 proposal scope、design Decisions、spec Scenarios 與 tasks，確認沒有修改左側清單、Preview、辨識、repair width、Project schema、persistence、export 或 Solver。
