  # Geometry-based Support Adjacency

  Status: Approved for Design

  ## 1. Purpose

  本功能讓同一 `Zoning` 內的支撐相鄰關係，依 Project 中的實際 Strut
  幾何位置建立，不再受下列順序影響：

  - Project row order。
  - UI 顯示順序。
  - Solver input order。
  - `SharedLayoutGroup` 第一次出現的位置。

  產生的幾何相鄰關係必須一致用於：

  - Support Phase 2 全域搜尋。
  - 相鄰 Jack center `500 mm` hard constraint。
  - Jack region consistency soft penalty。
  - Manual Support result recalculation。
  - Manual neighbor checks。
  - `GlobalSolution.min_jack_distance`。
  - Solver diagnostics。

  本文件細化 `DOMAIN.md` 與 `SOLVER.md` 已記錄的 Adjacent Strut known gap，
  但不取代其中其他既有工程規則。

  ---

  ## 2. Background / Current Problem

  目前 `SupportInputBuilder` 依 Project Strut row order 建立 `SupportConfig`。
  `SupportZoneInput` 雖會將 `SharedLayoutGroup` 組成 optimization unit，unit
  順序仍由首次出現位置決定。

  Phase 2 再將 units 展開成 plan list，並把清單中的前後項目視為相鄰支撐。
  這可能造成：

  - 實際不相鄰的 Struts 被套用 `500 mm` Jack spacing。
  - 實際相鄰的 Struts 未被檢查。
  - Jack region penalty 計算在錯誤的支撐組合上。
  - 調整 Project row 順序後，合法性、分數或 Solver 結果改變。
  - Manual editing、diagnostics 與初次求解使用錯誤的 list adjacency。
  - `SharedLayoutGroup` 的兩支 lane 因展開順序參與錯誤的 adjacency chain。

  本功能只修正 adjacency 的來源，不改變既有 `500 mm` 規則、region
  penalty 權重或其他 Solver policy。

  ---

  ## 3. Scope

  ### 3.1 In scope

  本功能涵蓋：

  1. Zoning geometry validation。
  2. 建立同一 Zoning 的共同 Strut direction。
  3. 建立垂直於 Strut direction 的 row direction。
  4. 建立 adjacency／optimization units。
  5. 計算普通 Strut 與 `SharedLayoutGroup` unit 的幾何代表位置。
  6. 依 row-direction projection 建立 deterministic order。
  7. 從排序結果建立 adjacency pairs。
  8. Phase 2 使用 geometry-based adjacency contract。
  9. `500 mm` Jack spacing 使用相同 adjacency pairs。
  10. Jack region consistency 使用相同 adjacency pairs。
  11. `SharedLayoutGroup` 視為單一 adjacency unit。
  12. Manual Support editing 全域重算。
  13. Manual neighbor checks。
  14. `GlobalSolution.min_jack_distance`。
  15. Solver diagnostics 與 validation feedback。
  16. Row reorder、UI reorder 與等價 axis 表示下的 deterministic behavior。

  ### 3.2 Architecture boundary

  本功能必須遵守以下責任分工：

  - Domain：定義純幾何意義、容許值與有效性規則。
  - Application：使用 `ProjectDomainModel` geometry 建立 adjacency／ordering
    contract。
  - Algorithms：消費已建立的 adjacency contract，執行 spacing、region
    penalty 與 Beam Search。

  Algorithms 不得直接解讀 `ProjectDataModel` rows，也不得自行從 Project
  start/end、Zoning 或 Waler 關係推導現場幾何 adjacency。

  ### 3.3 Result lifecycle

  Zoning geometry validation failure 屬於 Solver operation commit 前失敗：

  - 不得 commit 新的 Support result。
  - 若已有 committed result，原結果保持不變。
  - 若原本沒有結果，仍維持 No Result。
  - 不得以 list order fallback 後繼續求解。

  ---

  ## 4. Domain Rules

  ### 4.1 Zoning

  同一 `Zoning` 表示：

  > 同一排、需要共同協調 Jack placement 的 Struts。

  同一 Zoning 中所有參與求解的實體 Struts 必須：

  - approximately parallel；
  - equal-length within tolerance。

  不同方向或不同排的 Struts，工程上應使用不同 Zoning。

  ### 4.2 Parallel validation

  平行角度比較必須忽略 axis 的 start/end 方向：

  - 同方向的 `0°` 視為平行。
  - 起終點反轉形成的 `180°` 也視為平行。
  - 使用兩條無方向性軸線之間的最小夾角。

  正式規則為：

  ```text
  angle difference <= 5°  → valid
  angle difference > 5°   → invalid
  ```

  `= 5°` 必須接受。

  有效性必須與輸入順序無關，不能只將其他 Struts 與第一筆 Project row
  比較後便決定結果。同一 Zoning 中任何一對實體 Struts 超過容許角度，
  整個 Zoning geometry 即為 invalid。

  ### 4.3 Length validation

  同一 Zoning 中任兩支實體 Struts 必須符合：

  ```text
  absolute length difference <= 5 mm  → valid
  absolute length difference > 5 mm   → invalid
  ```

  `= 5 mm` 必須接受。等價地，同一 Zoning 的最大與最小 Strut length
  差不得超過 `5 mm`。

  此規則同樣適用於 `SharedLayoutGroup` 的兩支 lane。

  ### 4.4 Common Strut direction

  合法 Zoning 必須能從全組 geometry 建立一個共同、無方向性的 Strut
  direction。

  共同方向必須：

  - 由整組 geometry 決定。
  - 不依賴第一筆 Project row。
  - 不依賴 UI 或 optimization order。
  - 將等價的 start/end 反轉視為相同 axis。
  - 對相同 geometry 產生相同結果。

  共同方向的正負號本身不具有工程意義，但必須採用固定、可重現且與輸入
  順序無關的 normalization。

  ### 4.5 Row direction

  `row direction` 為共同 Strut direction 的垂直方向。

  各 adjacency unit 的代表位置投影至 row direction 後，形成橫向排序值。
  row direction 反向只會反轉整條排序，不應改變 adjacency pair set。

  內部仍須採用 deterministic orientation，避免 Beam Search traversal 因任意
  正負方向改變。

  ### 4.6 Adjacency unit

  同一 Zoning 中：

  - 一支普通 Strut 形成一個 adjacency unit。
  - 一個 `SharedLayoutGroup` 的兩支 lane 共同形成一個 adjacency unit。

  相鄰關係建立在 units 之間，不建立在 Phase 2 展開後的原始 plan list 上。

  ### 4.7 Normal Strut representative position

  普通單支 Strut adjacency unit 的正式代表位置為 Strut axis midpoint：

  ```text
  midpoint = (axis.start + axis.end) / 2
  ```

  此代表位置：

  - 不受 Start／End 方向反轉影響。
  - 不依賴 Project row order。
  - 不依賴 UI order。
  - 不依賴 Solver input order。

  不得改用 `FromWaler` endpoint、`ToWaler` endpoint 或其他 endpoint-based
  位置作為普通 unit 的橫向排序位置。

  ### 4.8 SharedLayoutGroup representative position

  `SharedLayoutGroup` 的每支 lane 先依第 4.7 節取得自己的 axis midpoint。
  group representative position 為兩個 lane midpoint 的幾何中心：

  ```text
  group_midpoint = (lane_A_midpoint + lane_B_midpoint) / 2
  ```

  該中心投影至 row direction 後，作為整個 group unit 的橫向 projection。
  group member 的 Project row order 不得影響此位置。

  ### 4.9 Projection tie

  對已形成的兩個不同 adjacency units，正式 projection tie rule 為：

  ```text
  abs(unit_A_projection - unit_B_projection) <= 1 mm
  → transverse geometry ambiguous
  → Zoning geometry invalid
  ```

  `= 1 mm` 視為 tie。只有 projection difference `> 1 mm` 才通過此項 tie
  validation，並仍須符合其他 Zoning geometry rules。

  此 `1 mm` 是幾何數值／重疊判定 tolerance：

  - 不是新的施工容許誤差。
  - 不是 Solver preference。
  - 不是 Solver tuning parameter。

  發生 tie 時，不得使用其他 secondary information 嘗試強行解 tie，也不得
  使用 Project row、UI order、optimization/input index、StrutID 或第一支
  Strut 作為 fallback。

  `SharedLayoutGroup` 會先形成一個 adjacency unit，因此同組兩支 lane
  彼此不適用這項跨-unit tie rule。

  ### 4.10 Adjacent pair

  將有效 units 依 row-direction projection 排序後，只建立連續 units 之間的
  pair：

  ```text
  U1, U2, U3, U4

  adjacency pairs:
  U1 ↔ U2
  U2 ↔ U3
  U3 ↔ U4
  ```

  不得額外建立：

  ```text
  U1 ↔ U3
  U1 ↔ U4
  U2 ↔ U4
  ```

  排序整體反轉時，adjacency pair set 必須保持相同。

  ### 4.11 Jack station semantics

  `jack_center` 保留目前定義：

  > 從各 Strut 起點沿 Strut axis 量測的 station。

  同一 Zoning 代表同一排支撐；Struts 必須在 `5°` 方向容許內平行，並在
  `5 mm` 長度容許內等長。因此既有：

  ```text
  abs(first.jack_center - second.jack_center)
  ```

  繼續表示相鄰支撐沿支撐方向的 Jack 錯開距離。

  `500 mm` 的工程目的是避免同一排相鄰支撐的 Jack 集中於相近截面，形成
  力學弱面。它不是兩個 Jack 在 Project 平面中的二維空間距離。

  本功能：

  - 不建立 canonical Jack coordinate transformation。
  - 不重新定義 Jack station。
  - 不改寫既有 `jack_center`。
  - 不自動反轉既有 `SupportPlan` station。
  - 不改成二維 Jack-to-Jack distance。

  Start／End 反轉只保證不改變橫向 geometry adjacency ordering；本功能不
  宣稱既有 `SupportPlan.jack_center` 會自動隨 Start／End 反轉而轉換。

  ---

  ## 5. Functional Requirements

  ### FR-1 — Geometry validation boundary

  在 Phase 2 開始前，Application 必須確認該 Zoning geometry：

  - 所有必要 Strut axes 有效。
  - 所有 Struts 符合 `5°` parallel tolerance。
  - 所有 Struts 符合 `5 mm` length tolerance。
  - 所有不同 units 的 projection difference 均大於 `1 mm`。
  - 可以建立唯一的橫向線性 unit ordering。

  任一條件不成立時，不得進入 Phase 2。

  ### FR-2 — Input-order independence

  建立共同方向、unit 代表位置、projection、排序及 adjacency pairs 時，
  不得使用：

  - Project row index。
  - UI row index。
  - 原始 `SupportConfig` index。
  - Phase 1 candidate-list index。
  - `SharedLayoutGroup` 首次出現位置。

  作為工程排序依據或最終 fallback。

  ### FR-3 — Geometry-based ordering contract

  Application 提供給 Phase 2 的 adjacency contract，至少必須能明確表達：

  - Zoning identity。
  - adjacency units。
  - 每個 unit 的實體 member identity。
  - deterministic unit order。
  - consecutive adjacency pairs。
  - `SharedLayoutGroup` identity。
  - normal unit 或 group unit 的工程語意。

  Algorithms 不得從展開後的 plan list 重新猜測 adjacency。

  ### FR-4 — Jack spacing

  每一組幾何相鄰 units 必須執行：

  ```text
  abs(first.jack_center - second.jack_center) >= 500 mm
  ```

  結果：

  - `< 500 mm`：hard constraint failure。
  - `= 500 mm`：合法。
  - `> 500 mm`：合法。

  同一 `SharedLayoutGroup` 的兩支 lane 不形成內部 adjacency pair，因此不
  執行一般 `500 mm` spacing。

  ### FR-5 — Jack region consistency

  Jack region soft penalty 必須使用與 spacing 完全相同的 geometry-based
  adjacency pairs。

  不得出現：

  - spacing 使用 geometry adjacency；
  - region penalty 使用 list adjacency。

  每個 unit boundary 的 region consistency 只計算一次，不得因
  `SharedLayoutGroup` 有兩支 lane 而重複計分。

  既有 region-difference 權重與公式不在本功能中修改。

  ### FR-6 — SharedLayoutGroup shared Jack station

  既有 `SharedLayoutGroup` invariant 應保證兩支 lane 使用相同 ordered piece
  layout，並具有相同 Jack station。

  若：

  ```text
  lane_A.jack_center != lane_B.jack_center
  ```

  此結果為 `SharedLayoutGroup` invariant violation：

  - 不得視為普通 region mismatch。
  - 不得任意採用其中一支 lane 的 Jack station。
  - 不得依 list 或 row order 選擇第一支 lane。

  ### FR-7 — SharedLayoutGroup group-level Jack region

  同組兩支 lane 仍允許具有 `<= 5 mm` 的合法長度差。即使 shared
  `jack_center` 相同，兩支 lane 也可能落在不同的個別 `jack_region_id`。

  個別 lane region 不同：

  - 不使 `SharedLayoutGroup` invalid。
  - 不新增 Engineering Hard Constraint。
  - 不得任意選用 lane A 或 lane B 的 region。

  group representative length 正式定義為：

  ```text
  group_representative_length = (lane_A.length + lane_B.length) / 2
  ```

  group-level Jack region 必須使用：

  ```text
  shared jack_center
  + group_representative_length
  + 既有 Jack region 判定規則
  ```

  得到唯一且 deterministic 的 `group-level jack_region_id`。group 對外
  adjacency boundary 的 region consistency 使用此 group-level region。

  ### FR-8 — Phase 2 search

  Phase 2 必須依 deterministic geometry unit order 進行搜尋。

  若內部仍需處理 `SharedLayoutGroup` 的兩支實體 plan：

  - 不得將兩 lane 間的 list transition 解讀為一般 adjacency。
  - 不得讓 lane 展開方式改變對外 adjacency pair。
  - 同一 geometry 與 Solver settings 下，Project row reorder 不得改變
    Phase 2 traversal semantics。

  ### FR-9 — Manual Support editing

  人工修改 Support plan 後的全域重算必須：

  - 取得同一份 geometry-based adjacency contract。
  - 重新檢查正確的 `500 mm` spacing pairs。
  - 重新計算正確的 Jack region penalty。
  - 不得直接以 `solution.plans` 的現有順序當作 adjacency。
  - 不得因舊 result plan order 恢復 list-based behavior。

  若無法建立有效 adjacency contract，staged manual result 不得被判定為
  有效並 commit。

  ### FR-10 — Neighbor checks

  人工編輯畫面中的「前一支／下一支」或鄰近支撐資訊，必須以 geometry
  unit order 為準。

  對 `SharedLayoutGroup`：

  - UI／Application 可顯示 group 或實際 member identity。
  - 工程上的 previous／next 必須是 group 外側的相鄰 unit。
  - 不得將同組另一 lane 顯示為一般 `500 mm` spacing neighbor。

  ### FR-11 — Minimum adjacent Jack distance

  `GlobalSolution.min_jack_distance` 必須是：

  > 所有 geometry-based、跨 unit adjacency pairs 的 Jack center 差值最小值。

  計算時：

  - 排除 `SharedLayoutGroup` 內部 lane pair。
  - 不比較非相鄰 units。
  - 若 Zoning 少於兩個 adjacency units，結果維持無相鄰距離資料。
  - 不得以全體 Jack center 單純數值排序取代 geometry adjacency。

  ### FR-12 — Diagnostics

  Phase 2 diagnostics 必須使用相同 adjacency contract，並能對每一 pair
  表達：

  - first unit/member identity。
  - second unit/member identity。
  - Jack center difference。
  - 是否符合 `500 mm`。
  - Jack region difference 或 penalty。
  - `SharedLayoutGroup` context，如適用。

  Diagnostics 不得另外依 `solution.plans` list order 產生不同 pair。

  ### FR-13 — Result consistency

  下列流程對相同 Project geometry 必須取得相同 adjacency pair set：

  - Initial Support solve。
  - Search escalation stages。
  - Manual Support result recalculation。
  - Manual neighbor checks。
  - Result score summary。
  - `min_jack_distance`。
  - Diagnostics。

  ---

  ## 6. SharedLayoutGroup Behavior

  ### 6.1 Unit identity

  每一個 `SharedLayoutGroup`：

  - 必須包含既有 Domain 規則要求的兩支 Strut。
  - 在 adjacency ordering 中形成一個 unit。
  - 兩支 lane 仍保留各自 StrutID。
  - 不合併或刪除實際 Strut。
  - 不改變材料分別計數的行為。
  - 必須繼續共用 ordered piece layout。

  ### 6.2 Geometry validation

  兩支 lane 都是 Zoning 中的實體 Strut，因此都必須參與：

  - parallel tolerance validation。
  - length tolerance validation。

  不能只使用 group 代表線後忽略其中一支無效 lane。

  ### 6.3 Representative geometry

  兩支 lane 各自以 axis midpoint 表示位置，group unit 再以兩 midpoint
  的中心作為代表位置。

  `SharedLayoutGroup` 會先形成 unit，才與其他 units 執行 `1 mm` projection
  tie validation；group 內兩 lane 不互相觸發跨-unit tie。

  ### 6.4 External adjacency

  假設排序結果為：

  ```text
  Normal A
  SharedLayoutGroup G1
  Normal B
  ```

  正式 adjacency 為：

  ```text
  A ↔ G1
  G1 ↔ B
  ```

  不得因 plan list 展開而將以下序列本身當成工程 adjacency：

  ```text
  A ↔ G1-A ↔ G1-B ↔ B
  ```

  其中：

  - `G1-A ↔ G1-B` 不套用一般 `500 mm` spacing。
  - group 內部不產生 Jack region consistency penalty。
  - group 對外每個 boundary 只計算一次 spacing 與 region consistency。
  - spacing 使用唯一的 shared `jack_center`。
  - region consistency 使用唯一的 group-level `jack_region_id`。
  - group 兩支 lane 的材料使用量仍分別計入全域材料統計。

  ### 6.5 Group-level invariants

  同組兩支 lane 的 shared-layout result 必須提供唯一 shared `jack_center`。
  Jack station 不一致是 group invariant violation，不能降級成一般 soft
  penalty。

  在 shared Jack station 相同且兩 lane 長度差 `<= 5 mm` 時，個別
  `jack_region_id` 不同不構成 invariant violation。唯一的 group-level region
  依兩 lane 平均長度與既有 region 判定規則產生。

  ---

  ## 7. Validation / Error Behavior

  ### 7.1 Invalid parallel geometry

  錯誤內容至少應包含：

  - Zoning ID。
  - 涉及的 Strut IDs。
  - 實際方向差。
  - 允許值 `5°`。
  - 明確說明 Phase 2 未執行。

  ### 7.2 Invalid length geometry

  錯誤內容至少應包含：

  - Zoning ID。
  - 涉及的 Strut IDs。
  - 各自長度或實際長度差。
  - 允許值 `5 mm`。
  - 明確說明 Phase 2 未執行。

  ### 7.3 Ambiguous projection

  任兩個不同 adjacency units 的 projection difference `<= 1 mm` 時：

  - Zoning geometry invalid。
  - diagnostic 必須指出發生 tie 的 units。
  - diagnostic 必須包含實際 projection difference 與 `1 mm` tolerance。
  - 不得使用 Project row、UI order、input index、StrutID 或第一支 Strut
    作為 fallback。
  - 不得進入 Phase 2。

  ### 7.4 SharedLayoutGroup invariant violation

  若同組 lane 的 Jack stations 不一致，錯誤必須：

  - 明確識別 `SharedLayoutGroup` 及兩支 member IDs。
  - 說明這是 shared-layout invariant violation。
  - 不得將其報告成普通 Jack region mismatch。
  - 不得任意選一支 lane 繼續 group-level spacing／region calculation。

  ### 7.5 No best-effort fallback

  以下行為禁止：

  - 超過 `5°` 後仍取平均方向繼續求解。
  - 超過 `5 mm` 後仍依 midpoint 排序。
  - projection difference `<= 1 mm` 時嘗試 secondary tie-break。
  - validation failure 時改用 Project row order。
  - Application validation 失敗後讓 Algorithms 自行猜測順序。
  - diagnostics 無法取得 adjacency 時退回 list adjacency。

  ### 7.6 Manual editing failure

  人工修改後若無法取得有效 geometry adjacency：

  - staged result 不得 commit。
  - 現有 committed result 保持不變。
  - 回傳清楚的 geometry validation message。
  - 不得只將方案標示為一般 Jack spacing failure，掩蓋 Zoning geometry
    invalid。

  ---

  ## 8. Determinism Requirements

  相同 Project geometry 在下列變化後，必須產生相同 adjacency pair set：

  - Project rows 重排。
  - UI rows 重排。
  - `SupportConfig` 輸入順序不同。
  - `SharedLayoutGroup` members 的 row 順序交換。
  - Strut Start／End 反轉，但線段 geometry 等價。
  - Solver cache hit 或 cache miss。
  - Phase 2 搜尋階段升級。

  共同方向與 row direction 必須由整組 geometry deterministic 地建立。

  對不同 adjacency units，只要：

  ```text
  abs(unit_A_projection - unit_B_projection) <= 1 mm
  ```

  便必須 deterministic 地拒絕該 Zoning，而不是 deterministic 地選出一個
  假的工程順序。改變 row order、member order 或 ID lexicographic order 均
  不得使相同 tie geometry 通過 validation。

  StrutID 只能用於 diagnostic identity，不能作為 geometry ordering fallback。

  Start／End 反轉的 determinism 只適用於橫向 adjacency geometry；本功能不
  建立既有 Jack station 的方向轉換契約。

  ---

  ## 9. Acceptance Criteria

  ### AC1 — Row reorder invariance

  Given 同一 Zoning 有至少三個合法 adjacency units，
  When Project rows 使用不同排列，
  Then：

  - adjacency pair set 相同；
  - `500 mm` legality 相同；
  - Jack region penalty 相同；
  - `min_jack_distance` 相同；
  - diagnostics 中的工程 pair set 相同；
  - 相同 Solver settings 下的 Phase 2 工程結果不因 row order 改變。

  ### AC2 — Parallel tolerance accepted

  Given 同一 Zoning 中任兩 Strut 的無方向性 axis angle difference `<= 5°`，
  Then geometry 可通過 parallel validation。

  Start／End 反轉不得使角度由合法變成不合法；`= 5°` 必須接受。

  ### AC3 — Parallel tolerance rejected

  Given 任一 Strut pair angle difference `> 5°`，
  Then：

  - Zoning geometry invalid；
  - Phase 2 不執行；
  - 回傳包含 Strut IDs、實際角度與 `5°` tolerance 的 diagnostic；
  - 不 commit 新結果。

  ### AC4 — Length tolerance accepted

  Given 同一 Zoning 的所有 Strut pair length difference `<= 5 mm`，
  Then geometry 可通過 length validation。

  `= 5 mm` 必須接受。

  ### AC5 — Length tolerance rejected

  Given 任一 Strut pair length difference `> 5 mm`，
  Then：

  - Zoning geometry invalid；
  - Phase 2 不執行；
  - diagnostic 包含 Strut IDs、長度差與 `5 mm` tolerance；
  - 不 commit 新結果。

  ### AC6 — Normal Strut midpoint representative

  Given 一支普通 Strut，
  Then adjacency unit representative position 等於 axis start 與 end 的 midpoint。

  交換 Start／End 或 Project row order，不得改變該 representative position
  及其橫向 projection。

  ### AC7 — SharedLayoutGroup is one midpoint-based unit

  Given 一個合法 `SharedLayoutGroup` 具有兩支 lane，
  Then：

  - adjacency ordering 中只出現一個 group unit；
  - 每支 lane 以自己的 axis midpoint 表示位置；
  - group representative position 等於兩 lane midpoint 的中心；
  - 交換兩 lane 的 Project row order，不得改變 group projection 或外部
    adjacency；
  - 兩 lane 本身不執行跨-unit `1 mm` tie validation。

  ### AC8 — Shared Jack station and group-level region

  Given `SharedLayoutGroup` 的兩支 lane 共用 ordered piece layout，
  Then：

  - 兩 lane 必須具有相同 `jack_center`；
  - 不同 `jack_center` 回報 shared-layout invariant violation；
  - 不得選用 list 中第一支 lane 的 station。

  Given 兩 lane 具有相同 `jack_center`，且 length difference `<= 5 mm`，
  When 兩 lane 個別 `jack_region_id` 不同，
  Then：

  - group 不因此 invalid；
  - `group_representative_length` 等於兩 lane length 的平均值；
  - group-level region 由 shared `jack_center`、平均長度與既有 region rule
    唯一決定；
  - row order 或 lane order 不得改變 group-level region。

  ### AC9 — No internal double-support spacing

  Given `SharedLayoutGroup` 兩支 lane 的 Jack center 相同，
  Then：

  - 不執行組內一般 `500 mm` spacing；
  - 不產生組內 region consistency penalty；
  - solution 不因兩 lane Jack center 相同而 invalid。

  ### AC10 — One adjacency definition everywhere

  Given 一個 Support result 經過 initial solve 或 manual editing，
  Then以下內容使用完全相同的 geometry adjacency：

  - Phase 2 hard constraint。
  - region consistency penalty。
  - manual recalculation。
  - neighbor checks。
  - `GlobalSolution.min_jack_distance`。
  - diagnostics。

  ### AC11 — Projection tie boundary and order-independent rejection

  Given 兩個不同 adjacency units，
  Then：

  - projection difference `< 1 mm` 時 Zoning invalid；
  - projection difference `= 1 mm` 時 Zoning invalid；
  - projection difference `> 1 mm` 時通過本項 tie validation；
  - row reorder、UI reorder、input reorder 或 StrutID 交換不得改變 rejection；
  - tie 時不得進入 Phase 2。

  ### AC12 — Existing result preservation

  Given `ProjectResultModel` 已有 committed Support result，
  When 新一輪求解因 Zoning geometry invalid 而在 commit 前失敗，
  Then原 committed result 保持不變。

  ### AC13 — External group adjacency counted once

  Given geometry order 為：

  ```text
  A, SharedLayoutGroup G1, B
  ```

  Then：

  - adjacency pair set 為 `A ↔ G1`、`G1 ↔ B`；
  - 不包含一般工程 pair `G1-A ↔ G1-B`；
  - 每個外部 boundary 的 spacing 與 region penalty 只計算一次；
  - spacing 使用 G1 的 shared `jack_center`；
  - region penalty 使用 G1 的 group-level `jack_region_id`；
  - G1 的兩支 lane 材料仍各自計數。

  ---

  ## 10. Non-goals

  本功能不處理：

  - Support Phase 1 candidate generation。
  - 單支 `SupportPlan` piece legality。
  - Jack／Shim／Steel 排列規則。
  - `TargetJackRegion` 行為。
  - Phase 1 candidate retention。
  - Phase 1 cache policy。
  - 材料比例或庫存最佳化。
  - Phase 2 Beam Width、search escalation 或 score weight。
  - Waler Solver。
  - DXF recognition。
  - CandidatePoint。
  - Project row UI ordering。
  - Project persistence schema。
  - 自動修改 Zoning。
  - 將無效 Zoning 自動拆成多個 Zoning。
  - 自動改派 `FromWaler`／`ToWaler`。
  - canonical Jack station transformation。
  - 將 Jack spacing 改成二維空間距離。
  - 修改 `500 mm` hard constraint。
  - 修改 Jack region penalty 公式或權重。

  ---

  ## 11. Open Questions

  None.

  普通 Strut midpoint、`1 mm` projection tie rule，以及 `SharedLayoutGroup`
  group-level Jack region 均已完成工程／產品決策。本文件沒有待確認的
  Product 或 Engineering ambiguity。
