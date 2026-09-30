# Tasks

## 實作前閱讀

- **Task group 1**：閱讀 `proposal.md` 的「不變事項」、`design.md` D1／D2／D5，以及 spec「圍令工程資料須顯示直接連接構件」的 identity domain、CornerBrace 完整性、候選排除、去重與順序 scenarios。
- **Task group 2**：閱讀 `design.md` D3／D4、spec 的空集合與非圍令 scenarios，並重新檢查 `dxf_import/dialog.py` 的 `_engineering_data_rows()` 與既有 panel refresh flow。
- **Task group 3**：閱讀 `design.md` D6 與 spec「顯示不得建立第二份關聯資料」，確認 model、Project、persistence、export 與 Solver contract 不得擴張。
- **Task group 4**：回讀全部 delta spec scenarios、`proposal.md` Out of Scope 與 `design.md` Risks，確認驗證未漏掉候選排除、permutation invariance 及非 Waler regression。

## 1. 正式關聯摘要

- [x] 1.1 在開始實作前確認 `Strut.from_waler`／`to_waler`、`Brace.from_waler`／`to_waler`、formal `CornerBraceConnection.waler_id` 與 selected formal `Waler.id` 皆使用同一 Waler member identity domain，且 adopted formal CornerBrace connection 的 authoritative collection 仍為 `corner_brace_connections`；以 code inspection 與既有 tests 證明，若任一 contract 不相容則停止，不得猜測 mapping。
- [x] 1.2 先加入 Waler 正式 identity 與顯示／Treeview identity 分離測試，再在 DXF Review／Presentation 邊界新增 pure read-only relation-summary helper；helper 必須只以 selected formal `Waler.id` 和 formal connection identities exact-match，並驗證 Treeview item ID、label、source handle、collection index 與 format 後值不參與。
- [x] 1.3 擴充 rebuild／permutation tests：即使 rebuild 後 Treeview／顯示 ID 或 member／connection collection 順序改變，只要正式 identity 關係等價，摘要仍相同並維持 deterministic member-ID 排序；同一構件雙端或多筆正式 connection 只顯示一次。
- [x] 1.4 加入 CornerBrace 完整性 tests，驗證只有目前 staged result 中正式 CornerBrace member 與 formal adopted connection 同時存在、且 Waler identity exact-match 時才顯示；orphan／stale connection、已排除 member 或沒有正式 member 的 connection 一律不顯示。
- [x] 1.5 加入非正式狀態排除 tests，證明 body hypothesis、`BodyRelationshipAssessment`、unresolved body／relationship、repair candidate、Preview temporary selection 與純幾何鄰近不會進入摘要；Presentation 不得解析 diagnostic message 或自行修復／重新指派 connection。
- [x] 1.6 對 helper 做完整不可變性測試，保存呼叫前後 staged `DXFImportResult`、Waler、Strut、Brace、CornerBrace 與 connection models，驗證值與 object graph 均未被修改，且 helper 只回傳 immutable ID sequences。

## 2. 圍令工程資料顯示

- [x] 2.1 在 `bracing_optimizer/presentation/field_labels.py` 新增三個 stable internal display keys 的中文標籤，並擴充 `tests/test_field_labels.py` 驗證「直接連接支撐」、「直接連接斜撐」、「直接連接角撐」映射正確且不改變既有 labels。
- [x] 2.2 在 `dxf_import/dialog.py` 的 Waler engineering-data row 組裝接入同一 relation-summary helper，於既有 Waler fields 之後、構件長度之前固定加入三列；以 `tests/test_dxf_review_layout.py` 驗證非空類別使用 `、` 串接、空集合顯示 `—`、欄位順序符合 design D3。
- [x] 2.3 擴充 `tests/test_dxf_review_layout.py`，驗證 Strut、Brace、CornerBrace、Column、Beam 等非 Waler 構件不會新增三個欄位，且既有寬度、Column association、Beam crossing 與 Strut engineering-data tests 仍通過。
- [x] 2.4 加入 refresh projection 測試：替換或 rebuild 目前 staged result 的正式 connection、Treeview item ID 與 collection order 後重新建立 engineering rows，顯示須只反映新 result 的正式 Waler identities 且不得沿用舊 UI identity／反向清單；同時驗證 result、Waler／members／connections 與 `to_project_row()` 呼叫前後完全不變。

## 3. Contract 與邊界驗證

- [x] 3.1 檢查實作 diff，確認未修改 `Waler.to_project_row()`、`DXFImportResult` serialization、Project mapping/schema、save/load、Excel／DXF export 或 Solver input；以既有 persistence／mapping tests 或靜態 contract assertions 驗證沒有新增反向關聯資料欄位。
- [x] 3.2 執行 focused tests `python -m unittest tests.test_field_labels tests.test_dxf_review_layout`（依專案實際 test runner 調整等價命令），確認所有新增顯示與既有工程資料行為通過。

## 4. Regression 與 OpenSpec 驗證

- [x] 4.1 執行與正式關聯來源直接相關的 DXF Review、Waler contact adjustment／face、CornerBrace connection／repair focused regressions；確認本 change 沒有改變 recognition、repair、validation、confirmation 或 staged mutation 行為。
- [x] 4.2 執行專案完整測試套件或依當時環境可執行的最大相關 regression 範圍，記錄任何既有或環境限制，並確認沒有與本 change 相關的失敗。
- [x] 4.3 逐項對照 `proposal.md`、delta spec、`design.md` 與本 tasks，執行 strict OpenSpec validation，確認所有 scenarios 有實作／測試證據、沒有超出 scope，且 change artifacts 與 implementation coherent。
