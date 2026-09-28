# 實作任務

## 1. 根來源契約與現況特徵測試

- [x] 1.1 為一般 INSERT、具有完整外框的 BIM Strut，以及類似 Y05 的 fragmented Strut Block 建立精簡的 synthetic DXF fixture builders；先只加入目前 root grouping／provenance 的通過中現況特徵 assertions，並確認改變 recognition behavior 前 `tests/test_dxf_bim_block_recognition.py` 通過。
- [x] 1.2 在 `dxf_import/recognition.py`／`dxf_import/importer.py` 擴充內部 geometry-group source scope，加入明確的 root handle 與 root entity type；確認 `tests/test_dxf_ocs_wcs.py` 仍證明 nested transforms 只會正確套用一次並產生 WCS geometry。
- [x] 1.3 加入 root-layer／child-layer integration coverage，證明 Layer 0 children 會繼承 root Strut role，而 Brace 與其他 root roles 仍使用既有路徑；確認 focused BIM recognition test module 通過。

## 2. 純類構件幾何服務

- [x] 2.1 建立 pure `dxf_import/block_member_recognition.py` input／outcome contract，包含 `not_applicable`、`recognized`、`failed` 與 `ambiguous` states；以 unit tests 驗證 contract invariants，並確認此 module 不 import Presentation／Review workflow code。
- [x] 2.2 實作不受順序影響的 primitive normalization 與 fragment extraction，涵蓋 closed POLYLINE outlines、connected LINE contours、合法 local rail pairs 與 weak single-line evidence；驗證等價的 LINE rectangle 與 POLYLINE rectangle tests 會產生等價 fragment axes。
- [x] 2.3 使用既有具名 tolerances 實作 undirected orientation clustering 與 longitudinal-support scoring；驗證反轉 endpoints、反轉 path traversal、重排 children，以及加入大量 transverse detail lines，都不會改變 dominant-axis result。
- [x] 2.4 實作 transverse center／width compatibility 與 whole-component cluster classification；驗證 unrelated geometry 回傳 `not_applicable`、一個可信 cluster 形成唯一解，而兩個相近且互相衝突的可信完整 clusters 回傳 `ambiguous`。
- [x] 2.5 從 accepted fragments 的外側 longitudinal evidence 實作 supported whole-axis reconstruction，且不設定 interior-gap cutoff；驗證具有 large gaps 的多個 aligned rectangles 會產生一條完整 axis、局部 3 m pair 不會截短有完整 evidence 支持的 12 m member，而且 axis 不會外插超過 terminal source evidence。
- [x] 2.6 實作明確的 whole-source legacy-evidence detection，使 full-span centerline／MLINE／single outline／complete rail sources 對新 service 回傳 `not_applicable`；驗證上述案例的既有 general recognition methods 與 engineering-line options 均不變。

## 2A. Task 3 前置修正與回歸保護

- [x] 2.7 依已確認的 winner-gate／reliable-runner policy，先加入 `50/50 → ambiguous`、`51/49 → ambiguous`、best `>= 0.5` 且所有可靠不等價 runners 的 delta `> 0.03 → recognized`、runner coverage `< 0.8` 不因排名觸發 ambiguity，以及 equivalent duplicate 不會遮蔽後續可靠不等價 runner 的 focused tests；再將 pure service 改為只以 `0.5` 限制 winner，並對所有可靠、不等價、delta `<= 0.03` 的 runners 執行 ambiguity comparison。不得新增 runner-up magic threshold。
- [x] 2.8 新增獨立 ordinary compound CAD Block fixture：包含多個一般繪圖用途且不足以支持單一 component-like Strut 的 primitives，不得使用 full-span outline 加 detail lines 代替；驗證 BIM path 回傳 `not_applicable`，並保留既有 general recognition outcome。
- [x] 2.9 新增 pure-service final-outcome permutation tests，涵蓋 child order、LINE start/end、closed POLYLINE traversal／起始 vertex 及等價 duplicate primitives；驗證 status、normalized whole axis、representative width 與 accepted-fragment semantics 不因等價表示改變。
- [x] 2.10 以 Y05 S2 root handle `957` 的關鍵 WCS geometry 建立穩定 regression fixture；驗證 best 約 `0.907178718`、可靠不等價 runner 約 `0.873110802`、delta 約 `0.034067916 > 0.03`，因此 pure service 維持 `recognized`，重建約 `18,900 mm`、約 `(-53379, -9450) → (-53379, 9450)` 的完整軸，並明確拒絕退回既有約 `6,978 mm`、約 `(-53379, -3488.368) → (-53379, 3489.368)` 的局部辨識。

Task 3 只有在 2.7～2.10 完成、focused tests 全部通過後才能開始。

## 3. 辨識流程整合

- [x] 3.1 在 `dxf_import/importer.py`／`dxf_import/recognition.py` 的跨 group merge 之前，加入只處理 Strut root INSERT 的 router；逐 group 驗證非空 root handle、`root_entity_type == "INSERT"` 與 `role == "strut"`，並使後續 `_merge_related_line_groups()` 排除 root INSERT groups。驗證每個 root INSERT 都獨立送入 pure service、Brace／其他 role／非 INSERT 不會呼叫它、`not_applicable` 對同一未合併 root group 呼叫既有 recognizer、`recognized` 只建立一個 candidate，而 terminal `failed`／`ambiguous` outcomes 不會落入 local parallel-pair recognition。
- [x] 3.2 將成功的 whole-block result 轉成一個既有 `_Candidate`，使用穩定的 `bim_block_whole_axis` method、root source identity、computed width，且不提供 local fragment boundary alternatives；驗證 candidate points 與 downstream Waler connection 使用完整 axis，而不是 fragment axis。
- [x] 3.3 為新的 recognition method 加入使用者可讀的繁體中文 label，但不新增 UI controls；驗證 member details 顯示該 label，同時保留 unknown-method fallback behavior。
- [x] 3.4 為 conflicting axes 與 unreliable whole extent 加入 source-aware blocking validation codes，並將其分類為 recognition problems；驗證每種情況都只產生一個以 root handle 為 identity 的 unresolved ReviewItem、不建立 formal Strut，且會阻止 import completion。
- [x] 3.5 限縮 candidate deduplication，使 BIM candidate 不會跨不同 root source keys 合併；驗證兩個不同且共線的 root INSERTs 仍保留為兩個 provenance-distinct candidates，同時既有 general outline／centerline dedup tests 仍通過。
- [x] 3.6 使用 2.10 的 Y05 S2 fixture 執行 importer-level regression；驗證正式 candidate 使用約 `18,900 mm` whole axis、recognition method 為 BIM whole-axis path，且 downstream 不再取得約 `6,978 mm` 的 local parallel-pair candidate。

## 4. WCS、來源追溯與決定性整合

- [x] 4.1 加入包含 insertion、rotation、positive／negative scale 與 child OCS geometry 的 nested INSERT integration cases；驗證 reconstructed whole axis 的 WCS 座標正確，且最外層 root handle 仍是 member／problem source identity。
- [x] 4.2 加入 importer-level deterministic permutations，涵蓋 child entity order、LINE start/end direction、POLYLINE traversal／起始 vertex 與等價 duplicate geometry；驗證等價 DXFs 產生相同的 success／fallback／ambiguity classification、normalized engineering axis 與 root provenance，並與 2.9 的 pure-service final-outcome tests 使用相同 determinism contract。
- [x] 4.3 驗證 source geometry 仍保留 original expanded underlay evidence，且 component service 不會跨 root INSERTs 合併 fragments；執行 focused BIM、WCS 與既有 DXF input test modules。

## 5. 檢核生命週期與持久化相容性

- [x] 5.1 為 recognized BIM Strut 與 unresolved BIM source 加入 source exclusion／restore tests；驗證 exclusion 會過濾 recognition、restore 會重新辨識、preview source geometry 仍可使用，而且 original DXF bytes／fingerprint 不變。
- [x] 5.2 加入 exact-root manual replay 與 confirmation invalidation tests；驗證合法人工輸入只會重播到一個 matching source、non-unique／missing recognition 會回報 needs-review，而 changed member geometry 會透過既有 signatures 移除先前 confirmation。
- [x] 5.3 加入 pause／resume 與 completed-import coverage；驗證既有 fingerprint gate 仍為 authoritative、accepted BIM Struts 使用既有 `DXFImportResult → Project rows` boundary，且不會將 BIM child metadata 或 schema migration 帶入 `ProjectDataModel`／Project persistence。
- [x] 5.4 執行 focused Review workflow、ReviewItem、confirmation、source exclusion 與 Project persistence tests；確認未建立新的 state owner 或替代 commit path。

## 6. 回歸測試邊界

- [x] 6.1 為 standalone LINE、MLINE、explicit centerline、complete closed outline、complete parallel edges、ordinary non-component INSERT 與目前 small-gap behavior 加入 regression cases；驗證其既有 recognition outputs 均不變。
- [x] 6.2 為 Brace、Waler、Continuous Wall、Column、Beam 與 CornerBrace 加入 role-scope regression cases；驗證它們都不會呼叫 BIM Strut service，也不會改變既有 recognition behavior。
- [x] 6.3 執行 `tests/test_dxf_module_boundaries.py`，確認新的 pure module 不依賴 Tkinter／Presentation／Project／Solver，且 `dialog.py` 不包含 BIM geometry interpretation。
- [x] 6.4 驗證 CandidatePoint、Double Support、material recognition、Solver 與 optimization tests 保持不變並通過；不得為配合新 recognition path 而修改這些規則。

## 7. 文件與最終驗證

- [x] 7.1 實作完成且 focused tests 通過後，只更新 `docs/WORKFLOW.md` 的 DXF recognition current-behavior 章節；將 Guided Recognition 保留為本 change 以外的獨立未來需求，並確認未改寫 Architecture／Domain／Solver truth。
- [x] 7.2 使用 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 執行完整 regression suite；記錄通過／失敗數量，且不得以降低 assertions 或擴大 scope 的方式處理 failure。
- [x] 7.3 對 `bim-block-member-recognition` 執行 strict OpenSpec validation／implementation verification；確認每個 requirement scenario 都對應通過的 tests、所有 tasks 均完成，且 approved artifacts 以外的 production behavior 沒有改變。
