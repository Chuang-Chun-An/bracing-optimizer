# Spec Delta

## Purpose

本 capability 讓 DXF Import 能在不破壞一般圖層／線段辨識的前提下，從代表單一實體 Strut 的 BIM root `INSERT` 全體 WCS geometry，可靠重建完整工程軸並保留既有 Review 與來源追溯契約。

## ADDED Requirements

### Requirement: BIM Block recognition SHALL be a restricted Strut source path

系統 SHALL 僅將位於使用者指定 Strut role layer 的 root `INSERT` 視為 BIM component-like recognition 的候選 source scope。root `INSERT` 的存在不得直接等同一支正式 Strut；系統 MUST 先判斷該 source scope 的整體 geometry 是否支持單一實體構件。

root layer classification SHALL 決定候選 role。遞迴展開後的 child entity layer（包含 Layer 0）只提供 geometry evidence，不得重新分類為其他 member role。

第一版 SHALL 只啟用 Strut BIM Block recognition，不得改變 Brace、Waler、Continuous Wall、Column、Beam 或 CornerBrace 的辨識規則。

#### Scenario: Root Strut layer supplies the role

- **WHEN** root `INSERT` 位於已分類為 Strut 的 layer，且其 child LINE／POLYLINE 位於 Layer 0 或其他 child layer
- **THEN** 系統以 Strut role 評估整個 root source scope
- **AND** child layer 不會使 geometry 失去 Strut role 或改成其他 role

#### Scenario: INSERT identity alone is insufficient

- **WHEN** Strut role layer 上的 root `INSERT` 內含多個互不相關、無法支持單一構件形狀的 geometry
- **THEN** 系統不得僅因它是一個 `INSERT` 就建立正式 Strut

#### Scenario: Brace behavior remains unchanged

- **WHEN** root `INSERT` 位於 Brace role layer
- **THEN** 系統 SHALL 使用本 change 之前的 Brace recognition behavior
- **AND** 不得套用 Strut BIM component-like path

### Requirement: Component-like eligibility SHALL use whole-source evidence

系統 MUST 以同一 root `INSERT` 的全體有效 geometry 判斷是否為 component-like Strut。充分證據 SHALL 同時支持：

- 單一明顯的主要長方向；
- 相對於橫向寬度呈細長的整體 extent；
- 大部分有效 longitudinal geometry 沿共同方向排列；
- fragment center 或等價的 longitudinal evidence 大致落在共同工程軸附近；
- fragments 的橫向寬度具合理一致性；
- 整體 evidence 支持一支完整 Strut，而不是多個互不相關構件。

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

### Requirement: The formal axis SHALL represent the whole supported component extent

對已通過 component-like eligibility 的 root `INSERT`，系統 SHALL 從整體 evidence 推導唯一工程軸。正式軸 MUST 代表主要構件有可靠 geometry 支持的完整 longitudinal extent，不得只使用其中一個 fragment、局部 closed outline、局部漂亮平行邊對或最長單一 LINE 的長度。

內部 fragment gaps 不構成自動拆件條件。即使 gap 明顯大於一般 LINE recognition 的 small-gap tolerance，只要 root identity、共同方向、共同軸對齊、寬度一致性與整體 component shape 仍提供強而一致的證據，系統 SHALL 允許跨越該 interior gap 重建一支 Strut。系統不得越過缺乏來源支持的 terminal extent 外插工程軸。

#### Scenario: Complete outline produces one full Strut

- **WHEN** BIM Strut root `INSERT` 具有一個可唯一支持完整構件 extent 的正常封閉外框
- **THEN** 系統 SHALL 辨識為一支涵蓋完整外框長度的 Strut

#### Scenario: Occlusion gaps do not split a supported component

- **WHEN** 同一 root `INSERT` 的 aligned fragments 之間存在明顯 interior gaps，但整體 axis、width、alignment 與 extent evidence 強烈支持同一構件
- **THEN** 系統 SHALL 重建一支跨越 interior gaps 的完整 Strut
- **AND** 不得只因 gap 大而拆成多支 Strut

#### Scenario: Local short parallel pair cannot truncate the member

- **WHEN** 一支整體約 12 m 的 component-like Strut Block 含有一組約 3 m 的局部平行邊，而其他 aligned evidence 顯示構件明顯更長
- **THEN** 正式工程軸 SHALL 代表主要構件的完整 supported extent
- **AND** 系統不得產生只涵蓋該 3 m 局部 pair 的正式 Strut

#### Scenario: Y05 S2 retains the whole supported axis

- **WHEN** Y05 S2 root handle `957` 的等價 WCS geometry 由多組沿共同縱向排列的 LINE fragments 形成，且整體 evidence 支持約 `18,900 mm` 的完整軸
- **THEN** BIM component-like recognition SHALL 重建約 `(-53379, -9450) → (-53379, 9450)` 的完整工程軸
- **AND** SHALL NOT 退回既有約 `6,978 mm`、約 `(-53379, -3488.368) → (-53379, 3489.368)` 的局部平行邊辨識

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

特殊辨識 SHALL 產生下列互斥結果：

1. `not applicable`：root source 缺乏 component-like 資格，系統 MUST 回到目前一般 DXF recognition；
2. `recognized`：component-like 資格成立且存在唯一可靠的完整工程軸，系統 SHALL 產生一個 Strut candidate；
3. `failed or ambiguous`：component-like 資格已成立，但完整 extent 無法可靠重建，或存在多個同樣合理且互相衝突的完整工程軸，系統 MUST 回報 blocking recognition problem，不得再回到會選取局部 geometry 的一般 fallback。

`failed or ambiguous` 結果 SHALL 保留 root source identity，形成既有 Review workflow 可顯示的 unresolved ReviewItem，且不得從該 root source 建立 formal Strut。

#### Scenario: Non-component INSERT keeps general recognition

- **WHEN** 一個一般人工 CAD `INSERT` 不符合 component-like eligibility
- **THEN** 系統 SHALL 將該 root source 交回既有一般 recognition
- **AND** 一般非 BIM behavior 不因本 change 被強制改寫

#### Scenario: Conflicting complete axes are ambiguous

- **WHEN** 同一 component-like root Block 同時支持兩個互相衝突且近似可信的完整工程軸，且沒有足夠 evidence 唯一決定
- **THEN** 系統 SHALL 回報 blocking ambiguous recognition problem
- **AND** SHALL 建立以該 root source 為 identity 的 unresolved ReviewItem
- **AND** SHALL NOT 任意選擇其中一軸或建立 formal Strut

#### Scenario: Unreliable complete extent fails instead of truncating

- **WHEN** source 已可判定為 component-like，但 geometry 無法可靠確定完整 longitudinal extent
- **THEN** 系統 SHALL 回報 blocking recognition failure
- **AND** SHALL NOT 以局部 fragment 建立較短 formal Strut

### Requirement: Root INSERT SHALL remain the recognition source boundary

每個 root `INSERT` SHALL 是獨立的 recognition source scope。系統 MUST 在同一 root scope 內整合 child fragments，但不得因不同 root `INSERT` 的 geometry 共線、接近或寬度相同，就合併成同一正式構件。

一個成功的 component-like root source SHALL 最多產生一個 BIM Strut candidate。若同一 source 顯示多構件或多解，系統 SHALL 依 failure／ambiguity 規則處理，而不是拆出多個 formal Struts。

#### Scenario: Collinear root INSERTs remain separate

- **WHEN** 兩個不同 root `INSERT` 的 fragments 恰好共線且各自支持一支 Strut
- **THEN** 系統 SHALL 產生兩個來源獨立的 Strut candidates
- **AND** 不得跨 root handle 合併為一支構件

#### Scenario: One root cannot silently yield several BIM Struts

- **WHEN** 單一 root `INSERT` 的 geometry 看似包含多個互不相關的完整構件
- **THEN** 系統 SHALL NOT 由 BIM component-like path 產生多個 formal Struts
- **AND** SHALL 依 not-applicable 或 ambiguous behavior 處理

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
