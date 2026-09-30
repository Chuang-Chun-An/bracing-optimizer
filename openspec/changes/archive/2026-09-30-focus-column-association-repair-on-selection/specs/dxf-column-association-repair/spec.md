# dxf-column-association-repair Spec Delta

## 閱讀導航

### 必讀

- 「只讓明確的雙候選中間柱進入修補」：本 change 只修改此 Requirement，新增目前選取中間柱的入口與單一 subject 規則。
- 「Y29 C25 為可修補案例」「有效已修柱可查看並撤銷」「需重新檢查柱顯示失效原因」與「非中間柱選取」Scenario：作為主要 UI acceptance criteria。

### 條件式閱讀

- 實作 Preview 時，搭配主 spec 的「人工選擇決定各支撐的禁止點」與「採用與撤銷必須可預覽且原子提交」。

### 可先跳過

- 主 spec 的人工決策保存、compatible recovery、雙路資格與 Solver 邊界未被本 change 修改，可先跳過。

## MODIFIED Requirements

### Requirement: 只讓明確的雙候選中間柱進入修補

系統 SHALL 在 DXF Review 的「修改工具」提供獨立的「中間柱關聯修補」入口。此入口 SHALL 以目前唯一選取的 Review 構件為操作對象，且只有該構件角色為中間柱時才可使用；選取斜撐、支撐、圍令或任何其他非中間柱項目時，系統 MUST NOT 允許啟動此工具。

使用者啟動工具後，系統 SHALL 只規劃並顯示目前選取的中間柱，不得列出其他待修、已修或需重新檢查的中間柱，也不得在同一修補視窗內切換操作對象。若啟動當下選取已清除、已失效或無法唯一解析為一支正式中間柱，系統 MUST 拒絕進入可套用的修補 Preview，並保持正式 Review 結果與人工決策不變。只有 Review 中仍存在正式 Column 的項目可成為此工具 subject；只有待修 ReviewItem、來源問題或其他尚未形成正式 Column 的項目 MUST NOT 啟用此工具。

目前選取柱若已有有效人工決策，系統 SHALL 允許開啟工具、顯示目前所選 Strut 決策並允許撤銷，不得因原始歧義警告已解除而回報「無可修補內容」。目前選取柱若有 `requires_review` 決策，系統 SHALL 允許開啟工具並顯示既有 Workflow plan 或 Review problem 所提供的失效原因；Presentation MUST NOT 自行推導失效原因、候選資格或撤銷資料。若 Workflow plan 無法提供已修柱的目前決策與安全撤銷所需資訊，系統 MUST 停止該操作，不得由 Presentation 重建。

若人工決策對應的 Column 已不存在，該決策不得成為此工具 subject；其既有 `disabled`／`requires_review` 診斷 MUST 繼續出現在 Review 問題清單，不得因移除全案中間柱清單而消失。

清單選取、圖面點選或清除選取每次改變目前 Review selection 時，系統 SHALL 立即重新評估此工具入口。從正式 Column 改選非 Column 時入口 MUST 隱藏或停用；從非 Column 改選正式 Column 時入口 SHALL 出現或啟用。清單與圖面兩種選取路徑對同一項目 MUST 產生相同結果。

目前選取中間柱的合法修補 plan SHALL 只存在於其自動關聯結果中兩支不同有效 Strut 均在既有依柱與支撐截面尺寸計算的關聯容差內、柱中心沿各 Strut 有限軸線的 station 均在 `[0, length]`，且兩個最近有效距離差 `<= ambiguous_connection_delta_mm` 的案例。預設 `ambiguous_connection_delta_mm = 25 mm`，等號屬符合；本 capability SHALL NOT 改動容差設定。本規格使用「有效人工決策」表示通過目前來源身分、fingerprint、候選資格與幾何重新驗證後成功提交的選擇。

若存在第三支同樣落在歧義差值內的有效 Strut，系統 MUST 顯示多候選原因並拒絕以「雙候選」修補任選兩支。

修補 plan 與預覽 MUST 根據目前有效工程幾何及關聯候選事實建立，不得只比對警告文字或把相同警告代碼的「多個雙路群組」情況誤當成此修補。已由 accepted `SharedLayoutGroup` 正式共享該柱的兩支 lane，不列為本工具的待修雙候選。

#### Scenario: Y29 C25 為可修補案例

- **GIVEN** Y29 C25 對 S20、S35 都有有效有限軸線投影與容差內距離，距離差約 3 mm，且兩支未形成正式 accepted 雙路群組
- **WHEN** 使用者在 DXF Review 唯一選取 C25
- **THEN** 修改工具 SHALL 提供「中間柱關聯修補」入口
- **AND** 開啟後 SHALL 只顯示 C25 與 S20／S35 的修補內容
- **AND** MUST NOT 顯示其他中間柱清單

#### Scenario: 選取另一支中間柱

- **GIVEN** 全案另有其他待修或已修中間柱
- **WHEN** 使用者唯一選取其中一支中間柱並開啟修補工具
- **THEN** 修補 Preview SHALL 只以該次選取的中間柱為操作對象
- **AND** 使用者 MUST NOT 能在該視窗切換至其他柱

#### Scenario: 有效已修柱可查看並撤銷

- **GIVEN** 目前選取的正式中間柱已有有效人工決策，且原始歧義警告已解除
- **WHEN** 使用者開啟「中間柱關聯修補」
- **THEN** 系統 SHALL 顯示該柱目前所選的一支或兩支 Strut
- **AND** SHALL 提供撤銷該人工決策的操作
- **AND** MUST NOT 回報該柱「無可修補內容」

#### Scenario: 需重新檢查柱顯示失效原因

- **GIVEN** 目前選取的正式中間柱具有 `requires_review` 人工決策
- **WHEN** 使用者開啟「中間柱關聯修補」
- **THEN** 系統 SHALL 顯示既有 Workflow plan 或 Review problem 提供的失效原因
- **AND** Presentation MUST NOT 自行推導新的候選資格、原因或撤銷資料

#### Scenario: 對應柱不存在的失效決策仍在問題清單可見

- **GIVEN** 已保存人工決策所對應的 Column 已不在目前正式辨識結果
- **WHEN** Review 重建工具入口與問題清單
- **THEN** 該決策 MUST NOT 啟用中間柱關聯修補工具
- **AND** 既有 `disabled` 或 `requires_review` 問題 MUST 繼續出現在 Review 問題清單

#### Scenario: 清單選取在柱與支撐之間切換

- **WHEN** 使用者從清單中的正式中間柱改選支撐
- **THEN** 中間柱關聯修補入口 MUST 隱藏或停用
- **WHEN** 使用者再從支撐改選正式中間柱
- **THEN** 中間柱關聯修補入口 SHALL 出現或啟用

#### Scenario: 圖面與清單選取結果一致

- **WHEN** 使用者分別由構件清單與圖面選取同一正式中間柱或同一非 Column 構件
- **THEN** 兩種選取路徑 SHALL 產生相同的中間柱關聯修補入口狀態
- **AND** 清除 selection 後入口 MUST 隱藏或停用

#### Scenario: 非中間柱選取

- **WHEN** 使用者選取斜撐、支撐、圍令或其他非中間柱項目
- **THEN** 系統 MUST NOT 允許使用「中間柱關聯修補」
- **AND** 即使全案其他位置存在可修補中間柱，也 MUST NOT 以該柱自動開啟修補 Preview

#### Scenario: 選取清除或啟動時已失效

- **WHEN** 沒有唯一選取項目，或啟動時原選取已失效或無法解析為目前有效中間柱
- **THEN** 系統 MUST 拒絕進入可套用的修補 Preview
- **AND** 正式關聯、Review 決策與診斷 MUST 保持不變

#### Scenario: Preview 開啟後改選其他構件

- **GIVEN** 使用者已為正式中間柱開啟修補 Preview
- **WHEN** 使用者在主 Review 改選其他構件
- **THEN** 已開啟 Preview SHALL 繼續固定原中間柱，不得切換 subject
- **AND** 提交 SHALL 由既有 revision、identity 與 stale-plan validation 決定是否接受或拒絕

#### Scenario: 未有人工決策的中間柱沒有合法修補案例

- **WHEN** 使用者選取一支沒有人工決策的正式中間柱，但該柱不符合雙候選修補資格
- **THEN** 系統 MUST NOT 顯示其他柱作為替代 subject
- **AND** MUST 清楚告知目前選取的中間柱無可修補內容

#### Scenario: 未形成正式 Column 的待修項目不啟用工具

- **WHEN** 使用者選取角色或來源指向中間柱、但尚未形成正式 Column 的待修 ReviewItem
- **THEN** 系統 MUST NOT 顯示或啟用「中間柱關聯修補」
- **AND** 原待修問題 SHALL 保持在既有 Review 問題清單

#### Scenario: 恰在歧義差值邊界

- **WHEN** 目前選取中間柱的兩支有效候選距離差正好等於目前 `ambiguous_connection_delta_mm`
- **THEN** 系統 SHALL 允許該柱進入修補 Preview

#### Scenario: 另一種相同警告代碼

- **WHEN** 目前選取柱的警告是主要支撐同時屬於多個已採用雙路群組，而非一根柱只有兩個距離相近的候選
- **THEN** 本工具 MUST NOT 將該柱視為合法雙候選中間柱修補

#### Scenario: 三支同時接近

- **WHEN** 目前選取柱的第三支有效 Strut 也與最近距離相差 `<= ambiguous_connection_delta_mm`
- **THEN** 系統 MUST 保留多解提示，且 MUST NOT 只因排序而任選兩支供採用
