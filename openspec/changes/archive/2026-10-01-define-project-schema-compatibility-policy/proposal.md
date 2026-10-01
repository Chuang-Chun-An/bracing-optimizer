# Project Schema 相容政策提案

## 閱讀導航

- **P0／現在必讀**
  - 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
  - `specs/project-schema-compatibility/spec.md` 的 Requirement「以版本上限與現行結構共同判斷是否可載入」與五類相容 Scenario。
  - `design.md` 的「Decision 1：先驗證版本型別與範圍，再將版本標籤與資料結構分開判斷」。
- **P1／實作前閱讀**
  - `design.md` 的其餘 Decisions、failure semantics 與測試矩陣。
  - `tasks.md` 的實作順序與驗證項目。
  - `README.md`「11.5 專案 JSON 與 DXF 資產」、`docs/WORKFLOW.md`「4.2 Open Project」。
- **P2／需要時再讀**
  - `docs/ARCHITECTURE.md`「Major Components and Ownership」與 Project persistence flow，用於確認責任邊界。
  - `tools/upgrade_project_schema.py`，只在依中性提示處理可能的舊版專案時閱讀。
- **本次可先跳過**
  - Solver、DXF recognition 與 export 相關 specs；本 change 不改搜尋、工程規則、DXF lifecycle 或輸出格式。

## 快速摘要

- README 宣稱只接受 schema 3，但目前載入程式與測試允許「結構已是現行格式、版本號為 2 或缺少」的檔案，三者政策不一致。
- 本 change 將「版本標籤較舊」與「無法以現行格式讀取」明確分開：前者可相容開啟；後者回報「無法以現行格式讀取；若為舊版專案，請先執行升級工具」及底層驗證錯誤，不在載入時偵測舊格式特徵或猜測轉換。
- 新存檔與相容檔案的再次儲存一律輸出 schema 3；schema 3 仍執行完整現行結構與 Domain 驗證。
- 高於目前支援版本的檔案拒絕開啟，並明確提示需使用較新程式；無法通過現行結構驗證的檔案則回報「無法以現行格式讀取；若為舊版專案，請先執行升級工具」及底層驗證錯誤。
- 不改 schema 3 的欄位定義、升級工具的轉換責任、Solver 或 DXF lifecycle。

## 現況與目標

此處的「版本標籤」指 `schema_version` 欄位；「資料結構」指 `input_data`、`dxf_asset` 等現行 schema 3 所要求的實際內容。

| 面向 | Before（現況） | After（目標） |
| --- | --- | --- |
| 政策來源 | README、程式與測試對舊版本號的說法不一致 | Spec 成為單一相容政策，README、程式與測試一致 |
| 缺少／較舊版本號 | 現行程式因只驗結構而可開啟，但未明確定義 | 內容符合現行結構即可開啟 |
| 現行版本 | 驗證現行結構 | 維持完整驗證 |
| 未來版本 | 未明確拒絕，可能被當成現行結構載入 | 拒絕開啟，提示使用較新程式 |
| 結構驗證失敗 | 與版本相容政策未清楚區分 | 不偵測舊格式特徵、不自動猜測轉換；回報中性提示與底層驗證錯誤 |
| 再次儲存 | Persistence 寫入 schema 3，但相容意義未文件化 | 明定所有成功新存／再存檔案都寫 schema 3 |

## 主要流程

1. 讀取 Project JSON；只有欄位不存在才分類為 missing。欄位存在時先驗證它是排除 bool 的真正整數且至少為 `1`，否則以格式錯誤拒絕載入。
2. 對合法版本值辨識是較舊、現行或未來版本；若是未來版本，立即拒絕並提示需使用支援該版本的較新程式。
3. 若是 missing、較舊或現行版本，使用同一套現行 schema 3 結構與 Domain 規則驗證內容。
4. 驗證成功即可開啟；驗證失敗時拒絕載入，回報「無法以現行格式讀取；若為舊版專案，請先執行升級工具」並附上底層驗證錯誤；載入流程不偵測舊格式特徵，也不猜測轉換。
5. 已開啟的相容檔案在下一次儲存時，由既有 save boundary 寫成 schema 3。

## 不變事項

- schema 3 的欄位、Domain row 約束、`dxf_asset` 契約與交易式儲存順序不變。
- `tools/upgrade_project_schema.py` 仍是明確、離線的舊結構升級入口；載入流程不接管其轉換工作。
- Open failure 仍不得採用部分 Project state；目前 Project、results 與 dirty state 保持不變。
- 不修改 Architecture layer、Domain 工程規則、Solver 行為或 DXF managed-copy lifecycle。

## Why

目前 README 宣稱 Application 只接受 schema 3，程式與測試卻已允許結構符合現行格式但版本號較舊或缺少的檔案，且未來版本沒有明確防護。需要建立單一、可測試的相容政策，避免文件、實作與回歸測試繼續漂移。

## What Changes

- 定義 Project 載入的版本分類與結構驗證順序。
- `schema_version` 存在時只接受排除 bool、且大於等於 `1` 的真正整數；字串、浮點數、`null`、布林值、`0` 與負數均以格式錯誤拒絕。
- 允許版本號缺少或低於 3、但資料結構完整符合現行 schema 3 的檔案開啟。
- 維持 schema 3 的正常嚴格驗證，並規定所有成功儲存均輸出 `schema_version: 3`。
- 拒絕高於 3 的檔案，提供「需使用較新程式」的可辨識錯誤。
- 對無法通過現行結構驗證的檔案提供「無法以現行格式讀取；若為舊版專案，請先執行升級工具」及底層驗證錯誤；載入路徑不偵測舊格式特徵或自動轉換。
- 補齊 missing、older、current、future、old-structure 五類相容測試，並校正 README 說明。

## Scope

### In Scope

- Project JSON 的 load/save schema version policy。
- `ProjectService` 與 persistence validation boundary 的錯誤分類與訊息。
- 專案持久化／服務層的五類測試與 README 相容政策。

### Out of Scope

- 新增 schema 4 或修改 schema 3 欄位。
- 在載入期間執行 legacy migration、推測缺失欄位或修補舊資料。
- 擴充離線升級工具可轉換的舊格式範圍。
- 修改案例 JSON、DXF review state 子版本、Solver cache schema 或其他非 Project schema。

## Capabilities

### New Capabilities

- `project-schema-compatibility`: 定義 Project schema 的版本分類、現行結構驗證、拒絕／升級提示，以及再次儲存為 schema 3 的行為。

### Modified Capabilities

- 無。現有 capability inventory 尚未定義 Project schema 相容行為。

## Impact

- **預期程式範圍**：`bracing_optimizer/application/project_service.py`、`bracing_optimizer/infrastructure/project_persistence.py`，以及必要的 presentation error 顯示檢查。
- **預期測試範圍**：`tests/test_project_service.py`、`tests/test_project_persistence.py`；若 UI 需驗證訊息傳遞，再納入最接近的 navigation/presentation test。
- **文件**：校正 `README.md` 的 Project JSON 相容說明；不預先改寫尚未成立的 `docs/ARCHITECTURE.md` 或 `docs/WORKFLOW.md`。
- **Architecture／Domain／Solver／Workflow truth**：不改 Architecture、Domain 或 Solver；會明文化既有 Open workflow 的 schema compatibility truth，但不改其 transaction/rollback 模型。

## 尚未決定與重新評估條件

- 錯誤物件是否新增 machine-readable reason code，或先沿用 `ProjectPersistenceError` 的 stage/detail，由 design 與現有 UI 錯誤呈現契約決定；若 presentation 需要依類型採取不同動作，必須重新評估並補規格。
- 若實作時發現某個「版本號舊但現行結構」檔案仍依賴版本特定語意，而非單純標籤差異，應停止實作並回到本 proposal／spec 重新界定相容邊界。
