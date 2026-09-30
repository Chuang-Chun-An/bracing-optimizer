# dxf-review-engineering-data-presentation Specification

## 閱讀導航

- **必讀**：「斜撐與角撐寬度顯示」Requirement；定義右側工程資料的顯示值、格式與未知值行為。
- **條件式閱讀**：「顯示不得改變工程資料 contract」Requirement；修改 model、Project row、匯入、持久化或 Solver 邊界時必讀。
- **可先跳過**：斜撐與角撐的辨識、候選選擇及修補規格；本 capability 只消費既有可靠寬度，不定義寬度如何產生。

## Purpose

定義 DXF Review 右側工程資料對斜撐與角撐寬度的可見呈現，使使用者可在工程資料區直接檢核可靠尺寸，同時避免把未知寬度顯示成真實工程數值。

## Requirements

### Requirement: 問題說明須使用可在清單定位的代號

DXF Review 的全體問題清單與選取項目的「問題／處理建議」明細 SHALL 使用同一份問題說明投影。替換候選 MUST 限於該則 `ValidationMessage.source_handles` 或同一訊息明確保存的 structured competing identities；系統 MUST NOT 以整個 result 的 ownership index 對 description 全文搜尋。當候選 DXF source 已由目前 Review result 唯一或明確地擁有於一個以上正式 members 時，畫面 SHALL 以 `正式 ID（來源 handle）` 顯示；使用者 MUST 能以括號外的正式 ID 在目前清單找到對應項目，並可由括號內 handle 追溯來源。

當一個 source handle 同時由多個正式 members 擁有時，系統 SHALL 顯示所有對應 member IDs、去除重複、依左側清單相同的自然排序輸出，並固定以 `／` 分隔；例如 `W2` MUST 排在 `W10` 之前。系統 MUST NOT 依 collection order、目前選取、first match 或任意 winner 只顯示其中一個。當多個候選 source handles 屬於同一正式 member 時，說明 SHALL 只顯示一次 member ID，並在同一組括號內列出相關 handles。

若候選 source 尚未形成任何正式 member 或目前已排除，系統 SHALL 只保留 source handle，使其可對應左側既有的 `待修-<handle>` 或 `已排除-<handle>` 項目；系統 MUST NOT 為此建立虛構正式 member ID。文字中看似 handle 但未列於該訊息 structured fields 的 token SHALL 保留原文。即使 token 同時是結構化候選，若其緊接 `mm`、`°`、`%` 單位，或是小數、座標的一部分，系統 MUST 將該次出現視為工程數值而不得替換。此 Requirement 是 Presentation-facing diagnostic projection，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: Y29 重疊問題顯示正式 ID 與來源 handle

- **WHEN** Y29 的正式 Waler `W6` 與 `W12` 發生 overlap 或 blocking competition
- **AND** 其底層來源分別包含 `232` 與 `4E4`
- **THEN** Review 問題說明 SHALL 以 `W6（232）` 與 `W12（4E4）` 指出兩支競爭圍令
- **AND** 使用者 SHALL 能在左側清單直接找到 `W6` 與 `W12`
- **AND** 問題說明 MUST NOT 只以 `232` 與 `4E4` 代表這兩支已辨識圍令

#### Scenario: 其他診斷引用已辨識構件來源

- **WHEN** overlap 以外的 Review 診斷文字引用目前已屬於正式 Waler、Strut、Brace、Column、Beam 或 CornerBrace 的 source handle
- **AND** 該 handle 已列於此訊息的 structured fields
- **THEN** 問題說明 SHALL 顯示 `正式 ID（來源 handle）`
- **AND** 相同顯示規則 SHALL 同時適用於全體問題清單與選取項目的問題明細

#### Scenario: 未解析來源維持可對應待修項目

- **WHEN** 問題引用 source handle `FB7`
- **AND** 目前 Review result 沒有任何正式 member 擁有 `FB7`
- **AND** 來源 `FB7` 尚未排除
- **THEN** 問題說明 SHALL 保留 `FB7`
- **AND** 左側清單 SHALL 維持可由該 handle 對應的 `待修-FB7` 項目
- **AND** 系統 MUST NOT 為 `FB7` 猜測或建立正式 member ID

#### Scenario: 同一來源由多個正式構件擁有

- **WHEN** 問題引用的同一 source handle 由兩個以上正式 members 擁有
- **AND** 對應 members 為 `W10` 與 `W2`
- **THEN** 問題說明 SHALL 依自然排序顯示 `W2（<handle>）／W10（<handle>）`
- **AND** 輸入 member collection order 改變後 SHALL 產生相同顯示順序
- **AND** 系統 MUST NOT 自動挑選其中一個 member 作為唯一對象

#### Scenario: 同一正式構件具有多個來源圖元

- **WHEN** 問題文字引用的兩個以上 source handles 都屬於同一正式 member
- **THEN** 問題說明 SHALL 只顯示一次正式 member ID，並在同一組括號內列出相關 handles
- **AND** MUST NOT 因來源圖元數量而重複顯示相同 member ID 或建立多個構件標籤

#### Scenario: 結構化 handle 與相同量測值同時出現

- **WHEN** `232` 已列於該則 `ValidationMessage` structured fields
- **AND** 同一問題文字分別以來源 handle 與量測值 `232 mm` 出現 `232`
- **THEN** 系統 SHALL 只把來源 handle 顯示為 `W6（232）`
- **AND** 量測值 SHALL 維持 `232 mm`

#### Scenario: 文字 handle 未列於結構化欄位

- **WHEN** 問題文字包含一個看似 source handle 的 token
- **AND** 該 token 未列於該則 `ValidationMessage.source_handles` 或 structured competing identities
- **THEN** 系統 SHALL 保留該 token 原文
- **AND** MUST NOT 因目前 result 中存在同 handle owner 而替換它

#### Scenario: 已排除來源維持 handle

- **WHEN** 問題引用已排除來源 `FB7`
- **AND** 目前沒有正式 member 擁有 `FB7`
- **THEN** 問題說明 SHALL 維持只顯示 `FB7`
- **AND** 該 handle SHALL 可對應左側既有 `已排除-FB7`

### Requirement: 顯示代號不得取代診斷 identity

清單代號轉換 MUST 只改變使用者可見的問題說明。系統 SHALL 保留原始 validation severity、code、source handles、member IDs、role、blocking truth 與目前 Review result；MUST NOT 以顯示文字反向建立或修改 recognition、terminal、contact-face、overlap、selection、source exclusion、rebuild 或 persistence identity。

顯示投影 MUST 由目前 Review result 的正式 member IDs 與 source ownership 唯讀建立。若找不到可靠 owner，系統 SHALL 保留原始文字中的 source handle，而不是猜測鄰近構件、沿用舊 result 的 ID 或讓問題消失。

#### Scenario: 顯示轉換不修改診斷資料

- **WHEN** 問題說明把正式來源 `232`、`4E4` 顯示為 `W6（232）`、`W12（4E4）`
- **THEN** 對應 validation message 與 problem record 的 severity、code、role、source handles、member IDs 及 blocking 結果 SHALL 維持原值
- **AND** source selection、排除、還原與 rebuild SHALL 繼續使用既有 structured identity

#### Scenario: 找不到正式 owner 時安全保留來源

- **WHEN** 問題文字包含 source handle，但目前 Review result 無法將其對應到任何正式 member
- **THEN** 系統 SHALL 保留該 source handle
- **AND** MUST NOT 使用 proximity、名稱格式、collection index、舊 Review state 或字串相似度猜測正式 member ID

### Requirement: 斜撐與角撐寬度顯示

當使用者在 DXF Review 選取正式斜撐或正式角撐時，系統 SHALL 在右側「工程資料」區顯示「構件寬度（mm）」欄位。若該構件具有有限且大於 `0` 的可靠來源寬度，系統 MUST 使用該既有寬度並固定顯示至小數第 3 位；若寬度缺失、非有限或 `<= 0`，系統 SHALL 顯示「—」，且 MUST NOT 猜測、繼承或顯示為 `0.000`。

此 Requirement 是 Presentation 行為，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 顯示斜撐可靠寬度

- **WHEN** 使用者選取來源寬度為 `350.0` mm 的正式斜撐
- **THEN** 右側工程資料 SHALL 顯示「構件寬度（mm）：350.000」

#### Scenario: 顯示角撐可靠寬度

- **WHEN** 使用者選取來源寬度為 `300.0` mm 的正式角撐
- **THEN** 右側工程資料 SHALL 顯示「構件寬度（mm）：300.000」

#### Scenario: 未知寬度不產生工程數值

- **WHEN** 使用者選取來源寬度缺失、非有限或 `<= 0` 的正式斜撐或角撐
- **THEN** 右側工程資料 SHALL 在「構件寬度（mm）」顯示「—」
- **AND** 系統 MUST NOT 顯示 `0.000`、從其他構件繼承寬度或推定替代值

#### Scenario: 其他構件維持既有工程資料

- **WHEN** 使用者選取非斜撐且非角撐的構件
- **THEN** 本 change SHALL NOT 因該選取而新增「構件寬度（mm）」工程資料列
- **AND** 其既有工程資料顯示 SHALL 維持不變

### Requirement: 顯示不得改變工程資料 contract

寬度顯示 MUST 只讀取 DXF member 已保存的可靠來源寬度。系統 MUST NOT 為此顯示新增或修改 Project row、Project schema、序列化資料、匯出欄位、Solver input、材料規格、辨識結果、構件幾何或角撐修補結果；左側構件清單、DXF 預覽與角撐修補預覽 SHALL 維持既有行為。

#### Scenario: 顯示寬度不回寫資料

- **WHEN** 系統建立或刷新斜撐或角撐的右側工程資料
- **THEN** 顯示前後的 member 寬度、Project row、正式幾何與關聯 SHALL 相同
- **AND** 不得產生新的 persistence 或 Solver 欄位

#### Scenario: 人工修補角撐沒有可靠寬度

- **WHEN** 人工修補角撐的既有來源寬度為未知值
- **THEN** 右側工程資料 SHALL 顯示「—」
- **AND** 系統 MUST NOT 因顯示需求而從 reference template 或鄰近構件取得寬度

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

### Requirement: Preview 必須區分正式接觸面與 provisional axis

DXF Review Preview SHALL 使用不會被合理誤認為正式 Waler engineering line 的視覺語意呈現 unresolved／ambiguous Waler provisional axis。正式完成 contact-face finalization 的 Waler SHALL 維持正式工程線呈現；未完成者 SHALL 以不同線型、色彩、標記或等價的明確方式顯示 provisional 狀態。Presentation MUST 只消費目前 staged recognition／contact-face state，不得自行推導重疊、關係或接觸面。

Preview 的 viewport、selection、highlight 或重繪 MUST NOT 改變 Waler 的 formal／provisional truth。若某 Waler 沒有正式接觸面，Preview MUST NOT 因其具有 `closed_outline_axis`、selected candidate 或可畫線段而將它渲染成已完成正式辨識。

#### Scenario: W17 與 W20 的 provisional axes 不偽裝為正式線
- **WHEN** Y29 W17 與 W20 因重疊競爭而維持 unresolved contact-face state
- **THEN** Preview SHALL 將兩支 provisional axes 與正式 Waler engineering lines 明確區分
- **AND** MUST NOT 顯示成兩支已成功完成內側接觸面判定的正式線

#### Scenario: 排除來源後更新為正式線
- **WHEN** 排除 W17 或 W20 後，剩餘 Waler 完成 contact-face finalization
- **THEN** Preview SHALL 依目前 staged truth 將剩餘 Waler 顯示為正式 engineering line
- **AND** SHALL 移除該 pair 的 stale provisional／competition 呈現

#### Scenario: 重繪與選取不改變工程 truth
- **WHEN** 使用者縮放、平移、選取 Waler 或觸發 Preview 重繪
- **THEN** formal／provisional 狀態與 staged `DXFImportResult` SHALL 保持不變

### Requirement: Review 必須呈現重疊來源與重建資訊

對重大共線重疊 warning 或 blocking competition error，DXF Review SHALL 讓使用者定位所有參與的 Waler sources，並顯示重疊原因、重疊比例及目前是否阻擋完成。Blocking competition error SHALL 顯示 direct identity provenance 所指向的受影響 terminal 或 contact-face finalization context。Review SHALL 中性說明 active sources 變更後會重新辨識，但 MUST NOT 推薦、暗示或預選應刪除、排除、保留的 Waler winner。

Presentation MUST NOT 建立第二份 overlap qualification、direct identity join、connection 或 contact-face 規則，也不得將 source handle、Treeview item ID、顯示 ID 或 collection index 當成正式 identity。顯示內容 SHALL 由目前 staged diagnostics 與 source provenance 唯讀投影；Presentation MUST NOT 因附近另有 unresolved outcome 而自行把 warning 升級為 blocking。

#### Scenario: Blocking overlap 可定位兩方來源
- **WHEN** W17（source `69C`）與 W20（source `721`）形成 blocking competition
- **THEN** Review SHALL 顯示並可定位兩方 sources、重大重疊原因與 blocking 狀態
- **AND** SHALL 顯示 direct provenance 所指向的受影響 terminal 或 finalization context
- **AND** SHALL 中性說明 active sources 變更後會重新辨識
- **AND** MUST NOT 推薦排除、刪除或保留 W17、W20 的任一方

#### Scenario: 純 overlap warning 不偽裝成 blocking error
- **WHEN** 重大共線重疊沒有造成 terminal 或 contact-face 多解
- **THEN** Review SHALL 顯示 warning 而非 blocking error
- **AND** SHALL 不因該 warning 單獨阻止完成

#### Scenario: 其他 unresolved 不改變 overlap pair 的顯示層級
- **WHEN** A／B overlap 只有 warning，而 staged diagnostics 的 unresolved outcome 沒有 A、B 同時競爭同一 terminal／finalization 的 direct provenance
- **THEN** Review SHALL 維持 A／B warning-only 呈現
- **AND** MUST NOT 自行建立 A／B blocking 標示或 winner 建議

#### Scenario: Rebuild 後只呈現目前診斷
- **WHEN** source exclusion／restore、Pause／Resume、recovery 或 rebuild 改變目前 overlap／competition outcomes
- **THEN** Review SHALL 只呈現目前 staged diagnostics 與 identities
- **AND** MUST NOT 顯示已不存在 pair 的 stale 問題或先前 UI identity
