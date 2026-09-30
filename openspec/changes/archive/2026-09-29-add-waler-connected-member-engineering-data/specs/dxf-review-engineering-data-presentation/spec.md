# Spec Delta

## 閱讀導航

- **必讀**：「圍令直接連接構件顯示」Requirement；定義三類顯示、正式關聯來源、去重、排序與空集合行為。
- **條件式閱讀**：「顯示不得建立第二份關聯資料」Requirement；修改 model、Project row、序列化、匯出、recognition 或 Solver boundary 時必讀。
- **可先跳過**：既有斜撐／角撐寬度顯示 Requirement，以及 Waler contact face、CornerBrace recognition／repair 的完整 specs；本 delta 只消費它們已建立的正式結果。

## ADDED Requirements

### Requirement: 圍令工程資料須顯示直接連接構件

當使用者在 DXF Review 選取正式 Waler 時，系統 SHALL 在右側「工程資料」區分別顯示「直接連接支撐」、「直接連接斜撐」與「直接連接角撐」。系統 MUST 使用 formal connection contract 所保存的 Waler member identity，與目前選取正式 Waler 的同類 member identity 比對。直接連接支撐與斜撐 MUST 分別由正式 member 的起點或終點 Waler identity 等於所選正式 Waler member identity 判定。直接連接角撐 MUST 同時具有目前 staged `DXFImportResult` 中的正式 CornerBrace member，以及指向所選正式 Waler member identity 的正式 adopted CornerBrace connection。

若上述 identities 使用相同 identity domain，系統 MUST 使用 exact identity equality；若既有 contract 使用不同 identity domain，系統 MUST 僅使用既有正式 mapping 對應，且 MUST NOT 新增 proximity、source handle 或字串猜測。Treeview item ID、畫面顯示文字、collection index、source handle、entity order與 format 後的 field value 均不得代替正式 Waler member identity。

系統 MUST 對每一類構件 ID 去重，並以不受 member collection order、DXF entity order 或同一構件重複 terminal reference 影響的 deterministic 順序顯示。若某一類沒有正式直接連接，該欄位 SHALL 保留並顯示 `—`。三類欄位 MUST 只在正式 Waler 的工程資料中新增，其他構件 SHALL 維持其既有工程資料內容。

此 Requirement 是 Presentation 行為，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 顯示圍令連接的支撐與斜撐

- **WHEN** 使用者選取正式 Waler `W1`
- **AND** 正式 Strut `S1`、`S2` 的任一 terminal Waler identity 為 `W1`
- **AND** 正式 Brace `B1` 的任一 terminal Waler identity 為 `W1`
- **THEN** 右側工程資料 SHALL 在「直接連接支撐」顯示 `S1` 與 `S2`
- **AND** SHALL 在「直接連接斜撐」顯示 `B1`

#### Scenario: 顯示正式連接的角撐

- **WHEN** 使用者選取正式 Waler `W1`
- **AND** 目前 staged Review result 中存在正式 CornerBrace member `CB1`
- **AND** 同一 result 已有 `CB1` 指向 `W1` 的正式 adopted connection
- **THEN** 右側工程資料 SHALL 在「直接連接角撐」顯示 `CB1`

#### Scenario: 顯示 identity 不得取代正式 Waler identity

- **WHEN** 使用者選取正式 Waler
- **THEN** 系統 SHALL 使用 formal connection contract 的 Waler member identity 反查直接連接構件
- **AND** MUST NOT 使用 Treeview item ID、顯示順序、source handle 或 label 文字推導關聯

#### Scenario: 不同 identity domain 只可使用既有正式 mapping

- **WHEN** formal connection contract 的 Waler identity 與目前選取正式 Waler 的 identity 不屬於相同 domain
- **THEN** 系統 MUST 僅使用既有正式 mapping 建立對應後再判定直接連接
- **AND** MUST NOT 使用 proximity、source handle、collection index、entity order、format 後欄位值或字串猜測建立 mapping

#### Scenario: 未採用的候選關係不顯示

- **WHEN** 一個 Strut、Brace 或 CornerBrace 只是幾何鄰近、相交、候選、ambiguous 或 unresolved，且沒有對所選 Waler 成立正式 connection
- **THEN** 系統 MUST NOT 將該構件列入所選 Waler 的任何直接連接欄位
- **AND** MUST NOT 在 Presentation 以距離、交點、Waler chain、diagnostic message 或候選順序推測關聯

#### Scenario: 沒有正式 CornerBrace member 的 connection 不顯示

- **WHEN** connection record 沒有對應目前 staged result 中的正式 CornerBrace member
- **THEN** 系統 MUST NOT 將該 ID 顯示為直接連接角撐
- **AND** Presentation MUST NOT 自行建立、修復或重新指派 connection

#### Scenario: 非正式 CornerBrace 狀態不顯示

- **WHEN** CornerBrace 只存在 body hypothesis、BodyRelationshipAssessment、unresolved body／relationship、repair candidate、Preview temporary selection 或已排除 member 狀態
- **THEN** 系統 MUST NOT 將該 CornerBrace 顯示為直接連接角撐
- **AND** SHALL 僅在目前 staged result 同時存在正式 CornerBrace member 與正式 adopted connection 後顯示

#### Scenario: 同一構件的重複參照只顯示一次

- **WHEN** 同一正式構件對所選 Waler 出現多個等價 terminal 或 connection reference
- **THEN** 對應直接連接欄位 SHALL 只顯示該構件 ID 一次

#### Scenario: 關聯顯示不受輸入順序影響

- **WHEN** 相同的正式連接集合以不同 member collection order、DXF entity order 或 connection record order 提供
- **THEN** 三類直接連接欄位 SHALL 產生相同文字與 ID 順序

#### Scenario: Rebuild 後 UI identity 改變不影響正式摘要

- **WHEN** Review rebuild 改變 Treeview item ID、顯示 ID 或 member collection order，但正式 Waler members 與 formal connection identities 的關係保持等價
- **THEN** 三類直接連接欄位 SHALL 維持相同正式摘要
- **AND** SHALL NOT 沿用 rebuild 前的 UI identity 或 collection position

#### Scenario: 沒有正式連接時保留空集合欄位

- **WHEN** 所選正式 Waler 沒有任何正式直接連接支撐、斜撐或角撐
- **THEN** 「直接連接支撐」、「直接連接斜撐」與「直接連接角撐」SHALL 全部顯示 `—`
- **AND** 系統 SHALL NOT 省略這三個欄位

#### Scenario: 非圍令構件維持既有工程資料

- **WHEN** 使用者選取 Strut、Brace、CornerBrace、Column、Beam 或其他非 Waler 構件
- **THEN** 本 change SHALL NOT 在其工程資料中新增圍令的三類直接連接欄位
- **AND** 其既有工程資料顯示 SHALL 維持不變

### Requirement: 顯示不得建立第二份關聯資料

圍令直接連接構件顯示 MUST 是目前 DXF Review result 正式關聯的唯讀投影。系統 MUST NOT 為此顯示在 Waler、Project row、Project schema、序列化資料、匯出欄位或 Solver input 中新增反向關聯欄位，亦 MUST NOT 修改 member identity、正式 connection、recognition、validation、Review confirmation 或 repair outcome。Presentation 對不存在正式 member 的 orphan／stale connection 只可過濾，不得自行修復或重新指派。

#### Scenario: 建立或刷新顯示不回寫資料

- **WHEN** 系統建立或刷新正式 Waler 的右側工程資料
- **THEN** 顯示前後的 Waler、Strut、Brace、CornerBrace、正式 connections 與 Project rows SHALL 相同
- **AND** 目前 staged `DXFImportResult` 及其 members／connections SHALL 完全不變
- **AND** 不得產生新的 persistence、export 或 Solver 欄位

#### Scenario: Review 關係變更後重新投影目前結果

- **WHEN** 合法 Review 操作使某個正式 connection 新增、移除或改指向另一支 Waler
- **AND** 工程資料面板依既有 refresh lifecycle 更新
- **THEN** 圍令直接連接欄位 SHALL 反映目前 Review result 的正式關聯
- **AND** SHALL NOT 使用先前顯示所保存的反向清單
