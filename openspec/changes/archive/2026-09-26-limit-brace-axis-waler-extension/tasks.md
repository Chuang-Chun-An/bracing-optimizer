# Tasks

## 1. 邊界 Characterization 與測試保護

- [x] 1.1 在 `tests/test_dxf_brace_waler_extension.py` 補齊 pure resolution 邊界案例：250 mm 內仍走 `direct`、250～600 mm 可走 `axis_extension`、`= 600 mm` 合法、`> 600 mm` 回傳 `missing` 並保留 source endpoint；執行該測試檔並確認新增案例精確覆蓋新舊邊界。
- [x] 1.2 補齊候選選擇案例：兩個 600 mm 內近距交點維持 `ambiguous`、合法交點後方的超距離交點不參與 ambiguity、Waler collection order 與 Brace start/end 反轉不改變等價結果；執行 focused tests確認 deterministic contract。
- [x] 1.3 補齊 `CandidatePointBuilder` characterization：600 mm 內交點可建立 `extended_axis_waler_intersection`，超過 600 mm 不建立自動候選；執行 focused candidate-point tests確認候選與 formal resolution預期一致。

## 2. Brace 專用距離設定與 Pure Resolution

- [x] 2.1 在 `dxf_import/models.py` 的 `GeometryTolerances` 新增唯一具名設定 `maximum_brace_axis_extension_mm = 600.0`，標示為 Brace recognition tuning而非全域工程接觸容許值；執行 model／focused tests確認預設值與既有 tolerance未改變。
- [x] 2.2 在 `dxf_import/brace_waler_connection.py` 的共用 outward finite-intersection enumeration套用 `> 0` 且 `<= maximum_brace_axis_extension_mm` 篩選，維持原 deterministic排序、nearest及ambiguity規則；執行 `tests/test_dxf_brace_waler_extension.py` 確認 Task 1 pure tests通過。
- [x] 2.3 驗證 direct resolution仍只使用 `connection_tolerance_mm = 250 mm`，Strut及manual Brace不會因新 setting改變；執行 direct／manual／Strut focused regressions確認沒有把600 mm誤用成 direct snap。

## 3. Formal Connection、Review 候選與 Diagnostics 一致性

- [x] 3.1 讓 `dxf_import/candidate_points.py` 的正式 Brace connection與Candidate Points共同消費受限的intersection enumeration，不另寫600 mm常數或第二套filter；執行 formal／candidate integration tests確認兩者不會漂移。
- [x] 3.2 補齊超距離整合測試：source-supported endpoint不變、不產生 `BRACE_AXIS_EXTENDED_TO_WALER`、沿用 `BRACE_NOT_CONNECTED`／`BRACE_ONE_END_NOT_CONNECTED` blocking behavior，且不得完成含 unresolved Brace的import；執行對應 DXF Review tests確認failure-before-commit。
- [x] 3.3 補齊 source exclusion／restore、recognition rebuild與manual endpoint replay regressions，確認重建後仍使用同一600 mm contract且不覆寫人工決定；執行相關 Review workflow focused tests。

## 4. Y05 與跨角色 Regression

- [x] 4.1 以 Y05／等價fixture驗證 root `9E9` 約425 mm兩端延伸及root `B9C` 目前約503 mm（歷史約528 mm）單端延伸仍成功，並加入超過600 mm的Y05型案例確認維持unresolved；執行 `tests/test_dxf_bim_block_recognition.py` 的相關案例。
- [x] 4.2 執行 Brace、Strut、CornerBrace、Waler association及一般非BIM DXF recognition regressions，確認本 change僅收斂Brace auto axis extension，且沒有放寬全域connection tolerance。

## 5. 文件與最終驗證

- [x] 5.1 在程式與測試完成後，最小幅度更新 `docs/WORKFLOW.md` 的current Brace connection behavior，清楚區分250 mm direct snap與600 mm axis-extension safety boundary；重讀相關段落確認未把planned behavior提早或重複寫入其他長期文件。
- [x] 5.2 先執行所有受影響的 DXF focused tests，再執行完整 regression suite，回報通過／失敗數量並確認未弱化既有 assertions。
- [x] 5.3 執行 OpenSpec strict validation與implementation verification，確認proposal、delta spec、design、tasks及實作一致，且沒有 production magic `600`、persistence migration或scope外修改。
