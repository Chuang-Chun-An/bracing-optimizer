# Design

## 閱讀導航

### 現在必讀

- Decision 1「以 Algorithms evaluator 作為單一真相來源」：核心責任與 dependency direction。
- Decision 2「結構化 evaluation result 與具名 issue」：避免以中文訊息驅動邏輯。
- Decision 3「以 compatibility projector 保留既有 payload」：保護未受確認決策影響的分數、錯誤呈現與排序。
- Decision 4「以 characterization／equivalence tests 鎖定行為」：重構前後的驗證方式。
- Decision 6「效能比較是 mandatory gate」：Single／Global fixture 的前後計時與停線條件。
- Decision 7「套用已確認的 Waler 總長與 issue projection 規則」：五項 B 類差異的實作方式。
- Decision 8「完整 diagnostics 與 repair boolean probe 共用 synchronous scanner」：效能 gate 後經兩輪 profiler 確認的最小修正。

### 遇到特定情況再讀

- 修改 `WalerPlanEditing` 時讀 Decision 5「Application 只補 workflow context 與人工顯示投影」。
- 發現 invalid candidate score 與人工 score 欄位語意不同時，讀 Decision 3 的 core local score／search penalty 分離。
- characterization comparison 發現兩條路徑核心結果不一致時，讀 Decision 4 的 A／B 分類、差異報告與使用者決策 gate。
- 需要回滾或發現 payload consumer 未涵蓋時，讀「Migration Plan」與「Risks / Trade-offs」。

### 可先跳過

- 未修改 persistence、DXF、Support Solver 或 Global selection policy 時，不需延伸閱讀其設計文件。

## 方案摘要

```text
Algorithms
  decode automatic individual ─┐
                               ├─ evaluate_waler_plan(input) ─> structured result
Application                    │                                ├─ legality/issues
  build manual edit context ───┘                                ├─ allocation/components
                                                                └─ local score
                    structured result
                           ├─ automatic compatibility projection ─> existing candidate dict
                           └─ manual compatibility projection ────> existing edited plan/legality
```

本 change 中的「core evaluation」只代表對已決定的 segments／joints 做合法性、allocation 與 local scoring；「compatibility projection」則把同一結果轉回既有自動或人工 payload。GA 搜尋不成為 evaluator 的第二套規則。Waler 總長的 200 mm 閉區間與「不使用 adjustment block」則是使用者確認後加入 core 的 Engineering Hard Constraint。

## 決策對照

| Decision | 對應 spec Requirement | 對應 tasks |
| --- | --- | --- |
| 1. Algorithms evaluator 是 single source of truth | 自動與人工流程使用共用核心評估；搜尋政策與評估分離 | 1.1、2.1、3.1 |
| 2. 結構化 result 與具名 issue | 具名問題識別與完整顯示 | 1.2、2.2、4.1 |
| 3. Compatibility projector 保留未受決策影響的舊 payload | 既有分數與排序相容；具名問題識別與完整顯示 | 2.3、3.2、4.2 |
| 4. Characterization 與 equivalence tests | 全部 Requirements | 1.1～1.4、2.4、3.3、4.1～4.4 |
| 5. Application 只處理人工 workflow context | 共用核心評估；統一合法性與 allocation 語意 | 3.1～3.4 |
| 6. 效能比較是 mandatory gate | 搜尋政策與評估分離 | 1.5、4.3 |
| 7. 已確認的總長、invalid evaluation 與完整 issue projection | 統一合法性與 allocation 語意；Waler 總長使用 200 mm 閉區間且不使用 adjustment block；具名問題識別與完整顯示 | 2.1～2.4、3.1～3.3、4.1～4.5 |
| 8. Synchronous issue scanner 與 repair boolean probe | 搜尋政策與評估分離；具名問題識別與完整顯示 | 4.3a、4.3b |

## Context

動機見 `proposal.md` 的 Why。現況中 `wales.evaluate_individual()` 依序 decode、`validate_segments()`、`allocate_stock_best_fit()`、計算 ratio 與 local score；`WalerPlanEditing.recalculate()` 則在 Application 重新組裝 allocation、相同 score expression、合法性與人工顯示資料。`WalerPlanEditing.validate()` 也會從文字錯誤中排除已另行顯示的 joint／purchasable 問題，形成依中文訊息內容分類的脆弱耦合。

既有 Architecture 已明確將 Waler 候選評分與計算核心放在 Algorithms，將人工方案修改與 Project／Inventory context 協調放在 Application。因此本 change 沿用架構，不建立新 layer，也不讓 Algorithms 依賴 `ProjectDataModel` 或 `InventoryLookup`。

## Goals / Non-Goals

**Goals:**

- 一個可直接以 segments／joints 與純 Solver config、stock items 呼叫的 Algorithms evaluation boundary。
- 自動與人工路徑共享完全相同的合法性、allocation、score components 與具名 issues。
- 套用重新確認的 invalid evaluation sequence：完整收集 hard issues 後，任何 invalid plan 都不進入 allocation／ratio／local score；同時保留完整人工 issue 顯示與 Waler 總長 200 mm 閉區間。
- 保留未被確認決策修改的既有 dict payload、中文顯示、invalid penalty、排序與人工編輯 workflow。
- 讓新增／修改評估規則時只需修改 evaluator 及其單元測試。

**Non-Goals:**

- 不建立跨 Support／Waler 的通用 evaluation framework。
- 不把 Project row、Material Spec 查詢或 UI formatting 移入 Algorithms。
- 不修改 Support Shim、GA policy、Global Waler selection policy 或 result adoption；Waler adjustment block 明確移除。
- 不趁此機會重命名全部舊欄位或把所有 Solver dict 改成公開 dataclass API。

## Decisions

### Decision 1：在 Algorithms 建立 plan-level evaluator 作為單一真相來源

在 `bracing_optimizer/algorithms/wales.py`（或同一 Algorithms package 的小型專責模組）建立接受下列純計算輸入的 evaluator：

- `segments`、`joints`
- `required_length`、`required_length - 200` 下界、segment range、forbidden points／clearance、purchasable lengths 與 ratio targets
- 已由 Application／Builder 解析完成的 `stock_items`

`evaluate_individual()` 只保留 chromosome decode 與 automatic compatibility projection，然後呼叫此 evaluator。人工路徑由 Application 建立相同 `Config` 與 stock items 後直接呼叫 evaluator。

理由：scoring 與 calculation core 本來就屬 Algorithms；輸入仍是 solver-native data，不需要反轉 dependency。此 boundary 評估既定 plan，不知道 GA stage、Project row、UI 或 persistence。

Rejected alternative：把共用邏輯放在 `WalerPlanEditing`。這會迫使 Algorithms 依賴 Application 或讓自動 Solver 複製另一份 wrapper，違反既有 dependency direction。

Rejected alternative：建立新的跨所有 Solver 通用 evaluator abstraction。Support 與 Waler 的 plan model、hard constraints 和 scoring 不同，這會擴大 scope 並產生不必要抽象。

### Decision 2：核心結果使用結構化資料與具名 issue

核心 evaluator 回傳一個 typed internal result（優先 dataclass），至少承載：

- `valid`
- normalized `segments`／`joints`
- structured `issues`
- `assignments` 與 allocation metrics
- ratio analysis 與各 score components
- `local_score`

每個 issue 至少包含穩定 `code`、顯示所需的 facts，以及可由 projector 產生的 message。初始 code 應覆蓋 steel-total-short、steel-total-long、joint-clearance violation、segment below／above range、segment not purchasable 與 allocation unavailable；名稱在實作時可依專案命名風格確定，但一經公開給下游測試與 projection 即視為穩定 runtime contract。

分類與去重使用 `(code, normalized facts)`，不可再以 message substring 過濾。message 仍可由 issue 保存或由集中 formatter 產生，但不得反向成為判斷來源。

理由：code 表達問題 identity，facts 表達哪個位置／長度觸發；中文只是一種 projection，未來修正文案不會改變行為。

Issue code 與 structured issue 只存在執行期間，用於 evaluator、compatibility projector、diagnostics 與測試；不得寫入 `ProjectResultModel` 的 durable projection、Project JSON 或任何結果存檔。本 change 不新增 persistence 欄位或 schema migration。

Rejected alternative：只替現有字串加前綴。這仍需解析字串，且同一 code 的多個 segment／joint 無法可靠區分。

### Decision 3：核心 local score 與 workflow compatibility projection 分離

合法 plan 的 `local_score` 只在 evaluator 計算一次，沿用現行 components：

```text
buy_count * 100000
+ ratio_penalty
+ under_4000_segment_count * 100000
+ distinct_groups * 5000
+ length_variation
+ joint_count * 1000
```

抽取時必須逐項保留原本的運算順序與數值型別，不得因為代數等價而重排加總、預先 round、改用不同 numeric type 或在 component 間轉型。合法 plan 的 `local_score` 及每個 component 均以 exact equality 與修改前 baseline 比較，不使用 `isclose`、epsilon、rounding tolerance 或其他浮點容差。

自動 candidate dict 與人工 edited plan dict 暫時維持既有 schema。Projector 將 structured result 映射到舊欄位：

- 自動合法 candidate 的 `score` 取 `local_score`。
- 自動 invalid candidate 的 `score` 保留目前 legality penalty 或 allocation penalty，避免 GA fitness 與排序改變。
- 只要 plan 已有任何總長、joint clearance、segment range 或 non-purchasable hard issue，core 不執行 allocation／ratio／local score；manual projector 將 assignments、allocation metrics、ratio fields 與 score 以 `None` 表達 unavailable，自動 projector 仍使用既有 invalid penalty。
- 只有沒有 hard issue 的 plan 才執行 exact-length allocation；此時若 defensive allocation 回報 unavailable，core 產生 allocation-unavailable issue，且不產生 buy count、stock groups、variation 或 local score。
- 人工 `legality.summary/details` 依 structured issues 投影全部 joint-clearance 與 non-purchasable facts，並以「鋼材總長不足／太長」取代 tail-adjustment error。

因此 invalid search penalty 是搜尋相容層，不是第二套合法 plan scoring 公式。這同時滿足「共用評分公式」與「現有排序維持不變」。若 characterization test 顯示既有 invalid 分支還有其他特殊欄位，先補 projector，不改 core rule。

Rejected alternative：立即以新 dataclass 取代所有 dict consumer。這會擴及 dialogs、global merge、persistence／export consumer，超出技術債範圍並提高回歸風險。

Rejected alternative：讓所有 invalid plan 都改用同一新 penalty。這會改變 GA fitness／排序，直接違反不變事項。

### Decision 4：先鎖定再抽取，使用等價矩陣驗證

實作前先以現有公開行為建立 characterization fixtures，至少涵蓋：

- 合法、全庫存與需要採購的 plans
- joint 距離 `< clearance`、`= clearance`
- segment `< min`、`= min`、`= max`、`> max`
- purchasable／non-purchasable length
- total-length mismatch 與 allocation failure defensive path
- 多個同 code 不同 facts 的 issues
- material spec 有值與空白兩種情境；空白時必須沿用既有 fallback

Task 1.3 完成後、任何 Group 2 程式修改前，必須以完全相同的 resolved context 比對 automatic `evaluate_individual()` 與 `WalerPlanEditing` 的既有結果。兩邊必須使用相同 segments、joints、config、material spec、purchasable lengths、ratio targets 與同一份庫存資料；庫存比較包含每一筆 length、Qty，以及 material spec 空白時的既有 fallback 結果。

差異報告將結果分為：

- A 類：只有訊息文字、順序或欄位名稱不同。記錄後由各自 compatibility projector 保留原格式，可繼續實作。
- B 類：合法性、allocation、任一 score component、local score 或 issue 種類不同。報告完成後停止，不得開始 Group 2。

每一項 B 類差異必須包含：差異名稱、可重現的 segments／joints／config／完整庫存輸入、自動結果、人工結果、差異來源程式位置、建議採哪一邊或哪條規則及理由（工程合理性、對既有專案與 Solver 結果的影響），以及採用建議後會改變的既有行為。建議不是決策：不得自行採用任一邊、折衷或較寬鬆規則。只有使用者確認後，才能先更新 spec Requirement／Scenario、proposal 不變事項／Impact 與必要的 `docs/DOMAIN.md`／`docs/SOLVER.md` 更新標記，再繼續實作。

五項 B 類差異已由使用者確認並寫入 Decision 7。B-01 初次採「可 allocation 的 invalid plan 仍計 diagnostics」實作後，效能 gate 測得 Single 中位數增加 114.2%、Global 增加 65.3%；使用者因此重新確認 B-01 最終規則為「任何 hard issue 都停止 allocation／ratio／local score」。這是 evaluation 語意修訂，不以快取、微調或搜尋參數變更取代。artifact 更新與 strict validation 後，重新測 evaluator、automatic／manual equivalence、focused regression 與同一組效能 fixture。

理由：目前重複邏輯已有細微的 payload 差異，先鎖定 observable output 才能安全區分「核心一致」與「相容投影不同」。

### Decision 5：Application 只補 workflow context 與人工顯示投影

`WalerPlanEditing` 保留：

- 從 `ProjectDataModel`／`InventoryLookup` 取得 material-specific purchasable lengths、stock items 與 quantity。
- 從人工 segments 重建 joints，準備 `required_length` 與 200 mm 下界 context。
- 將 evaluator result 轉成既有人工 plan 與 legality 顯示資料。

它移除：

- allocation metrics 的自行重算。
- local score expression 的複製。
- 對 `validate_segments()` 中文字串做 substring filtering。

採購 warning 可以繼續由 Application 依 inventory quantity 與 structured allocation／issue facts 組裝，因這是人工 workflow presentation；但「是否可 allocation」與 buy count 必須來自 core evaluator。

### Decision 6：效能比較是 mandatory gate

在修改前與修改後，使用既有 Single Waler 與 Global Waler fixtures，在相同環境、相同 config、相同 seed 與相同輸入資料下記錄執行時間並回報。計時至少分別涵蓋 Single 與 Global 路徑，保留每次量測值、執行次數與摘要，避免只用單次偶發抖動下結論。

若前後結果顯示明顯變慢，實作必須停止並回報量測證據與可能來源；不得修改 GA stage、population／candidate count、seed、停止條件或其他搜尋參數來掩蓋 evaluator regression。由於目前未確認固定效能門檻，本 change 不自行發明百分比；實作者應呈現原始量測與環境，對超出正常 run-to-run noise 且可重現的退化視為停線條件。

Rejected alternative：只依完整測試是否在 timeout 內判斷效能。這無法辨識尚未超時但已增加 Solver 成本的 regression。

Rejected alternative：降低搜尋量補回總時間。這會改變 Solver policy 與結果品質，違反本 change 的不變事項。

### Decision 7：套用已確認的 Waler 總長、invalid evaluation 與 issue projection 規則

characterization report 的 B 類差異採以下最終固定 pipeline：

```text
normalize segments / joints / required length
        ↓
collect all total / joint / segment / purchasable issues
        ↓
存在任一 hard issue？ ──是──> allocation／ratio／local score unavailable
        │否
        ↓
exact-length allocation ──失敗──> allocation unavailable issue
        │成功
        ↓
ratio + score components + diagnostic local score
        ↓
valid = 無任何 hard-constraint issue
        ↓
automatic / manual compatibility projection
```

- Core 不因第一個 legality issue early-return；它先收集全部 issues，再決定是否進入 allocation。
- 任何 hard issue 都使 allocation、ratio、score components 與 local score unavailable；不得因 segments 可購買而對 invalid plan 補做診斷評分。
- 無 hard issue 才執行 exact-length allocation；allocation unavailable 時不以 segment 數量虛構 buy count／stock group／variation／local score。
- Automatic search score 對 hard-invalid candidate 保留既有 legality penalty，對 allocation defensive failure 保留既有 allocation penalty。
- Manual projector 依 core issue order 顯示全部 issues；total issue 在前，joint issues 依 joints 輸入順序，segment issues 依 segment index／輸入順序。同 code 不同 facts 不去重。

Waler 總長改為：

```text
minimum_steel_length = max(0, required_length - 200)
minimum_steel_length <= sum(segments) <= required_length
```

Core 不再呼叫 adjustment-block resolution 判斷 Waler 合法性。Waler `pieces` 只包含 steel；既有 `tail_adjustment` compatibility 欄位固定投影為 `0`。若保留既有 `gap` 欄位，投影為 `required_length - steel_length`，其合法範圍為 `0..200`，不代表 adjustment block。Support 的 `shim` piece、數量與 placement 規則完全不受影響。

Automatic candidate generation仍使用既有 stage、seed、population／candidate count、repair 與 joint step；但 candidate 是否符合新總長 hard constraint 由 core 統一判斷。原本只有依 adjustment block 才能完成的 Waler 可能失去合法候選，這是已確認的 domain change，不可透過修改搜尋參數掩蓋。

Rejected alternative：保留 Waler adjustment block 但只改中文文案。使用者已確認 Waler 不使用 adjustment block，這會留下錯誤的工程模型。

Rejected alternative：manual projector 只顯示第一筆 issue。這會繼續隱藏已由 core 發現的其他接頭／料長違規，與使用者確認的完整顯示不符。

### Decision 8：完整 diagnostics 與 repair boolean probe 共用 synchronous scanner

Profiler 顯示 GA repair 的 `is_valid_selected()` 在 Single fixture 內呼叫 legality validation 121,354 次。該路徑只使用 boolean，卻因共用 evaluator 抽取而每次 materialize structured issues 並格式化中文訊息；同場 profile 將 primitive calls 由修改前約 843 萬提高到約 1,167 萬，主要 cumulative 增量集中在 `_collect_waler_plan_issues()`、`_waler_issue()` 與 `format_automatic_waler_issue()`。Allocation 與 `evaluate_individual()` 本身沒有相稱的退化。

第一輪先改為 lazy iterator，確實移除 repair 路徑的完整 issue list 與中文訊息 materialization，102 個 Waler focused／Global regression tests 亦保持 metadata、signature 與 exact score；但同場 benchmark 仍較 Git HEAD 慢 26.2%（Single）與 17.2%（Global）。第二輪 profiler 顯示剩餘成本集中於 121,354 次 `_has_waler_plan_issue()` 所建立與 resume 的 generator；plain synchronous boolean experiment則曾在相同 observable metadata 下回到 Git HEAD 附近。

因此 hard rules 最終由單一 synchronous scanner 實作，接受 optional issue sink，並維持兩種 consumer：

- `evaluate_waler_plan()` 與需要 diagnostics 的 compatibility API 傳入 `issues.append`，scanner 依固定順序掃完並建立全部 issue codes、facts 與顯示所需資料。
- GA repair 的內部 feasibility probe 不傳 sink；scanner 在第一個 violation 直接回傳 `True`，不建立 generator、issue object、完整 list 或顯示文字。

這不是第二套規則：所有 hard-rule branches 只存在同一 scanner，boolean 結果必須等於完整 issue list 是否非空。Repair probe 不是正式 plan evaluation，不向外提供 issues；因此不違反 Decision 7 對 core 完整收集的要求。不得改動 repair steps、候選生成、stage、seed、population／candidate count、score、排序或 diagnostics payload。

Rejected alternative：把 `validate_segments()` 複製回舊 loops。這會重新建立平行 hard rules 與 drift 風險。

Rejected alternative：加入 candidate cache。Profiler 已定位到未使用 diagnostics materialization；cache 會增加 key／生命週期／記憶體語意，且不是解除根因的最小修正。

Rejected alternative：只替換較輕的 issue 型別。Repair 仍會反覆建立 facts 與中文字串，無法消除主要成本。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer 定義：

```text
Presentation → Application.WalerPlanEditing → Algorithms.wales evaluator → Domain policy helpers（如既有）
                         OptimizeWaler ────────┘
```

- Algorithms 擁有 plan evaluation、allocation 與 scoring single source of truth。
- Application 擁有 Project／inventory lookup、manual edit orchestration 與 compatibility presentation projection。
- Algorithms 不依賴 Application、Presentation 或 Infrastructure。
- Presentation 不新增 legality 或 scoring 判斷。

重要 contract 的 single source of truth 是 structured evaluation result；automatic／manual dict 都是 projection，不得回頭各自計算 score 或 legality。此設計消除兩份公式 drift，但不改現有 result ownership。

## Backward Compatibility 與 Persistence Impact

- 既有 automatic candidate dict 與 manual edited plan dict 的消費者維持可用；新增內部 structured result 不要求它們遷移。
- 未被 Decision 7 修改的 `errors`、`legality`、assignments、score component 欄位與顯示順序由 characterization tests 保護。
- Manual 多筆 issue 顯示、unavailable allocation fields、Waler `tail_adjustment=0` 及無 `shim` piece 是明確相容例外。
- 不改 Project JSON 或 result persistence schema，不建立 migration。
- Issue code 與 structured issue 是 runtime-only diagnostics contract，不進入 Project JSON、durable result projection 或結果存檔。
- 不新增外部 dependency。

## Risks / Trade-offs

- [核心 issues 與舊文字順序不同，造成未預期 UI 變化] → 除確認後的完整多筆顯示與總長文案外，projector 保存舊優先順序並加入 projection regression。
- [Invalid candidate penalty 被誤併入 local score，改變 GA fitness] → 分開命名 `local_score` 與 compatibility search score，對 invalid branches 建立固定 fixture。
- [移除 Waler adjustment block 使部分既有結果失效] → 對舊結果採 load-as-is、recalculate-on-edit；不做 persistence migration，回歸報告明列因新 domain rule 造成的預期差異。
- [Issue code 粒度過粗造成不同位置被錯誤去重] → 去重鍵包含 normalized facts，不只使用 code。
- [Typed result 增加一次 projection 成本] → 評估成本主要在大量候選迭代；hard-invalid plan 在 issue collection 後停止，不做 allocation／ratio／score，並以既有 Waler regression 與同 fixture benchmark 驗證。
- [重構使 Single／Global Waler 明顯變慢] → 初次實作已觸發 gate 並停線；使用者選擇修訂 B-01 語意，而非調整搜尋參數或以內部優化掩蓋。修訂後必須重跑相同 fixtures，若仍有超出正常抖動且可重現的退化，再次停線回報。

## Migration Plan

1. 建立 characterization tests，記錄現有合法／不合法／allocation／score／message projection，並記錄修改前 Single／Global fixture 執行時間。
2. 以相同 resolved context 產生自動／人工差異報告；若有 B 類差異，停止並等待使用者確認，完成相應 artifact 修訂與 validation 後才繼續。
3. 新增 structured evaluator、issue model 與 200 mm Waler 總長規則，先由 `evaluate_individual()` 使用；除確認後例外外保持舊 dict 相容。
4. 將 `WalerPlanEditing` 改為建立 evaluator input 並投影人工結果，移除重複公式、tail-adjustment 判斷與字串解析，完整顯示 structured issues。
5. 執行 focused、Single／Global Waler 與 Solver regression，記錄修改後同 fixtures 執行時間；初次效能 gate 失敗後依使用者決策修訂 invalid pipeline，再以同 fixtures 重跑；若仍明顯變慢即再次停止回報。
6. 若 gate 失敗，以 profiler 定位後由使用者確認最小修正；先驗證 lazy traversal，再依第二輪 profiler 與使用者確認改為 single synchronous scanner＋optional issue sink，保留正式完整 diagnostics，僅讓 repair boolean probe 不 materialize issues 並 short-circuit；重跑相同 fixtures 與 metadata equality。
7. 更新 `docs/DOMAIN.md` 移除 Waler adjustment block、加入 200 mm 總長閉區間；更新 `docs/SOLVER.md` 說明共用 evaluator、runtime-only issues 與新 Waler total pipeline。

回滾時可讓既有 callers 暫時回到原評估組裝；本 change 不修改 persistence data，因此不需資料回滾。若除 Decision 7 的確認例外外無法維持既有 score、排序或顯示 contract，停止於 migration step 2 或 3 並回報，不以額外改規則方式通過測試。
