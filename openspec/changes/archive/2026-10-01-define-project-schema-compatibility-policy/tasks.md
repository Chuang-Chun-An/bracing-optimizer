# Tasks

## 實作前閱讀

- **Group 1 開始前**：讀 `proposal.md`「主要流程／不變事項」、`design.md` Decision 1～4，以及 spec Requirements「schema_version 必須是有效整數」與「以版本上限與現行結構共同判斷是否可載入」。
- **Group 2 開始前**：讀 `design.md` Decision 5、Backward Compatibility / Persistence Impact，以及 spec 的 invalid-version、missing、older、current、future、old-structure 全部 Scenarios 與 Requirement「成功儲存一律寫入現行版本」。
- **Group 3 開始前**：讀 `proposal.md` Impact、`design.md` Architecture Alignment，以及 spec Requirement「拒絕時提供可行的下一步並保留目前狀態」。
- Solver、DXF recognition、案例 JSON 與 export 相關文件本次可先跳過；若實作必須觸碰這些模組，先停止並確認是否超出 scope。

## 1. 建立 Load Compatibility Boundary

- [x] 1.1 在 `bracing_optimizer/infrastructure/project_persistence.py` 為 `ProjectSerializer` 加入 load-oriented compatibility validation：先以欄位存在性區分 missing，欄位存在時只接受排除 bool、且 `>= 1` 的真正整數，再分類 older／current／future；future 先拒絕，missing／older／current 共用既有 current structure validation。以 `tests/test_project_persistence.py` 的 focused tests 驗證判斷順序且沒有複製 schema 3 欄位規則。
- [x] 1.2 在 `bracing_optimizer/application/project_service.py` 將正式 load path 接到新的 compatibility boundary，維持 hydrate/adopt 順序且不正規化或寫回來源 payload；以 `tests/test_project_service.py` 驗證 missing／older 載入成功後回傳版本標籤狀態不被 load 改寫。
- [x] 1.3 沿用 `ProjectPersistenceError(stage, detail)` 完成 future、無法以現行格式讀取、invalid-current 三種可辨識錯誤語意，並為結構失敗保留底層 validation detail；以 service/persistence focused assertions 透過 `stage` 或固定關鍵字區分三類，不比對完整訊息文字。

## 2. 鎖定相容與儲存行為

- [x] 2.1 在 `tests/test_project_service.py`／`tests/test_project_persistence.py` 補齊 `"3"`、`3.0`、`true`、`false`、`null`、`0`、`-1` 的拒絕測試，以及 missing、older、current、future、old-structure 五類矩陣；以 `.\.venv\Scripts\python.exe -m unittest tests.test_project_service tests.test_project_persistence` 驗證：只有欄位不存在走 missing，前三類相容版本依現行結構判斷，future 無條件拒絕，old-structure 不偵測特徵或轉換，且回報中性訊息與底層錯誤。
- [x] 2.2 補上「僅 load／close 不覆寫來源」及 missing／older 相容檔案下一次成功儲存必為 `schema_version: 3` 的 regression tests；測試 MUST 實際呼叫正式儲存流程並重新讀取磁碟檔案驗證，不得依賴 dirty state 代替 Save，最後以上述 focused unittest command 確認輸出通過現行 validator。
- [x] 2.3 檢查 `tests/test_project_navigation_guard.py` 的既有 load-failure coverage；若尚未直接涵蓋 schema compatibility failure，補最小測試證明 input、result、DXF/path 與 dirty state 不被部分採用，並執行 `.\.venv\Scripts\python.exe -m unittest tests.test_project_navigation_guard`。

## 3. 文件、回歸與 OpenSpec 驗證

- [x] 3.1 更新 `README.md`「專案 JSON 與 DXF 資產」，清楚區分舊版本號與無法通過現行格式驗證，列出 invalid-version／future rejection、中性錯誤與離線 upgrade 流程，並明寫「相容檔案只有在使用者實際儲存時才改寫為 schema 3；僅開啟或關閉不會改寫來源檔」；同時檢查 `docs/WORKFLOW.md` 的 Open Project long-term truth，若實作後內容不足則同步更新，並以 `rg` 確認不再保留「Application 只接受 schema 3」的衝突敘述。
- [x] 3.2 執行 focused project regression：`.\.venv\Scripts\python.exe -m unittest tests.test_project_persistence tests.test_project_service tests.test_project_navigation_guard tests.test_project_domain`；所有測試通過，且既有離線 `upgrade_payload()` 測試仍證明 migration 未移入 load path。
- [x] 3.3 依實際影響範圍執行 project/presentation boundary regression（至少 `.\.venv\Scripts\python.exe -m unittest tests.test_interface_presentation tests.test_project_validation`），確認沒有把 schema policy 複製到 UI 或破壞架構邊界。
- [x] 3.4 執行 `openspec validate define-project-schema-compatibility-policy --strict` 並使用 `$openspec-verify-change` 對照 proposal、design、spec 與 tasks；確認指定非正常版本值、五類相容 Scenario、actual-save-as-schema-3、錯誤提示與 state preservation 都有實作及測試證據。
