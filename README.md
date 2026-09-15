# Support Distribution UV

開挖圍令與支撐配置、CAD 幾何匯入、材料統計及配置圖輸出的 Windows 桌面工具。

本文件以目前工作目錄中的實際程式碼為準，供未來維護者重新理解專案。它不只是操作說明，也記錄資料模型、模組責任、主要函式、Solver 流程、評分公式、JSON contract、GUI 呼叫關係及已知待重構區域。

更新日期：2026-09-11

---

# 1. 專案目的

本專案協助工程師把開挖支撐系統的幾何資料轉換成可以檢查、求解與輸出的工程資料。

主要用途如下。

## 1.1 圍令配置最佳化

針對一根圍令：

- 由圍令起終點計算總長度。
- 將支撐端點、斜撐端點及角撐延伸位置投影成圍令上的禁止接頭點。
- 依候選接頭位置、材料長度、庫存與禁止區產生合法分段。
- 使用接頭位置型遺傳演算法搜尋低分方案。
- 回傳前五名不同分段方案。

圍令材料目前不可裁切。每一段必須剛好等於 Inventory 中存在的可購買長度。

## 1.2 支撐配置最佳化

針對同一分區內的多根支撐：

- 由支撐起終點計算總長。
- 將中間柱位置轉成 pile forbidden zone。
- 將托梁位置轉成 waler forbidden zone。
- 產生鋼材、調整塊、千斤頂與餘長組合。
- 先求每根支撐的合法候選方案。
- 雙路支撐仍保留為兩支實體支撐，但同群組必須採用相同的 ordered pieces。
- 再考量相鄰支撐的千斤頂間距與區域一致性，求多支支撐全域方案。

## 1.3 CAD 半自動匯入

progeCAD 端使用 `cad_builder.lsp`：

- 點選圍令、支撐或斜撐起終點。
- 支撐可加選托梁與中間柱位置。
- `UPDSTRUT` 可依 `StrutID` 原位修正既有支撐幾何。
- LSP 在寫入事件前將 UCS 點位轉成 WCS。
- DXF 匯入會找出中心線距離約 1000 mm 的平行雙路支撐候選，供使用者採用或取消。
- 產生單一 TEMP JSON 事件。
- `main.py` 每 500 ms 監看事件，依 `operation=add/update` 加入或更新正式資料模型。

CAD Builder 沒有獨立正式 GUI。`main.py` 是唯一工程資料 GUI。

## 1.4 工程資料檢查

主程式會檢查：

- ID 是否空白或重複。
- 幾何座標是否為有效數字。
- 線段長度是否大於零。
- 支撐與斜撐端點是否落在指定圍令上。
- 起點與終點圍令是否合理。
- 支撐與圍令方向是否近似垂直。
- 托梁與中間柱測站是否重複、超界或格式錯誤。
- 角撐長度與目標千斤頂區域是否有效。
- Inventory 長度與數量是否合法。

## 1.5 結果、材料統計與圖面

程式可以：

- 保存多個圍令方案及分區支撐方案。
- 個別切換方案是否顯示。
- 在預覽圖疊加圍令分段與支撐材料配置。
- 依目前可見方案統計材料用量與庫存差額。
- 將目前可見方案的逐根材料明細與庫存彙總匯出為 Excel。
- 匯出高解析度 PNG/JPEG 完整配置圖。
- 依專案已保存的工程幾何，建立目前可見圍令與支撐配置的乾淨 DXF 成果檔。

DXF 匯出不再重新儲存原始 DXF。程式以 `ezdxf.new("R2018")` 新建毫米圖檔，從 `dxf_import_state` 的世界座標重建必要工程背景；鋼材、調整塊與餘量使用對齊尺寸標註，千斤頂插入 `SUPPORT_JACK` 專用圖塊且不另標尺寸。DWG 與 PDF 尚未提供原生輸出。

---

# 2. 系統架構總覽

```text
progeCAD
└─ cad_builder.lsp
   ├─ ADDWALER
   ├─ ADDSTRUT
   ├─ UPDSTRUT
   ├─ ADDBRACE
   └─ SUPSTATUS
          │
          ▼
Windows TEMP JSON
support_distribution_uv_cad_builder_temp.json
          │
          ▼
bracing_optimizer/infrastructure/cad_builder.py
├─ CadEventReader
├─ CadEventMapper
└─ TempEventWatcher
          │
          ▼
main.py / SupportInputApp
├─ ProjectDataModel
│  ├─ walers
│  ├─ struts
│  ├─ braces
│  └─ inventory
├─ ProjectDomainModel
│  └─ Waler / Strut / Brace（Column／Beam 位置由各 Strut 持有）
├─ 資料表與驗證
├─ 案例 JSON
├─ Matplotlib Preview
├─ Results / 方案直接編輯 / 材料統計
└─ bracing_optimizer/application/solver_input_builder.py
   ├─ WalerProblemInput ─► WalerSolverDialog ─► OptimizeWaler ─► algorithms/wales.py ────┐
   └─ SupportZoneInput ─► SupportSolverDialog ─► OptimizeSupportZone ─► algorithms/support.py ──┴─► domain/material_rules.py
```

模組責任邊界：

```text
main.py
    GUI 主視窗、資料編輯、流程協調、預覽與輸出；驗證、結果模型與
    手動方案重算已轉交 application/，共用 UI 已轉交 presentation/

bracing_optimizer/domain/
    不依賴 GUI、Application 或外部資源的工程 entity 與材料規則

bracing_optimizer/algorithms/
    圍令／支撐最佳化演算法與共用搜尋政策

bracing_optimizer/application/
    Use Case、Solver Input Builder、工程驗證、結果模型與手動方案編輯服務

bracing_optimizer/presentation/
    Tkinter presentation 子系統；包含共用 Widget、選擇 Dialog、
    Solver Dialog、主執行緒橋接與純文字結果格式化

bracing_optimizer/application/project_data.py
    應用程式資料列模型、正式欄位 schema、ID 產生與 Domain 投影

bracing_optimizer/domain/project_domain.py + application/project_mapper.py
    純工程 entity／aggregate；將 Strut 內的 Column／Beam 位置轉成 typed tuples

bracing_optimizer/application/solver_input_builder.py
    唯讀地將 ProjectDataModel 幾何與庫存轉成 WalerProblemInput / SupportZoneInput

bracing_optimizer/infrastructure/
    庫存來源、專案持久化、CAD 事件、Excel 與 DXF 成果輸出的外部資源實作；
    InventoryRepository 與其 JSON／記憶體實作仍維持同一個小型 cohesive module

bracing_optimizer/algorithms/wales.py
    單根圍令接頭位置型 GA、材料配置與評分

bracing_optimizer/algorithms/support.py
    單支支撐候選生成及多支支撐全域最佳化

bracing_optimizer/application/optimize_support_zone.py
    單一支撐分區的候選快取、分階段搜尋、最佳解選擇與診斷 Use Case

bracing_optimizer/application/optimize_waler.py
    單根圍令的 Config 建立、分階段搜尋、結果合併與診斷 Use Case

bracing_optimizer/domain/material_rules.py
    圍令與支撐共用的材料長度分類、比例目標與比例懲罰規則

dxf_import/
    DXF 匯入子系統；模型、幾何、辨識、候選點、驗證、控制器、預覽、讀檔與 Tkinter Dialog 分開維護

dxf_import/__init__.py
    DXF 匯入子系統的正式公開 API；實作由各自的 models、geometry、importer、dialog 等模組持有

cad_builder.lsp
    CAD 端點位輸入與 JSON 寫入

bracing_optimizer/application/project_service.py + infrastructure/project_persistence.py
    專案存取流程、schema 3 嚴格驗證與 DXF managed-copy lifecycle

```

---

# 3. 檔案結構

```text
support_distribution_uv\
├─ bracing_optimizer\
│  ├─ domain\
│  │  ├─ material_rules.py
│  │  └─ project_domain.py
│  ├─ algorithms\
│  │  ├─ solver_search.py
│  │  ├─ support.py
│  │  └─ wales.py
│  ├─ application\
│  │  ├─ optimize_support_zone.py
│  │  ├─ optimize_waler.py
│  │  ├─ solver_input_builder.py
│  │  ├─ plan_editing.py
│  │  ├─ project_data.py
│  │  ├─ project_mapper.py
│  │  ├─ project_results.py
│  │  ├─ project_service.py
│  │  └─ project_validation.py
│  ├─ infrastructure\
│  │  ├─ cad_builder.py
│  │  ├─ dxf_result_export.py
│  │  ├─ excel_result_export.py
│  │  ├─ inventory_repository.py
│  │  └─ project_persistence.py
│  └─ presentation\
│     ├─ cad_view_interaction.py
│     ├─ result_formatters.py
│     ├─ widgets\
│     └─ dialogs\
├─ main.py
├─ bootstrap.py
├─ app_dependencies.py
├─ cad_builder.lsp
├─ cad_bridge_event_examples.json
├─ tools\
│  ├─ inventory_conversion.py
│  └─ upgrade_project_schema.py
├─ dxf_import\
│  ├─ models.py
│  ├─ geometry.py
│  ├─ recognition.py
│  ├─ importer.py
│  ├─ candidate_points.py
│  ├─ validation.py
│  ├─ controllers.py
│  ├─ preview.py
│  └─ dialog.py
├─ data\
│  ├─ inventory.json
│  └─ default_inventory.json
├─ picture\
│  └─ 001.txt
├─ test_cases\
│  ├─ 123.json
│  ├─ Y1A站第一層支撐.json
│  └─ Y1A站第二層支撐.json
├─ tests\
│  └─ test_cad_builder_integration.py
├─ docs\
│  └─ wales\
│     └─ README.md
├─ SupportSolver.spec
├─ pyproject.toml
└─ uv.lock
```

| 檔案 | 類型 | GUI | Solver | 主要責任 |
|---|---|---:|---:|---|
| `main.py` | 主應用程式 | 是 | 協調 | Tkinter 主視窗、資料表、預覽與流程協調；委派 Application service 與 Presentation 類別 |
| `bracing_optimizer/presentation/` | UI 子系統 | 是 | 協調 | Preview toolbar、選擇 Dialog、Solver Dialog、執行緒橋接與結果文字格式化 |
| `bracing_optimizer/application/project_data.py` | Application Model | 否 | 否 | TABLE schema、ID、可變資料列與 Domain 投影 |
| `bracing_optimizer/domain/project_domain.py` | Domain Model | 否 | 間接 | Waler、Strut、Brace；各 Strut 自己持有 Column／Beam 位置與 aggregate invariant |
| `bracing_optimizer/application/project_mapper.py` | Domain Mapper | 否 | 間接 | schema 3 row 與純 Domain entity 的唯一映射邊界 |
| `bracing_optimizer/application/project_service.py` | Application Service | 否 | 否 | 儲存、載入、DXF relink 流程協調；沿用既有可注入 persistence components |
| `bracing_optimizer/infrastructure/project_persistence.py` | Persistence | 否 | 否 | schema 3 驗證、DXF managed copy 與交易式 JSON 寫入 |
| `bracing_optimizer/infrastructure/inventory_repository.py` | 資料來源模組 | 否 | 否 | InventoryRepository 及 JSON／記憶體實作維持同檔，不為分層而拆分 |
| `tools/inventory_conversion.py` | 資料整理工具 | 否 | 否 | 將機料清冊 JSON 轉為執行期 `inventory.json`，不是 Solver 依賴 |
| `bracing_optimizer/infrastructure/cad_builder.py` | CAD Adapter | 否 | 否 | CAD event JSON 讀取、映射、監看、acknowledge |
| `bracing_optimizer/infrastructure/dxf_result_export.py` | DXF Adapter | 否 | 否 | 建立、驗證並交易式交付正式成果 DXF |
| `bracing_optimizer/infrastructure/excel_result_export.py` | Excel Adapter | 否 | 否 | 建立、驗證並交易式交付材料明細與庫存彙總活頁簿 |
| `cad_builder.lsp` | progeCAD 外掛 | CAD 命令列 | 否 | 點選座標、產生 JSON、寫入 TEMP |
| `bracing_optimizer/algorithms/wales.py` | 圍令 Solver | 否 | 是 | 接頭型 GA、分段、材料配置、評分；不依賴 GUI framework |
| `bracing_optimizer/algorithms/support.py` | 支撐 Solver | 否 | 是 | 單支候選與多支全域最佳化 |
| `bracing_optimizer/application/optimize_support_zone.py` | Application Use Case | 否 | 協調 | 支撐分區 Phase 1/2、候選快取、搜尋升級、最佳解與診斷 |
| `bracing_optimizer/application/optimize_waler.py` | Application Use Case | 否 | 協調 | 圍令 Config、分階段搜尋、結果合併與診斷 |
| `bracing_optimizer/application/solver_input_builder.py` | Application Input Builder | 否 | 輸入 | ProjectDataModel→工程 Input；庫存查詢、幾何轉換且不修改 Model |
| `bracing_optimizer/application/plan_editing.py` | Application Service | 否 | 協調 | 手動支撐／圍令方案的重算與工程規則檢查 |
| `bracing_optimizer/application/project_results.py` | Application Model | 否 | 間接 | Solver 結果狀態、序列化、逐根材料明細與材料用量彙整 |
| `bracing_optimizer/application/project_validation.py` | Application Service | 否 | 否 | 以 data-only report 驗證工程資料，不操作 Tkinter |
| `bracing_optimizer/domain/material_rules.py` | 共用領域規則 | 否 | 共用 | 材料長度分類、比例正規化、比例統計與懲罰；不依賴任何 Solver |
| `dxf_import/` | DXF 匯入子系統 | 僅 `dialog.py` | 否 | 分離模型、幾何辨識、雙路配對、候選點、驗證、控制器、預覽與 `ezdxf` importer |
| `inventory.json` | 資料 | 否 | 間接輸入 | 系統預設 Inventory，由設定頁籤載入後才交給 Solver |
| `default_inventory.json` | 歷史資料 | 否 | 否 | 舊版預設庫存，不再是執行期資料源 |
| `test_cases/*.json` | 資料 | 否 | 輸入 | 可載入與儲存的工程案例 |
| `cad_bridge_event_examples.json` | 文件／測試資料 | 否 | 否 | CAD add 與 Strut update 事件範例 |
| `picture/*.txt` | 資源 | 否 | 否 | 彩蛋 ASCII art |
| `test_cad_builder_integration.py` | 測試 | 否 | 否 | CAD→Mapper→main→case 端到端測試 |
| `SupportSolver.spec` | 封裝 | 否 | 否 | 唯一正式 PyInstaller onedir 設定 |

正式發佈只使用 `SupportSolver.spec`。

---

# 4. 資料流（Data Flow）

## 4.1 主資料流

```text
手動表格輸入 / 案例 JSON / CAD JSON
                  │
                  ▼
         ProjectDataModel
 walers / struts / braces / inventory
                  │
                  ▼
           validate_data()
                  │
                  ▼
bracing_optimizer/application/solver_input_builder.py
      ┌───────────┴───────────┐
      ▼                       ▼
WalerProblemInput       SupportZoneInput
      │                       │
      ▼                       ▼
WalerSolverDialog      SupportSolverDialog
      │                       │
      ▼                       ▼
OptimizeWaler          OptimizeSupportZone
      │                       │
      ▼                       ▼
algorithms/wales.py     algorithms/support.py
      │                       │
      ├────► domain/material_rules.py ◄┤
      └───────────┬───────────┘
                  ▼
             result_items
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
    Results    Preview   材料統計
                              │
                              ▼
                  PNG / JPEG、DXF 匯出
```

## 4.2 CAD 匯入資料流

```text
ADDWALER / ADDSTRUT / UPDSTRUT / ADDBRACE
              │
              ▼
cad_builder.lsp 以 UCS 點選，再用 trans point 1 0 轉成 WCS
              │
              ▼
%TEMP%\support_distribution_uv_cad_builder_temp.json
              │
              ▼
TempEventWatcher.check_new_event()
              │
              ▼
CadEventReader.load()
              │
              ▼
CadEventMapper.map_command()
              │
              ├─ add → project_data.build_input_row()
              └─ update → 複製既有 Strut 並原索引 replace
              │
              ▼
SupportInputApp._apply_cad_event()
              │
              ├─ append 或原位更新 ProjectDataModel
              ├─ 條件式同步 DXF confirmed binding
              ├─ acknowledge 並刪除同 event_id JSON
              ├─ 清除舊 Solver 結果與快取
              └─ 更新表格與預覽
```

## 4.3 圍令輸入轉換

```text
Waler row
├─ 起終點 → 幾何長度
└─ WalerID

Strut rows
├─ 支撐端點投影到對應圍令
└─ 角撐長度產生額外禁止點

Brace rows
└─ 斜撐端點投影到對應圍令

          ▼

{
  waler_id,
  start_point,
  end_point,
  length,
  forbidden_points
}
```

## 4.4 支撐輸入轉換

```text
Strut row
├─ StrutID / 舊 SupportID
├─ SharedLayoutGroup → 雙路支撐共用配置關係
├─ 起終點 → total_length
├─ ColumnPositions → pile_centers
├─ BeamPositions → waler_centers
├─ TargetJackRegion
└─ Zoning

          ▼

SupportZoneInput
├─ 單支 SupportOptimizationUnit
└─ 雙路 SupportOptimizationUnit（兩個 SupportConfig）
```

---

# 5. 類別（Class）說明

## 5.1 資料與 Solver 類別

### `project_data.ProjectDataModel`

GUI 的唯一正式可變資料列 adapter；Solver 與工程規則透過 `to_domain()`
取得不可變的 `ProjectDomainModel`，不直接解讀字典 key。

主要欄位：

```text
walers
struts
braces
inventory
```

`ColumnPositions`／`BeamPositions` 直接屬於各 Strut。Domain Mapper 將儲存用的
逗號字串轉成 `Strut.column_positions`／`Strut.beam_positions` typed tuples；DXF 的
完整 Column／Beam 幾何只保留在匯入狀態，不提升為正式專案 entity。
兩筆 Strut 使用相同的 `SharedLayoutGroup` 時，Domain 以 `SupportGroup` 表達雙路
關係；兩支仍是各自獨立的實體與材料用量，不會合併成一筆虛擬支撐。
資料由 `SupportInputApp` properties 代理，因此 `main.py` 不再另外維護第二份 BuilderModel。

### `wales.Config`

單根圍令 Solver 設定。

重要欄位：

| 欄位 | 意義 |
|---|---|
| `total_length` | 圍令總長度 |
| `support_points` | 禁止接頭中心點 |
| `candidate_joint_points` | 染色體對應候選點 |
| `min_piece_length` | 硬性最小段長 |
| `preferred_min_piece_length` | repair 偏好最小段長 |
| `max_piece_length` | 硬性最大段長 |
| `joint_clearance_to_support` | 禁止點安全距離 |
| `purchasable_lengths` | 可購買且不可裁切的段長 |
| `*_segment_ratio_target` | 短中長目標比例 |
| `population_size` | GA 族群數 |
| `generations` | 演化代數 |
| `crossover_rate` | 交配率 |
| `mutation_rate` | 突變率 |
| `elite_size` | 每代保留菁英數 |
| `tournament_k` | tournament 抽樣數 |
| `top_n` | 最終回傳方案數 |

### `support.SupportConfig`

單根支撐求解輸入。

| 欄位 | 意義 |
|---|---|
| `support_id` | 支撐編號 |
| `total_length` | 支撐總長 |
| `pile_centers` | 中間柱位置 |
| `waler_centers` | 托梁位置 |
| `target_jack_region` | 目標千斤頂區域 |
| `shared_layout_group` | 雙路支撐共用配置群組；空字串表示一般單支撐 |

### `support.SupportPlan`

單根支撐的一個完整候選方案。

| 欄位 | 意義 |
|---|---|
| `pieces` | `[("steel", L), ("shim", L), ("jack", 600)]` |
| `joints` | piece 交界位置，不含兩端 |
| `gap` | 支撐需求長度減去 piece 總長 |
| `jack_center` | 千斤頂中心位置 |
| `jack_region_id` | 千斤頂所在區域 |
| `score` | 單支支撐分數 |
| `shared_layout_group` | 所屬雙路共用配置群組 |
| `valid` | 是否通過硬限制 |
| `reason` | 不合法原因 |
| `breakdown` | 各評分項目 |

### `support.GlobalSolution`

同一 Zoning 內多根支撐的全域解。

| 欄位 | 意義 |
|---|---|
| `plans` | 每根支撐選中的 `SupportPlan` |
| `total_score` | 單體分數與 pair penalty 總和 |
| `valid` | 全域是否合法 |
| `reason` | fallback 或失敗原因 |

## 5.2 CAD 類別

### `cad_builder.CadEventReader`

讀取 UTF-8/UTF-8-BOM JSON，驗證 envelope：

- 最上層必須是 dict。
- 必須有 `event_id`。
- `type` 必須可映射為正式資料表。
- `operation` 必須是 `add` 或 `update`。
- `coordinate_space` 必須是 `WCS`。
- `update` 第一版只接受 Strut，且必須有 `target_id`。
- `data` 必須是 dict。

### `cad_builder.CadEventMapper`

將 CAD event 轉成正式 Solver row。

它不擁有第二份資料模型，只接收：

```text
event + rows_by_table
```

`add` 會呼叫 `project_data.build_input_row()` 產生完整資料列及下一個 ID；
`update` 則複製既有 Strut，只覆寫允許的幾何欄位。

### `cad_builder.TempEventWatcher`

監看單一 TEMP JSON。

狀態：

```text
temp_path
last_event_id
```

只有事件成功加入正式資料模型後才呼叫 `acknowledge()`。如果檔案仍是同一個 `event_id`，就刪除；如果已被較新事件取代，不會誤刪新事件。

## 5.3 GUI 類別

### `main.PreviewNavigationToolbar`

Matplotlib 自訂工具列，只保留：

- 全圖
- 平移
- 儲存

另外實作：

- 平移 40 ms throttle。
- 滾輪／平移期間隱藏文字、座標標籤與 legend。
- 顯示目前縮放百分比。
- 將儲存按鈕導向自訂高解析度輸出。

### `main.SupportInputApp`

主程式核心類別，也是目前最大的類別。

責任包含：

- `ProjectDataModel` ownership
- 七個 Notebook tabs
- 表格 CRUD 與驗證
- CAD event polling
- 案例管理
- 結果樹與方案編輯
- 材料統計
- Matplotlib preview
- Solver Dialog 建立
- Solver 結果保存與疊圖

### `main.WalerSelectionDialog`

讓使用者從目前圍令 ID 選擇一根執行圍令 Solver。

### `main.ZoningSelectionDialog`

讓使用者從支撐表現有 `Zoning` 選擇一個分區執行支撐 Solver。

### `main.TextRedirector`

背景 Solver thread 不能直接操作 Tk widget，因此先把訊息放入 `queue.Queue`，再由 Tk `after()` 定時安全寫入 ScrolledText。

### `main.SupportSolverDialog`

同一分區支撐的求解視窗。

責任：

- 取得並驗證使用者輸入的材料比例。
- 在背景 thread 呼叫 `OptimizeSupportZone.execute()`。
- 顯示 Use Case 回報的進度、診斷與結果。
- 將結果 callback 回 `SupportInputApp`。

### `optimize_support_zone.OptimizeSupportZone`

不依賴 Tkinter 的支撐分區最佳化 Use Case。接收 `SupportZoneInput` 與 `MaterialRatioTargets`，負責 Phase 1 候選、cache、Phase 2 分階段搜尋、搜尋升級、最佳解選擇與 diagnostics，回傳 `OptimizeSupportZoneResult`。

### `main.WalerSolverDialog`

單根圍令求解視窗。

責任：

- 顯示固定工程資訊與評分權重。
- 取得並驗證使用者輸入的短中長比例。
- 重用同一執行期間的 Solver memory。
- 在背景 thread 呼叫 `OptimizeWaler.execute()`。
- 顯示 Top 5，並 callback 回主結果模型。

### `optimize_waler.OptimizeWaler`

不依賴 Tkinter 的單根圍令最佳化 Use Case。接收 `WalerProblemInput` 與 `MaterialRatioTargets`，負責建立 `wales.Config`、分階段搜尋、搜尋升級、合併結果與 diagnostics。

---

# 6. 函數（Function）索引

以下索引涵蓋所有 Solver、資料模型與 CAD 函式，以及 `main.py` 的重要 GUI 方法。純粹的 Tk button callback、字串格式化與 Treeview IID helper 依責任分組列出。

### `bracing_optimizer/application/optimize_support_zone.py`

| 類別／方法 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `OptimizeSupportZoneRequest` | `SupportZoneInput`、比例 | immutable request | Use Case 輸入邊界 |
| `OptimizationProgress` | stage、message、support ID | progress event | GUI 無關的進度回報 |
| `OptimizeSupportZone.execute()` | request、callbacks | result | 完整支撐分區最佳化流程 |
| `OptimizeSupportZoneResult` | solution、diagnostics | immutable result | Use Case 輸出邊界 |

### `bracing_optimizer/application/optimize_waler.py`

| 類別／方法 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `OptimizeWalerRequest` | `WalerProblemInput`、比例 | immutable request | Use Case 輸入邊界 |
| `WalerOptimizationProgress` | stage、message | progress event | GUI 無關的進度回報 |
| `OptimizeWaler.execute()` | request、callbacks | result | 完整單根圍令最佳化流程 |
| `OptimizeWalerResult` | solutions、diagnostics、config | immutable result | Use Case 輸出邊界 |

### `bracing_optimizer/application/solver_input_builder.py`

| 類別／函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `SupportZoneInput` | zoning、configs | immutable input | 整理好的支撐分區工程題目 |
| `SupportOptimizationUnit` | 一或兩個 `SupportConfig` | immutable input | 一般單支或共用配置的雙路求解單位 |
| `WalerProblemInput` | 圍令工程資料、庫存 | immutable input | Dialog 與 Use Case 共用的圍令題目 |
| `InventoryLookup` | Project inventory rows | 長度、stock、qty | 查詢已載入的庫存，不接觸資料來源 |
| `SupportInputBuilder.build_zone()` | ProjectDataModel、zoning | `SupportZoneInput` | 唯讀建立支撐 Solver 輸入 |
| `WalerInputBuilder.build_all()` | ProjectDataModel | Waler input map | 唯讀建立所有圍令輸入，保留既有 eager 行為 |
| `project_point_onto_segment()` | 線段與點 | station/None | 建立圍令 forbidden point |

### `bracing_optimizer/domain/material_rules.py`

| 類別／函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `MaterialLengthRules` | 短／中／長邊界 | immutable rules | Solver 無關的分類規則 |
| `MaterialRatioTargets.normalized()` | 三類比例 | normalized targets | 驗證並正規化比例 |
| `classify_length()` | length、rules | short/mid/long/out | 唯一正式材料分類實作 |
| `analyze_material_ratios()` | lengths、targets、weight | analysis | 共用統計、偏差與 penalty 計算 |

## 6.1 `bracing_optimizer/application/project_data.py`

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `next_identifier()` | rows、ID field、prefix | `Wn/Sn/Bn` | 取相同 prefix 最大數字加一 |
| `build_input_row()` | table、values、existing rows | 完整 row | 套 defaults、產生 ID、限制正式 columns |
| `normalize_project_row()` | table、source | normalized row | 依 schema 3 補 defaults 並限制正式欄位 |
| `ProjectDataModel.rows()` | table | mutable list | 取得指定資料表 |
| `replace_table()` | table、rows | `None` | 正規化後替換整張表 |
| `to_domain()` | 無 | `ProjectDomainModel` | 建立供 Solver／工程規則使用的不可變 aggregate |
| `geometry_rows()` | 無 | 三種構件 dict | 提供 CAD／DXF mapper 目前資料 |
| `to_case_data()` | 無 | schema 3 deep copy | 產生專案 JSON 的 `input_data` |

## 6.2 `bracing_optimizer/infrastructure/project_persistence.py`

| 類別／函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `ProjectSerializer.validate()` | payload | `None` | schema 3、Strut 位置與 `dxf_asset` 契約的嚴格驗證 |
| `DxfAssetManager.file_info()` | DXF path | hash、size、mtime | SHA-256 與 DXF 可讀性驗證 |
| `DxfAssetManager.inspect()` | project path、asset、state | `DxfAssetStatusReport` | 唯一的 DXF 狀態判斷與同 hash 修復入口 |
| `DxfAssetManager.save_project()` | payload、已驗證 DXF | `ProjectSaveResult` | 管理副本與 JSON 的交易式儲存／回復 |
| `DxfCompatibilityChecker.compare()` | 保存 state、候選 state、Solver rows | 相容性報告 | handle＋工程線、圖層＋工程線、跨圖層工程線比對 |
| `merge_source_references()` | 兩份 state、match report | 新 state | 只更新來源參照，保留 ID、工程線與人工修正 |

`DxfStatus` 包含 `READY`、`SOURCE_MODIFIED`、`MISSING`、`RELINK_REQUIRED`、`BINDING_REQUIRED`、`LEGACY_NO_STATE` 與 `INCOMPATIBLE`，並另有 runtime／待儲存／管理副本異常等細分狀態。這些狀態仍用於專案保存、來源追蹤與重新連結；正式成果匯出不使用 `can_export` 或 stale binding 作為阻擋條件，也不讀取或重新儲存來源檔。

### 6.2.1 `bracing_optimizer/infrastructure/dxf_result_export.py`

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `export_coordinate_system_from_import_state()` | import state 的 coordinate metadata | `ExportCoordinateSystem` | 在 Main orchestration boundary 建立窄的 Project → WCS 契約 |
| `build_project_member_bindings()` | Current Project 圍令／支撐列、座標契約 | world-coordinate bindings | 直接從目前 Project geometry 建立 Solver placement line，不讀 converted |
| `build_project_geometry_segments()` | Current Project 圍令／支撐／斜撐列、座標契約 | formal WCS lines | 建立 `SD_PROJECT_WALER/STRUT/BRACE` 正式工程線 |
| `export_results_to_dxf()` | 輸出路徑、可見方案、Current Project rows、座標契約、optional background | `DXFExportReport` | 新建 R2018 clean document、加入目前工程線、背景與成果，暫存驗證後交易式交付 |

正式輸出只在新文件上執行一次 `saveas()` 到同資料夾唯一暫存檔，重新讀取後要求 Audit 為 0 errors／0 fixes，並驗證背景及成果世界座標、圖層、Dimension、Jack Block、重複 Layer、XRecord 與懸空 Handle。全部通過後才以 `os.replace()` 取代正式檔。

## 6.3 `bracing_optimizer/infrastructure/cad_builder.py`

| 函數／方法 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `_table_key()` | CAD type | table key | `waler→walers`、`strut→struts`、`brace→braces` |
| `_normalize_coordinates()` | event data | 原 dict 就地正規化 | 驗證四座標為有限數字、線長大於零 |
| `CadEventReader.load()` | path | event dict | 解析與驗證 JSON envelope |
| `CadEventMapper.build_row()` | table、values、rows | 完整 row | 座標驗證後呼叫 `build_input_row()` |
| `CadEventMapper.map_event()` | event、rows_by_table | `(table, row)` | CAD event 正式映射入口 |
| `TempEventWatcher.__init__()` | temp path | watcher | 設定事件檔與 last event |
| `check_new_event()` | 無 | event 或 `None` | 檔案存在且非 last event 才回傳 |
| `acknowledge()` | 已成功 event | `None` | 同 event_id 才刪檔並記錄 last ID |

## 6.4 `bracing_optimizer/algorithms/support.py`

### 資料與顯示工具

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `get_support_config_key()` | `SupportConfig` | tuple | 候選快取 key，不含 support ID |
| `clone_plan_with_support_id()` | plan、ID | 新 `SupportPlan` | 相同幾何快取套回實際支撐 ID |
| `set_logger()` | callback | `None` | 設定 GUI logger |
| `log()` | 任意訊息 | `None` | 有 logger 才輸出 |
| `display_piece_kind()` | kind | 中文名稱 | steel/shim/jack 中文化 |
| `format_pieces_for_display()` | pieces | 字串 | 將配置轉成人類可讀文字 |
| `print_summary()` | context、metrics | `None` | 輸出框線摘要 |
| `print_global_summary()` | `GlobalSolution` | `None` | 全域分數、合法性、jack 分布摘要 |
| `print_plan()` | `SupportPlan` | `None` | 輸出單一方案 |
| `format_plan_compact()` | `SupportPlan` | 字串 | 單行方案摘要 |
| `print_global_solution()` | `GlobalSolution` | `None` | 輸出所有支撐方案 |

### 幾何與禁止區

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `build_positions()` | pieces | 累積節點 | 將 piece 長度轉成位置 |
| `get_joint_positions()` | pieces | joints | 取得內部 piece 交界 |
| `get_jack_center()` | pieces | float | 找出 jack 中心；無 jack 回 `-1` |
| `forbidden_zones()` | config | `(start,end,label)` | 端部、pile、waler 禁止區 |
| `check_joint_forbidden()` | joint、config | bool | 接頭是否落入任一禁止區 |
| `count_forbidden_joints()` | joints、config | int | 禁止接頭數 |
| `_merged_forbidden_intervals()` | config | merged intervals | 診斷禁止區覆蓋率 |
| `get_jack_region_id()` | jack center、piles | int | 以 pile centers 分隔區域 |

### 候選生成與評分

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `evaluate_single_support()` | config、pieces | `SupportPlan` | 硬限制與單支評分中心 |
| `_keep_top_candidates()` | DP states、limit | states | 依 sequence 去重、保留低分狀態 |
| `_steel_order_state_penalty()` | steel sequence | float | beam 排序 heuristic |
| `generate_length_combinations_dp()` | config、limits | combo dicts | DP 產生鋼材 multiset、shim、gap |
| `beam_search_steel_orders()` | steel lengths | orders | 搜尋同一組鋼材的排列順序 |
| `beam_search_layout()` | config、combo | `SupportPlan[]` | 插入 shim/jack 並評估配置 |
| `_invalid_reason_statistics()` | plans | Counter | 彙整不合法原因 |
| `_log_support_candidate_diagnostics()` | config、metrics | `None` | 完整 Phase 1 診斷 |
| `log_support_candidate_diagnostics()` | config、record | `None` | 重播快取診斷 |
| `generate_single_support_candidates()` | config、search limits | plans | Phase 1 正式入口 |

### 全域最佳化

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `pair_penalty()` | 前後 `SupportPlan` | `(ok, penalty)` | 相鄰 jack 硬限制與區域差懲罰 |
| `build_global_solution()` | 每支候選、beam width | `GlobalSolution` | Phase 2 beam search |
| `fallback_global_solution()` | 每支候選 | invalid `GlobalSolution` | 全域無路徑時取各支最低分並加 5M |

## 6.5 `bracing_optimizer/algorithms/wales.py`

完整逐函式教學另見 `docs/wales/README.md`。

### 設定與工具

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `debug_print()` | 訊息 | `None` | `DEBUG=True` 才輸出細節 |
| `set_logger()` | callback | `None` | 設定 GUI logger |
| `generate_candidate_joint_points()` | total、min、step | points | 產生染色體候選點 |
| `Config.__post_init__()` | self | `None` | 補候選點與購買長度預設 |
| `classify_length()` | segment、config | short/mid/long/out | 保留舊 API，轉呼叫 `material_rules.classify_length()` |
| `is_joint_allowed()` | point、config | bool | forbidden/support 安全距離 |
| `expand_stock_items()` | qty stock | 單支庫存 | 展開庫存 |

### 解碼、驗證與評分

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `decode_individual()` | 0/1 individual、config | joints、segments | 染色體解碼 |
| `validate_segments()` | joints、segments、config | valid、errors | 硬限制 |
| `segment_ratio_summary()` | segments、config | counts、ratios | 短中長統計 |
| `calculate_ratio_penalty()` | segments、config | penalty、ratios | 目標比例偏差 |
| `allocate_stock_best_fit()` | segments、stock、lengths | allocation/None | 等長庫存優先，不足則 BUY |
| `evaluate_individual()` | individual、config、stock | result dict | Waler 評分中心 |

### Repair 與合法路徑

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `repair_individual()` | individual、config | repaired individual | 移除 forbidden、修短／長段、簡化接頭 |
| `is_joint_path_feasible()` | config | bool | 圖搜尋判斷終點可達 |
| `find_valid_joint_sequence()` | config、randomize | joints/None | memoized DFS 找合法路徑 |
| `build_valid_individual()` | config | 0/1 individual | 路徑轉染色體 |
| `create_individual()` | config | individual | build 後 repair |
| `initial_population()` | config | population | 建立初始族群 |

`repair_individual()` 內部 helpers：

| helper | 用途 |
|---|---|
| `to_individual()` | 接頭清單轉染色體 |
| `get_points()` | 加入固定起終點 |
| `get_segments()` | 節點轉段長 |
| `is_valid_selected()` | 重新解碼與驗證 |
| `count_preferred_short()` | 小於偏好最短長度的段數 |
| `remove_invalid_support_joints()` | 移除 forbidden joint |
| `try_remove_joint()` | 嘗試刪接頭；目前主流程未使用 |
| `fix_hard_short_once()` | 刪相鄰接頭合併硬性短段 |
| `fix_hard_long_once()` | 新增接頭拆分硬性長段 |
| `improve_preferred_short_once()` | 合併合法但不偏好的短段 |
| `simplify_joints_once()` | 合法時刪除不必要接頭 |

`find_valid_joint_sequence()` 內部 `dfs()` 使用 node index memo，成功回傳目前節點到終點的路徑。

### GA 與結果

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `tournament_selection()` | population、aligned eval、k | parent | 抽 k 個取最低分 |
| `crossover()` | parents、rate | two children | 單點交配 |
| `mutate()` | individual、rate | mutated copy | bit flip |
| `_reset_performance_counters()` | 無 | `None` | 重設評估與配料統計 |
| `_run_generations()` | population、config、stock | population、eval | elite→selection→交配→突變→repair→評估 |
| `_log_performance_statistics()` | counters | `None` | 平均 evaluate/allocate 耗時 |
| `_top_results()` | final eval、config | Top N | 有效優先、segments 去重、排序 |
| `evolve()` | config、stock、seed | result dict list | Waler 正式入口 |
| `build_neighbors()` | config | nodes、neighbors | 不含 forbidden filter 的診斷圖 |
| `diagnose_search_space()` | config、stock、sample count | `None` | 命令列搜尋空間報告 |
| `print_results()` | results | `None` | 命令列方案輸出 |

## 6.6 `main.py`

### 模組級函數

| 函數 | 輸入 | 輸出 | 用途 |
|---|---|---|---|
| `point_on_line_by_station()` | 線段、station | `(x,y)`/None | 將支撐測站轉成平面座標 |
| `load_ascii_art()` | code | text/None | 安全讀取 `picture/<code>.txt` |
| `calculate_ascii_art_font_size()` | 行數、最大寬度 | font size | 彩蛋視窗字體估算 |
| `_text_is_at_bottom()` | Text widget | bool | 新 log 是否自動跟隨到底部 |
| `main()` | 無 | `None` | Tk root 與 `SupportInputApp` 入口 |

### `SupportInputApp` 方法分組

| 方法群組 | 主要方法 | 輸入／輸出與責任 |
|---|---|---|
| 資料模型 | `_ensure_project_data()`、`walers/struts/braces/inventory` properties | 確保只有一份 `ProjectDataModel` |
| GUI 建立 | `__init__()`、`_build_ui()`、`_create_table_tab()`、`_create_cad_import_tab()`、`_create_test_cases_tab()`、`_create_results_tab()` | 建立主視窗與 tabs；回傳 `None` |
| 彩蛋 | `_on_ascii_art_*()`、`_show_ascii_art_window()` | code→picture text→最大化視窗 |
| 案例管理 | `_test_case_json_files()`、`_sanitize_test_case_name()`、`_test_case_path()`、`_refresh_test_case_list()`、`_selected_test_case_name()`、`_load_selected_test_case()`、`_delete_selected_test_case()`、`_save_current_test_case_from_prompt()`、`_build_test_case_payload()`、`save_test_case()`、`load_test_case()` | case name/path/payload；讀寫 JSON |
| 專案持久化 | `_new_project()`、`_save_current_project()`、`_save_project_as()`、`save_project_case()`、`load_project_case()`、`_relink_dxf()`、`_mark_project_dirty()` | 協調 serializer／asset manager，更新 GUI 與 Dirty；不自行做 hash 或幾何比對 |
| 結果互動 | `_on_results_tree_click()`、`_on_results_tree_space()`、`_on_results_tree_double_click()`、`_show_result_details()` | 切換顯示、展開、詳細資訊與雙擊編輯 |
| 支撐方案編輯 | `_support_config_by_id()`、`_support_plan_piece_rows()`、`_support_kind_*()`、`_replace_support_plan()`、`_recalculate_support_global_solution()`、`_find_support_forbidden_zone_hit()`、`_format_support_status()`、`_format_support_plan_breakdown()`、`_support_neighbor_penalty_for_plan()`、`_open_support_plan_editor()` | 編輯 pieces、重評單體與鄰支撐 penalty |
| 圍令方案編輯 | `_open_waler_plan_editor()`、`_apply_waler_plan_segments()`、`_recalculate_waler_plan()`、`_has_modified_waler_results()` | 直接編輯 Top 5 方案的鋼材順序，立即重算 score、工程合法性與預覽 |
| 結果 ID/群組 | `_result_group_iid()`、`_is_result_group_iid()`、`_support_plan_iid()`、`_is_support_plan_iid()`、`_parse_support_plan_iid()`、`_get_result_tree_info()`、`_get_result_group_entries()` | Treeview IID 與排序 |
| 顯示狀態 | `_result_group_visible_mark()`、`_result_item_visible_mark()`、`_support_plan_ids()`、`_support_plan_visible()`、`_support_group_visible_mark()`、`_toggle_result_group_visibility()`、`_toggle_result_visibility()`、`_toggle_support_plan_visibility()` | 管理方案可見性 |
| 結果格式 | `_format_result_value()`、`_format_result_list()`、`_format_waler_score_breakdown()`、`_format_result_details()`、`_describe_result_item()` | 結果與評分拆解文字 |
| Results tree | `_refresh_results_tree()`、`_store_result_item()` | result_items→階層 Treeview |
| 材料統計 | `_material_length_key()`、`_collect_visible_material_usage()`、`_collect_inventory_quantities()`、`_update_material_summary()` | 可見方案材料用量、庫存、剩餘量 |
| Excel 匯出 | `_export_visible_results_to_excel()` | 可見唯一方案→逐根材料明細與鋼材庫存彙總 `.xlsx` |
| Preview 建立 | `_build_preview()`、`_format_preview_coordinates()`、`_capture_preview_home_view()`、`_get_preview_zoom_percent()` | Figure/Canvas/Toolbar |
| Preview 效能 | `_begin_preview_interaction()`、`_begin_preview_pan_interaction()`、`_end_preview_interaction()`、`_on_preview_scroll()`、`_schedule_preview_scroll_redraw()`、`_flush_preview_scroll_redraw()`、`_cancel_preview_scroll_redraw()` | 文字隱藏、scroll debounce、pan throttle 協調 |
| 圖片匯出 | `_ask_export_scale()`、`_export_preview_image()` | scale→PNG/JPEG；先重建完整圖面 |
| DXF 匯出 | `_visible_dxf_export_plans()`、`_export_visible_results_to_dxf()` | 可見結果＋保存工程模型→乾淨 R2018 世界座標成果 DXF |
| CAD polling | `_schedule_cad_event_poll()`、`_poll_cad_event()`、`_set_cad_import_status()`、`_refresh_cad_import_status()`、`_toggle_cad_import()`、`_manual_read_cad_event()` | 500 ms 自動或手動讀取 |
| CAD apply | `_project_rows_by_table()`、`_invalidate_solver_state_after_input_change()`、`_handle_input_data_changed()`、`_select_input_row()`、`_apply_cad_event()`、`read_cad_event()` | mapper row→正式 model→ack→重畫 |
| 表格資料 | `_load_initial_data()`、`_refresh_tree()`、`_format_display_value()`、`_format_position_value()`、`_format_position_list()`、`_migrate_strut_position_fields()`、`_parse_position_list()` | Model 與 Treeview 同步 |
| 表格編輯 | `_on_tree_double_click()`、`_finish_edit()`、`_item_id_to_index()`、`_get_table_name_by_tree()`、`_parse_cell_value()`、`add_row()`、`delete_row()`、`_move_current_table_row()`、`move_selected_row()` | cell edit、CRUD、排序 |
| 驗證 | `validate_data()`、`_clear_error_tags()`、`_tag_error_row()`、`_has_duplicate_numbers()` | 所有工程資料檢查；回 bool |
| 幾何 helper | `_waler_coords()`、`_point_on_waler_segment_with_tolerance()`、`_walers_are_nearly_parallel()`、`_line_is_nearly_perpendicular_to_waler()`、`_to_number()`、`_line_length()`、`_line_length_positive()`、`_readable_line_angle()`、`_waler_direction_unit()` | 平面幾何與安全轉數字 |
| 基礎圖面 | `_draw_segment_length_label()`、`_draw_strut_angle_brace()`、`update_preview()` | 繪製輸入圍令、支撐、斜撐、托梁、中間柱與角撐 |
| 結果疊圖 | `_draw_result_overlays()`、`_draw_single_waler_solution_overlay()`、`_draw_support_solution_overlay()` | 只疊加可見結果 |
| Inventory 顯示 | `_inventory_quantity()`、`_update_material_summary()` | 透過 `InventoryLookup` 取得數量並呈現 |
| Solver 開啟 | `_open_waler_solver()`、`_open_support_solver()` | validate→Builder→選擇／建立 Dialog |
| Solver 結果 | `_store_support_solution()`、`_store_waler_result()` | callback 結果→result_items |
| 應用生命週期 | `_on_main_window_close()`、`_on_tab_changed()`、`show_result()`、`_set_window_size()` | 停止 polling、切換 tab、append log、視窗尺寸 |

### Dialog 與 thread 方法

| 類別 | 重要方法 | 用途 |
|---|---|---|
| `PreviewNavigationToolbar` | `drag_pan()`、`_flush_pending_pan()`、`release_pan()` | 40 ms 平移節流與最後事件套用 |
|  | `set_zoom_percent()`、`sync_zoom_display()`、`set_message()` | 工具列狀態 |
|  | `home()`、`save_figure()` | 全圖及自訂匯出 |
| `WalerSelectionDialog` | `_on_ok()`、`_on_cancel()`、`open()` | 回傳 WalerID 或 None |
| `ZoningSelectionDialog` | `_on_ok()`、`_on_cancel()`、`open()` | 回傳 Zoning 或 None |
| `TextRedirector` | `write()`、`_flush_queue()`、`flush()` | thread-safe GUI log |
| `SupportSolverDialog` | `_run_solver()`、`_solver_thread()`、`_display_solution()` | 收集比例、背景呼叫 Use Case、顯示與結果 callback |
| `WalerSolverDialog` | `_build_solver_key()`、`_ask_use_memory_result()`、`_save_solver_memory()`、`_restore_solver_memory()` | 本次執行記憶 |
|  | `_run_solver()`、`_solver_thread()` | 建 Config 並背景執行 GA |
|  | `_waler_ratio_targets()`、`_waler_segment_counts()`、`_with_waler_display_metadata()` | 補顯示 metadata |
|  | `_display_results()`、`_format_plan_summary()` | Top 5 顯示與 callback |

---

# 7. Support Solver 流程

支撐 Solver 分成兩階段。

## 7.1 固定工程參數

```text
預設 STEEL_LENGTHS = 1000～10000，每 500 mm（舊專案 fallback）
JACK_LENGTH = 600
SHIM_LENGTHS = 0, 100, 150, 200, 300
MAX_GAP = 150
TARGET_GAP = 80
MIN_END_CLEAR = 1600
PILE_FORBIDDEN_HALF = 830
WALER_FORBIDDEN_HALF = 550
MIN_JACK_DISTANCE_BETWEEN_SUPPORTS = 600
```

正式執行時，預設資料流為 `inventory.json → JsonInventoryRepository → 設定頁籤 → Solver`。Solver 不直接讀取 Excel 或 JSON，而是使用目前專案設定中，符合用途與已選規格的庫存列。`Length` 供候選生成，`Qty` 供既有庫存配置與缺料評分；評分公式未改變。規格未選時不檢查庫存，結果數量統一顯示 `99`。

## 7.2 Phase 1：每根支撐候選

```text
SupportConfig
      │
      ▼
generate_length_combinations_dp()
      │
      ├─ steel multiset
      ├─ shim
      └─ gap
      │
      ▼
beam_search_steel_orders()
      │
      ▼
beam_search_layout()
      │
      └─ 依圍令材料規格推導施工規則並直接生成合法 shim／jack 位置
      │
      ▼
evaluate_single_support()
      │
      ▼
只保留 target_jack_region
      │
      ▼
generate_single_support_candidates()
```

### `generate_length_combinations_dp()`

使用 DP 依總和保存鋼材 multiset。sequence 維持非遞減，避免同一 multiset 重複排列。

DP state 初步分數：

```text
鋼材支數 × 1000 + 短鋼材數 × 10
```

加入 shim/gap 後排序分數：

```text
DP score + gap × 3 + shim × 1
```

這個分數只用於候選搜尋排序，不是最終 `SupportPlan.score`。

### `beam_search_steel_orders()`

同一組鋼材可能因排列不同產生不同接頭位置。此函式用 beam search 避免全排列爆炸。

heuristic 偏好：

- 第一支不要小於 4000。
- 最後一支不要小於 4000。
- 避免最後兩支都是短料。
- 整體減少短料。

### `beam_search_layout()`

針對每個鋼材順序：

- Steel Waler：只生成 jack 與 shim 相鄰的排列。
- RC Waler：只生成 shim 位於 RC 接觸面的排列。
- 兩端皆為 RC 時，直接生成 shim 位於任一端接觸面的兩組合法空間。
- shim = 0 時不建立 shim piece，jack 仍可位於各鋼材間隙。
- 每個 pieces tuple 去重。
- 呼叫 `evaluate_single_support()`。
- 依最終單支分數排序並截斷。

使用者只選擇 `material_spec`。規格為 `RC` 時內部採 RC 圍令施工規則；其他鋼材規格或未指定時採鋼圍令規則。這個內部推導值只限制 Layout Generation 的生成空間，不進入單體評分、Pattern、Material Ratio、Spec Distribution 或 Phase 2 評分。

RC 接觸面上的終端調整塊界面不套用該側 `MIN_END_CLEAR` 端部禁止區；這項豁免不延伸到下一個接頭，也不忽略樁位或托梁禁止區。

### `generate_single_support_candidates()`

依 DP 組合順序逐批建立 layout，直到：

- 合法且符合目標 jack region 的候選數已足夠；或
- 組合已用盡。

只把：

```text
plan.valid
and not plan.reason
and plan.jack_region_id == target_jack_region
```

當成正式候選。

### 雙路支撐候選交集

同一個 `SharedLayoutGroup` 必須剛好包含兩支實體支撐，且兩支必須具有相同的
Zoning、材料規格、FromWaler 與 ToWaler 方向。Phase 1 仍分別檢查兩支支撐各自的
中間柱、托梁與端部條件，之後以 ordered `(piece kind, length)` 取候選交集；沒有共同
排列時不進入 Phase 2。

兩支支撐的材料會分別計數，因此同一組配置需要兩套材料。雙路群組內的兩個 Jack
允許位於相同測站，不套用一般相鄰支撐的 600 mm Jack 間距；群組與前後其他支撐仍
照常檢查間距。手動修改群組任一成員時，同一組的另一成員會一起重新套用並各自驗證。

## 7.3 Phase 2：多支支撐全域解

```text
candidates_by_support
          │
          ▼
build_global_solution()
          │
          ├─ 依支撐表順序逐支擴展
          ├─ 雙路群組只接受相同 ordered pieces
          ├─ pair_penalty()
          ├─ 保留最低分 beam
          └─ 找不到路徑時 fallback
```

每個 beam state：

```python
(累積分數, 已選 SupportPlan 清單)
```

若任何階段 beam 清空，呼叫 `fallback_global_solution()`：

- 每支取最低單體分數。
- 總分加 `5,000,000`。
- `valid=False`。

---

# 8. Waler Solver 流程

## 8.1 接頭型染色體

```text
candidate_joint_points = [1000, 1500, 2000, ...]
individual             = [   0,    1,    0, ...]
```

gene `1` 表示選擇該候選接頭。

```text
individual
↓ decode_individual()
joints
↓ 相鄰位置相減
segments
```

## 8.2 硬限制

`validate_segments()` 檢查：

- 中間接頭不得進入 forbidden/support 安全距離。
- 段長不得小於 `min_piece_length`。
- 段長不得大於 `max_piece_length`。
- 段長必須剛好存在於 `purchasable_lengths`。

## 8.3 初始合法方案

```text
is_joint_path_feasible()
      │
      ▼
find_valid_joint_sequence()
      │ memoized DFS
      ▼
build_valid_individual()
      │
      ▼
repair_individual()
      │
      ▼
initial_population()
```

正式 path search 在建圖前就排除不通過 `is_joint_allowed()` 的中間候選點。

## 8.4 Repair

```text
移除 forbidden joint
↓
修硬性短段：刪相鄰接頭合併
↓
修硬性長段：新增候選接頭拆段
↓
改善小於 preferred min 的合法短段
↓
刪除不必要接頭
↓
仍不合法則重新 build_valid_individual()
```

目前沒有專門局部修補「在 min/max 內但不是可購買長度」的段，這種情況可能直接走 fallback。

## 8.5 GA

```text
初始 population 評估
↓
每代依 score 排序
↓
保留 elite
↓
tournament_selection()
↓
crossover()
↓
mutate()
↓
repair_individual()
↓
新 population 單次評估
↓
下一代
```

`evaluated_for_population` 與 population index 對齊，供 tournament 使用；`sorted_evaluated` 只供 elite 排名。

評估次數約為：

```text
population_size × (generations + 1)
```

## 8.6 最終輸出

`_top_results()`：

1. 有有效方案時排除 invalid。
2. 以 `tuple(segments)` 去重。
3. 相同分段保留低分者。
4. 依 score 排序。
5. 回傳 Top N，GUI 目前顯示前五名。

---

# 9. CAD Builder 流程

## 9.1 AutoLISP 指令

| 指令 | 功能 |
|---|---|
| `ADDWALER` | 點選圍令起點、終點 |
| `ADDSTRUT` | 點選支撐起終點，選填托梁與中間柱測站 |
| `UPDSTRUT` | 輸入既有 StrutID，重新點選支撐及托梁／中間柱測站 |
| `ADDBRACE` | 點選斜撐起點、終點 |
| `SUPSTATUS` | 顯示 TEMP 路徑及 pending 狀態 |

沒有 `ADDSUPPORT`；支撐使用 `ADDSTRUT`。

## 9.2 座標系

`getpoint` 保留執行指令當下的 UCS 操作；起終點與測站選點都會在運算及寫入 JSON 前使用 `(trans point 1 0)` 轉成 WCS。

因此建議：

```text
getpoint（UCS）
↓ trans point 1 0
TEMP JSON（WCS）
↓ CoordinateSystem.transform()
Project world/local 座標
```

## 9.3 TEMP 路徑

Python：

```python
Path(tempfile.gettempdir()) /
"support_distribution_uv_cad_builder_temp.json"
```

AutoLISP：

1. 優先 `(getenv "TEMP")`
2. fallback `(getvar "TEMPPREFIX")`

一般路徑：

```text
C:\Users\<登入使用者>\AppData\Local\Temp\
support_distribution_uv_cad_builder_temp.json
```

CAD 與 Solver 應使用同一 Windows 帳號及權限層級。

## 9.4 目前實作的事件生命週期

目前 LISP 實際流程：

```text
若正式 JSON 已存在
    → 顯示 pending，拒絕覆寫
否則
    → 寫入正式 JSON
```

Python 成功匯入後：

```text
acknowledge(event)
↓
再次讀目前檔案
↓
event_id 相同才刪除
```

## 9.5 Strut 測站

托梁與中間柱點會投影到支撐方向：

```text
station =
((selected-start) · (end-start))
/ 支撐長度
```

最後四捨五入成整數，輸出逗號字串：

```json
"BeamPositions": "3500,7000",
"ColumnPositions": "5000,10000"
```

---

# 10. GUI 架構

## 10.1 主視窗

主視窗是左右 PanedWindow：

```text
左側：輸入、案例、結果 tabs
右側：Matplotlib preview
下方：操作按鈕與累積求解訊息
```

左側 Notebook tabs：

1. 圍令
2. 支撐
3. 斜撐
4. 庫存
5. CAD 匯入
6. 專案
7. 測試案例
8. 結果

## 10.2 資料表畫面

共同功能：

- 新增列
- 刪除選取列
- 上移／下移
- 雙擊 cell 編輯
- 錯誤列紅底
- 驗證資料
- 更新圖面

## 10.3 CAD 匯入畫面

顯示：

- 是否自動接收
- 實際事件檔路徑
- 目前狀態
- 最近事件
- 最近錯誤
- 立即讀取
- 重新顯示狀態

## 10.4 專案畫面

功能：

- 新增、開啟、儲存及另存專案。
- 儲存時才建立 `source/source.dxf` 管理副本；單純匯入 DXF 不會建立永久副本。
- 顯示 Dirty、DXF 管理副本、外部原始來源、構件匹配及 Solver 保留狀態。
- 重新連結 DXF；完全相同使用 SHA-256，版本不同則使用構件工程線與集中容許誤差比對。
- 視窗標題的 `*` 表示有尚未儲存的變更。

專案資料夾：

```text
project_cases/
└─ 專案名稱/
   ├─ project.json
   ├─ project.json.bak
   └─ source/
      └─ source.dxf
```

舊版 `project_cases/專案名稱.json` 仍可直接開啟；重新儲存後會建立上述資料夾格式，舊檔保留作為相容來源。

## 10.5 測試案例畫面

功能：

- 列出 EXE 同層 `test_cases/*.json`
- 載入案例
- 將目前資料存為案例
- 刪除案例

## 10.6 結果畫面

以群組顯示：

- WalerID 下的 Top 5 方案
- Zoning 下的各支支撐

功能：

- 群組或單案顯示切換
- 雙擊圍令方案直接編輯鋼材長度與順序
- 編輯支撐 piece 順序
- 圍令方案新增／刪除鋼材及上移／下移
- 修改後立即檢查合法性、重新計分並更新預覽
- 依可見方案更新材料統計

## 10.7 Solver Dialog

### Waler

固定資訊：

- 圍令 ID、起終點、總長
- 禁止點數量與清單
- 候選接頭點數
- 安全距離
- min/max 段長
- 可購買材料
- 評分權重

執行設定：

- generations
- population size
- 短中長比例

### Support

固定資訊：

- Zoning
- 支撐數量與 ID
- 重複幾何設定數
- 目標 jack region 統計

執行設定：

- 鋼材組合探索數
- 合法候選保留數

兩個 Solver 都在 daemon thread 中運算，GUI log 經 `TextRedirector` 回到 Tk 主執行緒。

---

# 11. JSON 格式

## 11.1 CAD event envelope

共同格式：

```json
{
  "event_id": "唯一事件識別",
  "type": "waler | strut | brace",
  "data": {}
}
```

### Waler

```json
{
  "event_id": "example-waler-001",
  "type": "waler",
  "data": {
    "StartX": 0,
    "StartY": 0,
    "EndX": 12000,
    "EndY": 0
  }
}
```

### Strut

```json
{
  "event_id": "example-strut-001",
  "type": "strut",
  "data": {
    "StartX": 0,
    "StartY": 0,
    "EndX": 12000,
    "EndY": 0,
    "BeamPositions": "3500,7000,10500",
    "ColumnPositions": "5000,10000",
    "TargetJackRegion": 2
  }
}
```

### Brace

```json
{
  "event_id": "example-brace-001",
  "type": "brace",
  "data": {
    "StartX": 2500,
    "StartY": 1000,
    "EndX": 6500,
    "EndY": 4500
  }
}
```

ID 不由 LISP 提供。Mapper 根據目前資料產生：

```text
W1, W2...
S1, S2...
B1, B2...
```

規則是相同 prefix 的最大數字加一，不主動補中間缺號。

## 11.2 正式資料列 schema

### Waler

```json
{
  "WalerID": "W1",
  "StartX": 0,
  "StartY": 0,
  "EndX": 12000,
  "EndY": 0,
  "material_spec": "H350x350",
  "Remark": ""
}
```

### Strut

```json
{
  "StrutID": "S1",
  "SharedLayoutGroup": "G1",
  "FromWaler": "W1",
  "ToWaler": "W2",
  "StartX": 0,
  "StartY": 0,
  "EndX": 12000,
  "EndY": 0,
  "BeamPositions": "3500,7000",
  "ColumnPositions": "5000,10000",
  "FromBraceToWalerStartLen": 0,
  "FromBraceToWalerEndLen": 0,
  "ToBraceToWalerStartLen": 0,
  "ToBraceToWalerEndLen": 0,
  "TargetJackRegion": 2,
  "Zoning": "A"
}
```

`SharedLayoutGroup` 為空時是一般單支撐；相同非空群組值必須剛好出現兩次。DXF
匯入以中心線距離 `1000 ± 150 mm`、平行角度、投影重疊率及長度差產生候選；若同一
支撐有多個可能配對，預設不採用並要求人工選擇。反向繪製的第二支在轉成正式 row
時會連同測站與角撐端欄位一起翻轉，確保兩支使用同一個 FromWaler → ToWaler 方向。

### Brace

```json
{
  "BraceID": "B1",
  "FromWaler": "W1",
  "ToWaler": "",
  "StartX": 0,
  "StartY": 0,
  "EndX": 3000,
  "EndY": 3000
}
```

### 支撐內的 Column／Beam 位置

```json
{
  "StrutID": "S1",
  "ColumnPositions": "5000,10000",
  "BeamPositions": "3500,7000",
  "AssociatedColumnIDs": "C1,C2",
  "AssociatedBeamIDs": "BM1,BM2"
}
```

Solver 的正式輸入是每支 Strut 上的 station。`AssociatedColumnIDs`／
`AssociatedBeamIDs` 只保留匯入標籤；完整 DXF 幾何留在 `dxf_import_state`。

## 11.3 Inventory

```json
{
  "inventory": [
    {
      "ItemCode": "MAT-001",
      "Spec": "H350x350",
      "Usage": "支撐",
      "Length": 9500,
      "Qty": 0
    }
  ]
}
```

規則：

```text
已選 Spec + Usage 的所有有效 Length → purchasable_lengths
同規格且 Qty > 0                         → stock_items
未選規格                                  → 不檢查庫存，Qty = 99
```

因此已選規格時，`Qty=0` 仍代表可以購買該長度。庫存列保留機料編號、規格、用途、長度與數量，但 Solver 查詢邊界只取得指定用途與規格的可用材料。

目前預設庫存由「機料庫存.json」轉換：326 筆原始資料中納入 229 筆支撐樑與圍令樑本體，排除 28 筆調整塊與 69 筆其他機料。轉換時將 `H400*408` 正規化為 `H400x408`，並將 `L=4.5M` 轉為 `4500` mm。調整塊不會被當作一般 Solver 鋼料；AN／BN 不同機料編號則各自保留。

## 11.4 材料規格

```json
{
  "material_specs": [
    {"Usage": "支撐", "Spec": "H350x350"},
    {"Usage": "圍令", "Spec": "RC"}
  ]
}
```

材料規格表不含長度。「設定」頁籤內分為「材料規格」與「庫存」；支撐與圍令只能從對應用途的規格下拉選擇，不接受自由輸入。圍令 `RC` 為必要規格，資料模型會自動補回，UI 也不允許修改或刪除。規格名稱供專案設定、圖面標示與報表，不是新的評分因子；材料長度仍由獨立 `inventory` 表管理。

## 11.5 案例 JSON

簡化結構：

```json
{
  "schema_version": 1,
  "case_name": "案例名稱",
  "data": {
    "walers": [],
    "struts": [],
    "braces": []
  },
  "derived": {
    "waler_inputs": {}
  },
  "solver_settings": {
    "waler": {},
    "support": {},
    "export": {}
  },
  "parameters": {
    "support_solver": {}
  }
}
```

目前載入時真正套用的主要內容是：

```text
data.walers
data.struts
data.braces
```

Inventory 不儲存在案例 `data` 中，也不會因載入案例而被替換；它維持目前或預設 Inventory。

`derived`、`solver_settings`、`parameters` 目前會寫入檔案，但 `load_test_case()` 沒有把它們重新套回 runtime 設定，主要屬於紀錄資訊。

## 11.5 專案 JSON 與 DXF 資產

專案使用 `schema_version: 3`。`dxf_import_state` 繼續保存既有的純資料辨識狀態；DXF 檔案完整性與管理位置由 `dxf_asset` 單獨負責：

```json
{
  "schema_version": 3,
  "project_information": {
    "project_name": "Y1A站第一層支撐",
    "saved_at": "2026-08-12T15:30:00",
    "application": "SupportSolver"
  },
  "input_data": {
    "walers": [],
    "struts": [],
    "braces": []
  },
  "dxf_asset": {
    "storage_mode": "managed_copy",
    "relative_path": "source/source.dxf",
    "original_path": "D:/Project/Y1A.dxf",
    "original_file_name": "Y1A.dxf",
    "sha256": "完整的 SHA-256",
    "file_size": 123456,
    "modified_time": 1786519800.0
  },
  "dxf_import_state": {
    "source_path": "D:/Project/Y1A.dxf",
    "coordinate_system": {
      "mode": "local",
      "origin_x": 338238.287,
      "origin_y": -724845.57,
      "source": "user_origin"
    },
    "layer_classification": {},
    "converted": {
      "walers": [],
      "struts": [],
      "braces": [],
      "columns": [],
      "beams": [],
      "corner_braces": []
    }
  },
  "result": {}
}
```

純手動專案的 `dxf_asset` 與 `dxf_import_state` 均可為 `null`。JSON 不保存 Base64 DXF，也不保存 `ezdxf` 的 Document、Entity、Layout 或 Block 執行階段物件。

Application 只接受 schema 3，不在載入時自動轉換舊格式。受版本控制的舊專案可一次執行：

```powershell
.\.venv\Scripts\python.exe tools\upgrade_project_schema.py --no-backup project_cases\舊專案.json
```

工具會從既有 `dxf_import_state` 提取可確認的 Column／Beam 幾何；無法恢復幾何時只建立 `Source: legacy` 的未連結障礙，不猜測或捏造構件。

交易式儲存順序：

```text
驗證目前 DXF
→ 複製 source.dxf.tmp 並核對 SHA-256
→ 寫入及重新解析 project.json.tmp
→ 備份既有 project.json.bak
→ 原子替換 source/source.dxf
→ 原子替換 project.json
```

若 JSON 正式替換失敗，程式會把 DXF 回復成原版本；所有失敗都保留 Dirty。管理副本遺失時，只有 `original_path` 的 SHA-256 完全相同才會自動修復，否則必須重新連結。

---

# 12. 評分系統

所有 Solver 都是「分數越低越好」。

## 12.1 Support 單支評分

硬限制：

- 必須恰好一個 jack。
- `0 <= gap <= 150`。
- 接頭不得落入端部、pile 或 waler forbidden zone。
- steel 長度必須存在於 `STEEL_LENGTHS`。

軟性評分：

```text
short_penalty
    = 小於 4000 的鋼材數 × 8,000

joint_penalty
    = 接頭數 × 1,200

gap_penalty
    = |gap - 80| × 20

jack_edge_penalty
    = jack center 距任一端小於 2500 時加 5,000
```

不合法時：

```text
invalid_penalty =
    1,000,000
  + forbidden_count × 100,000
  + 超出 gap 下限的量 × 1,000
  + 超出 gap 上限的量 × 1,000
```

最後：

```text
SupportPlan.score =
    short_penalty
  + joint_penalty
  + gap_penalty
  + jack_edge_penalty
  + invalid_penalty
```

## 12.2 Support pair penalty

相鄰支撐 jack center 距離：

```text
distance < 600
→ 硬性淘汰，回傳 False / 1,000,000
```

區域不同：

```text
pair penalty =
3,000 × |前一支 region - 後一支 region|
```

全域分數：

```text
所有單支 SupportPlan.score
+ 所有相鄰 pair penalty
```

## 12.3 Waler 評分

硬性幾何／材料長度無效：

```text
1,000,000 + errors × 50,000
```

無法配料：

```text
800,000 + joints × 1,000
```

有效方案：

```text
buy_count × 100,000
+ ratio_penalty
+ under_4000_segment_count × 100,000
+ distinct_groups × 5,000
+ length_variation
+ joint_count × 1,000
```

比例懲罰：

```text
(
  |實際短段比例 - 目標短段比例|
+ |實際中段比例 - 目標中段比例|
+ |實際長段比例 - 目標長段比例|
)
× 100,000
```

材料配置目前只接受庫存長度與段長完全相同。庫存不足但該長度可購買時產生 `BUY-長度`。

## 12.4 圍令方案直接編輯

`bracing_optimizer.application.plan_editing.WalerPlanEditing` 負責重算 Waler score，
並透過 `validate()` 檢查：

- 總長是否等於圍令需求長。
- 接頭是否進 forbidden zone。
- 每段是否為可購買長度。
- min/max 段長。
- 庫存不足警告。

結果頁中的 Top 5 圍令方案可直接雙擊編輯。編輯器提供新增鋼材、刪除鋼材、
上移、下移與雙擊更換料長；每次操作立即更新原方案、合法性、分數和圖面預覽。
修改後以 `[已修改]` 標示，不再另外建立自訂方案。

`main.py` 現在只委派給這個 data-only service。Application 與演算法層之間仍有一份
評分公式重複，未來可再收斂回 `algorithms/wales.py` 的單一 API。

---

# 13. 圖面輸出

## 13.1 Matplotlib Preview

`update_preview()` 繪製：

- 圍令：黑色粗線與 `WalerID`
- 支撐：黑色粗線與 `StrutID`
- 斜撐：橘色虛線與 `BraceID`
- 托梁位置：紫色 scatter
- 中間柱位置：綠色 scatter
- 支撐角撐：依欄位方向繪製
- 圖例、座標、物件數統計

Beam 與 Column 點先收集，再各自呼叫一次 `scatter()` 批次繪製。

## 13.2 Solver overlay

可見 Waler result：

- 將 segment 沿原圍令方向轉回平面線段。
- 不同分段使用不同顏色。
- 顯示接頭位置。

可見 Support result：

- 依 pieces 將 steel、shim、jack 沿支撐方向繪製。
- 可個別切換同一 Zoning 中每支支撐。

## 13.3 平移與縮放效能

- 平移事件每 40 ms 處理一次。
- 滾輪採 debounce。
- 互動期間暫時隱藏所有 axes text、ticks、title、labels 與 legend。
- 操作停止後恢復並完整 redraw。
- `preserve_view=True` 時資料更新保留目前 x/y 範圍。

## 13.4 圖片輸出

工具列「儲存」會呼叫 `_export_preview_image()`：

1. 選擇 100%～400% 輸出倍率。
2. 選擇 PNG 或 JPEG。
3. 先呼叫 `update_preview()` 重建完整圖面。
4. 暫時調整 Figure 尺寸。
5. `figure.savefig()`。
6. 還原使用者原本視角與 Figure 大小。

基準：

```text
16 × 10 inches
100 dpi
100% = 1600 × 1000 px
400% = 6400 × 4000 px
```

## 13.5 材料統計

結果頁不是材料統計圖，而是表格：

```text
料長
使用數量
庫存數量
剩餘數量
```

剩餘數量小於零會標紅。

統計只包含目前可見結果，且庫存比較只計鋼材。Waler 優先使用方案的 `pieces`；舊資料沒有 `pieces` 時依序 fallback `segments` 與 assignments 的 stock length。Support 只計 `pieces` 中的 steel；jack、shim 與 gap 不納入鋼材庫存差額。

## 13.6 Excel 材料明細輸出

「配置結果」頁的 Excel 按鈕不依賴 DXF，只匯出目前勾選為可見且每個構件唯一的方案。`project_results.py` 先建立一件材料一列的標準資料，包含材料用途、構件編號、成果方案、分區、段次、材料類型、材料規格、長度與數量；鋼材、調整塊、千斤頂會列入明細，gap 不列入。`excel_result_export.py` 再產生「材料明細」與「材料彙總」兩張工作表，設定標題、篩選、凍結窗格、數字格式及缺料標示，並以同資料夾暫存檔驗證後原子替換正式 `.xlsx`。

## 13.7 DXF 配置標註輸出

結果頁的「匯出支撐配置成果DXF」會：

1. Main 從 `dxf_import_state.coordinate_system` 只提取 Project → WCS 座標 metadata；不開啟原始 DXF，也不使用 converted Waler／Strut／Brace 配對成果。
2. 新建 R2018／毫米的 clean document，將目前 `ProjectDataModel` 的圍令、支撐、斜撐畫在 `SD_PROJECT_WALER`、`SD_PROJECT_STRUT`、`SD_PROJECT_BRACE`。原圖連續壁、角撐、中間柱、托梁與輔助線是 optional background；合法來源圖層會沿用，非法、空白或與正式層衝突時改用 `SD_BASE_*` fallback。
3. 直接以目前 Project world line 放置 Solver 結果。圍令標註位於 `SD_RESULT_WALER`；支撐標註與千斤頂位於 `SD_RESULT_SUPPORT`。鋼材用一般對齊尺寸、調整塊用「調整塊」尺寸、尾端現場處理長度用「餘量」尺寸。
4. 千斤頂只從 `assets/dxf/jack_symbol.dxf` 複製允許的 `LINE`／`CIRCLE` 幾何建立 `SUPPORT_JACK`，Block 內圖元位於 `0` 層，INSERT 位於支撐成果層，且不另加尺寸標註。
5. 先寫入輸出資料夾內唯一暫存檔，再從磁碟重新讀取，執行 Audit、世界座標、成果數量、圖層、Block definition、重複 Layer、XRecord 與裸 Handle reference 驗證；只有全部通過才交易式替換正式檔。

Dimension 不直接在大世界座標下 render。每支構件先以自身起點建立 Local Support Geometry，在局部座標完成 Dimension geometry 與匿名 Block render，再以純平移矩陣將 Dimension 定義點及 Block 內 `LINE`、`MTEXT`、`SOLID`、`INSERT` 等實體統一轉回世界座標。最終驗證也會比對匿名 Block 的實際顯示文字，避免 Dimension 量測值正確但畫面文字受浮點誤差影響。

只匯出結果樹目前勾選為可見的方案。同一構件若同時勾選兩個方案，匯出會停止並要求只保留一個可見方案。

原始 DXF 或專案管理副本遺失、converted binding stale、或舊 DXF Review 留有 error／critical 訊息，都不會否定合法的 Current Project + Solver Result。背景不完整時只略過有問題的背景項目並在報告列出 warning。schema 3 若完全缺少可證明的 Project → World 座標資訊，Main 會明確停止；底層 exporter 則可由呼叫端明確傳入 world context，在沒有任何 background state 時輸出 Project + Solver。成果檔採世界座標與毫米單位；合併回原始 DWG 時，先確認目標單位為毫米，再使用 Insert、Xref 或貼到原始座標，避免額外縮放、旋轉或位移。

---

# 14. 模組相依與 Call Graph

## 14.1 Python import 關係

```text
main.py
├─ bracing_optimizer/application/
│  ├─ optimize_waler.py
│  ├─ optimize_support_zone.py
│  ├─ solver_input_builder.py
│  ├─ plan_editing.py
│  ├─ project_data.py
│  ├─ project_mapper.py
│  ├─ project_results.py
│  ├─ project_service.py
│  └─ project_validation.py
├─ bracing_optimizer/algorithms/
│  ├─ wales.py
│  ├─ support.py
│  └─ solver_search.py
├─ bracing_optimizer/domain/
│  ├─ project_domain.py
│  └─ material_rules.py
├─ bracing_optimizer/infrastructure/
│  ├─ cad_builder.py
│  ├─ dxf_result_export.py ─► assets/dxf/jack_symbol.dxf
│  ├─ excel_result_export.py ─► openpyxl
│  ├─ inventory_repository.py
│  └─ project_persistence.py
├─ bracing_optimizer/presentation/
├─ tkinter
└─ matplotlib

tests/test_cad_builder_integration.py
├─ main.py
├─ bracing_optimizer/application/project_data.py
└─ bracing_optimizer/infrastructure/cad_builder.py
```

`bracing_optimizer/algorithms/` 與 `bracing_optimizer/domain/` 不 import `main.py` 或
`bracing_optimizer/presentation/`，因此 Solver 與 Domain 不依賴 GUI。

## 14.2 Waler call graph

```text
SupportInputApp._open_waler_solver()
└─ validate_data()
└─ WalerInputBuilder.build_all()
└─ WalerSelectionDialog.open()
└─ WalerSolverDialog
   └─ _run_solver()
      └─ OptimizeWalerRequest
      └─ threading.Thread
         └─ _solver_thread()
            └─ OptimizeWaler.execute()
               └─ wales.Config
               └─ wales.evolve()
               ├─ initial_population()
               │  └─ create_individual()
               │     ├─ build_valid_individual()
               │     │  ├─ is_joint_path_feasible()
               │     │  └─ find_valid_joint_sequence()
               │     └─ repair_individual()
               ├─ _run_generations()
               │  ├─ evaluate_individual()
               │  ├─ tournament_selection()
               │  ├─ crossover()
               │  ├─ mutate()
               │  └─ repair_individual()
               └─ _top_results()
            └─ WalerSolverDialog._display_results()
               └─ SupportInputApp._store_waler_result()
```

## 14.3 Support call graph

```text
SupportInputApp._open_support_solver()
└─ validate_data()
└─ ZoningSelectionDialog.open()
└─ SupportInputBuilder.build_zone()
└─ SupportSolverDialog
   └─ _run_solver()
      └─ OptimizeSupportZoneRequest
      └─ threading.Thread
         └─ _solver_thread()
            └─ OptimizeSupportZone.execute()
               ├─ get_support_config_key()
               ├─ generate_single_support_candidates()
               │  ├─ generate_length_combinations_dp()
               │  ├─ beam_search_layout()
               │  │  ├─ beam_search_steel_orders()
               │  │  └─ evaluate_single_support()
               │  └─ log_support_candidate_diagnostics()
               └─ build_global_solution()
                  ├─ pair_penalty()
                  └─ fallback_global_solution()
            └─ _display_solution()
               └─ SupportInputApp._store_support_solution()
```

## 14.4 CAD call graph

```text
SupportInputApp._schedule_cad_event_poll()
└─ _poll_cad_event()
   └─ read_cad_event()
      ├─ TempEventWatcher.check_new_event()
      │  └─ CadEventReader.load()
      └─ _apply_cad_event()
         ├─ CadEventMapper.map_event()
         │  └─ CadEventMapper.build_row()
         │     └─ project_data.build_input_row()
         │        └─ next_identifier()
         ├─ rows.append()
         ├─ TempEventWatcher.acknowledge()
         ├─ _refresh_tree()
         └─ _handle_input_data_changed()
```

---

# 15. 待重構區域與改善建議

本節記錄目前程式碼觀察，不代表必須一次全部重寫。

## 15.1 `main.py` 與 `SupportInputApp` 過大

目前：

```text
main.py：約 5,974 行
SupportInputApp：約 4,600 行
方法：約 200 個
```

建議拆分：

```text
ui/
├─ main_window.py
├─ table_controllers.py
├─ result_controller.py
├─ preview_controller.py
├─ case_controller.py
├─ cad_import_controller.py
└─ solver_dialogs.py
```

## 15.2 `wales.py` 已移除舊 GUI，仍可繼續拆分 Solver 內部責任

舊版 Tkinter 輸入函式與命令列 main block 已刪除；`wales.py` 現在不依賴 GUI framework。若要進一步降低 Solver 單檔複雜度，建議：

```text
wales/
├─ model.py
├─ validation.py
├─ allocation.py
├─ repair.py
├─ ga.py
└─ diagnostics.py
```

## 15.3 `repair_individual()` 過大

約 217 行，包含 11 個 nested helpers。

建議建立可單元測試的獨立 repair primitives：

- remove forbidden
- move joint
- split segment
- merge left/right
- candidate ranking
- fallback policy

目前也缺少「min/max 內但非可購買長度」的局部修補。

## 15.4 Waler 評分邏輯重複

兩處存在相同或近似公式：

- `bracing_optimizer.algorithms.wales.evaluate_individual()`
- `bracing_optimizer.application.plan_editing.WalerPlanEditing.recalculate()`
建議由 `bracing_optimizer.algorithms.wales` 提供：

```python
score_waler_plan(...)
format/return breakdown
```

GUI 只顯示 breakdown，不重算。

## 15.5 Support Solver 與 Inventory 的責任邊界

Support 候選鋼材長度由目前專案 Inventory 中符合「支撐 + 已選規格」的有效 `Length` 提供；Waler 使用「圍令 + 已選規格」。`Qty=0` 仍表示該長度可購買。規格未選時跳過庫存檢查並以 `99` 表示不限庫存。Inventory 或構件規格改變時會清除候選快取，並隨專案保存及開啟。

目前仍維持以下責任邊界：

- `Length` 決定 Solver 可生成的鋼材長度。
- `Qty` 供庫存配置與材料統計，不是材料規格評分。
- 材料規格表完全不提供長度。
- Support 庫存統計只計入 `kind == "steel"`，jack 與 shim 不當作鋼材庫存。

## 15.6 材料統計鍵值

`_collect_visible_material_usage()` 將使用量依下列鍵值分開統計：

```text
Usage + Spec + Length
```

這樣不同用途或規格的同長度材料不會共用庫存數量。

## 15.7 JSON schema 與離線升級

舊版測試案例另包含：

- `derived`
- `solver_settings`
- `parameters`

這些測試案例設定不等同於正式專案 schema。正式專案已使用 schema 3，
包含 Inventory 與三種工程構件；Column／Beam 位置保存於各 Strut，舊專案必須先由離線工具升級。

仍待決定：

- 舊版測試案例的 solver settings 是紀錄還是可恢復設定。
- 測試案例格式是否也應收斂到正式專案 schema。

## 15.8 CAD LISP、範例與測試 contract

目前 LSP、JSON 範例、Python Reader/Mapper 與整合測試共用同一契約：

```text
event_id + type + operation + coordinate_space=WCS + data
```

`UPDSTRUT` 另要求 `target_id`。`ADDSTRUT` 的 `TargetJackRegion` 明確輸出數值 `2`。

## 15.9 PyInstaller 打包入口

專案只保留 `SupportSolver.spec` 作為正式 onedir 打包設定。打包及 CI
一律使用 README 第 16.9 節的固定指令，避免產生不同名稱或缺少資源的成品。

## 15.10 結果模型型別不一致

`result_items` 同時保存：

- Waler dict
- Support `GlobalSolution`
- 自訂 Waler dict

GUI 需要大量 `isinstance()` 與 `.get()` 分支。

建議建立：

```text
WalerResult
SupportResult
ResultItem
VisibilityState
```

並提供明確 serialization。

## 15.11 Logger 與全域狀態

兩套 Solver 使用模組級 logger；`wales.py` 另有全域效能 counters。

如果未來允許多個 Solver 同時執行，可能互相覆蓋 logger。

建議改為：

- Solver instance
- callback parameter
- run-specific statistics object

## 15.12 測試覆蓋

目前測試集中在 CAD bridge、資料模型與 main 匯入整合。

欠缺：

- Waler score formula
- path search forbidden filter
- repair edge cases
- Support single score
- DP/beam candidate limits
- pair penalty/global fallback
- case schema round trip
- result visibility/material statistics
- preview geometry

---

# 16. 新開發者快速上手

## 16.1 安裝與執行

需求：

- Windows 10/11
- Python 3.12
- Tkinter/Tcl/Tk
- `uv`

```powershell
uv sync --group dev
.\.venv\Scripts\python.exe .\main.py
```

## 16.2 建議閱讀順序

```text
README.md
↓
project_data.py
↓
cad_builder.py
↓
wales.py / docs/wales/README.md
↓
support.py
↓
main.py 的 Solver input/output methods
↓
main.py GUI 與 preview
```

## 16.3 要修改 GUI

先看：

```text
SupportInputApp._build_ui()
_create_*_tab()
_refresh_tree()
validate_data()
_refresh_results_tree()
```

GUI 幾乎都在 `main.py`。改動資料欄位前，必須先同步 `project_data.TABLE_SPECS`。

## 16.4 要修改 Waler Solver

先看：

```text
wales.Config
decode_individual()
validate_segments()
evaluate_individual()
find_valid_joint_sequence()
repair_individual()
_run_generations()
evolve()
```

再看：

```text
solver_input_builder.WalerInputBuilder
optimize_waler.OptimizeWaler
WalerSolverDialog._run_solver()
SupportInputApp._store_waler_result()
```

不要把染色體改成段長清單，除非有明確架構變更需求。

## 16.5 要修改 Support Solver

先看：

```text
SupportConfig
SupportPlan
evaluate_single_support()
generate_length_combinations_dp()
beam_search_layout()
generate_single_support_candidates()
pair_penalty()
build_global_solution()
```

再看：

```text
solver_input_builder.SupportInputBuilder
OptimizeSupportZone.execute()
_draw_support_solution_overlay()
```

## 16.6 要修改 CAD Builder

依序看：

```text
cad_builder.lsp
cad_bridge_event_examples.json
cad_builder.CadEventReader
cad_builder.CadEventMapper
cad_builder.TempEventWatcher
main.read_cad_event()
main._apply_cad_event()
tests/test_cad_builder_integration.py
```

修改任何一端後都要同步 JSON 範例與測試。

## 16.7 要修改資料欄位

唯一正確起點：

```text
project_data.TABLE_SPECS
```

接著檢查：

```text
main.table_column_labels
main.numeric_columns
validate_data()
CAD event mapping
case migration
preview
Solver input builders
tests
```

## 16.8 執行測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

截至 2026-07-30，目前結果：

```text
12 tests
11 passed
1 failed
```

失敗項目是 AutoLISP contract 測試仍期待 WCS `(trans)`，但目前 LISP 已依需求保留 UCS。這是測試與現況不一致，不是 Python Mapper JSON 解析失敗。

## 16.9 onedir 打包

正式指令：

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean .\SupportSolver.spec
```

輸出：

```text
dist\SupportOptimizer\
├─ SupportOptimizer.exe
├─ cad_builder.lsp
├─ project_cases\
├─ test_cases\
└─ _internal\
   ├─ assets\dxf\
   │  └─ jack_symbol.dxf
   ├─ data\
   ├─ picture\
   ├─ _tcl_data\
   ├─ _tk_data\
   └─ Python / Matplotlib dependencies
```

發佈時必須複製整個 `dist\SupportOptimizer`，不能只拿 EXE。

若 PyInstaller 顯示：

```text
tkinter installation is broken
```

請在一般 Windows PowerShell 執行打包，確認 Python 3.12 可以讀取 Tcl/Tk。成功輸出應包含：

```text
_tcl_data
_tk_data
tcl86t.dll
tk86t.dll
_tkinter.pyd
```

---

# 附錄 A：目前正式 schema

來源：`project_data.TABLE_SPECS`

```text
walers
    WalerID
    StartX
    StartY
    EndX
    EndY
    Remark

struts
    StrutID
    FromWaler
    ToWaler
    StartX
    StartY
    EndX
    EndY
    BeamPositions
    ColumnPositions
    FromBraceToWalerStartLen
    FromBraceToWalerEndLen
    ToBraceToWalerStartLen
    ToBraceToWalerEndLen
    TargetJackRegion
    Zoning

braces
    BraceID
    FromWaler
    ToWaler
    StartX
    StartY
    EndX
    EndY

inventory
    Length
    Qty
```

# 附錄 B：核心設計不變項

在沒有正式架構變更決策前，應維持：

```text
Waler：
candidate_joint_points
→ individual 0/1
→ decode_individual()
→ joints
→ segments
→ validate_segments()
→ allocate_stock_best_fit()
→ evaluate_individual()
→ score
→ evolve()

Support：
SupportConfig
→ length combinations
→ steel orders
→ jack/shim layouts
→ SupportPlan candidates
→ pair penalty
→ GlobalSolution

CAD：
AutoLISP
→ single TEMP JSON
→ TempEventWatcher
→ CadEventMapper
→ ProjectDataModel
→ main GUI
```

# 附錄 C：小型 Helper 與事件 Callback 索引

這些方法不是 Solver 核心，但仍屬於目前程式符號的一部分。

| 函數／方法 | 用途 |
|---|---|
| `rows` | `ProjectDataModel` 依 table name 回傳資料列 |
| `build_row` | `CadEventMapper` 將單一 CAD data 建成正式 row |
| `map_event` | `CadEventMapper` 的 event 映射入口 |
| `__post_init__` | `wales.Config` 建立後補預設候選點與材料長度 |
| `_format_zoom_percent` | Preview toolbar 格式化倍率文字 |
| `_refresh_message` | Preview toolbar 合併座標訊息與倍率 |
| `struts`、`braces`、`inventory` | `SupportInputApp` 的 ProjectDataModel properties 與 setters |
| `_on_ascii_art_entry_focus_in` | 彩蛋輸入框取得焦點時調整外觀 |
| `_on_ascii_art_entry_focus_out` | 彩蛋輸入框失焦時恢復外觀 |
| `_on_ascii_art_code_enter` | Enter 後載入並顯示 ASCII art |
| `_load_default_inventory` | 透過 `JsonInventoryRepository` 從 `data/inventory.json` 載入預設庫存 |
| `_tree_column_key` | 把 Treeview `#n` 欄位轉成正式欄名 |
| `_has_modified_waler_results` | 判斷重新計算是否會覆蓋已修改的圍令方案 |
| `_apply_waler_plan_segments` | 將編輯後的鋼材順序套用至原方案並重新驗證 |
| `_support_kind_label` | steel/shim/jack 顯示名稱 |
| `_support_kind_key` | 將顯示名稱轉回正式 piece kind |
| `_table_label` | table key 轉中文表名 |
| `_field_label` | schema field 轉中文欄名 |
| `_append_message` | Waler/Support Dialog 將訊息接續加入 log |
| `_log_candidate_shortage` | Support 候選不足時輸出原因與建議 |
| `_format_solver_number` | Waler Dialog 格式化設定與結果數值 |
| `_on_close` | Solver Dialog 關閉 callback |
