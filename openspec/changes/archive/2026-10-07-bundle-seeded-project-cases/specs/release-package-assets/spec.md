# Spec Delta：正式發行包預置兩個 Project 案例

## 閱讀導航

- **必讀**：「正式發行包提供兩個 Project 案例」；定義兩個案例的名稱、初始檔案集合、清單呈現與 `.bak` 排除。
- **必讀**：「正式發行包只預置核准 Project 與 runtime 資產」與「正式 Project 素材來源必須可重現」；定義 release 邊界與 build failure semantics。
- **條件式閱讀**：「Runtime Project 目錄可由正式案例建立或按需建立」；修改首次啟動、repository 建立或 Project 儲存時必讀。
- **條件式閱讀**：「Repository 只保留正式發行 Project 素材而不保留 regression Project case」；調整 fixture、`.gitignore` 或 asset ownership 時必讀。
- **可先跳過**：三份 DXF 使用者素材 Requirement、軟體資訊歷程細節、Project schema、Solver、Domain 與 DXF recognition；本 change 不修改那些規則。

## ADDED Requirements

### Requirement: 正式發行包提供兩個 Project 案例

乾淨正式 build output SHALL 在可寫的 `project_cases/` repository 中直接包含且僅預置下列兩個 managed Project，目錄名稱 MUST 保持不變：

- `Y05車站第一層支撐`
- `Y29車站第一層支撐`

每個預置 Project 初始內容 SHALL 恰好包含正式 `project.json` 與 `source/source.dxf`；MUST NOT 包含 `project.json.bak`、temporary、rollback、捷徑、placeholder 或其他副本。兩個 `project.json` 與 managed DXF MUST 通過現行 Project load／schema／DXF asset validation，且使用者 SHALL 能透過既有 Project repository selection 開啟它們。

本 Requirement 是 release／workflow contract，不新增 Engineering Hard Constraint、Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 首次開啟正式包的 Project 清單

- **WHEN** 使用者首次啟動未另行建立 Project 的乾淨正式發行版本
- **THEN** Project repository SHALL 列出 `Y05車站第一層支撐` 與 `Y29車站第一層支撐`
- **AND** 使用者 SHALL 能以既有 Open 流程載入任一案例
- **AND** `sample_dxf/` 內素材或其他 release resource MUST NOT 被列為 Project

#### Scenario: 檢查預置案例的初始 layout

- **WHEN** 正式 build 成功完成且尚未由使用者啟動或修改
- **THEN** 每個指定案例 SHALL 具有可驗證的 `project.json` 與 `source/source.dxf`
- **AND** `project_cases/` MUST NOT 預置任何其他 Project 或案例內其他檔案
- **AND** package MUST NOT 包含任一 `project.json.bak`

#### Scenario: 使用者儲存預置案例

- **WHEN** 使用者開啟、修改並儲存任一預置案例
- **THEN** 系統 SHALL 沿用一般 Project 的既有 Save transaction 與 `.bak` 建立行為
- **AND** 預置案例 MUST NOT 因其 release 來源而成為唯讀或使用不同 persistence schema

#### Scenario: 使用者刪除預置案例

- **WHEN** 使用者依既有 Project 刪除流程確認刪除任一預置案例
- **THEN** 系統 SHALL 將其視為一般 managed Project 完成刪除
- **AND** 系統 MUST NOT 在同一次執行或下次啟動時自動補回該案例

### Requirement: 正式 Project 素材來源必須可重現

兩個預置 Project 的正式 build source SHALL 是 repository 中 tracked、獨立於可變動 runtime `project_cases/` 的 release asset 快照。Build SHALL 以明確 allowlist 複製每個案例的 `project.json` 與 `source/source.dxf`，MUST NOT 以整包目錄複製而將日後新增檔案自動納入 release。

#### Scenario: 從乾淨 checkout 建立正式包

- **WHEN** build workspace 只包含 tracked files 且不含 runtime `project_cases/`
- **THEN** build SHALL 仍能產生包含兩個指定案例的正式包
- **AND** output 內容 SHALL 與核准 release asset allowlist 一致

#### Scenario: 指定 Project 素材缺少或無效

- **WHEN** 任一 allowlisted `project.json` 或 `source/source.dxf` 缺少、無法讀取或不符合現行 load validation
- **THEN** build 或 release verification SHALL 失敗並指出案例及失敗檔案
- **AND** MUST NOT 將缺件或無效成品視為成功的正式包

#### Scenario: Release asset 來源含有備份或額外檔案

- **WHEN** 檢查兩個正式 Project 素材來源
- **THEN** 每個來源案例 SHALL 恰好包含 `project.json` 與 `source/source.dxf`
- **AND** 任一 `.bak`、temporary、rollback 或額外 Project 檔案 SHALL 使 allowlist verification 失敗

## MODIFIED Requirements

### Requirement: 正式發行包只預置核准 Project 與 runtime 資產

正式 build output SHALL NOT 預置任何未核准 Project payload，也 SHALL NOT 包含 regression-only fixture directory。Release resource list MUST 只包含應用程式 runtime 必要資產、軟體資訊視窗所需的「起始歷史紀錄」精確投影、「三份 DXF 使用者素材」Requirement 指定的檔案，以及「正式發行包提供兩個 Project 案例」Requirement 指定的兩個 Project。該歷程 resource SHALL 完整對應 `docs/DEVELOPMENT_HISTORY.md` 的「起始歷史紀錄（截至 2026/09/28 早上）」表格，且 MUST NOT 包含其他 Project payload、regression fixture、OpenSpec artifact 集合、完整 `docs/DEVELOPMENT_HISTORY.md` 或其他 repository 文件樹。

#### Scenario: 檢查乾淨 checkout 的正式 build output

- **WHEN** 從只含 tracked files 的乾淨 checkout 建立正式發行包
- **THEN** package SHALL 只在 `project_cases/` 預置兩個指定案例，且不含 `tests/fixtures/`、`test_cases/` 或其他 Project
- **AND** package SHALL 保留應用程式啟動、inventory、圖片、DXF symbol、CAD bridge、軟體資訊視窗的起始歷史紀錄投影與三份指定使用者素材

#### Scenario: 首次開啟 Project 清單

- **WHEN** 使用者首次啟動尚未另行建立 Project 的正式發行版本
- **THEN** Project 清單 SHALL 只包含兩個指定預置案例
- **AND** SHALL NOT 將 `sample_dxf/` 內素材或起始歷史紀錄 resource 顯示為已建立 Project

#### Scenario: 正式發行包可離線顯示起始歷史紀錄

- **WHEN** 使用者從正式 build output 在沒有 repository 與網路連線的環境開啟軟體資訊
- **THEN** package SHALL 提供顯示完整起始歷史紀錄所需的 runtime resource
- **AND** 該 resource SHALL NOT 要求存取 `openspec/changes/` 或外部服務

#### Scenario: 正式發行包排除其他歷程區段

- **WHEN** 檢查軟體資訊視窗使用的 release history resource
- **THEN** resource SHALL 逐筆對應「起始歷史紀錄」的日期與紀錄文字及原始順序
- **AND** MUST NOT 包含「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或「AI 對話統計」區段

### Requirement: Runtime Project 目錄可由正式案例建立或按需建立

正式 build SHALL 由 tracked release asset 快照建立含兩個指定案例的 runtime `project_cases/`。若 source run、測試環境或其他合法部署沒有任何預置案例且 runtime Project 路徑不存在，應用程式 SHALL 仍沿用既有行為建立可寫目錄；系統 MUST NOT 依賴空 `test_cases/`、未追蹤的 runtime seed 或 regression fixture 才能啟動。

#### Scenario: 正式包建立預置 Project repository

- **WHEN** 從乾淨 checkout 建立正式 onedir 成品
- **THEN** output `project_cases/` SHALL 由兩個指定 release asset 快照建立
- **AND** SHALL NOT 從 build workspace 的 runtime `project_cases/` 複製使用者資料

#### Scenario: Runtime Project 目錄不存在

- **WHEN** source run、測試環境或合法部署的 runtime Project 目錄尚不存在
- **THEN** 系統 SHALL 建立該目錄
- **AND** 使用者 SHALL 能依既有流程建立與儲存 Project

#### Scenario: Clean checkout 沒有空資料夾

- **WHEN** build workspace 沒有 Git 無法追蹤的空 `test_cases/` 或 runtime `project_cases/`
- **THEN** build SHALL 從 tracked release assets 解析兩個指定案例並成功建立 output
- **AND** SHALL NOT 為了完成 build 而讀取或建立 repository root 的 runtime Project seed

### Requirement: Repository 只保留正式發行 Project 素材而不保留 regression Project case

Repository SHALL 僅在正式 release asset 位置保留兩個指定 Project 的 tracked `project.json` 與 managed `source/source.dxf`。Repository root 的 runtime `project_cases/` SHALL 維持不追蹤；automated tests MUST NOT 將正式 Project 素材複製到 `tests/fixtures/` 或重新建立第二份 Project case。其他 regression tests MUST 程式化建立所需 Project state，或直接使用既有正式 release assets；既有 assertions MUST 保留。非 Project 的 regression-only JSON MAY 位於 `tests/fixtures/` 下依 owner 分類，但 MUST 有直接 test consumer。

#### Scenario: 正式 Project 素材同時作為 release verification input

- **WHEN** automated tests 驗證 Y05 或 Y29 預置 Project 的 schema、managed DXF 或 package layout
- **THEN** tests SHALL 使用正式 Project release asset source
- **AND** SHALL NOT 在 runtime `project_cases/` 或 `tests/fixtures/` 建立 tracked 副本

#### Scenario: 正式素材同時作為 regression input

- **WHEN** automated tests 驗證 Y29、Y1A 或 Y05 DXF 使用者素材的既有工程行為
- **THEN** tests SHALL 使用正式 DXF 素材的 repository source
- **AND** SHALL NOT 在 `tests/fixtures/` 建立相同 DXF 副本

#### Scenario: 移除既有 Project fixture

- **WHEN** automated test 需要不屬於兩個正式預置案例的 Project state
- **THEN** test SHALL 程式化建立等價輸入
- **AND** repository SHALL NOT 在 `tests/fixtures/` 或其他位置保留額外 Project case 副本
- **AND** 改寫 SHALL 保留原有 assertions，不得刪除測試、降低 assertion 或新增 skip

#### Scenario: 非 Project automated fixture 搬移

- **WHEN** automated test 需要 CAD event 等不屬於 Project case 或正式素材的 regression-only JSON
- **THEN** test SHALL 從 `tests/fixtures/` 的具名 owner path 載入資料
- **AND** fixture SHALL 有直接 automated consumer 且不得進入正式 release

## RENAMED Requirements

- FROM: `### Requirement: 正式發行包不預置 Project 或測試資料`
- TO: `### Requirement: 正式發行包只預置核准 Project 與 runtime 資產`
- FROM: `### Requirement: Runtime Project 目錄不依賴 build seed`
- TO: `### Requirement: Runtime Project 目錄可由正式案例建立或按需建立`
- FROM: `### Requirement: Regression tests 不保留 Project case`
- TO: `### Requirement: Repository 只保留正式發行 Project 素材而不保留 regression Project case`
