# Tasks

## 實作前閱讀

- **Group 1開始前**：讀[proposal.md](./proposal.md)「相關change與實作順序」、[design.md](./design.md) Context／D8，以及已封存`stabilize-corner-brace-repair-reference-identity`的最終tasks與verification結果；先固定replay baseline，避免重新定義同一條驗證路徑。
- **Group 2開始前**：讀delta spec「來源排除必須由使用者逐筆明確選取」、「逐筆入口與source-atomic assembly必須維持相容」與design D1／Single Source of Truth；實作pending identity前重讀`dxf_import/source_exclusion.py`的正規化與eligibility helpers。
- **Group 3開始前**：讀delta spec新增的「待排除草稿必須與正式Review truth分離」與design D2、D6；盤點所有會修改Review revision／truth的Workflow與Dialog入口。
- **Group 4開始前**：讀delta spec「來源排除必須以一次完整canonical staging建立結果」、「人工決策replay必須安全且結果等價」、「來源排除提交必須原子且綁定revision」，以及design D3、D4、D7；不得建立第二套recognition或commit path。
- **Group 5開始前**：讀delta spec「排除後畫面必須反映同一份目前結果」與design D5；修改Preview時另讀`dxf-review-preview-error-selection`的hit-index scenarios。
- **Group 6開始前**：讀design D8、archived `optimize-dxf-source-exclusion-workflow/benchmark-results.md`及current Y05／Y29 fixture tests；效能assertion使用work-count，不使用固定秒數。
- **Group 7開始前**：回讀proposal In／Out of Scope、完整delta spec與design Architecture Alignment／Backward Compatibility；確認沒有引入pending restore、persistence migration、background worker、incremental recognition或Solver變更。

## 1. 固定共用 replay baseline 與現況特徵

- [x] 1.1 讀取已封存`stabilize-corner-brace-repair-reference-identity`的最終verification證據並固定等價baseline；記錄其最終`source_exclusion.py`／`corner_brace_repair.py`行為，驗證本change不新增reference matcher或修改stable identity規則。
- [x] 1.2 執行`tests.test_dxf_source_exclusion`、`tests.test_dxf_source_exclusion_fixture_regression`、`tests.test_dxf_review_workflow`及`tests.test_dxf_review_layout`，記錄實作前通過基線或既有失敗，讓後續回歸可歸因於本change。
- [x] 1.3 在`tests/test_dxf_source_exclusion.py`補現行single-item planner／commit characterization，鎖定normalized exclusions、manual replay、revision increment、rollback及single restore輸出，驗證後續重用canonical path不改工程結果。

## 2. 建立 Workflow-owned pending draft

- [x] 2.1 在`dxf_import/review_workflow.py`加入immutable pending draft／snapshot，包含`base_revision`、`source_fingerprint`、`generation`與normalized `ExcludedSource` tuple；以unit tests驗證初始empty、snapshot不可反向修改Workflow及mark不增加正式Review revision。
- [x] 2.2 實作單筆mark command，重用現有ReviewItem eligibility、`excluded_source_from_review_item()`、canonical identity與shared-handle檢查；以tests驗證合法來源加入、正式excluded／不存在／角色不符／shared-handle conflict拒絕且不執行`DXFImporter.convert()`。
- [x] 2.3 實作unmark與discard commands，每次有效變更增加draft generation並以`normalize_excluded_sources()`去重排序；以tests驗證取消一筆保留其餘項目、取消最後一筆回到empty、no-op不改generation或正式state。
- [x] 2.4 加入paired BIM Joist source-atomic pending tests，驗證依序mark兩個sibling只形成一筆shared-root decision，任何一個sibling unmark都以同一canonical identity處理，且不得拆成半套assembly。
- [x] 2.5 實作draft base revision／source fingerprint stale判定，禁止自動rebase或改選來源；以tests直接改變revision／fingerprint後驗證apply拒絕、draft標示`STALE`、只有explicit discard可清除且committed state不變。

## 3. Pending期間的操作 gate 與 session lifecycle

- [x] 3.1 在`DXFReviewWorkflow`加入共用pending-mutation guard，盤點manual repair、confirmation、coordinate、layer-role recognition、double-support／column decisions、正式restore、Pause及Complete相關commands；以parameterized tests驗證pending非空時全部拒絕、empty時沿用既有行為。
- [x] 3.2 驗證selection、inspection、filter所需read-only snapshot及Presentation-only zoom／pan不觸發guard、不改revision且保留draft；在`tests/test_dxf_review_layout.py`與Workflow tests覆蓋允許清單。
- [x] 3.3 確認`to_review_state()`、Pause outcome、Project payload與resume cache不序列化pending；以round-trip tests驗證pending存在時serialization內容仍只有committed `excluded_sources`，且Project／Review schema版本不變。
- [x] 3.4 保留draft empty時的既有single restore path，draft active時由共用guard拒絕restore；以tests比較restore前後manual override、impact、revision與persistence結果，確認未新增pending／batch restore。

## 4. 一次 canonical staging 與原子提交

- [x] 4.1 新增pending apply planner，將committed `excluded_sources`與draft sources正規化成單一candidate set，並恰好呼叫一次既有`plan_source_exclusion_change()`；以spies驗證N筆mark期間convert／replay皆0次、一次apply時convert／replay各1次。
- [x] 4.2 擴充`SourceExclusionPlan`或等價token保存draft generation與pending identities，同時保持既有single restore plan相容；以tests驗證impact顯示後mark／unmark、revision或fingerprint改變都使commit stale且不修改live state。
- [x] 4.3 以final plan建立aggregate impact資料，涵蓋pending來源摘要、members、warning、error／critical、`preserved`／`needs_review`／`disabled`及confirmation invalidations；輸出須包含「以下為所有待排除來源合併後的結果」及「若結果不如預期，可取消個別待排除後重新套用」；以headless formatter tests驗證兩段說明存在，且資料全部來自同一份staged result而非逐筆中間結果。
- [x] 4.4 將pending plan commit整合到既有`commit_source_exclusion_plan()`atomic adoption，成功只增加一次Review revision並以不可失敗的plain assignment清draft；以failure injection驗證adoption任一步驟失敗時完整rollback且draft保留。
- [x] 4.5 補recognition、manual replay、problem／ReviewItem、confirmation、candidate store與aggregate impact建立失敗tests，逐欄比較正式snapshot完全不變、draft可重試且Project dirty不變。
- [x] 4.6 補使用者取消aggregate impact測試，驗證plan丟棄但draft保留；再次apply必須建立新plan一次，不得提交已取消或已stale plan。

## 5. Dialog控制、pending投影與關閉行為

- [x] 5.1 在`dxf_import/dialog.py`將主視窗「修改工具 → 來源」入口改為「標記待排除／取消待排除」，並在Preview「目前選取」工具列新增相同入口；兩者只讀取Workflow同一份draft／action-state snapshot。於`tests/test_dxf_review_layout.py`補layout tests，驗證兩個按鈕位於指定父區塊、依同一選取與pending狀態同步切換文字／enabled state，且Preview不出現第二套apply／discard controls。
- [x] 5.2 在主視窗來源排除區新增待排除清單，逐筆顯示構件ID與來源，並在清單下方依序放置「重新辨識並套用（N）」與「捨棄待排除」；以layout tests驗證empty／active／stale／planning時的清單可見性、欄位、按鈕上下順序、文字、count及enabled state，並驗證Dialog不持有第二份可修改pending collection。
- [x] 5.3 串接待排除清單互動與Preview overlay：點擊清單列沿用既有selection／location path定位構件，每列取消操作只unmark該canonical identity；mark／unmark只刷新兩個入口、清單、count、相關source style與action state。以Dialog interaction與render tests驗證主視窗或Preview任一入口操作後另一入口立即同步、單筆取消保留其餘draft、點擊列可定位、pending來源仍可依committed hit index選取、不移除formal members，且unsafe scene index fallback不執行recognition。
- [x] 5.4 串接位於待排除清單下方的「重新辨識並套用（N）」與「捨棄待排除」互動：防止re-entry、顯示planning狀態、建立一次plan；aggregate impact須顯示「以下為所有待排除來源合併後的結果」並提示「若結果不如預期，可取消個別待排除後重新套用」；確認後提交同一plan，取消後保留draft並允許取消個別待排除再重新套用，捨棄則清空draft但不改committed truth。以Dialog interaction tests覆蓋success／discard／cancel-and-unmark／reapply／stale／planning exception及雙視窗狀態同步。
- [x] 5.5 成功commit後沿用`ReviewMutationEffects`更新正式excluded style、members、problems、selection與hit index並保留viewport，且清除全部pending overlay／count；以partial-vs-full refresh tests驗證語意等價及舊hit target不再命中。
- [x] 5.6 Pending非空時，將被共用action gate擋下的主視窗與Preview按鈕設為disabled，並以tooltip顯示「請先套用或捨棄待排除來源」；對Pause／Complete沿用相同提示，window close提供「捨棄並關閉／取消關閉」且不自動recognize。以layout／interaction tests驗證所有受gate控制的按鈕狀態與tooltip精確文字、draft清空後恢復、取消關閉保留視窗與draft，且明確捨棄才沿用既有close path。
- [x] 5.7 驗證hidden developer debug在mark／unmark與commit時不序列化；打開debug時formal payload只反映committed revision，若顯示pending則放在明確uncommitted區段，且不進入`DXFImportResult.to_debug_dict()`或persistence。

## 6. 多來源工程回歸與效能證據

- [x] 6.1 在`tests/test_dxf_source_exclusion_fixture_regression.py`加入Y05至少兩筆可安全排除來源的multi-pending case，將一次apply結果與直接對相同final exclusion set執行canonical planner比較，驗證members、connections、messages、repair provenance、stable references、problems、ReviewItems、confirmations、completion truth與replay report完全等價。
- [x] 6.2 擴充Y05 paired Joist／CornerBrace scenarios，驗證source-atomic deduplication、secondary-reference dependency pass及`preserved`／`needs_review`／`disabled`不因pending合併而改變；執行整個fixture regression module通過。
- [x] 6.3 使用Y29 legacy source驗證multi-pending、正式single restore、manual Waler override、persistence round trip與Preview selection，確認功能沒有只對Y05或CornerBrace特例化。
- [x] 6.4 加入deterministic work-count tests：N筆mark／unmark為0次recognition／replay，一次apply為1次full recognition、1次manual replay、1次final problem／ReviewItem projection及1次revision increment，hidden debug為0次serialization。
- [x] 6.5 更新`tools/benchmark_dxf_source_exclusion.py`或新增同工具內multi-pending模式，記錄N次single flow與一次multi-pending flow的convert、replay、commit、refresh及wall-clock；執行Y05／Y29一次並保存觀測結果，但不得建立固定秒數CI門檻。
- [x] 6.6 執行`tests.test_dxf_module_boundaries`與dependency tests，驗證`review_workflow.py`未依賴Tk／Dialog／`RenderDirty`，recognition／source_exclusion modules未依賴pending Presentation state。

## 7. 文件、完整回歸與OpenSpec驗證

- [x] 7.1 在功能及focused tests通過後更新`docs/WORKFLOW.md`的DXF Source Exclusion lifecycle，記錄pending intent、一次canonical staging、aggregate impact、action gate、atomic commit與non-persistence；確認未把background worker、incremental recognition或pending restore寫成已成立行為。
- [x] 7.2 執行focused regression：`tests.test_dxf_source_exclusion`、`tests.test_dxf_source_exclusion_fixture_regression`、`tests.test_dxf_review_workflow`、`tests.test_dxf_review_layout`、`tests.test_dxf_review_items`、`tests.test_dxf_corner_brace_repair`、`tests.test_dxf_bim_joist_recognition`與`tests.test_dxf_module_boundaries`，修正本change造成的失敗且不得降低assertion或工程門檻。
- [x] 7.3 執行`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`完整suite，確認Project persistence、Pause／Resume、relink、DXF export、Domain與Solver無回歸；回報與本change無關的既有失敗，不擴張scope處理。
- [x] 7.4 逐項對照proposal In／Out of Scope、delta spec scenarios與design Decisions，執行`openspec validate stage-multiple-dxf-source-exclusions --strict`及`$openspec-verify-change stage-multiple-dxf-source-exclusions`，確認所有requirements有測試證據且無未說明限制後才建議archive。
