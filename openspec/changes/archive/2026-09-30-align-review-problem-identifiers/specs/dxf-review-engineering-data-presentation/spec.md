# Spec Delta

## 閱讀導航

- **必讀**：「問題說明須使用可在清單定位的代號」；定義正式構件、未解析來源與多 owner 的顯示行為。
- **條件式閱讀**：「顯示代號不得取代診斷 identity」；修改 validation、selection、source exclusion、rebuild 或 persistence 時必讀。
- **可先跳過**：既有寬度、圍令直接連接摘要與 Preview 線型 Requirements；本 change 不修改這些行為，也不修改 overlap qualification 或 Solver 規則。

## ADDED Requirements

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

