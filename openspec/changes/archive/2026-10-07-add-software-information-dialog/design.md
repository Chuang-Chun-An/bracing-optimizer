# Design

## 閱讀導航

- **P0／現在必讀**：Decision 1「產品身分的單一 runtime truth」、Decision 2「起始歷史紀錄的精確投影」、Decision 3「Presentation 只負責顯示」。
- **P1／實作前閱讀**：修改 `SupportSolver.spec` 或資源測試時讀 Decision 4；實作視窗與 lifecycle tests 時讀 Decision 5。
- **P2／需要時再讀**：只有發生 metadata drift、歷程缺漏或 package build 問題時，才讀「Risks / Trade-offs」與「Migration Plan」。
- **可先跳過**：Domain、Solver、DXF、Project persistence 與 result lifecycle；本 change 不接觸這些路徑。

## 方案摘要

```text
bracing_optimizer/product_metadata.py
  └─ ProductIdentity（名稱／版本／作者，runtime truth）

docs/DEVELOPMENT_HISTORY.md／起始歷史紀錄（authoritative source）
  └─ assets/software_history.json（逐筆精確投影）
       └─ SoftwareHistoryRepository（驗證、保序、fallback）
       └─ SoftwareInformationDialog（唯讀顯示）
            └─ main.py「說明 → 軟體資訊」
```

`ProductIdentity` 是程式本身的身分資料；`software_history.json` 只保存 `docs/DEVELOPMENT_HISTORY.md`「起始歷史紀錄」表格的逐筆結構化投影。兩者在開啟視窗時組合成顯示模型，不寫入 Project，也不查詢網路。

## 決策對照

| Decision | 影響的 spec Requirement | 對應 tasks |
|---|---|---|
| 1. Python module 保存 runtime 產品身分 | `software-information-presentation`「顯示可辨識的軟體身分」 | `tasks.md` §1、§4 |
| 2. JSON 精確投影起始歷史紀錄 | 「完整顯示起始歷史紀錄」、「資源異常時保留基本資訊」 | §1、§2、§4 |
| 3. loader 與 dialog 分層 | 「資訊視窗不得修改 Project」 | §2、§3、§4 |
| 4. 歷程 resource 明確列入 PyInstaller datas | `release-package-assets`「正式發行包不預置 Project 或測試資料」 | §3、§4 |
| 5. 主視窗只新增 Help menu wiring | 「可從主視窗開啟軟體資訊」 | §3、§4 |

## Context

動機見 `proposal.md` 的 Why。現況中 `pyproject.toml` 宣告即將發布的版本 `3.0.0`，主視窗 `SupportInputApp._build_project_menu_and_toolbar()` 只建立「檔案」選單；`docs/DEVELOPMENT_HISTORY.md` 是 archive workflow 維護的完整工程紀錄，而 `SupportSolver.spec` 目前不封裝它。

設計須同時滿足：

- Tkinter Presentation 可以在沒有 Project 的情況下開啟資訊。
- 正式 onedir 成品無 repository、無網路仍可讀歷程。
- UI 只需要起始歷史紀錄，不得納入同一文件中的 Codex／OpenSpec 封存、人工補充或 AI 對話統計區段。
- `main.py` 已是 Presentation shell；新增行為不得成為重構既有 Main／Dialog accepted debt 的理由。

## Goals / Non-Goals

**Goals:**

- 建立小型、可單元測試且不依賴 Tkinter 的產品身分與歷程讀取 contract。
- 以逐筆比對固定 runtime history 與起始歷史紀錄的日期、文字及順序一致性。
- 讓 source run 與 PyInstaller onedir 透過相同 resource path 語意呈現同一內容。
- 將 loader failure 收斂成可顯示狀態，避免未處理例外穿透 UI。
- 以 focused tests 固定版本一致性、歷程逐筆 parity／原序驗證、menu wiring、唯讀呈現與 package datas。

**Non-Goals:**

- 不把軟體資訊加入 `AppDependencies` 或 ProjectService；它不是長生命週期 use case，也不需要 Project transaction。
- 不建立 release server、更新檢查、markdown renderer 或通用 CMS。
- 不從 Git log、OpenSpec archive 或 `DEVELOPMENT_HISTORY.md` 的其他區段於 runtime 動態加入內容。
- 不為這個視窗拆分或整理 `main.py` 的其他 UI 責任。

## Decisions

### Decision 1：以 `product_metadata.py` 作為產品身分的單一 runtime truth

新增 `bracing_optimizer/product_metadata.py`，以 immutable dataclass／常數提供：

- `name = "SupportOptimizer"`
- `version = "3.0.0"`
- `author = "莊竣安（Chuang Chun An）"`

dialog 只接收這個模型，不在 labels、menu command 或 JSON 內重複版本與作者。`pyproject.toml` 仍需保留 PEP 621 的 distribution version，故它是 release metadata mirror；focused test 以 `tomllib` 驗證它與 runtime version 相等，若不同就讓測試失敗。未來 bump version 時必須同一 change 更新兩處，runtime 顯示仍只讀 Python module。

**替代方案：** runtime 直接讀 `pyproject.toml`。拒絕原因是正式 PyInstaller 成品目前不攜帶整份 build 設定，為了一個版本欄位把 project config 當 runtime contract 會擴大封裝與失敗面。`importlib.metadata` 也不採用，因目前 PyInstaller spec 沒有保證收集本專案 distribution metadata。

### Decision 2：使用者歷程是「起始歷史紀錄」的逐筆精確 JSON 投影

新增 `assets/software_history.json`，頂層包含 `schema_version: 1`、固定的 `source_heading` 與 `entries`；每筆 entry 使用非空白的 `date_label` 與 `record`。entries SHALL 逐筆對應 `docs/DEVELOPMENT_HISTORY.md` 中「起始歷史紀錄（截至 2026/09/28 早上）」表格，保留表格既有日期文字、紀錄文字及由上至下的原始順序。日期不是排序 key，不要求轉成 ISO 格式，loader 也不得重新排序。

`docs/DEVELOPMENT_HISTORY.md` 的該區段是唯一 authoritative source；JSON 只是正式成品所需的結構化投影。focused test 解析起始歷史表格並逐筆比對 `(date_label, record)` 與順序，任何缺漏、新增、摘要或重排都必須失敗。由於 `archive-development-history` 已規定 archive workflow 不改寫起始歷史，這份投影不會隨新 archive 自動增加內容。JSON MUST NOT 投影「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」或「AI 對話統計」。

**替代方案：** 直接封裝並於 runtime 解析完整 `docs/DEVELOPMENT_HISTORY.md`。拒絕原因是正式成品會攜帶使用者未要求的封存紀錄、人工補充與 AI 對話統計；以最小 JSON 投影配合 parity test，可以只交付指定區段而不形成內容漂移。另一替代方案是重新撰寫摘要，因會刪減使用者指定的起始歷史內容而拒絕。

### Decision 3：Application model、Infrastructure loader、Presentation dialog 各自單一責任

- `bracing_optimizer/application/software_information.py` 定義 immutable `SoftwareHistoryEntry`、`SoftwareHistoryLoadResult` 與組合後的 `SoftwareInformation`；不 import Tkinter、不讀檔。
- `bracing_optimizer/infrastructure/software_history.py` 負責 UTF-8 JSON 讀取、schema／`source_heading`／欄位驗證與原序保留，並把 missing、I/O、JSON 或 validation error 轉成 `available=False` 的 load result。底層原因寫入 logger，使用者訊息固定為可理解的 fallback。
- `bracing_optimizer/presentation/dialogs/software_information_dialog.py` 只把 `SoftwareInformation` 映射成 labels、唯讀 scrollable text 與關閉按鈕。
- `main.py` 的 command handler 使用 `RESOURCE_DIR / "assets" / "software_history.json"` 呼叫 loader、與 `ProductIdentity` 組合後建立 dialog。這是使用者觸發的終端讀取，與 Architecture 記錄的 Main 直接呼叫 terminal adapter 例外一致，不建立新的通用 service。

Dependency direction 為 `Presentation → Application model` 與 `Infrastructure → Application model`；Main 作為 composition／Presentation shell 同時組合兩者。Domain 與 Algorithms 不新增依賴。

**替代方案：** 把 JSON parsing 放進 dialog。拒絕原因是 Presentation 會同時擁有 I/O、validation 與 rendering，難以在無 Tk 環境驗證 fallback。把它放進 ProjectService 也拒絕，因產品資訊與 Project lifecycle 無關。

### Decision 4：只封裝起始歷史投影，不封裝完整歷程或 OpenSpec tree

`SupportSolver.spec` 的 `datas` 新增 `assets/software_history.json` 到相同的 `assets` 目的路徑。package tests 驗證該精確 resource 被列入、完整 `docs/DEVELOPMENT_HISTORY.md` 與其他 docs 不會被封裝，且既有對 `project_cases/`、`test_cases/`、`tests/fixtures/` 與 `copytree` 的禁止 assertion 保留。

loader 使用與 app icon 相同的 `RESOURCE_DIR` 語意，因此 source run 與 PyInstaller 都解析 `<resource root>/assets/software_history.json`。若 runtime resource 缺少或損壞，identity 仍來自 compiled Python module，歷程區顯示 fallback。

**替代方案：** 封裝整個 `assets/` 或 `docs/`。拒絕原因是會把未經 allowlist 的檔案帶入正式 release，違反 release-package-assets 的最小資源邊界。

### Decision 5：資訊視窗為 modal、唯讀且不接觸 Project callbacks

dialog 使用 `Toplevel`、`transient(parent)` 與既有 modal pattern；identity 使用普通 labels，歷程使用 disabled `ScrolledText`，只提供「關閉」控制與 Escape shortcut。它不接收 `ProjectDataModel`、`ProjectResultModel`、dirty callback 或 save handler，因此沒有修改 Project 的路徑。

Main 新增獨立的 `help_menu`，label 為「說明」，command 為「軟體資訊」。`file_menu` 與 `_update_project_action_states()` 保持原樣，資訊命令永遠可用且不依賴 Project selection。

**替代方案：** 把資訊做成 workspace tab。拒絕原因是它會占用工程工作區、混入 Project navigation，且不符合短暫查閱後返回原工作內容的流程。使用 `messagebox` 也不採用，因長歷程不適合捲動閱讀與結構化顯示。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

| Layer | 變更 | 不變邊界 |
|---|---|---|
| Presentation | Help menu、dialog、顯示格式 | 不持有歷程 parsing 規則，不修改 Project state |
| Application | 純資料 contract | 不 orchestrate Solver／Project workflow |
| Infrastructure | 單一 JSON resource loader | 不定義 Domain／工程規則 |
| Domain／Algorithms | 無變更 | 不依賴產品資訊或 Tkinter |

`docs/ARCHITECTURE.md` 已允許 Main 處理 user-triggered terminal I/O。本功能只新增一個窄的 read-only adapter，不引入反向依賴；architecture boundary tests 必須繼續通過。

## State、Contract 與一致性

- **Runtime identity truth**：`bracing_optimizer/product_metadata.py`。
- **Distribution mirror**：`pyproject.toml [project].version`；由 test 與 runtime truth 比對，不被 UI 直接讀取。
- **Initial history truth**：`docs/DEVELOPMENT_HISTORY.md` 的「起始歷史紀錄」區段。
- **Packaged projection**：`assets/software_history.json`；由逐筆 parity test 防止與 authoritative section 漂移。
- **Other history sections**：`docs/DEVELOPMENT_HISTORY.md` 的封存、人工補充與 AI 對話統計；不進入 runtime resource。
- **Project truth**：完全不變；dialog 無 Project reference 與寫入 callback。

這些 contract 透過明確 source 與 verification 避免 drift：同一欄位（runtime version）只有 Python module 是 UI source；起始歷史則以文件區段為 source、JSON 為必須逐筆相同的投影。

## Backward Compatibility 與 Persistence Impact

- 既有選單 command、Project JSON、DXF Review state、UI state 與 save/load contract 均不變。
- `assets/software_history.json` 是新的 release resource，只投影既有起始歷史，不是 Project payload，沒有 schema migration。
- 舊的正式成品不會有新入口；新成品的 resource 若遺失會 fallback，不影響啟動及 Project 操作。
- 不提升 Project schema version、Review state version 或 Solver policy version。

## Risks / Trade-offs

- **[Risk] `product_metadata.py` 與 `pyproject.toml` 版本值不同步** → 加入 exact equality test，release version bump 必須同時更新兩處。
- **[Risk] 手工建立的 JSON 漏掉、摘要或重排起始歷史** → 測試解析 authoritative section 並逐筆比對日期、紀錄文字與順序；任何差異直接失敗。
- **[Risk] 完整歷程文件的其他區段被誤帶入成品** → package tests 禁止封裝完整 `docs/DEVELOPMENT_HISTORY.md`，resource content tests 排除三個非目標區段。
- **[Risk] JSON 損壞導致 dialog 無法開啟** → loader 將所有可預期的 file／decode／validation error 收斂為 unavailable result；identity 與關閉操作仍存在。
- **[Risk] 歷程日後變長** → 使用唯讀 scrollable widget；不在本 change 引入搜尋、分頁或 markdown renderer。
- **[Trade-off] modal dialog 會暫停主視窗操作** → 資訊查閱是短流程，modal 可避免重複視窗與額外 lifecycle state；若日後需長期並排比較，再另行評估 modeless singleton。

## Migration Plan

1. 先加入 model、作者 metadata、起始歷史精確投影與逐筆 parity／loader tests，不改 UI。
2. 加入 dialog 與 Help menu wiring，執行 focused Presentation tests。
3. 更新 `SupportSolver.spec` 與 package asset tests，建立乾淨 onedir 後手動確認離線顯示。
4. 執行 architecture boundaries 與受影響回歸測試，再進行 OpenSpec verify。

回滾時可移除 Help menu command、dialog／model／loader、單一 JSON resource 及 PyInstaller datas entry；因沒有 persistence migration 或 Project 寫入，不需資料回復程序。
