# Spec Delta

## ADDED Requirements

### Requirement: BIM Strut transverse center authority SHALL follow qualified whole-source evidence order

對同一 Strut root `INSERT`，系統 SHALL 在方向、root provenance 與既有 component eligibility 成立後，依下列 evidence order 決定 transverse center authority：第一，唯一且可驗證的無分支完整外框；第二，唯一可靠的 whole-root outer-envelope；第三，僅在前兩層均沒有合格候選時使用 local fragmented rail-pair fallback。較低層候選不得因先被產生、局部 confidence 較高或 source-only route 先成功，就排除或覆寫較高層候選。

Tier 2 whole-root outer-envelope MUST 由可共同支持完整 component corridor 的 component-boundary evidence 建立。可作為 outer face 的 longitudinal evidence MUST 通過既有 direction、coverage、length、slenderness、width compatibility、same-root provenance 與 whole-component completeness eligibility。系統 MUST NOT 直接對同一 root 內所有平行 longitudinal rails 取 transverse global minimum／maximum；短 detail、branch rail、connection detail、局部 rail，或無法共同支持完整 corridor 的線段不得成為 Tier 2 outer face。這些線段可參與 completeness／conflict 診斷，但 MUST NOT 改寫 Tier 2 center 或 `source_width`。

系統 SHALL 先把同一層幾何等價的候選合併為一致 evidence，再判定該層是否唯一。若目前最高合格層含有多個幾何不等價且無法由既有資格規則區分的中心，系統 MUST 回報 blocking ambiguity，且 MUST NOT 退到較低層、依 score、距離、`INSERT` point、handle、entity order 或 candidate order 任選。

Axis equivalence 與 width reconciliation MUST 分開判定。同一 authority tier 中，中心軸等價但 envelope width 不同的候選 SHALL 合併為一個 center evidence group；合併後系統 MUST NOT 依 candidate order、first occurrence 或 recognition method 任選 `representative_width`。系統 SHALL 僅從該 center group 的有效 envelopes，依 topology、whole extent、containment 與 component-envelope credibility 尋找唯一實體外包絡。若 center 唯一但有效 envelope 不唯一或無法唯一決定外包絡，系統 SHALL 保留該 axis、將 `source_width` 視為 unknown，且 MUST NOT 將 width ambiguity 升級為 center ambiguity。

Waler context SHALL 只提供 longitudinal corridor 與 terminal span evidence；transverse center 與來源寬度仍 MUST 由該 Strut root 自身的 source geometry 支持。

#### Scenario: Valid full outline has first center authority

- **WHEN** 同一 root 具有唯一可驗證的無分支完整外框，且另有 whole-root outer-envelope 或 local rail-pair 候選
- **THEN** 系統 SHALL 以該完整外框的中心作為 transverse center
- **AND** 幾何不等價的較低層候選 SHALL NOT 覆寫該中心

#### Scenario: Unique whole-root envelope precedes local fallback

- **WHEN** 同一 root 沒有合格的完整外框，但 outermost longitudinal evidence 可唯一建立可靠 whole-root outer-envelope，且另有幾何不等價的 local rail-pair 候選
- **THEN** 系統 SHALL 以 whole-root outer-envelope 的中心作為 transverse center
- **AND** SHALL NOT 因 local 候選先被辨識而排除 whole-root 候選

#### Scenario: Tier 2 outer rails ignore internal branch rails

- **WHEN** 同一 root 具有兩條通過全部 component-boundary eligibility、共同支持完整 corridor 的 outer rails，且其間另有 internal branch rails
- **THEN** Tier 2 SHALL 以合格 outer rails 建立 center 與 envelope
- **AND** internal branch rails 可參與 completeness 診斷但 SHALL NOT 改寫 Tier 2 center 或 `source_width`

#### Scenario: Short outer detail cannot expand the Tier 2 envelope

- **WHEN** 一條位於合格 component envelope 外側的短 detail line 或 connection detail 未通過既有 coverage、length、slenderness 或 whole-component completeness eligibility
- **THEN** 該線 SHALL NOT 成為 Tier 2 outer face
- **AND** SHALL NOT 擴大 envelope、偏移 center 或改寫 `source_width`

#### Scenario: Raw global transverse extremes are not an envelope

- **WHEN** root 內所有平行 longitudinal rails 的 raw transverse minimum／maximum 來自無法共同支持完整 component corridor 的不同 detail evidence
- **THEN** 系統 MUST NOT 以該 raw global minimum／maximum 建立 Tier 2 envelope
- **AND** SHALL 僅評估通過全部 component-boundary eligibility 的 envelope interpretations

#### Scenario: Two complete Tier 2 interpretations remain ambiguous

- **WHEN** 同一 root 存在兩個中心軸不等價、且各自均通過 direction、coverage、length、slenderness、width、same-root 與 whole-component completeness 的完整 outer-envelope interpretations
- **THEN** 系統 SHALL 回報 blocking center ambiguity
- **AND** SHALL NOT 依較外側、較寬、candidate order 或 Tier 3 outcome 任選

#### Scenario: Local rail-pair remains the final compatibility fallback

- **WHEN** 同一 root 沒有合格的完整外框，也沒有唯一可靠的 whole-root outer-envelope，但既有 local fragmented rail-pair eligibility 可唯一建立中心
- **THEN** 系統 SHALL 維持 local fragmented rail-pair fallback behavior
- **AND** SHALL NOT 僅因前兩層缺席就把來源自動判成多構件

#### Scenario: Competing centers at the highest eligible tier remain ambiguous

- **WHEN** 目前最高合格 evidence tier 產生多個幾何不等價的中心，且既有完整性與 ambiguity rules 無法唯一區分
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** SHALL NOT 以較低層候選或非幾何順序規則任選中心

#### Scenario: Same-axis candidates form one center group before width reconciliation

- **WHEN** 同一 authority tier 有多個中心軸幾何等價但 envelope width 不同的合格候選
- **THEN** 系統 SHALL 將它們合併為一個 center evidence group，並保留唯一 axis
- **AND** SHALL 另行執行 envelope reconciliation，而非將不同 width 視為 center ambiguity

#### Scenario: Nested same-axis envelopes select the unique physical outer envelope

- **WHEN** 同一 center group 具有多個同軸、完整、可信且呈 containment 關係的有效 envelopes，並可唯一辨識最外層實體 component envelope
- **THEN** 系統 SHALL 以該唯一外包絡推導 `source_width`
- **AND** SHALL NOT 依 first occurrence、較小 envelope 或 recognition method 選擇寬度

#### Scenario: Known axis with unresolved envelope preserves unknown width

- **WHEN** center evidence group 可唯一建立工程軸，但多個有效 envelopes 無法依 topology、whole extent、containment 與 component-envelope credibility 唯一決定實體外包絡
- **THEN** 系統 SHALL 保留該唯一 axis
- **AND** SHALL 將 `source_width` 視為 unknown
- **AND** SHALL NOT 回報 center ambiguity 或任選 `representative_width`

#### Scenario: Waler span cannot choose a lateral center

- **WHEN** Waler context 可唯一界定 Strut 的 longitudinal terminal span，但 root source geometry 仍支持多個無法唯一區分的 transverse centers
- **THEN** 系統 SHALL 保留 ambiguity
- **AND** SHALL NOT 以 Waler 中點、接觸面或最近距離替 Strut 選擇 transverse center

#### Scenario: Y05 S20 uses its whole-root outer envelope

- **WHEN** Y05 S20 root handle `B05` 的等價 WCS geometry 沒有更高層的合格無分支完整外框，但 outermost rails 約位於 `X = 53294.5` 與 `X = 53644.5`，並共同支持唯一 whole-root envelope
- **THEN** 系統 SHALL 建立約 `X = 53469.5`、來源寬度約 `350 mm` 的工程軸
- **AND** SHALL NOT 採用約 `X = 53379.0`、局部寬度約 `204 mm` 的 local rail-pair 中心
- **AND** Tier 2 成功取得 authority 後，Tier 3 SHALL NOT 再參與 winner selection 或改寫寬度

#### Scenario: Mirrored whole-root evidence yields mirrored component envelopes

- **WHEN** Y05 root handles `957` 與 `B05` 的等價 WCS source geometry 互為鏡像，且兩者均由相同資格的 whole-root outer rails 支持唯一 350 mm component envelope
- **THEN** 系統 SHALL 分別建立約 `X = -53469.5` 與 `X = 53469.5` 的鏡像工程軸
- **AND** SHALL NOT 讓 `957` 因既有 regression 或 local rail-pair 先出現而保留約 `X = -53379.0`、204 mm 的非對稱結果

## MODIFIED Requirements

### Requirement: The formal axis SHALL represent the whole supported component extent

對已通過 component-like eligibility 的 root `INSERT`，系統 SHALL 從 whole-source geometry 與有效 Waler context 共同推導唯一工程軸。候選軸的方向與 transverse position MUST 由同一 root 的來源 geometry 支持；正式 longitudinal terminal extent SHALL 由沿該軸兩側唯一包圍來源的有限 Waler intersections 界定，並由 Waler-bounded corridor 內的 whole-root evidence 驗證。系統不得只使用其中一個 fragment、局部 closed outline、局部漂亮平行邊對或最長單一 LINE 的位置與長度。

內部 fragment gaps 不構成自動拆件條件。即使 gap 明顯大於一般 LINE recognition 的 small-gap tolerance，只要 root identity、共同方向、transverse alignment、寬度相容性、whole-root completeness 與兩端 Waler span 仍提供強而一致的證據，系統 SHALL 允許跨越該 interior gap 重建一支 Strut。系統 MUST NOT 越過已選定的有限 Waler intersections，亦不得以 Waler context 憑空產生缺乏來源 geometry 支持的方向或 transverse center。

#### Scenario: Complete outline produces one full Strut

- **WHEN** BIM Strut root `INSERT` 具有可唯一支持完整構件方向與 transverse center 的正常封閉外框，且候選軸兩側各有唯一正式 Waler intersection
- **THEN** 系統 SHALL 辨識為一支以該兩端 Waler contact geometry 為 terminal extent 的 Strut

#### Scenario: Occlusion gaps do not split a supported component

- **WHEN** 同一 root `INSERT` 的 aligned fragments 之間存在明顯 interior gaps，但 whole-root axis、width、alignment 與兩端 Waler span 強烈支持同一構件
- **THEN** 系統 SHALL 重建一支跨越 interior gaps 的完整 Strut
- **AND** 不得只因 gap 大而拆成多支 Strut

#### Scenario: Local short parallel pair cannot truncate the member

- **WHEN** 一支由兩端 Waler 界定約 12 m span 的 component-like Strut Block 含有一組約 3 m 的局部平行邊，而其他 aligned root evidence 支持完整 corridor
- **THEN** 正式工程軸 SHALL 代表 Waler-bounded whole component extent
- **AND** 系統不得產生只涵蓋該 3 m 局部 pair 的正式 Strut

#### Scenario: Y05 S2 retains the whole supported axis

- **WHEN** Y05 S2 root handle `957` 的等價 WCS geometry 由多組沿共同縱向排列的 LINE fragments 形成，兩端正式 Waler 與整體 evidence 支持約 `18,900 mm` 的完整軸，且合格 whole-root outer rails 位於約 `X = -53644.5` 與 `X = -53294.5`
- **THEN** BIM component-like recognition SHALL 重建約 `(-53469.5, -9450) → (-53469.5, 9450)`、來源寬度約 `350 mm` 的完整工程軸
- **AND** SHALL NOT 採用約 `X = -53379.0`、局部寬度約 `204 mm` 的 local rail-pair 中心
- **AND** SHALL NOT 退回既有約 `6,978 mm`、約 `(-53379, -3488.368) → (-53379, 3489.368)` 的局部平行邊辨識

### Requirement: Same-source outline topology SHALL constrain Strut rail pairing

對位於 Strut role layer 的單一 root `INSERT`，系統 SHALL 將可辨識的完整外框或等價的連續 rail topology 視為 longitudinal rail pairing 的來源邊界。可取得中心 authority 的 outline topology MUST 能以不依賴內部 detail rails 的無分支 boundary traversal 驗證其對應 longitudinal rails；單純位於同一 connected component 不足以證明它是一個 component envelope。若 connected graph 含有 branch、T-junction 或接入外框的內部 detail rails，系統 MUST NOT 將整個 branched graph 直接折算為一個外框中心或寬度；只有能從該 graph 獨立驗證的無分支完整 boundary 才可保留為 outline candidate。

Topology graph 的 endpoint equivalence 與後續 boundary geometry MUST 使用一致的既有 endpoint tolerance。已被 graph adjacency 判定為同一節點的端點 SHALL 映射到單一 deterministic canonical node，再用於 outline center、direction 與 width 計算；系統 MUST NOT 在後續以精確浮點座標重新去重，使同一角點因微小數值差異被重複加權。此 normalization 只合併既有 tolerance 內的同一 topology node，不得跨越 root、擴大 tolerance 或連接原本不相鄰的 geometry。

兩條 longitudinal rail 只有在同一個可驗證 outline／rail topology 中互為對應邊時，才可共同推導工程中線；系統 MUST NOT 將不同 outline topology 的 rail 交叉配對，也不得只因兩條 rail 平行、長度相近、投影重疊、間距合理或位於同一 root source，就認定它們互為 companion rails。

同一 root source 可以含有寬度不同的多層外框。若各外框各自推導的完整軸幾何等價，系統 SHALL 將它們視為同一支 Strut 的一致 evidence，並以共同軸建立一個 formal Strut；多層外框不得因此形成多支 Strut，也不得產生由跨外框配對造成的橫向偏移軸。

此規則是 DXF recognition 的來源幾何語意，不是新的工程設計限制、材料寬度規則或 Solver rule。

#### Scenario: Same-axis nested outlines produce one engineering axis

- **WHEN** 一個 Strut root `INSERT` 內含寬度不同、但各自具可驗證完整 outline topology 的兩層同軸外框
- **THEN** 系統 SHALL 從每個 outline 的自身對應 rail 推導工程軸
- **AND** 若兩軸幾何等價，系統 SHALL 建立一支具有該共同軸的 formal Strut
- **AND** SHALL NOT 將一層外框的一邊與另一層外框的一邊配對成偏移中心線

#### Scenario: Y05 S10 ignores open detail rails when deriving its axis

- **WHEN** Y05 S10 root handle `D17` 的等價 WCS geometry 包含約 `350 mm` 寬的完整 connected contour，以及間距約 `12 mm`、全長同軸但沒有端部連接或共同封閉 traversal 的開放 detail rails
- **THEN** 系統 SHALL 建立約 `X = -15498.5` 的共同縱向工程軸
- **AND** 約 `12 mm` 的開放 detail rails SHALL NOT 被視為獨立完整 outline 或可驗證的 companion rails
- **AND** SHALL NOT 以跨外框 rail 配對產生約 `X = -15414` 或約 `X = -15589` 的偏移工程軸

#### Scenario: Branched connected contour cannot directly define an envelope

- **WHEN** 一個 Strut root 的 outer rails 與內部 detail rails 因 branch 或 T-junction 形成單一 connected graph，但該整體 graph 不是無分支的完整 boundary traversal
- **THEN** 系統 MUST NOT 直接以整體 connected graph 推導 component center 或 `source_width`
- **AND** SHALL 繼續依合格 whole-root outer-envelope 或既有 fallback rules 判定，而不是把 connected 當成完整外框

#### Scenario: Tolerance-equivalent contour endpoints have one canonical node

- **WHEN** 一個有效無分支完整外框的相鄰 segments 端點只存在既有 endpoint tolerance 內的浮點微差，且 topology adjacency 已將它們視為同一節點
- **THEN** outline center、direction 與 width SHALL 使用單一 deterministic canonical node
- **AND** SHALL NOT 因 raw endpoint exact-value 不同而重複加權該角點

#### Scenario: Y05 S11 keeps its valid Tier 1 outline after endpoint normalization

- **WHEN** Y05 S11 root handle `D19` 的等價 WCS geometry 具有 outer rails 約位於 `X = -5673.5` 與 `X = -5323.5` 的有效無分支四邊外框，且同一角點的 raw endpoints 只有浮點微差
- **THEN** tolerance-normalized Tier 1 topology SHALL 建立約 `X = -5498.5`、來源寬度約 `350 mm` 的工程軸
- **AND** SHALL NOT 因同一角點保留多份 raw coordinates 而產生傾斜軸或約 `408.34 mm` 的 envelope width

#### Scenario: Ordinary root INSERT without usable outline topology retains compatibility

- **WHEN** 一個非 component-like root `INSERT` 沒有可驗證的完整 outline／rail topology
- **THEN** 系統 SHALL 維持既有 non-component fallback eligibility
- **AND** 本 requirement 不得僅因缺乏 topology evidence 而把該 source 視為多構件或強制產生 blocking problem

### Requirement: Recognized Strut width SHALL come from a unique valid component envelope

系統 SHALL 將 Strut 工程軸辨識與 `source_width` 判定視為兩個相關但可獨立成立的結果。Strut 不具有固定 350 mm 寬度；對不同合法支撐寬度，系統 SHALL 從該 root source 內唯一、完整且可靠的 component envelope 橫向尺寸推導 `source_width`。

有效 component envelope 必須具有可驗證的 closed outline、無分支 connected boundary traversal，或由 whole-root outermost longitudinal evidence 唯一支持的外包絡；它 MUST 支持完整構件 longitudinal extent，並能將 envelope boundary 與內部 detail rails 區分。當同軸、全長且巢狀的有效外框存在唯一外包絡時，系統 SHALL 以該外包絡寬度作為 `source_width`；這是 source topology／whole-root geometry 的結果，不得以任意最小值、平均值、局部 rail 間距或 candidate 排名代替。

沒有封閉或連接 provenance 的開放內部 rails，以及接入外框但不屬於可驗證 boundary traversal 的 branch rails，MUST NOT 決定或覆寫 `source_width`。中心軸等價的候選 SHALL 先合併為 center evidence group，再獨立 reconcile 該 group 的有效 envelopes；不得由 first occurrence、candidate order 或 recognition method 任選寬度。若工程軸可唯一辨識，但沒有唯一可靠的 component envelope，系統 SHALL 保留該工程軸、將來源寬度視為未知，MUST NOT 將 width ambiguity 升級為 center ambiguity，且 MUST NOT 自動指派材料規格；既有材料 Review 仍可由使用者確認。現有 `maximum_component_width_mm = 600` 只作為具名 recognition eligibility setting；已確認的合法支撐寬度均小於此值，本 change 不變更該設定，也不把 600 mm 或 350 mm 宣告為材料規格。

#### Scenario: A non-350 component envelope preserves its actual width

- **WHEN** 一個 component-like Strut root `INSERT` 具有唯一、完整且可驗證的 400 mm 或 500 mm 寬 component envelope
- **THEN** 系統 SHALL 從該 envelope 建立完整工程軸
- **AND** `source_width` SHALL 分別反映約 400 mm 或 500 mm，而不是固定為 350 mm

#### Scenario: Y05 S10 width comes from its connected outer contour

- **WHEN** Y05 S10 root handle `D17` 具有約 350 mm 寬的完整 connected outer contour，以及間距約 12 mm 但無 companion provenance 的開放內部 rails
- **THEN** 系統 SHALL 以完整 connected outer contour 推導約 350 mm 的 `source_width`
- **AND** SHALL NOT 以 12 mm rail 間距推導或覆寫材料寬度

#### Scenario: Unique whole-root outer envelope provides width without a closed contour

- **WHEN** root source 沒有合格 closed outline，但唯一可靠的 whole-root outermost longitudinal evidence 可驗證完整 component envelope
- **THEN** 系統 SHALL 以該 outer envelope 的橫向尺寸推導 `source_width`
- **AND** SHALL NOT 以內部或局部 rail separation 覆寫該寬度

#### Scenario: Nested same-axis different-width envelopes use containment

- **WHEN** 多個 axis-equivalent candidates 各自具有完整且可信的不同寬度 envelope，且 topology、whole extent 與 containment 可唯一證明其中一個是實體外包絡
- **THEN** 系統 SHALL 保留共同 axis，並以唯一實體外包絡推導 `source_width`
- **AND** SHALL NOT 依候選產生順序或 recognition method 任選寬度

#### Scenario: Unique axis without a unique envelope does not guess material width

- **WHEN** root source 的幾何足以唯一建立完整 Strut 工程軸，但沒有唯一可靠的 component envelope 可決定物理寬度
- **THEN** 系統 SHALL 保留該唯一工程軸
- **AND** SHALL 將 `source_width` 視為未知
- **AND** SHALL NOT 將 width ambiguity 回報為 center ambiguity
- **AND** SHALL NOT 由內部 detail rail、任意 outline 選擇或固定預設值自動指派材料規格
