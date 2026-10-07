# Proposal

## 閱讀導航

### P0｜現在必讀

- 本文件「快速摘要」「現況與目標」「主要流程」「不變事項」：先確認這次只新增圍令尾端調整塊，不改其他 Solver 政策。
- `specs/waler-plan-evaluation/spec.md` 的「圍令以單一尾端 adjustment block 與 Gap 完成需求長度」與邊界 scenarios：確認 `100／150／200／300 mm`、尾端位置及 `Gap <= 150 mm`。
- `design.md` Decision 1～4：確認單一 resolver、自動／人工共用 evaluator、結果投影與既有 Global change 的整合順序。

### P1｜實作前閱讀

- `docs/DOMAIN.md`「5.4 Waler 鋼材總長容許範圍」與「6.3 Steel Piece、Jack 與 Shim」：這兩節是本 change 明確要修改的現行 Domain truth。
- `docs/SOLVER.md`「8.3 Material-derived search discretization」「8.4 Search representation and evaluation pipeline」「11.2 WalerPlanEditing」。
- `openspec/changes/archive/2026-10-06-expand-global-waler-candidate-pool/` 的 proposal、design Decision 8 與兩份 delta specs；該 change 已封存並同步 main spec，本 change 必須保留其 Single Top 5／Global expanded retention 契約。

### P2｜需要時再讀

- 修改結果顯示、材料摘要或匯出 projection 時，再讀 `openspec/specs/dxf-result-export/spec.md`、`openspec/specs/excel-result-export/spec.md` 與 `openspec/specs/global-waler-result-adoption/spec.md` 的既有結果生命週期。
- 只處理圍令配置時，可先跳過 `support-shim-joint-validation` 的 Support Jack／Shim placement，以及 DXF recognition、Support adjacency、Project input schema 等 specs；它們不在本 change 範圍。

## 快速摘要

- 現在圍令只允許標準鋼材總長與需求長度相差 `0～200 mm`；鋼材以 `500 mm` 級距配置時，像 `16450 mm` 會因最接近的 `16000 mm` 仍短 `450 mm` 而無解。
- 新規則允許每個圍令方案最多一塊 `100／150／200／300 mm` 調整塊，固定放在全部 Steel segments 之後、Gap 之前，絕不出現在中間。
- 尾端組合必須滿足 `steel_length + adjustment + gap = required_length` 且 `0 <= gap <= 150 mm`；短差在 `0～150 mm` 時不放調整塊，只有短差大於 `150 mm` 時才使用能使 Gap 合法的最小調整塊。
- 自動 Solver 與人工重算共用同一規則；既有 segment、joint、庫存、評分權重、GA 搜尋與 Global Exact DP 規則不變。
- 這會改變 Domain 與 Solver truth，且與已封存的 `expand-global-waler-candidate-pool` 共用 evaluator／搜尋投影邊界；實作必須以其已同步的 retention 契約為基線。

## 現況與目標

本 change 的「調整塊」是圍令尾端用來補足標準鋼材與需求長度差的固定尺寸構件；它不是 Steel segment，也不是 Support 的端部 Shim placement 規則。

| 行為 | Before | After |
| --- | --- | --- |
| 可用尾端構件 | 不允許圍令調整塊 | 每個方案最多一塊 `100／150／200／300 mm` 調整塊；`0` 表示不用 |
| 配置位置 | `pieces` 只有 Steel，最後直接接 Gap | `Steel... → optional adjustment → Gap`；調整塊不得出現在 Steel segments 中間 |
| 長度合法性 | `required - 200 <= steel_length <= required` | `steel_length + adjustment + gap = required` 且 `0 <= gap <= 150` |
| `16450 mm` 範例 | `16000 + 450 Gap`，Gap 超限而無解 | `16000 Steel + 300 adjustment + 150 Gap`，合法 |
| 多解決定方式 | 無調整塊選擇 | 能不用就不用；必須使用時選能使 Gap 落在 `0～150 mm` 的最小調整塊，結果 deterministic |
| 自動／人工結果 | 新結果固定 `tail_adjustment = 0`、無 Waler `shim` | 兩條路徑共用 resolver，輸出相同 adjustment、Gap 與尾端 pieces |

## 主要流程

```text
需求長度 + 已決定的標準 Steel segments
  → 枚舉 adjustment ∈ {0, 100, 150, 200, 300}
  → 保留 adjustment + Gap 能恰好補足需求、且 0 <= Gap <= 150 的組合
  → 短差 <= 150 時選 adjustment = 0；否則選能使 Gap 合法的最小 adjustment
  → 共用 Waler evaluator 驗證 segments／joints／材料並產生結果
  → pieces = 全部 Steel +（若非 0）一塊尾端 adjustment
  → Single／Global／人工編輯及既有結果顯示、摘要、匯出消費同一結果
```

若找不到任何合法尾端組合，plan 仍依共用 evaluator 回報具名總長／尾端完成問題，不得由搜尋或 UI 自行放寬 Gap。

## 不變事項

- Steel segment 仍必須位於 `1000～10000 mm` 且存在於對應 `Purchasable Length`；調整塊不會變成可任意切割的 Steel segment。
- Waler joint clearance `>= 300 mm`、forbidden points、exact-length Steel allocation、庫存不足仍可採購等規則不變。
- 調整塊不納入 Steel 的 Short／Mid／Long／Out 分類、比例、庫存 allocation 或既有 local score components；本 change 不新增調整塊成本權重。
- GA stage、population、generations、Random Seed、candidate joint grid、repair、retention profile、candidate count、merge、tie-break 與 Global Exact DP objective 不變。
- Support 的 Jack／Shim 尺寸、位置、joint 例外與 scoring 完全不變。
- RC Waler optimization exclusion、Project input schema、commit／rollback、dirty、cancellation 與 result adoption workflow 不變。
- 不新增 persistence schema migration；既有 `tail_adjustment`／`pieces` 欄位沿用目前相容格式，新結果可重新產生非零值。

## Why

圍令標準鋼材以 `500 mm` 級距配置，但現行只容許最多 `200 mm` 的未覆蓋 Gap，造成部分實際需求長度即使可用固定調整塊施工，Solver 仍判定無合法方案。將一塊調整塊固定放在尾端，可補足這個離散長度缺口，同時避免調整塊插入中間後影響 joint 位置與搜尋表示法；本 change 同時將新方案的 Gap 上限收斂為 `150 mm`。

## What Changes

### In Scope

- 將 `100／150／200／300 mm` 定義為 Waler 可用的單一尾端調整塊尺寸，`0` 代表不配置。
- 將 Waler 完成長度契約改為 `steel_length + tail_adjustment + gap = required_length`，Gap 合法閉區間為 `0～150 mm`。
- 定義 deterministic 選擇順序：短差在 `0～150 mm` 時 `tail_adjustment = 0`、Gap 等於短差；短差大於 `150 mm` 時，選擇能使 `0 <= Gap <= 150 mm` 的最小調整塊。
- 要求調整塊只可位於最後一段 Steel 之後、Gap 之前，且每個 plan 最多一塊。
- 讓 automatic Solver 與 `WalerPlanEditing` 使用同一個尾端解析／評估結果，並輸出一致的 `tail_adjustment`、`gap` 與 `pieces`。
- 恢復既有相容 consumer 對非零 `tail_adjustment`／Waler `shim` piece 的顯示、材料摘要、Preview、Excel／DXF export 與 save／load regression coverage；不建立第二套調整塊推導。
- 新增 `12100 = 12000 + 0 + 100`、`12180 = 12000 + 100 + 80`、`12250 = 12000 + 100 + 150`、`16450 = 16000 + 300 + 150`、`0～450 mm` 可完成 residue、`451～499 mm` 不可解 residue、`Gap = 150` 等號邊界、非法尺寸／位置及無解案例測試。
- 實作驗證後更新 `docs/DOMAIN.md` 與 `docs/SOLVER.md`，把新規則寫成已成立的 long-term truth。

### Out of Scope

- 允許兩塊以上調整塊、將調整塊放在中間、讓使用者自由輸入任意調整塊尺寸，或把調整塊加入 joint positions。
- 建立調整塊庫存、採購數量、Material Spec、成本、Short／Mid／Long 分類或新的 score component。
- 修改 Steel purchasable lengths、500 mm 搜尋 grid、Waler joint clearance、Support Shim 規則或 RC Waler eligibility。
- 修改 GA／Global candidate retention、搜尋預算、scoring weights、Global objective、result adoption 或 persistence schema。
- 清理現有 result compatibility code 或進行無關重構。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `waler-plan-evaluation`：把「不使用 adjustment block、只以 Steel 短差判斷」改為「最多一塊尾端調整塊＋`0～150 mm` Gap」，並維持自動／人工共用 evaluator、既有 score 與搜尋政策邊界。

## Impact

- **Algorithms**：`bracing_optimizer/algorithms/wales.py` 的尾端解析、Config derived fields、共用 hard-rule evaluation、result signature／projection 與候選結果。
- **Application**：`bracing_optimizer/application/plan_editing.py` 的人工重算、合法性 details 與共用 resolver 投影；`optimize_waler.py` 的 cache schema／key 需確認 adjustment policy 變更不會讀取舊語意 cache。
- **Result consumers**：`project_results.py`、Preview、材料摘要、Excel／DXF export 目前已有 legacy `tail_adjustment`／`shim` 相容路徑；實作以驗證與必要的最小修正為主。
- **Tests**：Waler evaluator、tail adjustment、manual editing、Single／Global solver、result adoption／persistence、Preview／summary／export 與 architecture boundary regressions。
- **Dependencies／schema**：不新增外部 dependency，不提升 Project schema；既有結果可照常載入，重新計算時依新規則產生新的尾端組合。
- **Long-term truth**：Domain 與 Solver truth 會改變，實作完成後更新 `docs/DOMAIN.md`、`docs/SOLVER.md`；Architecture 與 Workflow ownership 不變。
- **Expected recomputation difference**：短差為 `151～200 mm` 的圍令在舊規則下以同尺寸 Gap 直接合法；新規則因 Gap 上限為 `150 mm`，重算時會改用一塊 `100 mm` adjustment block，Gap 變為 `51～100 mm`。這類既有合法 plan 的尾端 projection 改變屬預期行為，不代表 Steel segments、scoring 或搜尋政策被改寫。
- **Archived baseline coordination**：`expand-global-waler-candidate-pool` 已於 `2026-10-06` 封存並同步 main spec；其 `wales.py`、`optimize_waler.py`、`docs/SOLVER.md` 與 `waler-plan-evaluation` retention 契約皆是本 change 的實作基線，不得以覆寫方式遺失。

## 實作閱讀指引

實作者先讀 `design.md` Decision 1～4，再讀 delta spec 的「圍令以單一尾端 adjustment block 與 Gap 完成需求長度」「既有分數與搜尋政策相容」及所有 boundary scenarios。修改 Global 路徑前，再讀已封存 `expand-global-waler-candidate-pool` 的 Decision 1、2、8，以及 main spec 的 `Global output retention 擴大`／`搜尋政策與評估分離`；只有 result consumer regression 失敗時，才延伸閱讀 export／adoption specs。

## 尚未決定事項與重新評估條件

- 尾端選擇已確認採「能不用就不用；必須使用時取最小合法調整塊」。若產品要改成 Gap 最小優先、把 Gap 納入 scoring，或引入調整塊庫存／成本，屬新的產品決策，必須先更新本 change 的 spec 與 design。
- Gap 上限已確認為 `150 mm` 且包含等號；這不是未決事項。若工程端未來再次調整邊界，必須先同步更新本 change 的 spec 與 design，再修改實作。
- 若實作發現現有 persistence／export 無法安全承接非零 adjustment 而需改 schema 或公開格式，應停止並回報，不得自行擴大 scope。
