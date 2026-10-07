# Spec Delta

## 閱讀導航

- **必讀**：「可靠 Waler envelope 的代表寬度必須使用正交間距」Requirement；它定義本 change 唯一新增的正式辨識行為。
- **條件式閱讀**：若修改材料辨識，閱讀「Y29 W18 使用修正後寬度配對材料」與「Y29 W19 維持既有寬度與材料」Scenarios；若修改 overlap／terminal topology，閱讀「W18／W19 overlap 與 B15 端點歧義不受影響」Scenario；若修改旋轉或來源正規化，閱讀「旋轉、端點方向與來源順序不改變寬度」Scenario。
- **可先跳過**：主規格中的接觸側 unique-first precedence、Brace terminal identity、overlap competition 與 Project lifecycle Requirements；本 change 不修改這些規則。

## ADDED Requirements

### Requirement: 可靠 Waler envelope 的代表寬度必須使用正交間距

當 Waler 來源辨識已在單一 qualified component scope 內建立兩條最外 longitudinal faces 時，系統 MUST 以這兩條 faces 所在 supporting lines 之間的正交間距作為唯一代表 `source_width`。完全平行時，該值 MUST 為固定的 line-to-line perpendicular distance；在既有 `parallel_angle_tolerance_deg` 內但不完全平行時，系統 MUST 使用對稱正交量測，即分別量取每條 face 中點到另一條 supporting line 的正交距離，再取兩者平均。

此規則屬於 DXF Recognition Engineering Policy。有限 rail 的縱向端點錯位、overhang、斜端長度或端點到另一有限 segment 的距離 MUST NOT 增加或減少代表寬度。系統 MUST 將同一 `source_width` 提供給 Review 顯示、Waler contact review baseline 與既有材料規格辨識，不得由 downstream path 重新推導第二套寬度。

此 change MUST NOT 改變既有 outer-face qualification、`parallel_angle_tolerance_deg`、`minimum_projection_overlap_ratio`、一般構件最大寬度 gate、contact-face finalization、單線 Waler unknown-width semantics，或材料規格的 `material_width_tolerance_mm = 1.0` 唯一匹配規則。

#### Scenario: 對齊的平行外側線維持原寬度
- **WHEN** qualified Waler envelope 的兩條平行外側 supporting lines 正交相距 `350.000 mm`，且有限線段端點沿縱向對齊
- **THEN** 系統 SHALL 產生 `source_width = 350.000 mm`
- **AND** 既有 envelope、接觸面與材料規格流程 SHALL 維持相容

#### Scenario: 縱向端點錯位不增加寬度
- **WHEN** qualified Waler envelope 的兩條平行外側 supporting lines 正交相距 `400.000 mm`，但其中一條有限 rail 沿縱向延伸或縮短，使端點不對齊或端部形成斜邊
- **THEN** 系統 SHALL 產生約 `400.000 mm` 的 `source_width`
- **AND** MUST NOT 將斜邊長度、longitudinal residual 或有限端點到另一 segment 的距離納入寬度

#### Scenario: 容許角度內的外側線使用對稱正交量測
- **WHEN** qualified Waler envelope 的兩條外側 faces 不完全平行，但角度差 `<= parallel_angle_tolerance_deg`
- **THEN** 系統 SHALL 以兩個「face 中點到另一條 supporting line」正交距離的平均作為 `source_width`
- **AND** MUST NOT 改用有限 segment 最短距離、四端點平均、最小寬度或最大寬度

#### Scenario: 旋轉、端點方向與來源順序不改變寬度
- **WHEN** 同一 qualified Waler envelope 只改變整體 WCS 旋轉、兩條 faces 的 start／end 表示方向或 source entity iteration order，而幾何保持等價
- **THEN** `source_width` SHALL 保持數值等價
- **AND** 對應材料規格辨識結果 SHALL 保持相同

#### Scenario: Y29 W18 使用修正後寬度配對材料
- **WHEN** 系統辨識 Y29 W18 source handle `69F`，其兩條 longitudinal outer supporting lines 正交相距約 `400.000 mm`，且圍令材料選項同時包含 `H400x400` 與 `H414x405`
- **THEN** W18 的 `source_width` SHALL 約為 `400.000 mm`，而不是 `404.682 mm`
- **AND** 既有 `±1.0 mm` 唯一匹配規則 SHALL 自動選擇 `H400x400`
- **AND** MUST NOT 自動選擇 `H414x405`

#### Scenario: Y29 W19 維持既有寬度與材料
- **WHEN** 系統以相同正交公式辨識 Y29 W19 source handle `720`，且圍令材料選項包含 `H400x400`
- **THEN** W19 的 `source_width` SHALL 維持約 `400.000 mm`
- **AND** 既有 `±1.0 mm` 唯一匹配規則 SHALL 維持自動選擇 `H400x400`
- **AND** W19 SHALL 維持通過既有 `maximum_component_width_mm = 600.0` gate

#### Scenario: W18／W19 overlap 與 B15 端點歧義不受影響
- **WHEN** Y29 W18 source `69F` 的 `source_width` 改以正交方式量測，而 W18、W19 source `720` 的 outer faces、provisional axes、contact faces 與 source identities 均未改變
- **THEN** 系統 SHALL 維持 `69F`／`720` 的 `WALER_SOURCE_OVERLAP` 與相關 `WALER_OVERLAP_COMPETITION` 結果
- **AND** B15 source `71E` SHALL 維持對 W18／W19 的 `AMBIGUOUS_WALER_CONNECTION`
- **AND** B15 MUST NOT 因寬度修正而取得正式 endpoint choice

#### Scenario: 單線 Waler 不製造寬度
- **WHEN** Waler 只有一條可靠正式工程線，且來源幾何無法證明第二條外側 face
- **THEN** 系統 SHALL 維持既有 unknown-width semantics
- **AND** MUST NOT 為套用正交量測而複製、offset 或猜測另一條 supporting line

#### Scenario: HATCH 與 MLINE 等價 envelope 不產生回歸
- **WHEN** HATCH RC 或 MLINE Waler 已提供兩條幾何對齊、正交間距可靠的外側 faces
- **THEN** 其 `source_width` SHALL 與既有可靠幾何寬度保持等價
- **AND** HATCH RC material precedence 與 MLINE provenance SHALL 維持不變
