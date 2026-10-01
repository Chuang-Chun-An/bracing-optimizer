# Design：Application 材料規格編輯 Use Case

## 閱讀導航

### 現在必須理解

- **Decision 1**：所有材料規格 mutation 由獨立 Application use case staging，live state 不可在 staging 期間被修改。
- **Decision 2**：有引用的 rename 採兩次呼叫的 confirmation protocol，引用判定與同步邏輯不回到 Main。
- **Decision 3**：成功結果同時攜帶 `ProjectDataModel`、`ProjectResultModel` 與 cache／refresh effects，Main 只負責採用及 UI side effects。
- **Decision 4**：Application 回傳穩定 error code 與 presentation arguments；既有使用者文案及 dialog 類型仍由 Main 決定。

### 遇到特定模組或風險時再讀

- 修改 `ProjectInputChangePlan` 或 cache invalidation 時讀 **Decision 3** 與「Single Source of Truth」。
- 修改材料設定 Treeview、warning／confirmation 時讀 **Decision 2、4**；UI layout 本身不在 scope。
- 調整 `ProjectDataModel` copy／construction 時讀 **Decision 1** 與「風險與取捨」。
- 更新長期文件或 boundary tests 時讀「Architecture Alignment」與「向後相容及 Persistence 影響」。

## 方案摘要

```text
MaterialSpecEditRequest + current ProjectData/ProjectResults
                ↓
       MaterialSpecEditing.stage(...)
         ├─ rejected(error code + args)
         ├─ confirmation_required(reference summary)
         └─ staged(project data + project results + effects)
                                      ↓
                         Main atomic adoption + UI refresh
```

本 change 中的 **command** 是一次 rename、Usage edit 或 delete 意圖；**reference summary** 是 Inventory／Waler／Strut 的引用索引與數量；**staged result** 是尚未寫入 live session、但已完成所有驗證及跨表同步的新 Application state。這三者分別對應 proposal 流程中的「收集輸入」、「引用檢查／確認」與「一次採用」。

## 決策對照

本 change 沒有 delta spec；以下以 proposal 的不變事項與 implementation tasks 作為 traceability。

| Decision | 保護的相容性契約 | 對應 task |
| --- | --- | --- |
| D1：pure staging | 失敗或取消不得留下部分修改；staged model 保留全部 persisted 與 runtime-only state；Material Specs／Inventory／Waler／Strut 一次同步 | 1.1、1.5、2.1–2.3 |
| D2：two-call confirmation | 被引用 rename 必須確認；取消時 state 完全不變；引用規則只存在一處 | 1.2–1.3、2.2、3.1 |
| D3：完整 staged state 與 effects | referenced rename 清除 Solver result／cache；unreferenced definition edit／delete 保留結果並標記 dirty | 1.4、2.3、3.2 |
| D4：結構化 outcome | 現行錯誤條件、dialog 類型與可觀察文案維持；防禦性錯誤不形成新 UI 行為 | 1.2–1.3、2.1、3.1 |
| D5：Main 只採用與投影 | UI layout／interaction 不變，Presentation 不再持有第二套材料規則 | 2.1–2.4、4.1 |

## Context

動機見 `proposal.md`「Why」。目前 `main.py` 同時擁有 `_material_spec_key*`、reference lookup／rename、Usage 限制、delete guard、確認 dialog、跨表原地修改及 `_handle_input_data_changed()` 呼叫。`ProjectService.plan_input_change()` 已集中部分 invalidation 判斷，但完整材料規格 transaction 仍由 Presentation 串接。

既有 owner 與約束如下：

- `ProjectDataModel` 是 Material Specs、Inventory、Walers、Struts 的唯一正式 Project input owner。
- `ProjectResultModel` 是 committed Solver result 的 owner；input invalidation 會清除不再可信的結果。
- Main 持有 session-local Solver memory／support candidate cache，Application 只能回傳清除指示，不能反向依賴 Presentation。
- rename、Usage edit、delete、必要 RC 規格與 reference-scoped synchronization 的可觀察行為不得改變。
- Inventory row 自身的 Usage edit 與 incompatible Spec clearing 不是 Material Spec definition mutation，仍走現行一般 table editing path。

## Goals / Non-Goals

**Goals:**

- 建立可脫離 Tkinter 測試的 Application transaction boundary。
- 確保所有 validation 與跨表 mutation 在複本完成，成功前 live Project／results 不變。
- 讓 result invalidation decision、staged result state 與 cache effects 由同一 use case 產生。
- Main 僅保留 UI draft、confirmation、錯誤顯示、state adoption 與 widget refresh。

**Non-Goals:**

- 不建立所有 Project field 共用的 command bus、repository 或 undo framework。
- 不移動一般 Waler／Strut／Brace field editing 或 Inventory Usage edit。
- 不重新定義材料政策、Solver validity 或 result lifecycle。
- 不改 `ProjectDataModel`／Project JSON 的 durable schema。

## Decisions

### Decision 1：新增獨立 `material_spec_editing.py` Application use case

新增小型 `MaterialSpecEditing` service 與 frozen request／outcome dataclasses，而不是把流程繼續塞入 `ProjectService`。它接受 current `ProjectDataModel`、current `ProjectResultModel` 與一個 command，先驗證 row identity，再以能保留完整 instance state 的方式建立 staged `ProjectDataModel`，所有修改只落在 staged copy。

staged copy 必須完整保留原 model 的所有狀態，不只 `to_case_data()` 會寫入 Project JSON 的 tables，也包含目前或未來不持久化的 runtime-only attributes，以及 rows 內不屬於 durable schema 但仍由 live model 持有的 DXF 綁定、構件來源或其他執行期資訊。建立複本後、套用 command 前，staged model 的全部 attributes 與 nested values 必須和 current model 相等，同時 object identity 必須彼此獨立。因此預設採 `copy.deepcopy(current_project_data)` 或由 `ProjectDataModel` 提供等價的完整 clone contract；不得以 `to_case_data()` → constructor reconstruction 作為 staging copy，除非測試能證明它保留全部 instance state。若現有 model 含有無法完整複製的狀態，實作必須停止並回報，不得靜默遺失或自行縮小 contract。

request 至少包含：operation（edit／delete）、row index、expected `(Usage, Spec)`、edit field／proposed value，以及 `allow_reference_sync`。`expected` key 用於防止確認 dialog 前後 row selection 或資料內容已變時誤套用到另一列；不相符時回傳 stale request failure。

支援的 edit field 僅為 `Usage` 與 `Spec`。相同 normalized value 回傳 no-op outcome；非法 index／field、必要 RC 修改／刪除、空白 rename、同 Usage duplicate、referenced Usage change 與 referenced delete 均回傳 rejected outcome。

**理由：** 此流程有清楚的 aggregate boundary 與 transaction semantics，獨立 module 比大型 `ProjectService` 更容易測試與維持單一責任。

**拒絕方案：**

- 只把 Main helpers 搬成 Application free functions：雖可減少行數，但無法形成 request／outcome 與 atomic staging boundary。
- 擴充成通用 Project editing framework：超出 F1，會迫使無關欄位與 DXF binding policy 一起重構。
- Application 直接修改傳入 model 再於失敗時 rollback：容易遺漏 nested row 或 result/cache side effect，且測試難以證明沒有部分 mutation。

### Decision 2：rename confirmation 使用 two-call protocol

首次 `stage()` 若發現 `Spec` rename 有引用且 `allow_reference_sync=False`，回傳 `confirmation_required`，其中包含 canonical old／new values 與 `ReferenceSummary`。Main 以該 summary 顯示現行確認 dialog：取消即停止；確認則以相同 expected identity 及 `allow_reference_sync=True` 重新呼叫 use case。

第二次呼叫必須重新驗證 current input 與 reference set，不能直接採用第一次產生的 staged object；這可避免確認期間 state 已改變。Tkinter 目前為單執行緒，但這個 revalidation 仍使 contract 自足，且不讓 Main 擁有 reference lookup。

**拒絕方案：** 將 callback／messagebox 傳入 Application 會造成 Application → Presentation 反向依賴；讓 Main 先自行計算 references 則保留兩套規則。

### Decision 3：staged outcome 包含 Project data、Project results 與明確 effects

成功 outcome 應包含：

- 完整 staged `ProjectDataModel`；
- staged `ProjectResultModel`：需要 invalidation 時為空 model，不需要時為 current results 的獨立 copy；
- `changed_tables`，供 Main 精準刷新 Material Specs／Inventory／Walers／Struts projection；
- `clear_solver_memory`、`clear_support_candidate_cache`、`update_material_summary`、`dirty_reason` 等 effects；
- reference summary，供 diagnostics／UI 文案使用，不作為另一份正式 state。

referenced Spec rename 必須視為 Solver input 改變：清空 staged results 並要求清 caches。unreferenced Material Spec definition edit／delete 不影響已選取材料或 inventory，故 staged results 保留；這與既有 `ProjectInputChangePlan` 規則一致。use case 應重用或委派現有 planning policy，避免複製 table-level invalidation 集合。

Main adoption 依固定順序進行：先保存舊 model references，換入 staged Project data／results，清除指定 caches，再刷新 Treeview、material summary、Results Tree、Preview 並標 dirty。若 state adoption 本身發生例外，恢復舊 Project data／results 與可恢復的 cache snapshots；adoption 成功後的純 UI refresh failure 不回滾正式 state，沿用其他 workflow 的 commit／refresh 錯誤分界。

**拒絕方案：** outcome 只回傳 row patches 會讓 Main 再次主持跨表 mutation；只回傳 `invalidate=True` 而不 stage results，則「結果失效」仍不在 Application transaction 中。

### Decision 4：結構化 failure，不把 UI 文案放進 Application

outcome 使用穩定 status／error code，例如 `invalid_row`、`stale_request`、`required_spec_locked`、`blank_spec`、`duplicate_spec`、`referenced_usage_locked`、`referenced_delete_blocked`。同時提供安全的 display arguments（usage、spec、reference counts），Main 將 code 映射到既有 warning title／message／dialog type。每一個 error code 都必須有明確的 Main mapping，不能因漏接而無提示、拋出 presentation exception 或落入新的互動流程。

`invalid_row` 與 `stale_request` 只是在 Application boundary 防止非法 caller 或確認期間 state 漂移的防禦性檢查，正常 Main 操作不應出現。若真的發生，Main 以既有通用輸入錯誤 warning 顯示並保留原 state；不得新增 confirmation、重試 dialog、專用畫面或其他 user-visible workflow。其他 error code 則精確沿用切換前已由 Main characterization tests 鎖定的 dialog 類型、顯示時機與文案。

這使 Application tests 驗證語意而非 Tk 文案，Main integration tests 則鎖定現行顯示與確認時機。reference summary formatter 可留在 Presentation，不能參與允許／拒絕判斷。

**拒絕方案：** Application 回傳完整中文 message 會把 presentation policy 帶入 Application，且使核心測試依賴文案。

### Decision 5：移除 Main 的正式材料規則，只保留 presentation helpers

完成切換後，Main 不再實作 key uniqueness、reference lookup/count、rename mutation、Usage/delete guards 或 result invalidation decision。可保留的 helper 只限：從 Treeview 建 request、顯示 reference summary、映射 outcome code、採用 staged models 與刷新 widgets。

cell editor 的選項生成可繼續讀取 `ProjectDataModel.material_specs` 作為 read-only projection；必要 RC row 是否允許開啟 editor 的 UI shortcut 可保留以維持 interaction，但 Application 仍必須再次驗證，不能把 shortcut 當作唯一保護。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer 定義或 dependency direction**；它修正實作與既有原則的落差。

| Layer | 變更後責任 | Dependency |
| --- | --- | --- |
| Presentation (`main.py`) | 收集 UI draft、確認、顯示錯誤、採用 outcome、刷新 widgets | `Presentation → Application` |
| Application | 驗證 command、查找引用、建立 staged Project／result、規劃 cache effects | `Application → Application models`；必要時可依賴 Domain，但本 change 不需新增 |
| Domain | 不變 | 不新增依賴 |
| Algorithms | 不變 | 不新增依賴 |
| Infrastructure | 不變；persistence 消費採用後的 Project models | 不新增依賴 |

不得新增 `Application → main.py/Tkinter`、`Domain → Application` 或 `Algorithms → Application` 依賴。Architecture boundary tests 應驗證新 module 不 import `tkinter`、`main`、Infrastructure 或 Algorithms。

## Single Source of Truth

- 正式 Material Specs／Inventory／Waler／Strut input：採用後的 `ProjectDataModel`。
- 正式 Solver results：採用後的 `ProjectResultModel`。
- 編輯規則與 reference semantics：`MaterialSpecEditing`；Main 不保留等價判斷。
- table-level invalidation policy：既有 `ProjectService.plan_input_change()` 或抽出的 Application-internal policy，材料 use case 只消費同一份決策。
- session caches：Main session 持有；Application outcome 只提供清除命令，不保存 cache copy 為第二份 truth。

staged models 在 adoption 前不是正式 state；Main 不應同時逐列修改 live model。adoption 後立即丟棄 staged wrapper，避免 live／staged 長期並存造成 drift。

## 向後相容及 Persistence 影響

- 使用者操作、錯誤條件、確認時機、結果失效與 UI layout 全部向後相容。
- `ProjectDataModel.to_case_data()` 與 Project JSON schema 不變；不新增 migration 或 persistence 欄位。
- Application dataclasses 是 process-local contract，不進入 payload。
- 既有專案載入、legacy material defaults 與必要 RC 自動補回行為不變。

## 風險與取捨

- [Risk] deep copy 可能增加大型 Project 編輯延遲 → 以現有 Project case 做 focused timing／manual smoke；只有可量測問題才改為 Application-internal copy-on-write patch，且替代方案仍須通過全部 persisted／runtime-only attributes 完整保留測試，外部 staged contract不變。若無法完整複製則停止並回報。
- [Risk] two-call confirmation 期間資料變更 → 第二次呼叫驗證 expected key 與重新計算 references；不符即 `stale_request`，不採用舊結果。
- [Risk] Main adoption 遺漏 cache 或 UI projection → outcome 提供明確 effects，集中成單一 `_adopt_material_spec_edit()` helper，integration test 驗證 Project／results／caches／refresh。
- [Risk] 搬移時錯誤文案或條件 drift → 先建立現況相容性表與 characterization tests，再切換 Main；不得弱化既有 assertions。
- [Trade-off] Application outcome 包含完整 result model，資料量高於 row patch → 換取 transaction 原子性與清楚 ownership；本 change 優先正確性。

## Migration Plan

1. 切換前先補齊並執行 Main characterization tests，鎖定錯誤條件、確認時機、dialog 類型、可觀察文案與取消行為；後續不得修改這些 assertions 來配合新實作。
2. 在 Application 新增 request／outcome、pure validation／reference lookup、完整 model clone 與 staging tests，不接 Main。
3. 將既有 `ProjectInputChangePlan` 接入 result／cache／dirty effects，完成 referenced／unreferenced edit／delete matrix。
4. 新增完整 error-code mapping、Main outcome orchestration 與 adoption helper，讓材料規格 edit／delete 改呼叫 use case；切換後重跑原封不動的 Main characterization tests。
5. 刪除 Main 中已無 caller 的正式規則 helpers，保留 presentation-only formatting。
6. 執行 focused tests、Main editing／Project service regression、architecture boundary tests，再更新長期 ownership 文件。

此為本機桌面應用的內部重構，不需要資料 migration 或分階段 deployment。若回滾，恢復 Main orchestration 與原測試即可；durable Project data 不受影響。
