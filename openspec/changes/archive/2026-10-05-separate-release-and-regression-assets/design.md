# Design

## 閱讀導航

- **現在必讀（P0）**：D1「三份素材的 source／package layout」、D2「release exclusion」與 D3「runtime Project 目錄」。
- **實作前閱讀（P1）**：D4「移除 Project cases 與保留非 Project fixtures」、`specs/release-package-assets/spec.md` 全部 Requirements，以及 `tasks.md` 對應 task group。
- **條件式閱讀（P2）**：更新素材 consumers 時讀所有 Y05／Y1A／Y29 tests；改寫 Project-fixture consumers 時讀 DXF export、save-as 與 support shim tests；搬移 CAD JSON 時讀 `tests/test_cad_builder_integration.py`。
- **可以先跳過**：Project schema、DXF recognition internals、Solver 與 installer 架構；這些不在本 change 的設計範圍。

## 方案摘要

```text
assets/sample_dxf/（exact source allowlist）
├─ Y29_test.dxf
├─ Y1A擋土支撐簡化版.dxf
└─ 670-CO-Y05-...第一層支撐平面圖.dxf
              │
              ├─> SupportSolver.spec ──> dist/SupportOptimizer/sample_dxf/
              └─> existing DXF regression tests

tests/fixtures/cad/ <── 有直接 consumer 的 non-Project CAD event data
runtime project_cases/ <── application mkdir；不由 build seed、不追蹤 fixture
```

`user material` 在本 change 指會隨正式產品交付、供使用者自行選取與匯入的 DXF。`fixture` 則只指有直接 automated consumer 的非 Project 測試資料，不是產品交付內容。三份指定 DXF 即使也被 tests 使用，仍屬 user materials，不因 test consumer 而降級成 fixtures。

## 決策對照

| Decision | 影響的 Requirement | 對應 tasks |
| --- | --- | --- |
| D1. 三份素材使用 exact source allowlist，輸出到 `sample_dxf/` | 正式發行包提供三份 DXF 使用者素材 | 2.1～2.3 |
| D2. `SupportSolver.spec` 排除 Project 與 regression-only data | 正式發行包不預置 Project 或測試資料 | 3.1、3.2 |
| D3. `project_cases` 只由 runtime 建立 | Runtime Project 目錄不依賴 build seed | 4.1、4.2 |
| D4. 移除所有 Project cases，只保留有 consumer 的非 Project fixture | Regression tests 不保留 Project case | 1.1～1.2、5.1～5.4 |

## Context

`SupportSolver.spec` 目前在 `COLLECT` 後把 `Y29_test.dxf` 放在執行檔旁，同時整包複製 `project_cases/` 與可能不存在的空 `test_cases/`。Y1A 與 Y05 DXF 位於 repository root，雖被多個 tests 使用，但尚未作為正式 release material 打包。

使用者已確認正式包不附任何 Project，但要附 Y29、Y1A、Y05 三份 DXF，並統一放在 `sample_dxf/`。因此這三份檔案的分類從 regression-only candidate 改為正式 user material；所有 tracked `project_cases/` 內容與 Project JSON 都移除，不搬到 fixture tree，只有 CAD event 等非 Project 測試資料另行歸屬。

`main.py` 已在啟動與列舉 Project 前建立 `project_cases_dir`，`bootstrap.py` 透過 `AppDependencies.project_cases_dir` 提供路徑；建立空 runtime 目錄原則上不需要新的產品 abstraction。

## Goals / Non-Goals

**Goals:**

- 正式 package 不含任何預置 Project 或 regression-only fixture。
- `sample_dxf/` 穩定且只包含三份已確認使用者素材。
- Repository 中三份素材各只有一個 authoritative source，同時供 build 與 tests 使用。
- Clean checkout build 不依賴 Git 無法追蹤的空目錄。
- 所有 tracked Project cases 與 Project JSON 都移除，原有 test consumers 以程式化輸入或正式 DXF 改寫。
- 非 Project fixture 只有在具有直接 automated consumer 時才保留。

**Non-Goals:**

- 不新增 sample gallery、素材選單、自動匯入或特殊解析流程。
- 不修改三份 DXF 的內容、檔名或 DXF recognition expectations。
- 不修復或保存 legacy Project cases、不調整 schema compatibility。
- 不搬移 runtime `assets/dxf/`、`data/`、`picture/` 或 `cad_builder.lsp`。
- 不把歷史 analysis output 的字串路徑當成 executable fixture consumer；若報告是歷史快照則保留原文。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility 或 dependency direction：

- `assets/sample_dxf/` 與 PyInstaller spec 屬 deployment asset boundary，不進入 Application、Domain 或 Algorithms。
- 使用者仍透過既有 Presentation → DXF subsystem 流程手動選取素材；產品程式不硬編碼或自動載入這三份檔案。
- `AppDependencies` 繼續是 runtime Project path contract 的 single source of truth。
- `tests/fixtures/` 只保留非 Project 測試資料；test-side asset paths 與程式化測試資料不形成產品 state 或第二套 Project persistence contract。

## Decisions

### D1. 三份 user materials 使用 source allowlist 與固定 output directory

三份 tracked source 從 repository root 集中到 `assets/sample_dxf/`，保留原始檔名。`SupportSolver.spec` 宣告三個明確檔名，逐一複製到 `dist/SupportOptimizer/sample_dxf/`；不以整個來源目錄作為無條件 copytree，避免日後新增檔案時意外擴大正式包。

同一 source files 供現有 Y05／Y1A／Y29 regression tests 使用。被多個 test modules 引用的路徑由 test-side asset path module 集中定義，但該 helper 指向 `assets/sample_dxf/`，不得建立 `tests/fixtures/` 副本。

Build contract 檢查三個 source names 與 output directory；frozen smoke build 再驗證 `sample_dxf/` 恰好三個檔案且每個可由 DXF reader 開啟。任一 source 缺少時，spec copy 應直接失敗，不能 catch 後繼續產生缺件 package。

**Rejected alternative:** 繼續把素材散放在執行檔旁。這會讓使用者難以辨識產品檔與素材，也無法對三份檔案建立穩定邊界。

**Rejected alternative:** `copytree(assets/sample_dxf)`。它會讓未經 review 的新檔案自動進入正式包，不符合「只附三份」的決定。

### D2. 正式 package 其餘內容採 runtime allowlist

保留 `SupportSolver.spec` 中已確認的 `data/`、`picture/`、`assets/dxf/` 與 `cad_builder.lsp`。移除 `project_cases/`、`test_cases/` 及其他 regression-only post-`COLLECT` copy。三份 user materials 是明確例外，由 D1 的 allowlist 管理，不視為 test fixture。

驗證分兩層：快速 contract test 檢查 forbidden roots 不再被引用且 runtime／material allowlist 完整；PyInstaller smoke build 檢查實際 output。只檢查 source text 不足以證明最終成品，只有 smoke build 又太慢，不適合作為唯一 regression guard。

**Rejected alternative:** 保留空 `project_cases/` copy 只刪內容。空目錄不是可靠的 tracked build input，且會模糊 build seed 與 runtime user data 的責任。

### D3. Runtime `project_cases` 延續既有 dependency-owned path

`AppDependencies.project_cases_dir` 繼續提供正式路徑，`SupportInputApp` 在需要時以既有 `mkdir(exist_ok=True)` 行為建立目錄。實作先以 tests 證明「路徑不存在也能建立並保存」；只有測試揭露缺口時才最小修改產品程式，不預先重寫 frozen path policy。

Repository 的 `/project_cases/` 加入 ignore policy，避免本機 runtime data 再被誤提交為 fixture。正式 build output 在啟動前沒有 Project；啟動後可出現空 runtime directory，兩者不衝突。

**Rejected alternative:** 把使用者 Project 改到新的 OS-specific data root。這會改變既有 workflow 與資料發現位置，超出本 change。

### D4. 移除 Project cases，非 Project fixture 依 owner 分類

三份 user materials 不進 `tests/fixtures/`。所有 tracked `project_cases/`、Project JSON、`.bak` 與 Project-managed `source/source.dxf` 都直接移除，不搬到 `tests/fixtures/projects/` 或 `tests/fixtures/manual/`。其中與 Y29／Y1A 素材內容相同的 managed DXF 由 `assets/sample_dxf/` 的正式素材取代，不保留重複副本。

原本讀取 Project fixture 的 tests 依測試目的分兩類改寫：只需要 DXF 的測試改讀 `assets/sample_dxf/`；需要 Project state 的測試利用既有 model／persistence API 在測試暫存目錄程式化建立最小輸入。不得為了移除 fixture 而刪除測試、降低 assertion 或新增 skip。

唯一保留的 regression-only repository data 是有直接 automated consumer 的非 Project fixture，目標結構為：

```text
tests/fixtures/
├─ README.md
└─ cad/cad_bridge_event_examples.json
```

**Rejected alternative:** 把 Project cases 搬到 `tests/fixtures/projects/` 或 `tests/fixtures/manual/`。這仍會保留使用者已明確不要的 Project case，並讓無用途歷史資料看似受 regression 保護。

## Source of Truth

- 三份 user-material sources：`assets/sample_dxf/` 的 exact filenames。
- 正式 release inputs／output mapping：`SupportSolver.spec` allowlist。
- Runtime Project location：`AppDependencies.project_cases_dir`。
- Shared test asset paths：test-side helper 指向 `assets/sample_dxf/`。
- 非 Project fixture ownership：`tests/fixtures/README.md` 與直接 automated consumer。

Build 與 tests 共用同一份素材 source，package output 是 build artifact，不是第二份 repository truth；`tests/fixtures/` 不複製三份素材，因此不會形成可漂移副本。

## Backward Compatibility / Persistence

Project JSON schema、managed DXF layout、save／load 行為與外部 Project 相容政策不變。使用者既有 runtime Projects 不需 migration。三份 DXF 內容與檔名不變，但 repository source path 與 package output path會改變；所有 tests／開發工具引用須在同一 change 更新。

## Risks / Trade-offs

- [素材 allowlist 漏檔或拼錯 Unicode 檔名] → 以 exact-name contract test、source existence test 與 frozen output enumeration 三層驗證。
- [來源目錄新增檔案意外出貨] → spec 逐檔複製，不使用 directory-wide copy。
- [tests 與 package 使用不同副本而 drift] → tests 與 build 共用 `assets/sample_dxf/` source，fixture tree 禁止重複。
- [Project 或 regression fixture 仍混入 release] → forbidden-root contract test加上 clean frozen smoke build。
- [移除 Project fixture 造成 regression coverage 下降] → 先盤點每個 consumer，再以程式化 Project state 或正式 DXF 改寫並保留原 assertions。
- [repository runtime data 再次被提交] → `/project_cases/` ignore rule加上 source-layout audit。

## Migration Plan

1. 建立 file-level inventory，把三份 DXF 標記為 user materials，列出全部 tracked Project cases、其 consumers 與非 Project fixture。
2. 建立 `assets/sample_dxf/` 與 shared test asset paths，移動三份 source，更新全部 consumers並執行 targeted regressions。
3. 更新 package contract tests 與 `SupportSolver.spec`，把 exact allowlist 輸出到 `sample_dxf/`，移除 Project／test directory copies。
4. 改寫所有 Project-fixture test consumers，刪除全部 tracked Project cases；只將有直接 consumer 的非 Project data 整理到 `tests/fixtures/`，並加入 runtime root ignore rule。
5. 驗證 runtime 仍能建立空 Project 目錄與保存 Project。
6. 執行 clean PyInstaller smoke build、完整 tests 與 OpenSpec strict validation。

Rollback 必須把素材 source paths、test consumers 與 package mapping 一起還原；不得只恢復 `project_cases/` copy，因為那會違反已確認的 release requirement。
