# Tasks

## 實作前閱讀

- **Group 1 開始前**：閱讀 `proposal.md`「不變事項」、`design.md` Decision 1／4，以及 `specs/dxf-review-preview-error-selection/spec.md`「圖面可選取未解析錯誤來源」。重點是 index freshness、以實際繪製定義可見，以及以 `ReviewItem.key` 去重。
- **Group 2 開始前**：閱讀 `design.md` Decision 2／3／5，以及 spec「重疊歧義與既有操作優先序」、「錯誤來源選取不得改變正式資料」。重點是重用既有 unresolved selection path、抑制 tree event 重入，且不改變 endpoint／candidate／formal member 優先序。
- **Group 3 開始前**：閱讀 `design.md`「Testing Strategy」與「State and Contract Truth」。重點是驗證 tree、detail、focus 同步及 Workflow／Project／dirty state 無副作用。
- **Group 4 開始前**：回讀 proposal 的 In Scope／Out of Scope、全部 spec scenarios 與 design decisions；確認實作沒有擴張到 popup、warning selection、recognition、repair、persistence 或 Solver。
- **可先跳過**：Solver、材料、Project persistence 與其他 DXF recognition specs；除非實作意外觸碰這些模組，否則不需閱讀或修改。

## 1. 錯誤來源命中基礎

- [x] 1.1 在 DXF Preview 的純 Presentation hit-test 層新增「容差內全部線段命中」能力，回傳結果以 distance 與 identity 穩定排序；加入 pixel tolerance、無命中、輸入順序改變結果不變的單元測試並確認通過。（對應 D4／「重疊歧義與既有操作優先序」）
- [x] 1.2 在 `dxf_import/dialog.py` 建立 UI-only unresolved error hit records與 freshness stamp，記錄 viewport transform、monotonic render generation、source visibility、ReviewItems 及 active result signatures；在 pan／zoom／fit、visibility、focus、ReviewItems、active result 或 full render generation 改變時失效，並確保 click 在 stale 時以目前 render inputs 重建或安全 no-op。測試平移與縮放後立即點擊只命中新畫面位置、舊位置不命中，且 stale index 不參與 click／hover。（對應 D1／viewport 同步 Scenario）
- [x] 1.3 以目前 unresolved `ReviewItem.key` 建立 source-handle lookup，只索引最高嚴重度為 `error`／`critical` 且實際繪製於目前畫面的來源；index 與 renderer 共用相同 visibility decision。測試同一 ReviewItem 多 handles／多 segments 去重、warning／info／recognized／excluded／未繪製 source 不命中，以及 source layer hidden 時由 `focus_handles` 強制繪製的來源仍可命中。（對應 D1、D2、D4／唯一命中、實際繪製可見性 scenarios）

## 2. 圖面選取與同步

- [x] 2.1 擴充既有 unresolved ReviewItem selection path，使 canvas 觸發可設定 `selected_review_item_key`、完整 `focus_handles`、清除 formal `SelectionState`、更新 detail panel，並只透過既有 tree synchronizer 選取及捲動至相同 ReviewItem；利用 synchronizer guard 讓 `<<TreeviewSelect>>` 略過 programmatic selection。測試一次 canvas unique-hit 只執行一次 selection flow、detail 與 render 各更新一次，且不建立 member／candidate state。（對應 D2／圖面選取同步清單 Scenario）
- [x] 2.2 在 canvas click flow 的正式 member 處理之後加入 unresolved error hit handling：零 key no-op、唯一 key 選取、多 key 保留既有 selection 並顯示清單引導提示；加入 endpoint、candidate、pick-mode invalid guard、formal member 優先，以及多 ReviewItems 歧義不改 selection 的 regression tests，並確認任何延後的 programmatic tree event 都不會覆蓋歧義提示。（對應 D3、D4／「重疊歧義與既有操作優先序」）
- [x] 2.3 在 canvas motion flow 中只於既有 hover targets 皆未命中且目前 index 唯一命中 unresolved error 時顯示可互動游標，移出、歧義、未實際繪製、stale index 或非錯誤來源時維持既有 cursor；加入 hover 不改 ReviewItem／member selection且不使用舊 viewport 座標的測試。（對應 D1、D3、D5／Hover scenarios）

## 3. 無副作用與整合驗證

- [x] 3.1 新增 selection safety 測試，快照比較成功點選與歧義點擊前後的 Workflow result、ReviewItems、members、messages、source geometry、confirmation／exclusion／repair state、Project／Solver projection及 dirty state，確認只有允許的 Presentation state 或提示改變。（對應「錯誤來源選取不得改變正式資料」）
- [x] 3.2 執行 `tests/test_dxf_review_items.py` 與受影響的 Preview controller／renderer focused tests；若修改共用 CAD hit helper，再執行 `tests/test_cad_view_interaction.py`，修正本 change 引入的回歸並記錄通過結果。（驗證 D1–D5）
- [x] 3.3 使用含正式 error member、唯一 unresolved error source、同一 ReviewItem 多段幾何及兩個不同 ReviewItems 重疊的 DXF 手動驗證；確認 cursor、點選優先序、tree、detail、藍色 focus、歧義提示及 source layer visibility 符合 spec，並記錄可重現步驟與結果。（整合驗證全部使用者可見 scenarios）

## 4. 最終驗證與文件一致性

- [x] 4.1 檢查實際 diff 只涵蓋 DXF Presentation、相關測試與本 change artifacts，確認沒有 recognition、Domain、Solver、Project schema、persistence 或無關 cleanup；若實作沒有改變 Architecture／Workflow truth，不修改長期文件並在驗證結果中明確記錄。（驗證 proposal In Scope／Out of Scope）
- [x] 4.2 執行受影響的完整 DXF Review regression suite 與既有 architecture boundary tests，確認所有測試通過且沒有把 UI dependency 導入 Workflow／recognition。（Final regression test）
- [x] 4.3 執行 `openspec validate select-error-components-from-preview --strict`，再依 `openspec-verify-change` workflow 對照 proposal、design、spec 與 tasks 驗證 implementation；所有 requirement 與 scenario 有證據且沒有 scope drift 後才標記完成。（OpenSpec implementation verification）

## Implementation Verification Record

- 2026-09-30：以實際 `670-CO-Y05-FW-圖紙 - 005 - Y05站 安全支撐系統 第一層支撐平面圖.dxf` 匯入結果確認有 258 個正式構件、37 個 unresolved error ReviewItems 與 2 個 formal error ReviewItems，可重現正式構件與未解析錯誤來源並存情境。
- 2026-09-30：以 deterministic DXF Preview fixtures 驗證唯一命中、多 handles／segments 去重、兩個 ReviewItems 重疊、pan／zoom freshness、cursor、tree／detail 單次同步、藍色 focus、來源圖層隱藏與既有操作優先序；focused tests 28 項通過。
- 2026-09-30：DXF Review regression 179 項通過；CAD interaction、DXF input 與 architecture boundary regression 103 項通過。
