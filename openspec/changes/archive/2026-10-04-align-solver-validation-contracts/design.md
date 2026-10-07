# Design

## 閱讀導航

- **現在必讀（P0）**：Decision 1 的三態材料語意與 Decision 2～3 的 Support 共用 issue composition。
- **實作前閱讀（P1）**：兩份 delta specs、docs/SOLVER.md 相關段落與 tasks.md 第 1～3 節。
- **條件式閱讀（P2）**：若觸及 manual editor，讀 support-editor-result-mutation；若觸及 Waler allocation，讀主 waler-plan-evaluation。
- **可先跳過**：搜尋調參、材料比例權重、DXF workflow 與 persistence migration。

## 方案摘要

Waler Config 將「未指定」與「明確空集合」分開，Application 在材料規格空白時明確解析為既有預設與 99 支，核心不再把所有 falsy list 當預設。Support validator 新增 Jack／Shim size issues，並由同一個 issue composer 同時決定 automatic 與 manual plan 的 valid／reason；自動候選因只使用既有尺寸而完全不變，人工／direct-call 錯誤尺寸則套用既有 invalid penalty。Application editor 從相同 issues 投影前置回饋，Presentation 只顯示結果。

## 決策對照

| Decision | 對應 Requirement | 對應 task |
| --- | --- | --- |
| D1. Waler purchasable lengths 使用 omitted／empty 三態 contract | 明確空的可購買料長不得被核心預設值覆蓋 | 2.1、2.2 |
| D2. 自動 Support 尺寸來源封閉，外部錯誤尺寸成為具名 hard issues | Jack 與非零 Shim 必須使用既有合法尺寸；自動候選不變 | 1.2、3.1 |
| D3. 單一 Support issue composer 決定 verdict 與 editor feedback | deterministic priority、自動與人工相同 | 3.2、3.3 |
| D4. 無可購買 Waler 以既有 invalid fitness 與 failure result 結束 | 明確空集合的 allocation；Single／Global 無合法方案 | 2.2 |

## Context

Waler Config.__post_init__ 目前以 falsy 判斷補預設料長，使 application 已解析出的空集合失去語意。Support 基礎輸入檢查能發現部分尺寸問題，但核心 plan evaluator 的 valid 可能未包含同一 issue，造成 UI、manual recalculation 與 headless use case 不一致。

## Design Discovery 與前置狀態

- `bracing_optimizer/algorithms/support.py` 的 `generate_length_combinations_dp()` 只以 `SHIM_LENGTHS` 迭代 Shim，並以 `JACK_LENGTH` 計算 Steel target；`generate_waler_rule_layouts()` 建立 Jack 時固定使用 `("jack", JACK_LENGTH)`，非零 Shim 直接取自前述 combination。`beam_search_layout()` 是正式自動候選進入 `evaluate_single_support()` 的唯一 layout 建立路徑，因此自動候選不會產生錯誤 Jack／Shim 尺寸。
- 既有 `tests/test_support_waler_type_rules.py` 覆蓋 Steel／RC 端型態的 layout generation、零 Shim 與完整 Phase 1／Phase 2。2026-10-04 focused run 共 25 tests 通過；另以四種端型態產生 80 個自動候選逐一檢查，全部只有 `600 mm` Jack，所有 Shim 均屬 `SHIM_LENGTHS`。實作時仍須新增一個直接斷言尺寸集合、candidate signature、score 與排序 exact equality 的永久 regression test。
- `align-support-shim-joint-validation` 與 `unify-waler-plan-evaluation` 均已於 2026-10-01 archive；本 change 使用的 MODIFIED Requirement 標題分別存在於主規格 `support-shim-joint-validation` 與 `waler-plan-evaluation`，沒有未完成的前置 artifact。

## Goals / Non-Goals

**Goals:**

- 保留「未填規格使用預設 99 支」政策，同時讓明確空集合可被忠實評估。
- Jack／Shim size 在所有入口得到同一 invalid verdict。
- Support 自動候選集合、score、breakdown 與排序 exact 不變；人工／direct-call 錯誤尺寸只依既有公式新增 invalid penalty。
- Waler invalid fitness、candidate ordering 與 search policy 不變，無合法方案以既有 result／diagnostics contract 回報。

**Non-Goals:**

- 不建立採購／即時庫存系統。
- 不廢除短中長比例或調整 Support／Waler 比例。
- 不阻擋人工保存可解析但工程不合法的 plan。

## Architecture Alignment

本 change 沿用 Architecture。Application 的 solver_input_builder 將 Project 材料資料解析成明確 contract；Algorithms 執行合法性與既有 allocation；Presentation 不判斷尺寸或補材料。Support 尺寸常數與 issue composition 留在 solver/domain-adjacent core，不依賴 UI。

## Decisions

### Decision 1: 用 None／omitted 表示核心預設，空 sequence 表示無可購買料長

Waler config 建構時，未提供 purchasable lengths 才套既有預設；顯式空 sequence 正規化後仍為空。Application 對「材料規格未填」建立預設 material context，每種數量 99；使用者明確輸入數量則保持原值。這使 default policy 的 single source of truth 留在 solver_input_builder，Algorithms 不再猜 Project 是否空白。

拒絕在 evaluator 看到空集合就 fallback，因為它抹除呼叫端已解析的商務語意。

明確空集合仍須完成 automatic compatibility projection：core allocation／local score 保持 unavailable，但每個自動候選以既有 hard-invalid penalty 作為 fitness，既有 sort key、signature、去重與 tie-break 不變。Single Waler 搜尋結束後回報 `no_legal_solution`；Global Waler 遇到任一必要 Waler 沒有合法 local candidate 時回傳 invalid solution 與 failed-Waler diagnostics，不把正常不可行結果轉成 exception。

### Decision 2: Jack／Shim size 以具名 issue 表示

沿用既有 JACK_LENGTH = 600 與 SHIM_LENGTHS = [0, 100, 150, 200, 300]。新增穩定 issue code 與中文訊息；0 在 normalization 階段仍代表沒有 Shim，不建立 size issue。尺寸問題屬 Engineering Hard Constraint。

自動候選生成不修改，因為其 Jack／Shim 尺寸已由上述常數封閉產生。只有人工 editor 或 direct core caller 能送入錯誤尺寸；這些 layout 從修改前的 valid 轉為 invalid 時，使用既有 invalid-candidate penalty 公式，不新增權重、不改公式，也不改 short、joint、gap、Jack edge 等既有 components。

### Decision 3: verdict 由完整 issue composer 一次產生

在既有 Jack count、Shim count、placement、gap、joint、Steel length 檢查中加入 size stages，按 spec 的 priority 建立 ordered issues。plan.valid 由是否存在 hard issue 推導，plan.reason 由同一 ordered list 格式化。automatic evaluator、manual SupportPlanEditing 與 headless core call 共用此函式；SupportPlanEditing 的前置 feedback 只投影相同 issue code／message，另保留無法正規化輸入的 basic parse rejection。

issue gate 只控制 reason 呈現，不跳過既有 score／penalty 計算。自動候選及不涉及新 size issue 的 layout 必須 exact 不變；新 size-invalid layout 的唯一預期 score 差異，是依既有公式加入 invalid penalty。若出現其他 component、權重、自動候選 signature 或排序差異，應停止並回報。

## Source of Truth

- 未填規格的預設料長與 99 支：solver_input_builder resolved context。
- Waler plan legality：Waler evaluator issues。
- Jack／Shim 合法尺寸：Support core 的既有具名常數。
- Support valid／reason：共用 issue composer。
- Support size-invalid score：既有 invalid-candidate penalty 公式；本 change 不建立第二套 penalty。

## Backward Compatibility / Persistence

既有 Project payload 不變。舊結果載入時不重算；下一次 manual recalculation 或 Solver execution 使用新 verdict。省略 Waler lengths 的既有程式呼叫仍取得預設；顯式空 sequence 的語意有意改為「無可購買料長」。

## Risks / Trade-offs

- [舊測試以空 sequence 代表 omitted] → 先做 caller audit，將真正的 omitted caller 改用 None，空集合測試改驗證新 contract。
- [size issue 誤改自動候選 scoring] → 先以永久 regression 鎖定自動 candidate signatures、score components、total score 與排序 exact equality；錯誤尺寸 direct-call cases 只允許既有 invalid penalty 差異。
- [Application editor 仍保留平行尺寸分支] → 尺寸 feedback 改由 shared core issue 投影；只有型別、數值與正長度等 basic normalization failure 維持獨立拒絕。
- [空 Waler 集合使搜尋路徑拋例外] → Single／Global tests 明確要求 normal failure result／diagnostics，不以 exception 表示無合法方案。

## Migration Plan

兩個 prerequisite changes 已 archive。先以 characterization tests 鎖定 Support 自動候選與 Waler invalid fitness，再調整 Waler context；Support 先新增 issue function與既有 invalid penalty 接線，再接 manual feedback。完成 focused／full regression 與 OpenSpec verify 後再 archive 本 change；不需插入或處理其他 active change。沒有資料 migration，可按兩個 capability 獨立回退。
