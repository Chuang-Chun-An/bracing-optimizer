# Proposal：DXF Review 診斷文字白話化

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「In Scope／Out of Scope」；先確認只改可見文案，不改辨識與阻擋規則。
- **P0／現在必讀**：`openspec/specs/dxf-review-engineering-data-presentation/spec.md` 的「問題說明須使用可在清單定位的代號」與「顯示代號不得取代診斷 identity」；保留既有定位及資料邊界。
- **P1／實作前閱讀**：本 change 的 `design.md` Decision 3「固定 code 分類與安全 fallback」與 delta spec「DXF Review 診斷須使用白話中文」；定義 88 個既有 code 的文案來源、fallback A 與測試邊界。
- **P1／實作前閱讀**：`dxf_import/validation.py` 的 `build_problem_records()`、`review_item_guidance()`，以及 `dxf_import/dialog.py` 的問題清單／明細投影。
- **P2／需要時再讀**：只在修改特定診斷測試時閱讀產生該診斷的 recognition／repair 模組。可先跳過 Solver、Project persistence、DXF result export，以及其他與 Review 診斷顯示無關的 specs。

## 快速摘要

- DXF Review 目前會把 `active sources`、`provisional`、`identity`、`baseline`、`staged finalization` 等內部詞彙直接顯示給使用者，且問題清單以原始大寫底線 code 當成「類型」。
- 本 change 將主要問題清單與選取項目的問題明細改為一致、精簡的繁體中文：先說「發生什麼事」，再說「使用者要檢查什麼」。
- 每個目前會形成 `ValidationMessage` 的 code 都固定歸入「保留原始 message」、「專用 formatter」或「使用 fallback」之一；不在執行時猜測原始文字是否夠清楚。
- Fallback 採用通用說明加上構件 ID 與來源 handle，不附原始 message；本次也不提供查看原始 diagnostic code 的 UI 入口。
- 原始 severity、diagnostic code、來源 handle、構件 ID、blocking truth 與辨識結果全部保留；文案不參與任何工程判斷。
- 不改 DXF 辨識、幾何容許值、警告／錯誤分級、可否完成匯入及既有修正工具。

## 現況與目標

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 問題類型 | 顯示 `WALER_CONTACT_FINALIZE_FAILED` 等內部 code | 顯示「圍令接觸位置無法確認」等可掃讀的中文類型 |
| 問題說明 | 混用 `Waler`、`identity`、`baseline`、`provisional`、`staged finalization` 等實作詞彙 | 使用「圍令」、「正式連接」、「調整基準」、「尚未確認」、「確認失敗」等工程操作語言 |
| 處理建議 | 部分文字抽象或夾帶 `active sources` | 指出畫面上可採取的檢查步驟，且不暗示系統沒有的工具 |
| 診斷真相 | code 與 message 同時承擔判斷和顯示責任 | structured diagnostics 維持判斷依據；顯示文案是唯讀投影 |

這裡的「診斷」是 DXF 辨識與檢核產生的結構化結果，包括等級、代碼、相關構件與來源圖元；本 change 只調整它在 Review 畫面上的說法。

## 主要流程

```text
既有 DXF ValidationMessage
  → 保留 severity／code／identity／blocking truth
  → 依 code 投影中文「類型、說明、處理建議」
  → 套用既有正式 ID（來源 handle）定位格式
  → 同一份結果顯示於全部問題清單與選取項目明細
```

無專用中文文案的新 code 必須使用安全、通順的通用 fallback，僅顯示通用說明、構件 ID 與來源 handle；不得顯示原始 message、大寫底線 code 或例外 reason token。

## 不變事項

- Diagnostic code 仍是程式、測試與問題追查的穩定 identity，不重新命名或刪除。
- Warning／error／critical 分級、阻擋匯入條件與數量統計不變。
- Source handle、正式 member ID、role 與既有點選定位行為不變。
- Recognition、geometry、validation、repair、rebuild、source exclusion 與 persistence 資料不因文案改變。
- 不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

## Why

目前 DXF Review 的部分警告直接暴露內部程式術語和診斷代碼，使用者需要先理解實作概念才能判斷問題與下一步。將診斷改成一致的白話繁體中文，可降低檢核負擔，同時保留工程安全與問題追查能力。

## What Changes

- 為 DXF Review 問題建立一致的使用者可見投影：中文類型、白話說明、可執行的處理建議。
- 主要問題清單與選取項目明細使用同一份投影，不再把原始 diagnostic code 當作主要類型文字。
- 將內部英文與程式狀態詞改成工程人員可直接理解的繁體中文；保留必要的正式構件 ID、來源 handle、量測值與阻擋狀態。
- 以固定清單將目前 88 個會形成 `ValidationMessage` 的 code 分為保留原始 message、專用 formatter 與 fallback；新增未分類 code 時由測試阻擋。
- 未知或分類為 fallback 的 code 顯示通用說明、構件 ID 與來源 handle，不顯示原始 message、snake case、exception reason 或 Python exception 文字。
- 以代表性的辨識、連接、重疊、關聯、圍令接觸與人工修正診斷建立文案與不變性測試。

## In Scope

- DXF Review「全部問題清單」與選取項目的「問題／處理建議」。
- 上述區域顯示的等級文字、類型、說明及建議用語。
- `ValidationMessage` 到 `ProblemRecord`／Review UI 的 presentation projection 與相關 focused tests。

## Out of Scope

- 改變任何診斷的觸發條件、severity、blocking policy、數量或排序。
- 修改 DXF 幾何辨識、容許值、候選選擇、人工修補能力或匯入流程。
- 重命名 diagnostic code、變更 serialized state／Project schema，或新增完整的除錯／log 檢視器。
- 新增查看原始 diagnostic code 的 UI 入口；日後若有除錯需求，應另立 change 評估呈現位置與權限。
- 順便統一整個應用程式、Solver 或匯出功能的所有訊息。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-review-engineering-data-presentation`：新增 DXF Review 診斷的白話中文、共享顯示投影、fallback 與診斷真相不變要求。

## Impact

- **主要程式**：`dxf_import/validation.py` 的問題紀錄／處理建議投影，以及 `dxf_import/dialog.py` 的問題類型顯示。
- **可能的輕量 model 調整**：若顯示投影需要獨立的中文類型欄位，可擴充 presentation-facing record；不得取代原始 `code`。
- **測試**：`tests/test_dxf_review_items.py`、`tests/test_dxf_review_layout.py` 及直接覆蓋受調整診斷文字的 targeted DXF tests。
- **相容性**：不改公開檔案格式、Project contract、DXF source、Solver input 或第三方 dependency。
- **長期文件**：預期不改 Architecture、Domain、Solver 或 Workflow truth；完成後只需同步 main spec，不預先修改長期文件。

## 已確認決策與重新評估條件

- 目前盤點出的 88 個 `ValidationMessage` code 及三分類以 `design.md` Decision 3 為準；實作期間若發現漏列的既有 producer，必須先更新分類與測試，不得以執行時字串判斷代替。
- Fallback 採選項 A：只顯示通用說明、構件 ID 與來源 handle，不附原始 message。
- 本 change 不提供查看原始 diagnostic code 的 UI 入口；後續若確有使用需求，應另立 change 評估，不在本次實作中順帶加入。
