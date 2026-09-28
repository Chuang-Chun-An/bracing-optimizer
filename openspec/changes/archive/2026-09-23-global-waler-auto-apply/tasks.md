# Tasks

## 1. 建立 Dialog 自動採用的回歸契約

- [x] 1.1 在 `tests/test_waler_global_reliability.py` 新增或調整測試，驗證合法 Global solution 完成後會在 UI thread 自動呼叫既有 apply callback，且每次求解只呼叫一次；執行該測試檔確認通過。
- [x] 1.2 新增測試驗證 Solver exception、無合法 solution 與 invalid solution 都不會呼叫 apply callback，並保留原本的失敗提示；執行相關指定測試確認通過。
- [x] 1.3 新增 Dialog outcome 測試，涵蓋 commit failure、commit success 加 UI refresh failure、完整成功三種結果，並驗證只有 commit 成功時摘要會明確顯示「全域結果已採用」；執行相關指定測試確認通過。
- [x] 1.4 新增介面契約測試，驗證求解完成後不再存在或依賴「套用全域結果」按鈕，關閉已成功採用結果的 Dialog 不會觸發撤銷；執行相關指定測試確認通過。

## 2. 實作 Global Waler 自動採用流程

- [x] 2.1 修改 Global Waler Solver Dialog，在合法結果回到 UI thread 並完成結果呈現後，立即且僅一次呼叫既有 global result apply callback；執行 `tests/test_waler_global_reliability.py` 確認通過。
- [x] 2.2 移除求解完成後的 Apply／「套用全域結果」操作與舊 callback 入口，但保留結果表格、全場 S/M/L/O、比例、Out、local regret 與調整 Waler 摘要；執行 Dialog 相關測試確認呈現與流程通過。
- [x] 2.3 依 apply outcome 顯示「已採用」、套用失敗或畫面更新失敗狀態，並確保 commit 成功後關閉 Dialog 只關閉視窗、不修改 `ProjectResult`；執行新增的 outcome 與 close regression tests 確認通過。

## 3. 保護確認、交易與更新邊界

- [x] 3.1 在 presentation 測試補上人工修改成果的求解前確認：拒絕時不建立 Dialog、不啟動求解且成果不變；同意或無人工修改時才繼續；執行對應 `tests/test_interface_presentation.py` 測試確認通過。
- [x] 3.2 檢查並視缺口擴充 `tests/test_waler_global_apply.py`，驗證全部 staging 成功後才 commit、commit failure 完整 rollback，以及不相關成果不被覆蓋；執行該測試檔確認通過。
- [x] 3.3 驗證 commit 成功後仍沿用成果樹、材料統計與預覽更新流程，且 UI refresh failure 不回滾已採用成果；執行 apply 與 presentation 指定測試確認通過。
- [x] 3.4 確認修改範圍未進入 Global DP、objective、candidate generation、單支 Waler Solver、Inventory、material rules 或 Project schema；執行既有 Global Waler solver/application regression tests 確認演算法輸出契約不變。

## 4. 文件與完整驗證

- [x] 4.1 更新 `docs/WORKFLOW.md` 的 Global Waler 流程與成果生命週期，改為合法解自動 atomic commit，移除仍描述人工 Apply 的舊流程；以文字搜尋確認沒有互相矛盾的現行流程描述。
- [x] 4.2 執行聚焦測試：`python -m unittest tests.test_waler_global_reliability tests.test_waler_global_apply tests.test_interface_presentation tests.test_optimize_waler_global tests.test_waler_global -v`，確認全部通過。
- [x] 4.3 執行完整 test suite 與架構 boundary tests，確認沒有既有功能回歸，並記錄實際通過數與任何既知限制。
- [x] 4.4 執行 `openspec validate global-waler-auto-apply --strict`，確認 proposal、design、spec 與 tasks 結構及情境全部通過驗證。
