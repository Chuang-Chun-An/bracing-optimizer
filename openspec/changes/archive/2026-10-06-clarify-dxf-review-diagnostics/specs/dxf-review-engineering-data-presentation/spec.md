# Spec Delta：DXF Review 診斷文字白話化

## 閱讀導航

- **必讀**：「DXF Review 診斷須使用白話中文」；定義主要問題清單與選取項目明細的可見文字。
- **必讀**：「白話顯示不得改變診斷真相」；定義 severity、code、阻擋狀態及定位資料的不變邊界。
- **條件式閱讀**：main spec 的「問題說明須使用可在清單定位的代號」；修改正式 ID 與來源 handle 的呈現時必讀。
- **可先跳過**：main spec 的構件寬度、圍令直接連接摘要與 Preview 線型 requirements；本 delta 不改這些行為，也不改 DXF 辨識或 Solver 規則。

## ADDED Requirements

### Requirement: DXF Review 診斷須使用白話中文

DXF Review 的「全部問題清單」與選取項目的「問題／處理建議」明細 SHALL 以一致、通順的繁體中文呈現問題類型、說明與處理建議。主要文字 MUST 先表達「發生什麼事」及「應檢查什麼」，並使用畫面與工程流程中可辨識的名稱；MUST NOT 要求使用者理解大寫底線 diagnostic code、snake case、Python exception、內部 reason token，或 `active sources`、`provisional`、`identity`、`baseline`、`staged finalization` 等實作術語。

對分類為保留原始 message 或專用 formatter 的診斷，必要的正式構件 ID、來源 handle、數值、單位及可定位資訊 SHALL 保留。當診斷分類為 fallback，或收到尚未納入已知分類的新 code 時，系統 MUST 顯示依構件角色與等級形成的通用中文類型、通用說明、構件 ID、來源 handle 及安全處理建議；MUST NOT 顯示原始 message、原始 diagnostic code、內部 reason token 或未整理的例外文字。

本 change SHALL NOT 提供查看原始 diagnostic code 的額外 UI 入口。原始 code 只保留於既有 structured diagnostic、程式判斷與問題追查資料中；若未來需要使用者可見的技術資訊入口，須由後續 change 另行定義。

此 Requirement 是 Presentation 行為，不新增或修改 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 已知診斷顯示可理解的中文類型

- **WHEN** DXF Review 顯示具有既有 diagnostic code 的問題
- **THEN** 問題清單與選取項目明細 SHALL 顯示同一個可理解的中文類型
- **AND** 主要類型欄位 MUST NOT 直接顯示大寫底線 diagnostic code

#### Scenario: 內部狀態詞改為工程操作語言

- **WHEN** 原始診斷涉及尚未確認的圍令、正式連接、調整基準或接觸位置確認失敗
- **THEN** 說明 SHALL 使用「尚未確認」、「正式連接」、「調整基準」或「接觸位置無法確認」等對應的繁體中文
- **AND** MUST NOT 直接顯示 `provisional`、`identity`、`baseline` 或 `staged finalization`

#### Scenario: 保留定位與量測資訊

- **WHEN** 分類為保留原始 message 或專用 formatter 的診斷具有正式構件 ID、來源 handle、量測值或單位
- **THEN** 白話說明 SHALL 保留判讀及定位所需的資訊
- **AND** 正式 ID 與來源 handle SHALL 繼續遵守 main spec 的既有顯示規則

#### Scenario: 未知代碼使用安全 fallback

- **WHEN** 一則診斷尚未建立專用白話文案
- **THEN** 系統 SHALL 依該診斷的構件角色與等級顯示通用中文類型、通用說明與處理建議
- **AND** SHALL 顯示可取得的構件 ID 與來源 handle 供使用者定位
- **AND** MUST NOT 顯示原始 message、diagnostic code、內部 reason token、exception representation 或 traceback
- **AND** 該診斷 MUST NOT 因缺少專用文案而從問題清單消失

#### Scenario: 處理建議只引用現有操作

- **WHEN** 系統為問題顯示處理建議
- **THEN** 建議 SHALL 指向目前 Review 中確實存在且適用的檢查或修正方式
- **AND** MUST NOT 暗示不存在的自動修復、人工工具或特定來源取捨

### Requirement: 白話顯示不得改變診斷真相

白話文案 MUST 是既有 structured diagnostic 的唯讀顯示投影。系統 SHALL 保留原始 severity、diagnostic code、role、source handles、member IDs、問題排序、數量統計、blocking truth 與目前 Review result；MUST NOT 由中文類型、說明或處理建議反向推導、覆寫或合併診斷。

全部問題清單與選取項目明細 MUST 消費同一份顯示投影。文案差異、fallback 或重新整理 MUST NOT 造成同一診斷在兩處顯示不同語意，也不得改變點選定位、匯入按鈕狀態或完成前確認行為。

#### Scenario: 文案改變但阻擋行為不變

- **WHEN** 一則 error 或 critical 診斷改以白話中文顯示
- **THEN** 它的 severity、diagnostic code 與 blocking truth SHALL 維持原值
- **AND** 匯入按鈕狀態、錯誤數量及完成條件 SHALL 與文案調整前相同

#### Scenario: 警告仍維持非阻擋語意

- **WHEN** 一則 warning 改以白話中文顯示
- **THEN** 它 SHALL 維持原本的 warning 等級與非阻擋語意
- **AND** 系統 MUST NOT 因文案看似嚴重而將其升級為 error 或 critical

#### Scenario: 兩個問題區域使用同一份投影

- **WHEN** 同一則診斷同時出現在全部問題清單與選取項目的問題明細
- **THEN** 兩處 SHALL 顯示相同的中文類型與白話說明
- **AND** 兩處 SHALL 保留相同的構件／來源定位資料

#### Scenario: 顯示 fallback 不遺失診斷 identity

- **WHEN** 一則未知 code 使用通用中文 fallback
- **THEN** 原始 diagnostic code、severity、role、source handles 與 member IDs SHALL 繼續保留供程式判斷與問題追查
- **AND** fallback 文字 MUST NOT 成為新的 diagnostic identity
