# Proposal：暫存多筆 DXF 來源排除後一次重新辨識

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認本案允許逐筆累積多個待排除來源，但不自動選取來源，也不省略最後的完整辨識。
- **P0／現在必讀**：本 change 的 delta spec `dxf-source-exclusion-workflow`；它會修改現行「每選一筆就立即完整辨識」與「不得有多來源 pending state」的既有 Requirement。
- **P0／現在必讀**：`openspec/specs/dxf-source-exclusion-workflow/spec.md` 的「人工決策 replay 必須安全且結果等價」與「來源排除提交必須原子且綁定 revision」；多筆操作仍受相同工程安全邊界約束。
- **P1／實作前閱讀**：本 change `design.md` 的 pending draft ownership、base revision invalidation、一次 canonical staging、aggregate impact 與 UI action gate Decisions；另讀 active change `stabilize-corner-brace-repair-reference-identity` 的 replay lifecycle，確認先完成其 verification 再修改共用路徑。
- **P2／需要時再讀**：修改 Preview 樣式／hit index 時讀 `dxf-review-preview-error-selection`；驗證 paired BIM Joist 時讀 `bim-joist-recognition` 的 source-atomic requirement。可先跳過 Solver、Project schema、材料比例、recognition 幾何門檻、成果匯出與 changed-content recovery specs，本案不改那些規則。

## 快速摘要

- 現在每排除一筆來源都會執行一次完整辨識與人工決策 replay；即使前一個效能 change 已大幅改善，連續處理多筆來源仍會重複等待數秒。
- 本案新增「待排除來源」草稿：使用者仍逐筆明確選取來源，但可連續標記／取消多筆，不在每次標記時重新辨識。
- 使用者最後按一次「重新辨識並套用」，系統才針對「既有排除＋全部待排除」執行一次 canonical staging，顯示合併影響並原子提交同一份 plan。
- 待排除期間，正式 recognition result、錯誤清單、工程關聯、Project、Solver、persistence 與 dirty state都不改變；畫面必須清楚區分 pending 標記與正式 excluded 狀態。
- 完整辨識、manual replay、source-atomic identity、revision guard、失敗零副作用與既有工程規則全部保留；本案不做增量辨識或背景 worker。

## 現況與目標

本案中的「待排除來源」是使用者已明確選取、但尚未重新辨識與提交的 canonical source identity集合。它只代表操作意圖，不是新的工程辨識結果，也不是正式 `excluded_sources`。

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 連續排除 | 每選一筆就建立完整 plan、重新辨識、顯示影響並提交 | 每次只加入／移除 pending draft；最後針對全部 pending來源執行一次完整辨識 |
| 單筆排除 | 選取一筆後立即建立plan、重新辨識並顯示影響 | 即使只排除一筆，也必須先標記待排除，再按「重新辨識並套用」；比以往多一步，屬於預期行為變更，且不新增立即排除入口 |
| 使用者選擇 | 一次明確選取一個 ReviewItem | 仍一次明確選取一個 ReviewItem，但可累積多個 canonical source identities；不提供自動全選 |
| 等待成本 | N筆來源最多觸發N次 full recognition與manual replay | N筆待排除來源合併成一次 full recognition與一次manual replay |
| 待排除期間畫面 | 沒有 pending 狀態 | 保留目前 committed工程結果，另以明確pending樣式與計數呈現尚未套用的來源 |
| 影響確認 | 每一筆辨識完成後顯示單筆impact | 一次staging完成後顯示整組aggregate impact；確認後提交同一份plan |
| 失敗／取消 | 單筆plan失敗或取消不改live state | 整組staging／commit全有或全無；失敗或取消保留committed state與pending draft供調整／重試 |
| Pause／Complete／關閉 | 沒有未提交排除草稿 | pending存在時不得Pause或Complete；關閉時可取消關閉或明確捨棄pending，pending不寫入Project |

## 主要流程

```text
使用者選取一個目前可排除的 ReviewItem
  -> 立即執行既有 source identity／shared-handle eligibility 檢查
  -> 將 canonical source identity 加入 pending draft
  -> 畫面顯示「待排除」，但 committed result／problems／relationships 不變
  -> 使用者可繼續標記其他來源，或取消任一 pending 標記

使用者按「重新辨識並套用」
  -> 以目前 committed exclusions + 全部 pending exclusions 建立一個candidate set
  -> 對整組 candidate set 執行一次 full recognition
  -> 依既有順序完整 replay manual decisions與confirmations
  -> 建立一份revision-bound plan與aggregate impact
  -> 畫面註明「以下為所有待排除來源合併後的結果」
     並提示「若結果不如預期，可取消個別待排除後重新套用」
  -> 使用者確認：原子提交同一份plan、清空pending draft、刷新畫面
  -> 使用者取消或任一步驟失敗：committed state不變，pending draft保留
```

## 不變事項

- 每一個 pending來源都必須由使用者逐筆明確選取；不得自動加入全部error／critical、紅色來源、同類來源或系統推測的排除目標。
- 最終 plan 仍須從排除後 active DXF sources 完整重建 recognition、formal members、connections、associations、diagnostics、ReviewItems 與 completion truth。
- CornerBrace repairs、Waler decisions、材料／工程線輸入與 confirmations仍依當下 staged result完整、安全 replay；`preserved`、`needs_review`、`disabled`與dependency pass語意不變。
- paired BIM Joist等shared-root assembly仍以既有source-atomic identity作為一筆排除單位；不得把siblings拆成多個pending或正式exclusion。
- 原始DXF、source fingerprint、recognition tolerances、repair eligibility／ranking、Project rows、Solver input／scoring與工程Domain rule不變。
- 成功提交仍只增加一次Review revision並採用同一份完整plan；staging、impact確認、取消或失敗都不得部分修改live truth。
- 主畫面的「重新整理全部畫面」仍只負責從committed Project state重建UI projection，不作為本案的DXF重新辨識入口。

## Why

既有優化已把Y05單筆來源排除降到約8.9秒、Y29約3.4秒，但每一筆仍必須各自支付full recognition與manual replay成本。使用者需要連續處理多個來源時，將明確選取先累積成pending draft，再一次完整重新辨識，可以減少重複等待，同時保留現有canonical rebuild與工程安全契約。

## What Changes

- 將既有來源排除入口從「立即建立單筆plan」改為「逐筆加入或取消pending exclusion draft」；即使只有一筆也必須先標記，再由「重新辨識並套用」處理，且不保留或新增立即排除入口。標記操作本身不得呼叫full recognition。
- Pending draft以canonical source identity正規化及去重，並綁定建立時的Review revision與source fingerprint；每筆加入時仍執行來源存在性、角色、normalized handles及shared-handle安全檢查。
- DXF Review新增「重新辨識並套用」入口；無pending時disabled，有pending時顯示數量，並針對整組candidate exclusions只呼叫一次既有canonical staging路徑。
- Staging完成後顯示aggregate impact，包含正式構件、警告／錯誤、manual replay與confirmation invalidation變化；畫面必須註明「以下為所有待排除來源合併後的結果」，並提示「若結果不如預期，可取消個別待排除後重新套用」。使用者確認後才提交該份revision-bound plan。
- Pending期間只允許選取、檢視、縮放與pending標記／取消等不改工程truth的操作；會修改Review truth的manual repair、confirmation、圖層用途、座標、restore、Pause／Complete等入口須先套用或捨棄pending。
- Pending樣式不得冒充正式excluded；problems、ReviewItems、completion status及工程資料仍標示為上次committed result，並顯示「尚未重新辨識」提示。
- Staging、aggregate impact取消、stale revision或commit失敗時保留完整committed state與pending draft；成功commit才清空draft並沿用既有partial refresh／full refresh fallback。
- Pending draft只存在於目前live Review session，不新增Project persistence欄位；視窗關閉時若仍有pending，必須提供捨棄或取消關閉，不得靜默保存或套用。

## In Scope

- 多筆待排除來源的mark／unmark、deduplication、pending count與明確視覺狀態。
- Pending draft的base revision／source fingerprint綁定、stale處理及UI-neutral workflow ownership。
- 以既有committed exclusions加上全部pending exclusions建立一份batch candidate set，執行一次canonical staging、一次manual replay及一份aggregate impact。
- 同一份plan的確認、revision-bound原子commit、失敗零副作用與成功後draft清除。
- Pending期間的Review mutation action gate，以及Pause／Complete／close行為。
- paired BIM Joist source-atomic、CornerBrace repair replay、Y05／Y29多來源效能與correctness regression。

## Out of Scope

- 自動排除全部error／critical、依顏色或severity自動選取、框選／多選Tree rows，或替使用者決定winner。
- Pending restore或多來源batch restore；已正式排除來源的restore在沒有pending draft時維持既有單筆流程，有pending時先拒絕並要求套用或捨棄draft。
- 增量recognition、角色局部重算、跨operation recognition cache、略過manual replay或沿用無法證明安全的derived truth。
- Background worker、進度取消、固定秒數SLA，或把Tk主執行緒辨識改成非同步架構。
- 將pending draft寫入Project／Review persistence、Project schema migration、source relink或changed-content recovery。
- 修改CornerBrace stable reference identity、repair eligibility、candidate ranking、diagnostic severity、completion rule、Solver或工程Domain rule。
- 重用或改寫主畫面「重新整理全部畫面」的projection recovery workflow。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-source-exclusion-workflow`：將現行單筆立即辨識流程改為逐筆累積多個pending exclusions，最後以一次完整canonical staging建立aggregate impact並原子提交；同步定義pending期間的畫面truth、action gate、失敗與關閉語意。

## Impact

- **Workflow**：`dxf_import/review_workflow.py`新增UI-neutral pending exclusion draft contract，並重用現有`plan_source_exclusion_change()`與`commit_source_exclusion_plan()`作為唯一canonical staging／commit路徑；`DXFReviewWorkflow`仍是正式Review state owner。
- **Presentation**：`dxf_import/dialog.py`將來源排除按鈕改為mark／unmark，新增pending count、pending樣式、「重新辨識並套用」、aggregate impact、action gate及close提示。
- **Preview／selection**：pending overlay與正式excluded style分離；只有成功commit才依`ReviewMutationEffects`更新正式layers、selection與hit index。
- **Manual replay**：`dxf_import/source_exclusion.py`與`dxf_import/corner_brace_repair.py`不新增第二套replay規則；多筆candidate set仍只進入既有canonical replay一次。
- **Persistence**：不修改Project或Review schema；pending draft不保存，正式提交後仍只持久化normalized `excluded_sources`。
- **Tests**：主要影響`tests/test_dxf_source_exclusion.py`、`tests/test_dxf_review_layout.py`、`tests/test_dxf_review_workflow.py`與`tests/test_dxf_source_exclusion_fixture_regression.py`；需補多筆mark／unmark、single-recognition work-count、stale／failure、action gate及close regression。
- **Architecture／Domain／Solver**：沿用既有DXF Workflow與Presentation責任，不修改Architecture layer direction、Domain或Solver。實作完成後需要更新`docs/WORKFLOW.md`的來源排除transaction lifecycle。

## 相關 change 與實作順序

- 已封存`optimize-dxf-source-exclusion-workflow`建立目前的single-plan canonical staging、optimized replay、atomic commit、partial refresh與lazy debug基線；本案刻意修改它當時排除的多來源pending UI，但不得撤銷其correctness保護。
- `stabilize-corner-brace-repair-reference-identity`已於2026-10-07封存，最終tasks為27／27完成；實作本案時應以其已驗證的CornerBrace replay lifecycle作為共用baseline，不得另建reference matching規則。
- `harden-project-state-transactions`提供的主畫面`projection_stale`與「重新整理全部畫面」只處理Project UI recovery，與本案DXF Review內的pending draft及重新辨識入口分離。

## 已確認決策與重新評估條件

- 已確認：使用者仍逐筆選取來源，但可連續累積多個pending；最後只執行一次full recognition與一次manual replay。
- 已確認：單筆排除也一律先標記待排除，再按「重新辨識並套用」；相較舊流程多一次明確操作是預期行為變更，不提供立即排除捷徑。
- 已確認：pending不是正式excluded truth，不提前改problems、relationships、completion或persistence；只以獨立視覺標記呈現。
- 已確認：staging完成後仍顯示aggregate impact並確認，確認採用同一份plan，不再重跑recognition。
- 已確認：第一版pending不保存、不支援pending restore，且不新增background worker或incremental recognition。
- 已確認：pending存在時阻擋會修改Review truth的其他入口，避免把draft擴張成涵蓋所有manual operations的大型transaction。
- 若實作discovery證明現有single-item eligibility無法在不辨識的情況下安全正規化source-atomic identity，必須停止並回報，不得延後到final staging才偷偷改選其他來源。
- 若UX測試顯示阻擋全部manual mutation不可接受，需另行擴張draft transaction模型並更新proposal／spec／design，不得在implementation中臨時允許會使base revision漂移的操作。
- 若pending需要跨Pause／關閉保存，將涉及persistence contract與recovery語意，超出本change，必須另行評估schema及相容性。
