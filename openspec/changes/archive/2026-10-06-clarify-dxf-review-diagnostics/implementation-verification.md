# Implementation Verification

## 閱讀導航

- **現在必讀（P0）**：先看「結論」與「代表案例」，即可確認最終可見文案、fallback A 與診斷真相保護結果。
- **實作前閱讀**：若要修改本 change，先讀 `proposal.md`「In Scope／Out of Scope」、`design.md` Decision 1～4，以及 delta spec 的兩個 requirements。
- **需要時再讀**：測試命令與完整回歸範圍見「自動化驗證」；88-code 完整分類與 producer 位置見 `design.md` Decision 3。

## 結論

- 全部問題清單與選取項目明細共用 `ProblemRecord` 的中文問題類型與 description；原始 code 僅保留作內部 identity，沒有新增查看 raw code 的 UI。
- 88 個已知 code 已固定分為保留原文 63 個、專用 formatter 23 個、已知 fallback 2 個；未知 code 也採 fallback A。
- 白話投影不改動原始 `ValidationMessage`、severity、排序、錯誤／警告數量、`can_import` 或 blocking truth。
- fallback A 只顯示通用說明、構件 ID 與來源 handle，不顯示原始 message、raw code、reason token、exception 或 traceback。

## 代表案例

以下案例以最終 `build_problem_records()` 與 `review_item_guidance()` 投影檢查，順序皆為「問題類型 → 發生什麼事 → 處理建議」。

### 1. 辨識失敗：`BEAM_RECOGNITION_FAILED`

- 問題類型：`托梁辨識失敗`
- 發生什麼事：`來源幾何無法可靠辨識為正式托梁（構件 BM2；來源 BM2（J01））。`
- 處理建議：`請開啟「圖層 ✓」確認用途後重新辨識，並檢查原始 DXF 幾何。`
- 檢查：保留正式構件 ID `BM2` 與來源 handle `J01`；原始 `staged finalization`、`RuntimeError` 等內部文字未顯示。

### 2. 圍令重疊：`WALER_SOURCE_OVERLAP`

- 問題類型：`圍令來源重疊`
- 發生什麼事：`兩個圍令來源有重大共線重疊；重疊長度 1250.500 mm，占較短圍令 82.5%（來源 W6（232）／W12（4E4））。`
- 處理建議：`請定位問題列出的圍令來源與受影響端點，並依外部工程判斷檢查 DXF。若參與辨識的來源有變更，系統會重新辨識；本提示不推薦刪除、排除或保留任一來源。`
- 檢查：保留正式 ID `W6`、`W12`、來源 handle `232`、`4E4`，以及量測值 `1250.500 mm`、`82.5%`；未顯示 `source-supported` 或 `provisional axis`。

### 3. 構件關聯：`AMBIGUOUS_COMPONENT_ASSOCIATION`

- 問題類型：`構件關聯問題`
- 發生什麼事：`構件同時符合多個支撐關聯，需重新確認應採用的正式關聯（構件 S3；來源 S3（A03））。`
- 處理建議：`請先檢查相關構件的工程線與端點；若位置有誤，可由候選點或 CAD 工程線工具修正。`
- 檢查：保留正式構件 ID `S3` 與來源 handle `A03`；原始 `identity candidates` 等內部文字未顯示。

### 4. 未知 code：`NEW_DIAGNOSTIC_CODE`

- 問題類型：`斜撐檢核警告`
- 發生什麼事：`系統無法完成這項斜撐檢核，請檢查相關構件與來源圖元（構件 B7；來源 B7（B01））。`
- 處理建議：`請依上方問題內容檢查此構件；目前沒有對應的專用人工修正工具。`
- 檢查：只保留正式構件 ID `B7` 與來源 handle `B01`；未顯示 raw code、原始 `reason=secret_token ValueError secret traceback` 或任何未結構化量測值。

## 自動化驗證

- Focused suite：`134` tests passed。
- 完整 DXF suite：`845` tests passed，`1` skipped；跳過原因是工作區缺少既有 `source_*.dxf` fixture，沒有測試失敗。
- 分類 contract 測試會直接掃描列入 Design 的 producer 模組及 importer 動態 role 展開，確認 88 個已知 code 恰屬一類且三類互斥；producer 新增未分類 code 時會失敗。
- Workflow regression 確認 error／critical／warning 的順序、數量、blocking 與 `can_import` 不受顯示投影影響。

## OpenSpec Verification Report

| Dimension | Status |
| --- | --- |
| Completeness | 16／16 tasks；2／2 requirements 有實作與測試證據 |
| Correctness | 10／10 scenarios 有直接或組合 regression coverage |
| Coherence | 遵守 Design D1～D4；未發現 scope、dependency 或 persistence 偏離 |

### Issues by priority

- **CRITICAL**：無。
- **WARNING**：無。
- **SUGGESTION**：無。

### Final assessment

所有檢查通過，可交付 review；尚未執行 archive 或 main spec sync。
