# Proposal

## 閱讀導航

| 優先級 | 要回答的問題 | 文件／段落 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | 為什麼要改、使用者會看到什麼？ | 本文件「快速摘要」「現況與目標」「主要流程」「不變事項」 | 在 30 秒內確認產品方向與範圍。 |
| P0 現在必讀 | 預覽與明確採用目前有哪些安全約束？ | `openspec/specs/dxf-corner-brace-repair-tool/spec.md`「修補必須先預覽再明確採用」 | 確認介面重整不能跳過候選檢核或使用者確認。 |
| P0 現在必讀 | 介面文字與數值必須保留什麼？ | 同一主規格「角撐修補介面須使用繁體中文」 | 確認工程 ID、座標、單位與內部值仍可稽核。 |
| P1 實作前閱讀 | 版面、預覽圖層與格式化如何落實？ | `design.md` 的 Decision 1～4；本 change delta spec | 依既有 Presentation boundary 實作，不建立第二套工程規則。 |
| P2 需要時再讀 | 現有 UI 與 overlay 位於何處？ | `dxf_import/dialog.py` 的 `_show_corner_brace_repair_window`、`_on_corner_brace_repair_candidate_selected`、`_draw_corner_brace_repair_overlay` | 修改 Tkinter widget、選取更新或圖面 overlay 時查閱。 |

本次可以先跳過主規格中的 reference eligibility、候選排序、unresolved create、Pause／Resume replay、原子提交與 persistence 細節；這些行為不在本 change 內改動。也不需要閱讀 Solver specs，因為本 change 不涉及最佳化。

## 快速摘要

- 現有角撐修補預覽以九欄候選表格為主，單一候選的常見情境仍需閱讀大量重複且偏稽核用途的資料。
- 新介面保留既有候選選擇能力，但單一候選以「建議修補方案」為主，先呈現目標關係、移植方式與結果長度。
- 圖面預覽以灰色顯示所選角撐 exact source geometry 的全部來源線段，並以醒目但不混淆的樣式顯示建議角撐軸線與定位錨點。
- `reference_waler_offset_mm`／`reference_strut_station_mm` 的使用者可見名稱統一為「圍令端定位距離」／「支撐端定位距離」，並使用已確認的量測基準說明。
- 角撐修補預覽的工程長度、定位距離與座標分量統一顯示至小數第 3 位；長度與定位距離帶 `mm`，座標維持無單位，候選資格、排序、幾何與提交流程維持不變。

## 現況與目標

| 面向 | Before：目前介面 | After：目標介面 |
| --- | --- | --- |
| 資訊入口 | 九欄表格同時混合主要決策、模板尺寸與稽核證據。 | 先顯示目標關係、移植方式、模板與結果長度；次要證據置於稽核／診斷區。 |
| 單一候選 | 仍以候選比較表呈現，且表格與下方明細重複。 | 以單一「建議修補方案」呈現；仍須按「套用此修補」明確採用。 |
| 多候選 | 表格供使用者選取候選。 | 保留可選取候選的能力，不為少見多候選情境新增或改變候選規則。 |
| 來源幾何 | exact target residual 以橘色虛線疊加於既有 Review preview。 | 所選角撐的全部 exact source line segments 以低干擾灰色顯示；建議軸線與錨點維持清楚區隔。 |
| 定位尺寸 | 使用不易直接理解量測方向的局部模板術語。 | 使用「圍令端定位距離」「支撐端定位距離」，並顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」 |
| 數值格式 | 表格多為 1 位小數、明細多為 3 位，座標直接使用 Python tuple 格式。 | 工程長度與定位距離固定三位小數並帶 `mm`；座標每個分量固定三位小數且維持無單位。 |
| 稽核資訊 | 候選明細與 diagnostics 直接鋪在主要畫面。 | 稽核與診斷區預設收合，可明確顯示／隱藏，且切換只改變 Toplevel 的 Presentation state。 |

## 主要流程

```text
開啟角撐修補預覽
        ↓
查看建議方案的目標關係、模板、移植方式與結果長度
        ↓
在圖面中比較灰色原始來源線段與建議角撐軸線
        ↓
確認「圍令端定位距離」「支撐端定位距離」與有效性
        ↓
需要時展開稽核／診斷資料
        ↓
明確套用或取消
```

若存在多個合法候選，使用者仍需先選定一個候選；選取後更新同一組摘要、圖面與稽核內容。

## 不變事項

- 不改變角撐修補候選的生成、資格、排序、去重或多候選規則。
- 不改變 automatic primary、manual repaired secondary、target evidence 或 finite geometry 的工程語意。
- 不改變 `DXFReviewWorkflow` 的 commit、rollback、confirmation invalidation 或 Pause／Resume 行為。
- 不改變正式 CornerBrace 幾何、Project schema、persistence contract、Domain、Solver 或其他 DXF 辨識流程。
- 即使只有一個合法候選，也不會自動套用；取消或關閉仍保持零副作用。

## Why

目前預覽介面把主要決策資訊、模板局部尺寸與稽核證據平鋪在同一張寬表，且數值精度不一致，使常見的單一候選確認工作難以快速判讀。這次調整讓使用者先看修補結果與原始來源幾何，再按需查看診斷資料，同時保留完整可追溯性與既有安全邊界。

## What Changes

### In Scope

- 重整角撐修補預覽的資訊層級，為單一候選提供直接的建議方案摘要。
- 保留多候選選取能力；選取候選後以相同摘要與明細區呈現。
- 在預覽圖層以灰色顯示所選角撐 exact source geometry 的全部來源線段，並區分建議軸線與定位錨點。
- 將使用者可見欄位改為「圍令端定位距離」與「支撐端定位距離」，並顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」
- 將角撐修補預覽內的工程長度、定位距離與座標分量統一格式化至小數第 3 位；只有工程長度與定位距離帶 `mm`，座標維持無單位。
- 將稽核與診斷區設為預設收合，提供明確的顯示／隱藏操作，且不得影響候選選取、Apply state、overlay 或正式 Review state。
- 更新 Presentation 層的 focused tests，涵蓋文字、格式、單一／多候選狀態、稽核區狀態及 overlay 樣式。

### Out of Scope

- 不修改 `dxf_import/corner_brace_repair.py` 的候選規劃與工程檢核。
- 不新增候選、放寬目標證據或改變多候選出現條件。
- 不修改其他 Review 工具、主視窗、Solver UI 或 Project persistence。
- 不進行 `dxf_import/dialog.py` 的大型拆分或無關重構。
- 不新增使用者可編輯的幾何或定位尺寸欄位。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `dxf-corner-brace-repair-tool`：修改「修補必須先預覽再明確採用」與「角撐修補介面須使用繁體中文」的可觀察介面行為，明確定義摘要層級、灰色 exact-source 預覽、直觀定位尺寸名稱與小數三位格式。

## Impact

- **主要程式**：`dxf_import/dialog.py` 的角撐修補 preview window、候選選取明細與 temporary overlay。
- **可能共用的顯示邊界**：若既有 `bracing_optimizer/presentation/field_labels.py` 適合承載新增的共用術語，可在不改變內部欄位名稱的前提下沿用；否則完整句子留在 DXF dialog。
- **測試**：`tests/test_dxf_review_layout.py` 為主要 Presentation contract；必要時補充不需啟動完整 Tk mainloop 的 overlay／格式化 focused tests。既有 `tests/test_dxf_corner_brace_repair.py` 應作為候選行為未改變的 regression coverage。
- **相容性**：沒有 API、資料 schema、序列化或 migration 影響。
- **長期 truth**：不預期修改 `ARCHITECTURE.md`、`DOMAIN.md`、`SOLVER.md` 或 `WORKFLOW.md`；這是既有 Presentation 責任內的 user-visible refinement。

## 已確認的實作限制

- 本 change 沒有會改變 scope 或驗收條件的未決事項。稽核與診斷區必須預設收合，並提供「顯示稽核與診斷」／「隱藏稽核與診斷」操作。
- 灰色來源線只投影 `plan.residual_segments`；不得重新掃描 DXF、不得重複建立同一 residual overlay item，也不得把顯示線段當成新的 eligibility evidence。
