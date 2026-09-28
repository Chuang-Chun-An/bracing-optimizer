# Spec Delta

## Purpose

定義 RC 圍令在正式 Project 與 Support 工程關係中持續有效，但不進入鋼圍令材料配置最佳化，並確保材料類型切換不會沿用已失效的 Solver 成果。

## ADDED Requirements

### Requirement: RC Waler 必須保留為正式工程構件但排除於 Waler 最佳化
當 Waler 的正式 `material_spec` 經去除前後空白並忽略大小寫後等於 `RC`，系統 MUST 將其視為 RC Waler。RC Waler MUST 保留於 Project 工程資料、幾何、構件連接關係及 Support Solver 所需的 Waler 類型判定，但 MUST NOT 成為 Waler 材料配置最佳化的對象。任何非 RC Waler SHALL 繼續進入既有 validation、材料／庫存檢查與求解流程；系統不得因其不是 RC 就逕行宣告為有效 Steel Waler。

#### Scenario: RC Waler 仍供 Support Solver 使用
- **WHEN** Strut 的任一端連接 material spec 為 RC 的 Waler
- **THEN** Support Solver input MUST 保留該 Waler 的 RC 類型
- **AND** 既有 RC／Steel 接觸面工程規則 MUST 繼續適用

#### Scenario: RC 判定正規化
- **WHEN** Waler 的 `material_spec` 只在大小寫或前後空白上與 `RC` 不同
- **THEN** 系統 MUST 將該 Waler 視為 RC 並排除於 Waler 最佳化

#### Scenario: 非 RC Waler 沿用既有行為
- **WHEN** Waler 的 `material_spec` 不是 RC
- **THEN** 系統 SHALL 依既有 validation、材料、庫存、候選、搜尋、評分與結果採用規則處理該 Waler
- **AND** blank、unknown 或自訂規格 MUST NOT 僅因不是 RC 而被重新分類為 Steel

### Requirement: Single Waler workflow 不得計算 RC Waler
Single Waler workflow MUST 僅允許 eligible non-RC Waler 進入選擇與求解範圍。RC Waler MUST NOT 被送入 Single Waler optimization use case、Solver Dialog 或背景 worker。Eligibility 只代表未被 RC exclusion 排除，不取代既有資料與材料合法性檢查。

#### Scenario: 混合 RC 與 Steel Waler
- **WHEN** Project 同時包含 RC 與 Steel Waler，且使用者啟動 Single Waler Solver
- **THEN** 可供本次 Single Waler 求解選擇的集合 MUST 僅包含 non-RC Waler
- **AND** non-RC Waler 的既有 validation 與求解流程保持不變

#### Scenario: Project 沒有可最佳化的 Steel Waler
- **WHEN** Project 僅有 RC Waler，且使用者啟動 Single Waler Solver
- **THEN** 系統 MUST 告知沒有可進行材料配置的 non-RC Waler
- **AND** MUST NOT 開啟 Solver Dialog 或啟動 worker
- **AND** 既有 Project results 與 operation state MUST 保持不變

### Requirement: Global Waler workflow 必須排除 RC Waler
Global Waler workflow MUST 在 local candidate generation 與既有前置檢查前，將 RC Waler 排除於本次求解範圍。材料庫存檢查、人工修改成果覆蓋確認、local optimization 與 global selection MUST 僅涵蓋 eligible non-RC Waler；成功 result adoption 另 MUST 清除 Project 中所有 RC Waler 的 historical configuration results。

#### Scenario: 混合 RC 與 Steel Waler 的全域求解
- **WHEN** Project 同時包含 RC 與 Steel Waler，且使用者啟動 Global Waler Solver
- **THEN** 系統 MUST 只替 non-RC Waler 產生 local candidates 並進行全域選擇
- **AND** RC Waler 缺少 purchasable lengths MUST NOT 阻擋 non-RC Waler 的求解
- **AND** 成功採用的結果 MUST 取代本次涵蓋的 non-RC Waler 結果
- **AND** MUST 清除 Project 中所有 RC Waler 的 historical configuration results

#### Scenario: 人工成果覆蓋確認只涵蓋 Steel Waler
- **WHEN** RC Waler 與 Steel Waler 都存在人工修改成果
- **THEN** Global Waler 求解前的覆蓋確認 MUST 僅列出本次將被求解的 non-RC Waler
- **AND** RC Waler 的 historical result cleanup MUST NOT 被描述成重新求解或方案取代

#### Scenario: Project 全部為 RC Waler
- **WHEN** Project 沒有任何可最佳化的 Steel Waler，且使用者啟動 Global Waler Solver
- **THEN** 系統 MUST 告知沒有可進行材料配置的 non-RC Waler
- **AND** MUST NOT 產生 local candidates、執行 global selection、開啟 Solver Dialog 或啟動 worker
- **AND** 既有 Project results 與 operation state MUST 保持不變

#### Scenario: Global 求解失敗不得清除 historical RC result
- **WHEN** Global Waler Solver 發生 exception、沒有 valid solution、staging 失敗或 commit 失敗
- **THEN** historical RC Waler results MUST 保持不變
- **AND** 其他既有 Project results MUST 依既有 atomic failure semantics 保持不變

#### Scenario: Global commit 後 UI refresh 失敗
- **WHEN** valid Global result 已成功 commit 並已清除 historical RC results，但後續 UI refresh 失敗
- **THEN** committed non-RC results 與 RC cleanup MUST 保持有效
- **AND** 系統不得因 UI refresh failure 回復已提交的 historical RC results

### Requirement: Application use case 必須防止 RC 進入 Waler 演算法
即使呼叫端未先過濾，Application 層的 Single 與 Global Waler optimization contract 仍 MUST 在任何 Waler 演算法、搜尋或候選生成開始前排除或拒絕 RC input。此防線 MUST NOT 修改 Waler Solver 演算法本身。

#### Scenario: 直接呼叫 Single use case 傳入 RC
- **WHEN** Application caller 直接以 RC Waler input 呼叫 Single Waler optimization
- **THEN** use case MUST 在演算法開始前拒絕該 request
- **AND** MUST NOT 產生或提交 Waler result

#### Scenario: 直接呼叫 Global use case 傳入混合集合
- **WHEN** Application caller 直接以 RC 與 Steel Waler inputs 呼叫 Global Waler optimization
- **THEN** use case MUST 只將 non-RC inputs 送入 local optimization 與 global selection
- **AND** selected result scope MUST 只包含 non-RC Waler

### Requirement: Waler 材料切換必須使既有 Solver state 失效
Waler `material_spec` 成功變更時，系統 MUST 沿用正式 Project input change lifecycle，使既有 committed Solver results 與依賴舊輸入的 runtime Solver caches 失效。此失效 MUST 發生於資料修改成功之後；取消、驗證失敗或實際值未變的編輯 MUST NOT 清除結果。

#### Scenario: Steel Waler 改成 RC
- **WHEN** 使用者成功將已有配置結果的 Steel Waler 改為 RC
- **THEN** 原有 Steel Waler 配置結果 MUST 失效
- **AND** 依賴原材料類型的 Support results 與 runtime Solver caches MUST 失效
- **AND** 系統 MUST NOT 對該 RC Waler 自動重新計算材料配置

#### Scenario: RC Waler 改回 Steel
- **WHEN** 使用者成功將 RC Waler 改為 Steel material spec
- **THEN** 該 Waler SHALL 再次成為可最佳化對象
- **AND** 系統 MUST NOT 自動恢復或重用切換前的舊 Waler result
- **AND** 使用者可依既有 Single 或 Global workflow 重新計算

#### Scenario: 材料編輯未成立
- **WHEN** Waler material edit 被取消、未通過驗證或正規化後沒有實際變更
- **THEN** 系統 MUST NOT 因該次編輯清除既有 results 或 runtime caches
