# BIM Block Member Recognition Specification

## Purpose

本 capability 讓 DXF Import 能在不破壞一般圖層／線段辨識的前提下，從代表單一實體 Strut 的 BIM root `INSERT` 全體 WCS geometry，可靠重建完整工程軸並保留既有 Review 與來源追溯契約。

## Requirements

### Requirement: BIM Block recognition SHALL be a restricted Strut source path

系統 SHALL 繼續僅將位於使用者指定 Strut role layer 的 root `INSERT` 納入既有 Strut BIM component-like recognition。root `INSERT` 的存在不得直接等同一支正式 Strut；系統 MUST 先判斷該 source scope 的整體 geometry 是否支持單一實體構件。

root layer classification SHALL 決定候選 role。遞迴展開後的 child entity layer（包含 Layer 0）只提供 geometry evidence，不得重新分類為其他 member role。

Brace role root `INSERT` SHALL 依 `bim-block-brace-recognition` capability 進入獨立、role-correct 的 BIM Brace path；Beam role root `INSERT` SHALL 依 `bim-joist-recognition` capability 進入獨立、role-correct 的 BIM Joist path。一般 Beam root 最多產生一支 single-axis Joist；只有 whole-source geometry 已可靠證明為雙 C 型 assembly 的 Beam root，才可產生一個包含恰好兩條 source-supported axes 的 paired-axis outcome。各角色可以重用共同 pure geometry primitives，但 MUST NOT 被偽裝成 Strut、不得取得 Strut-specific downstream semantics，也不得使 Waler、Continuous Wall、Column 或 CornerBrace 自動進入 Strut／Brace／Joist BIM path。

#### Scenario: Root Strut layer supplies the role

- **WHEN** root `INSERT` 位於已分類為 Strut 的 layer，且其 child LINE／POLYLINE 位於 Layer 0 或其他 child layer
- **THEN** 系統以 Strut role 評估整個 root source scope
- **AND** child layer 不會使 geometry 失去 Strut role 或改成其他 role

#### Scenario: INSERT identity alone is insufficient

- **WHEN** Strut role layer 上的 root `INSERT` 內含多個互不相關、無法支持單一構件形狀的 geometry
- **THEN** 系統不得僅因它是一個 `INSERT` 就建立正式 Strut

#### Scenario: Brace behavior remains unchanged

- **WHEN** root `INSERT` 位於 Brace role layer，但不符合 BIM Brace component-like eligibility
- **THEN** 系統 SHALL 使用既有一般 Brace recognition behavior
- **AND** SHALL NOT 套用 Strut BIM component-like path

#### Scenario: Brace uses its own restricted role path

- **WHEN** root `INSERT` 位於 Brace role layer
- **THEN** 系統 SHALL 依 BIM Brace capability 評估該 root source
- **AND** SHALL 保留 Brace role、Brace diagnostics 與 Waler-to-Waler downstream contract
- **AND** SHALL NOT 將該 source 當成 Strut

#### Scenario: Beam uses its own restricted Joist path

- **WHEN** root `INSERT` 位於 Beam role layer
- **THEN** 系統 SHALL 依 BIM Joist capability 評估該 root source
- **AND** SHALL 保留 Beam role、Joist diagnostics 與既有 downstream Beam constraint contract
- **AND** SHALL NOT 將該 source 當成 Strut 或 Brace

#### Scenario: Proven double-C Beam root may represent two physical Joists

- **WHEN** 一個 Beam-role root `INSERT` 的 whole-source geometry 唯一證明它是一個雙 C 型 paired-axis Joist assembly
- **THEN** BIM Joist path MAY 從該 root 建立恰好兩支正式 Beam models
- **AND** 兩支 Beam SHALL 保留共同 root provenance，且不得被視為違反一般的一來源一模型安全檢核

#### Scenario: Unproven root cannot bypass the one-model rule

- **WHEN** Beam-role root `INSERT` 無法以 whole-source geometry 唯一建立 single-axis 或已證明的 paired-axis outcome
- **THEN** 系統 SHALL 回報 failed 或 ambiguous recognition
- **AND** SHALL NOT 以局部平行邊、generic fallback 或一來源多模型例外建立 Beam

#### Scenario: Other roles remain outside BIM member path

- **WHEN** root `INSERT` 位於 Waler、Continuous Wall、Column 或 CornerBrace role layer
- **THEN** 系統 SHALL 維持該 role 的既有 recognition behavior
- **AND** SHALL NOT 自動套用 Strut、Brace 或 Joist BIM path

### Requirement: Component-like eligibility SHALL use whole-source evidence

系統 MUST 以同一 root `INSERT` 的全體有效 geometry 判斷是否為 component-like Strut。充分證據 SHALL 同時支持：單一明顯的主要長方向、相對於橫向寬度呈細長的整體 extent、大部分有效 longitudinal geometry 沿共同方向排列、fragment center 或等價 longitudinal evidence 大致落在共同工程軸附近、fragments 的橫向寬度具合理一致性，且整體 evidence 支持一支完整 Strut 而不是多個互不相關構件。

短橫線、端板線或其他 detail geometry 可以作為輔助 evidence，但不得主導主要長方向。component-like eligibility 不得由單一局部平行邊對、最長單一 LINE、entity order 或 candidate order 決定。

#### Scenario: Fragmented rectangles form one component-like Strut

- **WHEN** 同一 root `INSERT` 內有多個沿共同長方向排列的封閉 rectangle fragments，且其中心對齊、寬度一致與整體 extent 共同支持一支 Strut
- **THEN** 系統 SHALL 將這些 fragments 作為同一 component-like Strut 的整體 evidence
- **AND** 不得把每個 rectangle 視為不同正式 Strut

#### Scenario: Detail geometry does not control the axis

- **WHEN** 一個 component-like Strut Block 內含大量橫向短線或局部 detail geometry
- **THEN** 主要長方向與工程軸 SHALL 由整體 longitudinal evidence 決定
- **AND** detail geometry 不得因數量或先出現而主導結果

#### Scenario: Unrelated contents are not component-like

- **WHEN** root `INSERT` 的 geometry 無法支持單一主要方向、共同軸或一致構件寬度
- **THEN** 系統 SHALL 判定 BIM component-like path 不適用

### Requirement: BIM Strut recognition SHALL use formal finite Waler context

對已判定為 component-like 的 Strut root `INSERT`，系統 SHALL 以同一次 DXF recognition 中已成功辨識、未排除且具有有限工程幾何的正式 Waler 作為跨度 context。系統 MUST 先取得 Strut source geometry 支持的長方向與候選軸，再沿每條候選軸的兩個相反方向尋找與有限 Waler geometry 的實際交點；不得將 Waler 無限延長、不得僅以空間最近距離代替交點，也不得以 unresolved、excluded 或 preview-only geometry 作為正式端點。

有效自動跨度 MUST 具有一個位於 source longitudinal extent 起點外側的唯一包圍 Waler，以及一個位於終點外側的唯一包圍 Waler。每一側有多個有效交點時，系統 SHALL 只在最近 outward intersection 可唯一決定時採用；若無法唯一決定則 SHALL 回報 blocking ambiguity。Waler context 只界定 longitudinal span，不得單獨決定候選軸的 transverse position。

#### Scenario: Unique finite Walers bracket a BIM Strut source

- **WHEN** 一個 component-like Strut root `INSERT` 的候選軸在 source longitudinal extent 兩側各與一支唯一正式有限 Waler 相交
- **THEN** 系統 SHALL 以兩側交點建立該候選軸的預期支撐跨度
- **AND** SHALL NOT 以原始局部 LINE endpoint 作為完整支撐的 terminal truth

#### Scenario: Infinite extension of a Waler is not an intersection

- **WHEN** 候選軸只與某支 Waler 的無限延長線相交，但交點不在該 Waler 的有限工程 segment 上
- **THEN** 該 Waler SHALL NOT 成為該候選軸的端部 Waler

#### Scenario: Only one side has a formal Waler

- **WHEN** source 已符合 component-like BIM Strut eligibility，但候選軸只有一側可取得正式有限 Waler 交點
- **THEN** 系統 SHALL 保留 root source identity 並回報 blocking incomplete-span problem
- **AND** SHALL NOT 以局部 geometry 建立 formal Strut 或回到一般平行線 fallback

#### Scenario: Competing outward Walers are not guessed

- **WHEN** 候選軸同一側存在多個無法唯一決定的有效包圍 Waler intersections
- **THEN** 系統 SHALL 回報 blocking ambiguous Waler-span problem
- **AND** SHALL NOT 依 entity order、Waler ID 或任意 first occurrence 選擇端點

#### Scenario: Waler context cannot choose lateral axis by itself

- **WHEN** 多條 transverse position 不同的平行候選軸都能與同一對 Waler 相交
- **THEN** 系統 SHALL 以同一 root INSERT 的 whole-source completeness 決定候選軸
- **AND** SHALL NOT 只因候選軸能碰到兩端 Waler 就視為可靠中心線

### Requirement: Waler-bounded corridor SHALL select the whole-root Strut explanation

系統 SHALL 對每條具有有效 Waler span 的 axis hypothesis，建立由兩端 Waler 交點界定的 longitudinal corridor，並僅使用同一 root `INSERT` 的 WCS geometry 評估該假設是否能解釋一支完整 Strut。可靠 whole-root explanation MUST 通過既有方向、component length、slenderness 與寬度 eligibility，並 SHALL 說明該 corridor 內主要 longitudinal evidence 的橫向配置與延續；大量同方向、同 root、位於相同 corridor 內但無法由候選軸解釋的主要長線 SHALL 使該假設失效。

系統 SHALL 允許符合既有 eligibility 的同軸 fragments 跨越 interior gaps；Waler span 提供預期 terminal extent，而非授權把方向不符、橫向位置不符、寬度不相容或不同 root 的線段加入構件。Waler context 與 whole-root completeness SHALL 在既有 `bim_minimum_longitudinal_evidence_ratio = 0.5`、`minimum_projection_overlap_ratio = 0.8` 及 `ambiguous_candidate_score_delta = 0.03` gate 之前過濾不完整假設；本 requirement 不修改這些既有數值或其 runner-up semantics。

#### Scenario: A half-section axis leaves major source evidence unexplained

- **WHEN** 一條 axis hypothesis 只能解釋 H 型或多縱線 root INSERT 的單側外緣／內緣，而同一 Waler-bounded corridor 內仍有另一側的主要 longitudinal evidence
- **THEN** 系統 SHALL 拒絕該 hypothesis 作為完整 Strut 軸
- **AND** SHALL NOT 因其局部平行線較長而採用

#### Scenario: Symmetric whole-section evidence selects the central axis

- **WHEN** 一條 axis hypothesis 能以相容的雙側 longitudinal evidence 解釋 Waler-bounded corridor 內的完整 root geometry，且其他 hypotheses 均留下主要未解釋 evidence
- **THEN** 系統 SHALL 將該 hypothesis 作為唯一 whole-root axis 繼續既有 credibility checks

#### Scenario: Large interior gaps do not truncate Waler-bounded evidence

- **WHEN** 同一 root INSERT 的 eligible longitudinal fragments 沿同一 whole-root axis 排列，兩端由唯一 Waler span 界定，但 fragments 之間存在 large interior gaps
- **THEN** 系統 SHALL 允許跨越 gaps 建立該 Waler-bounded whole axis
- **AND** SHALL NOT 只保留最長的局部連續 fragment

#### Scenario: Y05 S19 rejects the left half-section axis

- **WHEN** Y05 S19 root handle `D4B` 的等價 WCS geometry 可取得兩端唯一正式 Waler span，且主要 longitudinal stations 約為 `X = 29326.5`、`29495.5`、`29507.5`、`29676.5`
- **THEN** whole-root completeness SHALL 選出約 `X = 29501.5` 的完整支撐中心軸
- **AND** SHALL NOT 採用只解釋左半斷面的約 `X = 29411` 軸
- **AND** SHALL NOT 以約 `186.5 mm` 的局部 rail separation 當成完整 Strut envelope width

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

### Requirement: One root Strut source SHALL have a terminal one-member-or-problem outcome

當同一 Strut root `INSERT` 的有效 geometry 拓撲支持兩條以上幾何不等價、且各自具完整 source-supported extent 的工程軸時，系統 SHALL 將該 source 視為無法唯一解釋為一支 Strut，回報 blocking ambiguous recognition problem，並且不得建立 formal Strut。系統 MUST NOT 依 candidate score、DXF entity order、child order、first occurrence 或一般 parallel-pair fallback 任意選擇其中一軸。

此 terminal outcome 適用於已可驗證多軸 topology 的 root source；它不將一般人工 CAD 的缺乏 topology evidence 自動升級為 error。成功辨識時，同一 root `INSERT` 最多建立一支 formal Strut。

#### Scenario: Two separate complete axes in one root are blocking ambiguous

- **WHEN** 一個 Strut root `INSERT` 內存在兩組拓撲上獨立、各自完整且幾何不等價的 Strut outline evidence
- **THEN** 系統 SHALL 以該 root handle 建立 blocking ambiguous recognition problem
- **AND** SHALL NOT 建立任何 formal Strut
- **AND** SHALL NOT 將其中一組視為 winner

#### Scenario: One root source cannot create two formal Struts

- **WHEN** 單一 Strut root `INSERT` 的 child geometry 可被一般 recognition 分析為多個局部 parallel-pair candidates
- **THEN** 系統 SHALL 先套用已辨識的 same-source topology outcome
- **AND** 成功時最多建立一支 formal Strut，歧義時建立 zero formal Strut

### Requirement: Winner credibility and reliable-runner ambiguity SHALL be separate gates

`bim_minimum_longitudinal_evidence_ratio = 0.5` SHALL 是自動選出 winner 的最低 credibility threshold，而不是 runner-up 是否能參與 ambiguity comparison 的硬切除門檻。只有最佳可靠候選的 evidence ratio `>= 0.5` 時，特殊路徑才可能回傳 `recognized`。

「可靠候選」MUST 已通過 whole-component geometry 建立所需的方向相容、transverse center alignment、width、component length 與 slenderness checks，並 MUST 能由來源 evidence 重建完整競爭軸。其 root longitudinal extent coverage MUST 達到既有 `minimum_projection_overlap_ratio`（目前為 `0.8`）。單純排名第二、具有局部漂亮平行邊，或 coverage 不足，均不得視為 reliable runner-up。

在最佳可靠候選通過 `0.5` winner threshold 後，系統 MUST 檢查其他所有可靠、且與 best axis 幾何不等價的 candidates。若任一 candidate 與 best 的 evidence ratio 差值 `<= ambiguous_candidate_score_delta`（目前為 `0.03`），結果 MUST 為 `ambiguous`，即使該 runner-up 自身的 evidence ratio 略低於 `0.5`。

低於 `0.5` 的 runner-up 不得單獨成為 winner。與 best 幾何等價的 duplicate candidate 不構成衝突，也不得遮蔽後續另一個可靠且不等價的 runner-up。

#### Scenario: Equal competing axes are ambiguous

- **WHEN** 兩個可靠且不等價的完整候選軸各具有 `0.50` evidence ratio
- **THEN** 系統 SHALL 回傳 `ambiguous`

#### Scenario: A 49 percent reliable runner still participates in ambiguity

- **WHEN** best reliable candidate 的 evidence ratio 為 `0.51`，另一個可靠且不等價的 runner-up 為 `0.49`
- **AND** evidence delta `0.02 <= 0.03`
- **THEN** 系統 SHALL 回傳 `ambiguous`
- **AND** 不得僅因 runner-up `< 0.5` 而自動選擇 best

#### Scenario: A clearly dominant reliable winner is recognized

- **WHEN** best reliable candidate 的 evidence ratio `>= 0.5`
- **AND** 所有可靠且不等價的 runner-up 與 best 的 evidence delta 都 `> 0.03`
- **AND** best 通過其他既有完整軸與 component-like checks
- **THEN** 系統 SHALL 將 best 判定為唯一 winner並回傳 `recognized`

#### Scenario: Rank alone does not make a runner reliable

- **WHEN** 排名第二的 candidate 無法形成完整 source-supported axis，或 root extent coverage `< 0.8`
- **THEN** 該 candidate SHALL NOT 只因排名第二而觸發 ambiguity
- **AND** 其餘 outcome 仍依 best credibility、whole-extent failure 與其他可靠 candidates 決定

### Requirement: BIM path fallback and failure SHALL be distinct

特殊辨識 SHALL 產生下列互斥結果：`not applicable`（source 不符合 component-like BIM Strut eligibility，回到目前一般 DXF recognition）、`recognized`（source geometry、兩端 Waler span 與 whole-root completeness 共同建立一個 Strut candidate），以及 `failed or ambiguous`（component-like 資格成立，但缺少唯一兩端 Waler span、完整 corridor 無法可靠重建、沒有唯一 whole-root axis 或存在衝突完整解時，回報 blocking recognition problem）。

`failed or ambiguous` 結果 SHALL 保留 root source identity，形成既有 Review workflow 可顯示的 unresolved ReviewItem，不得從該 root source 建立 formal Strut，也不得回到局部 geometry fallback。只有真正不符合 component-like eligibility 的一般人工 CAD `INSERT` 才可取得 `not applicable`。

#### Scenario: Non-component INSERT keeps general recognition

- **WHEN** 一個一般人工 CAD `INSERT` 不符合 component-like eligibility
- **THEN** 系統 SHALL 將該 root source 交回既有一般 recognition
- **AND** 一般非 BIM behavior 不因本 change 被強制改寫

#### Scenario: Conflicting complete axes are ambiguous

- **WHEN** 同一 component-like root Block 在 Waler-bounded completeness 後仍支持兩個互相衝突且近似可信的完整工程軸，且沒有足夠 evidence 唯一決定
- **THEN** 系統 SHALL 回報 blocking ambiguous recognition problem
- **AND** SHALL 建立以該 root source 為 identity 的 unresolved ReviewItem
- **AND** SHALL NOT 任意選擇其中一軸或建立 formal Strut

#### Scenario: Missing Waler span fails instead of falling back

- **WHEN** source 已可判定為 component-like，但無法取得唯一的兩端正式 Waler intersections
- **THEN** 系統 SHALL 回報 blocking recognition failure 或 ambiguity
- **AND** SHALL NOT 以局部 parallel pair 建立 formal Strut

#### Scenario: Unreliable complete extent fails instead of truncating

- **WHEN** source 已可判定為 component-like 且具有兩端 Waler span，但沒有 axis hypothesis 能可靠解釋 Waler-bounded corridor 內的 whole-root geometry
- **THEN** 系統 SHALL 回報 blocking recognition failure
- **AND** SHALL NOT 以局部 fragment 建立較短或偏移的 formal Strut

### Requirement: Root INSERT SHALL remain the recognition source boundary

每個 root `INSERT` SHALL 是獨立的 recognition source scope。系統 MUST 在同一 root scope 內整合 child fragments，但不得因不同 root `INSERT` 的 geometry 共線、接近或寬度相同，就合併成同一正式構件。

一個成功的 component-like root source SHALL 最多產生一個 BIM Strut candidate。若同一 source 顯示多構件或多解，系統 SHALL 依 failure／ambiguity 規則處理，而不是拆出多個 formal Struts。對具有可驗證同源 outline topology 的 Strut root source，系統 SHALL 在交由一般 local parallel-pair fallback 前先完成該 topology 的唯一軸／blocking ambiguity 判定；一般 fallback 不得繞過此 source boundary。

#### Scenario: Collinear root INSERTs remain separate

- **WHEN** 兩個不同 root `INSERT` 的 fragments 恰好共線且各自支持一支 Strut
- **THEN** 系統 SHALL 產生兩個來源獨立的 Strut candidates
- **AND** 不得跨 root handle 合併為一支構件

#### Scenario: One root cannot silently yield several BIM Struts

- **WHEN** 單一 root `INSERT` 的 geometry 看似包含多個互不相關的完整構件
- **THEN** 系統 SHALL NOT 由 BIM component-like path 產生多個 formal Struts
- **AND** SHALL 依 not-applicable 或 ambiguous behavior 處理

#### Scenario: Topology outcome cannot be bypassed by general fallback

- **WHEN** Strut root `INSERT` 已具有可驗證的 same-source outline topology，且 topology 判定其共同軸或多軸歧義
- **THEN** 系統 SHALL 採用該 topology outcome
- **AND** SHALL NOT 再由一般 local parallel-pair candidate 選擇不同的工程軸

### Requirement: Nested geometry SHALL use the existing WCS boundary and root provenance

系統 SHALL 遞迴展開 Nested `INSERT`，對每一層套用 insertion、rotation 與 scale，並在目前既有 importer WCS boundary 中執行 whole-block geometry interpretation。不得對已轉換的 child geometry 重複套用 transform。

成功候選、recognition failure、ValidationMessage、ProblemRecord 與 ReviewItem SHALL 保留最外層 root `INSERT` source handle 作為 provenance。child handle 不得取代 root handle 成為該 member 的 exclusion／restore identity。

#### Scenario: Nested transform produces WCS engineering geometry

- **WHEN** Strut root `INSERT` 包含一層以上具有 insertion、rotation 或 non-unit scale 的 Nested Blocks
- **THEN** 所有 child geometry SHALL 正確轉換一次至 WCS
- **AND** 重建的正式工程軸 SHALL 使用該 WCS geometry

#### Scenario: Root handle survives nested expansion

- **WHEN** component-like recognition 使用多層 nested child entities 建立 Strut 或 unresolved problem
- **THEN** 對外的 source identity SHALL 包含最外層 root `INSERT` handle
- **AND** source exclusion／restore SHALL 以該 root identity 操作整個 source scope

### Requirement: Recognition SHALL be deterministic for equivalent geometry

在 WCS geometry、root source identity 與 role 等價時，child entity order、LINE start/end direction、POLYLINE vertex traversal direction或 candidate enumeration order 的改變，不得改變成功／fallback／ambiguity 分類或等價的正式工程軸。

若仍有幾何上等價的 start/end 表示，系統 SHALL 使用 deterministic geometry-derived normalization；不得以 first occurrence、DXF entity order 或任意 candidate order 作為 fallback。

#### Scenario: Reordered children preserve recognition

- **WHEN** 同一 Block 的 child entities 只改變儲存順序
- **THEN** 系統 SHALL 產生相同的 recognition outcome 與等價工程軸

#### Scenario: Reversed segment directions preserve recognition

- **WHEN** child LINE start/end 或 closed path traversal direction 反轉，但 WCS shape 不變
- **THEN** 系統 SHALL 產生相同的 recognition outcome 與 normalized engineering axis

### Requirement: Existing DXF Review lifecycle SHALL remain authoritative

BIM Block recognition SHALL 只改變特定 source geometry 如何產生 member candidate。recognition result 仍 MUST 進入既有 `DXFImportResult`、Validation／ProblemRecord／ReviewItem、manual modification、confirmation 與 completed import lifecycle；特殊辨識不得直接寫入 `ProjectDataModel`。

Source exclusion SHALL 在不修改 original DXF 的前提下停用該 root source 的 recognition，restore SHALL 重新執行 recognition。Manual override replay SHALL 繼續使用 role + exact source handle identity；當 fresh recognition 無法唯一對應 source，既有 override SHALL 依目前 needs-review／disabled behavior 處理。fresh geometry 改變時，confirmation SHALL 依既有 confirmation identity/signature 規則失效，不得被特殊路徑繞過。

Pause／Resume SHALL 繼續受 source fingerprint safety 保護，且不得要求 Project persistence schema migration。

#### Scenario: Exclude and restore a recognized BIM Strut

- **WHEN** 使用者排除一個由 component-like root Block 辨識的 Strut source
- **THEN** 該 source 不再產生 formal Strut，但 original source geometry 保持可供預覽與 restore
- **AND** restore 後系統重新辨識同一 root source

#### Scenario: Manual override replay uses exact root source identity

- **WHEN** fresh recognition 仍唯一產生相同 role + root source handle identity
- **THEN** 既有可重播的人工材料或工程線輸入 SHALL 依目前 workflow 規則重播
- **AND** 不得依舊 member ID 或 child entity order 綁定

#### Scenario: Ambiguous BIM source remains in Review

- **WHEN** component-like root source 回報 ambiguous／failed recognition
- **THEN** existing Review workflow SHALL 顯示該 unresolved source 與 blocking problem
- **AND** import completion SHALL 在 blocking problem 未處理前保持不可完成

#### Scenario: Completed import uses the existing Project contract

- **WHEN** 使用者完成 Review 且 BIM Strut 已成為合法 formal member
- **THEN** 系統 SHALL 透過既有 DXF result-to-project conversion 建立 Project row
- **AND** BIM child geometry metadata SHALL NOT 建立新的 Project schema field

### Requirement: Existing recognition paths and source files SHALL remain compatible

本 change SHALL 保持明確中心線、MLINE、完整 closed outline、完整平行邊、一般 standalone LINE 與非 component-like `INSERT` 的既有 recognition behavior。BIM 特殊路徑不得改變 source fingerprint 計算、original DXF immutable contract、一般 small-gap behavior、material recognition、CandidatePoint 或 Double Support engineering rules。

#### Scenario: Ordinary non-BIM drawing is unchanged

- **WHEN** DXF 使用一般 LINE、MLINE、完整 closed outline 或完整平行邊表達構件，且不需要 component-like fragmented Block interpretation
- **THEN** 系統 SHALL 維持既有 recognition result 與 downstream behavior

#### Scenario: Recognition never writes the original DXF

- **WHEN** 系統辨識、排除、復原、暫停或完成含 BIM Block 的 DXF Review
- **THEN** original DXF bytes SHALL remain unchanged

#### Scenario: Guided Recognition is not introduced

- **WHEN** automatic recognition 與 BIM Block recognition 都無法可靠建立構件
- **THEN** 本 capability SHALL 只回報既有 Review problem
- **AND** SHALL NOT 提供人工輔助線、影像辨識或直接從人工標記建立 Project component
