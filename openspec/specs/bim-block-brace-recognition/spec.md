# BIM Block Brace Recognition Specification

## Purpose

定義 DXF Import 如何將代表單一實體斜撐、但由 BIM 畫法切成多個 fragments 的 Brace root `INSERT`，安全重建為完整 Waler-to-Waler 工程構件，並在無法唯一判定時保留可審查的 blocking problem。

## Requirements

### Requirement: Brace BIM recognition SHALL use one root INSERT as one source scope

系統 SHALL 僅將位於使用者指定 Brace role layer、具有有效 root source identity 的 root `INSERT` 納入 Brace BIM component-like recognition。root layer classification SHALL 決定 Brace role；遞迴展開後的 child entity layer僅提供 geometry evidence，不得重新分類 member role。

一個 root `INSERT` 代表一支實體 Brace 是本 capability 的 source boundary，但 `INSERT` 身分本身不足以建立正式構件。系統 MUST 先確認該 root 的整體 geometry 唯一支持一支完整 Brace；成功時最多建立一支 formal Brace。

#### Scenario: Root Brace layer supplies the role

- **WHEN** root `INSERT` 位於已分類為 Brace 的 layer，且其 child LINE／POLYLINE 位於 Layer 0 或其他 child layer
- **THEN** 系統 SHALL 以 Brace role 評估整個 root source scope
- **AND** child layer SHALL NOT 使 geometry 改為 Strut、CornerBrace 或其他 role

#### Scenario: INSERT identity alone is insufficient

- **WHEN** Brace role root `INSERT` 的 geometry 無法支持單一主要方向、共同軸或一支完整構件
- **THEN** 系統 MUST NOT 僅因它是一個 `INSERT` 就建立 formal Brace

#### Scenario: One root creates at most one formal Brace

- **WHEN** 一個 Brace root source 成功通過 component-like recognition
- **THEN** 系統 SHALL 最多建立一支 formal Brace
- **AND** SHALL NOT 將同一 root 的局部 fragments 建立成多支 Brace

### Requirement: Formal Brace axis SHALL represent the whole source-supported member

對已通過 component-like eligibility 的 Brace root `INSERT`，系統 MUST 使用同一 root 的整體有效 geometry 推導唯一 recognition axis。共軸、方向與寬度相容且拓撲一致的 fragments SHALL 可共同支持完整 longitudinal extent；interior gaps 不得單獨構成拆件或截短理由。

Recognition axis MUST 涵蓋來源 geometry 可靠支持的完整構件 extent，不得只採用局部 closed outline、局部平行邊、最長單一 LINE、entity order 或 candidate order。BIM recognition 本身 MUST NOT 越過 terminal source evidence 無限制外插，或跨不同 root `INSERT` 合併 fragments。Recognition 成功後，獨立的 Brace-to-Waler connection 階段 MAY 依 `brace-axis-waler-extension` capability 沿已確認軸向，把 formal connection endpoint 延伸至唯一有限 Waler；該延伸不得反向改變 recognition winner、source-supported extent 或 root identity。

#### Scenario: Fragmented BIM Brace becomes one whole axis

- **WHEN** 同一 Brace root `INSERT` 內的多個 fragments 具有共同主要方向、共同工程軸、相容寬度與一致 topology，且整體 evidence 唯一支持一支完整 Brace
- **THEN** 系統 SHALL 重建一條涵蓋完整 source-supported extent 的 Brace 工程軸
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

### Requirement: Brace recognition outcome SHALL fail safely and deterministically

Brace BIM recognition SHALL 產生互斥的 `not applicable`、`recognized`、`failed` 或 `ambiguous` outcome。非 component-like 的一般 CAD `INSERT` SHALL 回到既有 Brace recognition；已確認為 component-like 但完整 extent 不可靠，或同一 root 支持多個不等價完整軸時，系統 MUST 建立 blocking recognition problem，且 MUST NOT 退回一般局部 candidate 強行成功。

在 WCS geometry、root source identity 與 Brace role 等價時，child entity order、LINE start/end direction、POLYLINE traversal direction或 candidate enumeration order的改變，不得改變 outcome 或等價的正式軸。

#### Scenario: Ordinary Brace block keeps general recognition

- **WHEN** 一個 Brace root `INSERT` 不具 component-like fragmented member evidence
- **THEN** 系統 SHALL 將同一未合併 root source 交回既有一般 Brace recognition

#### Scenario: Unreliable whole extent blocks local fallback

- **WHEN** source 已可判定為 component-like Brace，但無法可靠建立完整 longitudinal extent
- **THEN** 系統 SHALL 回報 blocking recognition failure
- **AND** SHALL NOT 以局部 fragment 建立較短 formal Brace

#### Scenario: Conflicting complete Brace axes are ambiguous

- **WHEN** 同一 root source 唯一性不足並支持兩條以上不等價的完整 Brace axes
- **THEN** 系統 SHALL 回報 blocking ambiguous recognition problem
- **AND** SHALL 建立零支 formal Brace

#### Scenario: Equivalent child order produces equivalent result

- **WHEN** Brace root 的 child entity order、segment direction 或 closed-path traversal 改變，但 WCS geometry 等價
- **THEN** 系統 SHALL 產生相同 outcome 與等價 normalized engineering axis

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

### Requirement: Brace BIM recognition SHALL preserve Review and persistence boundaries

成功候選、failure、ambiguity、ValidationMessage、ProblemRecord 與 ReviewItem SHALL 保留 Brace role 與最外層 root handle。Nested `INSERT` geometry MUST 沿用既有 insertion／rotation／scale 與 OCS-to-WCS boundary，且不得重複 transform。

Source exclusion／restore、manual endpoint replay、confirmation invalidation、Pause／Resume、source fingerprint 與 completed import SHALL 沿用既有 DXF Review lifecycle。BIM child geometry metadata MUST NOT 新增至 Project schema；完成 Review 後仍只透過既有 `DXFImportResult` 到 Brace Project row contract。

#### Scenario: Brace problem remains reviewable by root identity

- **WHEN** component-like Brace root 回報 failed 或 ambiguous
- **THEN** Review SHALL 以 Brace role 與 exact root handle 顯示 unresolved source
- **AND** import completion SHALL 在 blocking problem 未處理前保持不可完成

#### Scenario: Exclude and restore a Brace root

- **WHEN** 使用者排除後再恢復一個 BIM Brace source
- **THEN** original DXF SHALL 保持不變
- **AND** restore SHALL 以相同 Brace role + root handle 重新執行 recognition

#### Scenario: Completed Brace uses existing Project schema

- **WHEN** BIM Brace 已合法辨識、連接兩端 Waler 並完成 Review
- **THEN** 系統 SHALL 透過既有 Brace row contract 寫入 Project
- **AND** SHALL NOT 將 child fragments 或 BIM topology metadata寫入新的 Project 欄位

#### Scenario: Ordinary Brace and Strut behavior remains compatible

- **WHEN** DXF 使用一般 LINE、MLINE、完整 closed outline 或非 component-like Brace `INSERT`，或包含既有 BIM Strut source
- **THEN** 其既有 general Brace 或 BIM Strut behavior SHALL 保持不變
