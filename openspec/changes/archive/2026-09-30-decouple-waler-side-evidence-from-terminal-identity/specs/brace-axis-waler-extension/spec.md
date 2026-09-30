# Spec Delta

## 閱讀導航

- **必讀**：「Terminal evidence 必須單向支援 Waler contact-face 判定」Requirement；定義 Brace candidate side evidence 與 formal terminal identity 的分權。
- **條件式閱讀**：主規格的「延伸結果必須一致更新正式 Brace 連接」與「Y29 重疊 Waler 端點必須維持未解析」Requirements；修改 atomic commit、P02／P07 或 Y29 regression 時必讀。
- **可先跳過**：CornerBrace、Project schema、Solver 與材料規則；本 change 不修改這些 contract。

## REMOVED Requirements

### Requirement: Terminal evidence 必須單向支援 Waler contact-face 判定

**Reason**：既有 Requirement 將 ambiguous terminal 的 candidate direction 與正式 connection identity 視為同一 authority，無法表達「可提供方向、不得建立連接」及 unique-first precedence。

**Migration**：由「候選方向證據必須與正式連接 identity 分權」Requirement 取代；正式 Brace atomic commit 規則不變。

## ADDED Requirements

### Requirement: 候選方向證據必須與正式連接 identity 分權

每一個依既有 direct／axis-extension 資格成立的 Brace terminal-to-Waler candidate relation SHALL 可保存為只供該候選 Waler contact-face finalization 使用的 side-only evidence。端點層級唯一且合法的 terminal relation SHALL 另建立正式 identity evidence；即使同一 Brace 因另一端無解、ambiguous 或其他 member-level 條件失敗而整體 unresolved，該唯一 identity evidence 與其方向 evidence 仍 SHALL 保持有效。

若某端 ambiguous，系統 MUST 保留所有 competing Waler identities 並阻止該端建立正式 identity；但各合法 candidate relation 的非退化 Waler-to-member 方向 SHALL 可分別支援對應 Waler 的 contact-face 判定。Side-only evidence MUST NOT 建立 Brace 正式 endpoint、`FromWaler`／`ToWaler`、Candidate Point adoption、forbidden point、Project row 或 Solver input，也 MUST NOT 被解讀為 Brace 同時連接所有候選 Waler。

Waler contact-face finalization MUST 對同一 Waler 採 unique-first precedence：若存在任何可靠 unique direction evidence，Brace 的 competing side-only evidence MUST NOT 參與接觸側選擇；若其方向與 authoritative unique result 相反，系統 SHALL 保留 unique result 並產生不阻擋、可追溯至 Waler 與兩類 member sources 的 warning。只有該 Waler 沒有任何可靠 unique evidence 時，Brace competing side-only evidence 才可參與接觸側選擇。

Waler contact-face finalization SHALL 只消費目前 candidate／identity direction evidence 及既有 Waler envelope facts；其後建立的 member-level verdict 只控制 Brace 是否成為 formal member，MUST NOT 回頭新增、移除或改派 evidence，也 MUST NOT 影響已由 evidence 判定的 Waler contact face。資料依賴 MUST 維持 `terminal candidates -> Waler contact-face finalization -> Brace member-level verdict`，不得形成由 verdict 或已選 contact face 回饋候選 identity 的循環。

此 Requirement 是 DXF Recognition／Workflow contract，不改變 Waler envelope 規則、既有 candidate eligibility、Solver Preference 或 Project schema。

#### Scenario: Brace 整體 unresolved 仍保留唯一端側向 evidence

- **WHEN** Brace start 對 W16 具有唯一合法 terminal identity，而 end 因其他原因使整支 Brace unresolved
- **THEN** W16 contact-face finalization SHALL 仍可使用該 start direction evidence 判定 member-side
- **AND** Brace unresolved verdict MUST NOT 移除或降級該 evidence

#### Scenario: Ambiguous 端可提供不具連接權限的候選方向

- **WHEN** Brace end 同時對 W18 與 W19 形成無法區分的合法 terminal candidates，且兩個 candidate directions 各自非退化
- **THEN** 該 end SHALL 可分別為 W18 與 W19 建立 side-only evidence
- **AND** W18／W19 contact-face finalization SHALL 可各自使用該 evidence 判定支撐側
- **AND** Brace end MUST 維持 identity ambiguous，不得正式連到 W18 或 W19

#### Scenario: Ambiguous 端不得建立正式連接 identity

- **WHEN** Brace end 同時對 W18 與 W19 形成無法區分的 terminal candidates
- **THEN** 該 end MUST NOT 為 W18 或 W19 建立具有正式連接權限的 identity evidence
- **AND** 該 end SHALL 可為每一支合法候選 Waler 建立不具連接權限的 side-only evidence
- **AND** W18／W19 contact-face finalization SHALL 只可使用其方向語意，不得把它解讀為正式 Brace connection

#### Scenario: Unique evidence 優先於 Brace competing direction

- **WHEN** Waler A 已有指向上側的可靠 unique evidence，且 ambiguous Brace candidate 另對 A 提供指向下側的 competing side-only evidence
- **THEN** A SHALL 保留由 unique evidence 決定的上側正式接觸面
- **AND** competing evidence MUST NOT 使 A 變成 contact-face ambiguous
- **AND** 系統 SHALL 產生 warning 並保留 A、unique member sources 與 competing Brace sources 的 provenance

#### Scenario: Member-level verdict 不回饋 contact-face 判定

- **WHEN** candidate／identity direction evidence 已完成 Waler contact-face finalization，之後 Brace member-level verdict 因 identity ambiguity、交點、長度或另一端問題判定 unresolved
- **THEN** verdict MUST NOT 回頭改變任何 Waler contact face 或重新分配 evidence
- **AND** rebuild SHALL 從目前 active sources 重新依相同單向順序計算，而不是循環重試至某個 Brace 成為 formal

#### Scenario: Y29 B15 的唯一端與 ambiguous 端分流

- **WHEN** Y29 B15 start 唯一對應 W16，而 end 同時對應 W18 與 W19，且三支 Waler 的相關方向證據均合法且一致
- **THEN** W16 SHALL 可使用 B15 start identity direction evidence 完成其 contact-face 判定
- **AND** W18 與 W19 SHALL 可各自使用 B15 end 的 side-only evidence 完成其 contact-face 判定
- **AND** B15 整體 SHALL 維持 unresolved，P02 與 P07 均不得成為該 ambiguous end 的正式 endpoint

#### Scenario: Waler contact face 已完成仍不得繞過 Brace identity ambiguity

- **WHEN** 一個 ambiguous Brace end 的所有候選 Waler 均已由 side-only evidence 完成 formal contact face
- **THEN** Brace MUST 仍等到該端只剩唯一合法 identity 後才可進行 atomic formal commit
- **AND** 系統 MUST NOT 以已選 contact face、距離或候選順序挑選其中一支 Waler

