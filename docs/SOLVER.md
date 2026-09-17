# Solver Guide

本文件提供 SupportOptimizer 求解器的高階流程、安全邊界與修改注意事項。詳細演算法以程式碼與既有測試為準。

## 1. Solver Components

主要檔案：

- `bracing_optimizer/algorithms/support.py`
- `bracing_optimizer/algorithms/wales.py`
- `bracing_optimizer/algorithms/solver_search.py`
- `bracing_optimizer/application/optimize_support_zone.py`
- `bracing_optimizer/application/optimize_waler.py`
- `bracing_optimizer/application/solver_input_builder.py`
- `bracing_optimizer/domain/material_rules.py`

## 2. Support Solver Flow

```text
ProjectDataModel
    |
    v
solver_input_builder.py
    |
    v
SupportZoneInput
    |
    v
OptimizeSupportZone
    |
    +--> Phase 1: 每支支撐產生合法候選
    |       |
    |       +--> 幾何 / 禁止區 / 材料 / Jack / Shim 規則
    |       +--> 候選多樣性與保留策略
    |
    +--> Candidate Cache
    |
    +--> Phase 2: 多支支撐全域搜尋
            |
            +--> Shared Layout Group
            +--> Jack 區域與相鄰支撐協調
            +--> Material Ratio / Penalty
            +--> Solver Search Policy
```

`OptimizeSupportZone` 是 application use case，負責流程協調與 diagnostics；GUI 不應自行重做此流程。

## 3. Waler Solver Flow

```text
ProjectDataModel
    |
    v
WalerProblemInput
    |
    v
OptimizeWaler
    |
    v
wales.py
    |
    +--> 建立可行分段
    +--> 避開 forbidden positions
    +--> staged search / GA
    +--> scoring
    +--> 合併與排序結果
```

圍令材料、接頭與尾端調整規則請另讀 `docs/wales/README.md`。

## 4. Search Policy

搜尋參數集中於 `solver_search.py` 的 policy，而不是 GUI。

修改下列項目會改變演算法行為與可重現性：

- candidate count
- beam width
- random seed
- population / generations
- staged search thresholds
- stability / escalation conditions

這些不是一般 UI setting。除非需求明確要求，不應自行調整。

## 5. Candidate Cache

支撐候選使用 cache 避免重複計算。

任何會影響候選結果的輸入或搜尋參數，都必須反映在 cache key。

因此，若修改：
- 幾何限制
- 材料條件
- Jack / Shim 規則
- candidate generation 參數
- search policy version

必須檢查 `build_support_candidate_cache_key` 與 `tests/test_support_candidate_cache_key.py`。

錯誤的 cache key 可能造成「程式看似正常，但拿到舊候選」的隱性 bug。

## 6. Legality Before Score

Solver 的首要條件是工程合法性，而不是低分。

AI 修改時不可：
- 為了找到解而放寬 forbidden zone。
- 為了速度跳過 legality check。
- 把 invalid candidate 留進全域最佳化。
- 只因測試難通過就降低限制。

若沒有合法解，應改善 diagnostics 或確認輸入條件，而不是默默放寬工程規則。

## 7. Scoring

目前 scoring 包含多個工程與材料目標，不是一個可以自由「優化得更聰明」的 generic objective function。

可能包含：
- 購買材料數量。
- 材料長度比例偏差。
- 過短材料懲罰。
- 材料種類。
- 長度差異。
- 接頭數。
- Jack 分布與全域協調相關 penalty。

若要修改 scoring：
1. 先寫 spec 說明想改變的工程行為。
2. 列出舊公式與新公式。
3. 說明可能改變哪些既有案例排序。
4. 建立或更新測試。
5. 不要同時混入 unrelated refactor。

## 8. Diagnostics

Solver diagnostics 是使用者理解「為什麼找不到解 / 為什麼增加搜尋強度」的重要資訊。

修改 solver 時需保留：
- 是否找到合法解。
- 搜尋是否 escalated。
- 結果是否穩定。
- 候選不足與 invalid reason。

Presentation 應顯示工程意義，不必暴露所有演算法參數。

## 9. Recommended Test Order

### 修改 Support Solver
優先：

```text
tests/test_optimize_support_zone.py
tests/test_support_candidate_cache_key.py
tests/test_support_material_ratio.py
tests/test_double_support.py
tests/test_support_waler_type_rules.py
tests/test_solver_search.py
tests/test_solver_diagnostics_integration.py
```

### 修改 Waler Solver
優先：

```text
tests/test_optimize_waler.py
tests/test_wales_tail_adjustment.py
tests/test_material_rules.py
tests/test_solver_search.py
```

### 修改 Input / Domain Boundary
優先：

```text
tests/test_solver_input_builder.py
tests/test_application_domain_boundaries.py
tests/test_project_domain.py
```

## 10. Change Checklist

修改 Solver 前回答：

- 這是 Domain Rule、Search Policy、Performance 還是 Presentation 問題？
- 是否影響 candidate legality？
- 是否影響 cache key？
- 是否影響 scoring？
- 是否影響 random reproducibility？
- 是否影響 diagnostics？
- 哪些 tests 應該先失敗、修改後通過？

若回答不清楚，先分析，不要直接改 Solver。
