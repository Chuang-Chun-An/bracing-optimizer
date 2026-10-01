# Support Distribution UV

開挖工程圍令與支撐配置、DXF 幾何匯入、材料統計及成果輸出的 Windows 桌面工具。

README 是 repository 入口與閱讀地圖。工程規則、Solver 細節、runtime workflow 與精確需求分別由專責文件維護；本文件不再逐一鏡像所有 class、function 或 call graph。

更新日期：2026-10-01

## 1. 快速開始

需求：

- Windows 10／11
- Python 3.12 以上
- Tkinter／Tcl／Tk
- `uv`

安裝並執行：

```powershell
uv sync --group dev
.\.venv\Scripts\python.exe .\main.py
```

執行全部測試：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

建立 Windows onedir 成品：

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean .\SupportSolver.spec
```

輸出位於 `dist/SupportOptimizer/`。`SupportSolver.spec` 會一併放入執行所需的 `data/`、`picture/`、`assets/dxf/`、`cad_builder.lsp`、回歸圖檔及封裝用 fixtures。

Repository 內可驗證上述檔案、命令與 Python dependency 設定；Windows、Tkinter、progeCAD 及 PyInstaller 成品的實際可用性仍需在目標電腦確認。

## 2. 文件與真相來源

遇到不一致時，先依資訊類型找對應 owner，不以 README 覆蓋專責文件。

| 位置 | 責任 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Agent 工作方式、閱讀順序、架構與驗證規則 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 模組責任、依賴方向、state ownership 與已接受的架構例外 |
| [`docs/DOMAIN.md`](docs/DOMAIN.md) | 工程名詞、正式工程規則、Solver Preference、Temporary Heuristic 與 domain gaps |
| [`docs/SOLVER.md`](docs/SOLVER.md) | Support／Waler 搜尋、評分、候選保留、診斷與限制 |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Runtime state、commit／rollback、結果生命週期、Project 與輸出流程 |
| [`openspec/specs/`](openspec/specs) | 已成立 capability 的精確 requirement 與 scenario |
| [`openspec/changes/`](openspec/changes) | 進行中 change 的 proposal、design、delta spec 與 tasks |
| [`openspec/changes/archive/`](openspec/changes/archive) | 已完成 change 的決策與驗證紀錄；不是現行行為的優先來源 |
| [`docs/DEVELOPMENT_HISTORY.md`](docs/DEVELOPMENT_HISTORY.md) | 已完成變更的歷程摘要；不作為現行規格 |

建議閱讀順序：

```text
AGENTS.md
  ↓
README.md
  ↓
docs/ARCHITECTURE.md
  ↓
依任務選讀 docs/DOMAIN.md、docs/SOLVER.md、docs/WORKFLOW.md
  ↓
相關 openspec/specs/<capability>/spec.md
  ↓
若有 active change，再讀 proposal → design → 相關 delta spec → tasks
  ↓
受影響的程式與測試
```

OpenSpec change 完成並驗證後，只有確實改變長期真相時才更新四份長期文件。Archive 保留當時的決策脈絡，不應被當成新的 active requirement。

## 3. 系統做什麼

### 3.1 圍令配置最佳化

系統依 Waler 幾何、支撐與斜撐連接位置、材料規格、可購買料長、庫存及使用者設定的短／中／長段比例，搜尋前五名合法方案。

Waler 的正式工程邊界與評分政策以 [`docs/DOMAIN.md`](docs/DOMAIN.md) 與 [`docs/SOLVER.md`](docs/SOLVER.md) 為準。自動 Solver 與人工方案編輯共用 `bracing_optimizer.algorithms.wales.evaluate_waler_plan()`，避免合法性、評分或 breakdown 出現兩套算法。

### 3.2 支撐配置最佳化

系統先為各 Strut 產生 Steel、Jack 與 Shim 的候選排列，再考量分區、相鄰支撐與雙路支撐關係，建立全域方案。

Column 與 Beam 在 Project 中以各 Strut 上的 station 保存。雙路支撐仍是兩支實體 Strut；只有正式接受且符合工程條件的 pair 才共享 ordered pieces 與相關衍生效果。

### 3.3 DXF 匯入與 Review

`dxf_import/` 是獨立子系統，負責：

- 讀取 DXF 並將 geometry 正規化到 WCS。
- 依使用者指定的圖層角色辨識 Waler、Strut、Brace、Column、Beam 與 CornerBrace。
- 顯示 Review problems、來源 provenance 與可採用的人工決策。
- 在完成前驗證 blocking problems、工程關聯及使用者確認。
- 將確認後的工程資料投影到 Current Project。

DXF Review 的精確規則分散在對應的 [`openspec/specs/`](openspec/specs) capabilities；不要只依 README 推斷辨識門檻。

### 3.4 CAD 半自動輸入

`cad_builder.lsp` 提供 progeCAD 端的點選指令。LSP 會把 UCS 選點轉為 WCS，再寫入 TEMP JSON event；`bracing_optimizer/infrastructure/cad_builder.py` 讀取並映射成 Project row，Main 再以既有 validation 與 input-change lifecycle 採用。

CAD Builder 是補充輸入方式，沒有獨立正式 GUI。Current Project 與 DXF Review 仍由主程式管理。

### 3.5 結果與輸出

程式可以：

- 保存並切換 Waler Top 5 與 Support zoning results。
- 人工編輯已產生的 Waler／Support 方案並立即重算合法性與 score。
- 在 Matplotlib preview 顯示 Project geometry 與可見 Solver results。
- 依目前可見方案產生材料統計。
- 匯出 Excel 材料明細與彙總。
- 匯出 PNG／JPEG 完整預覽。
- 匯出乾淨的 R2018 DXF 成果檔。

DWG 與 PDF 目前沒有原生輸出。

## 4. 架構概覽

```text
Presentation
  main.py + bracing_optimizer/presentation/
        │
        ▼
Application
  project workflow、editing use cases、validation、solver input、result model
        │                         │
        ▼                         ▼
Domain                       Algorithms
  engineering entities       Support / Waler optimization
  material policies          search / scoring / evaluation

Infrastructure
  project persistence、CAD、DXF result、Excel、inventory files

DXF Import Subsystem
  models、geometry、recognition、validation、workflow、dialog
```

主要依賴原則：

```text
Presentation → Application → Domain
Application  → Algorithms
Infrastructure 實作 Application／Domain 所需的外部邊界
```

Domain 與 Algorithms 不依賴 Tkinter。Infrastructure 不定義核心工程規則。DXF 子系統維持自己的 models、geometry、recognition、validation、workflow 與 dialog 邊界。

完整責任與已接受例外見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 5. 主要資料流

### 5.1 手動輸入與求解

```text
UI table edit
  → Application validation / staged editing
  → ProjectDataModel
  → SolverInputBuilder
  → OptimizeWaler / OptimizeSupportZone
  → Algorithms
  → ProjectResultModel
  → Preview / material summary / export
```

### 5.2 DXF 匯入

```text
DXF file
  → immutable source geometry / WCS normalization
  → recognition + validation
  → DXF Review workflow
  → user confirmation / manual decisions
  → Project rows
  → Current Project
```

### 5.3 Project 儲存與開啟

```text
Current Project + results + DXF state
  → ProjectService
  → ProjectSerializer / DxfAssetManager
  → project.json + optional source/source.dxf
```

Persistence 採 temporary write、重新讀取／驗證及 atomic replace。細節見 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)。

## 6. 主畫面

主視窗左側有三個 workspace，右側是 Matplotlib preview，下方是隨目前區域切換的操作列。

### 6.1 工程配置

子頁籤：

- 支撐
- 圍令
- 斜撐
- DXF 匯入
- CAD 匯入

Project 的新增、開啟、儲存、另存與 DXF 重新連結由主選單及 toolbar 提供。

### 6.2 材料設定

子頁籤：

- 材料規格
- 機料庫存

Material Spec definition 的 rename、Usage 修改與刪除由 `bracing_optimizer/application/material_spec_editing.py` staging。Application 驗證引用、同步受影響 rows 並計算 result／cache effects；Main 只負責對話、採用 staged state 與畫面更新。

### 6.3 分析結果

包含 Solver 操作、結果樹、材料摘要與輸出入口。可見性決定 preview、材料統計與匯出內容；同一構件同時選取多個可見方案時，要求唯一結果的輸出會停止。

## 7. Domain 與 Solver 規則摘要

本節只列常用入口，完整規則以 [`docs/DOMAIN.md`](docs/DOMAIN.md)、[`docs/SOLVER.md`](docs/SOLVER.md) 及相關 main spec 為準。

### 7.1 Waler

- RC Waler 保留幾何與 Support 連接語意，但不進入鋼圍令材料分段最佳化。
- Non-RC Waler 的 segment 必須符合該 Usage／Material Spec 可購買料長。
- Waler 不使用 Shim 或 adjustment block。
- 鋼材總長必須位於 `required_length - 200 mm` 到 `required_length` 的閉區間。
- 自動 Solver 與人工編輯共用 `evaluate_waler_plan()` 的 hard issues、庫存／採購資料、ratio、score 與 breakdown。

### 7.2 Support Shim 與 joint

- 每個 ordered layout 可有零塊或一塊非零 Shim；`shim = 0` 表示沒有 Shim piece。
- Steel／Steel 時，Shim 必須與唯一 Jack 相鄰。
- 一端為 RC 時，Shim 位於該 RC terminal；兩端皆 RC 時可位於任一 terminal。
- Waler 類型缺失、空白或無法辨識時，Shim 規則視為 Steel。
- Strut 兩端各 `1600 mm` 的 material-joint exclusion 只有一個例外：RC terminal Shim 與朝內第一段 Steel 的 boundary，可忽略同一 RC 端的 exclusion。
- 該例外不適用 Shim／Jack、其他 joints，也不解除 Column `±830 mm` 或 Beam `±550 mm` exclusion。

### 7.3 Material Spec、庫存與比例

- Material Spec 可留空；系統不因空白而拒絕求解。
- 有選擇 Material Spec 時，Solver 使用符合 Usage／Spec 的 Inventory rows 與使用者目前設定的 Qty。
- Material Spec 空白時，現行 fallback 使用該 Usage 的可用料長，並以每種 `99` 根近似無限庫存。
- 預設 Inventory 的 Qty 可由使用者修改；例如改為 `5` 就以 `5` 進入既有庫存／採購評估，不額外警告使用者不要修改。
- Support 與 Waler 的 Short／Mid／Long ratio 分開設定，不共用比例。
- Ratio 只影響 scoring 與結果排序，不是工程 hard constraint。
- 目前預設 `99` 與比例政策是暫時執行策略；未來接上可靠庫存系統後可替換，但現行採購／庫存評分仍保留。

## 8. Project 與資料契約

### 8.1 Current Project schema

正式 Project 使用 `schema_version: 3`。主要資料位於 `input_data`：

- `walers`
- `struts`
- `braces`
- `inventory`
- `material_specs`

每個 table 的現行 row 欄位由 `bracing_optimizer/application/project_data.py` 的 table contract 定義。Persistence boundary 會檢查 table、row shape 與 Domain validity。

### 8.2 版本相容政策

- `schema_version` 缺少或低於 `3` 時，只有內容已完整符合現行 schema 3 才能開啟。
- `schema_version: 3` 仍須通過相同的現行結構與 Domain 驗證。
- 高於 `3` 的 Project 會拒絕開啟並要求使用較新程式。
- 版本欄位若是字串、浮點數、布林值、`null`、零或負數，會以格式錯誤拒絕。
- 載入流程不偵測 `Beam1`／`Beam2`、`Column1`／`Column2` 等 legacy 欄位，也不進行欄位轉換。
- Repository 不提供 legacy Project schema upgrade tool。無法符合現行 row contract 的舊檔需建立新 Project，重新匯入 DXF 或重新輸入資料。
- 相容的 missing／older version 檔案只有在使用者實際成功儲存時才會寫成 schema 3；單純開啟或關閉不覆寫來源。

精確行為見 [`openspec/specs/project-schema-compatibility/spec.md`](openspec/specs/project-schema-compatibility/spec.md) 與 [`openspec/specs/project-input-row-schema/spec.md`](openspec/specs/project-input-row-schema/spec.md)。

### 8.3 Project 資料夾

```text
project_cases/
└─ <ProjectName>/
   ├─ project.json
   ├─ project.json.bak
   └─ source/
      └─ source.dxf   # 有可管理來源時建立
```

`project.json` 是正式資料；managed DXF copy、外部 source path、fingerprint 與 workflow state 由 persistence／ProjectService 管理。

## 9. 輸出

### 9.1 Excel

Excel 只匯出目前可見且每個構件唯一的方案，包含材料明細與材料彙總。輸出先寫 temporary workbook、重新讀取驗證，再替換 destination。

### 9.2 圖片

Preview 可匯出 PNG／JPEG。輸出會重建完整圖面，不依賴目前縮放視窗的裁切範圍。

### 9.3 DXF 成果

DXF Result Export 只依 `dxf_import_state` 是否存在判斷模式：

| 模式 | 條件 | 內容 |
|---|---|---|
| `source-backed` | `dxf_import_state` 存在且不是 `None` | 使用保存的 Project → WCS metadata，輸出 Project geometry、Solver results 及可用背景 |
| `result-only` | 欄位不存在或值為 `None` | 將 Project 座標直接視為圖面座標，只輸出實際存在的 Solver result layers |

空 Mapping `{}` 或不完整 state 屬於 source-backed 座標錯誤，不會 fallback 到 result-only。

手動建立、沒有 DXF Project state 的 Project 可以輸出 result-only DXF。此模式不建立背景或 `SD_PROJECT_*` layers；檔案沒有來源圖面的定位資訊，合併到其他圖面時由使用者自行定位。

兩種模式都建立新的 R2018／毫米 DXF，不修改原始來源檔。Temporary DXF 會重新讀取並通過 audit、座標、圖層、成果數量、block 與 reference validation 後才替換 destination。

精確契約見 [`openspec/specs/dxf-result-export/spec.md`](openspec/specs/dxf-result-export/spec.md)。

## 10. Repository 結構與主要入口

```text
support_distribution_uv/
├─ main.py                         # Tkinter 主程式入口
├─ bracing_optimizer/
│  ├─ domain/                      # 工程 entities 與共用材料規則
│  ├─ algorithms/                  # Support／Waler Solver 與評估
│  ├─ application/                 # Use cases、validation、editing、Project/result models
│  ├─ infrastructure/              # Persistence、CAD、Excel、DXF result、inventory
│  └─ presentation/                # Widgets、dialogs、UI formatting／navigation
├─ dxf_import/                     # 獨立 DXF import／review 子系統
├─ docs/                           # 長期 Architecture／Domain／Solver／Workflow truth
├─ openspec/                       # Main specs 與 change artifacts
├─ tests/                          # unittest regression suite
├─ data/                           # 預設材料與庫存資料
├─ assets/dxf/                     # DXF output symbols
├─ cad_builder.lsp                 # progeCAD 輸入端
├─ SupportSolver.spec              # PyInstaller onedir 設定
└─ pyproject.toml                  # Python 與 dependency 設定
```

常用 entry points：

| 工作 | 先讀 |
|---|---|
| Main UI／table／preview | `main.py`、`bracing_optimizer/presentation/`、`docs/ARCHITECTURE.md` |
| Project save／load | `bracing_optimizer/application/project_service.py`、`bracing_optimizer/infrastructure/project_persistence.py`、`docs/WORKFLOW.md` |
| Material Spec editing | `bracing_optimizer/application/material_spec_editing.py` |
| Solver input | `bracing_optimizer/application/solver_input_builder.py` |
| Waler optimization | `bracing_optimizer/application/optimize_waler.py`、`bracing_optimizer/algorithms/wales.py`、`docs/SOLVER.md` |
| Support optimization | `bracing_optimizer/application/optimize_support_zone.py`、`bracing_optimizer/algorithms/support.py`、`docs/SOLVER.md` |
| Manual result editing | `bracing_optimizer/application/plan_editing.py` |
| DXF import／review | `dxf_import/`、`docs/WORKFLOW.md`、相關 OpenSpec capability |
| CAD event input | `cad_builder.lsp`、`bracing_optimizer/infrastructure/cad_builder.py` |
| Excel／DXF result export | `bracing_optimizer/infrastructure/excel_result_export.py`、`dxf_result_export.py` |

查找細部 symbol 時使用 repository search，不在 README 維護完整清單：

```powershell
rg -n "def evaluate_waler_plan|class ProjectService" .
rg -n "<domain term>" docs openspec/specs tests bracing_optimizer dxf_import
```

## 11. 開發與驗證

修改前先依 [`AGENTS.md`](AGENTS.md) 閱讀相關文件。非小型工作使用：

```text
Analyze → Spec → Plan → Implement → Verify → Review
```

### 11.1 一般變更

1. 先執行最接近受影響模組的 focused tests。
2. 再依 dependency 與風險擴大 regression 範圍。
3. 不以刪除測試、降低 assertion 或忽略錯誤讓測試通過。
4. 若改變長期 Architecture、Domain、Solver 或 Workflow truth，同步更新對應專責文件。

### 11.2 Solver 變更

修改 Waler／Support 核心前先讀 [`docs/SOLVER.md`](docs/SOLVER.md) 與相關 regression tests。除非 requirement 明確要求，不自行調整 scoring、Candidate Count、Beam Width、Random Seed、搜尋階段、合法性、Jack constraint 或材料比例。

### 11.3 Architecture boundary

修改 layer responsibility 或 dependency direction 時，執行 `tests/test_application_domain_boundaries.py`，並檢查 Domain／Algorithms 沒有引入 Tkinter、Main 或 Infrastructure dependency。

### 11.4 OpenSpec

```powershell
openspec list --json
openspec validate --all --strict
```

Active change 以 proposal 定義問題與 scope、design 定義方案、delta spec 定義精確行為、tasks 定義實作與驗證。完成後先 verify，再 sync／archive；不要把未完成 change 寫成長期既定行為。

## 12. 已知維護熱點

下列項目是目前可觀察的維護風險，不代表可以在功能 change 中順便重構：

- `main.py` 仍同時承擔大型 Tkinter shell、table orchestration、preview 與多個 workflow integration；新增行為應優先放入既有 Application／Presentation boundary。
- `bracing_optimizer/algorithms/wales.py` 的 repair／search 內部仍較集中；任何拆分都必須保持 Solver regression 與 deterministic behavior。
- Results tree 同時呈現不同類型的 Waler／Support results，Presentation 仍需要多種 projection 分支。
- Solver logger 與部分 performance counters 是 process-level state；若未來允許 concurrent runs，需要另立設計。
- DXF recognition capabilities 很多，修改時應從相關 main spec 與 targeted tests 進入，避免無差別追蹤整個 subsystem。

已完成的 Waler shared evaluation、legacy schema normalization 移除、Material Spec editing Application boundary、manual Project result-only DXF 及 Support Shim 共用驗證，不再列為待重構項目。

## 13. 目前重要限制

- Material Spec 空白的每種 `99` 根只是現行 fallback，不是可靠庫存系統。
- Short／Mid／Long ratio 是可由使用者調整的排序偏好，未來若有可靠庫存系統可重新設計。
- Source-backed DXF export 仍需要完整 Project → WCS metadata；state 存在但資料不完整時會停止。
- Result-only DXF 不宣稱和任何來源圖面自動對齊。
- Project loader 不轉換 legacy row shape。
- README 提供入口與現況摘要；精確 tolerance、failure semantics 與 edge cases 必須回到專責文件及 main specs。
