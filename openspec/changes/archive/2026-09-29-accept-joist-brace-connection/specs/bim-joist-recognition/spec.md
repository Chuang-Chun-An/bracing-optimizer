# BIM Joist Recognition Spec Delta

## 閱讀導航

### 必讀

- MODIFIED「Brace contact SHALL retain single-Joist semantics」：要求 Brace contact 從 pure recognition 保留到 runtime Review state，且不產生 Strut constraint。
- MODIFIED「Legacy non-BIM Beam recognition and DXF Review lifecycle SHALL remain compatible」：允許一般 Beam 採用相同保守 Brace direct-contact contract。

### 條件式閱讀

- 修改共用 warning 或 rebuild 行為時，同時閱讀 `specs/beam-member-connection-validation/spec.md`。
- 修改 paired assembly 或 Project projection 時，回讀 main spec 的 paired-axis 與 validated crossing Requirements。

### 可先跳過

- Column terminal residual recovery、`518 ± 5 mm` spacing、midpoint `±2 mm` 與 Y05 paired-axis station 細節不由本 delta 修改。

## MODIFIED Requirements

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

