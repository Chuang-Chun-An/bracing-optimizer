# Spec Delta

## ADDED Requirements

### Requirement: 角撐修補決策不得跨內容靜默轉移

系統 SHALL 將已採用的角撐修補視為與 exact target source identity、人工採用工程線及明確 Waler／Strut 關係綁定的人工決策。`EXACT_MATCH` Relink MUST 完整保留該修補 state。候選 DXF fingerprint 不同時，compatible recovery MUST 以候選重新辨識結果為基底，且 MUST NOT 依一般 critical-member geometry matching 或相同／相近位置，自動把舊角撐修補效果轉移到候選來源。

若 changed-content 候選仍存在相同角色與 exact source identity 的可處理角撐 subject，舊修補決策 SHALL 不套用並分類為 `requires_review`；若 exact source identity 不再存在、角色改變或無法定位可處理 subject，該舊修補決策 SHALL 分類為 `disabled`。兩種分類都不得讓舊修補幾何影響 recovered engineering state。

任何在 compatible recovery 中分類為 `requires_review` 或 `disabled` 的 repaired CornerBrace decision MUST NOT 成為其他 CornerBrace repair 的 primary 或 secondary reference。只有使用者在 recovered Review 重新完成修補、明確採用並使其符合現行 secondary eligibility 後，它才可作為 secondary reference；compatible recovery 不得自動恢復 reference eligibility。

#### Scenario: Exact Match 保留角撐修補
- **WHEN** paused Review 透過 `EXACT_MATCH` 候選重新連結來源
- **THEN** 系統 SHALL 與其他既有 Review state 一起完整保留已採用的角撐修補
- **AND** SHALL NOT 重新辨識或要求第二次修補確認

#### Scenario: changed-content 候選保留 exact subject
- **WHEN** compatible recovery 的候選內容不同，但相同角色與 exact source identity 的角撐 subject 仍存在
- **THEN** 系統 MUST 以候選辨識幾何保留該 subject
- **AND** MUST NOT 套用舊修補效果
- **AND** SHALL 將該修補 decision 分類為 `requires_review`

#### Scenario: changed-content 候選失去 exact subject
- **WHEN** compatible recovery 的候選內容不同，且角撐修補的 exact source identity 不再存在、角色改變或無法定位可處理 subject
- **THEN** 系統 MUST 不套用舊修補效果
- **AND** SHALL 將該修補 decision 分類為 `disabled`

#### Scenario: geometry-only match 不轉移修補
- **WHEN** 舊修補來源可在候選中找到幾何相近但 source identity 不同的角撐
- **THEN** 系統 MUST NOT 將舊 repaired axis、目標 Waler／Strut 或 reference provenance 轉移至該角撐
- **AND** recovered Review SHALL 維持 candidate-based engineering state

#### Scenario: Requires-review repair 不得提供 reference evidence
- **WHEN** compatible recovery 將一筆舊 CornerBrace repair 分類為 `requires_review`
- **THEN** recovered Review MUST NOT 將該舊 repair 當作後續 repair 的 primary 或 secondary reference
- **AND** 使用者必須先在 recovered Review 重新建立並確認合法 repair，才能恢復 secondary eligibility
