# Design：DXF 多筆待排除來源的 draft 與一次性重新辨識

## 閱讀導航

- **P0／現在必讀**：先讀「方案摘要」、D1「Pending draft由Workflow單一持有」、D2「狀態機與action gate」、D3「一次canonical staging」及D4「Plan與draft雙重stale guard」；這些決定避免pending與正式結果混成兩份truth。
- **P0／現在必讀**：實作transaction前讀「Single Source of Truth」與「Architecture Alignment」；`DXFReviewWorkflow`仍擁有正式Review state與pending intent，Dialog只投影及發命令。
- **P1／修改UI時閱讀**：D5「Presentation投影」與D6「關閉／Pause／Complete」；定義pending樣式、按鈕狀態、aggregate impact及未提交草稿的離開行為。
- **P1／修改replay或commit時閱讀**：D3、D4、D7與已封存`stabilize-corner-brace-repair-reference-identity`的D4 replay lifecycle；不得新增第二套recognition、repair matching或commit路徑。
- **P2／需要時再讀**：D8的work-count與fixture驗證、Backward Compatibility與Rollback；只有處理paired Joist、Y05／Y29效能或發佈回退時需要深入閱讀。可先跳過Solver、Project schema、成果匯出與recognition幾何規則。

## 方案摘要

`pending exclusion draft`在本change中是「尚未重新辨識的使用者排除意圖」，內容為一組正規化`ExcludedSource`、建立時的Review revision／source fingerprint及draft generation。它不是`world_result`、不是`result.excluded_sources`，也不會寫入Project。

```text
Committed Review state
  |
  +--> mark/unmark one ReviewItem
  |      -> Workflow validates identity
  |      -> updates PendingSourceExclusionDraft only
  |      -> Dialog updates pending overlay/count only
  |
  +--> apply pending draft
         -> validate base revision/fingerprint/generation
         -> union(committed exclusions, pending exclusions)
         -> existing plan_source_exclusion_change() exactly once
         -> aggregate impact from the returned plan
         -> confirm same plan
         -> existing atomic commit
         -> clear draft after commit succeeds
```

本方案不建立增量recognizer，也不把每一筆pending依序套用。所有工程truth仍只來自最後一次成功提交的`SourceExclusionPlan`。

## 決策對照

| Decision | 解決的問題 | 對應spec／主要tasks |
| --- | --- | --- |
| D1. Workflow單一持有immutable pending draft | 避免Dialog與Workflow各存一份pending並漂移 | 「待排除草稿必須與正式Review truth分離」；draft model／command tests |
| D2. Pending狀態機與集中action gate | 避免尚未辨識時混入manual mutation或Pause | 同Requirement的唯讀、mutation、close scenarios；gate／lifecycle tests |
| D3. Candidate union只呼叫既有canonical planner一次 | 讓N筆標記只支付一次full recognition，同時保留完整replay | 「來源排除必須以一次完整canonical staging建立結果」、「人工決策replay」；work-count／equivalence tests |
| D4. Review revision、source fingerprint與draft generation三重guard | 防止impact顯示後pending被改動或source／Review truth已變 | 「來源排除提交必須原子且綁定revision」；stale／failure tests |
| D5. Pending overlay與committed projection分層 | 讓使用者知道哪些來源待處理，但不把舊problems冒充新結果 | 「排除後畫面必須反映同一份目前結果」；render／selection tests |
| D6. Pending不持久化，離開前明確捨棄 | 限制schema與recovery影響，避免靜默遺失intent | 「待排除草稿必須與正式Review truth分離」、「逐筆入口與source-atomic assembly必須維持相容」；close／pause tests |
| D7. 成功commit後才清draft並刷新formal layers | 保留失敗可重試與atomic semantics | 「來源排除提交必須原子」；commit／rollback／refresh tests |
| D8. 以deterministic work-count與Y05／Y29驗證 | 避免把不穩定秒數當correctness門檻 | canonical staging／replay requirements；fixture benchmark tasks |

## Context

動機與使用者流程見[proposal.md](./proposal.md)的「Why」與「主要流程」。目前`DXFReviewWorkflow.plan_source_exclusion_for_item()`會在一次使用者操作內立即組合candidate exclusions並呼叫`plan_source_exclusion_change()`；後者透過`_recognize_staged()`執行`DXFImporter.convert()`、`replay_manual_overrides()`、association rebuild、problem／ReviewItem、confirmation及candidate-store projection。Dialog取得完整`SourceExclusionPlan`後才顯示單筆impact並commit。

現有`SourceExclusionPlan`已具備適合重用的transaction boundary：它包含base revision、normalized exclusions、world／projected result、problems、ReviewItems、confirmations、candidate store、manual replay與UI-neutral effects；`commit_source_exclusion_plan()`在guard後一次adopt，失敗時rollback。前一個`optimize-dxf-source-exclusion-workflow`亦已建立partial refresh、full refresh fallback及lazy debug。

因此本change的結構問題不是如何再做一套batch recognizer，而是如何在canonical planner前安全持有多筆使用者intent，且不讓pending期間的UI成為第二份工程truth。

`stabilize-corner-brace-repair-reference-identity`已於2026-10-07封存且27／27 tasks完成；本change應直接以其已驗證的`replay_manual_overrides()` CornerBrace reference reconstruction語意為baseline，不得建立自己的reference matching或改寫其replay輸出。

## Goals / Non-Goals

**Goals:**

- 將N次明確來源標記合併為一次canonical recognition／manual replay／commit。
- 使pending intent、正式Review truth與temporary plan各有明確owner及生命週期。
- 重用現有source identity、source-atomic assembly、canonical planner、atomic commit與render effects。
- 讓取消、stale、recognition failure與commit failure都保留完整committed state及可調整的pending draft。
- 以可測量的convert／replay呼叫次數證明改善，不降低任何工程validation。

**Non-Goals:**

- 不做incremental recognition、background worker、跨operation cache或固定秒數SLA。
- 不讓pending包含restore、manual repairs、confirmations、座標或圖層設定。
- 不保存pending到Project／Review state，也不修改relink／recovery。
- 不重新設計全部DXF Review toolbar、Tree多選或Preview selection model。
- 不調整CornerBrace、Waler、Joist或其他工程recognition規則。

## Decisions

### D1. Pending draft由`DXFReviewWorkflow`單一持有

在`dxf_import/review_workflow.py`加入UI-neutral、immutable draft value，例如：

```text
PendingSourceExclusionDraft
  base_revision
  source_fingerprint
  generation
  sources: tuple[ExcludedSource, ...]
```

`sources`使用現有`normalize_excluded_sources()`排序、去重；保留完整`ExcludedSource`而非只存identity，讓既有manual override snapshot與正式exclusion contract可直接進入planner。`generation`在每次有效mark／unmark／discard後增加，用來識別同一Review revision內被修改過的draft。

Workflow提供小型commands與read-only snapshot：mark目前ReviewItem、unmark identity、discard全部、查詢是否pending及建立apply plan。Dialog不得另存一份可修改的pending list；Tree rows、status、buttons與Preview overlay都由Workflow snapshot投影。

加入來源時重用`excluded_source_from_review_item()`、canonical identity、normalized handles及現有eligibility／shared-handle檢查。已正式excluded item不是pending候選；paired Joist siblings若解析成同一source-atomic identity，第二次mark為no-op或保持同一筆，而不是建立duplicate。

**Rejected：Presentation自行維護`set[str]`。** 這會使Dialog的pending與Workflow實際plan input成為兩份truth，且難以在restore、revision或source變更時一致失效。

**Rejected：mark時直接修改`excluded_sources`但延後recognition。** 這會讓正式exclusion truth與members／problems／connections不一致，違反現有state ownership及spec。

### D2. 使用明確pending狀態機與集中action gate

Draft狀態如下：

```text
EMPTY
  -> ACTIVE: first valid mark

ACTIVE
  -> ACTIVE: mark/unmark while at least one remains
  -> EMPTY: unmark last item or explicit discard
  -> PLANNING: apply command starts
  -> STALE: base revision or fingerprint no longer matches

PLANNING
  -> AWAITING_CONFIRMATION: canonical plan succeeds
  -> ACTIVE: planning fails

AWAITING_CONFIRMATION
  -> EMPTY: same plan commits successfully
  -> ACTIVE: user cancels or commit fails
  -> STALE: draft generation/revision/source changes

STALE
  -> EMPTY: explicit discard
```

`PLANNING`與`AWAITING_CONFIRMATION`可以是短生命週期operation state，不必持久存在於draft dataclass；但Dialog與Workflow commands必須防止re-entrant mark／unmark或第二次apply。

Action gate集中在Workflow可查詢的pending狀態與Dialog action-state刷新：

- 允許selection、inspection、filter、zoom、pan、mark、unmark、discard。
- 拒絕會修改Review truth或revision的manual repair、confirmation、coordinate、layer role、double-support／column decisions、正式restore、Pause及Complete。
- `recognize()`、recovery install或其他非Dialog入口若仍改變revision／source，draft轉為`STALE`，不得自動rebase。

實作應優先讓共用mutation入口呼叫一個UI-neutral guard，Presentation另負責disable按鈕與友善訊息。只disable widget不足以防止快捷鍵、測試或其他call path繞過。

**Rejected：允許manual mutation並在最後重新讀最新state。** 這需要把pending draft擴張成可rebase的長生命週期transaction，會增加依賴比對、impact語意與失敗組合，超出本change。

### D3. 整組candidate exclusions只進入既有canonical planner一次

Apply command先建立：

```text
candidate_exclusions = normalize(
    committed excluded_sources + pending draft.sources
)
```

然後恰好呼叫一次現有`plan_source_exclusion_change(candidate_exclusions)`。該方法仍是唯一canonical staging入口，負責：

1. 從committed `world_result`捕捉manual overrides。
2. `DXFImporter.convert()`完整recognition一次。
3. `replay_manual_overrides()`完整、安全replay一次。
4. double-support decisions與component associations重建。
5. coordinate projection、problems、ReviewItems、confirmations與candidate store。
6. `ReviewMutationEffects`及final plan。

不得在mark時呼叫`convert()`，也不得以N個single-item plans串接出最終result。Aggregate impact沿用現有before committed result與final staged result比較，只把「將排除」標題由單筆改為pending identities／display labels摘要；manual replay report只來自final plan。

即使draft只有一筆來源，也必須經過mark後再執行同一個apply command；Presentation與Workflow皆不保留選取後立即建立plan或立即排除的捷徑。Aggregate impact畫面固定註明「以下為所有待排除來源合併後的結果」，並提示「若結果不如預期，可取消個別待排除後重新套用」，讓單筆與多筆共用相同流程與回復方式。

**Rejected：逐筆plan但延後commit。** 即使不commit，仍會支付N次recognition，無法達成本change目的；中間plan也不是下一筆的安全base。

**Rejected：直接從舊result刪除pending members。** Connections、associations、diagnostics、repair references及completion truth有跨來源依賴，局部刪除不能成為formal truth。

### D4. Plan同時驗證Review revision、source fingerprint與draft generation

Mark第一筆來源時draft記錄`base_revision`與`source_fingerprint`。每次command先確認它們仍與Workflow一致；不一致時draft標示`STALE`，保留來源清單供使用者辨識，但只能discard，不得apply或自動換成新identity。

建立plan時，`SourceExclusionPlan`需攜帶或可由companion token驗證：

- 建立時draft generation。
- Pending canonical identities。
- Candidate union的normalized exclusions。

在使用者閱讀aggregate impact期間若pending被mark／unmark、Review revision改變或source fingerprint改變，commit必須拒絕。最小實作可擴充`SourceExclusionPlan`加入optional `pending_generation`與`pending_source_identities`；現有single restore plan使用`None`／空tuple，維持原contract。Commit除了既有guards外，再比較目前draft generation與`normalize(committed + pending)`是否等於plan exclusions。

Plan成功只代表可預覽，不修改draft或live state。使用者取消impact時丟棄plan、保留draft。Commit成功後才清draft；commit exception／rollback後draft仍存在。

**Rejected：只使用Review revision。** Mark／unmark刻意不增加正式Review revision，因此impact顯示後draft內容可能改變而revision不變；必須有獨立generation。

### D5. Pending overlay不改正式Review projection

目前UI基線只有DXF Review主視窗的「修改工具」內「來源」列提供`source_exclusion_button`；按鈕依選取狀態顯示「排除此 DXF 來源」或「復原此來源」。獨立Preview視窗的「目前選取」工具列目前只有構件資訊、端點選取與選點套用／取消，沒有來源排除入口。本change將新增Preview入口，但不讓兩個視窗各自持有draft。

Presentation把來源顯示狀態分成三層，優先序明確：

1. 正式committed engineering／problem／selection projection。
2. 正式excluded style。
3. Pending intent overlay。

Pending建議使用與正式excluded不同的顏色／dash或標記文字，並在來源排除區顯示「待排除（N，尚未重新辨識）」。選取pending來源時原ReviewItem仍可檢視；按鈕文字改為「取消待排除」。非pending且eligible來源顯示「標記待排除」。

主視窗與Preview都 SHALL提供「標記待排除／取消待排除」入口。主視窗入口位於既有「修改工具 → 來源」區；Preview入口位於既有「目前選取」工具列，緊鄰目前構件資訊。兩個入口只向`DXFReviewWorkflow`發出mark／unmark command，按鈕文字、enabled state與pending狀態皆由Workflow同一份draft snapshot投影；任一入口操作後，兩個視窗 MUST同步顯示相同結果，Dialog或Preview不得各自保存pending集合。

主視窗來源排除區 SHALL新增待排除清單，逐筆顯示構件ID與來源資訊。點擊清單列 SHALL選取並定位該構件，沿用既有Review selection與Preview定位行為；每列另提供取消單筆待排除的操作，取消後由Workflow snapshot同步更新主視窗按鈕、Preview按鈕、清單、count與pending overlay。清單不得以顯示文字或row index作為truth，command仍使用Workflow提供的canonical identity。

「重新辨識並套用（N）」與「捨棄待排除」 SHALL放在主視窗待排除清單下方；前者在draft非空且有效時可執行，後者清除完整draft但不修改committed Review truth。Preview不重複放置整組apply／discard controls，避免在較窄工具列塞入transaction操作；Preview只提供目前選取來源的mark／unmark入口。

Pending存在時，所有被D2共用action gate擋下的按鈕 SHALL呈現disabled，且滑鼠停留時顯示「請先套用或捨棄待排除來源」。Tooltip只是拒絕原因的Presentation投影；Workflow guard仍是最終保護，不得只靠disabled widget。Draft清空、成功commit或狀態改變後，兩個視窗 SHALL由同一action-state snapshot移除或更新tooltip與enabled state。

目標排版示意如下；中括號代表按鈕，實際寬度可依視窗調整，但群組與上下順序不變：

```text
DXF Review主視窗／修改工具
┌─ 來源排除 ─────────────────────────────────────┐
│ 目前選取：S14    [標記待排除／取消待排除]       │
│ 待排除來源（N，尚未重新辨識）                   │
│ ┌──────────┬────────────────────┬───────────┐ │
│ │ 構件 ID  │ 來源               │ 操作      │ │
│ │ S14      │ Strut / Handle D1A │ [取消]    │ │
│ │ CB68     │ CornerBrace / ...  │ [取消]    │ │
│ └──────────┴────────────────────┴───────────┘ │
│ [重新辨識並套用（N）]  [捨棄待排除]             │
└───────────────────────────────────────────────┘

Preview視窗／目前選取
┌────────────────────────────────────────────────────────────┐
│ 目前構件：S14  [標記待排除／取消待排除]  （既有選點controls）│
└────────────────────────────────────────────────────────────┘
```

Mark／unmark只需更新相關source handles的style、Tree status文字及action state，不重建formal member、problem、candidate或hit index。若Preview source index不完整或generation不安全，允許重建source style layer，但不得重新recognize或把pending從hit index移除；pending來源仍是committed result中的可選取來源。

Apply按鈕顯示「重新辨識並套用（N）」且draft空時disabled。Planning期間避免re-entry並顯示既有watch cursor／status。Plan完成後顯示aggregate impact，標示「以下為所有待排除來源合併後的結果」，並提示「若結果不如預期，可取消個別待排除後重新套用」；確認成功後使用既有`_commit_source_exclusion_stage()`／`ReviewMutationEffects`刷新formal layers，取消則保留draft供使用者取消個別標記後重新apply。

Developer debug的formal payload仍依committed revision產生。若需要顯示pending，只能放在Dialog-local、清楚標為uncommitted的獨立區段，不得寫入`DXFImportResult.to_debug_dict()`或Review persistence。

### D6. Pending不持久化，Pause／Complete／close採安全停止

Pending draft屬目前live session，`to_review_state()`、Pause outcome、Project payload與same-session resumable cache都不包含它。這避免Project schema、recovery planner與changed-content classification一起擴張。

- Pending非空時，Pause及Complete command在Workflow／Dialog雙層拒絕。
- Window close顯示「捨棄待排除並關閉／取消關閉」；只有明確捨棄才清draft並繼續既有close行為。
- 不提供「關閉前自動重新辨識」；關閉動作不得隱含昂貴或改資料的commit。
- 正式excluded restore在draft空時走既有single-item path；draft非空時由gate拒絕。

**Rejected：將pending寫入version 2 Review state。** Pending沒有recognition result可供recovery驗證，保存它會要求schema、Resume UI、source change classification及stale handling一起改動。

### D7. Commit後才清draft，失敗保留可重試intent

Canonical plan沿用既有`commit_source_exclusion_plan()`atomic adoption及rollback snapshot。成功順序為：

1. 驗證Review／source／draft token及plan payload。
2. Adopt完整`SourceExclusionPlan`並增加一次Review revision。
3. 清除pending draft；此步必須是不可失敗的plain assignment，或納入同一rollback snapshot。
4. 同步Dialog snapshot並依`ReviewMutationEffects`刷新。

為避免「正式commit成功但清draft失敗」，draft clear不得呼叫Tk、serialization或可拋錯callback。UI refresh失敗時正式Review commit不回滾；Dialog保留既有錯誤處理，但下一次成功refresh必須由Workflow已清空的draft truth重建，不得讓舊pending overlay繼續顯示。

Recognition、replay、impact建立或使用者取消都發生在commit前，保留committed state與draft。Commit validation或adoption失敗則沿用現有rollback並保留draft。

### D8. Correctness與效能使用deterministic work-count驗證

正式acceptance不以秒數設門檻。對包含N筆pending且N大於或等於1的單次apply，測試記錄：

- mark／unmark期間`DXFImporter.convert()`與`replay_manual_overrides()`皆為0次。
- Apply plan期間full importer／recognition為1次、manual replay為1次、final problem／ReviewItem projection各1次。
- Commit revision增加1次。
- Hidden debug不序列化。

Y05以至少兩筆可安全排除來源建立multi-pending fixture，驗證全部既有CornerBrace repairs、stable references、members、connections、messages、problems、ReviewItems、confirmations、completion truth及replay report與直接對相同final exclusion set執行canonical planner完全一致。Y29驗證legacy Waler manual override及single restore相容性。

Benchmark另記錄N次既有single flow與一次multi-pending flow的總convert／replay次數及wall-clock，wall-clock只作觀測，不作CI assertion。

## Single Source of Truth

| State | 唯一owner | 非truth投影 |
| --- | --- | --- |
| 正式DXF Review結果／`excluded_sources`／revision | `DXFReviewWorkflow` committed fields | Dialog trees、Preview、status、debug text |
| 未提交排除intent | `DXFReviewWorkflow.pending_source_exclusion_draft` | Pending badge、count、source overlay、button state |
| 一次重新辨識的候選結果 | Immutable `SourceExclusionPlan` | Aggregate impact dialog |
| Project／Solver state | 既有Application／Main owners | DXF Dialog不得在pending或staging時修改 |

Pending與committed不是兩份同類truth：前者只表示intent，後者才是工程結果。任何顯示正式members、problems、connections或completion的UI只能讀committed result；pending overlay只能讀draft snapshot。成功commit以plan取代committed truth並清draft，不能把overlay反向推導成正式exclusion。

## Architecture Alignment

本change沿用既有Architecture，不修改layer方向。

- **DXF Review Workflow／Application-like boundary**：`dxf_import/review_workflow.py`持有pending draft、eligibility commands、stale guard、canonical planning及atomic commit。它可依賴recognition／models／validation，但不得依賴Tkinter、Dialog或`RenderDirty`。
- **DXF Presentation**：`dxf_import/dialog.py`負責按鈕、提示、aggregate impact、pending overlay、selection與close互動，只消費Workflow snapshot／effects，不自行正規化工程identity或建立candidate exclusions。
- **Recognition／Review pure operations**：`importer.py`、`source_exclusion.py`、`corner_brace_repair.py`沿用既有recognition與replay contract；不認識pending UI或Tk state。
- **Infrastructure／Project persistence**：不修改；只在成功正式commit後由既有Review serialization保存normalized exclusions。
- **Domain／Algorithms／Solver**：不受影響。

依賴方向維持：

```text
DXF Presentation
      -> DXFReviewWorkflow
            -> Recognition / Review operations
                  -> DXF Models / Geometry
```

## Backward Compatibility與Persistence Impact

- Project與Review schema不變；舊Project直接載入，不存在pending migration。
- 現有正式`excluded_sources`、manual overrides、confirmations、Pause／Resume及recovery payload格式不變。
- Draft空時的single restore仍走既有plan／impact／commit path。
- 來源排除的UI行為是刻意變更：未正式excluded的ReviewItem不再於第一次操作立即recognize，而是一律先成為pending；即使單筆排除也必須再明確執行apply，比以往多一步，且不提供立即排除入口。
- Existing API tests若直接呼叫`plan_source_exclusion_change()`或`commit_source_exclusion_plan()`可維持有效；舊Dialog single-action tests需改為mark + apply + confirm。
- 若需回退功能，可移除pending UI／commands並恢復Dialog直接呼叫`plan_source_exclusion_for_item()`；canonical planner、commit、schema及既有formal exclusions不需migration。

## 重要替代方案

- **Debounce後自動重新辨識**：拒絕。使用者停頓時間不是明確commit意圖，仍可能在標記途中觸發多次昂貴工作。
- **Background worker**：拒絕於本change。它改善UI凍結但不減少N次recognition，且需要operation cancellation／stale callback lifecycle。
- **Incremental／role-local recognition**：拒絕。Waler、Strut、Brace、CornerBrace、Column、Joist及associations有順序與跨角色依賴，驗證成本與風險遠高於先合併intent。
- **保存pending到Project**：拒絕。需要schema、Pause／Resume、relink與recovery semantics，不符合第一版最小安全範圍。
- **允許pending restore**：拒絕。排除新增與正式restore的manual override／impact語意不同，先保持既有restore path可降低transaction組合。
- **重用主畫面「重新整理全部畫面」**：拒絕。該入口只重建committed Project UI projection，不執行DXF recognition，也不屬於DXF Review session。

## Risks / Trade-offs

- **[Risk] 使用者把pending樣式誤認為已正式排除** -> 使用不同於excluded的顏色／文字，固定顯示「尚未重新辨識」，problems與completion區同步顯示committed狀態提示。
- **[Risk] Dialog disable遺漏某個mutation入口** -> Workflow加入共用guard，UI disable只作輔助；以入口盤點及parameterized tests覆蓋manual commands。
- **[Risk] Impact顯示後draft被更動仍提交舊plan** -> plan保存draft generation及identities，commit同時重驗generation、revision、fingerprint與candidate union。
- **[Risk] Paired Joist兩個siblings形成重複或半套pending** -> mark時沿用source-atomic canonical identity並正規化去重，fixture驗證任一sibling都得到同一decision。
- **[Risk] 成功commit後UI refresh失敗留下pending overlay** -> draft在formal commit boundary以plain assignment清除；任何重建UI都從Workflow snapshot取得空draft，舊canvas item依revision／generation失效。
- **[Risk] Pending存在時操作限制過多** -> 第一版刻意換取transaction可證明性；若實際UX不可接受，另案設計可rebase draft，不在本change內逐項放寬。
- **[Trade-off] 使用者要到最後才知道整組工程影響** -> 保留aggregate impact與取消；取消不丟pending，可移除特定項目後重試，但已支付該次recognition成本。
- **[Trade-off] 長時間recognition仍在前景執行** -> 本change降低重複次數但不處理單次UI blocking；background execution保留為獨立change。

## Migration Plan

1. 以已封存且27／27 tasks完成的`stabilize-corner-brace-repair-reference-identity`作為focused test與CornerBrace replay baseline。
2. 加入draft model／commands／guards，預設draft為empty；尚未改Dialog入口前不影響既有行為。
3. 加入multi-pending planner token與commit validation，先以headless tests證明single recognition及atomic semantics。
4. 切換Dialog來源排除入口、pending overlay、aggregate impact與lifecycle gates。
5. 執行focused、fixture及完整regression後更新`docs/WORKFLOW.md`。

Rollback不需資料migration：移除pending入口並恢復single-item Dialog orchestration即可；正式Project／Review payload仍由既有schema讀取。若在實作途中發現source-atomic identity無法於mark時可靠建立，停止在UI切換前並回報，不以final recognition時改選來源作fallback。
