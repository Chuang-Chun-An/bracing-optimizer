# Design

## Context

需求背景見 [proposal.md](proposal.md)，正式行為見 [specs/dxf-rc-waler-hatch-recognition/spec.md](specs/dxf-rc-waler-hatch-recognition/spec.md)。

目前 `DXFImporter.GEOMETRY_TYPES` 支援 `LINE`、`LWPOLYLINE`、`POLYLINE`、`MLINE`、`SOLID`、`TRACE` 與 `INSERT`，但不含 `HATCH`。`_geometry_groups()` 因此不會為 HATCH 建立 recognition source；Waler 圖層上的獨立外框 LINE 隨後由 `_merge_related_line_groups()` 依端點連接合併，再交給 `_candidate_from_group()` 解讀成一支直線構件。

Y05 的實際來源顯示：

- `1647` 是一個水平、約 800 mm 寬的 `FP_55` patterned HATCH；`1650` 是與其端點相接的垂直 HATCH。
- `E65` 與 `163D` 是另一組同型水平／垂直 HATCH。
- 四個 HATCH 都是非 associative（沒有 `source_boundary_objects`），各自具有一個由 line edges 組成的封閉 `EdgePath`。
- 目前只有周圍 LINE 被讀取，因此水平與垂直外框被合併成 L 形 group，形成 `WALER_RECOGNITION_FAILED`／`WALER_ENGINEERING_LINE_FAILED`。
- 現有 `maximum_component_width_mm = 600` 會拒絕把 800 mm 外框當成一般 outline／parallel-pair component；提高此全域值會影響 Strut、Brace 與一般 Waler，不符合本 change 範圍。

現有 downstream contract 已能承接本功能：`Waler` 有 `source_handles`、`source_entity_types`、`source_width`、`recognized_axis`、`boundary_lines` 對應資訊以及 `material_spec`／`material_spec_source`；`DXFImportResult.to_project_rows()` 也已傳遞 `material_spec`。正式 `material_spec = RC` 的 Solver／Project 行為由既有 `rc-waler-optimization-exclusion` capability 負責。

## Goals / Non-Goals

**Goals:**

- 在 DXF importer／recognition boundary 新增小型、可獨立測試的 HATCH RC Waler interpretation。
- 讓 HATCH handle 成為單一來源 truth，從其 boundary geometry 建立 WCS candidate、Review identity 與 RC material hint。
- 在 HATCH 有效或無效時，都阻止相同外框 LINE 再走一般 recognition 產生第二份結果。
- 重用既有 inner-contact-face selection、Review workflow、source exclusion、manual override 與 Project mapping。
- 保持一般 Waler、其他 member roles、Project schema 與 Solver 行為不變。

**Non-Goals:**

- 建立通用 HATCH framework、HATCH pattern 材料資料庫或 UI 設定。
- 支援曲線／弧形 Waler、從單一 L 形 HATCH 拆出多支 Waler，或從單一 HATCH 的多個離散外邊界建立多支構件。
- 改寫 `_merge_related_line_groups()` 的一般圖形分組演算法。
- 改變 Waler contact adjustment、CandidatePoint、connection、association 或 Solver 規則。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改層級或 dependency direction。

| Layer / Boundary | 本 change 的責任 |
| --- | --- |
| `dxf_import` importer boundary | 讀取 HATCH boundary、套用 OCS／entity transform、輸出 WCS source scope；協調 HATCH route 與一般 route |
| `dxf_import` pure recognition logic | 驗證封閉外邊界、推導完整 axis／width／longitudinal boundaries、回傳 recognized／failed／ambiguous outcome |
| DXF Review application | 沿用現有 ProblemRecord、ReviewItem、exclusion、restore、confirmation 與 staged mutation |
| Presentation | 只顯示既有 member／problem／material state，不推導 HATCH 幾何 |
| Project / Solver | 只接收既有 Waler row 與 `material_spec = RC`，不理解 HATCH |

Dependency direction 維持：

```text
DXF entity reader
  → HATCH WCS source extraction
  → pure RC Waler recognition
  → existing candidate / Review pipeline
  → DXFImportResult
  → existing Project row conversion
```

HATCH boundary geometry 與 HATCH handle 是 source truth；正式 Waler model 是 reviewed engineering truth；Project row 是完成匯入後的 Application model truth。三者不得互相反推或保存第二份可漂移的分類規則。

## Decisions

### 1. 在 Waler route 前先建立 HATCH source scopes

Importer 針對每個被分類為 Waler 的 layer，先分離：

1. Waler HATCH entities。
2. 其他既有 geometry entities。

每個頂層 HATCH 以自己的 handle 建立一個 source scope，不進入 `_merge_related_line_groups()`。Importer 必須先完成所有 HATCH boundary extraction 與 boundary-evidence claim，再把未被 claim 的一般 geometry 送入現有 block route、LINE merge 與 `_candidate_from_group()`。

這個順序保證兩個端點相接的 HATCH 仍是兩個 source units，也確保無效 HATCH 不會因稍後 fallback 至相同 LINE 而被誤認成 Steel Waler。

HATCH path 只在 Waler role 啟用；其他 role 不加入 route。這避免把「有填充」誤解成跨圖層、跨角色的通用 RC 分類。

**Rejected alternatives:**

- 把 `HATCH` 直接加入一般 `GEOMETRY_TYPES` 並交給 `_merge_related_line_groups()`：會重新引入 HATCH 與 LINE 的混組問題，且無法表達 RC material precedence。
- 先跑一般 recognition，再以附近 HATCH 修改材料：一般 route 已可能在材料判定前形成錯誤 L 形群組，無法補救構件 identity。

### 2. HATCH extraction 讀取 boundary path，不展開視覺填充線

新增 importer-side extraction helper，把 HATCH boundary 正規化為 immutable WCS source DTO。第一版接受：

- 只含 line edges 的封閉 `EdgePath`。
- 無 bulge 曲線的 closed `PolylinePath`。
- 一個可唯一判定的 exterior loop；其他 path 僅可作為完全位於 exterior 內且不影響外包絡的 hole／detail。

Arc、ellipse、spline、非零 bulge、開放／不連續 path、自交、無唯一 exterior、多個離散 exterior 或需要把單一 L 形 envelope 拆段的來源，回傳具名 failure／ambiguous outcome。第一版不 flatten 曲線，避免以任意 chord tolerance 改變工程幾何。

座標在 importer boundary 依 HATCH OCS、elevation 及既有 entity transform 正規化為 WCS。正式 recognition service 不接觸 ezdxf entity，也不處理 Project local coordinate。

正規化包含：移除等價的重複 closure vertex、將相鄰共線 edge 合併為 topology edge、canonicalize loop traversal，以及使用既有 ordered-line 規則固定 axis start／end。child order、boundary traversal direction 或起始 vertex 不得影響結果。

**Rejected alternatives:**

- 分析 HATCH pattern strokes：pattern 只控制顯示，不代表工程外框，且會產生大量與構件方向無關的斜線。
- 只依 HATCH extents 建立矩形：bounding box 會把旋轉構件、L 形或多外邊界來源誤造成一支構件。

### 3. 新增 pure HATCH Waler recognition service

新增小型 module（建議 `dxf_import/hatch_waler_recognition.py`），其輸入為不含 ezdxf object 的 WCS boundary DTO 與 `GeometryTolerances`，輸出 terminal outcome：

- `recognized`：唯一完整 axis、source width、兩條 longitudinal boundary lines、HATCH handle／layer、`material_hint = RC`。
- `failed`：boundary 無效或不足以形成一支完整直線 Waler。
- `ambiguous`：存在多個幾何不等價且同樣完整的外邊界／工程軸解。

`failed` 與 `ambiguous` 都是該 HATCH source 的 terminal blocking outcome，不 fallback 至其 boundary LINE。Outcome reason 由 importer 映射成 role=`waler` 且帶 HATCH handle 的 `ValidationMessage`，讓既有 `build_problem_records()`／`build_review_items()` 產生 unresolved row。

服務驗證下列幾何性質：

- boundary topology 封閉且連續；
- 存在唯一主要直線方向；
- exterior 形成單一長條 envelope；
- 完整縱向 extent 非零且滿足既有 minimum component length；
- 長寬關係滿足既有 named slenderness setting；
- longitudinal boundaries、axis 與 source width 可唯一導出。

服務可重用現有 outline geometry primitives，但不得套用 `maximum_component_width_mm`。這個例外僅存在於已由 Waler-layer HATCH 確立 RC 語意的 route，不修改 `GeometryTolerances.maximum_component_width_mm`，也不改變其他 member type。

### 4. Recognition tolerance mapping 不新增無名 magic number

| 判斷 | 既有 named setting |
| --- | --- |
| boundary vertex／edge continuity | `endpoint_tolerance_mm` |
| 主要方向與 longitudinal edges 平行性 | `parallel_angle_tolerance_deg` |
| 同一直線 edge 的橫向偏差 | `collinear_tolerance_mm` |
| 對應 longitudinal edge 寬度一致性 | `width_tolerance_mm` |
| 最小完整構件長度 | `minimum_component_length_mm` |
| 長條 envelope eligibility | `minimum_slenderness_ratio` |
| boundary evidence 投影覆蓋 | `minimum_projection_overlap_ratio` |
| 等價 axis／geometry 去重 | `duplicate_tolerance_mm` |
| 多個完整候選 ambiguity | `ambiguous_candidate_score_delta`，僅在候選 scoring 確實沿用同一 normalized scale 時使用；否則以幾何不等價且無唯一 topology winner 直接 ambiguous |

`maximum_component_width_mm` 明確不適用於此 HATCH RC route。若實作發現現有 tolerance 無法安全表達某一判斷，必須先新增具名 internal recognition setting、以 synthetic fixtures characterization 並更新 Design；不得在 production code 加入無命名常數。

### 5. HATCH handle 是來源 identity，外框 LINE 是 runtime boundary evidence

正式 member／unresolved item 的 authoritative `source_handles` 以 HATCH handle 為主，不把所有附近 LINE handles 組成另一個 durable identity。原因是 Y05 HATCH 為 non-associative，DXF 沒有可靠 `source_boundary_objects` 可證明某條 LINE 的 ownership；以 handle 鄰近或 entity order 推測會破壞 source safety。

Importer 另建立本次 recognition runtime 的 boundary-evidence claim：

- LINE／POLYLINE 的全部有效 segments 必須在既有 angle、collinearity、projection coverage 與 endpoint tolerances 下，落在一個或多個 Waler HATCH exterior boundary segments 上，才可被 claim。
- 單純相交、端點接觸、平行但偏離、只覆蓋少量局部，或同圖層但無幾何等價者不得被 claim。
- 被 claim 的 entity 不再進入一般 Waler group merge；其 `SourceGeometry` 仍可保留作 immutable underlay／diagnostic evidence。
- claim 是每次從原始 DXF 重建的 runtime projection，不持久化到 Project schema。

不論 HATCH outcome 是 recognized、failed、ambiguous 或 explicitly excluded，都必須先由該 HATCH boundary 重建 claim。如此排除 HATCH 後，外框 LINE 不會換一個 identity 重新出現；復原則重新啟用同一 HATCH source。

若 HATCH boundary 本身無法解析到足以判定 claim 的程度，Importer 不得廣泛吞掉附近 LINE；此時只為 HATCH 建立 blocking problem，無法證明等價的 LINE 維持原 route。Review 可能同時看見 HATCH problem 與無關 LINE 結果，優先保護不誤刪其他構件。

**Rejected alternatives:**

- 將所有相鄰 LINE handles 永久加入 HATCH member identity：non-associative HATCH 無法可靠證明 ownership，且可能造成跨 ReviewItem 共用 handle。
- 依 handle 數值鄰近推斷 boundary：DXF handle 只表示 entity identity，不表示工程關係。

### 6. HATCH candidate 重用既有 inner-contact-face selection

Pure service 的 `recognized` outcome 先建立完整中心軸及兩條 longitudinal boundary lines，再轉成現有 `_Candidate` 等價資料。後續仍由 `_select_waler_inner_lines()` 使用 Strut／Brace endpoints 與 framing centroid 選擇正式接觸側。

因此：

- HATCH 不建立新的「RC 中心線就是正式線」規則。
- `recognized_axis` 保留 HATCH envelope 的完整中心軸。
- `start/end` 在既有 selection 後仍代表正式 inner-contact line。
- `source_width` 使用 HATCH exterior 的實際橫向寬度。
- 既有 Waler contact review、backfill 與 endpoint connection downstream 不需了解 HATCH。

### 7. RC material hint 在 candidate-to-model boundary 採用

HATCH recognized outcome 帶有明確 internal `material_hint = RC` 與 `material_spec_source = auto_hatch`。Candidate-to-Waler mapping 將這兩項寫入既有 `Waler` 欄位；不增加 `Waler` 或 Project row schema 欄位。

`recognize_result_material_specs()` 調整 precedence：

1. `auto_hatch` RC Waler 保留 `RC`。
2. 其他 Waler／Strut 才依既有 `source_width` 規則嘗試材料辨識。
3. Review 中後續 `set_member_material_spec()` 仍可建立 `manual` override。
4. Review rebuild／source restore 先重建 `auto_hatch` base，再依既有 exact source identity 規則 replay manual override。

不得依 `recognition_method` 字串或 HATCH pattern name 在下游重新猜材料；material hint 只在 recognition boundary 建立一次。

### 8. Debug、Review 與 source exclusion 沿用既有模型

Importer 對 HATCH 增加 `EntityDebugInfo` 與 `SourceGeometry`：

- role=`waler`
- handle=HATCH root handle
- entity type=`HATCH`
- boundary WCS points／closed state
- recognized、failed、ambiguous 或 excluded 所需 detail

成功 candidate 的 `source_entity_types` 包含 `HATCH`，source layer 保留原 Waler layer。Failure messages 至少區分：boundary invalid、unsupported nonlinear boundary、ambiguous exterior／axis、engineering line failed。具體 code 名稱可沿用現有 Waler prefix，但必須穩定且能由測試斷言。

Review workflow、confirmation signature、source exclusion identity、pause／resume 及 fingerprint 不增加新的 state owner。HATCH recognition 改變後，fresh recognition 使用 HATCH identity；既有 exact paused Review 仍依現行 contract 不重新辨識。若 content-changed recovery 導致舊 LINE identity 轉為 HATCH identity，既有 recovery rules決定 preserved／requires_review／disabled，不做 schema migration或靜默搬移 exclusion。

### 9. Determinism 與 one-source outcome

同一 HATCH source 最多建立一支 formal Waler，否則建立一個 blocking source problem。Determinism 由下列 normalization 保證：

- WCS points 先 quantize／compare through named tolerances，不使用 raw object order。
- boundary loop 起點與 traversal direction canonicalize。
- 共線 edge merge 後依幾何 key 排序。
- axis endpoints 使用既有 `_ordered_line()` 等價規則。
- candidate tie 只依 canonical geometry／topology；不得使用 entity order、handle 大小或 first occurrence。

兩個不同 HATCH 即使幾何相接，也不共享 source unit。真正 geometry-equivalent duplicate HATCH 交由既有 candidate deduplication，但 merged provenance 必須仍保留兩個 HATCH handles，並由既有 duplicate warning／Review contract處理。

## Runtime Data Flow

```text
Waler-role DXF entities
  → collect each HATCH source
  → extract/canonicalize WCS boundary
  → pure HATCH Waler recognition
      → recognized candidate + RC hint
      → failed/ambiguous ValidationMessage
  → derive boundary-evidence claims
  → remove claimed outline LINE/POLYLINE from general recognition input
  → existing Waler general recognition for remaining geometry
  → existing deduplication
  → existing inner-contact-face selection
  → Waler model (`material_spec = RC`, source=auto_hatch)
  → width material recognition preserves auto_hatch RC
  → existing CandidatePoint / contact / Review / coordinate workflow
  → existing Project row conversion
```

## Backward Compatibility and Persistence

- 原始 DXF immutable；本功能只讀 HATCH boundary。
- `DXFImportResult` 與 Project payload schema 不新增欄位。
- `material_spec_source` 已是既有欄位，新增值 `auto_hatch` 為 backward-compatible runtime／debug value。
- 未含 Waler HATCH 的圖面不進入新 route。
- 舊 paused Review exact-match resume 不重新辨識，因此不會被本 change 靜默改寫。
- Fresh import 或 compatible re-recognition 可能把舊 LINE-based unresolved identity 改為 HATCH identity；這是預期 recognition 改善，人工 decision 仍依既有 source safety 規則處理。
- 不需要資料 migration、Project schema upgrade 或 Solver result migration。

## Risks / Trade-offs

- **[CAD 誤放 HATCH 會把來源分類為 RC]** → 規則是使用者已確認的 authoring contract；限定 Waler role layer，且幾何仍須通過唯一直線 envelope validation。
- **[50 mm 等既有 tolerance 對細節圖可能過寬]** → boundary claim 必須同時通過方向、共線、全 segment 覆蓋及 endpoint checks；若 characterization 顯示仍不安全，新增具名 setting，不寫 magic number。
- **[非 associative HATCH 無法證明 LINE ownership]** → HATCH handle 作 durable identity，LINE claim 僅為可重建的 runtime geometry projection，不持久化猜測關係。
- **[無效 HATCH 可能與一般 LINE 同時顯示問題]** → 只在可證明 geometry-equivalent 時 claim；寧可保留額外 Review evidence，也不吞掉無關 Steel Waler。
- **[曲線或複雜多 path HATCH 第一版無法辨識]** → terminal blocking Review，使用者可在 CAD 修正、排除來源或沿用既有合法人工流程；不以 flattening 猜測工程線。
- **[RC 寬度繞過 600 mm gate]** → bypass 僅限已具 Waler-role HATCH RC 語意的 pure route；全域 tolerance 與其他 recognition 不變。

## Migration Plan

此 change 不需要資料 migration。實作以新增 pure service 與 synthetic fixtures 開始，再接入 importer、material precedence、Review/source exclusion，最後執行 Y05 與完整 DXF regression。若需回復，移除 HATCH route 即可回到既有 LINE-based behavior；不需回復 Project payload。
