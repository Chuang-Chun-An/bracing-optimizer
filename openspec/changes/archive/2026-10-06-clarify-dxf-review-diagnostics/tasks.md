# Tasks

## 實作前閱讀

- **Group 1 前**：閱讀 `proposal.md`「In Scope／Out of Scope」、delta spec「DXF Review 診斷須使用白話中文」，以及 `design.md` Decision 1～3 的 88-code inventory 與固定分類；先建立顯示 contract、分類完整性與 fallback A 測試。
- **Group 2 前**：閱讀 delta spec「白話顯示不得改變診斷真相」與 `design.md` Decision 2、4；確認 `ProblemRecord` 是共享投影、Dialog 不自行判斷。
- **Group 3 前**：閱讀 main spec「問題說明須使用可在清單定位的代號」與 `design.md`「驗證策略」；保留正式 ID、來源 handle、severity、code 與 blocking behavior。
- **Group 4 前**：回看 `proposal.md`「不變事項」、`design.md`「Architecture Alignment／相容性與 persistence」，以及兩個 delta requirements；確認未擴大到 recognition、Solver、Project schema 或全應用訊息整理。

## 1. 建立診斷顯示 contract

- [x] 1.1 在 `tests/test_dxf_review_items.py` 新增 `ProblemRecord` 顯示投影測試，覆蓋中文類型、原始 `code` 保留、severity／role／source handles／member IDs 不變，並執行該 test module 確認新測試能精確描述 spec 行為。
- [x] 1.2 在 `tests/test_dxf_review_items.py` 建立 producer code inventory 與分類完整性測試：盤點直接 `ValidationMessage` code、間接 recognition outcome code 及 `importer.py` 的 role 動態展開，斷言所有 88 個已知 code 恰好屬於保留原文、專用 formatter、已知 fallback 三類之一，三集合互斥；加入未分類 code fixture，驗證新增 producer code 而未分類時測試失敗。
- [x] 1.3 在 `tests/test_dxf_review_items.py` 新增含 `provisional`／`identity`／`baseline`／`staged finalization` 的專用 formatter 案例，以及已知／未知 code 的 fallback A 測試；驗證 fallback 僅顯示通用說明、構件 ID 與來源 handle，不含原始 message、raw code、reason token、exception representation 或 traceback，且診斷仍保留一筆 record。
- [x] 1.4 為保留原文與專用 formatter code 的正式構件 ID、來源 handle、數值與單位補上白話投影 regression cases，並執行 targeted tests 確認既有 `_format_problem_description()` 定位規則未被覆蓋或誤改；fallback 只驗證構件 ID 與來源 handle。

## 2. 實作共享白話投影

- [x] 2.1 在 `dxf_import/models.py` 與 `dxf_import/validation.py` 建立非持久化的中文問題類型，以及 Decision 3 固定的保留原文、專用 formatter、已知 fallback 三分類；移除任何依 message 內容或語言判斷分類的執行時分支，保留 `ProblemRecord.code` 為診斷 identity，並以 Group 1 tests 驗證分類完整性與 structured fields 不變。
- [x] 2.2 在 `dxf_import/validation.py` 依 Design 清單實作 23 個專用 formatter，整理辨識、端點連接、構件關聯、圍令重疊、圍令接觸與人工修正用語；只允許 code-specific、具測試的穩定資料擷取，不得以全域 regex 猜測任意 exception 文字，並驗證需保留的量測值與定位資訊。
- [x] 2.3 實作 fallback A：已知 fallback 與未來未知 code 均以 `role + severity` 形成通用中文類型，只顯示通用說明、構件 ID、來源 handle 與安全建議，不附原始 message；執行 Group 1 fallback tests。
- [x] 2.4 更新 `review_item_guidance()` 的使用者用語，移除 `active sources` 等內部詞彙，保留 unresolved、來源重疊及各 role 目前確實存在的操作限制；執行 guidance tests 確認不推薦特定來源 winner 或不存在的工具。
- [x] 2.5 更新 `dxf_import/dialog.py`，讓全部問題清單與選取項目明細都顯示同一份中文類型與 description，而不是直接顯示 `record.code`；不得新增查看 raw code 的 UI 入口，並執行 `tests/test_dxf_review_layout.py` 與相關 rendering tests，確認兩處文案一致且點選定位仍使用 structured identity。

## 3. 保護診斷真相與工作流程

- [x] 3.1 在 `tests/test_dxf_review_items.py` 增加共享 rendering 與未知 fallback regression，驗證兩個問題區域的 type／description 相同、component／source 定位不變、fallback 不顯示原始 message，且 fallback 不成為新的 diagnostic identity。
- [x] 3.2 在 `tests/test_dxf_review_workflow.py` 補上 error／critical 與 warning 代表案例，驗證白話投影前後的排序、錯誤／警告數量、`can_import`／blocking truth、匯入按鈕前置狀態所依據的 structured diagnostics 均不變。
- [x] 3.3 執行 `tests/test_dxf_module_boundaries.py`，確認文案 catalog／formatter 未引入 Dialog、Tkinter、Project、Solver 或 persistence 反向依賴；若失敗，只修正本 change 新增的 dependency。

## 4. 整體驗證與 review

- [x] 4.1 執行 `.\.venv\Scripts\python.exe -m unittest tests.test_dxf_review_items tests.test_dxf_review_layout tests.test_dxf_review_workflow tests.test_dxf_module_boundaries -v`，修正本 change 引入的 focused regression，且不得降低既有 assertions。
- [x] 4.2 執行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_dxf*.py" -v`，確認 DXF Review、recognition、repair 與 result projection regression 全部通過。
- [x] 4.3 以至少一組辨識失敗、一組圍令重疊／接觸、一組構件關聯及一組未知 code fixture 檢查最終可見文案，確認「問題類型 → 發生什麼事 → 處理建議」可直接讀懂；保留原文與 formatter 案例須保留正式 ID、來源 handle 與量測值，fallback 案例只顯示通用說明、構件 ID 與來源 handle；將結果記錄於 implementation verification。
- [x] 4.4 執行 `openspec validate clarify-dxf-review-diagnostics --strict` 並使用 `$openspec-verify-change` 對照 proposal scope、兩個 delta requirements、design decisions 與本 tasks；確認沒有 code／test／文件偏離後，才將 change 交付 review。
