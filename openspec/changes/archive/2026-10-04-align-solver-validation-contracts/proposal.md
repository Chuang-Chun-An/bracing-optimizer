# Proposal

## 閱讀導航

- **P0 現在必讀**：本 proposal 的前五節；`waler-plan-evaluation` 的共用核心評估與不可購買料長；`support-shim-joint-validation` 的自動／人工共用 contract。
- **P1 實作前閱讀**：`design.md` 的 empty-set 語意與 Support verdict composition；本 change 的兩份 delta specs。
- **P2 需要時再讀**：`docs/SOLVER.md` Manual Editing、Waler Config 與 Support validation；相關 characterization tests。
- **可以先跳過**：Solver 搜尋參數、Global Waler DP、DXF workflow 與 persistence。

## 快速摘要

- 指定 Waler 規格卻得到明確空可購買集合時，核心目前會回填一般預設料長；GUI 雖阻擋，但 Application contract 不完整。
- Support 的人工編輯前置檢查會辨識 Jack／Shim 尺寸，但完整 plan evaluator 未將尺寸納入正式 valid verdict。
- 本 change 讓同一份 resolved context 在 UI、Application 與 Algorithms 得到一致工程結論。
- Support 自動候選本來就只使用 `JACK_LENGTH` 與 `SHIM_LENGTHS`，因此候選集合、分數與排序必須完全不變；只有人工或直接呼叫傳入的錯誤尺寸 layout 會由 valid 改為 invalid，並套用既有 invalid penalty。
- Waler 明確空集合的自動候選沿用既有 invalid fitness 與排序規則；Single／Global 找不到合法方案時回報失敗結果，不拋出例外。

## 現況與目標

| | Before | After |
| --- | --- | --- |
| Waler empty set | Config 將明確空集合補成預設料長 | 區分未提供 fallback 與已解析但無可購買料長 |
| Waler automatic solve | 空集合被 fallback 後可能進入一般搜尋 | 空集合候選均 invalid，沿用既有 invalid fitness；無合法方案以 diagnostics／invalid result 回報 |
| Support size | 人工編輯前置 validation 可判 invalid，core evaluator 的 plan 卻仍可能 valid | 一個正式 verdict 包含尺寸與既有 layout issues |
| Support scoring | 錯誤尺寸未形成正式 invalid penalty | 人工／直接呼叫的錯誤尺寸 layout 套用既有 invalid penalty；其他 score components 不變 |
| Editor feedback | Application 另有尺寸判斷分支 | 從 core issue 投影回饋，不建立第二套尺寸 verdict |
| UI | 顯示 Application 回傳的結果 | 只顯示 Application／core 的 authoritative verdict |

## 主要流程

1. Builder 建立可區分「未提供」與「明確空集合」的 resolved material context。
2. Waler evaluator 對明確空集合拒絕所有 Steel segments，不虛構採購料長。
3. Support evaluator 將 Jack／Shim 尺寸 issue 納入正式 verdict 與 deterministic priority。
4. Automatic、manual staged recalculation 與 headless core evaluation 消費同一 verdict；Application editor 從相同 issues 投影前置回饋，Presentation 不補判工程合法性。

## 不變事項

- Material Spec 空白仍允許求解，Usage fallback 與每種 99 根政策不變。
- Waler 庫存不足仍可採購，只有「料長不在可購買集合」才不合法。
- Jack／Shim 合法尺寸、Shim placement、RC terminal exception 數值不變。
- Support 自動候選生成只使用既有合法尺寸，候選集合、score、breakdown 與排序不變。
- 人工／direct-call 錯誤尺寸由 valid 改為 invalid 時，只有既有 invalid penalty 與因此得到的 total score 是預期差異；其餘 score components 不變。
- Waler invalid candidate penalty、candidate order、seed、search stage、merge／tie-break 與 cache policy 不因本 change 調整。

## Why

目前人工 Support editor 的 Application 前置檢查會回報錯誤尺寸，因而遮住 core verdict 的缺口；automatic、headless 或其他直接評估路徑仍可能把同一排列判為 valid。Waler 也會在明確空材料集合進入 Config 後被 falsy fallback 改寫。合法性應由 Application／Algorithms contract 自足，而不是依賴特定入口的額外判斷。

## What Changes

- 修改 Waler material context，保留未提供與明確空可購買集合的語意差異。
- 明確空集合使有 Steel segment 的 Waler plan 產生 non-purchasable issues，且不進行 allocation／score。
- 明確空集合進入自動求解時仍以既有 invalid-candidate penalty 作為 fitness；Single／Global 無合法方案時回傳既有失敗結果與 diagnostics，不以 exception 表示正常的不可行結果。
- 將 Jack 固定長度與 Shim 合法尺寸納入 Support 共用 evaluator 的正式 verdict。
- 保持 Support 自動候選生成不變；人工或 direct-call 錯誤尺寸 layout 改套既有 invalid penalty，除此之外不改 score components 或排序。
- 讓 Application editor 從 core issues 投影尺寸回饋，移除其平行尺寸 verdict；Presentation 維持只顯示 outcome。
- 增加 automatic／manual／Application direct-call 的一致性 tests 與既有分數 exact regression。

### In Scope

- Waler purchasable-length context 與 Support piece-size verdict。
- Automatic、manual、headless use case 的一致性。

### Out of Scope

- 新材料尺寸、庫存 scoring、比例政策、Solver cache redesign。
- 改變 invalid manual plan 可保存的產品決策。
- 調整搜尋效能或候選生成策略。

## 前置條件

- `align-support-shim-joint-validation` 已於 2026-10-01 archive，`Validation issues SHALL follow a deterministic priority` 等 Requirements 已存在於主規格 `support-shim-joint-validation`。
- `unify-waler-plan-evaluation` 已於 2026-10-01 archive，`統一合法性與 allocation 語意`、`既有分數與排序相容` 等 Requirements 已存在於主規格 `waler-plan-evaluation`。
- 因兩個前置 change 均已完成並同步主規格，本 change 可直接進入實作；不需先處理其他 active change。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `waler-plan-evaluation`: 明確空可購買集合不得回填預設料長，並須產生一致的不可購買 verdict。
- `support-shim-joint-validation`: Jack／Shim 尺寸 issue 必須進入自動與人工共用的正式 plan verdict。

## Impact

- 影響 `solver_input_builder.py`、`algorithms/wales.py`、`algorithms/support.py`、`plan_editing.py` 與對應測試；不預期修改 Main 的工程判斷。
- Domain 尺寸數值不變；Solver 文件會在實作完成後補充 resolved context、size-invalid penalty 與 issue priority。
- 不需要 persistence migration；舊結果只在下一次重算時套用一致 verdict。

