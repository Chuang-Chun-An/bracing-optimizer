# Tasks

## 1. 建立現況與安全邊界測試

- [x] 1.1 在 `tests/test_dxf_corner_brace_repair.py` 建立最小 WCS fixtures，涵蓋 CB71 類「正式角撐軸線錯誤」、unresolved 殘線、automatic recognized primary、manual repaired secondary 與有限 Waler／Strut；驗證 fixture 可重現修補前缺口，且不依賴外部絕對路徑。
- [x] 1.2 在 `tests/test_dxf_input.py` 與 `tests/test_dxf_waler_contact_adjustment.py` 鎖定現行未啟動修補時的 automatic CornerBrace 數量、recognition method、端點延伸、`CornerBraceConnection` 與 Strut 角撐衍生長度；驗證既有 Y1A／Y29 類案例完全不變。
- [x] 1.3 在 `tests/test_dxf_corner_brace_repair.py` 增加拒絕基線：無 target residual、無 automatic primary、只有 repaired references、repaired-only chaining、未確認／requires-review secondary、只有無限延長線交點、reference connection 無效及多條缺少必要 evidence 的 residual guesses；驗證都不產生可 Apply candidate。

## 2. 建立 pure CornerBrace repair planning

- [x] 2.1 在 `dxf_import/models.py` 與 `dxf_import/corner_brace_repair.py` 加入 immutable repair subject key、candidate、plan 與 provenance DTO；以 exact source evidence + base geometry discriminator 區分同 handles 的多支 CornerBrace，並以 unit tests 驗證 deterministic equality／serialization-friendly data。
- [x] 2.2 在 `dxf_import/corner_brace_repair.py` 實作 target residual hypothesis 擷取與 canonicalization，只使用 exact target `SourceGeometry` 與現有 `GeometryTolerances`；測試 350／任意材料寬度皆不影響規則，且 entity order 不改變輸出。
- [x] 2.3 在 `dxf_import/corner_brace_repair.py` 實作 reference eligibility：automatic recognized + active source + unique valid `CornerBraceConnection` 才能成為 primary；explicitly adopted + complete provenance + current confirmation + active source + non-`requires_review` + valid connection 的 repaired CornerBrace 只能成為 secondary；測試同支撐／鄰支撐 primary、合法 secondary、invalid reference rejection，及每個 candidate 都至少保有一支 primary。
- [x] 2.4 在 `dxf_import/corner_brace_repair.py` 阻止 repaired-reference transitive chaining：secondary provenance 不遞迴提供 reference confidence，repaired-only evidence 永遠無法成立 candidate；測試 repaired CB1 → CB2 後，CB2 不能在沒有新的 automatic primary 時單獨支持 CB3。
- [x] 2.5 在 `dxf_import/corner_brace_repair.py` 以 target residual + reference consistency + finite Waler／Strut intersections 建立 hypotheses，正式 endpoints與 fixed length只由 target finite intersections 推導；測試 reference coordinates／fixed length 不會覆寫或移動交點，length／side／topology不一致只會 reject hypothesis。
- [x] 2.6 實作 hard-filter-before-preview 與 canonical dedup／sorting：`CornerBraceRepairPlan.candidates` 只含通過全部 hard eligibility 的 candidates，rejected hypotheses 只產生 diagnostics，proximity 只排序合法 candidates；測試零候選、唯一候選、多個完整非等價候選、多個缺證據 guesses 與最近距離不得合法化或自動選 winner。
- [x] 2.7 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_corner_brace_repair.py`，確認 reference classification／chaining、reference-length semantics、hard filtering、finite intersection、determinism 與 ambiguity contract 全部通過。

## 3. 建立原子 Review mutation 與衍生資料重建

- [x] 3.1 在 `dxf_import/corner_brace_repair.py` 分開實作 recognized replace 與 unresolved create：replace 保留原 ID；create 只有在 exact `corner_brace` identity、target residual、可靠有限 hypotheses、全體 surviving hypotheses 的唯一 Waler／Strut relationship、automatic primary、explicit adoption 與全部既有 applicable CornerBrace validation 通過後，才配置 deterministic unique `CB<n>`；測試僅有 layer／INSERT／nearby/reference、缺 residual、多組 relationships 或任一 validation failure 時維持 unresolved 且不產生 ghost formal member。
- [x] 3.2 重用 `rebuild_candidate_points_for_components()`、`attach_corner_braces_to_struts()` 與 `build_corner_brace_connections()` 建立 repair-specific derived rebuild；測試只重建 target candidate points、保留其他 member 的人工選擇與既有 Waler contact adopted values，並正確更新 Strut 四個角撐長度欄位、hole station 及 fixed length。
- [x] 3.3 在 `dxf_import/review_workflow.py` 加入 plan／commit commands，以 `base_revision` 與 subject signature 拒絕 stale plan，commit 時再次確認 selected candidate 仍通過全部 hard filters與 unresolved create gate，並在 local staged projection 完成後一次交換 world result、projected result、problems、ReviewItems、confirmations、candidate store 與 revision；測試成功 commit、stale／eligibility-change rejection 及任一步驟失敗的零部分更新。
- [x] 3.4 在 `tests/test_dxf_review_confirmation.py` 與 repair workflow tests 驗證修補 target／關聯 subject 的 current-state signature 失效時會移除 confirmation 並回報 invalidation，而無關 confirmation 保持有效。
- [x] 3.5 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_corner_brace_repair.py tests/test_dxf_waler_contact_adjustment.py tests/test_dxf_review_confirmation.py`，確認 headless repair commit 與 downstream 一致性。

## 4. 補齊 Pause／Resume 與 compatible recovery

- [x] 4.1 在 `dxf_import/source_exclusion.py` 的既有 `manual_overrides` capture／parse boundary 擴充 optional CornerBrace repair payload，保存 automatic primary／manual repaired secondary identities及 reference class，不新增 Project schema或提高 `review_state_version`；在 `tests/test_dxf_source_exclusion.py`／`tests/test_dxf_review_workflow.py` 驗證舊 state 相容、完整 reference provenance round-trip 及缺漏 provenance 不會取得 secondary eligibility。
- [x] 4.2 實作 same-fingerprint repair replay：base recognition 後依 repair subject key、target Waler／Strut exact identities重新驗證，且至少一支保存的 automatic primary與所有採用 secondary 仍符合現行 eligibility才可重建；測試同 handles 多角撐不互換、preferred `CB<n>` 衝突、primary失效但secondary仍存在、secondary未確認／來源失效／connection失效／requires-review、reference改變時不另猜 reference，以及 replay failure 回報 needs-review 而不套錯物件。
- [x] 4.3 在 `dxf_import/review_recovery_planner.py` 將 repair decision 與一般 manual endpoint 分開分類；測試 Exact Match 完整保留、changed-content exact subject=`requires_review`、subject missing／role changed=`disabled`、geometry-only match 不轉移，且 `requires_review`／`disabled` repair 不提供 primary或secondary reference eligibility、category counts 仍由 entries 推導。
- [x] 4.4 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_source_exclusion.py tests/test_dxf_review_workflow.py tests/test_dxf_review_recovery.py tests/test_project_service.py tests/test_project_persistence.py`，確認 Pause／Resume、Relink 與 persistence regression 通過。

## 5. 接上 STEP4 修改工具與預覽

- [x] 5.1 在 `dxf_import/dialog.py` 加入「修補角撐」入口，只在選取 recognized CornerBrace 或具有安全 identity 的 unresolved `corner_brace` subject 時啟用；在 `tests/test_dxf_review_layout.py` 驗證其他 role、excluded item 與缺少 source identity 時不啟用。
- [x] 5.2 在 `dxf_import/dialog.py`／`dxf_import/preview.py` 只顯示 planner 已通過 hard eligibility 的 repair candidates，並標示 target residual、proposed axis、target Waler／Strut、automatic primary、optional repaired secondary 與 diagnostics；測試零 candidate 顯示拒絕原因、唯一 candidate 仍需確認、多個完整 candidates 可切換，且多個 rejected guesses 不會出現 Apply action。
- [x] 5.3 將 Apply／Cancel 接到 `DXFReviewWorkflow` commands；UI tests 驗證 Cancel／關閉 preview 零副作用、Apply 只提交 selected candidate、stale plan 提示重新預覽，Dialog 不直接 replace workflow-owned models。
- [x] 5.4 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_review_layout.py tests/test_interface_presentation.py tests/test_dxf_corner_brace_repair.py`，確認 Presentation ownership、button state 與 preview／commit 行為。

## 6. 文件、Regression 與 OpenSpec 驗證

- [x] 6.1 實作完成後更新 `docs/WORKFLOW.md`，記錄 STEP4 CornerBrace repair 的 staged preview、explicit adoption、Pause／Resume 與 changed-content recovery；若 `corner_brace_repair.py` 成為長期 module owner，再同步 `docs/ARCHITECTURE.md` 的 DXF module inventory，並確認 `docs/DOMAIN.md`／`docs/SOLVER.md` 無需變更。
- [x] 6.2 執行 focused DXF suite：`\.venv\Scripts\python.exe -m pytest tests/test_dxf_corner_brace_repair.py tests/test_dxf_input.py tests/test_dxf_waler_contact_adjustment.py tests/test_dxf_source_exclusion.py tests/test_dxf_review_workflow.py tests/test_dxf_review_confirmation.py tests/test_dxf_review_recovery.py tests/test_dxf_review_layout.py tests/test_dxf_ocs_wcs.py tests/test_dxf_module_boundaries.py`，修正本 change 造成的失敗且不得降低 assertion 或 skip 既有案例。
- [x] 6.3 執行完整 test suite 與 boundary checks，確認未修改 automatic recognition、Project schema、Solver、Waler contact displacement、一般 Waler／Strut／Brace editing 或無關 workflow behavior，並記錄總測試結果。
- [x] 6.4 執行 `openspec validate add-corner-brace-repair-tool --strict --no-interactive` 與 OpenSpec implementation verification，確認 proposal、三份 spec delta、design、tasks 與實作一致，且所有 task 完成後才進入 sync／archive。
