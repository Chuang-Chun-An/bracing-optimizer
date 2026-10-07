# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：本 delta 的兩項 `MODIFIED Requirements`；它們只校正 `reference_template` 與 `body_relationship_selection` 的文字適用範圍，不改變 runtime 行為。
- **實作前閱讀**：不適用；本 change 不修改程式碼、測試或主規格，主規格由後續 archive 合併本 delta。
- **需要時再讀**：若需追溯完整上下文，再讀 `openspec/specs/dxf-corner-brace-repair-tool/spec.md` 的同名 Requirements，以及本 change 的 `proposal.md`、`design.md` 與 `tasks.md`。

## MODIFIED Requirements

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

### Requirement: 修補決策必須可追溯且安全重播

新採用的修補 MUST 記錄 exact target source identity、採用的 world engineering line、目標 Waler／Strut、selection source 與 selection mode。`reference_template` 修補 MUST 另外記錄被選用的 automatic primary template identity、transfer mode、reference local Waler offset、reference Strut inward station，以及參與驗證的 manual repaired secondary identities；其他符合 eligibility 但未被選為 template 的 automatic primaries MAY 記錄為 validation evidence，但不得與 selected template 混淆。`body_relationship_selection` 修補 MUST 另外記錄可唯一核對的 body signature 與被選用的 target relationship identities，且 MUST NOT 要求 selected template、template local transfer 或 secondary reference fields。

相同 DXF fingerprint 的 Pause／Resume 重新辨識 MUST 先確認 exact target subject、保存的 target Waler／Strut 與 adopted world line 仍可唯一核對。`reference_template` 只有在 selected automatic primary template、transfer mode、局部尺寸與 adopted world line 仍能唯一重建並通過現行檢核時才可重播。`body_relationship_selection` 只有在保存的 body signature、exact active target relationship identities 與 adopted world line 仍能唯一核對並通過該模式的現行檢核時才可重播，且不得為了完成 replay 改選 template 或新的 target relationship。任一模式無法滿足其 replay 條件時，系統 MUST 保留 candidate-based state 並要求重新修補。既有不含 template-transfer fields 的 version 2 repair payload MUST 保持可讀，並以其保存的 adopted world line、target identities 與 references 走既有安全 replay；不得因本 change 靜默套用新的 reference selection。

#### Scenario: 相同來源安全重播
- **WHEN** paused Review 以相同 source fingerprint 恢復，selection mode 為 `reference_template`，exact target、target relationship 與 selected template identities 唯一存在，且保存的 transfer 可重建相同 adopted world line
- **THEN** 系統 SHALL 恢復修補後的正式 CornerBrace 與重新推導的衍生資料

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
