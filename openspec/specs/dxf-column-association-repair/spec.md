# dxf-column-association-repair Specification

## 閱讀導航

### 必讀

- 「只讓明確的雙候選中間柱進入修補」：確認哪些 Column 可進入人工修補。
- 「人工選擇決定各支撐的禁止點」與「有效人工決策解除原關聯歧義」：確認單選、雙選及警告處理。
- 「採用與撤銷必須可預覽且原子提交」：確認預覽、採用、撤銷與失效行為。

### 條件式閱讀

- 修改 Review 重建／保存時，閱讀「人工決策須安全重建與續作」。
- 修改雙路支撐或 diagnostics 時，閱讀「修補不得改變一般關聯與雙路資格」。

### 可先跳過

- Solver 搜尋與 Jack spacing、角撐修補幾何模板、Waler contact-face recognition 不屬於本 capability。

## Purpose

本 capability 定義 DXF Review 如何讓使用者針對中間柱同時接近兩支有效支撐的警告，在修改工具中預覽並人工決定應受柱禁止點影響的支撐，安全保存決策並隨目前幾何重建關聯。

## Requirements

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

### Requirement: 人工選擇決定各支撐的禁止點

對一筆可修補案例，使用者 SHALL 能明確選擇第一支、第二支或兩支 Strut；不得選空集合或未列出的 Strut。工具 SHALL 在採用前顯示柱與兩支支撐的工程位置、各自距離及從各支撐當前起點量測的 station。有效人工決策對該 Column 的自動最近支撐關聯具有覆寫權，MUST 先排除該 Column 的自動關聯效果，再以被選 Struts 建立唯一的 active association set，不得將人工單選疊加到自動最近結果。套用後每支被選 Strut SHALL 分別包含該 Column ID 與依其自身當前方向計算的 Column station；未被選的非共享 Strut MUST NOT 保留同一 Column 的自動 association 或禁止點。現有 Support material joint 對每個 Column station 左右各 `830 mm` 的避讓規則 SHALL 照常使用。

Column-to-Strut 的雙側關聯 MUST NOT 建立 `SharedLayoutGroup`、使暫定雙路候選合格或要求兩支使用相同 ordered piece layout。若兩支從相反方向表示，station SHALL 各自依自己的起點計算。

#### Scenario: C25 同時影響兩側

- **WHEN** 使用者在修補工具對 C25 明確選擇 S20 與 S35 並採用
- **THEN** S20、S35 SHALL 各有 C25 的關聯與各自的 Column station
- **AND** 完成匯入後兩支 Strut rows SHALL 各保有相應 `AssociatedColumnIDs` 與 `ColumnPositions`
- **AND** 系統 MUST NOT 因此建立雙路群組

#### Scenario: 只選其中一支

- **WHEN** 使用者只選其中一支並採用
- **THEN** 僅該支 SHALL 取得此人工決策的 Column station
- **AND** 系統 SHALL 將此選擇標示為已人工判定，而非未處理的距離歧義

#### Scenario: 人工單選覆寫自動最近支撐

- **GIVEN** 自動關聯因距離較近而將 Column 關聯至第一支 Strut
- **WHEN** 使用者在中間柱關聯修補中只選擇第二支 Strut 並成功採用
- **THEN** 第二支 Strut SHALL 取得該 Column 的 association 與 station
- **AND** 第一支 Strut MUST NOT 保留同一 Column 的自動 association 或禁止點
- **AND** 該 Column SHALL 只有一筆 active association，且系統 SHALL 將結果標示為人工判定

#### Scenario: 反向支撐

- **WHEN** 兩支候選 Strut 的 Start／End 方向相反且使用者選兩支
- **THEN** 每支的 station SHALL 依自己的當前起點量測
- **AND** 結果 SHALL 保留等價物理位置

### Requirement: 有效人工決策解除原關聯歧義

Workflow 成功重新驗證並原子提交一筆有效的人工 Column association decision 後，系統 MUST 從 active unresolved diagnostics 中移除該 Column 的雙候選距離歧義警告；該警告 MUST NOT 繼續阻止 DXF Review 完成或進入完成前的未解決警告計數。系統 MAY 以「已人工判定」的 informational provenance 呈現此次決策，但不得將它列為未解決警告。其他未被此決策處理的 blocking problems 與 warnings SHALL 保持各自原有的判定；人工柱關聯 MUST NOT 解除 Waler、雙路支撐、source identity 或其他無關問題。當決策失效時，系統 MUST NOT 保留「已解決」狀態，且 MUST 顯示 `requires_review`。

#### Scenario: 有效人工決策解除原關聯歧義

- **WHEN** 使用者對可修補案例明確選擇一支或兩支 Strut
- **AND** Workflow 重新驗證並成功原子提交人工決策
- **THEN** 原本由該 Column 雙候選距離歧義產生的 blocking warning SHALL 不再阻止 DXF Review 完成
- **AND** 系統 MAY 以「已人工判定」資訊保留人工 provenance
- **AND** 其他無關 blocking problems SHALL 保持不變

#### Scenario: 人工決策失效不得誤標已解決

- **WHEN** 原已採用的人工決策因來源、身份或有效幾何改變而失效
- **THEN** 舊人工 station MUST NOT 繼續生效
- **AND** 系統 SHALL 顯示 `requires_review`，MUST NOT 標示原歧義已由有效人工決策解決
- **AND** 其他 blocking problems SHALL 保持不變

### Requirement: 採用與撤銷必須可預覽且原子提交

選柱與切換選項只 SHALL 更新預覽，不得修改正式 Review 結果。使用者明確採用時，系統 MUST 以目前 Review revision、Column 與兩支 Strut identity／幾何重新驗證候選與選擇；預覽已過期、柱或支撐已排除、候選不再合格或驗證失敗時 MUST 拒絕整次提交，保持提交前 Review 結果與人工決策。採用成功 SHALL 同步更新此柱的關聯紀錄、各支撐衍生欄位與診斷，且 SHALL 可看出這是人工修補。使用者 SHALL 能撤銷自己的決策，使目前幾何重新套用既有自動最近支撐行為與其警告。

#### Scenario: 取消預覽

- **WHEN** 使用者關閉或取消修補預覽
- **THEN** 正式關聯、Review 決策與診斷 MUST 保持不變

#### Scenario: 預覽後幾何已改變

- **WHEN** 預覽後柱或候選 Strut 幾何、來源有效性或 Review revision 已改變
- **THEN** 採用 MUST 被拒絕並要求重新預覽
- **AND** 不得留下部分 Column station 或決策

#### Scenario: 撤銷後恢復自動歧義狀態

- **WHEN** 使用者撤銷有效的人工 Column association decision
- **THEN** 系統 SHALL 依目前 geometry 重新執行自動關聯
- **AND** 若雙候選距離歧義仍存在，原 blocking warning SHALL 重新出現
- **AND** 人工判定資訊與人工加入的禁止點 SHALL 被移除

### Requirement: 人工決策須安全重建與續作

人工決策 SHALL 保存柱與兩支候選的可靠來源身份及所選 Strut 身份，作為 Review 中的決策；`ComponentAssociation`、`ColumnPositions` 與顯示結果只是衍生值。相同來源 fingerprint 的 Review 重算、Pause／Resume 及座標投影 SHALL 重新驗證當前兩候選資格，依目前 WCS 幾何重算 station，不得依目前最近距離改選或複製舊 station。來源不同的 compatible recovery MUST NOT 自動轉移已採用的柱關聯；可安全找到相同角色與來源時只標示需要重新判斷，找不到時停用。當原柱、所選 Strut、候選幾何或身份不再符合時，系統 MUST 停止套用舊決策並顯示需要重新檢查，不得靜默退回不同支撐或保留舊禁止點。

#### Scenario: 相同來源續作

- **WHEN** 保存後以相同 fingerprint 的 DXF 繼續 Review，且柱與兩支支撐仍符合原候選身份與幾何
- **THEN** 人工選擇 SHALL 保留
- **AND** 禁止點 SHALL 從目前幾何重算，不依賴舊衍生 station

#### Scenario: 選中的支撐被排除

- **WHEN** 柱或所選 Strut 被排除或不再通過有效有限軸線及關聯資格
- **THEN** 系統 MUST NOT 將決策套用到其他最近 Strut
- **AND** SHALL 顯示需重新檢查，且不得保留失效決策的禁止點

#### Scenario: 來源內容不同

- **WHEN** Pause／Resume 經 compatible recovery 換成內容不同的 DXF
- **THEN** 原人工柱關聯 MUST NOT 自動生效
- **AND** 使用者 SHALL 能辨認需要重新檢查或已停用的決策

### Requirement: 修補不得改變一般關聯與雙路資格

未採用人工修補的中間柱 SHALL 沿用既有最近有效支撐與警告語意。已 accepted 雙路支撐的共享 Column constraint SHALL 保持既有規則；暫定或不相容雙路候選仍無正式共享效果。此工具 SHALL NOT 改動 Beam 關聯、Strut／Column recognition、雙路幾何與 Waler topology qualification、initial Zoning 或 Support Solver 規則。人工選擇兩支一般 Struts 只改變各自 Column station 的輸入事實。

#### Scenario: 未處理的歧義保持原狀

- **WHEN** 中間柱出現兩支距離相近警告，但使用者未採用修補
- **THEN** 系統 SHALL 保持目前自動最近支撐關聯及警告

#### Scenario: 暫定雙路候選旁的柱

- **WHEN** 柱的兩支 Struts 另有 `pending_waler` 雙路候選，且本工具選擇兩支作為柱禁止點
- **THEN** 兩支各自 SHALL 取得人工確認的 Column station
- **AND** `pending_waler` pair MUST NOT 因該柱關聯變成 accepted 或 `SharedLayoutGroup`
