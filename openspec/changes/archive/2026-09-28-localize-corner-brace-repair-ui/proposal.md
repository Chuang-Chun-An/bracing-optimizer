# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」、「現況與目標」、「In Scope／Out of Scope」；`specs/dxf-corner-brace-repair-tool/spec.md` 的「角撐修補介面須使用繁體中文」。
- **P1 實作前閱讀**：`design.md` 的「Decision 1：共用術語集中在既有 Presentation label boundary」與「Decision 2：完整句子留在最窄責任邊界」；既有 `openspec/specs/dxf-corner-brace-repair-tool/spec.md` 中「修補必須先預覽再明確採用」。
- **P2 需要時再讀**：`docs/ARCHITECTURE.md` 的 DXF import 模組責任；若測試發現文案來自非 UI 邊界，再查 `dxf_import/corner_brace_repair.py` 的 diagnostics／exception 來源。
- **本次可先跳過**：Solver、材料比例、一般 Brace／Strut／Waler recognition，以及 `dxf-corner-brace-centerline-extension` 中純幾何求點的需求；本 change 不改這些行為。

## 快速摘要

- 角撐修補視窗目前同時出現中文與英文，使用者必須理解 `Selected template`、`Transfer`、`Waler offset` 等術語才能判讀候選。
- 將修補入口、預覽說明、表格欄位、候選明細、拒絕原因與修補失敗訊息統一為繁體中文。
- 可重複使用的角色與移植方式術語集中到既有 Presentation label boundary，讓角撐修補與其他介面可逐步共用同一名稱。
- `corner_brace`、`same_side`、`mirrored` 等內部值仍維持既有 contract，只在顯示層轉成「角撐」、「同側移植」、「鏡射移植」。
- 修補候選、工程驗證、排序、提交、回復與持久化行為完全不變。

## 現況與目標

| | 現況（Before） | 目標（After） |
|---|---|---|
| 預覽視窗 | 中文標題中夾雜英文說明與欄位名稱 | 使用者可見的說明與欄位名稱均為繁體中文 |
| 候選明細 | 顯示 `Transferred axis`、`Target`、`mode` 等英文標籤 | 以一致的中文工程用語呈現相同資料 |
| 共用術語 | 角色與修補移植方式可能由各視窗各自翻譯 | 可重複術語由既有共用 Presentation label boundary 提供 |
| 狀態值 | 直接顯示 `same_side`／`mirrored` 等內部列舉值 | 共用顯示「同側移植」／「鏡射移植」，但不改內部值與持久化資料 |
| 診斷與錯誤 | 部分 planner 診斷及例外會直接以英文出現在訊息框 | 角撐修補流程呈現給使用者的原因與錯誤為繁體中文 |

「使用者可見文字」指角撐修補入口至預覽、套用或拒絕過程中，出現在按鈕、視窗、表格、說明標籤與訊息框的文字；程式內部識別字不在此定義內。

## 主要流程

1. 使用者在 STEP4 選取可修補的角撐並開啟修補預覽。
2. 系統沿用既有 planner 產生候選與診斷，不改任何工程判斷。
3. Presentation 從既有共用 label boundary 取得角色與移植方式術語；視窗完整句子與專屬診斷仍由各自責任邊界提供。
4. 使用者選取、套用或取消候選；既有 atomic commit 與零副作用取消語意維持不變。

## 不變事項

- 不修改 CornerBrace repair eligibility、reference selection、candidate ranking 或幾何計算。
- 不修改自動辨識、Solver、Project schema、Review state schema 或 persistence payload。
- 不翻譯工程構件 ID、座標、數值、單位及供程式判斷的內部 enum／key。
- 不進行角撐修補以外的全系統國際化或 UI 重構。
- 不要求本次一次改寫主畫面與 DXF 匯入介面所有既有局部角色字典；共用術語可由後續工作逐步採用。

## Why

角撐修補是需要人工判讀工程證據的安全流程，但現有預覽與錯誤訊息仍大量混用英文，降低中文使用者判讀候選與拒絕原因的效率。現在應將這條已成立的工作流程完整中文化，使其與專案其餘繁體中文介面一致。

## What Changes

### In Scope

- 將角撐修補視窗的說明、表格欄位、空白提示、候選明細與操作回饋改為繁體中文。
- 在既有 Presentation label boundary 集中可重複的角色與角撐修補移植方式術語，至少涵蓋 `corner_brace`、`same_side` 與 `mirrored`，並保留未知值的可診斷 fallback。
- 讓角撐修補介面使用共用術語來源；完整的視窗說明、操作引導與訊息框句子仍留在各自 UI boundary。
- 將會直接到達角撐修補訊息框或預覽區的 planner diagnostics、disabled reason 與 commit error 改為繁體中文。
- 新增或調整聚焦測試，驗證主要介面不再暴露既知英文標籤，且 UI 仍只讀 candidate DTO、不重算工程規則。

### Out of Scope

- 不建立通用 i18n framework、語系切換或英文介面選項。
- 不將既有 repair-specific diagnostics 重構為 structured diagnostic code／payload。
- 不為了消除所有既有重複而重構主畫面或整個 DXF 匯入介面。
- 不更名 Python 類別、欄位、常數、持久化 key 或既有 domain term contract。
- 不修改角撐修補候選內容、順序、資格、安全門檻或提交行為。
- 不清理其他 DXF Review 畫面或其他功能的中英文混用。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-corner-brace-repair-tool`：補充角撐修補流程的使用者可見介面、診斷與錯誤訊息必須使用繁體中文，並明定內部工程資料 contract 不因顯示翻譯而改變。

## Impact

- **主要程式**：`bracing_optimizer/presentation/field_labels.py` 的共用術語與顯示函式、`dxf_import/dialog.py` 的角撐修補預覽；必要時調整 `dxf_import/corner_brace_repair.py` 中會直接呈現給使用者的 repair-specific diagnostics／exceptions。
- **測試**：共用 label helper 測試、`tests/test_dxf_review_layout.py`；若翻譯 planner 訊息，補充 `tests/test_dxf_corner_brace_repair.py` 的中文訊息與行為不變檢查。
- **相容性**：無 API、資料格式或 persistence migration；內部識別值維持原狀。
- **長期文件**：Architecture、Domain、Solver 與 Workflow truth 預期均不改變，因此不預計修改其文件。

## 已確認決策與重新評估條件

- 已確認採「共用術語集中、完整句子就地維護」：角色、欄位、辨識方式與修補移植方式等穩定詞彙可進入既有 Presentation label boundary；包含上下文的說明、警告與操作引導不建立全域整句字典。
- 已確認本次直接調整 repair-specific diagnostics 的人類可讀文字；只有未來需要多個 Presentation consumer、多語系或程式邏輯穩定消費診斷時，才另行評估 structured diagnostic boundary。
- 若實作時發現共用 validation 訊息同時被其他流程使用，應優先在角撐修補顯示邊界處理。只有無法在不重複邏輯的情況下完成時，才重新評估是否擴大共用訊息範圍。
