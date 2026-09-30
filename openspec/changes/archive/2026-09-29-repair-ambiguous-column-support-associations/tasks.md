# Tasks

## 實作前閱讀

- Group 1：讀 `proposal.md`「現況與目標」「不變事項」、`design.md` Decision 1、spec「只讓明確的雙候選中間柱進入修補」；檢查 `candidate_points.py` 與 `tests/test_double_support.py`。
- Group 2：讀 `design.md` Decision 2、spec「人工選擇決定各支撐的禁止點」「有效人工決策解除原關聯歧義」「修補不得改變一般關聯與雙路資格」；檢查 `models.py`、`candidate_points.py`、Project row conversion。
- Group 3：讀 `design.md` Decision 2、3、spec「有效人工決策解除原關聯歧義」「採用與撤銷必須可預覽且原子提交」；檢查 `review_workflow.py` 的 staged mutation、snapshot 與 completion status。
- Group 4：讀 `design.md` Decision 5、spec「只讓明確的雙候選中間柱進入修補」「採用與撤銷必須可預覽且原子提交」；檢查 `dialog.py` 修改工具與 UI tests。
- Group 5：讀 `design.md` Decision 4、spec「人工決策須安全重建與續作」；檢查 `source_exclusion.py`、Review state serialization、`review_recovery_planner.py` 及 paused Review tests。
- Group 6：回讀 proposal scope、全部相關 spec scenarios 與 `design.md` Architecture Alignment；檢查 `docs/WORKFLOW.md` 對應 Review lifecycle。可先跳過 Solver 搜尋與角撐模板細節。

## 1. 固定現況並抽取候選事實

- [x] 1.1 在 `tests/test_double_support.py` 加入 Y29 C25 baseline characterization：確認 S20／S35 的距離、現有最近關聯與警告，執行該 focused test；對應「只讓明確的雙候選中間柱進入修補」。
- [x] 1.2 在 `dxf_import/candidate_points.py` 抽取共用 WCS Column option 計算，讓現有自動關聯結果不變；以最近選擇、容差等號、有限 station 與反向軸 tests 通過驗證；對應 Decision 1。
- [x] 1.3 建立兩候選 eligibility／多候選拒絕的 pure plan，排除 accepted 雙路共享與同碼的多群組 warning；以兩候選、第三支、正式雙路及不同輸入順序測試驗證；對應「只讓明確的雙候選中間柱進入修補」。

## 2. 讓人工選擇形成各支撐的禁止點

- [x] 2.1 在 `dxf_import/models.py` 與 association operation 加入 source-bound `ColumnAssociationDecision`，保持 `Column.associated_strut_id` 單值相容；以 source identity 一對一與無決策舊路徑測試驗證；對應 Decision 2。
- [x] 2.2 讓 `rebuild_component_associations()` 接收／消費已驗證決策，以該 Column 的人工選擇完整覆寫自動最近 assignment，並一次重建 `ComponentAssociation`、`associated_columns`、`column_positions` 與診斷；focused test 固定自動最近 S20、人工只選 S35 時 S35 有 C25 station、S20 無 C25 station 且恰有一筆 active association，另驗證反向 Strut 與重複 rebuild idempotence；對應「人工單選覆寫自動最近支撐」。
- [x] 2.3 驗證 `DXFImportResult.to_project_rows()` 對人工雙選 S20／S35 產生兩支各依自身方向計算的 C25 `AssociatedColumnIDs`／`ColumnPositions`，且不建立 `SharedLayoutGroup`、不讓 `pending_waler` 候選生效；以 Y29 C25 與合成 regression 驗證；對應「人工選擇決定各支撐的禁止點」「修補不得改變一般關聯與雙路資格」。
- [x] 2.4 在 `candidate_points.py` 的同一關聯重建路徑只移除有效人工決策所處理之 Column 距離歧義 warning，可保留 info provenance；focused test 驗證該 warning 不再列為未解決、無關 Waler／雙路／source identity problems 仍在，並驗證失效決策不誤標已解決；對應「有效人工決策解除原關聯歧義」。

## 3. Review 預覽、採用與撤銷

- [x] 3.1 在 `dxf_import/review_workflow.py` 提供 side-effect-free repair plan 與 snapshot 資料，顯示兩支距離、station、目前人工狀態；以 preview 不改 `world_result`／revision 的測試驗證；對應 Decision 3。
- [x] 3.2 實作 revision／fingerprint／source identity／當前 eligibility 重驗後的 staged commit；focused test 驗證成功採用後原 C25 距離歧義 warning 不再出現在 Review 完成前未解決警告計數、info provenance 可見且其他 blocking problems 不變，另驗證 stale revision、排除與幾何改動時完整 rollback；對應「有效人工決策解除原關聯歧義」「採用與撤銷必須可預覽且原子提交」。
- [x] 3.3 實作已修決策的撤銷與自動最近關聯恢復，並將已修、待修、需重新檢查分開顯示；focused test 驗證撤銷後依目前幾何恢復 nearest，若歧義仍在則 warning 恢復、人工 provenance 與人工 station 消失；另驗證決策失效時舊人工 station 不生效、顯示 `requires_review` 且不誤標已解決；對應「撤銷後恢復自動歧義狀態」「人工決策失效不得誤標已解決」。

## 4. 修改工具介面

- [x] 4.1 在 `dxf_import/dialog.py` 的 STEP4「修改工具」加入「中間柱關聯修補」入口與待修／已修清單；以 `tests/test_dxf_review_layout.py` 或對應 UI test 驗證入口存在、警告頁無新增點擊行為；對應 Decision 5。
- [x] 4.2 加入兩支候選的工程位置、距離、station 與畫布 overlay 預覽，以及第一支／第二支／兩支、套用／撤銷／取消操作；以 UI workflow test 驗證選項切換只改 draft、取消無副作用、過期預覽提示；對應「採用與撤銷必須可預覽且原子提交」。

## 5. 保存、重建與來源恢復

- [x] 5.1 在 Review state version 2 加入 optional `column_association_decisions` 讀寫，確認 Project loader 對此 Review 子欄位的相容性；以舊 payload 缺欄位、same-fingerprint Pause／Resume round trip 測試驗證；對應 Decision 4。
- [x] 5.2 接入重新辨識、端點修改、source exclusion／restore、座標切換及雙路決策變更後的決策重驗／關聯重建；以有效重播、反向軸 station 重算、失效顯示與無舊禁止點 tests 驗證；對應「人工決策須安全重建與續作」。
- [x] 5.3 在 compatible recovery planner 分類人工柱關聯：來源內容不同時僅 `requires_review` 或 `disabled`，不套用效果；以 exact relink 保留、changed-content 不轉移、cancel 保留原 Review 的 focused tests 驗證；對應 Decision 4。

## 6. 文件與整體驗證

- [x] 6.1 實作完成後更新 `docs/WORKFLOW.md` 的 DXF Review 修補、重建與續作事實；以文件對照本 change spec 且不宣稱 Solver／Domain 規則改動驗證；對應 proposal Impact。
- [x] 6.2 執行 focused Y29、double-support、DXF Review／recovery、Project row 與 DXF boundary regressions；核對 C25 單選覆寫與雙選禁止點、人工採用後局部解除警告、撤銷後恢復警告、失效 `requires_review`、一般最近行為及雙路隔離均通過；對應全部主要 scenarios。
- [x] 6.3 執行 `openspec validate repair-ambiguous-column-support-associations --strict` 與 implementation 對照檢查，核對 tasks、spec、design、proposal scope 一致且無不相關修改；保存驗證結果供 Review。
