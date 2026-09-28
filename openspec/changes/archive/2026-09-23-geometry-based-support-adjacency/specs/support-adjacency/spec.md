# Spec Delta

## Purpose

本 capability 定義 DXF Import 如何依 Strut geometry 建立初始 Support Zoning、Main 如何保存使用者指定的 Zoning，以及 Solver 如何驗證同一 Zoning、建立與輸入順序無關的 adjacency units 與 pairs，並保證 Support 求解、人工編輯、最小 Jack 距離及 diagnostics 使用同一份工程相鄰語意。

## ADDED Requirements

### Requirement: DXF Import shall establish initial Zoning from recognized geometry

DXF Import SHALL NOT 在圖層辨識或尚未完成的 Review 過程中建立初始 `Zoning`。系統 SHALL 僅在使用者已完成當次 DXF Review 中各 Waler／Strut 的必要確認與 geometry 修正，並執行「完成匯入」後，依最終 reviewed geometry 建立初始 `Zoning`；此步驟 SHALL 發生於建立 Project rows 之前。此分組只是一份進入 Main 前的 initial suggestion，不是後續 authoritative Zoning。

對不屬於同一個已確認 `SharedLayoutGroup` 的一般 Struts，自動分組 SHALL 將無方向性 axis angle difference `<= 5°` 且 length difference `<= 5 mm` 視為可屬於同一 Zoning 的必要條件，而非充分條件；任一條件超出容差的 Struts SHALL NOT 被自動分入同一 Zoning。系統 SHALL 同時使用 Waler connection topology 與橫向空間順序辨識 initial support row，且 SHALL NOT 只依賴 DXF entity order、recognition output order 或 Project row order。

使用者已在 DXF Review 確認為雙路支撐的 `SharedLayoutGroup` SHALL 視為一個不可拆分的 initial-grouping ordering unit，兩支 physical lanes SHALL 取得相同 initial `Zoning`。若兩支 lanes 的 angle 或 length 差異超出 Solver geometry tolerance，系統 SHALL 仍允許完成匯入並在 Main 保存該使用者已確認的 shared relationship，但 Support Solver SHALL 在進入 Phase 2 前拒絕該 Zoning；系統 SHALL NOT 因此自動解除 `SharedLayoutGroup` 或改寫其 Zoning。

當 Struts 的兩端分別連接至幾何上相同的兩條連續 Waler chains 時，即使各端對應的 Waler member IDs 不同，系統 SHALL 將其視為 topology-compatible。當 Waler connection topology 缺失或有歧義時，系統 SHALL 使用 deterministic transverse spatial order 作為 initial grouping fallback。當 topology 明確顯示 Struts 連接不同 Waler chains 時，空間 fallback SHALL NOT 覆寫該衝突。

每一個 initial Zoning SHALL 是完整 transverse geometry order 中的連續區段。系統 SHALL NOT 跳過位於兩個 Struts 之間的其他 Strut，把兩側 Struts 單獨放入同一 initial Zoning。對 geometry order 中相鄰且符合其他 initial-grouping 條件的候選，系統 SHALL NOT 僅因兩者的絕對空間距離較大而拆組；本 capability 不定義固定最大相鄰距離。

當 topology 缺失或有歧義的 Strut 可同時合理歸入兩個互相衝突的 initial runs，系統 SHALL 採 conservative grouping：該 Strut SHALL 保持為獨立 initial Zoning並產生 ambiguity diagnostic，而非依來源順序、row order或任意一側猜測歸組。

#### Scenario: Initial grouping does not run during an unfinished DXF Review

- **WHEN** DXF 圖層與 members 已完成辨識
- **AND** 使用者尚未完成當次 Review 中各 Waler／Strut 的必要確認或尚未執行「完成匯入」
- **THEN** 系統 SHALL NOT 建立或套用 initial `Zoning`
- **AND** SHALL NOT 因 Review polling 或局部修正而反覆改寫 Project rows

#### Scenario: Completing DXF Review triggers initial grouping

- **WHEN** 使用者完成必要確認與 geometry 修正並執行「完成匯入」
- **THEN** 系統 SHALL 使用該次最終 reviewed geometry 建立 initial `Zoning`
- **AND** SHALL 在建立 Project rows 前完成此步驟

#### Scenario: Topology-compatible recognized Struts receive an automatic initial grouping

- **WHEN** DXF Import 已辨識出兩支或多支 Struts
- **AND** 其無方向性 axis angle differences 均 `<= 5°`
- **AND** 其 length differences 均 `<= 5 mm`
- **AND** 其兩端分別連接至幾何上相同的兩條連續 Waler chains
- **AND** 其 members 在 transverse geometry order 中形成連續區段
- **THEN** DXF Import SHALL 自動為其建立共同的初始 `Zoning`
- **AND** 使用者 SHALL NOT 必須逐支手動建立該初始分組

#### Scenario: Different Waler member IDs may represent the same continuous chains

- **WHEN** 兩支符合 angle 與 length eligibility 的 Struts 連接至不同 Waler member IDs
- **AND** 這些 Waler members 的 geometry 分別構成相同的兩條連續 Waler chains
- **THEN** DXF Import SHALL NOT 僅因 Waler member IDs 不同而強制拆分 initial Zoning

#### Scenario: Spatial adjacency is used when Waler topology is unavailable

- **WHEN** 兩支符合 angle 與 length eligibility 的 Struts 之 Waler connection 缺失或有歧義
- **AND** 兩者在 deterministic transverse geometry order 中相鄰
- **THEN** DXF Import SHALL 允許以其空間相鄰關係建立共同的初始 `Zoning`
- **AND** SHALL NOT 使用 DXF entity order 或 recognition output order 取代 geometry order

#### Scenario: Ambiguous spatial assignment remains independent

- **WHEN** 一支 topology 缺失或有歧義的 Strut 在 transverse geometry order 中可同時合理歸入左右兩個互相衝突的 initial runs
- **THEN** DXF Import SHALL 將該 Strut 保持為獨立 initial `Zoning`
- **AND** SHALL 產生可識別該 Strut 的 ambiguity diagnostic
- **AND** SHALL NOT 依 DXF entity order、recognition output order 或任意一側猜測歸組

#### Scenario: Explicitly different Waler chains are not overridden by spatial fallback

- **WHEN** 兩支 Struts 的 Waler connection topology 明確連接至不同的 Waler chain pairs
- **THEN** DXF Import SHALL NOT 僅因兩者在空間上相鄰而將其自動分入同一 `Zoning`

#### Scenario: Out-of-tolerance Struts are not automatically grouped together

- **WHEN** 兩支已辨識 Struts 的無方向性 axis angle difference `> 5°` 或 length difference `> 5 mm`
- **AND** 兩者不屬於同一個已由使用者確認的 `SharedLayoutGroup`
- **THEN** DXF Import SHALL NOT 將兩者自動指定為同一 `Zoning`

#### Scenario: Confirmed double support remains one initial ordering unit

- **WHEN** 使用者已在 DXF Review 確認兩支 physical lanes 屬於同一 `SharedLayoutGroup`
- **THEN** initial grouping SHALL 將兩支 lanes 視為一個 ordering unit
- **AND** SHALL 為兩支 lanes 指定相同 initial `Zoning`
- **AND** SHALL 保留兩支 physical Strut identities
- **AND** lane order SHALL NOT 改變該 unit 的 initial Zoning membership

#### Scenario: Out-of-tolerance confirmed double support imports but cannot be solved

- **WHEN** 使用者已確認一個 `SharedLayoutGroup`
- **AND** 兩支 lanes 的 angle difference `> 5°` 或 length difference `> 5 mm`
- **THEN** DXF Import SHALL 仍允許兩支 lanes 以相同 initial `Zoning` 進入 Main
- **AND** Main SHALL 允許查看、修改及保存該資料
- **AND** Support Solver SHALL 在進入 Phase 2 前拒絕該 Zoning
- **AND** 系統 SHALL NOT 自動解除 shared relationship、拆分 Zoning 或覆寫使用者資料

#### Scenario: Initial grouping cannot skip an intervening Strut

- **WHEN** transverse geometry order 為 `S1, S2, S3`
- **THEN** DXF Import SHALL NOT 建立只包含 `S1` 與 `S3`、但排除 `S2` 的同一 initial Zoning
- **AND** 若 `S2` 無法與相鄰候選形成同組關係，該位置 SHALL 成為 initial Zoning boundary

#### Scenario: A large gap alone does not split consecutive eligible Struts

- **WHEN** 兩支 Struts 在 transverse geometry order 中相鄰
- **AND** 兩者符合 angle、length 與 topology 或 spatial-fallback grouping conditions
- **AND** 兩者之間沒有其他 Strut
- **THEN** DXF Import SHALL NOT 僅因兩者的絕對空間距離較大而強制拆成不同 initial Zonings

#### Scenario: DXF source order does not define the initial grouping

- **WHEN** 相同的 recognized Strut geometry 以不同 DXF entity order 或 recognition output order 提供
- **THEN** DXF Import SHALL 產生等價的初始 Zoning membership
- **AND** Start／End 表示反轉 SHALL NOT 改變該 membership

### Requirement: Initial Zoning application shall respect import mode

系統 SHALL 僅對本次 DXF Review 產生的新 imported Strut rows 套用 deterministic initial `Zoning`。Replace SHALL 以本次 imported rows 建立新的工程 geometry；Append SHALL 保留所有既有 Project rows 的 `Zoning` membership與名稱，且 SHALL NOT 重新分組、覆寫或改名既有 rows。Append 中新建立的 initial Zoning名稱 SHALL 與既有 Project Zoning名稱保持唯一，不得因名稱碰撞使新舊群組被誤視為同一 Zoning。

#### Scenario: Replace assigns Zoning only to the current imported result

- **WHEN** 使用者以 Replace 完成 DXF Import
- **THEN** 系統 SHALL 只依本次最終 reviewed geometry為本次 imported Strut rows建立deterministic initial `Zoning`
- **AND** SHALL NOT 從被取代的舊Project geometry繼承或混入Zoning membership

#### Scenario: Append preserves existing Project Zoning

- **WHEN** 使用者以 Append 完成 DXF Import
- **THEN** 系統 SHALL 保留既有 Project rows 的 Zoning membership與名稱
- **AND** SHALL NOT 重新分組、覆寫或改名既有 Project rows
- **AND** SHALL 只為本次新增的 imported Strut rows建立initial `Zoning`

#### Scenario: Appended Zoning names do not collide

- **WHEN** Append產生的initial Zoning建議名稱與既有Project Zoning名稱相同
- **THEN** 系統 SHALL deterministic地配置另一個未使用名稱
- **AND** SHALL NOT 因名稱碰撞將新imported rows與既有rows合併為同一Zoning

### Requirement: Main Zoning edits shall remain user-controlled

Project 進入 Main 後，initial Zoning suggestion SHALL 以一般可編輯的 Project `Zoning`資料顯示，不新增獨立的 Zoning confirmation state或強制確認步驟；目前保存的 `Zoning` SHALL 由使用者決定。Main SHALL 允許使用者修改及保存 `Zoning`，即使修改後的成員暫時不符合 `5°` 或 `5 mm` geometry tolerance；Main SHALL NOT 僅因該 tolerance 在欄位編輯或 Project 儲存時拒絕、復原、自動拆分或改回 DXF 初始分組。後續 Support Solver SHALL 以 Main 當下保存的 Zoning membership 作為求解前 geometry validation 的輸入，且 SHALL NOT 以 DXF 初始分組覆寫它。

#### Scenario: User-defined Zoning is retained in Main

- **WHEN** 使用者在 Main 將 Struts 改派至不同 `Zoning`
- **THEN** Main SHALL 保存使用者指定的 membership
- **AND** SHALL NOT 自動恢復為 DXF Import 的初始 membership

#### Scenario: Editing and saving do not enforce solver geometry tolerance

- **WHEN** 使用者建立一個 angle difference `> 5°` 或 length difference `> 5 mm` 的 Zoning membership
- **THEN** Main SHALL 允許該 Project 資料被編輯及保存
- **AND** geometry tolerance failure SHALL 延後至 Support Solver 求解前驗證

#### Scenario: Solver validates the current Project grouping

- **WHEN** 使用者啟動 Support Solver
- **THEN** Solver SHALL 驗證 Main 當下保存的 Zoning membership
- **AND** SHALL NOT 重新執行 DXF Zoning 自動分組或覆寫 Project 資料

### Requirement: Zoning geometry shall be valid before Phase 2

系統 SHALL 在每次 Support 求解或相關全域重算進入 Phase 2 前，驗證 Main 當下 `Zoning` 內所有參與求解的實體 Struts，包含 `SharedLayoutGroup` 的每一支 lane。每一條 axis SHALL 為有效非零長度線段；任兩條無方向性 axes 的最小夾角 SHALL 不大於 `5°`，任兩支 Struts 的長度差 SHALL 不大於 `5 mm`。此驗證 SHALL 決定能否求解，但 SHALL NOT 修改 Project 中的 Zoning membership。

#### Scenario: Boundary-valid parallel geometry is accepted

- **WHEN** 同一 Zoning 內所有必要 Strut pairs 的無方向性 axis angle difference 均 `<= 5°`
- **THEN** 系統 SHALL 將該 Zoning 視為通過 parallel validation
- **AND** angle difference 正好為 `5°` SHALL 被接受
- **AND** 反轉任一 axis 的 Start／End SHALL NOT 改變驗證結果

#### Scenario: Excessive angle difference rejects the zoning

- **WHEN** 同一 Zoning 內任一 Strut pair 的無方向性 axis angle difference `> 5°`
- **THEN** 系統 SHALL 將整個 Zoning geometry 標示為 invalid
- **AND** SHALL NOT 進入 Phase 2
- **AND** SHALL NOT 以 best-effort average direction 繼續求解
- **AND** SHALL NOT 自動拆分或改寫 Project 中的 Zoning membership

#### Scenario: Boundary-valid length difference is accepted

- **WHEN** 同一 Zoning 內最長與最短 physical Strut 的長度差 `<= 5 mm`
- **THEN** 系統 SHALL 將該 Zoning 視為通過 length validation
- **AND** length difference 正好為 `5 mm` SHALL 被接受

#### Scenario: Excessive length difference rejects the zoning

- **WHEN** 同一 Zoning 內任兩支 physical Struts 的長度差 `> 5 mm`
- **THEN** 系統 SHALL 將整個 Zoning geometry 標示為 invalid
- **AND** SHALL NOT 進入 Phase 2
- **AND** SHALL NOT 繼續使用 midpoint ordering
- **AND** SHALL NOT 自動拆分或改寫 Project 中的 Zoning membership

### Requirement: Common directions shall be derived deterministically from the full zoning geometry

合法 Zoning 的 common Strut direction SHALL 由全組 physical Strut geometry 建立，並 SHALL 將等價的 Start／End 反轉視為同一無方向性 axis。Row direction SHALL 為 common Strut direction 的垂直方向。二者的建立 SHALL NOT 依賴第一筆 Project row、UI order、optimization order 或 `SharedLayoutGroup` 第一次出現的位置。

#### Scenario: Reordered rows produce the same direction semantics

- **WHEN** 同一組 Project geometry 以不同 Project／UI／input row order 提供
- **THEN** 系統 SHALL 產生相同的 common undirected Strut direction 與等價 row direction

#### Scenario: Reversed endpoints preserve transverse geometry

- **WHEN** 一支或多支 Struts 的 Start 與 End 交換，但實際線段 geometry 不變
- **THEN** 系統 SHALL 保持相同的橫向 adjacency semantics

### Requirement: Adjacency units shall use geometry-defined representative positions

普通 Strut SHALL 形成一個 adjacency unit，且其 representative position SHALL 為 axis midpoint。合法 `SharedLayoutGroup` 的兩支 lanes SHALL 共同形成一個 adjacency unit，其 representative position SHALL 為兩支 lane axis midpoints 的幾何中心。

#### Scenario: Normal Strut uses its axis midpoint

- **WHEN** 系統建立普通 Strut 的 adjacency unit
- **THEN** representative position SHALL 等於 axis Start 與 End 的 midpoint
- **AND** SHALL NOT 使用 `FromWaler` endpoint、`ToWaler` endpoint 或其他 endpoint-based 位置

#### Scenario: Shared layout group uses the center of both lane midpoints

- **WHEN** 系統建立一個由兩支 lanes 構成的 `SharedLayoutGroup` unit
- **THEN** 兩支 lanes SHALL 在 adjacency ordering 中只產生一個 unit
- **AND** group representative position SHALL 等於兩支 lane midpoints 的幾何中心
- **AND** 交換兩支 lanes 的 row order SHALL NOT 改變 representative position

#### Scenario: All shared lanes remain physical members

- **WHEN** `SharedLayoutGroup` 被建立為一個 adjacency unit
- **THEN** 系統 SHALL 保留兩支 lanes 各自的 Strut identity
- **AND** SHALL 將兩支 Struts 的材料用量分別計數
- **AND** SHALL 繼續要求兩支 lanes 共用 ordered piece layout

### Requirement: Unit ordering and adjacency shall be geometry-based

系統 SHALL 將每個 adjacency unit 的 representative position 投影至 row direction，依 projection 建立 deterministic linear order，並只將排序後的 consecutive units 建立為 adjacency pairs。Project row order、UI order、`SupportConfig` order、Phase 1 candidate order、StrutID 與 group first occurrence SHALL NOT 作為工程排序依據或 fallback。

#### Scenario: Three or more units use only consecutive geometry pairs

- **WHEN** geometry projection order 為 `U1, U2, U3, U4`
- **THEN** adjacency pairs SHALL 為 `U1 ↔ U2`、`U2 ↔ U3` 與 `U3 ↔ U4`
- **AND** SHALL NOT 額外建立 `U1 ↔ U3`、`U1 ↔ U4` 或 `U2 ↔ U4`

#### Scenario: Row reordering preserves adjacency pairs

- **WHEN** 相同 Project geometry 的三個以上 units 以不同 row／UI／input order 提供
- **THEN** 系統 SHALL 產生相同的 adjacency pair set

#### Scenario: Reversing row direction preserves the engineering pair set

- **WHEN** deterministic row direction 的表示方向整體反轉
- **THEN** unit traversal order MAY 整體反轉
- **AND** unordered adjacency pair set SHALL 保持相同

### Requirement: Ambiguous transverse projections shall be rejected

任兩個不同 adjacency units 的 projection difference `<= 1 mm` SHALL 被視為 transverse geometry ambiguous，並 SHALL 使整個 Zoning geometry invalid。系統 SHALL NOT 使用 row order、UI order、input index、StrutID 或其他 secondary tie-break 強行排序。

#### Scenario: Projection below the tolerance is invalid

- **WHEN** 兩個不同 adjacency units 的 projection difference `< 1 mm`
- **THEN** 系統 SHALL 拒絕該 Zoning
- **AND** SHALL NOT 進入 Phase 2

#### Scenario: Projection exactly at the tolerance is invalid

- **WHEN** 兩個不同 adjacency units 的 projection difference `= 1 mm`
- **THEN** 系統 SHALL 拒絕該 Zoning
- **AND** SHALL NOT 使用任何 fallback order

#### Scenario: Projection above the tolerance passes the tie rule

- **WHEN** 所有不同 adjacency units 的 projection difference `> 1 mm`
- **THEN** 系統 SHALL 將該 Zoning 視為通過 projection-tie validation
- **AND** 仍 SHALL 驗證其他 Zoning geometry rules

#### Scenario: Shared lanes do not tie with each other

- **WHEN** 兩支 lanes 屬於同一 `SharedLayoutGroup`
- **THEN** 系統 SHALL 先將它們建立為一個 adjacency unit
- **AND** SHALL NOT 在組內套用跨 unit 的 `1 mm` projection-tie rule

### Requirement: Adjacent Jack spacing shall use longitudinal station offset

每一組 geometry-adjacent、跨 unit 的支撐 SHALL 滿足 `abs(first.jack_center - second.jack_center) >= 500 mm`。`jack_center` SHALL 保留從各 Strut 起點沿該 Strut axis 量測的 station 定義，該距離 SHALL NOT 被改為二維 Jack-to-Jack 空間距離。

#### Scenario: Adjacent station offset below 500 mm is illegal

- **WHEN** 兩個 geometry-adjacent units 的 Jack station offset `< 500 mm`
- **THEN** 系統 SHALL 將該 candidate combination 視為 hard-constraint failure

#### Scenario: Adjacent station offset at or above 500 mm is legal

- **WHEN** 兩個 geometry-adjacent units 的 Jack station offset `>= 500 mm`
- **THEN** 系統 SHALL 將該 pair 視為通過 Jack spacing constraint
- **AND** offset 正好為 `500 mm` SHALL 被接受

#### Scenario: Non-adjacent units are not compared for spacing

- **WHEN** 兩個 units 不是 geometry ordering 中的 consecutive units
- **THEN** 系統 SHALL NOT 對它們套用相鄰 Jack `500 mm` constraint

#### Scenario: The feature does not reinterpret Jack station

- **WHEN** 系統計算 adjacency spacing
- **THEN** 系統 SHALL 使用現有 `SupportPlan.jack_center` station
- **AND** SHALL NOT 建立 canonical Jack coordinate transformation
- **AND** SHALL NOT 根據二維 Project 座標重新計算 Jack distance

### Requirement: SharedLayoutGroup shall expose one external Jack fact

同一 `SharedLayoutGroup` 的兩支 lanes SHALL 具有相同 `jack_center`。當 shared Jack station 一致時，group-level `jack_region_id` SHALL 使用 shared `jack_center` 與合併後的 Column stations／`pile_centers` 透過既有 `get_jack_region_id(jack_center, pile_centers)` 規則唯一決定。Strut total length 或 lane length difference SHALL NOT 參與 Jack region calculation。

#### Scenario: Shared Jack mismatch is an invariant violation

- **WHEN** 同一 `SharedLayoutGroup` 兩支 lanes 的 `jack_center` 不同
- **THEN** 系統 SHALL 回報 `SHARED_JACK_INVARIANT_VIOLATION`
- **AND** SHALL NOT 任意選用任一 lane 的 Jack station
- **AND** SHALL NOT 將它降級為一般 region mismatch

#### Scenario: Shared group region uses merged pile centers

- **WHEN** 同一 `SharedLayoutGroup` 兩支 lanes 具有相同 `jack_center`
- **AND** 兩支 lanes 的 Column stations 已合併為 shared `pile_centers`
- **THEN** group-level `jack_region_id` SHALL 由 shared `jack_center` 與 merged `pile_centers` 透過既有 `get_jack_region_id()` 唯一決定
- **AND** row order 或 lane order SHALL NOT 改變該 region

#### Scenario: Lane length difference does not define the group region

- **WHEN** 同組 lanes 通過 `<= 5 mm` Zoning length validation
- **THEN** 系統 SHALL NOT 以 lane 平均長度、`representative_length` 或任何 length-based rule 計算 group-level Jack region

#### Scenario: Internal shared lanes do not form an adjacency boundary

- **WHEN** 兩支 lanes 屬於同一 `SharedLayoutGroup`
- **THEN** 系統 SHALL NOT 執行組內一般 `500 mm` spacing
- **AND** SHALL NOT 產生組內 Jack region consistency penalty

#### Scenario: External group boundaries are counted once

- **WHEN** geometry unit order 為 `Normal A, SharedLayoutGroup G1, Normal B`
- **THEN** adjacency pairs SHALL 為 `A ↔ G1` 與 `G1 ↔ B`
- **AND** 每個 external boundary 的 spacing 與 region consistency SHALL 各計算一次
- **AND** SHALL NOT 建立一般工程 pair `G1-A ↔ G1-B`

### Requirement: Jack region consistency shall use the same adjacency pairs

Jack region consistency soft penalty SHALL 使用與 Jack spacing 完全相同的 geometry-based adjacency pairs。每個 adjacency-unit boundary SHALL 只計算一次 region difference；本 capability SHALL NOT 修改既有 region-difference formula 或 weight。

#### Scenario: Region penalty follows geometry adjacency

- **WHEN** 系統重算一個 Support global solution
- **THEN** 每一組套用 region penalty 的 pair SHALL 來自 geometry-based adjacency contract
- **AND** SHALL NOT 來自 flattened physical-plan list order

#### Scenario: Shared group region penalty is not duplicated

- **WHEN** `SharedLayoutGroup` 與一個外部 unit 相鄰
- **THEN** 系統 SHALL 使用 group-level `jack_region_id` 計算一次 region consistency
- **AND** SHALL NOT 因兩支 physical lanes 重複計分

### Requirement: Phase 2 shall consume the geometry adjacency contract

Support Phase 2 SHALL 依 deterministic geometry unit order 處理 candidates，並 SHALL 以 unit adjacency 套用 spacing 與 region consistency。Algorithms SHALL NOT 從 flattened `SupportPlan` list、Project rows 或 `SharedLayoutGroup` member expansion 重新推測 adjacency。

#### Scenario: Row reorder does not alter Phase 2 engineering results

- **WHEN** 相同 Project geometry 以不同 row order 求解，且 Solver settings 相同
- **THEN** Phase 2 SHALL 使用相同 adjacency pair set
- **AND** `500 mm` legality 與 Jack region penalty SHALL 保持相同

#### Scenario: Shared member expansion does not create extra transitions

- **WHEN** Phase 2 內部保留 `SharedLayoutGroup` 的兩支 physical plans
- **THEN** 系統 SHALL NOT 將兩支 lanes 之間的 list transition 解讀為一般 adjacency
- **AND** member expansion order SHALL NOT 改變 group 對外的 adjacency pairs

#### Scenario: Search stages use the same adjacency

- **WHEN** Support global search 升級至不同 search stage 或 Phase 1 candidate cache 命中狀態改變
- **THEN** 所有 stages SHALL 繼續使用同一份 geometry adjacency contract

### Requirement: Manual support editing shall reuse geometry adjacency

人工修改 Support plan 後的全域重算、neighbor checks 與結果分析 SHALL 使用與 initial solve 相同的 geometry adjacency semantics，並 SHALL NOT 以現有 `solution.plans` 順序作為 adjacency。

#### Scenario: Manual recalculation uses the initial-solve pair set

- **WHEN** 使用者人工修改一個 Support plan 並觸發 staged global recalculation
- **THEN** 系統 SHALL 重建或取得當前 Project geometry 的 adjacency contract
- **AND** SHALL 以該 contract 重新檢查 spacing 與 region consistency

#### Scenario: Manual neighbors are external unit neighbors

- **WHEN** 使用者檢視普通 Strut 或 `SharedLayoutGroup` member 的前一支／後一支支撐
- **THEN** neighbor checks SHALL 回報 geometry unit order 中的 external previous／next units
- **AND** SHALL NOT 將同組另一支 lane 當作一般 `500 mm` spacing neighbor

#### Scenario: Invalid manual adjacency is not committed

- **WHEN** 人工修改後無法建立有效 geometry adjacency 或發生 shared Jack invariant violation
- **THEN** staged result SHALL NOT 被 commit
- **AND** 現有 committed result SHALL 保持不變

### Requirement: Minimum adjacent Jack distance shall use geometry adjacency

`GlobalSolution.min_jack_distance` SHALL 為所有 geometry-based、跨 unit adjacency pairs 之 Jack station offset 的最小值。系統 SHALL 排除 `SharedLayoutGroup` 內部 lane pair，並 SHALL NOT 比較非相鄰 units 或以全體 Jack centers 單純數值排序取代 geometry adjacency。

#### Scenario: Minimum distance uses only consecutive units

- **WHEN** 一個 Zoning 含有兩組以上 geometry adjacency pairs
- **THEN** `min_jack_distance` SHALL 等於這些 pairs 的 Jack station offsets 最小值

#### Scenario: Fewer than two units has no adjacent distance

- **WHEN** 一個 Zoning 少於兩個 adjacency units
- **THEN** `min_jack_distance` SHALL 表示沒有相鄰距離資料

### Requirement: Diagnostics shall report geometry-based adjacency facts

Support validation 與 Phase 2 diagnostics SHALL 使用同一 geometry adjacency contract。Pair diagnostics SHALL 能識別雙方 unit／member identity、Jack station offset、`500 mm` 合法性、Jack region difference／penalty 及適用的 `SharedLayoutGroup` context。

#### Scenario: Pair diagnostics match solver pairs

- **WHEN** Phase 2 建立 adjacency-pair diagnostics
- **THEN** diagnostics 中的 pair set SHALL 與 spacing 及 region consistency 實際使用的 pair set 相同
- **AND** SHALL NOT 由 `solution.plans` list order 另行產生 pairs

#### Scenario: Invalid angle diagnostic is explicit

- **WHEN** Zoning 因 angle difference `> 5°` 失敗
- **THEN** diagnostic SHALL 包含 Zoning ID、涉及的 Strut IDs、實際角度、`5°` tolerance 與 Phase 2 未執行的說明

#### Scenario: Invalid length diagnostic is explicit

- **WHEN** Zoning 因 length difference `> 5 mm` 失敗
- **THEN** diagnostic SHALL 包含 Zoning ID、涉及的 Strut IDs、實際長度或長度差、`5 mm` tolerance 與 Phase 2 未執行的說明

#### Scenario: Projection tie diagnostic is explicit

- **WHEN** Zoning 因 unit projection difference `<= 1 mm` 失敗
- **THEN** diagnostic SHALL 包含發生 tie 的 units、實際 projection difference、`1 mm` tolerance 與 Phase 2 未執行的說明

#### Scenario: Shared Jack invariant diagnostic is explicit

- **WHEN** `SharedLayoutGroup` 兩支 lanes 的 Jack stations 不一致
- **THEN** diagnostic SHALL 識別 group 與兩支 member IDs
- **AND** SHALL 明確說明這是 shared-layout invariant violation，而非一般 Jack region mismatch

### Requirement: Validation failure shall preserve the committed result

Zoning geometry validation 或 Shared Jack invariant validation 若在 Solver operation commit 前失敗，系統 SHALL NOT commit 新 Support result。若已有 committed result，該結果 SHALL 保持不變；若原本沒有 result，系統 SHALL 維持 No Result。

#### Scenario: Previous result survives geometry validation failure

- **WHEN** `ProjectResultModel` 已有 committed Support result
- **AND** 新一輪求解因 invalid Zoning geometry 而在 commit 前失敗
- **THEN** 系統 SHALL 保留原 committed result
- **AND** SHALL NOT 以 row-order fallback 產生新結果

#### Scenario: No-result state remains unchanged after validation failure

- **WHEN** Project 原本沒有 committed Support result
- **AND** 新一輪求解在 commit 前因 adjacency validation 失敗
- **THEN** Project SHALL 維持 No Result

### Requirement: Existing unrelated solver behavior shall remain unchanged

本 capability SHALL 只改變 DXF Import 對已辨識 Struts 的初始 Zoning 判定，以及 Support adjacency 的建立與消費方式。系統 SHALL NOT 因本 change 改變 Support Phase 1 candidate generation、個別 plan legality、`TargetJackRegion`、Jack region formula／boundary、region penalty weight、material optimization、search tuning、Project persistence schema、Waler Solver、DXF member／line recognition 或 CandidatePoint。

#### Scenario: General DXF recognition remains unchanged

- **WHEN** DXF Import 為已辨識的 Struts 建立初始 `Zoning`
- **THEN** 此步驟 SHALL 消費既有 member recognition 的結果
- **AND** SHALL NOT 改變哪些 DXF entities 被辨識為 Strut 或其他工程構件

#### Scenario: Existing Jack region rule is preserved

- **WHEN** 系統計算普通或 shared unit 的 Jack region
- **THEN** 系統 SHALL 繼續使用現有 `get_jack_region_id(jack_center, pile_centers)` 語意
- **AND** SHALL NOT 引入 length-based region rule

#### Scenario: Phase 1 and persistence contracts remain unchanged

- **WHEN** 本 capability 被套用
- **THEN** Support Phase 1 candidate behavior SHALL 保持不變
- **AND** Project persistence schema SHALL 保持不變
