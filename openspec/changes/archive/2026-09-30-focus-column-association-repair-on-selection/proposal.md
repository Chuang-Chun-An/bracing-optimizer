# Proposal

## 閱讀導航

### P0｜現在必讀

- 本文件「快速摘要」「現況與目標」「主要流程」：先確認使用者可見行為。
- `openspec/specs/dxf-column-association-repair/spec.md` 的「只讓明確的雙候選中間柱進入修補」：了解既有候選資格。
- 本 change 的 `specs/dxf-column-association-repair/spec.md`：確認選取門檻與單一柱顯示的新契約。

### P1｜實作前閱讀

- 本 change 的 `design.md`「D1～D5」：確認 Presentation 如何取得目前選取的中間柱、同步按鈕、建立單一柱 Preview，並保留不存在柱的失效決策問題。
- `docs/ARCHITECTURE.md` 的「State Ownership」及 `docs/WORKFLOW.md` 的 DXF Review／中間柱關聯修補段落：維持 UI selection 與正式 Review truth 的責任邊界。
- `tests/test_dxf_review_layout.py` 的 column repair 測試：了解現有入口與 subject list 行為。

### P2｜需要時再讀

- 若修改提交或撤銷流程，再讀主 spec 的「採用與撤銷必須可預覽且原子提交」。
- 本次可先跳過 Support Solver、雙路支撐資格、角撐修補、Waler contact-face 與 persistence specs；它們不在本 change 範圍。

## 快速摘要

- 現行工具只要全案存在任一可修補柱就會出現，開啟後一次列出全部中間柱，容易讓操作脫離目前選取對象。
- 改為只有目前選取項目是正式中間柱時，才顯示並允許使用「中間柱關聯修補」；每次清單、圖面或清除選取都立即同步入口。
- 開啟後直接規劃並顯示該中間柱，不再提供全案中間柱清單或讓使用者在視窗內切換柱。
- 已修柱仍可開啟查看目前決策並撤銷；`requires_review` 柱可開啟查看 Workflow 提供的失效原因。
- 選到斜撐、支撐、圍令或其他非中間柱項目時，工具不可使用；工程候選資格、人工單選／雙選、提交與撤銷規則不變。

## 現況與目標

| | Before | After |
|---|---|---|
| 入口條件 | 全案只要存在任一可修補柱，工具便可能出現 | 目前必須選取一支中間柱，工具才顯示並可使用 |
| 開啟內容 | 顯示全部待修／已修中間柱清單，再選一筆 | 直接顯示目前選取中間柱的修補內容 |
| 已修／失效決策 | 依全案清單找到已修或需重新檢查項目 | 正式柱仍存在時由選取柱開啟；柱已不存在時保留在既有 Review 問題清單 |
| 選取同步 | 入口可由全案其他柱決定 | 清單選取、圖面點選與清除選取均立即重評入口 |
| 非柱選取 | 選斜撐、支撐或圍令時仍可能看到入口 | 非中間柱選取不顯示／不可啟動此工具 |
| 工程規則 | Workflow 判定候選資格並處理提交 | 完全沿用既有 Workflow 判定與交易規則 |

## 主要流程

```text
使用者在 DXF Review 選取構件
  → 是中間柱：顯示「中間柱關聯修補」
      → 點擊工具
      → 只規劃目前中間柱
      → 待修：顯示兩支候選與第一支／第二支／兩支選項
      → 已修：顯示目前決策並允許撤銷
      → 需重新檢查：顯示 Workflow／Review problem 提供的失效原因
  → 不是中間柱：不提供此工具
  → 決策對應柱已不存在：不提供工具，但既有 Review 問題清單保留失效決策
```

## 不變事項

- 不改變哪些中間柱符合修補資格，也不放寬雙候選、有限軸線、距離差或來源身分規則。
- 不改變人工選擇如何覆寫自動關聯、Column station、禁止點、警告解除、提交、撤銷及 Resume 行為。
- 不改變 Strut、Brace、Waler、Column recognition、雙路支撐、Project schema 或 Solver。

## Why

目前修補工具以全案清單為入口，與使用者正在檢視的構件脫節，並會在選取斜撐、支撐或圍令時提供不相關工具。將入口綁定目前選取的中間柱，可降低誤修其他柱的風險，讓「選取對象就是修補對象」成為一致且可預期的操作。

## What Changes

- 「中間柱關聯修補」只在目前唯一選取的 Review 構件角色為 `column` 時可見且可啟動。
- 開啟工具時只向 Workflow 規劃目前選取的 Column ID；不再掃描所有柱形成 subject list。
- 修補視窗移除待修／已修中間柱清單，直接呈現該柱狀態、候選支撐、距離、station 與 Preview overlay。
- 有效已修柱仍可開啟、查看目前選擇並撤銷；`requires_review` 柱仍可開啟並顯示 authoritative 失效原因。
- 對應正式柱已不存在的失效決策不成為工具 subject，但必須繼續出現在既有 Review 問題清單。
- 每次清單選取、圖面點選與清除選取都重新評估入口；已開啟 Preview 的 subject 不隨後續 selection 改變。
- 若選取狀態已失效、選取對象不是中間柱，或該柱沒有合法修補 plan，工具拒絕啟動並維持正式 Review state。
- 斜撐、支撐、圍令及其他非中間柱構件不顯示此工具，也不能成為其修補 subject。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-column-association-repair`：將修補入口與 Preview subject 改為目前選取的單一中間柱，排除全案清單與非柱選取。

## In Scope

- DXF Review 修改工具的顯示／啟用條件。
- 從目前 Presentation selection 解析唯一 Column subject。
- 單一柱修補視窗、預覽與既有套用／撤銷操作的串接。
- 已修／`requires_review` 柱的查看、撤銷或失效原因顯示，以及 orphan decision 的問題清單可見性。
- 清單、圖面與清除選取路徑的入口同步。
- 對應的 Presentation tests 與既有 column repair workflow regression tests。

## Out of Scope

- 修改中間柱關聯候選、距離容差、station 或禁止點工程算法。
- 修改斜撐、支撐、圍令或角撐的編輯工具。
- 修改 Workflow transaction、Review persistence、Project schema、Domain 或 Solver。
- 順帶重構 DXF Review 的其他按鈕、selection controller 或對話框。

## Impact

- 主要影響 `dxf_import/dialog.py` 的工具可見性、目前中間柱解析與修補視窗建立。
- 主要測試位於 `tests/test_dxf_review_layout.py`；`tests/test_double_support.py` 用於確認既有 Workflow 行為未回歸。
- 不新增外部依賴或資料 migration。
- Architecture、Domain 與 Solver truth 不變；`docs/WORKFLOW.md` 的中間柱關聯修補入口描述在實作完成後需更新為選取導向流程。

## 尚未決定的事項

- 無會改變需求範圍的未決事項。視覺上的「隱藏」或「disabled」以專案現有修改工具慣例決定，但無論呈現方式，非中間柱選取皆不得啟動工具。
