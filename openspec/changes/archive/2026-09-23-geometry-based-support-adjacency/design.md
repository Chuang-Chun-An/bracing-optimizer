# Design

## Context

本 change 的動機與需求範圍見 [proposal.md](proposal.md)，正式行為見 [support-adjacency spec](specs/support-adjacency/spec.md)。

目前 Support 流程中的相鄰關係仍由 `SupportConfig`／`SupportPlan` 的輸入順序隱含決定：

- `SupportInputBuilder` 依 Project row 順序建立 configs，`SupportZoneInput.units` 再依 `SharedLayoutGroup` 第一次出現的位置組成 optimization units。
- `OptimizeSupportZone` 將 units 展平成 physical configs 後交給 Phase 2。
- `algorithms.support` 以相鄰 list item 計算 Jack spacing、Jack region penalty、`min_jack_distance` 與 diagnostics。
- `SupportPlanEditing` 的全域重算與 neighbor checks 也各自依 physical plan list 判斷前後鄰居。

現有資料其實已足以建立幾何相鄰關係：Project `Strut` 保存 axis、Zoning、`SharedLayoutGroup`、`FromWaler` 與 `ToWaler`；DXF reviewed Strut 保存 active/world/local axis 與 Waler connection。缺少的是一個由 Application 建立、Algorithms 明確消費的 adjacency contract。

現有 Jack region 規則是 `get_jack_region_id(jack_center, pile_centers)`。`SupportInputBuilder` 已將 SharedLayoutGroup 兩 lane 的 Column stations 合併後提供給兩個 configs，因此 group-level region 不需要也不得使用代表長度。

本 change 橫跨 DXF Review、Domain geometry、Application input construction、Support Phase 2 與 manual result editing，但不改變既有分層方向、Project persistence schema 或 Phase 1 candidate generation。

## Goals / Non-Goals

**Goals:**

- 以 pure geometry rule 驗證一個 Zoning 是否能形成合法支撐排。
- 由 Application 從目前 Project geometry 建立 deterministic optimization-unit ordering 與 explicit adjacency pairs。
- 讓 Phase 2、manual editing、neighbor checks、minimum adjacent distance 與 diagnostics 共用同一 contract。
- 將 SharedLayoutGroup 收斂為一個 adjacency unit，同時保留兩支 physical plans 與各自的材料計數。
- 在 DXF reviewed geometry 轉成 Project rows 時產生可解釋、deterministic 的初始 Zoning suggestion。
- 保持 Main 中 Zoning 為使用者可編輯、可保存的 Project data；invalid geometry 只在驗證／求解邊界被拒絕。

**Non-Goals:**

- 不改 Support Phase 1、單支 `SupportPlan` 合法性、材料最佳化、score weights、Beam width 或 candidate cache policy。
- 不改 Jack region formula、TargetJackRegion 語意、500 mm station 定義或建立二維 Jack distance。
- 不改 Waler Solver、DXF entity recognition、Project row UI ordering或 persistence schema。
- 不自動修正、拆分或覆寫使用者在 Main 中設定的 Zoning。
- 不以此 change 清理既有 architecture exceptions 或其他 accepted debt。

## Architecture Alignment

本 change **沿用既有 Architecture，不改變 layer dependency direction**：

```text
DXF Presentation
    -> DXF Review / pure DXF grouping operation
    -> DXFImportResult.to_project_rows()

Presentation
    -> Application SupportInputBuilder / OptimizeSupportZone / SupportPlanEditing
    -> Domain geometry policy
    -> Algorithms Support Phase 2
```

各 layer 責任如下：

- **Domain**：提供不依賴 Project rows、Tkinter 或 Solver search 的 axis normalization、方向／長度 tolerance 驗證、row projection 與 tie 判定等 pure geometry semantics。
- **DXF Import subsystem**：使用 reviewed DXF geometry、Waler topology 與空間順序建立 initial Zoning suggestion。它不決定 Main 中 Zoning 的後續 truth。
- **Application**：從 `ProjectDomainModel` 建立當次求解使用的 optimization units、代表位置、排序與 adjacency contract；協調 validation error、solver invocation 與 committed result 保護。
- **Algorithms**：只消費已排序的 units／adjacency contract 與 unit-level Jack facts，執行 Phase 2 search、spacing、region penalty、summary 與 diagnostics；不讀取 Project geometry。
- **Presentation**：顯示 validation feedback，不複製幾何或 adjacency 規則。

`ProjectDataModel` 中目前保存的 Zoning 是使用者資料的 single source of truth。DXF initial grouping 只在建立 imported Project rows 時提供初值；solver adjacency contract 是由目前 Project geometry 與 Zoning 即時計算的 transient derived state，不寫回 Project，也不持久化。如此可避免 initial suggestion、Project Zoning 與 solver ordering 形成多份可漂移的 truth。

## Decisions

### 1. 以 Domain pure geometry policy 表達排向與 tolerance

新增小型、無狀態的 Domain geometry component（預期位於 `bracing_optimizer/domain/`），接受 physical Strut axes，產出 normalized axis facts、共同方向、row direction、midpoint projection 與 structured validation issues。

共同方向不得由第一筆 Project row 決定。實作採用 **undirected axial mean**：將每支軸方向以 double-angle representation 聚合，再還原共同無向軸，最後使用固定的幾何 sign convention 正規化方向。這能讓同一幾何在 Start／End 反轉或輸入重排後得到相同結果。

Zoning validation 直接檢查所有 physical axes：

- zero-length axis 無法建立方向，回傳 validation error；
- 任兩支必要比較的 undirected angle difference 必須 `<= 5°`；
- 任兩支長度差必須 `<= 5 mm`；
- optimization-unit projection difference `<= 1 mm` 視為無法建立唯一線性順序。

這些 tolerance 使用具名 Domain constants，避免 Application、DXF 與 Algorithms 各自保存 magic numbers。DXF initial grouping可重用方向／長度 eligibility primitive，但 topology 與 grouping policy仍留在 DXF subsystem。

**考慮但拒絕：**

- 以第一支 Strut 決定 canonical direction：會重新引入 row-order dependency。
- 直接按 midpoint X/Y 排序：只對特定圖面方向成立。
- 將 geometry interpretation 放入 `algorithms/support.py`：會讓 Algorithms 依賴 Project geometry 意義，違反既有 boundary。

### 2. Application 建立 explicit `SupportAdjacencyContract`

`SupportInputBuilder` 在每個 Zoning 建立 solver input 時，依下列順序建立 transient contract：

1. 取得該 Zoning 全部 physical Strut axes 並執行 geometry validation。
2. 先將相同 `SharedLayoutGroup` 的兩支 lane 合併為一個 optimization unit；normal Strut 各自為一個 unit。
3. normal unit 的代表位置為該 Strut axis midpoint；shared unit 的代表位置為兩 lane midpoint 的算術中心。
4. 將代表位置投影至共同 axis 的垂直 row direction。
5. 在 collapse shared lanes 後檢查 projection tie。
6. 依 projection 排序，並由相鄰 ordered units 建立 explicit adjacency pairs。

contract 概念上包含：

- ordered optimization units；
- 每個 unit 對應的 physical member IDs 與 configs；
- unit representative position 與 row projection；
- explicit consecutive unit pairs；
- geometry validation outcome。

contract **不包含 `representative_length`**。長度只從 physical axes 用於 5 mm validation；Jack region 也不依賴長度。

tie 的判斷只使用 projection distance。若超過 1 mm，projection 已提供唯一線性順序；若 `<= 1 mm`，直接 validation failure，不以 StrutID、Project row、dict insertion order 或 UI order作 fallback。幾何-derived secondary key只用於不影響 adjacency pair set 的 serialization／diagnostic ordering，不得繞過 tie error。

`SupportZoneInput` 持有或可直接取得這份 contract；既有 `.units` 不再以 config iteration order動態推導。`SupportConfig` 無須新增 Project axis，因為 geometry 已在 Application boundary 被消化。

**考慮但拒絕：**

- 將排序後 physical configs 當作隱含 contract：SharedLayoutGroup 仍會在 flatten 時產生錯誤的內部鄰接。
- 將 contract 保存於 `ProjectDataModel`：它是 derived solver input，持久化後會與可編輯 geometry／Zoning 漂移。
- 只為 SharedLayoutGroup 保存第一次出現的代表位置：仍依賴 input order。

### 3. DXF initial Zoning 是 Review 後、Project mapping 前的 pure operation

初始分組只在使用者已完成當次 DXF Review 中各 Waler／Strut 的必要確認與 geometry 修正，並執行「完成匯入」後觸發；圖層辨識、Review polling或局部修正本身不執行分組。分組使用該次最終 reviewed Strut geometry，並在`DXFImportResult.to_project_rows()`產生Project rows之前完成。輸入以canonical world geometry為準；start/end reversal只改表示，不改分組。

DXF operation 先從 reviewed Waler geometry 建立 continuous Waler chains。Waler segments使用既有`GeometryTolerances.parallel_angle_tolerance_deg`判定方向相容、`collinear_tolerance_mm`判定近似共線，並使用`endpoint_tolerance_mm`判定端點連接；近似共線且segment相交、重疊或端點連接時可屬於同一chain。這些都是既有recognition evidence tolerances，不是新的Solver hard constraint或新的工程常數。每支Strut的兩端連接被正規化為unordered chain-pair topology signature。

initial row grouping 的判斷分兩層：

1. **Eligibility**：不屬於同一個已確認SharedLayoutGroup的一般physical Struts必須符合`<= 5°`與`<= 5 mm`；這是進入同一建議群組的必要條件，但不是充分條件。已確認的SharedLayoutGroup是不可拆分的ordering-unit例外，兩lane仍保留供Solver validation使用。
2. **Contiguous row grouping**：先依 canonical transverse geometry 建立 deterministic 空間順序，再依 Waler-chain topology 與連續性形成 maximal contiguous runs。

具體規則：

- 相同 unordered continuous Waler-chain pair 是同排的強 topology evidence，即使來源 Waler member ID 不同仍可同組。
- 明確屬於不同 chain pair 的 Struts不得因距離接近被合併。
- connection 缺失或有歧義時，才以橫向空間相鄰作 fallback；fallback不得跨越中間其他支撐。
- 不設固定最大相鄰距離。只要中間沒有其他支撐、eligibility 與 topology/fallback 條件成立，即可維持同一 contiguous run。
- 若未知 topology 的 Strut 可同時合理歸入兩側不同 runs，系統不以來源順序猜測；該 Strut獨立成組並產生可診斷的 ambiguity indication。
- 掃描中的不相容 Strut會形成 boundary；不得把 boundary 兩側相容的 Struts跳接成同組。

現有DXF double-support decision仍保留兩支physical Struts與`SharedLayoutGroup`。只有使用者已在Review確認的shared pair才會作為一個空間ordering unit，以避免兩lane破壞contiguous ordering；兩lane取得相同initial Zoning，且其physical axes仍完整保留給Solver validation。若兩lane geometry超出5°／5 mm求解tolerance，初始資料仍可進Main並保存，但Support validation會在Phase 2前明確拒絕求解；系統不解除group、不拆分Zoning，也不以initial grouping隱藏問題。

Replace import 對本次全部 imported rows 套用建議；Append import只設定新 rows 的初始 Zoning，不讀寫或重新分組既有 Project rows。Zoning名稱配置必須 deterministic 且避開既有名稱，但名稱本身不參與 geometry判斷。

**考慮但拒絕：**

- 只以 5°／5 mm 做 connected-component grouping：會把不同支撐排合併，且 transitive edges可能形成 pairwise invalid group。
- 只比較 `FromWaler`／`ToWaler` member ID：同一 continuous chain可能由多個 Waler members構成。
- 使用固定 spatial gap threshold：需求已確認相鄰但距離較大的 Struts仍可同組。
- 在每次 Main edit後重跑 DXF grouping：會覆寫使用者 authoritative Zoning。

### 4. Phase 2 以 optimization unit 搜尋，不以 physical plan list 推導鄰接

Phase 1仍逐支 physical Strut產生 `SupportPlan` candidates，candidate cache key與 reuse policy不變。進入 Phase 2前，Application／Algorithm assembly依 adjacency contract組成 unit candidates：

- normal unit candidate包含一個 physical plan；
- shared unit candidate包含兩個 physical plans，兩者必須具有相同 `shared_layout_signature`。

目前Phase 1對單一physical Strut以完整`tuple(plan.pieces)`去重，而`shared_layout_signature`正是同一份完整ordered pieces，因此retained candidate pool中每個physical Strut的同一signature至多對應一個`SupportPlan`。unit assembly只建立signature索引並配對兩lane，不新增「每個signature只留最佳方案」之類的pruning，也不改Phase 1 candidate retention。若未來或異常輸入破壞此一對一invariant，assembly必須回報internal invariant failure，不得任意挑選或靜默刪除候選。

shared unit candidate assembly依序：

1. 以既有 ordered piece layout signature配對兩 lane candidates。
2. 保留兩個 physical plans，score與材料量仍分別計入。
3. 驗證兩 lane的 `jack_center` 相同；不一致時回傳 `SHARED_JACK_INVARIANT_VIOLATION`，不得任選其中一支。
4. 使用兩 lane configs中已共享／合併的 `pile_centers`。
5. 呼叫既有 `get_jack_region_id(shared_jack_center, merged_pile_centers)`，取得唯一 unit-level `jack_region_id`。

unit-level candidate／fact只需攜帶 unit ID、physical plans、shared `jack_center` 與 `jack_region_id`；不攜帶 Project geometry或 representative length。

Phase 2 Beam Search按 ordered units前進。每次只對 contract中相鄰 unit boundary套用：

- `abs(previous.jack_center - current.jack_center) >= 500 mm` hard constraint；
- Jack region consistency soft penalty一次。

SharedLayoutGroup內部不是 adjacency boundary，因此不執行一般500 mm spacing或 region penalty。材料比例、材料集中、plan score與 physical plan數量仍按照兩支 lane分別計算。

最後 `GlobalSolution.plans`仍輸出兩支 physical plans，以維持現有 UI、result model與 persistence contract；輸出順序採 unit geometry order，shared unit內使用 deterministic member geometry key。`min_jack_distance`、adjacent-distance diagnostics與 region summary必須在 unit boundaries計算，不能再對 flattened plans使用 `zip(plans, plans[1:])`推導。

完整adjacency contract、canonical direction、projection與unit runtime objects只存在於當次Application／Solver operation，不加入Project或result payload。成功commit的`GlobalSolution.search_diagnostics`可透過既有dict contract加入JSON-safe、optional的unit／pair diagnostic fields，並沿用`ProjectResultModel`現有serialization保存；這是既有`search_diagnostics`的backward-compatible extension，不是新的required schema。舊result缺少這些optional fields時照常載入；需要重新計算adjacency時，仍由current Project geometry重建contract，絕不從persisted diagnostics恢復工程ordering。

**考慮但拒絕：**

- 繼續以 flattened plan list跑 Beam Search並跳過同 group pair：shared group外側仍可能漏掉或重複 boundary。
- 以 Jack二維座標計算500 mm：與已核准的 longitudinal station語意不符。
- 將 shared group region取其中一支 lane：會掩蓋 invariant violation，並可能受 lane order影響。

### 5. 共用一個 Algorithm-level unit scoring path

`pair_penalty`／全域 summary將以 unit-level Jack facts為輸入，或由同一 pure helper提供。Phase 2、fallback solution、manual recalculation、`min_jack_distance`與 diagnostics都呼叫同一路徑。不得保留一套 geometry adjacency給initial solve、另一套 list adjacency給旁路。

Algorithms收到的 adjacency pair sequence已由 Application contract決定；Algorithms只檢查500 mm hard constraint與計算既有 region penalty，不重新排序。

diagnostics需要能指出：

- Zoning與涉入 member IDs；
- validation code；
- angle／length／projection的實際值與 tolerance；
- 若為SharedLayoutGroup invariant failure，列出group與兩 lane Jack stations；
- 若為Phase 2鄰接失敗，列出相鄰 unit IDs與station difference。

使用structured data保留既有 Presentation格式化邊界，不讓Algorithms組合UI訊息。

成功solution的unit／pair diagnostics放在既有`search_diagnostics`中的optional fields，供save/load後顯示當次求解依據；它們不是後續求解的input。pre-Phase-2 validation failure因不commit新result，只透過當次Application error／diagnostic response回傳，不建立可持久化的失敗result。`SolverDiagnostics.from_dict()`與Presentation projection必須將缺少新fields視為正常舊payload。

### 6. Manual editing重建相同 contract，失敗時不 commit staged result

`SupportPlanEditing`在 edit／global recalculation前，透過`SupportInputBuilder`或共用Application builder，從目前Project geometry與Zoning重建相同`SupportAdjacencyContract`。它不自行掃描physical plan list尋找previous／next。

- `neighbor_checks`查詢contract中包含目標unit的前後adjacency pairs。
- normal edit只替換該unit的一個physical plan。
- shared edit仍同步處理兩 lane，並重新執行shared Jack invariant與unit-level region計算。
- 全域score、500 mm legality、region penalty與`min_jack_distance`呼叫與initial solve相同的unit scoring path。

若current Zoning geometry invalid、projection tie或shared Jack invariant失敗，staged edit不commit；既有committed `ProjectResultModel`保持不變並回傳structured validation。TargetJackRegion仍只是preference，不因本change升級為manual edit hard constraint。

### 7. Validation與result transaction boundary留在Application

Zoning geometry validation不加入`ProjectDomainModel.validate()`、save validation或Main field editor。因此使用者可建立、修改與保存超出5°／5 mm的Zoning。

validation發生在：

- Support solve建立`SupportZoneInput`時；
- manual Support result edit需要重算global solution時；
- 明確的solver preflight／data validation入口。

invalid Zoning不會進入Phase 2。Application先建立並驗證完整transient input／candidate state，成功後才替換result；任何pre-commit failure或dialog discard都保留先前committed result。validation不得修改Project Zoning或自動呼叫DXF grouping。

建議的stable diagnostic codes包括：

- `ZONING_ZERO_LENGTH_AXIS`
- `ZONING_ANGLE_OUT_OF_TOLERANCE`
- `ZONING_LENGTH_OUT_OF_TOLERANCE`
- `ZONING_PROJECTION_TIE`
- `SHARED_JACK_INVARIANT_VIOLATION`

code由Application error contract承載；UI顯示文字可在Presentation層本地化。

### 8. Backward compatibility與persistence

本change不新增或遷移Project／result schema：

- `Zoning`與`SharedLayoutGroup`仍使用現有Project row fields。
- adjacency contract、canonical direction、projection與unit facts都是runtime-derived state。
- 成功Support result的unit／pair diagnostic snapshots可作為既有`search_diagnostics`的optional JSON fields保存；這些欄位不構成adjacency truth，也不改schema version。
- 現有Project即使包含geometry-invalid Zoning仍可load、edit與save；只有Support validation／solve被拒絕。
- 舊的committed solver result仍可反序列化。新求解成功時以新語意commit；失敗時舊result保持不變。
- DXF import輸出的Project row contract不增加必填欄位，只改變新rows的initial `Zoning`值。

因此不需要data migration。若回滾implementation，Project檔案仍可由舊版本讀取；唯一回滾差異是舊版本會恢復以input order判定adjacency。

## Data Flows

### DXF initial Zoning

```text
DXF recognition result
  -> Required Waler/Strut confirmation + manual geometry corrections
  -> User completes import
  -> reviewed Strut + Waler world geometry
  -> continuous Waler chain derivation
  -> eligibility + deterministic transverse order
  -> maximal contiguous initial-row groups
  -> DXFImportResult.to_project_rows()
  -> Project rows with initial Zoning suggestion
```

### Support solve

```text
ProjectDataModel (authoritative user Zoning)
  -> ProjectDomainModel
  -> SupportInputBuilder
       -> Domain geometry validation
       -> SharedLayoutGroup collapse
       -> ordered SupportAdjacencyContract
       -> SupportZoneInput
  -> Phase 1 physical candidates (unchanged)
  -> assemble unit candidates
  -> Phase 2 over ordered units
  -> flatten selected physical plans
  -> staged GlobalSolution
  -> success commit to ProjectResultModel
```

### Manual Support result edit

```text
Current Project geometry + Zoning
  -> rebuild same SupportAdjacencyContract
  -> stage edited physical plan(s)
  -> assemble affected unit(s)
  -> shared invariant + unit adjacency validation
  -> common global scoring / diagnostics
  -> success commit

failure before commit -> previous committed result unchanged
```

## Risks / Trade-offs

- **[DXF Waler chain over-merge或under-merge]** → 僅使用reviewed geometry與既有DXF tolerance，保存可診斷的chain evidence，並以explicit different-chain boundary阻止spatial fallback跨鏈合併。
- **[無最大距離可能把相距很遠但連續的eligible Struts分在同組]** → 這是已確認產品語意；以topology、不中斷的transverse order與diagnostics降低不可解釋性，不私自加入gap threshold。
- **[pairwise tolerance不具傳遞性]** → 每個proposed initial group與solver Zoning都驗證全部必要physical pairs，不以connected component的單純傳遞性宣稱整組合法。
- **[浮點誤差造成方向或排序不穩定]** → 使用normalized vectors、undirected axial mean、具名numeric epsilon；正式tie仍嚴格依`<= 1 mm`判定，不用row/ID fallback。
- **[SharedLayoutGroup candidate組合增加Phase 2組合量]** → 先依既有`shared_layout_signature`索引／配對，再形成unit candidates；不改Phase 1 candidate count或Beam width。
- **[同時保留physical plans與transient unit facts可能漂移]** → unit facts只在assembly時從physical plans計算且不可獨立修改；manual edit後必須重組受影響unit。
- **[舊result沒有adjacency contract]** → contract永遠從current Project geometry重建，不要求舊payload補資料；只在需要重新計算時使用新語意。
- **[initial grouping與solver validity被誤當同一件事]** → API與diagnostic分開命名；DXF grouping只寫初值，Application validation不回寫Project。

## Migration Plan

不需要資料 migration或feature-specific persistence rollout。實作可在同一版本切換runtime行為：

1. 先加入pure geometry policy與Application adjacency contract，保留既有public Project/result schema。
2. 讓Phase 2及所有summary／diagnostic consumers改用unit contract後，再移除list-adjacency內部路徑，避免同時存在兩套truth。
3. 將manual editing切換至同一builder與scoring path。
4. 最後在DXF Review到Project mapping boundary加入initial Zoning suggestion；Main對Zoning的ownership與保存行為不變。

回滾時可移除runtime contract／DXF suggestion接線，無須回復任何已儲存資料。已由新版本保存的Zoning仍是普通Project data，舊版可讀取。

## Open Questions

無。現有Spec所需的產品與工程決策均已關閉；後續實作若發現必須改變requirement、architecture boundary或persistence contract，應停止並回到change artifacts修正，而非在code中自行決定。
