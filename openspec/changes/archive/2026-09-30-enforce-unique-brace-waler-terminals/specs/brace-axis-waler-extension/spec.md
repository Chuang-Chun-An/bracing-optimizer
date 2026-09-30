# Spec Delta

## 閱讀導航

- **必讀**：「Brace 直接端點連接必須優先於軸向延伸」與「延伸結果必須一致更新正式 Brace 連接」；兩者定義每端唯一性及整支 Brace 的原子式正式提交。
- **必讀**：「Terminal evidence 必須單向支援 Waler contact-face 判定」；定義唯一端 evidence 可參與接觸側判定、ambiguous 端不得參與，以及 member verdict 不得形成循環依賴。
- **必讀**：「延伸失敗不得改變可靠 recognition 軸或提交不完整 Project」；定義 unresolved 與 blocking 行為。
- **條件式閱讀**：「Review 與人工端點操作必須沿用同一連接語意」；修改 Candidate Points、manual replay、exclusion／restore 或 Review 顯示時必讀。
- **條件式閱讀**：「Y29 重疊 Waler 端點必須維持未解析」；處理 Y29 fixture 或 duplicate-Waler regression 時必讀。
- **可先跳過**：主規格中的 Y05 軸向延伸距離案例及其他 member role 規格；本 delta 不改 250 mm／600 mm 邊界，也不改 Strut 或 CornerBrace。

## MODIFIED Requirements

### Requirement: Brace 直接端點連接必須優先於軸向延伸

系統 SHALL 先沿用既有 endpoint-to-Waler direct connection：當 Brace 端點位於既有 `connection_tolerance_mm` 內時，只有該端最近合法位置可唯一識別一支有限 Waler segment，才可形成 direct terminal resolution。只有找不到任何合法 direct 候選的 Brace 端點，才可進入軸向延伸判定；若最近合法位置有兩支以上無法依既有 ambiguity boundary 區分的 Waler，該端 MUST 保持 ambiguous，MUST NOT 改走軸向延伸或以 Waler ID、DXF handle、entity order、candidate order、浮點微差選出一支。此能力 MUST NOT 套用至 Strut、CornerBrace 或其他 member role。

此 Requirement 是 DXF Recognition Hard Constraint，不是 Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 端點已可直接連接

- **WHEN** Brace 端點在既有 connection tolerance 內可唯一連接有限 Waler segment
- **THEN** 系統 SHALL 使用既有 direct connection 結果
- **AND** MUST NOT 以軸向延伸改選其他 Waler

#### Scenario: 只有未連接端進入延伸

- **WHEN** Brace 一端已唯一直接連接 Waler，另一端沒有任何合法 direct 候選
- **THEN** 系統 SHALL 保留已連接端的 resolution evidence
- **AND** SHALL 僅對沒有 direct 候選的端執行軸向延伸判定

#### Scenario: Direct 最近位置有多支 Waler

- **WHEN** Brace 端點在 direct connection tolerance 內的最近合法位置同時對應兩支以上無法區分的有限 Waler
- **THEN** 該端 MUST 標示為 ambiguous 並產生 blocking problem
- **AND** MUST NOT 以軸向延伸、候選點或任一非幾何順序打破歧義

#### Scenario: Strut 行為不變

- **WHEN** Strut 端點超出既有 Waler connection tolerance
- **THEN** 本 capability MUST NOT 沿 Strut 軸向自動延伸端點
- **AND** Strut SHALL 維持既有 connection validation behavior

### Requirement: 延伸結果必須一致更新正式 Brace 連接

每一端的 direct／extension resolution SHALL 先保存為該次 staged recognition 的 terminal evidence，不得各自直接改寫部分正式 Brace。只有下列條件全部成立時，系統才 SHALL 一次更新兩個正式 endpoints、`FromWaler`、`ToWaler` 與完整 formal Brace geometry：start 與 end 各自恰好具有一筆唯一 terminal evidence；任一端均無 blocking terminal issue；兩端連接至不同且可識別的有限 Waler；兩端 Waler 的 selected contact face 均已正式完成而非 provisional；Brace 軸線與兩個 selected contact faces 各自具有合法有限交點；且以兩個交點形成的提交後 Brace 長度符合既有合法長度規則。

若任一上述條件未成立，包含任一端為零解／ambiguous、兩端指向同一 Waler、任一 selected contact face 尚未正式完成、缺少合法有限交點或提交後長度不合法，整支 Brace MUST 維持 unresolved 並產生 blocking validation：任何單端成功結果、source-supported endpoint、provisional axis 或 Candidate Point 均不得單獨成為部分正式 Brace truth。world／local geometry、Candidate Points、connection diagnostics、Review state 與 Project conversion MUST 使用同一份完整性判定；不得同時保留來源端點與 resolution endpoint 兩套正式 truth，也不得在 Candidate Points 顯示超過 600 mm 的自動軸向延伸候選。

此 Requirement 是 DXF Recognition Hard Constraint，不改變 Project schema 或 Solver 規則。

#### Scenario: 兩端皆由延伸完成

- **WHEN** Brace 兩個 source-supported endpoints 各自沿 outward ray 在 600 mm 內唯一命中不同有限 Waler
- **THEN** 系統 SHALL 以兩個交點一次建立完整 Waler-to-Waler formal Brace
- **AND** SHALL 清除該 Brace 的 not-connected connection error

#### Scenario: 一端直接連接、一端延伸

- **WHEN** Brace 一端唯一直接連接 W1，另一端沿 outward ray 在 600 mm 內唯一命中不同的 W2
- **THEN** 系統 SHALL 以兩端 resolution evidence 一次建立完整 Waler-to-Waler formal Brace
- **AND** 正式 geometry SHALL 同時採用 W1 與 W2 的 resolved endpoints

#### Scenario: 一端成功而另一端無解

- **WHEN** Brace 一端可唯一直接連接或合法延伸，另一端找不到 600 mm 內的唯一有限 Waler
- **THEN** 系統 SHALL 保留成功端與未成功端的 evidence 供 Review 追溯
- **AND** 整支 Brace MUST 維持 unresolved，不得提交單端 connection 或混合正式／來源 endpoints
- **AND** SHALL 以 blocking validation 阻止完成 import

#### Scenario: 一端成功而另一端 ambiguous

- **WHEN** Brace 一端只有一支合法 Waler，另一端最近合法位置有兩支以上無法區分的 Waler
- **THEN** 系統 SHALL 保留唯一端及競爭端的 evidence 供 Review 追溯
- **AND** 整支 Brace MUST 維持 unresolved，不得把唯一端或任一競爭端提交為部分正式 connection

#### Scenario: 兩端指向同一支 Waler

- **WHEN** direct／extension evidence 使 Brace 兩端都指向同一 Waler
- **THEN** 系統 MUST NOT 將該結果視為合法 Waler-to-Waler Brace
- **AND** SHALL 產生 blocking connection validation 並維持整支 Brace unresolved

#### Scenario: 任一 Waler contact face 尚未正式完成

- **WHEN** Brace start／end 均具有唯一且不同的 Waler terminal evidence，但任一端 Waler 仍只有 provisional geometry，尚未產生 selected formal contact face
- **THEN** 整支 Brace MUST 維持 unresolved 並產生 blocking validation
- **AND** 系統 MUST NOT 以 provisional Waler axis／face 建立正式 endpoint、`FromWaler`、`ToWaler` 或 formal Brace geometry

#### Scenario: Selected contact face 沒有合法有限交點

- **WHEN** Brace 兩端 Waler contact faces 已正式完成，但 Brace 軸線與任一 selected contact face 沒有合法有限交點
- **THEN** 整支 Brace MUST 維持 unresolved 並產生 blocking validation
- **AND** MUST NOT 只提交另一端的合法交點或改用無限延長線建立端點

#### Scenario: 提交後 Brace 長度不合法

- **WHEN** Brace 軸線與兩個 selected contact faces 均有有限交點，但兩交點形成的提交後 Brace 長度不符合既有合法長度規則
- **THEN** 整支 Brace MUST 維持 unresolved 並產生 blocking validation
- **AND** MUST NOT 提交任一單端 endpoint 或部分 connection

### Requirement: 延伸失敗不得改變可靠 recognition 軸或提交不完整 Project

若任一端找不到合法 finite Waler、最近合法候選 ambiguous、軸為零長度／不可靠，或兩端無法形成不同 Waler 的完整關係，系統 SHALL 保留原本的 reliable recognition geometry 與 source identity 作為 staged Review evidence，但 MUST 將該 member 明確標示為 unresolved，而不是 formal Brace。blocking problem SHALL 指出 Brace identity、失敗端別、失敗類型；多解時還 SHALL 列出所有參與最近等價位置的競爭 Waler identities。

unresolved Brace MUST 留在 staged DXF Review，不得產生 Project Brace row、Waler forbidden point 或 Solver input，也不得修改既有 committed Project 或 Solver result。系統 SHALL 沿用或細化既有 `BRACE_NOT_CONNECTED`、`BRACE_ONE_END_NOT_CONNECTED`、`AMBIGUOUS_WALER_CONNECTION` 與 `AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION` blocking behavior；錯誤碼的實作選擇不得降低上述資訊與阻擋條件。

#### Scenario: Outward ray 找不到 Waler

- **WHEN** Brace 未連接端的 outward ray 不與任何 extension distance `<= 600 mm` 的有限 Waler segment 相交
- **THEN** 系統 SHALL 保留該端的 source-supported endpoint 作為 Review evidence
- **AND** SHALL 回報未連接 blocking problem並維持整支 Brace unresolved

#### Scenario: 多解問題列出競爭 identities

- **WHEN** Brace 任一端的最近合法位置對應 W18 與 W19 且兩者無法唯一區分
- **THEN** blocking problem SHALL 識別該 Brace、該端及 W18／W19
- **AND** MUST NOT 只回報其中一支 Waler 或把另一支隱藏為一般候選

#### Scenario: 延伸失敗保留既有 committed state

- **WHEN** DXF Review 中的 Brace validation 因無解、超距離、歧義或不完整兩端關係而失敗
- **THEN** 使用者 MUST 無法以該 unresolved Brace 完成正式 import
- **AND** 既有 ProjectDataModel 與 committed Solver result MUST 保持不變

#### Scenario: Unresolved Brace 不形成下游工程資料

- **WHEN** staged Review 中仍存在 unresolved Brace
- **THEN** 該 Brace MUST NOT 產生 Project row、Waler forbidden point 或 Solver input
- **AND** source-supported geometry SHALL 僅作 Review evidence，不得被下游視為 formal geometry

### Requirement: Review 與人工端點操作必須沿用同一連接語意

距離不超過 600 mm 的 direct／extension candidates SHALL 顯示為可追溯 evidence，保留 Brace 與 Waler source provenance；只有屬於兩端皆唯一且連至不同 Waler 的完整 resolution，才可顯示或選取為正式 endpoints。當任一端 ambiguous 時，Candidate Points MUST NOT 預選、建議或採用任一競爭 Waler 的交點，也不得以 source-supported endpoint 將該 Brace 表示成 formal member。超過 600 mm 的交點 MUST NOT 顯示成可採用的自動延伸候選。

Source exclusion／restore、recognition rebuild、manual endpoint replay、confirmation invalidation、Pause／Resume 與 completed import MUST 沿用既有 Review lifecycle。使用者明確採用的人工端點重播後，系統 SHALL 以目前 active sources 及相同 direct connection 規則重新推導 Waler identity，不得保存或沿用舊 Waler identity。只有重新推導後仍能唯一驗證兩端 Waler identities 且兩端不同，才可形成 formal Brace；只選取幾何點 MUST NOT 解除兩支重疊 Waler 的 identity ambiguity。

#### Scenario: 延伸交點可在 Review 追溯

- **WHEN** Brace 兩端各自由 600 mm 內的 direct 或軸向延伸唯一連接不同 Waler
- **THEN** Review SHALL 顯示兩端交點與各自特定有限 Waler 的 provenance
- **AND** 正式 Brace SHALL 與該完整 resolution 一致

#### Scenario: Ambiguous 端點候選不得被預選

- **WHEN** Brace 一端的最近合法位置對應兩支以上無法區分的 Waler
- **THEN** Review MAY 顯示各競爭交點作為 evidence，但 MUST NOT 將任一點標成建議或已採用的正式 endpoint
- **AND** Candidate Point 操作 MUST NOT 將該 unresolved Brace 升級為 formal Brace

#### Scenario: 超距離交點不成為自動候選

- **WHEN** Brace outward ray 與有限 Waler 的交點距離超過 600 mm
- **THEN** Review MUST NOT 將該交點列為可採用的自動軸向延伸候選

#### Scenario: 排除或復原來源會重建結果

- **WHEN** 使用者排除或復原參與 Brace terminal resolution 的 Waler source
- **THEN** 系統 SHALL 從目前 active sources 重新建立兩端 evidence 與完整性判定
- **AND** MUST NOT 保存指向已不存在來源的 stale formal connection

#### Scenario: 排除競爭 Waler 後變成唯一

- **WHEN** ambiguous 端原有 W18 與 W19 兩支競爭 Waler，使用者排除 W18 後只剩 W19 為唯一合法關係，且另一端也唯一連接不同 Waler
- **THEN** rebuild SHALL 允許建立完整 formal Brace 並採用 W19 的 resolved endpoint
- **AND** 復原 W18 後 SHALL 重新回到 unresolved 並取消該次 staged formal connection

#### Scenario: 人工端點重播優先

- **WHEN** 使用者已在既有 Review workflow 明確選擇 Brace endpoint，之後發生 recognition rebuild
- **THEN** 系統 SHALL 沿用既有 manual override replay order
- **AND** SHALL 以重播後的幾何端點、目前 active sources 與相同 direct connection 規則重新推導兩端 Waler identities，而非沿用舊 identity
- **AND** 只有重新推導的兩端 Waler identities 仍唯一且不同時才可恢復 formal Brace
- **AND** 人工幾何點 MUST NOT 靜默指定重疊 Waler 中的 winner

#### Scenario: Production import 必須提供 member-level verdict

- **WHEN** 正式 DXF import 流程將 Brace terminal／contact-face 結果交給 connection finalization
- **THEN** 每支 Brace SHALL 具有 authoritative member-level verdict，明確表示完整 resolved pair 或 unresolved
- **AND** unresolved Brace MUST NOT 因缺少 committed pair 而進入 legacy nearest-Waler fallback
- **AND** legacy fallback MAY 僅供未使用正式 staged recognition contract 的既有獨立呼叫者維持相容

## ADDED Requirements

### Requirement: Terminal evidence 必須單向支援 Waler contact-face 判定

端點層級唯一且合法的 terminal evidence SHALL 在 Waler contact-face finalization 時作為該特定 Waler 的 member-side evidence，即使同一 Brace 因另一端無解、ambiguous 或其他 member-level 條件失敗而整體 unresolved，該唯一 evidence 仍 SHALL 保持有效。若某端 ambiguous，該端的競爭候選 MUST NOT 作為任一競爭 Waler 的 member-side evidence。

Waler contact-face finalization SHALL 只消費 terminal evidence 及既有 Waler envelope facts；其後建立的 member-level verdict 只控制 Brace 是否成為 formal member，MUST NOT 回頭新增、移除或改派 terminal evidence，也 MUST NOT 影響已由 evidence 判定的 Waler contact face。資料依賴 MUST 維持 `terminal evidence -> Waler contact-face finalization -> Brace member-level verdict`，不得形成由 verdict 回饋 Waler contact-face 的循環。

此 Requirement 是 DXF Recognition／Workflow contract，不改變 Waler envelope 規則、Solver Preference 或 Project schema。

#### Scenario: Brace 整體 unresolved 仍保留唯一端側向 evidence

- **WHEN** Brace start 對 W16 具有唯一合法 terminal evidence，而 end 因其他原因使整支 Brace unresolved
- **THEN** W16 contact-face finalization SHALL 仍可使用該 start evidence 判定 member-side
- **AND** Brace unresolved verdict MUST NOT 移除或降級該 evidence

#### Scenario: Ambiguous 端不得提供競爭 Waler 側向 evidence

- **WHEN** Brace end 同時對 W18 與 W19 形成無法區分的 terminal candidates
- **THEN** 該 end MUST NOT 為 W18 或 W19 建立 member-side evidence
- **AND** W18／W19 contact-face finalization MUST NOT 使用該 ambiguous end 判定支撐側

#### Scenario: Member-level verdict 不回饋 contact-face 判定

- **WHEN** terminal evidence 已完成 Waler contact-face finalization，之後 Brace member-level verdict 因 contact face、交點、長度或另一端問題判定 unresolved
- **THEN** verdict MUST NOT 回頭改變任何 Waler contact face 或重新分配 terminal evidence
- **AND** rebuild SHALL 從目前 active sources 重新依相同單向順序計算，而不是循環重試至某個 Brace 成為 formal

#### Scenario: Y29 B15 的唯一端與 ambiguous 端分流

- **WHEN** Y29 B15 start 唯一對應 W16，而 end 同時對應 W18 與 W19
- **THEN** W16 SHALL 可使用 B15 start evidence 完成其 contact-face 判定
- **AND** W18 與 W19 MUST NOT 使用 B15 end 的競爭關係作為側向 evidence
- **AND** B15 整體 SHALL 維持 unresolved

### Requirement: Y29 重疊 Waler 端點必須維持未解析

Y29 未人工調整編號的 B15（Brace source handle `71E`）SHALL 作為重疊 Waler terminal regression。當其一端唯一連接 W16、另一端同時對應 W18（source handle `69F`）與 W19（source handle `720`）時，系統 MUST 回報 blocking ambiguity 並維持整支 B15 unresolved；來源輪廓推得的 P02 只可保留為 source-supported evidence，不得成為 formal endpoint。當 active sources 中只剩唯一 W19 且其 selected formal contact face 已完成時，系統 SHALL 依既有規則取 Brace 軸線與 W19 selected formal contact face 的合法有限交點作為 resolved endpoint；此 fixture 預期該交點在既有具名 `endpoint_tolerance_mm` 內等價於 P07，而 P07 可由 P04／P06 在軸線上的中點描述。

此 Requirement 是 DXF regression contract；P01、P02、P04、P06、P07 為該 fixture 的可追溯點位名稱，不是新的全域幾何演算法或 tolerance。系統 MUST NOT 將「取 P04／P06 中點」實作成端點計算方法；P07 只用來驗證既有軸線／selected formal contact-face 交點結果。

#### Scenario: W18 與 W19 同時存在

- **WHEN** Y29 B15 source `71E` 的終端最近合法位置同時對應 active W18 source `69F` 與 W19 source `720`
- **THEN** 系統 SHALL 回報包含 B15、該端、W18 與 W19 identities 的 blocking ambiguity
- **AND** P02 與 P07 均 MUST NOT 成為該端的正式 endpoint
- **AND** B15 MUST 維持 unresolved，即使另一端已唯一對應 W16

#### Scenario: 只剩唯一 W19

- **WHEN** W18 source `69F` 被排除或不存在，B15 兩端分別唯一對應 W16 與 W19，且 W19 selected formal contact face 已完成
- **THEN** 系統 SHALL 建立完整 formal B15
- **AND** W19 端 SHALL 採用 Brace 軸線與 W19 selected formal contact face 的合法有限交點，而不是突出 Waler 的 P02
- **AND** 該 fixture 交點 SHALL 在 `endpoint_tolerance_mm` 內等價於 P07
- **AND** MUST NOT 以直接計算 P04／P06 中點取代既有交點規則

#### Scenario: 輸入順序不影響歧義結果

- **WHEN** W18／W19 collection order、DXF entity order 或 B15 start／end 表示反轉，但 WCS geometry 與 active source identities 等價
- **THEN** 系統 SHALL 產生等價的 unresolved result、競爭 identities 與 blocking status
- **AND** MUST NOT 因順序不同而採用 W18、W19、P02 或 P07
