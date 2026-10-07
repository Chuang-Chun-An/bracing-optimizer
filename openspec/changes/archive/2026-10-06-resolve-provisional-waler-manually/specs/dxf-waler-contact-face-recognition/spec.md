# Spec Delta：人工正式線與自動接觸面 authority 分流

## 閱讀導航

- **必讀**：修改後的「Waler 接觸面必須依 unique-first evidence precedence 判定」；自動辨識仍使用原 precedence，只有專用且有效的人工正式化 decision 可提供另一種 contact-line authority。
- **必讀**：「Provisional axis 不得由一般確認動作升級」與新增的「專用人工修補建立正式接觸線」Scenarios；兩者共同界定使用者意圖。
- **條件式閱讀**：修改 overlap／terminal identity 時閱讀 W17／W20 與 formal contact face Scenarios；人工正式線不得解除 identity competition。
- **可先跳過**：代表寬度正交量測、HATCH／MLINE envelope 及一般 formal fixture Scenarios；本 change 不修改自動幾何規則。

## MODIFIED Requirements

### Requirement: Waler 接觸面必須依 unique-first evidence precedence 判定

除已通過 `dxf-waler-engineering-line-repair` capability 專用驗證與原子提交的人工正式化 decision 外，Waler 的 contact-face state SHALL 由目前 active candidate relations、完整 envelope 與 unique-first evidence precedence 決定。系統 MUST 先把非退化方向 evidence 分為 `unique` 與 `competing` 兩組：

- 若至少存在一筆可靠 unique evidence，接觸側 MUST 只由全部可靠 unique evidence 決定；competing evidence MUST NOT 參與選側。
- 若可靠 unique evidence 全部指向同一側，系統 SHALL 選出該側最外實體表面作為 formal contact face。方向相反的 competing evidence MUST NOT 推翻此結果或使 Waler 變成 contact-face ambiguous；系統 SHALL 產生 warning 類型的可追溯診斷。
- 若可靠 unique evidence 本身同時指向兩側，系統 MUST 將 Waler 判定為 contact-face ambiguous。
- 只有完全沒有可靠 unique evidence 時，系統才 SHALL 使用可靠 competing evidence；competing evidence 全部同側時可形成 formal contact face，同時指向兩側時 MUST 判定 contact-face ambiguous。
- unique 與 competing 皆無可靠方向時，Waler SHALL 維持 contact-face unresolved。

Unique／competing precedence 是 DXF Recognition Engineering Policy，不是票數權重或 Solver Preference。warning SHALL 為 deterministic、non-blocking，並至少保留 Waler source identity、決定結果的 unique member source identities，以及方向相反而被忽略的 competing member source identities；建議通用 code 為 `WALER_COMPETING_SIDE_EVIDENCE_IGNORED`。相同方向的 competing evidence不需產生此 warning。

當 Waler 因沒有可靠 evidence、authoritative evidence 兩側衝突、envelope ambiguity 或幾何退化而無法完成自動 finalization 時，系統 SHALL 保留 provisional axis 與完整 envelope 作為 staged recognition／diagnostic facts，且 MUST NOT 自動將 provisional axis 提交為正式接觸面、Project 或 Solver engineering line。只有使用者對 exact provisional Waler 明確執行專用人工正式化、選定有限線通過該 capability 的 validation 且 atomic commit 成功後，該人工線本身才 SHALL 取代目標 Waler 的自動 envelope／side outcome，成為 canonical formal contact face；它不必位於 envelope 外側邊，系統亦 MUST NOT 再依支撐側選擇另一條 outer face。

人工正式化後，unique-first precedence SHALL 只用於以人工線重建的 current terminal evidence之支撐側判斷：由 authoritative member body位於人工線哪一側建立 `support_normal_world`。若 authoritative evidence兩側衝突或完全沒有可靠 evidence，支撐側 SHALL 為 unknown；人工 contact face仍維持 formal，但後續接觸調整 SHALL 依既有 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋。自動 Waler仍依前述規則選擇支撐側最外實體表面，本人工例外不得改變自動流程。

Member identity competition 的 blocker 與 contact-face state MUST 分別維持；不論 formal contact line 來自自動 finalization 或人工正式化，均 MUST NOT 解除 identity ambiguity或挑選 connection winner。一般 confirmation、Preview selection、顯示狀態及沒有明確正式化意圖的 legacy manual geometry MUST NOT 建立人工 contact-line authority。

#### Scenario: Unique evidence 與 conflicting competing evidence

- **WHEN** Waler A 具有指向上側的可靠 unique evidence，且另有指向下側的可靠 competing evidence
- **THEN** A SHALL 維持由 unique evidence 決定的上側 formal contact face
- **AND** A MUST NOT 因 competing evidence 變成 contact-face ambiguous
- **AND** 系統 SHALL 產生 non-blocking warning，定位 A、unique evidence sources 與 conflicting competing evidence sources

#### Scenario: 只有 competing evidence 且全部同側

- **WHEN** Waler A 沒有任何可靠 unique evidence，且所有可靠 competing evidence 均指向同一側
- **THEN** A SHALL 採用該側最外實體表面作為 formal contact face
- **AND** competing terminal identities SHALL 維持 unresolved，不得建立正式 connection

#### Scenario: 只有 competing evidence 且同時指向兩側

- **WHEN** Waler A 沒有任何可靠 unique evidence，且可靠 competing evidence 同時指向上側與下側
- **THEN** A SHALL 判定為 contact-face ambiguous
- **AND** 系統 MUST NOT 以票數、輸入順序或距離微差任選一側

#### Scenario: Unique evidence 本身同時指向兩側

- **WHEN** Waler A 的可靠 unique evidence 同時指向上側與下側
- **THEN** A SHALL 判定為 contact-face ambiguous
- **AND** competing evidence MUST NOT 用來打破該 authoritative conflict

#### Scenario: W17 與 W20 的 identity 與 contact face 分別判定

- **WHEN** Y29 W17（source `69C`）與 W20（source `721`）同時是某些 terminal 的 competing identities
- **THEN** 受影響 terminals SHALL 維持 identity ambiguous，overlap competition SHALL 維持 blocking，Review MUST NOT 完成
- **AND** W17 與 W20 SHALL 各自依 unique-first precedence 判定 formal／ambiguous／unresolved contact-face state

#### Scenario: Formal contact face 不解除 identity competition

- **WHEN** Waler A／B 均完成 formal contact face，而同一 terminal 仍直接列出 A、B 為 competing identities
- **THEN** 該 terminal 與 A／B overlap competition SHALL 維持 blocking
- **AND** formal contact faces MUST NOT 被用來挑選 A 或 B 作為 connection winner

#### Scenario: 既有 formal fixtures 維持正式結果

- **WHEN** 以目前 Y05、Y1A 與一般 CAD fixtures 執行 Waler contact-face recognition
- **THEN** 原本 formal 的 Waler SHALL 在 unique-first precedence 下全部維持 formal
- **AND** 其 selected outer face 與既有唯一 connection identities SHALL 保持幾何等價

#### Scenario: Provisional axis 不得由確認動作升級

- **WHEN** Waler 的 identity／contact-face blocking ambiguity 仍存在，且使用者沒有完成專用人工正式化
- **THEN** 使用者確認、Preview 選取或顯示狀態 MUST NOT 將 provisional axis 升級為正式接觸面

#### Scenario: 專用人工修補建立正式接觸線

- **WHEN** 一支 provisional Waler 的自動 envelope／contact-face outcome 無法唯一提交，但使用者已對 exact source 完成專用人工正式化
- **THEN** 選定人工線本身 SHALL 成為該 Waler 的 canonical formal contact face，即使它不在 envelope 外側邊
- **AND** 自動 unique-first outcome MUST NOT 再為同一 Waler 建立另一條正式接觸線

#### Scenario: 人工接觸線同側證據建立 support normal

- **WHEN** 系統已依人工接觸線重建 terminal evidence，且 authoritative member bodies依既有 unique-first precedence全部位於同一側
- **THEN** 系統 SHALL 建立指向該側的 `support_normal_world`
- **AND** MUST NOT 將 support side判斷結果用來替換人工 contact face

#### Scenario: 人工接觸線兩側衝突或無證據

- **WHEN** 以人工接觸線重建後的 authoritative evidence分布兩側，或完全沒有可靠 terminal evidence
- **THEN** `support_normal_world` SHALL 為 unknown，人工 contact face SHALL 維持 formal
- **AND** 後續背填／寬度調整 MUST 依 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋，不得猜測方向

#### Scenario: 人工正式接觸線不解除 competing identity

- **WHEN** Waler A 已由人工正式化取得 formal contact line，但某 member terminal 仍同時以 A 與 Waler B 為 competing identities
- **THEN** 該 terminal identity ambiguity 與任何直接 overlap competition SHALL 維持 blocking
- **AND** 人工 decision MUST NOT 被用來選擇 A 作為 winner

#### Scenario: 一般非重疊 Waler 維持既有正式結果

- **WHEN** 一支非重疊 Waler 具有唯一 terminal identity 與可靠側向證據
- **THEN** 系統 SHALL 依既有規則選出支撐側最外實體表面
- **AND** 本 change MUST NOT 改變其正式接觸面或 connection identity

#### Scenario: Generic unresolved 不證明 overlap competition

- **WHEN** Waler A／B 具有重大重疊 warning，而某 contact-face outcome 是 unresolved，但沒有在同一 finalization context 明確列出 A、B 兩個完整 source identities 為 competitors
- **THEN** 該 outcome MUST NOT 被用來建立 A／B 的 blocking competition error
- **AND** A／B 的 formal／provisional state SHALL 仍由各自實際 contact-face resolution outcome 或有效人工正式化 decision 決定
