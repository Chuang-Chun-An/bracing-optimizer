# Proposal

## Why

Global Waler 求解成功後目前仍要求使用者再按一次「套用全域結果」，使求解完成與正式採用之間存在不必要的暫存狀態，也與 Support／Single Waler 成功後立即採用的操作模式不一致。這次變更讓合法的全域結果在求解完成時直接透過既有 atomic apply 邊界寫入 `ProjectResultModel`，同時保留失敗時原成果不變的保護。

## What Changes

### In Scope

- Global Waler Solver 回傳合法 solution 後，立即呼叫既有 global result apply 流程，不再等待額外 Apply 操作。
- 移除 Global Waler Dialog 的「套用全域結果」操作入口及其待套用狀態。
- 保留求解開始前的人工修改成果覆蓋確認；使用者拒絕時不啟動求解，也不修改成果。
- 沿用既有 staging、atomic commit 與 rollback：staging 或 commit 失敗時保留完整原成果，不允許部分 Waler 更新。
- commit 成功後刷新成果樹、材料統計所依賴的結果狀態與預覽；refresh 失敗只提示畫面問題，不回滾已採用成果。
- Dialog 保留全場 S／M／L／O、比例、Out distance、local regret 與變更 Waler 摘要，並明確顯示「全域結果已採用」。
- 自動採用完成後關閉 Dialog 只關閉結果視窗，不撤銷已提交成果。
- 新增自動採用、求解失敗、commit rollback、refresh failure 與 pre-solve confirmation 的 regression tests。

### Out of Scope

- Global DP、objective、Out／Ratio／Local regret 計算與候選生成。
- Single Waler Solver、Inventory、material rules 與 Project schema。
- 重新設計 `ProjectResultModel` 或另建第二套 global apply transaction。
- 改變人工修改成果被 Global Waler 結果取代的既有產品規則。

## Capabilities

### New Capabilities

- `global-waler-result-adoption`: 定義 Global Waler 求解前覆蓋確認、合法結果自動採用、原子提交、失敗保留與結果摘要行為。

### Modified Capabilities

- 無；目前 `openspec/specs/` 尚未定義相關 capability。

## Impact

- 主要影響 Global Waler Dialog 的完成回呼與 UI 狀態，以及 Main 的既有 global apply callback 串接。
- `ProjectResultModel.stage_waler_global_result()` 與既有 commit／rollback 邊界應被重用，預期不改變其資料契約。
- 這是 Workflow truth 的變更，不改變 Domain、Solver objective、演算法或架構分層；實作驗證完成後需同步更新 `docs/WORKFLOW.md` 中仍描述手動 Apply 的段落。
