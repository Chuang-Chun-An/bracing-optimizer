# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：下列修改後 Requirement 全文；它保留 valid result 的立即自動採用，並加入 operation eligibility gate。
- **條件式閱讀（P1）**：實作 callback gate 時同讀 `../solver-cad-update-cancellation/spec.md` 的「stale operation 不得採用任何輸出」。
- **可先跳過**：`global-waler-result-adoption` 其餘 Requirements；其 atomic commit、failure preservation 與 refresh error semantics 不變。

## MODIFIED Requirements

### Requirement: 合法全域結果須立即自動採用

Global Waler 求解完成、solution 為 valid、registry判定該operation仍可採用，且既有Project mutation guard允許正式state mutation時，系統 SHALL 立即採用該全域結果，不得要求使用者再執行 Apply 或「套用全域結果」操作。若 operation 已因 CAD mutation 失效或取消，或既有ACK unresolved guard拒絕adoption，即使 solution 為 valid，系統 MUST NOT 啟動結果採用流程。

#### Scenario: 合法 solution 完成

- **WHEN** Global Waler Solver 回傳 valid solution、registry判定該operation仍可採用，且既有Project mutation guard允許正式state mutation
- **THEN** 系統立即啟動既有全域結果採用流程
- **AND** 使用者不需要再按 Apply

#### Scenario: 自動採用成功

- **WHEN** 仍可採用的 valid solution 之 staging 與 commit 均成功
- **THEN** `ProjectResult` 包含本次選定的全部 Waler 結果
- **AND** 本次涵蓋的舊 Waler 結果被完整取代
- **AND** 不屬於本次涵蓋範圍的結果保持不變
- **AND** 成果樹、材料統計與預覽被要求更新

#### Scenario: valid solution 在 CAD mutation 後晚到

- **WHEN** Global Waler Solver 回傳 valid solution，但該 operation 已因 CAD mutation 失去 adoption 資格
- **THEN** 系統 MUST NOT 啟動 staging 或 commit
- **AND** `ProjectResult`、calculated time 與 dirty state SHALL NOT 因該 callback 改變

