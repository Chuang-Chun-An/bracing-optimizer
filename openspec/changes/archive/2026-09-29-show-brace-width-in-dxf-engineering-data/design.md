# Design

## 閱讀導航

- **現在必讀**：Decision 1、Decision 2；決定顯示資料來源與避免修改 Project row contract 的方式。
- **實作前閱讀**：Decision 3、Decision 4；決定可靠值判定、格式與限縮的構件角色。
- **條件式閱讀**：Architecture Alignment 與 Risks；只有在實作需要跨出 `dxf_import/dialog.py`、加入 persistence 欄位或變更辨識結果時才需重新評估。
- **可先跳過**：Migration Plan；本 change 沒有資料遷移，僅需確認回滾方式。

## 方案摘要

DXF Review 右側工程資料仍由既有 member 建立顯示列。對 `Brace` 與 `CornerBrace`，Presentation 在既有 Project-row-derived rows 與「構件長度」之間插入一個 UI-only 寬度列；數值直接讀取 `source_width`，通過有限且大於零判定後格式化為三位小數，否則顯示「—」。

```text
DXFReviewWorkflow.result member
              |
              | read only
              v
DXFImportDialog._engineering_data_rows()
              |
      +-------+--------+
      | Brace /        | other role
      | CornerBrace    |
      v                v
append width row     keep current rows
      |
      v
right-side engineering data widgets
```

本 change 中的「構件寬度」是既有 `source_width` 的工程資料顯示名稱，不是新增欄位，也不代表 Presentation 取得寬度判定權。

## 決策對照

| Decision | 影響的 Spec | 對應 Task |
|---|---|---|
| D1：以既有 `source_width` 為唯一資料來源 | 「斜撐與角撐寬度顯示」、「顯示不得改變工程資料 contract」 | 1.1、2.1 |
| D2：加入 UI-only row，不修改 `to_project_row()` | 「顯示不得改變工程資料 contract」 | 1.1、2.2 |
| D3：只顯示有限且 `> 0` 的值，固定三位小數 | 「斜撐與角撐寬度顯示」 | 1.2、2.1 |
| D4：只套用 `Brace` 與 `CornerBrace` | 「其他構件維持既有工程資料」Scenario | 1.1、2.1 |

## Context

動機與範圍見 `proposal.md`。現行 `Brace` 直接持有 `source_width`，`CornerBrace` 透過 `AuxiliaryComponent` 持有相同欄位；Importer 已把辨識候選寬度寫入這些 members。`DXFImportDialog._engineering_data_rows()` 先使用 `to_project_row()` 組合右側工程資料，再額外加入構件長度，因此寬度雖存在於 DXF Review model，卻不在工程資料中。

既有架構將 `dialog.py` 定位為 DXF Presentation，允許它把 Workflow 的 read-only snapshot 投影成 UI；正式 WCS／projected result 仍由 `DXFReviewWorkflow` 擁有。這使本 change 可以停留在 Presentation，而不需修改 recognition、workflow 或 Project boundary。

## Goals / Non-Goals

**Goals:**

- 在斜撐與角撐的右側工程資料加入一致、可測試的寬度列。
- 明確處理未知、零、負值與非有限值，避免顯示虛假工程尺寸。
- 維持 DXF member 為寬度 single source of truth，Presentation 僅格式化。
- 以 focused presentation tests 保護角色範圍、格式與 contract 不變性。

**Non-Goals:**

- 不改善或重寫斜撐、角撐辨識與 repair 流程。
- 不讓使用者在此欄位編輯寬度。
- 不把寬度加入 Project rows、持久化、匯出或 Solver input。
- 不為單一顯示列拆分 Dialog 或建立新的跨層 abstraction。

## Decisions

### Decision 1：直接讀取 member 的既有 `source_width`

`source_width` 是 recognition 已保存的寬度結果，也是目前「DXF 辨識資料」使用的來源。工程資料顯示 SHALL 讀取同一欄位，不從端點、source geometry、selected rails、材料規格或相鄰構件重新推導。

這可維持 single source of truth：辨識層負責判定寬度，Presentation 只決定是否及如何顯示。

**替代方案：** 在 Dialog 依來源線重新量測。拒絕，因為會讓 Presentation 複製辨識規則並可能產生第二個寬度 truth。

### Decision 2：寬度是 UI-only row，不加入 `to_project_row()`

實作在 `_engineering_data_rows()` 取得既有 rows 後，針對目標角色插入 `("構件寬度（mm）", display_value)`。此列不需要先建立虛擬 Project key，也不修改 `Brace.to_project_row()` 或 `AuxiliaryComponent.to_project_row()`。

寬度列應位於既有欄位之後、構件長度之前，使尺寸資訊相鄰，同時維持目前長度列位於最後的布局慣例。

**替代方案：** 將 `Width` 加入 `to_project_row()`，再交由共用 field-label mapping 翻譯。拒絕，因為 `to_project_row()` 是 DXF → Project boundary；僅為 UI 顯示新增 key 容易被誤認為正式 Project contract，並擴大 persistence／export 影響面。

### Decision 3：集中使用明確的顯示判定與格式

Presentation 應以一個小型、可直接測試的格式化路徑判定：值可轉成有限數字且 `> 0` 時使用 `f"{value:.3f}"`；其餘顯示「—」。不得使用 truthiness 判定，避免 `NaN`／`Infinity` 被格式化為看似有效的文字。

此判定只控制 UI fallback，不重新定義 recognition 對可靠寬度的工程規則。

**替代方案：** 沿用一般 `_review_display_value()`。拒絕，因為一般 formatter 不具備本 spec 的有限正值與固定三位小數 contract。

### Decision 4：以正式 runtime type 限定顯示角色

新增列只套用 `Brace` 與 `CornerBrace`。`CornerBrace` 雖繼承 `AuxiliaryComponent`，不得讓所有 auxiliary roles 因繼承共同欄位而一起顯示；其他角色的工程資料保持現況。

**替代方案：** 所有具有 `source_width` 的 members 一律顯示。拒絕，因為使用者已確認的範圍只有斜撐與角撐，且會改變 Waler、Strut、Column、Beam 等既有介面。

## Data Flow

1. 使用者在左側構件樹選取正式斜撐或角撐。
2. Dialog 從既有 Review snapshot 找到對應 member。
3. `_engineering_data_rows()` 先建立現行工程資料 rows。
4. Presentation 讀取該 member 的 `source_width` 並套用顯示判定。
5. Dialog 插入「構件寬度（mm）」row，再沿用既有 widget rendering。
6. 全程不產生 command、不更新 Workflow，也不回寫 member 或 Project row。

## Architecture Alignment

- **採用既有 Architecture，不修改架構本身。**
- **受影響 layer：** 僅 DXF Presentation；預期修改 `dxf_import/dialog.py` 與相鄰 presentation tests。
- **依賴方向：** `DXF Presentation → read-only DXF member model` 維持現況；不新增 Recognition → Presentation、Domain → UI 或 Algorithms → UI 依賴。
- **State ownership：** 寬度 authoritative value 仍在 Workflow result 所持有的 DXF member；Dialog 僅建立 transient display string。
- **旁路確認：** 左側 summary、Preview、角撐修補 preview、diagnostics 與 export 不共用本次 UI row，也不應增加另一套寬度格式或推導邏輯。

## Backward Compatibility and Persistence

- 既有 member dataclass、`to_project_row()`、Project schema 與 serialized DXF Review state 均不變。
- 舊專案或舊 paused Review 可照常載入；若其 member 寬度為未知值，只會在新 UI 顯示「—」。
- 不需要 schema migration、資料回填或 compatibility adapter。

## Risks / Trade-offs

- **[Risk] 「構件寬度」可能被誤認為人工可編輯的正式 Project 欄位。** → 維持唯讀顯示，且不加入 `to_project_row()` 或 Project column labels。
- **[Risk] 修補角撐常保留未知寬度，使用者可能看到「—」。** → 這是保守且可稽核的 fallback；若要推定 repair width，需另立 engineering rule 與 change。
- **[Risk] type 判定過寬會讓其他 auxiliary members 出現新欄位。** → 測試明確覆蓋 `Brace`、`CornerBrace` 與至少一個非目標角色。
- **[Trade-off] 寬度在「DXF 辨識資料」與「工程資料」都會出現。** → 接受此重複：前者表達辨識 provenance，後者支援工程檢核；兩者仍讀取同一值，沒有資料 drift。

## Migration Plan

1. 發布 Presentation 與測試變更；不執行資料 migration。
2. 以 focused tests 驗證目標角色、未知值、格式與 Project row 不變性。
3. 若需回滾，只還原 UI row 與相關測試；既有資料無需轉換或復原。
