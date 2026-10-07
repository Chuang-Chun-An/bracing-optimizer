# Tasks

## 實作前閱讀

- **Task group 1 前**：閱讀 `proposal.md`「不變事項」、`design.md` Decision 1／2 與「Fixture characterization baseline」，以及 delta spec「對齊的平行外側線」、「容許角度內的外側線」與「旋轉、端點方向與來源順序」scenarios。
- **Task group 2 前**：閱讀 `design.md` Decision 3／4，以及 delta spec「縱向端點錯位不增加寬度」、「Y29 W18 使用修正後寬度配對材料」、「Y29 W19 維持既有寬度與材料」、「W18／W19 overlap 與 B15 端點歧義不受影響」與「單線 Waler」scenarios。
- **Task group 3 前**：閱讀 `design.md`「相容性與 persistence 影響」與 Risk 1／2／5，以及 delta spec「HATCH 與 MLINE 等價 envelope 不產生回歸」scenario；舊 paused Review 由使用者刪除並重新匯入，不新增 migration、相容邏輯或 regression。
- **Task group 4 前**：回看 `proposal.md` 的 In Scope／Out of Scope，確認實作沒有改動材料 `±1 mm`、接觸面、Project schema 或 Solver 規則。

## 1. Characterization 與共用正交距離幾何語意

- [x] 1.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 建立 Y05、Y29、Y1A fixture 全 Waler characterization，比較既有有限 segment 與新 supporting-line 公式的 `source_width`，並列出差值 `> width_tolerance_mm = 50.0`、材料自動配對及 `maximum_component_width_mm = 600.0` gate 翻轉；驗證結果與 `design.md`「Fixture characterization baseline」逐支一致，若出現未記錄變化則停止並回報，不調整辨識規則。
- [x] 1.2 在最接近的純幾何／Waler recognition 測試中新增 symmetric supporting-line separation cases，涵蓋對齊、縱向錯位、整體旋轉、line direction／argument order 反轉及 `<= parallel_angle_tolerance_deg` 的略不平行 rails；驗證結果使用正交 supporting-line 距離且不受有限端點 overhang 影響。
- [x] 1.3 在 `dxf_import/geometry.py` 實作共用 private supporting-line separation helper，並讓 CornerBrace 現有正式 rail-width wrapper／call site 重用它；執行 CornerBrace focused tests，驗證既有寬度與 hard gate 行為不變。

## 2. Waler 寬度與材料匹配

- [x] 2.1 在 `dxf_import/waler_contact_face.py` 將 Waler envelope hypothesis、recognized component width gate 與 `_canonical_pair()` 的 physical width 改用共用正交 helper，同時保留 finite segment proximity call sites；執行 `tests.test_dxf_waler_contact_face_recognition` 的 focused tests，驗證 `WalerEnvelopeFacts.source_width`、外側 faces 與 contact-face outcome。
- [x] 2.2 在 `dxf_import/recognition.py` 讓 Waler rail-pair candidate 的寬度與最大寬度 gate使用相同正交語意，但不改 Strut／Brace 或 duplicate／nearby 判斷；新增／調整一般 LINE、closed outline、單線與 MLINE tests，驗證 candidate 與 final envelope 不產生兩套寬度。
- [x] 2.3 新增 Y29 importer regression，以 source handle `69F` 定位 W18並傳入包含 `H400x400`、`H414x405` 的圍令材料選項；驗證 `source_width ≈ 400.000 mm`、`material_spec == "H400x400"`、不再選擇 `H414x405`，且 W18 source provenance 與既有 contact-face state 保持不變。
- [x] 2.4 擴充 Y29 overlap regression，以 source handle `720` 定位 W19並驗證 `source_width ≈ 400.000 mm`、`material_spec == "H400x400"`、`69F`／`720` 的 `WALER_SOURCE_OVERLAP` 與 `WALER_OVERLAP_COMPETITION` 維持不變，以及 B15 source `71E` 仍為 `AMBIGUOUS_WALER_CONNECTION` 且沒有正式 endpoint choice。

## 3. 相容性與長期文件

- [x] 3.1 執行 Waler contact-face、material recognition、HATCH Waler、CornerBrace 及 DXF module boundary focused suites；驗證 HATCH RC precedence、MLINE width、單線 unknown width、CornerBrace width 與 dependency boundary 無 regression。
- [x] 3.2 在 focused tests 通過後更新 `docs/WORKFLOW.md` 的 Waler recognition 段落，記錄可靠 outer faces 以 symmetric supporting-line 正交間距建立唯一 `source_width`，並明確區分 finite segment proximity；檢查未提前改寫 Architecture、Domain 或 Solver truth。

## 4. 最終驗證

- [x] 4.1 執行 `python -m unittest tests.test_dxf_waler_contact_face_recognition tests.test_dxf_material_recognition tests.test_dxf_hatch_waler_recognition tests.test_dxf_corner_brace_occluded_recognition tests.test_dxf_module_boundaries -q`（使用專案 `.venv` Python），確認相關 regression 全數通過且沒有刪除或弱化 assertion。
- [x] 4.2 執行此 change 的 OpenSpec strict validation 與 implementation verification，對照 proposal scope、delta spec scenarios 與 tasks，確認沒有未完成行為、未記錄限制或不相關修改。
