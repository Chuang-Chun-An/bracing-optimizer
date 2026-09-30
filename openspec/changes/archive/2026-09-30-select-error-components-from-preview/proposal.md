# Proposal

## 閱讀導航

- **P0｜現在必讀**：本文件的「快速摘要」、「現況與目標」、「主要流程」、「In Scope／Out of Scope」；先確認使用者可見行為與邊界。
- **P0｜現在必讀**：本 change 的 `specs/dxf-review-preview-error-selection/spec.md`「圖面選取未解析錯誤來源」Requirement；定義可選取對象、歧義處理與選取結果。
- **P1｜實作前閱讀**：`design.md`「決策對照」與「Selection flow」；確認既有正式構件、候選點及端點選取優先序不被改變。
- **P1｜實作前閱讀**：`docs/ARCHITECTURE.md`「3.6 DXF Subsystem」、「6. State Ownership」及 `docs/WORKFLOW.md`「DXF Import and Review」；確認 Preview selection 仍由 Presentation 擁有。
- **P2｜需要時再讀**：`dxf_import/dialog.py` 的 Preview 繪製、hit-test、`_select_unresolved_review_item()`，以及 `tests/test_dxf_review_items.py`。可先跳過 Solver、材料、Project persistence、辨識演算法與其他 DXF recognition specs，這些都不在本 change 範圍。

## 快速摘要

- DXF Review 已能在圖面顯示紅色的未解析錯誤來源，但目前沒有為這些來源建立圖面點選入口，只能從構件或問題清單定位。
- 本 change 讓使用者以滑鼠左鍵直接選取圖面上可見的 error／critical 未解析來源，並同步既有 ReviewItem、明細與藍色聚焦效果。
- 同一次點擊只對應一個 ReviewItem 時才選取；多個不同錯誤項目重疊時不任意決定，維持目前選取並提示改由清單選擇。
- Hit index 與目前 viewport／render generation 綁定；平移、縮放、來源可見性、ReviewItems 或 active result 改變後，不得使用舊螢幕座標。
- 候選點、待修改端點與正式構件的既有圖面操作優先序不變。
- 此功能只改變 Presentation 的選取體驗，不改變辨識、驗證、工程幾何、Review truth、Project、Solver 或持久化資料。

## 現況與目標

「未解析錯誤來源」是指驗證訊息具有 source handle，但系統尚未產生正式 member ID 的 error／critical ReviewItem；它不是正式工程構件。

| | Before | After |
| --- | --- | --- |
| 圖面呈現 | 未解析錯誤來源以紅色粗線顯示 | 維持紅色顯示，並成為可點選目標 |
| 選取入口 | 只能從構件清單或問題清單選取 | 清單仍可使用，也可直接點圖面上的紅色來源 |
| 選取結果 | 清單選取後聚焦來源並更新明細 | 圖面點選重用相同 ReviewItem 選取結果 |
| 重疊歧義 | 無圖面選取行為 | 多個不同 ReviewItem 同時命中時不猜測，提示使用清單 |
| 工程資料 | 不因選取而改變 | 維持不變 |

## 主要流程

1. 使用者在 DXF Review 預覽圖以左鍵點擊可見幾何。
2. 系統先保留既有候選點、待修改端點與正式構件 hit-test 行為。
3. 若既有目標皆未命中，系統先確認 error hit index 與目前 viewport、render generation、來源可見性、ReviewItems 及 active result 一致；失效時先重建，不得沿用舊螢幕座標。
4. 系統檢查點擊容差內目前實際繪製的 error／critical 未解析來源，並依 source handle 對應至目前 ReviewItem。因目前選取而強制繪製的 `focus_handles` 即使來源圖層隱藏，仍屬於可見且可命中的來源。
5. 唯一 ReviewItem 命中時，系統選取該項目、以防重入的方式同步左側清單與右側問題明細，並以既有藍色效果聚焦來源；多個不同 ReviewItem 命中時維持現況並顯示歧義提示。
6. 整個流程只更新 Preview／selection UI state，不提交任何 Review 或工程資料變更。

## 不變事項

- 正式構件、候選點、起終點修改、平移及縮放的操作契約不變。
- 未解析來源不會因圖面選取而成為正式 member，也不會取得 member ID 或候選點編輯能力。
- Recognition、validation、confirmation、source exclusion、repair、Project rows、Solver inputs 與 persisted review state 不變。
- 問題清單與構件清單仍是重疊歧義及非可見來源的完整選取入口。

## Why

DXF Review 已將未解析錯誤來源醒目地畫在預覽圖上，但使用者看到紅色幾何後仍必須回到清單尋找對應項目，定位流程不連續且容易選錯。讓圖面與既有 ReviewItem 選取流程互通，可降低大型圖面的錯誤檢查成本，同時保留未解析來源不是正式構件的工程邊界。

## What Changes

- 為 Preview 中可見的 error／critical 未解析來源建立 source-handle hit-test 索引。
- Hit index 記錄建立時的 viewport transform 與 render generation，並在 viewport、來源可見性、ReviewItems 或 active result 改變時失效；點擊不得使用 stale index。
- 唯一命中時，使用既有 unresolved ReviewItem 選取流程同步構件清單、問題明細與來源聚焦。
- 圖面觸發的程式化 tree synchronization 必須抑制對應的 `<<TreeviewSelect>>` 重入，確保一次點擊只執行一次選取流程。
- 為可點選錯誤來源提供游標或等價的可互動提示。
- 多個不同 ReviewItem 同時命中時不任意選取，改以狀態提示引導使用清單。
- 保留既有端點、候選點與正式構件的點選優先序及行為。

## In Scope

- DXF Review Preview 的 error／critical 未解析來源點選與 hover 可互動提示。
- viewport／render generation 同步、index invalidation 與 stale-index 防護。
- source handle 到目前 unresolved ReviewItem 的唯讀對應與同一 ReviewItem 命中去重。
- 選取後以防重入方式同步既有 tree、detail panel、focus handles 與 render lifecycle。
- 唯一命中、重疊歧義、viewport 變更、實際繪製可見性、tree event 防重入、既有選取優先序及 UI-only 無副作用測試。

## Out of Scope

- 新增或放寬 DXF recognition、guided recognition 或自動修正能力。
- 讓 warning、info、已排除來源或一般背景 source geometry 全部變成可點選對象。
- 在多個重疊 ReviewItem 之間自動猜測、循環選取或新增選擇 popup。
- 修改 source exclusion、Review confirmation、repair、Project schema、Solver 或 persistence。
- 重構整個 Preview renderer、SelectionController 或 Dialog。

## Capabilities

### New Capabilities

- `dxf-review-preview-error-selection`: 定義 DXF Review 使用者從預覽圖直接選取 error／critical 未解析來源、同步既有 ReviewItem，以及安全處理重疊歧義的 Presentation 行為。

### Modified Capabilities

無。既有 `dxf-review-engineering-data-presentation` 只規範右側工程資料內容，本 change 不改變其 requirements。

## Impact

- 主要影響 `dxf_import/dialog.py` 的 source geometry hit-test、canvas click／motion 與 unresolved ReviewItem 同步流程。
- 視實作需要，可在 `dxf_import/preview.py` 增加純 Presentation 的 source hit-test index；不得把 UI selection 寫入 Workflow-owned result。
- 相關測試集中於 `tests/test_dxf_review_items.py`、Preview interaction／renderer 測試及必要的 Dialog selection regression。
- 不新增外部 dependency、公開 API、資料 schema 或 migration。
- **Architecture**：不改變；Selection 與 viewport 仍由 Presentation 擁有。
- **Domain／Solver**：不改變；不新增 Engineering Hard Constraint、Solver Preference 或 heuristic。
- **Workflow truth**：正式 Review state 不改變；只新增從圖面觸發既有 unresolved ReviewItem selection 的 UI 路徑。

## 尚未決定事項與重新評估條件

目前決定以「歧義時提示使用清單」控制範圍，不新增 popup 或循環選取。若實際圖面驗證顯示多個 unresolved ReviewItem 長距離完全重疊、導致主要錯誤無法由圖面選取，應另行評估可見候選選單；不得在本 change 實作時自行改成任選最近或依繪製順序決定。
