# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：Jack／Shim 尺寸 Requirement 與更新後的 deterministic priority。
- **實作前閱讀（P1）**：`../../design.md` 的共用 verdict composition 決策。
- **需要時再讀（P2）**：主規格其餘 Shim placement、RC terminal exception 與 scoring compatibility；本 delta 不修改它們。

## ADDED Requirements

### Requirement: Jack 與非零 Shim 必須使用既有合法尺寸

Support ordered pieces 中每一支 Jack SHALL 恰為 `600 mm`。每一塊非零 Shim SHALL 為 `100 mm`、`150 mm`、`200 mm` 或 `300 mm`；`0` SHALL 依既有規格表示沒有 Shim piece。可解析但尺寸不符的人工或 direct-call layout SHALL 保持可評估，正式 plan verdict SHALL 為 invalid，且 SHALL 提供可辨識的尺寸原因。這類修改前未被尺寸規則判 invalid 的 layout SHALL 套用既有 invalid-candidate penalty 公式；除 invalid penalty 與因此改變的 total score 外，既有 score components SHALL 不變。

#### Scenario: Jack 尺寸正確

- **WHEN** 唯一 Jack 的長度恰為 `600 mm`
- **THEN** validator SHALL NOT 單因 Jack 尺寸產生 issue

#### Scenario: Jack 尺寸錯誤

- **WHEN** ordered pieces 含有一支 `700 mm` Jack
- **THEN** Support plan SHALL 為 invalid
- **AND** reason SHALL 可辨識為 Jack 尺寸問題

#### Scenario: Shim 尺寸錯誤

- **WHEN** ordered pieces 含有一塊 `145 mm` Shim
- **THEN** Support plan SHALL 為 invalid
- **AND** reason SHALL 可辨識為 Shim 尺寸問題

#### Scenario: 自動 Solver 只產生既有合法尺寸

- **WHEN** Support 自動 Solver 以相同 Project input、search config、cache state 與 random seed 產生候選
- **THEN** 每個候選中的唯一 Jack SHALL 為 `600 mm`
- **AND** 每塊非零 Shim SHALL 屬於 `100 mm`、`150 mm`、`200 mm` 或 `300 mm`
- **AND** 本 change 前後的候選集合、每個 score component、total score 與 deterministic 排序 SHALL 完全相同

#### Scenario: 人工與直接呼叫的錯誤尺寸成為 invalid

- **WHEN** 一個修改前只因尺寸未進入正式 verdict 而被視為 valid 的 Jack 或 Shim 錯誤尺寸 layout，經由人工 staged recalculation 或 direct core evaluation 評估
- **THEN** plan SHALL 由 valid 改為 invalid，並產生相同的尺寸 issue
- **AND** invalid penalty SHALL 依既有 invalid-candidate penalty 公式由 `0` 改為對應值
- **AND** short、joint、gap、Jack edge 及其他既有 score components SHALL 與修改前完全相同
- **AND** total score SHALL 只因既有 invalid penalty 的加入而改變
- **AND** 可解析的人工 layout SHALL 仍可依既有 staged invalid 語意保存

#### Scenario: 共用評估與人工流程投影相同錯誤尺寸

- **WHEN** 相同的錯誤 Jack 或 Shim 尺寸分別經由 direct core evaluation 與人工 staged recalculation 評估
- **THEN** 兩條路徑 SHALL 產生相同的 invalid verdict 與尺寸 issue
- **AND** 人工編輯的前置回饋 SHALL 從相同正式 issue 投影，不得建立另一個尺寸 verdict
- **AND** Presentation SHALL NOT 自行改寫 verdict

## MODIFIED Requirements

### Requirement: Validation issues SHALL follow a deterministic priority

Support validation reason SHALL 使用固定優先順序：Jack count、Jack size、Shim count、Shim size、Shim placement、gap、forbidden joint、Steel length。高優先 gate 未通過時 SHALL 只限制 reason 要回報哪些 issues；gate SHALL NOT 中止完整 candidate evaluation、scoring 或 penalty 計算。既有扣分輸入與計算（包含 `count_forbidden_piece_joints` 等既有項目）SHALL 仍完整執行。其餘可同時回報的 issues SHALL 依固定順序組成 reason，且不受 piece iteration、collection 或執行順序影響。

#### Scenario: Invalid Jack count suppresses later issues

- **WHEN** ordered pieces 的 Jack 數量不符合既有規則
- **THEN** reason SHALL 只包含 Jack 數量問題
- **AND** reason builder SHALL NOT 回報 Jack size、Shim count、Shim size、Shim placement、gap、forbidden joint 或 Steel length issue
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score／penalty 項目

#### Scenario: Invalid Jack size suppresses later issues

- **WHEN** Jack 數量正確但任一 Jack 尺寸不符合既有合法尺寸
- **THEN** reason SHALL 只包含 Jack 尺寸問題
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score components，並套用既有 invalid-candidate penalty 公式

#### Scenario: Multiple Shims suppress placement and later issues

- **WHEN** Jack 數量與尺寸正確
- **AND** ordered pieces 含有超過一塊非零 Shim
- **THEN** reason SHALL 只包含 Shim 數量問題
- **AND** reason builder SHALL NOT 回報 Shim size、Shim placement、gap、forbidden joint 或 Steel length issue
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score／penalty 項目

#### Scenario: Invalid Shim size suppresses later issues

- **WHEN** Jack 與 Shim 數量 gate 均通過，但唯一非零 Shim 尺寸不合法
- **THEN** reason SHALL 只包含 Shim 尺寸問題
- **AND** candidate evaluation SHALL 仍計算修改前會計算的所有 score components，並套用既有 invalid-candidate penalty 公式

#### Scenario: Remaining issues have stable order

- **WHEN** Jack count、Jack size、Shim count 與 Shim size gate 均通過
- **AND** layout 同時觸發兩個或以上其餘 issues
- **THEN** reason SHALL 依 Shim placement、gap、forbidden joint、Steel length 的順序組成
- **AND** 等價 pieces 或 checks 以不同 iteration／execution order 執行時 SHALL 產生相同 reason
