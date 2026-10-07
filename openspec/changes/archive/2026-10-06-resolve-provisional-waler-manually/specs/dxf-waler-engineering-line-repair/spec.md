# Spec Delta：暫定圍令工程線人工修補

## Purpose

本 capability 定義 DXF Review 中已形成 provisional Waler 的使用者，如何以候選點或 CAD 指定工程線作出明確、可追溯的人工裁決，將通過驗證的線正式提交為該 Waler 的工程線與接觸線，同時保留其他獨立工程問題。

## 閱讀導航

- **必讀**：「人工修補必須是明確且合格的操作」、「人工採用線成為唯一正式幾何 truth」與「只解除被人工裁決取代的問題」；三者共同定義正式化邊界。
- **必讀**：「正式化後必須原子重建下游結果」與「Y29 W14 可由人工選線完成幾何修補」；定義提交效果與主要 fixture acceptance。
- **條件式閱讀**：修改材料自動配對時閱讀「寬度與材料不得由人工線猜測」；修改 Pause／Resume、排除／復原或 recovery 時閱讀「人工裁決必須可安全保存與重驗」。
- **可先跳過**：Waler Solver scoring、Global Waler candidate generation、DXF result export 與一般 formal Waler 自動辨識；本 capability 不修改這些行為。

## ADDED Requirements

### Requirement: 人工修補必須是明確且合格的操作

系統 SHALL 只對已形成 Review member、具有唯一且非空 source identity、目前 `contact_face_state == "provisional"`，或已滿足 `contact_face_state == "formal"` 與 `engineering_line_authority == "manual_repair"` 而要重新採用另一條線的 Waler 提供「採用為正式圍令」修補。使用者 MUST 先以目前 Waler 的候選點形成一條工程線，或提供一條 CAD 指定工程線，再明確執行採用動作；一般問題確認、選取 Review item、Preview 點選、hover、只讀顯示或尚未套用的 temporary line MUST NOT 建立人工正式化 decision。

提交前系統 MUST 驗證目標 Waler 與 exact source identity 仍存在且唯一、選定起終點皆為有限 WCS 座標、線長符合既有 Waler 最小構件長度、候選／CAD line 通過既有工程線 hard validation，且 Review revision、來源 fingerprint 與修補預覽基準仍未過期。任何通過這些既有 validation 的合法線均 MAY 被採用，不得新增「必須位於 source envelope 外側邊」的條件。採用前的 Preview detail與確認內容 MUST 明確顯示：「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」。候選點恰好等於目前 provisional line 的起終點時，只要使用者仍明確執行採用且其餘驗證通過，系統 SHALL 允許該人工裁決；不得以座標未改變為由忽略使用者的正式化意圖。

此 Requirement 屬於 DXF Review Engineering Hard Constraint；它不放寬自動 recognition tolerance 或候選資格。

#### Scenario: 以既有候選點正式採用暫定線

- **WHEN** 使用者為一支 eligible provisional Waler 選定合法起終點，並明確執行「採用為正式圍令」
- **THEN** 系統 SHALL 建立待提交的人工正式化 decision
- **AND** MUST NOT 把該操作只當成一般端點座標修改

#### Scenario: 以 CAD 工程線正式採用

- **WHEN** 使用者為一支 eligible provisional Waler 讀取合法 CAD 工程線、預覽後明確執行「採用為正式圍令」
- **THEN** 系統 SHALL 以該 CAD 線建立與候選點路徑等價的人工正式化 decision
- **AND** 兩種輸入路徑 MUST 使用相同的正式化 validation、commit 與 downstream rebuild contract

#### Scenario: 採用與目前暫定線相同的候選

- **WHEN** 使用者選定的起終點在既有幾何容許值內等於目前 provisional line，但使用者已明確執行正式採用
- **THEN** 系統 SHALL 將這次動作視為有效人工裁決
- **AND** MUST NOT 因幾何座標沒有改變而保留 provisional 狀態

#### Scenario: 一般確認不得正式化

- **WHEN** 使用者只確認問題、選取 Preview 項目或查看 provisional line，沒有執行專用採用動作
- **THEN** Waler SHALL 維持 provisional
- **AND** 原 blocking diagnostics SHALL 維持原狀

#### Scenario: 預覽與確認說明接觸面語意

- **WHEN** 使用者預覽候選點線或 CAD 指定線，準備對 eligible Waler 執行專用正式化
- **THEN** Preview detail與確認內容 SHALL 顯示「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」
- **AND** 系統 MUST NOT 將該線描述成中心線或暗示必須落在 envelope 外側邊

#### Scenario: 重新採用另一條人工線

- **WHEN** Waler 已由 `manual_repair` 正式化，但使用者以專用操作明確採用另一條通過 validation 的合法線
- **THEN** 新 decision SHALL 原子取代舊人工正式線與其 downstream baseline
- **AND** 系統 MUST NOT 同時保留兩筆 formal authority，亦 MUST NOT 先取消成 provisional

#### Scenario: Stale 或不合法修補不改變狀態

- **WHEN** 選定線不合法，或提交時 target identity、fingerprint、revision、候選幾何任一項已不同於預覽基準
- **THEN** 系統 MUST 拒絕提交並說明原因
- **AND** 目前 WCS Review result、confirmations、人工決策與 committed Project／Solver state MUST 保持不變

### Requirement: 人工採用線成為唯一正式幾何 truth

人工正式化成功後，選定有限線本身 SHALL 成為該 Waler 唯一正式 engineering line 與 contact face，`contact_face_state` SHALL 為 `formal`，且使用者可辨識其來源為候選點人工採用或 CAD 人工採用。只要該線通過既有 validation，就不要求它與 source envelope 任一外側邊共線或重合。系統 MUST NOT 同時把原 provisional axis、未選 envelope interpretation 或其他 boundary line 保留為第二條正式接觸線，亦 MUST NOT 再由 support side選擇另一條 outer face。

人工正式線的 authority 只屬於 exact Waler source identity；它 MUST NOT 建立、合併、刪除或改派其他 Waler source identity，也 MUST NOT 將一個 source 自動拆成多支 Waler。人工正式化不是自動 envelope recognition 的新 fallback，亦不得回寫或修改 original DXF。

#### Scenario: 成功提交候選點人工線

- **WHEN** 候選點正式化 decision 通過提交前重驗並成功提交
- **THEN** 目標 Waler SHALL 使用選定起終點作為唯一 formal engineering／contact line
- **AND** Preview、Review engineering data 與完成匯入後的 Waler row SHALL 使用同一條線

#### Scenario: 成功提交 CAD 人工線

- **WHEN** CAD 工程線正式化 decision 通過提交前重驗並成功提交
- **THEN** 目標 Waler SHALL 使用該 CAD 線作為唯一 formal engineering／contact line
- **AND** MUST NOT 另外從 source envelope 選出第二條正式線

#### Scenario: 合法人工線不在 envelope 外側邊

- **WHEN** 使用者採用的有限線通過既有 validation，但不與任何 source envelope 外側邊共線或重合
- **THEN** 該線 SHALL 仍成為 Waler 的唯一 formal contact face
- **AND** 系統 MUST NOT 因它不是 outer boundary而拒絕、平移或替換該線

#### Scenario: 不拆分同一來源

- **WHEN** 一個 source scope 同時支持多個完整 Waler envelope interpretations，使用者只人工採用其中一條計算線
- **THEN** 系統 SHALL 正式化目前單一 Waler member
- **AND** MUST NOT 因此建立其他 Project Waler 或宣稱其餘 source geometry 已成為另一支正式構件

### Requirement: 只解除被人工裁決取代的問題

人工正式化成功後，系統 SHALL 只移除或取代目標 exact source identity 上、其原因已由人工 engineering／contact line authority 完整解決的 `WALER_ENVELOPE_AMBIGUOUS`、`WALER_ENVELOPE_UNRESOLVED`、`WALER_CONTACT_FACE_AMBIGUOUS` 與 `WALER_CONTACT_FACE_UNRESOLVED` blocking diagnostics。系統 SHALL 保留可追溯的人工選線 provenance，讓 Review 可辨識該 formal line 不是自動 contact-face finalization 的結果。

來源重疊、`WALER_OVERLAP_COMPETITION`、`AMBIGUOUS_WALER_CONNECTION`、其他 Waler／member source identity 問題、duplicate engineering member、connection、association、zero-length、minimum-length 或任何不由選定人工線直接解決的診斷 MUST 依重建後的目前 facts 保留或重新產生。人工正式 Waler line MUST NOT 被用來挑選 competing Waler identity winner。

#### Scenario: Envelope ambiguity 被人工線取代

- **WHEN** 目標 Waler 唯一阻擋是同一 exact source 的 envelope／contact-face ambiguity，且人工正式化成功
- **THEN** 對應的 envelope／contact-face blocking diagnostic SHALL 不再阻止匯入
- **AND** Review SHALL 顯示該 Waler 已由人工選線形成 formal line

#### Scenario: 重疊與 terminal identity 問題仍保留

- **WHEN** 人工正式化的 Waler 同時參與 source overlap、overlap competition 或 member terminal identity ambiguity
- **THEN** 系統 SHALL 依重建後 facts 保留對應問題與 blocking semantics
- **AND** MUST NOT 因目標 Waler 已 formal 就選擇任一 competing identity

#### Scenario: 其他來源的問題不受影響

- **WHEN** 使用者只正式化 Waler A，而 Waler B 或其他 member 仍有獨立錯誤
- **THEN** B 與其他 member 的 diagnostics、formal state 及 completion eligibility SHALL 依自身 facts 維持

### Requirement: 正式化後必須原子重建下游結果

人工正式化 SHALL 是單一 staged Review mutation。系統 MUST 先以選定 WCS line 建立 staged result，丟棄以 provisional axis 建立的舊 terminal evidence／relations，再以人工線作為 contact face重建 Strut／Brace terminal topology、connections、candidate points、component associations、double-support eligibility、Waler contact review baseline、formal Brace adjustment baseline、validation diagnostics、Review items 與 `can_import`。所有 downstream consumer MUST 使用同一條人工正式線，不得各自重新選擇 envelope、outer face或 provisional axis。

支撐側 SHALL 由重建後的 current terminal evidence依既有 unique-first precedence判斷，並由 authoritative member body位於人工接觸線哪一側導出 `support_normal_world`；人工線本身就是接觸面，支撐側只決定法向，不再選擇另一條外側面。若 authoritative evidence分布在兩側或完全沒有可靠 evidence，`support_normal_world` SHALL 為 unknown。unknown MUST NOT 使人工正式化失效，但後續背填／寬度調整 MUST 依既有 `WALER_SUPPORT_SIDE_UNKNOWN` 原子阻擋，不得猜測方向。

連到該 Waler且已建立完整正式連接的 Brace SHALL 以人工接觸線重建 immutable adjustment baseline。後續調整該 Waler時，Brace SHALL 沿用既有 rigid-translation規則；若支撐側 unknown或 rigid translation無合法解，整次 adjustment MUST 失敗且 Waler、Brace、review baseline與manual override狀態不變。

只有全部重建與提交前 validation 成功時，系統才 SHALL 原子採用新的 WCS result、projected result、人工 decision 與 confirmation invalidation。任一步驟失敗、使用者取消或 stale-plan validation 失敗時 MUST 丟棄 staged state。正式 Project input、Solver result、Solver memory 與候選 cache MUST 保持不變，直到使用者依既有 Review completion 流程完成匯入。

#### Scenario: 相關構件依人工正式線重建

- **WHEN** 一支 provisional Waler 成功採用人工正式線
- **THEN** 所有相關 Strut／Brace connection 與衍生資料 SHALL 由該線重新建立
- **AND** 舊 provisional intersection、舊 contact face 或舊 association MUST NOT 繼續作為正式結果

#### Scenario: 構件同側時取得支撐側

- **WHEN** 人工正式化後重建的 authoritative Strut／Brace terminal evidence均使構件本體位於人工接觸線同一側
- **THEN** 系統 SHALL 依既有 unique-first precedence建立指向該側的 `support_normal_world`
- **AND** 人工線 SHALL 繼續作為 contact face，不得再選擇 envelope outer face

#### Scenario: 兩側衝突時支撐側 unknown但正式化成立

- **WHEN** 人工正式化後的 authoritative terminal evidence使構件本體分布於人工接觸線兩側
- **THEN** Waler SHALL 維持已成立的人工 formal contact face，且 `support_normal_world` SHALL 為 unknown
- **AND** 後續背填／寬度 adjustment SHALL 以 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋並保持全部狀態不變

#### Scenario: 無構件證據時支撐側 unknown但正式化成立

- **WHEN** 人工正式化後沒有任何可靠 Strut／Brace terminal evidence可判斷支撐側
- **THEN** Waler SHALL 維持已成立的人工 formal contact face，且 `support_normal_world` SHALL 為 unknown
- **AND** 後續背填／寬度 adjustment SHALL 以 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋，不得由線方向、drawing centroid或 envelope猜測支撐側

#### Scenario: 人工正式化後調整背填並剛體平移 Brace

- **WHEN** 人工正式化後已依新 contact line重建 formal Brace adjustment baseline，且使用者合法調整該 Waler背填
- **THEN** 連到該 Waler的 Brace SHALL 依既有 rigid-translation規則從新 baseline計算兩端共同位移
- **AND** Brace角度與長度 SHALL 在既有 tolerance內保持不變

#### Scenario: 重建產生新的連接問題

- **WHEN** 人工正式線本身合法，但重建後某 Strut／Brace 無法建立合法連接
- **THEN** Waler SHALL 維持已提交的人工 formal line
- **AND** 新的 member connection problem SHALL 依既有 severity 阻止或警告 Review，不得回復成舊 provisional geometry

#### Scenario: 提交過程失敗

- **WHEN** staged rebuild、提交前重驗或正式 mutation 任一步驟失敗
- **THEN** 系統 MUST 保留提交前完整 live Review state
- **AND** MUST NOT 留下 formal Waler 配舊 diagnostics、或 provisional Waler 配新 connections 的混合狀態

### Requirement: 寬度與材料不得由人工線猜測

人工工程線只決定 Waler 的正式有限線，不提供新的實體 envelope 或寬度證據。`source_width_state` MUST 只使用已完成正交 supporting-line量測後的 `WalerEnvelopeFacts.source_width` 結果判斷：沒有可靠量測為 `unknown`、全部可靠量測在既有數值語意下等價為 `unique`、存在不等價可靠量測為 `ambiguous`。若為 `unique`，系統 SHALL 保留該 `source_width` 及依既有唯一匹配規則成立的自動材料規格；若為 `unknown`或`ambiguous`，系統 MUST 將 `source_width` 維持或重設為 unknown，並清除依該不唯一寬度形成的自動材料結果；MUST NOT 從人工線長度、方向、鄰近幾何、有限線段端點距離或任一 envelope winner重新量測／猜測寬度。

使用者已明確指定且仍為合法選項的 manual material SHALL 依既有人工材料 contract 保留；本 capability MUST NOT 自動替使用者選擇材料規格。

#### Scenario: 多個 interpretations 具有相同可靠寬度

- **WHEN** envelope interpretations 雖不唯一，但所有可靠代表寬度在既有幾何／材料比對語意下數值等價
- **THEN** 人工正式化後 SHALL 保留該唯一代表寬度
- **AND** 既有自動材料唯一匹配結果可依原規則保留

#### Scenario: Envelope interpretations 寬度不一致

- **WHEN** 同一 provisional Waler 的可靠 interpretations 提供不等價代表寬度
- **THEN** 人工正式化 MUST NOT 任選其中一個寬度
- **AND** 系統 SHALL 使用 unknown width semantics、清除不再可靠的自動材料結果並要求使用者另行處理材料

#### Scenario: 已有人工材料規格

- **WHEN** 目標 Waler 已有使用者明確指定且目前仍合法的材料規格
- **THEN** 人工工程線正式化 SHALL 保留該 manual material decision
- **AND** MUST NOT 以 source width ambiguity 覆寫使用者決定

### Requirement: 人工裁決必須可安全保存與重驗

已採用人工正式線 SHALL 與 Waler role、exact source identity、採用 WCS 起終點、輸入來源類型及明確正式化意圖綁定，並沿用既有 Review manual decision、confirmation invalidation、Pause／Resume 與 source exclusion／restore contract。系統 MUST NOT 只因 `selection_source` 是一般人工候選點或 CAD line，就把沒有正式化意圖的舊資料推定為人工正式 Waler。

Same-fingerprint Pause／Resume 或同一 Review 內 restore exact source 時，系統 SHALL 重新驗證 decision；只有 exact subject 唯一存在、採用線仍合法且 replay 後 downstream rebuild 成功時才恢復 formal 效果。來源被排除時 decision MUST 不影響 active engineering state；合法 restore 後可依相同重驗規則恢復。任一必要 evidence 無法重建時，系統 SHALL 保留可處理 subject、將 decision 標示為需要重新檢查，並不得套用舊 formal 效果。

#### Scenario: Same-fingerprint Resume 成功重播

- **WHEN** paused Review 以相同 fingerprint 恢復，且 exact Waler subject 與採用線均通過目前 validation
- **THEN** 系統 SHALL 恢復該人工 formal line 及其 provenance
- **AND** downstream results SHALL 從目前 canonical result 重新建立

#### Scenario: 排除後不套用人工正式線

- **WHEN** 具有人工正式化 decision 的 Waler source 被排除
- **THEN** 該 decision MUST 不影響 active Waler、connections 或 Project rows
- **AND** 原 decision SHALL 依既有 exclusion lifecycle 保留為可安全 restore 的人工 state

#### Scenario: Restore exact source 後重新生效

- **WHEN** 同一 Review 內 exact Waler source 被還原，且人工 decision 重驗成功
- **THEN** 系統 SHALL 恢復人工 formal line並重建其 downstream result
- **AND** MUST NOT 沿用排除期間的 stale connections 或 diagnostics

#### Scenario: 舊一般人工端點不得被推定為正式化

- **WHEN** 系統載入只保存一般 Waler candidate-point／CAD geometry selection、但沒有明確正式化意圖的舊 Review state
- **THEN** 系統 MUST 保持其既有相容行為
- **AND** MUST NOT 自動清除 envelope／contact-face blocker 或把 provisional Waler 升級為 formal

### Requirement: Y29 W14 可由人工選線完成幾何修補

Y29 W14 source `58D` 具有同一來源支持多個完整 Waler interpretations 的 blocking envelope ambiguity。當使用者對 W14 以候選點或 CAD 工程線明確採用一條合法計算線時，系統 SHALL 將該線正式化、移除 `58D` 上已被人工 authority 取代的 envelope／contact-face blocker，並依目前全案 facts 重建相關連接與其他 diagnostics。

W14 的人工正式化 MUST NOT 自動把 `58D` 拆成垂直與斜向兩支 Waler，也不得清除 Y29 中與 W14 無關的 Waler overlap、terminal identity 或其他來源問題。採用的 W14線只需通過既有 validation，不必落在 `58D` 任一 envelope外側邊；採用前必須顯示接觸面提示。只有當整份 Y29 Review 的所有其餘 blocking problems 亦已合法處理時，`can_import` 才可為 true。

#### Scenario: W14 採用目前顯示的暫定線

- **WHEN** 使用者選擇 W14 目前 provisional line 的起終點並明確執行正式採用，且 validation 成功
- **THEN** W14 SHALL 以該線成為 formal Waler
- **AND** Preview與確認 SHALL 提示「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」
- **AND** source `58D` 的 `WALER_ENVELOPE_AMBIGUOUS` SHALL 不再單獨阻止匯入

#### Scenario: W14 改由 CAD 指定線

- **WHEN** 使用者為 W14 提供另一條合法 CAD 工程線並明確執行正式採用
- **THEN** W14 SHALL 以 CAD 線本身成為 formal contact face，即使該線不在 `58D` 的 envelope外側邊
- **AND** 系統 SHALL 使用與候選點採用相同的診斷範圍、重建與 lifecycle contract

#### Scenario: Y29 其他 blockers 仍存在

- **WHEN** W14 已人工 formal，但 Y29 仍有 W17／W20 overlap competition、B15 或其他 terminal identity ambiguity
- **THEN** 對應 diagnostics 與 `can_import == false` SHALL 維持
- **AND** 系統 MUST NOT 把 W14 的人工裁決解讀成全案確認
