# Tasks

## 實作前閱讀

- **Group 1 開始前**：讀 [proposal.md](./proposal.md)「相關 change與實作順序」、[design.md](./design.md) D7，以及已封存`resolve-provisional-waler-manually`與active `separate-waler-positioning-from-formal-adoption`；確認replay path的實際交集。
- **Group 2 開始前**：讀delta spec「人工決策 replay必須安全且結果等價」的候選局部驗證scenario、既有`dxf-corner-brace-repair-tool`候選安全規則，以及design D2.1／D6；先固定舊full validation oracle，才可切換production path。
- **Group 3 開始前**：讀design D2.2～D2.3；確認互動工具仍取得全部合法候選，所有planning context只活在單次函式呼叫內。
- **Group 4 開始前**：讀 delta spec「來源排除提交必須原子且綁定 revision」，以及 design D3、Single Source of Truth。
- **Group 5 開始前**：讀 delta spec「排除後畫面必須反映同一份目前結果」、既有 `dxf-review-preview-error-selection` spec，以及 design D4。
- **Group 6 開始前**：讀 delta spec的developer debug scenarios，以及 design D5。
- **Group 7 開始前**：讀 design D6與proposal「不變事項」；確認Y05／Y29驗證比較canonical結果與deterministic work-count，不建立固定秒數assertion。
- **Group 8 開始前**：回讀proposal In／Out of Scope、全部delta Requirements、design Architecture Alignment／Backward Compatibility；確認沒有引入多選／批次排除、geometry extraction cache、background worker、Solver或schema migration。

## 1. Replay contract整合與基線

- [x] 1.1 以已封存`resolve-provisional-waler-manually`為baseline，並重查active `separate-waler-positioning-from-formal-adoption`是否仍只碰`dxf_import/dialog.py`而未修改`dxf_import/source_exclusion.py::replay_manual_overrides()`；以change status與path search確認本案不新增第二套Waler或CornerBrace replay path。
- [x] 1.2 執行現有`tests/test_dxf_source_exclusion.py`、`tests/test_dxf_corner_brace_repair.py`、`tests/test_dxf_review_workflow.py`與Waler manual change的直接相關測試，記錄實作前通過基線或既有失敗，驗證後續差異可歸因於本案。
- [x] 1.3 為目前canonical sequential replay補足characterization tests，涵蓋多筆獨立repairs、secondary-reference deferred pass、target消失、preferred ID衝突、confirmation與`preserved`／`needs_review`／`disabled`，並保存可供後續differential comparison的完整結果投影。
- [x] 1.4 為現有單筆exclude／restore、取消、stale plan與paired Joist shared-root補足workflow regression，驗證本案不需要且不新增多選或batch state。

## 2. 候選局部validation

- [x] 2.1 在`tests/test_dxf_corner_brace_repair.py`建立舊`_candidate_passes_existing_validation()`的full-field characterization oracle，對相同result、temporary candidate、target Waler／Strut及tolerances記錄逐候選pass／fail；覆蓋合法、無connection、多重／模糊connection、target mismatch、candidate connection message、正反向duplicate及tolerance邊界。
- [x] 2.2 在`dxf_import/corner_brace_repair.py`以既有connection builder／predicate抽出temporary-candidate-only connection檢查，只保留現行要求的唯一connection、target Waler／Strut匹配與涉及temporary member的messages；不得複製或修改工程門檻。
- [x] 2.3 使用既有duplicate predicate與tolerances，將temporary candidate逐一和目前既有CornerBraces比較，不重算既有CornerBraces彼此；驗證正向／反向line、端點交換與邊界結果和full validator相同。
- [x] 2.4 建立逐候選local-vs-full differential test：同一planning輸入產生的每個候選都跑兩條validation並斷言相同結果；任何不等價case必須修正，或讓production對該case使用full validation fallback。
- [x] 2.5 整合local validation後比較完整`CornerBraceRepairPlan`，斷言subject、residuals、selection mode、全部candidate values／IDs／順序、provenance與diagnostics和baseline相同；保留full validator作test oracle，不形成第二套eligibility規則。
- [x] 2.6 加入deterministic work-count assertion：每個候選只建立temporary member connection並做對既有corners的pairwise duplicate比較，不再為該候選重建全場既有CornerBrace connections或既有pair duplicate diagnostics。

## 3. 單次planning context與完整候選輸出

- [x] 3.1 在`plan_corner_brace_repair()`單次呼叫內建立Waler／Strut canonical identity對照表、eligible reference／member對照與primary／secondary lookup；以spy／work-count測試驗證同次call不重做線性lookup，下一次repair則依新current result重建。
- [x] 3.2 將reference template與Waler／Strut relationship frame改為per-call memoization，key包含實際使用的identity、geometry及tolerances；以differential test驗證template內容、transfer modes、relationship選擇與diagnostics不變。
- [x] 3.3 建立只縮小比較集合的direction／positional-anchor索引，仍呼叫原matching predicate與原tie-break；以完整enumeration oracle比較每筆candidate eligibility、ranking、deduplication與順序，不得漏掉合法候選。
- [x] 3.4 確認per-call context不掛到workflow、module global、Project或repair record，函式返回後即可釋放；以連續兩筆repair且第一筆改變CornerBrace集合的測試證明第二筆不讀stale cache。
- [x] 3.5 保留互動式工具的完整合法候選輸出：多template、多relationship fixtures仍回傳全部候選並由`dialog.py`逐筆列出；不得實作「第一個通過即停止」或改成只回傳rank 1。
- [x] 3.6 維持secondary-reference deterministic deferred pass、pending順序、preferred ID、無進展終止條件與final staged result的一次完整problem／ReviewItem建立；以cross-manual differential test比較完整replay report及最終truth。

## 4. Revision-bound原子提交

- [x] 4.1 擴充`SourceExclusionPlan`，在staging階段以獨立物件預建revalidated confirmations、新candidate projection／`CandidatePointStore`與UI-neutral mutation effects；以failure-injection測試驗證任一預建步驟失敗時live workflow snapshot完全不變。
- [x] 4.2 重構`commit_source_exclusion_plan()`為base-revision／plan-validity guard後的state swap，移除live assignment後的fallible derived rebuild；以測試驗證成功只增加一次revision，且所有adopted fields來自同一plan。
- [x] 4.3 為stale plan、非法payload與assignment期間非預期例外加入rollback tests，逐欄比較提交前後完整workflow snapshot，驗證不會留下部分exclusion、混合新舊ReviewItems或遺失manual decisions／confirmations。
- [x] 4.4 驗證staging／取消不改Project dirty或persisted Review，成功commit與restore的dirty／pause-save行為和基線一致，且儲存資料仍只使用既有normalized excluded sources schema。

## 5. Mutation effects、局部刷新與hit index

- [x] 5.1 在workflow plan／commit回傳不依賴Tk或`RenderDirty`的mutation effects，描述revision、source geometry／bounds、changed source identities、members、problems、candidate points與hit-index invalidation；以`tests/test_dxf_module_boundaries.py`驗證workflow未依賴Presentation。
- [x] 5.2 在Preview dirty model加入source-style與derived-layer更新路徑，使用`PreviewScene.source_handle_items`更新changed handles並重建member／candidate／problem layers；以render tests驗證committed styles與正式結果正確，且安全路徑不重建source geometry layer。
- [x] 5.3 在單筆exclusion commit後清理不存在的selection／focus、更新tree／detail／completion projection並讓舊revision／generation的source hit index失效；以點擊測試驗證excluded或已消失的unresolved item不再被命中。
- [x] 5.4 保留source geometry／bounds未變時的viewport，實作signature、scene index、revision或dirty dependency不安全時的full-scene fallback；以測試驗證commit不自動fit-to-scene，fallback仍保留有效viewport。
- [x] 5.5 建立partial-refresh與full-refresh semantic equivalence tests，比較source styles、formal members、problems、selection priority與hit-test outcome；驗證不等價條件一律fallback而非留下stale scene。

## 6. Revision-aware lazy debug

- [x] 6.1 將`_refresh_result_views()`的debug serialization從一般結果刷新拆出，加入Dialog-local的debug revision／dirty cache；以spy測試驗證debug panel隱藏時單筆exclusion commit不呼叫`to_debug_dict()`、`json.dumps()`或完整widget insert。
- [x] 6.2 在開啟／刷新developer debug時以目前committed workflow snapshot產生payload並於完成後校驗revision；以測試驗證多次commit後只顯示最新exclusions、members、diagnostics與replay outcome，同revision可重用cache。
- [x] 6.3 將debug serialization／widget update失敗處理為可重試Presentation error而不rollback工程commit；以failure-injection test驗證workflow state與revision維持已提交值、debug cache保持dirty。

## 7. Y05／Y29效能與工程回歸

- [x] 7.1 加入deterministic work-count regression，驗證單筆排除只有一次full importer／recognition、每次CornerBrace planning不為每個候選重建全場既有CornerBrace connection／duplicate diagnostics、per-call context不跨repair共用、commit只增加一次revision、hidden debug不序列化，且安全partial refresh不重建source geometry。
- [x] 7.2 使用Y05 sample／可重建Review state比較optimized與canonical replay，驗證paired Joist source-atomic、11筆CornerBrace repairs的`preserved`／`needs_review`／`disabled`、provenance、members、connections、diagnostics與completion truth完全等價。
- [x] 7.3 使用Y29 sample／legacy source驗證單筆exclude、restore、manual replay、persistence round trip與Preview hit selection，確認本案沒有只對Y05特例化。
- [x] 7.4 新增或更新可重複執行的非CI-threshold benchmark，分別記錄Y05／Y29的convert、manual replay、final validation、commit、refresh、debug serialization、projection build count與repair數；執行一次並保存結果，確認改善來自減少重複工作而非省略validation。

## 8. 文件、完整回歸與OpenSpec驗證

- [x] 8.1 在功能與測試通過後更新`docs/WORKFLOW.md`，記錄已成立的單筆plan、optimized replay／fallback、revision-bound atomic commit與Presentation projection lifecycle；檢查diff確認未把多選／batch、geometry cache或background worker寫成既有事實。
- [x] 8.2 執行所有直接相關source exclusion、review workflow、confirmation、recovery、layout、CornerBrace、BIM Joist、Waler manual、Preview／hit selection與module-boundary tests，修正本案回歸並保留任何既有失敗紀錄。
- [x] 8.3 執行專案完整test suite；確認Domain／Solver、舊Project persistence與無關DXF recognition行為沒有回歸，且沒有靠刪除測試、降低assertion或改工程門檻通過。
- [x] 8.4 逐項對照proposal In／Out of Scope、delta spec scenarios與本tasks勾選狀態，執行`openspec validate optimize-dxf-source-exclusion-workflow --strict`並完成OpenSpec implementation verification；確認所有requirements有測試證據、無未說明限制後才進入archive。
