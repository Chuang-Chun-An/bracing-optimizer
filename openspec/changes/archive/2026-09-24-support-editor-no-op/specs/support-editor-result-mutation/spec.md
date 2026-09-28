# Spec Delta

## Purpose

定義 Support Editor 何時屬於真正的人工成果修改，以及 no-op 時必須保留的正式結果、時間、dirty state 與畫面副作用，避免單純查看方案被誤認為資料變更。

## ADDED Requirements

### Requirement: Support Editor no-op 不得修改正式 Project result state

當 Support Editor 的 ordered piece layout 經既有正規化後，與目前 committed Support result 中所有受影響構件的 layout 相同時，系統 SHALL 將操作視為 no-op。No-op MUST 保留目前 committed Support solution、result metadata、`last_calculated_time`、persisted result projection、Project dirty flag 與 dirty reason，且 MUST NOT 觸發正式 Results Tree／Preview mutation refresh。

#### Scenario: 開啟 Editor 後直接關閉
- **WHEN** 使用者開啟 Support Editor，未修改任何 piece，並以「關閉」按鈕或視窗關閉動作離開
- **THEN** committed Support solution、result metadata、calculated time 與 Project dirty state 全部維持開啟前的值

#### Scenario: 開啟 Editor 後保持原值
- **WHEN** Editor 初始化目前 piece layout 及狀態摘要，但正規化後的 layout 與 committed result 相同
- **THEN** 系統可更新 Editor 內的唯讀顯示，但不得採用新的 staged solution、更新正式結果時間或觸發正式結果畫面 refresh

#### Scenario: 欄位確認為相同值
- **WHEN** 使用者進入 piece 類型或長度編輯，最後確認的正規化值與目前 committed layout 相同
- **THEN** 系統將該操作視為 no-op，不修改 Project result 或 dirty state

#### Scenario: Project 原本已經 dirty
- **WHEN** Support Editor 發生 no-op，而 Project 在開啟 Editor 前已是 dirty
- **THEN** 系統保留既有 dirty flag 與 dirty reason，不得清除或改寫成 Support result change

### Requirement: No-op 判定必須涵蓋 shared-layout group

當被編輯的 Support 屬於 shared-layout group 時，系統 MUST 以該次操作會影響的全部 group members 之目前 committed ordered piece layout 判定是否有實際變更。只有所有受影響 member 均已具有相同的正規化 layout 時才是 no-op；任一受影響 member 不同時 SHALL 視為實際修改。

#### Scenario: Shared group 全部已是相同 layout
- **WHEN** 使用者送出的正規化 piece layout 與 shared-layout group 內每一支受影響 Support 的 committed layout 相同
- **THEN** 系統回報 no-op，且不重算、不採用、不更新時間或 dirty

#### Scenario: Shared group 仍有 member 不同
- **WHEN** 目標 Support 的 layout 相同，但 shared-layout group 內至少一支會被同步的 Support 仍與送出 layout 不同
- **THEN** 系統將操作視為實際修改，並沿用既有 shared-layout group 更新流程

### Requirement: 實際 Support 修改維持 immediate commit 行為

當正規化後的 ordered piece layout 與目前 committed result 確實不同時，系統 SHALL 沿用既有 Support manual-edit workflow：以 Application staged result 重新計算受影響方案及全域分析，成功 staging 後立即採用，更新 calculated time 與 persisted result metadata、設定 Project dirty，並刷新 Results Tree 與 Preview。可形成方案但工程檢查為 invalid 的結果仍 SHALL 依既有行為正式保留供後續修正。

#### Scenario: 修改 piece 類型、長度、數量或順序
- **WHEN** 使用者新增、刪除、移動 piece，或將 piece 類型／長度改為不同的合法輸入值
- **THEN** 系統 stage 並採用新的 Support solution，更新時間與 dirty，並刷新正式結果畫面

#### Scenario: 實際修改形成工程 invalid result
- **WHEN** 使用者輸入格式可處理且 layout 確實不同，但重新計算後工程檢查為 invalid
- **THEN** 系統仍依既有 manual-edit 行為採用 invalid result、更新時間與 dirty，供使用者繼續修正

#### Scenario: 無法形成合法輸入格式
- **WHEN** piece 類型或長度無法正規化為既有可處理格式
- **THEN** 系統拒絕 staging 與採用，保留目前 committed result、時間與 dirty state

#### Scenario: 修改後再改回先前 layout
- **WHEN** 使用者先完成一次實際修改，之後再把目前 committed layout 改成更早的 layout
- **THEN** 第二次操作仍是相對於最新 committed result 的實際修改，系統再次沿用 immediate commit 行為
