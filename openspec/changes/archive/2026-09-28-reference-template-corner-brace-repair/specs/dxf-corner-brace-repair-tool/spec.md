# Spec Delta

## MODIFIED Requirements

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

每一個可採用 repair candidate MUST 由恰好一支被選為 template 的 `automatic primary` 產生局部配置，並可由其他 eligible references 補充一致性 evidence。`manual repaired secondary` 不得成為 template、不得單獨使候選成立；系統不得遞迴展開 secondary reference 自己曾使用的 repaired references，也不得讓 repaired CB1 → repaired CB2 → repaired CB3 形成無 automatic primary 的推測鏈。

Reference 必須先通過 target endpoint topology、Waler／Strut 局部夾角、有限構件落點及 target residual validation 等 compatibility gates，才可進入 locality ranking。排序 MUST 依序優先：同一 target Waler／Strut 關係的對側 automatic primary、相同 endpoint topology 的相容鄰近 Strut，最後才是其他相容 automatic primary；同一優先層內才可使用目標 positional anchor 至 reference engineering line 的空間距離排序。距離不得使不相容 reference 合法。

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
- **WHEN** target 附近只有一支或多支 manual repaired CornerBrace，沒有任何 compatible automatic primary
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
- **WHEN** 所有附近 CornerBrace 都未通過 primary eligibility、target compatibility 或有限幾何檢核
- **THEN** 系統 MUST NOT 產生可 Apply candidate
- **AND** SHALL 顯示沒有合格 automatic primary reference 的拒絕原因

### Requirement: 每個修補候選必須具有有效的目標工程接點

每一個可預覽的修補候選 MUST 明確且唯一綁定一支目標 Waler、一支目標 Strut 及一支 automatic primary template。此唯一性是 candidate-level contract，不代表整個 repair plan 只能包含一組 target relationship。系統 MUST 以 reference 的 Waler／Strut 有限交點建立 reference local frame，量取 reference Waler attachment 相對交點的側向 offset，以及 reference Strut attachment 沿支撐 inward direction 的 station；再依 target side 採同側 transfer 或鏡射 transfer，將這些局部尺寸映射到 target local frame。

Transferred Waler endpoint MUST 位於 target Waler 有限工程線，transferred Strut endpoint MUST 位於 target Strut 有限中心線；兩者形成的 candidate 必須通過 target direction／positional-anchor validation、既有最小長度、duplicate、CornerBraceConnection 與其他既有 CornerBrace validation。系統不得複製 reference 的 absolute world coordinates、修改 target Waler／Strut 幾何，或將只能落在有限構件之外的 transferred endpoint 吸附回構件。

#### Scenario: 目標 Waler 與 Strut 接點有效
- **WHEN** candidate 明確綁定唯一 target Waler／Strut，且 template transfer 產生的兩個 endpoints 分別位於其有限工程線上
- **THEN** 系統 SHALL 允許該 candidate 繼續進行 target evidence 與既有 CornerBrace validation

#### Scenario: 同側局部配置移植
- **WHEN** compatible template 與 target 位於等價 side，且局部 offset／station 映射後的兩端都落在 target 有限構件上並符合 target evidence
- **THEN** 系統 SHALL 以映射後端點建立 eligible candidate
- **AND** SHALL 由該兩端距離計算 candidate fixed length

#### Scenario: 對側局部配置鏡射
- **WHEN** compatible template 位於 target Strut 的另一側，且 target direction／positional anchor 支持鏡射方向
- **THEN** 系統 SHALL 對 Waler 側向 offset 進行鏡射並保留 Strut inward station
- **AND** SHALL 以 target local frame 產生兩個正式端點

#### Scenario: 任一接點不在有限構件上
- **WHEN** template 的局部 offset 或 station 映射後，使任一 endpoint 落在 target Waler 或 Strut 的有限工程線之外
- **THEN** 該 transferred candidate MUST 被拒絕
- **AND** MUST NOT 使用無限延長線或最近點吸附使其成立

#### Scenario: 多組 Waler 或 Strut 關係皆可成立
- **WHEN** recognized replace target 可形成多個非等價且各自通過 hard validation 的 Waler／Strut relationships
- **THEN** repair plan SHALL 將每組 relationship 建立為明確且各自唯一綁定的 candidate，並分開呈現其 target relationship 與 template
- **AND** MUST NOT 在使用者選擇前把其中一組當成正式關聯

#### Scenario: Unresolved create 不得把 relationship 歸屬交給使用者
- **WHEN** unresolved create target 的 hard-eligible candidates 指向多組非等價 Waler／Strut relationships
- **THEN** 系統 MUST 將 create path 視為 blocking
- **AND** MUST NOT 將不同 relationships 包裝成可由使用者選擇的 Preview candidates

### Requirement: 修補必須先預覽再明確採用

Repair planner MAY 保留未通過 hard eligibility 的 internal hypotheses 以建立拒絕 diagnostics，但只有同時具備 exact target source identity、可靠 target direction、target positional anchor、在該 candidate 內唯一且有效的 target relationship、compatible automatic primary template、有效 finite transferred endpoints，並通過 target residual validation 與既有 CornerBrace validation 的 hypotheses，才可成為 Preview 中可選取、可 Apply 的 candidates。

系統 SHALL 在修改 live Review state 前顯示 candidate 工程線、exact target residual、目標 Waler／Strut、被選用的 automatic primary template、同側／鏡射 transfer mode、reference local offset／station、manual secondary evidence 及各項 target validation 結果。即使只有一個 eligible candidate，也 MUST 由使用者明確採用；取消或關閉預覽 MUST 保持零副作用。Recognized replace 可顯示分屬不同 relationship 的多個完整 candidates；unresolved create 只有在所有 hard-eligible candidates 指向同一 relationship 時，才可顯示該 relationship 內的多個 template candidates。多個可預覽 candidates 存在時，系統 SHALL 要求使用者明確選擇，不得自動提交。

#### Scenario: 唯一候選仍需確認
- **WHEN** 系統只建立一個合法 reference-template candidate
- **THEN** 系統 SHALL 顯示其 template、transfer mode、局部尺寸、目標關係與殘線驗證
- **AND** 只有使用者明確採用後才可修改正式 Review state

#### Scenario: 使用者選擇多個候選之一
- **WHEN** 系統顯示多個合法但非等價的 transferred candidates，且使用者選取其中一個並確認
- **THEN** 系統 SHALL 只採用被選取 candidate 的 template transfer、工程線與關係
- **AND** SHALL 不採用其他 candidates 的幾何或 provenance

#### Scenario: 使用者取消預覽
- **WHEN** 使用者取消或關閉修補預覽
- **THEN** 正式 CornerBrace、unresolved subject、關聯、validation、confirmation 與 dirty Review state SHALL 維持提交前狀態

#### Scenario: 沒有合法候選
- **WHEN** target evidence、compatible template、有限 transferred endpoints 或既有 validation 任一不足
- **THEN** 系統 SHALL 顯示不可安全修補的具體原因
- **AND** SHALL 保留原正式幾何或 unresolved 狀態

#### Scenario: 多個 hypotheses 都缺少必要 evidence
- **WHEN** planner 產生多個 internal hypotheses，但每一個都缺少 target evidence、compatible automatic primary、有限 endpoints 或既有 validation 的必要條件
- **THEN** 系統 MUST NOT 將任何 hypothesis 包裝成可 Apply candidate
- **AND** SHALL 顯示對應的拒絕 diagnostics

#### Scenario: Proximity 只排序合法候選
- **WHEN** 多支 automatic primaries 已各自通過 compatibility gates
- **THEN** 系統 MAY 依正式 tier 與 locality 排序其 candidates
- **AND** MUST NOT 因距離較近而跳過 hard validation、隱藏非等價同級 candidate 或自動 Apply

### Requirement: Unresolved 來源建立正式 CornerBrace 必須通過額外門檻

系統 MUST 區分「replace existing recognized CornerBrace」與「create formal CornerBrace from unresolved source」。Replace path SHALL 更新已存在且 subject identity 唯一的 CornerBrace。Create path 只有在 unresolved subject 具備 exact `corner_brace` role／source identity、可靠 target direction、target positional anchor、全體 hard-eligible candidates 指向同一組唯一 finite target Waler／Strut relationship、至少一支 compatible automatic primary template、明確使用者 adoption，且建立後通過全部既有 CornerBrace validation 時才可提交。

只有 layer classification、INSERT identity、附近構件或 references，而沒有 exact target direction 與 positional anchor，不足以建立 formal CornerBrace。Create path 若存在多組非等價 target Waler／Strut relationships，MUST 拒絕建立，不得將 unresolved relationship selection 移交給 Apply；在唯一 relationship 內若仍有多個各自完整的 template-transfer candidates，則可依 Preview requirement 交由使用者明確選擇。

#### Scenario: Replace existing recognized CornerBrace
- **WHEN** target 是具有唯一 repair subject identity 的 existing recognized CornerBrace，且使用者採用一個 eligible template-transfer candidate
- **THEN** 系統 SHALL 更新該 CornerBrace，而不是新增第二支 formal CornerBrace

#### Scenario: Unresolved source 通過完整 create eligibility
- **WHEN** unresolved `corner_brace` subject 具有 exact identity、圍令端 positional anchor、可靠局部方向、唯一 finite target relationship、compatible automatic primary template，且 staged validation 全部通過
- **THEN** 系統 SHALL 允許使用者明確採用後建立 source-traceable formal CornerBrace

#### Scenario: 只有 layer 或 nearby evidence
- **WHEN** unresolved subject 只有正確 layer、INSERT、附近 Waler／Strut 或 reference CornerBrace，但缺少 target direction 或 positional anchor
- **THEN** 系統 MUST NOT 建立 formal CornerBrace

#### Scenario: Unresolved source 有多組 target relationships
- **WHEN** unresolved source 的 hard-eligible hypotheses 指向多組非等價 target Waler／Strut relationships
- **THEN** 系統 MUST 拒絕 create path 並顯示 relationship ambiguity
- **AND** MUST NOT 將這些 relationships 包裝成可 Apply candidates

#### Scenario: 建立後 validation 未全部通過
- **WHEN** selected unresolved repair 在 staged formal CornerBrace 建立後有任一既有 CornerBrace validation 未通過
- **THEN** 系統 MUST 拒絕提交並保留原 unresolved state

### Requirement: 修補決策必須可追溯且安全重播

新採用的修補 MUST 記錄 exact target source identity、採用的 world engineering line、目標 Waler／Strut、selection source、被選用的 automatic primary template identity、transfer mode、reference local Waler offset、reference Strut inward station，以及參與驗證的 manual repaired secondary identities。其他符合 eligibility 但未被選為 template 的 automatic primaries MAY 記錄為 validation evidence，但不得與 selected template 混淆。

相同 DXF fingerprint 的 Pause／Resume 重新辨識只有在 exact target subject、保存的 target Waler／Strut、selected automatic primary template、transfer mode、局部尺寸與 adopted world line 仍能唯一重建並通過現行檢核時才可重播；否則 MUST 保留 candidate-based state 並要求重新修補，不得改找新的 nearest reference。既有不含 template-transfer fields 的 version 2 repair payload MUST 保持可讀，並以其保存的 adopted world line、target identities 與 references 走既有安全 replay；不得因本 change 靜默套用新的 reference selection。

#### Scenario: 相同來源安全重播
- **WHEN** paused Review 以相同 source fingerprint 恢復，exact target、target relationship 與 selected template identities 唯一存在，且保存的 transfer 可重建相同 adopted world line
- **THEN** 系統 SHALL 恢復修補後的正式 CornerBrace 與重新推導的衍生資料

#### Scenario: exact target source identity 不再唯一
- **WHEN** 恢復 Review 時 exact target source identity 已不存在、對應到多個 subjects，或不再唯一代表原修補目標
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 保留 candidate-based state 並要求重新處理

#### Scenario: 參考角撐後續改變
- **WHEN** exact target 仍有效，但保存的 selected automatic primary template 已改變、不存在或不再 compatible
- **THEN** 系統 MUST NOT 以目前最近的另一支 reference 代替
- **AND** SHALL 將修補標示為需要重新處理

#### Scenario: Local transfer 無法重建相同工程線
- **WHEN** 保存的 target relationship 仍存在，但依保存 template 與 transfer mode 重建的工程線不再符合 adopted world line 或 target evidence
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 保留重新辨識的 candidate-based state

#### Scenario: Legacy version 2 repair payload
- **WHEN** same-fingerprint paused Review 含有本 change 前建立、沒有 template-transfer fields 的 repair provenance
- **THEN** 系統 SHALL 依既有 adopted world line、target identities 及 reference eligibility 驗證 replay
- **AND** MUST NOT 自動重新選擇 nearest template 或重算其工程線

#### Scenario: Resume 後只剩 repaired references
- **WHEN** 保存修補的 secondary references 仍有效，但 selected automatic primary template 已失效或不存在
- **THEN** 系統 MUST NOT replay 該修補
- **AND** SHALL 要求使用者重新檢查，不得以 secondary reference chain 取代 primary template

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Reference 幾何只能作為一致性檢核

**Reason**: 人工修補的新產品規則要求 compatible automatic primary 的局部配置尺寸產生 candidate；原規則禁止 reference 影響端點與長度，與 FB7 類遮擋修補需求衝突。

**Migration**: Automatic recognition 仍沿用殘線中心軸與有限構件交點。只有使用者明確啟動的 STEP4 repair 改用 local reference template transfer，且必須保留 exact target evidence、finite target geometry、Preview 與 explicit Apply gates。
