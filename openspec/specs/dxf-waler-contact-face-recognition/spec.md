# dxf-waler-contact-face-recognition Specification

## Purpose
本 capability 定義 DXF Import 在各構件完成來源辨識後，如何以同一套幾何與關係語意判定 Waler 的支撐側及最外實體接觸面，使一般 CAD、BIM Block 與 HATCH RC Waler 不因來源畫法不同而產生不同正式工程線。

## Requirements

### Requirement: Waler 接觸面語意不得依賴來源畫法

系統 MUST 對一般 CAD、BIM Block 與 HATCH RC Waler 使用相同的 Waler 支撐側及接觸面規則。不同來源路徑可以用不同方式產生可靠的 Waler source geometry 與 member recognition facts，但 MUST NOT 以來源類型選擇不同的內外側規則。

Waler、Strut 與 Brace MUST 先各自完成其來源辨識；Waler 接觸面只能在 downstream relationship／canonical finalization 中決定。該 finalization MUST NOT 反向改變 component-like classification、recognition winner、來源支持的工程軸、代表寬度、role 或 root provenance。

#### Scenario: 等價 CAD 與 BIM 幾何得到相同接觸面
- **WHEN** 一般 CAD 與 BIM Block 以不同 source primitives 表示等價的 Waler envelope 與同側支撐關係
- **THEN** 系統 MUST 選出幾何等價的正式 Waler 接觸面
- **AND** MUST NOT 因 Strut／Brace 的來源辨識路徑不同而改選另一側

#### Scenario: 接觸面 finalization 不改變來源辨識
- **WHEN** downstream finalization 成功選出或無法選出唯一 Waler 接觸面
- **THEN** 已完成的 Waler、Strut 與 Brace recognition outcome MUST 保持不變
- **AND** 系統 MUST NOT 重新執行 recognition 以迎合接觸面結果

### Requirement: Waler 來源辨識必須保留完整構件 envelope

對具有可靠實體寬度的 Waler，系統 MUST 先證明 boundary evidence 共同支持單一 Waler component，形成 qualified component scope，才可在該 scope 內保留 provisional reference axis、完整橫向 envelope，以及 envelope 兩側可證明的最外實體表面。同 layer、同一 GeometryGroup、端點相接、彼此平行、長度相近或 longitudinal coverage 重疊，均不足以單獨證明多條 boundary evidence 屬於同一 component。內部平行線、H 型鋼細部線、局部輪廓或首先出現的平行線對不得縮小完整 envelope，也不得單獨成為接觸面。

完整 envelope 與其最外表面 MUST 只由 Waler 自身來源幾何建立，不得使用 Strut／Brace endpoint 反向決定 Waler 的 source geometry。只有在單一 qualified component scope 內，系統才可沿 transverse direction 選擇 extreme outer faces；不得跨 component 對 raw evidence 取全局 min/max。同一 source scope 或 GeometryGroup 若支持兩個以上不等價的完整 component envelopes，系統 MUST 保留可證明的分離 interpretations，或在無法唯一分離時回報 blocking ambiguity，不得合成一個較寬的假 envelope。對可靠 HATCH RC Waler，HATCH exterior boundary 所支持的兩條最外 longitudinal faces MUST 參與同一 contract。對本來就只以單一正式工程線表達、且沒有可證明寬度的既有 Waler，系統 SHALL 保留該線作為正式接觸線，不得製造虛構 envelope。

#### Scenario: 四條縱向線保留最外兩側
- **WHEN** 同一 Waler source scope 具有四條共同支持單一構件的縱向線，其中兩條是完整 envelope 的最外表面、兩條是內部細部線
- **THEN** 系統 MUST 保留完整 envelope 的最外兩側作為可選接觸面
- **AND** MUST NOT 只因任一內部線與另一條線平行、等長或較早出現就縮小 envelope

#### Scenario: 同一 group 中相接的兩支 Waler 不形成共同 envelope
- **WHEN** 同 layer 或同一 GeometryGroup 中有兩支端點相接、但各自具有完整且不等價 envelope 的 Waler components
- **THEN** 系統 MUST 保留兩個分離 component interpretations，或在無法唯一分離時回報 blocking ambiguity
- **AND** MUST NOT 以兩支 Waler 的全部 rails 建立一個共同 envelope

#### Scenario: 同方向多支 Waler 不以平行關係合併
- **WHEN** 同一 source scope 或 GeometryGroup 中有兩支方向相同、長度相近或 projection coverage 重疊，但 topology 不足以證明為單一 component 的 Waler
- **THEN** 平行、等長與 coverage evidence MUST NOT 單獨使它們成為同一 qualified component scope
- **AND** 系統 MUST NOT 跨兩支 Waler 選擇 transverse extremes

#### Scenario: 跨 component raw minmax 不得製造假 envelope
- **WHEN** raw longitudinal evidence 的最小與最大 transverse offsets 分別來自不同 Waler components
- **THEN** 系統 MUST NOT 直接以該全局 min/max 建立一個 envelope
- **AND** MUST 先完成 component qualification與分離，否則回報 blocking ambiguity

#### Scenario: 多個完整 envelope interpretations 不得任意合併
- **WHEN** 同一 source scope 的 geometry 同時支持兩個以上不等價且各自完整的 component envelope interpretations
- **THEN** 系統 MUST 保留可唯一證明的分離 interpretations，或將無法唯一分離的結果標示為 ambiguous
- **AND** MUST NOT 依 candidate order、first occurrence 或較寬的 combined extent 選擇單一 interpretation

#### Scenario: W7 與 W12 不在 envelope extraction 中合併
- **WHEN** 與 Y05 W7、W12 等價的兩個 Waler components 位於同一 drawing region且彼此鄰近
- **THEN** envelope extraction MUST 將兩者維持為不同 qualified component scopes
- **AND** MUST NOT 以 W7、W12 的共同 transverse extremes 建立一個假 envelope

#### Scenario: HATCH RC Waler 使用 exterior envelope
- **WHEN** HATCH RC Waler 已由唯一可靠 exterior boundary 建立中心參考軸、實際寬度與兩條最外 longitudinal faces
- **THEN** 該 Waler MUST 使用本 capability 的共用支撐側判定
- **AND** MUST NOT 建立 HATCH 專用的接觸面規則

#### Scenario: 單一 Waler 工程線保持相容
- **WHEN** 一支既有 Waler 只有一條可靠正式工程線，且來源幾何無法證明另一側或實體寬度
- **THEN** 系統 SHALL 保留該工程線
- **AND** MUST NOT 因缺少 envelope 而任意 offset 或複製另一條線

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
- **WHEN** 一個尚未具有可靠 Waler identity 的 member terminal 對 provisional geometry 存在兩個無法唯一區分的合法關係
- **THEN** 系統 MUST 回報 blocking ambiguity
- **AND** MUST NOT 以 Waler ID、DXF handle、entity order 或 collection order 任選
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
- **WHEN** 同一 member 的 start/end 表示反轉，但 WCS 軸線、terminal-to-Waler 關係與構件本體位置等價
- **THEN** 系統 MUST 得到相同的 Waler 支撐側與等價正式接觸面

#### Scenario: 無關構件不影響 Waler
- **WHEN** DXF 中新增、移除或重排一支與目標 Waler 沒有 terminal 關係的 Strut／Brace
- **THEN** 目標 Waler 的接觸側 MUST 保持不變

#### Scenario: 同一 terminal 對兩支候選 Waler 提供同側方向

- **WHEN** 一個 terminal 對 Waler A 與 Waler B 形成無法唯一區分的合法 candidate relations，且從 A、B 各自的 provisional axis 朝 member 本體均可得到可靠方向
- **THEN** A 與 B SHALL 各自取得可追溯至該 terminal 的 side-only evidence
- **AND** 兩份 evidence MUST NOT 被解讀為該 terminal 同時正式連接 A 與 B

#### Scenario: 退化方向不得作為 side evidence

- **WHEN** 某 candidate relation 的 Waler-to-member body vector 對該 Waler 法向分量絕對值 `<= endpoint_tolerance_mm`
- **THEN** 該 relation MUST NOT 參與該 Waler 的接觸側選擇
- **AND** 系統 SHALL 保留既有無可靠側向證據的 failure semantics

### Requirement: 正式接觸面必須是支撐側的最外實體表面

當 Waler 具有可靠完整 envelope 且支撐側可唯一決定時，正式 Waler engineering line MUST 使用該 envelope 在支撐側的最外實體表面。位於 envelope 內部的縱向線不得因較靠近 provisional center、member endpoint 或其他 detail geometry 而被選為正式接觸面。

#### Scenario: Y05 W7 使用支撐側最外表面
- **WHEN** 與 Y05 W7 等價的 Waler source 具有約 `y = 8800`、`8781`、`8469`、`8449` 的四條縱向線，且相關 Strut／Brace 位於較低一側
- **THEN** 正式接觸面 MUST 使用較低側 envelope 的最外實體表面 `y = 8449`
- **AND** MUST NOT 使用內部線 `y = 8469` 或上側線 `y = 8781`

#### Scenario: 支撐位於相反側
- **WHEN** 同一可靠 Waler envelope 的相關 members 明確位於較高一側
- **THEN** 正式接觸面 MUST 使用較高側 envelope 的最外實體表面

#### Scenario: Y1A 一般 CAD 結果保持等價
- **WHEN** Y1A 類型的一般 CAD Waler 與其相關 Strut／Brace 已由幾何唯一表示同一支撐側
- **THEN** 新規則 MUST 選出與既有正確結果等價的正式接觸面
- **AND** 不得要求該 drawing 改成 BIM Block 表達

### Requirement: 接觸側無法唯一決定時必須保守失敗

若同一 Waler 沒有可用的 related member side evidence、可靠 evidence 同時指向 envelope 兩側、來源 envelope 無法唯一建立，或幾何退化使方向無法判定，系統 MUST 產生包含 Waler source identity 與可理解原因的 blocking Review problem。系統 MUST NOT 使用 row order、entity order、first occurrence、lexical ID、浮點噪音或全域 centroid 強行選擇。

#### Scenario: Related members 位於兩側
- **WHEN** 同一 Waler 的可靠 related Strut／Brace evidence 分別指向 envelope 的相反兩側
- **THEN** 系統 MUST 將接觸側標示為 ambiguous 並阻止該 unresolved result 完成 import
- **AND** MUST NOT 以 members 數量或輸入順序任選一側

#### Scenario: 沒有可用 side evidence
- **WHEN** 多面 Waler 已有可靠 envelope，但沒有任何可建立 terminal 關係的 Strut／Brace evidence
- **THEN** 系統 MUST 留在既有 Review workflow
- **AND** MUST NOT 以其他 Waler 的位置或全域 drawing centroid 猜測接觸側

#### Scenario: Provisional reference axis 不得代替正式接觸面
- **WHEN** 多面 Waler 已有 provisional reference axis 與可靠 envelope，但沒有可用的 related member side evidence
- **THEN** 系統 MUST 回報 blocking `WALER_CONTACT_FACE_UNRESOLVED`
- **AND** provisional reference axis MUST 只保留為 recognition／diagnostic fact，不得被提交為 formal contact face
- **AND** DXF Import MUST 保持 blocked，直到該 unresolved source 透過既有合法 Review workflow 被處理

#### Scenario: Equivalent source ordering
- **WHEN** Waler source entities、related members 或 boundary traversal 只改變儲存順序與線段方向，WCS geometry 不變
- **THEN** recognition／finalization status 與等價正式接觸面 MUST 保持不變

### Requirement: 下游正式幾何與診斷必須使用同一接觸面 truth

接觸面決策完成後，正式 Waler geometry、已選定 Waler identity 的 contextual Strut endpoints、Brace-to-Waler connection、CandidatePoint、association、validation 與 diagnostics MUST 使用同一份 finalization outcome。系統不得在不同 downstream path 重新推導第二套支撐側規則，亦不得同時保留 provisional centerline 與 selected face 作為兩套正式連接 truth。

接觸面 finalization 失敗時，來源辨識 facts MUST 保留以供 Preview／Review，但不得將未完成的正式 Waler connection 提交至 Project。既有 committed ProjectDataModel 與 Solver result MUST 保持不變，直到 staged DXF Review 被合法完成。

#### Scenario: Contextual Strut endpoint 使用最終表面
- **WHEN** BIM contextual Strut 已選定一支具有可靠 envelope 的 Waler identity，且接觸面成功 finalization
- **THEN** 該 Strut formal endpoint MUST 位於該 Waler 的最終接觸面
- **AND** CandidatePoint 與 connection diagnostics MUST 指向相同 Waler identity 與同一正式位置

#### Scenario: 接觸面失敗不提交 Project
- **WHEN** Waler 接觸面產生 blocking ambiguity 或 validation failure
- **THEN** 該 unresolved DXF Review MUST NOT 完成正式 Project import
- **AND** 既有 committed Project input 與 Solver result MUST 保持不變

### Requirement: 既有 DXF Review 與來源生命週期必須保持相容

本 capability MUST 保持 original DXF immutable、root source provenance、Source Exclusion／Restore、manual override replay、confirmation invalidation、Review staged mutation、Pause／Resume、fingerprint safety 與 completed import lifecycle。接觸面是由目前 recognition facts 重建的 runtime／Review outcome，不得新增 Project persistence schema 或將 DXF 細部 envelope metadata寫入 Solver Domain。

#### Scenario: 排除或復原來源會重建接觸面
- **WHEN** 使用者排除或復原參與接觸面判定的 Waler、Strut 或 Brace source
- **THEN** 系統 MUST 從目前 staged recognition facts 重新建立 relation 與接觸面 outcome
- **AND** MUST NOT 保留指向已不存在來源的 stale connection

#### Scenario: Manual override replay 不建立第二套自動規則
- **WHEN** recognition rebuild 後既有人工操作可依 exact source identity 安全重播
- **THEN** 系統 SHALL 沿用既有 manual override 與 confirmation invalidation contract
- **AND** Presentation MUST NOT 自行重算另一個 Waler 支撐側

#### Scenario: Completed import 維持既有 Project contract
- **WHEN** 使用者完成所有 Waler 接觸面均合法的 DXF Review
- **THEN** 系統 SHALL 透過既有 DXF result-to-project conversion 建立 Project rows
- **AND** MUST NOT 新增 persistence schema 或 Solver input 欄位

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

### Requirement: 競爭來源變更後必須重建方向與 identity 狀態

當 source exclusion／restore 改變重疊 pair 或 terminal candidates 時，系統 SHALL 由目前 active facts 從零重建 candidate relations、identity states、unique／competing evidence groups、warnings 與 contact-face outcome，並重新套用 unique-first precedence。系統 MUST NOT 沿用 stale candidate、排除前 warning、另一支已排除 Waler 的 identity 或先前 contact-face outcome。

#### Scenario: 排除 W17 後 W20 重新套用 precedence
- **WHEN** source `69C` 被排除且 source `721` 成為目前 active source
- **THEN** 系統 SHALL 僅依 source `721` 的目前 active relations 與 evidence 重新判定 formal／ambiguous／unresolved contact-face outcome
- **AND** MUST NOT 重用 source `69C` 的 identity、candidate、warning 或先前 contact-face outcome

#### Scenario: 排除 W20 後 W17 重新套用 precedence
- **WHEN** source `721` 被排除且 source `69C` 成為目前 active source
- **THEN** 系統 SHALL 僅依 source `69C` 的目前 active relations 與 evidence 重新判定 formal／ambiguous／unresolved contact-face outcome
- **AND** MUST NOT 重用 source `721` 的 identity、candidate、warning 或先前 contact-face outcome

#### Scenario: 還原競爭來源後重建方向與 identity 狀態
- **WHEN** 已排除的重疊 Waler source 被還原並再次造成 terminal identity competition
- **THEN** 系統 SHALL 重新建立 blocking identity ambiguity 與目前 active candidate relations
- **AND** 每支 Waler SHALL 依 unique-first precedence 重新評估 formal／ambiguous／unresolved contact-face outcome 與 warnings
- **AND** MUST NOT 沿用排除期間建立的 stale identity、candidate、warning 或正式接觸面
