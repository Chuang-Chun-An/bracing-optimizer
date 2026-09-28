# Tasks

## 1. 建立 Application no-op contract

- [x] 1.1 在 `tests/test_plan_editing.py` 補上單支 Support 與 shared-layout group 的 characterization／規格測試，涵蓋相同 normalized ordered piece layout 為 no-op、任一 group member 不同即為 change，並以測試失敗確認現行缺口。
- [x] 1.2 在 `bracing_optimizer/application/plan_editing.py` 為 `SupportPlanEditResult` 增加明確的 `changed` outcome，集中重用既有 piece normalization 與 shared-layout target 判定；以型別檢查及 `tests/test_plan_editing.py` 驗證 caller 不需用 object identity、空清單或 UI raw value 推測是否變更。
- [x] 1.3 在 `SupportPlanEditing.stage_edit()` 的 deep copy、單支重算及全域重算之前，比對所有 affected Support 的 committed canonical ordered piece layout；驗證全數相同時回傳 `changed=False` 且不執行工程重算、不修改來源 solution，任一 member 不同時仍走既有完整 staging 流程。
- [x] 1.4 擴充 `tests/test_plan_editing.py` 的 changed-path regression，驗證新增、刪除、移動、修改材料型別或長度，以及 shared-layout propagation 仍回傳 `changed=True` 並保留目前 validation、adjacency 與 global recalculation 結果。

## 2. 收斂 Main 的結果採用與 dirty-state 邊界

- [x] 2.1 在 `main.py` 的 Support Editor workflow 抽出最小範圍的 staged-result adoption gate（或等價 helper），只有 `changed=True` 才替換 `item["result"]`、呼叫 `_mark_results_updated()` 並 refresh Results Tree／Preview；以 presentation interaction test 驗證 no-op 不會觸發任何正式結果 mutation side effect。
- [x] 2.2 將 Editor 開啟時的初始顯示、欄位確認及既有 edit callbacks 接到同一個 no-op-aware flow；以 headless UI／callback 測試驗證開啟後直接關閉、開啟後未修改即確認，以及輸入等價值時，既有 result、`last_calculated_time`、persisted result projection、`project_dirty` 與 `project_dirty_reason` 全部不變。
- [x] 2.3 補上 Main changed-path regression，驗證真實修改仍立即採用 staged solution、更新時間與 persisted result metadata、設為 dirty、刷新 Results Tree／Preview，且工程上 invalid 的手動結果仍依既有行為保存並顯示警告。
- [x] 2.4 補上 change-then-revert 與 already-dirty regression：前者以最新 committed solution 為比較基準，第二次操作仍視為實際修改；後者執行 no-op 時保留原 dirty flag 與 dirty reason，不改寫為 Support result change。

## 3. 維持架構邊界與長期文件

- [x] 3.1 更新 `tests/test_interface_presentation.py` 的 boundary assertions，驗證 `main.py` 只消費 Application 的 `changed` outcome，不複製 piece normalization、shared-layout 或 Solver 規則，並確認既有 Support Editor dependency direction 測試通過。
- [x] 3.2 在功能及測試成立後更新 `docs/WORKFLOW.md`，把 Support Editor 開啟即 mutation 的 Product Gap 改為已實作的 no-op／immediate-commit truth；檢查 diff 確認未提前或額外修改 `ARCHITECTURE.md`、`DOMAIN.md`、`SOLVER.md` 與 Project schema。

## 4. 整合驗證

- [x] 4.1 執行 Support 編輯與成果生命週期的 focused tests（至少 `tests/test_plan_editing.py`、新增的 Support Editor interaction tests、`tests/test_interface_presentation.py`、`tests/test_project_results.py`），確認 no-op 與 changed paths 全部通過。
- [x] 4.2 執行專案完整 test suite，確認既有 manual editing、Solver、persistence、dirty-state 與 UI 行為無回歸，且不得以 skip、刪除測試或降低 assertion 排除失敗。
- [x] 4.3 執行 OpenSpec change 的嚴格驗證與 implementation verification，逐項核對 `support-editor-result-mutation` scenarios、proposal／design／tasks 與實際程式一致，並記錄任何仍存在的限制。
