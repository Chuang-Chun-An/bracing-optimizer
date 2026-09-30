# BIM Block Brace Recognition Delta Specification

## 閱讀導航

### P0｜現在必讀

- 「Component-like Brace body evidence SHALL require whole-source support」：決定 root 可否回到 general route 的分類邊界。
- 「Brace 實體寬度 SHALL 通過正式 hard gate」：所有自動 body-derived Brace 共用的必要工程限制、closed-outline 量測方式與 `250.0 mm` 邊界。
- 「Component-like Brace SHALL 依 whole-source center authority 選軸」：Y05 B8 中心偏移的直接修正規格。
- 「Brace recognition outcome SHALL fail safely and deterministically」：禁止過窄或不可靠來源藉 fallback 成功。

### P1｜實作前閱讀

- 主規格 `openspec/specs/bim-block-brace-recognition/spec.md` 的完整 source scope、whole-axis 與 Waler connection requirements。
- 本 change 的 `design.md`：候選產生、authority tier、寬度量測與 terminal outcome 的落點。
- 本 change 的 `tasks.md`：實作與測試順序。

### P2｜需要時再讀

- `openspec/specs/bim-block-member-recognition/spec.md`：只有重用 Strut whole-root 幾何方法時再讀；本 change 不修改 Strut 行為。
- `openspec/specs/dxf-corner-brace-occluded-rail-recognition/spec.md`：只用來核對 CornerBrace 既有 `> 250 mm` 邊界，並非本規格的行為來源。
- `openspec/specs/brace-axis-waler-extension/spec.md`：只在 connection regression 時閱讀；其中 `600 mm` 軸向延伸不是 Brace 實體寬度限制。

## ADDED Requirements

### Requirement: Component-like Brace body evidence SHALL require whole-source support

同一 Brace-role root `INSERT` 只有在 whole-source geometry 已足以支持「這是一個具有實體 body／外包絡的構件」時，系統 SHALL 判定 component-like body evidence 成立。成立證據 SHALL 至少能由完整或 connected body topology、共同支持主要 longitudinal corridor 的 whole-root longitudinal bands，或其他同時建立主要方向、可靠 terminal extent 與 body envelope 的既有 component-like classification evidence 提供。

單一局部平行線組、只覆蓋構件局部長度的短 detail、branch line、flange／web 局部內部線、孔洞邊，或無法共同支持 whole-root main corridor 的零散 fragments，MUST NOT 單獨使 root 成為 component-like。Classification SHALL 只依 normalized whole-source geometry 與 root identity 決定；child order、handle order 或 candidate enumeration order 不得改變結果。

沒有足夠 component-like body evidence 時，component-like recognizer SHALL 回傳 `not_applicable`，router SHALL 依既有 contract 交回 general Brace recognition。Evidence 一旦成立，後續候選不合法或不唯一時 MUST 回傳 `failed` 或 `ambiguous`，不得改回 `not_applicable`。

#### Scenario: 局部 detail 不足以建立 component-like body evidence

- **WHEN** 同一 Brace root 只有局部平行線、短 detail、branch、孔洞邊或零散內部線
- **AND** 這些來源無法共同支持 whole-root main corridor、可靠 terminal extent 與 body envelope
- **THEN** component-like recognizer SHALL NOT 只因存在兩條平行線就將 root 判為 component-like
- **AND** SHALL 回傳 `not_applicable`，由 router 依既有 contract 交回 general Brace recognition

#### Scenario: Whole-source body evidence establishes component-like classification

- **WHEN** 同一 Brace root 的完整或 connected topology，或 whole-root longitudinal bands，共同支持主要方向、主要 longitudinal corridor、可靠 terminal extent 與 body envelope
- **THEN** 系統 SHALL 將該 root 判為具有 component-like body evidence
- **AND** 後續 candidate outcome MUST 遵守 terminal `recognized`、`failed` 或 `ambiguous` contract

#### Scenario: Component-like classification is order independent

- **WHEN** Brace root 的 WCS geometry 與 root identity 相同，但 child order、handle order、LINE direction 或 candidate enumeration order 改變
- **THEN** component-like body-evidence classification SHALL 保持相同

### Requirement: Brace 實體寬度 SHALL 通過正式 hard gate

系統 SHALL 將「自動 Brace 候選可由來源 body geometry 可靠量得的正交實體寬度必須嚴格 `> 250.0 mm`」視為 Engineering Hard Constraint。此限制 SHALL 適用於 component-like root `INSERT`、MLINE、closed outline 與 parallel-edge／rail-pair 等所有 body-derived 自動候選；`= 250.0 mm` 與 `< 250.0 mm` 均不合法。

寬度 SHALL 由支持候選工程軸的合格外緣之正交距離計算，不得以 block name、BIM family、材料庫存、標註文字或既有 Waler context 代替幾何證據。最大 component width、LINE merge tolerance、Brace direct connection tolerance 與 axis-extension distance 均為不同語意，不得代替或放寬本 hard gate。

Closed body outline 的 Brace body width SHALL 由 engineering axis 相對兩側、方向與主要 longitudinal direction 相容、對主要 longitudinal corridor 具有足夠 coverage，且共同支持同一 source-supported body envelope 的兩個 outer supporting sides 之正交 separation 決定。系統 MUST NOT 使用 axis-aligned bounding-box width、rotated bounding box 的短邊（除非其兩側已另行證明為合格 supporting sides）、斜端板或端板平均長度、任意最遠頂點距離、局部突出造成的最大外距、短區段內部邊、軸向端點距離或 longitudinal gap 代替 body width。

若 closed outline 無法唯一建立這兩個主要 supporting sides，該 topology candidate 的 width SHALL 視為 unreliable；系統 MUST NOT 猜測或補足寬度，並 SHALL 繼續依 authority pipeline 評估 lower-tier whole-root evidence。

純單 LINE 或其他明確 centerline-only 來源沒有可量測 body width 時，寬度 SHALL 視為 unknown，而不是零寬或不合法；這類來源 SHALL 保留既有一般 Brace 辨識與後續 validation。系統 MUST NOT 為通過本 gate 而猜測未知寬度。

#### Scenario: Width greater than 250 mm is eligible

- **WHEN** 自動 Brace body candidate 的可靠正交實體寬度為 `300.0 mm`
- **THEN** 該候選 SHALL 通過寬度 hard gate
- **AND** 是否正式成立仍 SHALL 由 center authority、唯一性與既有 connection／validation 規則決定

#### Scenario: Width equal to 250 mm is rejected

- **WHEN** 自動 Brace body candidate 的可靠正交實體寬度恰為 `250.0 mm`
- **THEN** 系統 MUST 將該候選判為不符合 Engineering Hard Constraint
- **AND** MUST NOT 以 inclusive comparison 將其接受

#### Scenario: Width below 250 mm is rejected

- **WHEN** 自動 Brace body candidate 的可靠正交實體寬度小於 `250.0 mm`
- **THEN** 系統 MUST 拒絕該候選
- **AND** MUST NOT 因其長度、slenderness、overlap 或 evidence score 較高而覆寫 hard gate

#### Scenario: General body-derived Brace uses the same gate

- **WHEN** 一般 Brace recognition 從 MLINE、closed outline 或 parallel edges 量得 body width
- **THEN** 系統 SHALL 在建立 formal Brace 前套用相同的嚴格 `> 250.0 mm` hard gate
- **AND** MUST NOT 僅對 component-like root `INSERT` 套用此限制

#### Scenario: Supporting outer edges define perpendicular width

- **WHEN** 一組合格 outer edges 共同支持同一 Brace corridor 與工程軸
- **THEN** 系統 SHALL 以兩外緣相對工程軸的正交 separation 作為 body width
- **AND** SHALL NOT 以端點距離、軸向 gap 或任一短 detail 的間距作為 body width

#### Scenario: Closed outline width uses primary longitudinal supporting sides

- **WHEN** 一個 closed body outline 可唯一識別 engineering axis 兩側、共同支持主要 longitudinal corridor 的 outer supporting sides
- **THEN** 系統 SHALL 使用兩側 supporting sides 的正交 separation 作為 Brace body width
- **AND** MUST NOT 使用斜端板長度、bounding-box width 或最遠頂點距離代替

#### Scenario: Irregular outline without unique supporting sides has unreliable width

- **WHEN** closed outline 含有斜端板、突出 detail、branch 或不規則邊界
- **AND** 無法唯一識別 engineering axis 兩側的主要 longitudinal supporting sides
- **THEN** 該 topology candidate 的 body width SHALL 視為 unreliable
- **AND** 系統 MUST NOT 以 bounding box、最遠點或端板長度補足
- **AND** SHALL 繼續依 authority pipeline 評估 lower-tier 的合法 whole-root evidence

#### Scenario: Centerline-only Brace keeps unknown width

- **WHEN** Brace source 是單一 LINE 或已明確表示中心線，且沒有可可靠量測的 body envelope
- **THEN** 系統 SHALL 保留 unknown width 與既有中心線辨識行為
- **AND** SHALL NOT 將 unknown width 當成 `0 mm` 後依本 hard gate 拒絕

#### Scenario: Metadata cannot manufacture a passing width

- **WHEN** source 的 block name、family 名稱、材料文字或庫存資料暗示寬度大於 `250.0 mm`，但幾何只能量得不合法寬度或無法量得寬度
- **THEN** 系統 MUST NOT 以該 metadata 建立、取代或放寬自動 body width

### Requirement: Component-like Brace SHALL 依 whole-source center authority 選軸

對已判定為 component-like 的 Brace root `INSERT`，系統 SHALL 分別列舉三個 authority tiers 的全部候選：第一，完整且可驗證的 closed body outline（`TOPOLOGY`）；第二，由整個 root 的可靠 terminal extent 與外側 supporting faces 建立的 whole-root outer-envelope（`WHOLE_ROOT_ENVELOPE`）；第三，local rail-pair fallback（`LOCAL_RAIL_PAIR`）。

Authority tier 只有在候選通過該 tier 的完整性、whole-source support、可靠 extent、可靠 width measurement 與 Brace body-width hard gate 後才成立。系統 SHALL 先移除未通過 `width > 250.0 mm` 或上述來源支持要求的候選，再找出仍有一個或多個合法候選的最高 authority tier；只可在該最高合法 tier 內執行 normalized geometry grouping、幾何等價合併、deterministic uniqueness judgment 與 ambiguity judgment。

較高 tier 只有不合法候選時，系統 SHALL 繼續評估下一 tier，不得因 authority 較高而立即失敗。最高合法 tier 只有一個 normalized engineering axis 時，系統 SHALL 採用該軸，且較低 tier MUST NOT 以分數、長度或 evidence ratio 覆寫。最高合法 tier 有多個不等價完整 axes 時，系統 SHALL 回報 blocking `ambiguous`，不得降到較低 tier 尋找單一解。只有全部 tiers 都沒有合法候選時，系統才 SHALL 回報 blocking `failed`。

Whole-root outer-envelope 的兩側外緣 SHALL 共同支持主要 corridor 與可靠 terminal extent；短 detail、內部 flange／web 線、branch rail、孔洞邊或只覆蓋局部長度的線 MUST NOT 單獨成為 outer face。已存在 component-like body evidence但全部 tiers 均無合法候選時，不得降級至一般 body recognition。

#### Scenario: Complete outline has highest authority

- **WHEN** 同一 Brace root 同時提供唯一的完整合法 body outline 與一個或多個局部 rail pairs
- **THEN** 系統 SHALL 使用完整 outline 的中心軸與 source-supported extent
- **AND** MUST NOT 以局部 rail pair 改寫該中心

#### Scenario: Invalid topology candidate does not block a legal envelope

- **WHEN** `TOPOLOGY` tier 只有 `160.0 mm` 或 width unreliable 的不合法候選
- **AND** `WHOLE_ROOT_ENVELOPE` tier 有唯一、完整且寬度為 `300.0 mm` 的合法候選
- **THEN** 系統 SHALL 繼續評估並採用 `300.0 mm` whole-root envelope candidate
- **AND** MUST NOT 因 `TOPOLOGY` authority 較高而直接失敗

#### Scenario: Unique legal topology candidate excludes lower tiers

- **WHEN** `TOPOLOGY` tier 有唯一、完整且寬度為 `300.0 mm` 的合法候選
- **AND** `WHOLE_ROOT_ENVELOPE` 或 `LOCAL_RAIL_PAIR` 也有候選
- **THEN** 系統 SHALL 採用 topology candidate
- **AND** lower-tier candidate MUST NOT 以分數、長度或 evidence ratio 覆寫

#### Scenario: Whole-root outer-envelope outranks local rails

- **WHEN** root 沒有可用的完整 outline，但可靠 terminal extent 與兩側 supporting outer faces 唯一形成合法 whole-root outer-envelope
- **THEN** 系統 SHALL 以 outer-envelope 的兩外側面中線建立 Brace axis
- **AND** SHALL 在任何 local rail-pair fallback 之前採用該候選

#### Scenario: Internal detail is not an outer face

- **WHEN** 一條線只覆蓋主要 corridor 的局部長度，或其 topology 顯示為 flange、web、branch、孔洞或其他內部 detail
- **THEN** 系統 MUST NOT 將該線與外緣配對為 whole-root outer-envelope
- **AND** 該 detail 的局部高 evidence score MUST NOT 改變 outer-envelope 中心

#### Scenario: Local rail pair is the final fallback

- **WHEN** component-like Brace 沒有合格完整 outline 或 whole-root outer-envelope，但存在唯一、完整且寬度嚴格大於 `250.0 mm` 的可靠 local rail pair
- **THEN** 系統 SHALL 以該 pair 建立 normalized engineering axis
- **AND** SHALL 保留 root source identity 與完整 source-supported extent

#### Scenario: Highest authority tier remains ambiguous

- **WHEN** 同一最高合法 authority tier 支持兩個以上不等價且均通過 hard gate 的完整 Brace axes
- **THEN** 系統 SHALL 回報 blocking `ambiguous`
- **AND** MUST NOT 降到較低 tier 任選一軸

#### Scenario: All authority tiers without a legal candidate fail

- **WHEN** component-like Brace 的 `TOPOLOGY`、`WHOLE_ROOT_ENVELOPE` 與 `LOCAL_RAIL_PAIR` tiers 都沒有通過完整性、whole-source support、可靠 extent、可靠 width 與 `> 250.0 mm` gate 的候選
- **THEN** 系統 SHALL 回報 blocking `failed`
- **AND** MUST NOT 回到 general body recognition

#### Scenario: Width gate precedes authority selection and scoring

- **WHEN** 某 tier 同時含有 `160.0 mm` 的高分候選與 `300.0 mm` 的合法候選
- **THEN** 系統 SHALL 在 authority selection 與 scoring 前移除 `160.0 mm` 候選
- **AND** 過窄候選 MUST NOT 遮蔽或擊敗 `300.0 mm` 合法候選

#### Scenario: Y05 B8 uses the whole-root envelope center

- **WHEN** Y05 B8 root `DD9` 同時含有約 `160.015 mm` 的局部 rail pair 與約 `300 mm` 的可靠 whole-root outer-envelope
- **THEN** 系統 MUST 拒絕過窄的局部 pair 並採用 whole-root outer-envelope center
- **AND** normalized axis SHALL 約為 `(-37000, -18368.859)` 至 `(-32168.859, -23200)`，不得沿用約 `(-37000, -18259.258)` 至 `(-32059.258, -23200)` 的偏移軸

## MODIFIED Requirements

### Requirement: Brace recognition outcome SHALL fail safely and deterministically

Brace BIM recognition SHALL 產生互斥的 `not_applicable`、`recognized`、`failed` 或 `ambiguous` outcome。只有 whole-source geometry 不足以成立 component-like body evidence 時，recognizer 才 SHALL 回傳 `not_applicable`，並由 router 交回既有 Brace recognition；一般 route 對任何可量測的 body-derived candidate 仍 SHALL 套用相同寬度 hard gate。

Component-like body evidence 一旦成立，recognizer MUST 完成全部 authority tiers 的合法候選評估：唯一合法 candidate 回傳 `recognized`；全部 tiers 無合法候選、完整 extent 或 width 不可靠時回傳 blocking `failed`；最高合法 authority tier 支持多個不等價完整軸時回傳 blocking `ambiguous`。上述情況 MUST NOT 改回 `not_applicable`，且 MUST NOT 退回一般局部 candidate 強行成功。

在 WCS geometry、root source identity 與 Brace role 等價時，child entity order、LINE start/end direction、POLYLINE traversal direction 或 candidate enumeration order 的改變，不得改變 outcome 或等價的正式軸。寬度 gate 與 authority selection 的 failure／ambiguity SHALL 保留 exact root identity 供 Review 處理。

#### Scenario: Ordinary Brace block keeps general recognition

- **WHEN** 一個 Brace root `INSERT` 不具 component-like fragmented member evidence
- **THEN** 系統 SHALL 將同一未合併 root source 交回既有一般 Brace recognition
- **AND** 其可量測 body-derived candidate SHALL 仍通過嚴格 `> 250.0 mm` hard gate 才能成立

#### Scenario: Local parallel detail alone keeps component route not applicable

- **WHEN** 一個普通 Brace root `INSERT` 內剛好存在局部平行 detail，但 whole-source geometry 不足以支持主要 corridor、可靠 terminal extent 與 body envelope
- **THEN** component-like recognizer SHALL 回傳 `not_applicable`
- **AND** child order、handle order 或 candidate order 的改變不得使它成為 component-like

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

#### Scenario: Invalid component body cannot bypass through general fallback

- **WHEN** whole-source geometry 已足以證明該 root 是 component-like Brace body
- **AND** 後續候選全部未通過 body-width hard gate、完整 extent 或 width 不可靠，或最高合法 tier 的中心不唯一
- **THEN** 系統 SHALL 回報 blocking `failed` 或 `ambiguous`
- **AND** MUST NOT 改回 `not_applicable`
- **AND** MUST NOT 將相同 root 重新解讀為一般 outline、parallel-pair 或單一 fragment Brace

### Requirement: Brace BIM recognition SHALL preserve Review and persistence boundaries

成功候選、failure、ambiguity、ValidationMessage、ProblemRecord 與 ReviewItem SHALL 保留 Brace role 與最外層 root handle。Nested `INSERT` geometry MUST 沿用既有 insertion／rotation／scale 與 OCS-to-WCS boundary，且不得重複 transform。

Source exclusion／restore、manual endpoint replay、confirmation invalidation、Pause／Resume、source fingerprint 與 completed import SHALL 沿用既有 DXF Review lifecycle。BIM child geometry metadata MUST NOT 新增至 Project schema；完成 Review 後仍只透過既有 `DXFImportResult` 到 Brace Project row contract。寬度 hard-gate failure 與 center-authority ambiguity SHALL 使用既有 reviewable problem pipeline，不得另建不可追蹤的旁路狀態。

#### Scenario: Brace problem remains reviewable by root identity

- **WHEN** component-like Brace root 回報 failed 或 ambiguous，包括寬度未通過或中心 authority 無法唯一決定
- **THEN** Review SHALL 以 Brace role 與 exact root handle 顯示 unresolved source
- **AND** import completion SHALL 在 blocking problem 未處理前保持不可完成

#### Scenario: Exclude and restore a Brace root

- **WHEN** 使用者排除後再恢復一個 BIM Brace source
- **THEN** original DXF SHALL 保持不變
- **AND** restore SHALL 以相同 Brace role + root handle 重新執行 recognition

#### Scenario: Completed Brace uses existing Project schema

- **WHEN** BIM Brace 已合法辨識、連接兩端 Waler 並完成 Review
- **THEN** 系統 SHALL 透過既有 Brace row contract 寫入 Project
- **AND** SHALL NOT 將 child fragments、BIM topology metadata 或新的 width-state 欄位寫入 Project schema

#### Scenario: Ordinary Brace and Strut behavior remains compatible

- **WHEN** DXF 使用單一 LINE／明確 centerline Brace，或包含既有 BIM Strut source
- **THEN** 其既有 general Brace 或 BIM Strut behavior SHALL 保持不變
- **AND** unknown Brace width SHALL NOT 因本 change 單獨成為 blocking problem

#### Scenario: Body-derived Brace compatibility is conditional on legal width

- **WHEN** DXF 使用 MLINE、完整 closed outline、parallel edges 或非 component-like Brace `INSERT` 建立可量測 body width 的一般 Brace candidate
- **THEN** 其既有 recognition 流程 SHALL 保持不變，唯 candidate 必須先嚴格通過 `> 250.0 mm` hard gate

