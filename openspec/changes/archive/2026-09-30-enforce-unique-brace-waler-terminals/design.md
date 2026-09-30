# Design

## 閱讀導航

- **P0 現在必讀**：Decision 1「terminal evidence → contact face → member verdict 的單向資料流」；這是避免循環依賴並解決 B15 一邊成功、一邊失敗的核心。
- **P0 現在必讀**：Decision 2「正式狀態由完整 connection 推導，不新增持久化旗標」；說明 unresolved 如何留在 Review、又不形成第二份 truth。
- **P0 現在必讀**：Decision 3「Candidate Points 只消費完整 verdict」；避免 P02／P07 繞過 Waler identity 歧義。
- **P1 實作前閱讀**：Decision 4、5；修改 diagnostics、Review rendering、Project conversion 或 lifecycle 時必讀。
- **P2 需要時再讀**：Risks、Migration Plan 與 Rejected Alternatives；可先跳過 CornerBrace 內部計分、Solver 與 persistence 細節，因為本 change 不修改它們。

## 方案摘要

目前 `build_member_terminal_evidence()` 已能找出每個 terminal 的唯一 evidence 或 ambiguity issue，但 `_apply_terminal_resolutions()` 逐端更新 geometry，之後 importer 又把可取得的單端 identity 寫入 `committed_connections`。新方案保留既有候選計算，先讓每一筆唯一 terminal evidence 支援其特定 Waler 的 contact-face finalization，再建立 Brace member-level 完整性判定。只有 start、end 各有唯一 evidence、兩端 Waler identity 不同、兩支 selected contact faces 已正式完成、各自與 Brace 軸有合法有限交點且提交後長度合法時，才一次提交兩端；其他情況兩端皆不提交，來源軸線只留作 Review evidence。

```text
terminal candidates
  -> unique terminal evidence（ambiguous 端不產生 evidence）
  -> Waler contact-face finalization
  -> Brace member-level verdict（不得回饋前兩階段）
  RESOLVED  -> atomic endpoints + pair connection -> Candidate Points -> formal row
  UNRESOLVED -> source axis + diagnostics       -> evidence preview -> no formal row
```

## 決策對照

| Decision | 解決的問題 | 對應 Spec | 對應 Tasks |
| --- | --- | --- | --- |
| 1. 單向 evidence／contact-face／verdict 與 atomic commit | W16 唯一端仍可支援接觸側，但 W18／W19 ambiguous 端不可；Brace 不再部分正式 | 「Terminal evidence 必須單向支援 Waler contact-face 判定」與「延伸結果必須一致更新正式 Brace 連接」 | 1.1、1.2、2.1、2.2 |
| 2. 由 pair connection 推導 formal／unresolved | 避免新增第二個可漂移的狀態或 persistence 欄位 | 「延伸失敗不得改變可靠 recognition 軸或提交不完整 Project」 | 2.2、3.2 |
| 3. Candidate Points 只消費完整 verdict | P07 是幾何候選但不能替 W18／W19 選 identity | 「Review 與人工端點操作必須沿用同一連接語意」 | 2.3、3.1 |
| 4. diagnostics 保留完整競爭 identities | Review 能說明為何未採用 P02／P07 | 「多解問題列出競爭 identities」 | 2.1、3.1 |
| 5. active-source rebuild 重算、不保存 winner | 刪 W18 可變唯一，復原後須再變 ambiguous | 「排除競爭 Waler 後變成唯一」與 Y29 requirement | 2.4、3.3 |

## Context

動機見 `proposal.md` 的 Why。現況的重要事實如下：

- `dxf_import/waler_contact_face.py::build_member_terminal_evidence()` 以 terminal 為單位，對 direct 或 axis-extension candidates 排序；在最近位置數值等價或落入 ambiguity tolerance 時產生 `TerminalTopologyIssue`，不建立該端 evidence。
- `dxf_import/recognition.py::_apply_terminal_resolutions()` 目前只要某端有 evidence 就可能更新該端；因此一端唯一、另一端 ambiguous 時，staged geometry 會混合 resolved endpoint 與 source-supported endpoint。
- importer 由 `candidate.waler_terminal_source_handles` 建立每支 member 的 `(FromWaler, ToWaler)`；現況允許 tuple 只有一端有值，再由 `connect_components_to_walers()` 保留部分 connection。
- `dxf_import/candidate_points.py` 會建立及推薦 initial start／end point；若未收到明確完整 verdict，來源端點仍可能看似已選定。
- CornerBrace 的既有模式是先列舉完整關係，最佳兩案落入 ambiguity boundary 時只產生 diagnostic，不建立 `CornerBraceConnection`。本設計沿用「多解不提交正式 relationship」的原則，但不共用 CornerBrace 的幾何計分實作。

本 change 中：

- **terminal evidence**：一個 Brace terminal 與特定 Waler source identity 的候選／已解析幾何證據。
- **member-level verdict**：由同一支 Brace 的兩端 evidence、issues 與 finalized Waler faces 推導出的本次 staged 結果；只有 `resolved pair` 或 `unresolved`，不允許 partial formal。
- **source-supported axis**：來源辨識支持、可供 Review 顯示的暫存 geometry，不等於 formal Brace。
- **formal Brace predicate**：兩端 Waler member IDs 都非空且互異，且 endpoints 來自同一個成功的 member-level verdict。

## Goals / Non-Goals

### Goals

- 在既有 terminal candidate 與 contact-face pipeline 內建立 Brace pair-level transaction boundary。
- 讓 geometry、connections、Candidate Points、diagnostics、Review 與 Project conversion 消費同一 verdict。
- 對 Y29 B15 在 duplicate Waler 存在／移除／復原時產生 deterministic、可回歸的結果。
- 保持 Strut terminal finalization 的現況，避免把 Brace 的 pair constraint 套到 Strut。

### Non-Goals

- 不重寫 Brace outline centerline 或 Waler envelope recognition。
- 不合併 W18／W19，不替使用者建立 winner policy。
- 不新增 persistent unresolved collection、Project 欄位或 Solver DTO。
- 不把 CornerBrace option scoring 抽象成通用引擎。

## Decisions

### Decision 1：terminal evidence、contact-face 與 member verdict 維持單向依賴

先維持 `TerminalTopologyOutcome` 的 terminal evidence／issues。唯一且合法的 terminal evidence 先交給 Waler contact-face finalization 作 member-side evidence；即使同一 Brace 因另一端失敗而最終 unresolved，該唯一端 evidence 仍有效。ambiguous terminal 只有 issue／competitor provenance，不建立指向任一競爭 Waler 的 side evidence。contact-face finalization 完成後，才以 Brace source identity 分組建立 member-level verdict；verdict 不得回頭新增、移除或改派 terminal evidence，也不得改變 Waler contact-face outcome。

member-level verdict 成功條件必須同時滿足：

1. start 與 end 各恰好一筆唯一 evidence；
2. 任一端沒有 blocking terminal issue；
3. 兩端指向不同 Waler source identities；
4. 兩支 Waler 都有 finalized contact resolution；
5. source axis 與兩個 selected faces 各自有合法有限交點，且提交後長度合法。

只有五項全數成立才一次寫入兩個 staged endpoints 與 pair identities。任一 Waler 尚未產生 finalized selected contact face、任一 selected face 與 source axis 沒有合法有限交點，或提交後長度不合法，都直接得到 unresolved／blocking。任一項失敗時，不寫入任何單端 endpoint 或 connection；保留原始 source-supported axis，並將該 Brace 加入 blocked set。既有交點函式仍是端點 authority；不得為 Y29 加入「直接取 P04／P06 中點」分支。

這個 verdict 應是 runtime immutable value，資料至少包含 member source identity、status、兩端 evidence／resolved points、pair Waler source identities 與 failure issues。它屬於 `dxf_import` recognition runtime，不進入 Domain、Project 或 persistence。單向順序的 source of truth 分別是：terminal candidate cardinality 決定 evidence；evidence 加 Waler envelope facts 決定 contact face；contact faces 加兩端完整性決定 verdict。

**替代方案：**維持逐端更新，只在 UI 加警告。拒絕，因為 geometry、connection、Candidate Points 與 Project conversion 仍會各自看到不同程度的「正式」結果。

### Decision 2：正式狀態由完整 pair connection 推導，不新增持久化狀態

Importer 必須對每支 Brace 明確傳遞 verdict：

- resolved：`committed_connections[brace.id]` 只包含兩個非空、互異的 Waler IDs；member geometry 已由同一 verdict 一次更新。
- unresolved：明確放入 `blocked_connection_members`，且不得讓 downstream 走 legacy nearest-Waler fallback；pair connection 為空或不建立，但 downstream 必須能辨認這是 authoritative unresolved，而不是「尚未計算」。

`Brace` 是否 formal 由完整 pair connection predicate 推導，不另存 `is_formal`／`is_unresolved` 欄位。Review 可保留該 Brace object 作來源幾何預覽，但 rendering、connection summary 與 project conversion 都必須使用相同 predicate。`to_project_rows()` 即使被防禦性呼叫，也只可輸出 formal Brace；正常 completed-import gate 仍會因 blocking problems 而先拒絕整次 staged import。

為區分「沒有 committed entry，允許 legacy fallback」與「authoritative unresolved，禁止 fallback」，API 應使用明確 mapping membership／verdict，而不是只判斷 tuple 內容；不得讓 unresolved Brace 因空值再次進入 `resolve_brace_waler_connection()`。正式 production import path 必須對每支 Brace 都提供 verdict，並以 integration test 證明不會落入 legacy nearest fallback；fallback 只保留給沒有 staged recognition contract 的既有獨立呼叫者。

**替代方案：**在 `Brace` 新增持久化 `connection_status`。拒絕，因為狀態可由 pair connection 與 diagnostics 推導，新增欄位會擴大 serialization、pause/resume 與相容性範圍，並可能形成第二份 truth。

### Decision 3：Candidate Points 與 manual replay 不得成為 identity resolver

Candidate Point builder 接收完整 verdict 或等價的 authoritative committed pair：

- resolved Brace 可依兩個 resolved endpoints 建立 recommended／selected points。
- unresolved Brace 可保留 source points 與競爭 intersection evidence供預覽，但 `recommended_*`、`selected_*` 不得宣告其中任何點為 formal adoption，亦不得回寫 pair connection。

manual endpoint replay 維持既有順序，但不保存舊 Waler identity。replay 後以目前 active sources 與相同 direct rule 從重播幾何重新推導 identities，再通過同一 pair completeness validation。幾何點相同不代表 Waler source identity 唯一；因此 W18／W19 重疊時，點選 P07 不會自動指定其中一支。

**替代方案：**以使用者點選的最近 Waler 當作明確選擇。拒絕，因為現有 override contract 只保存幾何端點，沒有保存 source-bound Waler identity，無法可靠 replay 或在 restore 後判斷失效。

### Decision 4：沿用 error code 家族，擴充結構化 provenance

terminal 層沿用 `AMBIGUOUS_WALER_CONNECTION` 與 `AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION`；pair incomplete 沿用既有 Brace blocking validation。每個 ambiguity issue 必須保留：

- Brace source handles／後續可投影的 display ID；
- `terminal_name`；
- 經 canonical normalization 的所有 competing Waler source identities；
- relation kind（direct 或 axis extension，可由 error code 或 evidence 表達）。

Importer／Review projection 只轉譯這份資料，不重新以距離找 competitors。若現有 `ValidationMessage.member_ids` 不足以同時承載顯示 ID 與 source identities，優先沿用 `source_handles` 加結構化 topology evidence；只有確認無法無損投影時才新增通用 runtime diagnostic field，不建立 Y29 專用 code。

**替代方案：**把 duplicate Waler overlap warning 當成唯一 blocker。拒絕，因為 terminal uniqueness 必須適用於所有同位多解，即使未達相鄰 change 的一般 overlap qualification。

### Decision 5：rebuild 只依目前 active sources 重算

Source exclusion／restore 後，既有 recognition rebuild 重新產生 envelope facts、terminal evidence、contact resolutions 與 member verdict。不得保存先前 W18／W19 的 winner 或 pair connection：

- 排除 W18，若 W19 唯一、W19 selected formal contact face 已完成且另一端完整，verdict 可變 resolved；B15 端點由既有 Brace 軸線／selected face 有限交點函式計算，Y29 fixture 預期結果在 `endpoint_tolerance_mm` 內等價於 P07。
- 復原 W18，最近位置重新出現兩個 identities，verdict 回到 unresolved；先前 staged pair、recommended point 與 confirmation 必須失效。

此設計與 `detect-waler-overlap-errors` change 的邊界是：該 change 提供一般 overlap qualification／diagnostics；本 change 直接從 active Waler identities 判斷 Brace terminal cardinality，且不複製 overlap ratio。由於兩個 change 共用 terminal competitor identities／diagnostic provenance contract，開始本 change 的 implementation 前必須先確認該格式已定案或相關 change 已合併；這是格式相容性的前置 gate，不代表 Brace verdict 依賴 overlap qualification 才能運作。

**替代方案：**偵測 exact duplicate 後先把 W18／W19 視為同一支 Waler。拒絕，因為 source identities 代表兩個使用者可獨立排除／復原的構件，合併會隱藏輸入問題並破壞 provenance。

## Architecture Alignment

本 change 沿用既有 Architecture，不改變 dependency direction。

| Layer／子系統 | 責任 | 不得承擔 |
| --- | --- | --- |
| `dxf_import` recognition／geometry | 依序建立 terminal evidence、Waler contact faces、member verdict、atomic geometry 與 diagnostics | Project 或 Solver 規則，或由 verdict 回饋重算 contact face |
| `dxf_import` importer／validation | 將 verdict 投影成 formal pair／blocked Review problem，控制 completed import | 重新計算候選距離或另選 Waler |
| Presentation／Review | 依 verdict／formal predicate 區分正式與 unresolved 預覽，顯示競爭 identities | 以顯示順序、點選位置或 proximity 修復關係 |
| Project conversion | 防禦性排除非 formal Brace | 保存 DXF terminal evidence |
| Domain／Algorithms | 無程式變更；只接收合法 Project rows | 解讀 DXF source handles 或修補 unresolved Brace |

formal Brace 的 single source of truth 是本次 staged recognition 的 member-level verdict；pair IDs、formal Brace geometry、Candidate Points 與 formal diagnostics 都是其投影。Waler contact face 的 source of truth 則是先前完成的 terminal evidence 加 Waler envelope facts，不受後續 verdict 回饋。Waler source identity 與 Waler member ID 的 mapping 仍由 importer 在所有 Walers 建立後一次完成，不移入 Presentation。

## Backward Compatibility 與 Persistence

- 不新增 Project schema、DXF saved-review schema 或 Solver input 欄位，因此不需要 migration。
- 已完整且唯一連接的 Brace 輸出格式不變；Y05 既有 direct／extension 成功案例必須維持。
- 舊呼叫者未提供 authoritative verdict 時，legacy helper behavior 可保留；production import path 必須明確提供 resolved 或 unresolved 狀態，避免 fallback。
- Pause／Resume、manual override 與 source exclusion 仍保存既有資料；resume 後由 active sources 重建 verdict，不保存 runtime object。

## Risks / Trade-offs

- **[Risk]** 將單端成功也視為整支 unresolved，Preview 可能比現在少一個已校正端點。→ **Mitigation**：保留兩端 evidence 與競爭交點作可追溯預覽，但以不同樣式及無 recommendation 表示，避免冒充正式 geometry。
- **[Risk]** `result.braces` 目前同時承載 Review object 與 Project source，formal predicate 若只套在一條路徑會再度 drift。→ **Mitigation**：建立單一 helper／contract，Project conversion、Waler connection summary、Candidate Points 與 renderer 都測同一 predicate。
- **[Risk]** Strut 與 Brace 共用 `_apply_terminal_resolutions()`，原子化時可能誤改 Strut。→ **Mitigation**：保留 Strut 現有逐端流程，只在 `role == "brace"` 使用 pair-level gate，並執行既有 Strut regression。
- **[Risk]** 若把整支 Brace unresolved 誤解為所有 terminal evidence 都無效，W16 會失去本來唯一的側向證據。→ **Mitigation**：以 B15 regression 固定 W16 可消費 start evidence、W18／W19 不可消費 ambiguous end，並禁止 verdict 回饋 contact-face。
- **[Risk]** 與 `detect-waler-overlap-errors` 同時實作時可能修改相同檔案。→ **Mitigation**：先合併／同步 overlap change 的 terminal diagnostics contract，再實作本 change；若其 artifact 改變 source identity 形態，回頭核對本 design，而非複製另一份 detector。
- **[Trade-off]** 本 change 不提供人工指定 W18 或 W19 的 repair，因此保留兩支時無法完成匯入。→ 這是刻意的 fail-safe；新增 source-bound identity selection 需另立規格。

## Migration Plan

1. 先確認 `detect-waler-overlap-errors` 的 terminal diagnostic／identity provenance 格式已定案或已合併，再加入 characterization tests，固定 B15 start evidence 對 W16、ambiguous end 不支援 W18／W19，以及唯一 W19 交點在 `endpoint_tolerance_mm` 內等價於 P07。
2. 依單向資料流實作 contact-face 後的 member-level verdict 與 atomic apply，保留既有 error codes及 Strut 路徑。
3. 讓 importer connection mapping、Candidate Points、Review projection 與 Project conversion 改由同一 verdict／formal predicate驅動。
4. 加入 provisional contact face、無有限交點、非法長度、production no-fallback、exclusion／restore、input order、manual replay 與 Y05／Strut regression。
5. 實作完成後才更新 `docs/DOMAIN.md`，記錄 formal Brace 的唯一兩端 hard constraint；同步更新 `docs/WORKFLOW.md`，記錄單端失敗時整支 Brace unresolved 的 connection lifecycle。

Rollback 可整體移除 pair-level gate 與其投影，因為沒有 persistence migration；既有 saved review 仍可由原流程重建。若部署後發現非預期 fixture 大量變成 unresolved，應保留 blocking 診斷並回滾程式，不得臨時改成 first-match。
