# Spec Delta

## Purpose

定義 Global Waler 最佳化從求解前覆蓋確認、合法結果自動採用，到失敗保留與結果摘要的可靠 workflow，確保全場結果只會完整提交或完全不變。

## ADDED Requirements

### Requirement: 人工修改成果須於求解前確認覆蓋
當本次 Global Waler 求解涵蓋的任一 Waler 存在人工修改成果時，系統 MUST 在啟動求解前告知將被取代的 Waler，並取得使用者確認。

#### Scenario: 使用者同意覆蓋人工修改成果
- **WHEN** 本次涵蓋人工修改成果，且使用者同意覆蓋
- **THEN** 系統開始 Global Waler 求解
- **AND** 在合法結果成功提交前保留目前成果

#### Scenario: 使用者拒絕覆蓋人工修改成果
- **WHEN** 本次涵蓋人工修改成果，且使用者拒絕覆蓋
- **THEN** 系統不得開始 Global Waler 求解
- **AND** `ProjectResult` MUST 保持不變

#### Scenario: 沒有人工修改成果
- **WHEN** 本次涵蓋的 Waler 均沒有人工修改成果
- **THEN** 系統不顯示覆蓋確認並可直接開始求解

### Requirement: 合法全域結果須立即自動採用
Global Waler 求解完成且 solution 為 valid 時，系統 SHALL 立即採用該全域結果，不得要求使用者再執行 Apply 或「套用全域結果」操作。

#### Scenario: 合法 solution 完成
- **WHEN** Global Waler Solver 回傳 valid solution
- **THEN** 系統立即啟動既有全域結果採用流程
- **AND** 使用者不需要再按 Apply

#### Scenario: 自動採用成功
- **WHEN** valid solution 的 staging 與 commit 均成功
- **THEN** `ProjectResult` 包含本次選定的全部 Waler 結果
- **AND** 本次涵蓋的舊 Waler 結果被完整取代
- **AND** 不屬於本次涵蓋範圍的結果保持不變
- **AND** 成果樹、材料統計與預覽被要求更新

### Requirement: 全域結果提交必須具備原子性
系統 MUST 先完整 staging 所有選定 Waler 結果，只有 staging 全部成功後才能 commit；commit 期間發生失敗時 MUST rollback 到提交前的完整成果狀態。

#### Scenario: Staging 失敗
- **WHEN** 任一選定 Waler 缺少必要資料或 staging 發生 exception
- **THEN** 系統回報套用失敗
- **AND** `ProjectResult` 與提交前完全相同
- **AND** 不得留下部分 Waler 更新

#### Scenario: Commit 失敗
- **WHEN** staging 成功但 commit 發生 exception
- **THEN** 系統回報套用失敗
- **AND** `ProjectResult`、計算時間與 dirty state 回復至提交前狀態
- **AND** 不得執行成功後的 UI refresh

### Requirement: 求解失敗不得改變正式成果
Global Waler Solver 發生 exception、沒有 solution 或回傳 invalid solution 時，系統 MUST 保留原 `ProjectResult`，且不得啟動結果採用流程。

#### Scenario: Solver 發生 exception
- **WHEN** Global Waler 求解拋出 exception
- **THEN** 系統顯示求解失敗
- **AND** `ProjectResult` 保持不變

#### Scenario: Solution 不合法或不存在
- **WHEN** 求解完成但 solution 不存在或 `valid` 為 false
- **THEN** 系統顯示無合法全域結果及可用原因
- **AND** `ProjectResult` 保持不變

### Requirement: Commit 後 UI refresh 失敗不得撤銷成果
結果 commit 與後續 UI refresh MUST 維持不同的錯誤邊界；commit 成功後，任何成果樹、材料統計、結果頁或預覽更新失敗均不得 rollback 已提交成果。

#### Scenario: Commit 與 refresh 均成功
- **WHEN** 全域結果 commit 成功且所有必要 UI refresh 成功
- **THEN** 新結果保持為正式成果
- **AND** Dialog 顯示全域結果已採用

#### Scenario: Commit 成功但 refresh 失敗
- **WHEN** 全域結果 commit 成功但任一 UI refresh 發生 exception
- **THEN** 新結果仍保持在 `ProjectResult`
- **AND** 系統提示成果已採用但畫面更新失敗
- **AND** 不得將成果回復成提交前狀態

### Requirement: Dialog 須顯示已採用摘要且關閉不撤銷
自動採用成功後，Global Waler Dialog SHALL 保留全場結果摘要與逐支選定方案，並明確顯示「全域結果已採用」；關閉 Dialog 只關閉視窗，不得改變已提交成果。

#### Scenario: 顯示已採用摘要
- **WHEN** valid solution 已成功 commit
- **THEN** Dialog 顯示「全域結果已採用」
- **AND** 摘要仍可呈現 S／M／L／O、比例、Out distance、local regret 與調整的 Waler
- **AND** Dialog 不提供仍待執行的 Apply 操作

#### Scenario: 採用後關閉 Dialog
- **WHEN** 使用者在自動採用成功後關閉 Global Waler Dialog
- **THEN** 已提交的全域結果保持不變

