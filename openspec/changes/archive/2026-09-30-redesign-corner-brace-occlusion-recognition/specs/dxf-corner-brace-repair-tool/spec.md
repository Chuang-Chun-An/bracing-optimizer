# Spec Delta

## 閱讀導航

- **現在必讀**：「每個修補候選必須具有有效的目標工程接點」與「Unresolved 來源建立正式 CornerBrace 必須通過額外門檻」。
- **實作前閱讀**：「修補必須先預覽再明確採用」，確認 explicit selection、revision revalidation 與 rollback。
- **需要時再讀**：「自動辨識與非目標系統維持既有行為」；驗證 compatibility 時閱讀。既有 reference-template 細節未被取代。

## MODIFIED Requirements

### Requirement: 每個修補候選必須具有有效的目標工程接點

每一個可預覽的修補候選 MUST 明確標示為既有 `reference_template` 或新的 `body_relationship_selection`，並唯一綁定一支 target Waler 與一支 target Strut。兩種 mode 的 evidence 與 endpoint authority不得混用。

`reference_template` candidate MUST 維持既有 automatic primary、local-frame transfer、finite endpoint 與 validation contract。

`body_relationship_selection` candidate 只有在 automatic recognition 已建立唯一 `BodyGeometryEvidence`，且失敗原因僅為該 body 有多組 hard-valid `BodyRelationshipAssessment` 時才可建立。每個 candidate MUST：

- 引用同一 unique body signature、selected RailTracks 與 midline；
- 綁定自己的一組 exact active Waler／Strut source identities；
- 使用該 assessment 的 finite intersections 作為 endpoints；
- 確認兩條 rail coverage 各自 `>=50%`；
- 確認 Waler 與 Strut 每端 outward extension 各自 `<=600 mm`；
- 保留 complete／occluded classification、gaps／occluders與 structured validation；
- 通過 duplicate、CornerBraceConnection與既有 CornerBrace validation。

該 mode 不需要 template，不得改選 rails、重新推導 body、使用無限延長線、以 proximity 決定 relationship、解析 diagnostic message 或將 body ambiguity 包裝成可選 candidate。

#### Scenario: Reference-template 目標接點有效
- **WHEN** reference-template candidate 依既有 contract 產生有效 finite transferred endpoints 並通過 validation
- **THEN** 系統 SHALL 允許該 candidate 進入 Preview

#### Scenario: Body relationship candidate 使用同一 centerline
- **WHEN** unique body 有多組 hard-valid assessments
- **THEN** planner SHALL 為每組 assessment 建立綁定 exact identities 的 candidate
- **AND** 每個 candidate SHALL 使用同一 body midline 與自己的 finite endpoints

#### Scenario: Body relationship candidate 不要求 template
- **WHEN** candidate mode 是 `body_relationship_selection`
- **THEN** 系統 SHALL 以 unique `BodyGeometryEvidence` 作為本體 authority
- **AND** MUST NOT 因缺少 template 而拒絕或執行 template transfer

#### Scenario: Coverage 不足不得建立 candidate
- **WHEN** 某 assessment 任一 rail coverage 低於 `50%`
- **THEN** planner MUST NOT 將它建立為可 Apply candidate
- **AND** 合法 extension MUST NOT 補償 coverage 不足

#### Scenario: Extension 超限不得建立 candidate
- **WHEN** 某 assessment 任一端 extension 大於 `600 mm`
- **THEN** planner MUST NOT 將它建立為可 Apply candidate
- **AND** 合法 coverage MUST NOT 補償 extension 超限

#### Scenario: Body 多解不得建立 relationship candidate
- **WHEN** automatic result 有零個 body 或多個非等價 body solutions
- **THEN** 系統 MUST NOT 建立 `body_relationship_selection` candidates

#### Scenario: 不同 identities 必須分開呈現
- **WHEN** 幾何重合的不同 Waler sources 各自形成 hard-valid assessment
- **THEN** planner SHALL 建立不同 candidate IDs
- **AND** MUST NOT 合併為 canonical Waler

#### Scenario: 目標 Waler 與 Strut 接點有效
- **WHEN** candidate明確綁定target identities且兩個endpoints位於其finite engineering lines並通過對應mode validation
- **THEN** 系統 SHALL 允許candidate進入Preview

#### Scenario: 同側局部配置移植
- **WHEN** reference-template candidate依既有local frame完成同側transfer且endpoints有效
- **THEN** 系統 SHALL 保留既有eligible behavior與result length計算

#### Scenario: 對側局部配置鏡射
- **WHEN** reference-template candidate依既有contract完成對側mirror且endpoints有效
- **THEN** 系統 SHALL 保留既有eligible behavior

#### Scenario: 任一接點不在有限構件上
- **WHEN** 任一candidate endpoint不在綁定的finite Waler或Strut engineering line
- **THEN** 系統 MUST 拒絕candidate，不得使用infinite extension或nearest snap補足

#### Scenario: 多組 Waler 或 Strut 關係皆可成立
- **WHEN** unique body有多組分別hard-valid的relationships
- **THEN** planner SHALL 以不同candidate IDs呈現每組relationship
- **AND** MUST NOT 在使用者選擇前採用任一組

#### Scenario: Unresolved create 不得把 relationship 歸屬交給使用者
- **WHEN** unresolved source沒有unique body，而reference-template hypotheses指向多組relationships
- **THEN** 系統 MUST 維持既有blocking behavior
- **AND** MUST NOT 包裝成 `body_relationship_selection` candidates

### Requirement: 修補必須先預覽再明確採用

系統 SHALL 在修改 live Review state 前，以 Preview 顯示 candidate mode、unique body axis、target Waler／Strut source identities、finite endpoints、result length、每軌 coverage、每端 extension、complete／occluded classification與 validation。`reference_template` 另顯示既有 template-transfer evidence；`body_relationship_selection` SHALL 顯示「本體已辨識，請選擇工程關係」或等價說明。

即使只有一個 eligible candidate，也 MUST 由使用者明確 Apply。多候選時 MUST 以穩定 candidate ID 要求使用者選擇；未選時 Apply disabled。Preview 開啟、候選改選、取消或關閉 MUST 零副作用，不得以格式化字串識別候選或自動提交。

Apply 前 MUST 以 current revision、body signature、active source identities及完整 assessment gates 重驗。任何 state、identity、finite intersection、coverage、gap evidence、extension或 validation 改變，candidate MUST 視為 stale 或 invalid。

#### Scenario: 唯一候選仍需確認
- **WHEN** repair plan 只有一個 eligible candidate
- **THEN** Preview SHALL 顯示完整 evidence
- **AND** 只有使用者明確 Apply 後才可提交

#### Scenario: Relationship ambiguity 顯示多組候選
- **WHEN** unique body 有多組 hard-valid assessments
- **THEN** Preview SHALL 分別顯示每組 identities、endpoints、coverage、extensions與 validation
- **AND** Apply SHALL 在使用者選擇前維持 disabled

#### Scenario: 使用者選擇其中一組
- **WHEN** 使用者依 candidate ID 選定一組並 Apply
- **THEN** 系統 SHALL 只提交該 candidate 的 relationship、endpoints與 provenance
- **AND** MUST NOT 混用其他 candidate evidence

#### Scenario: Preview 後 source state 改變
- **WHEN** Preview 後 revision、body signature 或 active Waler／Strut identities 改變
- **THEN** Apply MUST 拒絕 stale candidate
- **AND** SHALL 要求重新建立 Preview

#### Scenario: 取消或關閉 Preview
- **WHEN** 使用者取消、關閉或尚未 Apply
- **THEN** 正式 CornerBrace、unresolved subject、confirmation與 dirty state SHALL 維持提交前狀態

#### Scenario: Planner 不解析 message
- **WHEN** planner 需要 body、relationship或 rejection evidence
- **THEN** 系統 SHALL 只使用 structured evidence
- **AND** MUST NOT 解析 ValidationMessage 文字

#### Scenario: 主要資訊與稽核資訊分層
- **WHEN** 使用者檢視candidate
- **THEN** 主要區 SHALL 顯示mode、target relationship、endpoints與result length
- **AND** 次要區 SHALL 顯示source identities、body／assessment或template evidence與diagnostics

#### Scenario: 稽核與診斷區預設收合
- **WHEN** Preview開啟
- **THEN** 次要區 SHALL 預設收合且可展開
- **AND** 顯示狀態 MUST NOT 改變selection、Apply或live state

#### Scenario: 使用者選擇多個候選之一
- **WHEN** 使用者以stable candidate ID選擇一組
- **THEN** Preview SHALL 更新summary、overlay與Apply state
- **AND** MUST NOT 混用其他candidate evidence

#### Scenario: 以灰色顯示目標來源線段
- **WHEN** Preview具有residual source segments
- **THEN** Presentation SHALL 以低干擾方式顯示來源，並凸顯selected axis
- **AND** overlay MUST NOT 成為eligibility evidence

#### Scenario: 改選或離開預覽時清除 temporary overlay
- **WHEN** 使用者改選、取消或關閉Preview
- **THEN** 系統 SHALL 清除temporary overlay且不修改live state

#### Scenario: 使用者取消預覽
- **WHEN** 使用者取消或關閉Preview
- **THEN** 所有正式geometry、relationships、confirmation與dirty state SHALL 維持提交前狀態

#### Scenario: 沒有合法候選
- **WHEN** 沒有candidate通過其mode所需全部hard gates
- **THEN** 系統 SHALL 顯示structured rejection diagnostics並保持原狀態

#### Scenario: 多個 hypotheses 都缺少必要 evidence
- **WHEN** 多個hypotheses各自缺少body、relationship、finite endpoint、coverage、extension、gap或template evidence
- **THEN** 系統 MUST NOT 將任何hypothesis包裝成可Apply candidate

#### Scenario: Proximity 只排序合法候選
- **WHEN** reference-template candidates已先通過全部hard gates
- **THEN** 系統 MAY 依既有tier／locality排序
- **AND** proximity MUST NOT 使不合法candidate成立或影響relationship-selection winner

### Requirement: Unresolved 來源建立正式 CornerBrace 必須通過額外門檻

系統 MUST 區分 `replace existing recognized CornerBrace`、`reference-template create from unresolved source` 與 `create from recognized body relationship selection`。

既有 reference-template create 維持其 exact source identity、target evidence、唯一 relationship、compatible primary、finite transfer與 staged validation contract。

`create from recognized body relationship selection` 只適用於唯一 `BodyGeometryEvidence` 加多組 hard-valid `BodyRelationshipAssessment`。Body 零解／多解、任一 rail coverage不足、任一 extension超限、unexplained gap或其他 hard gate失敗都不得進入此例外。成功 Apply MUST 原子建立正式 CornerBrace、唯一 connection、candidate points、problems／ReviewItems、derived values與 selection provenance；任一步失敗 MUST rollback。

#### Scenario: Body-recognized source 有多組 relationships
- **WHEN** unique body 有多組 assessments，且每組分別通過 coverage、extension、gap與既有 validation
- **THEN** 系統 SHALL 允許將它們建立為 Preview candidates
- **AND** MUST NOT 在使用者選擇前建立正式 connection

#### Scenario: Body 零解或多解
- **WHEN** source 沒有 unique body
- **THEN** 系統 MUST 拒絕 relationship-selection create path
- **AND** MUST NOT 讓使用者只選 Waler／Strut 繞過 body eligibility

#### Scenario: Assessment 不完整
- **WHEN** candidate 缺少任一 rail coverage、gap assignment、finite endpoint、extension或 validation evidence
- **THEN** 系統 MUST 拒絕該 candidate

#### Scenario: Atomic Apply 成功
- **WHEN** selected candidate 在 current revision 重驗全部 hard gates成功
- **THEN** 系統 SHALL 一次提交 CornerBrace、唯一 connection及衍生 Review state

#### Scenario: Atomic Apply 失敗
- **WHEN** staged build或任一 validation失敗
- **THEN** 系統 MUST rollback全部修改
- **AND** SHALL 保留提交前 unresolved state

#### Scenario: 不新增 Project schema
- **WHEN** relationship-selection provenance需要保存 optional mode或body signature
- **THEN** 系統 SHALL 使用 backward-compatible Review／override contract
- **AND** 若無法做到則 MUST 停止實作並回報

#### Scenario: Replace existing recognized CornerBrace
- **WHEN** target是具有唯一repair subject identity的existing CornerBrace且使用者Apply合法candidate
- **THEN** 系統 SHALL 更新該CornerBrace，不得建立duplicate member

#### Scenario: Unresolved source 通過完整 create eligibility
- **WHEN** unresolved source通過既有reference-template exact identity、target evidence、唯一relationship、finite transfer與staged validation
- **THEN** 系統 SHALL 允許使用者明確Apply後建立formal CornerBrace

#### Scenario: 只有 layer 或 nearby evidence
- **WHEN** unresolved source只有layer、INSERT、nearby members或references而缺少既有target evidence與unique body
- **THEN** 系統 MUST NOT 建立formal CornerBrace

#### Scenario: Unresolved source 有多組 target relationships
- **WHEN** unresolved source沒有unique body且reference-template hypotheses指向多組relationships
- **THEN** 系統 MUST 拒絕create path並顯示ambiguity

#### Scenario: 建立後 validation 未全部通過
- **WHEN** staged formal CornerBrace有任一既有validation失敗
- **THEN** 系統 MUST rollback並保留原unresolved state

### Requirement: 自動辨識與非目標系統維持既有行為

Repair tool MUST NOT 放寬 automatic CornerBrace hard gates、修改一般 member recognition、建立 canonical Waler、改變 Solver或 Project schema。Automatic recognition SHALL 只在 body 唯一且 hard-valid relationship唯一時建立正式 connection。

Body 零解／多解時只能依既有 reference-template eligibility處理；problem文字本身不是 evidence。Body 唯一且 relationship多解時，repair tool MAY 建立 `body_relationship_selection` candidates，但不得自動選擇或 Apply。Source exclusion／restore後 MUST 依 active facts重辨識。

#### Scenario: Automatic 唯一結果不使用 repair
- **WHEN** unique body只有一組 hard-valid relationship且使用者未啟動 repair
- **THEN** 系統 SHALL 維持 automatic result

#### Scenario: Body ambiguity 沿用既有 repair eligibility
- **WHEN** automatic recognition因 body零解或多解 unresolved
- **THEN** repair tool MAY 評估既有 reference-template route
- **AND** MUST NOT 建立 relationship-selection candidates

#### Scenario: 重複 Waler 只能由使用者明確解決
- **WHEN** unique body對應多個 hard-valid active Waler identities
- **THEN** repair tool MAY 顯示分開的 candidates
- **AND** MUST NOT 合併、first-match、自動選擇或自動 Apply

#### Scenario: 排除 source 後 automatic 重算
- **WHEN** 使用者排除其中一個 competing source後只剩一組 hard-valid relationship
- **THEN** automatic recognition SHALL 建立該唯一 connection
- **AND** MUST NOT 重播舊 Preview selection

#### Scenario: 未合法解決前維持 completion block
- **WHEN** unresolved source尚未被排除、重算為唯一結果或明確 Apply合法 candidate
- **THEN** DXF Review MUST NOT 完成

#### Scenario: 可靠角撐不使用修補工具
- **WHEN** automatic recognition已建立unique body與唯一hard-valid connection且使用者未啟動repair
- **THEN** 系統 SHALL 維持automatic結果

#### Scenario: Automatic 無解來源仍需符合 repair eligibility
- **WHEN** automatic recognition因body零解／多解或relationship零解而unresolved
- **THEN** repair tool SHALL 依對應既有route eligibility評估
- **AND** MUST NOT 只因warning存在而建立candidate

#### Scenario: 重複 Waler relationship 不由 repair 自動解決
- **WHEN** unique body同時對應多個hard-validWaler identities
- **THEN** repair tool MUST NOT 合併、first-match或自動Apply

#### Scenario: Unresolved source 未合法解決前維持 completion block
- **WHEN** source尚未被排除、automatic重算為唯一或explicit Apply合法candidate
- **THEN** DXF Review completion MUST 保持blocked

#### Scenario: 修補不進入 Project schema
- **WHEN** repair後的DXF Review完成匯入
- **THEN** Project boundary SHALL 維持既有正式member contract
- **AND** selection evidence SHALL 留在backward-compatible DXF Review state
