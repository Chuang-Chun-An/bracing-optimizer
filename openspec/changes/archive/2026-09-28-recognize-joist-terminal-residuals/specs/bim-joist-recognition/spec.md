# Spec Delta

## 閱讀導航

### 必讀

- ADDED「已證明跨越中間柱的托梁可恢復端部殘線」：定義 700 mm 候選窗、來源資格與 paired terminal 行為。
- MODIFIED「Joist contact SHALL preserve source axes while supporting finite crossings and qualified Strut-face contacts」：定義 terminal recovery 與 contact classification 的先後順序。
- MODIFIED「Y05 characterization SHALL remain a regression contract」：更新 Y05 E8F／BM18、F2A 與 crossing regression。

### 條件式閱讀

- 修改 Joist pure recognition／axis extent 時，完整閱讀三個 Requirements。
- 修改 contact、association 或 Project projection 時，閱讀兩個 MODIFIED Requirements，並對照 main spec 的 Project projection requirement。
- 修改 Y1A／Y29 legacy Beam path 時才需要閱讀最後的 backward-compatibility scenarios。

### 可先跳過

- Main spec 的 Review source-atomic、manual replay 與 Project schema Requirements 沒有改變，可在處理對應 regression 時再讀。
- Solver、Waler optimization、BIM Strut、Brace extension 與 CornerBrace repair specs 不在本 change 範圍。

## ADDED Requirements

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

## MODIFIED Requirements

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
