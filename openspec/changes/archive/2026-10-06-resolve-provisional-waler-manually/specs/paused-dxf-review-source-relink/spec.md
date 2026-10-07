# Spec Delta：人工圍令正式化 decision 的恢復邊界

## 閱讀導航

- **必讀**：「人工圍令正式化 decision 不得跨內容靜默轉移」；定義 Exact Match、same-content resume 與 changed-content recovery 的差異。
- **條件式閱讀**：修改 recovery summary 時閱讀 preserved／requires_review／disabled Scenarios；修改 source identity 重綁時閱讀 exact subject 存在與消失 Scenarios。
- **可先跳過**：一般材料、人工端點、Waler 尺寸輸入、雙路支撐及 CornerBrace repair recovery requirements；本 delta 不改它們的既有分類。

## ADDED Requirements

### Requirement: 人工圍令正式化 decision 不得跨內容靜默轉移

系統 SHALL 將已採用的 provisional Waler 人工正式化視為與 Waler role、exact source identity、採用 WCS 起終點、工程線輸入來源及明確正式化意圖綁定的人工 decision。Paused Review 以相同 source fingerprint 恢復，或透過 `EXACT_MATCH` 重新連結來源時，系統 MUST 完整保留該 decision；恢復 live Review 後仍 MUST 依目前 validation 重建人工 formal line 與 downstream state，且 replay 失敗時 MUST 保留可處理 subject、要求重新檢查，不得靜默退回自動 winner。

候選 DXF fingerprint 不同時，compatible recovery MUST 以候選重新辨識結果為基底，且 MUST NOT 依一般 critical-member geometry matching、相同或相近位置、相同顯示 ID，或舊人工端點 replay 成功，就自動轉移人工正式化 authority。若 changed-content 候選仍存在相同角色與 exact source identity 的可處理 provisional Waler subject，舊 decision SHALL 不套用並分類為 `requires_review`；若 exact source identity 不再存在、角色改變、subject 已無法定位或不再可處理，舊 decision SHALL 分類為 `disabled`。兩種分類均不得讓舊人工 formal line、diagnostic suppression 或 downstream connections 影響 recovered engineering state。

只有使用者在 recovered Review 中重新預覽、明確採用並通過目前 formalization validation 後，該 Waler 才可再次取得人工 formal authority。系統 MUST NOT 從 legacy `selection_source`、一般 manual endpoint 或 CAD geometry override 推定正式化意圖。

#### Scenario: Same-fingerprint Resume 保留人工正式化

- **WHEN** paused Review 以相同 source fingerprint 恢復，且人工正式化 decision 的 exact Waler subject 與採用線仍通過 validation
- **THEN** 系統 SHALL 恢復該人工 formal line、正式化 provenance 與由目前 result 重建的 downstream state
- **AND** MUST NOT 要求使用者只因暫停／繼續而重新採用

#### Scenario: Exact Match Relink 保留人工正式化

- **WHEN** paused Review 透過 `EXACT_MATCH` 候選重新連結來源
- **THEN** 人工圍令正式化 decision SHALL 與其他既有 Review state 一起完整保留
- **AND** Relink MUST NOT 新增只因該 decision 而產生的 `requires_review` entry

#### Scenario: Changed-content 中 exact provisional subject 仍存在

- **WHEN** compatible recovery 的候選內容不同，但相同 Waler role 與 exact source identity 的可處理 provisional subject 仍存在
- **THEN** 系統 SHALL 不套用舊人工 formal line，將 decision 分類為 `requires_review`
- **AND** recovered Review SHALL 顯示 candidate-based provisional state，等待使用者重新採用

#### Scenario: Changed-content 中 exact subject 不再存在

- **WHEN** compatible recovery 的候選內容不同，且人工正式化 decision 的 exact source identity 不再存在、角色改變或無法定位可處理 subject
- **THEN** 系統 SHALL 不套用舊 decision 並將其分類為 `disabled`
- **AND** geometry-only rebind MUST NOT 把人工 authority 轉移至另一支 Waler

#### Scenario: Changed-content 候選已自動 formal

- **WHEN** compatible recovery 的候選內容不同，且同 exact source 的候選 Waler 已可由目前 recognition 自動形成 formal contact line
- **THEN** recovered Review SHALL 使用候選自己的自動 formal result
- **AND** 舊人工正式化 decision SHALL 不套用並分類為 `requires_review`，直到使用者決定是否仍需人工覆寫

#### Scenario: Legacy 一般人工幾何沒有正式化意圖

- **WHEN** paused state 只有一般 `manual_candidate_points` 或 `cad_manual` geometry selection，沒有人工圍令正式化 decision
- **THEN** Resume 或 Relink MUST 保持既有 geometry replay contract
- **AND** MUST NOT 因 geometry replay 成功而清除 envelope／contact-face blocker或升級 provisional Waler
