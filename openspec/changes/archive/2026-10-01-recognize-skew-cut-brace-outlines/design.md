# Design

## 閱讀導航

### P0｜現在必須理解

1. Decision 1：一般 closed polyline 與 root `INSERT` topology 共用同一份純幾何量測結果。
2. Decision 2：封閉拓撲先證明 body 完整性，再由 rails 與 terminal cuts 建立 source axis。
3. Decision 3：共用 `minimum_projection_overlap_ratio = 0.8` 不變，斜切不是較低門檻。
4. Decision 4：修正後的 source axis 直接進入既有 terminal evidence pipeline，不建立第二套 Waler 連接邏輯。

### P1｜實作相關模組時閱讀

- 修改 component-like authority tiers：Decision 1、2、5。
- 修改 diagnostics／Review evidence：Decision 5、6。
- 處理 Y29 regression 或 source deduplication：Decision 6 與 Risks。

### P2｜可先跳過

- Migration Plan 不涉及資料轉換；只有發布與 rollback 時需要。
- CornerBrace、Solver、Project persistence 與 UI layout 不在本設計內。

## 方案摘要

```text
normalized closed boundary
  → deterministic rail/cut decomposition
  → one immutable BraceOutlineMeasurement
       rails + cuts + width + midline + source axis
  → general Brace candidate 或 INSERT topology candidate
  → existing deduplication
  → existing terminal evidence → Waler face → Brace verdict
```

本設計把「完整性」與「rail 長度相近」分開：完整 closed topology 負責證明兩條 rails 與兩個端面屬於同一 body；rail supporting lines 負責方向、中心與寬度；terminal cuts 負責 source-supported longitudinal endpoints。開放或碎片來源沒有這些拓撲證據，仍走既有 `0.8` coverage gates。

## 決策對照

| Decision | 對應 Spec Requirement | 對應 Tasks |
|---|---|---|
| 1. 共用 immutable outline measurement | 三個 Requirements 的一致 geometry／provenance | 1.x、2.x |
| 2. Topology-driven rail／cut decomposition | 完整斜切封閉外框、來源軸由有限端面界定 | 2.x、3.x |
| 3. 保留全域 0.8 與 width hard gate | 完整斜切封閉外框、既有安全邊界 | 2.x、4.x |
| 4. 沿用既有 terminal pipeline | 斜切外框辨識保留既有安全邊界 | 3.x、4.x |
| 5. Authority 與 failure integration | 多解／破損外框、既有合法 Brace 不改軸 | 2.x、3.x、4.x |
| 6. Source identity 與 diagnostics 不另建 truth | Y29 71A、多來源 scopes、Review 可追溯性 | 3.x、4.x、5.x |

## 專有名詞

- **body rail**：Brace 外框兩側、沿主要構件方向延伸的 outer supporting side；有限線段可因端部斜切而長度不同。
- **supporting line**：body rail 所在的無限直線，只用來量測正交寬度與建立中間 supporting line，不直接成為正式有限端點。
- **terminal cut**：在起端或終端連接兩條 body rails 的有限直線端面；其長度與斜率不代表 body width。
- **source axis**：由 body midline 與兩個 terminal cuts 的有限交點界定、尚未經 Waler formal contact-face finalization 的可靠來源軸。
- **formal axis**：既有 member verdict 通過後，由 source axis 與兩個 selected formal Waler contact faces 的有限交點形成的正式 Brace 軸。

## Context

動機見 `proposal.md`。目前一般 closed-outline Brace 經 `brace_outline_centerline()`／`_brace_supporting_side_measurement()` 量測；每個 supporting band 必須對所有 outline points 的 longitudinal root extent 覆蓋至少 `minimum_projection_overlap_ratio`。Y29 `71A` 的兩條 rails 平行且相距約 `400 mm`，但因端面斜切，較短 rail coverage 約 `77.36%`，所以在 terminal-to-Waler 之前即失敗。

若只把門檻降為 `0.7`，目前 axis construction 仍以 outline point projection extrema 放到 midline，會使 `71A` 兩端分別超出 terminal cuts 約 `200 mm` 與 `379.33 mm`。此外共用 ratio 也用於 open rails、fragment candidates、extent reliability 與部分 equivalence checks，不能為單一幾何型態全域放寬。

現有架構已將 DXF recognition、workflow 與 presentation 分層：pure recognition operations 只依賴 DXF models／geometry；`DXFReviewWorkflow` 擁有 canonical WCS result；Dialog 只投影與操作 workflow。本 change 沿用這個架構，不新增跨層依賴。

## Goals / Non-Goals

**Goals:**

- 建立一個 deterministic、order-independent 的 closed Brace outline measurement，讓一般 polyline 與 INSERT 內 closed topology 共用。
- 正確辨識由兩條平行 outer rails 與兩個斜切 terminal cuts 組成的完整 Brace body。
- 以 rail supporting-line separation 量測 width，以 midline／terminal-cut intersections 建立 source axis。
- 保留既有 authority、failure、terminal identity、contact-face 與 formal verdict contracts。
- 用 focused unit tests 與 Y29／Y05 fixture regressions 證明沒有全域門檻放寬。

**Non-Goals:**

- 不推導跨 gap、occlusion 或不同 root source 的 terminal cuts。
- 不消解 coincident／overlapping Waler identities。
- 不重設一般 candidate deduplication identity。
- 不建立可持久化的新 DXF state，也不改 Project row schema。
- 不抽取通用 polygon framework或重構無關 recognizers。

## Decisions

### Decision 1：以單一 immutable measurement 作為 closed Brace geometry truth

在 `dxf_import/block_member_recognition.py` 擁有一個 package-internal immutable result（設計名稱 `BraceOutlineMeasurement`），至少包含：

- normalized `axis`
- `representative_width`
- 兩條 selected finite `rail_lines`
- 兩條 ordered finite `terminal_cut_lines`
- `confidence`
- 用於 deterministic comparison 的 geometry signature／provenance

一般 `LWPOLYLINE`／`POLYLINE` route 與 component-like root `INSERT` 的 `TOPOLOGY` tier 都必須由同一 pure measurement builder 取得 axis、width 與 supporting evidence。既有 `brace_outline_centerline()` 可保留為 compatibility wrapper，轉投影舊 tuple contract；不得在 wrapper 內另算一套 geometry。

理由：目前一般 closed outline 與 component-like topology 分別經 supporting-side measurement 與 point-cloud／topology axis 路徑，斜切端點若各自修正容易形成兩個 truth。共享 measurement 讓 width、center、extent、ordering 與 failure semantics 一致。

替代方案：只在 `_candidate_from_group()` 特判 Y29 型四邊形。拒絕原因是 INSERT 內等價 closed outline 仍會走不同計算，且 fixture-specific branch 無法形成穩定 capability。

### Decision 2：以 boundary topology 分解 rails 與 terminal cuts

Measurement builder 先正規化一個 closed boundary：移除重複閉合點、零長度 edge，並使用既有 endpoint tolerance 驗證單一無分支 cycle。單一 closed primitive 可直接提供 ordered cycle；由多段 LINE 組成的來源只在既有 connectivity 可唯一建立等價 cycle 時使用。

正規化 cycle 只以其幾何主方向判斷哪一組 opposite edges 有資格成為 longitudinal rails，候選 rail 方向仍須在既有 `parallel_angle_tolerance_deg` 內與該主方向相容。主方向只用來拒絕把橫跨 body 的 terminal cuts 反向命名為 rails；正式 axis、width 與 endpoints 仍完全由 selected finite rails／cuts 建立，不使用 PCA extent 或 bounding-box geometry。

對 cycle 列舉可能的 outer rail pair，候選必須：

1. rail directions 在既有 `parallel_angle_tolerance_deg` 內相容；
2. 兩條 finite rails 各自長度 `>= minimum_component_length_mm`；
3. 兩條 rails 沿主要方向的有限投影具有正的 longitudinal overlap，形成兩側共同支持的 body corridor；
4. supporting-line separation 位於既有合法 width 範圍；
5. rails 位於 body corridor 的兩側，而非同側共線 detail；
6. cycle 移除兩個 rail paths 後，剩餘邊界可唯一形成起端、終端兩條 terminal cut paths；
7. 每個 terminal cut path 必須可正規化成一條有限直線，連接兩條 rail supporting lines，且其方向不得在既有 `parallel_angle_tolerance_deg` 內與 rail 方向平行；
8. midline 與兩 terminal cuts 各有一個位於有限 cut 上的合法交點，且兩交點形成正長度、符合既有 slenderness／minimum length 的 axis。

以上退化檢查只重用 `minimum_component_length_mm`、`parallel_angle_tolerance_deg`、既有 endpoint tolerance、width gate 與既有 axis length／slenderness 規則。不得為近三角形、近乎平行端面或無共同 corridor 個案加入匿名 epsilon、角度或比例門檻；若實作／測試證明既有 tolerance 仍會接受退化外框，必須停止 apply、回報 artifact／domain tolerance 缺口，再由明確規格決定是否另增具名設定。

相鄰且共線的 rail 或 cut segments可以先合併成 supporting band／finite cut；非共線 detail、branch 或多義 terminal chain 不得被平均成一條端面。對每個合法 decomposition 建立 measurement，最後依 normalized geometry grouping 判斷唯一或 ambiguous，不依 polyline 起點或 traversal direction 排名。

來源軸定義為：

```text
normal = perpendicular(rail_direction)
midline_offset = (low_rail_offset + high_rail_offset) / 2
source_start = finite_intersection(midline, start_terminal_cut)
source_end   = finite_intersection(midline, end_terminal_cut)
```

對直接連接兩條平行 rails 的 terminal segment，midline intersection 等於其幾何中點；實作仍使用有限線段交點語意，避免把「取中點」誤用到非直線或不完整端面。

替代方案：沿用 projection extrema，但只放寬 coverage。拒絕原因是來源軸會超出斜切 body，且後續 direct／extension distances 不再代表真實來源端點。

### Decision 3：closed topology 不降低共用 coverage gate

完整 closed topology candidate 不使用「每條 rail 對全體 root projection 必須 `>= 0.8`」作為 terminal completeness gate；cycle 本身已證明兩 rails 經兩 terminal cuts 封閉成同一 body。它仍須通過唯一 rail pair、width、minimum length、slenderness 與 finite terminal intersection gates。

下列路徑維持 `minimum_projection_overlap_ratio = 0.8`：

- open parallel edges
- paired-rail fragments
- whole-root outer-envelope
- local rail-pair fallback
- topology 不完整後進入的 lower authority candidates
- 現有 equivalence／runner-up checks

`minimum_brace_body_width_mm = 250.0` 的 strict `>` 與 `maximum_component_width_mm` 的 inclusive `<=` 均不變。

替代方案：新增全域 `minimum_projection_overlap_ratio = 0.7`。拒絕原因是實測會使 Y29 多個待修來源同時進入後續流程，其中多數仍有 terminal ambiguity，且會改變非斜切用途的同名 tolerance。

### Decision 4：沿用既有 terminal evidence 與 formal verdict pipeline

Measurement 只修正 `recognized_axis`／source axis 及其 closed-outline evidence；`_resolve_waler_contact_geometry()` 仍把該軸轉成既有 `MemberGeometryFacts`，依序執行：

```text
build_member_terminal_evidence
  → resolve_waler_contact_faces
  → build_brace_terminal_verdicts
  → _apply_terminal_resolutions
```

第一版不讓 terminal cut 直接選擇 Waler identity，也不新增 cap-to-Waler 特例。理由是 corrected source endpoints 已使既有 direct／outward-ray 距離回到實體語意；重疊 identities 仍必須依既有 ambiguity contract 保守失敗。

若 implementation discovery 證明現有 `MemberGeometryFacts.axis` 無法保留 spec 要求的必要 source provenance，僅可增加 package-internal immutable evidence field並由同一 measurement 投影；不得新增第二套 Waler winner selection 或改變 `terminal evidence → contact face → member verdict` 方向。

替代方案：terminal cut 與最近 Waler face 共線即直接指定 identity。拒絕原因是 coincident Waler sources 仍可能同時滿足，且會繞過既有 terminal ambiguity、contact-face finalization 與 atomic member verdict。

### Decision 5：TOPOLOGY authority 使用 shared measurement，lower tiers 不變

對一般 closed polyline，成功 measurement 仍建立 `closed_outline_axis` candidate。對 component-like root `INSERT`，可驗證 closed boundary 的 `TOPOLOGY` candidate 必須由同一 measurement 產生；`WHOLE_ROOT_ENVELOPE` 與 `LOCAL_RAIL_PAIR` 生成方式不改。

若 closed boundary 存在但：

- 找不到合法 decomposition：該 topology candidate 不合法，繼續既有 lower-tier evaluation；
- 找到多個不等價合法 measurements：該最高合法 tier回報 ambiguity；
- body evidence 已成立但所有 tiers 均失敗：維持 `BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE` 或更具體且仍屬 reviewable recognition failure 的診斷。

一般 route若沒有其他合法候選，仍產生既有 `BRACE_RECOGNITION_FAILED` 與 `BRACE_CENTERLINE_FAILED` summary。不得因新 measurement 失敗而回退至 bounding box 或 PCA 猜測 axis。

替代方案：只要 boundary closed 就使用 polygon PCA。拒絕原因是 PCA 無法證明選到 outer rails、會被斜切與突出 detail偏移，且 width 可能退化成 bounding-box 語意。

### Decision 6：diagnostics 與 source identity 沿用既有 projection

`BraceOutlineMeasurement` 是 runtime pure geometry truth；`_Candidate`／`Brace` 仍是 Review projection。selected rails 沿用既有 `boundary_lines`／engineering line candidates 顯示，terminal cuts 可由 exact source geometry 追溯；只有實際 UI／problem reporting 需要明確標示時才加入 package-internal candidate evidence，不新增 persistence schema。

不同 root `INSERT` 永不在 recognition measurement 內合併。一般獨立 polylines 各自先形成 measurement，再進入既有 `_deduplicate_candidates()`；本 change 不修改 deduplication contract。`44E`／`45C` 只作為回歸觀測，若既有 dedup identity 被確認為另一項工程問題，另立 change。

診斷至少要能區分：

- closed topology 合法但 Waler identity unresolved；
- boundary 不完整／分支／自交；
- rail pair 多解；
- width hard gate 失敗；
- terminal cut 與 midline 無合法有限交點。

可沿用現有 error code 加 detail；只有 Review 無法據此判斷修復方向時才新增專用 recognition code，且必須加入 problem／overview classification。

## Architecture Alignment

本 change 沿用現有 Architecture，不修改 layer boundary：

| Layer／模組 | 責任 | Dependency direction |
|---|---|---|
| `dxf_import/block_member_recognition.py` | pure closed-body geometry、measurement、component-like topology candidate | 只依賴 DXF models／geometry helpers |
| `dxf_import/recognition.py` | 將 measurement 投影為 candidate，協調 authority、dedup、terminal pipeline | 呼叫 pure recognition 與 Waler contact services；不依賴 UI |
| `dxf_import/waler_contact_face.py` | 既有 terminal evidence、contact-face、member verdict | 不依賴 Importer mutable state或 Presentation |
| `dxf_import/importer.py` | entity extraction、root grouping、stage ordering | 不承載新的 Brace 工程判定 |
| `dxf_import/dialog.py` | 顯示既有 result／problem／candidate evidence | 不重算 rail、cut、width 或 Waler identity |

Single source of truth如下：

- closed outline 的 geometry interpretation：`BraceOutlineMeasurement`。
- staged canonical WCS result：`DXFReviewWorkflow.world_result`。
- Waler terminal identity 與 formal member outcome：既有 terminal evidence／`BraceTerminalVerdict`。
- Project truth：只有 completed Review 投影出的正式 rows。

`terminal cut midpoint` 不另存成可人工漂移的第二組正式 endpoints；Review 顯示一律由 measurement/source axis或既有 formal verdict投影。Manual replay 仍依現行 workflow 重建 terminal identities，不直接覆寫 measurement 的工程規則。

## Backward Compatibility / Persistence

- `DXFImportResult`、Project rows、paused Review payload 與 project schema 不變。
- 不新增 migration；舊 project重新辨識同一 DXF 時，符合新 requirement 的 skew-cut source可能由待修變成可審查的 Brace candidate，這是預期行為變更。
- 既有已保存 manual endpoint／exclusion／confirmation replay仍依 source identity與現有 invalidation規則處理；若 recognition signature因 axis修正而改變，confirmation必須依既有 contract失效，不得沿用 stale geometry。
- `brace_outline_centerline()` 若有測試或 package-internal caller，保留既有 callable contract；新 evidence由額外 internal function／result提供。

## Risks / Trade-offs

- [Risk] 任意 closed polygon被誤解為斜切 Brace → 只接受唯一無分支 cycle、唯一 outer rail pair、兩個可驗證 terminal cuts、合法 width與有限交點；多解保守失敗。
- [Risk] 斜切很大時可能退化為近三角形、近乎平行端面或彼此錯開的兩條 rails → 兩條 rails 各自必須達到 `minimum_component_length_mm`、具有正的 longitudinal overlap，且 terminal cut 不得在 `parallel_angle_tolerance_deg` 內與 rails 平行；只沿用既有 tolerance，若仍無法阻擋退化案例則停止實作並回報，不得加入 magic number。
- [Risk] shared measurement改變既有矩形或 INSERT topology axis → 保留既有矩形、反向 traversal、Y05/Y29 fixture characterization與全套 Brace regressions；只有新 spec符合的 skew-cut geometry應改變。
- [Risk] corrected source axis改變 direct／extension classification → 這是使距離回到實體端面的預期結果，但 formal outcome仍必須通過既有 terminal tests、600 mm boundary與Waler ambiguity regressions。
- [Risk] `44E`／`45C` 因兩者新近都成功而進入既有 dedup → 不修改 dedup contract；用 regression記錄實際結果，若工程 identity需求不同則另案處理。
- [Trade-off] 第一版不以 terminal cut對Waler face的共線性消解 identity，可保留安全但部分案例仍 unresolved；這符合本 change不猜測重疊Waler winner的邊界。

## Migration Plan

1. 先加入 pure geometry measurement與synthetic tests，不接入 production route。
2. 將一般 closed Brace route轉接 shared measurement，跑 focused closed-outline／width tests。
3. 將 component-like `TOPOLOGY` tier轉接 shared measurement，跑 BIM Brace tests。
4. 驗證 terminal pipeline、Y29 `71A`與Y05/Y29 regressions，再更新 `docs/DOMAIN.md`。
5. 不需資料 migration；若回歸不符合 spec，rollback只需撤回 recognition route接線與internal measurement，不處理任何持久化資料。
