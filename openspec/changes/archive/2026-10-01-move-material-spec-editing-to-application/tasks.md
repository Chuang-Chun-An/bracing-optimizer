# Tasks

## 實作前閱讀

- **Task Group 1｜Application contract**：先讀 `proposal.md`「不變事項／In Scope」及 `design.md` Decision 1–4、Single Source of Truth；本 change 的 specs 已因純重構標為 skipped，不另讀 delta spec。
- **Task Group 2｜Application staging**：先讀 `design.md` Decision 1–3、`docs/WORKFLOW.md`「6. Project Editing and Invalidation」，以及 `tests/test_material_spec_settings.py` 的現行行為案例。
- **Task Group 3｜Main integration**：先讀 `design.md` Decision 2、4、5，並檢視 `main.py` 的 `_finish_edit()`、`delete_row()`、`_handle_input_data_changed()`；只搬移材料規格 definition workflow。
- **Task Group 4｜文件與驗證**：先回讀 `proposal.md`「Architecture／Domain／Solver／Workflow Truth」、`design.md`「Architecture Alignment／向後相容」，再對照全部 tasks；不需閱讀無關 Solver／DXF specs。

## 1. 建立 Application contract 與相容性基線

- [x] 1.1 在 `bracing_optimizer/application/material_spec_editing.py` 定義 typed request、operation／status、`ReferenceSummary`、structured failure 與 staged outcome，範圍只含 Material Spec definition edit／delete；以 import test 驗證 module 可載入且不依賴 `main`／`tkinter`／Infrastructure／Algorithms。
- [x] 1.2 切換前在 Main 層補齊現行 rename、Usage edit、delete 的 characterization tests，鎖定錯誤條件、確認時機、dialog 類型、可觀察文案與取消行為；先執行並確認全部通過，保存原 assertions，後續切換到 Application 後這批測試必須原封不動再次通過。
- [x] 1.3 另建 Application focused tests，覆蓋 no-op、`invalid_row`／`stale_request`、必要 RC lock、空白 Spec、同 Usage duplicate、referenced Usage、referenced delete 與 confirmation-required；驗證 Application 測試補充而不取代 Task 1.2 的 Main characterization tests。
- [x] 1.4 為 referenced rename 與 unreferenced definition edit／delete 建立 result lifecycle 測試，明確驗證前者回傳空 staged `ProjectResultModel` 與 cache-clear effects，後者保留獨立的 result copy、不要求清 cache，且未引用規格的修改與刪除都回傳 dirty effect。
- [x] 1.5 建立完整 state-preservation 與 transaction isolation tests：在任何修改套用前，staged `ProjectDataModel` 的全部 attributes／nested values（含測試注入的 runtime-only、DXF 綁定及構件來源資訊）必須與原 model 完全相同但 identity 獨立；並驗證 rejected、confirmation-required、no-op 與 staging exception 都不修改傳入的 `ProjectDataModel`／`ProjectResultModel`。若無法完整複製，停止並回報。

## 2. 實作材料規格 staging use case

- [x] 2.1 實作 normalized `(Usage, Spec)` key、same-Usage reference lookup 與 reference summary，覆蓋 Inventory `Spec`、Waler／Strut `material_spec`；以 case-insensitive／whitespace、跨 Usage 同名及空白值測試驗證引用範圍與現況一致。
- [x] 2.2 實作 edit／delete validation 與 two-call confirmation protocol，第二次呼叫重新驗證 expected identity 與 current references；以 confirmed、cancelled（不重呼）、確認前 state 改變及 reference set 改變測試驗證不會套用 stale staged data。
- [x] 2.3 以 `copy.deepcopy` 或經測試證明等價的完整 clone contract 建立 staged `ProjectDataModel`，不得透過會遺失 runtime-only state 的 `to_case_data()` reconstruction；在 staged copy 上原子更新 Material Specs／Inventory／Walers／Struts，並沿用 `ProjectInputChangePlan` 建立 staged results、changed tables、material summary／cache／dirty effects，以完整 attribute preservation、referenced rename 同步及 unreferenced edit／delete dirty tests 驗證 outcome。
- [x] 2.4 若 use case 需要 package-level import，僅在 `bracing_optimizer/application/__init__.py` 匯出必要 public types；執行相關 import／architecture boundary tests，確認 dependency direction 仍為 Presentation → Application。

## 3. 將 Main 改為 outcome orchestration

- [x] 3.1 將 Material Spec `Spec`／`Usage` cell edit 與 delete 改為建立 request、呼叫 use case、依 structured outcome 顯示既有 warning／confirmation；為每個 error code 新增 Main mapping coverage test，確認無遺漏，且 `invalid_row`／`stale_request` 只走既有通用輸入錯誤 warning、不新增確認或 UI；切換後原封不動重跑 Task 1.2 tests，驗證 dialog 類型、確認時機、取消行為與既有可觀察文案／錯誤條件不變。
- [x] 3.2 新增集中 `_adopt_material_spec_edit()`（或等價 presentation helper），一次採用 staged Project data／results、依 effects 清 session caches、刷新 changed tables／material summary／Results Tree／Preview 並標 dirty；以 integration tests 驗證 referenced rename 的 result invalidation 與 unreferenced edit 的 result preservation。
- [x] 3.3 為 adoption error boundary 增加測試：正式 state 換入失敗時恢復原 Project／results／cache，可觀察 UI refresh 在 commit 後失敗時不回滾已採用 state；驗證行為符合 `design.md` Decision 3。
- [x] 3.4 移除 `main.py` 已被 Application 取代且沒有 caller 的 key uniqueness、reference lookup/count、rename mutation、Usage／delete guard 與 invalidation decision；保留 request building／formatting／widget refresh，並以 `rg` 與 focused tests 確認 Main 未殘留第二套正式材料規則。
- [x] 3.5 執行現有 `tests/test_material_spec_settings.py`、`tests/test_main_project_editing.py` 與 `tests/test_project_service.py`，必要時只調整測試邊界、不降低 assertions；確認 Inventory Usage edit、一般 geometry field edit 及既有 input-change planning 未被本 change 改動。

## 4. 文件、回歸與 OpenSpec 驗證

- [x] 4.1 實作完成後更新 `docs/ARCHITECTURE.md` 的 component responsibility／state ownership，以及 `docs/WORKFLOW.md`「6. Project Editing and Invalidation」的 Application staging／Main adoption 描述；以文件 review 確認 Domain、Solver、UI layout 與 persistence truth 未被誤寫成改變。
- [x] 4.2 執行受影響的 Application／Presentation focused suite、architecture boundary tests 與完整專案 regression test；記錄命令與結果，任何既有 failure 必須與本 change 區分且不得以刪除測試、降低 assertion 或忽略錯誤處理。
- [x] 4.3 依 `proposal.md`、`design.md` 與本 checklist 進行 final review，確認沒有修改材料政策、Solver scoring／搜尋、Project schema、DXF binding、Inventory Usage workflow 或 UI layout，並確認 worktree 沒有無關修改。
- [x] 4.4 執行 `openspec validate move-material-spec-editing-to-application --strict` 與 `$openspec-verify-change`，確認 proposal／design／tasks、`skip_specs` 理由、實作及測試證據一致後，才將本 change 視為可 archive。
