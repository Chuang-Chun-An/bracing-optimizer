# Tasks

## 實作前閱讀

| Task group | 開始前必讀 | 本組依據 |
| --- | --- | --- |
| 1 | proposal「現況與目標」、design Decision 1、兩份 delta specs 的 single-source Requirements | committed result 是唯一合法性 truth |
| 2 | `excel-result-export` 全部 Requirements、design Decision 2 | Excel 欄位、原因 fallback 與 staged workbook 驗證 |
| 3 | 本 change `dxf-result-export` 全部 Requirements、主 spec 的 source protection／result-only structure／failure safety、design Decision 3 | warning layer、定位、兩種模式與 atomic semantics |
| 4～5 | proposal「不變事項」、design Architecture Alignment、兩份 delta specs 的 failure／single-source scenarios、前述測試結果 | 長期 workflow 更新與整體回歸 |

## 1. 建立共用 export legality projection

- [x] 1.1 在 `bracing_optimizer/application/project_results.py` 建立逐構件唯讀 legality projection，涵蓋 Support／Waler identity、`valid`、完整 ordered reasons 與「未提供不合法原因」fallback；在 `tests/test_project_results.py` 驗證合法、單一問題、多問題、原因缺失、混合 plans 與 deterministic ordering，並明確涵蓋 Support 缺少 `valid`、Support `valid=True` 但 `reason` 非空、Waler 同時缺少 `legality.valid`／`plan.valid`、Waler 的 `legality.valid` 與 `plan.valid` 矛盾且以前者為準，以及 projection 不因合法性改變材料摘要／匯出範圍。
- [x] 1.2 在 `main.py` 的 Excel／DXF export orchestration 改用同一 projection，並以 orchestration tests 驗證 exporter 收到的資料來自 committed result，Presentation 未重新呼叫 evaluator，既有 duplicate-visible-result 拒絕行為不變。

## 2. Excel 合法性欄位

- [x] 2.1 擴充 `bracing_optimizer/infrastructure/excel_result_export.py` 的明細 contract，在既有欄位後加入「是否合法」「不合法原因」，同步 staged workbook 重讀驗證；確認合法原因空白、invalid 原因完整、同一 member 的多筆材料列一致。
- [x] 2.2 擴充 `tests/test_excel_result_export.py` 與必要的 Main orchestration tests，驗證 Support／Waler、同批合法與不合法、原因缺失 fallback、無額外確認，以及 write／validation failure 不取代既有 destination。

## 3. DXF invalid warning

- [x] 3.1 在 `bracing_optimizer/infrastructure/dxf_result_export.py` 加入 `SD_WARNING_INVALID_RESULT`、ACI red／BYLAYER annotation，以及引用新細明體 `PMingLiU`／`mingliu.ttc` 的 `SD_WARNING_CJK` text style；以 `MemberBinding` 為準建立共用 anchor builder 與 expected-warning validation contract，並以 `WARNING_TEXT_OFFSET_MM`、`WARNING_TEXT_COLLISION_RADIUS_MM`、`WARNING_TEXT_STACK_SPACING_MM`、`WARNING_ANCHOR_TOLERANCE_MM` 等具名常數實作固定左法向偏移與穩定避讓。驗證每個 invalid member 恰好一筆包含 identity／全部 reasons 的文字、雙路群組的每支 invalid Strut 各自產生且不合併 warning，並維持全合法時不建立 warning layer。
- [x] 3.2 擴充 `tests/test_dxf_result_export.py` 與 `tests/test_dxf_export_validation.py`，驗證 source-backed／result-only 內容等價、原因缺失 fallback、多個 invalid member、雙路群組逐 Strut warning、不重疊案例的固定左法向偏移、可能重疊時依穩定順序避讓，以及來源檔未改；重讀輸出 DXF 時驗證 warning entity 使用 `SD_WARNING_CJK`、該 STYLE 的字型參照為 `mingliu.ttc`，並使用 `WARNING_ANCHOR_TOLERANCE_MM` 驗證鄰近性。layer／顏色／identity／文字／數量／位置／text style／style font reference 任一驗證失敗時不得取代 destination，測試不得以匿名數字表達偏移量或容差。

## 4. 同步長期文件

- [x] 4.1 在實作驗證完成後更新 `docs/WORKFLOW.md` 的 Export 說明，明確記錄 invalid result 可匯出、Excel 欄位與 DXF warning layer，並 review 確認未把 exporter 描述成合法性 source of truth；Architecture／Domain／Solver 文件維持不變。

## 5. 整體驗證

- [x] 5.1 執行 project results、Excel export、DXF export validation 與 invalid manual result targeted tests，逐項對照兩份 delta specs 的 scenarios，確認 focused tests 全部通過。
- [x] 5.2 執行完整 test suite，確認合法結果的既有 Excel／DXF 內容、source-backed 保護、result-only 結構與 Project persistence 無回歸。
- [x] 5.3 執行 `openspec validate mark-invalid-results-in-exports --strict`，再用 `$openspec-verify-change` 對照 proposal／design／specs／tasks；確認沒有新增 export block、confirmation、persistence migration 或 Solver rule。
