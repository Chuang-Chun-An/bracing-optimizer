# Design：DXF 單筆來源排除的 replay 與刷新優化

## 閱讀導航

- **P0／現在必讀**：Context 的 Y05 實測與 D1～D3。D2 已採方案 D：優化只限單次 `plan_corner_brace_repair()`，不跨 repair 共用 cache。
- **P0／現在必讀**：Architecture Alignment 與 Single Source of Truth。正式 Review state仍只屬於 `DXFReviewWorkflow`；replay projection、render scene與 debug text都是可丟棄投影。
- **P1／修改 Preview 時閱讀**：D4。只有修改 `dxf_import/dialog.py`、preview dirty flags、canvas item index或 hit index時需要深入閱讀。
- **P1／修改 developer debug 時閱讀**：D5。只有拆分 `_refresh_result_views()` 與 debug panel時需要深入閱讀。
- **P1／寫效能測試時閱讀**：D6。correctness gate是避免不必要的全角色重算與 optimized-vs-canonical等價，不是固定秒數。
- **P2／需要時再讀**：D7。只有修改 Waler UI／replay整合時才讀相關 change狀態與路徑交集。
- **可先跳過**：多選／批次 UI、DXF geometry extraction cache、Solver、Project schema、recognition 幾何門檻與 background worker；本 change不改這些內容。

## 方案摘要

```text
現有單筆 ReviewItem
  -> 現有 eligibility / source identity 檢查
  -> 一次 full recognition
  -> 依原順序 replay manual decisions
       -> 每次 plan 內只計算暫時候選自身 connection
       -> 以相同 duplicate rule逐一比較既有角撐
       -> 預建該次 plan 的 lookup／template／frame／方向與 anchor索引
       -> plan結束即丟棄；不跨 repair共用
  -> 最終完整 problems / ReviewItems / confirmations / candidates
  -> immutable SourceExclusionPlan
  -> revision guard + atomic state swap
  -> 局部畫面刷新；hidden debug僅標 dirty
```

本 change 的「replay projection」是一次 staging 內，供 CornerBrace repair target lookup與相關 validation使用的暫存衍生資料；它不是 UI tree，也不是工程 result。「canonical sequential replay」是目前每筆 repair都根據當下 result重新建立完整 projection再執行的參考語意。方案 D 不沿用其他 repair的projection或outcome，只改寫單次planning內的重複計算，且必須產生完全相同的候選集合、順序與診斷。

## 決策對照

| Decision | 對應 spec Requirement | 主要實作／驗證工作 |
| --- | --- | --- |
| D1. 保留單筆入口與現有選取模型 | 單筆來源排除必須由使用者明確啟動；單筆入口與 source-atomic assembly相容 | 不新增 UI、單筆／取消／paired Joist regression |
| D2. 方案 D：單次 planning 內局部驗證與短生命週期索引 | 人工決策 replay必須安全且結果等價 | 逐候選 local-vs-full differential test、plan輸出等價、per-call lifetime驗證 |
| D3. Plan預建所有 fallible projection後原子 swap | 來源排除提交必須原子且綁定 revision | immutable plan、stale guard、candidate／confirmation預建、failure tests |
| D4. UI-neutral effects驅動局部刷新 | 排除後畫面必須反映同一份目前結果 | source style／derived layers、hit index、viewport、fallback tests |
| D5. Debug payload依 revision延遲產生 | 排除後畫面必須反映同一份目前結果 | hidden debug不序列化、open時 current-revision tests |
| D6. 避免不必要重算與 canonical equivalence作效能 gate | 完整 staged result；安全且等價 replay | spies、reference replay、Y05／Y29 benchmark |
| D7. 以既有 Waler replay為baseline並追蹤UI change | 完整 staged result；安全且等價 replay | path overlap確認與 cross-manual regression |

## Context

效能動機與量測見 [proposal.md](./proposal.md)「Why」。目前單筆來源排除已只呼叫一次 `plan_source_exclusion_change()`；因此增加 batch入口不是改善單次等待的必要條件。

主要熱點在 `replay_manual_overrides()` 的 CornerBrace repair loop。對每一筆 pending repair，目前流程都會：

1. 將整份 current result套用座標投影。
2. 建立所有角色的 problem records。
3. 建立所有 ReviewItems。
4. 掃描 CornerBrace items並逐一計算 `repair_subject_key`。
5. 規劃及套用一筆 repair後，下一筆再重做以上工作。

### Y05 fixture與量測限制

量測日期為2026-10-06，fixture為`project_cases/Y05車站第一層支撐/project.json`及其managed DXF。當前保存狀態有28筆exclusions、11筆manual overrides（全部為CornerBrace repair）、0筆其他manual overrides、0筆review confirmations。早期紀錄的14.2秒來自較早的保存狀態／程式baseline；目前fixture已變動，無法事後把原14.2秒精確回填到各函式。因此以下以同一條production path、單次wall-clock instrumentation的現況重測為準；數字用來判斷成本結構，不作CI秒數門檻。

主案例排除的是與11筆repair輸入距離最遠的Beam／Joist來源`BM29`（handle`E91`、identity`beam:E91`，最近repair輸入距離約33,048.789 mm）。未加細部分段instrumentation時，baseline recognition為30.918784秒、exclusion plan為29.624775秒；分段instrumentation run的baseline recognition為31.751122秒、plan為31.180429秒，其中manual replay為26.671668秒。Instrumentation本身會增加一些成本，因此應比較同一run內各段比例，而不把31.180429秒與未instrumented數字直接相減。

| manual replay區段 | 次數 | 時間（秒） | replay占比 | 實際位置／說明 |
| --- | ---: | ---: | ---: | --- |
| 座標投影 | 11 | 1.469434 | 5.5% | `source_exclusion.py:1098`，每筆repair對整份result呼叫`apply_coordinate_system()` |
| `build_problem_records` | 11 | 1.115848 | 4.2% | `source_exclusion.py:1099`，包含所有角色 |
| `build_review_items` | 11 | 0.076885 | 0.3% | `source_exclusion.py:1100`，包含所有角色 |
| target掃描 | 1,089次`repair_subject_key` | 0.100371 | 0.4% | `source_exclusion.py:1104-1110`附近，掃描每輪ReviewItems |
| repair planning | 22次 | 22.776648 | 85.4% | 11次`plan_corner_brace_repair()`共21.944085秒，11次`reconstruct_saved_template_candidate()`共0.832563秒；入口見`corner_brace_repair.py:827`、`:1194` |
| `apply_corner_brace_repair` | 11 | 1.096526 | 4.1% | `source_exclusion.py:1220`／`corner_brace_repair.py:1539` |
| orchestration與其他manual override | 1 | 0.035956 | 0.1% | `replay_manual_overrides()`自身exclusive residual；此fixture沒有其他manual override |
| **合計** | **11 repairs** | **26.671668** | **100%** | 分段和與replay總時間相符 |

這次重測修正了原先「主要成本是重建全量problem／ReviewItem」的假設：明確可歸入座標投影、problem／ReviewItem與target掃描的成本合計2.762538秒（10.4%）；最大成本是repair planning 22.776648秒（85.4%）。所以A或B若只減少projection，改善有上限；C若能安全命中，才可能跳過大部分planning。

### 排除無關來源時的實際變化

對`BM29`／`E91`執行排除後，CB66～CB76共11筆repair全部為`preserved`。逐筆比較排除前與排除後的subject、target Waler、target Strut、automatic／manual／template references、confirmations及selected candidate，全部11筆皆相同；因此使用者指定的四類輸入實際改變為**0/11**，candidate也為**0/11**。

另做一個反例：排除遠處Strut`S14`（handle`D1A`、identity`strut:D1A`，最近已記錄repair輸入距離約26,878.411 mm）時，CB66～CB70共5筆變成`needs_review`，只有CB71～CB76六筆`preserved`。這表示「距離遠」及「不在已記錄target／reference identity中」都不是跨repair沿用的充分證明；本案因此不採跨repair dependency footprint或fingerprint。S14的實際失敗是顯示member ID漂移，另由`stabilize-corner-brace-repair-reference-identity`處理。

### 每筆CornerBrace repair正確性依賴輸入

以下是目前code path實際讀取的完整依賴分類；方案 D 雖不跨repair沿用，仍必須確保候選局部validation與單次呼叫索引沒有漏讀這些輸入：

| 依賴輸入 | 內容 | 程式位置 |
| --- | --- | --- |
| 保存的repair決策與provenance | subject key（source fingerprint、normalized handles、target kind、base geometry key）、preferred member ID、target Waler／Strut canonical identity、primary／secondary／template references、selection／transfer mode、offset／station／fixed length、body／evidence signature | `source_exclusion.py:132-265`；資料結構見`corner_brace_repair.py:121-165` |
| Subject來源與目前幾何 | unresolved／recognized subject、source geometry、points／segments／closed狀態、目前member geometry、body evidence及relationship assessments | `corner_brace_repair.py:256-430`、`:827-970` |
| Target Waler | 唯一canonical source identity、目前world line／geometry、member ID，以及repair relationship所讀取的connection/contact結果 | `corner_brace_repair.py:446-615`、`:827-1125` |
| Target Strut | 唯一identity、目前world line、member ID、from／to Waler拓撲與endpoint name | `corner_brace_repair.py:446-615`、`:827-1125` |
| 參考角撐全集 | 每個reference的subject key、member ID、reference class、目前角撐幾何、provenance、connection、Waler／Strut relationship、attachment points、offset／station／fixed length | `corner_brace_repair.py:645-724`、`:972-1125` |
| Confirmations | confirmation identity→signature map、目前confirmation result／ReviewItem內容，以及已修補角撐能否成為secondary reference | `review_confirmation.py:65-188`、`:208-224`；`corner_brace_repair.py:645-707` |
| Tolerances／validation context | endpoint、connection、collinear、duplicate、parallel angle、projection overlap、maximum width、minimum length、ambiguous connection delta等`GeometryTolerances`值 | `corner_brace_repair.py:170-211`、`:364-589`、`:1022-1125`；replay傳入點`source_exclusion.py:851-860` |
| 全域目前result | 全部Walers、Struts、CornerBraces、corner connections、candidate points、messages、excluded sources、body evidence／assessments與source fingerprint | planning入口`corner_brace_repair.py:827-1125` |
| 全域candidate驗證 | 把candidate暫放回全部corner braces後重建connections，並對全部工程構件做duplicate validation | `corner_brace_repair.py:799-824` |
| ID與套用effects | preferred ID可用性／下一個CornerBrace ID、套用後corner geometry、candidate points、strut attachment、connections與messages | `corner_brace_repair.py:1539`起；replay套用點`source_exclusion.py:1220` |
| 順序與deferred state | 先前repair已改變的current result、pending順序、manual secondary reference deferred pass與無進展終止條件 | `source_exclusion.py:1076-1240`附近 |
| 座標與Review投影 | repair target使用的world／projected座標系、全量problem records及ReviewItems；confirmation可使用另一路`confirmation_result` | `source_exclusion.py:1087-1133`、`:1178-1201` |

難以比對之處有四類：第一，candidate validation目前用全部CornerBraces／Walers／Struts重建connections與duplicate diagnostics；第二，reference eligibility依賴全體ReviewItems、messages與confirmations；第三，第N筆repair的輸入包含前N-1筆repair的輸出；第四，浮點幾何必須依tolerances正規化，raw float equality不可靠。這些因素使跨repair footprint／fingerprint難以安全維護，因此方案 D 刻意把所有預建資料限制在單次planning呼叫內；局部validation則以舊全場validation作逐候選differential oracle。

### `plan_corner_brace_repair()`內部量測

本節仍使用Y05排除`BM29`／`E91`的11筆replay。另一輪warm-cache、低輸出量instrumentation中，11次`plan_corner_brace_repair()`共14.358215秒，平均1.305292秒；前一輪為21.944085秒，平均約1.995秒，顯示wall-clock會受cache／instrumentation影響。以下以14.358215秒run的呼叫結構與比例判斷熱點，不把秒數當固定SLA。

`plan_corner_brace_repair()`本身不呼叫`build_problem_records()`或`build_review_items()`；它只掃描呼叫端已建立的`review_items`。完整problem／ReviewItem成本屬外層replay，planning內的ReviewItem查詢集中在`eligible_repair_references()`。

| 內部步驟 | 呼叫次數 | inclusive時間 | planning占比／結果 | 程式位置 |
| --- | ---: | ---: | --- | --- |
| Subject key／signature／residual／target evidence extraction | 22／11／11／11 | 合計約0.040秒 | 每筆subject不同；不是熱點 | `corner_brace_repair.py:256-445` |
| Reference搜尋與ReviewItem／confirmation查詢 | 11 | 0.070340秒 | 0.5%；每次掃全體corner braces與ReviewItems | `corner_brace_repair.py:645-724`、`:972` |
| Local template抽取 | 715 | 0.030247秒 | 65個primary references × 11次 | `corner_brace_repair.py:481-535`、`:978-986` |
| Waler／Strut relationship frame | 1,177 | 0.012374秒 | 每次107個；只有42組不同frame輸出 | `corner_brace_repair.py:446-479`、`:1000-1008` |
| Template transfer | 30,030 | 0.212487秒 | 每次2,730個；全部產生有限幾何 | `corner_brace_repair.py:536-579`、`:1029-1041` |
| Target evidence validation | 30,030 | 0.915488秒 | 29,697拒絕、333通過；只有1.1%進入下階段 | `corner_brace_repair.py:581-643`、`:1045-1050` |
| Angle difference | 209,307 | 0.427027秒 | inclusive；多數包含在target evidence等上層時間內，不可重複加總 | `corner_brace_repair.py:1022-1027`及geometry helpers |
| Candidate ID | 333 | 0.018622秒 | 通過target evidence後才建立 | `corner_brace_repair.py:732-758`、`:1075` |
| Existing candidate validation | 333 | 12.814017秒 | **89.2%**；333/333通過 | `corner_brace_repair.py:799-824`、`:1106` |
| └ 全場connection rebuild | 333 | 7.058356秒 | **49.2%**；每個candidate重算全部corners × struts | `corner_brace_repair.py:814`、`waler_contact_adjustment.py:616-760` |
| └ 全場duplicate validation | 333 | 5.208364秒 | **36.3%**；每個candidate重跑全部corner pairs | `corner_brace_repair.py:823`、`validation.py:1292-1325` |
| └ temporary result／matching等其餘成本 | 333 | 約0.548秒 | 約3.8% | `corner_brace_repair.py:760-824` |
| Candidate列舉、分組、排序及其他未被子函式包住的工作 | — | 約1.544秒 | 約10.8%；包含上述部分inclusive子項，故只作parent residual解讀 | `corner_brace_repair.py:987-1188` |

每筆planning都從21支Struts的兩端、65個primary templates及兩種transfer mode列舉假設；topology先排除約一半後，實際每筆做2,730次transfer。11筆共30,030次，只有333個通過target evidence，而每筆plan最後都只輸出1個candidate。昂貴的全場validation發生在分組／tier／proximity選出最終candidate之前。

11次之間確認有以下重複：

- `eligible_repair_references()`的65個primary、0個secondary結果11/11完全相同，但仍掃描11次。
- `extract_corner_brace_local_template()`共715次，實際只有65個reference／template結果，每個相同template重建11次。
- `_relationship_frame()`共1,177次，只有42組不同frame輸出；同一frame會在不同reference及不同repair重算。
- 333次duplicate validation的輸出全部是空集合。輸入candidate不同，因此不能直接把「空」快取成永遠成立；但現行呼叫對全部unchanged corner pairs重做檢查，而最後只讀取是否有包含temporary member ID的message。
- 333次connection rebuild幾乎每次完整輸出都不同（332種），但差異主要來自temporary candidate；現行流程仍重算其他既有corners的connection，最後只讀temporary member的matching connection及message。
- Target evidence是11個不同subject，因此不是跨repair相同輸入；candidate geometry與current corner set也會隨前一筆repair套用而變，不能無條件跨repair共用。

### 不改輸入輸出的純效能方向與採用結論

方案 D 採用下列兩項、且只限單次 `plan_corner_brace_repair()`：

1. **候選局部validation。** 現行connection結果最後只檢查temporary member，因此改用相同connection規則只計算temporary corner對目前Walers／Struts的配對；duplicate結果則用相同`_lines_duplicate()`逐一比較temporary corner與既有corners，不重算既有corners彼此。以目前約65～75個corners估算，connection工作可由每candidate約`corners × struts`縮成`1 × struts`，duplicate由`O(corners²)`縮成`O(corners)`。估計可省約11.5～12.3秒，但必須逐候選證明connection唯一性、target Waler／Strut、diagnostics與duplicate判定完全相同。
2. **單次call內預建immutable lookup／索引。** 預建Waler／Strut maps、primary template map、relationship frames、reference member map及方向／anchor索引，消除同次呼叫內的線性查找與重複幾何抽取。已直接量到的helper成本約0.1秒級；若方向／anchor索引可減少30,030次target-evidence測試，估計再省約0.5～1.2秒，但候選列舉、eligibility、ranking與輸出順序必須不變。

以上暫存資料綁定當次傳入的current result、ReviewItems、confirmations與tolerances，呼叫返回即丟棄；不跨11次planning共用，因此不需要判斷repair之間的dependency，也不建立dependency footprint或input fingerprint。合併後Y05本fixture的合理上限約省12～13秒planning；這是工程估計，不是SLA。

**暫不採用：延後validation／第一個通過即停止。** `_show_corner_brace_repair_window()`會在多候選時逐筆列出`plan.candidates`供使用者選擇（`dxf_import/dialog.py:3376-3429`），單一候選時才自動選取（`:3514-3516`）；`commit_corner_brace_repair()`又會重新planning並以候選ID及完整值核對（`dxf_import/review_workflow.py:1183-1205`）。既有tests也明確驗證2筆合法候選及不同template／relationship集合（`tests/test_dxf_corner_brace_repair.py:815-826, 851-892`）。因此planning輸出確實供互動工具列出全部合法候選；找到第一個合法候選即停止會縮小公開候選集合，不是純效能等價改寫。本change不採用此方向，也不自行改變互動產品行為。

### S14／D1A反例根因

S14是handle`D1A`、canonical identity`strut:D1A`的正式Strut，排除前連接`W8`與`W7`。它不是CB66～CB70保存的target Strut，也不是它們保存的reference source。實際因果鏈如下：

1. S14直接支撐4支自動角撐：CB28／`corner_brace:10D0`、CB29／`10D1`連到W7端，CB30／`10D2`、CB31／`10D3`連到W8端。排除S14後這4支失去合法Strut connection並不再成為formal CornerBrace；這項工程依賴合理。
2. Importer用`candidates_by_role["corner_brace"]`的順序從1重新編`CB{index}`，見`dxf_import/importer.py:809-820`。中間少4支後，後續仍存在且幾何相同的references發生display ID位移：CB50→CB46、CB53→CB49、CB56→CB52、CB61→CB57、CB62→CB58。
3. 保存的`CornerBraceRepairReference`同時包含穩定`subject_key`與`member_id`，見`dxf_import/models.py:724-729`。`reconstruct_saved_template_candidate()`以整個dataclass作`primary_by_reference`的exact key，見`corner_brace_repair.py:1229-1233`。五筆repair的source handles、reference幾何與reference connection皆未改，但保存member ID已不存在，所以`selected_evidence is None`並在line 1232回傳`None`。
4. `source_exclusion.py:1205-1214`收到0個match；五筆又沒有manual secondary reference可defer，因此CB66～CB70直接標成`needs_review`。它們沒有走到target identity、template transfer、target evidence或candidate validation；CB71～CB76的參考CB11／CB2／CB1位於消失位置之前，ID未漂移，所以6筆成功preserved。

工程判斷：排除S14後移除實際依附它的CB28～CB31是合理工程結果；repair replay必須確認仍是同一支reference也是合理安全要求。但本例中失敗依賴的是recognition順序產生的display `member_id`，不是reference的source identity、幾何或connection變化。依目前證據，CB66～CB70是安全但保守的false negative；「member ID漂移即needs_review」不是必要的工程幾何依賴，而是目前identity contract的實作依賴。本調查不修改該規則。

另外，`commit_source_exclusion_plan()` 目前在指派 live result後才重驗 confirmations並重建 candidate store；後段若失敗可能形成 partial mutation。`_refresh_result_views()` 則會完整重建畫面並無條件產生大型 debug JSON。這兩項可在不改工程規則下改善。

## Goals / Non-Goals

**Goals:**

- 直接降低單次來源排除中多筆 CornerBrace repair replay的重複 projection成本。
- 以逐候選local-vs-full differential test保護connection、duplicate、eligibility、ranking、候選集合與輸出；所有快取只活在單次planning內。
- 讓 plan在 commit前已包含全部可失敗的衍生資料，使 live state adoption原子化。
- 移除一般排除 critical path上的全場景重畫與 hidden debug serialization。

**Non-Goals:**

- 不新增多選構件、多來源 batch planner、batch impact或 batch persistence。
- 不改 CornerBrace候選生成、ranking、reference priority或 acceptance rule。
- 不快取 DXF entity expansion，不重寫整套 recognition或 application transaction framework。
- 不使用 thread／process，也不設定固定秒數 SLA。

## Decisions

### D1. 完全保留現有單筆 UI 與 workflow入口

`dialog.py::_on_source_exclusion_action` 仍從目前 primary selected `ReviewItem` 建立一份 plan、顯示既有單筆 impact並提交；不新增 selection draft、多選 widget或 batch state。`plan_source_exclusion_for_item()` 仍負責 exclude／restore分支，並沿用既有 canonical source identity、shared-handle與 paired Joist source-atomic規則。

本案可以重構該入口的 refresh呼叫，但不得改變使用者一次只處理一項的操作。UI也不得從紅色樣式、severity或清單位置自動加入其他來源。

**理由**：目前瓶頸在單次 staging內部；維持入口可避免新的 selection state與無關 UI測試，並縮小回歸面。

**Rejected alternatives:**

- 多選 tree或獨立 batch dialog：新增產品行為但不降低一次排除本身的19秒等待。
- UI連續呼叫多次單筆排除：會重跑完整 recognition／replay，且產生中間 live states。

### D2. 方案 D：只加速單次 `plan_corner_brace_repair()`

每筆manual repair仍依既有順序，以當下staged result重新呼叫`plan_corner_brace_repair()`，再依既有規則 reconstruct、驗證與apply。方案 D 不共用不同repair的projection，不沿用舊plan／outcome，也不建立dependency footprint或input fingerprint。所有預建資料只屬於一次函式呼叫，返回後立即釋放。

#### D2.1 候選局部驗證

以candidate-local validation取代`_candidate_passes_existing_validation()`目前對整場CornerBrace的重算，但完全保留既有判斷規則：

1. 用既有temporary CornerBrace與相同Waler／Strut connection規則，只建立該temporary member的connection與messages。
2. 仍要求temporary member恰有一筆合法connection，且其target Waler／Strut與candidate指定值一致；任何涉及temporary member的connection message都拒絕。
3. 用既有duplicate predicate與相同tolerances，把temporary line逐一和每支既有CornerBrace比較；任一pair判定duplicate即拒絕。
4. 不計算既有CornerBraces彼此的connection或duplicate，因現行函式最終只觀察涉及temporary member的結果。

舊全場validation保留為test oracle及保守fallback。Differential test必須在同一result、candidate、target與tolerances下，逐候選比較local與full validation的pass／fail結果；另覆蓋無connection、多重／模糊connection、target mismatch、connection diagnostic、正向／反向duplicate及tolerance邊界。只有全部等價時才能讓production改走local path。

#### D2.2 延後validation／第一個通過即停止：暫不採用

調查結論是`CornerBraceRepairPlan.candidates`不是只供自動replay取第一筆，而是互動工具的完整合法候選集合：

- `dxf_import/dialog.py:3335-3345`取得plan並以空候選顯示失敗。
- `dxf_import/dialog.py:3376-3429`在多候選時逐筆建立Treeview，讓使用者查看Waler／Strut、template、transfer mode與幾何資料後選擇。
- `dxf_import/dialog.py:3514-3516`只有恰好一筆候選才自動選取。
- `dxf_import/review_workflow.py:1183-1205`在commit前重新planning，並核對原plan及current plan中同ID候選的完整值。
- `tests/test_dxf_corner_brace_repair.py:815-826, 851-892`驗證多個template／relationship候選會同時存在。

因此「依排序驗證到第一個通過就停止」會少回傳其他合法候選，改變互動輸出與commit可選集合。本change暫不採用，不調整`CornerBraceRepairPlan` contract；是否另行設計互動候選分頁／按需驗證不在本案決定。

#### D2.3 單次呼叫內預建 lookup、template、frame與索引

在`plan_corner_brace_repair()`入口建立不可變的per-call planning context，至少包含：

- 依canonical identity索引的Waler／Strut對照表。
- primary／secondary eligible references與reference member對照。
- 每個reference只計算一次的template資料。
- 以relationship key索引的Waler／Strut relationship frame。
- target evidence的方向與positional anchor索引；索引只可縮小需比較集合，不得改變匹配predicate、tie-break或排序。

context不得保存到workflow、module global、Project或下一筆repair；其key必須包含函式實際使用的identity／幾何及tolerances。若某計算無法安全索引，維持現行計算；不得為了命中率改eligibility、reference priority、candidate ranking、diagnostics或候選去重。

#### D2共同ordering、輸出與fallback

- 保留manual順序、deterministic secondary-reference deferred pass、preferred ID檢查與無進展終止條件。
- 同一輸入下，`CornerBraceRepairPlan`的subject、residuals、selection mode、全部candidates、candidate IDs、排序、provenance與diagnostics必須與現行實作完全相同。
- 候選局部validation若無法重現舊全場判定，production必須使用舊full validation；索引若不能證明只減少重複計算，就不使用該索引。
- 全部manual decisions完成後，仍由final staged result建立一次完整problems／ReviewItems作plan truth。

**未採用方向：** A（repair-only projection）、B（跨repair dependency footprint）與C（repair input fingerprint／outcome reuse）不納入本change；S14的reference identity問題也不在方案 D 修正。

### D3. `SourceExclusionPlan` 預建全部 commit projection，commit只做guarded state swap

`SourceExclusionPlan` 保持不可變語意，除現有 exclusions、world/result、problems、ReviewItems與replay report外，明確保存：

- `base_revision`
- 經staged result重驗的confirmations
- 由staged result建立的新candidate projection／`CandidatePointStore`
- UI-neutral mutation effects

所有可能拋出錯誤或依賴staged result的運算都在plan期間對獨立物件完成。例如建立新的candidate store，而不是在live store上clear／rebuild。Staging失敗只丟棄plan。

`commit_source_exclusion_plan()` 先檢查base revision與plan payload，然後以reference／scalar assignment採用整份plan並增加一次revision。若現有mutable container不能整體替換，先在外部建好新container；不得在live assignment後繼續fallible rebuild。不可預期assignment例外仍以提交前snapshot rollback作最後防線。

**理由**：prebuild-and-swap縮小partial mutation風險，也確保使用者確認、replay report與實際commit指向同一份staged result。

**Rejected alternatives:**

- 保留先指派result再rebuild candidate store：後段失敗會留下混合狀態。
- 每一步後手工rollback mutable objects：alias容易漏還原，風險高於先建後換。
- 引入通用Unit of Work：只有一個workflow aggregate，不需要大型抽象。

### D4. Workflow回傳UI-neutral effects；Dialog映射為dirty layers

Workflow不引用Tk或`RenderDirty`。Plan／commit回傳UI-neutral `ReviewMutationEffects`（名稱可配合現有model），描述：

- source geometry／bounds是否改變。
- changed／excluded source identities。
- engineering members、problems／ReviewItems、candidate points是否改變。
- selection target／hit index是否失效。
- committed revision。

Dialog依effects：

1. 重建member／candidate／problem等derived layers。
2. 使用`PreviewScene.source_handle_items`更新changed source items樣式。
3. 清理不存在的selection／focus並更新tree／detail／completion projection。
4. 使舊revision／generation的source hit index失效，之後依目前scene lazy rebuild。
5. source geometry與bounds未變時保留目前viewport。

source style所需excluded／issue-level集合必須來自commit前後snapshot的顯示投影；Presentation可diff但不可判斷engineering eligibility。source geometry signature改變、handle index缺漏、canvas item失效、revision不符或dirty dependency不完整時，使用full-scene fallback。Fallback仍優先保留有效viewport。

**理由**：workflow描述「什麼變了」，Presentation決定「如何畫」，符合既有dependency direction並避免重畫Y05數千筆source geometry。

**Rejected alternatives:**

- Workflow直接回傳`RenderDirty`：會讓workflow依賴Presentation。
- 每次排除一律full scene：正確但保留大量可避免工作並重設互動狀態。
- 永不fallback的細粒度patch：index不完整時可能留下stale scene或hit target。

### D5. Debug text是以workflow revision為key的lazy cache

Dialog保存Presentation-only的`debug_payload_revision`與dirty狀態。一般result commit只標dirty；debug panel未顯示時，不呼叫`result.to_debug_dict()`、`json.dumps()`或widget insert。

使用者開啟／切到debug panel或明確刷新時：

1. 取得目前committed snapshot與revision。
2. cache revision不同或dirty才序列化。
3. 完成後再次確認revision；若期間改變，丟棄舊payload並從最新snapshot重建。
4. 更新widget並記錄revision。

Cache只能保存格式化text或debug DTO，workflow不得讀回。序列化或widget更新失敗不得rollback已成功的engineering commit；顯示Presentation error並保持dirty供重試。

**理由**：大型debug JSON對一般來源排除沒有使用者價值，可直接移出critical path。

### D6. 以不必要重算次數與optimized-vs-canonical equivalence驗證

測試提供instrumented projection builder與canonical sequential replay reference，驗證：

- 一次單筆排除只呼叫一次full importer／recognition path。
- 每次`plan_corner_brace_repair()`的temporary candidate不觸發全場既有CornerBrace connection／duplicate重算，per-call context不跨repair存活。
- 同一輸入的每個候選，local validation與舊full validation回傳相同pass／fail；整份plan的候選集合、順序、IDs、provenance與diagnostics相同。
- deferred reference仍重新planning，不會沿用前一筆repair的projection、validation或outcome。
- optimized與canonical path的members、connections、associations、messages、provenance、problems／ReviewItems、completion與replay report等價。
- commit只增加一次revision。
- hidden debug不序列化，安全partial refresh不重建source geometry。

Y05與Y29 fixture regression驗證paired Joist、CornerBrace outcomes與legacy source。Benchmark分開記錄convert、manual replay、final validation、commit、refresh與debug；數字供比較，不設CI固定秒數threshold。

**理由**：工作次數與semantic equivalence可穩定防止回歸；wall-clock受機器、Tk與檔案cache影響。

### D7. 以已封存Waler replay為baseline，追蹤另一個UI change

`resolve-provisional-waler-manually`已封存於`openspec/changes/archive/2026-10-06-resolve-provisional-waler-manually/`，其tasks全部完成。該change歷史上修改`dxf_import/source_exclusion.py`的manual override capture／replay與`dxf_import/review_workflow.py`的Waler repair planning／commit，因此確實碰觸本案同一`replay_manual_overrides()`路徑；它現在是本案必須相容的baseline，不是待rebase的active change。當前Y05有0筆非CornerBrace manual overrides，所以本次量測沒有執行Waler replay分支。

`separate-waler-positioning-from-formal-adoption`目前是active change（4/4 planning artifacts complete、0/19 implementation tasks）。現有proposal／design／tasks把影響範圍放在`dxf_import/dialog.py`的Waler定位、正式採用與Preset UI，並明確不改`manual_overrides`及`waler_engineering_line_formalized`；目前沒有規劃修改`dxf_import/source_exclusion.py`或`replay_manual_overrides()`。兩案會同時碰`dialog.py`，但不是同一段replay loop；若該change之後擴大scope，實作前再重新檢查。

不可建立CornerBrace-only report truth而漏掉Waler、材料或工程線outcome。若整合後contract不能對獨立staged result運作，停止並回報spec／design衝突，不在Dialog補工程邏輯。

## Architecture Alignment

本change **沿用既有Architecture，不修改layer boundary**。

| Layer／子系統 | 本案責任 | 不得承擔 |
| --- | --- | --- |
| Presentation：`dxf_import/dialog.py`、Preview | 單筆確認顯示、effects→dirty layer、viewport／selection、lazy debug | replay target資格、dependency判斷、工程impact推導 |
| DXF application workflow：`dxf_import/review_workflow.py` | 單筆plan、canonical staging協調、revision guard、atomic commit、mutation effects | Tk widget、canvas item、debug panel |
| DXF source lifecycle：`dxf_import/source_exclusion.py` | manual replay ordering、projection lifecycle、report整合 | UI selection、persistence schema |
| CornerBrace repair／validation | 在單次plan內提供candidate-local validation與per-call planning context；維持plan／apply contract | workflow commit、UI refresh、跨repair cache |
| Domain／Algorithms／Infrastructure persistence | 無行為變更；沿用既有contract | 新規則、Solver tuning、schema migration |

Dependency direction維持：

```text
Dialog / Preview
    -> DXFReviewWorkflow
        -> source exclusion replay
            -> corner-brace repair / validation / models
```

`ReviewMutationEffects`不含Tk型別；replay projection不含Presentation state，因此沒有反向依賴。

## Single Source of Truth

- **正式Review truth**：`DXFReviewWorkflow`目前committed的exclusions、world/result、problems、ReviewItems、manual decisions／report、confirmations、candidate store與revision。
- **暫時候選truth**：一份immutable `SourceExclusionPlan`；確認前不能成為live result。
- **Per-call planning context**：只存在於一次`plan_corner_brace_repair()` stack內的可丟棄衍生資料；不得跨repair共用、取代committed Review truth或持久化。
- **Preview／tree／debug**：committed result的只讀projection，以revision／generation對齊，不可回寫工程state。

避免drift的關鍵是：互動式repair與replay共用canonical target／planning helpers；方案 D 只改單次planning內的計算方式，不另定eligibility或縮小候選輸出。最終plan的全量problems／ReviewItems永遠從完成replay後的staged result建立一次。

## Backward Compatibility與Persistence

- 單筆exclude／restore公開入口與使用者流程不變。
- paired Joist shared-root representation不變。
- Waler、材料、工程線與CornerBrace manual override payload／report格式不變。
- 專案仍只保存normalized excluded sources與既有manual decisions；per-call planning context、mutation effects與debug cache都不持久化。
- 不新增schema version或migration；舊專案載入與新結果保存沿用現有格式。

## Risks / Trade-offs

- **[Risk] candidate-local connection漏掉full builder的ambiguity或message語意。** → 舊full validation作逐候選oracle，覆蓋唯一、多重、無connection、target mismatch與diagnostic cases；不等價時fallback full path。
- **[Risk] duplicate pairwise判定與全場validator的message/filter語意漂移。** → 重用相同predicate與tolerances，加入正反向、端點與tolerance differential cases；不得複製另一套門檻。
- **[Risk] 方向／anchor索引漏掉合法候選或改變排序。** → 比較完整plan的候選集合、順序、IDs與diagnostics；索引只縮小計算，不改predicate與tie-break。
- **[Risk] per-call context意外跨repair存活。** → context不掛到workflow／module global，測試確認下一筆repair由新的current result重建。
- **[Risk] Plan攜帶candidate store等資料使暫時記憶體增加。** → 同時只保留目前單筆plan，取消、commit或stale後釋放。
- **[Risk] 局部畫面刷新漏掉style或hit target。** → revision／generation guard與partial-vs-full semantic tests；不安全即full refresh。
- **[Risk] Waler相關change造成replay或Dialog衝突。** → 以已封存Waler replay為baseline；實作前重查active UI change的scope，不複製helper。
- **[Trade-off] 每次排除仍做一次full recognition，Y05不會變成即時操作。** → 本階段只處理manual replay與UI額外成本；geometry extraction cache或background staging另立change。

## Migration Plan

1. 以已封存`resolve-provisional-waler-manually`行為建立目前canonical sequential replay baseline，並重查`separate-waler-positioning-from-formal-adoption`是否擴大到replay path。
2. 先把舊full candidate validation固定為test oracle，加入逐候選differential fixtures，再實作candidate-local connection／duplicate validation；不等價時保留full fallback。
3. 加入per-call Waler／Strut maps、templates、relationship frames與方向／anchor索引，以完整plan differential tests證明候選集合與排序不變。
4. 將confirmations、candidate store與其他fallible projection移入`SourceExclusionPlan`，完成atomic commit tests。
5. 加入UI-neutral effects、partial refresh、viewport保留與full-scene fallback。
6. 將debug serialization改為revision-aware lazy cache。
7. 執行Y05／Y29 regression與非門檻benchmark，確認不必要重算次數與canonical equivalence。
8. 驗證完成後更新`docs/WORKFLOW.md`；不提前將規劃中行為寫成long-term truth。

### Rollback

optimized replay可切回canonical sequential replay helper，資料格式與使用者流程都不受影響。若partial refresh有一致性問題，可先將effects映射為full refresh並保留viewport與lazy debug。兩種rollback都不需persistence migration。
