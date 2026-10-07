# Tasks

## 實作前閱讀

- **第 1 組**：讀 proposal「主要流程」、spec 四個 Requirements 與 design D1／D4；先完成 file-level inventory 與 consumer mapping，不可直接刪檔。
- **第 2 組**：讀 spec「正式發行包提供三份 DXF 使用者素材」與 design D1，並盤點全部 Y05／Y1A／Y29 test consumers。
- **第 3 組**：讀 spec「正式發行包不預置 Project 或測試資料」與 design D1～D2，並對照 `SupportSolver.spec`、`tests/test_dxf_assets.py`。
- **第 4 組**：讀 spec「Runtime Project 目錄不依賴 build seed」與 design D3，並對照 `bootstrap.py`、`main.py` 的 `project_cases_dir` 建立點。
- **第 5 組**：讀 spec「Regression tests 不保留 Project case」、design D4 與第 1 組 inventory；三份 user materials 不進 fixture tree，Project cases 全部移除，只有非 Project data 可依 owner 搬移。
- **第 6～7 組**：讀 proposal「不變事項」與 design Risks，確認 package、targeted tests、完整 tests 與 OpenSpec validation 都有證據。

## 1. 建立 release asset 與 fixture ownership inventory

- [x] 1.1 盤點 `SupportSolver.spec`、三份指定 DXF、所有 tracked `project_cases/`／root-level JSON、`test_cases/` 狀態及其 test／tool consumers；將三份 DXF 標記為 user materials，逐項記錄 Project case 的移除對象與替代 consumer strategy，並以 `git ls-files` 與 scoped `rg` 驗證沒有漏項。
- [x] 1.2 建立 `tests/fixtures/README.md` ownership table，明確排除三份 user materials 與所有 Project cases，只記錄具有直接 automated consumer 的非 Project fixture；以 scoped `rg` 驗證每個列出的 fixture 都有 consumer。

## 2. 建立三份 DXF 使用者素材來源

- [x] 2.1 建立 `assets/sample_dxf/`，將 `Y29_test.dxf`、`Y1A擋土支撐簡化版.dxf`、`670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf` 移到該目錄且保持檔名不變；以 hash／DXF reader 驗證內容未改、三份都可開啟且 repository root 不再有重複副本。
- [x] 2.2 建立 test-side shared asset path module 指向 `assets/sample_dxf/`，更新 `test_double_support.py`、DXF recognition／review／layout tests 等全部 Y05／Y1A／Y29 consumers；執行受影響 targeted tests，驗證原 assertions 保留且未新增 skip。
- [x] 2.3 新增 source-layout contract test，驗證 `assets/sample_dxf/` 恰好有三個 allowlisted filenames、沒有第四份素材且 `tests/fixtures/` 沒有相同 DXF 副本；執行該 test 確認 single source of truth。

## 3. 收斂正式 package assets

- [x] 3.1 更新 `tests/test_dxf_assets.py` 的 build contract，明確檢查必要 `data/`、`picture/`、`assets/dxf/`、`cad_builder.lsp` 仍在 allowlist，三份素材逐檔對應成品 `sample_dxf/`，且 `project_cases/`、`test_cases/`、`tests/fixtures/` 不得成為 build input；執行該 test 驗證新 contract 能捕捉現況違規。
- [x] 3.2 修改 `SupportSolver.spec` 移除 `project_cases/`、`test_cases/` 與舊的單一 Y29 root copy，改為逐檔複製三份 allowlisted source 到 `sample_dxf/` 且缺檔直接失敗；重跑 `tests/test_dxf_assets.py`，驗證 contract、output name 與唯一 spec assertions 全部通過。

## 4. 固定 runtime Project boundary

- [x] 4.1 在 `tests/test_app_dependencies.py` 或最接近的 Project navigation test 補上「`project_cases_dir` 原先不存在」案例，驗證應用程式可建立空目錄並依既有流程保存 Project；只有測試揭露缺口時才最小修改 `main.py`／`bootstrap.py`，並重跑相關 Project tests。
- [x] 4.2 將 repository root `/project_cases/` 加入 `.gitignore`，並新增 source-layout assertion 驗證該路徑沒有 tracked fixtures；以 `git ls-files project_cases` 與 ignore check 確認本機 runtime data 不會再被當成產品或測試資產提交。

## 5. 移除 Project cases 並整理非 Project fixtures

- [x] 5.1 建立 `tests/fixtures/cad/`，移動 `cad_bridge_event_examples.json` 並更新 `tests/test_cad_builder_integration.py`；執行其 examples contract test，驗證事件種類與 payload assertions 完整保留。
- [x] 5.2 更新 `tests/test_dxf_saveas_minimal_repro.py` 直接使用 `assets/sample_dxf/Y1A擋土支撐簡化版.dxf`；更新 `tests/test_dxf_export_validation.py` 與 `tests/test_support_shim_fixture_regression.py`，利用既有 model／persistence API 在測試暫存目錄程式化建立最小 Project state，不讀取 repository Project JSON；執行三組 targeted tests，驗證原有 source hash、export validation 與工程 assertions 不變。
- [x] 5.3 刪除第 1 組 inventory 中全部 tracked `project_cases/` 內容，包括 Project JSON、`.bak` 與 managed `source/source.dxf`，且不搬到 `tests/fixtures/projects/`、`tests/fixtures/manual/` 或其他 repository 位置；以 `git ls-files project_cases`、Project JSON 路徑搜尋及 duplicate hash 檢查驗證只剩三份正式 DXF source。
- [x] 5.4 執行 fixture layout audit，確認 `git ls-files project_cases test_cases` 為空、repository 沒有 tracked Project case／Project JSON、三份 user materials 只存在 `assets/sample_dxf/`、tests 未從 runtime path 讀 fixture，且每個非 Project fixture 都有直接 automated consumer。

## 6. 文件與 frozen build 驗證

- [x] 6.1 更新 `README.md` 的 build、`sample_dxf/` 與 Project 資料夾說明，明確記錄正式包不附任何 Project、固定提供三份 DXF素材、`project_cases` 由 runtime 建立；檢查內容未把素材目錄寫成 Project persistence contract。
- [x] 6.2 從只含 tracked files 的 clean checkout／等價暫存環境執行 PyInstaller build，檢查 `dist/SupportOptimizer/sample_dxf/` 恰好包含三份可讀 DXF，成品保留 runtime allowlist且不含 `project_cases/`、`tests/fixtures/`、`test_cases/`；啟動 smoke check 再驗證空 Project 清單與 runtime 目錄建立。

## 7. 整體驗證

- [x] 7.1 執行 DXF assets、三份 user-material consumers、AppDependencies、Project persistence／navigation、CAD integration 與全部改寫後 Project-fixture consumers 的 targeted tests，確認 package boundary、素材可用性、runtime directory 與既有 regression assertions 同時通過。
- [x] 7.2 執行完整 test suite，確認 source relocation 未影響 DXF recognition／review／export、Support／Waler Solver 或 Project loader，並檢查沒有新增 skip 或降低 assertion。
- [x] 7.3 執行 `openspec validate separate-release-and-regression-assets --strict` 與 OpenSpec implementation verification workflow，逐一對照四個 Requirements、D1～D4 與 tasks，確認所有行為有實作及驗證證據後才標記完成。
