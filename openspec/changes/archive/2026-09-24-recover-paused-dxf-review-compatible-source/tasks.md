# Tasks

## 1. 建立 Review Recovery 核心

- [x] 1.1 在 `dxf_import` 新增或校正非 UI 的 recovery stage、plan、summary entry/result 資料契約，正式實作互斥的 `preserved`／`requires_review`／`disabled` 語意；以單元測試驗證每個 entry 恰屬一類、counts 只由 entries 推導、disabled entry 不影響 recovered engineering state，以及資料物件不會修改輸入 state。
- [x] 1.2 抽取或重用既有 line/handle matching primitive，實作同角色且一對一的 Waler／Strut／Brace matching：先以既有 geometry tolerance 篩選，再依 shared handle、same layer、changed layer 排 evidence priority，同 priority 內依 error 與既有 ambiguity tolerance 判定；以測試驗證 tolerance 邊界、各 evidence priority、歧義、缺少既有構件、跨角色禁止配對、候選不可重用與候選新增構件。
- [x] 1.3 實作隔離的候選重新辨識與 Review setting 篩選；驗證候選仍存在且有效的 layer mapping、coordinate system、import mode 分類為 `preserved`，missing/unseen layer 與無效 coordinate/import setting 使用既有 safe/default behavior 並分類為 `requires_review`，且舊 candidate／association／validation 不會被複製。

## 2. 選擇性恢復 Review 狀態

- [x] 2.1 依唯一 member mapping 重新綁定材料規格、人工端點與 Waler 接觸輸入，再交由既有 replay helper 驗證；逐類測試 replay 成功一律為 `preserved`、replay 失敗或無安全映射一律為 `requires_review`，候選 state 保持可處理，且不得套用到錯誤構件或分類為 `disabled`。
- [x] 2.2 實作 source exclusion、雙路支撐 decision 與 confirmation 的固定恢復分類；測試 exclusion 僅在 exact source identity 對同 role 仍有效時為 `preserved`，changed handle 即使有 geometry-only member match 也不得轉移且一律為 `disabled`；兩支 Strut 唯一 rebind 且候選 pair 唯一存在的雙路 decision 為 `preserved`，否則為 `requires_review`；current-state signature 有效的 confirmation 為 `preserved`，否則從 recovered state 移除並為 `requires_review`。
- [x] 2.3 在所有 replay 後以現有函式重建 candidate points、double-support candidates、associations、validation 與 Review items，再由既有 serializer 產生 version 2 recovered state；測試 recovered state 的來源 path/fingerprint 正確、衍生資料來自候選且 schema 未增加 recovery 欄位。

## 3. 擴充 Application 評估與提交契約

- [x] 3.1 擴充 `ProjectService` paused Review Relink evaluation，使 fingerprint mismatch 產生不可直接提交的 recovery seed，並接收 DXF planner 的 `COMPATIBLE_RECOVERY_AVAILABLE`／`INCOMPATIBLE_SOURCE`／`VALIDATION_FAILED` 結果；以 `tests/test_project_service.py` 驗證 workflow、缺少 fingerprint、檔案錯誤與各狀態。
- [x] 3.2 擴充 compatible plan 與 commit，使提交前重驗 workflow、base-state token、candidate path/fingerprint，並回傳可供原子採用的 recovered state/status report；測試候選改變、Review state 改變與狀態建立失敗都拒絕且不回傳可採用資料。
- [x] 3.3 保留 Exact Match 原有快速路徑與選檔即授權行為，執行既有 paused Review Relink service tests 並新增 assertion，確認 Exact Match 不觸發 recognition、summary 或 compatible confirmation。

## 4. 串接既有 DXF Review 與 Main

- [x] 4.1 在既有 DXF Review dialog/workflow 路徑建立 staged recovery，不放入任何 matching 規則；以 headless workflow/dialog tests 驗證 summary 同時顯示 `preserved`、`requires_review`、`disabled` 的 count/reason，接受與拒絕回傳正確結果。
- [x] 4.2 擴充 `main.py` paused Review Relink 分流：Exact Match 直接提交，Compatible Source 顯示 summary 並只在明確接受後提交；以 UI interaction tests 驗證取消選檔、拒絕、關閉、驗證失敗與重試全部維持原 paused Review、dirty state、Project 與 Solver state。
- [x] 4.3 擴充既有 adoption rollback snapshot，使單一 atomic adoption／rollback 明確涵蓋 candidate source reference、recovered serialized Review state、candidate `world_result` runtime cache、dirty state、recovery／asset reports，以及現有 snapshot 已保護的所有欄位（包含 `dxf_last_import_debug`、`dxf_asset_status_report`、compatibility report、dirty flag/reason、`dxf_review_session`）；測試成功時整組採用並淘汰舊 fingerprint cache、workflow 維持 `REVIEW`，任一步驟失敗時整組回復且不得留下 source/state 混合 truth 或執行 Review completion。
- [x] 4.4 驗證 compatible recovery 成功後透過既有 resume path 開啟同一個 DXF Review workspace，候選新增構件與失效決策仍待 Review，且沒有建立第二套 editor 或 Main 幾何辨識功能。

## 5. 持久化、邊界與文件

- [x] 5.1 新增 Save／Load round-trip 測試，驗證接受 recovery 後仍使用現有 Project schema 與 Review state version、Relink 不寫入 managed DXF、Save 才更新管理副本，重新載入仍為可繼續的 `REVIEW`。
- [x] 5.2 更新或新增 architecture-boundary tests，驗證 recovery matching/replay 不位於 `main.py`／Tkinter、Domain 與 Algorithms 不依賴 DXF recovery，且 completed Project Relink 與 paused Review recovery 仍是不同 contract。
- [x] 5.3 實作與測試全部通過後更新 `docs/WORKFLOW.md`，將 exact-only 限制改為已實作的 compatible recovery、明確接受、零副作用與 cache/source-of-truth 行為；確認 `docs/ARCHITECTURE.md`、`docs/DOMAIN.md`、`docs/SOLVER.md` 不需改動。

## 6. 最終驗證

- [x] 6.1 執行直接相關測試：`.venv\Scripts\python.exe -m pytest tests/test_project_service.py tests/test_dxf_review_workflow.py tests/test_dxf_review_application.py tests/test_dxf_source_exclusion.py tests/test_double_support.py tests/test_dxf_review_confirmation.py tests/test_project_persistence.py`，並修正所有非預期失敗。
- [x] 6.2 執行 UI、boundary 與完整 regression test suite，確認 Exact Match、completed Project Relink、DXF Review、Save／Load、Project/Solver result lifecycle 均未退化。
- [x] 6.3 執行 `openspec validate recover-paused-dxf-review-compatible-source --strict` 與 OpenSpec implementation verification，逐項核對 proposal、spec、design、tasks 與實作證據後才將 change 視為完成。
