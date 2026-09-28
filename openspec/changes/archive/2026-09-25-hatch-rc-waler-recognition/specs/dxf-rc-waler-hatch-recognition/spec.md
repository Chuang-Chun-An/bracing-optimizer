# Spec Delta

## Purpose

本 capability 定義 DXF Import 如何將使用者指定 Waler 圖層中的填充來源辨識為 RC 圍令，從 HATCH 封閉邊界建立可追溯的正式直線工程構件，並在幾何不可靠時留在既有 Review workflow，而不影響一般鋼圍令辨識。

## ADDED Requirements

### Requirement: Waler 圖層中的 HATCH 必須表示 RC 圍令來源

當 DXF `HATCH` 位於使用者指定為 Waler role 的圖層時，系統 MUST 將該填充來源的材料語意視為 RC，不得依 HATCH pattern 名稱、pattern angle、pattern scale 或 solid／patterned fill 的差異重新分類。此規則只適用於 Waler role；其他 role 與 ignored layer 的 HATCH MUST NOT 因本 capability 自動成為 RC Waler。

HATCH identity 本身只確立 RC 來源語意，不保證幾何足以建立正式構件；正式 Waler 仍必須通過本 capability 的 boundary 與唯一工程線條件。

#### Scenario: Patterned HATCH 自動判定為 RC
- **WHEN** 一個使用 pattern fill 的 HATCH 位於 Waler role layer，且其 boundary 可唯一支持一支正式直線 Waler
- **THEN** 系統 MUST 建立一支 RC Waler
- **AND** 不得要求 pattern 名稱存在於額外對照表

#### Scenario: Solid HATCH 自動判定為 RC
- **WHEN** 一個 solid fill HATCH 位於 Waler role layer，且其 boundary 可唯一支持一支正式直線 Waler
- **THEN** 系統 MUST 以與 patterned HATCH 相同的 RC 規則處理

#### Scenario: 非 Waler 圖層的 HATCH 不改變角色
- **WHEN** HATCH 位於 Strut、Brace、其他 engineering role、preview-only role 或 ignored layer
- **THEN** 本 capability MUST NOT 將其建立為 RC Waler
- **AND** 該 role 的既有 recognition behavior SHALL 保持不變

### Requirement: 正式 RC Waler 必須來自唯一可靠的 HATCH 外邊界

系統 MUST 以 HATCH 的 boundary path，而不是視覺填充線段，判斷正式構件幾何。可辨識的 HATCH MUST 具有唯一封閉外邊界，且該外邊界 MUST 支持單一、完整、非零長度的直線長條 Waler 範圍。內部孔洞或 detail boundary 不得被建立成額外 Waler；只有在它們不妨礙唯一外邊界與工程線判定時，才可保留為來源細節。

本 capability 不得因既有一般構件的 `maximum_component_width_mm` 而拒絕像 Y05 約 800 mm 寬、但填充邊界仍明確支持單一 RC Waler 的來源；亦不得為 RC Waler 引入任意固定寬度。幾何是否可用必須由封閉性、單一直線長方向、完整範圍與唯一性判定。

#### Scenario: 單一封閉長條填充建立一支 RC Waler
- **WHEN** Waler layer 中的一個 HATCH 具有唯一封閉長條外邊界，且可唯一建立一支完整直線 Waler
- **THEN** 系統 MUST 建立恰好一支 RC Waler candidate
- **AND** 工程範圍 MUST 涵蓋該 boundary 所支持的完整縱向 extent

#### Scenario: 800 mm RC 圍令不受一般 600 mm eligibility 限制
- **WHEN** 一個 HATCH boundary 可靠表示約 800 mm 寬的直線長條 RC 圍令
- **THEN** 系統 MUST NOT 只因其寬度大於既有 600 mm 一般構件 recognition setting 而拒絕辨識
- **AND** MUST NOT 修改該全域 setting 以影響其他 member recognition

#### Scenario: 內部孔洞不形成額外構件
- **WHEN** 一個有效外邊界內含不影響唯一完整工程線的 hole 或 detail boundary
- **THEN** 系統 MUST 只由外邊界建立一支 RC Waler
- **AND** MUST NOT 將內部 boundary 建立為其他 Waler

#### Scenario: 單一 HATCH 無法表示一支直線 Waler
- **WHEN** 一個 Waler HATCH 只有開放或無效 boundary、是一個需要拆段的 L 形外邊界、包含多個互不連續外邊界，或支持多個不等價的完整工程線
- **THEN** 系統 MUST NOT 自動拆件、任選一軸或建立正式 Waler
- **AND** MUST 產生指向該 HATCH source 的 blocking Review problem

### Requirement: 不同 HATCH 必須維持獨立構件來源

每一個有效 Waler HATCH MUST 以其自身 source identity 進行 recognition。兩個 HATCH 即使邊界相接、共用角點、方向垂直、彼此相鄰或外框 LINE 在 connectivity graph 中相連，系統也 MUST NOT 只因接觸而將它們合併為一支構件。幾何等價的 duplicate HATCH 可以沿用既有 duplicate handling，但不得以 DXF entity order 任意決定結果。

#### Scenario: 相接的水平與垂直 HATCH 維持兩支圍令
- **WHEN** 一個水平 RC Waler HATCH 與一個垂直 RC Waler HATCH 在端點相接
- **THEN** 系統 MUST 分別建立兩支 RC Waler
- **AND** MUST NOT 將兩者合併成一支 L 形來源

#### Scenario: HATCH source 順序不影響結果
- **WHEN** 等價 DXF 中 HATCH entity order 或 boundary traversal direction 改變
- **THEN** 正式 Waler 幾何、RC 材料分類與 source identity set MUST 維持等價

### Requirement: HATCH RC Waler 必須沿用既有正式 Waler 工程線語意

系統 MUST 從有效 HATCH 外邊界推導完整縱向軸、實際邊界寬度及兩條 longitudinal boundary evidence，並沿用既有 Waler support-side／inner-contact-face 選擇建立正式工程線。系統不得將填充視覺線、任意中心線或外側邊界直接當成正式接觸線。

若既有 Strut／Brace 幾何不足以唯一決定 inner-contact face，系統 MUST 沿用既有 Waler ambiguity／Review behavior，不得為 HATCH RC Waler建立第二套工程規則。

#### Scenario: 支撐側邊界成為正式工程線
- **WHEN** HATCH 外邊界可靠支持兩條縱向邊界，且既有 framing evidence 可唯一判定支撐接觸側
- **THEN** 正式 RC Waler geometry MUST 使用既有規則選出的 inner-contact boundary
- **AND** recognized center axis 與 source width SHALL 保留為既有 Review／contact workflow 所需的來源資訊

#### Scenario: 接觸側無法唯一判定
- **WHEN** HATCH 幾何有效，但既有 framing evidence 無法唯一判定正式接觸側
- **THEN** 系統 MUST 沿用既有 Waler Review／validation behavior
- **AND** MUST NOT 以 HATCH pattern direction 或 entity order 猜測接觸側

### Requirement: HATCH RC 分類必須優先於自動寬度材料辨識

成功由 Waler HATCH 建立的構件 MUST 在 DXF recognition base result 中取得正規化的 `material_spec = RC` 與可追溯的自動來源。既有依 `source_width` 對應 H 型鋼規格的自動材料辨識 MUST NOT 覆寫此 RC 分類。

既有 STEP4 人工材料修改及其 replay contract SHALL 保持不變；人工操作以前的自動 recognition base truth 仍 MUST 是 RC。轉入 Project 後，既有 `material_spec = RC` 的 Domain、Support 與 Waler Solver 行為 SHALL 由現有 contract 接續處理。

#### Scenario: 寬度也符合鋼材規格時仍為 RC
- **WHEN** HATCH RC Waler 的 source width 同時可匹配某個鋼材 material spec
- **THEN** 自動 recognition result 的 `material_spec` MUST 仍為 `RC`
- **AND** `material_spec_source` MUST 能區分此值來自 HATCH RC recognition

#### Scenario: Project row 保留 RC
- **WHEN** 使用者完成包含 HATCH RC Waler 的 DXF Review 並匯入 Main
- **THEN** 對應 Waler Project row MUST 具有 `material_spec = RC`
- **AND** 不得新增 Project schema 欄位

#### Scenario: 既有人工材料操作維持相容
- **WHEN** 使用者在既有 STEP4 workflow 明確修改已辨識 Waler 的材料規格
- **THEN** 系統 SHALL 沿用既有 manual override、confirmation invalidation 與 replay behavior
- **AND** 本 capability MUST NOT 新增第二套材料編輯 UI

### Requirement: HATCH 與等價外框 LINE 不得產生重複辨識

當有效或已進入 blocking Review 的 Waler HATCH boundary 與同圖層獨立 LINE／POLYLINE 幾何等價時，系統 MUST 將這些外框圖元視為該 HATCH source scope 的 boundary evidence，不得再由一般 LINE connectivity／parallel-pair recognition 建立重複正式 Waler或重複 unresolved item。此 suppression MUST 以幾何等價與 Waler role 為依據，不得依 handle 相鄰、entity order 或 HATCH associative reference 是否存在。

不屬於任何 HATCH boundary 的一般 Waler geometry SHALL 繼續使用既有 recognition behavior。

#### Scenario: 非關聯式 HATCH 仍可抑制等價外框 LINE
- **WHEN** HATCH 沒有 associative source references，但其 boundary 與獨立 Waler LINE 幾何唯一等價
- **THEN** 系統 MUST 以幾何比對將該 LINE 視為 HATCH boundary evidence
- **AND** MUST NOT 由該 LINE 再建立第二支 Waler 或第二個待修來源

#### Scenario: 無關 LINE 維持一般辨識
- **WHEN** Waler layer 的 LINE 不與任何 HATCH boundary 幾何等價
- **THEN** 該 LINE SHALL 繼續進入既有一般 Waler recognition
- **AND** HATCH path 不得吞掉鄰近但無關的 Steel Waler geometry

### Requirement: HATCH source 必須完整參與既有 Review 與來源生命週期

系統 MUST 保留 HATCH root handle、Waler role、source layer、entity type、WCS boundary geometry 與 recognition method，並以穩定且 deterministic 的 source identity 支援 ReviewItem、ProblemRecord、confirmation、Source Exclusion／Restore、manual override replay、pause／resume、fingerprint safety 及 completed import lifecycle。原始 DXF MUST 保持 immutable。

排除一個 HATCH RC Waler source 時，該 HATCH 及其被認定為等價 boundary evidence 的 LINE MUST 不得透過一般 recognition 重新出現；復原後 MUST 以相同來源語意重新辨識。這些 runtime／Review 資料 MUST 使用既有 persistence contract，不得新增 Project schema migration。

#### Scenario: 排除後不由外框 LINE 重新出現
- **WHEN** 使用者在 Review 排除一個 HATCH RC Waler source
- **THEN** 該正式 Waler 或 blocking item MUST 從 staged Review result 移除
- **AND** 等價外框 LINE MUST NOT 以另一個 source identity 重新產生同一構件

#### Scenario: 復原來源重新建立 RC Waler
- **WHEN** 使用者復原先前排除的有效 HATCH RC Waler source
- **THEN** 系統 MUST 重新建立其 RC candidate 與既有 derived Review state
- **AND** source identity MUST 仍可由原 HATCH handle 追溯

#### Scenario: HATCH recognition failure 保留可修復來源
- **WHEN** Waler HATCH 無法唯一建立合法直線工程線
- **THEN** 系統 MUST 建立包含 HATCH source handle、layer 與可理解原因的 unresolved ReviewItem
- **AND** MUST NOT fallback 至相同 boundary LINE 並製造非 RC formal Waler

### Requirement: 既有非 HATCH Waler 與下游 contract 必須保持相容

沒有 HATCH 語意的 Waler source MUST 維持目前一般 LINE、POLYLINE、MLINE、outline 與 parallel-edge recognition behavior。本 capability MUST NOT 修改 CandidatePoint、Waler contact adjustment 公式、connection／association 工程規則、Project row contract、Solver、Result lifecycle 或 DXF 原始 entity。

#### Scenario: 一般 Steel Waler regression
- **WHEN** Waler layer 僅包含既有可辨識 LINE、POLYLINE 或 MLINE，且沒有相關 HATCH
- **THEN** 正式 Waler geometry、material recognition、Review behavior 與 Project conversion SHALL 維持既有結果

#### Scenario: Recognition failure 不提交 Project
- **WHEN** HATCH Waler 產生 blocking Review problem
- **THEN** 使用者 MUST 無法以該 unresolved source 完成正式 DXF import
- **AND** 既有 ProjectDataModel 與 committed Solver result MUST 保持不變，直到使用者在 staged Review 中排除、修正來源後重辨識或完成其他既有合法處置

### Requirement: Y05 RC Waler 案例必須被穩定辨識

Y05 中 HATCH `1647` 與 `1650` 的等價幾何 MUST 分別表示相接的水平與垂直 RC Waler；HATCH `E65` 與 `163D` 的等價幾何 MUST 遵循相同規則。結果不得再將各對 HATCH 周圍的 LINE 合併成單一 L 形 unresolved Waler。

#### Scenario: Y05 1647 與 1650 分別建立 RC Waler
- **WHEN** 系統辨識與 Y05 `1647`、`1650` 等價的兩個 Waler HATCH boundaries
- **THEN** MUST 建立兩支互相獨立且 `material_spec = RC` 的 Waler
- **AND** 一支 MUST 使用完整水平 extent，另一支 MUST 使用完整垂直 extent
- **AND** MUST NOT 保留由其等價外框 LINE 形成的 `待修-1648` L 形辨識問題

#### Scenario: Y05 E65 與 163D 遵循相同行為
- **WHEN** 系統辨識與 Y05 `E65`、`163D` 等價的 Waler HATCH boundaries
- **THEN** MUST 分別建立其水平與垂直 RC Waler
- **AND** MUST NOT 保留由其等價外框 LINE 形成的單一 L 形 unresolved source
