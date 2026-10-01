# Tasks

## 實作前閱讀

| Task group | 開始前必讀 | 要確認的行為／決策 |
| --- | --- | --- |
| 1. 模式 contract | `proposal.md`「In Scope／Out of Scope」；`design.md` Decision 1、4；spec「匯出模式判定」「共同的結果範圍與失敗安全」 | 只有 state 完全不存在才是 result-only；不完整 state 必須 fail |
| 2. Result-only exporter | `design.md` Decision 2、3；spec「Result-only 使用 Project 圖面座標」「Result-only DXF 內容」 | binding 重用 Project geometry，但輸出檔不得含背景或 `SD_PROJECT_*` 圖層 |
| 3. Main 與相容性 | `design.md` Decision 1、3、Architecture Alignment；spec「輸出前模式提示」「來源支援匯出相容性」 | 寫檔前可辨識模式，完成摘要以 report 為準，source-backed 行為不變 |
| 4. 文件與整體驗證 | `proposal.md`「不變事項」；`design.md` Migration Plan；完整 `dxf-result-export` spec | 長期文件只在實作驗證後更新，最後依 spec 逐項核對 |

## 1. 建立明確的匯出模式 contract

- [x] 1.1 在 `tests/test_dxf_result_export.py` 或最接近 Main 匯出入口的介面測試加入模式判定案例，涵蓋欄位不存在／`None` → `result-only`、合法 Mapping → `source-backed`、空 Mapping `{}`／其他不完整 Mapping → 明確座標錯誤且不 fallback，以及 `dxf_workflow_status == REVIEW` 時完整座標走 source-backed、不完整座標報錯；執行新增 tests 並確認先能捕捉現行缺口。（對應 spec「匯出模式判定」）
- [x] 1.2 在 `main.py` 與 `bracing_optimizer/infrastructure/dxf_result_export.py` 之間加入小型、受驗證的 export mode contract，讓手動 Project 使用 `ExportCoordinateSystem("world")`、來源 Project 沿用嚴格座標解析；執行 Task 1.1 tests 驗證三種分支。（對應 Design Decision 1、4）
- [x] 1.3 將 `export_results_to_dxf()` 的 export mode 設為沒有預設值的必填 keyword 參數，修改所有呼叫端明確傳入 mode，並使用 `rg "export_results_to_dxf"` 確認沒有未審查或依賴預設值的呼叫端。（驗證 mandatory mode contract 與 backward compatibility boundary）

## 2. 實作 Result-only DXF 內容與驗證

- [x] 2.1 先在 `tests/test_dxf_result_export.py` 新增 result-only 成果檔案例，驗證 Project 座標 identity、`coordinate_mode == "world"`、背景與 Project geometry counts 為 0、結果實體座標正確，重讀檔案不存在 `SD_PROJECT_WALER`／`SD_PROJECT_STRUT`／`SD_PROJECT_BRACE` 圖層或 background／project-geometry markers，並分別驗證 Waler-only 不建立 `SD_RESULT_SUPPORT`、Support-only 不建立 `SD_RESULT_WALER`；執行該 test 驗證 contract。（對應 spec「Result-only 使用 Project 圖面座標」「Result-only DXF 內容」）
- [x] 2.2 調整 clean document、背景／Project geometry 建立與繪製流程，使 `result-only` 只建立成果所需圖層與實體、`source-backed` 保持現行內容；執行 Task 2.1 與既有 project/background tests，確認兩種模式均通過。（對應 Design Decision 2）
- [x] 2.3 擴充磁碟重讀驗證，讓 result-only 明確拒絕任何背景 marker、Project geometry marker 或 `SD_PROJECT_*` layer definition，同時保留既有 result、Dimension、Jack、audit 驗證；以注入非法暫存內容或等價 validator test 證明失敗時不替換目的檔。（對應 spec「Result-only DXF 內容」「共同的結果範圍與失敗安全」）
- [x] 2.4 擴充 `DXFExportReport` 與 mode-specific guidance，驗證 result-only report 的 mode／零計數，完成摘要不顯示背景與 Project geometry 計數，且明示「使用 Project 座標、未對齊來源圖面、合併時需自行定位」；同時驗證 source-backed report 的既有 counts 與合併指引不變。（對應 Design Decision 3）
- [x] 2.5 補齊 result-only 有 jack 與無 jack 的測試，重讀 DXF 驗證 `SUPPORT_JACK` 只在需要時存在，且 reference 位於 `SD_RESULT_SUPPORT`；執行對應 focused tests。（對應 spec「Result-only DXF 內容」Jack scenarios）

## 3. 整合 Main 提示並保護既有 Source-backed 行為

- [x] 3.1 更新 `main.py` 匯出流程，在正式寫檔前以 mode-specific title／說明清楚標示 result-only 或 source-backed；result-only 明示不含來源背景與 Project geometry，完成摘要以 `DXFExportReport` 的實際 mode 顯示。以 mocked file dialog／messagebox 介面測試驗證提示發生於 exporter 呼叫前。（對應 spec「輸出前模式提示」）
- [x] 3.2 新增 Main 手動 Project 整合測試，驗證沒有 `dxf_import_state` 時仍會收集目前可見且唯一的方案、呼叫 result-only exporter，取消選檔時不寫檔且不修改 Project／dirty state。（對應 spec「共同的結果範圍與失敗安全」）
- [x] 3.3 擴充 source-backed regression tests，驗證 local → WCS transform、背景、三種 `SD_PROJECT_*` geometry、結果符號、計數與現有 missing-original-source 行為維持不變；執行 `tests/test_dxf_result_export.py` 與 `tests/test_dxf_export_validation.py`。（對應 spec「來源支援匯出相容性」）
- [x] 3.4 執行同一構件多個 visible plans、無 visible plans、結果長度不符及不完整 import state 的失敗案例，確認兩種模式均在寫正式檔前拒絕且不覆寫既有目的檔。（對應 spec「匯出模式判定」「共同的結果範圍與失敗安全」）

## 4. 長期文件與完成驗證

- [x] 4.1 在功能與 focused tests 通過後更新 `README.md`「13.7 DXF 配置標註輸出」與 `docs/WORKFLOW.md`「11. Export／Limitation 2」，記錄 source-backed／result-only 雙模式及手動 Project identity contract；以文件搜尋確認舊的「無 metadata 即不可匯出」敘述不再被當成現況。（對應 proposal「Workflow truth」）
- [x] 4.2 執行 DXF focused regression：`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_result_export tests.test_dxf_export_validation`，確認 result-only 與 source-backed 全部通過。（final focused verification）
- [x] 4.3 依影響範圍執行 Main／presentation 與架構 boundary tests（至少 `tests.test_interface_presentation`、`tests.test_application_domain_boundaries` 及新增 Main 匯出測試所在模組），確認沒有 GUI dependency 進入 Domain／Algorithms 且既有介面行為無回歸。（final boundary regression）
- [x] 4.4 執行 `openspec validate export-result-only-dxf-for-manual-projects --strict` 與 `$openspec-verify-change`，逐項核對 spec scenarios、tasks、實際 DXF 內容與測試證據；只有全部符合後才可標記 change implementation 完成。（OpenSpec implementation verification）
