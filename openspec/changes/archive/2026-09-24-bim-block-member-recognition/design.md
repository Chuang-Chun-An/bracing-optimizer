# 技術設計

## 現況與限制

需求背景請參考 `proposal.md`，正式行為契約請參考 `specs/bim-block-member-recognition/spec.md`。

目前 DXF 流程已提供本次變更所需的大部分邊界：

- `DXFImporter._geometry_groups()` 會為 modelspace 中的每個頂層 entity 建立一個 `_GeometryGroup`。
- `_extract_entity()` 使用 `virtual_entities()` 遞迴展開 `INSERT`。Child LINE／POLYLINE geometry 已轉換至 WCS，而 `group.handles` 與 `SourceGeometry.source_handle` 會保留最外層 root handle。
- 同一 root `INSERT` 的 child entities 會先留在同一 group；但目前 `_merge_related_line_groups()` 是以「group 只有一個 LINE primitive」篩選，不會再確認該 LINE 是否來自頂層 LINE。因而只含一個 LINE child 的 root `INSERT` 仍可能在 router 前與其他 group 合併。Task 3 必須先關閉這個 root-boundary 缺口，不能假設現況已安全隔離不同 INSERT groups。
- `_candidate_from_group()` 負責一般辨識。在 MLINE／明確中心線／封閉外框檢查之後，它會依局部邊線長度排序平行邊對；對 fragmented BIM Block 而言，這可能選到一個短矩形，而不是完整實體構件。
- `_deduplicate_candidates()` 可能合併不同 source groups 中幾何重複的 candidates。BIM candidate 的 root scope 必須保持獨立，因此需要略過這項既有行為。
- `DXFReviewWorkflow` 負責 staged recognition、依精確 role + source-handle identity 重播明確人工輸入、重建 validation 與 ReviewItems，以及移除失效 confirmations。Source exclusion 會在 recognition 前過濾 group，同時保留 original `source_geometry` 供預覽與復原。

因此，本 change 不需要新的 Review workflow、Project model、persistence schema 或 presentation controller，只需要在既有 recognition boundary 插入一個純粹的 whole-block geometry decision。

## 目標／非目標

**目標：**

- 區分一般／非 component INSERT 與強烈代表單一 Strut 的 fragmented root INSERT；
- 從所有採用的 fragments 重建一條完整 axis，不把較大的 interior gap 自動視為拆分點；
- 產生明確的 `not_applicable | recognized | failed | ambiguous` 結果，使 fallback 安全且可供 Review；
- 保留 root scope、WCS、provenance 與 deterministic behavior；
- 整合既有 candidate、validation 與 Review contracts，不建立第二個 state owner。

**非目標：**

- 取代或通用化整套 DXF recognition framework；
- 為 Brace、Waler 或其他 role 定義新的工程規則；
- 新增 persisted evidence model、BIM mode 設定或使用者可見的 recognition 開關；
- 修改後續 Waler connection／snap、material、CandidatePoint、Double Support 或 Project conversion rules；
- 新增 Guided Recognition 或平行的 manual editor。

## 架構對齊

本設計沿用目前 Architecture，不改變 layer model。

```text
DXFImportDialog（Presentation）
        ↓
DXFReviewWorkflow（live Review application state）
        ↓
DXFImporter（reader / recognition pipeline adapter）
        ↓
component-like Block geometry service（pure recognition operation）
        ↓
既有 Candidate / DXFImportResult / Validation / ReviewItem
        ↓ 僅在 Review 完成後
既有 DXF → Project row boundary
```

- Presentation 只顯示既有 formal member 或 unresolved ReviewItem。
- `DXFReviewWorkflow` 仍是 live Review state、manual replay、exclusion、confirmation 與 coordinate projection 的 authoritative owner。
- Importer 仍是 WCS reader／pipeline adapter，並負責判斷何時呼叫 pure operation。
- 新 service 只解讀 geometry；不 import Tkinter、不寫檔、不修改 Review state，也不建立 Project rows。
- `models.py` 仍是共用 immutable result contract。BIM-specific metadata 不會加入 `ProjectDataModel` 或 Solver input。

## 設計決策

### 1. 在內部幾何群組加入明確的根來源資訊

`_GeometryGroup` 將持有明確的內部 `root_handle` 與 `root_entity_type`（或等價的 immutable source-scope value），由 `_geometry_groups()` 在 recursive expansion 前設定。

特殊 router 必須同時符合：

1. role 是 `strut`；
2. root entity type 確實為 `INSERT`；
3. 所有 evidence 都屬於同一個 root group；
4. source 尚未被排除。

不得僅以 `"INSERT" in entity_types` 推斷資格，因為該 collection 也記錄遞迴展開的 child types，代表 provenance，而不是精確的 root-kind contract。

Role 仍由 root layer 決定，不新增 child-layer classifier。

Router 必須在任何可能跨 group 的 `_merge_related_line_groups()` 之前，逐一以原始 root group 呼叫 pure service。呼叫端必須明確驗證 `group.root_entity_type == "INSERT"`、`group.role == "strut"` 與非空 `root_handle`；不符合者不得呼叫 v1 BIM Strut service。後續一般 LINE 合併也必須排除 root entity type 為 `INSERT` 的 group，避免兩個不同 root INSERT 因各自只含一個 LINE child 而失去獨立 source scope。

這項限制不表示 root INSERT 自動成立為構件；它只保證每一個 root INSERT 會以自己的 WCS primitives 獨立接受 eligibility 判斷。`not_applicable` 仍會對同一個、未合併的 root group 執行既有 general recognizer。

**否決方案：**從 `block_instances[0]` 或第一個 entity type 推斷 root 狀態。這會重新引入 traversal-order dependency，也無法可靠區分 source scope 與 nested provenance。

### 2. 新增一個小型純整體圖塊幾何模組

新增一個聚焦的 module，例如 `dxf_import/block_member_recognition.py`，負責 component-like evidence analysis。它會公開內部 immutable input／output DTOs，而不從 `recognition.py` import `_Primitive`，以避免 circular dependency，並讓測試不依賴 importer objects。

概念 contract：

```text
recognize_component_like_strut(root scope, WCS primitives, tolerances)
    → status: not_applicable | recognized | failed | ambiguous
    → optional whole axis, representative width, confidence
    → optional source-aware validation problem
```

此 service 為 stateless。它的 single source of truth 是目前 root group 的 WCS primitives；derived orientation clusters、fragment axes 與 scores 只存在於單次 invocation，不會 serialization。

`recognition.py` 會將成功結果轉成既有 `_Candidate` contract，並使用穩定的 recognition method，例如 `bim_block_whole_axis`。Importer 接著沿用既有 connection、association、candidate-point、material 與 validation pipeline。

**否決方案：**把演算法直接加入 `dialog.py` 或 `DXFReviewWorkflow`。這會讓 Presentation／Application 主持 geometry interpretation，並建立具有不同 state 的第二條 recognition path。

**否決方案：**將所有目前 recognition 搬入新的 framework。本 feature 只需要一個 isolated operation；framework rewrite 會擴大 regression risk，卻不會改變必要行為。

### 3. 使用四狀態分流，並讓來源內的失敗成為終止結果

Importer-level router 會依下列方式處理符合資格的 Strut root INSERT：

```text
whole-block service
├─ not_applicable ──► existing _candidate_from_group()
├─ recognized ──────► existing _Candidate pipeline
├─ failed ──────────► blocking source-aware problem；不執行一般 fallback
└─ ambiguous ───────► blocking source-aware problem；不執行一般 fallback
```

`not_applicable` 表示沒有可信的 component-like whole-member solution，因而保留一般 CAD Blocks 與所有目前 general methods。

只有在 source 已有足夠 evidence 進入 component-like interpretation 後，才會回傳 `failed`／`ambiguous`：

- 存在一個可信 component cluster，但無法確立完整 supported terminal extent → `failed`；
- Best 通過 winner credibility 後，存在另一個互相衝突、具有完整幾何與 coverage 的 reliable whole-axis candidate，且 evidence delta 落在 ambiguity boundary 內 → `ambiguous`；runner 不必自行達到 winner threshold。

這兩種 terminal state 都不得呼叫一般 local parallel-pair fallback，否則系統可能先承認 whole-member evidence，最後卻仍輸出被禁止的 truncated candidate。

#### 3.1 Winner credibility 與 reliable-runner ambiguity 採分離 gate

目前 pure service 先以 `bim_minimum_longitudinal_evidence_ratio = 0.5` 篩選 credible candidates，再對通過 whole-extent coverage 的前兩名執行 `ambiguous_candidate_score_delta` 比較。這個順序具有下列實際結果：

- `50% / 50%`：兩個候選都通過 `>= 0.5`，因此可判定為 `ambiguous`；
- `51% / 49%`：49% runner-up 先被 credibility gate 排除，即使兩者差 `0.02`、仍落在既有 ambiguity delta `0.03` 內，也可能直接判定為 `recognized`。

已確認採用原選項 B：`0.5` 只控制 winner 是否具有最低 credibility；它不會把略低於 `0.5`、但幾何可靠的 runner-up 從 ambiguity comparison 中硬切除。

正式判斷 contract：

1. 先依既有 geometry checks 建立 whole-component candidates。
2. Candidate 只有在方向、transverse center、width、component length、slenderness 均合法，能由來源 evidence 重建完整競爭軸，且 `root_extent_coverage >= minimum_projection_overlap_ratio`（目前 `0.8`）時，才是 reliable whole-axis candidate。
3. 在可靠候選中依 evidence ratio 與既有 deterministic geometry tie-break 找出 best。只有 `best.evidence_ratio >= 0.5` 才可能 `recognized`；低於 `0.5` 的 candidate 不能單獨成為 winner。
4. Best 通過 winner gate 後，檢查其他所有 reliable candidates，而不是直接相信排序第二名。與 best 幾何等價的 candidates 視為 duplicates 並略過；任何可靠、不等價 candidate 若與 best 的 evidence delta `<= 0.03`，結果即為 `ambiguous`。
5. 若所有可靠且不等價的 runners 與 best 差值皆 `> 0.03`，best 才能在其他既有條件也成立時回傳 `recognized`。

因此正式邊界為：

- `50/50` → `ambiguous`；
- `51/49` → `ambiguous`，因 49% runner 雖不能單獨勝出，但仍是可靠完整競爭軸；
- best `>= 0.5` 且所有可靠不等價 runners 的 delta `> 0.03` → best 可 `recognized`；
- 排名第二但 coverage `< 0.8`、無完整 supported extent 或未通過 whole-component geometry checks → 不是 reliable runner，不會只因排名觸發 ambiguity。

被否決的 gate-first 作法會讓 `51/49` 在 ambiguity delta 內仍直接成功；另增 runner-up threshold 則會引入沒有額外 fixture 依據的新 tuning。兩者均不採用。

### 4. 保留可靠的整體來源既有表示

新 service 專門處理 compound／fragmented evidence。當既有 representation 已能明確描述整個 source 時，它會回傳 `not_applicable`，包括：

- 明確且 full-span 的 centerline 或 MLINE；
- 一個涵蓋整個 source 的完整 closed outline；
- 一個涵蓋整個 source 的完整 parallel-edge representation。

上述 representations 仍由目前 general recognizer 負責，保留既有 recognition methods、candidate-line behavior 與 confidence。

Full-span 判斷會比較 legacy representation 與完整 root-scope longitudinal envelope；位於更長 aligned source 內的短局部線或局部外框，不會只因幾何清楚就被視為 full-span。

一般 compound CAD Block 必須有獨立 fixture，不得只以「完整 full-span outline 加短 detail lines」代表。該 fixture 應包含多個一般繪圖用途、彼此不足以支持單一 component-like Strut 的 primitives，而且本身不具會提早命中 full-span legacy gate 的完整中心線或外框；預期 BIM path 為 `not_applicable`，之後仍由既有 general recognition 決定其原有結果。

**否決方案：**強制所有 Strut INSERT 都通過新演算法。這會改變已可靠的 centerline／outline cases，並使一般 drafting Blocks 依賴 BIM heuristics。

### 5. 先建立碎片證據，再建立構件軸線

Pure service 依下列 deterministic stages 運作。

#### 5.1 Tolerance／Recognition Setting Mapping

本 change 不建立另一套散落於 helper 內的 tolerance。BIM whole-block service 對現有判斷的 mapping 如下；表中的既有欄位均來自 `GeometryTolerances`，並沿用目前 drawing units（通常為 mm）與既有語意。

| 辨識判斷 | 預計使用的既有 `GeometryTolerances` 欄位 | 使用方式與邊界 |
| --- | --- | --- |
| fragment endpoint connectivity | `endpoint_tolerance_mm` | 判斷同一 root scope 內 LINE endpoints 是否可連成同一 closed contour。它只處理端點連接，不作為跨越 BIM interior gap 的最大 gap。 |
| parallel／dominant-direction compatibility | `parallel_angle_tolerance_deg` | 判斷 fragment axis 是否可加入同一個 undirected orientation cluster。此欄位只控制角度相容性；「主要方向擁有足夠整體 evidence」另由下述新增 internal setting 控制。 |
| fragment width compatibility | `width_tolerance_mm` | 比較各 fragment 推導出的 representative widths 是否相容。不得在 helper 內另寫未命名的絕對或相對 width delta。若 synthetic fixtures 證明絕對 tolerance 不足，必須另增具名 internal setting，而不是內嵌比例常數。 |
| transverse center alignment | `collinear_tolerance_mm` | 比較 fragment center axes 在 transverse direction 的偏移，判斷它們是否支持同一條共同工程軸。這是幾何共線容許值，不代表實體構件寬度。 |
| valid component width | 下限使用 `collinear_tolerance_mm`；上限使用 `maximum_component_width_mm` | 沿用一般 recognition 的 component-width contract：小到落在共線雜訊範圍內的雙邊 evidence 不構成有效寬度，超過最大構件寬度也不合法。這些是 recognition tolerance，不新增材料規格或工程尺寸規則。 |
| slenderness | `minimum_slenderness_ratio` | 以 whole-component supported longitudinal extent 與 representative width 的比值判斷是否具有細長構件形態，不以任一局部 rectangle 的長寬比代替整體判斷。 |
| ambiguity comparison | `ambiguous_candidate_score_delta` | 比較同一 root scope 中使用相同尺度計分的 whole-component candidates。只有幾何上不等價、且分數差落在該具名 ambiguity 範圍內的競爭解才回傳 `ambiguous`。 |
| duplicate／equivalent geometry | `parallel_angle_tolerance_deg`、`duplicate_tolerance_mm`、`minimum_projection_overlap_ratio` | 以方向、位置／端點距離及 longitudinal projection overlap 共同判斷兩條 candidate axes 是否為等價幾何；比較必須對 start/end 反轉不敏感。不同 root INSERT 即使幾何等價，仍不得因這項判斷而合併。 |

另外兩個既有欄位維持輔助責任：

- `minimum_projection_overlap_ratio` 也用於判斷 legacy centerline／outline／parallel-edge representation 是否確實覆蓋 root-scope longitudinal envelope，而不是只覆蓋一小段局部 fragment；
- `minimum_component_length_mm` 仍是既有最小候選長度檢核，不取代 whole-block 的 component-like evidence 判斷。

BIM fragment 之間**不新增 maximum gap tolerance**。`endpoint_tolerance_mm` 只用於 contour connectivity；interior gap 是否很大，不會單獨拆分或接受一個 component cluster。

目前沒有合適既有 tolerance 可表達「勝出的主要方向占整體有效 longitudinal evidence 的最低比例」，因此需要新增一個具名的 internal recognition setting：

**`bim_minimum_longitudinal_evidence_ratio`（名稱可在實作時等價調整，但責任不得改變）**

- **控制行為：**以 length-weighted、已去除重複 interval 的有效 fragment-axis evidence，判斷 winning orientation cluster 是否具有足夠 dominance，避免大量短 detail lines 以 entity count 主導方向，也避免只憑一組漂亮但局部的 parallel pair 宣稱整個 root INSERT 是一支 Strut。
- **既有 tolerance 不適合的原因：**`parallel_angle_tolerance_deg` 只能決定 evidence 能否加入方向群組；`minimum_slenderness_ratio` 只描述候選外形；`ambiguous_candidate_score_delta` 只比較兩個已成立候選的接近程度。三者都不能表示 winning cluster 相對於 root scope 有多少 longitudinal support。
- **Synthetic BIM fixture characterization：**使用同一 root INSERT 的完整外框、沿共同軸排列且含大 gap 的多個 rectangles、逐步增加橫向 detail geometry、局部短 parallel pair 混入較長無關 geometry、以及兩組互相衝突 whole-axis evidence 等 fixtures。Task 2 以兩組等量完整衝突軸作為可解釋邊界，選定 `0.5` 為 winner 的具名最低 credibility；它是 recognition tuning，不是工程規則，也不是 runner-up ambiguity eligibility threshold。Task 3 前必須補上 `50/50`、`51/49`、delta 明顯大於 `0.03` 的 winner，以及不可靠 runner cases，以固定 3.1 的正式 policy。
- **規則分類：**這是 internal recognition tuning，不是 Engineering Hard Constraint、材料規格、Project data 或使用者可調的 UI setting。

本 change 新增的 production code 中，所有會改變 BIM classifier、candidate retention、confidence、ambiguity 或 geometry acceptance 的距離、角度、比例與計數門檻，都必須引用具名 `GeometryTolerances` 欄位或具名 internal recognition setting。不得直接出現未命名的 `0.6`、`0.7`、`50`、`100` 或其他 BIM heuristic magic numbers；若實作發現還需要新的門檻，必須先補上具名 setting 與對應 synthetic fixture characterization，不能藏在條件式或 score expression 中。

#### 5.2 正規化圖元證據

- 排除 zero-length segments；
- 將 directions 視為 undirected；
- 依 geometry canonicalize 每個 direction，不使用 start/end order；
- 從 closed POLYLINE／LWPOLYLINE evidence 推導 closed-outline fragment axes；
- 在同一 root scope 內由相連 LINE edges deterministic reconstruct closed contours，使 LINE rectangles 與 POLYLINE rectangles 產生等價的 fragment evidence；
- 只有在兩條 rails 具有足夠 overlap 與合法 width 時，才推導 local paired-edge fragment axes；
- 個別 LINE 僅保留為 weak supporting evidence，不能單獨成為截短 compound source 的理由。

上述 connectivity、parallelism、width consistency、component width、slenderness 與 ambiguity comparison 一律依 5.1 的 mapping；不得由個別 helper 重新定義第二套 tolerance。

#### 5.3 建立主要無向方向群組

Fragment-axis directions 會依既有 parallel-angle tolerance 分群。Cluster strength 以 longitudinal support 為基礎，而不是 entity count，因此大量短 transverse detail lines 不會只因數量多就壓過長距離 aligned evidence。

對每個 orientation cluster，service 會將 fragment evidence 投影到：

- canonical longitudinal direction；
- 與其垂直的 transverse direction。

#### 5.4 建立完整構件群組

在同一 orientation cluster 中，fragment axes 會依共同 transverse center alignment 與 compatible widths 分組。合法 component cluster 必須符合既有 component-width 與 slenderness contracts，並呈現 coherent center alignment 與 width evidence。

Longitudinal intervals 會以 union 合併，因此兩條 rails 或重複 outline edges 所造成的重複 evidence 不會取得任意額外權重。Interior gaps 仍是沒有可見 geometry 的 intervals，但不會拆分 cluster。

若沒有可靠 best 達到 winner credibility，結果不得為 `recognized`。當 reliable best 達到 `0.5` 後，任何可靠、不等價、且與 best evidence delta `<= 0.03` 的 runner 都會使結果成為 `ambiguous`；runner 本身不必達到 `0.5`。Candidate 的排序位置不構成 reliability，與 best 等價的 duplicate 也不構成衝突。

#### 5.5 重建有來源支持的完整軸線

對唯一的 component cluster：

- 使用不受順序影響的 robust statistic，從採用的 fragment axes 推導 transverse center；
- 使用不受順序影響的 robust statistic，從 compatible fragment widths 推導 representative width；
- 以採用的 terminal evidence 的最小與最大 longitudinal projections 作為 supported extent；
- 在上述 projected limits 之間建立 center axis；
- 不得超出最外側 accepted source evidence；
- 依 canonical direction 正規化 start/end。

此階段不套用 maximum interior-gap rule。Gap size 本身不能推翻共同 root identity、direction、center alignment 與 width consistency；反之，只有 root identity 也不能補足缺漏或互相衝突的 terminal evidence。

#### 5.6 Task 3 前的實際案例與決定性保護

Y05 站 S2（root handle `957`）必須加入 regression coverage。其 root INSERT 目前展開為 54 個 WCS LINE primitives；pure service 應從整體 evidence 重建約 `18,900 mm` 的完整軸，約為 `(-53379, -9450) → (-53379, 9450)`，不得退回既有 general recognizer 約 `6,978 mm` 的局部結果，約為 `(-53379, -3488.368) → (-53379, 3489.368)`。目前 trace 中 best evidence ratio 約為 `0.907178718`，可靠且不等價的 runner 約為 `0.873110802`，delta 約為 `0.034067916 > 0.03`；因此採用 3.1 policy 後，預期結果仍是 `recognized`，不是 `ambiguous`。Focused fixture 可以是從該 root scope 擷取的穩定、精簡測試資料，但必須保留會形成競爭 transverse component clusters 的關鍵幾何，不能簡化成已知必過的四個理想 rectangles。

Pure-service final outcome 必須另外以 permutations 驗證，而不只檢查中間 fragment 或 orientation 結果。至少涵蓋：

- child primitive order；
- LINE start/end 反轉；
- closed POLYLINE traversal／起始 vertex 改變；
- 幾何等價 duplicate primitives 的順序與表示改變。

所有 permutations 都必須得到相同 `not_applicable / recognized / failed / ambiguous` status；成功時還必須得到等價的 normalized whole axis、representative width 與 accepted-fragment semantics。Importer-level WCS permutations 仍由後續 integration tests 再驗證一次。

### 6. 只保留一個正式候選，不將局部碎片公開為替代選項

成功結果會建立一個 `_Candidate`，內容包括：

- start/end 為 reconstructed whole axis，之後才進行一般 downstream Waler connection／snap；
- `recognition_method = "bim_block_whole_axis"`（確切 identifier 可於程式實作時定案，但一旦保存於 debug state 後必須穩定）；
- root source key 與 root handle；
- 既有累積的 source entity types 與 BlockInstanceInfo；
- computed centerline status、representative width 與 confidence；
- 不將 local fragment boundary lines 提供為獨立 engineering-line candidates。

Original fragment geometry 仍保留於 `DXFImportResult.source_geometry`，供 preview 與 provenance 使用。不公開局部 boundary options，可避免新的 automatic candidate 又透過生成的 line choices 引入同一種 short-fragment interpretation。

既有 downstream Waler connection、endpoint snap、association 與 validation behavior 均不變。

### 7. 在候選去重中保護根來源範圍

`_deduplicate_candidates()` 對 general recognition 保持目前行為。當任一 candidate 為 `bim_block_whole_axis`，而兩者來自不同 root source keys 時，即使 axes 在 tolerance 內共線或重複，也不得合併。

這是一個範圍狹窄的 source-boundary exception，不是 global dedup redesign。後續 duplicate-engineering validation 仍可回報重疊的 formal components，但不得抹除彼此獨立的 provenance。

**否決方案：**允許目前 deduplication 合併兩個 root handles。這會把兩個獨立匯出的 physical Blocks 變成一個 member，也會使 source exclusion／restore 產生歧義。

### 8. 使用來源感知的阻擋診斷與既有檢核投影

Service 至少會針對下列情況回傳明確的 blocking codes：

- component-like Strut 存在互相衝突的 whole axes；
- component-like Strut 無法重建完整 supported extent。

這些 codes 會加入既有 recognition-problem classification，使 Guidance 引導使用者檢查 layer／source geometry。每個 message 都包含 role `strut` 與 root handle，因此 `build_problem_records()` 與 `build_review_items()` 可將 source 投影為一個 unresolved ReviewItem，不需要新的 UI model。

`not_applicable` 本身不是 warning 或 error；只回報 general recognizer 的既有結果。成功的 BIM candidate 不會只因使用特殊路徑就增加 warning。Presentation 可為新的 `recognition_method` 加上繁體中文 label，但不新增 control 或 workflow。

### 9. 重用檢核狀態識別與失效語意

下列既有 state contracts 繼續作為 authoritative truth：

- source identity：正規化的 `role + exact root source_handles`；
- live WCS result 與 staged mutation：`DXFReviewWorkflow`；
- source exclusion 與 restore：既有 `ExcludedSource` path；
- manual replay：既有 exact-source lookup 與 needs-review／disabled reporting；
- confirmation：涵蓋完整 member、problems 與 coordinate system 的既有 confirmation signature；
- pause／resume safety：既有 source fingerprint gate；
- completion：既有 `DXFImportResult.can_import` 與 result-to-project mapping。

由於 BIM axis 變更會改變 confirmation signature 中的 member，既有 confirmation pruning 會自動使其失效。不新增 BIM-specific confirmation flag 或 replay store。

Special recognizer 不會寫入 `ProjectDataModel`；只有 completed Review 才能透過既有 boundary 轉換 accepted `DXFImportResult`。

### 10. 維持持久化向後相容性

不需要修改 Project schema 或 DXF Review state version。新的 recognition method 是既有 debug／result data 中新增的 string value，而新的 validation codes 使用既有 `ValidationMessage` shape。

舊專案仍可載入。在相同 source 上重新執行 recognition 時，符合資格的 BIM Block 可能有意產生 corrected whole-axis member；manual overrides 與 confirmations 接著依既有 exact-source 與 signature rules 處理。

Original DXF files 保持 immutable。Source exclusion 仍只過濾 recognition input，不刪除 source geometry，也不修改檔案。

### 11. v1 不處理 Brace，但讓幾何程式碼保持可重用

Pure evidence types 與 orientation／fragment helpers 應避免 hard-code Strut UI 或 Project concepts，但 importer router 在 v1 只會對 role `strut` 呼叫此 service。

Brace 目前具有獨立的 outline、diagonal connection 與 endpoint semantics。缺少明確 Brace examples 與 acceptance criteria 時直接啟用，可能默默改變已正常運作的路徑。未來 change 可在先定義相關規則後重用 geometry service；本設計不加入 dormant Brace behavior。

## 風險／取捨

- **[風險] 過於寬鬆的 classifier 可能吸收一般 compound Block。** → 要求完整 component-like evidence set，使用 `not_applicable` 結果，並保留 ordinary INSERT／LINE／MLINE／outline recognition regression tests。
- **[風險] 過於嚴格的 classifier 可能漏掉部分 BIM fragments。** → 優先使用安全 fallback 或 unresolved Review，不製造 geometry；thresholds 維持具名，並測試完整、fragmented、含 detail 與 ambiguous sources。
- **[風險] Interior-gap 容忍可能製造不存在的 geometry。** → 不外插超過 accepted terminal evidence，並要求 common axis／width coherence；只跨越構件內部未顯示的區域。
- **[風險] 大量 fragments 可能使 pairwise analysis 成本提高。** → 所有工作限於單一 root INSERT，提早 deduplicate segment／interval evidence，並避免跨 roots 比較。不新增 global recognition scan。
- **[風險] 新 recognition 可能影響既有 confirmations 或 manual replay。** → 使用既有 root identity 與 confirmation signatures；無法安全重播時回報 needs-review，而不是默默附加到 non-unique member。
- **[風險] 目前 generic dedup 可能破壞 root identity。** → 加入狹窄的 BIM-candidate dedup guard，並以明確的 two-root regression coverage 保護。
- **[已處理風險] 0.5 gate-first 會讓 50/50 與 51/49 走向不同 terminal status。** → 已採用 3.1 的 winner-gate／reliable-runner policy；Task 3 前仍須先完成緊鄰邊界與 runner reliability tests，不得把 policy 修改混入 router 接線。
- **[風險] 單 LINE child 的 root INSERT 可能先被一般 line-group merge 合併。** → Router 必須在 merge 前逐 root 呼叫，且後續 merge 必須排除 root INSERT groups；以兩個相連／共線 root INSERT 的 regression coverage 保護。
- **[取捨] Strut-only v1 仍無法處理類似的 Brace files。** → 這能保留 Brace engineering behavior 並讓第一個 change 可驗證；共用 pure helpers 可減少後續成本，但不會預先授權未來 Brace change。

## 遷移方案

1. 新增 pure service 與 focused tests，但先不讓 production recognition 呼叫它。
2. 依已確認的 3.1 policy 完成 Task 2 review 所列前置測試與 pure-service 修正。
3. 加入明確 root-source facts 與 Strut-only router，接著以 integration tests 啟用 successful／terminal outcomes。
4. 加入 diagnostic classification、Review lifecycle 與 source-identity regression tests。
5. 執行 focused DXF tests、architecture boundary tests 與完整 regression suite。

不需要 data migration。Rollback 只需移除 router 與 pure service；既有檔案及已儲存專案不需轉換。

## 未決問題

無。已確認可靠的 49% runner-up 在與 winner 的 evidence delta `<= 0.03` 時必須參與 ambiguity comparison。確切 helper names 屬於 implementation choices；不得藉此新增 product rules 或未具名 tuning constants。
