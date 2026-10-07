# Spec Delta

## 閱讀導航

- **必讀**：「正式發行包不預置 Project 或測試資料」；本 delta 只把 `docs/DEVELOPMENT_HISTORY.md` 的起始歷史紀錄精確投影加入合法且必要的 runtime resource。
- **條件式閱讀**：修改 `SupportSolver.spec` 或 package asset tests 時，連同主規格的「正式發行包提供三份 DXF 使用者素材」一起閱讀。
- **可先跳過**：Runtime Project 目錄與 regression fixture 搬移 scenarios；本 change 不修改那些既有行為。

## MODIFIED Requirements

### Requirement: 正式發行包不預置 Project 或測試資料

正式 build output SHALL NOT 預置任何示範、歷史、測試或其他 Project payload，也 SHALL NOT 包含 regression-only fixture directory。Release resource list MUST 只包含應用程式 runtime 必要資產、軟體資訊視窗所需的「起始歷史紀錄」精確投影，以及「三份 DXF 使用者素材」Requirement 指定的檔案。該歷程 resource SHALL 完整對應 `docs/DEVELOPMENT_HISTORY.md` 的「起始歷史紀錄（截至 2026/09/28 早上）」表格，且 MUST NOT 包含 Project payload、regression fixture、OpenSpec artifact 集合、完整 `docs/DEVELOPMENT_HISTORY.md` 或其他 repository 文件樹。

#### Scenario: 檢查乾淨 checkout 的正式 build output

- **WHEN** 從只含 tracked files 的乾淨 checkout 建立正式發行包
- **THEN** package SHALL 不含預置 Project、`project_cases/`、`tests/fixtures/` 或 `test_cases/`
- **AND** package SHALL 保留應用程式啟動、inventory、圖片、DXF symbol、CAD bridge、軟體資訊視窗的起始歷史紀錄投影與三份指定使用者素材

#### Scenario: 首次開啟 Project 清單

- **WHEN** 使用者首次啟動尚未建立任何 Project 的正式發行版本
- **THEN** Project 清單 SHALL 為空
- **AND** SHALL NOT 將 `sample_dxf/` 內的素材或起始歷史紀錄 resource 顯示為已建立 Project

#### Scenario: 正式發行包可離線顯示起始歷史紀錄

- **WHEN** 使用者從正式 build output 在沒有 repository 與網路連線的環境開啟軟體資訊
- **THEN** package SHALL 提供顯示完整起始歷史紀錄所需的 runtime resource
- **AND** 該 resource SHALL NOT 要求存取 `openspec/changes/` 或外部服務

#### Scenario: 正式發行包排除其他歷程區段

- **WHEN** 檢查軟體資訊視窗使用的 release history resource
- **THEN** resource SHALL 逐筆對應「起始歷史紀錄」的日期與紀錄文字及原始順序
- **AND** MUST NOT 包含「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或「AI 對話統計」區段

