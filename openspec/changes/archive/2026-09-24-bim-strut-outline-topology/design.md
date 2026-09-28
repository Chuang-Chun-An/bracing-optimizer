# Design

## Context

見 [proposal.md](proposal.md)。現行 BIM pure service 已能從 closed `POLYLINE`、connected LINE contour 與局部 rail pair 萃取 `_FragmentAxis`；它也保留 root `INSERT` source scope、WCS primitives、deterministic normalization 與 `recognized / failed / ambiguous / not_applicable` outcome。Importer 目前在 pure service 回傳 `not_applicable` 後，會交給一般 `_candidate_from_group()` 的全域平行邊配對。

Y05 `D17` 顯示這個 boundary 的缺口：root 內有一個由四條 outer LINE 形成、約 350 mm 寬的完整 connected contour，以及兩組重複、間距約 12 mm、但沒有端帽或共同封閉 traversal 的開放 longitudinal detail rails。這些 12 mm rails 不是第二層 closed outline，也沒有 provenance 可證明兩條 rail 互為 companion。pure service 因完整 legacy evidence 而回傳 `not_applicable`；一般 recognizer 則可把內部 rail 和 outer contour rail 交叉配對，得到約 `X=-15414` 與 `X=-15589` 的偏移中線，而非 outer contour 的中心軸 `X=-15498.5`。

本 change 沿用既有 DXF Import 架構：幾何解讀仍留在 `dxf_import` 的 pure recognition support，importer 只 route outcome，validation／Review 使用既有 source-aware problem lifecycle。工程軸與 `source_width` 分別由可靠的 axis evidence 與 component envelope evidence 推導；後續材料辨識仍使用既有 `source_width` contract。它不改變 Domain、Application、Solver、材料規格或 Project schema。

## Goals / Non-Goals

**Goals:**

- 在 root Strut `INSERT` 內，先以 outline／rail topology 限制哪些 rail 可以配對。
- 讓多層、同軸、拓撲上可驗證的外框共同支持一條工程軸。
- 支援 350 mm 以外的合法 Strut 寬度，並由唯一完整 component envelope 推導正確 `source_width`。
- 避免開放內部 detail rails 影響工程軸或材料寬度。
- 對一個 root 內真正存在兩條不等價完整軸的情況，以既有 blocking ambiguity lifecycle 終止，而不任選或拆出多支 Strut。
- 保持一般人工 CAD、單純 complete outline 和不具 topology evidence 的 non-component `INSERT` 行為。

**Non-Goals:**

- 不重新設計所有 general parallel-edge recognition。
- 不將「一個 INSERT 一個實體構件」當成無條件前提；沒有足夠 topology evidence 的 root 仍依既有 fallback contract。
- 不新增 Brace BIM recognition、Guided Recognition、AI／影像辨識、材料／CandidatePoint／Double Support 規則或 Project persistence migration。
- 不改變既有 `maximum_component_width_mm = 600`；已確認所有合法支撐寬度均小於此 recognition eligibility setting。
- 不新增新的工程尺寸或未命名 BIM heuristic threshold，也不把 D17 的 350 mm 寫成固定支撐寬度。

## Decisions

### 1. 以 root-local topology guard 補足 legacy fallback 缺口

在 `dxf_import/block_member_recognition.py` 擴充 pure analysis，使它在既有 `_has_full_span_legacy_evidence()` 宣告 `not_applicable` 前，先檢查 root 是否同時具有：

1. 可驗證的完整 outline 或連續 rail topology；以及
2. 額外 longitudinal rail evidence，足以使一般 unrestricted pairing 產生跨 topology 的候選軸。

這個 guard 只有在 topology 可以提供更強的來源邊界時才介入。沒有 guard 的普通 full-span outline 仍保持 `not_applicable`，因此維持既有 `closed_outline_axis` 或一般 recognition method／UI 行為。

**理由：** D17 不缺整體 extent；問題是 legacy fallback 沒有 rail parentage，會枚舉跨外框組合。只把所有完整 outline 強制走 BIM whole-axis path 會無必要改變已正常的普通 CAD Block 結果。

**替代方案：** 將所有 `INSERT` 禁止一般 fallback。拒絕，因為會破壞既有 ordinary compound CAD Block 的相容性，且把缺乏 topology evidence 的來源不必要變成 error。

### 2. 對 outline／rail 來源保留拓撲 provenance，禁止跨來源 rail pairing

pure service 會從既有 WCS primitive／segment evidence 建立「topology member」。root handle 只界定 recognition source scope，不能單獨證明 child rails 互為 companion。topology member 必須符合下列其中一種來源關係：

1. **Closed outline**
   - 來自同一個標記為 closed 的 source primitive。
   - 經 endpoint normalization 後至少具有三個相異節點。
   - primitive 的完整 segment set 形成單一 connected、unbranched closed cycle，每個節點的 degree 都是 2。
   - 若有 branch、dangling edge、斷裂子圖或無法形成唯一 cycle，不成立。

2. **Connected contour**
   - 可由多個 LINE／segment primitive 組成。
   - endpoint 只依既有 `endpoint_tolerance_mm` normalization 合併。
   - 被採用的 exact segment set 必須形成單一 connected、unbranched closed cycle，每個節點的 degree 都是 2。
   - branch、dangling edge、disconnected component 或同一 edge 的重複使用都不得形成 connected contour。

3. **Companion rail topology**
   - 兩條 longitudinal rails 必須先通過既有 parallel angle、projection overlap、width、length 與 slenderness eligibility。
   - 除上述幾何條件外，還必須具有明確 source relationship：兩條 rail 來自同一 closed primitive traversal，或位於同一 unbranched connected component，且由實際 transverse／end-cap paths 在兩端連接成完整 envelope。
   - 若存在第三條同等 longitudinal rail，使 companion pairing 無法由 connectivity 唯一決定，該 rail set 不成立為唯一 topology member。
   - 僅有「同一 root、互相平行、長度相近、投影重疊、間距合理或 entity 相鄰」都不足以成立 companion provenance。

每個 topology member 保留 runtime-only 的 canonical provenance：WCS normalization 後的 canonical segment key、primitive scope 與 endpoint-connectivity graph membership。既有依載入順序產生的 segment index 不得成為 topology truth，也不寫入 persistence schema。工程軸只可由同一 topology member 的 companion rails，或由該 member 的整體 outline 推導；不同 member 的 rail 不得彼此配對。

多個 topology member 各自推導的 axes 會先以既有 geometric-equivalence logic 比較：方向、line separation、endpoint／projection overlap 與既有 `GeometryTolerances`。等價者合併成一個 axis evidence set；不等價且各自完整者形成 source-level conflict。

**理由：** 這直接表達「同源多外框可同組，但不能跨外框取一邊」；D17 的約 350 mm outer LINE set 是 connected contour，能自行產生共同軸。間距約 12 mm 的 duplicated open rails 沒有端帽、共同 primitive traversal 或其他 connecting provenance，因此不是 closed outline、connected contour 或 companion rail topology，不能與 outer contour 的任一邊交叉配對。

**替代方案：** 單純用最小寬度、最大寬度或最高 score 選外框。拒絕，因為寬度不是此 feature 的工程選擇規則；也會再次以未命名 heuristic 處理不同 BIM 畫法。

### 3. topology 決定成功或 terminal ambiguity；不把多軸交給一般 winner score

若 topology guard 發現所有完整 axes 幾何等價，pure service 回傳一條共同軸的 `recognized` outcome。若發現兩條以上拓撲獨立且不等價的完整 axes，pure service 回傳既有 `BIM_BLOCK_CONFLICTING_WHOLE_AXES` 的 `ambiguous` terminal outcome；router 不得 fallback 到 `_candidate_from_group()`。

若 topology guard 無法建立足夠 source-bound evidence，它回傳 `not_applicable`，保留既有 non-component fallback。這不是把「兩條 candidate」一律視為 error，而是只處理已確定為 multiple complete topology members 的 root。

**理由：** 「同一 root Strut source 最多一支 formal Strut」需在正式 candidate 建立前成立。後段 `_validate_one_model_per_source()` 僅能回報已產生多模型，不能防止 D17 這種錯誤單一模型。

**替代方案：** 讓 candidate score 選出最高的 topology axis。拒絕，因為當 root 已清楚支持兩個獨立完整構件時，score 並不代表工程上可任選的權限。

### 4. 工程軸與 `source_width` 分開判定，由唯一 component envelope 提供寬度

topology analysis 先建立 axis evidence，再獨立建立 width evidence：

- axis evidence 回答「這一支 Strut 的完整工程中心線在哪裡」。
- width evidence 回答「哪一個 source-supported envelope 代表構件的物理橫向寬度」。

可提供 `source_width` 的 component envelope 必須是有效 closed outline 或 connected contour，且其 longitudinal coverage 足以支持 recognized whole-axis extent。當多個有效、等價軸且全長的 envelopes 彼此巢狀時，只有在 topology containment 能唯一找出完整外包絡時，才使用該外包絡的 transverse extent 作為 `source_width`。這個選擇依據是完整 envelope 與 containment，不是對所有 rail 距離任意取最大值。

開放 detail rails、局部 parallel pair 或沒有 companion provenance 的 rail 間距不得成為 width evidence。若 axis evidence 唯一但 component envelope 不存在或無法唯一判定，recognized outcome 仍可保留完整工程軸，但 `source_width` 使用既有 unknown 表示 `0.0`；後續 `recognize_material_spec_from_width()` 因此不會自動填入材料規格，DXF Review 維持既有人工選擇能力。

D17 的 outer connected contour 唯一支持完整 component envelope，所以輸出約 350 mm 的 `source_width`；12 mm duplicated open rails 不參與 width selection。其他 400 mm、500 mm 等合法外框依相同規則輸出其實際寬度，不得使用 350 mm default。

既有 `maximum_component_width_mm = 600` 繼續作為 component geometry 的具名 recognition eligibility setting。已確認所有合法支撐寬度均小於 600 mm，因此本 change 不調整此設定；它也不取代材料庫規格或 `material_width_tolerance_mm` 的唯一材料比對契約。

**理由：** 工程軸可能被多組同軸 evidence 一致支持，但材料辨識需要可靠的物理 envelope 寬度。分離兩種結果可避免為了保留正確軸線而被迫猜測材料，也避免內部 detail 間距污染 `source_width`。

**替代方案：** 對同軸 rail 距離取最小值、最大值、平均值或沿用固定 350 mm。拒絕，因為這些方法忽略 topology containment，會將內部細節或特定圖面的尺寸誤當成實體構件寬度。

### 5. 重用既有 tolerance 與 Review contract，不新增 persistence 或 UI state

topology connectivity、parallelism、width、component length、slenderness、axis equivalence 與 projection coverage 只使用既有具名 `GeometryTolerances`。若 characterization 發現既有 tolerance 無法區分 fixture，必須先回到 Design/Spec 決定具名 internal recognition setting；不得直接加入數字常數。

新的 source-level ambiguity 沿用 `BIM_BLOCK_CONFLICTING_WHOLE_AXES`、`ValidationMessage`、ProblemRecord、unresolved ReviewItem、source exclusion／restore、manual replay、confirmation invalidation 與 pause/resume。source identity 一律是 root handle。`DXFImportResult` 與 `ProjectDataModel` 不新增欄位。

## Architecture Alignment

本 change 沿用既有 DXF Import boundary，不修改整體 Architecture：

- `dxf_import` pure recognition logic 是 topology、axis evidence 與 width evidence 的 single source of truth。
- importer／recognition router 只將 pure outcome 轉為既有 candidate 或 validation problem，不自行重建第二套 topology 規則。
- material recognition 只消費已判定的 `source_width`；它不反向決定工程軸或 component envelope。
- Review Presentation 只顯示正式 member、unknown width 或 blocking problem，不解讀 child geometry。
- `DXFImportResult`、Project mapping、persistence 與 Solver contract 保持不變。

## Data and Control Flow

```text
root Strut INSERT (WCS primitives, root handle)
        │
        ▼
pure block-member recognition
  ├─ existing component-like whole-axis analysis
  └─ topology guard for multi-outline / rail pairing risk
        │
        ├─ no decisive topology → not_applicable → existing general recognition
        ├─ one equivalent axis set
        │      ├─ unique component envelope → recognized whole axis + source_width
        │      └─ no unique envelope → recognized whole axis + unknown source_width
        └─ multiple non-equivalent complete axes → ambiguous → blocking problem
        ▼
existing importer / validation / Review lifecycle
        │
        └─ reliable source_width → existing material auto-recognition
           unknown source_width  → existing manual material Review
```

Pure geometry interpretation remains the single owner of topology semantics. `recognition.py` converts only its outcome into `_Candidate` or `ValidationMessage`; `importer.py` preserves its existing per-root routing order. The dialog only displays current Review state and does not re-evaluate outline topology.

## Risks / Trade-offs

- **[A BIM root has incomplete rail topology]** → Guard must return `not_applicable`, preserving legacy behavior rather than inventing a contour.
- **[Endpoint drafting noise breaks a contour]** → Reuse existing endpoint tolerance and add near-tolerance characterization fixtures; do not relax a tolerance without an explicit design update.
- **[Equivalent outlines are represented by different entity order or direction]** → Normalize segment endpoints and sort provenance-derived topology members before axis comparison；test order and direction permutations.
- **[Open internal rails look like a narrow second outline]** → Require closed-cycle or explicit end-cap／connectivity provenance；parallelism and common root alone never establish companion rails.
- **[Axis is reliable but physical width is not]** → Preserve the whole axis, output unknown `source_width`, and let the existing material Review request user confirmation rather than guessing.
- **[Different legal Strut widths regress to a D17-specific value]** → Characterize at least 350 mm, 400 mm and 500 mm full-envelope fixtures and assert each retains its own width；never introduce a 350 mm default.
- **[A root actually contains two physical Struts]** → Produce one blocking unresolved source, not two formal Struts. User can resolve it through the existing Review/source workflow；Guided Recognition remains out of scope.
- **[Regression to ordinary CAD Block recognition]** → Guard activation requires topology risk；retain explicit ordinary full-outline and compound-block regression tests.

## Migration Plan

No data migration is required. The change affects fresh DXF recognition only. Existing saved Project rows and persisted DXF state remain readable；when a source is freshly re-recognized, existing manual replay and confirmation invalidation rules decide whether prior review decisions remain applicable. Rollback is code rollback only because original DXF and persistence schemas remain untouched.
