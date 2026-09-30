# Spec Delta

## 閱讀導航

- **必讀**：「競爭關係必須升級為 blocking error」Requirement；確認 overlap competition 持續阻擋正式連接，但不再強迫 contact-face state 與 identity state 綁定。
- **條件式閱讀**：主規格的「重大共線重疊必須產生來源診斷」與「診斷必須隨 Review truth 重建」Requirements；修改 50% overlap qualification 或 lifecycle 時才需閱讀。
- **可先跳過**：Waler envelope extraction、Brace endpoint 計算、Project／Solver 與 Preview 樣式；它們不由本 capability 決定。

## MODIFIED Requirements

### Requirement: 競爭關係必須升級為 blocking error

重大共線重疊 warning 本身 SHALL 不自動阻擋 Review。系統只有在既有 terminal topology issue 或 contact-resolution outcome 提供 direct identity provenance，明確證明 overlap pair 的兩個完整 Waler source identities 同時是同一 terminal 或同一 contact-face finalization 的實際 competing identities 時，才 MUST 另外產生 `WALER_OVERLAP_COMPETITION` blocking error。Blocking error SHALL 定位重疊 pair、同一 terminal／finalization identity 與受影響 terminal sources，並維持既有 terminal identity ambiguity。

Overlap competition 與 Waler contact-face state MUST 分別判定。Competition SHALL 持續阻止 ambiguous terminal 建立正式 connection，但 MUST NOT 僅因 identity 多解就強迫兩支 Waler 保持 `WALER_CONTACT_FACE_UNRESOLVED`；每支 Waler SHALL 依其目前可靠 side evidence 與 envelope outcome 獨立成為 formal 或 provisional。Formal contact face MUST NOT 反過來解除 competition、挑選 identity winner 或建立正式 member connection。

系統 MUST NOT 以「有 overlap 且附近或同批存在 unresolved outcome」推論 identity competition，也 MUST NOT 將另一組 identities 的 competition 歸因至目前 overlap pair。Generic unresolved、缺少兩方完整 identity provenance 的 contact-resolution issue，或只列出 overlap pair 其中一方的 evidence，均不足以升級 warning。系統亦 MUST NOT 以 Waler ID、handle、entity order、距離微差、lexical ordering、first match、formal contact-face state 或既有 Preview 選取狀態解除競爭。沒有 direct pair provenance 的重大共線重疊 SHALL 保留 warning-only。

#### Scenario: Y29 W17 與 W20 形成競爭關係
- **WHEN** Y29 W17（source `69C`）與 W20（source `721`）同時存在，且其重大共線重疊使既有 member terminals 對兩個 identities 形成等價合法關係
- **THEN** 系統 SHALL 產生 W17／W20 重疊 warning 與 blocking competition error
- **AND** SHALL 維持受影響 terminals 的 identity ambiguity
- **AND** W17 與 W20 的 contact-face state SHALL 分別由各自目前 side evidence 決定
- **AND** Review MUST NOT 完成

#### Scenario: 重疊但沒有 terminal competition
- **WHEN** 兩支 Waler 符合重大共線重疊資格，但沒有任何 terminal identity 或 contact-face outcome 因此變成多解
- **THEN** 系統 SHALL 保留重大重疊 warning
- **AND** MUST NOT 僅因重疊幾何阻擋 Review

#### Scenario: A B 重疊但 unresolved 由其他原因造成
- **WHEN** Waler A／B 形成重大共線重疊，而附近或同批存在 unresolved contact-face outcome，但該 outcome 沒有明確列出 A、B 同時競爭同一 terminal 或 finalization
- **THEN** 系統 SHALL 保留 A／B overlap warning
- **AND** MUST NOT 建立 A／B 的 `WALER_OVERLAP_COMPETITION`

#### Scenario: A B 重疊但實際競爭者是 A C
- **WHEN** Waler A／B 形成重大共線重疊，但 direct identity provenance 明確列出的同一 terminal／finalization competitors 是 A／C 而不是 A／B
- **THEN** 系統 SHALL 保留 A／B overlap warning
- **AND** MUST NOT 將 A／B 標示為 blocking pair
- **AND** A／C 是否 blocking SHALL 取決於 A／C 自身是否具有合格 overlap fact 與相符 direct provenance

#### Scenario: A B 被同一 terminal 明確列為 competitors
- **WHEN** Waler A／B 形成重大共線重疊，且同一 terminal 的 direct identity provenance 明確將 A、B 的完整 source identities 同時列為實際 competitors
- **THEN** 系統 SHALL 產生 A／B overlap warning 與 `WALER_OVERLAP_COMPETITION` blocking error
- **AND** blocking error SHALL 定位同一 terminal 與 A、B 兩方 source identities
- **AND** A、B 即使都具有 formal contact face也不得因此解除 blocking error

#### Scenario: Competition join 不受 input 與 source 順序影響
- **WHEN** 相同 overlap facts 與 direct competition provenance 交換 Waler input order、source order、axis endpoint order 或 competing identity collection order
- **THEN** warning／blocking qualification、pair identity、受影響 terminal 與可完成狀態 SHALL 保持等價
- **AND** 系統 MUST NOT 以任何排序挑選 winner

#### Scenario: 不得自動挑選重疊 Waler
- **WHEN** 兩支重大重疊 Waler 同時是某 terminal 的合法候選
- **THEN** 系統 MUST NOT 自動合併、刪除、改名或選擇其中一支
- **AND** MUST NOT 由 Waler ID、handle、entity order、距離微差、first match 或 formal contact-face outcome 建立正式關係

