# BIM Joist Recognition Specification

## Purpose

本 capability 定義 Beam-role BIM root 如何由 whole-source geometry 與 immutable upstream engineering context 建立可靠的 single-axis 或 paired-axis Joist，並安全投影成 Review 與 Strut Beam constraints。

## 閱讀導航

### 必讀

- 「已證明跨越中間柱的托梁可恢復端部殘線」：定義 700 mm 候選窗、每個 sibling 的來源端點與 paired terminal event。
- 「Joist contact SHALL preserve source axes while supporting finite crossings and qualified Strut-face contacts」：定義 recovery 後的 crossing 重建與 endpoint-face fallback。
- 「Y05 characterization SHALL remain a regression contract」：定義 E8F／BM18、F2A 與 finalized crossing regression。

### 條件式閱讀

- 修改 Project projection 時，閱讀「Validated Joist crossings SHALL project without Project schema changes」。
- 修改非 BIM Beam 或 Brace-contact single Joist 時，閱讀末段相容性與 Brace contact Requirements。

### 可先跳過

- Paired assembly 的 Review source-atomic、manual replay 及其他未受本次行為影響的 Requirements 可先跳過。

## Requirements

### Requirement: BIM Joist recognition SHALL preserve one root source scope while supporting single-axis and proven paired-axis outcomes

系統 SHALL 以一個 Beam-role root `INSERT` 作為一個 BIM Joist source scope。root layer 決定 Beam／Joist role；child layer 僅提供 geometry evidence，不得重新分類角色。不同 root MUST 獨立處理，不得跨 root 合併。

一般 Joist root 成功時 SHALL 最多建立一支 single-axis Joist。只有 whole-source geometry 唯一證明為雙 C 型 BIM Joist assembly 的 root，才可建立一個 paired-axis outcome；該 outcome SHALL 恰好包含兩條 source-supported Joist axes，代表兩支實體 Joists。無法唯一建立 single-axis 或 paired-axis outcome 時，系統 SHALL 回報 `failed` 或 `ambiguous`，不得回退局部 parallel pair。

#### Scenario: Ordinary root produces one Joist

- **WHEN** 一個 Beam-role root 的 whole-source geometry 唯一支持一條完整 Joist axis，且不符合可靠雙 C topology
- **THEN** 系統 SHALL 建立最多一支 single-axis Joist

#### Scenario: Reliable double-C root produces a paired assembly

- **WHEN** 一個 Beam-role root 的 whole-source geometry 唯一支持雙 C topology 與兩條完整 envelope center axes
- **THEN** 系統 SHALL 建立最多一個 paired-axis Joist assembly
- **AND** 該 assembly SHALL 恰有兩條 source-supported axes

#### Scenario: Local pair cannot rescue an unresolved root

- **WHEN** whole-source geometry 無法唯一支持 single-axis 或 paired-axis outcome
- **THEN** 系統 SHALL 回報 `failed` 或 `ambiguous`
- **AND** SHALL NOT 選擇局部漂亮平行邊、first occurrence、entity order 或 generic local-pair fallback

### Requirement: Formal BIM Joist axes SHALL be derived from whole-source geometry

系統 MUST 使用同一 root 的全部有效 WCS geometry 建立主要長方向、source-supported terminal extent 與 transverse center。內部 fragments MAY 跨越 BIM projection gaps，但不得越過 root source boundary。短橫線、端板、孔洞與 detail lines 不得主導長方向或軸線。

可靠雙 C topology MUST 由兩個完整 C envelopes 或等價可驗證 topology 支持；每一條實體 Joist axis SHALL 是該 envelope 的 center axis。雙 C outcome 不得以全部 rails 的總中心、單一 web、任意兩條平行線或局部 rail pair 代替。

#### Scenario: Double-C axes use envelope centers

- **WHEN** whole-source geometry 顯示兩個完整且可唯一區分的 C envelopes
- **THEN** 系統 SHALL 從每個 envelope 各建立一條 center axis
- **AND** SHALL NOT 將兩個 envelopes 合併成一條總中心軸

#### Scenario: Interior fragments preserve the whole axis

- **WHEN** 同一 envelope 的 longitudinal fragments 方向、transverse alignment、寬度與 topology 相容，但中間具有大 gap
- **THEN** 系統 SHALL 以 whole-source evidence 保留完整 source-supported axis
- **AND** SHALL NOT 只保留局部 fragment

#### Scenario: Conflicting whole-source explanations are ambiguous

- **WHEN** 同一 root 存在多個幾何不等價且無法唯一區分的 single-axis 或 paired-axis explanations
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** SHALL NOT 依 candidate score、ID 或 entity order 任選

### Requirement: Joist recognition SHALL consume immutable completed upstream context

Joist stage SHALL 位於 `Waler → Strut → Brace → CornerBrace → Column → Joist` recognition dependency order 的最後。箭頭表示 stage ordering 與向前讀取權限，而不是只能依賴緊接前一個 member type。Joist MAY 消費已完成 upstream stages 所提供、且本 capability 明確需要的 formal Strut、Brace 與 Column immutable engineering context。

共同 contract SHALL 為 `Joist source geometry + applicable immutable upstream engineering context → pure recognition outcome`。Upstream context MAY 提供 span、boundary、contact、support 或 assembly evidence，但 MUST NOT 取代 Joist 自身 source geometry evidence；pure service MUST NOT 回查 importer mutable global state，也不得反向修改 upstream source recognition truth。

#### Scenario: Formal upstream members are visible

- **WHEN** Joist stage 開始前 formal Strut、Brace 與 Column stages 已完成
- **THEN** Joist recognition SHALL 以 immutable snapshot 讀取其有限 WCS geometry 與 identities

#### Scenario: Non-formal sources are not context

- **WHEN** upstream source 為 unresolved、excluded 或 preview-only
- **THEN** 該 source MUST NOT 成為 Joist contact 或 assembly evidence

#### Scenario: Context cannot invent an axis

- **WHEN** upstream context 可推測某處可能有 Joist，但 Beam root source 無法支持該 axis
- **THEN** 系統 MUST NOT 由 context 憑空建立 Joist

### Requirement: 已證明跨越中間柱的托梁可恢復端部殘線

對已由既有 same-Strut、opposite-side、`518 ± 5 mm` spacing 與 Column midpoint `±2 mm` 規則唯一證明的 paired BIM Joist assembly，系統 SHALL 允許 formal Column context 限定 terminal residual eligibility。此規則是 DXF recognition safety boundary，不是材料尺寸、Solver rule 或固定構件延長量。

具名 Column terminal window SHALL 為沿既有 Joist longitudinal axis、朝正在評估的 terminal outward direction 所定義的 signed projection `0～700 mm`，且兩端採 inclusive boundary。距離 SHALL 從 formal Column center 量測至 residual source evidence 的最外投影；只有 signed projection 位於該區間的 evidence 可成為候選，`> 700 mm` 或位於反方向的 evidence MUST 被拒絕。

候選 residual evidence MUST 同時符合：屬於同一 Beam root `INSERT`、位於既有主體 terminal 的 Column 另一側或 Column 遮蔽 corridor、方向與既有 Joist axis 相容，且 transverse offset 可唯一對齊該 paired assembly 已成立的 longitudinal rail bands。距離、空間最近、短線長度、Column identity 或 root identity 任一項單獨成立均不足以取得資格；不同 root、橫向 detail、端板、孔洞線、未對齊 rail 的斜線或孤立短線 MUST NOT 改寫 terminal extent。

每一支 sibling Joist envelope 的 terminal residual set MUST 各自至少由兩個相異且已對齊的 longitudinal rail bands 支持，並各自從自己的合格 source evidence 決定 terminal station。兩支 sibling envelopes 的 source-supported terminal stations 必須相差 `<= 50 mm`，才能確認為同一 paired terminal recovery event；此 tolerance MUST NOT 用來把兩個 stations 合併為共同端點。每支 finalized axis MUST 終止於自身 envelope 的合格 source-supported station，不得取兩者較外值、不得平均、不得延伸至另一支 sibling 的 station，也不得直接取 Column center `±700 mm` 邊界。

若 residual evidence 不足，或 recovery candidate 無法在 final pass 重新建立 preliminary seed 的相同 Strut／Column relation且沒有形成矛盾 identity，系統 SHALL 放棄該 recovery、保留既有 base axes，並從 base axes 建立唯一正式結果。若 finalized candidate 明確改指其他 Strut／Column、同時符合多個 identities，或存在多個彼此不相容且各自完整合格的 terminal interpretations，系統 SHALL 回報 blocking ambiguity／context drift，且不得任選、回退 first occurrence 或提交 preliminary truth。

#### Scenario: 700 mm inclusive boundary is eligible

- **WHEN** 已成立的 paired Joist／Column relation 具有同 root、同方向且對齊既有 rail bands 的 terminal residual set，其朝 terminal outward direction 的最外來源 signed projection 距 Column center 恰為 `700.0 mm`，且兩個 sibling envelopes 的 terminal stations 相容
- **THEN** 系統 SHALL 允許該 residual set 參與 terminal recovery
- **AND** SHALL 以來源支持的位置而非固定 700 mm 邊界建立 extent

#### Scenario: Residual beyond 700 mm is rejected

- **WHEN** terminal residual 朝 terminal outward direction 的最外來源 signed projection 大於 `700.0 mm`，或 evidence 位於 Column center 的反方向
- **THEN** 該 residual MUST NOT 參與 terminal extent recovery
- **AND** 系統 MUST NOT 為了連接該 residual 而放寬距離、改變 Joist 方向或延伸至無來源支持的位置

#### Scenario: Aligned residuals bridge a Column occlusion gap

- **WHEN** 同一 paired root 的主體 rails 與 Column 另一側殘線分屬相同 longitudinal rail bands，兩者之間的 gap 可由已成立的 formal Column／Strut corridor 解釋，且所有 terminal eligibility 均成立
- **THEN** 系統 SHALL 跨越該 interior gap，將每支 paired axis 分別恢復至自身合格殘線支持的端部
- **AND** SHALL NOT 將 Column 實體遮蔽 gap 視為自動拆件或截短條件

#### Scenario: Short fragments from a Brace-clipped envelope remain usable as collective evidence

- **WHEN** 斜撐投影使某一 sibling envelope 的 terminal rails 被切成長度不一的短 fragments，但至少兩個相異 rail bands 仍可在 700 mm Column window 內唯一對齊既有 envelope，且兩個 sibling terminal stations 相容
- **THEN** 系統 SHALL 將這些 fragments 作為 collective terminal evidence
- **AND** SHALL NOT 要求每一條 residual 單獨通過一般「最長 fragment 20%」門檻

#### Scenario: One isolated short line cannot extend a Joist

- **WHEN** Column window 內只有一條短線，或短線無法唯一對齊既有 longitudinal rail band／sibling envelope
- **THEN** 系統 MUST NOT 以該線延伸 Joist terminal extent
- **AND** SHALL 保留既有未恢復軸，不得把不足 evidence 升格為新的 formal geometry

#### Scenario: Conflicting complete terminal interpretations are blocking

- **WHEN** 同一 terminal side 存在兩組以上各自通過 root、方向、rail-band、Column window 與 sibling support，但 terminal stations 超出既有 endpoint tolerance 而無法確認為同一 paired terminal event 的 interpretations
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** SHALL NOT 依最長、最外、最近、ID、entity order 或 first occurrence 任選

#### Scenario: Insufficient final proof falls back to base axes

- **WHEN** preliminary context 已開啟 recovery，但某一 sibling 不足 rail-band quorum，或 recovery candidate 在 final pass 無法重新建立相同 Strut／Column relation且沒有指向其他或多個 identities
- **THEN** 系統 SHALL 放棄該 recovery candidate並保留 base axes
- **AND** 正式 contacts／relations SHALL 從 base axes 重新建立，不得提交 preliminary contacts／relations

#### Scenario: Contradictory final identity is blocking

- **WHEN** recovery candidate 的 finalized axes 明確改指不同於 preliminary seed 的 Strut／Column identity，或同時完整符合多個 identities
- **THEN** 系統 SHALL 回報 blocking context drift／ambiguity
- **AND** SHALL NOT 提交 recovery candidate、preliminary contacts／relations或任選其中一個 identity

### Requirement: Joist contact SHALL preserve source axes while supporting finite crossings and qualified Strut-face contacts

Joist-to-Strut 或 Joist-to-Brace direct contact MUST 由 finalized source-supported Joist finite axis 與 formal upstream finite segment 的實際垂直接觸建立。對 Column-qualified terminal residual recovery，系統 MUST 先完成 source-supported terminal extent finalization，再建立 contact；若恢復後的 finite axis 已穿越原本的 Strut，該 relation SHALL 使用 direct finite crossing，且 MUST NOT 同時保留同位置的 `endpoint_face_contact`。

除此之外，Joist-to-Strut MAY 由 Joist 的真實 terminal endpoint 接觸 formal Strut 實體外緣建立 `endpoint_face_contact`；此規則不得套用到 Joist 內部點或 Brace。`endpoint_face_contact` 是 axis finalization 後仍真正停在 Strut face 的 fallback，不得阻止合格 residual recovery，也不得反向改寫 finalized source axis。

`endpoint_face_contact` 的具名容許值 SHALL 為 `joist_strut_face_contact_tolerance_mm = 25.0`，並須同時滿足：Joist 與 Strut 近似垂直、Strut 具有可靠正值 `source_width`、由 terminal endpoint 沿 Joist 軸向外投影可唯一命中有限 Strut 中心線、且 `abs(projection_distance - strut_source_width / 2) <= 25.0 mm`。系統 SHALL 保留 Joist source axis 與外緣 `source_contact_point` 不變，只以中心線 `engineering_crossing_point` 計算 Strut station 與 downstream relation。

系統 MUST NOT 以一般無限延長線、最近外框距離、nearest snap、INSERT point 或非垂直接近建立 contact；同一 terminal endpoint 若有多支合格 Struts，SHALL 回報 ambiguity 而不得依距離、ID 或順序任選。

#### Scenario: Terminal recovery precedes contact classification

- **WHEN** Column-qualified terminal residual recovery 使 finalized Joist finite axis 從 Strut 一側延伸至另一側，並與該 finite Strut 形成真實垂直交點
- **THEN** 系統 SHALL 將 relation 分類為 finite crossing
- **AND** crossing station SHALL 與同一 Strut 中心線交點一致
- **AND** 系統 MUST NOT 再為同一 Joist／Strut relation 建立 `endpoint_face_contact`

#### Scenario: Finite perpendicular crossing establishes contact

- **WHEN** finalized Joist finite axis 與 formal finite Strut 或 Brace segment 實際垂直相交
- **THEN** 系統 SHALL 建立帶有 WCS point、upstream member identity 與 Strut station 的 contact

#### Scenario: Terminal endpoint on a reliable Strut face establishes contact without changing the source axis

- **WHEN** axis finalization 後沒有合格 terminal residual recovery，且 Joist terminal endpoint 沿 Joist 軸向外投影至一支有限、近似垂直且具有可靠寬度的 formal Strut 中心線
- **AND** 投影距離與該 Strut `source_width / 2` 的差異不超過 `25.0 mm`
- **AND** 該 endpoint 只有一支合格 Strut
- **THEN** 系統 SHALL 建立 `endpoint_face_contact`
- **AND** SHALL 保存外緣 `source_contact_point` 與中心線 `engineering_crossing_point`
- **AND** SHALL NOT 延長或改寫 Joist source axis

#### Scenario: Endpoint-face tolerance uses inclusive boundary

- **WHEN** `abs(projection_distance - strut_source_width / 2) = 25.0 mm` 且其他資格均成立
- **THEN** 該 endpoint-face contact SHALL 通過 eligibility

#### Scenario: Endpoint-face contact outside the width-derived range is rejected

- **WHEN** Strut 缺少可靠正值寬度，或 `abs(projection_distance - strut_source_width / 2) > 25.0 mm`
- **THEN** 系統 MUST NOT 建立 endpoint-face contact

#### Scenario: Multiple eligible Strut faces are ambiguous

- **WHEN** 同一 Joist terminal endpoint 同時符合多支 formal Struts 的完整 endpoint-face eligibility
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** SHALL NOT 依 nearest、member ID 或 collection order 任選

#### Scenario: Infinite or nearest geometry is not contact

- **WHEN** 只有一般無限延長線會相交，或 geometry 只是空間接近但未形成 finite crossing 或完整 endpoint-face eligibility
- **THEN** 系統 MUST NOT 建立 Joist contact

### Requirement: Proven double-C assembly SHALL use the confirmed 518 mm Strut-station spacing contract

本 requirement 是 whole-source geometry 已證明的雙 C 型 BIM Joist assembly 專用 Engineering Hard Constraint，不得泛化為所有 Joist 型式。

具名設定 SHALL 為：

- `joist_pair_nominal_station_spacing_mm = 518.0`
- `joist_pair_station_spacing_tolerance_mm = 5.0`

對同一有限 Strut 的兩個實際 crossing stations，`actual_spacing = abs(station_b - station_a)`，pair eligibility SHALL 使用 inclusive 判定：`abs(actual_spacing - 518.0) <= 5.0`。518 mm MUST 由兩條 Joist envelope center axes 與同一有限 Strut 的實際垂直 crossing stations 計算；不得以 INSERT point、428 mm 淨距、441／443.5 mm web 間距、外框距離或 Joist width 取代。

#### Scenario: Lower inclusive spacing boundary is eligible

- **WHEN** 已證明的雙 C axes 與同一有限 Strut 形成 `513.0 mm` station spacing，且其他資格均成立
- **THEN** 該 spacing SHALL 通過 eligibility

#### Scenario: Upper inclusive spacing boundary is eligible

- **WHEN** 已證明的雙 C axes 與同一有限 Strut 形成 `523.0 mm` station spacing，且其他資格均成立
- **THEN** 該 spacing SHALL 通過 eligibility

#### Scenario: Spacing outside the inclusive range is rejected

- **WHEN** actual spacing 小於 `513.0 mm` 或大於 `523.0 mm`
- **THEN** 該 pair MUST NOT 成為合格雙 C Joist pair

#### Scenario: Proxy distances cannot replace crossing spacing

- **WHEN** 428 mm 淨距、441／443.5 mm web 間距、外框距離、width 或 INSERT point 看似符合某個距離
- **THEN** 系統 SHALL 忽略這些 proxy，並只使用兩條 envelope center axes 的實際 Strut crossing station spacing

### Requirement: Strut and Column context SHALL qualify a unique two-Joist assembly

兩條 paired axes 必須與同一支有限 formal Strut 形成實際垂直接觸，且兩個 crossing stations 必須位於同一 formal Column station 的相反兩側。具名設定 SHALL 為 `joist_pair_column_midpoint_tolerance_mm = 2.0`；`pair_midpoint = (station_a + station_b) / 2`，eligibility SHALL 使用 inclusive 判定：`abs(pair_midpoint - column_station) <= 2.0`。

「各側最近」只可在已通過 same-Strut、opposite-side、spacing 與 midpoint eligibility 的候選中排序，不得單獨構成配對依據。沒有合格 pair 時 SHALL 回報 blocking unpaired problem；若有多組合格 pair 且不能由工程證據唯一區分，SHALL 回報 blocking ambiguity，不得依 ID、entity order 或 first occurrence 任選。

#### Scenario: Exact opposite-side pair is eligible

- **WHEN** 兩個合格 crossings 位於同一 Column station 的相反側，spacing 符合 `518 ± 5 mm`，且 midpoint 差為 `0 mm`
- **THEN** 系統 SHALL 接受該 pair

#### Scenario: Midpoint positive inclusive boundary is eligible

- **WHEN** 其他資格均成立且 `pair_midpoint - column_station = +2.0 mm`
- **THEN** 該 pair SHALL 通過 midpoint eligibility

#### Scenario: Midpoint negative inclusive boundary is eligible

- **WHEN** 其他資格均成立且 `pair_midpoint - column_station = -2.0 mm`
- **THEN** 該 pair SHALL 通過 midpoint eligibility

#### Scenario: Midpoint outside the inclusive range is rejected

- **WHEN** `abs(pair_midpoint - column_station) > 2.0 mm`
- **THEN** 該 pair MUST NOT 成為合格 assembly

#### Scenario: Same-side contacts are rejected

- **WHEN** 兩個 crossings 都位於 Column station 同一側，即使 spacing 與 midpoint 其他數值看似接近
- **THEN** 系統 MUST NOT 建立 two-Joist Column assembly

#### Scenario: Nearest but ineligible contacts are ignored

- **WHEN** Column 各側最近的 contacts 未通過 spacing、midpoint、same-Strut 或 perpendicular-contact eligibility，而較遠 contacts 形成唯一合格 pair
- **THEN** 系統 SHALL 只在合格集合中選擇該 pair
- **AND** SHALL NOT 先選 nearest 再放寬資格

#### Scenario: Multiple eligible pairs remain ambiguous

- **WHEN** 同一 Strut／Column assembly 有多組通過所有資格且無法由工程證據唯一區分的 pairs
- **THEN** 系統 SHALL 回報 blocking ambiguity
- **AND** SHALL NOT 依 member ID、entity order 或排序位置任選

#### Scenario: Missing eligible pair is blocking

- **WHEN** formal Strut 與 Column context 中找不到任何通過全部資格的 pair
- **THEN** 系統 SHALL 保留可追溯來源並回報 blocking unpaired problem
- **AND** SHALL NOT 投影不完整 Beam constraint

### Requirement: Paired-axis assembly SHALL map deterministically to runtime Beam models and IDs

一個成功的 paired-axis outcome SHALL 產生兩個 runtime Beam models，每條 source-supported axis 對應一個不同且 deterministic 的 BM ID。兩支 Beam SHALL 共享同一 root `INSERT` provenance 與 paired-assembly identity，但各自保有自己的 axis geometry、crossing records、Strut stations 與 BM ID。

軸與 BM ID 的相對順序 SHALL 由 normalized WCS geometry 決定，不得由 child entity order、LINE direction 或 candidate enumeration order 決定。現有「一個來源最多一模型」安全檢核 SHALL 只對已證明且恰有兩軸的 paired outcome 開放窄例外；第三條模型或未證明的雙模型仍為 blocking error。

#### Scenario: One paired root creates two Beam models

- **WHEN** 一個 root 成功建立 paired-axis outcome
- **THEN** 系統 SHALL 建立兩個不同 BM IDs 與兩個 Beam models
- **AND** 每個 Beam SHALL 對應一條 source-supported axis

#### Scenario: Ordering is deterministic

- **WHEN** 相同 WCS geometry 的 child order、LINE direction 或 enumeration order 改變
- **THEN** paired axes 的 normalized order、BM mapping 與 crossings SHALL 保持等價

#### Scenario: More than two models remains invalid

- **WHEN** 同一 paired root 嘗試產生零、一、三條以上 axes，或兩軸不是同一已證明 assembly
- **THEN** 系統 SHALL 拒絕 paired outcome 並回報 blocking problem

### Requirement: Paired assembly Review and source lifecycle SHALL remain source-atomic

兩個 Beam models SHALL 在構件清單中各自保留可選 BM ID 與 Preview geometry，但其 shared root 是 confirmation、source exclusion／restore 與 fresh-recognition replay 的原子範圍。

確認其中一支 paired Beam 時，confirmation signature SHALL 覆蓋該 root paired assembly 的兩支 Beam engineering state 與共同 problems，使兩支 Beam 的確認狀態一致；任一 axis、crossing、association 或 blocking problem 改變時，整個 assembly 的既有確認 SHALL 失效。從任一 paired Beam 執行 source exclusion SHALL 排除整個 root 與兩支 Beam；restore SHALL 重新辨識該 root，且只有重新得到唯一合法 paired outcome 才可恢復兩支 Beam。

Manual geometry replay 不得因兩個 members 共用 source identity 而任意套用。若既有 replay contract 無法唯一且 deterministic 對應兩條 normalized axes，系統 SHALL 將 override 標記為 needs review，不得套到 first member。

#### Scenario: Each Beam remains selectable

- **WHEN** paired assembly 成功建立
- **THEN** Review SHALL 顯示兩個可依 BM ID 選取與定位的正式 Beam items
- **AND** 兩者 SHALL 顯示共同 root provenance

#### Scenario: Confirmation covers the whole assembly

- **WHEN** 使用者確認 paired assembly 的任一正式 Beam item
- **THEN** 兩個 sibling Beam items SHALL 共用同一 source-level confirmation outcome
- **AND** 任一 sibling engineering state 改變 SHALL 使該 confirmation 失效

#### Scenario: Exclusion and restore are assembly-atomic

- **WHEN** 使用者從任一 sibling Beam 排除共同 root source
- **THEN** 兩支 Beam SHALL 一起移除並形成一個 excluded source decision
- **AND** restore SHALL 由原 root source 一次重建整個 paired assembly

#### Scenario: Ambiguous manual replay is not guessed

- **WHEN** persisted manual override 只能辨識共同 root，無法唯一對應 paired axes
- **THEN** replay SHALL 回報 needs review
- **AND** SHALL NOT 依 BM ID 或 collection order 任意套用

### Requirement: Validated Joist crossings SHALL project without Project schema changes

每一支 paired Beam SHALL 以自己的 BM ID 與實際 crossing station 建立 `BeamCrossing`／association。對同一 Strut 的成功 paired assembly SHALL 投影兩個 station 至既有 `BeamPositions`，並投影兩個對應 BM IDs 至既有 `AssociatedBeamIDs`；完整 Beam axes、shared-root provenance 與 assembly diagnostics SHALL 留在 DXF state。不得合併成單一平均 station，也不得建立新的 Project entity 或 schema migration。

只有通過 recognition、contact 與 assembly finalization 的 crossings 才可進入 Project conversion。既有 Beam exclusion `±550 mm` SHALL 分別套用於兩個 validated stations。

#### Scenario: Project conversion retains two stations and IDs

- **WHEN** paired assembly 對一支 Strut 成功 finalization
- **THEN** Project conversion SHALL 在該 Strut 的既有欄位輸出兩個 Beam stations 與兩個 BM IDs
- **AND** SHALL NOT 以 midpoint 或單一 assembly ID 取代兩個實體 crossings

#### Scenario: Invalid pair does not leak into Project

- **WHEN** paired assembly 為 failed、ambiguous 或 unpaired
- **THEN** 系統 MUST NOT 將其 crossings 投影至 `BeamPositions` 或 `AssociatedBeamIDs`

### Requirement: Brace contact SHALL retain single-Joist semantics

系統 SHALL 允許與 formal Brace 形成有限垂直接觸、且未同時形成需由 Strut／Column pair rule 處理之 blocking Strut contact 的可靠 single-axis Joist，以一支 Joist 成功。Brace contact 不要求 518 mm paired spacing，也不得把 Brace 當成 Strut 或 Column。

成功 recognition 所建立的 Joist-to-Brace contact SHALL 從 pure recognition outcome 保留至對應 runtime Beam 與 DXF Review engineering state，並保存 member role、formal Brace identity、WCS contact point 與 recognition method。後續 association rebuild MUST 使用該 contact truth 或由相同 finalized geometry 與 formal Brace identity 得到等價結果，不得因 runtime projection 只保存 Strut crossing 而遺失 Brace relationship或產生 `BEAM_NOT_ASSOCIATED`。

runtime validation SHALL 使用 `Beam is connected iff beam.crossings is not empty or beam.brace_contacts is not empty`。Pure recognition 的 Strut contacts SHALL 依既有流程投影為 `BeamCrossing`，不得建立第二份 runtime Strut contact collection。本 change MUST NOT 修改 Joist Strut `endpoint_face_contact`、direct Strut crossing eligibility、station 或 Project projection。

Brace-only single Joist SHALL 維持沒有 Strut `BeamCrossing`、`BeamPositions` 或 `AssociatedBeamIDs`；Brace contact 不得偽裝成 Strut constraint。Joist-to-Brace direct contact 若發生在兩條 finite segments 的真實共用 endpoint 且角度資格成立，仍為合法 direct contact；endpoint face projection、nearest point、finite gap 或無限延長線交點不得建立 Brace contact。

#### Scenario: Brace-only single Joist is valid

- **WHEN** 一支 source-supported single-axis Joist 與 formal Brace 有唯一有限垂直接觸，且沒有未解決的 Strut assembly obligation
- **THEN** 系統 SHALL 保留一支 formal Beam 與 Brace relationship
- **AND** SHALL NOT 要求第二支 Joist 或套用 518 mm spacing

#### Scenario: Runtime projection retains the recognized Brace contact

- **WHEN** Brace-only single Joist recognition 成功並轉換為 runtime Beam／DXF Review state
- **THEN** runtime engineering state SHALL 保留相同 formal Brace identity、WCS contact point 與 recognition method
- **AND** MUST NOT 因沒有 Strut crossing 而產生 `BEAM_NOT_ASSOCIATED`

#### Scenario: Pure Strut contacts keep the existing runtime projection

- **WHEN** Joist pure recognition 建立既有 direct Strut contact 或合格 Strut `endpoint_face_contact`
- **THEN** importer SHALL 依既有流程建立 `BeamCrossing`
- **AND** SHALL NOT 因本 change 建立第二份 Strut contact collection或改變 crossing eligibility、station 與 Project projection

#### Scenario: Brace relationship does not become a Strut constraint

- **WHEN** Brace-only single Joist 已保留其 runtime Brace contact
- **THEN** 系統 SHALL NOT 由該 contact 建立 `BeamCrossing`、`BeamPositions`、`AssociatedBeamIDs` 或 Solver constraint

### Requirement: Y05 characterization SHALL remain a regression contract

目前 Y05 fixture 中已確認 20 個雙 C paired assemblies，每個 assembly 恰有兩條 source-supported axes，共代表 40 支實體 Joists；另有六個角落各 3 支與 Brace 形成有限垂直接觸的 single-axis Joists，共 18 支。因此完整 recognition outcome SHALL 為 58 支 formal Joists。

上述 20 個 paired assemblies 跨越多支有限 Struts，合計形成 68 組 paired-axis-to-Strut contact relations。Column-qualified terminal residual recovery 後，20 組原本停在第一支主 Strut 外緣的 paired relations SHALL 恢復為跨越該 Column／Strut corridor 的 source-supported axes，並改以 direct finite crossings 表達；其餘 48 組 direct relations 維持 direct。每一 relation SHALL 由同一 paired assembly 的兩條 envelope center axes 對同一有限 Strut 建立；relation 數不得誤當成 Joist 或 assembly 數。

Characterization 的 station spacing 範圍仍為約 `518.000–518.001 mm`，Column midpoint absolute error 範圍仍為 `0–0.942 mm`；terminal extent 與 contact method 的改變 MUST NOT 改變這些 stations、Column identity 或正式 pair eligibility。這些觀測支持但不取代正式的 `518 ± 5 mm` 與 midpoint `±2 mm` inclusive contracts。

#### Scenario: Y05 component inventory remains valid

- **WHEN** 以目前 Y05 fixture 與正式 upstream context 執行 whole-source Joist recognition
- **THEN** 系統 SHALL 建立 20 個 paired assemblies／40 支 paired-axis Joists
- **AND** SHALL 建立六個角落各 3 支、合計 18 支 Brace-contact single-axis Joists
- **AND** formal Joist 總數 SHALL 為 58 支
- **AND** 與主構件幾何高度重疊的 46 個 L-angle detail／residual roots SHALL NOT 另建 formal Joists

#### Scenario: Y05 E8F and BM18 recover the Column-side terminal

- **WHEN** Y05 root `E8F` 的等價來源在第一支主 Strut／Column corridor 外側具有同 root、同方向且對齊既有雙 C rail bands 的 terminal residuals，其最外端距 Column center 約 `675 mm`
- **THEN** 兩條 paired axes SHALL 各自將 terminal extent 從約 `X=-35323.5` 恢復至自身來源支持的約 `X=-36173.5`
- **AND** BM18 對該第一支主 Strut SHALL 使用 finite crossing，而非 `endpoint_face_contact`
- **AND** 對應 Strut station、Column midpoint 與 paired spacing SHALL 保持等價

#### Scenario: Y05 F2A accepts collectively aligned Brace-clipped residuals

- **WHEN** Y05 root `F2A` 的一個 sibling envelope 具有完整 500 mm terminal rails，另一個 sibling envelope 的對應 rail bands被斜撐投影切成長度不一的短 fragments，但兩側仍通過 Column window、rail alignment、sibling support 與 terminal compatibility
- **THEN** 系統 SHALL 將兩支 sibling axes 分別恢復至各自 source-supported terminal station；兩個 endpoints 可以不同，且不得因 `50 mm` compatibility tolerance 取較外值、平均或互相延伸成相同端點
- **AND** SHALL NOT 將附近未對齊的短 detail 建立為第三條 axis 或新的 Beam

#### Scenario: All 68 Y05 paired-axis-to-Strut relations remain valid

- **WHEN** 以目前 Y05 fixture、正式 upstream context、Column-qualified terminal recovery 與 whole-source double-C axes 執行 recognition
- **THEN** 68 組已 characterization 的 paired-axis-to-Strut relations SHALL 全部通過 spacing 與 midpoint eligibility
- **AND** 68 組 SHALL 全部由 finalized axes 的 direct finite crossings 建立
- **AND** 不得退回局部 parallel pair、428 mm 淨距或 441／443.5 mm web 間距

#### Scenario: Y1A and Y29 legacy Beam recognition remains unchanged

- **WHEN** 以目前 Y1A 與 Y29 fixtures 執行一般 MLINE／closed-outline Beam recognition
- **THEN** 系統 SHALL 維持既有 Beam 數量、來源路徑、起終點與 association outcomes
- **AND** SHALL NOT 對非 BIM root 套用 Column-qualified terminal residual recovery

### Requirement: Legacy non-BIM Beam recognition and DXF Review lifecycle SHALL remain compatible

Standalone LINE、MLINE、closed outline 與其他非 component-like Beam sources SHALL 維持既有 recognition path、source axis 與 path geometry，不得套用 BIM whole-source topology、雙 C assembly、Column terminal recovery 或 `518 ± 5 mm` pair rule。

上述 legacy compatibility 不禁止 downstream connection validation 使用 formal Brace context。一般 Beam MAY 依 `beam-member-connection-validation` capability，以其 finalized finite path 與 formal Brace finite segment 的實際近似垂直接觸建立 Brace relationship及滿足已連接狀態；此行為 MUST NOT 改寫 Beam recognition geometry、source fingerprint、coordinate conversion、Pause／Resume、Project schema、Solver、material rules、Waler contact adjustment、Double Support 或一般 Strut／Brace recognition。

一般 Beam 的 runtime connected predicate、`BeamBraceContact` engineering identity、共用頂點去重、distinct WCS contacts、finite endpoint eligibility 與 rebuild behavior SHALL 完整遵守 `beam-member-connection-validation` capability，不得由 legacy path 建立較寬鬆的 nearest／gap／face-projection 規則。

#### Scenario: Non-BIM Beam source retains legacy behavior

- **WHEN** Beam source 不符合 BIM root eligibility
- **THEN** 系統 SHALL 使用既有適用的 Beam recognition behavior
- **AND** SHALL NOT 套用雙 C 518 mm assembly rule、BIM terminal recovery 或改寫其 finalized path

#### Scenario: Legacy Beam may use qualified Brace contact for connection validation

- **WHEN** 一支 legacy Beam 的 finalized finite path 與 formal Brace 形成符合 `beam-member-connection-validation` 的 contact
- **THEN** 系統 SHALL 允許該 Brace relationship滿足托梁已連接狀態
- **AND** SHALL NOT 將 Brace relationship投影成 Strut constraint

#### Scenario: Disk resume rebuilds derived Joist outcomes safely

- **WHEN** paused Review 由相同 source fingerprint 從 disk 恢復
- **THEN** 系統 SHALL 由 fresh recognition 重建 Joist axes、Strut crossings、Brace contacts 與 paired relationships
- **AND** SHALL 依既有 confirmation、exclusion 與 manual replay safety contract 恢復 Review state
