# Proposal：將材料規格修改流程移至 Application

## 閱讀導航

### P0｜現在必讀

1. 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」：先確認本 change 只搬移責任，不改產品行為。
2. 本文件的「In Scope／Out of Scope」：確認 F1 的實作邊界。
3. `docs/ARCHITECTURE.md`「3.1 Presentation」、「3.2 Application」與「6. State Ownership」：確認 Main 只主持 UI，正式 Project input 仍由 `ProjectDataModel` 擁有。
4. `docs/WORKFLOW.md`「6. Project Editing and Invalidation」：既有材料規格編輯、引用同步與結果失效的相容性基準。

### P1｜實作前閱讀

- `design.md`：Application use case、request／staged result、錯誤邊界與 Main 採用流程。
- `tasks.md`：依相依順序執行實作與驗證。
- `main.py` 的材料規格 helper、`_finish_edit()`、`delete_row()` 與 `_handle_input_data_changed()`：目前待搬移的流程。
- `tests/test_material_spec_settings.py` 與 `tests/test_project_service.py` 的 input-change planning 測試：現行錯誤條件與失效行為。

### P2｜需要時再讀

- `bracing_optimizer/application/project_data.py`：`ProjectDataModel`、Material Specs／Inventory row schema 與必要 RC 規格保護。
- `bracing_optimizer/application/project_service.py`：既有 `ProjectInputChangePlan` 與其他 staged Project workflow 的慣例。
- 可以先跳過 Solver 演算法 specs、DXF recognition specs、`docs/SOLVER.md` 與 `docs/DOMAIN.md`；本 change 不修改其規則。

## 快速摘要

- 問題：材料規格 rename、Usage 修改限制、引用檢查與跨表同步目前由 `main.py` 主持，Presentation 同時承擔 UI 與 Application workflow 責任。
- 決定：新增一個 Application use case，以目前 Project input 與一個明確 command 產生成功或失敗的 staged result。
- 流程變化：Main 只收集輸入與確認、呼叫 use case、顯示錯誤，成功時一次採用 staged Project state 與失效指示。
- 不變：所有允許／拒絕條件、Inventory／Waler／Strut 同步範圍、Solver result 失效、dirty／refresh 行為與 UI layout 均維持現況。
- 規格：這是純重構，不新增或修改 observable requirement，因此不建立 delta spec。

## 現況與目標

| 面向 | Before｜現況 | After｜目標 |
| --- | --- | --- |
| 流程 owner | Main 直接查找引用、判斷 rename／Usage／delete、修改多張 Project tables 並觸發失效 | Application use case 完成驗證與 staging；Main 只協調 UI |
| 修改方式 | Main 依序原地修改 Material Specs、Inventory、Walers、Struts | use case 先建立完整 staged result；成功後由 Main 一次採用 |
| 錯誤處理 | Main 根據分散條件直接顯示 warning | Application 回傳結構化失敗；Main 沿用現行文字與互動時機顯示 |
| 結果生命週期 | Main 以 `ProjectInputChangePlan` 決定 Solver result／cache 失效 | staged result 明確攜帶既有失效與 refresh 指示，Main 採用後執行 |
| 可測試性 | 核心行為需建立不完整的 `SupportInputApp` 測試 | rename、Usage、引用同步與 delete 可脫離 Tkinter 測試 |

`staged result` 指 Application 在不修改目前 live state 的前提下，先產生可完整採用的新 Project input 與 side-effect 指示；只有成功結果才可被 Main 採用。

## 主要流程

```text
使用者編輯／刪除材料規格
→ Main 收集 row identity、欄位值與必要的 rename 確認
→ Application use case 驗證 key、Usage、必要 RC 規格與引用狀態
→ Application 在複本同步 Material Specs／Inventory／Walers／Struts
→ Application 回傳失敗，或完整 staged result
→ Main 顯示既有錯誤，或一次採用 staged result
→ Main 依 staged 指示清除結果／cache、更新材料摘要、dirty 與畫面
```

## 不變事項

- Material Spec key 仍以正規化後的 `(Usage, Spec)` 判定，rename 只同步相同 Usage 的引用。
- 被引用規格仍不得改變 Usage；被引用規格 rename 仍需使用者確認；取消確認時不得修改任何 state。
- 空白或重複 Spec、必要 RC 規格保護、被引用規格不得刪除等錯誤條件維持現況。
- rename 仍同步 Inventory `Spec`、Waler／Strut `material_spec`，並依現行規則使 Solver result 與 caches 失效；未被引用的 Material Spec definition 修改仍不失效 Solver result。
- 不改材料政策、Solver input／scoring、Project persistence schema、DXF binding 判斷或 UI layout。

## Why

F1 指出材料規格修改已是一個跨 Material Specs、Inventory、Waler、Strut 與 result lifecycle 的完整 use case，但目前集中在 `main.py`，使 Presentation 成為規則與 transaction boundary 的 owner。將流程移至 Application 可符合既有架構方向、提供無 Tkinter 的原子測試邊界，並避免未來各 UI 入口重複或漏做引用同步與結果失效。

## What Changes

- 新增 Application material-spec editing use case，涵蓋 rename、Usage 修改限制、引用查找、刪除保護、跨表同步及 input-change effect planning。
- 定義明確 request、成功 staged result 與結構化失敗結果；失敗不得改動傳入的 live Project state。
- 將 Main 縮減為收集 UI 輸入／確認、呼叫 use case、顯示既有錯誤及採用 staged result。
- 將規則與 transaction 測試移至 Application 層，保留少量 Main integration tests 驗證 UI orchestration。
- 視實作結果更新長期架構／workflow 文件，使 ownership 描述與實際程式一致，但不把本提案階段描述成已完成。

## In Scope

- Material Spec definition 的 Spec rename、Usage edit 與 delete workflow。
- 以 `(Usage, Spec)` 查找 Inventory、Waler、Strut 引用及引用數量／摘要資料。
- 成功 rename 時的 Material Specs／Inventory／Waler／Strut staged synchronization。
- 與既有 `ProjectInputChangePlan` 一致的 Solver result／cache 失效、材料摘要更新、dirty 與 refresh 指示。
- Main 與 Application 的 focused tests、相關 architecture boundary tests 及既有材料設定 regression tests。

## Out of Scope

- 新增或改變材料規格、可購買長度、Inventory 數量、RC 必要規格或其他材料政策。
- 修改 Support／Waler Solver scoring、合法性、candidate generation 或搜尋參數。
- 改變材料設定頁、Treeview、dialog、文案、確認步驟或其他 UI layout／interaction。
- 修改 Project JSON schema、migration、DXF import／binding 規則或其他一般 Project field editing。
- 順帶抽取 `main.py` 其他編輯流程、建立通用 command framework 或進行無關 cleanup。

## Capabilities

### New Capabilities

無。本 change 為純架構重構，沒有新的 observable behavior；`.openspec.yaml` 使用 `skip_specs: true`。

### Modified Capabilities

無。`docs/WORKFLOW.md`「6. Project Editing and Invalidation」所描述的既有行為與錯誤條件全部維持。

## Architecture／Domain／Solver／Workflow Truth

- **Architecture**：預期修正實作與既有架構原則的落差，使 Application 成為材料規格編輯 workflow／transaction owner；不是新增 layer 或改變 dependency direction。
- **Domain**：不變；本 change 不重新分類或修改材料工程規則。
- **Solver**：不變；只保留現行 result／cache invalidation trigger。
- **Workflow**：user-visible truth 不變；內部流程由 Main 原地協調改為 Application staging、Main 採用。

## Impact

- 主要受影響：`main.py`、`bracing_optimizer/application/` 下新增或擴充的材料規格編輯 use case、Application package exports，以及 `tests/test_material_spec_settings.py`／新增 focused Application tests。
- 可能小幅調整：`bracing_optimizer/application/project_service.py` 的 input-change planning reuse，以及 `docs/ARCHITECTURE.md`／`docs/WORKFLOW.md` 的 ownership 描述。
- 不新增外部 dependency，不改 public persistence contract，不需資料 migration。

## 尚未決定事項與重新評估條件

- use case 採獨立 `material_spec_editing.py` 或由既有 Project service 組合，留待 design 決定；不得因此擴張成通用 editing framework。
- 若實作探索發現現行 UI 存在本文件未列出的可觀察錯誤條件或 side effect，應先補入相容性矩陣並回報，不得自行「修正」行為。
- 若 staged copy 的成本在實際 Project 規模造成可量測的 UI 問題，才重新評估較窄的 immutable patch；不得以效能假設預先犧牲原子性。
