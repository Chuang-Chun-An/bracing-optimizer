# Proposal

## 閱讀導航

| 優先級 | 文件／段落 | 要回答的問題 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | 本 proposal 的「快速摘要」至「不變事項」 | 使用者會看到什麼改變，哪些既有行為不變？ | 確認 change 方向與範圍 |
| P0 現在必讀 | `openspec/specs/support-editor-result-mutation/spec.md` 的「實際 Support 修改維持 immediate commit 行為」 | 為什麼 invalid result 會成為可見、可匯出的正式結果？ | 理解問題來源，不把 invalid result 誤當暫存資料 |
| P0 現在必讀 | `openspec/specs/dxf-result-export/spec.md` 的「共同的結果範圍與失敗安全」 | 現有 DXF 匯出範圍與失敗保護是什麼？ | 避免改變既有 export transaction |
| P1 實作前閱讀 | `design.md` 的 Decision 1～3；本 change 兩份 delta specs | 合法性資料如何投影，Excel／DXF 要精確輸出什麼？ | 實作與測試的直接依據 |
| P2 需要時再讀 | `docs/ARCHITECTURE.md` 的 Application／Infrastructure、`docs/WORKFLOW.md` 的 Export | layer responsibility 與長期 workflow truth 是否一致？ | 處理跨層 contract 或更新長期文件時查閱 |

**本次可以先跳過**：DXF recognition／Review、Solver 搜尋與 scoring、Project schema compatibility，以及 `docs/DOMAIN.md` 的幾何與材料工程邊界；本 change 不修改這些行為。

## 快速摘要

- 人工編輯後的 invalid result 會正式保留，但目前只要可見，仍能匯出且輸出檔不帶 invalid 狀態。
- 使用者已決定繼續允許匯出，不增加阻擋或確認視窗。
- Excel 材料明細必須增加「是否合法」與「不合法原因」欄位。
- DXF 必須在不合法構件旁建立紅色警告文字，並放在專用警告圖層；合法構件不產生警告。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| Invalid result | 可見即匯出，valid／reason 在 projection 遺失 | 仍可匯出，valid／reason 成為正式 export contract |
| Excel | 無合法性欄位 | 每筆材料明細可辨識所屬成果是否合法及原因 |
| DXF | 成果幾何看不出待修狀態 | 每個不合法構件旁有一筆紅色持久警告文字 |

## 主要流程

1. 使用者照常選擇可見成果並啟動 Excel 或 DXF 匯出。
2. 系統從已 committed 的結果取出每個構件的合法性與既有原因；這份唯讀資料稱為 **export legality projection**。
3. Excel 將狀態與原因寫入材料明細；DXF 對每個 invalid member 建立專用警告圖層及鄰近文字。
4. 暫存輸出經重讀、內容與既有安全檢查驗證後，才原子替換目的檔。

## 不變事項

- Invalid result 仍可保存與匯出；不新增 export confirmation dialog。
- 同一構件多個可見方案仍拒絕匯出。
- Result-only／source-backed 座標與背景規則不變。
- 工程合法性仍由既有 Solver／Application evaluator 決定，export 不重算規則。

## Why

Invalid result 是刻意保留供使用者修正的正式狀態，但匯出 projection 目前遺失其合法性與原因，容易使待修方案看起來像可直接交付成果。輸出檔需要攜帶既有判定，讓接收者可以辨識風險。

## What Changes

- 建立共用成果匯出 projection，正規化每個 member plan 的 `valid` 與 ordered reasons。
- Excel 材料明細加入「是否合法」與「不合法原因」欄位；合法方案原因保持空白。
- DXF 新增專用 invalid-result warning layer，以紅色文字在對應構件附近標示構件編號與原因。
- 驗證 result-only 與 source-backed 兩種模式、Support 與 Waler，以及多個 invalid member 的 deterministic 輸出。
- 實作完成後更新 Export workflow 與相關主 specs。

### In Scope

- 目前可見、每構件唯一的 Waler／Support result。
- Excel 與 DXF 內的永久警告資料及失敗安全驗證。
- 已 committed invalid result 缺少可顯示原因時，仍明確標示「未提供不合法原因」，不捏造工程判斷。

### Out of Scope

- 阻止 invalid result 保存或匯出。
- 重新設計 Solver issue taxonomy、匯出前確認視窗或 Preview Image 警告。
- 改變成果圖層、Project geometry 或來源背景的既有座標語意。

## Capabilities

### New Capabilities

- `excel-result-export`: 定義可見成果材料表的合法性欄位、原因與失敗安全。

### Modified Capabilities

- `dxf-result-export`: 允許 invalid result 匯出時，要求專用紅色警告圖層與構件旁文字。

## Impact

- 影響 `ProjectResultModel` 的 export projection、`main.py` 匯出協調、Excel exporter、DXF exporter 及其 staged-file validation／tests。
- 不新增 persistence 欄位；使用 committed result 已有的 validity／reason。
- 沿用既有 Architecture；Domain 與 Solver truth 不變。Export workflow truth 會增加「invalid 可匯出但必須永久標示」，因此只在實作與驗證完成後更新 `docs/WORKFLOW.md`。

