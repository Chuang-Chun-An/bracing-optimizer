# Proposal

## 閱讀導航

| 優先級 | 要回答的問題 | 文件／段落 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | 為什麼手動 Project 目前不能匯出 DXF，這次要改成什麼？ | 本文件「快速摘要」「現況與目標」「In Scope／Out of Scope」 | 確認使用者可見範圍與相容性邊界 |
| P0 現在必讀 | `None`、`{}`、REVIEW 如何判定模式，兩種模式各自允許輸出哪些內容？ | `specs/dxf-result-export/spec.md` 的「匯出模式判定」「Result-only DXF 內容」「來源支援匯出相容性」 | 確認正式行為與驗收條件 |
| P1 實作前閱讀 | 模式如何分流，Infrastructure 如何避免畫出 Project geometry？ | `design.md` 的 Decision 1～3、Architecture Alignment | 理解責任分層與 exporter contract |
| P1 實作前閱讀 | 實作與測試的先後順序為何？ | `tasks.md` | 依依賴順序修改與驗證 |
| P2 需要時再讀 | 現行 DXF 匯出的 transaction 與長期 workflow truth 是什麼？ | `docs/WORKFLOW.md`「11. Export」「Limitation 2 — Project → WCS metadata dependency」；`README.md`「13.7 DXF 配置標註輸出」 | 更新長期文件與檢查既有 source-backed 行為 |

本次可以先跳過其他 DXF recognition、DXF Review、Solver scoring 與材料規則 specs；它們不改變匯出模式或成果檔內容。

## 快速摘要

- 手動建立、沒有 `dxf_import_state` 的 Project 目前會因缺少 Project → WCS metadata 而無法輸出 DXF。
- 本 change 新增 **result-only export**：只有 `dxf_import_state` 欄位不存在或值為 `None` 時採用；把 Project 座標直接視為 WCS／圖面座標，使用 identity transform，只輸出目前可見的 Solver 成果與必要結果符號。
- 空 Mapping `{}` 或其他存在但不完整的 import state 會回報座標錯誤；模式不依 `dxf_workflow_status` 判定，REVIEW 也依座標資訊完整性走 source-backed 或失敗。
- 有來源 DXF 的 Project 繼續走 **source-backed export**，現有座標轉換、背景與 Project geometry 輸出行為維持不變。
- 輸出前會清楚告知使用者即將使用哪一種模式，避免把無背景的成果檔誤認為來源圖面的完整輸出。
- 不修改 Solver、Project geometry、結果 visibility、專案持久化 schema 或原始 DXF。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| 手動 Project | 因沒有 `dxf_import_state.coordinate_system` 而停止匯出 | 可使用 result-only export，Project 座標直接作為 WCS |
| Result-only 檔案內容 | 沒有正式支援 | 只建立實際有結果的 `SD_RESULT_WALER`／`SD_RESULT_SUPPORT` 與必要的 Dimension／`SUPPORT_JACK` 等結果符號 |
| 背景與工程線 | 現行 exporter 會重建可用背景並畫出 Project geometry | Result-only 不輸出背景，也不建立 `SD_PROJECT_WALER`、`SD_PROJECT_STRUT`、`SD_PROJECT_BRACE` |
| 有來源 DXF 的 Project | 使用已保存座標 metadata 進行 source-backed export | 行為維持不變 |
| 使用者辨識模式 | 匯出流程未將兩種模式並列說明 | 選檔／寫檔前清楚標示 result-only 或 source-backed |

## 主要流程

```text
使用者要求匯出目前可見結果
        ↓
檢查 dxf_import_state 欄位是否存在且非 None（不看 workflow status）
        ├─ 不存在／None → 告知 result-only export → 使用 identity transform
        │                                      ↓
        │                         只建立實際需要的成果圖層與結果符號
        ├─ 存在且座標完整 → 告知 source-backed export → 執行既有輸出
        └─ 存在但不完整（含 {}）→ 回報座標錯誤，不 fallback
        ↓
暫存寫入、重讀驗證、成功後原子替換目的檔
```

## 不變事項

- 有來源 DXF 的 source-backed export 保留現行 Project → WCS 轉換、可用背景與 Project geometry 行為。
- 匯出範圍仍只包含目前可見結果；同一構件有多個可見方案時仍拒絕匯出。
- 尺寸、千斤頂符號、DXF R2018／毫米單位、暫存驗證與原子替換規則不變。
- 匯出仍是 terminal output，不修改 Project input、Solver results、visibility 或 dirty state。
- 不重新開啟、儲存或修改原始 DXF。

## Why

純手動 Project 是正式支援的專案型態，但其合法 Solver 結果目前因沒有 DXF import state 而無法輸出 DXF。讓這類專案以明確的 result-only 模式輸出，可解除不必要的來源圖面依賴，同時避免捏造背景或工程圖層。

## What Changes

- 在 DXF 匯出前只依 `dxf_import_state` 是否存在判定模式：欄位不存在或 `None` 為 `result-only`；存在（含 `{}`）則必須以 source-backed 規則解析，資訊不完整即失敗。`dxf_workflow_status` 不參與模式判定。
- 手動 Project 走 result-only 模式時，將 Project 座標直接視為 WCS，採 identity transform。
- Result-only DXF 只建立實際有結果的 Solver 成果圖層與必要結果符號，不輸出背景 DXF 或 `SD_PROJECT_*` geometry 圖層。
- Result-only 完成摘要不顯示背景／Project geometry 計數，並明示檔案使用 Project 座標、未對齊來源圖面，合併至其他圖面時需自行定位。
- 保留 source-backed export 的既有內容、座標與驗證行為。
- 為兩種模式補上可驗證的報告／提示內容與 regression tests。

### In Scope

- Main／Presentation 匯出流程的模式判定與使用者提示。
- DXF exporter 的明確輸出模式 contract、result-only 內容選擇與報告。
- 手動 Project、source-backed Project、失敗不覆寫目的檔等相關測試。
- 實作完成後更新 `README.md` 與 `docs/WORKFLOW.md` 的長期行為描述。

### Out of Scope

- 將座標系新增為獨立 Project persistence metadata 或變更 schema version。
- 讓使用者任意選擇是否加入背景或 Project geometry 的一般化匯出設定。
- 變更 DXF import／Review／relink、來源幾何辨識或 managed DXF asset lifecycle。
- 變更 Solver 結果、評分、visibility、尺寸樣式或千斤頂圖塊外觀。
- 新增 DWG、PDF 或其他輸出格式。

### 尚未決定事項與重新評估條件

- 模式提示的精確 UI 形式留待 design／實作依既有 Tkinter 互動模式決定，但必須發生在正式寫檔前，且不能把 result-only 描述成含來源背景的完整圖面。
- 若實作時發現「有 `dxf_import_state` 但缺少合法 coordinate system」是現有 Project 的實際常態，應停止並重新評估分類規則；本提案不授權把這類損壞／不完整 state 靜默降級為 identity transform。

## Capabilities

### New Capabilities

- `dxf-result-export`: 定義 DXF 成果輸出的模式判定、result-only 檔案內容、source-backed 相容性、提示與失敗安全行為。

### Modified Capabilities

- 無。現有 capability inventory 沒有 DXF result export spec；本 change 建立新的正式 capability。

## Impact

- **Presentation／流程協調**：`main.py` 的 DXF 匯出入口需先分類模式並顯示對應提示與完成摘要。
- **Infrastructure**：`bracing_optimizer/infrastructure/dxf_result_export.py` 需接受明確模式，並在 result-only 模式略過背景與 Project geometry 的繪製／驗證。
- **Tests**：`tests/test_dxf_result_export.py`、`tests/test_dxf_export_validation.py` 與 Main 介面相關測試需涵蓋兩種模式及 regression。
- **Architecture**：不改變既有 layer responsibility；Presentation 負責互動，Infrastructure 負責 DXF 建立與驗證。
- **Domain／Solver**：不變。
- **Workflow truth**：DXF Result Export 從只接受具 Project → WCS metadata 的 source-backed 路徑，擴充為明確的 source-backed 與 manual result-only 兩種模式。
