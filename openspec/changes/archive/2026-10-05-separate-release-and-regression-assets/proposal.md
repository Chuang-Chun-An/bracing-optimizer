# Proposal

## 閱讀導航

- **P0 現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
- **P0 現在必讀**：`SupportSolver.spec` 的 `datas` 與 `COLLECT` 後複製段落，確認目前哪些檔案會進入正式發行包。
- **P0 現在必讀**：`specs/release-package-assets/spec.md` 的四個 Requirements，作為實作驗收標準。
- **P1 實作前閱讀**：`design.md` 的 D1～D4，確認 `sample_dxf/` allowlist、runtime Project 目錄、Project case 移除方式與非 Project fixture 歸屬。
- **P2 需要時再讀**：只有調整對應資料時，才讀引用三份素材 DXF、既有 Project fixture 或 `cad_bridge_event_examples.json` 的 targeted tests。
- **可以先跳過**：Project schema compatibility、DXF recognition 演算法、Solver scoring 與 installer 重設計；本 change 不修改這些規則。

## 快速摘要

- 正式發行包不附任何預置、示範、歷史或測試 Project，`project_cases/` 只保留為執行期使用者資料目錄。
- 正式發行包會在 `sample_dxf/` 附上三份指定 DXF，作為使用者可自行匯入、操作的素材。
- 三份使用者素材同時可供既有 regression tests 使用，但它們是正式 release assets，不搬到 `tests/fixtures/`。
- 所有 tracked Project cases 與 Project JSON 都移除，不搬到 `tests/fixtures/`；只保留有直接 consumer 的非 Project 測試資料。
- Project 格式、DXF 辨識、匯入流程與 Solver 行為全部不變。

## 現況與目標

| 面向 | Before | After |
| --- | --- | --- |
| 正式發行包 | 夾帶整個 `project_cases/`，只有 Y29 DXF 直接放在執行檔旁，並依賴空 `test_cases/` | 不附任何 Project；三份指定素材統一放在 `sample_dxf/` |
| 使用者素材 | 與 regression data／repository root 混在一起 | Y29、Y1A、Y05 三份 DXF 是明確的正式使用者素材 allowlist |
| Runtime Project | build 預先複製 repository 內容 | 應用程式建立空的可寫 `project_cases/`，之後只放使用者資料 |
| Regression fixture | 與使用者素材、runtime Project 混放 | 不保留 Project case；只有非 Project 測試資料集中於 `tests/fixtures/` |
| Clean checkout build | 可能因 Git 不追蹤空目錄而失敗 | 不依賴 `test_cases/` 或預置 `project_cases/` |

## 主要流程

```text
Repository assets
├─ runtime 必要資產 ───────────────> 正式發行包
├─ 三份指定 DXF 使用者素材 ────────> sample_dxf/
├─ non-Project regression data ────> tests/fixtures/<owner>/
└─ 使用者 Project ────────────────> runtime project_cases/（不預置）
```

1. 將三份指定 DXF 建立為正式 user-material allowlist，統一由 `sample_dxf/` 對外提供。
2. PyInstaller 保留 runtime assets 與 user-material allowlist，移除 `project_cases/`、`test_cases/` 及其他 regression-only 複製。
3. Tests 可直接使用同一份正式素材來源；原本依賴 Project case 的測試改為程式化建立輸入，不保留 Project JSON 或 managed source 副本。
4. 只有 `cad_bridge_event_examples.json` 等非 Project 測試資料依 owner 搬入 `tests/fixtures/`；build contract 與 clean-build smoke test 同時驗證「三份素材完整存在」與「正式包沒有任何 Project／test fixture」。

## 不變事項

- Project schema、loader validation、save／load contract 與既有 runtime Project 位置語意不變。
- 三份 DXF 仍可由既有匯入流程選取；不新增自動載入、sample gallery 或特殊解析路徑。
- DXF recognition、export、Support／Waler Solver 規則與 regression assertions 不變。
- `data/`、`picture/`、`assets/dxf/`、`cad_builder.lsp` 等既有 runtime 資產繼續打包。
- 測試資料整理不得用刪除測試、降低 assertion 或新增 skip 取代。

## Why

正式發行內容需要把使用者 Project、可交付素材與純測試資料清楚分開：Project 不應預置，但三份具有實際操作價值的 DXF 應隨產品提供。明確 allowlist 能保留有用素材，同時避免整包複製 `project_cases/` 與測試目錄。

## What Changes

- 從 `SupportSolver.spec` 移除 `project_cases/`、`test_cases/` 及其他 regression-only 資產的發行複製。
- 將下列三份 DXF 定義為正式使用者素材，統一輸出至成品 `sample_dxf/`：
  - `Y29_test.dxf`
  - `Y1A擋土支撐簡化版.dxf`
  - `670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf`
- 以明確 allowlist 與 package contract test 保證三份素材完整存在，且不會因來源目錄新增檔案而自動擴大發行內容。
- 維持應用程式按需建立 runtime `project_cases/` 的行為，乾淨 build 不再需要預置空目錄。
- 三份正式素材可繼續作為 regression input；所有 tracked Project cases 與 Project JSON 直接移除，不在 fixture tree 保留副本。
- 原本依賴 Project case 的測試改為程式化建立所需輸入或直接使用三份正式 DXF；CAD event 等非 Project 測試資料才歸入 `tests/fixtures/<owner>/`。
- 更新 README，說明正式包沒有示範 Project，但提供 `sample_dxf/` 使用者素材。

### In Scope

- PyInstaller runtime／user-material allowlist 與 package-layout contract tests。
- 三份指定 DXF 的 source ownership、`sample_dxf/` 輸出位置及既有 test consumers。
- Runtime `project_cases` 建立行為的驗證。
- 所有 tracked Project cases／Project JSON 的移除，以及既有 test consumers 的等價改寫。
- 排除 Project cases 與三份正式素材後，其餘非 Project 測試資料的 fixture ownership。
- 受影響的 targeted tests、README 與 `.gitignore`。

### Out of Scope

- 附帶任何 Project JSON、修復 legacy Project、提供預先可開啟的示範 Project 或 sample gallery。
- 修改三份素材內容、Project persistence、DXF recognition、export 或 Solver 的正式行為。
- 搬移與測試無關的分析輸出、使用者成果檔，或重新設計 installer／使用者資料根目錄。

## Capabilities

### New Capabilities

- `release-package-assets`: 定義正式發行包不附任何 Project、固定提供三份 `sample_dxf/` 使用者素材，並將其餘 regression fixtures 與產品資產分離。

### Modified Capabilities

- 無。

## Impact

- 主要影響 `SupportSolver.spec`、三份 DXF 的 repository source path、原本引用 Project cases 或三份素材的 tests、`tests/fixtures/`、`tests/test_dxf_assets.py`、README 與 `.gitignore`。
- `bootstrap.py`、`main.py` 與 `tests/test_app_dependencies.py` 只需確認既有 runtime directory contract；除非驗證發現不符合 spec，否則不改產品 workflow。
- 不預期改變既有 Architecture、Domain、Solver 或 Workflow truth；這是 deployment asset、使用者素材與 test-data ownership 的邊界收斂。
