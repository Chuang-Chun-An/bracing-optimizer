# Spec Delta

## Purpose

本 capability 定義 DXF Import 在各構件完成來源辨識後，如何以同一套幾何與關係語意判定 Waler 的支撐側及最外實體接觸面，使一般 CAD、BIM Block 與 HATCH RC Waler 不因來源畫法不同而產生不同正式工程線。

## ADDED Requirements

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

系統 MUST 先使用已完成的 immutable recognition facts 與 provisional Waler geometry，建立 Strut／Brace terminal 與特定 Waler source identity 的唯一關係，再使用該關係判定接觸側。不同 Waler source identity 即使平行、鄰近或 source geometry 部分重疊，也不得因接觸面選擇而被自動合併、替換或刪除。

已由可靠 upstream context 唯一決定的 Waler source identity MUST 被保留；下游接觸面 finalization 只能解析該 identity 的正式接觸面，不得因另一支 Waler 較接近某個已投影 endpoint 而改派來源。尚未具有 identity 的一般 member terminal 只有在 provisional geometry 能唯一建立關係時才可參與；多解 MUST 進入 blocking ambiguity。

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

### Requirement: 支撐側必須由 member 軸線朝構件本體的方向判定

對已建立 member-to-Waler 關係的 terminal，系統 MUST 以 provisional Waler 交會位置及 member 來源支持軸線，取得由該 Waler 朝 member 本體／另一端的方向，並以此方向判定 Waler 的支撐側。member start/end 表示反轉不得改變結果。

系統 MUST NOT 以已完成 provisional projection 的 endpoint 到候選表面的最短距離、最接近數個全域 endpoints 的距離總和、所有 framing endpoints 的 centroid、浮點微差或 source entity order 決定支撐側。只有與該 Waler 具有已建立關係的 member evidence 才可參與；無關構件不得作為全域投票點。

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
