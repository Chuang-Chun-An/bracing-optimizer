# Tasks

## 1. 建立 Project lifecycle characterization 基線

- [x] 1.1 新增 `tests/test_project_navigation_guard.py` 的最小 Main 測試 fixture，可保留並比較 Project object、`ProjectResultModel`、dirty flag/reason、current path 與代表性 UI selection，並以 continuation spy 驗證 New reset／Open load 是否被呼叫；執行 fixture smoke tests 確認可觀察現有 state boundary。
- [x] 1.2 補上現行 Save／Save As characterization tests，確認已有路徑會呼叫 `save_project_case()`、未命名 Project 會進入 Save As、成功後才清除 dirty，而取消或 persistence exception 不會清除目前 state；執行相關指定測試確認通過。
- [x] 1.3 補上現行 Open hydrate-before-adopt、New reset 與 manual-edit immediate commit 的 characterization assertions，確認 committed results 在 navigation continuation 前仍由 `ProjectResultModel` 擁有；執行 navigation、persistence 與 manual-edit 指定測試確認通過。

## 2. 建立明確的儲存結果契約

- [x] 2.1 在 presentation 範圍新增小型 save outcome／navigation decision types，明確表示 `saved`、`cancelled`、`failed` 與 `proceed`／`cancelled`，並以單元測試確認呼叫端不需依賴 `Path | None` 或 truthy／falsy。
- [x] 2.2 重構既有 Save As orchestration，使取消名稱、無效名稱、拒絕覆蓋回傳 `cancelled`，Application persistence 成功回傳 `saved`，已顯示錯誤的 persistence failure 回傳 `failed`；執行 Save As outcome tests 確認三種結果與 state preservation。
- [x] 2.3 重構既有 Save orchestration，使已有路徑沿用 `save_project_case()`、未命名 Project 沿用同一 Save As 實作，並視現有 extension contract 保留薄的 legacy projection；執行路由、成功與失敗測試確認沒有第二套 persistence。
- [x] 2.4 更新 Close 對新 save outcome 的 consumption，但不改變現有 Save／Discard／Cancel 與 shutdown cleanup 行為；補上 Close saved/cancelled/failed regression tests 並確認只有 `saved` 或既有 Discard 才會 destroy Main window。

## 3. 實作共用 New／Open navigation guard

- [x] 3.1 在 Main 實作單一 decision-only dirty navigation guard，使用既有 tri-state dialog 將 Save／Discard／Cancel 映射成具名結果；以 table-driven tests 驗證 clean bypass、Save outcomes、Discard 與 Cancel 的 `proceed`／`cancelled` 結果。
- [x] 3.2 將現有 New reset body保留在可觀察的 destination-specific continuation，讓 `_new_project()` 只在 guard 回傳 `proceed` 後呼叫一次；測試 clean、已有路徑 Save success、未命名 Save As success、Discard、Cancel、Save As cancel 與 save failure。
- [x] 3.3 更新 `_load_selected_project_case()`，維持先驗證現有 project-case selection、再執行共用 guard、最後才呼叫 `load_project_case()`；測試 clean、已有路徑 Save success、未命名 Save As success、Discard、Cancel、Save As cancel、save failure 與沒有有效選取目標。
- [x] 3.4 對 New／Open 的 cancelled 與 failed 路徑做完整 snapshot assertions，確認 Project object、dirty state/reason、current path、committed results、DXF/session state 與 UI selection 不變，且 destructive continuation 呼叫次數為零。
- [x] 3.5 新增共用語意 regression test，對相同 dirty state、使用者選擇與 save outcome 驗證 New／Open 得到相同 guard 結果；另驗證 Save 尚未回報 `saved` 前不會先呼叫任何 destination continuation。

## 4. 文件與整體驗證

- [x] 4.1 在實作與 focused tests 通過後更新 `docs/WORKFLOW.md`，將 New／Open 的 current behavior 改為 Save／Discard／Cancel、補上明確 save outcome 與 destructive ordering，並移除對應 Product Gap；以文字搜尋確認沒有互相矛盾的現行流程描述。
- [x] 4.2 執行聚焦測試，至少包含 project navigation guard、project persistence、ProjectService、Main project editing、manual result editing 與 interface presentation 測試，確認全部通過且沒有降低既有 assertions。
- [x] 4.3 執行完整 test suite 與 architecture boundary tests，確認沒有 Solver、Domain、DXF、persistence schema 或其他 Main UI 回歸，並記錄實際通過數與任何既知限制。
- [x] 4.4 執行 `openspec validate add-save-option-to-unsaved-changes-prompt --strict` 並依 OpenSpec verify workflow 對照 proposal、spec、design、tasks 與實作，確認所有 scenarios、文件及測試證據完整後才標記完成。
