# Design：人工修補並正式採用暫定圍令工程線

## 閱讀導航

- **P0／現在必讀**：Decision 1「明確 decision 與一般幾何編輯分離」、Decision 2「Workflow 擁有 plan／commit」及 Decision 3「人工線是唯一 formal contact-face truth」；三者決定 authority、Option A 與 transaction boundary。
- **P0／現在必讀**：Decision 4「只替換 exact source 的四類診斷」、Decision 5「從正式線重建 downstream state」及 Decision 11「支撐側與後續尺寸調整」；避免人工修補沿用 provisional 證據或變成全案跳過檢核。
- **P1／實作前閱讀**：Decision 6「來源寬度使用 recognition outcome 的唯一性」、Decision 7「沿用 version 2 optional manual override」及 Decision 8「UI 明確表示正式化意圖」。
- **P1／實作前閱讀**：修改 recovery 時閱讀 Decision 9；修改 confirmation 或 source exclusion 時閱讀 Decision 7、10。
- **P2／需要時再讀**：「相容性與 persistence」、「與進行中 change 的協調」、「Rejected alternatives」及「Migration Plan」。可先跳過 Solver、Global Waler 與 export；本 change 不改那些模組。

## 方案摘要

```text
Dialog pending line
  -> DXFReviewWorkflow 建立 repair plan
  -> pure validation / staged formalization
       * exact provisional Waler
       * finite + minimum-length line
       * explicit manual authority
       * scoped diagnostic replacement
       * downstream rebuild
  -> commit-time revision + fingerprint revalidation
  -> atomic adopt world_result
  -> projection refresh
```

本 change 中：

- **人工正式化 decision（Option A）**：使用者明確把一條通過既有 validation 的候選點或 CAD 工程線宣告為該 Waler 的正式工程線與接觸面；該線不必位於 source envelope 外側邊，且不同於一般 endpoint edit。
- **人工 line authority**：表示 formal line 來自人工修補而非自動 envelope／side finalization；它不代表 terminal identity 或全案問題已解決。
- **Scoped diagnostic replacement**：只移除 exact target source 上已被人工 authority 取代的 envelope／contact-face diagnostics，其他問題仍從目前 facts 重建。

## 決策對照

| Decision | 影響的 spec Requirement | 對應 tasks |
| --- | --- | --- |
| D1. 明確 decision 與一般幾何編輯分離 | 人工修補必須是明確且合格的操作；舊一般人工端點不得被推定為正式化 | 1.x、2.x、5.x |
| D2. Workflow 擁有 plan／commit | 正式化後必須原子重建下游結果 | 2.x、3.x |
| D3. 人工線是唯一 formal truth | 人工採用線成為唯一正式幾何 truth；專用人工修補建立正式接觸線 | 2.x、3.x |
| D4. 診斷取代使用 exact identity allowlist | 只解除被人工裁決取代的問題 | 2.x、3.x |
| D5. Downstream 全量重建而非 patch | 正式化後必須原子重建下游結果；Y29 W14 | 3.x、7.x |
| D6. Width uniqueness 由 recognition facts 決定 | 寬度與材料不得由人工線猜測 | 1.x、3.x |
| D7. Optional manual override 保存明確意圖 | 人工裁決必須可安全保存與重驗 | 4.x、5.x |
| D8. Provisional Waler 使用專用 Apply 語意 | 一般確認不得正式化；候選點／CAD 兩條路徑 | 6.x |
| D9. Changed-content 不轉移 authority | 人工圍令正式化 decision 不得跨內容靜默轉移 | 5.x |
| D10. Confirmation／exclusion 沿用既有 mutation contract | 人工裁決必須可安全保存與重驗 | 4.x、5.x、7.x |
| D11. 人工接觸線重建支撐側與 adjustment baseline | 正式化後原子重建；同側／衝突／無證據；Brace 剛體平移 | 3.x、7.x |

## Context

動機見 `proposal.md` 的「Why」。目前 importer 對 Waler group 先由 `_candidate_from_group()` 形成可顯示 candidate，再由 `_characterize_waler_candidate_envelope()` 建立 envelope facts。Y29 W14 source `58D` 的封閉 LWPOLYLINE 可形成一條 preliminary candidate，但 envelope extraction 回傳兩個完整 interpretations；caller 因 `len(outcome.facts) != 1` 產生 `WALER_ENVELOPE_AMBIGUOUS`，candidate 仍進入 Review 且 `contact_face_state` 保持 `provisional`。

現有 `apply_candidate_point_selection()`／`set_cad_engineering_line()` 已能改寫 WCS 起終點、重新連接構件並記錄 `selection_source`，但它們刻意保留原 recognition diagnostics，也不把 provisional Waler 升為 formal。實測 W14 套用既有 `line_1` 後仍為 provisional 且 `can_import == false`。這說明本 change 需要新增「人工 authority」而不是只放寬現有 candidate edit。

`DXFReviewWorkflow` 是 live Review WCS result、manual decisions、confirmation 與 exclusion 的 authoritative owner；`DXFImportDialog` 只保存 selection、temporary pending line 與 projection。`SourceManualOverride` 已以 role + exact source handles 保存材料、幾何、Waler contact input及 CornerBrace repair optional state，paused Review state version 2 也已允許 backward-compatible optional payload。這些是本設計要重用的 boundary。

## Goals / Non-Goals

**Goals:**

- 在不改自動 recognition 的前提下，增加一條明確、可追溯的人工 Waler engineering-line authority。
- 讓候選點與 CAD 指定線共用同一 validation、atomic commit、diagnostic scope 與 replay contract。
- 維持 live Review single owner、WCS canonical truth、confirmation invalidation 與完成匯入 transaction。
- 讓寬度、材料與 terminal identity 仍由各自既有 authority 決定，不從人工線旁推。

**Non-Goals:**

- 不讓 raw unresolved source 直接建立新 Waler member，不實作 source split 或 polyline Waler。
- 不重寫 envelope／contact-face recognition，也不新增 Solver 欄位或 preference。
- 不把 generic candidate edit 全面改造成 repair framework；只增加 provisional Waler 所需的最小 use case。
- 不順便重構 `candidate_points.py`、manual override 或 recovery 的既有 technical debt。

## Decisions

### Decision 1：明確 decision 與一般幾何編輯分離

新增明確的 runtime authority 欄位，建議在 `Waler` 使用 `engineering_line_authority`，合法值至少為 `automatic` 與 `manual_repair`，default 為 `automatic`。`contact_face_state` 繼續表示 formal／provisional，`selection_source` 繼續表示輸入來自 `manual_candidate_points` 或 `cad_manual`；三者責任分離：

| 欄位 | 回答的問題 |
| --- | --- |
| `contact_face_state` | 這條線現在是否可作為正式工程／接觸線？ |
| `engineering_line_authority` | formal authority 來自自動 finalization 還是專用人工修補？ |
| `selection_source` | 這次線座標由候選點或 CAD 哪一個入口提供？ |

人工正式化只有在 `engineering_line_authority == "manual_repair"` 且 `contact_face_state == "formal"` 時成立。既有 saved state 沒有新 authority 時一律視為 `automatic`，不得從 `selection_source` 推論。

原因：目前 formal Waler 也可做一般候選點／CAD geometry edit；若只看 `selection_source`，舊資料與一般編輯會被錯誤升級。明確 authority 同時讓 capture、replay、UI 與 diagnostics 共用一個 truth。

### Decision 2：由 DXFReviewWorkflow 擁有 repair plan 與 atomic commit

新增 immutable `WalerEngineeringLineRepairPlan`（名稱可依現有命名微調），至少包含：

- baseline `revision` 與 `source_fingerprint`；
- target member ID、role 與 normalized exact source handles；
- canonical WCS start／end；
- input kind（candidate points 或 CAD）；
- staged validation outcome 與會失效的 confirmation IDs。

Workflow 提供 plan／commit use case。Plan 從目前 `world_result` 建立 staged outcome，不修改 live state；commit 再驗 revision、fingerprint、target identity 與 canonical line signature，成功才一次替換 `world_result` 並更新 projection／confirmation。Dialog 只負責 pending selection、warning 顯示、呼叫 workflow 與 refresh。

原因：這符合 `docs/ARCHITECTURE.md` 的 live Review ownership，也能避免 Dialog 先改 Waler、再分別清 message 與重建 connection 的非原子狀態。

### Decision 3：人工線是該 Waler 唯一 formal geometry truth

建立一個 DXF subsystem pure operation（建議新模組 `dxf_import/waler_engineering_line_repair.py`），輸入 current `DXFImportResult`、exact target identity、canonical WCS line、input kind 與 tolerances，輸出完整 staged `DXFImportResult` 或 structured rejection。

operation SHALL：

1. 重用既有 candidate-point／CAD line hard validation；任何通過 validation 的有限線都可採用，不增加「必須落在 envelope 外側邊」的條件；
2. 只替換 exact target Waler 的 start／end、world/local line metadata、candidate selection fields；
3. 設 `contact_face_state="formal"`、`engineering_line_authority="manual_repair"`；
4. 將採用線本身視為接觸面，不再由 envelope 選擇外側面，也不保留另一條 source envelope face 作為 formal line；
5. 不改 source geometry、source handles、role 或 original DXF。

`line_candidates` 可保留作為 Review evidence，但只有 selected line 是正式 truth；Preview style、Project row 與 downstream geometry全部讀取 Waler 的 canonical start／end及 authority，不從 candidates 重新推導。此線的語意是「支撐頂到的接觸面」，不是 Waler 中心線；其 support side 另依 Decision 11 判斷。

選擇專用小模組而非把 policy 直接塞進 Dialog 或 recognition，是因為 manual repair 需要被 live apply、replay、restore 與 tests 共用，但不應改變 automatic recognition core。

### Decision 4：只以 exact source identity 與固定 code allowlist 取代診斷

正式化 operation 只可移除符合全部條件的 message：

- `role == "waler"`；
- normalized `source_handles` 恰好等於 target exact identity；
- code 屬於：`WALER_ENVELOPE_AMBIGUOUS`、`WALER_ENVELOPE_UNRESOLVED`、`WALER_CONTACT_FACE_AMBIGUOUS`、`WALER_CONTACT_FACE_UNRESOLVED`。

包含額外 Waler 或 member handles 的 composite diagnostic不得因「包含 target handle」就被刪除。Connection／association／overlap diagnostics 先依既有 code groups移除舊衍生值，再從 staged formal line 重建；`WALER_SOURCE_OVERLAP`、`WALER_OVERLAP_COMPETITION`、`AMBIGUOUS_WALER_CONNECTION` 等不得列入人工 suppression allowlist。

人工 provenance 優先重用既有 `MANUAL_POINT_SELECTION`／`CAD_MANUAL_LINE_SELECTION` info diagnostics與結構化 authority 欄位，不新增 diagnostic code。這可避免和進行中的 `clarify-dxf-review-diagnostics` 88-code inventory產生不必要衝突；顯示文字可依 authority 投影成「已人工採用為正式圍令」。

### Decision 5：從人工正式線重建 downstream state，不做局部 patch

人工 Waler line 採用後，沿用 candidate editing 已有的 rebuild sequence：

```text
canonical WCS walers
  -> discard provisional-axis terminal evidence
  -> rebuild Strut / Brace terminal topology against the manual contact line
  -> apply existing unique-first precedence and write formal relations
  -> derive support_normal_world from rebuilt relations and the manual line
  -> rebuild double-support candidates
  -> rebuild Column / Beam association
  -> reattach CornerBrace derived fields
  -> duplicate validation
  -> initialize/rebuild Waler contact review baselines
  -> build Review problems/items and projection
```

實作可抽出目前 `apply_candidate_point_selection()` 中已存在的 internal rebuild helper，或由 repair operation呼叫同一 pure pipeline；不得複製第二套 connection／association規則。若抽 helper，只做支援本 change 的最小機械調整，不延伸成 repository-wide refactor。

Waler formalization成功但 downstream member 新增 error、支撐側衝突或無支撐側 evidence 時，formal Waler decision仍提交，錯誤由新 result 的 diagnostics阻擋後續操作或 Review completion。只有 staging／commit 本身失敗才 rollback。這區分「人工接觸線合法但造成需處理的工程關係」與「transaction 沒有成功」。

### Decision 6：Width uniqueness 由 envelope outcome 明確導出

已封存的 `calculate-waler-width-orthogonally` 已讓 `WalerEnvelopeFacts.source_width` 使用兩條 supporting lines 的正交距離；本 change 不再量測另一份寬度。現在 ambiguous envelope outcome 可以包含多個已正交量測的 `WalerEnvelopeFacts`，但 `_characterize_waler_candidate_envelope()` 在 `len(facts) != 1` 時只產生 error，沒有把 width resolution 明確帶到後續。調整 characterization，使 provisional candidate 在不升級 formal 的前提下仍可取得 runtime-only width assessment：

- 無可靠 fact：`unknown`，`source_width = 0.0`；
- 所有可靠 fact 的正交 `source_width` 在既有數值語意下等價：`unique`，採用 canonical equivalent value；
- 存在不等價值：`ambiguous`，`source_width = 0.0`。

建議在 DXF `Waler`／candidate 上保存小型 `source_width_state`（`unique`／`unknown`／`ambiguous`），不持久化完整 envelope facts到 Project／Solver。人工 formalization只消費這個 recognition assessment，不從選線推導 width。`auto_width` material 只在 `unique` 下保留／重算；`unknown`／`ambiguous` 清除 auto result，`material_spec_source == "manual"` 則依既有合法性保留。

原因：只看目前 `source_width` 無法分辨「唯一 400」與「任選到 400」。將 resolution state明確化可避免第二份 width truth。

### Decision 7：沿用 version 2 optional manual override，新增明確 intent flag

擴充 `SourceManualOverride` 的 backward-compatible optional field，建議為 `waler_engineering_line_formalized: bool = False`。當它為 true 時，既有 `geometry_selection_source`、`world_start`、`world_end` 是該 decision 的唯一採用線資料；不再建立一份重複座標 payload。

Capture 只在以下條件成立時寫 true：member 是 Waler、`engineering_line_authority == "manual_repair"`、`contact_face_state == "formal"`，且 geometry source／WCS line 完整。Parser 對缺欄位、非法 role 或不完整 geometry一律視為 false。Replay 對 true 的 Waler override 呼叫專用 formalization operation；不得先 generic replay geometry 再單獨翻 formal flag。

這會增加 optional `manual_overrides` mapping key，但不提升 Review state version 或 Project schema version；舊 reader忽略未知 key，現行 reader對舊 payload使用 default false。若實作查證現有 serializer 不允許 optional key，必須停止並回報，不得改成由 `selection_source` 猜測。

### Decision 8：UI 以同一 pending line、不同 Apply 語意表達明確意圖

保留目前候選點 Tree、Preview temporary line 與「從 CAD 指定工程線」讀取流程。當選取 member 是 eligible provisional Waler，或已由 `manual_repair` 正式化而正在重新採用時：

- candidate section與 CAD button仍提供線的來源；
- Apply action文案改為「採用為正式圍令」；
- Preview detail、warning confirmation與最終確認均顯示完整固定提示：「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」；同時說明不會清除其他獨立問題；
- 按下 action本身就是明確採用意圖；若 validation有 warning，沿用既有 warning confirmation；不另加無資訊量的第二次 Yes／No。

對 automatic formal Waler、Strut、Brace及其他 member，既有「套用選取點」語意不變。已人工正式化的 Waler 可再次進入同一專用 use case，以另一條合法線原子取代舊 decision；CAD line讀入仍只建立 pending candidate，不立即 formalize，使用者必須按專用 Apply。

### Decision 9：Changed-content recovery 不轉移人工 authority

Same-fingerprint Resume與 `EXACT_MATCH` 沿用 manual override replay並重新驗證，可恢復 formal effect。Changed-content compatible recovery在 candidate-based result上不得呼叫 formalization replay：

- exact role + source identity仍存在且是可處理 Waler subject：summary entry=`requires_review`，不套用 geometry／suppression／authority；
- exact identity消失、role改變或 subject不可處理：entry=`disabled`；
- geometry-only rebind、相同 member ID或相近 line不得轉移。

若 changed candidate同 exact source已自動 formal，candidate-based automatic result照常保留；舊人工 decision仍列 `requires_review` 而不覆寫它。Recovery summary label建議為「<Waler ID> 人工正式工程線」。

### Decision 10：Source exclusion、confirmation 與重新採用沿用既有 lifecycle

Source exclusion snapshot會攜帶完整 manual override；source active時decision才可生效，排除期間不參與任何 engineering state。Restore exact source後由 replay重新驗證，禁止使用排除前的 connections／diagnostics。

正式化 mutation將 target Waler及因 rebuild改變的 related members交給既有 confirmation invalidation signature。本 change 不提供取消人工正式化或恢復 provisional／automatic 的操作；若選錯線，已是 manual formal 的 Waler 可再次使用同一專用 use case採用另一條合法線，新的 atomic decision取代舊 decision，不得建立兩筆並存 authority。普通 endpoint edit仍不得被推定為新的正式化 decision。

### Decision 11：人工接觸線重建支撐側與 adjustment baseline

人工正式化只裁決 contact line，不裁決 support side。採用成功後必須先丟棄所有以 provisional axis 建立的 terminal evidence／relations，以人工線作為 Waler canonical line重新執行既有 terminal topology與 connection rebuild；只有這次重建產生的 current evidence可判斷 `support_normal_world`。

程式調查結果如下：

- `dxf_import/waler_contact_face.py:1129` 的 `build_member_terminal_evidence()` 建立 unique／competing terminal evidence；`dxf_import/waler_contact_face.py:1345` 的 `resolve_waler_contact_faces()` 實作既有 unique-first side precedence。這些 recognition core規則不需修改。
- `dxf_import/waler_contact_adjustment.py:469` 的 `support_side_normal(waler, struts, braces, tolerances)` 以 `_world_line(waler)` 取得 canonical Waler line，並以 relation attachment到構件本體的方向判斷同側、衝突或無 evidence；因此當人工線已寫入 Waler canonical world line、且 relations已重建後，該函式可直接接受人工線，不需 envelope boundary輸入。
- `support_side_normal()` 本身不攜帶完整 unique／competing classification，所以不得把舊 provisional relations直接餵入它來宣稱符合 unique-first。正確順序是先沿用既有 topology／connection rebuild完成 unique-first relation authority，再用它從 current formal relations產生 `support_normal_world`。若實作 discovery顯示無法沿用此順序而必須更改 recognition precedence，應停止並回報，不得在本 change 改寫核心工程規則。
- `dxf_import/waler_contact_adjustment.py:517` 的 `_waler_outer_line()`只供自動實體 envelope選外側面；人工 Option A不得呼叫它另選外側面，因為人工線本身就是接觸面。

若 authoritative evidence全在人工線同一側，`support_normal_world` SHALL 指向該側。若 authoritative evidence分布兩側或完全沒有可靠 evidence，`support_normal_world` SHALL 為 `None`；人工 formal line仍成立，但 `plan_waler_contact_adjustment()` 沿用既有 `WALER_SUPPORT_SIDE_UNKNOWN` 原子阻擋，禁止背填／寬度調整猜測方向或留下部分變更。

人工正式化完成下游重建時，必須以新的人工 contact line重新初始化 `WalerContactReviewState.baseline_contact_start/end`，並以重建後連到該 Waler的 formal Brace重建 `BraceAdjustmentBaseline`。之後調整該 Waler背填或寬度時，沿用已封存 `rigidly-translate-braces-on-waler-adjustment` 的既有 rigid-translation solver；支撐側 unknown時整次 adjustment在 planning階段阻擋，Waler、Brace、review baseline與manual override全部保持提交前狀態。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer responsibility 或 dependency direction**。

| Layer／component | 本次責任 | 不得負責 |
| --- | --- | --- |
| `DXFImportDialog`／Preview | 顯示 eligibility、pending line、專用 Apply 文案與 workflow outcome | 判斷 formal authority、刪 diagnostics、直接修改 WCS result |
| `DXFReviewWorkflow` | 建立／提交 repair plan、revision／fingerprint guard、confirmation invalidation、single owner mutation | Tk widget、Solver result commit |
| `waler_engineering_line_repair.py`／pure operations | eligibility、line validation、formal contact-face authority、scoped diagnostic replacement與 staged rebuild orchestration | UI、Project persistence、自動 recognition winner、另選 envelope 外側面 |
| Recognition／contact-face modules | 提供 provisional facts、automatic unique-first outcome及已正交量測的 width evidence | 消費 UI decision、改寫既有 precedence或替人工線另選外側面 |
| Manual override／recovery | capture、parse、replay與 recovery classification | 由 geometry proximity猜測正式化意圖 |
| Project／Solver boundary | 只在 Review completion後消費既有 Waler row | 新增 manual-repair欄位或重新判斷 contact face |

Dependency仍為：

```text
DXF Presentation
  -> DXFReviewWorkflow
  -> repair / candidate / validation pure operations
  -> DXF models / recognition facts
```

Presentation不反向成為 engineering truth；Recognition不依賴 Workflow或Dialog。正式人工 decision的 live single source of truth是 `DXFReviewWorkflow.world_result` 中 Waler canonical line + authority；paused single source of truth是 version 2 `manual_overrides` 中 exact identity、既有 WCS geometry與 explicit flag。兩者透過同一 capture／replay operation轉換，避免平行邏輯。

## 相容性與 persistence

- `Waler.engineering_line_authority`與 `source_width_state` 使用有 default的 runtime fields，舊 debug／mapping資料缺欄位時保持既有 automatic semantics。
- `SourceManualOverride.waler_engineering_line_formalized`是 optional key，default false；不提升 Project schema或Review state version。
- 既有 `manual_candidate_points`／`cad_manual` state沒有 flag時只重播一般 geometry，不會 retroactively升級 Waler。
- `to_project_row()`不增加欄位；人工 formal Waler仍輸出既有 Start／End／material contract。
- Solver不讀 authority或 source width state，只讀完成Review後的正式 Project row。
- Rollback只需停止寫入新 optional flag並還原專用 operation／UI；舊保存檔中的未知 optional key不影響舊版核心 Project資料。

## 與已完成 change 的協調

實作順序固定為：已封存 `calculate-waler-width-orthogonally` → 已封存 `rigidly-translate-braces-on-waler-adjustment` → 已封存 `clarify-dxf-review-diagnostics` → 本 change。前三者已是 main spec與目前程式基線，不得重新套用舊 delta或覆寫其結果。

- 寬度：`source_width_state` 只分類既有正交量測後的 `WalerEnvelopeFacts.source_width`，不新增平行的 width helper或 finite-endpoint量測。
- Brace：人工正式化後重建 formal `BraceAdjustmentBaseline`，後續接觸調整直接沿用既有 rigid-translation與 atomic failure semantics。
- 診斷：`clarify-dxf-review-diagnostics` 已於 2026-10-06 封存且 16／16 tasks完成。本 design不新增 diagnostic code，僅重用既有 manual-selection info code並改變特定 raw diagnostic是否存在。重疊檔案為 `dxf_import/models.py`、`dxf_import/validation.py`、`dxf_import/dialog.py`、`tests/test_dxf_review_layout.py`、`tests/test_dxf_review_workflow.py`及`tests/test_dxf_module_boundaries.py`；不得覆蓋其 problem projection、known-code inventory、白話 formatter或重新引入 raw code顯示。

其他 active Solver changes不與本 change共享工程 contract；不得因同時進行而修改 Solver candidate或scoring。

## Risks / Trade-offs

- **[Risk] 人工正式化誤清 composite／其他來源診斷** → 使用 role + exact normalized identity + 四 code allowlist；含額外 handles 的 message保留，並以 Y29 overlap／terminal regression鎖定。
- **[Risk] generic manual geometry被誤視為正式化** → explicit runtime authority + optional persisted flag；缺欄位永遠 false，不從 `selection_source`推論。
- **[Risk] formal line與 downstream connection形成兩份 truth** → 專用 operation輸出完整 staged result並走同一 rebuild pipeline，禁止 Dialog局部 patch。
- **[Risk] ambiguous envelope錯誤寬度延續自動材料** → recognition產生 `source_width_state`；非 unique時將 auto material清除，manual material保留。
- **[Risk] source exclusion／Resume後沿用 stale diagnostics** → replay從 fresh recognition result套用decision，再全量 rebuild；不序列化 derived connections或suppressed message清單。
- **[Risk] changed-content geometry-only rebind錯移 authority** → recovery planner把decision獨立分類，changed content從不自動 replay，exact subject存在也只列 `requires_review`。
- **[Risk] W14 formal後使用者誤以為全案可匯入** → UI impact文字與 preserved independent blockers；Y29 regression明確斷言其他 blockers仍使 `can_import == false`。
- **[Risk] 人工接觸線成立但仍沿用 provisional relations／Brace baseline** → 正式化 staged rebuild先清除舊 evidence，再依人工線重建 terminal topology、`support_normal_world`、Waler contact review與formal Brace baseline。
- **[Risk] support side unknown時仍移動 Waler或Brace** → 沿用 `WALER_SUPPORT_SIDE_UNKNOWN` planning error並驗證整次 adjustment state不變。
- **[Trade-off] 不支援 raw unresolved source建立 Waler** → 保持本次 use case與既有 Review member identity相容；完全未形成 member的 guided recognition另立 change。

## Rejected Alternatives

### 只要 `selection_source != auto` 就自動 formal

拒絕。既有 formal／provisional Waler都可能保存一般 candidate／CAD geometry edit，舊 paused state也沒有正式化意圖；自動推論會造成相容性與工程安全問題。

### 將 `WALER_ENVELOPE_AMBIGUOUS` 降為 warning

拒絕。這會讓所有 ambiguous source在沒有人工判斷時也通過，直接破壞目前保守失敗規則。

### 人工選線後刪除該 Waler 的全部 error

拒絕。Overlap、terminal identity、connection與association是獨立工程問題；正式線 authority不能取代它們。

### 由系統自動選最長 envelope interpretation

拒絕。這仍是未經工程規格支持的自動 winner policy，且無法表達使用者想採用目前 provisional chord或CAD線的需求。

### 把完整 envelope facts寫入 Project或Solver schema

拒絕。它們只供 DXF Review recognition／width assessment，正式Project仍只需要既有Waler row；新增schema會擴大 persistence與Solver scope。

### 另建獨立 repair state store

拒絕。會與 `DXFReviewWorkflow.world_result`／`manual_overrides`形成第二份 truth；現有 lifecycle已提供合適 owner與replay boundary。

## Migration Plan

1. 先加入 model default、manual override parser round-trip及legacy false-semantics tests，確保舊 state不會自動 formalize。
2. 建立 pure repair operation與width resolution contract，先以 synthetic cases鎖定 exact diagnostic scope與material behavior。
3. 接入 Workflow plan／commit與full rebuild，再加入 atomic failure、confirmation invalidation、source exclusion／restore tests。
4. 接入Pause／Resume與recovery classification；驗證same-fingerprint preserved、changed-content requires-review／disabled。
5. 最後接入Dialog專用Apply文案與Y29 W14 end-to-end regression，確認其他Y29 blockers仍在。
6. 執行DXF focused suite、boundary tests及OpenSpec verification；完成後更新`docs/WORKFLOW.md`的long-term manual repair lifecycle。

Rollback時移除專用入口與operation，保留parser對optional flag的容忍；不需要Project migration或Solver資料回復。
