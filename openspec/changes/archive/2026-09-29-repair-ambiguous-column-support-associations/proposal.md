# Proposal

## 閱讀導航

### P0｜現在必讀

1. 本文件「快速摘要」「現況與目標」：確認只處理兩支支撐距離接近的中間柱警告。
2. 本文件「主要流程」「不變事項」：確認人工選擇如何成為各支撐的禁止點，以及不會建立雙路支撐。
3. `specs/dxf-column-association-repair/spec.md` 的「只讓明確的雙候選中間柱進入修補」「人工選擇決定各支撐的禁止點」「有效人工決策解除原關聯歧義」。

### P1｜實作前閱讀

- `design.md` Decision 1～4：候選來源、Review 決策、重建及畫面入口。
- `dxf_import/candidate_points.py` 的 `associate_components_to_struts()`、`rebuild_component_associations()`，以及 `dxf_import/review_workflow.py` 的 Review mutation／resume 流程。
- `docs/DOMAIN.md` 4.2、4.7：Column station 禁止點與雙路支撐的不同工程意義。

### P2｜需要時再讀

- 修改相同來源恢復時，閱讀 `openspec/specs/paused-dxf-review-source-relink/spec.md` 的 Exact Match／replay 規則。
- 檢查共享關聯時，閱讀 `openspec/changes/surface-provisional-double-support-candidates/` 的 proposal 與 spec「暫定候選不得提前產生正式效果」。
- 可先跳過 `support-adjacency` 的 Solver adjacency、Jack spacing，以及角撐修補的 reference-template 規則；本 change 不改這些演算法。

## 快速摘要

- Y29 C25 同時接近 S20、S35，現行僅因 S20 稍近而把柱的禁止點給 S20；警告沒有可操作的修補途徑。
- 在 DXF Review 的「修改工具」新增「中間柱關聯修補」，只列出中間柱同時接近兩支有效支撐的警告案例。
- 使用者預覽距離與各支撐的 station 後，明確選擇其中一支或兩支；兩支各自形成禁止點，不推定雙路支撐。
- 有效人工選擇覆寫該柱的自動最近結果，並解除該柱的雙候選歧義警告；其他未解問題照常保留。
- 人工決策須在 Review 重建與同來源 Pause／Resume 後仍有效；來源或幾何不再符合時不得靜默沿用。

## 現況與目標

「禁止點」指中間柱在一支支撐軸線上的 station；Support material joint 必須避開該 station 左右各 830 mm。「關聯」只表示哪支支撐要避讓該柱，不表示兩支共用材料排列。

| 面向 | Before｜現況 | After｜目標 |
| --- | --- | --- |
| 模糊關聯 | 有效候選距離差 `<= 25 mm` 時警告，但仍選最近一支 | 警告案例可在「修改工具」由人選擇一支或兩支 |
| 操作入口 | 警告頁沒有點開修補功能 | 「修改工具」新增獨立的中間柱關聯修補入口 |
| 工程結果 | 非雙路情況只有最近 Strut 取得 Column station | 人工單選覆寫自動最近結果；雙選時每支被選 Strut 各自取得 station 與禁止點 |
| 警告狀態 | 該柱的雙候選距離歧義持續列為未處理警告 | 有效人工決策後只解除該柱的歧義；撤銷後依目前幾何恢復警告 |
| Review 重建 | 關聯衍生值整批重算，直接改值會消失 | 保存人工決策並以當前有效幾何重建衍生值 |

## 主要流程

```text
DXF Review 產生「中間柱同時接近兩支支撐」警告
  → 修改工具列出可修補的柱
  → 選柱，預覽兩支候選及距離／各自 station
  → 人工選一支或兩支並套用
  → 覆寫該柱自動最近關聯，重建 ComponentAssociation、ColumnPositions、AssociatedColumnIDs
  → 解除已處理的柱距離歧義，其他問題保留
  → Review 重算／同來源續作時驗證決策並重新投影
```

## 不變事項

- 未人工處理時維持既有最近支撐結果與警告，不對全部中間柱自動共享。
- 不以柱接近兩支支撐建立、接受或繞過 `SharedLayoutGroup`；不變更雙路候選資格及其既有共享規則。
- Column station 的 `830 mm` 禁止寬度、既有關聯容差與歧義差值、Support Solver、Project rows schema 均不改。
- 暫定雙路候選不因本修補取得任何雙路正式效果；人工柱關聯屬另一項明確的 Review 決策。
- 人工決策只解除它所處理的 Column 雙候選歧義；Waler、雙路支撐、source identity 與其他問題維持原判定。

## Why

現行最近距離選擇無法表達一根柱實際影響兩側不同支撐的情況。C25 的兩個距離只差約 3 mm，警告已指出歧義，但使用者無法把工程判斷轉成兩支各自的禁止點。

## What Changes

- 為有明確兩支候選的中間柱歧義警告提供專用修補清單、幾何預覽與人工採用操作。
- 保存選中的 Column-to-Strut 關係；重建時重新計算各支撐自己的 station 與衍生禁止點。
- 人工單選不疊加原自動最近關聯；有效採用後移除該柱未解決的距離歧義警告，可保留「已人工判定」資訊。
- 對取消、過期預覽、幾何／來源變更、暫停續作提供明確保留或失效語意。
- 加入 C25／S20／S35 與一般合成案例的關聯、Review、UI、持久化回歸測試。

### In Scope

- DXF Review 中間柱歧義關聯修補及其診斷解除、預覽、採用與撤銷。
- 同來源 Review 重建、Pause／Resume 與完成匯入後的 Strut row 禁止點結果。
- 僅對柱與兩支有效候選的指定案例生效；一般自動關聯仍沿用既有策略。

### Out of Scope

- 將警告頁改成可點擊修補入口，或開放任意 Column／Strut 自由連線。
- 變更中間柱／支撐幾何辨識、雙路支撐 eligibility、Waler 身分、Solver hard constraint 或搜尋策略。
- 將來源不同的 compatible recovery 自動視為同一人工關聯，或新增 Project persistence schema。

## Capabilities

### New Capabilities

- `dxf-column-association-repair`: 定義警告案例的人工關聯修補、禁止點效果、Review 重建及安全保存。

### Modified Capabilities

- 無；`support-adjacency`、`paused-dxf-review-source-relink` 與進行中的雙路候選 change 保持既有規則。

## Impact

- 主要涉及 `dxf_import/candidate_points.py`、`models.py`、`review_workflow.py`、`dialog.py` 與 Review decision serialization／replay；測試集中於 DXF association、Review workflow／UI、Pause／Resume 與 Y29 importer regression。
- 沿用 DXF 子系統的 Presentation → Workflow → pure association operation 方向。實作完成後若長期 Review 行為確實改變，更新 `docs/WORKFLOW.md`；不預期改 Architecture、Domain、Solver 或 Project schema。

## 尚未決定的事項

- 修補清單在「修改工具」中採內嵌列表或獨立視窗屬畫面實作選擇；均須提供兩支候選及採用前預覽。
- 若實作發現既有 Review state 無法在不更動 Project schema 的情況下保存決策，需先回報並重新評估保存方案；不得只修改衍生欄位充當持久化。
