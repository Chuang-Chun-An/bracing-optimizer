# Tasks

## 實作前閱讀

- **第 1 組**：讀 `proposal.md`「快速摘要／不變事項」、design D1／D3，以及 spec「正式 Project 素材來源必須可重現」與「Repository 只保留正式發行 Project 素材而不保留 regression Project case」。
- **第 2 組**：讀 design D2／D3、`SupportSolver.spec` 與 spec「正式發行包提供兩個 Project 案例」「正式發行包只預置核准 Project 與 runtime 資產」。
- **第 3 組**：讀 design D4／D5、`bootstrap.py` 的 `APP_DIR/project_cases` composition、`docs/WORKFLOW.md`「Save / Load Persistence」，以及 spec 的首次清單／Save／Delete scenarios。
- **第 4 組**：讀 proposal In Scope／Out of Scope、design Risks／Migration Plan 與整份 delta spec；驗證時可跳過 Solver、Domain、DXF recognition 與成果匯出的內部規則。

## 1. 建立正式 Project 快照與來源契約

- [x] 1.1 從目前 runtime `project_cases/Y05車站第一層支撐` 與 `project_cases/Y29車站第一層支撐` 複製且只複製 `project.json`、`source/source.dxf` 到 `assets/project_cases/` 相同 layout；以檔案清單確認四個檔案存在、兩份 `project.json.bak` 與其他檔案均未進入正式來源。（對應 D1；驗證：exact relative-path listing）
- [x] 1.2 在 `tests/` 建立兩個正式案例的共用 allowlist，擴充 `tests/test_dxf_assets.py` 驗證頂層案例名稱、每案 exact file set、非 symlink、無 `.bak`／temp／rollback、schema version 及 managed DXF 可讀，並以現行 `ProjectService.load_project()` 證明兩案不依賴原開發機 absolute source path即可載入。（對應 D3；驗證：新增 focused tests 全數通過）
- [x] 1.3 保留 repository root `/project_cases/` 的 ignore 規則，新增 assertion 確認正式 Project 只位於 `assets/project_cases/` 且 runtime／test fixture 沒有 tracked 副本；以 `git check-ignore`、`git ls-files`／等價檔案盤點及 focused test 驗證。（對應 D1；驗證：runtime 路徑仍 ignored、release asset allowlist 唯一）

## 2. 更新 PyInstaller 精確封裝映射

- [x] 2.1 修改 `SupportSolver.spec`，在 `COLLECT` 後逐檔建立兩個 output Project 的父目錄並 `copy2` 四個 allowlisted source 到 `dist/SupportOptimizer/project_cases/`；不得讀取 repository root runtime `project_cases/`、不得使用 `copytree` 或封裝 `.bak`，且保留既有 icon、software history、runtime assets、CAD bridge 與三份 sample DXF mapping。（對應 D2；驗證：spec source review與缺檔時非零 build failure）
- [x] 2.2 擴充 package contract tests，驗證兩個案例及四個檔案在 spec 中各有一次明確來源／目的 mapping，且 `project.json.bak`、未核准 Project、`test_cases/`、`tests/fixtures/` 與 `copytree` 仍被排除；執行 `python -m unittest tests.test_dxf_assets -v`。（對應 D2／D3；驗證：完整 `DXFAssetTests` 通過）

## 3. 驗證 runtime 相容性並更新長期文件

- [x] 3.1 以 temporary packaged-layout fixture 將 `project_cases_dir` 指向兩個正式快照的衍生副本，驗證既有 repository 列舉只顯示 `Y05車站第一層支撐`／`Y29車站第一層支撐`，兩案可開啟，且既有 source-run 空目錄建立測試仍通過；除非測試證明既有 composition 不足，否則不修改 `bootstrap.py`、`main.py` 或 persistence code。（對應 D4／D5；驗證：`tests.test_app_dependencies`、相關 Project load tests及新增案例測試通過）
- [x] 3.2 更新 README 的建置內容與 repository map，並更新 `docs/WORKFLOW.md` 的首次 Project repository／Save-Load 說明：正式包預置兩案、初始不含 `.bak`、日後 Save／Delete 沿用一般 Project；確認未宣稱唯讀、自動補回、schema migration 或 installer merge。（對應 D5；驗證：文件與 delta scenarios 逐項一致）

## 4. 成品與最終驗證

- [x] 4.1 從不含 repository root runtime `project_cases/` 的 tracked-only clean checkout／等價暫存 workspace 執行 `pyinstaller --noconfirm --clean SupportSolver.spec`，驗證 `dist/SupportOptimizer/project_cases/` 恰好包含兩案與四檔、無 `.bak`，且兩個 output `project.json` 都能以 output managed DXF 載入；同時確認 `sample_dxf/` 與既有 runtime assets 未回退。（對應 D3；驗證：實際 onedir layout與兩案 load smoke check）
- [x] 4.2 執行最接近修改的 package、application dependency、Project persistence／schema tests與 architecture boundary tests，確認預置內容沒有改變 persistence transaction、Project schema或 dependency direction。（驗證：所有 focused suites 通過）
- [x] 4.3 執行完整 `python -m unittest discover -s tests -v`、`git diff --check` 及 scoped repository audit，確認無測試刪除／降級、無 `.bak` 或 runtime Project 誤納、無 Solver／Domain／DXF recognition／UI scope 外修改。（驗證：完整 regression及diff檢查通過）
- [x] 4.4 執行 `openspec validate bundle-seeded-project-cases --strict`，再使用 `$openspec-verify-change bundle-seeded-project-cases` 逐項核對 proposal scope、delta spec scenarios、design D1～D5、tasks與實作證據；只有兩案可重現封裝、四檔精確、`.bak` 排除及所有 task 均完成後才建議 sync／archive。（驗證：OpenSpec strict validation與implementation verification通過）
