# Design

## 閱讀導航

### 現在必讀

- D1：定義目前選取中間柱的唯一解析來源。
- D2：定義修改工具入口只依目前 selection 顯示與防禦性重驗。
- D3：定義單一柱 Preview 如何涵蓋待修、已修與 `requires_review` 狀態。
- D5：定義不存在柱的失效決策仍由既有 Review problem 呈現。

### 條件式閱讀

- 修改選取同步時閱讀「Selection 變更流程與 state ownership」。
- 修改 Workflow planning／commit 時閱讀「D4：Workflow contract 維持不變」；本 change 原則上不應修改該層。
- 修改測試或文件時閱讀「Migration Plan」與「Risks / Trade-offs」。

### 可先跳過

- Solver、Domain、persistence、角撐修補與雙路支撐內部設計不受影響。

## 方案摘要

```text
Presentation selection
  → 解析目前唯一 ReviewItem／member
  → role == column 才呈現入口
  → 每次清單／圖面／清除 selection 都重評入口
  → 點擊時再次解析同一 selection
  → 以該 Column ID 呼叫既有 plan API
  → 單一柱 Preview 依 unresolved／repaired／requires_review 顯示
  → 使用既有 apply／withdraw API 與既有 Review problem 原因
```

「目前選取中間柱」是指 DXF Review 當下唯一選取、可解析為有效 Column 的 ReviewItem／正式構件；它只是 Presentation selection，不是新的持久化工程資料。「修補 subject」是該次 Preview 唯一可被規劃與提交的 Column ID。

## 決策對照

| Decision | 對應 Spec | 對應 Tasks |
|---|---|---|
| D1：從既有 selection 解析唯一正式 Column subject | 「Y29 C25 為可修補案例」「非中間柱選取」「未形成正式 Column 的待修項目不啟用工具」 | 1.1、1.2 |
| D2：所有 selection 路徑重評入口，command 執行再重驗 | 「清單選取在柱與支撐之間切換」「圖面與清單選取結果一致」「選取清除或啟動時已失效」 | 1.2、1.3、2.1 |
| D3：單一柱 Preview 涵蓋三種 plan status | 「有效已修柱可查看並撤銷」「需重新檢查柱顯示失效原因」「Preview 開啟後改選其他構件」 | 2.1～2.4 |
| D4：沿用既有 Workflow plan／commit／withdraw | 主 spec 的原子提交與工程資格 requirements | 2.2、3.2 |
| D5：orphan decision 不進工具但保留既有問題 | 「對應柱不存在的失效決策仍在問題清單可見」 | 2.5、3.2 |

## Context

動機見 `proposal.md` 的 Why。現行 `DXFImportDialog` 由 `_column_repair_subjects()` 掃描 `world_result.columns`，只要任一柱可規劃，就在 `_update_modification_tools()` 顯示入口；開啟後再以 Listbox 顯示所有 subject。另一方面，DXF Review 已由 Presentation 的 `SelectionState`、目前 ReviewItem 與 member lookup 管理單一選取，且 `docs/ARCHITECTURE.md` 明定 Preview selection 屬 Presentation、`DXFReviewWorkflow` 才擁有正式 Review truth。

此 change 應重用既有 selection 與 `plan_column_association_repair(column_id)` contract，不在 Presentation 重算工程候選，也不建立第二份 Column association truth。

## Goals / Non-Goals

**Goals:**

- 讓工具入口與當下選取的中間柱一致。
- 確保視窗只有一個 immutable subject，避免在 Preview 內切換到其他柱。
- 對 stale／非柱／不合格 selection fail closed，正式 Review state 零副作用。

**Non-Goals:**

- 不改寫 column repair eligibility、diagnostics 或 transaction。
- 不修改通用 selection controller 或引入新的全域 selection abstraction。
- 不新增 persistence 欄位或 migration。

## Decisions

### D1：以既有 Review selection 解析唯一 Column subject

Presentation 新增小型 helper，從 `_selected_review_item()` 與必要的 member lookup 取得目前 selection；只有 `role == "column"` 且可對應 `world_result.columns` 中唯一正式 Column ID 時回傳 subject。僅有 column-like unresolved ReviewItem、來源問題或不存在的舊決策不回傳 subject。helper 不列舉其他柱、不呼叫候選資格算法，也不以 warning 文字猜測角色。

理由：既有 selection 是 UI 的 single source of truth，符合 Architecture 的 state ownership；Workflow 的 `world_result` 與 plan API 繼續是工程 truth。

Rejected alternative：沿用 `_column_repair_subjects()` 後再挑與 selection 同 ID 的項目。這仍會掃描並規劃全案柱，保留不必要的全案耦合，也可能在其他柱錯誤時影響目前柱入口。

### D2：入口顯示與 command 執行採雙重 gate

`_update_modification_tools()` 只在 D1 helper 回傳 Column subject 時呈現按鈕。所有會改變 Review selection 的既有完成路徑——構件清單選取、圖面 member／ReviewItem 選取與清除 selection——都必須在 selection state 更新後呼叫或到達同一修改工具 refresh，不各自維護按鈕條件。`_open_column_association_repair()` 不信任先前 render 狀態，執行時再次解析目前 selection；selection 已改變、清除或不是正式 Column 時，顯示提示並停止。

理由：Tkinter widget 可在 selection 更新前後被觸發，command boundary 重驗可避免 stale UI 把舊柱帶入修補。入口是否採 `pack_forget()` 或 disabled 沿用現有 modification tools 慣例；contract 是非柱不可啟動。

Rejected alternative：只靠按鈕可見性。這無法防止 stale callback 或程式直接呼叫 command。

### D3：視窗建立時立即規劃單一 subject

開啟 command 取得 Column ID 後，直接呼叫既有 `plan_column_association_repair(column_id)`。移除 Listbox、`_column_repair_subjects()` 對此流程的依賴與 `select_case` callback；標題或 detail 明確顯示 Column ID 與 plan status：

- `unresolved`：顯示候選、三個互斥選項、overlay 與套用。
- `repaired`：使用 plan 的 `selected_strut_ids` 顯示目前決策與 overlay，提供撤銷；不得用「目前沒有歧義 warning」判成無內容。
- `requires_review`：以 plan status 搭配同來源的既有 `COLUMN_ASSOCIATION_REQUIRES_REVIEW` problem 顯示 Workflow 已產生的失效原因；不由 UI 重算原因或候選。若目前 plan 無安全撤銷所需資訊，Presentation 不補資料。

若沒有既有人工決策且目前柱不合格，呈現該柱的錯誤原因，不回退到其他可修補柱，也不自動開啟其他 subject。Preview 生命週期內 `column_repair_plan.column_id` 是唯一 subject；主 Review selection 在背景改變只刷新主畫面入口，不會把現有 Preview 換柱，提交仍由既有 revision／identity revalidation 判定是否 stale。

Rejected alternative：保留只有一列的 Listbox。它增加一次無意義操作，且仍暗示視窗可切換 subject。

### D4：Workflow contract 與工程計算維持不變

Presentation 仍只傳 Column ID 給 plan API，選擇仍轉換為既有 candidate Strut IDs，apply／withdraw 繼續呼叫既有 Workflow transaction。Presentation 不自行判斷距離、station、第三候選、共享群組或 warning 解決狀態。

理由：candidate eligibility 與正式 association 的 single source of truth 已在 `DXFReviewWorkflow`；本 change 是選取導向的 UI boundary 調整。

Rejected alternative：為了控制按鈕，先在 UI 計算該柱是否 eligible。這會複製工程邏輯並造成 drift。按鈕可以在所有有效 Column selection 顯示；不合格柱由 plan API 回報「目前選取的中間柱無可修補內容」。

實作前 contract audit 已確認：現有 `plan_column_association_repair()` 對有效已修柱提供 `status="repaired"`、`selected_strut_ids`、candidate identities 與 revision-bound plan，現有 `withdraw_column_association_repair()` 可直接使用該 plan。若實作期間此 contract 不成立，必須停止，不得修改 Presentation 來推導撤銷資訊；本 change 也不授權修改 plan／commit／withdraw contract。

### D5：不存在 Column 的失效決策只走既有 Review problem

當保存的 column decision 對應來源已不在 `world_result.columns` 時，不存在可選取的正式 Column，因此不建立工具入口。`rebuild_component_associations()` 既有行為會產生 `COLUMN_ASSOCIATION_REQUIRES_REVIEW` warning，Review problem／ReviewItem 建構流程必須繼續保留它；移除全案 subject list 不得順帶過濾或隱藏此 problem。

Rejected alternative：在 Presentation 為 orphan decision 建立虛構 Column subject。這會建立第二份構件 truth，違反正式 Column gate，也無法安全提供 plan／withdraw contract。

## Selection 變更流程與 State Ownership

- `SelectionState`／selected ReviewItem：Presentation 的唯一選取 truth。
- `DXFReviewWorkflow.world_result`：目前有效工程構件與幾何 truth。
- `ColumnAssociationRepairPlan`：單次 Preview draft；關閉／取消即丟棄。
- `column_association_decisions` 與重建後結果：Workflow 的正式人工決策 truth。
- `COLUMN_ASSOCIATION_REQUIRES_REVIEW` ProblemRecord／ReviewItem：失效原因與 orphan decision 可見性的既有 authoritative projection。

helper 只橋接前兩者以取得 Column ID，不快取第二份 selected column 欄位；因此 selection 更新後不會與另一本地 subject state 漂移。已開啟 Preview 則以 plan 自身 subject 固定此次操作，交由既有 stale-plan validation 保護提交。

## Architecture Alignment

本 change 沿用而不修改既有 Architecture：

- Presentation：決定按鈕是否呈現、解析目前 selection、顯示單一柱 Preview。
- Application／Review Workflow：維持 candidate planning、工程重新驗證、commit／withdraw 與正式 state ownership。
- Dependency direction：Presentation → Workflow；Workflow 不依賴 Tkinter 或 Presentation selection。
- Domain、Algorithms、Infrastructure：無變更。

## Backward Compatibility / Persistence

- 已保存的 column association decisions、Review state version 與 Pause／Resume payload 不變。
- 既有已修柱仍可在使用者選取該柱後開啟並撤銷。
- 不新增 schema migration；舊專案載入結果與工程輸出不變。

## Risks / Trade-offs

- [選到不合格但正式的柱時按鈕仍可能出現] → command 只針對該柱呼叫 plan；無決策時顯示不可修補原因，有有效／失效決策時依 plan status 呈現，不掃描其他柱。
- [selection 在視窗開啟後改變] → Preview subject 固定於 plan，套用由既有 revision／identity validation 防止 stale commit。
- [不同 selection 路徑漏刷新入口] → 清單、圖面與清除路徑共用同一修改工具 refresh，並以路徑對照測試鎖定。
- [orphan decision 因清單移除而不可見] → 工具不承擔 orphan 導覽；以既有 Review problem list regression test 保護可見性。
- [移除全案清單後無法從工具內巡覽所有待修柱] → 這是本需求刻意的取捨；使用者回到既有 Review 清單選另一柱再開啟。
- [既有測試依賴 `_column_repair_subjects()`] → 以目前 Column selection、非柱 selection、無 selection 與單一 Preview 測試取代，不降低 Workflow regression coverage。

## Migration Plan

1. 先以 focused tests 固定目前 selection → tool visibility／subject contract。
2. 調整 Presentation helper、入口 gate 與單一柱 dialog；保留既有 Workflow API。
3. 執行 layout tests 與 column association workflow regression tests。
4. 實作驗證完成後更新 `docs/WORKFLOW.md` 的入口描述；若需回滾，只還原 Presentation 與該段文件，不涉及資料 migration。
