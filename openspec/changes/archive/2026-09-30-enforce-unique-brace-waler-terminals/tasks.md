# Tasks

## 實作前閱讀

- **Group 0 前**：讀相鄰 change `../detect-waler-overlap-errors/proposal.md`、其 design 中 terminal diagnostics／identity provenance 決策及相關 spec；未確認格式定案或合併前不得開始本 change 的實作。
- **Group 1 前**：讀 `proposal.md` 的「現況與目標」及 delta spec 的「Y29 重疊 Waler 端點必須維持未解析」；先固定 B15／W18／W19 與唯一 W19 的可觀測基線。
- **Group 2 前**：讀 `design.md` Decision 1～3，以及 spec 的「Terminal evidence 必須單向支援 Waler contact-face 判定」、「Brace 直接端點連接必須優先於軸向延伸」與「延伸結果必須一致更新正式 Brace 連接」。
- **Group 3 前**：讀 `design.md` Decision 2～5，以及 spec 的「延伸失敗不得改變可靠 recognition 軸或提交不完整 Project」與「Review 與人工端點操作必須沿用同一連接語意」。
- **Group 4 前**：讀 `proposal.md` 的「不變事項／Out of Scope」、`design.md` 的 Architecture Alignment／Risks，以及完整 delta spec；確認沒有把 Waler 合併、Solver 或 CornerBrace 變更帶入。
- **可先跳過**：`docs/SOLVER.md` 與材料配置測試；只有實作意外觸及 Solver safety 檔案時才停止並依 AGENTS.md 補讀，不得在本 change 內順便修改 Solver。

## 0. 前置 diagnostics contract 確認

- [x] 0.1 確認 `detect-waler-overlap-errors` 的 terminal competitor identities、`terminal_name`、source provenance 與 Review diagnostic projection 格式已定案或已合併，記錄本 change 要重用的欄位／型別並驗證不需建立第二套格式；若尚未定案，停止後續 tasks 而不先實作相容層。

## 1. 建立失敗與成功基線

- [x] 1.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 補上 Brace direct 最近位置為 0／1／2 個 Waler identities 的 characterization tests，驗證多解保留 `terminal_name` 與完整 competitors、不得建立該端 evidence，並以反轉輸入順序確認結果等價。
- [x] 1.2 在 `tests/test_dxf_waler_contact_face_recognition.py` 補上 terminal evidence／contact-face 單向依賴測試：B15 整體 unresolved 時，唯一 start evidence 仍可決定 W16 接觸側；ambiguous end 不得為 W18 或 W19 提供側向 evidence；member-level verdict 不得回頭改變 contact-face outcome。
- [x] 1.3 在最接近既有 fixture 的 DXF import regression test 中加入 Y29 B15 source `71E`：W18 `69F` 與 W19 `720` 同時 active 時驗證 blocking ambiguity、P02／P07 都未成為正式端點；只保留 W19 時驗證端點由 Brace 軸線與 W19 selected formal contact face 的既有有限交點規則產生，且在 `endpoint_tolerance_mm` 內等價於 P07，並確認沒有中點專用分支。

## 2. 實作 Brace 兩端原子式裁決

- [x] 2.1 在 `dxf_import/waler_contact_face.py`／`dxf_import/recognition.py` 先維持唯一 terminal evidence 對 Waler contact-face 的既有消費，再建立 runtime-only Brace member-level verdict；以 pure unit tests 驗證五項成功條件全部成立才 resolved，並覆蓋零解、多解、同一 Waler、任一 contact face 尚為 provisional、selected face 無合法有限交點、提交後長度不合法及完整成功。
- [x] 2.2 修改 `_apply_terminal_resolutions()` 與 importer connection mapping，使 resolved Brace 一次提交兩端 geometry 及 pair identities，unresolved Brace 完全不提交單端 geometry／connection且禁止 legacy nearest fallback；驗證一端成功一端 ambiguous 時仍保留完整 source-supported axis與唯一端的 contact-face evidence，而 Strut 既有逐端行為不變。
- [x] 2.3 修改 `dxf_import/candidate_points.py`，只讓完整 resolved Brace 建立 recommended／selected formal endpoints；unresolved Brace 的來源點或競爭交點只能作 evidence、不得被預選或回寫 connection，並以 Candidate Point focused tests 驗證 P02／P07 無法繞過 W18／W19 identity ambiguity。
- [x] 2.4 保持 direct 優先與 `<= 600 mm` outward extension 邊界：direct 多解不得改走 extension；唯一 direct、唯一 extension 與 Y05 既有成功案例仍成立，並執行 `tests/test_dxf_brace_waler_extension.py` 驗證 250 mm／600 mm 邊界未改。

## 3. 統一 Review、diagnostics 與下游邊界

- [x] 3.1 讓 ambiguity／incomplete diagnostics 從同一 verdict 投影 Brace ID、端別、relation kind 與所有競爭 Waler identities，並驗證 Review problem 不會只顯示 W18 或 W19 其中一支，也不新增 Y29 專用 error code。
- [x] 3.2 建立並重用單一 formal Brace predicate，使 Review connection summary、Waler direct-Brace 顯示、Project `to_project_rows()` 與 Waler forbidden-point 來源都排除 unresolved Brace；驗證即使防禦性直接呼叫 conversion，也不產生 unresolved Brace row 或 Solver-facing資料。
- [x] 3.3 補上 source exclusion／restore／rebuild 與 confirmation invalidation tests：排除 W18 後 B15 由既有軸線／selected face 交點規則得到唯一 W19 endpoint，該 fixture 結果在 `endpoint_tolerance_mm` 內等價於 P07；復原 W18 後回到 unresolved、清除 staged formal pair及 recommendation，且結果不受 source／collection order 影響。
- [x] 3.4 補上 manual endpoint replay tests，驗證 replay 後以目前 active sources 與相同 direct rule 重新推導 Waler identities、不保存舊 identity；只選 P07 幾何點不能在 W18／W19 重疊時指定 winner，也不能把 unresolved Brace 升級為 formal。
- [x] 3.5 補上正式 import integration test，驗證 production path 對每支 Brace 一定傳遞 authoritative member-level verdict，unresolved Brace 不會因 committed pair 缺失而進入 legacy nearest fallback；另保留 legacy helper 獨立呼叫相容測試。

## 4. 文件、回歸與 OpenSpec 驗證

- [x] 4.1 僅在實作與測試完成後更新 `docs/DOMAIN.md` 的 Brace／formal connection 段落，記錄「兩端各唯一且連到不同 Waler」為 DXF Recognition Hard Constraint；同步更新 `docs/WORKFLOW.md` 的 Brace connection lifecycle，明定單端失敗不保留部分正式 Brace而使整支 unresolved，並確認未修改 Architecture、Solver、Project schema 或材料規則。
- [x] 4.2 執行聚焦測試 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_waler_contact_face_recognition.py tests/test_dxf_brace_waler_extension.py tests/test_dxf_input.py`，修正本 change 造成的失敗且不得降低既有 assertions。
- [x] 4.3 執行 Review／lifecycle／CornerBrace 鄰接回歸測試（包含 `tests/test_dxf_review_settings.py`、source exclusion／review workflow 相關 tests、`tests/test_dxf_corner_brace_repair.py`），驗證 blocking、rebuild、manual replay 與 CornerBrace 行為未退化。
- [x] 4.4 執行專案既有 DXF import 全套測試及 architecture boundary tests（若有），確認無不相關失敗、無 persistence schema 變更、無 Solver regression；若完整測試受既有失敗阻擋，記錄可重現命令與本 change 無關的證據。
- [x] 4.5 逐項對照 delta spec scenarios 與本 tasks 完成狀態，確認 `proposal.md` 只描述 why／what、`spec.md` 只定義 observable behavior、`design.md` 只說明 how／trade-offs、`tasks.md` 只列 implementation／verification，四份檔案獨立且無內容交錯；再執行 `openspec validate enforce-unique-brace-waler-terminals --strict`，確認 artifacts、tests 與實作一致後進入 archive 前 verification。
