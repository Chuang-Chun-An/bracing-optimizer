# Tasks

## 實作前閱讀

- Task Group 1：閱讀 `proposal.md` 的「現況與目標」、delta spec 的「Y29 C25 為可修補案例」「非中間柱選取」「清單選取在柱與支撐之間切換」「圖面與清單選取結果一致」，以及 `design.md` D1、D2。
- Task Group 2：閱讀 delta spec 的「有效已修柱可查看並撤銷」「需重新檢查柱顯示失效原因」「Preview 開啟後改選其他構件」「未形成正式 Column 的待修項目不啟用工具」，以及 `design.md` D3～D5。
- Task Group 3：閱讀主 spec 的「採用與撤銷必須可預覽且原子提交」、delta spec 的「對應柱不存在的失效決策仍在問題清單可見」，以及 `design.md` 的 Architecture Alignment、Backward Compatibility 與 Migration Plan。

## 1. 固定目前選取中間柱的入口契約

- [x] 1.1 在實作前以 `tests/test_double_support.py` 既有或新增 focused assertion 確認 `plan_column_association_repair()` 對已修柱提供 `status="repaired"`、目前 `selected_strut_ids` 與可供既有 `withdraw_column_association_repair()` 使用的完整 plan；若 contract 不成立，停止並回報，不修改 Presentation 或 Workflow API。
- [x] 1.2 在 `tests/test_dxf_review_layout.py` 新增目前選取正式 Column、Strut、Brace、Waler、無選取與未形成正式 Column 的待修 ReviewItem 案例，驗證只有正式 Column selection 能解析為 repair subject，且不掃描／替代成其他可修補柱。
- [x] 1.3 新增清單、圖面與清除 selection 的入口同步測試，驗證柱→支撐時入口隱藏或停用、支撐→柱時入口出現，且清單與圖面選取同一項目的結果一致。
- [x] 1.4 在 `dxf_import/dialog.py` 新增以既有 Review selection 與 `world_result.columns` 解析目前正式 Column ID 的小型 helper，並讓所有清單選取、圖面點選與清除 selection 完成路徑重新評估 `_update_modification_tools()`；執行 1.2、1.3 測試驗證非柱與未正式形成的 Column 項目無法使用入口。

## 2. 改為單一中間柱修補 Preview

- [x] 2.1 在 `tests/test_dxf_review_layout.py` 增加 command boundary 測試，驗證開啟時會重驗目前 selection、只以該 Column ID 呼叫 plan API，且 stale／非柱／無選取不建立可套用 Preview、不改變正式 state。
- [x] 2.2 新增「已修柱可開啟、顯示目前選擇並以既有 plan 撤銷」測試，以及「`requires_review` 柱可開啟並顯示既有同來源 problem 原因」測試；驗證 Presentation 不解析候選、原因或撤銷資料。
- [x] 2.3 調整 `dxf_import/dialog.py` 的 `_open_column_association_repair()`，移除全案 subject Listbox 與視窗內切換流程，依既有 plan 的 `unresolved`／`repaired`／`requires_review` 狀態顯示單一柱 detail、選項、overlay、套用或撤銷，並沿用既有 plan／commit／withdraw API；執行 2.1、2.2 與既有 column repair layout tests。
- [x] 2.4 新增 Preview 開啟後主畫面改選其他構件的測試，驗證 Preview 仍固定原 `plan.column_id`，提交只由既有 stale validation 接受或拒絕；同時新增無人工決策且不合格柱的測試，驗證不回退全案其他合法柱。
- [x] 2.5 在 Review item／problem tests 新增人工決策對應 Column 已不存在的案例，驗證 `COLUMN_ASSOCIATION_REQUIRES_REVIEW` 仍出現在既有問題清單且不啟用修補工具；不得建立虛構 Column subject。

## 3. 回歸驗證與文件同步

- [x] 3.1 實作完成後更新 `docs/WORKFLOW.md` 的中間柱關聯修補入口描述為「先選取中間柱，再開啟該柱的單一 Preview」，並確認未宣稱改動工程資格、Domain 或 Solver truth。
- [x] 3.2 執行 `tests/test_dxf_review_layout.py`、相關 Review item／selection tests 與 `tests/test_double_support.py`，驗證 Presentation 新流程、已修撤銷、`requires_review` 原因、orphan decision problem，以及既有 plan／commit／withdraw、單選／雙選、stale rejection、Resume 行為無回歸。
- [x] 3.3 執行與 DXF Review selection／layout 相關的擴大測試，確認清單、圖面、清除選取三條路徑及斜撐、支撐、圍令與其他修改工具行為未受影響；記錄任何非本 change 造成的既有失敗，不以降低 assertion 處理。
- [x] 3.4 執行 `openspec validate focus-column-association-repair-on-selection --strict`，再依 proposal scope、delta spec scenarios、design decisions 與本清單逐項核對實作，確認無全案柱清單、無非正式 Column／非柱入口、已修與失效決策仍可被正確查看、orphan problem 未消失，且無工程規則或 persistence 變更。
