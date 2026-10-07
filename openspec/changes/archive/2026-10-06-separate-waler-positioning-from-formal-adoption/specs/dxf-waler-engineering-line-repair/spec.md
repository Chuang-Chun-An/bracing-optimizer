# Spec Delta：以圍令正式化修補工具採用工程線

## 閱讀導航

- **必讀**：「人工修補必須是明確且合格的操作」全文；本 delta 將正式化入口集中到「修改工具 → 圍令正式化」。
- **必讀**：「修補工具只對合格圍令出現」、「工具選擇線的來源」、「以既有候選點正式採用暫定線」及「Stale 或不合法修補不改變狀態」scenarios；它們定義入口、來源與transaction boundary。
- **條件式閱讀**：修改CAD路徑時閱讀「以CAD工程線正式採用」、「沒有同member CAD線時停用選項」與「工具開啟後CAD線更新」；修改一般套用時閱讀「已正式化Waler的一般套用被拒絕」；驗證Y29時閱讀「W14不改點即可直接採用」。
- **可先跳過**：主spec的診斷allowlist、寬度／材料、Pause／Resume、source exclusion及支撐側細節；本delta不修改這些既有規則。

## MODIFIED Requirements

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
