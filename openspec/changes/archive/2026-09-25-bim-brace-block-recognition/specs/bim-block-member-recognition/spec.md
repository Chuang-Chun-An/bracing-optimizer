# Spec Delta

## MODIFIED Requirements

### Requirement: BIM Block recognition SHALL be a restricted Strut source path

系統 SHALL 繼續僅將位於使用者指定 Strut role layer 的 root `INSERT` 納入既有 Strut BIM component-like recognition。root `INSERT` 的存在不得直接等同一支正式 Strut；系統 MUST 先判斷該 source scope 的整體 geometry 是否支持單一實體構件。

root layer classification SHALL 決定候選 role。遞迴展開後的 child entity layer（包含 Layer 0）只提供 geometry evidence，不得重新分類為其他 member role。

Brace role root `INSERT` SHALL 依 `bim-block-brace-recognition` capability 進入獨立、role-correct 的 BIM Brace path。Brace 可以重用共同 pure geometry primitives，但 MUST NOT 被偽裝成 Strut、不得取得 Strut-specific downstream semantics，也不得使 Waler、Continuous Wall、Column、Beam 或 CornerBrace 自動進入 BIM member path。

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

#### Scenario: Other roles remain outside BIM member path

- **WHEN** root `INSERT` 位於 Waler、Continuous Wall、Column、Beam 或 CornerBrace role layer
- **THEN** 系統 SHALL 維持該 role 的既有 recognition behavior
- **AND** SHALL NOT 自動套用 Strut 或 Brace BIM component-like path
