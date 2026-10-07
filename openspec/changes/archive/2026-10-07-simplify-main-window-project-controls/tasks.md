# Tasks

## 實作前閱讀

- **Group 1開始前**：讀[proposal.md](./proposal.md)「現況與目標／不變事項」、[design.md](./design.md) Context，以及`main-window-project-controls`「主視窗專案操作必須集中於選單列」；先固定現行menu、toolbar、title與guard測試基線。
- **Group 2開始前**：讀`main-window-project-controls`「Open必須使用Project單選視窗」、`unsaved-changes-navigation-guard`修改後的「Open目標取消或缺失不得改變目前Project」及design D2；必須維持target-before-guard。
- **Group 3開始前**：讀`main-window-project-controls`「File選單與快捷鍵必須使用相同命令」、design D1／D6及`software-information-presentation`「可從主視窗開啟軟體資訊」；Save／Save As採方案A，必須先通過共用active-editor completion gate，menu與shortcut不得建立第二套workflow或使用`bind_all`。
- **Group 4開始前**：讀`main-window-project-controls`「Project選單必須投影目前專案狀態」、「視窗標題必須成為目前Project的精簡狀態來源」、「完整重新投影入口只在stale時顯示」，以及design D3／D4／Single Source of Truth。Project label必須以完整`DxfStatus` allowlist區分普通、`待儲存`與`⚠`，不得依賴dirty或反向排除推導。
- **Group 5開始前**：讀`main-window-project-controls`「刪除目前專案必須明確且安全」、design D5及`project-state-transaction-consistency`的projection failure Requirement；Delete必須重用New的同一mutation guard，不得先reset再刪filesystem，也不得在成功後保留deleted path。
- **Group 6開始前**：回讀proposal In／Out of Scope、完整delta specs、design Backward Compatibility／Migration Plan；確認所有次分頁、下方`context_toolbar`、Preview toolbar、Project schema、DXF workflow、Domain與Solver皆未改變。

## 1. 固定現行 Presentation 與 transaction 基線

- [x] 1.1 執行`tests.test_project_navigation_guard`、`tests.test_project_state_transactions`與`tests.test_software_information`，記錄實作前通過基線或既有失敗；完成條件是後續可區分本change造成的regression。（實作前基線：62 tests passed。）
- [x] 1.2 在既有Presentation tests補必要characterization，鎖定window title的Project name／dirty `*`、Help menu獨立於Project狀態、Open只在有效target後進guard，以及完整重新投影的success／failure semantics；以相關focused tests通過驗證，不改正式行為。
- [x] 1.3 盤點`main.py`中`project_case_var`、`project_case_selector`、`open_project_button`、`reproject_button`與`project_quick_status_var`的所有讀寫點，將每個call site對應到本change的Dialog或menu projection task；驗證不得把下方`context_toolbar`或Preview toolbar誤列為移除目標。
- [x] 1.4 完成真實Tk事件characterization：顯示中的menu Save callback執行時focus仍為Entry，未觸發FocusOut，Save看到舊model值且pending editor仍存在；root-scoped`Ctrl+S`在Entry內執行時同樣不觸發FocusOut。結果已記錄於design D6，未修改production code。

## 2. 建立 Project 單選視窗與 Open target 流程

- [x] 2.1 在`bracing_optimizer/presentation/dialogs/`新增UI-only Project selection Dialog，接收不可變names及optional current name，提供single selection、Open／Cancel、Enter、Escape與double-click；以headless widget tests驗證empty、initial selection、disabled Open、confirm及cancel回傳值，且Dialog不讀filesystem或呼叫load／guard。
- [x] 2.2 將Main Open入口改為每次取得既有managed／legacy Project names後開啟Dialog，並在Dialog回傳後、dirty guard前重新驗證target；更新`tests/test_project_navigation_guard.py`驗證valid target、cancel、empty repository、no selection及target race都遵守target-before-guard。
- [x] 2.3 保留既有Save／Discard／Cancel與load continuation，補clean、save success、discard、cancel、Save As cancel及save failure的Dialog-driven Open regressions；完成條件是只有`NavigationGuardOutcome.PROCEED`載入一次已固定目標，其他case完整保留目前snapshot。

## 3. 重組主選單與鍵盤快捷鍵

- [x] 3.1 重構`main.py`主選單建構，只建立File／Project／Help menus，不建立頂部Project toolbar；以menu wiring tests驗證固定順序、separators、command labels與handlers，並驗證`context_toolbar`、Preview toolbar及全部既有tab labels仍被建立且名稱不變。
- [x] 3.2 將DXF relink、Project／DXF status及delete-current移至Project menu，保留「說明 → 軟體資訊」既有handler；更新`tests/test_software_information.py`與menu tests，驗證Help在無Project、dirty或DXF warning下仍可開啟且不修改Project。
- [x] 3.3 為`Ctrl+N`、`Ctrl+O`、`Ctrl+S`及`Ctrl+Shift+S`建立root-scoped bindings與menu accelerator文字，所有入口共用相同handlers並回傳`"break"`；不得使用`bind_all`，以event/wrapper tests驗證shortcut不繞過menu state、navigation guard或save outcome。
- [x] 3.4 實作design D6方案A的共用active-editor completion gate，讓Save／Save As在建立payload、開啟命名流程或呼叫persistence前，先沿用`_finish_edit()`相同的解析、validation、必要確認、commit與post-processing規則；成功或no-op才關閉editor並繼續，失敗則顯示既有提示、保留editor／pending文字並abort。新增測試驗證：合法未確認值會進入本次saved payload；不合法值不呼叫Save／Save As persistence、檔案與dirty snapshot不變且editor保留；成功edit後Save As取消仍保留model值與dirty；選單Save／Save As與`Ctrl+S`／`Ctrl+Shift+S`結果一致。
- [x] 3.5 新增focus-scope tests：主視窗一般widget及inline editor取得focus時快捷鍵可進入共用handler；DXF Review、Support／Waler Solver及代表性child `Toplevel`取得focus時，四個快捷鍵均不得觸發主視窗New／Open／Save／Save As，也不得攔截子視窗既有按鍵行為；另以binding inspection確認沒有`bind_all`。
- [x] 3.6 在900×600、1024×768與最大化尺寸啟動主視窗進行layout smoke test，驗證頂部Project toolbar確實不占高度、選單可操作、主要工作區未被遮蔽，且次分頁名稱維持原值；保存測試紀錄但不新增與本change無關的視覺主題調整。（Windows Tk smoke：passed。）

## 4. 投影 Project title、DXF warning 與 conditional recovery

- [x] 4.1 移除`project_quick_status_var`依賴，保留`_update_window_title()`以`current_project_path`／`project_dirty`投影已命名、未命名、clean與dirty caption；新增title tests驗證Save、Save As、Open、New及dirty transition後沒有第二份常駐快速狀態。
- [x] 4.2 實作D3的三類Project top-level label projection：8-state warning allowlist顯示「專案 ⚠」；`RUNTIME_READY`／`VERIFIED_PENDING_SAVE`顯示「專案 待儲存」；`READY`／`NO_DXF`／無report顯示「專案」。以涵蓋全部enum值的parameterized tests固定mapping，另明確測試`RUNTIME_READY + dirty=False`與`VERIFIED_PENDING_SAVE + dirty=False`仍顯示「專案 待儲存」，且dirty變化不改變status-derived label。
- [x] 4.3 實作File／Project command state projection，使delete只對有效current path啟用，`projection_stale`時停用既有mutation commands但保留status、Help、Exit與recovery；以menu state tests驗證state只由正式runtime fields派生。
- [x] 4.4 將`_refresh_projection_guard_ui()`改接conditional menu projection：clean時無「⚠ 重新整理畫面」，stale時在Project與Help之間出現一次，成功後移除，失敗後保留；更新`tests/test_project_state_transactions.py`覆蓋dynamic insertion／removal、no-duplicate及formal state不變。

## 5. 將刪除入口限定為目前 Project

- [x] 5.1 重用既有managed／legacy path containment檢查，讓delete target只來自`current_project_path`；以tests驗證未命名、repository外path、錯誤managed shape與不存在target都不可執行，且不得fallback到第一筆Project或Dialog selection。
- [x] 5.2 讓delete在任何filesystem mutation前直接呼叫New使用的同一`_ensure_mutation_allowed()`；以parameterized tests驗證`cad_ack_unresolved_event_id`與`projection_stale`都使New／Delete一致被拒絕且filesystem／runtime零變更，並以non-regression cases確認Solver operation執行中與`dxf_dialog_active=True`不會被Delete自行新增為guard條件。
- [x] 5.3 建立完整blank Project runtime outcome preparation，將default inventory、empty results／caches、`DxfWorkflowStatus.NONE`、blank DXF report、`current_project_path=None`及clean state在filesystem刪除前準備完成；以unit tests驗證準備失敗時不刪檔也不修改runtime。
- [x] 5.4 更新delete confirmation顯示Project名稱、path、managed DXF、dirty狀態與不可復原警告；以tests驗證取消時filesystem與完整runtime snapshot零變更，且dirty Project不會隱含執行Save。
- [x] 5.5 依design D5完成filesystem-first、runtime-commit-second流程；以managed directory與legacy JSON tests驗證guard拒絕或刪除失敗時保留目前Project／path，成功只刪正確target並採用未命名clean新Project。
- [x] 5.6 加入delete成功後UI projection failure injection，驗證正式runtime仍為blank unnamed clean、deleted path不會恢復、`projection_stale`與recovery command生效，且完整重新投影成功後畫面一致。

## 6. 移除舊selector投影、更新文件並完整驗證

- [x] 6.1 移除只服務頂部Project toolbar的selector／button／quick-status更新分支與過時tests，保留repository listing、path解析及既有handler contract；以`rg`與focused tests確認沒有production code再依賴已移除widgets，且未順便重構無關`main.py`責任。
- [x] 6.2 實作完成且focused tests通過後，更新`docs/WORKFLOW.md`的Open target selection與`projection_stale` recovery入口描述，明確記錄Dialog selection、target-before-guard及conditional menu command；確認Architecture、Domain與Solver文件無需修改。
- [x] 6.3 執行focused regression：`tests.test_project_navigation_guard`、`tests.test_project_state_transactions`、`tests.test_software_information`、`tests.test_project_persistence`及新增Project selection/menu tests；修正本change造成的失敗且不得降低assertion。（161 tests passed；sandbox中1個真實Tk layout smoke因Tcl unavailable跳過，已另於Windows Tk環境通過。）
- [x] 6.4 執行`tests.test_application_domain_boundaries`，驗證新增Dialog與menu projection只位於Presentation，Application／Domain／Algorithms未新增Tkinter依賴。（10 tests passed。）
- [x] 6.5 執行`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`完整suite，確認Project persistence、DXF lifecycle、CAD、results、Domain與Solver無回歸；回報與本change無關的既有失敗，不擴張scope處理。（首次執行有1個packaged release project載入的非決定性error，單獨重跑通過；完整低輸出重跑為1787 tests passed、2 skipped。）
- [x] 6.6 逐項對照proposal In／Out of Scope、兩份delta specs與design Decisions，執行`openspec validate simplify-main-window-project-controls --strict`及`$openspec-verify-change simplify-main-window-project-controls`，確認implementation與文件一致後才建議archive。（8 requirements／35 scenarios均有implementation與tests evidence；strict validation passed，無critical、warning或suggestion。）
