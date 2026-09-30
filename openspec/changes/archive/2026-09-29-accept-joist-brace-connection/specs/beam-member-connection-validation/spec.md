# Beam Member Connection Validation Specification

## 閱讀導航

### 必讀

- 「正式支撐或斜撐接觸皆可滿足托梁連接狀態」：定義何時不再顯示未連接警告。
- 「斜撐接觸不得建立支撐限制」：定義 Brace contact 與 Strut constraint 的邊界。
- 「重建流程必須保持相同連接結果」：定義初次匯入與 derived rebuild 的一致性。

### 條件式閱讀

- 修改 BIM Joist importer projection 時，連同本 change 的 `bim-joist-recognition` delta spec 閱讀。
- 修改座標系統、Review confirmation 或 source replay 時，閱讀 contact identity 與 WCS／local projection scenarios。

### 可先跳過

- Solver、材料配置、BIM paired-axis spacing、Column terminal recovery 與 Waler connection 規則不受本 capability 影響。

## Purpose

本 capability 定義正式托梁如何由 Strut 或 Brace 的可靠有限接觸判定為已連接，並確保 Brace contact 只修正 Review 警告、不會被誤投影成 Strut station、Project constraint 或 Solver 禁止點。

## ADDED Requirements

### Requirement: Runtime 托梁連接狀態 SHALL 只有一個正式 predicate

正式 runtime 判斷 MUST 為：`Beam is connected iff beam.crossings is not empty or beam.brace_contacts is not empty.` 只有 `beam.crossings` 與 `beam.brace_contacts` 同時為空時，系統才可產生 `BEAM_NOT_ASSOCIATED` warning；該 warning 的使用者訊息 MUST 明確表示托梁未與任何正式支撐或斜撐形成有效接觸，且因此沒有建立 Strut constraint。

在 runtime validation 語境中，Strut contact SHALL 只指既有流程已建立的 `BeamCrossing`；Brace contact SHALL 只指新的 `BeamBraceContact`。本 change MUST NOT 新增第二份 Strut contact collection。Pure recognition 的 Strut contact SHALL 依既有流程投影為 `BeamCrossing`；Joist Strut `endpoint_face_contact`、Strut crossing eligibility、station 與 Project projection MUST 維持不變。

合格 `BeamBraceContact` MUST 由 finalized、source-supported Beam／Joist finite path segment 與 formal Brace finite segment 的實際交點建立，且兩線段的夾角與 90 度之差 MUST `<= 5.0°`。`5.0°` 邊界為 inclusive。

系統 MUST NOT 以無限延長線交點、nearest geometry、一般小間隙吸附、INSERT point、Brace 外框距離或 Brace face projection 建立 Brace contact。只有非垂直接近或夾角與 90 度之差 `> 5.0°` 時，該幾何 MUST NOT 單獨滿足托梁連接狀態。

#### Scenario: Existing Strut crossing alone means connected

- **WHEN** `beam.crossings` 非空且 `beam.brace_contacts` 為空
- **THEN** Beam SHALL 為 connected
- **AND** 既有 Strut crossing、station 與 Project projection SHALL 保持不變

#### Scenario: Brace-only finite perpendicular contact suppresses the warning

- **WHEN** `beam.crossings` 為空且 `beam.brace_contacts` 非空
- **THEN** 系統 SHALL 將該托梁視為已連接
- **AND** MUST NOT 產生 `BEAM_NOT_ASSOCIATED`
- **AND** MUST NOT 產生 Strut constraint

#### Scenario: Both member roles are absent

- **WHEN** `beam.crossings` 與 `beam.brace_contacts` 都為空
- **THEN** 系統 SHALL 產生 `BEAM_NOT_ASSOCIATED` warning
- **AND** 訊息 SHALL 表示沒有正式支撐或斜撐接觸，且未建立 Strut constraint

#### Scenario: Perpendicular tolerance uses inclusive boundary

- **WHEN** 托梁與 formal Brace finite segments 實際相交，且夾角與 90 度之差恰為 `5.0°`
- **THEN** 該交點 SHALL 通過 Brace contact 的角度資格

#### Scenario: Finite shared endpoint is a direct contact

- **WHEN** finalized Beam segment 與 formal Brace finite segment 真實共用一個 endpoint，且夾角與 90 度之差 `<= 5.0°`
- **THEN** 系統 SHALL 建立該 WCS endpoint 的 `BeamBraceContact`
- **AND** MUST NOT 將此 direct finite contact誤分類為 endpoint face projection

#### Scenario: Infinite or near-only geometry is not a connection

- **WHEN** 托梁與 Brace 只有無限延長線相交、只有有限 gap、只有 endpoint face projection／nearest point、只在外框上接近，或夾角與 90 度之差 `> 5.0°`
- **THEN** 系統 MUST NOT 以該幾何建立 Brace contact
- **AND** 若 `beam.crossings` 與 `beam.brace_contacts` 因此同時為空，系統 SHALL 產生 `BEAM_NOT_ASSOCIATED`

### Requirement: BeamBraceContact engineering identity SHALL be independent of segment provenance

`BeamBraceContact` engineering identity SHALL 由 Beam identity、Brace identity 與 tolerance-equivalent WCS contact point 組成。WCS point equivalence SHALL 重用既有 `beam_crossing_duplicate_tolerance_mm`，以 point distance `<= tolerance` 視為同一位置。`beam_segment_index` SHALL 只作 provenance，MUST NOT 參與 contact engineering identity。

同一 Beam identity、Brace identity 與 tolerance-equivalent WCS point MUST 只建立一筆 `BeamBraceContact`。若同一 WCS contact point 位於兩個相鄰 Beam path segments 的共用頂點，系統 SHALL 合併為一筆 contact，並 SHALL 由 normalized segment geometry 的 deterministic canonical ordering 選擇 provenance segment index；MUST NOT 依 segment iteration order、Brace order或 first match 產生兩筆或選擇 winner。

若同一 Beam 與同一 Brace 在兩個距離 `> beam_crossing_duplicate_tolerance_mm` 的 WCS points 真實相交，系統 SHALL 保留兩筆 contacts。Beam path 方向或 internal segment iteration order 改變時，engineering contact集合與 connected／warning outcome SHALL 保持等價。

#### Scenario: Adjacent segments share one vertex contact

- **WHEN** 同一 formal Brace 在相鄰兩個 Beam path segments 的共用頂點形成同一個合格 WCS contact
- **THEN** 系統 SHALL 只建立一筆 `BeamBraceContact`
- **AND** SHALL 以 deterministic canonical segment rule 保存一個 provenance `beam_segment_index`

#### Scenario: Two distinct WCS intersections remain distinct

- **WHEN** 同一 Beam 與同一 formal Brace 在兩個距離 `> beam_crossing_duplicate_tolerance_mm` 的 WCS points 真實相交且角度資格均成立
- **THEN** 系統 SHALL 保留兩筆 `BeamBraceContact`

#### Scenario: Path and iteration order do not change engineering outcome

- **WHEN** 等價 Beam path 以反向點序或不同 internal segment iteration order接受 validation，且 formal Brace geometry 未變
- **THEN** contact engineering identity集合 SHALL 保持等價
- **AND** connected predicate 與 `BEAM_NOT_ASSOCIATED` 結果 SHALL 保持相同
- **AND** MUST NOT 依 Brace collection order或 first match 改變結果

### Requirement: 斜撐接觸不得建立支撐限制

Brace contact SHALL 保留其 member role、formal Brace identity、WCS contact point 與 recognition method，並與 Strut crossing 保持可區分。系統 MUST NOT 將 Brace contact 表示為 Strut crossing，也 MUST NOT 由 Brace contact 建立 `strut_id`、`strut_station`、`BeamCrossing`、`ComponentAssociation`、`BeamPositions`、`AssociatedBeamIDs` 或任何 Solver constraint／forbidden point。

同一托梁同時具有 `BeamCrossing` 與 `BeamBraceContact` 時，既有 `BeamCrossing` SHALL 繼續依既有規則投影；`BeamBraceContact` 僅參與托梁連接狀態與 DXF Review engineering truth，不得增加、刪除、合併或改寫任何 Strut station。

#### Scenario: Brace-only contact creates no Strut constraint

- **WHEN** 一支托梁只有合格 Brace contact
- **THEN** 系統 SHALL 保留該 Brace relationship 並視托梁為已連接
- **AND** SHALL NOT 產生任何 Strut crossing、station、Project Beam constraint 或 Solver forbidden point

#### Scenario: Mixed contacts retain only real Strut projections

- **WHEN** 同一支托梁的 `beam.crossings` 與 `beam.brace_contacts` 同時非空
- **THEN** 系統 SHALL 只把既有 `BeamCrossing` 投影成 associations 與 Project constraints
- **AND** Brace contacts MUST NOT 改變任何 Strut identity 或 station

#### Scenario: Brace contact does not leak into downstream Strut consumers

- **WHEN** 一支托梁建立或移除 `BeamBraceContact`
- **THEN** 該 contact MUST NOT 增加或修改 `BeamCrossing`、`ComponentAssociation`、`BeamPositions`、`AssociatedBeamIDs` 或 Solver input

### Requirement: 重建流程必須保持相同連接結果

初次 DXF 匯入、座標投影、source exclusion／restore、fresh recognition replay、Waler contact adjustment 及其他會重建 Beam associations 的既有流程，SHALL 使用同一 finalized geometry、formal member identities 與 Brace contact qualification。只要相關 source geometry 與 formal upstream members 未改變，Brace-only 托梁在重建前後 MUST 維持已連接，且 `BEAM_NOT_ASSOCIATED` 不得因進入不同 rebuild path 而重新出現。

Brace contact 的工程 identity 或 WCS point 改變時，依賴該工程狀態的既有 Review confirmation SHALL 失效；僅 local coordinate origin 改變時，WCS truth SHALL 保持不變，local contact point SHALL 隨目前 coordinate system 重新投影。

#### Scenario: Derived rebuild preserves Brace-only connection

- **WHEN** 一支 Brace-only 托梁在未改變 source geometry 與 formal Brace identity 的情況下進入 association rebuild
- **THEN** 重建結果 SHALL 仍保留相同 Brace contact identity
- **AND** MUST NOT 新增 `BEAM_NOT_ASSOCIATED`

#### Scenario: Excluded Brace removes stale contact and reevaluates warning

- **WHEN** rebuild 前一支 Beam 只有某 formal Brace contact，而該 Brace 在目前 truth 中已被排除
- **THEN** rebuild SHALL 移除對應 `BeamBraceContact`
- **AND** SHALL 依目前 `beam.crossings` 與 `beam.brace_contacts` 重新判斷 connected 狀態
- **AND** 若兩者都空，SHALL 產生 `BEAM_NOT_ASSOCIATED`

#### Scenario: Coordinate projection preserves WCS truth

- **WHEN** DXF Review 改變 local coordinate origin
- **THEN** Brace contact 的 WCS point 與 formal Brace identity SHALL 保持不變
- **AND** local contact point SHALL 依新的 coordinate system 重新計算

#### Scenario: Contact change invalidates stale confirmation

- **WHEN** fresh recognition 使既有 Brace contact 的 member identity、WCS point 或有無狀態改變
- **THEN** 依賴原接觸工程狀態的既有 Review confirmation SHALL 失效
- **AND** 系統 MUST NOT 沿用舊 contact 只為避免警告

