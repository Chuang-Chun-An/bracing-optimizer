# Spec Delta

## ADDED Requirements

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

- **WHEN** Y05 S2 root handle `957` 的等價 WCS geometry 由多組沿共同縱向排列的 LINE fragments 形成，且兩端正式 Waler 與整體 evidence 支持約 `18,900 mm` 的完整軸
- **THEN** BIM component-like recognition SHALL 重建約 `(-53379, -9450) → (-53379, 9450)` 的完整工程軸
- **AND** SHALL NOT 退回既有約 `6,978 mm`、約 `(-53379, -3488.368) → (-53379, 3489.368)` 的局部平行邊辨識

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
