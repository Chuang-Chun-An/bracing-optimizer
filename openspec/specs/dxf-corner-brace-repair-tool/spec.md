# dxf-corner-brace-repair-tool Specification

## Purpose
提供 DXF Review 中受 BIM 遮蔽或中心軸誤判之角撐的保守人工修補流程，在不放寬自動辨識的前提下，以目標殘線、既有工程構件與可追溯參考角撐提出可預覽候選，並只在使用者明確採用後更新正式 Review state。

## 閱讀導航

- **必讀**：本規格的「修補必須先預覽再明確採用」、「修補決策必須可追溯且安全重播」與「角撐修補介面須使用繁體中文」；先確認顯示 ID 不決定 reference 或 confirmation 是否仍有效。
- **條件式閱讀**：變更候選幾何、reference selection 或 replay safety 時，閱讀目標來源證據、參考角撐分級、局部模板，以及 stable reference 零筆／多筆 match 與工程輸入改變情境。
- **條件式閱讀**：涉及 Pause／Resume 或 Relink 時，再讀 `paused-dxf-review-source-relink` 的「角撐修補決策不得跨內容靜默轉移」；stable matching 不得成為 changed-content recovery 套用舊 repair 的理由。
- **可先跳過**：未涉及暫停／續作時的 replay、未啟動修補時的自動辨識保護，以及既有 Solver、材料與 Project schema 邊界。

## Requirements

### Requirement: 修補工具只處理明確選取的角撐 subject

系統 SHALL 在 STEP4 修改工具中，對使用者目前選取的正式 CornerBrace 或狀態為 `unresolved`、角色為 `corner_brace` 且具有可識別 source identity 的來源提供角撐修補入口。一次修補 MUST 只針對一個明確 subject；工具不得掃描後自動修改其他角撐。

#### Scenario: 修補已辨識但軸線錯誤的角撐
- **WHEN** 使用者選取一支正式 CornerBrace 並啟動修補工具
- **THEN** 系統以該 CornerBrace 的 exact source identity 與來源幾何建立修補 session
- **AND** 不修改其他正式 CornerBrace

#### Scenario: 修補尚未形成正式角撐的來源
- **WHEN** 使用者選取角色為 `corner_brace`、具有 exact source identity 的 unresolved Review subject 並啟動修補工具
- **THEN** 系統可為該來源規劃建立正式 CornerBrace 的候選
- **AND** 在使用者採用前不得先建立正式工程構件

#### Scenario: 非角撐或缺少安全來源 identity
- **WHEN** 選取項目不是 CornerBrace subject，或無法取得可安全識別的角撐來源
- **THEN** 系統 SHALL 不啟用角撐修補
- **AND** SHALL 說明此項目不符合修補前提

### Requirement: 目標來源幾何是修補必要證據

系統 MUST 從目標 subject 自己的 exact DXF source geometry 取得修補證據。對 reference-template repair，目標證據 MUST 同時支持：一個可在既有具名容差內判定的角撐方向，以及至少一個可定位目標區域的 positional anchor；positional anchor 可為圍令連接板中點、與該方向共線的局部殘線 corridor，或其他由 exact target source geometry 唯一推得的點位。殘線不必覆蓋完整角撐、到達 Strut attachment，或自行提供完整長度。

附近已成功角撐、Waler 或 Strut 不得在完全沒有上述 target evidence 時單獨創造 CornerBrace。修補 eligibility 與幾何比較 SHALL 使用既有具名 `GeometryTolerances`；不得加入固定材料寬度、未命名距離門檻，或把連接板／外框的任意邊當作完整角撐軸。

#### Scenario: 殘線可支持候選方向
- **WHEN** BIM 遮擋使目標角撐只留下圍令端連接板中點與局部軸向殘線，且兩者可唯一支持一個 transferred candidate 的位置與方向
- **THEN** 系統 SHALL 允許該不完整殘線驗證 candidate
- **AND** MUST NOT 要求殘線自行延伸至兩個正式端點

#### Scenario: 參考角撐存在但目標沒有可用殘線
- **WHEN** 附近存在合格 reference CornerBrace，但 exact target source geometry 無法同時提供可靠方向與 positional anchor
- **THEN** 系統 MUST 拒絕產生可採用的正式修補候選
- **AND** MUST NOT 只依鄰近、對稱或圖層 identity 創造構件

#### Scenario: 多條殘線支持非等價軸
- **WHEN** exact target source geometry 在既有容差下支持多個非等價方向，且無法由 positional anchor 與 compatible template 唯一消除歧義
- **THEN** 系統 MUST 保留多解或證據不足狀態
- **AND** MUST NOT 依 entity order、handle 大小或 first match 任意選定方向

### Requirement: 參考角撐必須分級並阻止推測鏈

系統 MUST 將 reference CornerBrace 分為 `automatic primary` 與 `manual repaired secondary`。`automatic primary` MUST 來自 automatic recognition、來源目前有效，且具有唯一有效的 CornerBrace-to-Waler／Strut 關聯。`manual repaired secondary` MUST 已由使用者明確採用、具有完整 repair provenance、目前 Review confirmation 仍有效、來源目前有效、不是 `requires_review`，且仍具有唯一有效的 CornerBrace-to-Waler／Strut 關聯。

每一個 `reference_template` repair candidate MUST 由恰好一支被選為 template 的 `automatic primary` 產生局部配置，並可由其他 eligible references 補充一致性 evidence。對 `reference_template`，`manual repaired secondary` 不得成為 template、不得單獨使候選成立；系統不得遞迴展開 secondary reference 自己曾使用的 repaired references，也不得讓 repaired CB1 → repaired CB2 → repaired CB3 形成無 automatic primary 的推測鏈。`body_relationship_selection` candidate SHALL 依其既有 body 與 relationship evidence 建立，MUST NOT 選用 template，且 MUST NOT 僅因沒有 automatic primary 而被本 Requirement 拒絕。

對 `reference_template`，Reference 必須先通過 target endpoint topology、Waler／Strut 局部夾角、有限構件落點及 target residual validation 等 compatibility gates，才可進入 locality ranking。排序 MUST 依序優先：同一 target Waler／Strut 關係的對側 automatic primary、相同 endpoint topology 的相容鄰近 Strut，最後才是其他相容 automatic primary；同一優先層內才可使用目標 positional anchor 至 reference engineering line 的空間距離排序。距離不得使不相容 reference 合法。

#### Scenario: Automatic recognized CornerBrace 成為 primary reference
- **WHEN** 一支 automatic recognized CornerBrace 的來源有效、CornerBraceConnection 唯一有效，且其局部 topology 與 target 相容
- **THEN** 系統可將它列為 `automatic primary` template 候選

#### Scenario: 同一 Waler 與 Strut 的對側角撐優先
- **WHEN** target 與一支 automatic primary 共用同一有限 Waler／Strut 關係、位於可由 target evidence 支持的對側，且 transfer 後通過全部 hard validation
- **THEN** 系統 SHALL 優先使用該 reference 的鏡射 template
- **AND** SHALL NOT 因較遠的同側 reference 也通過寬鬆長度檢核而將其排在前面

#### Scenario: 鄰近支撐提供有效參考
- **WHEN** 同一 Waler／Strut 關係沒有相容 automatic primary，但鄰近 Strut 存在 endpoint topology 與局部夾角相容的 automatic primary
- **THEN** 系統可依 locality ranking 使用該鄰近 reference 建立 transferred candidate

#### Scenario: 已確認 repaired CornerBrace 成為 secondary reference
- **WHEN** 一支 manual repaired CornerBrace 已明確採用、provenance 完整、目前 confirmation 有效、來源有效、不是 `requires_review`，且 connection 唯一有效
- **THEN** 系統可將它列為 `manual repaired secondary` consistency evidence
- **AND** MUST NOT 將其選為 geometry template

#### Scenario: 只有 repaired references
- **WHEN** 系統評估 `reference_template` repair route，而 target 附近只有一支或多支 manual repaired CornerBrace，沒有任何 compatible automatic primary
- **THEN** 系統 MUST NOT 產生可 Apply candidate
- **AND** MUST NOT 以 repaired reference chain 補足 template evidence

#### Scenario: Repaired reference 不再可信
- **WHEN** 一支 manual repaired CornerBrace 的 confirmation、來源、connection 或 provenance 已失效，或已標示為 `requires_review`
- **THEN** 系統 MUST 排除該 secondary reference
- **AND** MUST NOT 讓它影響 template eligibility 或 candidate validation

#### Scenario: 參考角撐本身關聯無效
- **WHEN** 一支 automatic recognized CornerBrace 無法唯一建立有效 CornerBrace-to-Waler／Strut 關聯
- **THEN** 系統 MUST NOT 將它列為 automatic primary template

#### Scenario: 最近 reference 不相容
- **WHEN** 空間上最近的 CornerBrace 具有不同 endpoint topology、無效 connection、不同局部 Waler／Strut 幾何，或 transferred result 不符合 target evidence
- **THEN** 系統 MUST 排除該 reference
- **AND** SHALL 繼續評估下一支 compatible automatic primary，而不是降低 hard validation

#### Scenario: 多筆參考不一致
- **WHEN** 同一 compatibility tier 內有多支距離在既有 ambiguity tolerance 內的 automatic primaries，且它們產生非等價 candidates
- **THEN** 系統 SHALL 將非等價且各自完整的 candidates 保留供 Preview 選擇
- **AND** MUST NOT 依 ID、entity order 或 first match 自動選定 template

#### Scenario: 沒有合格參考角撐
- **WHEN** 系統評估 `reference_template` repair route，而所有附近 CornerBrace 都未通過 primary eligibility、target compatibility 或有限幾何檢核
- **THEN** 系統 MUST NOT 產生可 Apply candidate
- **AND** SHALL 顯示沒有合格 automatic primary reference 的拒絕原因

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

### Requirement: 採用修補必須原子重建相關 Review 資料

採用修補 SHALL 是 `DXFReviewWorkflow` 擁有的單一狀態轉換。系統 MUST 更新既有 CornerBrace，或為 unresolved target 建立一支具有唯一顯示 ID 的正式 CornerBrace；同一提交 MUST 保留目標 source handles／layer／entity types，標記人工修補 selection source 與參考 provenance，並重建 CornerBraceConnection、Strut 角撐衍生長度、candidate points、problems、ReviewItems 及 validation。任一步驟失敗 MUST 回復提交前完整 live Review state，不得留下部分更新。

#### Scenario: 更新已辨識 CornerBrace
- **WHEN** 使用者採用已辨識 CornerBrace 的修補候選
- **THEN** 系統 SHALL 以修補工程線更新同一來源的正式 CornerBrace
- **AND** SHALL 重新建立其角撐關聯與相關 Strut 衍生長度

#### Scenario: unresolved 來源成為正式 CornerBrace
- **WHEN** unresolved 角撐來源通過 create eligibility，且使用者採用合法修補候選
- **THEN** 系統 SHALL 建立一支來源可追溯的正式 CornerBrace
- **AND** 原 unresolved subject SHALL 由重新建立的 ReviewItems 取代，而不是與正式構件形成兩份 active truth

#### Scenario: 修補會使既有確認失效
- **WHEN** 修補改變被確認 subject 或其相關工程狀態的 current-state signature
- **THEN** 系統 MUST 依既有 confirmation validation 移除失效確認
- **AND** SHALL 回報被連帶失效的確認

#### Scenario: 重建中發生錯誤
- **WHEN** 正式角撐建立、關聯、衍生長度或 validation 重建任一步驟失敗
- **THEN** 系統 MUST 回復修補前的完整 world result、projected result、ReviewItems、confirmations、candidate store 與 revision 狀態

### Requirement: 修補決策必須可追溯且安全重播

新採用的修補 MUST 記錄 exact target source identity、採用的 world engineering line、目標 Waler／Strut、selection source 與 selection mode。`reference_template` 修補 MUST 另外記錄被選用的 automatic primary template identity、transfer mode、reference local Waler offset、reference Strut inward station，以及參與驗證的 manual repaired secondary identities；其他符合 eligibility 但未被選為 template 的 automatic primaries MAY 記錄為 validation evidence，但不得與 selected template 混淆。`body_relationship_selection` 修補 MUST 另外記錄可唯一核對的 body signature 與被選用的 target relationship identities，且 MUST NOT 要求 selected template、template local transfer 或 secondary reference fields。

相同 DXF fingerprint 下，凡 Pause／Resume、source exclusion／restore、`EXACT_MATCH` Relink 後續重建或其他 repair replay 入口需要從已保存 provenance 重新定位 `reference_template` references，系統 MUST 以 reference 的角色、source fingerprint、normalized source handles 與可穩定重建的 subject evidence 所形成之 stable subject identity 進行對齊。每次 recognition 依順序產生的顯示 member ID 只可作為呈現或診斷資料，MUST NOT 成為判定同一支 reference 仍存在的必要欄位。

每一筆保存的 reference MUST 在目前 eligible references 中得到恰好一筆 stable identity match。零筆 match、多筆 match 或 identity 歧義時，系統 MUST NOT 依相同顯示 ID、幾何鄰近、排序位置或 first match 選擇替代 reference，且 MUST 依該 replay 入口既有的 `needs_review`、`disabled` 或要求重新修補語意安全拒絕。

Stable identity 唯一對齊後，系統仍 MUST 依目前 Review result 重驗 reference 角色與來源有效性、reference engineering geometry、唯一 CornerBrace-to-Waler／Strut connection、automatic primary／manual repaired secondary eligibility，以及適用的 confirmation 與 repair provenance。`reference_template` 只有在 selected automatic primary template、transfer mode、局部尺寸與 adopted world line 仍能唯一重建並通過現行 candidate validation 時才可重播；任一安全輸入缺失或改變時，顯示 ID 或 stable identity 相符均不得使 replay 成立。

Stable subject evidence中的`base_geometry_key` MUST 保留既有語意：recognized CornerBrace使用完成Waler／Strut context refinement後的工程線段，unresolved CornerBrace使用exact source body geometry。該key MUST NOT納入Waler／Strut顯示member ID或以connection record取代；即使key可對齊，系統仍 MUST 另外重驗目前唯一connection。

保存的target Waler／Strut MUST 以canonical source identity重新定位目前構件，顯示W／S編號只可作當次result存取、呈現或診斷。Canonical identity零筆、多筆或current relationship改變時 MUST安全拒絕；系統 MUST NOT 因另一支構件取得舊顯示編號而接受該構件。

CornerBrace review confirmation的persisted key MUST維持由role與normalized source handles形成的stable identity。其signature MUST保留使用者確認時的source、geometry、repair evidence、relationship與review problems，但 MUST NOT因同一工程subject的CornerBrace ID、nested repair reference member ID、preferred display ID或其他純display metadata重編而失效。此規則只適用CornerBrace confirmation；其他role的confirmation contract不因本change改變。

保存的preferred repaired CornerBrace ID MUST繼續作replay結果與命名衝突的安全guard，而非source identity或reference fallback。該ID已由不同source subject占用，或staged replay無法產生相同preferred ID時，系統 MUST NOT commit部分replay、轉移repair或靜默接受新ID，並 SHALL依既有語意標示`needs_review`。

相同 DXF fingerprint 的 Pause／Resume 重新辨識 MUST 先確認 exact target subject、保存的 target Waler／Strut 與 adopted world line 仍可唯一核對。`body_relationship_selection` 只有在保存的 body signature、exact active target relationship identities 與 adopted world line 仍能唯一核對並通過該模式的現行檢核時才可重播，且不得為了完成 replay 改選 template 或新的 target relationship。任一模式無法滿足其 replay 條件時，系統 MUST 保留 candidate-based state 並要求重新修補。既有不含 template-transfer fields 的 version 2 repair payload MUST 保持可讀，並以其保存的 adopted world line、target identities 與 references 走既有安全 replay；不得因本 change 靜默套用新的 reference selection。

候選 DXF fingerprint 不同時，stable reference identity match MUST NOT 授權 compatible recovery 套用舊修補效果或恢復舊 reference eligibility。系統 MUST 維持 `paused-dxf-review-source-relink` 對角撐修補 decision 的 `requires_review`／`disabled` 分類、candidate-based recovered state 與重新確認要求。

#### Scenario: 相同來源安全重播
- **WHEN** paused Review 以相同 source fingerprint 恢復，selection mode 為 `reference_template`，exact target、target relationship 與 selected template stable identity 唯一存在，且保存的 transfer 可重建相同 adopted world line
- **THEN** 系統 SHALL 恢復修補後的正式 CornerBrace 與重新推導的衍生資料

#### Scenario: 顯示 member ID 重編但 stable reference 未變
- **WHEN** 相同 source fingerprint 的重新辨識使 selected template 或 secondary reference 的顯示 member ID 改變，但其 stable subject identity、角色、來源、engineering geometry、唯一 connection、eligibility、confirmation 與 provenance 均維持有效
- **THEN** 系統 SHALL 以該唯一 stable identity match 繼續安全 replay
- **AND** MUST NOT 僅因顯示 member ID 不同將該 repair 標示為 `needs_review`

#### Scenario: Target顯示編號位移但source identity未變
- **WHEN** same-fingerprint replay中target Waler或Strut顯示編號改變，但保存的canonical source identity仍各自唯一對應相同工程構件，且current relationship與其他安全輸入未變
- **THEN** 系統 SHALL以canonical source identity定位target並繼續安全replay
- **AND** MUST NOT僅因W／S顯示編號不同將repair標示為`needs_review`

#### Scenario: Target source identity缺失或不唯一
- **WHEN** 保存的target Waler或Strut canonical source identity在目前result為零筆、多筆，或relationship不再代表原target
- **THEN** 系統 MUST NOT依舊顯示編號、排序位置或first match選擇替代構件
- **AND** SHALL依既有語意安全拒絕該repair

#### Scenario: CornerBrace confirmation只發生顯示編號位移
- **WHEN** 已確認的CornerBrace及其repair references仍具有相同stable source／subject identities與全部工程、repair及review內容，但top-level CornerBrace ID、nested reference member ID或preferred display ID因重新辨識而改變
- **THEN** 目前confirmation signature SHALL與保存值相同
- **AND** manual repaired secondary MUST NOT僅因這些display metadata改變而失去eligibility

#### Scenario: CornerBrace confirmation的工程內容改變
- **WHEN** 已確認CornerBrace的source、geometry、repair subject、adopted line、transfer evidence、stable primary／secondary identities、relationship、warnings或review problems任一項改變
- **THEN** 目前confirmation signature MUST與保存值不同
- **AND** 系統 MUST依既有confirmation規則使該確認失效

#### Scenario: Preferred repaired ID衝突
- **WHEN** 保存的preferred repaired CornerBrace ID已由不同source subject占用，或staged replay產生的ID與preferred ID不同
- **THEN** 系統 MUST NOT commit該staged repair、改套占用該ID的構件或靜默接受新ID
- **AND** SHALL依既有語意將該repair標示為`needs_review`

#### Scenario: S14 target實體與顯示編號基準
- **WHEN** Y05 saved Review state排除Strut `S14`／`strut:D1A`並重播CB66～CB70
- **THEN** target Waler SHALL維持CB66=`W5`／`waler:B29`、CB67=`W6`／`waler:B34`、CB68～CB70=`W13`／`waler:1647`
- **AND** target Strut SHALL維持CB66=`S5`／`strut:B05`、CB67=`S5`／`strut:B05`，且CB68～CB70分別由`S21`→`S20`／`strut:D74`、`S20`→`S19`／`strut:D4B`、`S19`→`S18`／`strut:D34`
- **AND** 系統 MUST NOT因CB68～CB70的Strut顯示編號位移拒絕repair或改接另一source identity

#### Scenario: Stable reference 無匹配
- **WHEN** 一筆保存的 selected template 或 secondary reference 在目前 eligible references 中沒有 stable identity match
- **THEN** 系統 MUST NOT replay 該修補
- **AND** MUST NOT 依相同顯示 ID、幾何鄰近或排序位置選擇替代 reference

#### Scenario: Stable reference 匹配不唯一
- **WHEN** 一筆保存的 selected template 或 secondary reference 對應到多筆相同 stable subject identity 的目前 references，或無法證明唯一對應
- **THEN** 系統 MUST NOT 依 entity order、member ID 或 first match 任選一筆
- **AND** SHALL 依該 replay 入口既有語意要求重新檢查或停用舊 decision

#### Scenario: Stable reference 對齊後工程輸入改變
- **WHEN** 保存的 reference 可由 stable identity 唯一對齊，但其 engineering geometry、CornerBrace-to-Waler／Strut connection、primary／secondary eligibility、confirmation 或 provenance 任一項已改變或失效
- **THEN** 系統 MUST NOT replay 該修補
- **AND** MUST NOT 以顯示 ID 相同或 source identity 相符跳過現行安全檢核

#### Scenario: Body relationship selection 保存不含 template
- **WHEN** 使用者採用 `body_relationship_selection` candidate
- **THEN** repair provenance SHALL 保存 exact target source identity、adopted world line、target relationship identities、selection source、selection mode 與可唯一核對的 body signature
- **AND** MUST NOT 要求 selected template 或 template local transfer fields

#### Scenario: Body relationship selection 安全重播
- **WHEN** paused Review 以相同 source fingerprint 恢復，selection mode 為 `body_relationship_selection`，exact target、body signature、target relationship identities 與 adopted world line 仍唯一一致，且 candidate 通過該模式的現行檢核
- **THEN** 系統 SHALL 恢復修補後的正式 CornerBrace 與重新推導的衍生資料
- **AND** MUST NOT 改選 template 或新的 target relationship

#### Scenario: exact target source identity 不再唯一
- **WHEN** 恢復 Review 時 exact target source identity 已不存在、對應到多個 subjects，或不再唯一代表原修補目標
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 保留 candidate-based state 並要求重新處理

#### Scenario: 參考角撐後續改變
- **WHEN** selection mode 為 `reference_template`，exact target 仍有效，但保存的 selected automatic primary template 已改變、不存在或不再 compatible
- **THEN** 系統 MUST NOT 以目前最近的另一支 reference 代替
- **AND** SHALL 將修補標示為需要重新處理

#### Scenario: Local transfer 無法重建相同工程線
- **WHEN** selection mode 為 `reference_template`，保存的 target relationship 仍存在，但依保存 template 與 transfer mode 重建的工程線不再符合 adopted world line 或 target evidence
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 保留重新辨識的 candidate-based state

#### Scenario: Legacy version 2 repair payload
- **WHEN** same-fingerprint paused Review 含有本 change 前建立、沒有 template-transfer fields 的 repair provenance
- **THEN** 系統 SHALL 依既有 adopted world line、target identities 及 reference eligibility 驗證 replay
- **AND** MUST NOT 自動重新選擇 nearest template 或重算其工程線

#### Scenario: Resume 後只剩 repaired references
- **WHEN** selection mode 為 `reference_template`，保存修補的 secondary references 仍有效，但 selected automatic primary template 已失效或不存在
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 要求使用者重新檢查，不得以 secondary reference chain 取代 primary template

#### Scenario: Changed-content recovery 不因 stable reference match 恢復 repair
- **WHEN** compatible recovery 的候選 DXF fingerprint 與保存值不同，即使舊修補使用的 reference 可由 stable subject identity 唯一對齊
- **THEN** 系統 MUST NOT 因該 match 套用舊修補效果或恢復舊 reference eligibility
- **AND** SHALL 維持 changed-content recovery 的 `requires_review`／`disabled` 與重新確認語意

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

### Requirement: Automatic primary reference 提供局部配置模板

被選用的 automatic primary SHALL 以自身唯一 CornerBraceConnection 轉換成與 absolute world coordinates 無關的局部配置模板。模板 MUST 至少包含：reference endpoint topology、相對 reference Waler／Strut 有限交點的 Waler-side offset magnitude、沿 Strut inward direction 的 attachment station，以及可稽核的 reference fixed length。Transferred endpoints MUST 完全由 target local frame、reference Waler offset、reference Strut station 與 same-side／mirrored mode 決定；candidate fixed length MUST 由 transferred endpoints 重算。

Reference fixed length MUST 只用於 Preview 顯示、provenance 稽核與 diagnostic comparison。它 MUST NOT 移動 transferred endpoints、強迫 target candidate 與 reference 等長、透過圓交點／縮放／clamp 修改結果，亦 MUST NOT 單獨使 candidate 通過或失敗。

#### Scenario: 從有效 reference 建立 local template
- **WHEN** automatic primary 具有唯一 Waler／Strut connection，且其兩端分別位於相關有限工程線上
- **THEN** 系統 SHALL 以該 relationship 的局部交點與方向計算可移植 offset／station
- **AND** SHALL 保留 reference identity 與原 fixed length 供 Preview、provenance 稽核及 diagnostic comparison，但不將 fixed length 納入 hard eligibility

#### Scenario: Candidate length 由 transferred endpoints 重算
- **WHEN** target local frame、reference Waler offset、reference Strut station 與 transfer mode 已產生兩個有限 transferred endpoints
- **THEN** 系統 MUST 由這兩個 endpoints 的距離計算 candidate fixed length
- **AND** MUST NOT 複製 reference fixed length 作為 candidate fixed length

#### Scenario: Reference fixed length mismatch 只產生 diagnostic
- **WHEN** candidate fixed length 與 reference fixed length 不同，但 candidate 通過所有 target geometry、target evidence 與既有 CornerBrace validation
- **THEN** 系統 SHALL 保留該 candidate 的既有 eligibility，並可顯示長度差異 diagnostic
- **AND** MUST NOT 單獨因 reference fixed length mismatch 接受或拒絕 candidate

#### Scenario: Reference 無法建立有限 local frame
- **WHEN** reference Waler／Strut 沒有唯一有限交點、方向退化，或 attachment 無法映射為有限 local offset／station
- **THEN** 該 reference MUST NOT 成為 template

#### Scenario: Template transfer 與 target evidence 不一致
- **WHEN** local template 可映射到 target 有限構件，但 candidate 軸與 exact target direction 不相容，或未通過 positional-anchor／residual corridor validation
- **THEN** 該 transferred candidate MUST 被拒絕

### Requirement: 角撐修補介面須使用繁體中文

系統 SHALL 以繁體中文呈現角撐修補流程中的使用者可見文字，包括修補可用性說明、預覽視窗說明、候選選取、方案摘要、候選明細、顯示用狀態名稱、拒絕診斷與提交錯誤。同一角色、移植方式或定位尺寸在角撐修補介面中重複出現時 MUST 使用一致的中文術語，且可共用術語 SHALL 可由其他 Presentation consumer 重用。

使用者可見的 `reference_waler_offset_mm` SHALL 顯示為「圍令端定位距離」，`reference_strut_station_mm` SHALL 顯示為「支撐端定位距離」；介面 SHALL 顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」或語意完全相同的繁體中文說明。此顯示名稱變更 MUST NOT 更名內部欄位、DTO、serialized key 或 planner term。

角撐修補預覽中的工程長度、定位距離及座標分量 SHALL 固定顯示至小數第 3 位。工程長度與定位距離 SHALL 顯示 `mm` 單位；座標 SHALL 維持既有無單位表示方式。顯示格式 MUST NOT 改變原始 double precision、candidate eligibility、排序、candidate ID、工程幾何、提交結果或 persistence contract。

#### Scenario: 預覽合法候選

- **WHEN** 使用者開啟具有一個或多個合法候選的角撐修補預覽
- **THEN** 視窗說明、候選選取、方案摘要與候選明細 SHALL 使用繁體中文描述目標圍令與支撐、參考模板、移植方式、局部尺寸、結果長度及驗證證據
- **AND** 構件 ID、格式化數值與適用的 `mm` 單位 SHALL 保持可稽核內容

#### Scenario: 顯示移植方式

- **WHEN** 候選的內部移植方式為 `same_side` 或 `mirrored`
- **THEN** 介面 SHALL 分別顯示「同側移植」或「鏡射移植」
- **AND** 系統 MUST 保留原內部值供候選選取、提交與持久化使用

#### Scenario: 定位尺寸使用直觀名稱
- **WHEN** 介面顯示 candidate 的 reference local Waler offset 與 Strut inward station
- **THEN** SHALL 分別顯示「圍令端定位距離」與「支撐端定位距離」
- **AND** SHALL 顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」或語意完全相同的繁體中文說明
- **AND** MUST NOT 因顯示名稱變更而改寫內部欄位、DTO、serialized key、planner term 或幾何意義

#### Scenario: 預覽數值統一顯示三位小數
- **WHEN** 角撐修補預覽顯示結果長度、reference fixed length、圍令端定位距離、支撐端定位距離、positional anchor、candidate world engineering line 或多候選表格中的工程數值
- **THEN** 每一個工程數值與座標分量 SHALL 固定顯示至小數第 3 位
- **AND** 工程長度與定位距離 SHALL 顯示 `mm` 單位
- **AND** positional anchor 與 candidate world engineering line 的座標 SHALL 維持無單位表示方式
- **AND** 正數、負數與整數 SHALL 使用相同三位小數格式，包括必要的尾端補零與顯示四捨五入
- **AND** 顯示四捨五入 MUST NOT 回寫或改變原始 double precision、candidate eligibility、排序、candidate ID、工程幾何或提交值

#### Scenario: 重複概念使用一致術語

- **WHEN** 角撐修補的候選選取、主要確認區與次要稽核區顯示相同的角色、移植方式或定位尺寸
- **THEN** `corner_brace` SHALL 一致顯示為「角撐」，`same_side` SHALL 一致顯示為「同側移植」，`mirrored` SHALL 一致顯示為「鏡射移植」
- **AND** Waler-side offset 與 Strut inward station SHALL 分別一致顯示為「圍令端定位距離」與「支撐端定位距離」
- **AND** 其他介面使用相同可共用術語時 SHALL 能取得同一中文名稱，而不必重新定義另一份對照

#### Scenario: 修補不可執行或提交失敗

- **WHEN** 選取項目不符合修補前提、沒有候選通過安全條件，或提交時偵測到 stale／invalid repair state
- **THEN** 系統 SHALL 以繁體中文顯示具體原因
- **AND** SHALL 維持既有拒絕、保留原狀或 rollback 語意，不得因翻譯而改用較寬鬆的 fallback
