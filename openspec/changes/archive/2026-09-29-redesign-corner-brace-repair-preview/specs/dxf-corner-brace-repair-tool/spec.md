# Spec Delta

## 閱讀導航

- **必讀**：「修補必須先預覽再明確採用」中關於單一候選摘要、灰色 exact-source 幾何與多候選選取的 Scenarios；「角撐修補介面須使用繁體中文」中關於定位尺寸名稱與小數三位格式的 Scenarios。
- **條件式閱讀**：修改 overlay 時閱讀「以灰色顯示目標來源線段」；修改文字 formatter 或 widget 時閱讀「預覽數值統一顯示三位小數」與「定位尺寸使用直觀名稱」。
- **可先跳過**：主規格中的 reference eligibility、候選排序、unresolved create、原子提交、Pause／Resume 與 persistence Requirements；本 change 不改變這些行為。

## MODIFIED Requirements

### Requirement: 修補必須先預覽再明確採用

Repair planner MAY 保留未通過 hard eligibility 的 internal hypotheses 以建立拒絕 diagnostics，但只有同時具備 exact target source identity、可靠 target direction、target positional anchor、在該 candidate 內唯一且有效的 target relationship、compatible automatic primary template、有效 finite transferred endpoints，並通過 target residual validation 與既有 CornerBrace validation 的 hypotheses，才可成為 Preview 中可選取、可 Apply 的 candidates。

系統 SHALL 在修改 live Review state 前，以清楚分層的預覽呈現 candidate 工程線、`plan.residual_segments` 所代表的目標來源線段、目標 Waler／Strut、被選用的 automatic primary template、同側／鏡射 transfer mode、reference local offset／station、manual secondary evidence 及各項 target validation 結果。主要確認區 SHALL 優先呈現目標關係、選用模板、移植方式與 candidate 結果長度；reference fixed length、world engineering line、automatic primary／manual secondary evidence 及 diagnostics SHALL 保持可取得，但置於預設收合且可重新展開的次要稽核與診斷區。

即使只有一個 eligible candidate，也 MUST 由使用者明確採用；單一候選 SHALL 直接成為目前預覽方案，不要求使用者先操作候選表格，但系統 MUST NOT 因候選唯一而呼叫 commit。取消或關閉預覽 MUST 保持零副作用。Recognized replace 可顯示分屬不同 relationship 的多個完整 candidates；unresolved create 只有在所有 hard-eligible candidates 指向同一 relationship 時，才可顯示該 relationship 內的多個 template candidates。多個可預覽 candidates 存在時，系統 SHALL 要求使用者以 candidate ID 明確選擇，並以所選候選更新摘要、稽核與診斷、overlay 及 Apply state；系統 MUST NOT 以格式化後的顯示字串識別、合併或排序候選，也不得自動選擇或提交候選。

#### Scenario: 唯一候選仍需確認
- **WHEN** 系統只建立一個合法 reference-template candidate
- **THEN** 系統 SHALL 直接顯示該候選的目標關係、template、transfer mode、結果長度、局部尺寸與 target validation
- **AND** SHALL 將該候選設為目前 UI selection，顯示摘要、overlay 與可重新展開的稽核內容
- **AND** 開啟預覽 MUST NOT 呼叫 commit 或修改 live Review state
- **AND** 只有使用者按下「套用此修補」且既有 Apply callback 成功後才可修改正式 Review state

#### Scenario: 主要資訊與稽核資訊分層
- **WHEN** 使用者檢視目前角撐修補方案
- **THEN** 系統 SHALL 在主要確認區呈現目標 Waler／Strut、選用模板、移植方式、candidate 結果長度、「圍令端定位距離」與「支撐端定位距離」
- **AND** SHALL 在次要稽核區保留 reference fixed length、world engineering line、automatic primary references、manual repaired secondary references 與 diagnostics

#### Scenario: 稽核與診斷區預設收合
- **WHEN** 使用者開啟具有合法候選的角撐修補預覽
- **THEN** 次要稽核與診斷區 SHALL 預設收合
- **AND** 系統 SHALL 提供清楚的「顯示稽核與診斷」及「隱藏稽核與診斷」操作
- **AND** 收合後全部稽核資料 SHALL 可重新展開取得
- **AND** 收合或展開 MUST NOT 改變 selected candidate、Apply enabled state、candidate ID、overlay、live Review state 或 persistence
- **AND** reference fixed length、world engineering line、automatic primary references、manual repaired secondary references 及 diagnostics SHALL 保持可取得
- **AND** diagnostics 有內容時系統 MAY 顯示中性的「有診斷資料」提示，但 Presentation MUST NOT 自行重新判斷 severity

#### Scenario: 使用者選擇多個候選之一
- **WHEN** 系統顯示多個合法但非等價的 transferred candidates
- **THEN** 系統 SHALL 保留 Treeview browse selection，且未選取 candidate 時 Apply button SHALL 維持 disabled
- **AND** 使用者依 candidate ID 選取一個 candidate 後，系統 SHALL 同步更新主要確認區、次要稽核與診斷區、overlay 及 Apply state
- **AND** SHALL 只採用被選取 candidate 的 template transfer、工程線與關係
- **AND** SHALL 不採用其他 candidates 的幾何或 provenance
- **AND** MUST NOT 使用格式化後的三位小數字串識別、合併或排序 candidate
- **AND** MUST NOT 自動選擇或提交其中一個 candidate

#### Scenario: 以灰色顯示目標來源線段
- **WHEN** 使用者正在預覽一個合法角撐修補候選
- **THEN** 圖面預覽 SHALL 只將 `plan.residual_segments` 以低干擾灰色細線／虛線顯示
- **AND** SHALL 以藍色粗線顯示 selected candidate 工程軸線，並以橘色 marker 顯示 positional anchor
- **AND** UI MUST NOT 重新掃描整張 DXF 或鄰近幾何選擇來源線
- **AND** 每次刷新 MUST NOT 重複繪製同一 residual overlay item
- **AND** 灰色來源線只作顯示，MUST NOT 成為新的 eligibility evidence

#### Scenario: 改選或離開預覽時清除 temporary overlay
- **WHEN** 使用者改選 candidate、取消修補或關閉修補預覽視窗
- **THEN** 系統 SHALL 清除先前建立的 repair temporary overlay
- **AND** 改選 candidate 時 SHALL 只重畫一次 `plan.residual_segments`、新 selected candidate 工程軸線與 positional anchor

#### Scenario: 使用者取消預覽
- **WHEN** 使用者取消或關閉修補預覽
- **THEN** 正式 CornerBrace、unresolved subject、關聯、validation、confirmation 與 dirty Review state SHALL 維持提交前狀態

#### Scenario: 沒有合法候選
- **WHEN** target evidence、compatible template、有限 transferred endpoints 或既有 validation 任一不足
- **THEN** 系統 SHALL 顯示不可安全修補的具體原因
- **AND** SHALL 保留原正式幾何或 unresolved 狀態

#### Scenario: 多個 hypotheses 都缺少必要 evidence
- **WHEN** planner 產生多個 internal hypotheses，但每一個都缺少 target evidence、compatible automatic primary、有限 endpoints 或既有 validation 的必要條件
- **THEN** 系統 MUST NOT 將任何 hypothesis 包裝成可 Apply candidate
- **AND** SHALL 顯示對應的拒絕 diagnostics

#### Scenario: Proximity 只排序合法候選
- **WHEN** 多支 automatic primaries 已各自通過 compatibility gates
- **THEN** 系統 MAY 依正式 tier 與 locality 排序其 candidates
- **AND** MUST NOT 因距離較近而跳過 hard validation、隱藏非等價同級 candidate 或自動 Apply

### Requirement: 角撐修補介面須使用繁體中文

系統 SHALL 以繁體中文呈現角撐修補流程中的使用者可見文字，包括修補可用性說明、預覽視窗說明、候選選取、方案摘要、候選明細、顯示用狀態名稱、拒絕診斷與提交錯誤。同一角色、移植方式或定位尺寸在角撐修補介面中重複出現時 MUST 使用一致的中文術語，且可共用術語 SHALL 可由其他 Presentation consumer 重用。

使用者可見的 `reference_waler_offset_mm` SHALL 顯示為「圍令端定位距離」，`reference_strut_station_mm` SHALL 顯示為「支撐端定位距離」；介面 SHALL 顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」或語意完全相同的繁體中文說明。此顯示名稱變更 MUST NOT 更名內部欄位、DTO、serialized key 或 planner term。

角撐修補預覽中的工程長度、定位距離及座標分量 SHALL 固定顯示至小數第 3 位。工程長度與定位距離 SHALL 顯示 `mm` 單位；座標 SHALL 維持既有無單位表示方式。顯示格式 MUST NOT 改變原始 double precision、candidate eligibility、排序、candidate ID、工程幾何、提交結果或 persistence contract。

#### Scenario: 預覽合法候選

- **WHEN** 使用者開啟具有一個或多個合法候選的角撐修補預覽
- **THEN** 視窗說明、候選選取、方案摘要與候選明細 SHALL 使用繁體中文描述目標圍令與支撐、參考模板、移植方式、局部尺寸、結果長度及驗證證據
- **AND** 構件 ID、格式化數值與適用的 `mm` 單位 SHALL 保持可稽核內容

#### Scenario: 顯示移植方式

- **WHEN** 候選的內部移植方式為 `same_side` 或 `mirrored`
- **THEN** 介面 SHALL 分別顯示「同側移植」或「鏡射移植」
- **AND** 系統 MUST 保留原內部值供候選選取、提交與持久化使用

#### Scenario: 定位尺寸使用直觀名稱

- **WHEN** 介面顯示 candidate 的 reference local Waler offset 與 Strut inward station
- **THEN** SHALL 分別顯示「圍令端定位距離」與「支撐端定位距離」
- **AND** SHALL 顯示「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」或語意完全相同的繁體中文說明
- **AND** MUST NOT 因顯示名稱變更而改寫內部欄位、DTO、serialized key、planner term 或幾何意義

#### Scenario: 預覽數值統一顯示三位小數

- **WHEN** 角撐修補預覽顯示結果長度、reference fixed length、圍令端定位距離、支撐端定位距離、positional anchor、candidate world engineering line 或多候選表格中的工程數值
- **THEN** 每一個工程數值與座標分量 SHALL 固定顯示至小數第 3 位
- **AND** 工程長度與定位距離 SHALL 顯示 `mm` 單位
- **AND** positional anchor 與 candidate world engineering line 的座標 SHALL 維持無單位表示方式
- **AND** 正數、負數與整數 SHALL 使用相同三位小數格式，包括必要的尾端補零與顯示四捨五入
- **AND** 顯示四捨五入 MUST NOT 回寫或改變原始 double precision、candidate eligibility、排序、candidate ID、工程幾何或提交值

#### Scenario: 重複概念使用一致術語

- **WHEN** 角撐修補的候選選取、主要確認區與次要稽核區顯示相同的角色、移植方式或定位尺寸
- **THEN** `corner_brace` SHALL 一致顯示為「角撐」，`same_side` SHALL 一致顯示為「同側移植」，`mirrored` SHALL 一致顯示為「鏡射移植」
- **AND** Waler-side offset 與 Strut inward station SHALL 分別一致顯示為「圍令端定位距離」與「支撐端定位距離」
- **AND** 其他介面使用相同可共用術語時 SHALL 能取得同一中文名稱，而不必重新定義另一份對照

#### Scenario: 修補不可執行或提交失敗

- **WHEN** 選取項目不符合修補前提、沒有候選通過安全條件，或提交時偵測到 stale／invalid repair state
- **THEN** 系統 SHALL 以繁體中文顯示具體原因
- **AND** SHALL 維持既有拒絕、保留原狀或 rollback 語意，不得因翻譯或版面變更而改用較寬鬆的 fallback
