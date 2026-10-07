# Design

## 閱讀導航

- **P0／現在必讀**：D1「正式快照與 runtime Project 分離」、D2「四檔精確映射」與 D3「來源及成品雙層驗證」；它們共同保證兩個案例可重現、可開啟且不夾帶 `.bak`。
- **P1／實作前閱讀**：D4「不新增啟動期 seed 邏輯」；修改 `bootstrap.py`、`main.py` 或 Project repository 時先確認本案不需要動到它們。
- **P1／實作前閱讀**：D5「既有 persistence 語意不變」；修改測試與文件時確認預置案例仍是一般 managed Project。
- **P2／條件式閱讀**：只有發現 payload schema 或 managed DXF 驗證失敗時，才讀「風險與取捨」中的快照有效性項目，以及 `project-schema-compatibility`／`project-state-transaction-consistency`。
- **可先跳過**：Solver、Domain、DXF recognition、成果匯出與 `simplify-main-window-project-controls` 的 UI layout 決策；本案不修改這些行為。

## 方案摘要

「正式快照」是目前兩個案例中經核准要隨 release 交付的 `project.json` 與 `source/source.dxf`。它們放在 tracked 的 `assets/project_cases/`，不使用 repository root 那個被忽略、會隨使用者操作改變的 runtime `project_cases/`。

```text
assets/project_cases/<案例>/project.json
assets/project_cases/<案例>/source/source.dxf
                    |
                    | SupportSolver.spec：四檔 allowlist
                    v
dist/SupportOptimizer/project_cases/<案例>/...
                    |
                    | 既有 APP_DIR/project_cases repository
                    v
Open / Save / Save As / Delete（行為不變）
```

## 決策對照

| Decision | 影響的 Requirement | 對應 task |
| --- | --- | --- |
| D1. 正式快照與 runtime Project 分離 | 正式 Project 素材來源必須可重現；Repository 只保留正式發行 Project 素材 | 1.1～1.3 |
| D2. 四檔精確映射，不使用整目錄複製 | 正式發行包提供兩個 Project 案例；正式發行包只預置核准 Project 與 runtime 資產 | 2.1～2.2 |
| D3. 來源 contract test 加 clean onedir output 驗證 | 指定 Project 素材缺少或無效；檢查預置案例的初始 layout | 1.2、2.2、4.1 |
| D4. 不新增啟動期 seed／restore 邏輯 | Runtime Project 目錄可由正式案例建立或按需建立；使用者刪除預置案例 | 2.1、3.1 |
| D5. 既有 persistence 與 Project UI 語意不變 | 使用者儲存預置案例；首次開啟正式包的 Project 清單 | 3.1～3.2 |

## Context

動機見 `proposal.md` 的 Why。現況中 `bootstrap.build_dependencies()` 已把 frozen application 的 Project repository 固定為 executable 同層的 `APP_DIR/project_cases`；`SupportInputApp` 會建立該目錄並以 `*/project.json` 列舉 managed Project。`ProjectService.load_project()` 先執行現行 schema validation，再檢查 `source/source.dxf` 等 managed asset。這些既有 boundary 已能直接消費成品中的兩個案例。

目前 repository root `project_cases/` 被 `.gitignore` 排除，裡面兩個案例是 runtime user data；若 `SupportSolver.spec` 直接複製該目錄，clean checkout 無法重現，且任何使用者 Project、`.bak` 或暫存檔都可能意外進入 release。現行 `release-package-assets` spec 與 tests 也明確禁止這種做法。

兩個核准案例目前皆為 schema version 3，各自已有 `project.json` 與 managed `source/source.dxf`；不含 `.bak` 的來源合計約 41.6 MiB。`project.json.bak` 是 Save 時產生的上一版 JSON，不是 load 所需檔案。

## Goals / Non-Goals

**Goals:**

- 讓 clean checkout 可重現地產生兩個可開啟的預置 Project。
- 讓 source 與 output 都能驗證精確 allowlist、schema 與 managed DXF。
- 保留目前 runtime Project 目錄、開啟、儲存、另存、刪除與 `.bak` 語意。
- 讓封裝規格缺檔時直接失敗，不產生缺件正式包。

**Non-Goals:**

- 不新增 Project template／clone 模型、唯讀旗標或第一次啟動 copy-on-write。
- 不修改 Project schema、payload、DXF metadata 或 persistence transaction。
- 不替換使用者已安裝環境中的同名 Project，也不定義 installer upgrade／merge policy。
- 不調整進行中 Project controls change 的 UI 或 navigation guard。

## Decisions

### D1. 正式快照與 runtime Project 分離

新增 tracked `assets/project_cases/`，只保存：

```text
assets/project_cases/
├─ Y05車站第一層支撐/
│  ├─ project.json
│  └─ source/source.dxf
└─ Y29車站第一層支撐/
   ├─ project.json
   └─ source/source.dxf
```

實作時從目前 runtime 兩個案例複製這四個核准檔案；不複製 `project.json.bak`。`assets/project_cases/` 是「將什麼內容放進新 build」的 source of truth；成品 `project_cases/` 是其 build-derived copy，首次執行後則成為使用者可變動的 runtime truth。兩者生命週期不同，不做啟動期同步，因此不會形成同一執行環境的雙重 authoritative Project state。

**Rejected：直接解除 `.gitignore` 並追蹤 repository root `project_cases/`。** 該位置同時是 source run 的可寫 runtime repository；開發者儲存、另存或刪除 Project 會直接改動 release source，且容易把未核准案例與 `.bak` 納入 Git。

**Rejected：只在本機 build 時讀取被忽略的 runtime `project_cases/`。** Clean checkout、CI 與另一台 release machine 不具備相同輸入，無法產生可重現成品。

### D2. `SupportSolver.spec` 使用四檔精確映射

在 `COLLECT` 後建立下列目的目錄，逐檔 `shutil.copy2`：

1. `Y05車站第一層支撐/project.json`
2. `Y05車站第一層支撐/source/source.dxf`
3. `Y29車站第一層支撐/project.json`
4. `Y29車站第一層支撐/source/source.dxf`

來源都從 `Path(SPECPATH) / "assets" / "project_cases"` 解析，目的地都在 `Path(DISTPATH) / "SupportOptimizer" / "project_cases"`。父目錄逐一建立；任何來源缺少時由 `copy2` 使 build 失敗。不得使用 `copytree` 或把整個 asset root 加入 PyInstaller `datas`，避免新檔案自動擴張 release allowlist，也確保 runtime repository 位於 executable 同層而不是 `_internal`。

**Rejected：把 `assets/project_cases/` 整包加入 `datas`。** PyInstaller 6 onedir 會把資料放在 `_internal`，不符合既有 `APP_DIR/project_cases` repository path；整包收集也無法保證 `.bak` 排除。

**Rejected：同時封裝 `project.json.bak`。** Load 不讀取該檔，兩份 backup 約增加 36.5 MiB；使用者第一次儲存既有 Project 時，現行 persistence 會自行產生當時有效的 `.bak`。

### D3. 來源 contract 與實際成品分層驗證

快速 contract tests 負責：

- `assets/project_cases/` 頂層恰好兩個案例。
- 每個案例恰好具有 `project.json` 與 `source/source.dxf`，沒有 symlink、`.bak` 或額外檔案。
- `project.json` 通過 `ProjectSerializer.validate_for_load()`；managed DXF 可由現行 DXF reader／asset validation 讀取。
- `SupportSolver.spec` 對四個來源／目的檔各有一次明確映射，仍不引用 repository root runtime `project_cases/`、`test_cases/`、`tests/fixtures/` 或 `copytree`。

Clean onedir smoke build 再驗證實際 `dist/SupportOptimizer/project_cases/` 的 exact layout，並透過既有 `ProjectService.load_project()` 開啟兩案。這補足純 source-text assertion 無法證明最終成品的限制；快速測試仍保留，避免每次小改都只能跑昂貴 build。

測試常數可放在 `tests/release_project_assets.py` 之類的 test helper；production build mapping 仍由 `SupportSolver.spec` 擁有，測試只對正式 contract 做獨立 assertion，不讓 runtime code 依賴 test module。

### D4. 不新增啟動期 seed、同步或自動復原

既有 composition root 已將 frozen runtime repository 指到 executable 同層；PyInstaller build 直接把兩案放到該位置，所以 `bootstrap.py`、`main.py` 與 Project repository 列舉不需修改。若 source run 或測試環境沒有 `project_cases/`，既有 `mkdir(parents=True, exist_ok=True)` 行為仍建立空白 repository。

預置案例在 build 完成後沒有特殊身份。使用者刪除後，應維持刪除；下次啟動不從 `_internal` 或 assets 補回。只有重新部署一份新的正式 build output 才再次提供初始快照。

**Rejected：首次啟動從 `_internal` 複製 seed。** 這需要版本、同名衝突、使用者修改保留與重置政策，且會建立 startup mutation 與第二份 runtime source；需求只要求案例隨成品交付。

### D5. 既有 persistence 與 Project UI 語意不變

兩個案例沿用 schema version 3、現行 managed DXF relative path、load hydration 與 Save transaction。初始包不含 `.bak`；使用者儲存時，persistence 在替換 `project.json` 前建立上一版 `.bak`。Save As 與 Delete 也沿用一般 managed Project 行為，不新增保護規則。

進行中的 `simplify-main-window-project-controls` 只改變 Project selection UI；它仍從同一 `project_cases_dir` 列舉 `*/project.json`，因此本案只增加兩筆 repository content，不改其 navigation guard 或 transaction contract。若 apply 時該 change 已修改列舉入口，驗證應改走最新的公開 repository／dialog behavior，但不得在本案重寫 UI。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility 或 dependency direction：

| 範圍 | 責任 |
| --- | --- |
| Release／deployment boundary | `assets/project_cases/` 與 `SupportSolver.spec` 擁有正式輸入及 output mapping |
| Infrastructure | 既有 Project schema／DXF asset validation、load／save persistence，不新增規則 |
| Application | `ProjectService` 沿用既有 hydrate／load use case |
| Presentation | 沿用 Project repository selection 與既有命令，不知道「預置」身份 |
| Domain／Algorithms／DXF recognition | 無變更、無新增依賴 |

資料流仍是 `filesystem Project -> Infrastructure validation -> Application hydration -> Presentation adoption`。Release assets 不被 Domain 或 Algorithms import，也不讓 Presentation 直接解析 payload。

## Backward Compatibility 與 Persistence Impact

- 既有 source run 沒有正式 asset 複製時，仍可建立空的 runtime `project_cases/`。
- Project schema 與 payload 不變，不需 migration。
- 已存在的 user Project 仍依既有路徑與格式載入。
- 新正式包比舊版多兩個同名 Project；若以外部 installer 覆蓋一個已含同名使用者 Project 的安裝目錄，衝突處理不在本案範圍，release 流程不得直接把 build output 當作使用者資料 migration 工具。
- 初始成品沒有 `.bak`；第一次儲存預置案例後才由現行流程建立。

## Risks / Trade-offs

- **[成品增加約 41.6 MiB]** → 只保留 load 必要的 JSON 與 managed DXF，排除兩份 `.bak`。
- **[CJK 長路徑在 Windows build 或解壓時失敗]** → contract tests 使用原始名稱，clean Windows onedir build 驗證實際路徑與開啟。
- **[核准快照日後被意外加入額外檔案]** → source exact-layout test 與逐檔 mapping 共同阻擋。
- **[Payload 記錄的 original path 指向開發機]** → 正式 load 以案例內 managed `source/source.dxf` 為可攜來源；smoke test 必須在不依賴原始絕對路徑的情況載入。若無法做到，停止而不是改寫 schema。
- **[預置案例被使用者修改或刪除]** → 這是已確認的一般 Project 行為；不做自動補回。重新取得原始案例需重新部署正式包。
- **[工作區已有未提交的封裝修改]** → apply 只在目前內容上做最小增量，不覆寫 icon、software history、sample DXF 等既有變更。

## Migration Plan

1. 以目前兩個 runtime Project 建立 tracked release asset 快照，只複製四個核准檔案。
2. 先建立／更新 source contract tests並驗證快照可載入。
3. 更新 `SupportSolver.spec` 的逐檔 mapping，執行 focused package tests。
4. 更新 README 與 `docs/WORKFLOW.md` 的發行及首次 Project 行為。
5. 從 tracked-only clean checkout／等價暫存環境執行 onedir build，驗證 exact output 與兩案 load。
6. 執行相關 regression、OpenSpec strict validation 與 implementation verification。

回滾可移除四個 release assets、spec mapping、對應測試與文件增量，使成品恢復空 Project repository；沒有 schema migration 或 runtime data rewrite，因此不需資料回復程序。
