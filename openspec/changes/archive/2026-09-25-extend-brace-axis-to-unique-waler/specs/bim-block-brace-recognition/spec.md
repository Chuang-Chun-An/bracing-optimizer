# Spec Delta

## MODIFIED Requirements

### Requirement: Formal Brace axis SHALL represent the whole source-supported member

對已通過 component-like eligibility 的 Brace root `INSERT`，系統 MUST 使用同一 root 的整體有效 geometry 推導唯一 recognition axis。共軸、方向與寬度相容且拓撲一致的 fragments SHALL 可共同支持完整 longitudinal extent；interior gaps 不得單獨構成拆件或截短理由。

Recognition axis MUST 涵蓋來源 geometry 可靠支持的完整構件 extent，不得只採用局部 closed outline、局部平行邊、最長單一 LINE、entity order 或 candidate order。BIM recognition 本身 MUST NOT 越過 terminal source evidence 無限制外插，或跨不同 root `INSERT` 合併 fragments。Recognition 成功後，獨立的 Brace-to-Waler connection 階段 MAY 依 `brace-axis-waler-extension` capability 沿已確認軸向，把 formal connection endpoint 延伸至唯一有限 Waler；該延伸不得反向改變 recognition winner、source-supported extent 或 root identity。

#### Scenario: Fragmented BIM Brace becomes one whole axis

- **WHEN** 同一 Brace root `INSERT` 內的多個 fragments 具有共同主要方向、共同工程軸、相容寬度與一致 topology，且整體 evidence 唯一支持一支完整 Brace
- **THEN** 系統 SHALL 重建一條涵蓋完整 source-supported extent 的 Brace recognition axis
- **AND** SHALL NOT 只輸出其中一個 fragment 的局部短軸

#### Scenario: Interior gaps do not split a supported Brace

- **WHEN** 同一 root 內對齊 fragments 之間有 BIM 投影或遮蔽造成的 interior gaps，但 terminal extent 與共同軸仍有可靠來源 evidence
- **THEN** 系統 SHALL 以一支完整 Brace 解讀該 source
- **AND** SHALL NOT 只因 gap 大於一般 LINE merge tolerance 而拆件

#### Scenario: Different roots remain separate

- **WHEN** 兩個 Brace root `INSERT` 的 fragments 共線、接近或寬度相同
- **THEN** 系統 MUST 以各自 root handle 建立獨立 source scope
- **AND** MUST NOT 跨 root 合併為一支 Brace

#### Scenario: Terminal source evidence limits the axis

- **WHEN** Brace fragments 只可靠支持一段有限 longitudinal extent
- **THEN** BIM recognition MUST NOT 為了碰到 Waler 而改寫或擴大 source-supported recognition axis
- **AND** 只有後續 connection 階段符合 `brace-axis-waler-extension` 的唯一有限 Waler contract 時，formal endpoint 才可沿同一軸向延伸

### Requirement: Recognized Brace SHALL use the existing Waler-to-Waler connection contract

成功的 whole-axis candidate SHALL 進入 Brace endpoint-to-Waler connection 與 validation 流程。合法 formal Brace 的兩端 MUST 各連接一支不同且可識別的有限 Waler；`FromWaler`、`ToWaler` 與 snapped／extended endpoints SHALL 由該流程建立。

系統 SHALL 優先沿用既有 endpoint tolerance 內的 direct connection。未連接端 MAY 依 `brace-axis-waler-extension` capability，沿 reliable recognition axis 的 outward ray 連到唯一有限 Waler intersection。此行為不是放寬 direct connection tolerance，也不是 BIM recognition 外插：系統 MUST NOT 以 Waler context 選擇 recognition winner、猜測缺失 Waler、使用 Waler 無限延長線、改變 Brace 方向或在 ambiguous 時任選。fragment recognition 成功與 Waler connection 成功 MUST 保持可區分。

#### Scenario: Whole Brace connects to two Walers

- **WHEN** recognized whole Brace 的兩端透過 direct connection 或合法 axis extension 各自唯一連接不同有限 Waler
- **THEN** 系統 SHALL 建立 `FromWaler` 與 `ToWaler` 並採用對應交點
- **AND** formal Brace SHALL 進入既有 Project conversion

#### Scenario: Only one endpoint connects

- **WHEN** whole-axis recognition 成功，但 direct connection 與合法 axis extension 後仍只有一端可唯一連接 Waler
- **THEN** 系統 SHALL 保留 recognition 與 connection failure 的可診斷區別
- **AND** SHALL 依既有 Brace one-end-not-connected validation 阻擋完成

#### Scenario: Missing Waler is not repaired by recognition

- **WHEN** source-supported Brace 軸的 outward ray 找不到有限 Waler intersection，或最近交點無法唯一對應一支 Waler
- **THEN** 系統 MUST NOT 藉由 Waler 無限延長線、側向吸附、entity order 或任意 candidate ordering 建立假連接

#### Scenario: Waler context does not change recognition outcome

- **WHEN** 相同 BIM Brace source geometry 分別出現在不同 Waler context
- **THEN** component-like status、recognition axis、representative width 與 root provenance SHALL 保持相同
- **AND** 只有下游 connection outcome 與 formal endpoints MAY 因合法有限 Waler intersections 不同而改變
