# Tasks

## 實作前閱讀

- **Task Group 1**：讀`proposal.md`的「現況與目標／主要流程」、delta spec全文，以及`design.md` D1～D7；先以測試固定工具入口、source radio、point defaults、same-member CAD availability、click-time commit與zero-mutation boundaries。
- **Task Group 2**：讀`design.md` D1、D2及spec的「修補工具只對合格圍令出現」「工具選擇線的來源」「沒有同member CAD線時停用選項」「預覽與確認說明接觸面語意」scenarios；比照中間柱關聯修補的selection-driven入口，但不複製其工程選項邏輯。
- **Task Group 3**：讀`design.md` D3、D4、D6、D7及spec的candidate／CAD／CAD更新／W14／re-adoption／failure scenarios；只重用既有Waler repair plan／commit，不修改pure engineering rules。
- **Task Group 4**：讀`design.md` D5及spec的「一般確認不得正式化」「已正式化Waler的一般套用被拒絕」「Preview選點仍是一般幾何編輯」scenarios；確認主Review與Preview的generic selection邊界。
- **Task Group 5**：讀`proposal.md`「不變事項／Out of Scope」、完整delta spec及`design.md` Architecture Alignment；確認沒有擴張到recognition、材料、Solver或persistence。

## 1. 先建立修補工具行為契約測試

- [x] 1.1 在`tests/test_dxf_review_layout.py`加入修改工具入口測試：`_build_phase3_modification_tools()`包含「圍令正式化」，selected-subject helper只對唯一repair-eligible provisional／`manual_repair` Waler回傳ID，automatic formal Waler、其他角色、無member與不唯一subject皆不顯示；以單獨執行該測試模組確認舊版失敗。（驗證：修補工具只對合格圍令出現；D1）
- [x] 1.2 加入modal layout／controller tests：線來源radio互斥且預設點位清單、工具只有一個「採用正式圍令」、point list依`valid_for`分成start／end options並預設current selected IDs、顯示完整`WALER_CONTACT_FACE_ADOPTION_NOTICE`；open、切換、改選、取消及window close皆不呼叫plan／commit或改變Workflow state。（驗證：工具選擇線的來源、工具預選目前線端點、contact-face notice、取消零mutation；D2）
- [x] 1.3 將現有repairable Waler generic apply直接plan／commit測試改為新contract：provisional Waler的一般`_apply_candidate_changes()`只呼叫`apply_candidate_change()`且仍無authority；formal／`manual_repair` Waler在任何Workflow call前被拒絕、提示改用修改工具，並比較完整state不變。（驗證：一般確認不得正式化、已正式化Waler的一般套用被拒絕；D5）
- [x] 1.4 以Y29 fixture新增W14 regression：確認source `58D`的current start／end精確對應P01／P02、工具預選該pair、不改點採用時把`auto`轉為`manual_candidate_points`並保留`selected_candidate_id == "line_1"`；commit後座標不變、W14為`formal`／`manual_repair`、允許清除的58D blocker被取代且其他Y29 blockers仍在。（驗證：W14不改點即可直接採用；D6）
- [x] 1.5 新增CAD source tests：CAD選項只在目標member具有完整最新CAD pair時enable，其他member CAD線不得誤啟用；不先按一般套用，選CAD來源後單一採用handler以`cad_manual`完成與點位清單相同的eligibility、validation、commit、診斷取代及downstream rebuild。（驗證：以CAD工程線正式採用、沒有同member CAD線時停用選項；D2、D4）
- [x] 1.6 新增CAD stale-window test：工具開啟並snapshot同member CAD pair後再讀取新CAD線，舊視窗採用必須顯示「CAD 線已更新，請重新開啟圍令正式化」，不得呼叫plan／commit，且完整live Review state不變；重新開啟後才可看到並採用最新pair。（驗證：工具開啟後CAD線更新；D4、D7）
- [x] 1.7 新增provisional與manual re-adoption rollback tests：invalid pair、target變更、stale revision／fingerprint、plan失敗、commit失敗均保持完整live snapshot／revision／override／confirmation／diagnostics不變；另驗證manual Waler選同member CAD來源時舊formal line維持到`cad_manual` commit成功才被原子取代。（驗證：重新採用、已正式化Waler改用CAD線、Stale或不合法修補不改變狀態；D7）

## 2. 建立圍令正式化修改工具

- [x] 2.1 在`dxf_import/dialog.py`加入selected Waler formalization subject helper與「圍令正式化」button，依`_update_modification_tools()`比照中間柱修補的show／hide方式投影目前selection；helper只解析subject與既有eligibility，不建立plan，以1.1測試驗證。（驗證：唯一修改工具入口；D1）
- [x] 2.2 實作專用modal：固定綁定開啟時的target Waler ID，加入預設點位清單的source radio；從目前CandidatePointStore建立start／end rows並顯示ID、label及WCS座標、預選current selected IDs；任一預設ID無法解析時顯示可理解錯誤且不猜最近點，以1.2及W14測試驗證。（驗證：來源互斥、point list與目前線預設；D2、D6）
- [x] 2.3 由目標member的`cad_manual_start／end` provenance解析最新CAD pair，只有完整pair才enable CAD source，並保存開啟時IDs、WCS coordinates及revision作stale identity；不得讀取CAD event或接受其他member pair，以1.5、1.6測試驗證。（驗證：same-member CAD availability；D2、D4）
- [x] 2.4 在modal顯示完整接觸面提示，只提供一個「採用正式圍令」及「取消」；source／point selection只更新local variables／可選temporary overlay，close cleanup不得接觸Workflow mutation，以1.2測試驗證。（驗證：未提交工具state與Review truth分離；D2）

## 3. 串接 click-time repair plan 與原子提交

- [x] 3.1 在唯一採用handler重新取得current target與CandidatePointStore；點位來源驗證所選IDs，CAD來源先比對same-member pair identity，確認後才建立`WalerEngineeringLineRepairPlan`並立即commit；成功後關閉工具、刷新完整Review projection及顯示confirmation invalidations，以1.2、1.5測試驗證。（驗證：按採用才plan＋commit；D3）
- [x] 3.2 依source radio直接決定input kind：點位清單固定`manual_candidate_points`，CAD固定`cad_manual`且直接使用最新已讀取pair、不要求一般套用；W14維持current pair時保留相符`line_1`，其他改選不得誤帶舊candidate identity，以W14及CAD tests驗證。（驗證：auto直接採用、CAD contract；D4、D6）
- [x] 3.3 在任何plan前處理CAD identity mismatch：顯示精確訊息「CAD 線已更新，請重新開啟圍令正式化」並停止，不自動切換來源或線、不得sync／refresh／invalidate confirmation，以1.6驗證完整live state不變。（驗證：CAD更新要求重開；D4、D7）
- [x] 3.4 統一plan／commit exception處理：cancel不執行handler，failure保留工具供修正但不採用staged state；manual re-adoption不得先降回provisional或改寫舊formal line，以1.7及既有Workflow atomicity tests驗證。（驗證：zero-mutation rollback；D7）

## 4. 恢復一般候選點流程並限制 Preview 責任

- [x] 4.1 將`_apply_candidate_changes()`中的Waler formalization branch移除：provisional Waler只走既有generic pair validation、warning、`apply_candidate_change()`、snapshot sync與refresh且仍無`manual_repair` authority；formal／`manual_repair` Waler在validation及任何mutation前拒絕並提示改用修改工具，automatic formal Waler與其他角色維持既有行為，以1.3及既有candidate tests驗證。（驗證：一般套用邊界與拒絕零mutation；D5）
- [x] 4.2 在Preview恢復「選起點／選終點」radio controls時直接重用`candidate_pick_mode_var`、`_begin_candidate_pick()`與同一SelectionController；保留generic「套用選取點／取消本次選點」，並以layout source assertions確認Preview與候選點區都沒有正式化button或handler。（驗證：Preview選點仍是一般幾何編輯；D5）
- [x] 4.3 調整CAD讀取提示：對repair-eligible Waler明確指示可直接開啟修改工具並選「已讀取的CAD線」，不再要求先按「套用選取點」；確認CAD reader只更新目標member candidate points、不建立formal authority，以1.5測試驗證。（驗證：工具不另提供CAD讀取；D4、D5）

## 5. 文件與最終驗證

- [x] 5.1 執行focused regression：`.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_layout tests.test_dxf_review_workflow tests.test_dxf_waler_engineering_line_repair tests.test_dxf_input -v`，修正本change造成的失敗且不得刪除測試或降低assertion。（驗證：工具UI、Workflow atomicity、W14與repair工程contract）
- [x] 5.2 實作完成後更新`docs/WORKFLOW.md`「Provisional Waler人工正式化」：正式入口為修改工具、來源由radio決定、CAD讀取後不需一般套用、manual formal Waler一般套用拒絕、click採用才commit；確認`docs/ARCHITECTURE.md`、`docs/DOMAIN.md`與`docs/SOLVER.md`不需修改。（驗證：long-term Workflow truth與實作一致）
- [x] 5.3 執行DXF完整回歸與boundary tests：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_dxf*.py" -v`及`.\.venv\Scripts\python.exe -m unittest tests.test_application_domain_boundaries -v`（若實際boundary模組名稱不同，使用repository既有對應模組並記錄），確認零失敗且Presentation → Workflow依賴方向未變。（驗證：無DXF／架構回歸）
- [x] 5.4 執行`openspec validate separate-waler-positioning-from-formal-adoption --strict`，再使用`$openspec-verify-change`逐項對照proposal scope、delta spec scenarios、design decisions及tasks；只有行為、測試與文件全部一致時才標記change完成。（驗證：OpenSpec implementation verification）
