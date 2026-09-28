# Design

## Context

See [proposal.md](./proposal.md) for motivation and scope, and [support-editor-result-mutation spec](./specs/support-editor-result-mutation/spec.md) for behavior.

`SupportInputApp._open_support_plan_editor()` 目前在將 committed plan pieces 載入 Treeview 後，立即呼叫內部 `evaluate_and_refresh()`。該 callback 會呼叫 `SupportPlanEditing.stage_edit()`，即使輸入 pieces 與來源 plan 相同，仍建立 deep-copied solution、重算單支及全域分析；Main 隨後無條件執行 `item["result"] = solution` 與 `_mark_results_updated()`。後者透過 `ProjectResultModel.mark_updated()` 更新 `last_calculated_time` 和 persisted projection，再設定 Project dirty。這就是初始化 no-op 仍產生正式 mutation 的直接原因。

現有責任邊界已可支援修正：`SupportPlanEditing` 擁有 piece normalization、shared-layout group 影響範圍和 staged engineering result；Main 擁有正式 result adoption、dirty 與 UI refresh。Waler Editor 已能在相同欄位值時不提交，但本 change 不把兩種 Editor 重構成共用 framework。

## Goals / Non-Goals

**Goals:**

- 讓 Application 明確判定 normalized Support edit 是 no-op 或實際修改。
- 在任何正式 result assignment、timestamp 更新或 dirty side effect 之前完成判定。
- 初始化與相同值 edit 仍可顯示現有狀態摘要，但不重算或採用正式結果。
- 實際修改繼續使用現有 stage、immediate commit、invalid-result 保留與 refresh 流程。
- 讓 no-op／changed adoption boundary 可以脫離完整 Tkinter 視窗測試。

**Non-Goals:**

- 不把 Support Editor 改成 close-time Apply／Cancel transaction。
- 不 rollback 已 immediate-commit 的真實修改。
- 不修改 Support engineering validation、scoring、adjacency 或 Solver input。
- 不改 Waler Editor、Project schema、result persistence 格式或 calculated-time 格式。
- 不拆分 `main.py` 或建立通用 Editor framework。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

| Layer | 本 change 的責任 |
| --- | --- |
| Presentation (`main.py`) | 維持 Editor draft／widget state；呼叫 Application staging；只在明確 changed outcome 時採用結果、標記 dirty 及刷新正式 UI。 |
| Application (`plan_editing.py`) | 正規化 requested pieces、決定 shared-layout 影響範圍、比較目前 committed layouts，並回傳明確 no-op／changed staged outcome。 |
| `ProjectResultModel` | 繼續作為正式 result、`last_calculated_time` 與 persisted projection 的唯一 owner；本 change 不改其 `mark_updated()` 語意。 |
| Domain／Algorithms | 維持現有工程規則與計算；只有 changed edit 才走既有重新評估路徑。 |
| Infrastructure | 無變更。 |

依賴方向仍為 Presentation → Application → Algorithms／Domain。Tkinter 不取得 shared-layout 或 piece normalization 的第二套判定邏輯。

## Decisions

### 1. `SupportPlanEditResult` 明確表達 `changed`

在既有 staged-result contract 增加明確布林欄位（例如 `changed`），由 `SupportPlanEditing.stage_edit()` 回報本次 normalized input 是否會改變任何受影響 Support 的 committed piece layout。Presentation 不以 solution object identity、`updated_support_ids` 是否為空或深度序列化比較來猜測 mutation。

Changed outcome 繼續帶回既有 staged solution、plan、validation、neighbor checks 與 analysis。No-op outcome 保留 current solution／plan 作為 Editor 呈現資料，`updated_support_ids` 為空，且不建立可被誤認為新正式 truth 的重新計算 solution。

**Rejected alternative：**只在 Main 比較 Treeview raw strings。這會在 Presentation 複製 type/length normalization，且容易漏掉 shared-layout group 內的其他 member。

**Rejected alternative：**讓 `ProjectResultModel.mark_updated()` 自行深度比較。呼叫時 Main 已可能替換 result，而且該方法服務所有 Solver／manual-result commit；擴大其語意會影響無關流程。

### 2. 在 Application staging 的 deep copy／重算前判斷 no-op

`stage_edit()` 沿用同一套 normalization 與 validation 取得 canonical ordered `(piece_type, length)` layout，並先依現有 shared-layout group 規則找出 `target_ids`。只有當 requested layout 與每一個 target member 的 current committed layout 都相同時，才回傳 `changed = False`。

若任一 member 不同，才進行目前的 config 建立、solution deep copy、`evaluate_single_support()`、geometry adjacency assembly、global recalculation 與分析。這保留 shared group 可能需要修復不一致 member 的既有行為，也避免初始化 no-op 產生不必要計算。

比較基準永遠是 callback 當下的最新 committed solution，不是 Editor 開啟時的 snapshot。因此一次真實修改已 immediate commit 後，再改回更早 layout 仍是第二次真實修改。

**Rejected alternative：**只比較使用者目前選取的單支 Support。Shared-layout target 本身可能相同，但同 group 另一支仍不同；略過會錯失既有同步更新。

**Rejected alternative：**比較完整 solution／plan object。Score、breakdown、diagnostics 或 runtime metadata 不是 Editor 的 editable input，完整物件比較會製造 false positive，並把本 change 擴大成 result canonicalization。

### 3. Main 使用窄的 adoption gate，no-op 只更新 Editor display

把正式採用縮成可獨立測試的小 boundary（可為 `SupportInputApp` helper 或等價窄函式）：

- `changed = False`：不 assign `item["result"]`、不呼叫 `_mark_results_updated()`、不刷新正式 Results Tree／Preview；Editor 可使用 current plan、validation 與 analysis 更新自己的 status／summary widgets。
- `changed = True`：沿用目前 assignment、`_mark_results_updated()`、Results Tree selection/open state 與 `update_preview(preserve_view=True)`。

初始化仍可走同一個 evaluation/display callback，但 Application no-op outcome 會阻止正式採用。這也涵蓋 FocusOut／Return／Combobox callback 對相同值的重複觸發。

**Rejected alternative：**單純刪除 Editor 最後一次 `evaluate_and_refresh()`。這只修正開啟情境，無法保護相同值的 edit callback，也可能讓初始 status／summary 不完整。

**Rejected alternative：**新增 Apply／Cancel 按鈕並在關閉時一次提交。這會改變已確認的 immediate-commit 產品語意，並引入 rollback／draft lifecycle，超出範圍。

### 4. 保持時間與 dirty 的現有 single source of truth

`ProjectResultModel` 中的 committed result、`last_calculated_time` 與 persisted projection 仍是正式成果 truth；Main 的 `project_dirty`／`project_dirty_reason` 仍是 session navigation truth。No-op 不呼叫現有 mutation APIs，因此自然保留 clean 或既有 dirty 狀態，而不是在 no-op 後嘗試回復時間或 dirty。

這避免維護 Editor-open snapshot，也避免 no-op 對其他尚未保存修改的 dirty reason 造成覆蓋。

## Backward Compatibility and Persistence

- 不改 Project schema、serialized result shape 或 Save／Load contract。
- `changed` 只存在 Application runtime staged outcome，不持久化。
- 舊 Project 載入後使用相同 committed piece layout 比較，無 migration。
- 實際 Support edit 的 result payload、timestamp 與 dirty behavior 維持相容。

## Risks / Trade-offs

- **[Risk] Piece normalization 在 validation 與 comparison 間漂移。** → 抽取或重用單一 Application normalization helper，兩者不得各自實作轉型規則。
- **[Risk] Shared-layout group 的歷史資料已不一致。** → 比較所有現有 target members；只要任一 member 不同即視為 changed，交由既有 stage path 同步。
- **[Risk] 多個 widget event 對同一次輸入重複觸發。** → 每次都以最新 committed solution 判定；首次 changed commit 後的重複事件自然成為 no-op。
- **[Risk] No-op outcome 被未來 caller 誤採用。** → 使用明確 `changed` contract、窄 adoption helper與 boundary tests，禁止依 object identity 推論。
- **[Trade-off] No-op 仍可能執行輕量 normalization／current-state analysis。** → 這些是 read-only Editor 呈現成本；避免正式 engineering reevaluation、result replacement 與 mutation side effects 優先。

## Migration Plan

1. 先以 tests characterization 現有 Support Editor 初始化、Application staging 與 timestamp／dirty boundary。
2. 增加 no-op-aware staged outcome 與 shared-layout comparison，保持 changed path 測試綠燈。
3. 將 Main adoption／refresh 放在 `changed` gate 後，補 headless presentation tests。
4. 執行 manual editing、Project result lifecycle、UI boundary 與完整 regression tests。
5. 驗證後更新 `docs/WORKFLOW.md`，將 Support editor no-op 從 Product Gap 改為 implemented behavior。

Rollback 只需移除 no-op branch 與 Presentation gate；沒有 schema 或資料 migration。
