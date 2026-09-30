# Tasks

## 實作前閱讀

- **第 1 組前**：閱讀 `proposal.md` 的「快速摘要／不變事項」、`design.md` 的 D1，以及 delta spec 的 `Brace 實體寬度 SHALL 通過正式 hard gate`。
- **第 2 組前**：閱讀 `design.md` 的 D2／D3，以及 delta spec 的 `Component-like Brace body evidence SHALL require whole-source support`、`Component-like Brace SHALL 依 whole-source center authority 選軸`、`Brace recognition outcome SHALL fail safely and deterministically`。
- **第 3 組前**：閱讀 `design.md` 的 D1／D3，並檢查 `dxf_import/recognition.py::_candidate_from_group` 的 MLINE、outline、parallel-edge 與 single-LINE branches。
- **第 4 組前**：閱讀 `design.md` 的 D4／D5，以及 delta spec 的 Review／persistence requirement；需要時才閱讀 Brace-to-Waler、Strut 與 CornerBrace 主規格。
- **第 5 組前**：重新核對 proposal 的 In Scope／Out of Scope、全部 delta requirements 與 `design.md` 的 Architecture Alignment；只有 implementation 已通過驗證後才更新 long-term truth。

## 1. 建立 Brace 寬度 hard gate

- [x] 1.1 在 `dxf_import/models.py` 新增具名 `minimum_brace_body_width_mm = 250.0`，並在 `dxf_import/block_member_recognition.py` 建立 component/general route 共用的嚴格 `>` pure predicate；於 `tests/test_dxf_bim_block_recognition.py` 新增 `250.0` 拒絕、`250.001` 接受且不受 `width_tolerance_mm`、epsilon 或 display rounding 影響的測試，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceBodyWidthPolicyTests` 驗證。
- [x] 1.2 明確保留 centerline-only unknown width：新增單一 LINE／明確中心線無 body envelope 的 regression，確認 `source_width == 0.0` 只在此 route 表示 unknown、不呼叫 measured-width gate且仍產生 `existing_centerline`；執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceBodyWidthPolicyTests OrdinaryBraceAssetRegressionTests` 驗證。

## 2. 實作 component-like classification、supporting-side width 與 authority

- [x] 2.1 在 `dxf_import/block_member_recognition.py` 建立 whole-source component-like body-evidence classification，明確要求完整／connected topology、共同支持主要 corridor 的 whole-root bands，或同時支持主要方向、可靠 terminal extent 與 body envelope 的既有 evidence；新增正例、只有局部 pair／短 detail／branch／孔洞／零散內部線的反例，以及 child／handle／candidate order 重排測試，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceComponentLikeEvidenceTests` 驗證 classification 與排序無關。
- [x] 2.2 為 `TOPOLOGY` closed outline 實作 outer supporting-side width：只接受 engineering axis 相對兩側、方向相容、共同支持主要 longitudinal corridor 的 sides；新增矩形正確寬度、斜端板不取端板長度、突出 detail 不取最遠點、內部 web／flange 不成 supporting side、supporting sides 不唯一時 width unreliable 的 synthetic tests，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceClosedOutlineWidthTests` 驗證 bounding box、rotated-box 短邊、端板與最遠頂點均不能補足 width。
- [x] 2.3 將 Brace 分流到專用 pure recognition path，分別列舉 `TOPOLOGY`、`WHOLE_ROOT_ENVELOPE`、`LOCAL_RAIL_PAIR` 全部候選，逐候選完成完整性、whole-source support、reliable extent、width measurement 與 Task 1 gate，再從最高合法 tier 進行等價合併／唯一性判斷；執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceCenterAuthorityTests` 驗證：(a) 160 mm topology 不阻擋 300 mm envelope、(b) 唯一合法 topology 勝過 lower tier、(c) 最高合法 tier 多解必須 ambiguous且不降層、(d) 全 tiers 無合法候選必須 failed、(e) 160 mm 高分候選不得遮蔽 300 mm 合法候選。
- [x] 2.4 確認 topology supporting sides 不可靠時該 candidate 被移除但 lower-tier whole-root envelope 仍會被評估；新增 irregular outline + legal 300 mm envelope recovery test，並執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceClosedOutlineWidthTests BraceCenterAuthorityTests` 驗證不得猜測 width、不得因高 tier 不合法而提前失敗。
- [x] 2.5 對已成立 component-like body evidence 的 root，將唯一合法候選映射為 `recognized`、全部 tiers 無合法候選映射為 terminal `failed`、最高合法 tier 多解映射為 terminal `ambiguous`；過窄 measured candidates 使用 `BRACE_BODY_WIDTH_TOO_SMALL`，不可靠 extent／width 使用既有適當 diagnostic，且 `_route_component_like_member_block_with` 必須 `handled=True` 並保留 Brace role 與 exact root handle，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceBlockMemberPolicyTests BIMBlockRecognitionRouterTests BIMBlockProblemIntegrationTests` 驗證不得改回 `not_applicable` 或進入 general fallback。
- [x] 2.6 增加 component-like classification 與 authority outcome 的 child order、handle order、LINE direction、closed-path traversal、candidate enumeration 重排測試，確認 classification、winner、width、diagnostic 與 normalized axis deterministic；執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceComponentLikeEvidenceTests BraceCenterAuthorityTests BraceBlockMemberPolicyTests` 驗證。

## 3. 對一般 body-derived Brace 套用相同規則

- [x] 3.1 在 `dxf_import/recognition.py::_candidate_from_group` 對 Brace MLINE、closed outline，以及「outline + explicit centerline」的 measured width 在 candidate 建立／選擇前套用共用 gate；closed outline 必須沿用 Task 2 的 supporting-side width contract，全部過窄或寬度不可靠時回傳明確 error且不建立 candidate，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceGeneralBodyWidthGateTests BraceClosedOutlineWidthTests` 驗證 `250.0`、`250.001`、合法 outline center 與 unknown single LINE。
- [x] 3.2 調整一般 parallel-edge enumeration，使過窄 pair 先被剔除、合法 pair 不被過窄高分候選遮蔽；若所有 measurable pairs 過窄則產生 blocking diagnostic，執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceGeneralBodyWidthGateTests` 驗證「先 gate、後 selection」與 ambiguity 邊界。
- [x] 3.3 確認一般 route 與 component-like route 共用同一 predicate／threshold，且 `connection_tolerance_mm`、`minimum_corner_brace_rail_separation_mm`、`maximum_brace_axis_extension_mm` 未被重用或改值；以直接 assertions 加上 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BraceBodyWidthPolicyTests` 與 `.venv\Scripts\python.exe tests/test_dxf_corner_brace_occluded_recognition.py CornerBraceRailMaterialRuleTests` 驗證語意隔離。

## 4. 串接真實案例、Review 與相容性 regression

- [x] 4.1 在 `tests/test_dxf_bim_block_recognition.py` 新增 Y05 B8／legacy root `DD9`（重上傳 fixture 使用既有 handle mapping）的 real-asset regression，斷言約 `160.015 mm` local pair 被 gate 拒絕、representative width 約 `300 mm`、source-supported axis 約 `(-37000, -18368.859)` 至 `(-32168.859, -23200)`，且 formal member 保留同 root provenance；執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py Y05BraceCenterAuthorityRegressionTests` 驗證。
- [x] 4.2 補 component-like terminal failure／ambiguity 的 Review integration：確認 `ProblemRecord`／`ReviewItem` 保留 Brace role 與 exact root handle、未處理前阻擋完成，exclude／restore 後重新辨識，且 Pause／Resume、manual endpoint replay 與 Project row schema 未新增欄位；執行 `.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py BIMBlockProblemIntegrationTests BIMBlockReviewLifecycleIntegrationTests` 驗證。
- [x] 4.3 執行真實資產與相鄰功能 regression：`.venv\Scripts\python.exe tests/test_dxf_bim_block_recognition.py Y05BraceSourceCharacterizationTests OrdinaryBraceAssetRegressionTests Y05StrutCenterAuthorityRegressionTests`、`.venv\Scripts\python.exe tests/test_dxf_corner_brace_occluded_recognition.py`、`.venv\Scripts\python.exe tests/test_dxf_brace_waler_extension.py`；Y1A single-line、合法 Y29 outline、Strut、CornerBrace 與 Brace-to-Waler 行為須維持，Y29 若有 `<=250 mm` body 必須改成具 exact source 的明確 rejected expectation而非放寬 hard gate。

## 5. 長期文件與最終驗證

- [x] 5.1 在 focused implementation 與 regression 均通過後更新 `docs/DOMAIN.md`，把自動 body-derived Brace 的可靠實測寬度嚴格 `> 250.0 mm`、component-like whole-source evidence 與 supporting-side width 記為 Engineering Hard Constraint，並明確區分 unknown centerline、CornerBrace rule、250 mm connection tolerance 與 600 mm axis extension；以 `rg -n "Brace|250|component-like|supporting|unknown|connection|extension" docs/DOMAIN.md` 人工核對文件語意。
- [x] 5.2 執行 `.venv\Scripts\python.exe tests/test_package_layout.py` 驗證 dependency／public API boundary，再執行 `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` 完成全套 regression；不得刪除測試、降低 assertion、恢復 first-match、加入未命名 magic number或以放寬 hard gate 解決失敗，並記錄任何與本 change 無關的既存失敗。
- [x] 5.3 對照 `proposal.md`、delta spec、`design.md` 與本 checklist 執行 OpenSpec implementation verification，確認沒有修改 Solver、Project schema、Strut／CornerBrace 規則或人工 workflow，最後執行 `openspec validate strengthen-brace-body-recognition --type change --strict` 並取得通過結果。

