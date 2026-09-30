# Spec Delta

## 閱讀導航

- **必讀**：「Unresolved Waler 不得產生正式接觸面」Requirement；定義 provisional axis、正式工程線與 contact-resolution provenance 的 truth boundary。
- **條件式閱讀**：「排除競爭來源後必須重新 finalization」Requirement；修改 exclusion、rebuild 或 contact-face resolution 時必讀。
- **可先跳過**：重疊比例與 warning qualification；由 `dxf-waler-overlap-diagnostics` capability 定義。

## ADDED Requirements

### Requirement: Unresolved Waler 不得產生正式接觸面

當 Waler 因 member-to-Waler identity competition 或 contact-face ambiguity 尚未完成 finalization 時，系統 SHALL 保留來源支持的 provisional axis 與完整 envelope 作為 staged recognition／diagnostic facts，但 MUST 明確標記其 contact-face state 為 unresolved。該 provisional axis MUST NOT 被宣告、投影或提交為支撐側最外正式接觸面，也不得成為 completed Project 或 Solver 的 Waler engineering line。

若兩支重大重疊 Waler 對相同 terminals 形成競爭關係，兩支 Waler 的 provisional axes 均 SHALL 維持 unresolved，直到目前 active facts 能唯一決定各自關係與接觸面。既有 blocking Review semantics MUST 維持，使用者不得只確認 provisional axis 就繞過 identity ambiguity。

Formal／provisional state SHALL 只由目前 contact-face resolution outcome 決定。Contact-resolution outcome 若要作為 overlap competition 的 blocking provenance，MUST 明確識別同一 finalization context，並同時列出該 overlap pair 的兩個完整 Waler source identities 為實際 competitors。只有 unresolved code、provisional state、附近幾何或只列出其中一方 identity 的 outcome MUST NOT 被解讀為該 pair 的 direct competition evidence。

#### Scenario: W17 與 W20 同時存在時只保留 provisional truth

- **WHEN** Y29 W17（source `69C`）與 W20（source `721`）同時存在，且 terminal-to-Waler identities 無法唯一判定
- **THEN** 兩支 Waler SHALL 保留各自來源支持的 provisional axis 與 envelope 作為 Review facts
- **AND** 兩支 provisional axes MUST NOT 成為正式接觸面或 completed Project／Solver engineering line
- **AND** Review MUST 維持 blocked

#### Scenario: Provisional axis 不得由確認動作升級

- **WHEN** Waler 的 identity／contact-face blocking ambiguity 仍存在
- **THEN** 使用者確認、Preview 選取或顯示狀態 MUST NOT 將 provisional axis 升級為正式接觸面

#### Scenario: 一般非重疊 Waler 維持既有正式結果

- **WHEN** 一支非重疊 Waler 具有唯一 terminal identity 與可靠側向證據
- **THEN** 系統 SHALL 依既有規則選出支撐側最外實體表面
- **AND** 本 change MUST NOT 改變其正式接觸面或 connection identity

#### Scenario: Generic unresolved 不證明 overlap competition

- **WHEN** Waler A／B 具有重大重疊 warning，而某 contact-face outcome 是 unresolved，但沒有在同一 finalization context 明確列出 A、B 兩個完整 source identities 為 competitors
- **THEN** 該 outcome MUST NOT 被用來建立 A／B 的 blocking competition error
- **AND** A／B 的 formal／provisional state SHALL 仍由各自實際 contact-face resolution outcome 決定

#### Scenario: Contact finalization 明確保留兩方 competing identities

- **WHEN** 同一 contact-face finalization outcome 明確列出重大重疊 Waler A、B 的完整 source identities 為實際 competitors
- **THEN** 該 outcome SHALL 可作為 A／B competition 的 direct provenance
- **AND** A、B SHALL 維持 provisional，直到目前 active facts 能唯一 finalization

### Requirement: 排除競爭來源後必須重新 finalization

當 source exclusion 使重疊競爭 pair 只剩一支 active Waler 時，系統 SHALL 由目前 active member facts 從零重建 terminal relationships 與 contact-face finalization。若剩餘 Waler 具有唯一關係與可靠支撐／斜撐側向證據，系統 SHALL 將支撐側最外實體表面採用為正式 engineering line；不得沿用重疊期間的 provisional axis、stale ambiguity 或另一支已排除 Waler 的 identity。

#### Scenario: 排除 W17 後 W20 採用支撐側最外表面

- **WHEN** source `69C` 被排除且 source `721` 的剩餘關係與側向證據唯一
- **THEN** source `721` SHALL 採用其支撐側最外實體表面為正式 engineering line
- **AND** MUST NOT 保留重疊期間的 provisional centerline 作為正式結果

#### Scenario: 排除 W20 後 W17 採用支撐側最外表面

- **WHEN** source `721` 被排除且 source `69C` 的剩餘關係與側向證據唯一
- **THEN** source `69C` SHALL 採用其支撐側最外實體表面為正式 engineering line
- **AND** MUST NOT 保留重疊期間的 provisional centerline 作為正式結果

#### Scenario: 還原競爭來源使正式狀態重新評估

- **WHEN** 已排除的重疊 Waler source 被還原並再次造成 terminal identity competition
- **THEN** 系統 SHALL 重新產生 unresolved contact-face outcomes
- **AND** MUST NOT 沿用排除期間建立的唯一關係或正式接觸面

