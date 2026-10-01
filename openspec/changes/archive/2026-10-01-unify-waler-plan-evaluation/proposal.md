# Proposal

## 閱讀導航

### P0｜現在必讀

- 本文件的「快速摘要」、「現況與目標」、「不變事項」與「In Scope／Out of Scope」：確認本次只統一評估路徑，不改變 Solver 政策。
- `specs/waler-plan-evaluation/spec.md`：確認共用評估契約、具名錯誤 code 與相容性情境。
- `design.md` 的「Decisions」：確認共用 evaluator 的責任邊界與舊 payload 的投影方式。

### P1｜實作前閱讀

- `docs/SOLVER.md`「8.4 Search representation and evaluation pipeline」、「8.8 Local score」及「11.2 WalerPlanEditing」。
- `docs/ARCHITECTURE.md`「3.2 Application」、「3.4 Algorithms」及 Application component 表中的 `WalerPlanEditing`。
- `tasks.md`：依相依順序實作與驗證；不應跳過自動／人工等價回歸測試。

### P2｜需要時再讀

- `docs/WORKFLOW.md`「Manual Result Editing」：只有確認人工編輯提交與 dirty 行為時才需閱讀。
- `openspec/specs/global-waler-result-adoption/spec.md`：只有確認 Global Waler 採用邊界時才需閱讀。
- `openspec/specs/rc-waler-optimization-exclusion/spec.md`：只有修改 optimization eligibility 時才需閱讀；本次可先跳過，因 RC 排除規則不在範圍內。
- DXF recognition、Support Solver 與 persistence 相關 specs 可先跳過。

## 快速摘要

- 現在自動 Solver 與人工 Waler 編輯各自組裝合法性、配料及分數結果，公式雖預期相同，實作重複使後續修改容易漂移。
- 建立單一 Waler plan evaluator，讓兩條流程共用 segment legality、joint clearance、purchasable length、allocation 與 local score 計算。
- 評估問題改以穩定的具名 code 表達；中文訊息只負責顯示，不再作為去重或分類依據。
- 實作前先以相同 resolved context 比對兩條路徑；若合法性、allocation、score components 或 issue 種類不同，完成差異報告後停線，由使用者確認統一規則。
- 合法方案的分數公式與自動 invalid penalty 維持不變；任何含 hard-constraint issue 的方案都不執行 allocation／ratio／local score；人工畫面仍列出全部違規。圍令不再使用 adjustment block，鋼材總長改以需求長度向下 200 mm 的閉區間判斷。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| 評估入口 | 自動 Solver 在 Algorithms 評估；人工編輯在 Application 重做部分相同計算 | 兩者把已解析的 plan 輸入交給同一個 Algorithms evaluator |
| 合法性與配料 | 兩條路徑分別呼叫或重組 segment、joint、可購買料長與 allocation 判斷 | evaluator 一次產生一致的合法性、allocation、score 與 diagnostics |
| 錯誤識別 | 部分邏輯依中文訊息內容過濾、分類或去重 | 每個問題有穩定具名 code；顯示層仍投影成既有中文訊息 |
| 對外結果 | 自動與人工 payload 可能因重複實作而逐漸漂移 | 相同工程輸入得到相同的核心評估結果，既有 payload 與排序相容 |

「Waler plan evaluation」是指對一組已決定的 segments／joints 執行工程合法性、庫存／採購 allocation 及 local score 計算；它不包含 GA 候選生成、修補或選擇。

## 主要流程

```text
自動候選 decode ─┐
                 ├─> 共用 Waler plan evaluator
人工 segments ───┘      ├─ segment／joint／purchasable legality
                        ├─ exact-length allocation
                        ├─ 現行 local score
                        └─ 具名 issue code + 相容顯示資料
                                 ↓
                  自動排序或人工編輯結果投影
```

在建立共用 evaluator 前，流程先以完全相同的 resolved context（包括 segments、joints、config、同一份庫存 Qty 與空白規格 fallback）執行兩條既有路徑並產生差異報告：

1. A 類僅包含訊息文字、順序或欄位名稱等顯示格式差異，由各自 compatibility projector 保留，無需產品決策。
2. B 類包含合法性判斷、allocation、score components 或 issue 種類差異；報告完成後立即停止，不得開始共用 evaluator 實作。
3. B 類只能在使用者確認以哪一邊或哪一條明確規則為準後繼續；不得自行選擇較寬鬆規則或為通過測試而改規則。

## 已確認統一規則

characterization comparison 的五項 B 類差異已由使用者逐項確認：

1. Core 先完整收集總長、joint clearance、segment range 與 purchasable-length issues；只要已有任何 hard-constraint issue，automatic 與 manual 都不再執行 allocation、ratio 或 local score，相關欄位標示為 unavailable。此規則是初次效能 gate 顯示 Single／Global 明顯變慢後，由使用者重新確認取代原先「可 allocation 的 invalid plan 仍計 diagnostics」決策；不是以快取或調整搜尋參數掩蓋成本。
2. segment 不可購買或 allocation unavailable 時，以 automatic 語意為準：不得把不可購買 segment 虛構為採購，不產生 allocation components 或 local score。正常人工 UI 原本即禁止輸入不可購買料長，此變更只收斂防禦性 service contract。
3. core 保留每個 joint-clearance 與 non-purchasable segment issue；人工畫面也改為依固定順序列出全部違規，不再只顯示第一筆。
4. 圍令不使用 adjustment block；Support Shim 規則不受影響。Waler 鋼材總長 `steel_length` 的合法閉區間為 `required_length - 200 <= steel_length <= required_length`。
5. 鋼材總長低於下界時顯示「鋼材總長不足」，高於需求長度時顯示「鋼材總長太長」；不再產生或顯示「尾端調整量不合法」。

## 不變事項

- 在尚未發現或確認 B 類差異前，合法方案 local score 的 components、運算順序、數值型別、權重與結果完全不變，不使用浮點容差。
- segment range、joint clearance、purchasable length 與 exact-length allocation 規則不變；唯一確認的工程規則變更是 Waler 移除 adjustment block，並改採 `required_length - 200 <= steel_length <= required_length`。
- 自動 Solver 的 GA stage、population／candidate count、random seed、repair、merge 與 tie-break policy 不變；合法候選集合未受新總長規則影響時，score 與排序不變。
- 除已確認的「顯示全部違規」及「鋼材總長不足／太長」外，既有中文錯誤與警告呈現、候選 payload、人工編輯結果及有效／無效判定維持相容。
- 人工 invalid plan 是明確相容例外：只要有總長、joint clearance、segment range 或 non-purchasable issue，allocation／ratio／local score 欄位改為 unavailable；不再顯示可被誤認為合法方案比較依據的診斷分數。
- Project result commit、dirty、persistence、Global Waler adoption 與 RC exclusion 流程不變。
- 合法 plan 的 local score components、權重、運算順序與數值型別不變；受新總長規則影響而改變合法性的 plan 不受「既有結果完全相同」保證。

## Why

自動 Waler Solver 與人工編輯目前重複實作同一組評估責任，任何合法性、allocation 或 scoring 維護都必須同步修改多處，已確定增加修改成本並形成漂移風險。這是已確認的技術債，不需新增產品決策，但需要以明確契約保護現有行為。

## What Changes

- 新增可由自動 Solver 與人工編輯共同呼叫的 Waler plan evaluation 契約。
- 將 segment legality、joint clearance、purchasable length、exact-length allocation、材料比例與 local score 收斂到同一評估結果。
- 為評估問題定義穩定、具名的 issue code，並讓分類／去重依 code 與結構化內容進行。
- 保留未受確認決策影響的自動候選與人工編輯 payload 投影；相同合法候選的分數與排序不變。
- 套用重新確認的 invalid evaluation sequence：先完整收集全部 hard issues；有任一 hard issue 時停止 allocation／ratio／local score。只有無 hard issue 的 plan 才進入 exact-length allocation 與評分。
- 人工 legality 顯示改為完整列出所有 joint-clearance 與 non-purchasable issues。
- **BREAKING**：移除 Waler adjustment block；Waler 鋼材總長必須落在 `[required_length - 200, required_length]`，超界分別回報總長不足或總長太長。
- 增加等價與回歸測試，證明相同輸入在自動與人工路徑得到相同核心結果。
- 在重構前產生自動／人工差異報告；B 類差異採使用者決策 gate，A 類差異保留於各自 projector。
- 以既有 Single／Global Waler fixtures 記錄修改前後執行時間；明顯變慢時停線回報，不調整搜尋參數補償。
- 依 profiler 證據將 hard-rule traversal 分成完整 diagnostics 與 repair boolean probe 兩種消費方式；規則仍只有一份，正式 evaluator 仍完整收集 issues，repair 不再建立未使用的 issue list／中文訊息。

## In Scope

- `bracing_optimizer/algorithms/wales.py` 的既有 plan 評估、合法性、allocation 與 score 組裝。
- `bracing_optimizer/application/plan_editing.py` 中 `WalerPlanEditing` 對共用 evaluator 的調用與人工顯示資料投影。
- Single／Global Waler 間接使用同一自動候選評估路徑的相容性驗證。
- 自動／人工既有路徑的差異報告，以及與上述行為直接相關的 focused tests、效能比較與 Solver regression tests。
- Waler 總長 200 mm 容許範圍、移除 adjustment block，以及相關 automatic／manual payload 與顯示投影。
- 共用 synchronous issue scanner 在正式 plan evaluation 與 GA repair feasibility probe 間的效能修正；正式評估透過 optional sink 收集完整 issues，repair 無 sink 並在第一個 issue short-circuit；不修改 repair steps 或搜尋政策。

## Out of Scope

- 除已確認的 Waler 總長範圍與移除 adjustment block 外，修改其他工程合法性或材料政策。
- 修改 score component、權重、比例目標或 score comparison precision。
- 修改 GA stage、population、candidate count、seed、repair、搜尋空間或停止條件。
- 除完整列出違規與總長不足／太長文案外，重設計 UI、Dialog、結果 Tree、commit／rollback、dirty 或 persistence schema。
- 整理其他 Algorithms／Application technical debt。

## Capabilities

### New Capabilities

- `waler-plan-evaluation`: 定義自動 Solver 與人工編輯共用的 Waler plan 合法性、allocation、scoring、具名 issue 及相容輸出行為。

### Modified Capabilities

無。現有 capability 未定義這項共用評估契約。

## Impact

- 主要受影響程式：`bracing_optimizer/algorithms/wales.py`、`bracing_optimizer/application/plan_editing.py`。
- 主要受影響測試：`tests/test_plan_editing.py`、Waler evaluation／tail adjustment／Single 與 Global Waler regression tests。
- 實作前新增差異報告；若出現 B 類差異，將影響範圍暫停在報告與使用者決策，不進入 Algorithms／Application 重構。
- Automatic invalid candidate 對外 penalty 與 GA 排序維持相容；core 對任何含 hard issue 的 plan 不產生 diagnostic allocation／components。初次實作因對 invalid candidate 執行 allocation，使 Single 中位數增加 114.2%、Global 增加 65.3%；使用者據此重新確認 B-01 語意，而非授權調整 GA 或只做內部效能補償。
- 後續 profiler 證實主要退化來自 GA repair 的 boolean probe，而非 allocation 或 scoring。第一輪 lazy shared traversal 已移除 structured issue 與中文訊息 materialization，但仍因大量 generator 建立／resume 而相較同場 Git HEAD 明顯變慢；使用者已確認改採單一 synchronous scanner 與 optional issue sink：正式 evaluator 保持完整 issue collection，repair 不傳 sink 並在第一個 hard issue short-circuit。此修正不得改變任何 candidate、repair step、diagnostic output 或 Solver metadata。
- 人工 joint／總長／segment-range invalid plan 原先可能仍顯示 allocation 與 local score；統一後這些欄位與 non-purchasable invalid plan 一樣為 unavailable。合法性與完整 issue 顯示不受影響。
- 人工防禦性 service contract 對不可購買 segment 不再回傳虛構的 buy count、stock groups、variation 或 local score；正常 UI 原本即阻止此輸入。
- 人工 legality 顯示會由只列第一筆改為列出全部 joint-clearance 與 non-purchasable issues。
- Waler 既有 `0／100／150／200／300 mm` adjustment block 行為移除；`tail_adjustment` 不再代表可用 Waler 材料，Waler pieces 不再產生 `shim`。既有專案中仰賴 adjustment block 才合法的結果在下次重算時可能變為 invalid 或沒有可用候選。
- 新總長 hard constraint 可能改變 Single／Global Waler 的合法候選、Top N 與排序；這是使用者確認的工程規則影響，不得用調整 GA stage、seed、candidate count 或其他搜尋參數補償。
- 不新增外部 dependency，不改 persistence 或公開使用者操作流程。
- Architecture responsibility 不變：Algorithms 擁有計算核心，Application 準備人工編輯 context 並投影既有 workflow 結果。
- Domain 與 Solver truth 會因移除 Waler adjustment block、改採 200 mm 總長閉區間而改變；實作驗證後 MUST 更新 `docs/DOMAIN.md` 與 `docs/SOLVER.md`。Architecture 與 Workflow ownership 不變。

## 實作閱讀指引

實作者應先讀 `design.md` Decision 1～3、7，再讀 `specs/waler-plan-evaluation/spec.md` 中「共用核心評估」、「統一合法性與 allocation 語意」、「Waler 總長使用 200 mm 閉區間且不使用 adjustment block」與「具名問題識別與完整顯示」。只有碰到人工提交或 Global result adoption 的回歸問題時，才延伸閱讀 `docs/WORKFLOW.md` 或既有 adoption spec。

## 尚未決定事項與重新評估條件

目前沒有未決產品問題；五項 B 類差異均已確認，其中 B-01 在初次效能 gate 後由使用者重新確認為「任何 hard issue 都停止 allocation／ratio／local score」。修訂後 artifacts 完成並 strict validate 前不得繼續修改對應實作。

若實作發現維持既有中文錯誤呈現或 payload 必須改變公開欄位、分數、排序、合法性結果或搜尋政策，也應停止實作並重新評估 scope，不得自行選擇較寬鬆規則或為讓測試通過而改變行為。
