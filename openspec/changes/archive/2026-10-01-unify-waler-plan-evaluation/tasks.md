# Tasks

## 實作前閱讀

- Group 1 前：讀 `proposal.md`「不變事項／尚未決定事項與重新評估條件」、`design.md` Decision 4、6，以及 spec「既有路徑差異必須先報告並決策」「統一合法性與 allocation 語意」「既有分數與排序相容」。
- Group 2 前：確認已確認的五項 B 類規則寫入 artifacts 且通過 strict validation，並完成 Task 1.5；再讀 `design.md` Decision 1～3、7，以及 spec「共用核心評估」「統一合法性與 allocation 語意」「Waler 總長使用 200 mm 閉區間且不使用 adjustment block」「搜尋政策與評估分離」。
- Group 3 前：讀 `design.md` Decision 3、5、7，以及 spec「共用核心評估」「具名問題識別與完整顯示」。
- Group 4 前：讀 `proposal.md`「Out of Scope」、`design.md`「Architecture Alignment／Migration Plan」及完整 spec 驗證矩陣。
- 可先跳過 DXF、Support Solver、persistence 與 RC eligibility specs；只有回歸失敗指向其 boundary 時再讀。

## 1. 鎖定既有評估行為

- [x] 1.1 在 Waler Algorithms focused tests 建立合法 plan characterization cases，涵蓋全庫存、需採購、ratio／under-4000／stock group／length variation／joint score components；所有 local score 與 component 斷言 MUST 使用 exact equality 驗證現有 assignments、metrics、數值型別、運算結果固定，不得使用浮點容差。
- [x] 1.2 在 Waler Algorithms focused tests 建立 legality boundary cases，涵蓋 joint distance `< clearance` 與 `= clearance`、segment `< min`／`= min`／`= max`／`> max`、non-purchasable length、total mismatch 及 allocation defensive failure，並驗證有效性與既有 automatic payload。
- [x] 1.3 在 `tests/test_plan_editing.py` 補齊人工 Waler characterization cases，記錄合法／不合法 plan 的 `score`、`errors`、`legality.summary/details/warnings` 與欄位順序，確認測試在重構前通過。
- [x] 1.4 使用相同 resolved context 比對 automatic `evaluate_individual()` 與 `WalerPlanEditing` 的 characterization 結果並產生差異報告；輸入 MUST 使用相同 segments、joints、config 與同一份庫存資料（含 Qty、material spec 有值及空白規格 fallback）。A 類只記錄訊息文字／順序／欄位名稱差異並交由各自 projector 保留；B 類逐項記錄差異名稱與具體輸入、自動結果、人工結果、來源程式位置、建議規則及工程／既有專案／Solver 影響理由、採用後改變的既有行為。若有 B 類，完成報告後 MUST 停止且不得開始 Group 2，等待使用者確認；不得自行選邊、採較寬鬆規則或為通過測試改規則。使用者確認後，先更新 spec Requirement／Scenario、proposal「不變事項」／Impact、必要的 `docs/DOMAIN.md`／`docs/SOLVER.md` 更新標記及相關 design／tasks，並重新 strict validate。
- [x] 1.5 使用既有 Single Waler 與 Global Waler fixtures，在相同環境、config、seed 與輸入下執行多次修改前計時，保存各次時間、執行次數與摘要作為 baseline，並驗證未改動 GA stage、candidate count 或其他搜尋參數。

## 2. 建立共用 Algorithms evaluator

- [x] 2.1 在 `bracing_optimizer/algorithms/wales.py` 或同 package 小型專責模組新增 typed plan evaluation result，集中全部 total／joint／segment／purchasable issues、exact-length allocation、ratio analysis、score components 與 `local_score`；實作 `required_length - 200 <= steel_length <= required_length` 並以 11799／11800／12000／12001（required 12000）驗證閉區間。
- [x] 2.2 新增具名 structured issue model，以 `(code, normalized facts)` 支援分類與去重，至少區分 steel-total-short、steel-total-long、joint-clearance、segment below／above range、non-purchasable 與 allocation unavailable；用多個同 code 不同 joint／segment index facts、相同訊息不同 code 的單元測試驗證不會錯誤合併或遺失。
- [x] 2.3 實作重新確認的 evaluation sequence：先完整收集全部 hard issues；只要有任一 total／joint／segment range／non-purchasable issue，allocation、ratio、score components 與 local score 全部為 `None`。只有無 hard issue 時才執行 exact allocation；allocation unavailable 仍不得虛構 buy count／stock groups／variation／local score。以修訂後 B-01／B-02 cases 驗證。
- [x] 2.4 將 `wales.evaluate_individual()` 維持為 decode 後呼叫共用 evaluator，再投影成既有 candidate dict；合法 local score 與每個 component MUST 使用 exact equality，hard-invalid legality penalty 與 allocation-failure penalty 維持既有 automatic payload，且 GA repair、stage、seed、candidate count、merge／tie-break 程式與設定未被修改。
- [x] 2.5 移除 Waler adjustment-block evaluation／result generation：Waler `tail_adjustment` compatibility 值固定為 `0`、`pieces` 不產生 `shim`，合法 shortfall 以 `gap=required_length-steel_length` 表達且範圍為 `0..200`；驗證 Support Shim constants、generation 與 tests 完全未修改。
- [x] 2.6 執行直接 Algorithms evaluator 與 automatic `evaluate_individual()` 的等價測試，確認相同 context 的 issues 一致、所有 hard-invalid plan 的 allocation／ratio／local score 都 unavailable、合法 plan 的 allocation 與 score 完全相同；另以舊 adjustment-only cases 驗證預期改為 invalid／無合法候選，而非修改搜尋參數補償。

## 3. 將人工 Waler 編輯接到共用評估

- [x] 3.1 修改 `WalerPlanEditing` 的 compatibility projection，使任何 hard-invalid plan 的 assignments、allocation metrics、ratio fields 與 score 均為 `None`，同時保留 evaluator 的全部 issues、人工顯示與合法 plan payload；不得在 Application 重建 invalid score 或 allocation。
- [x] 3.2 以 structured issue codes／facts 重建人工 `legality` 投影，移除對 `validate_segments()` 中文訊息 substring 的分類／排除；summary 顯示違規總數，details 依 total、joint input order、segment index order 列出全部 issues，並驗證多接頭與多不可購買料長不再只顯示第一筆。
- [x] 3.3 將人工總長顯示改為「鋼材總長不足／鋼材總長太長」，移除「尾端調整量不合法」；驗證 11800／12000 合法、11799／12001 invalid、`tail_adjustment=0`、無 Waler `shim` piece，且正常 UI 仍只允許可購買料長。
- [x] 3.4 更新 automatic／manual equivalence matrix，兩條路徑 MUST 使用相同 segments、joints、required length、200 mm 下界、config 與同一份庫存資料（包含 Qty、material spec 有值及空白規格 fallback）；驗證 legality、全部 issue codes／facts、invalid unavailable fields 完全相同，合法 plan 的 allocation、`local_score` 與每個 score component MUST 使用 exact equality，並驗證人工輸入不會套用 GA repair 或搜尋 heuristic。

## 4. 整合、文件與完成驗證

- [x] 4.1 重新執行 Waler focused tests（至少 `tests/test_plan_editing.py`、`tests/test_optimize_waler.py`、`tests/test_wales_tail_adjustment.py`），確認所有 hard-invalid plan 不產生 allocation／local score、score 權重與未受影響顯示語意不變，且「無 Waler adjustment block＋200 mm 閉區間」邊界 coverage 保留。
- [x] 4.2 重新執行 Single／Global Waler regression（至少 `tests/test_waler_global.py`、`tests/test_optimize_waler_global.py`、`tests/test_waler_global_reliability.py`），分別記錄新總長 hard constraint 造成的預期 Top N／signature 差異與非預期 regression；stage、seed、candidate count、merge／tie-break policy 與相同合法候選的 exact score MUST 不變。
- [x] 4.3 使用 Task 1.5 的同一組 Single／Global fixtures、環境、config、seed、輸入與執行次數重跑修訂後效能，保留初次失敗結果並回報新原始量測、摘要及前後比較；若仍有超出正常 run-to-run noise 且可重現的明顯變慢，MUST 再次停止，不得調整任何搜尋參數補償。
- [x] 4.3a 依 profiler 定位實作 lazy hard-issue traversal：正式 evaluator／diagnostics 必須完整 materialize issues，GA repair feasibility probe 只以相同 traversal 查詢第一個 issue 並停止，不得建立未使用的完整 issue list／中文訊息。以 boundary／multiple-issue matrix 驗證 boolean 與完整 collection 的有效性完全相同，確認 repair 不呼叫 formatter；重跑 focused、Single／Global regression 與相同 benchmark，candidate metadata／signatures／exact scores 必須不變，若仍明顯變慢則再次停止。
- [x] 4.3b 依第二輪 profiler 與使用者確認，將 lazy generator 改為單一 synchronous hard-rule scanner＋optional issue sink：正式 evaluator 傳入 sink 並完整收集全部 issues，repair 不傳 sink 且在第一個 violation 回傳，不建立 generator、issue object 或顯示文字；hard-rule branches 不得複製。以相同矩陣、focused／Single／Global regressions 與同場 Git HEAD benchmark 驗證 metadata／signatures／exact scores 不變；若仍有超出 run-to-run noise 且可重現的明顯變慢，MUST 再次停止。
- [x] 4.4 執行完整相關 Solver regression、Project result load/recalculate tests 與 architecture boundary tests，確認舊結果含非零 Waler `tail_adjustment` 時可無 migration 載入、重新計算後歸零且無 `shim`；Algorithms 未依賴 Application／Presentation，Presentation 未新增 scoring／legality 判斷，且沒有不相關失敗。
- [x] 4.5 實作驗證後更新 `docs/DOMAIN.md`：移除 Waler adjustment block 規則、改為 200 mm 總長閉區間並保持 Support Shim 規則；更新 `docs/SOLVER.md` 的 Waler evaluation pipeline、invalid diagnostics、完整 issue projection 與 `WalerPlanEditing` 段落，並確認 runtime-only issue code 未寫入 Project JSON 或結果存檔；`docs/ARCHITECTURE.md`、`docs/WORKFLOW.md` 無 ownership／workflow truth 變更則不修改。
- [x] 4.6 執行 `openspec validate unify-waler-plan-evaluation --strict` 與 `$openspec-verify-change`，逐項核對 proposal scope、design decisions、spec scenarios 與 tasks，確認只有已確認的 invalid evaluation、完整 issue 顯示與 Waler 200 mm／無 adjustment block 規則改變；score weights、GA policy、seed、candidate count 與 persistence schema 未改。
