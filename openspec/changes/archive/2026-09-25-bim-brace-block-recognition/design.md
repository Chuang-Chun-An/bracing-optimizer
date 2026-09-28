# Design

## Context

見 [proposal.md](proposal.md)。目前 BIM special recognition 只由 `_route_component_like_strut_block()` 對 Strut role root `INSERT` 啟用；`BlockMemberRecognitionInput` 已攜帶 `role`，pure service 的 WCS primitive、fragment、topology、whole-axis 與 deterministic normalization 大部分不依賴 Strut downstream model，但 entry point、router、candidate mapping 與 diagnostic wording仍是 Strut-specific。

Brace root `INSERT` 目前不進入此路徑，而是在跨 group merge 前後交給一般 `_candidate_from_group()`。Y05 的 Brace layer 目前形成 25 個 root `INSERT` source：一般路徑產生 23 支 formal Brace，全部使用局部 `parallel_edges_midline`，並伴隨多個 `AMBIGUOUS_CENTERLINE`、2 個 recognition failure，以及大量 Waler connection errors。將目前 local working tree 的 pure whole-block service直接套到這 25 個 source，只得到 8 個 `recognized`、17 個 `BIM_BLOCK_CONFLICTING_WHOLE_AXES`；因此單純把 `role == "strut"` gate 改成 `role in {"strut", "brace"}` 並不安全。

`bim-strut-outline-topology` 已完成實作、strict verification、同步 main spec 並封存；其 current code 與 main spec 是本 change 的 Strut baseline。apply 時仍必須先核對該 baseline 與 regression tests 可重現，且不得在本 change 複製、弱化或重新解釋已成立的 topology contract。

## Goals / Non-Goals

**Goals:**

- 重用一套 pure root-local geometry／topology evidence，為 Strut 與 Brace 提供 role-aware policy。
- 讓一個可靠的 BIM Brace root source只建立一支完整、deterministic formal Brace。
- 將 fragment recognition outcome與 downstream Waler connection outcome分開，保留清楚 diagnostics。
- 沿用 root handle provenance、Review workflow、source exclusion／restore、manual replay與Project conversion。

**Non-Goals:**

- 不以 Waler connection 成功與否作為幾何 winner score或 ambiguity tie-breaker。
- 不放寬 `GeometryTolerances`、不新增未命名數值 threshold，也不調整 endpoint-to-Waler snap。
- 不保證所有 Y05 Brace root自動成功；真正缺乏唯一 geometry evidence者仍應 blocking。
- 不修改 CornerBrace、Waler recognition、Strut已確認語意、Project schema或 Solver。

## Decisions

### 1. 先完成 Strut topology change，再把 pure service收斂為 role-neutral core

`dxf_import/block_member_recognition.py` 繼續擁有 WCS primitive normalization、fragment extraction、topology member、axis consolidation、width evidence與 deterministic outcome。實作時將目前 `recognize_component_like_strut()` 內真正與 role無關的分析收斂為一個 internal role-neutral entry；Strut與Brace只提供薄的 policy／mapping，不各自複製 fragment演算法。

既有 Strut entry可保留為 compatibility wrapper，或在同一小範圍內重新命名並同步所有 internal callers；選擇以最小 diff且不影響已驗證 Strut tests為準。`BlockMemberRecognitionInput.role` 必須實際參與 policy dispatch，避免它只是一個未使用欄位。

role-neutral refactor 必須保留以下 Strut invariants：

- `whole_axis` 與 `representative_width` 是相關但可獨立成立的 evidence；不得由工程軸存在反推材料寬度，也不得為了保留寬度而改變可靠工程軸。
- 當 root `INSERT` 存在可驗證的 same-source outline topology 時，topology outcome 是 authoritative boundary。longitudinal rails 只能依該 topology provenance 配對；geometry-only parallel pairing 不得跨 outline 配對，一般 fallback 也不得覆寫已成立的共同軸或 blocking ambiguity。
- 當 root `INSERT` 完全沒有可用 topology evidence 時，維持既有 open parallel-edge／fragmented component fallback；不得只因沒有 closed contour 或 end-cap 就直接拒絕辨識。
- `source_width` 只能由唯一可靠的 component-envelope evidence建立。有效 envelope 必須先通過 closed outline／connected contour provenance、connected and unbranched topology、whole-axis longitudinal coverage、component length、slenderness與既有 width eligibility；topology containment 只在這些已合格 envelopes 中選擇唯一外包絡，不能只因某 contour 位於最外層就視為物理構件寬度。
- open detail rails、局部 parallel pair與沒有 companion provenance的 rail spacing不得決定或覆寫 `representative_width`。axis 唯一但 envelope 不唯一時，recognized outcome保留 axis並使用既有 unknown width `0.0`，後續仍交給 Material Review。
- `maximum_component_width_mm = 600` 只維持 recognition eligibility；不得成為 `source_width`、材料尺寸或 default。350／400／500 mm僅是 regression cases，各合法 envelope必須保留自身實際寬度，不得新增 350 mm或其他固定寬度假設。

**理由：** 現有 pure data types與幾何 helpers 已具可重用性；複製成 `brace_block_recognition.py` 會立即形成兩套 topology truth。

**替代方案：** 直接讓 Brace呼叫 `recognize_component_like_strut()`。拒絕，因為函式與 terminal messages 都表達 Strut語意，且 Y05 characterization證明直接開 gate會把17個 source立即變成 ambiguity，沒有 role-aware審核邊界。

### 2. Brace router與 Strut router共用 orchestration，但維持 role-correct output

將 `_route_component_like_strut_block()` 最小泛化為只接受明確支援 role的 root `INSERT` router。它在 `_merge_related_line_groups()` 前逐 root執行，確保 source scope不被其他 root合併：

```text
root group
  ├─ role not in {strut, brace} → existing path
  ├─ non-INSERT / missing root handle → existing path
  └─ role-aware pure recognition
       ├─ not_applicable → same unmerged root → general recognition
       ├─ recognized → one role-correct candidate
       └─ failed / ambiguous → terminal role-correct problem, no fallback
```

Brace recognized candidate使用既有 `_Candidate` 與通用 `bim_block_whole_axis` recognition method，不新增 Project model。terminal outcome沿用既有 diagnostic codes時，`ValidationMessage.role`與顯示文字必須是 `brace`／斜撐；不得出現「支撐構件」或產生 Strut ReviewItem。

**理由：** Router只做 outcome translation，geometry interpretation仍只有一個 owner；role與後續 member constructor則維持清楚。

**替代方案：** 在 importer的 Brace branch另寫一次路由。拒絕，因為會重複 terminal fallback與message mapping，未來 Strut／Brace容易漂移。

### 3. Brace使用既有 whole-source credibility gates，不以單一 topology member存在就自動成功

Brace root的「一個圖塊一支斜撐」是 source boundary，不是 automatic recognition permission。pure policy必須同時使用已確認的 whole-source evidence：dominant longitudinal direction、root extent coverage、transverse alignment、compatible width、topology provenance與 reliable-runner ambiguity。

Brace沿用 `bim-strut-outline-topology` 成立後的具名 tolerance與既有 credibility settings，包括 `bim_minimum_longitudinal_evidence_ratio`、`minimum_projection_overlap_ratio`與 `ambiguous_candidate_score_delta`；不得因Y05個案另加 magic number。完整 topology axes只有在自身通過 whole-member coverage／credibility後才可構成 competing runner，detail rectangle或橫向短構造不能只因形成closed contour就升級為完整 Brace axis。

共用 core 可以重用「合格 topology member」「axis equivalence」「component-envelope evidence」等 pure primitives，但 Brace policy不得反向改變上述 Strut authoritative-boundary 與 fallback 條件。尤其不能為了讓更多 Brace成功，就讓已存在可靠 topology 的 Strut重新接受 geometry-only cross-outline pairing，或把任一最外層 closed contour自動視為 `source_width` evidence。

同一 root內的等價 axis evidence依既有 geometry-equivalence與 topology containment收斂；明確不同且各自可靠的完整 axes仍為 terminal ambiguity。成功軸的 terminal extent只來自 accepted source evidence。

**理由：** Y05的17個直接 ambiguity顯示「任何完整 contour都是 competing whole axis」對Brace過度敏感；既有 winner／runner contract已能區分 dominant member與次要detail，不需要新規則。

**替代方案：** 因為使用者確認一個 root是一支Brace，就選最高分 axis。拒絕；當兩條完整軸同樣可信時，source仍沒有授權系統任選。

### 4. Waler-to-Waler是 downstream validity，不是 recognition tie-breaker

成功 whole-axis candidate與其他 Brace相同，在 member creation後統一交給 `connect_components_to_walers()`：

```text
Brace root fragments
  → pure whole-axis recognition
  → Brace candidate
  → existing endpoint-to-finite-Waler snap
  → FromWaler / ToWaler + connection validation
```

Pure service不接收 Waler collection，也不以「某 axis延長後能碰到兩支 Waler」選 winner。這維持 geometry recognition與工程關聯的單向依賴，並避免 Waler漏辨識或錯誤工程線反向污染 Brace axis。

若 source-supported endpoint在既有 `connection_tolerance_mm` 內，connection flow照常投影到有限 Waler segment；若零端或單端連接，保留 `BRACE_NOT_CONNECTED`／`BRACE_ONE_END_NOT_CONNECTED`。不得在本 change將 infinite-axis intersection或遠距離外插加入 connection flow。

**理由：** 使用者確認 Brace的正式關係是 Waler-to-Waler，但來源不足與 Waler不足是兩種不同問題；合併判定會讓 diagnostics失真。

**替代方案：** 在多個 geometry candidates中選唯一能連兩支 Waler者。拒絕，因為這會建立新的隱性 recognition rule，也可能用錯誤 Waler掩蓋 genuine source ambiguity。

### 5. Y05先做 source-handle characterization，再鎖定可證明的 regression

測試先按 exact root handle記錄每個Y05 Brace source的：一般路徑結果、pure outcome、whole-axis、terminal source extent、representative width與Waler connection結果。這是 deterministic fixture選擇，不把目前流水 `B<n>` ID當source identity。

至少選擇：

- 一個由局部短軸改善為唯一完整 whole axis的 root（目前characterization可由 `A37` 類型開始核對）；
- 一個 genuine multiple-complete-axis source，必須保持 ambiguous；
- 一個 whole-axis recognized但Waler connection仍失敗的 source，用來證明兩層diagnostic不混淆；
- 一個 ordinary non-component Brace root，維持 general fallback。

只有在source geometry能證明期望軸時，才把實際座標寫成 fixture assertion；不得用目前畫面看起來較長或能碰Waler就反推expected axis。Y1A一般 LINE／LWPOLYLINE與Y29 closed-outline Brace作為非BIM regression。

**理由：** Brace ID是匯入後投影，root handle才是穩定source identity；實際Y05資料也同時含 recognition與Waler connection問題，必須分開驗證。

**替代方案：** 直接要求Y05所有25個root都成功。拒絕，因為目前至少有多個source缺乏唯一geometry或有效Waler連接，這會迫使演算法猜測。

### 6. Review、state與persistence維持既有 owner

`DXFReviewWorkflow.world_result`仍是canonical WCS result，Presentation只顯示snapshot。recognized Brace與terminal problem均沿用role + exact root handle identity；source exclusion／restore重新執行recognition，manual endpoint replay與confirmation依既有signature規則處理。

不新增serialized topology state、Project row欄位或schema migration。完成Review後只有Brace的既有`BraceID`、`FromWaler`、`ToWaler`與端點進入Project；child fragments仍只存在DXF provenance／preview。

## Architecture Alignment

本change沿用現有Architecture，不修改layer responsibility：

- `dxf_import/block_member_recognition.py`：pure geometry與topology single source of truth。
- `dxf_import/recognition.py`／`importer.py`：route pure outcome並建立role-correct runtime candidate／message。
- `candidate_points.py`既有connection flow：唯一擁有Brace endpoint-to-Waler snap與validation。
- `DXFReviewWorkflow`：擁有live Review state與staged decisions。
- Presentation：只呈現Brace、source problem與既有人工修正，不解讀fragments。
- Project／Domain：只接收完成Review後的formal Brace，不知道BIM child geometry。

Dependency仍是 `DXF file → Infrastructure recognition → DXF Review → ProjectDataModel`；Domain、Application與Algorithms不反向依賴DXF。

## Risks / Trade-offs

- **[role-neutral refactor破壞已封存的 Strut topology baseline]** → apply前重跑已封存 change 的完整 Strut fixtures；除 status／axis／diagnostic 外，同時鎖定 `representative_width`、candidate `source_width`、Material Review outcome、topology-authoritative fallback boundary與無 topology時的 legacy fallback。
- **[寬度 regression 被單一 Y05 尺寸掩蓋]** → 以 350／400／500 mm、nested same-axis envelopes、D17 open detail rails、axis-known／width-unknown與 invalid envelope fixtures共同驗證；不得把 regression case提升為固定材料規則。
- **[Brace detail contours造成大量false ambiguity]** → 只有通過whole-source credibility與coverage的axis可成為reliable competitor，並用synthetic＋Y05 handle fixtures鎖定。
- **[過度偏向成功而錯選axis]** → 一個root一支Brace不代表可任選；genuine competing whole axes維持blocking ambiguity。
- **[recognition改善但Waler仍未連接]** → 保留兩階段diagnostic，且不修改Waler recognition／tolerance／snap。
- **[共用service改壞Strut]** → Strut既有完整suite與active topologychange的fixtures必須全數regression；role-neutral refactor不改其outcome。
- **[ordinary Brace behavior被特殊路徑攔截]** → `not_applicable`回到同一未合併root的general recognition，並以Y1A／Y29與syntheticfixtures保護。
- **[member流水ID隨candidate集合改變]** → integration assertions以role + root handle + geometry為identity，不依賴固定`B<n>`。

## Migration Plan

不需要資料migration。部署只影響fresh DXF recognition；既有Project rows與saved results維持可讀。paused Review重新連結或fresh re-recognition時，既有source fingerprint、manual replay與confirmation invalidation規則決定舊decision是否仍有效。

Rollback為code rollback；original DXF與persistence schema未改變。若focused Y05或Strut regression顯示role-neutral core無法保持既有contract，停止apply並回到planning artifacts，不以fallback或放寬assertion完成change。
