# Spec Delta

## 閱讀導航

- **必讀**：新增 Requirement「角撐修補介面須使用繁體中文」及其三個 Scenario；這是本 change 唯一新增的 observable behavior。
- **條件式閱讀**：若修改候選預覽內容，搭配主規格「修補必須先預覽再明確採用」；若修改無候選或提交失敗訊息，搭配同 Requirement 的「沒有合法候選」與原子提交相關 Scenario。
- **可先跳過**：主規格中的 reference eligibility、finite geometry、Pause／Resume、automatic recognition 與 persistence 細節；本 change 不改這些規則。

## ADDED Requirements

### Requirement: 角撐修補介面須使用繁體中文

系統 SHALL 以繁體中文呈現角撐修補流程中的使用者可見文字，包括修補可用性說明、預覽視窗說明、候選表格欄位、候選明細、顯示用狀態名稱、拒絕診斷與提交錯誤。同一角色或移植方式在角撐修補介面中重複出現時 MUST 使用一致的中文術語，且該術語 SHALL 可由其他 Presentation consumer 重用。工程構件 ID、座標、數值、單位及內部資料識別值 MUST 保持原始值；顯示翻譯 MUST NOT 改變候選資格、排序、工程幾何、修補提交或持久化 contract。

#### Scenario: 預覽合法候選

- **WHEN** 使用者開啟具有一個或多個合法候選的角撐修補預覽
- **THEN** 視窗說明、表格欄位、選取提示與候選明細 SHALL 使用繁體中文描述目標圍令與支撐、參考模板、移植方式、局部尺寸、結果長度及驗證證據
- **AND** 構件 ID、座標、數值與 `mm` 單位 SHALL 保持可稽核的原始內容

#### Scenario: 顯示移植方式

- **WHEN** 候選的內部移植方式為 `same_side` 或 `mirrored`
- **THEN** 介面 SHALL 分別顯示「同側移植」或「鏡射移植」
- **AND** 系統 MUST 保留原內部值供候選選取、提交與持久化使用

#### Scenario: 重複概念使用一致術語

- **WHEN** 角撐修補的表格與候選明細顯示相同的角色或移植方式
- **THEN** `corner_brace` SHALL 一致顯示為「角撐」，`same_side` SHALL 一致顯示為「同側移植」，`mirrored` SHALL 一致顯示為「鏡射移植」
- **AND** 其他介面使用相同顯示術語時 SHALL 能取得同一中文名稱，而不必重新定義另一份對照

#### Scenario: 修補不可執行或提交失敗

- **WHEN** 選取項目不符合修補前提、沒有候選通過安全條件，或提交時偵測到 stale／invalid repair state
- **THEN** 系統 SHALL 以繁體中文顯示具體原因
- **AND** SHALL 維持既有拒絕、保留原狀或 rollback 語意，不得因翻譯而改用較寬鬆的 fallback

