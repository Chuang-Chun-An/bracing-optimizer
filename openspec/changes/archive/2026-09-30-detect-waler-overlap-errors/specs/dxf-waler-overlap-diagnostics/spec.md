# Spec Delta

## 閱讀導航

- **必讀**：「重大共線重疊必須產生來源診斷」與「競爭關係必須升級為 blocking error」Requirements；定義 finite provisional-axis 分母、50% 邊界與 direct identity provenance。
- **條件式閱讀**：「診斷必須隨 Review truth 重建」Requirement；修改 source exclusion、Pause／Resume、rebuild 或 manual override replay 時必讀。
- **可先跳過**：Waler 接觸面的選面方式與 Preview 樣式；分別由 `dxf-waler-contact-face-recognition` 與 `dxf-review-engineering-data-presentation` 的 delta 定義。

## Purpose

本 capability 定義不同 Waler source identities 之間重大有限共線重疊的資格、可定位診斷、blocking 升級條件及 Review 重建一致性，使使用者能直接找到競爭來源而不需從下游構件錯誤反推。

## ADDED Requirements

### Requirement: 重大共線重疊必須產生來源診斷

系統 SHALL 對不同 Waler source identities 各自可靠、非零長度且由來源幾何支持的 provisional axis 有限區段評估重大共線重疊。只有兩軸方向在既有平行角度容差內、兩條 supporting lines 在既有共線距離容差內，且下式比例 `>= 0.50` 時，才構成重大共線重疊：

```text
overlap_ratio =
    positive finite projected overlap length
    / min(provisional_axis_length_a, provisional_axis_length_b)
```

分子 SHALL 是兩條 source-supported provisional axes 有限區段的正投影交集長度；分母 SHALL 是兩條 provisional axes 各自有限長度的較小值。系統 MUST NOT 使用 finalized contact face、envelope 周長、外框單邊、bounding box、Project row engineering line 或無限 supporting line 作為分母，也 MUST NOT 使用這些幾何取代有限 provisional axes 計算分子。Supporting lines 僅可用於共線資格。

任一 Waler 若沒有可靠且非零長度的 source-supported provisional axis，系統 MUST NOT 為涉及該 Waler 的 pair 建立本 capability 的 overlap fact 或 overlap warning，且 SHALL 保留既有 recognition、terminal 與 contact-face diagnostics。恰為 `0.50` SHALL 合格；低於 `0.50`、只有端點相接、零長度、非共線相交或僅 envelope 在橫向相鄰時 MUST NOT 合格。

每一組合格重疊 SHALL 產生一筆 deterministic、可定位至兩方 Waler source identities 的 warning。診斷 SHALL 保留兩方來源、有限重疊段、重疊長度及相對較短 Waler 的重疊比例；不得依 Waler ID、handle lexical order、entity order 或 collection order 改變工程判定。此規則是 DXF Review 的 geometry／diagnostic contract，不是 Solver Preference，且不得自動合併、刪除、改名或選擇任一 Waler。

#### Scenario: 恰好覆蓋較短 Waler 的百分之五十

- **WHEN** 兩支不同來源的可靠 source-supported provisional axes 符合平行與共線容差，正有限投影重疊長度恰為較短 provisional axis 有限長度的 `50%`
- **THEN** 系統 SHALL 產生一筆重大共線重疊 warning
- **AND** 診斷 SHALL 同時定位兩方 source identities 與有限重疊段

#### Scenario: Provisional axis 有限長度是唯一分母

- **WHEN** 兩支 Waler 各自具有可靠的 source-supported provisional axis，且其 finalized contact face、envelope、外框、bounding box 或 Project row engineering line 具有不同長度
- **THEN** 系統 SHALL 只以兩支 provisional axis 的有限長度較小值作為 overlap ratio 分母
- **AND** SHALL 只以兩支 provisional axes 的正有限投影交集作為分子
- **AND** 其他表示法或無限 supporting line MUST NOT 改變 overlap qualification

#### Scenario: 低於百分之五十不視為重大重疊

- **WHEN** 兩支共線 Waler 的有限重疊比例小於 `50%`
- **THEN** 系統 MUST NOT 產生本 capability 的重大共線重疊診斷

#### Scenario: 端點相接不算重疊

- **WHEN** 兩支 Waler 只有有限端點相接且正重疊長度為 `0`
- **THEN** 系統 MUST NOT 將其視為重大共線重疊

#### Scenario: 零長度 provisional axis 不建立 overlap fact

- **WHEN** 任一 Waler 的 source-supported provisional axis 有限長度為 `0`
- **THEN** 系統 MUST NOT 建立涉及該 Waler 的 overlap fact 或 overlap warning
- **AND** SHALL 保留既有 recognition／contact-face diagnostics

#### Scenario: 不可靠 provisional axis 不建立 overlap fact

- **WHEN** 任一 Waler 缺少可靠且非零長度的 source-supported provisional axis
- **THEN** 系統 MUST NOT 使用 envelope、外框、bounding box、finalized line、Project row 或無限 supporting line 補算 overlap fact
- **AND** SHALL 保留該 Waler 既有 recognition／terminal／contact-face diagnostics

#### Scenario: 方向或輸入順序不影響結果

- **WHEN** 等價 Waler 幾何反轉軸端點，或交換 source／entity／collection 順序
- **THEN** 重疊資格、重疊段、比例與兩方 source identity 集合 SHALL 保持等價
- **AND** 系統 MUST NOT 依 first match 選擇其中一支 Waler

### Requirement: 競爭關係必須升級為 blocking error

重大共線重疊 warning 本身 SHALL 不自動阻擋 Review。系統只有在既有 terminal topology issue 或 contact-resolution outcome 提供 direct identity provenance，明確證明 overlap pair 的兩個完整 Waler source identities 同時是同一 terminal 或同一 contact-face finalization 的實際 competing identities 時，才 MUST 另外產生 `WALER_OVERLAP_COMPETITION` blocking error。Blocking error SHALL 定位重疊 pair、同一 terminal／finalization identity 與受影響 terminal sources，並維持既有 terminal ambiguity 與 `WALER_CONTACT_FACE_UNRESOLVED` truth。

系統 MUST NOT 以「有 overlap 且附近或同批存在 unresolved outcome」推論 identity competition，也 MUST NOT 將另一組 identities 的 competition 歸因至目前 overlap pair。Generic unresolved、缺少兩方完整 identity provenance 的 contact-resolution issue，或只列出 overlap pair 其中一方的 evidence，均不足以升級 warning。系統亦 MUST NOT 以 Waler ID、handle、entity order、距離微差、lexical ordering、first match 或既有 Preview 選取狀態解除競爭。沒有 direct pair provenance 的重大共線重疊 SHALL 保留 warning-only。

#### Scenario: Y29 W17 與 W20 形成競爭關係

- **WHEN** Y29 W17（source `69C`）與 W20（source `721`）同時存在，且其重大共線重疊使既有 member terminals 對兩個 identities 形成等價合法關係
- **THEN** 系統 SHALL 產生 W17／W20 重疊 warning 與 blocking competition error
- **AND** SHALL 維持受影響 terminals 的 ambiguity 及兩支 Waler 的 unresolved contact-face outcome
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

#### Scenario: Competition join 不受 input 與 source 順序影響

- **WHEN** 相同 overlap facts 與 direct competition provenance 交換 Waler input order、source order、axis endpoint order 或 competing identity collection order
- **THEN** warning／blocking qualification、pair identity、受影響 terminal 與可完成狀態 SHALL 保持等價
- **AND** 系統 MUST NOT 以任何排序挑選 winner

#### Scenario: 不得自動挑選重疊 Waler

- **WHEN** 兩支重大重疊 Waler 同時是某 terminal 的合法候選
- **THEN** 系統 MUST NOT 自動合併、刪除、改名或選擇其中一支
- **AND** MUST NOT 由 Waler ID、handle、entity order、距離微差或 first match 建立正式關係

### Requirement: 診斷必須隨 Review truth 重建

重大重疊與競爭診斷 SHALL 由目前 active Waler sources、正式 member recognition facts 與目前 terminal/contact-face assessment 從零重建。Source exclusion／restore、fresh recognition、Pause／Resume、compatible recovery、rebuild 與 manual override replay MUST 使用相同資格與 identity contract；不得沿用已不存在來源的 stale overlap pair 或 stale blocking outcome。

排除重疊 pair 的任一 Waler source 後，系統 SHALL 移除該 pair 的 overlap／competition diagnostics，並依剩餘 active facts 重新執行既有 terminal-to-Waler 與 contact-face finalization；還原來源後 SHALL 重新計算，而不是重播先前結果。

#### Scenario: 排除 W17 後由 W20 完成接觸面

- **WHEN** 使用者排除 source `69C` 並重新辨識 Y29
- **THEN** `69C`／`721` 的 overlap 與 competition diagnostics SHALL 消失
- **AND** source `721` SHALL 依目前支撐／斜撐側向證據選出其支撐側最外接觸面

#### Scenario: 排除 W20 後由 W17 完成接觸面

- **WHEN** 使用者排除 source `721` 並重新辨識 Y29
- **THEN** `69C`／`721` 的 overlap 與 competition diagnostics SHALL 消失
- **AND** source `69C` SHALL 依目前支撐／斜撐側向證據選出其支撐側最外接觸面

#### Scenario: 還原來源後重新出現目前診斷

- **WHEN** 已排除的重疊 Waler source 被還原
- **THEN** 系統 SHALL 依目前 source geometry 與 relationships 重新計算 overlap、competition 與 contact-face outcomes
- **AND** MUST NOT 沿用排除期間的唯一關係或正式接觸面

#### Scenario: Pause Resume 與順序變化保持等價

- **WHEN** 相同 active sources 經 Pause／Resume、compatible recovery 或不同 source/entity 順序重建
- **THEN** overlap pairs、blocking competition、terminal ambiguity 與可完成狀態 SHALL 保持等價

