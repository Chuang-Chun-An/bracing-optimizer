# Tasks

## 1. 現況 Characterization 與 topology fixtures

- [x] 1.1 在 `tests/test_dxf_bim_block_recognition.py` 建立 Y05 S10 root `D17` 等價 WCS fixture，先鎖定目前一般 fallback 會產生偏移 parallel-pair axes 與 `AMBIGUOUS_CENTERLINE` 的現況；驗證 fixture 的約 350 mm outer LINE set 形成完整 connected contour，而間距約 12 mm 的 duplicated longitudinal detail rails 沒有端帽、共同 closed traversal 或其他 companion provenance。
- [x] 1.2 建立 pure topology fixtures：單一 closed primitive、由多個 LINE 組成的 connected contour、具有實際 transverse／end-cap connection 的 companion rails、沒有連接 provenance 的平行 open rails、同軸巢狀 outlines、兩條拓撲獨立且完整的不等價 axes，以及無完整 topology 的 ordinary compound CAD Block；驗證每一類的成立與拒絕邊界。
- [x] 1.3 建立 width characterization fixtures：350 mm、400 mm、500 mm 的唯一完整 envelopes，以及 axis 唯一但 envelope width 不唯一的案例；驗證各合法 envelope 保留實際寬度、未硬編碼 350 mm，且 width 不可靠時不由 detail rail 猜測。

## 2. Pure same-source topology analysis

- [x] 2.1 在 `dxf_import/block_member_recognition.py` 擴充 runtime-only canonical primitive／segment provenance 與 endpoint-connectivity graph：closed outline 與 connected contour 必須形成單一 connected、unbranched closed cycle且各節點 degree 為 2；companion rails 除既有幾何 eligibility 外，必須有共同 closed traversal 或實際 transverse／end-cap paths。驗證 topology member 不依賴 child entity order、LINE start/end 或 POLYLINE traversal，且不修改 persistence schema。
- [x] 2.2 實作 topology guard：同一 topology member 內才可配對 longitudinal rails，不同 member 的 rails 不得交叉配對；驗證同軸多層 outline 收斂為一條共同軸，D17 的 12 mm open detail rails 不成立為 companion rails，也不會產生偏移 axis。
- [x] 2.3 實作 root-level axis consolidation 與 conflict 判定；驗證等價 axes 只形成一個 recognized outcome，而兩條拓撲獨立、完整且不等價 axes 回傳 `BIM_BLOCK_CONFLICTING_WHOLE_AXES` 的 ambiguous outcome。
- [x] 2.4 實作獨立 width evidence：以唯一、全長且可靠的 component envelope transverse extent 產生 `source_width`；巢狀等價 envelopes 只有在 containment 可唯一判定外包絡時採用該寬度，open detail rails 不得參與。驗證 350／400／500 mm fixtures 各自輸出實際寬度，axis 唯一但 envelope 不唯一時輸出既有 unknown width `0.0`。
- [x] 2.5 保留 legacy compatibility gate：沒有 topology guard evidence 的 ordinary full-span outline／compound Block 仍回傳 `not_applicable`；只使用既有具名 `GeometryTolerances`，沿用 `maximum_component_width_mm = 600` 且不新增未命名 numeric threshold。
- [x] 2.6 執行 pure recognition focused tests，包含 D17、same-axis nested outlines、topology conflict、ordinary compound Block、variable-width／unknown-width 與 child order、LINE direction、closed-path traversal permutation fixtures；確認不會由 entity order、first occurrence 或 candidate order 決定結果。

## 3. Importer routing、validation 與 Review lifecycle

- [x] 3.1 調整 `dxf_import/recognition.py` 與 `dxf_import/importer.py` 的 per-root Strut router，使 topology recognized outcome 建立單一 whole-axis candidate，topology ambiguous outcome 成為 terminal result，不得進入一般 `_candidate_from_group()` fallback；驗證 root provenance、WCS geometry 與 candidate count。
- [x] 3.2 將新的 terminal ambiguity 接入既有 recognition validation／ProblemRecord／ReviewItem 分類；驗證 D17 成功時沒有 blocking ambiguity，真實多軸 root 則以 root handle 顯示 unresolved source、零 formal Strut 且不可完成匯入。
- [x] 3.3 驗證 reliable `source_width` 繼續交由既有 `recognize_material_spec_from_width()` 做唯一材料比對；unknown width `0.0` 不自動填入 `material_spec`，並由既有 DXF Review 提供人工選擇，不新增材料規則。
- [x] 3.4 驗證 Source Exclusion／Restore、manual override replay、confirmation invalidation 與 Pause/Resume 仍以 role + exact root handle 運作；確認不改變 `DXFImportResult` 或 Project persistence schema。

## 4. 回歸保護與文件

- [x] 4.1 為 Y05 S10 `D17` 加入 importer-level regression：結果恰有一支 Strut、工程軸約為 `X=-15498.5`、`source_width` 約為 350 mm，且不得採用 `X=-15414`、`X=-15589`、12 mm detail spacing 或留有 `AMBIGUOUS_CENTERLINE`；同時保留 Y05 S2 全長軸 regression。
- [x] 4.2 執行受影響 DXF focused tests，包括 `tests/test_dxf_bim_block_recognition.py`、material recognition、DXF input／validation／review lifecycle tests；確認 400／500 mm envelopes 可帶入正確 material-width flow，且 Brace、Waler、Column、Beam、CornerBrace、CandidatePoint 與 Double Support 的既有測試不受影響。
- [x] 4.3 若實作完成後 DXF recognition 的長期可觀察流程確實改變，最小幅更新 `docs/WORKFLOW.md` 的 BIM Block recognition 說明；不改寫 Architecture、Domain 或 Solver 文件，並確認 Current／Desired 不混寫。
- [x] 4.4 執行 `\.venv\Scripts\python.exe -m unittest discover -s tests -v` 全量 regression；記錄通過、失敗與 skip，且不得藉由刪除或弱化 assertion 讓測試通過。
- [x] 4.5 執行 `openspec validate bim-strut-outline-topology --strict --no-interactive` 與 OpenSpec implementation verification，逐項確認 Spec scenarios、Design decisions、Tasks 與實作一致後再供 review。
