# Proposal：以圍令正式化修補工具採用工程線

## 閱讀導航

- **P0／現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認正式化只存在於「修改工具 → 圍令正式化」。
- **P0／現在必讀**：`openspec/specs/dxf-waler-engineering-line-repair/spec.md` 的「人工修補必須是明確且合格的操作」，尤其是一般候選編輯不得正式化、CAD 與候選點共用正式化 contract，以及相同暫定線也可採用的 scenarios。
- **P0／現在必讀**：本 change 的 delta spec；它定義修補工具的 eligibility、點位預設、採用與 rollback 行為。
- **P1／實作前閱讀**：`design.md` 的 D1～D6，以及 `dxf_import/dialog.py` 的修改工具顯示、CandidatePointStore、現有 Waler repair plan／commit 與中間柱關聯修補視窗模式。
- **P2／需要時再讀**：修改 Workflow transaction 時再讀 `docs/WORKFLOW.md` 的 Provisional Waler 人工正式化區段。可先跳過 Solver、材料、寬度、Global Waler、Project persistence 與 export specs；本 change 不修改那些行為。

## 快速摘要

- 目前 eligible Waler 的「套用選取點」被改成直接正式化，混淆了一般幾何調整與正式工程裁決。
- 一般候選點流程恢復原語意：「選起點／選終點」及「套用選取點」只更新幾何，永遠不建立 `manual_repair` authority。
- 正式化移到 DXF Review「修改工具」中的獨立「圍令正式化」工具；工具只對 repair-eligible Waler 出現。
- 工具以互斥的「線的來源」選擇點位清單或已讀取的CAD線，且只有一個「採用正式圍令」按鈕；按下時才建立並commit既有repair plan。
- CAD線仍由一般流程讀取，但不必先按「套用選取點」；兩種來源共用相同validation、commit、診斷取代與downstream rebuild contract。

## 現況與目標

本 change 中，「一般選點」是 DXF Review 既有的幾何編輯；「圍令正式化工具」是使用者對 repair-eligible Waler 作出正式 contact-face authority 裁決的唯一 UI 入口。

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 一般套用 | eligible Waler 的 apply action會直接正式化 | 「套用選取點」只更新 provisional geometry，不建立 authority |
| 正式化入口 | 混在候選點區／Preview apply action | 移到「修改工具 → 圍令正式化」專用視窗 |
| 線的來源 | 依共用pending pair與目前selection source推導 | 工具明確單選「點位清單／已讀取的CAD線」，預設點位清單 |
| 點位清單 | 使用共用候選區的pending pair直接正式化 | 工具顯示該Waler點位清單，預選目前線端點，不修改也可直接採用 |
| 重新採用 | 候選區直接正式化，操作意圖不清楚 | 工具內選擇尚未提交；成功commit前舊formal line完全不變 |
| CAD 線 | CAD讀取與正式化入口混合 | 一般流程只負責把最新CAD線讀入目標member；工具可直接選用，不需先一般套用 |
| 已正式化Waler的一般套用 | 會再走repair plan並取代正式線 | 一律拒絕並提示改用修改工具；live Review state不變 |

## 主要流程

```text
一般候選點流程（保持幾何編輯語意）
  選起點／選終點
    -> 套用選取點
    -> 只更新目前線；provisional Waler 仍為 provisional
    -> manual_repair Waler：拒絕並提示改用圍令正式化工具

一般CAD讀取
  從CAD指定工程線
    -> 最新CAD pair寫入當下目標member的candidate points
    -> 不建立formal authority，也不要求先按「套用選取點」

正式化流程
  選取 repair-eligible Waler
    -> 修改工具顯示「圍令正式化」
    -> 開啟工具，線的來源預設「點位清單」
       * 點位清單：起終點預選目前線的selected point IDs
       * 已讀取的CAD線：只有同一member存在最新CAD pair時可選
    -> 按「採用正式圍令」
    -> 依所選來源使用manual_candidate_points或cad_manual建立repair plan並立即commit
    -> 成功後建立／取代 manual_repair authority
```

工具開啟、來源／清單選擇與取消都只是未提交的Presentation state。若工具開啟後同一member的CAD線已更新，採用時拒絕並顯示「CAD 線已更新，請重新開啟圍令正式化」。此拒絕及任何計畫建立、驗證或commit失敗都不得改變live Review state、confirmations、diagnostics或既有formal line。

## 不變事項

- `DXFReviewWorkflow` 仍是 live Review geometry、manual decision 與正式化 transaction 的唯一 owner；Dialog 只保存工具內尚未提交的點位選擇。
- 正式採用仍沿用既有 repair eligibility、contact-face notice、revision／fingerprint guard、diagnostic replacement 與 downstream rebuild。
- 人工正式線仍是唯一 engineering／contact line；不放寬 envelope、source identity、terminal connection 或其他工程 validation。
- 主Review的「選起點／選終點」「套用選取點」維持一般幾何編輯；provisional Waler只更新geometry，`manual_repair` Waler則拒絕一般套用。Preview若恢復endpoint controls，也只提供相同的一般選點功能。
- 「圍令正式化」工具不讀取CAD event、不建立CAD線；CAD線只由既有一般流程讀取並以member-owned candidate points保存，不需先一般套用。
- Project schema、Pause／Resume payload、Domain、Solver scoring、搜尋參數、材料與寬度政策不變。

## Why

正式圍令是工程 authority 裁決，不應隱藏在一般候選點 apply action中。把正式化移到修改工具，能保留使用者熟悉的幾何編輯流程，同時讓第一次正式化與重新採用都在一個明確、可取消且原子提交的專用操作中完成。

## What Changes

- 候選點區與Preview不新增正式化按鈕；兩處只保留一般幾何選點操作。
- 在 DXF Review「修改工具」新增「圍令正式化」，顯示／啟用方式比照「中間柱關聯修補」：只依目前選取的唯一 repair-eligible Waler決定入口，不在顯示階段建立plan。
- 專用視窗提供互斥的「線的來源」單選：預設「點位清單」，並顯示合法起終點、預選目前`selected_start_point_id`／`selected_end_point_id`；只有目標member存在最新CAD pair時才enable「已讀取的CAD線」。
- 專用視窗固定顯示：「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」。
- 只有一個「採用正式圍令」按鈕：點位清單使用`manual_candidate_points`，已讀取CAD線使用`cad_manual`；取消、validation失敗、CAD已更新、stale或commit失敗均為零mutation。
- 一般候選套用不再路由到正式化：provisional Waler只更新暫定線；既有`manual_repair` Waler一律拒絕並提示改用修改工具。
- CAD指定線維持既有讀取入口；讀取後不需先一般套用即可在工具選擇，工具本身不提供CAD event讀取。
- 加入Y29 W14目前線端點預設與不改點直接採用的fixture regression。

## In Scope

- `dxf_import/dialog.py` 的修改工具入口、eligibility projection及獨立圍令正式化視窗。
- 專用視窗的來源單選、點位清單、起終點預設、同member CAD availability、contact-face notice、採用／取消／失敗行為。
- 主 Review與Preview的一般候選點行為修正；Preview endpoint controls只恢復generic selection。
- eligible provisional Waler與既有`manual_repair` Waler重新採用。
- 已由一般流程讀入目標member但尚未一般套用的最新CAD線之正式化與共用repair contract。
- Y29 W14 source `58D` 直接採用目前線的端對端測試。

## Out of Scope

- 在候選點區或Preview提供「採用正式圍令」按鈕。
- 保存或同步跨視窗repair plan；工具只保存視窗內未提交的point selection。
- 在正式化工具內讀取CAD event、建立新的CAD候選線或保存另一份CAD geometry truth。
- 修改repair eligibility、工程線hard validation、contact-face authority、診斷allowlist或downstream rebuild。
- 修改候選點生成、自動Waler recognition、材料／寬度推導、支撐側規則或persistence schema。
- 新增撤銷正式化、回復provisional或重構整個Dialog／DXFReviewWorkflow。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-waler-engineering-line-repair`：將正式化UI移至獨立修補工具，定義點位選擇、目前線預設、click-time原子commit、一般候選編輯隔離及CAD既有線採用語意。

## Impact

- **Presentation**：`dxf_import/dialog.py` 新增修改工具入口、source radio與modal point-selection UI；候選點區／Preview只保留generic selection及apply。
- **Workflow use case**：重用`plan_waler_engineering_line_repair()`／`commit_waler_engineering_line_repair()`；plan只在使用者按採用時建立，不在Presentation保存。
- **Provenance**：由工具內明確來源決定；點位清單固定使用`manual_candidate_points`，已讀取CAD線固定使用`cad_manual`，不再從目前pair或member selection source推導。
- **Tests**：修改`tests/test_dxf_review_layout.py`，補W14 fixture、source radio、CAD availability／更新失效、modal cancellation／failure、manual re-adoption及一般candidate apply regressions。
- **Long-term truth**：實作完成後更新`docs/WORKFLOW.md`的正式化入口、CAD讀取與一般套用限制；不預期修改Architecture、Domain、Solver或persistence。

## 已確認決策與重新評估條件

- 已確認：正式化只存在於「修改工具 → 圍令正式化」，候選點區與Preview不提供正式化按鈕。
- 已確認：工具支援點位清單與已讀取CAD線，但不提供CAD reader；CAD線不需先一般套用。
- 已確認：來源預設點位清單，CAD選項只在目標member有最新CAD pair時enable；兩者共用唯一採用按鈕。
- 已確認：工具開啟、改選或取消不建立plan、不修改Review state；按採用才plan＋commit。
- 已確認：一般「套用選取點」對provisional Waler只改geometry；對既有`manual_repair` Waler一律拒絕且狀態不變。
- 已確認：工具開啟後若同member CAD線更新，舊工具不得自動切換，採用時顯示「CAD 線已更新，請重新開啟圍令正式化」並保持live Review state完全不變。
- 已確認：Preview恢復「選起點／選終點」時，只重用一般選點流程。
- 調查確認：Y29 W14目前線端點已有`P01`／`P02`候選點，`selected_*`與`recommended_*`都指向該pair，且`line_1`使用相同座標；工具可直接預選並採用，不需synthetic point。
- 預設採用：若其他異常／legacy member的目前selected IDs無法解析為合法point list選項，工具拒絕開啟或採用並說明資料需重新整理；不得為了UI預設而修改live Review或猜測最近點。若實作discovery證明正常repair-eligible資料也會出現此情況，需停止並重新評估workflow contract。
