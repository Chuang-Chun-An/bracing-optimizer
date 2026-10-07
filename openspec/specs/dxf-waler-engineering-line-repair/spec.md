# dxf-waler-engineering-line-repair Specification

## Purpose

本 capability 定義 DXF Review 中已形成 provisional Waler 的使用者，如何以候選點或 CAD 指定工程線作出明確、可追溯的人工裁決，將通過驗證的線正式提交為該 Waler 的工程線與接觸線，同時保留其他獨立工程問題。

## 閱讀導航

- **必讀**：「人工修補必須是明確且合格的操作」、「人工採用線成為唯一正式幾何 truth」與「只解除被人工裁決取代的問題」；三者共同定義正式化邊界。
- **必讀**：「正式化後必須原子重建下游結果」與「Y29 W14 可由人工選線完成幾何修補」；定義提交效果與主要 fixture acceptance。
- **條件式閱讀**：修改材料自動配對時閱讀「寬度與材料不得由人工線猜測」；修改 Pause／Resume、排除／復原或 recovery 時閱讀「人工裁決必須可安全保存與重驗」。
- **可先跳過**：Waler Solver scoring、Global Waler candidate generation、DXF result export 與一般 formal Waler 自動辨識；本 capability 不修改這些行為。

## Requirements

### Requirement: 人工修補必須是明確且合格的操作

系統 SHALL 只對已形成 Review member、具有唯一且非空 source identity、目前 `contact_face_state == "provisional"`，或已滿足 `contact_face_state == "formal"` 與 `engineering_line_authority == "manual_repair"` 而要重新採用另一條線的 Waler 提供「圍令正式化」修補工具。此工具 SHALL 位於 DXF Review 的「修改工具」，且只在目前選取項目能唯一對應一支 repair-eligible Waler 時顯示並可開啟。候選點區與 Preview MUST NOT 顯示「採用正式圍令」或其他會建立 formal authority 的動作。

圍令正式化工具 SHALL 提供互斥的「線的來源」單選：「點位清單」與「已讀取的 CAD 線」，且開啟時 MUST 預設為「點位清單」。選擇點位清單時，工具 SHALL 顯示目標Waler的point list，讓使用者分別從對應合法點位中選擇起點與終點，並以該Waler目前`selected_start_point_id`與`selected_end_point_id`作為預設；若兩個IDs均能解析為合法端點，即使使用者不改選也 SHALL 可直接採用。只有目標member的point list中存在同一批最新、分別適用於start與end的CAD人工端點時，「已讀取的CAD線」才 SHALL 可選；否則該選項 MUST 停用。

工具 SHALL 只有一個「採用正式圍令」按鈕。只有使用者按下此按鈕時，系統才 SHALL 依當下來源建立既有Waler engineering-line repair plan並立即嘗試commit：點位清單 MUST 以所選起終點及`manual_candidate_points`建立；已讀取的CAD線 MUST 以該member最新CAD pair及`cad_manual`建立。兩條路徑 MUST 使用相同的eligibility、geometry validation、revision／fingerprint guard、atomic commit、diagnostic replacement及downstream rebuild contract。來源／點位選擇均為尚未提交的Presentation state；開啟工具、切換來源、改選點位、關閉視窗或按取消 MUST NOT 修改live Review geometry、manual override、confirmation、diagnostics或authority。

主Review的「選起點」、「選終點」與「套用選取點」SHALL 維持一般幾何編輯語意；Preview若提供「選起點／選終點」，MUST 使用相同generic selection flow。「套用選取點」對provisional Waler只更新暫定工程線並依目前facts重建Review projection，MUST NOT建立formal authority；對已`manual_repair`正式化的Waler則 MUST 在任何Workflow mutation前拒絕，提示使用者改用修改工具的「圍令正式化」，並保持完整live Review state不變。一般問題確認、選取Review item、Preview點選、hover、只讀顯示或temporary line亦 MUST NOT 正式化Waler。

圍令正式化工具 MUST NOT 提供CAD event讀取或CAD工程線建立。使用者若要採用CAD線，MUST 先透過既有「從CAD指定工程線」流程把線讀入目標member，但 MUST NOT 被要求先按「套用選取點」。CAD線 SHALL 以目標member的candidate-point provenance辨識，不得使用其他member的CAD pair。若工具開啟後該member的CAD pair已被新讀取的CAD線取代，舊工具在採用時 MUST 拒絕並顯示「CAD 線已更新，請重新開啟圍令正式化」；不得靜默切換成新線或提交舊線，且拒絕前後live Review state MUST 完全不變。

採用前工具內容與確認訊息 MUST 明確顯示：「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」。提交前系統 MUST 驗證目標 Waler 與 exact source identity仍存在且唯一、選定起終點均存在於目標Waler的point list且適用於對應端點、座標為有限WCS值、線長符合既有Waler最小構件長度、工程線通過既有hard validation，且Review revision、來源fingerprint與修補基準仍未過期。任何通過這些既有validation的合法線均 MAY 被採用，不得新增「必須位於source envelope外側邊」的條件。

若正常repair-eligible Waler的目前selected endpoint IDs無法解析為point list中的合法起終點，系統 MUST 拒絕以猜測、最近點或隱含live mutation補足預設，並向使用者說明需重新整理或修正Review資料。採用時的plan建立、staged rebuild、提交前重驗或commit任一步驟失敗，系統 MUST 保留操作前完整live Review state；provisional Waler維持原暫定線，既有`manual_repair` Waler的舊formal line與authority在新commit成功前保持不變，且不得留下partial formal state。

此 Requirement 屬於 DXF Review Engineering Hard Constraint；它不放寬自動 recognition tolerance、候選資格或其他工程規則。

#### Scenario: 修補工具只對合格圍令出現

- **WHEN** 目前選取項目唯一對應一支provisional Waler，或一支`engineering_line_authority == "manual_repair"`的formal Waler
- **THEN** DXF Review修改工具 SHALL 顯示可開啟的「圍令正式化」
- **AND** automatic formal Waler、其他角色、無唯一member或不合格來源 MUST NOT 取得該工具入口

#### Scenario: 工具預選目前線端點

- **WHEN** repair-eligible Waler的目前selected起終點IDs均存在於point list且分別適用於start與end
- **THEN** 工具 SHALL 預選該pair
- **AND** 使用者 SHALL 可不改點直接按「採用正式圍令」

#### Scenario: 工具選擇線的來源

- **WHEN** 使用者開啟repair-eligible Waler的圍令正式化工具
- **THEN** 工具 SHALL 顯示互斥的「點位清單」與「已讀取的CAD線」來源選項，並預設點位清單
- **AND** 不論選擇哪個來源，工具 SHALL 只提供一個「採用正式圍令」按鈕

#### Scenario: 以既有候選點正式採用暫定線

- **WHEN** 使用者在圍令正式化工具為eligible provisional Waler選定合法起終點，並明確按「採用正式圍令」
- **THEN** 系統 SHALL 以`manual_candidate_points`建立待提交的人工正式化decision
- **AND** SHALL 使用既有repair validation、commit與downstream rebuild contract
- **AND** 工具外的一般「套用選取點」MUST NOT 產生相同authority effect

#### Scenario: 以 CAD 工程線正式採用

- **WHEN** 使用者已由一般流程為eligible Waler讀取合法CAD工程線，但尚未按「套用選取點」
- **AND** 使用者在圍令正式化工具選擇「已讀取的CAD線」並按「採用正式圍令」
- **THEN** 系統 SHALL 以`cad_manual`建立人工正式化decision
- **AND** MUST 使用與點位清單路徑相同的正式化validation、commit、診斷取代與downstream rebuild contract

#### Scenario: 沒有同member CAD線時停用選項

- **WHEN** 目標Waler的point list沒有同一批最新且分別適用於start與end的CAD人工端點
- **THEN** 「已讀取的CAD線」選項 MUST 停用
- **AND** 其他member的CAD線 MUST NOT 使此選項可用

#### Scenario: 工具開啟後CAD線更新

- **WHEN** 工具開啟後，目標member原有CAD pair被新讀取的CAD線取代
- **AND** 使用者在舊工具視窗嘗試採用CAD線
- **THEN** 系統 MUST 拒絕並顯示「CAD 線已更新，請重新開啟圍令正式化」
- **AND** MUST NOT 自動採用新線或舊線，且live Review state MUST 完全不變

#### Scenario: 採用與目前暫定線相同的候選

- **WHEN** eligible provisional Waler的目前線已對應point list中的合法selected pair，且使用者在工具內維持預設後明確執行採用
- **THEN** 系統 SHALL 將這次動作視為有效人工裁決
- **AND** MUST NOT 因geometry未改變或原selection source為`auto`而保留provisional狀態
- **AND** 這次明確工具採用 SHALL 記為`manual_candidate_points`

#### Scenario: W14 不改點即可直接採用

- **WHEN** Y29 W14 source `58D`由自動辨識建立目前`line_1`，其目前起終點分別對應point list的`P01`與`P02`
- **THEN** 圍令正式化工具 SHALL 預選`P01`與`P02`
- **AND** 使用者不改點按「採用正式圍令」時 SHALL 可成功建立`manual_candidate_points` repair plan並正式化W14
- **AND** 工具 MUST NOT 為此流程新增synthetic point或先修改live provisional line

#### Scenario: 一般確認不得正式化

- **WHEN** 使用者只確認問題、選取Preview項目、查看provisional line或執行一般「套用選取點」，沒有在圍令正式化工具按採用
- **THEN** Waler SHALL 維持既有authority狀態
- **AND** 原blocking diagnostics SHALL 依一般幾何編輯後目前facts維持或重建，但不得因formal authority被移除

#### Scenario: 已正式化Waler的一般套用被拒絕

- **WHEN** `engineering_line_authority == "manual_repair"`的formal Waler執行一般「套用選取點」
- **THEN** 系統 MUST 拒絕並提示改用修改工具的「圍令正式化」
- **AND** live Review geometry、revision、manual decision、confirmations、diagnostics與downstream state MUST 完全不變

#### Scenario: Preview 選點仍是一般幾何編輯

- **WHEN** Preview提供「選起點」與「選終點」controls
- **THEN** 這些controls SHALL 使用與主Review相同的一般pending selection與「套用選取點」流程
- **AND** Preview MUST NOT 顯示或觸發「採用正式圍令」

#### Scenario: 預覽與確認說明接觸面語意

- **WHEN** 使用者開啟圍令正式化工具並準備採用所選線
- **THEN** 工具內容與採用確認 SHALL 顯示「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」
- **AND** 系統 MUST NOT 將一般「套用選取點」描述成已正式採用

#### Scenario: 重新採用另一條人工線

- **WHEN** Waler已由`manual_repair`正式化，而使用者在工具內選擇另一個合法point pair
- **THEN** 工具選擇期間舊formal line與authority SHALL 保持不變
- **AND** 只有按「採用正式圍令」且新repair commit成功時，新decision SHALL 原子取代舊人工正式線與downstream baseline
- **AND** 系統 MUST NOT 先降回provisional或在Presentation保存repair plan

#### Scenario: 已正式化Waler改用CAD線重新採用

- **WHEN** `manual_repair` Waler已有舊formal line，且使用者在工具選擇同member最新CAD線後按「採用正式圍令」
- **THEN** 舊formal line與authority SHALL 保持不變直到`cad_manual` repair commit成功
- **AND** 成功時新CAD線 SHALL 原子取代舊正式線，失敗時完整live Review state MUST 保持不變

#### Scenario: Stale 或不合法修補不改變狀態

- **WHEN** 使用者取消工具，選定pair不合法，或採用因target identity、fingerprint、revision、point list、geometry或staged rebuild驗證失敗而被拒絕
- **THEN** 系統 MUST 保留操作前完整WCS Review result、confirmations、diagnostics與manual decision
- **AND** provisional Waler MUST 保留原暫定線，既有manual formal Waler MUST 保留舊formal line
- **AND** MUST NOT 留下partial formal authority、混合diagnostics或半套downstream state

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
