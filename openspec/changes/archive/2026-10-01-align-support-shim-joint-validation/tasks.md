# Tasks

## 閱讀導航

- **現在必讀（P0）**：依序執行 Task Group 1～5；不可跳過 characterization regression、文件更新或 strict validation。
- **實作前閱讀（P1）**：`proposal.md` 的 In Scope／Out of Scope、`specs/support-shim-joint-validation/spec.md` 全部 Requirements、`design.md` Decision 1～5。
- **需要時再讀（P2）**：`docs/SOLVER.md` Support evaluation／11.1／14、`docs/DOMAIN.md` Support hard rules，以及既有 DXF double-support、Project validation、adjacency tests。

## 1. 先建立 characterization 與 focused tests

- [x] 1.1 在 `tests/test_support_waler_type_rules.py` 建立 Shim count／placement matrix：零塊、一塊、多塊非零 Shim；Steel／Steel、From RC、To RC、RC／RC；`shim = 0` 不產生 piece；零長手動 piece 仍由 basic normalization 拒絕。加入缺失、空白、未知 Waler type 視為 Steel，以及明確 RC 保持 RC 行為的案例。
- [x] 1.2 在 `tests/test_support_waler_type_rules.py` 建立 boundary-aware joint tests：`shim -> steel`、`steel -> shim`、`shim -> jack`、非 terminal joint、另一端 end zone、恰好 `1600 mm`、Column `±830 mm`、Beam `±550 mm`，並證明 missing／unknown type 不可使用 RC 例外。
- [x] 1.3 在修改 implementation 前，記錄具代表性不合法 candidates 的精確 score、penalty、score breakdown 與相對排序，至少涵蓋 Jack 數量錯誤、多塊 Shim、禁區接頭、Steel 長度錯誤。建立 characterization assertions，要求修改後逐值完全相同、不使用容差；確認 `count_forbidden_piece_joints` 等既有扣分即使被 reason gate 隱藏仍會執行。若無法同時維持 reason gate 與既有扣分，停止並回報。
- [x] 1.4 新增 deterministic issue tests：Jack count 錯誤時 reason 只回報 Jack count；Jack 正確但 Shim 超過一塊時 reason 只回報 Shim count；其餘多 issue 依 Shim placement、gap、forbidden joint、Steel length 固定排序，且不受 piece／collection／execution order 影響。同時斷言 gate 不改變 Task 1.3 鎖定的 score／penalty／breakdown。
- [x] 1.5 保留並補強既有 characterization regression：DXF 雙路要求相同精確 Waler ID pair；方向相反時 canonicalize 後仍可辨識；不同 pair 不成立；Main／Project validation 對手動 SharedLayoutGroup 要求相同 ordered `(FromWaler, ToWaler)`。此 task 只鎖定既有行為，不新增 type-only 規則。

## 2. 實作共用 Support legality contract

- [x] 2.1 在 `bracing_optimizer/algorithms/support.py` 建立共用 Waler type normalization 與 Shim validator，輸出可穩定排序的 structured issues；接入 `evaluate_single_support`，實作只影響 reason projection 的 Jack count、Shim count gates 與後續固定 issue order。不得用 gate early-return 完整 evaluation；修改前的 scoring inputs、`count_forbidden_piece_joints`、penalty 與 score breakdown 必須照常計算。
- [x] 2.2 在 `bracing_optimizer/application/plan_editing.py` 讓 `_validate_normalized_pieces`／staged recalculation 消費共用 verdict，不在 Application 或 Presentation 複製 Waler type、Shim count 或 placement 規則。
- [x] 2.3 在 `bracing_optimizer/algorithms/support.py` 將 RC end-zone 例外改為 typed boundary 判斷，只允許 matching RC terminal 的 `shim -> steel`／`steel -> shim`；Column、Beam、另一端與其他 joints 維持 invalid。同步讓 Application forbidden-zone diagnostics 使用同一 boundary-aware 結果。
- [x] 2.4 檢查 diff，確認未修改 scoring constants、penalty inputs、材料比例、candidate count、Beam Width、Random Seed、search stages、cache selection version、Jack adjacency 或 persistence schema。比對 Task 1.3 的不合法 candidates，確認 score、penalty、score breakdown 與相對排序逐值完全相同；再以既有實際圖面 fixture 執行完整 Support 求解，確認 Waler identity／類型一致且原本合法的案例，其候選集合與最終結果和修改前相同。不得以調整 scoring／search 參數修正回歸。

## 3. 人工編輯、診斷與相容性測試

- [x] 3.1 在 `tests/test_plan_editing.py` 加入人工多 Shim、錯誤 placement、missing type 與 issue priority 案例，確認 Application validation、`SupportPlan.reason` 與自動 evaluation 一致。
- [x] 3.2 更新並測試 `SupportPlanEditing.find_forbidden_zone_hit` 或其替代共用接口，確認 RC exception 與 Column／Beam overlap 的 UI 診斷不會和 plan validity 漂移。
- [x] 3.3 新增 transaction tests：可解析的 Shim count／placement／joint invalid 仍 `changed=True`、保存 invalid staged result、更新 calculated time／metadata／dirty state；零長、負長或不可解析 piece 仍拒絕且 committed solution 不變。
- [x] 3.4 新增 legacy result tests：Project load 不因本 change 自動重新驗證或改寫已保存結果；下一次完整 Support 重算或 staged recalculation 才套用新規則。
- [x] 3.5 執行 `tests/test_plan_editing.py`、`tests/test_support_waler_type_rules.py`、`tests/test_optimize_support_zone.py`、`tests/test_support_adjacency_phase2.py`、`tests/test_support_adjacency_geometry.py`、相關 `tests/test_double_support.py` 與 Project validation tests，確認 manual workflow、Solver、adjacency、exact Waler identity 與 pre-solve validation regressions 全部通過。

## 4. 更新 long-term truth 文件

- [x] 4.1 必須更新 `docs/DOMAIN.md`：每個 layout 只能有零塊或一塊非零 Shim；RC terminal Shim 與第一段 Steel 的交界是唯一 `1600 mm` 例外；Column／Beam 不豁免；Waler 類型缺失／空白／未知視為 Steel；雙路支撐維持兩支 Strut 的 canonical 同端精確 Waler ID 相同（不只是同一 chain 或 type）；舊結果載入時不自動重驗，下次重算才套用新規則。
- [x] 4.2 必須更新 `docs/SOLVER.md`：在 11.1 SupportPlanEditing 移除「人工 Support editing 尚未驗證 RC／Steel Shim placement」的描述，改為說明共用 validator 與 invalid 保存語意；在 14 Known Solver Gaps 將 Gap 4 標記為已解決，並記錄不修改 scoring／search。

## 5. 完整驗證與 Review

- [x] 5.1 執行最接近修改的 focused tests，再擴大至 Support Solver regression 與 architecture boundary tests；檢查沒有刪除、弱化或跳過既有 assertions，且無不相關修改。
- [x] 5.2 執行 `openspec validate align-support-shim-joint-validation --strict`；完成實作後再使用 `$openspec-verify-change` 對照 proposal、spec、design、tasks，確認所有 Requirements 有測試且未超出 Out of Scope。
