# Proposal

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「In Scope／Out of Scope」；先確認本次只修正 DXF Review 問題文字的顯示代號。
- **P0／現在必讀**：`openspec/specs/dxf-review-engineering-data-presentation/spec.md` 的「Review 必須呈現重疊來源與重建資訊」；既有 Review 顯示與唯讀投影邊界。
- **P0／現在必讀**：`dxf_import/validation.py` 的 `build_problem_records()` 與 `build_review_items()`；目前診斷轉成問題列與清單項目的位置。
- **P1／實作前閱讀**：本 change 的 `design.md`「顯示代號解析」與 delta spec「問題說明須使用可在清單定位的代號」。
- **P2／需要時再讀**：`openspec/specs/dxf-waler-overlap-diagnostics/spec.md`；只有確認重疊診斷的 source identity contract 時才讀。可先跳過 Solver、材料配置、接觸面幾何判定及其他辨識規格，因本次不改其規則。

## 快速摘要

- 問題說明目前可能顯示 DXF source handle，例如 Y29 的 `232`、`4E4`，但左側清單顯示 `W6`、`W12`，使用者無法直接對照。
- 正式構件已存在時，問題說明採 `正式 ID（來源 handle）`，例如 `W6（232）`；尚未形成正式構件時，保留可對應 `待修-<handle>` 或 `已排除-<handle>` 的來源 handle。
- 只處理該則 `ValidationMessage` 結構化欄位已列出的 handles；不以整個 result 的 ownership index 對自由文字全文搜尋，未結構化的文字 handle 保留原文並由測試記錄。
- 多 owner 依左側清單相同的自然排序顯示並固定使用 `／`，例如 `W2（ABC）／W10（ABC）`。
- 底層 `ValidationMessage.source_handles`、member identity、辨識與 blocking 判定維持不變；這是唯讀顯示投影，不是工程規則變更。

## 現況與目標

| | Before | After |
|---|---|---|
| 已辨識來源 | 問題說明可能只顯示 `232`、`4E4`，清單顯示 `W6`、`W12` | 問題說明顯示 `W6（232）`、`W12（4E4）`，同時保留正式 ID 與來源追溯 |
| 未辨識／已排除來源 | 問題說明顯示 source handle，清單顯示 `待修-<handle>` 或 `已排除-<handle>` | 保留 source handle，不猜測正式 ID |
| 診斷資料 | source handles 用於定位、重建與 exclusion | 完全不變，只在問題文字投影正式構件 ID |
| 替換資格 | 尚未定義結構化範圍與數值保護 | 只替換該訊息結構化列出的 handles，且不替換單位、百分比、小數或座標中的數值 |

## 主要流程

```text
ValidationMessage（保留原始 structured identities）
    → 只取該訊息 source_handles／structured competing identities
    → 以目前 DXFImportResult ownership 解析正式 member ID
    → 產生 ProblemRecord 顯示文字
       ├─ 已有正式 member：顯示 W6（232）
       ├─ 無 owner／已排除：保留 handle
       └─ 單位、小數、座標 token：不替換
    → 問題總表與構件明細共用相同文字
```

## 不變事項

- 不改 Waler overlap、terminal、contact-face 或其他辨識資格與嚴重度。
- 不改 `ValidationMessage.source_handles`、`member_ids`、Review selection、來源排除與 rebuild identity。
- 不改左側清單的正式 ID、`待修-<handle>` 或 `已排除-...` 命名規則。
- 不改 Project schema、persistence、export、Solver input、Solver scoring 或工程限制。

## Why

DXF Review 的問題說明與左側構件清單使用不同代號域時，使用者無法由錯誤訊息判斷實際要檢查哪一支構件。Y29 W6／W12 的重疊只是已確認案例；同一缺口也存在於其他會把 source handle 寫進說明的診斷，因此需要統一問題文字的顯示規則。

## What Changes

- 問題說明引用已形成正式 Review member 的結構化來源時，改用 `正式 ID（來源 handle）`。
- 替換候選只來自該則 `ValidationMessage.source_handles` 或該訊息明確保存的 structured competing identities；文字中未被結構化列出的 handle 不替換。
- 緊接 `mm`、`°`、`%` 的 token，以及小數或座標的一部分不替換，避免全數字 handle 與工程數值碰撞。
- 同一來源若明確對應多個正式 members，依自然排序顯示所有可定位 IDs，以 `／` 分隔，不任選其中一個。
- 無正式 member owner 或已排除的來源維持 source handle，使其仍能對應既有 `待修-<handle>` 或 `已排除-<handle>` 清單項目。
- 問題總表與選取構件的「問題／處理建議」明細使用相同投影結果。
- 新增涵蓋 Waler overlap、一般正式構件來源、未解析來源與多 owner 邊界的測試。

### In Scope

- `ValidationMessage` 到 `ProblemRecord` 的顯示文字投影。
- 該訊息結構化 handles 與目前已辨識 member ID 的對應。
- DXF Review 問題總表與構件問題明細的代號一致性。
- Y29 W6／W12 overlap、數值碰撞、自然排序、multi-owner／multi-handle、未解析與已排除來源 regression。

### Out of Scope

- 修改 recognition 診斷內容的結構化 identity、資格、severity 或 blocking truth。
- 從整個 result 的 handles 對 message 自由文字全文搜尋，或替換未列於該訊息 structured fields 的 handle。
- 改名、重新排序或重新編號正式構件。
- 改變 unresolved ReviewItem 的分組或 `待修-<handle>` 命名。
- 新增點擊連結、搜尋功能或重新設計問題面板。
- 任何 Solver、工程規則、Project persistence 或 export 變更。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-review-engineering-data-presentation`：新增問題說明必須使用可在目前 Review 清單定位之顯示代號的行為，並明定顯示投影不得取代底層 source identity contract。

## Impact

- 主要受影響程式：`dxf_import/validation.py`。
- 可能調整的測試：`tests/test_dxf_review_items.py`、`tests/test_dxf_waler_contact_face_recognition.py`，以及已固定 raw handle 顯示的鄰近辨識測試。
- Architecture：沿用既有 DXF validation／Review projection boundary，不改 layer responsibility。
- Domain／Solver／Workflow truth：不變；本次是 Presentation-facing diagnostic projection 行為。
- 相容性：不改資料模型欄位與持久化格式，沒有 migration。

## 尚未決定事項

- 無產品行為上的未決事項。實作必須使用該訊息的 structured handle allowlist、自然排序與數值語境保護；不得以自由字串猜測建立新的工程 identity。
