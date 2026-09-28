# Spec Delta

## ADDED Requirements

### Requirement: Same-source outline topology SHALL constrain Strut rail pairing

對位於 Strut role layer 的單一 root `INSERT`，系統 SHALL 將可辨識的完整外框或等價的連續 rail topology 視為 longitudinal rail pairing 的來源邊界。兩條 longitudinal rail 只有在同一個可驗證 outline／rail topology 中互為對應邊時，才可共同推導工程中線；系統 MUST NOT 將不同 outline topology 的 rail 交叉配對，也不得只因兩條 rail 平行、長度相近、投影重疊、間距合理或位於同一 root source，就認定它們互為 companion rails。

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

#### Scenario: Ordinary root INSERT without usable outline topology retains compatibility

- **WHEN** 一個非 component-like root `INSERT` 沒有可驗證的完整 outline／rail topology
- **THEN** 系統 SHALL 維持既有 non-component fallback eligibility
- **AND** 本 requirement 不得僅因缺乏 topology evidence 而把該 source 視為多構件或強制產生 blocking problem

### Requirement: Recognized Strut width SHALL come from a unique valid component envelope

系統 SHALL 將 Strut 工程軸辨識與 `source_width` 判定視為兩個相關但可獨立成立的結果。Strut 不具有固定 350 mm 寬度；對不同合法支撐寬度，系統 SHALL 從該 root source 內唯一、完整且可靠的 component envelope 橫向尺寸推導 `source_width`。

有效 component envelope 必須具有可驗證的 closed outline 或 connected contour、支持完整構件縱向 extent，並能以來源拓撲與內部 detail rails 區分。當同軸、全長且巢狀的有效外框存在唯一外包絡時，系統 SHALL 以該外包絡寬度作為 `source_width`；這是 topology containment 的結果，不得以任意最小值、平均值、局部 rail 間距或 candidate 排名代替。

沒有封閉或連接 provenance 的開放內部 rails MUST NOT 決定或覆寫 `source_width`。若工程軸可唯一辨識，但沒有唯一可靠的 component envelope，系統 SHALL 保留該工程軸、將來源寬度視為未知，且 MUST NOT 自動指派材料規格；既有材料 Review 仍可由使用者確認。現有 `maximum_component_width_mm = 600` 只作為具名 recognition eligibility setting；已確認的合法支撐寬度均小於此值，本 change 不變更該設定，也不把 600 mm 或 350 mm 宣告為材料規格。

#### Scenario: A non-350 component envelope preserves its actual width

- **WHEN** 一個 component-like Strut root `INSERT` 具有唯一、完整且可驗證的 400 mm 或 500 mm 寬 component envelope
- **THEN** 系統 SHALL 從該 envelope 建立完整工程軸
- **AND** `source_width` SHALL 分別反映約 400 mm 或 500 mm，而不是固定為 350 mm

#### Scenario: Y05 S10 width comes from its connected outer contour

- **WHEN** Y05 S10 root handle `D17` 具有約 350 mm 寬的完整 connected outer contour，以及間距約 12 mm 但無 companion provenance 的開放內部 rails
- **THEN** 系統 SHALL 以完整 connected outer contour 推導約 350 mm 的 `source_width`
- **AND** SHALL NOT 以 12 mm rail 間距推導或覆寫材料寬度

#### Scenario: Unique axis without a unique envelope does not guess material width

- **WHEN** root source 的幾何足以唯一建立完整 Strut 工程軸，但沒有唯一可靠的 component envelope 可決定物理寬度
- **THEN** 系統 SHALL 保留該唯一工程軸
- **AND** SHALL 將 `source_width` 視為未知
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

## MODIFIED Requirements

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
