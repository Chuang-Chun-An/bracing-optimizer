# Spec Delta

## 閱讀導航

### 現在必讀

1. 「完整斜切封閉外框 SHALL 可由拓撲建立 Brace body」：定義斜切外框何時取代共用 rail coverage gate。
2. 「斜切封閉外框的來源軸 SHALL 由有限端面界定」：定義正確中心線與端點。
3. 「斜切外框辨識 SHALL 保留既有安全邊界」：定義失敗、歧義與回歸範圍。

### 條件式閱讀

- 實作 width measurement 時，搭配 main spec 的「Brace 實體寬度 SHALL 通過正式 hard gate」。
- 實作 authority／fallback 時，搭配 main spec 的「Component-like Brace SHALL 依 whole-source center authority 選軸」。
- 實作 terminal-to-Waler 時，閱讀 `brace-axis-waler-extension` 的 direct、outward-ray、member verdict requirements。

### 可先跳過

- Y05 fragmented BIM root、CornerBrace、Joist、Double Support 與 Solver specs；本 delta 不改變這些行為。

## ADDED Requirements

### Requirement: 完整斜切封閉外框 SHALL 可由拓撲建立 Brace body

當 Brace-role 來源具有單一、封閉、無自交、無分支且可唯一遍歷的 body boundary，且該 boundary 可唯一分解為一對方向相容的 outer longitudinal rails 與兩個分別連接 rail 兩端的有限 terminal cuts 時，系統 SHALL 將整個 closed topology 視為完整 Brace body evidence。此完整性 SHALL 由 rail 與 terminal cut 的連接拓撲共同建立，不得因斜切造成其中一條有限 rail 對全體 longitudinal projection 的覆蓋率低於共用 `minimum_projection_overlap_ratio = 0.8` 而單獨拒絕。

上述例外只適用於可唯一驗證的完整 closed topology。開放 rail pair、fragmented evidence、whole-root outer-envelope、local rail-pair fallback、缺邊、branch、T-junction、自交或無法唯一遍歷的 boundary，仍 MUST 依既有 `minimum_projection_overlap_ratio = 0.8` 與 authority rules 判定；本 Requirement MUST NOT 被解讀為將全域門檻改成 `0.7` 或其他較低數值。

兩條 outer rails MUST 唯一支持相同主要方向與同一 body corridor，其 supporting lines 的正交 separation MUST 作為 body width。該寬度仍 MUST 嚴格 `> 250.0 mm` 且 `<= maximum_component_width_mm`；terminal cut 的有限長度、斜率、兩個 cut 長度的差異、rail 長度差與 bounding-box 尺寸 MUST NOT 取代或修改 body width。

兩條 outer rails 各自的有限長度 MUST `>= minimum_component_length_mm`，且沿選定主要方向 MUST 具有正的 longitudinal overlap，以證明存在由兩側共同支持的 body corridor。每個 terminal cut 的方向 MUST NOT 在既有 `parallel_angle_tolerance_deg` 內與 selected outer rails 平行。這些退化保護 MUST 只使用既有 tolerance 與既有嚴格／含等號邊界，不得為本 Requirement 新增未命名門檻；若既有 tolerance 無法排除退化案例，實作 MUST 停止並回報規格／tolerance 缺口，不得自行加入 magic number。

此 Requirement 是 DXF Recognition Hard Constraint，不是 Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 兩端斜切但封閉拓撲完整

- **WHEN** 一個 Brace closed outline 具有唯一的一對平行 outer rails，兩條 rails 長度因兩端斜切而不同，且其餘 boundary 各自完整連接兩 rail 的起端與終端
- **THEN** 系統 SHALL 以該 closed topology 建立一支 Brace body candidate
- **AND** MUST NOT 只因較短 rail 的 longitudinal coverage `< 0.8` 而回報 `BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE`

#### Scenario: 開放 rail pair 不取得斜切 topology 例外

- **WHEN** 兩條平行 rails 沒有兩個可驗證的有限 terminal cuts，或來源 boundary 並未形成單一 closed traversal
- **THEN** 系統 MUST NOT 以斜切 closed-outline 規則宣告完整 body
- **AND** SHALL 繼續套用既有 `minimum_projection_overlap_ratio = 0.8`、whole-source support 與 fallback rules

#### Scenario: 斜切端面長度不等於 Brace 寬度

- **WHEN** 一個合法斜切 closed outline 的 rail supporting-line separation 為 `400.0 mm`，但任一 terminal cut 因斜率而長於 `400.0 mm`
- **THEN** 系統 SHALL 將 body width 記錄為 `400.0 mm`
- **AND** MUST NOT 以 terminal cut length、兩 cut 平均長度或 bounding-box width 取代

#### Scenario: 多組不等價 rail interpretations 保持 ambiguous

- **WHEN** 同一 closed boundary 支持兩組以上不等價且均通過 width 與完整性條件的 outer rail interpretations，且既有 authority rules 無法唯一區分
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** MUST NOT 依 edge order、polyline start vertex、candidate score 或較長 rail 任選一組

#### Scenario: 破損或分支外框不得假裝完整

- **WHEN** Brace outline 缺少任一 terminal connection、具有 self-intersection、branch、T-junction、懸空 detail，或無法形成唯一無分支 boundary traversal
- **THEN** 系統 MUST NOT 以本 Requirement 建立 closed-topology Brace
- **AND** SHALL 依既有 authority pipeline 評估其他合法 evidence，若無合法候選則保留 reviewable failure／ambiguity

#### Scenario: 一條長邊極短的近三角形外框不得建立 closed-topology Brace

- **WHEN** 一個封閉近三角形外框可勉強列舉出兩條近似平行邊，但其中任一 selected outer rail 的有限長度 `< minimum_component_length_mm`
- **THEN** 系統 MUST NOT 以 closed-topology 規則建立 Brace body
- **AND** MUST NOT 以降低最小長度、比例化短邊或新增未命名門檻使其通過

#### Scenario: 端面幾乎與長邊平行不得建立 closed-topology Brace

- **WHEN** 任一候選 terminal cut 的方向在 `parallel_angle_tolerance_deg` 內與 selected outer rails 平行
- **THEN** 系統 MUST NOT 將該邊視為 terminal cut
- **AND** 若不存在其他唯一合法 decomposition，MUST NOT 建立 closed-topology Brace

#### Scenario: 兩條長邊沒有共同 longitudinal overlap 不得建立 closed-topology Brace

- **WHEN** 兩條候選 outer rails 沿選定主要方向的有限投影沒有正的 longitudinal overlap
- **THEN** 系統 MUST NOT 宣告兩條 rails 形成共同 body corridor
- **AND** MUST NOT 以 closed-topology 規則建立 Brace body

### Requirement: 斜切封閉外框的來源軸 SHALL 由有限端面界定

對已通過完整斜切 closed topology 的 Brace，系統 SHALL 以兩條 selected outer rail supporting lines 的正中 supporting line 作為 source-supported center authority。recognition axis 的兩個 longitudinal endpoints MUST 分別是該 midline 與起端及終端 terminal cut 的合法有限交點；當 terminal cut 是直接連接兩條平行 rail 的單一線段時，該交點等價於 terminal cut 的幾何中點。

系統 MUST NOT 以所有 outline vertices 沿主要方向的最小／最大 projection 建立斜切來源端點，因為該作法會把中心軸延伸到實體 terminal cut 之外。系統亦 MUST NOT 在 recognition 階段為碰觸 Waler 而放大 source-supported extent；合法 Waler direct／outward-ray connection 仍 SHALL 由既有 `brace-axis-waler-extension` capability 在 recognition 成功後處理。

#### Scenario: Midline 與斜切端面交點建立來源軸

- **WHEN** 兩條 selected outer rails 與兩個 terminal cuts 唯一形成合法斜切 closed outline
- **THEN** recognition axis SHALL 位於兩條 rail supporting lines 的正中位置
- **AND** 兩個 source-supported endpoints SHALL 分別位於 midline 與兩個有限 terminal cuts 的交點

#### Scenario: Projection extrema 不得使軸超出外框

- **WHEN** 斜切造成某一 rail endpoint 比另一 rail endpoint 沿主要方向突出
- **THEN** 系統 MUST NOT 將突出頂點的 longitudinal projection 直接投影到 midline 作為來源端點
- **AND** recognition axis MUST 終止於實際 terminal cut

#### Scenario: Polyline traversal 反轉不改變幾何結果

- **WHEN** 同一 closed outline 改變起始 vertex、順時針／逆時針 traversal 或 LINE start／end direction，但 WCS boundary geometry 與 source identity 等價
- **THEN** 系統 SHALL 產生等價的 selected rails、body width、terminal cuts 與無方向 source axis
- **AND** outcome MUST NOT 因 enumeration order 改變

#### Scenario: Terminal cut 與 midline 沒有合法有限交點

- **WHEN** 候選 terminal boundary 只能與 midline 的無限延長線相交、交點位於有限 terminal segment 之外，或兩端交點無法形成正長度 axis
- **THEN** 該 closed-topology candidate MUST 被拒絕
- **AND** 系統 SHALL 依既有 authority pipeline 尋找其他合法候選，若無合法候選則回報 blocking failure

### Requirement: 斜切外框辨識 SHALL 保留既有安全邊界

斜切 closed-outline recognition 成功 SHALL 只建立可靠的 source-supported body axis、outer rails、terminal cuts、body width 與 exact source provenance。後續 terminal evidence、Waler contact-face finalization、member-level verdict、Review state 與 Project conversion MUST 沿用既有單向流程與 atomic formal-Brace contract。

當來源軸一端同時對應兩支以上無法區分的 active Waler identities 時，該端 MUST 維持 ambiguous；terminal cut、完整 closed topology、較小 connection distance或任一 source order MUST NOT 靜默指定 winner。整支 Brace 只有在兩端各自唯一連接不同有限 Waler、兩端 selected contact faces 正式完成且軸與兩面各有合法有限交點時，才能成為 formal Brace。

#### Scenario: Y29 71A 以預設門檻建立可靠來源軸

- **WHEN** 系統以預設 tolerances 辨識 Y29 Brace source handle `71A`，其 outer rail 長度約為 `3958.97 mm` 與 `5117.64 mm`、較短 rail 對整體 projection coverage 約為 `77.36%`，且 supporting-line separation 約為 `400.0 mm`
- **THEN** 系統 SHALL 以完整斜切 closed topology 建立一支 source-supported Brace candidate
- **AND** recognition axis endpoints SHALL 在既有幾何 tolerance 內等價於兩個 terminal cuts 與 body midline 的有限交點，約為 `(230552.691, -457043.396)` 與 `(234567.188, -459160.000)`
- **AND** MUST NOT 將全域 `minimum_projection_overlap_ratio` 改為 `0.7`

#### Scenario: Y29 71A 的重疊 Waler identity 仍保持多解

- **WHEN** `71A` 的可靠來源軸已建立，但同一 terminal resolution 位置仍同時對應 active Waler sources `69F` 與 `720`，且既有 ambiguity boundary 無法唯一區分
- **THEN** 系統 SHALL 保留兩個競爭 identities 並維持該端 ambiguous
- **AND** 整支 Brace MUST 維持 unresolved，直到 active sources 或明確 Review decision 使兩端可依既有 contract 唯一驗證

#### Scenario: 既有合法 Brace 不因新路徑改軸

- **WHEN** Brace 來源原本已由一般矩形 closed outline、MLINE、明確 centerline、完整 parallel edges 或 component-like fragmented route 可靠辨識
- **THEN** 新增的斜切 closed-topology behavior MUST NOT 改變其等價 source axis、body width、source identity 或既有 connection outcome

#### Scenario: 不同 source scopes 不得因共線而自動合併

- **WHEN** 兩個獨立 Brace source scopes 各自形成合法斜切 closed outline，且其 axes 共線、接近或部分重疊
- **THEN** 系統 MUST 保留各自 exact source provenance
- **AND** MUST NOT 僅因本 change 放寬 closed-topology eligibility 就跨 source scope 拼接為一個 body
- **AND** 是否屬於重複工程構件仍 SHALL 由既有、可追溯的 deduplication contract 判定
