# Tasks

## 實作前閱讀

- 第 1 組先讀 proposal 的 consumer audit gate、design Decision 1～2，以及三個候選 definition、replacement production caller 與 baseline tests。
- 第 2 組先讀 design Decision 2，確認範圍只含三個候選；_refine_corner_brace_axis_intersections_legacy 必須保留。
- 第 3～4 組先讀 design Decision 3；依修改範圍閱讀 `dxf-corner-brace-occluded-rail-recognition`、`dxf-waler-contact-face-recognition`、`dxf-column-association-repair`、`beam-member-connection-validation` 的相關 Requirements，不調整 expected output 來容納差異。

## 1. 完成 consumer 與 replacement audit

- [x] 1.1 對 `_legacy_corner_brace_candidates_from_group`、`_associate_components_to_struts_legacy`、`_select_waler_inner_lines` 建立逐項 audit matrix，搜尋 direct call/import、module/function alias、名稱字串、`__all__`／re-export、`getattr`／registration、monkeypatch、tests、維護腳本、`SupportSolver.spec` 與其他 build entry；將 archived OpenSpec 文字引用標為 non-runtime，並記錄使用者已確認沒有外部 consumer。
- [x] 1.2 逐項驗證 design Decision 2 的 replacement mapping：`_corner_brace_candidates_from_group`、`_resolve_waler_contact_geometry`、`associate_components_to_struts` 均有 production caller 與 focused tests；任一 mapping 不成立時停止整個 change 並回報，不搬移 caller、不新增 wrapper、不改成只刪部分候選。
- [x] 1.3 在刪除前以目前 production importer 執行真實 DXF fixtures，保存各 fixture 的 member 數量、engineering identity、幾何與 diagnostics 快照；快照必須可由刪除後的相同 entry point 重建並逐項比對，建立或保存失敗時停止刪除。
- [x] 1.4 確認 `_refine_corner_brace_axis_intersections_legacy` 仍由 `_refine_corner_brace_axis_intersections()` 呼叫且相關 tests 通過，將它列入明確保留清單。

## 2. 刪除已通過 gate 的 unreachable code

- [x] 2.1 從 `dxf_import/recognition.py` 刪除 `_legacy_corner_brace_candidates_from_group` definition，執行 `tests.test_dxf_corner_brace_occluded_recognition` 與相關 `tests.test_dxf_input` regression，驗證 current CornerBrace output 不變。
- [x] 2.2 從 `dxf_import/recognition.py` 刪除 `_select_waler_inner_lines` definition，執行 `tests.test_dxf_waler_contact_face_recognition` 與相關 `tests.test_dxf_input` regression，驗證 canonical Waler contact output 不變。
- [x] 2.3 從 `dxf_import/candidate_points.py` 刪除 `_associate_components_to_struts_legacy` definition，執行 `tests.test_dxf_waler_contact_adjustment`、`tests.test_dxf_beam_brace_contacts`、`tests.test_double_support` 與相關 `tests.test_dxf_input` regression，驗證 association output 不變。
- [x] 2.4 只修正 live code 中直接提及已刪名稱的 dangling docstring（目前為 `_finalize_contextual_strut_waler_spans` 對 `_select_waler_inner_lines` 的引用），以 module import 與 `tests.test_dxf_module_boundaries` 驗證；不得連帶刪除其他 helper、constant、setting、import 或 archived OpenSpec 歷史。

## 3. DXF regression 驗證

- [x] 3.1 執行 CornerBrace recognition／repair、candidate points、Waler recognition、source exclusion、Review workflow、`tests.test_dxf_module_boundaries` 與 `tests.test_package_layout`，確認 tolerance、priority、dedup、repair、public exports 與 Review behavior 不變。
- [x] 3.2 以相同 production importer 與真實 DXF fixtures 重建輸出，對 Task 1.3 快照逐項比對 member 數量、engineering identity、幾何與 diagnostics，驗證完全相同；任何差異皆停止交付，不得修改 snapshot 或 expected output 來容納差異。

## 4. 整體驗證

- [x] 4.1 執行完整 test suite，確認 DXF importer、Project workflow、Solver input 與 export 沒有隱含 dependency regression。
- [x] 4.2 重新執行 consumer matrix 搜尋，驗證三個已刪名稱不再存在於 executable code、tests、exports、dynamic registration 或 build hooks；允許本 change 與 archived OpenSpec 保留 non-runtime 歷史文字，並確認沒有 dangling live-code reference。
- [x] 4.3 掃描刪除前只由三個候選使用、刪除後已無 consumer 的 helper、constant、setting 與 import，列出清單供日後另案處理；本 change 一律保留，不得刪除。
- [x] 4.4 重新確認專案 tests、CI、pre-commit 與正式驗證入口是否執行 lint／unused-import 檢查；若保留 Task 4.3 清單中的 import 會使任何必要檢查失敗，停止並回報衝突，不得自行刪除 import 或放寬檢查。
- [x] 4.5 執行 `openspec validate retire-unused-dxf-legacy-functions --strict`，再以 `$openspec-verify-change` 對照 proposal、design、tasks 與實作，確認 behavior-preserving、`skip_specs: true` 合理且未刪除仍有 consumer 的 helper。
