# Design：以圍令正式化修補工具採用工程線

## 閱讀導航

- **P0／現在必讀**：D1「修改工具擁有唯一正式化入口」、D2「工具保存未提交來源與點位選擇」及D3「按採用才plan＋commit」；三者決定UI boundary與transaction。
- **P0／現在必讀**：D4「input kind由工具來源決定」與 D6「W14可由P01／P02直接採用」；它們解決CAD contract及自動目前線的人工採用語意。
- **P1／實作前閱讀**：D5「一般候選點與Preview維持generic flow」及 D7「失敗與重新採用保持零mutation」；修改`dxf_import/dialog.py`及layout tests前需理解。
- **P2／需要時再讀**：「相容性與persistence」、「風險與取捨」及「Rejected alternatives」。可先跳過recognition、寬度／材料、Pause／Resume、Solver及export；本change不修改那些模組。

## 方案摘要

```text
DXF Review選取repair-eligible Waler
  -> 修改工具顯示「圍令正式化」
  -> 開啟專用視窗（尚未建立repair plan）
       * 線的來源預設「點位清單」
       * 點位清單預選目前selected_start／selected_end
       * 同member存在最新CAD pair時才enable「已讀取的CAD線」
       * 顯示contact-face notice
  -> 使用者取消：close，零mutation
  -> 使用者按「採用正式圍令」
       * 重新取得current workflow member並驗證target
       * 依來源直接決定manual_candidate_points／cad_manual
       * 建立既有WalerEngineeringLineRepairPlan
       * 立即commit
  -> 成功才刷新live Review
```

本 change 中：

- **圍令正式化工具**：DXF Review修改工具中的獨立入口與modal視窗；不是候選點區或Preview action。
- **未提交工具選擇**：視窗內的source mode、selected point IDs及開啟時CAD pair identity，只有UI生命週期，不包含staged result或repair plan。
- **目前線**：Workflow-owned Waler的`selected_start_point_id`／`selected_end_point_id`所代表的canonical live line。
- **正式採用**：按鈕事件內建立plan並commit，是唯一會建立或取代`manual_repair` authority的UI動作。

## 決策對照

| Decision | 影響的spec行為 | 對應tasks |
| --- | --- | --- |
| D1. 修改工具擁有唯一正式化入口 | 修補工具只對合格圍令出現 | 1.x、2.x |
| D2. 工具保存未提交來源與點位選擇 | 來源互斥、CAD availability、點位預選、取消零mutation | 1.x、2.x |
| D3. 按採用才plan＋commit | 候選點採用、重新採用、stale／failure rollback | 1.x、3.x |
| D4. input kind由工具來源決定 | CAD不需先一般套用、CAD更新要求重開、兩來源共用contract | 1.x、3.x |
| D5. 一般候選點與Preview維持generic flow | provisional只改幾何、manual formal一般套用拒絕、Preview只做幾何編輯 | 1.x、4.x |
| D6. W14可由P01／P02直接採用 | W14不改點即可直接採用 | 1.x、3.x |
| D7. 失敗與重新採用保持零mutation | 舊formal line在成功前不變 | 1.x、3.x |

## Context

動機與user-visible Before／After見`proposal.md`。目前`DXFImportDialog._apply_candidate_changes()`對repair-eligible Waler直接建立並commit repair plan，且`_update_preview_candidate_action_state()`把generic apply button改名為正式化action。這使一般geometry edit與authority裁決共用同一入口。

DXF Review已有可重用的修改工具模式：`_selected_column_repair_subject_id()`只從目前selected Review item解析唯一subject，`_update_modification_tools()`據此顯示「中間柱關聯修補」，click handler再建立plan並開啟專用視窗。圍令正式化沿用相同的selection-driven入口與視窗生命週期，但eligibility仍由`is_waler_engineering_line_repair_eligible()`判定。

`DXFReviewWorkflow.plan_waler_engineering_line_repair()`已接受member ID、start point ID、end point ID及input kind，並在commit時使用revision／fingerprint／identity guard。這代表工具不需要保存repair plan；只需在按採用時把modal選擇交給既有plan／commit boundary。

目前CAD event由`_read_cad_engineering_line()`把selected `member.id`傳給`DXFReviewWorkflow.add_cad_candidate_line()`；後者以`add_cad_candidate_points()`只更新該member的`candidate_points`。每個point帶有`component_id == member.id`，CandidatePointStore亦以member ID查詢。同member再次讀取時會先移除舊`cad_manual*` types，再加入最新start／end，因此最新CAD pair可可靠綁定目標member，不需新增全域pending CAD state或persistence欄位。

目前`_apply_candidate_changes()`會把formal／`manual_repair` Waler視為repair-eligible，直接plan並commit重新採用，而不是拒絕。D5將此現況改成明確的Presentation guard。

### W14 調查結果

以正式`assets/sample_dxf/Y29_test.dxf`執行目前辨識流程，source `58D`得到：

- member：`W14`，`contact_face_state == "provisional"`，`selection_source == "auto"`；
- current line：`world_start == P01.world_point`、`world_end == P02.world_point`；
- `selected_start_point_id == recommended_start_point_id == "P01"`；
- `selected_end_point_id == recommended_end_point_id == "P02"`；
- `selected_candidate_id == "line_1"`，而`line_1`使用同一組世界座標；
- W14共有9個candidate points，P01的`valid_for`為start、P02為end。

因此W14可由point list直接預選P01／P02，不需建立synthetic point。另以目前API實測，若直接把`selection_source == "auto"`當`input_kind`傳入repair plan會被拒絕，因既有pure operation只接受`manual_candidate_points`與`cad_manual`。工具內按採用本身就是明確人工意圖，所以不改點採用auto目前線時必須轉為`manual_candidate_points`。

## Goals / Non-Goals

**Goals:**

- 以獨立修補工具清楚隔離一般geometry edit與formal authority裁決。
- 讓第一次正式化與`manual_repair`重新採用使用同一modal、同一plan／commit transaction。
- 讓目前線端點可直接預選與採用，同時保護cancel／failure零mutation。
- 保持點位清單與已讀取CAD線的正式化validation、commit與downstream effects完全一致，且CAD不需先一般套用。
- 重用既有CandidatePointStore、repair eligibility及Workflow API，不建立第二套工程規則。

**Non-Goals:**

- 不在候選點區或Preview加入正式化action。
- 不在Presentation保存跨視窗repair plan或staged result。
- 不在工具內讀取CAD event、建立CAD線或修改一般candidate workflow。
- 不修改candidate generation、repair pure operation、diagnostic allowlist、downstream rebuild或persistence schema。

## Decisions

### D1. 修改工具擁有唯一正式化入口

在`_build_phase3_modification_tools()`加入「圍令正式化」button，並以新的selected-subject helper投影可用性。helper採取與中間柱修補相同的boundary：

1. 只看目前selected Review item；
2. item必須唯一對應目前`world_result`中的Waler；
3. Waler必須通過`is_waler_engineering_line_repair_eligible()`；
4. helper只回傳member ID，不建立plan、不執行validation mutation。

`_update_modification_tools()`只在helper回傳ID時顯示／enable button。click handler再次解析subject；selection已改變或member不再eligible時顯示說明並不開啟視窗。

原因：正式化是高意圖repair operation，與中間柱／角撐修補同屬修改工具，不應偽裝成generic apply。

Rejected alternative：在候選點區與Preview各放一個正式化button。這會產生多個入口、複雜button-state同步，並再次混淆geometry edit與authority。

### D2. 工具保存未提交來源與點位選擇

工具以一個radio variable提供互斥的「點位清單／已讀取的CAD線」，每次開啟都預設點位清單。點位清單從目前Workflow member與CandidatePointStore建立兩組選項：start list只包含`valid_for`含`start`的points，end list只包含`valid_for`含`end`的points。每列至少顯示point ID、label與WCS座標，使使用者可辨識所選位置。

modal-local variables分別保存selected start/end IDs，初值為member目前`selected_start_point_id`／`selected_end_point_id`。兩個預設ID都必須存在於對應list；否則工具顯示資料不一致並停止，不用最近點、座標猜測或live mutation補足。

CAD availability由目標member的candidate points判斷：必須能從同一member解析最新`cad_manual_start`與`cad_manual_end` provenance，兩點分別適用於start與end。「已讀取的CAD線」只在該pair完整時enable；其他member的CAD points不算。工具開啟時保存該pair的point IDs、WCS coordinates及Workflow revision作為視窗內identity snapshot；這只是stale detection資料，不是第二份CAD geometry truth。

視窗固定顯示`WALER_CONTACT_FACE_ADOPTION_NOTICE`。選擇變更只更新modal detail／可選preview overlay；不得呼叫Workflow mutation、使confirmation失效或寫入manual override。取消與window close只清除widget state。

原因：member-owned candidate points已提供可靠CAD綁定；source mode與point IDs足以在按採用時建立既有repair plan，不需要新狀態或另一份formal truth。

### D3. 按「採用正式圍令」才建立並 commit plan

apply handler在click時按以下順序執行：

1. 重新取得target Waler並確認exact member及eligibility仍有效；
2. 依D4解析所選來源；若為CAD則確認same-member pair identity仍等於開啟時snapshot；
3. 確認要採用的start／end IDs仍存在於目前CandidatePointStore且適用於對應端點；
4. 呼叫`plan_waler_engineering_line_repair()`；
5. 緊接著呼叫`commit_waler_engineering_line_repair()`；
6. 成功後關閉工具、同步snapshot、刷新完整Review projection並顯示confirmation invalidations。

不得在window open、point selection或confirmation前預先建立plan。plan與commit位於同一button handler，但Workflow仍會執行既有stale guards；任何exception都不採用staged result。

原因：對re-adoption而言，舊formal line在commit成功前持續是唯一live truth；不需要額外狀態生命週期即可符合atomic replacement。

### D4. Input kind 由工具來源直接決定

`input_kind`不再從current pair或`member.selection_source`推導，而由工具內的互斥來源直接決定：

- 「點位清單」：以工具所選start／end IDs建立`manual_candidate_points` repair plan；若維持current selected pair，可傳遞相符的既有`selected_candidate_id`，W14因此保留`line_1`。
- 「已讀取的CAD線」：以目標member最新、且與開啟時identity snapshot完全相同的CAD pair建立`cad_manual` repair plan；不要求該pair先經一般`apply_candidate_change()`成為current line。

工具不提供CAD reader。CAD event仍由既有`_read_cad_engineering_line()`寫入指定member的candidate points。若工具開啟後該member讀取新CAD線，舊markers會被最新pair取代；handler不得靜默改採新pair，也不得嘗試提交已移除的舊pair，而是於任何repair plan建立前顯示「CAD 線已更新，請重新開啟圍令正式化」並return。此拒絕不得觸發Workflow command、revision、confirmation invalidation或refresh mutation。

兩種來源最後只共用一個採用handler與按鈕；進入repair plan後使用相同pure operation、validation、commit、diagnostic replacement及downstream rebuild contract。

原因：使用者的明確來源選擇比從current line反推provenance更直接；member-owned CAD markers已足以提供可靠綁定，而要求重開可避免視窗內容在使用者不知情時改變。

### D5. 一般候選點與 Preview 維持 generic flow

`_apply_candidate_changes()`不再呼叫formalization APIs。對provisional Waler沿用既有pair validation、warning、`apply_candidate_change()`、snapshot sync與refresh，套用後仍是provisional；對formal／`manual_repair` Waler則在validation或任何Workflow mutation前拒絕，顯示「此圍令已正式化，請使用修改工具的『圍令正式化』重新採用」，並保持live Review state完全不變。automatic formal Waler及非Waler角色維持既有generic behavior，本change不擴張其規則。

主Review現有「選起點／選終點」與「套用選取點」保持不變。Preview恢復endpoint radio controls時，直接重用`candidate_pick_mode_var`、`_begin_candidate_pick()`、Esc取消及同一SelectionController；Preview仍可有generic「套用選取點／取消本次選點」，但不得加入formalization button或呼叫formalization handler。

原因：一般選點只有一份SelectionState與一套mutation路徑；正式化由修改工具另行啟動。

### D6. W14 以現有 P01／P02 完成 direct-adoption regression

新增fixture test以現行Y29辨識結果鎖定：

1. W14 source `58D`的current endpoints精確對應P01／P02；
2. 工具model／UI預設P01／P02；
3. 不變更選擇按採用時，handler把`auto`明確轉成`manual_candidate_points`並保留`selected_candidate_id == "line_1"`；
4. plan／commit成功後W14為`formal`／`manual_repair`，採用線座標不變；
5. source `58D`允許清除的envelope／contact-face blocker被取代，Y29其他blockers仍保留，`can_import`依完整Review facts決定。

這個test同時證明正常auto provisional Waler不需要synthetic default points。

### D7. Cancel、failure 與 re-adoption 共用零 mutation boundary

- 開啟／改選／取消：沒有Workflow command，live state byte-for-byte不變。
- plan失敗：工具可保留開啟以讓使用者修正，但不得更新live snapshot。
- CAD pair在工具開啟後更新：顯示「CAD 線已更新，請重新開啟圍令正式化」並停止；不得plan、commit或refresh mutation。
- commit stale／failure：丟棄staged result；provisional維持原暫定線，manual formal維持舊formal line與authority。
- success：只有existing Workflow mutation outcome可使confirmation失效並觸發refresh。

測試對provisional及manual re-adoption都比較操作前後完整Workflow snapshot／revision／override／diagnostics。工具不提供「撤銷正式化」；重新採用成功後仍由新decision原子取代舊decision。

## Architecture Alignment

本change沿用既有Architecture，不修改layer或dependency direction：

```text
DXFImportDialog repair tool (uncommitted source / point selection)
                ↓ click adopt
DXFReviewWorkflow (plan / atomic commit / live Review owner)
                ↓
existing repair validation and pure operation
                ↓
DXF models / geometry
```

- **Presentation**：擁有button visibility、modal widgets、未提交source／point IDs及開啟時CAD identity snapshot；不擁有repair plan result或正式CAD geometry truth。
- **DXFReviewWorkflow**：繼續擁有live WCS／projected result、revision、manual authority與atomic commit。
- **Pure operations／models**：不變。

single source of truth仍是`DXFReviewWorkflow`。modal point IDs只是使用者intent，按採用時必須回到Workflow current state重新驗證；Dialog不得渲染或保存plan內的staged result作為第二份live truth。

## 相容性與 persistence

- 不變更Project schema、paused Review schema、`manual_overrides`或`waler_engineering_line_formalized`。
- 已保存的provisional／manual formal Waler載入後仍由既有Workflow重建；只改正式化UI入口。
- 既有automatic formal Waler、Strut、Brace candidate edit保持generic apply。
- 既有manual Waler重新採用的最終commit payload不變，Presentation不保存repair plan。
- 不需要資料migration或feature flag；回滾UI不影響已持久化authority。

## 風險與取捨

- **[Risk]** current selected point IDs不在point list。→ 開啟工具時精確驗證並阻擋，不以最近點猜測；W14 fixture鎖定正常auto案例可解析。
- **[Risk]** `auto`直接傳入repair plan被拒絕。→ tool adoption明確映射為`manual_candidate_points`，並以W14 integration test驗證。
- **[Risk]** CAD來源錯用其他member或舊線。→ 只從目標member解析最新CAD markers；開啟後identity不同即以固定訊息拒絕並要求重開。
- **[Risk]** 開啟工具後Review state改變。→ click時重新取得target與points；CAD identity先行比對，其他變更再由existing plan／commit revision guards裁決。
- **[Trade-off]** 工具不直接畫新的完整staged Review結果。→ 避免第二份truth；point detail及可選temporary overlay提供定位辨識，正式downstream projection只在commit後出現。
- **[Risk]** Preview恢復endpoint controls使toolbar過寬。→ 使用緊湊radio controls並保留目前instruction獨立行，不重排整個Dialog。

## Migration Plan

1. 先以測試固定修改工具eligibility、modal point defaults、cancel／failure零mutation與W14 P01／P02 direct adoption。
2. 加入工具入口與modal，click-time重用既有repair plan／commit。
3. 移除candidate apply中的formalization branch，恢復／驗證Preview generic endpoint controls。
4. 加入CAD source availability、免一般套用、更新後要求重開、manual re-adoption及共用contract regression。
5. 執行focused及完整DXF／boundary tests，完成後更新`docs/WORKFLOW.md`的工具入口說明。

Rollback不需資料轉換；移除新工具並恢復舊UI routing即可，既有persisted manual authority仍相容。
