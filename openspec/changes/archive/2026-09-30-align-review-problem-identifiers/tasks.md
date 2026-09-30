# Tasks

## 實作前閱讀

- **Group 1 前**：閱讀 `proposal.md`「現況與目標／不變事項」、`design.md` Decision 1～4，以及 delta spec「問題說明須使用可在清單定位的代號」。
- **Group 2 前**：閱讀 delta spec「顯示代號不得取代診斷 identity」及 `design.md`「Architecture Alignment／Risks」。
- **Group 3 前**：回看 `proposal.md` 的 In Scope／Out of Scope，確認沒有修改 recognition qualification、ReviewItem 分組、persistence 或 Solver。

## 1. 建立問題說明顯示代號投影

- [x] 1.1 在 `tests/test_dxf_review_items.py` 先新增 `build_problem_records()` 行為測試，涵蓋：只替換該則 `ValidationMessage.source_handles`／structured competing identities 中的 handle；文字 handle 未結構化列出時保留；同時出現來源 `232` 與量測 `232 mm` 時只替換前者；`°`、`%`、小數與座標不替換；以 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_items -v` 驗證新增測試在實作前失敗、實作後通過。
- [x] 1.2 在 `dxf_import/validation.py` 新增集中式 formatter，只以該 message 的 structured handle allowlist 查詢目前正式 ownership，並由 `build_problem_records()` 唯一套用至 `ProblemRecord.description`；驗證不得以全 result ownership index 做全文搜尋或使用無邊界 `str.replace()`，且 `severity`、`code`、`component`、`role`、`source_handles`、`member_ids` 全部維持原值。
- [x] 1.3 實作 `正式 ID（來源 handle）` 格式：unique owner 顯示如 `W6（232）`；同一 member 多 handles 只顯示一次 ID 並於同一括號列出 handles；multi-owner 依 numeric-aware 自然排序顯示 `W2` 在 `W10` 前並固定以 `／` 分隔。新增 W2／W10、member collection 反序、compound-source 去重測試後，以 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_items -v` 驗證。

## 2. 固定實際診斷與 Review 顯示整合

- [x] 2.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 新增或調整 Y29 regression，確認 `WALER_SOURCE_OVERLAP` 與 `WALER_OVERLAP_COMPETITION` 的 `ProblemRecord.description` 顯示 `W6（232）`、`W12（4E4）`，而非只顯示 `232`、`4E4`；同時原始 `ValidationMessage.source_handles`、severity、code 與 blocking truth 不變。
- [x] 2.2 盤點現有文字含 handle 的 diagnostics（至少 BIM block Waler span／finalization、terminal ambiguity、`MULTIPLE_MODELS_FROM_ONE_SOURCE`），新增 characterization assertions：只有該 message structured fields 已列出的 handle 才可轉換；文字有 handle 但 structured fields 未列出時保留原文。另新增未解析 `待修-FB7` 與已排除 `已排除-FB7` 都只保留 `FB7` 的測試，並執行各鄰近 focused tests。
- [x] 2.3 驗證全體問題清單與選取項目的「問題／處理建議」明細仍共用同一 `ProblemRecord.description`，必要時在 `tests/test_dxf_review_items.py` 或既有 dialog projection test 加 assertion；不得在 `dxf_import/dialog.py` 建立第二套 formatter。

## 3. 回歸與規格驗證

- [x] 3.1 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_items tests.test_dxf_waler_contact_face_recognition tests.test_dxf_bim_block_recognition -v`，確認問題投影、數值保護、自然排序、Y29 overlap 與 BIM characterization regression 全數通過。
- [x] 3.2 依實際 diff 擴大執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_workflow tests.test_dxf_source_exclusion tests.test_dxf_review_recovery -v`；確認 selection、排除、還原、rebuild 仍使用原 structured identities。
- [x] 3.3 檢查最終 diff 只包含本 change artifacts、`dxf_import/validation.py` 與直接相關測試，且不含 Solver、persistence schema、ReviewItem 分組或無關 cleanup；若發現原訊息已包含 member ID 而形成 `W6 來源 W6（232）` 類重複，記錄於驗證結果但不擴大本次修改；若 long-term Architecture／Domain／Solver／Workflow truth 未改變，不更新其文件。
- [x] 3.4 執行 `openspec validate align-review-problem-identifiers --strict`，再依 `openspec-verify-change` 流程核對 implementation、delta spec 與 tasks，確認所有 requirements／scenarios 有測試證據且無超出 proposal scope 的修改。
