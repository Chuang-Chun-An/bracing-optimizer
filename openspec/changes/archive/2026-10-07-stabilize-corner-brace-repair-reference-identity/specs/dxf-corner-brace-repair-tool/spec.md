# dxf-corner-brace-repair-tool Spec Delta

## 閱讀導航

- **必讀**：本文件「修補決策必須可追溯且安全重播」、「顯示 member ID 重編但 stable reference 未變」、「Target顯示編號位移但source identity未變」與「CornerBrace confirmation只發生顯示編號位移」情境；先確認顯示 ID 不再決定reference或confirmation是否仍有效。
- **條件式閱讀**：實作 reference eligibility 或 replay safety 時，再讀主規格「參考角撐必須分級並阻止推測鏈」及本 Requirement 的零筆／多筆 match、幾何或 connection 改變情境。
- **條件式閱讀**：涉及 Pause／Resume 或 Relink 時，再讀 `paused-dxf-review-source-relink` 的「角撐修補決策不得跨內容靜默轉移」；stable matching 不得成為 changed-content recovery 套用舊 repair 的理由。
- **可先跳過**：目標殘線候選生成、body relationship selection、Preview UI、候選 ranking、Solver、材料與 Project schema；本 change 不修改這些行為。

## MODIFIED Requirements

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
