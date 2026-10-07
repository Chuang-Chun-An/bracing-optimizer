# Tasks

## 實作前閱讀

- 現在必讀：先讀 `proposal.md` 的「快速摘要、現況與目標、不變事項」及三份 delta spec；可先跳過風險細節。
- 各階段實作前：依下列任務指向閱讀 `design.md` 的對應決策；不要把人工裁決擴張成一般候選編輯行為。
- 需要時再讀：涉及暫停案件、來源排除或內容變更復原時，再讀 `docs/WORKFLOW.md` 的 DXF Review、人工修補與 recovery 區段。

## 1. 建立資料與辨識證據契約

- [x] 1.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 與 `tests/test_dxf_source_exclusion.py` 先加入失敗測試，固定 `Waler` 的工程線權威與來源寬度狀態預設值、`SourceManualOverride.waler_engineering_line_formalized` 的序列化往返，以及舊 payload 缺少欄位時必須視為 `False`；以執行這兩個測試模組確認測試能捕捉尚未實作的行為。實作前閱讀 `design.md` D1、D6、D7 與新 capability spec 的「寬度與材料不得由人工線猜測」。
- [x] 1.2 在 `dxf_import/models.py` 與既有 override 解析／擷取位置加入具向後相容預設值的權威、寬度狀態及正式化旗標，不改動既有 payload schema version；以 1.1 測試及既有 model/source override 測試驗證新舊資料皆可讀寫。
- [x] 1.3 為 envelope 寬度證據新增測試，涵蓋唯一寬度、無寬度、多個相同寬度、多個不同寬度，以及既有人工材料不得被清除；`source_width_state` 必須只分類已封存 `calculate-waler-width-orthogonally` 所產生的正交 `WalerEnvelopeFacts.source_width`，再於 `dxf_import/recognition.py` 與既有匯入轉換流程產生 `unique`、`unknown`、`ambiguous` 狀態，並驗證不會從人工線或有限線段端點距離重新量測／猜測材料。實作前閱讀 `design.md` D6；以 `tests/test_dxf_waler_contact_face_recognition.py` 與 `tests/test_dxf_input.py` 驗證。

## 2. 建立純函式人工正式化操作

- [x] 2.1 新增 `tests/test_dxf_waler_engineering_line_repair.py`，先固定合格條件與明確意圖：已形成、來源 identity 非空且為 provisional 的 Waler可首次正式化；已是 `manual_repair` formal的 Waler可再次採用另一條線原子取代舊 decision；候選點與 CAD 路徑相同；任何通過既有 validation的合法線不必落在 envelope外側邊；座標與暫定線相同仍有效；不合格輸入不得改變結果。以執行新測試檔確認邊界完整。實作前閱讀 `design.md` D2、D3、D10 與新 capability spec 的前兩項 Requirement。
- [x] 2.2 新增 `dxf_import/waler_engineering_line_repair.py`，實作不依賴 UI、檔案或 application 的純函式正式化操作，將採用線本身設為唯一正式工程線／接觸面並記錄 `manual_repair` 權威，不呼叫 outer-face selection；以 2.1 測試驗證候選、CAD與重新採用路徑一致，並執行 `tests/test_dxf_module_boundaries.py` 確認依賴方向。
- [x] 2.3 在新測試檔加入 diagnostic 範圍測試：只移除同一 normalized source identity 的四個接觸面／包絡線 blocker，保留其他來源、複合 handles、重疊、身份競爭及 `AMBIGUOUS_WALER_CONNECTION`；以參數化案例驗證每一類訊息的去留。實作前閱讀 `design.md` D4 與新 capability spec 的「只解除被人工裁決取代的問題」。
- [x] 2.4 在純函式操作中完成精準 diagnostic 替換，沿用既有 info diagnostic 表達人工來源，不新增與 `clarify-dxf-review-diagnostics` 重疊的新 code；以 2.3 測試及既有 diagnostic 測試驗證只改變允許清單內的訊息。

## 3. 以工作流程原子提交並重建下游結果

- [x] 3.1 先為既有候選編輯流程補回歸測試，固定一般 `apply_candidate_change` 仍只代表草稿／幾何編輯，不會自動取得正式權威；再將現有重建程序整理成可由人工正式化重用的最小內部入口，不改變其他角色行為。實作前閱讀 `design.md` D5；以 `tests/test_dxf_review_workflow.py` 與 `tests/test_dxf_candidate_points.py`（若現有檔名不同則使用對應既有測試）驗證。
- [x] 3.2 在 `tests/test_dxf_review_workflow.py` 新增 plan/commit 測試，涵蓋 revision、source fingerprint、normalized identity 與目標 Waler 不變檢查，以及任一檢查失敗時 runtime result、override 與 diagnostics 全部不變；以失敗案例比較提交前後快照驗證原子性。實作前閱讀 `design.md` D2。
- [x] 3.3 在 `dxf_import/review_workflow.py` 加入不可變的 `WalerEngineeringLineRepairPlan` 建立與提交入口，提交時呼叫純函式操作並使用既有 workflow revision／fingerprint guard；以 3.2 測試驗證 stale plan 被拒絕且成功路徑只提交一次。
- [x] 3.4 新增成功提交後的整合測試，確認 provisional-axis terminal evidence先被丟棄，接觸點、unique／competing topology、formal relations、connection、構件關聯、review baseline、來源確認狀態與 `can_import` 都由人工接觸線及完整 current source/result 重建，且不沿用舊衍生資料；以 `tests/test_dxf_review_workflow.py`、`tests/test_dxf_waler_contact_face_recognition.py` 與 `tests/test_dxf_input.py` 驗證。實作前閱讀 `design.md` D5、D11 與新 capability spec 的「正式化後必須原子重建下游結果」。
- [x] 3.5 在 `tests/test_dxf_waler_contact_adjustment.py` 新增人工接觸線支撐側測試：authoritative member bodies同側時由既有 unique-first結果與 `support_side_normal()`取得該側法向；兩側衝突或無可靠構件時 `support_normal_world is None`，但 `contact_face_state == "formal"`與 `manual_repair` authority不變；驗證人工路徑從不呼叫 outer-face selection。實作前閱讀 `design.md` D11，並以 focused adjustment／contact-face tests驗證。
- [x] 3.6 在正式化 staged rebuild中，依人工 contact line重建 `WalerContactReviewState`與所有完整 formal Brace的 `BraceAdjustmentBaseline`；若支撐側 unknown只使後續 adjustment由既有 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋，不得使正式化 rollback。以 `tests/test_dxf_waler_contact_adjustment.py`及workflow整合測試驗證 baseline均源自新人工線。

## 4. 保存、重播及來源生命週期

- [x] 4.1 在 `tests/test_dxf_source_exclusion.py` 加入人工正式化 override 的擷取、解析、序列化與相同 fingerprint 重播測試，並證明舊式 generic manual geometry 或缺少正式化旗標的資料不會升格；以 round-trip 與 legacy fixture 驗證。實作前閱讀 `design.md` D7、D10。
- [x] 4.2 在 override 重播流程加入正式化旗標的專用分支，透過同一純函式／workflow 語義重驗，不以直接塞回幾何欄位取代正式化；以 4.1 測試及 workflow 原子性測試驗證重播成功與失敗都不產生半成品。
- [x] 4.3 新增並實作來源排除、還原與重新辨識案例，確認正式化決定跟隨既有來源生命週期，且排除後不殘留連線、接觸面或可匯入狀態；以 `tests/test_dxf_source_exclusion.py` 驗證排除與還原前後完整狀態。

## 5. 暫停案件與內容變更復原

- [x] 5.1 在 `tests/test_dxf_review_recovery.py` 新增案例：相同 fingerprint／exact match 可保留並重驗；內容改變但仍可定位同一 subject 時標為 `requires_review`；subject 消失或角色改變時停用；新檔自動得到正式候選時保持 automatic；generic geometry 不暗示曾正式化。以 recovery plan 與實際套用結果雙重斷言驗證。實作前閱讀 `design.md` D9 與 modified `paused-dxf-review-source-relink` spec。
- [x] 5.2 在既有 review recovery／relink planner 實作上述狀態轉移，禁止跨內容靜默轉移 `manual_repair` 權威；以 5.1 測試及既有 relink 測試驗證 exact-match 行為未退化。

## 6. 串接人工修補 UI

- [x] 6.1 在 dialog/layout/controller 測試先加入行為：合格的 provisional Waler及已是 `manual_repair` formal而要重新採用者顯示專用「採用為正式圍令」；點選候選或輸入 CAD 線只更新待採用選擇，不會立即正式化；Preview detail與確認均顯示「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」；automatic formal Waler及其他角色維持既有按鈕語意。以 `tests/test_dxf_review_layout.py` 與對應 dialog 測試驗證。實作前閱讀 `design.md` D8。
- [x] 6.2 在 `dxf_import/dialog.py` 將明確按鈕事件送入 workflow 的 plan/commit 入口，確認訊息保留完整接觸面提示；成功後刷新完整 review result，重新採用時原子取代舊 decision；失敗時保留原狀並顯示可理解原因。既有高風險確認機制照常使用；以 dialog/controller 測試驗證候選、CAD與重新採用三條操作路徑。
- [x] 6.3 新增視覺狀態與摘要測試，確認人工正式線使用正式線樣式並顯示人工 provenance，同時仍可看見未解除的重疊、身份或連線問題；以 layout snapshot／widget state 測試驗證，不以顏色作為唯一狀態來源。

## 7. Y29 W14 驗收與文件同步

- [x] 7.1 以 Y29 W14、來源 `58D` fixture 新增候選點選線整合測試，確認 Preview／確認顯示固定接觸面提示，W14選定線本身成為正式 `manual_repair` contact face且不要求落在 envelope外側邊，只清除該來源允許的 envelope/contact-face ambiguity、沒有拆成多個 Waler，其他 Y29 blocker保留；以 `tests/test_dxf_input.py` 或專用 fixture驗證。實作前閱讀新 capability spec 的 Y29 W14 Requirement。
- [x] 7.2 對同一 Y29 W14 fixture 新增 CAD 指定工程線整合測試，確認 CAD線本身作為接觸面、正交 `source_width_state`／材料政策與候選路徑等價；以比較兩條路徑的 Waler、diagnostics、support side與downstream associations驗證。
- [x] 7.3 新增人工正式化後調整背填 regression：先以新人工接觸線重建連到該 Waler的 formal Brace baseline，再執行既有 adjustment，驗證 Brace依 rigid-translation共同移動且角度／長度不變；以 `tests/test_dxf_waler_contact_adjustment.py`及workflow測試驗證。
- [x] 7.4 新增支撐側 unknown regression：人工正式化仍成功，但背填／寬度 adjustment回報 `WALER_SUPPORT_SIDE_UNKNOWN`，Waler、Brace、review baseline、manual override及confirmation狀態全部不變；以提交前後完整快照驗證原子阻擋。
- [x] 7.5 執行既有正式 Waler、contact-face unique-first、orthogonal width、overlap、connection、Brace rigid-translation 與 project-row 轉換回歸，確認人工例外未改變自動辨識規則、已封存 change行為或 Solver input contract；至少執行 `tests/test_dxf_waler_contact_face_recognition.py`、`tests/test_dxf_waler_contact_adjustment.py`、`tests/test_dxf_input.py` 與相關 overlap/connection 測試並保留結果。
- [x] 7.6 更新 `docs/WORKFLOW.md` 的 DXF Review 人工修補、接觸面／支撐側、暫停／復原與 provenance 說明；實作完成後逐項對照文件與三份 delta spec，若發現 Domain、Architecture、recognition precedence或 Solver truth也被改變，先停止並修正 change artifacts，不得逕自擴張實作範圍。

## 8. 最終驗證

- [x] 8.1 執行所有本次新增與直接受影響的單元測試，至少涵蓋 repair、workflow、source exclusion、recovery、layout、contact-face 與 input；確認零失敗且沒有以 skip 或弱化 assertion 規避錯誤。
- [x] 8.2 執行 `\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_dxf*.py" -v`，驗證完整 DXF 子系統回歸；若有失敗，區分既有問題與本次回歸並留下可重現證據。
- [x] 8.3 執行 `tests/test_dxf_module_boundaries.py` 與專案既有 architecture boundary tests，確認 Presentation → Workflow → Recognition／pure operations → models 的依賴方向未被破壞。
- [x] 8.4 執行 `openspec validate resolve-provisional-waler-manually --strict`，確認 proposal、design、三份 delta spec 與 tasks 一致且無格式或 requirement 驗證錯誤。
- [x] 8.5 使用 `$openspec-verify-change` 對照 `proposal.md` scope、三份 spec 的所有 scenarios、`design.md` 決策與本任務清單進行完成度審查；只有功能、相關測試、文件與驗證全部完成後才可建議 archive。
