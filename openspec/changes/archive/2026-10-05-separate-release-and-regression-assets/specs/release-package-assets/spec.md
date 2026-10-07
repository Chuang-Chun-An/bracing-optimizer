# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：四個 Requirements 全部；它們分別規範正式發行邊界、三份使用者素材、runtime Project 目錄與 Project case／非 Project fixture 歸屬。
- **實作前閱讀（P1）**：`../../design.md` 的 D1～D4，取得 `sample_dxf/` allowlist、source ownership、Project case 移除方式與非 Project fixture 分類方式。
- **條件式閱讀（P2）**：只有改寫既有 Project-fixture consumers 時才讀 Project schema specs；只有更新素材 consumers 時才讀對應 DXF recognition／review tests。
- **可以先跳過**：Solver、Domain 與 DXF recognition capability specs；本 change 不修改其行為。

## Purpose

定義正式發行包、可交付 DXF 使用者素材與開發回歸資料的可驗證邊界，使成品不附任何 Project、repository 不保留 Project case，並固定提供三份 DXF 素材。

## ADDED Requirements

### Requirement: 正式發行包不預置 Project 或測試資料

正式 build output SHALL NOT 預置任何示範、歷史、測試或其他 Project payload，也 SHALL NOT 包含 regression-only fixture directory。Release resource list MUST 只包含應用程式 runtime 必要資產與「三份 DXF 使用者素材」Requirement 指定的檔案。

#### Scenario: 檢查乾淨 checkout 的正式 build output

- **WHEN** 從只含 tracked files 的乾淨 checkout 建立正式發行包
- **THEN** package SHALL 不含預置 Project、`project_cases/`、`tests/fixtures/` 或 `test_cases/`
- **AND** package SHALL 保留應用程式啟動、inventory、圖片、DXF symbol、CAD bridge 與三份指定使用者素材

#### Scenario: 首次開啟 Project 清單

- **WHEN** 使用者首次啟動尚未建立任何 Project 的正式發行版本
- **THEN** Project 清單 SHALL 為空
- **AND** SHALL NOT 將 `sample_dxf/` 內的素材顯示為已建立 Project

### Requirement: 正式發行包提供三份 DXF 使用者素材

正式 build output SHALL 在 `sample_dxf/` 直接包含且僅包含下列三份 DXF，檔名 MUST 保持不變：

- `Y29_test.dxf`
- `Y1A擋土支撐簡化版.dxf`
- `670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf`

這三份檔案屬於正式 user materials，不得被歸類為 regression-only fixture；使用者 SHALL 能以既有 DXF 匯入流程自行選取它們。

#### Scenario: 檢查 sample_dxf 內容

- **WHEN** 正式 build 成功完成
- **THEN** `sample_dxf/` SHALL 存在且恰好包含上述三個檔名
- **AND** 三份檔案 SHALL 可作為 DXF 開啟，不得是 placeholder、捷徑或缺漏副本

#### Scenario: 指定素材來源缺少

- **WHEN** build workspace 缺少任一 allowlisted DXF source
- **THEN** build SHALL 失敗並指出缺少的素材
- **AND** SHALL NOT 產生被視為成功的缺件正式包

### Requirement: Runtime Project 目錄不依賴 build seed

應用程式 SHALL 在既有 runtime Project 路徑不存在時建立可寫目錄；build SHALL NOT 以複製 repository `project_cases/`、空 `test_cases/` 或其他 seed directory 來滿足此行為。

#### Scenario: Runtime Project 目錄不存在

- **WHEN** 應用程式啟動或第一次列舉 Project 時 runtime Project 目錄尚不存在
- **THEN** 系統 SHALL 建立該目錄
- **AND** 使用者 SHALL 能依既有流程建立與儲存 Project

#### Scenario: Clean checkout 沒有空資料夾

- **WHEN** build workspace 沒有 Git 無法追蹤的空 `test_cases/` 或 `project_cases/`
- **THEN** build SHALL 成功解析所有宣告的輸入
- **AND** SHALL NOT 為了完成 build 而建立或複製 Project seed 目錄

### Requirement: Regression tests 不保留 Project case

Repository SHALL NOT 保留任何 tracked Project case、Project JSON 或 Project-managed source 副本。原本依賴這些檔案的 automated tests MUST 改為程式化建立所需 Project state，或直接使用三份正式 DXF 使用者素材；既有 assertions MUST 保留。非 Project 的 regression-only JSON MAY 位於 `tests/fixtures/` 下依 owner 分類，但 MUST 有直接 test consumer。

#### Scenario: 正式素材同時作為 regression input

- **WHEN** automated tests 驗證 Y29、Y1A 或 Y05 使用者素材的既有工程行為
- **THEN** tests SHALL 使用正式素材的 repository source
- **AND** SHALL NOT 在 `tests/fixtures/` 建立相同 DXF 副本

#### Scenario: 移除既有 Project fixture

- **WHEN** 既有 automated test 原先從 `project_cases/` 載入 Project JSON 或 managed source
- **THEN** test SHALL 改為程式化建立等價輸入，或直接使用三份正式 DXF 使用者素材
- **AND** repository SHALL NOT 在 `tests/fixtures/` 或其他位置保留該 Project case 的副本
- **AND** 改寫 SHALL 保留原有 assertions，不得刪除測試、降低 assertion 或新增 skip

#### Scenario: 非 Project automated fixture 搬移

- **WHEN** 既有 automated test 需要 CAD event 等不屬於 Project case 或三份正式素材的 regression-only JSON
- **THEN** test SHALL 從 `tests/fixtures/` 的具名 owner path 載入資料
- **AND** fixture SHALL 有直接 automated consumer 且不得進入正式 release
