# Tasks

## 1. Characterization 與 Regression Fixtures

- [ ] 1.1 在 `tests/test_dxf_corner_brace_repair.py` 建立不依賴外部絕對路徑的 FB7／CB58 最小 WCS fixture，包含 FB7 exact source direction／圍令端 positional anchor、W2／S21、同關係對側 CB58 與較遠 references；驗證 fixture 可重現 CB58 距離最近且 local offset／station 約為 1712.030 mm、fixed length 約為 2421.177 mm。
- [ ] 1.2 在 `tests/test_dxf_corner_brace_repair.py` 固定現行錯誤模式與新 acceptance：舊 residual-axis result 約 2320.204 mm 不得成為預期，新 planner 應以 CB58 mirrored template 建立 finite W2／S21 candidate；驗證 candidate 明確記錄 CB58 與 `mirrored`，且 endpoints 來自 target local frame。
- [ ] 1.3 在既有 CornerBrace recognition／centerline tests 保留 automatic regression，驗證 `connection_plate_midpoints`、`parallel_edges_midline` 與 automatic finite-intersection endpoints 不因人工 repair 改動；執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_input tests.test_dxf_bim_block_recognition`。
- [ ] 1.4 在 `tests/test_dxf_corner_brace_repair.py` 增加拒絕矩陣：無 target direction、無 positional anchor、只有 layer／nearby evidence、無 automatic primary、invalid reference connection、incompatible endpoint topology、local angle 不相容、transferred endpoint 超出有限構件、residual mismatch、multiple unresolved relationships；驗證皆無可 Apply candidate。

## 2. Target Evidence 與 Local Template Primitives

- [ ] 2.1 在 `dxf_import/corner_brace_repair.py` 加入 immutable target-evidence DTO 與 pure extraction helpers，只讀 exact target `SourceGeometry`，分別輸出 direction hypotheses、plate／corridor positional anchors 與 diagnostics；以單元測試驗證半支殘線可用、無完整長度仍可驗證、entity order 不影響結果，連接板／外框任意邊不會被誤當完整軸。
- [ ] 2.2 在 `dxf_import/corner_brace_repair.py` 實作 automatic primary 的 finite local-frame 與 template extraction，從唯一 `CornerBraceConnection` 推導 endpoint topology、side、Waler offset、Strut inward station 與 audit fixed length；測試 reversed endpoint ordering、不同 Waler／Strut world orientation、退化交點、非 finite attachment 與超出有限構件的 rejection。
- [ ] 2.3 在 `dxf_import/corner_brace_repair.py` 實作 same-side／mirrored target-frame transfer，不複製 reference world coordinates、不 clamp／snap 超界 endpoint，且 candidate length 由 transferred endpoints 重算；測試旋轉、平移、鏡射與 arbitrary Strut material width 350／400／500 mm 皆只受工程幾何影響。
- [ ] 2.4 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair`，確認 evidence、template extraction、transfer 與 hard rejection primitives 通過後再進入 planner integration。

## 3. Compatibility、Locality 與 Planner Integration

- [ ] 3.1 在 `dxf_import/corner_brace_repair.py` 將 automatic-primary eligibility 與 template compatibility 分離：先檢查 active source、unique connection、endpoint topology、local included angle、finite target placement 與 target evidence，再產生可排序 reference；測試空間最近但不相容的 reference 被排除，下一支 compatible reference 可繼續評估。
- [ ] 3.2 在 `dxf_import/corner_brace_repair.py` 實作正式 tier ranking：同一 target Waler／Strut 的 evidence-supported 對側 reference 優先，其次相同 topology 的 compatible 鄰近 Strut，再到其他 compatible automatic primary；同 tier 才依 target anchor 至 reference engineering-line midpoint 排序，測試 member ID／entity order 不影響結果。
- [ ] 3.3 在 `dxf_import/corner_brace_repair.py` 處理 ambiguity：距離落在既有 `ambiguous_connection_delta_mm` 且產生非等價 geometry 的同 tier references 保留為多個 Preview candidates；不得 first-match 或自動 winner，並以測試驗證等價 candidates deterministic deduplicate。
- [ ] 3.4 調整 `CornerBraceRepairCandidate` 與 `plan_corner_brace_repair()`，明確保存 singular selected template、transfer mode、local offset／station、target evidence 與 supporting references；移除人工 repair 以 residual-axis finite intersections 直接產生 endpoints 的主路徑，測試 selected template 不由 `primary_references` tuple 順序暗示。
- [ ] 3.5 保留 manual repaired secondary 的既有 eligibility 與 anti-chaining contract，但只允許作 consistency／diagnostic evidence；測試 repaired CB1 → CB2 → CB3 無 automatic primary 時仍無 candidate，且 secondary 永不成為 geometry template。
- [ ] 3.6 保留 recognized replace 與 unresolved create 的不同 gate：recognized target 可預覽多個完整 relationships，unresolved target 只有全體 hard-eligible candidates 指向同一 Waler／Strut relationship 才可建立 formal CornerBrace；測試多 relationship unresolved 仍被拒絕，而同 relationship 的多個完整 templates 可供選擇。
- [ ] 3.7 在 staged validation 中確認 transferred endpoints 會建立唯一且與 candidate 相同的 CornerBraceConnection、通過 duplicate／minimum-length validation，並重建 Strut derived association；執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair tests.test_dxf_waler_contact_adjustment`。

## 4. Provenance、Persistence 與 Atomic Workflow

- [ ] 4.1 在 `dxf_import/models.py` 擴充 `CornerBraceRepairProvenance` 的 optional selected-template identity、transfer mode、Waler offset 與 Strut station fields，並在 `dxf_import/source_exclusion.py` 完成完整 serialization／deserialization；測試 new payload round-trip、partial invalid fields fail-safe，且不提升 Review state version 或修改 Project schema。
- [ ] 4.2 在 `dxf_import/source_exclusion.py` 調整 same-fingerprint replay：新 payload 必須以保存 template／mode／local values 重建等價 candidate並核對 adopted world line，不得改選目前最近 reference；測試 selected template missing／changed／incompatible、target relationship changed 與 reconstructed line drift 都回報 needs-review。
- [ ] 4.3 在 `dxf_import/source_exclusion.py` 保留 legacy version 2 repair payload 路徑，缺少 template fields 時只用既有 adopted world line、target identities 與 saved references 驗證，不套用新 ranking；以既有 legacy fixture 驗證可讀且不被靜默重算。
- [ ] 4.4 在 `dxf_import/review_recovery_planner.py` 確認 changed-content recovery 仍將 exact surviving subject 分類為 `requires_review`、missing／role-changed subject 分類為 `disabled`，且 template decision 不做 geometry-only transfer；新增 selected-template provenance regression。
- [ ] 4.5 在 `dxf_import/review_workflow.py` 擴充 stale-plan equality／signature coverage，使 target subject、target relationship、selected template connection、transfer mode或local values 改變皆拒絕 commit；測試 failure 不改變 world result、projected result、ReviewItems、confirmations、candidate store 與 revision。
- [ ] 4.6 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair tests.test_dxf_source_exclusion tests.test_dxf_review_workflow tests.test_dxf_review_recovery`，確認新舊 persistence、replay、recovery 與 atomic rollback 通過。

## 5. STEP4 Preview 與 Presentation Boundary

- [ ] 5.1 在 `dxf_import/dialog.py` 更新 CornerBrace repair Preview 表格與 detail，顯示 target Waler／Strut、selected template、`same_side`／`mirrored`、Waler offset、Strut station、result length、target direction／anchor validation及 supporting references；以 layout tests 驗證 UI 只讀 candidate DTO，不重算 compatibility 或 ranking。
- [ ] 5.2 在 `dxf_import/dialog.py` 保留 exact residual 與 proposed line overlay，並在 evidence 可用時標示 positional anchor；測試零候選只顯示具體拒絕原因、唯一候選仍需 Apply、多候選需使用者選擇、Cancel／關閉維持零副作用。
- [ ] 5.3 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_layout tests.test_interface_presentation tests.test_dxf_corner_brace_repair`，確認按鈕狀態、Preview、Apply 與 Presentation ownership 無回歸。

## 6. Documentation、Regression 與 OpenSpec Verification

- [ ] 6.1 實作完成後更新 `docs/WORKFLOW.md`，將 STEP4 repair truth 改為 compatible automatic-primary local-template transfer與target residual validation；只有 module ownership 實際改變時才更新 `docs/ARCHITECTURE.md`，並確認 `docs/DOMAIN.md`／`docs/SOLVER.md` 無需修改。
- [ ] 6.2 執行 focused DXF suite：`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_corner_brace_repair tests.test_dxf_input tests.test_dxf_waler_contact_adjustment tests.test_dxf_source_exclusion tests.test_dxf_review_workflow tests.test_dxf_review_recovery tests.test_dxf_review_layout tests.test_dxf_ocs_wcs tests.test_dxf_module_boundaries`；修正本 change 造成的失敗且不得降低 assertion 或 skip 既有案例。
- [ ] 6.3 執行完整 regression：`.\.venv\Scripts\python.exe -m unittest discover -s tests`，確認 automatic CornerBrace recognition、其他 DXF roles、Project、Solver 與 UI tests 無回歸，並記錄任何既有且與本 change 無關的 failure。
- [ ] 6.4 執行 `openspec validate reference-template-corner-brace-repair --strict`，再依 proposal、兩份 delta specs、design 與 tasks 逐項核對 implementation；確認沒有放寬 automatic recognition、沒有 manual-secondary template、沒有 proximity-only eligibility、沒有自動 Apply、沒有 Project／Solver schema 變更。
