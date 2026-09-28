# Tasks

## 1. Baseline Protection

- [x] 1.1 在 `tests/test_solver_input_builder.py`、`tests/test_optimize_support_zone.py`、`tests/test_plan_editing.py` 與 `tests/test_support_candidate_cache_key.py` 補足或確認既有 Phase 1、candidate cache、score weight、Beam width 與 manual-edit commit boundary 的 characterization coverage；執行這四個 test modules 並確認修改 production code 前全部通過。
- [x] 1.2 在 `tests/test_dxf_input.py`、`tests/test_double_support.py`、`tests/test_project_persistence.py` 與 `tests/test_project_results.py` 補足或確認 DXF recognition output、SharedLayoutGroup mapping、Project schema 與舊 result round-trip 的 characterization coverage；執行這四個 test modules並確認基準行為通過。

## 2. Domain Geometry Policy

- [x] 2.1 在 `bracing_optimizer/domain/` 建立 pure Support adjacency geometry module，定義具名的 `5°`、`5 mm`、`1 mm` tolerances、physical axis facts、undirected axis normalization 與 deterministic full-group common direction；以新 Domain unit tests 驗證 row reorder、Start／End reversal、水平／垂直／輕微角度差均產生等價 direction semantics。
- [x] 2.2 在相同 Domain module 實作 zero-length、全組 pairwise angle 與 length validation及 structured issue data；以 boundary tests 驗證正好 `5°`／`5 mm` 可接受、超過容差會產生包含 member IDs、實際值與 tolerance 的對應 issue code。
- [x] 2.3 在相同 Domain module 實作 midpoint、row-direction projection與 `<= 1 mm` ambiguity判定；以 unit tests 驗證正好 `1 mm` 仍 invalid、超過 `1 mm` 可排序，且不得使用 row index、StrutID或input order作 tie-break。

## 3. Application Adjacency Contract

- [x] 3.1 在 `bracing_optimizer/application/solver_input_builder.py`（必要時搭配小型 application model module）定義 transient `SupportAdjacencyContract`與 optimization-unit資料，讓 normal Strut使用axis midpoint、SharedLayoutGroup先collapse並使用兩lane midpoint中心；以builder tests驗證physical member identity與兩lane configs皆被保留，且contract沒有`representative_length`。
- [x] 3.2 讓 `SupportInputBuilder` 使用Domain geometry policy驗證目前Project Zoning、計算unit projections、建立deterministic ordered units與consecutive pairs；以`tests/test_solver_input_builder.py`驗證三支以上row reorder、endpoint reversal、SharedLayoutGroup lane reorder都維持相同pair set。
- [x] 3.3 讓 `SupportInputBuilder` 對zero-length、angle、length及projection tie回傳穩定的Application validation contract，而非改寫Zoning或best-effort排序；以builder tests驗證每個failure code及`Phase 2` input未建立。
- [x] 3.4 保持Main欄位編輯、Project validation與save流程不套用Solver geometry tolerance；在`tests/test_main_project_editing.py`、`tests/test_project_validation.py`及`tests/test_project_persistence.py`驗證使用者可保存`> 5°`或`> 5 mm`的Zoning（包含已確認但超出tolerance的SharedLayoutGroup），且重新開啟後membership與shared relationship不被DXF suggestion覆寫。

## 4. Unit-based Support Phase 2

- [x] 4.1 在 `bracing_optimizer/algorithms/support.py` 與 `bracing_optimizer/application/optimize_support_zone.py` 建立unit-level candidate/fact assembly：normal unit含一個physical plan，shared unit依既有`shared_layout_signature`配對兩個physical plans；以algorithm/application tests驗證Phase 1的完整`pieces`去重使每支physical Strut的signature至多對應一個retained plan、assembly不新增signature pruning，且兩lane材料與plan score仍分別計數。
- [x] 4.2 在shared unit assembly驗證兩lane `jack_center`相同，並以shared station及merged `pile_centers`呼叫既有`get_jack_region_id()`；以tests驗證lane order不影響region、length不參與region，station不一致回傳`SHARED_JACK_INVARIANT_VIOLATION`而不任選lane。
- [x] 4.3 將500 mm spacing與既有Jack region consistency penalty集中到單一unit-pair evaluator；以tests驗證`< 500 mm`失敗、`= 500 mm`通過、非相鄰unit不比較、shared內部不比較且每個external boundary只計算一次，並確認既有region weight未變。
- [x] 4.4 將 `build_global_solution`及其fallback/search stages改為依ordered optimization units與explicit adjacency contract進行Beam Search，不再從flattened plans推測相鄰；以`tests/test_optimize_support_zone.py`驗證row reorder及Phase 1 cache命中狀態不改變legality、region penalty或選擇結果。
- [x] 4.5 保持 `GlobalSolution.plans`輸出全部physical plans與既有persistence shape，同時讓`min_jack_distance`、score summary及pair diagnostics只取contract中的external unit boundaries；以tests驗證少於兩個units時沒有distance、shared lane pair與非相鄰pairs均被排除。
- [x] 4.6 在 `bracing_optimizer/application/optimize_support_zone.py` 接好pre-Phase-2 validation與failure result contract；以application tests驗證一般invalid Zoning及已確認但`> 5°`／`> 5 mm`的SharedLayoutGroup都完全不呼叫Phase 2，已有committed result時保持原結果，原本No Result時仍為No Result。

## 5. Manual Support Editing

- [x] 5.1 修改 `bracing_optimizer/application/plan_editing.py`，讓manual global recalculation從current Project geometry重建相同`SupportAdjacencyContract`並呼叫共用unit scorer；以`tests/test_plan_editing.py`驗證initial solve與manual recalculation使用相同pair set、spacing、region penalty及`min_jack_distance`。
- [x] 5.2 將 `SupportPlanEditing.neighbor_checks`改為查詢geometry unit的external previous／next pairs；以tests驗證normal member及SharedLayoutGroup任一lane都不會把同組lane當成一般500 mm neighbor。
- [x] 5.3 讓manual staged edit在geometry validation或shared Jack invariant失敗時拒絕commit；以tests驗證既有committed solution維持不變，且`TargetJackRegion`仍只是preference、不會被升級為額外invalid條件。

## 6. DXF Initial Zoning Suggestion

- [x] 6.1 在 `dxf_import/` 新增pure initial-Zoning operation，從reviewed Waler world geometry使用既有`GeometryTolerances.parallel_angle_tolerance_deg`、`collinear_tolerance_mm`與`endpoint_tolerance_mm`建立continuous Waler chains及unordered chain-pair topology signatures；以DXF unit tests驗證同一chain可跨不同Waler member IDs，明確不同chain pairs不會被spatial fallback合併，且沒有引入新的工程常數。
- [x] 6.2 在該operation重用Domain angle／length eligibility，依canonical transverse geometry建立deterministic order及maximal contiguous runs；以tests驗證source order與Start／End reversal不影響membership、一般out-of-tolerance member形成boundary、已確認SharedLayoutGroup作為不可拆分ordering-unit例外、不能跳過中間Strut且large gap本身不拆組。
- [x] 6.3 實作missing／ambiguous Waler topology的spatial-adjacency fallback與ambiguous assignment diagnostic；以tests驗證fallback只連接geometry order中的相鄰候選、不得跨越其他支撐或覆寫explicit topology conflict，兩側同樣合理但互相衝突時保持獨立且不依來源順序猜測。
- [x] 6.4 將initial grouping只接到使用者完成當次Waler／Strut必要確認並執行「完成匯入」後、`DXFImportResult.to_project_rows()`建立rows之前的mapping boundary；讓已確認DXF double-support pair作為一個ordering unit且兩lane取得相同initial Zoning，以`tests/test_dxf_input.py`、`tests/test_double_support.py`與`tests/test_dxf_review_workflow.py`驗證圖層辨識／Review polling不提前分組、recognition結果本身不變，且out-of-tolerance shared pair仍可匯入Main但在Solver preflight被拒絕。
- [x] 6.5 驗證Replace只對本次imported rows配置deterministic initial Zoning、Append不重分或覆寫既有Project rows且名稱不衝突；以DXF→Project application tests驗證使用者既有Zoning保持原值。

## 7. Diagnostics and Presentation Boundary

- [x] 7.1 擴充Support validation／solver diagnostics DTO，讓angle、length、projection tie、shared Jack invariant與unit-pair failure包含Zoning、unit/member IDs、實際值、tolerance及Phase 2是否執行；成功result將JSON-safe unit／pair snapshots放入既有`search_diagnostics` optional fields，pre-commit validation failure只回傳runtime diagnostics；以`tests/test_solver_diagnostics_integration.py`驗證diagnostic pair set與solver實際pair set完全相同，且缺少optional fields仍可讀取。
- [x] 7.2 在既有Support Solver presentation error path格式化新的structured diagnostics，不在UI複製geometry rules；以presentation tests驗證訊息清楚區分Zoning geometry invalid、shared invariant與一般無解，且failure before commit不清除既有result。

## 8. Compatibility, Boundaries, and Long-term Documentation

- [x] 8.1 執行並補強`tests/test_project_persistence.py`與`tests/test_project_results.py`，驗證完整runtime adjacency contract、canonical direction、projection與unit objects不進入Project／result payload；成功result的optional unit／pair `search_diagnostics`可沿用既有dict serialization round-trip，舊Project／result缺少新fields仍可load，且schema version與save/load migration保持不變。
- [x] 8.2 更新`tests/test_application_domain_boundaries.py`、`tests/test_app_dependencies.py`與`tests/test_dxf_module_boundaries.py`的architecture coverage，驗證Domain helper不依賴Application／UI／Infrastructure、Algorithms不讀Project geometry、DXF grouping維持在DXF subsystem且Application仍是Project→Solver contract owner。
- [x] 8.3 實作與驗證完成後更新`docs/DOMAIN.md`及`docs/SOLVER.md`，將input-order adjacency known gap改為已實作的geometry-based規則；檢查並僅在runtime truth確有改變時同步`docs/WORKFLOW.md`，只有責任邊界偏離既有架構時才修改`docs/ARCHITECTURE.md`，並以全文搜尋確認文件未把DXF suggestion寫成authoritative Zoning或引入length-based Jack region。

## 9. Final Verification

- [x] 9.1 執行所有本change直接相關測試：Domain adjacency、`test_solver_input_builder.py`、`test_optimize_support_zone.py`、`test_plan_editing.py`、`test_solver_diagnostics_integration.py`、DXF initial grouping／input／double-support／review workflow、Project persistence/results及architecture boundary tests，確認全部通過且沒有修改既有score weights、Beam width或Phase 1 candidate policy。
- [x] 9.2 執行完整regression suite `\.venv\Scripts\python.exe -m pytest -q`，確認Support、Waler、DXF、persistence與Presentation測試皆通過；任何failure須判定並回到對應task處理，不得降低assertion或排除測試。
- [x] 9.3 依proposal、support-adjacency spec與design逐項執行OpenSpec implementation verification，確認所有Scenario均有測試或可重現證據，然後執行`openspec validate geometry-based-support-adjacency --type change --strict --no-interactive`並確認change有效且所有tasks完成。
