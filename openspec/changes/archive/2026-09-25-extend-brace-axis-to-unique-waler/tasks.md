# Tasks

## 1. Characterization 與 pure geometry contract

- [x] 1.1 在 `tests/test_dxf_brace_waler_extension.py` 建立目前 direct Brace connection characterization，涵蓋端點在 `connection_tolerance_mm` 內、單端連接、雙端未連接及 direct ambiguity warning；以現有 endpoint、`FromWaler`／`ToWaler` 與 message code 在導入 extension 前均被鎖定驗證。
- [x] 1.2 在同一測試模組建立 outward-ray synthetic fixtures，涵蓋兩端延伸、單端 direct + 單端延伸、Waler 只在線的延長線上、交點位於 inward direction、射線先後命中兩支 Waler、最近位置多解、兩端同一 Waler、zero-length axis；以每一案例有明確 resolution status、交點與 Waler identity assertion 驗證。
- [x] 1.3 增加 determinism fixtures，交換 Brace start/end、Waler input order、Waler segment direction 與等價浮點交點表示；以輸出具有等價 endpoint-to-Waler 關係且工程 ambiguity 不被 ID／順序打破驗證。

## 2. Pure Brace-to-Waler resolution

- [x] 2.1 新增小型 internal pure module `dxf_import/brace_waler_connection.py`（或在實作前確認既有 geometry owner 更合適），定義 endpoint resolution DTO、finite ray-segment intersection enumeration 與 normalized deterministic ordering；以 1.2、1.3 pure tests 通過且 module 不依賴 Dialog／Review workflow 驗證。
- [x] 2.2 實作 direct-first policy：先重用既有 endpoint-to-finite-segment distance，只有未連接且 `selection_source == "auto"` 的 Brace 端點才搜尋 outward ray；以 direct candidate 不被 extension 改選、manual／CAD selection 不被自動延伸及 Strut 不進入此 module 驗證。
- [x] 2.3 實作 nearest finite boundary 與 blocking ambiguity：最近唯一交點成功、後方 Waler 不覆寫、distance delta `<= ambiguous_connection_delta_mm` 回傳 `ambiguous`、兩端同一 Waler 回傳 invalid；以 boundary tests 與無未命名 extension-distance magic number 的 code review 驗證。

## 3. Formal Brace connection 與 diagnostics

- [x] 3.1 在 `dxf_import/candidate_points.py` 將 Brace 分支改為消費 pure resolution，逐端更新 endpoint、`FromWaler`／`ToWaler`、world／local WCS staging geometry；保留 Strut 原有 `connect()` 路徑，以 focused tests 證明 Strut regression 不變。
- [x] 3.2 建立 `BRACE_AXIS_EXTENDED_TO_WALER` info、`AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION` error 與 `BRACE_SAME_WALER_CONNECTION` error mapping，並在 missing／one-end missing 時保留既有 `BRACE_NOT_CONNECTED`／`BRACE_ONE_END_NOT_CONNECTED`；以完整與部分成功案例的 message set 驗證無重複或互相矛盾的 failure truth。
- [x] 3.3 更新 connection validation code ownership／filtering，使 recognition rebuild 與 candidate mutation 可移除舊 extension diagnostics 後重建；以重跑同一 result 不累積 duplicate messages、排除 Waler 後不保留 stale connection 驗證。

## 4. Candidate Points 與 Review lifecycle

- [x] 4.1 讓 `CandidatePointBuilder` 使用同一 pure intersection enumeration／adopted resolution，移除 Brace extension 的第二套 250 mm gate；以 adopted endpoint 為 selected／recommended point、point provenance 同時含 Brace 與 Waler handles，且未採用候選排序 deterministic 驗證。
- [x] 4.2 在 `tests/test_dxf_review_workflow.py` 與相關 candidate-point tests 增加 source exclusion／restore、recognition rebuild、confirmation invalidation 及 Pause／Resume regression；以 extension outcome 可重建、不保存 stale Waler identity且不新增 persistence required field 驗證。
- [x] 4.3 增加 manual candidate point 與 CAD manual line replay regression；以 `selection_source != "auto"` 時新 extension 不覆寫人工 endpoint、既有 direct validation 仍運作驗證。

## 5. Y05 與相容性 regression

- [x] 5.1 在 `tests/test_dxf_bim_block_recognition.py` 或專用 integration test，以 Y05 exact root `9E9` 驗證兩端約 425 mm outward extension 分別命中 W1／W2，並確認不再產生該 member 的 `BRACE_NOT_CONNECTED`。
- [x] 5.2 以 Y05 exact root `B9C` 驗證既有 W4 direct connection 保留、另一端約 528 mm outward extension 命中 W5，並確認不再產生該 member 的 `BRACE_ONE_END_NOT_CONNECTED`；fixture distance 僅作 regression，不寫成全域 tolerance。
- [x] 5.3 對其他 Y05 Brace、一般 Y1A／Y29 Brace、BIM Brace whole-axis fixtures與 BIM Strut fixtures執行 regression；以 recognition status／axis／width／root provenance 不因 Waler context改變、ordinary direct-connected Brace 結果不變、Strut 不延伸驗證。
- [x] 5.4 驗證完成 Review 後 `Brace.to_project_row()` 仍只輸出既有欄位，extended endpoints 與 `FromWaler`／`ToWaler` 正確 round-trip，且沒有 Project／paused Review schema migration。

## 6. 文件與最終驗證

- [x] 6.1 實作及測試成立後更新 `docs/WORKFLOW.md` 的 BIM Brace connection current behavior，清楚區分 source-supported recognition axis 與 downstream finite-Waler endpoint extension；不修改 `ARCHITECTURE.md`、`DOMAIN.md` 或 `SOLVER.md`，除非實作發現其 current truth 確實改變並先回報。
- [x] 6.2 執行 focused tests：`tests.test_dxf_brace_waler_extension`、`tests.test_dxf_bim_block_recognition`、`tests.test_dxf_input`、`tests.test_dxf_review_workflow`、`tests.test_dxf_source_exclusion`、`tests.test_dxf_review_confirmation`，修正本 change 造成的失敗且不得降低既有 assertions。
- [x] 6.3 執行完整 regression：`.\.venv\Scripts\python.exe -m unittest discover -s tests`，確認沒有新增 DXF、Project、Solver 或 persistence regression。
- [x] 6.4 執行 `openspec validate "extend-brace-axis-to-unique-waler" --type change --strict --no-interactive`，逐項核對 proposal／兩份 delta specs／design／tasks 與實際 implementation，確認所有 requirements 有對應測試且 tasks 可追蹤。
