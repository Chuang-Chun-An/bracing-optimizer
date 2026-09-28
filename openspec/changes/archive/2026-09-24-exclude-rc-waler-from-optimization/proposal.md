# Proposal

## Why

RC 圍令是正式工程構件，但不是鋼圍令材料分段配置的計算對象；目前 Single Waler 與 Global Waler 流程仍會把 RC 送進 Waler Solver，造成缺少可購買料長的錯誤，甚至阻擋同案場其他 Steel Waler 的全域計算。系統需要在 Solver orchestration 邊界明確區分「保留於工程模型」與「可進行鋼材配置最佳化」。

## What Changes

- 將材料規格為 RC 的 Waler 定義為不可進入 Waler 材料配置最佳化，但仍完整保留於 Project geometry、連接關係與 Support Solver input。
- Single Waler workflow 不啟動 RC Waler 的 Solver Dialog、use case 或 worker，並提供明確的使用者回饋；其餘非 RC 規格仍沿用既有 validation 與求解行為。
- Global Waler workflow 在啟動最佳化前排除 RC，只對 eligible non-RC Waler 檢查庫存、確認人工成果覆蓋、產生候選及提交結果；若沒有可最佳化的 non-RC Waler，則不啟動 Solver且不修改結果。
- Global Waler valid result 成功採用時，一併清除 Project 中所有 RC Waler 的 historical configuration results；Solver、staging 或 commit 失敗時不得提前清除。
- 沿用現有 Project input edit lifecycle：Waler 材料由 Steel 改為 RC 或由 RC 改為 Steel 時，既有 Solver results 與 runtime caches 失效；改回 Steel 後可重新計算，但不恢復舊結果。
- Steel Waler 的 input、search、scoring、candidate generation 與結果採用行為保持不變。

### In Scope

- RC eligibility 的單一判定規則。
- Single／Global Waler 啟動前的排除與 UI 回饋。
- 混合 RC／Steel 與全 RC 專案的 workflow 行為。
- Global valid result adoption 對 historical RC Waler results 的原子清除。
- 材料切換後結果與 cache 失效的 regression coverage。
- 完成實作後，更新受影響的長期 Domain／Solver／Workflow 文件。

### Out of Scope

- 移除 RC Waler、修改其幾何或連接關係。
- 改變 Support Solver 對 RC／Steel 接觸面的既有規則。
- 修改 Waler Solver algorithms、搜尋、評分、候選數或材料比例。
- 自動恢復舊的 Steel Waler result。
- 載入時主動 migration 或清理舊版 Project 的不一致 result payload。
- 大型 Solver UI、Project edit 或 result lifecycle refactor。

## Capabilities

### New Capabilities

- `rc-waler-optimization-exclusion`: 定義 RC Waler 在 Single／Global Waler workflow 的排除、正式工程資料保留、Global adoption 時 historical RC result cleanup，以及材料切換後的結果失效行為。

### Modified Capabilities

無。既有 `global-waler-result-adoption` 的原子 staging／commit／rollback contract 維持不變；本 change 以新的 capability 定義 non-RC solve scope，並將目前 Project 的 RC Waler IDs 納入成功 adoption 的 cleanup scope，因此其餘未被選取且非 RC 的結果仍保持不變。

## Impact

- Application：集中提供 Waler optimization eligibility，並沿用既有 Project input change invalidation contract。
- Presentation／`main.py`：Single 選擇範圍、Global 求解集合、前置檢查與使用者回饋。
- Solver input：`WalerInputBuilder` 仍可建立正式 Waler 幾何輸入；RC 排除不下沉到 Algorithms，也不影響 Support input builder。
- Results／runtime state：沿用既有 input-edit 全結果與 Solver cache 清除行為；Global valid adoption 另在既有 atomic staging 中清除 historical RC results。
- Tests：Application eligibility、Single／Global workflow、result invalidation、Support RC regression 與 Steel regression。
- Long-term truth：預期更新 `docs/DOMAIN.md`、`docs/SOLVER.md` 與 `docs/WORKFLOW.md`；不改變 `docs/ARCHITECTURE.md` 的 dependency direction，也不改變 Waler 搜尋／評分演算法。
