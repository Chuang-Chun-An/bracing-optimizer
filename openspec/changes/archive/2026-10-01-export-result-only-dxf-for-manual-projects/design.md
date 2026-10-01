# Design

## 閱讀導航

| 優先級 | 決策／章節 | 適用時機 |
| --- | --- | --- |
| P0 現在必讀 | Decision 1「由匯出入口明確選擇模式」 | 修改 Main 匯出流程或 exporter API 前 |
| P0 現在必讀 | Decision 2「Result-only 重用 Project binding，但不畫 Project geometry」 | 修改 DXF 建檔與內容驗證前 |
| P0 現在必讀 | Decision 3「模式成為 report 與驗證 contract」 | 修改完成摘要、測試或診斷前 |
| P1 實作前閱讀 | Architecture Alignment、Backward Compatibility、Migration Plan | 合併產品程式碼與更新長期文件前 |
| P2 需要時再讀 | Risks / Trade-offs | 遇到不完整 import state、圖層殘留或既有測試回歸時 |

## 方案摘要

匯出入口先只依 `dxf_import_state` 是否存在且非 `None`，把目前 Project 分成 `source-backed` 與 `result-only`；`dxf_workflow_status` 不參與判定。前者沿用從 `dxf_import_state` 取得的座標系和現有 exporter 路徑，包含 `{}` 在內的不完整 state 會回報錯誤；後者建立明確的 `world` 座標 context，仍用 Project Waler／Strut 幾何定位 Solver 結果，但 exporter 不建立背景、不畫 Project geometry，也不建立 `SD_PROJECT_*` 圖層，並只建立實際有結果的 `SD_RESULT_*` 圖層。兩者共用既有成果正規化、長度檢查、Dimension／Jack 建立、暫存重讀、audit 與原子替換。

```text
Main 判定 export mode
  ├─ source-backed → saved coordinate context → background + Project geometry + results
  └─ result-only   → world identity context → results only
                                      ↓
                    共用 staged write / reread / validation / replace
```

本 change 的專有名詞：`source-backed` 指具有合法 DXF import state 與座標 metadata 的既有輸出；`result-only` 指沒有來源圖面的手動 Project 輸出，Project 座標本身就是 WCS。兩者是輸出模式，不是新的 Project lifecycle status，也不寫入 persistence。

## 決策對照

| Decision | 選擇原因 | 拒絕的替代方案 | 影響的 spec／task |
| --- | --- | --- | --- |
| 1. 匯出入口明確選擇模式，並以必填 keyword 傳入 exporter | 防止 Infrastructure 猜測產品語意，也能在寫檔前顯示正確提示，並強迫所有呼叫端表達意圖 | exporter 自動判定或提供預設 mode；會讓漏改呼叫端與損壞 import state 被掩蓋 | Spec「匯出模式判定」「輸出前模式提示」；Task 1、3 |
| 2. Result-only 仍以 Project Waler／Strut 建立結果 binding，但省略背景與 Project geometry 的建檔 | Solver result 只有 member id 與 pieces，仍需要目前 Project 線段定位；使用同一份 binding 可避免第二套座標邏輯 | 直接從 result payload 自行重建軸線；payload 沒有完整幾何且會形成第二 truth | Spec「Result-only 使用 Project 圖面座標」「Result-only DXF 內容」；Task 2 |
| 3. export mode 納入 exporter report，並以模式控制 layer 建立與內容驗證 | 完成摘要和 tests 能驗證實際模式；只不畫實體仍可能留下禁止的 `SD_PROJECT_*` layer definitions | 僅由 UI 文案推測模式；無法驗證輸出檔 contract | Spec「Result-only DXF 內容」「來源支援匯出相容性」；Task 2、3 |
| 4. 不完整 import state 維持錯誤，不降級 identity | Identity 僅對「確定沒有來源」的手動 Project 成立；對損壞來源 state 猜測可能造成座標錯置 | 任一座標解析錯誤都 fallback result-only；會掩蓋資料問題 | Spec「匯出模式判定」；Task 1、3 |
| 5. 共用既有 staged write 與 validator | 保留正式檔不被失敗輸出覆寫的既有可靠性 | 為 result-only 建立簡化直寫路徑；會繞過 audit 與原子替換 | Spec「共同的結果範圍與失敗安全」；Task 2、4 |

## Context

動機與 scope 見 `proposal.md`。現行 `main.py` 在收集可見方案前即呼叫 `export_coordinate_system_from_import_state()`，因此沒有 `dxf_import_state` 的手動 Project 直接停止。底層 `export_results_to_dxf()` 已能接受 `ExportCoordinateSystem("world")`，也以目前 Project geometry 建立 result bindings；但它目前無條件建立／繪製 Project geometry，並在 clean document 中預先建立三個 `SD_PROJECT_*` 圖層。

現行 exporter 不讀寫原始 DXF，而是以新建 R2018 document、暫存檔重讀驗證及原子替換產生成果。這些可靠性 boundary 應保留。

## Goals / Non-Goals

**Goals:**

- 讓完全沒有 DXF import state 的手動 Project 以 identity coordinate context 匯出。
- 用一個明確、可測試的 mode contract 控制 UI 提示、DXF 內容與 report。
- 共用現有 result binding、繪製及 staged validation pipeline。
- 對 source-backed 路徑建立 regression coverage，證明既有行為未改變。

**Non-Goals:**

- 不新增 persistence 欄位或 schema migration。
- 不把 export mode 變成 Project durable state。
- 不一般化成可自由勾選背景／Project geometry 的 export options UI。
- 不修改 DXF import／Review、Solver result payload 或任何 Solver 規則。

## Decisions

### Decision 1：由匯出入口明確選擇模式

Main 以 runtime `dxf_import_state` 的存在性先分類：

- `dxf_import_state` 欄位不存在或值為 `None`：`result-only`，建立 `ExportCoordinateSystem("world")`。
- 非 `None`（包含空 Mapping `{}`）：`source-backed`，沿用 `export_coordinate_system_from_import_state()` 的嚴格解析。
- 存在但解析失敗：顯示既有座標錯誤並停止，不 fallback。

模式判定不得讀取 `dxf_workflow_status`；因此 REVIEW 狀態只要 coordinate state 完整就照常 source-backed，否則回報錯誤。模式必須以 `export_results_to_dxf()` 的必填 keyword 參數傳入，函式簽章不得提供預設值，也不得讓 exporter 同時解讀 lifecycle state。模式值宜採小型 enum 或受驗證的 literal contract，避免散落 boolean 組合；不需要新增大型 service。

Presentation 在開啟／確認目的檔前使用 mode-specific title 或說明文字，完成摘要也使用 report 回傳的實際 mode，避免 UI 判定與 exporter 執行結果 drift。

### Decision 2：Result-only 重用 Project binding，但不畫 Project geometry

兩種模式都從目前 Project Waler／Strut rows 建立 member bindings並執行結果長度檢查。Result-only 的 `world` coordinate context 使 `_local_to_world` 等價於 identity；這是唯一的座標 truth，不另寫一套 result placement。

建檔階段依 mode 分流內容：

- `source-backed`：維持背景抽取、背景圖層準備、Project geometry 建立／繪製、既有結果與 Project 圖層預建行為及對應驗證。
- `result-only`：背景與 Project geometry expected collections 均為空；至少有 Waler 結果才建立 `SD_RESULT_WALER`，至少有 Support 結果才建立 `SD_RESULT_SUPPORT`；只有實際存在 jack piece 時才建立 `SUPPORT_JACK`。

Validator 除了驗證預期結果數量，也要能證明 result-only 重讀檔案中沒有 background／project-geometry marker，且不存在三個 `SD_PROJECT_*` layer definitions。這避免「沒有畫線但仍輸出禁止圖層」的半套結果。

### Decision 3：模式成為 report 與 summary contract

`DXFExportReport` 增加明確 export mode（名稱依實作使用既有命名慣例），`coordinate_mode` 在 result-only 應為 `world`。計數欄位繼續存在；result-only 的 background 與 project geometry counts 必須為零。

`merge_guidance`／完成摘要依 mode 說明內容：source-backed 沿用現有世界座標合併指引及背景／Project geometry 計數；result-only 不顯示這兩類計數，並必須明示檔案使用 Project 座標輸出、未對齊任何來源圖面，合併至其他圖面時需自行定位。摘要文字以 report mode 為準，不能重新從 `dxf_import_state` 推導。

### Decision 4：保留共同驗證與 transaction boundary

模式只改變 document expected content，不建立另一條寫檔函式。兩種模式仍經過：目的資料夾暫存檔、重新讀取、audit、clean structure、模式對應內容、結果座標／數量／圖層／block 驗證，最後才 replace 正式檔。

取消、建檔錯誤、驗證錯誤或 replace 錯誤都沿用現有 preserve semantics，不改 Project state 或 dirty。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer boundary**：

- **Presentation (`main.py`)**：讀取目前 session 的 DXF context、判定使用者可理解的 export mode、顯示模式提示、收集 destination 與顯示 report。
- **Infrastructure (`dxf_result_export.py`)**：接受明確 mode、coordinate context、Project rows 與 plans，建立並驗證對應 DXF。
- **Application／Domain／Algorithms**：不新增依賴且不改行為。

Dependency direction 維持 Presentation → Infrastructure export adapter；Infrastructure 不回查 Main 或 GUI state。Project geometry 是 result placement 的 single source of truth，export mode 是本次輸出呼叫的 single source of truth。Report 攜帶實際 mode，避免完成摘要形成第二套判定。

## Backward Compatibility 與 Persistence Impact

- `export_results_to_dxf()` 的 mode 是沒有預設值的必填 keyword；所有既有 call sites 必須明確傳入 mode，並以搜尋確認沒有遺漏。測試必須證明舊 source-backed fixtures 的輸出內容不變。
- `dxf_import_state`、`dxf_asset`、`dxf_workflow_status` 與 Project schema 均不變。
- 現有手動 Project 檔案不需 migration；功能由 runtime 缺少 `dxf_import_state` 即可使用。
- 不修改儲存檔，因此 rollback 是還原程式版本；既有 Project 資料不需回復。

## Risks / Trade-offs

- **[風險] 使用者誤以為 result-only 是完整圖面** → 寫檔前與完成摘要都明示不含背景及 Project geometry。
- **[風險] 僅略過繪圖但仍殘留 `SD_PROJECT_*` layer definitions** → document layer 建立依 mode 分流，並在磁碟重讀後負向驗證圖層不存在。
- **[風險] 損壞 import state 被誤判為手動 Project** → 只允許 state 完全不存在時使用 identity；存在但不合法即 fail。
- **[取捨] Result-only 檔案缺少工程線，不適合作為完整圖面檢查** → 這是刻意的最小輸出 contract；本 change 不加入一般化內容選項。
- **[風險] source-backed regression** → 保留現有 fixtures，檢查 local-to-world、背景、Project layers、result markers 與 report counts。

## Migration Plan

1. 先以 tests 固定 mode 判定及 result-only 負向內容 contract。
2. 擴充 exporter mode／report contract，保留共同 validation pipeline。
3. 更新 Main 提示、呼叫與完成摘要。
4. 執行 focused tests，再執行 DXF export validation 與 presentation／boundary regression tests。
5. 實作驗證完成後更新 `README.md` 與 `docs/WORKFLOW.md`；若驗證失敗則不把長期文件寫成已成立行為。

不需要資料 migration 或 feature flag。Rollback 僅需回復程式變更，既有 Project 與來源 DXF 均未被改寫。
