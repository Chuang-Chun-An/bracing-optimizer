# Spec Delta

## 閱讀導航

- **必讀**：「接觸面選擇必須先建立 member-to-Waler 關係」、「支撐側必須由 member 軸線朝構件本體的方向判定」與「Unresolved Waler 不得產生正式接觸面」Requirements；三者共同定義 candidate relation、side-only evidence 與 formal connection 的權限邊界。
- **條件式閱讀**：「排除競爭來源後必須重新 finalization」Requirement；修改 exclusion／restore、Pause／Resume 或 rebuild 時必讀。
- **可先跳過**：Waler envelope extraction、HATCH RC Waler、Project persistence 與 Solver 規則；本 change 不修改那些 contract。

## MODIFIED Requirements

### Requirement: 接觸面選擇必須先建立 member-to-Waler 關係

系統 MUST 先使用已完成的 immutable recognition facts 與 provisional Waler geometry，建立 Strut／Brace terminal 與每一支合法候選 Waler source identity 的 candidate relation，再使用該 relation 所提供的方向證據判定各 Waler 的接觸側。Candidate relation 只證明該 terminal 依既有幾何資格可能接近或連到該 Waler，並提供從該 Waler 朝 member 本體的方向；它 MUST NOT 單獨建立正式 terminal identity、endpoint 或 connection。

當同一 terminal 只有一個合法候選時，系統 SHALL 另建立既有的唯一 terminal identity evidence。當同一 terminal 有兩個以上無法唯一區分的合法候選時，系統 MUST 保留所有 competing identities、產生既有 blocking ambiguity，且 MUST NOT 選擇 winner；但每個合法候選 relation 仍可各自提供只供該 Waler contact-face finalization 使用的 side-only evidence。

不同 Waler source identity 即使平行、鄰近或 source geometry 部分重疊，也不得因接觸面選擇而被自動合併、替換或刪除。已由可靠 upstream context 唯一決定的 Waler source identity MUST 被保留；下游 contact-face finalization 只能解析該 identity 的正式表面，不得因另一支 Waler 較接近某個已投影 endpoint 而改派來源。

#### Scenario: BIM Strut 保留已選 Waler identity
- **WHEN** BIM Strut recognition 已以有限 provisional Waler context 唯一選定兩端 Waler source identities
- **THEN** 接觸面 finalization MUST 在相同 identities 上解析正式表面
- **AND** MUST NOT 因鄰近 Waler 到既有 endpoint 的距離更小而替換 identity

#### Scenario: 鄰近 Waler 不因接觸面決策被合併
- **WHEN** W7 與 W12 是不同 source identities 且彼此鄰近
- **THEN** 系統 MUST 分別保留兩支 Waler
- **AND** 接觸面決策 MUST NOT 自動合併、刪除或重新命名任一 Waler

#### Scenario: Terminal-to-Waler 關係不唯一
- **WHEN** 一個尚未具有可靠 Waler identity 的 member terminal 對 provisional geometry 存在兩個無法唯一區分的合法 candidate relations
- **THEN** 系統 MUST 回報包含該 terminal 與所有 competing identities 的 blocking ambiguity
- **AND** MUST NOT 以 Waler ID、DXF handle、entity order、collection order或 contact-face 結果任選正式連接
- **AND** 每個合法 candidate relation SHALL 可保留只供其候選 Waler 使用的 side-only evidence

#### Scenario: Side-only evidence 不建立正式連接
- **WHEN** 一個 ambiguous terminal 的 candidate relation 已協助某支 Waler 選出正式接觸面
- **THEN** 該 terminal MUST 仍維持 identity unresolved
- **AND** 該 evidence MUST NOT 建立或修改正式 endpoint、`FromWaler`、`ToWaler`、Candidate Point adoption、forbidden point、Project row 或 Solver input

### Requirement: 支撐側必須由 member 軸線朝構件本體的方向判定

對已建立 candidate relation 或唯一 identity relation 的 terminal，系統 MUST 以 provisional Waler 交會位置及 member 來源支持軸線，取得由該候選 Waler 朝 member 本體／另一端的方向，並以此方向判定該 Waler 的支撐側。member start/end 表示反轉不得改變結果。

系統 MUST NOT 以已完成 provisional projection 的 endpoint 到候選表面的最短距離、最接近數個全域 endpoints 的距離總和、所有 framing endpoints 的 centroid、浮點微差或 source entity order 決定支撐側。只有依既有 terminal candidate 資格與該 Waler 建立 relation 的 member evidence 才可參與；無關、僅在附近或未符合既有 candidate 資格的構件不得作為全域投票點。Candidate relation 的建立 MUST NOT 放寬既有 direct／axis-extension 幾何邊界或 tolerance。

#### Scenario: Endpoint 已投影到 Waler reference axis
- **WHEN** member endpoint 已位於 provisional Waler reference axis，使兩側最外表面到 endpoint 的距離相同
- **THEN** 系統 MUST 仍由 member 軸線朝構件本體的方向選出支撐側
- **AND** MUST NOT 由相等距離的浮點表示差決定結果

#### Scenario: Member start/end 反轉
- **WHEN** 同一 member 的 start/end 表示反轉，但 WCS 軸線、candidate relations 與構件本體位置等價
- **THEN** 系統 MUST 得到相同的 Waler 支撐側、等價正式接觸面與相同 identity ambiguity

#### Scenario: 無關構件不影響 Waler
- **WHEN** DXF 中新增、移除或重排一支未與目標 Waler 建立合法 terminal candidate relation 的 Strut／Brace
- **THEN** 目標 Waler 的接觸側 MUST 保持不變

#### Scenario: 同一 terminal 對兩支候選 Waler 提供同側方向
- **WHEN** 一個 terminal 對 Waler A 與 Waler B 形成無法唯一區分的合法 candidate relations，且從 A、B 各自的 provisional axis 朝 member 本體均可得到可靠方向
- **THEN** A 與 B SHALL 各自取得可追溯至該 terminal 的 side-only evidence
- **AND** 兩份 evidence MUST NOT 被解讀為該 terminal 同時正式連接 A 與 B

#### Scenario: 退化方向不得作為 side evidence
- **WHEN** 某 candidate relation 的 Waler-to-member body vector 對該 Waler 法向分量絕對值 `<= endpoint_tolerance_mm`
- **THEN** 該 relation MUST NOT 參與該 Waler 的接觸側選擇
- **AND** 系統 SHALL 保留既有無可靠側向證據的 failure semantics

## REMOVED Requirements

### Requirement: Unresolved Waler 不得產生正式接觸面

**Reason**：既有 Requirement 把所有方向 evidence 視為同一層級，且 scenario 名稱仍帶有「identity competition 必然 provisional」的舊語意，無法表達 unique-first precedence。

**Migration**：由「Waler 接觸面必須依 unique-first evidence precedence 判定」Requirement 取代；identity blocking、provisional geometry 與 Project／Solver boundary 均保留。

### Requirement: 排除競爭來源後必須重新 finalization

**Reason**：既有 Requirement 的 restore scenarios 重複，且沒有明確要求 rebuild 後重新套用 unique-first precedence。

**Migration**：由「競爭來源變更後必須重建方向與 identity 狀態」Requirement 取代；active-source rebuild 與不得沿用 stale outcome 的 contract 不變。

## ADDED Requirements

### Requirement: Waler 接觸面必須依 unique-first evidence precedence 判定

Waler 的 contact-face state SHALL 由目前 active candidate relations、完整 envelope 與 unique-first evidence precedence 決定。系統 MUST 先把非退化方向 evidence 分為 `unique` 與 `competing` 兩組：

- 若至少存在一筆可靠 unique evidence，接觸側 MUST 只由全部可靠 unique evidence 決定；competing evidence MUST NOT 參與選側。
- 若可靠 unique evidence 全部指向同一側，系統 SHALL 選出該側最外實體表面作為 formal contact face。方向相反的 competing evidence MUST NOT 推翻此結果或使 Waler 變成 contact-face ambiguous；系統 SHALL 產生 warning 類型的可追溯診斷。
- 若可靠 unique evidence 本身同時指向兩側，系統 MUST 將 Waler 判定為 contact-face ambiguous。
- 只有完全沒有可靠 unique evidence 時，系統才 SHALL 使用可靠 competing evidence；competing evidence 全部同側時可形成 formal contact face，同時指向兩側時 MUST 判定 contact-face ambiguous。
- unique 與 competing 皆無可靠方向時，Waler SHALL 維持 contact-face unresolved。

Unique／competing precedence 是 DXF Recognition Engineering Policy，不是票數權重或 Solver Preference。warning SHALL 為 deterministic、non-blocking，並至少保留 Waler source identity、決定結果的 unique member source identities，以及方向相反而被忽略的 competing member source identities；建議通用 code 為 `WALER_COMPETING_SIDE_EVIDENCE_IGNORED`。相同方向的 competing evidence不需產生此 warning。

當 Waler 因沒有可靠 evidence、authoritative evidence 兩側衝突、envelope ambiguity 或幾何退化而無法完成 finalization 時，系統 SHALL 保留 provisional axis 與完整 envelope 作為 staged recognition／diagnostic facts，且 MUST NOT 將 provisional axis 提交為正式接觸面、Project 或 Solver engineering line。Member identity competition 的 blocker 與 contact-face state MUST 分別維持；formal contact face MUST NOT 解除 identity ambiguity或挑選 connection winner。

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
- **WHEN** Waler 的 contact-face ambiguity 或 unresolved outcome 仍存在
- **THEN** 使用者確認、Preview 選取或顯示狀態 MUST NOT 將 provisional axis 升級為正式接觸面

#### Scenario: Generic unresolved 不證明 overlap competition
- **WHEN** Waler A／B 具有重大重疊 warning，而某 contact-face outcome 是 unresolved，但沒有 direct provenance 明確列出 A、B 同時競爭
- **THEN** 該 outcome MUST NOT 被用來建立 A／B 的 blocking competition error

### Requirement: 競爭來源變更後必須重建方向與 identity 狀態

當 source exclusion／restore 改變重疊 pair 或 terminal candidates 時，系統 SHALL 由目前 active facts 從零重建 candidate relations、identity states、unique／competing evidence groups、warnings 與 contact-face outcome，並重新套用 unique-first precedence。系統 MUST NOT 沿用 stale candidate、排除前 warning、另一支已排除 Waler 的 identity 或先前 contact-face outcome。

#### Scenario: 排除 W17 後 W20 重新套用 precedence
- **WHEN** source `69C` 被排除並重新辨識 Y29
- **THEN** source `721` SHALL 只依目前 active evidence 重新套用 unique-first precedence
- **AND** MUST NOT 沿用 source `69C` 的 identity、evidence 或 warning

#### Scenario: 排除 W20 後 W17 重新套用 precedence
- **WHEN** source `721` 被排除並重新辨識 Y29
- **THEN** source `69C` SHALL 只依目前 active evidence 重新套用 unique-first precedence
- **AND** MUST NOT 沿用 source `721` 的 identity、evidence 或 warning

#### Scenario: 還原競爭來源後重建兩種狀態
- **WHEN** 已排除的重疊 Waler source 被還原並再次造成 terminal identity competition
- **THEN** 系統 SHALL 重新建立 blocking identity ambiguity 與目前 candidate relations
- **AND** 每支 Waler SHALL 依重建後 unique-first evidence重新判定 formal／ambiguous／unresolved contact-face state及 warning
- **AND** MUST NOT 沿用排除期間建立的唯一 connection identity 或 stale contact-face outcome

