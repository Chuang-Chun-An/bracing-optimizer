# Tasks

## 實作前閱讀

- **Task Group 1 前**：閱讀 `proposal.md` 的 In Scope／Out of Scope、`design.md` Decision 1，以及 spec Requirement「角撐修補介面須使用繁體中文」的「預覽合法候選」「顯示移植方式」「重複概念使用一致術語」Scenario。
- **Task Group 2 前**：閱讀 `design.md` Decision 2，以及同 Requirement 的「修補不可執行或提交失敗」Scenario；區分共用短術語、UI 完整句子與 repair-specific diagnostics。
- **Task Group 3 前**：閱讀 `design.md` Decision 3、Architecture Alignment 與 Backward Compatibility；確認不需要重讀 Solver 或其他 recognition specs。

## 1. 建立共用術語並中文化角撐修補預覽

- [x] 1.1 在 `bracing_optimizer/presentation/field_labels.py` 擴充具名的共用角色與修補移植方式 display helper，至少提供 `corner_brace → 角撐`、`same_side → 同側移植`、`mirrored → 鏡射移植`，未知值保留原值；以 `tests/test_field_labels.py` 驗證固定對照、fallback 與原始 key 不被改寫。
- [x] 1.2 在 `dxf_import/dialog.py` 將角撐修補可用性說明、預覽說明、Treeview 表頭、選取提示與候選明細改為繁體中文，並讓角色及 transfer mode 使用 Task 1.1 的共用 helper；以 `tests/test_dxf_review_layout.py` 驗證既知英文 UI 標籤已由中文取代、重複概念使用同一術語，且構件 ID、座標、數值與 `mm` 保持原值。
- [x] 1.3 驗證角撐修補候選選取與 commit 仍使用原 candidate ID、`same_side`／`mirrored` DTO 值，不將中文 label 寫回 workflow 或 persistence；以 layout／workflow tests 覆蓋 display-only boundary。

## 2. 中文化拒絕診斷與錯誤

- [x] 2.1 在修改診斷文字前，搜尋 production code 對 repair diagnostics／`DXFImportError` 完整句子的 equality、substring、prefix／suffix 或其他控制流程依賴；確認不存在後才繼續，若存在則停止實作並回報需重新評估 structured diagnostic boundary，不得只同步替換判斷字串。
- [x] 2.2 盤點 `dxf_import/corner_brace_repair.py` 中會到達 Preview 或 messagebox 的 repair-specific diagnostics 與 `DXFImportError`，直接將人類可讀文字改為繁體中文且不新增 diagnostic code／payload、不更動分支條件；以 `tests/test_dxf_corner_brace_repair.py` 驗證無方向、無錨點、無合格 template、relationship ambiguity、無合法候選及提交失敗的中文原因。
- [x] 2.3 檢查角撐修補流程是否仍有共用英文 validation 訊息直接外露；若有，僅在角撐修補顯示邊界轉換並新增對應測試，若無則以來源搜尋結果記錄完成；完整說明句不得加入 `field_labels.py`，且不得修改其他 DXF Review 流程文案。

## 3. 驗證與完成度檢查

- [x] 3.1 執行 `python -m unittest tests.test_field_labels tests.test_dxf_review_layout tests.test_dxf_corner_brace_repair`，確認共用術語、中文介面與既有候選生成、排序、幾何及 atomic commit 回歸測試全部通過。
- [x] 3.2 依影響範圍執行 DXF Review 相關回歸測試，至少涵蓋 `tests.test_dxf_review_workflow` 與 source exclusion／Pause-Resume repair replay 測試，確認 persistence payload 與內部英文識別值未變。
- [x] 3.3 執行 `openspec validate localize-corner-brace-repair-ui --strict`，並逐項對照 proposal scope、design Decisions、spec Scenarios 與本 tasks checklist 完成 OpenSpec implementation verification；確認共用 labels 僅包含穩定短術語，且無 Solver、Project schema、Architecture／Domain／Workflow truth 或不相關 UI 修改。
