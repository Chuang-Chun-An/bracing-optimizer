# Design：主視窗專案操作的選單化與狀態投影

## 閱讀導航

- **P0／現在必讀**：D1「選單列取代頂部 Project toolbar」、D2「Project 單選視窗先決定 Open 目標」與 D4「完整重新投影使用 conditional menu command」；三者定義主要 UI 結構與安全順序。
- **P0／現在必讀**：D5「刪除目前專案使用 New 的同一 mutation guard，並採 filesystem-first、runtime-commit-second transaction」；此流程避免 New 已被正式 guard 阻擋時仍可刪除，也避免刪除失敗時先破壞目前 Project。
- **P1／修改狀態投影時閱讀**：D3「由既有正式 state 派生 title、Project warning與待儲存提示」及「Single Source of Truth」；三類label只讀`DxfStatus`，不得用dirty推導DXF提示。
- **P1／修改命令 wiring 時閱讀**：D6「快捷鍵與 menu state 共用 handler」及 Backward Compatibility；保留 Save／Discard／Cancel、software information 與 `projection_stale` contracts。
- **P2／需要時再讀**：Risks／Trade-offs 與 Migration Plan；只有遇到 Tcl/Tk menu index、刪除失敗或發佈回退時需要深入閱讀。可先跳過 DXF Review、Solver、Domain、材料與 persistence schema文件。

## 方案摘要

本 change 中的「選單列」是 Windows 視窗內容上方顯示「檔案／專案／說明」的 Tk menu bar，不是需要自繪的 OS title bar。Windows title caption 繼續只顯示應用程式名稱、目前 Project 與 dirty `*`。

```text
Window title:  開挖支撐系統幾何資料輸入介面 - 南側開挖案 *

Menu bar:      檔案 | 專案／專案 待儲存／專案 ⚠ | [⚠ 重新整理畫面] | 說明
                                                      conditional --------^

Workspace:     既有主分頁／次分頁／左右 PanedWindow
Bottom row:    既有 context_toolbar（保留）
Preview:       既有 PreviewNavigationToolbar（保留）
```

頂部 Project toolbar 整列移除。File menu 負責 Project 檔案生命週期；Project menu 負責目前 Project／DXF 維護；Help menu 保留 software information。Open 先由 UI-only Dialog回傳一個repository Project name，再進入既有navigation guard。所有狀態標籤都由正式 runtime state投影，不保存第二份狀態。

## 決策對照

| Decision | 解決的問題 | 對應 spec／主要 tasks |
| --- | --- | --- |
| D1. 選單列取代頂部 Project toolbar | 移除重複命令與橫向擁擠，但保留工作區 controls | `main-window-project-controls`「主視窗專案操作必須集中於選單列」；menu construction tasks |
| D2. UI-only Project 單選視窗先決定 Open 目標 | 移除 Combobox 後仍維持target-before-guard | 新 capability「Open 必須使用 Project 單選視窗」及 modified navigation Requirement；Dialog／guard tests |
| D3. Title、Project warning與待儲存提示皆由正式state派生 | 避免移除快速狀態後產生另一份Project或DXF truth，並讓pending-save不依賴dirty | 「Project 選單必須投影目前專案狀態」、「視窗標題必須成為精簡狀態來源」；三類projection tests |
| D4. Recovery command依`projection_stale`動態存在 | 正常時不占空間，異常時仍一眼可見且可執行 | 「完整重新投影入口只在stale時顯示」；transaction／menu projection tests |
| D5. Delete重用New mutation guard，再採filesystem-first、runtime-commit-second | New被正式guard阻擋時Delete亦不可執行；刪除失敗保留目前Project | 「刪除目前專案必須明確且安全」；guard parity／failure injection／success reset tests |
| D6. Menu與shortcut共用handlers、焦點範圍與state policy | 防止兩種入口的guard、編輯值處理與outcome漂移，也避免子視窗按鍵誤觸主視窗命令 | 「File選單與快捷鍵必須使用相同命令」；wiring／focus／active-editor tests |

## Context

動機與已確認版面見[proposal.md](./proposal.md)。目前`main.py`的`_build_project_menu_and_toolbar()`同時建立File／Help menus及頂部`ttk.Frame`；Frame內保存Project Combobox、Open／Save actions、長狀態文字與永久存在但通常disabled的`reproject_button`。工作區下方另有`context_toolbar`，右側Preview另有`PreviewNavigationToolbar`；兩者責任不同且本change保留。

目前Project repository listing已集中在`_project_case_json_files()`及`_project_case_name_from_path()`，同時支援managed `<name>/project.json`與legacy `<name>.json`。Open command從`project_case_var`讀目標，確認有效後才呼叫`_guard_unsaved_project_changes()`。這個先後順序是既有transaction保障；新Dialog只取代目標選擇介面，不改guard或load。

目前`_update_window_title()`已由`current_project_path`與`project_dirty`產生caption；`_refresh_project_status_display()`已從`dxf_asset_status_report`產生詳細內容。`_refresh_projection_guard_ui()`則只切換toolbar button state。本change保留前兩份正式projection來源，將最後一項改成menu command可見性。

Project delete目前以selector目標運作，具repository path containment檢查、managed／legacy判斷、managed DXF提示與filesystem deletion，但沒有呼叫New所用的`_ensure_mutation_allowed()`。新流程把目標固定為`current_project_path`、重用相同mutation guard與安全檢查，並新增成功後runtime reset transaction。

主視窗表格的inline editor在`main.py:7191-7250`建立，只有`Return`、Combobox selection或`FocusOut`會進入`_finish_edit()`；`_finish_edit()`在`main.py:7253-7388`處理解析、驗證、必要確認、提交與後續projection。選單Save則在`main.py:1862`直接連到`_save_current_project()`，該handler（`main.py:2732-2744`）沒有明確完成或取消`editing_entry`。Task 1.4已確認menu Save及root-scoped`Ctrl+S`本身不觸發`FocusOut`。D6因此採用明確的pre-save completion gate，而不依賴焦點事件順序。

## Goals / Non-Goals

**Goals:**

- 讓主視窗Project操作只有一個可見的頂部結構，並保留所有既有command能力。
- 讓Open的目標選擇與navigation guard有單一、可測試的先後順序。
- 讓Project name、dirty、DXF attention與projection recovery都由正式state派生。
- 讓刪除目前Project在filesystem失敗時零runtime副作用，成功時不留下失效path。
- 以focused Presentation tests證明menu、Dialog、shortcut與transaction wiring，不要求完整Tk event loop才能驗證核心決策。

**Non-Goals:**

- 不建立通用command framework、menu DSL、全域hotkey manager或Project repository abstraction。
- 不拆分`main.py`的其他責任，也不重寫現有Project persistence／load services。
- 不更改下方context toolbar、Preview toolbar、Notebook或Dialog整體視覺主題。
- 不改DXF warning的底層狀態判定、Project schema、Solver或Domain。

## Decisions

### D1. 選單列取代頂部 Project toolbar

將現有builder縮減為主選單建構與shortcut binding；可以保留原method name以降低測試及外部extension衝擊，或在同一change內以小型wrapper保留舊名稱。它建立並保存：

- `menu_bar`
- `file_menu`
- `project_menu`
- `help_menu`
- recovery command目前是否已投影的Presentation cache

File menu固定順序：

```text
新建專案              Ctrl+N
開啟專案…             Ctrl+O
----------------------------
儲存專案              Ctrl+S
另存新專案…           Ctrl+Shift+S
----------------------------
結束
```

Project menu固定順序：

```text
專案與 DXF 狀態…
----------------------------
重新連結 DXF…
----------------------------
刪除目前專案…
```

Help menu保留「軟體資訊」。不再建立頂部Frame、Combobox、quick status variable或Project toolbar buttons。`context_toolbar`在`_build_ui()`中的建立與pack順序保持不變；移除頂部Frame後，`main_paned`自然取得釋放的垂直空間。

**Rejected：把Project controls搬到自繪Windows title bar。** 這需要取消原生window decoration、重做拖曳／縮放／最小化／DPI與可及性，與需求中的「跟檔案、專案、說明放一起」不相稱。

**Rejected：保留空白toolbar只隱藏buttons。** 空Frame仍占高度，且保留兩層頂部結構，無法達成目的。

### D2. Project 單選視窗只回傳目標，不負責navigation

新增小型Presentation Dialog，例如`bracing_optimizer/presentation/dialogs/project_selection_dialog.py`。Dialog constructor只接收不可變project names及optional current name；`open()`同步回傳selected name或`None`。Dialog本身：

- 不讀filesystem、不load Project、不執行dirty guard。
- 使用單選Listbox或Treeview顯示既有repository names。
- 有效selection才enable Open；double-click與Enter共用confirm handler；Escape／window close共用cancel handler。
- repository空時顯示可理解的empty message並保持Open disabled。
- optional current name若仍存在可作初始selection；不存在時可選第一筆，但不在使用者confirm前觸發任何操作。

Main Open handler每次執行時先呼叫現有repository listing，將names傳給Dialog。只有Dialog回傳非空name後，Main才再次以`_project_case_path(name)`確認目標仍存在，然後呼叫既有`_guard_unsaved_project_changes()`；guard回報`PROCEED`才呼叫`load_project_case(name)`。

這個第二次target validation處理Dialog開啟期間的filesystem race，且必須發生在dirty guard前，避免目標已消失卻仍要求使用者Save／Discard。

**Rejected：Dialog直接呼叫load。** 這會把navigation transaction分散到Presentation child window並難以證明target-before-guard。

**Rejected：使用`filedialog.askopenfilename()`。** 既有Project repository同時支援managed與legacy layout，任意file picker會繞過既有listing與命名contract。

### D3. Title、Project warning與待儲存提示皆由正式state投影

Windows title caption繼續由`_project_display_name()`與`project_dirty`產生，不保存新的name／dirty變數。移除`project_quick_status_var`後，所有Project名稱與dirty更新仍只經`_update_window_title()`。

Project top-level label只由`dxf_asset_status_report.status`派生，採三類互斥projection：

- `MANAGED_COPY_MODIFIED`、`SOURCE_MODIFIED`、`MISSING`、`RELINK_REQUIRED`、`BINDING_REQUIRED`、`LEGACY_NO_STATE`、`INCOMPATIBLE`、`GEOMETRY_COMPATIBLE` -> `專案 ⚠`
- `RUNTIME_READY`、`VERIFIED_PENDING_SAVE` -> `專案 待儲存`
- `READY`、`NO_DXF`或`report is None` -> `專案`

「待儲存」是獨立於warning與window-title dirty `*`的DXF提示；即使`project_dirty=False`，只要status是`RUNTIME_READY`或`VERIFIED_PENDING_SAVE`仍顯示`專案 待儲存`。使用者點「專案與 DXF 狀態…」時仍由現有`_refresh_project_status_display()`與`project_asset_status_var`建立完整內容；menu label不得反向修改report，也不另存一份warning truth。

既有enum定義於`bracing_optimizer/infrastructure/project_persistence.py:64-76`；`main.py:2518-2531`提供目前狀態文字。正式分類如下：

| `DxfStatus` | 現行意義 | 是否需要使用者處理 | 頂層Project label |
| --- | --- | --- | --- |
| `READY` | managed DXF存在，且內容hash／size與Project metadata一致，可作為正式來源 | 否 | `專案` |
| `RUNTIME_READY` | DXF已匯入並可於目前runtime使用，但尚未隨Project Save建立managed copy | 需要Save以持久化，但目前可工作 | `專案 待儲存` |
| `VERIFIED_PENDING_SAVE` | relink候選已驗證並可用，但新來源尚未經Save寫入managed copy／metadata | 需要Save以完成持久化 | `專案 待儲存` |
| `MANAGED_COPY_MODIFIED` | managed copy無法驗證，或其hash／size與metadata不一致 | 是，來源完整性異常 | `專案 ⚠` |
| `SOURCE_MODIFIED` | managed copy缺失，原始來源仍在但內容已不同，不能自動修復 | 是，需重新連結或確認來源 | `專案 ⚠` |
| `MISSING` | managed copy缺失，且原始來源不存在、不可讀，或自動修復失敗 | 是 | `專案 ⚠` |
| `RELINK_REQUIRED` | Project有既有DXF import state，但沒有可用managed asset | 是，需重新連結後才能恢復完整DXF能力 | `專案 ⚠` |
| `BINDING_REQUIRED` | 候選DXF無法唯一重建所有構件綁定，或沒有足夠的可綁定資料 | 是，需使用者處理綁定 | `專案 ⚠` |
| `LEGACY_NO_STATE` | 舊Project有Solver結果但缺少DXF import／binding state | 視是否需要DXF匯出而定；若要維持DXF能力則需處理 | `專案 ⚠` |
| `INCOMPATIBLE` | 候選DXF與已保存構件／Solver資料不相容 | 是，需換檔或修正資料 | `專案 ⚠` |
| `GEOMETRY_COMPATIBLE` | 候選DXF幾何可對應既有構件，現行文字為「幾何相容，等待確認」 | 是，仍需確認才能完成relink | `專案 ⚠` |
| `NO_DXF` | Project沒有建立DXF關聯；系統仍允許不依賴DXF的使用情境 | 否，除非使用者主動需要DXF功能 | `專案` |

分類依據是status本身表達的處理類型，而不是`can_export`或dirty：需要修復／確認的異常與能力缺口使用`⚠`；可正常工作但必須Save才能持久化的狀態使用`待儲存`；正常／無DXF則不附加提示。

Dirty調查結果如下：

- 正常成功路徑會mark dirty：一般relink在`main.py:2877-2894`先採用`VERIFIED_PENDING_SAVE`，再呼叫`_mark_project_dirty()`；paused Review relink在`main.py:2952-2970`採用report後mark dirty；新DXF Review在`main.py:6092-6103`建立`RUNTIME_READY`後mark dirty。
- 但兩種status都不是與dirty一起atomic commit。一般relink會在`main.py:2878`先寫入report，並於`main.py:2879`刷新status，直到`main.py:2894`才mark dirty；若中間refresh失敗，外層error handling不回滾report，可能留下`VERIFIED_PENDING_SAVE`＋`dirty=False`。
- `RUNTIME_READY`會在`main.py:6098-6100`先寫入report，再於`main.py:6102`執行可能刷新UI的workflow transition，最後才於`main.py:6103`mark dirty；中途失敗沒有整體rollback，因此也可能留下`RUNTIME_READY`＋`dirty=False`。
- 狀態型別本身不承載dirty invariant；`runtime_report()`與`accepted_relink_report()`只建立`DxfAssetStatusReport`（`bracing_optimizer/infrastructure/project_persistence.py:628-657`）。既有tests亦明確建立`RUNTIME_READY`＋`project_dirty=False`作為no-op／rollback基準，例如`tests/test_dxf_review_workflow.py:1049-1055`及`tests/test_project_persistence.py:1044-1048`。

因此不能把dirty `*`視為這兩個pending-save status的必然替代提示；D3直接使用status顯示`待儲存`。Status先設定、dirty後標記的非原子問題不影響本mapping，但仍是已知transaction問題；依proposal記錄，另立change處理，本change不修改。

Project menu command state同樣由正式state派生：刪除只在`current_project_path`通過repository target validation時enable；`projection_stale`時依既有guard停用New／Open／Save／Save As／Relink／Delete等mutation入口，Project status、Help、Exit與recovery仍可用。

**Rejected：把完整DXF summary放入window title或top-level menu label。** 內容過長且會重新產生窄視窗擁擠；詳細資訊已有正式Dialog入口。

### D4. 完整重新投影使用conditional top-level command

`projection_stale`是唯一truth。Presentation提供`_sync_main_menu_projection()`或等價小函式，負責：

1. 更新Project top-level label。
2. 更新File／Project command state。
3. 當`projection_stale=True`且recovery command不存在時，在Project與Help之間插入top-level command。
4. 當`projection_stale=False`且command存在時移除它。

Menu insertion以固定邏輯位置及可驗證label處理，不依賴其他menu內部items。可保存一個`_reprojection_menu_visible`布林值作渲染cache，但每次sync都以`projection_stale`為權威；cache不一致時重建或校正menubar，而不是改正式state。

`_mark_projection_stale()`在記錄error後sync menu；`_reproject_all_from_committed_state()`成功清stale後再次sync，失敗路徑保持command。原`_refresh_projection_guard_ui()`可改為呼叫menu projection helper或保留名稱作相容wrapper，避免擴張call sites。

**Rejected：把recovery放進Project submenu。** Stale狀態會鎖住大量操作，入口必須在異常發生時直接可見，避免使用者猜測所在位置。

**Rejected：固定顯示disabled recovery command。** 這只是把原toolbar clutter搬到menu bar，違反已確認的conditional visibility。

### D5. Delete採filesystem-first、runtime-commit-second transaction

New在`main.py:2770-2781`先執行未儲存變更navigation guard，再由`_reset_to_new_project()`呼叫`_ensure_mutation_allowed()`。共用mutation guard定義於`main.py:467-475`，目前只明確阻擋：

- `cad_ack_unresolved_event_id is not None`：CAD event已套用但ACK尚未成功完成。
- `projection_stale is True`：正式state已commit但UI projection失敗，必須先完整重新投影。

Solver operation執行中**不是**這個guard的條件；`solver_operation_registry`只在特定資料mutation時做invalidate／adoption控制。DXF Review開啟中也**不是**這個guard的條件；`dxf_dialog_active`在`main.py:5943-5951`目前只暫停CAD event polling。Dirty本身則由`_guard_unsaved_project_changes()`處理，使用者Cancel、Save／Save As取消或儲存失敗會停止New，但它不是`_ensure_mutation_allowed()`中的mutation狀態。

Delete必須直接重用New所呼叫的同一個`_ensure_mutation_allowed()`，不得複製條件或另增Solver／DXF Review等新規則。這個method目前可由delete flow重用；若實作時發現無法在filesystem mutation前安全呼叫，必須停止並回報。未來若New的共用guard新增條件，Delete會因共用同一guard自然同步。Delete target只來自`current_project_path`，不得從Open Dialog selection、第一筆repository item或舊selector cache推測。流程如下：

```text
validate current path inside project_cases_dir
  -> invoke the same _ensure_mutation_allowed() used by New
  -> build deletion confirmation details
  -> user confirms explicit destructive action
  -> prepare complete blank Project runtime outcome (fallible work)
  -> delete validated managed directory or legacy JSON
  -> atomically adopt blank unnamed clean outcome (plain assignments)
  -> project all UI from new committed outcome
```

確認訊息明列dirty狀態；Delete不套用Save／Discard／Cancel navigation guard，因為「先Save再刪除」沒有保護價值且會增加反直覺流程，但仍必須套用與New完全相同的mutation guard。明確Delete confirmation本身就是丟棄目前runtime內容並刪除durable Project的授權。

所有可能失敗的blank outcome準備，例如default inventory與blank DXF report，必須在filesystem delete前完成。Filesystem delete失敗時不commit outcome。Delete成功後的runtime commit只做plain reference／scalar assignment；若後續UI projection失敗，正式state維持blank unnamed clean Project並進入既有`projection_stale` recovery，而不是復原已刪除filesystem target或保留失效path。

Managed target沿用既有containment規則：`project_cases_dir/<name>/project.json`刪除整個該Project directory；legacy target只允許`project_cases_dir/<name>.json`。任何resolved path不符合這兩種shape都拒絕。

**Rejected：Delete成功後保留舊runtime及current path。** 下一次Save可能重建已刪除Project或對不存在path操作，且title／status會宣稱一個不存在的durable Project。

**Rejected：先reset runtime再刪filesystem。** Delete失敗會使使用者失去目前工作區，違反failure zero-side-effect。

### D6. Menu與shortcut共用handlers與state policy

Menu items的`accelerator`只負責顯示；root另建立實際key bindings。不得使用`bind_all`或process-global hook。每個binding使用薄wrapper，先確認目前focus widget的`winfo_toplevel()`就是主視窗root，再呼叫與menu command完全相同的handler並回傳`"break"`，避免Tk預設行為或重複觸發。若DXF Review、Support／Waler Solver或其他child `Toplevel`取得焦點，wrapper不得觸發主視窗New／Open／Save／Save As。主視窗表格的inline `Entry`／`Combobox`仍屬root，因此可接收shortcut。

可用一個Presentation helper先判斷command是否依目前state允許，再呼叫handler；Menu state與shortcut wrapper都消費同一判定。至少涵蓋：

- `Ctrl+N` -> New handler
- `Ctrl+O` -> Open Dialog handler
- `Ctrl+S` -> Save handler
- `Ctrl+Shift+S` -> Save As handler

當主視窗表格inline editor尚未確認時，Save、Save As、`Ctrl+S`與`Ctrl+Shift+S`必須先通過同一個active-editor completion gate，再進入既有save handler。此gate不得依賴`FocusOut`自然發生，而要明確使用與既有`_finish_edit()`相同的解析、validation、必要確認、commit與post-processing規則。

Task 1.4的真實Tk characterization結果：

- 使用顯示中的Tk menu post／invoke執行Save callback時，focus仍是`Entry`，沒有發生`FocusOut`；Save當下model仍為舊值，pending文字仍留在editor，editor沒有被destroy。
- root-scoped`Ctrl+S`由focused Entry產生時，root binding handler會執行，但focus仍是該Entry；按鍵本身不移動focus，因此**不會觸發`FocusOut`**。
- 這與程式結構一致：`main.py:7243-7249`只在Return、Combobox selection與FocusOut完成編輯，而`main.py:1862`／`main.py:2732-2744`的menu Save沒有主動處理editor。

已選定方案A，completion gate回傳明確的success／abort結果：

1. 沒有active editor時直接進入既有Save或Save As。
2. 有active editor時先讀取pending文字，沿用`_finish_edit()`的table定位、解析、validation、材料規格staging／確認、commit與projection規則；不得複製一套較弱的validation。
3. 提交成功或值為no-op時才關閉editor並繼續既有save workflow。合法且有變更的值必須先進model，確保本次payload包含新值。
4. 驗證失敗或既有edit completion未成功時，顯示既有錯誤／確認結果、保留editor及pending文字供修正，並中止本次Save／Save As。不得呼叫persistence、不得開啟Save As命名流程，檔案與進入gate前的dirty狀態都維持不變。
5. 若edit已成功提交，但後續既有Save／Save As被使用者取消或發生失敗，已提交的edit仍留在model並維持dirty；只套用既有save outcome，不回滾已完成的cell edit。

目前`_finish_edit()`會先destroy editor才驗證，且沒有回傳completion outcome。實作可抽出／重用共同的edit completion核心或增加可回報結果的安全路徑，但必須保留一般Return／selection／FocusOut的既有規則，並確保Save失敗分支不destroy editor。Menu與shortcut只呼叫同一個高階Save／Save As command，不得各自實作gate。

Bindings只掛在主視窗生命週期，不使用`bind_all`、process-global hook或外部dependency。

**Rejected：只顯示accelerator文字但不bind。** 這會向使用者宣告不存在的行為。

## Single Source of Truth

| 資料／狀態 | 唯一truth | Presentation projection |
| --- | --- | --- |
| 目前Project identity | `current_project_path` | window title、delete enabled state、Dialog initial selection |
| 未儲存狀態 | `project_dirty`／`project_dirty_reason` | title `*`、delete confirmation文字 |
| 可開啟Project清單 | 每次command取得的repository listing | Project selection Dialog rows |
| DXF狀態 | `dxf_asset_status_report` | `專案`／`專案 待儲存`／`專案 ⚠`、status Dialog內容 |
| UI是否需要完整重建 | `projection_stale`／`projection_error` | recovery command存在性、mutation menu states |
| Open目標 | Dialog一次性回傳值，經Main重新驗證 | 不持久化、不成為目前Project直到load commit |

Dialog rows、menu label、enabled state與`_reprojection_menu_visible`都只是projection cache；任何refresh都必須能從上表的正式truth重建。

## Architecture Alignment

本change沿用既有Architecture，不修改layer direction。

- **Presentation／`main.py`**：負責menu composition、shortcut binding、Project repository names投影、command state、title、warning與transaction orchestration。
- **Presentation Dialog**：只負責顯示不可變names及回傳一次性selection，不讀Project payload、不判斷dirty、不呼叫Application。
- **Application**：既有Project load／save、hydration與state mutation outcomes不變；Delete blank outcome可重用既有`ProjectStateMutationOutcome`資料邊界，但不得把Tk state加入Application。
- **Infrastructure**：既有Project path layout與filesystem操作規則不變；本change不新增repository格式。
- **Domain／Algorithms／Solver**：不受影響。

依賴方向維持：

```text
Main Presentation
  -> Project Selection Dialog (Presentation-only)
  -> existing Application Project services
  -> existing Infrastructure persistence/filesystem boundary
```

## Backward Compatibility與Persistence Impact

- Project JSON、managed DXF、legacy Project支援與schema完全不變。
- 已保存Project不需migration；Open Dialog使用既有repository listing，因此可同時開啟managed與legacy targets。
- Save／Save As、New、Open load、DXF relink、status與software information handlers保持既有正式語意。
- UI操作習慣有刻意變更：不再從常駐Combobox先選Project；改為每次Open時在modal Dialog選擇。
- 既有extensions或tests若直接讀`project_case_var`、`project_case_selector`、`open_project_button`、`reproject_button`或`project_quick_status_var`需更新；這些是Presentation widgets，不是durable contract。
- Rollback不需data migration：可恢復原toolbar及selector wiring；Project資料、current state與persistence格式不需轉換。

## 重要替代方案

- **只調整toolbar spacing／button寬度**：拒絕。仍保留menu與toolbar的重複資訊層級，且長狀態在窄視窗仍可能碰撞。
- **把全部Project操作塞進單一Project menu**：拒絕。File lifecycle與Project／DXF maintenance責任不同；保留File慣例可降低學習成本。
- **以動態Project submenu列出所有Projects**：拒絕。Project數量增加時menu過長，也難以呈現empty state、keyboard selection與未來合理的Dialog資訊。
- **新增完整Project管理中心**：拒絕。搜尋、排序、批次刪除與metadata超出本change。
- **在window title顯示完整DXF狀態**：拒絕。內容過長且與既有status Dialog重複。

## Risks / Trade-offs

- **[Risk] 使用者找不到移除後的常用Save** -> File menu使用標準順序並提供實際可用的`Ctrl+S`／`Ctrl+Shift+S`。
- **[Risk] Tcl/Tk動態menu index因插入recovery command而漂移** -> 只在固定top-level位置插入／移除，保存menu references，並以label／presence測試驗證；command state不使用易漂移的裸index作唯一identity。
- **[Risk] Open Dialog期間Project被外部刪除** -> Dialog回傳後、dirty guard前再次解析並驗證target；失效時不進guard。
- **[Risk] Project warning或待儲存提示分類漂移** -> 以明確enum allowlist及涵蓋全部status的parameterized tests固定三類label；不得用dirty或反向排除推導。
- **[Risk] Save前edit validation失敗卻仍寫檔** -> completion gate必須在payload建立、Save As命名及persistence前回報abort，保留editor並驗證save service未被呼叫。
- **[Risk] Delete含dirty內容造成資料遺失** -> 確認文字明列dirty與不可復原；未確認不做任何事，且不提供模糊的預設accept。
- **[Risk] Delete成功後UI refresh失敗** -> filesystem成功後正式runtime一定先採用blank unnamed outcome，再使用既有`projection_stale` recovery；不得保留deleted path。
- **[Trade-off] Open由一個click增加為menu加Dialog selection** -> 以`Ctrl+O`、initial selection、Enter與double-click降低操作成本，換取較乾淨的常駐版面。

## Migration Plan

1. 先新增Project selection Dialog及headless selection tests，不切換現有Open入口。
2. 建立File／Project／Help menu composition、shortcut binding與derived command-state helpers，保留原toolbar直到focused wiring tests通過。
3. 將Open切換為Dialog target selection，執行navigation guard focused tests，確認target-before-guard。
4. 實作Project warning、conditional recovery command與delete-current transaction，逐組執行projection及failure tests。
5. 移除頂部Project toolbar及其widget state，確認context toolbar、Preview toolbar與所有tab labels不變。
6. 更新`docs/WORKFLOW.md`已過時的toolbar／Open selector描述，執行focused及完整regression與OpenSpec verification。

Rollback只需恢復原Project toolbar與selector orchestration、移除新Dialog及menu projection；不需要Project資料migration。若實作發現目前Project delete無法在filesystem成功後以plain runtime commit安全採用blank state，應停止在delete wiring切換前並回報，不得降低failure semantics或保留失效path。
