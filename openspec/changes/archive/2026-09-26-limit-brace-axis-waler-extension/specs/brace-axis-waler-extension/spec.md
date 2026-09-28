# Spec Delta

## MODIFIED Requirements

### Requirement: Brace 延伸只能使用向外軸線與有限 Waler 真實交點

對具有唯一、非零長度直線工程軸的 Brace candidate，系統 SHALL 從每個未連接端點沿遠離另一端的 outward ray 搜尋 Waler。合法候選 MUST 是 outward ray 與 Waler 有限線段的實際交點；系統 MUST NOT 使用 Waler 無限延長線、反向交點、側向最近點、改變 Brace 角度或跨不同 Brace source 拼接幾何。

既有 endpoint `connection_tolerance_mm = 250 mm` 只控制 direct connection，不得同時作為軸向延伸距離。Brace 自動軸向延伸 MUST 使用獨立且具名的最大距離 600 mm：extension distance `<= 600 mm` 的真實交點可成為合法候選，`> 600 mm` 的交點 MUST 被拒絕。此 600 mm 是 Brace recognition 的保守安全邊界，不得改變 Strut、CornerBrace 或其他 role 的連接 tolerance。

#### Scenario: Y05 型來源端點停在圍令前

- **WHEN** 可靠 Brace 軸的 source-supported endpoint 距離有限 Waler 超過既有 250 mm direct connection tolerance，但 extension distance `<= 600 mm`，且 outward ray 與該 Waler segment 有真實交點
- **THEN** 系統 SHALL 將該交點納入合法延伸候選
- **AND** MUST NOT 只因間距超過 direct connection tolerance 而拒絕

#### Scenario: 軸向交點恰好位於 600 mm

- **WHEN** 未連接 Brace 端點的 outward ray 在 extension distance `= 600 mm` 處唯一命中有限 Waler segment
- **THEN** 該交點 SHALL 是合法軸向延伸候選

#### Scenario: 軸向交點超過 600 mm

- **WHEN** 未連接 Brace 端點的 outward ray 只在 extension distance `> 600 mm` 處命中有限 Waler segment
- **THEN** 該交點 MUST NOT 成為合法軸向延伸候選
- **AND** 系統 SHALL 保留 source-supported endpoint

#### Scenario: 只與 Waler 無限延長線相交

- **WHEN** Brace outward ray 與某 Waler 的無限直線相交，但交點落在 Waler finite segment 之外
- **THEN** 該 Waler MUST NOT 成為延伸候選

#### Scenario: Waler 位於端點內側方向

- **WHEN** Waler 交點位於 Brace 端點朝向另一端的 inward direction
- **THEN** 系統 MUST NOT 反向縮短或穿過 Brace 來建立該端連接

### Requirement: 每個延伸端必須取得唯一最近的有限 Waler

系統 SHALL 先排除 extension distance `> 600 mm` 的交點，再依 Brace outward ray 上的非負 extension distance 排序合法有限 Waler intersections，並以最先遇到的位置作為 connection boundary。若最近合法位置只有一支可識別 Waler，系統 SHALL 選用該 Waler；位於其後的合法 Waler 不得覆寫最先交點。若最近合法位置有兩支以上 Waler 且依既有 Waler connection ambiguity tolerance 無法唯一區分，該端 MUST 保持未連接並產生 blocking ambiguity，不得依 Waler ID、entity order 或 candidate order 任選。超過 600 mm 的交點不得單獨造成歧義，也不得覆寫 600 mm 內的合法唯一交點。

#### Scenario: 射線依序穿越兩支 Waler

- **WHEN** 同一 outward ray 先與 W1 finite segment 相交，之後才與 W2 finite segment 相交，兩者 extension distance 皆 `<= 600 mm`，且 W1 交點唯一
- **THEN** 系統 SHALL 連接 W1
- **AND** MUST NOT 跳過 W1 改連 W2

#### Scenario: 最近位置有無法區分的多支 Waler

- **WHEN** 兩支以上 Waler 在 600 mm 內的最近交點距離落入既有 ambiguity boundary
- **THEN** 系統 MUST 將該端標示為 ambiguous 並阻止完成正式連接
- **AND** MUST NOT 以輸入順序、Waler ID 或 DXF handle 打破工程歧義

#### Scenario: 唯一合法交點後方存在超距離 Waler

- **WHEN** W1 在 600 mm 內形成唯一合法交點，而 W2 的交點超過 600 mm，即使兩者距離差落入 ambiguity tolerance
- **THEN** 系統 SHALL 連接 W1
- **AND** W2 MUST NOT 使該端變成 ambiguous

#### Scenario: 等價輸入順序不影響選擇

- **WHEN** Brace start/end 表示反轉或 Waler collection order 改變，但 WCS geometry 等價
- **THEN** 系統 SHALL 產生等價的兩端 Waler 關係與正式 Brace geometry

### Requirement: 延伸結果必須一致更新正式 Brace 連接

每一端的 direct／extension resolution SHALL 一致更新該端的正式 endpoint 與對應 `FromWaler` 或 `ToWaler`；未成功的端點（包含唯一交點超過 600 mm）SHALL 保留 source-supported endpoint。只有當兩端各自連接至不同且可識別的有限 Waler 時，Brace 才完成合法 Waler-to-Waler 關係。更新後的 world／local geometry、Candidate Points、connection diagnostics、Review state 與 Project conversion MUST 維持一致，不得同時保留來源端點與延伸端點兩套正式 truth，也不得在 Candidate Points 顯示超過 600 mm 的自動軸向延伸候選。

#### Scenario: 兩端皆由延伸完成

- **WHEN** Brace 兩個 source-supported endpoints 各自沿 outward ray 在 600 mm 內唯一命中不同有限 Waler
- **THEN** 系統 SHALL 以兩個交點建立完整 Waler-to-Waler formal Brace
- **AND** SHALL 清除該 Brace 的 not-connected connection error

#### Scenario: 一端直接連接、一端延伸

- **WHEN** Brace 一端已直接連接 W1，另一端沿 outward ray 在 600 mm 內唯一命中不同的 W2
- **THEN** 系統 SHALL 保留 W1 端並以交點完成 W2 端
- **AND** SHALL 建立完整 Waler-to-Waler formal Brace

#### Scenario: 一端成功而另一端無解

- **WHEN** Brace 一端可直接連接或合法延伸，另一端找不到 600 mm 內的唯一有限 Waler
- **THEN** 系統 SHALL 保留成功端的 Waler 關係與採用 endpoint，未成功端保留 source-supported endpoint
- **AND** SHALL 以既有 one-end-not-connected validation 阻止完成 import

#### Scenario: 兩端指向同一支 Waler

- **WHEN** direct／extension 結果使 Brace 兩端都指向同一 Waler
- **THEN** 系統 MUST NOT 將該結果視為合法 Waler-to-Waler Brace
- **AND** SHALL 產生 blocking connection validation

### Requirement: 延伸失敗不得改變可靠 recognition 軸或提交不完整 Project

若任一未連接端找不到 600 mm 內的 finite Waler intersection、最近合法候選 ambiguous、軸為零長度／不可靠，或兩端無法形成不同 Waler 的完整關係，系統 SHALL 保留原本的 reliable recognition geometry 與 source identity，並沿用或細化既有 `BRACE_NOT_CONNECTED`／`BRACE_ONE_END_NOT_CONNECTED` blocking behavior。失敗 MUST 留在 staged DXF Review，不得修改既有 committed Project 或 Solver result。

#### Scenario: Outward ray 找不到 Waler

- **WHEN** Brace 未連接端的 outward ray 不與任何 extension distance `<= 600 mm` 的有限 Waler segment 相交
- **THEN** 系統 SHALL 保留該端的 source-supported endpoint
- **AND** SHALL 回報既有未連接 blocking problem

#### Scenario: 延伸失敗保留既有 committed state

- **WHEN** DXF Review 中的 Brace extension validation 因無解、超距離或歧義而失敗
- **THEN** 使用者 MUST 無法以該 unresolved Brace 完成正式 import
- **AND** 既有 ProjectDataModel 與 committed Solver result MUST 保持不變

### Requirement: Review 與人工端點操作必須沿用同一連接語意

距離不超過 600 mm 的自動延伸候選 SHALL 顯示為可追溯的 axis-to-finite-Waler intersection，保留 Brace 與 Waler source provenance；超過 600 mm 的交點 MUST NOT 顯示成可採用的自動延伸候選。Source exclusion／restore、recognition rebuild、manual endpoint replay、confirmation invalidation、Pause／Resume 與 completed import MUST 沿用既有 Review lifecycle。使用者明確採用的合法人工端點 SHALL 依既有 manual override 順序重播，不得被重新辨識時的自動延伸靜默覆寫。本 change 不限制既有人工端點操作本身。

#### Scenario: 延伸交點可在 Review 追溯

- **WHEN** Brace endpoint 由 600 mm 內的軸向延伸連接 Waler
- **THEN** Review SHALL 能顯示其為 Brace axis 與特定有限 Waler 的交點
- **AND** source provenance SHALL 同時保留 Brace 與 Waler identity

#### Scenario: 超距離交點不成為自動候選

- **WHEN** Brace outward ray 與有限 Waler 的交點距離超過 600 mm
- **THEN** Review MUST NOT 將該交點列為可採用的自動軸向延伸候選

#### Scenario: 排除或復原來源會重建結果

- **WHEN** 使用者排除或復原參與延伸連接的 Brace 或 Waler source
- **THEN** 系統 SHALL 從目前 staged recognition result 重新建立 connection outcome
- **AND** MUST NOT 保存指向已不存在來源的 stale formal connection

#### Scenario: 人工端點重播優先

- **WHEN** 使用者已在既有 Review workflow 明確選擇合法 Brace endpoint，之後發生 recognition rebuild
- **THEN** 系統 SHALL 沿用既有 manual override replay contract
- **AND** 自動 axis extension MUST NOT 靜默覆寫該人工決定

### Requirement: Y05 Brace 軸延伸案例必須穩定成立

Y05 中 whole-axis recognition 已成功、但來源端點停在 Waler 前的 Brace SHALL 以實際 WCS geometry 驗證本 capability。至少 MUST 涵蓋兩端各約延伸 425 mm 才分別命中 W1／W2 的 root `9E9`，以及一端已連接 W4、另一端在目前 fixture 約延伸 503 mm（歷史觀測約 528 mm）命中 W5 的 root `B9C`；這些觀測值皆不得超過 600 mm，且不是新的全域工程 tolerance。另須以超過 600 mm 的等價案例證明系統不會為完成連接而長距離延伸。

#### Scenario: Y05 root 9E9 兩端延伸

- **WHEN** 系統辨識與 Y05 root `9E9` 等價的 Brace whole axis 及 W1／W2 finite geometry
- **THEN** 系統 SHALL 沿兩端 outward ray 分別建立 W1 與 W2 交點
- **AND** 結果 SHALL 為完整連接的一支 Brace，而不是 `BRACE_NOT_CONNECTED`

#### Scenario: Y05 root B9C 補齊單一未連接端

- **WHEN** 系統辨識與 Y05 root `B9C` 等價的 Brace，其中一端已直接連接 W4，另一端 outward ray 在 600 mm 內唯一命中 W5
- **THEN** 系統 SHALL 保留 W4 並完成 W5 端連接
- **AND** 結果 SHALL 不再是 `BRACE_ONE_END_NOT_CONNECTED`

#### Scenario: Y05 型長距離交點不得自動延伸

- **WHEN** 與 Y05 Brace 等價的 reliable whole axis 只能在超過 600 mm 處命中有限 Waler
- **THEN** 系統 MUST 保留 source-supported endpoint
- **AND** SHALL 維持既有未連接 blocking validation
