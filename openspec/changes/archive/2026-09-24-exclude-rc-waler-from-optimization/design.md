# Design

## Context

需求動機見 [proposal.md](proposal.md)。目前 `ProjectDataModel.walers[*].material_spec` 是正式材料規格，`RC` 也是不可刪除的圍令材料規格；`SupportInputBuilder` 會由同一欄位把端部 Waler 分成 `RC`／`Steel`，因此不能從 Project 或共用幾何資料中移除 RC。

現行 `WalerInputBuilder.build_all()` 會為全部正式 Waler 建立 `WalerProblemInput`。Main 的 Single／Global 入口之後才檢查 purchasable lengths，所以 RC 會被當成「沒有庫存料長」；Global 更會因此阻擋其他 Steel Waler。`OptimizeWalerGlobal` 目前也逐一把所有收到的 inputs 交給 `OptimizeWaler`。

現行 Main 欄位編輯已經透過 `_commit_project_field_edit()` → `_handle_input_data_changed()` → `ProjectService.plan_input_change()` 集中處理。任何 `walers` input edit 都會呼叫 `_invalidate_solver_state_after_input_change()`，清除 `ProjectResultModel`、Single Waler `solver_memory` 與 Support candidate cache。由於 Waler 類型也會改變 Support Shim placement，這個廣泛失效行為是安全且必要的。

## Goals / Non-Goals

**Goals:**

- 用一個 Application-level policy 一致判斷 RC Waler 是否須排除於材料配置最佳化。
- 讓 Main 與 Application use cases 都阻止 RC 進入 Waler algorithms。
- 保持 RC 在 Project／Support contract 中的完整語意。
- 重用既有 input-change invalidation，並把 historical RC result cleanup 納入 Global atomic adoption，不增加第二套 result truth。

**Non-Goals:**

- 不改變 `wales.py`、`waler_global.py` 或搜尋／評分設定。
- 不讓 `WalerInputBuilder` 隱藏 RC，因為 builder 仍負責忠實轉換正式 Project Waler。
- 不建立新的 Waler type 欄位或 persistence schema。
- 不在載入時主動 migration 或修復舊檔中可能已存在的 RC Waler result payload。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 dependency direction：

```text
Main / Solver Dialog (Presentation)
        ↓
RC exclusion policy + OptimizeWaler / OptimizeWalerGlobal (Application)
        ↓
Waler algorithms（只收到 eligible non-RC input）

ProjectDataModel（仍含 RC）
        ↓
SupportInputBuilder（仍解析 RC／Steel 端部類型）
        ↓
Support Solver
```

- Presentation 負責顯示可選集合與無可計算對象的訊息。
- Application 是 optimization eligibility 的 single source of truth，並在 use-case boundary 做防禦性保證。
- Domain Project model 仍保存 RC 的工程身份；Algorithms 不新增 RC 特例。
- `ProjectResultModel` 仍是 committed result 的唯一 truth；不新增 RC 專屬結果集合。

## Decisions

### 1. 以正式 `material_spec` 判定 RC，集中於 Application policy

新增一個小型 pure policy（優先放在既有 `optimize_waler.py` 邊界或同層小模組），以 `str(value).strip().casefold() == "rc"` 判定不可進行 Waler optimization，並提供可重用的 RC exclusion／partition 操作。Main、`OptimizeWaler` 與 `OptimizeWalerGlobal` 必須使用同一 policy，不各自複製字串判斷。

這是單向的 RC exclusion policy，不是完整 RC／Steel 二分類。`not RC` 只代表仍須沿用既有 validation 與求解流程；blank、unknown 或自訂規格不得因此被重新命名或宣告為 Steel。也不應透過「是否有 purchasable lengths」間接推斷 RC，否則會把資料缺漏的非 RC 規格誤認為 RC。

**Rejected alternatives:**

- 只在 UI 判斷：其他 Application caller 仍可把 RC 送入演算法。
- 在 `wales.py` 特判 RC：污染 algorithm boundary，且違反不修改 Solver 演算法的需求。
- 從 `WalerInputBuilder` 完全移除 RC：會讓 builder 不再忠實表示 Project，並可能誘發 Support／其他 caller 對正式構件的錯誤假設。

### 2. Presentation 先縮小可操作集合，Application use case 再防禦

Main 取得 `WalerInputBuilder.build_all()` 的結果後，先依共用 policy 分成 eligible non-RC 與 excluded RC。此處 eligible 只表示未被 RC 排除，不表示已通過既有 validation：

- Single：`WalerSelectionDialog` 只收到 eligible non-RC IDs。集合為空時，顯示「沒有可進行材料配置的 non-RC Waler」並返回；不開 Solver Dialog。後續 purchasable-length check 只針對被選取的 non-RC Waler。
- Global：missing inventory、人工修改覆蓋確認及傳入 `WalerGlobalSolverDialog` 的 inputs 都只使用 eligible non-RC Waler。可在現有 result/status area 說明 RC 已排除，但不要求新增複雜 summary UI。集合為空時直接回報並返回。

`OptimizeWaler.execute()` 在建立 algorithm config 前拒絕 RC request，形成 Single use-case contract。`OptimizeWalerGlobal.execute()` 自行再次 partition inputs，確保直接呼叫時也不把 RC 傳給 local optimizer；若 partition 後為空，回傳既有形狀的 invalid／no-op application result，且不得呼叫 algorithm。Presentation 正常路徑會更早攔截，所以不會用此結果開啟／提交 Dialog。

此雙層設計讓 UI 有清楚行為，同時避免 Presentation 成為唯一安全邊界。

### 3. Global solve scope 使用 eligible non-RC inputs，adoption 同時清除 historical RC results

`OptimizeWalerGlobal` 的 `waler_order`、diagnostics `waler_count`、local records、candidate groups 與 selected candidates 都由過濾後的 non-RC inputs 建立。Global algorithm result 不承載 RC candidates。

Main 另由目前正式 Project Waler rows 使用同一 RC policy 取得 `excluded_rc_waler_ids`，在呼叫 `ProjectResultModel.stage_waler_global_result()` 時明確提供。Staging 以 copy-on-write 方式移除：

- selected non-RC Waler IDs 的舊結果；
- `excluded_rc_waler_ids` 對應的所有 historical Waler configuration results。

完成全部新 selected results staging 後才回傳 apply plan。Main 沿用既有 atomic commit／rollback；因此 Solver failure、invalid solution、staging failure 或 commit failure 都不會清除 RC result，commit 後的 UI refresh failure 則不回滾已提交的新結果與 RC cleanup。

人工修改覆蓋確認只掃描 eligible non-RC IDs，因為 RC historical results 是依正式 RC identity 清理，不是重新求解或以新方案取代。全 RC Project 在 preflight 即 no-op，沒有 valid Global adoption，因此不藉此清理 historical results。

### 4. 沿用既有完整 Solver state invalidation

不新增只刪單支 Waler 結果的 API。成功修改任何 Waler `material_spec` 時，繼續走現有 `ProjectService.plan_input_change(table_name="walers", ...)`，由 Main 清除：

- 全部 committed Solver results 與 persisted result payload；
- `solver_memory`；
- `support_candidate_cache`。

這比只清除該支 Waler result 更符合依賴關係：Steel↔RC 會改變相連 Strut 的 Support 端部規則。RC 改回 Steel 時，由於舊結果已被清除，不存在自動恢復路徑；使用者須重新求解。

編輯未成功或 value 未變時，現有 `_commit_project_field_edit()` 在 post-processing 前返回，維持零副作用。實作只需補齊 regression tests，不應重寫此 lifecycle。

### 5. 文件與 persistence 邊界

實作完成後：

- `docs/DOMAIN.md` 補充 RC Waler 是正式連接構件，但不是鋼圍令材料分段配置對象。
- `docs/SOLVER.md` 補充 Single／Global 只對 eligible non-RC input 執行既有搜尋，演算法本身不增加 RC 分支。
- `docs/WORKFLOW.md` 補充 Single／Global 的 eligibility、全 RC no-op，以及材料切換沿用完整結果失效。

不新增 Project JSON 欄位、result schema version 或 load-time migration。舊檔載入後的正式 Project Waler 仍完整保留；既有檔案若含 RC Waler historical result，會在 material edit 的既有完整 invalidation，或下一次 valid Global result 成功採用時清除。單支求解與全 RC no-op 不主動清理其他 historical results。

## Risks / Trade-offs

- [Eligibility 在多入口 drift] → Main、Single use case 與 Global use case 全部引用同一 Application policy，並以 direct-use-case tests 防守。
- [Global diagnostics 數量與 Project Waler 總數不同] → 明確將 `waler_count` 定義為本次 eligible non-RC solve scope；UI 可另外顯示排除資訊，不把兩者混為一談。
- [過濾太晚導致 RC 缺料仍阻擋] → 所有 inventory precheck 必須在 partition 後只檢查 eligible inputs。
- [只失效 Waler result 會留下錯誤 Support result] → 保留既有完整 invalidation，不做局部最佳化。
- [RC cleanup 在 result commit 前產生部分 mutation] → cleanup 只能修改 staged copy，並納入既有 commit／rollback snapshot；不得在 Solver 啟動或 staging 完成前直接刪除正式 result。
- [舊 persistence 可能含 RC result] → 不做 load-time migration；valid Global adoption 或 material edit 會清除，Single／全 RC no-op 則保留到後續正式 lifecycle。

## Migration Plan

1. 加入純 eligibility policy 與 Application boundary tests。
2. 套用至 Single／Global Main preflight 及 Global use case，保持 algorithms 不變。
3. 補齊混合／全 RC、Steel regression、Support RC 與 material edit invalidation tests。
4. 更新 `docs/DOMAIN.md`、`docs/SOLVER.md`、`docs/WORKFLOW.md` 並執行 focused、boundary 與 full regression。

若需 rollback，可一併移除 policy 與入口過濾；沒有 persistence schema 或資料 migration 需要回復。
