# Tasks

## 實作前閱讀

| Task group | 開始前必讀 | 要確認的行為 |
| --- | --- | --- |
| 1. Baseline 與 terminal facts | `proposal.md`「不變事項」；`design.md` Decision 1；spec「雙路幾何候選與正式工程資格必須分層」 | 不改幾何數值與 Waler identity 規則；pending只使用可靠、source-supported的WCS Strut axis，structured terminal facts來自既有topology。 |
| 2. Candidate model 與 pure detection | `design.md` Decision 1、2、6；spec 前兩個 Requirements與 deterministic Requirement | geometry qualification先行，status互斥，`accepted` invariant及one-to-one ambiguity明確。 |
| 3. 正式效果隔離 | `design.md` Decision 3；spec「暫定候選不得提前產生正式效果」 | 所有正式 consumers共用 `eligible && accepted`，Column／Beam不得反向合法化 pair。 |
| 4. Workflow、重建與 persistence | `design.md` Decision 4；spec「候選必須隨 canonical Review state 安全重建」 | source identity replay、升降級與derived rebuild安全，provisional false不得成為explicit rejection。 |
| 5. Review 介面 | `design.md` Decision 5；spec「Review 必須呈現狀態、原因與操作限制」 | 顯示全部 eligible／pending candidates，原因可讀，pending不可操作，Presentation不重算。 |
| 6. 整合、文件與最終驗證 | `proposal.md` In／Out of Scope；完整 spec；`design.md` Architecture Alignment／Backward Compatibility | S19／S36案例成立，既有正式候選等價，不改Project schema、Waler規則或Solver。 |

## 1. Baseline 與 structured terminal facts

- [x] 1.1 在 `tests/test_double_support.py` 補足 production baseline characterization：固定 Y29 `S19`／`S36` 的雙路幾何量測會通過現有 thresholds、兩支目前因 terminal Waler ambiguity 而沒有正式 pair、C26目前只保留既有 primary association；先執行該 focused test確認現況。（對應 spec「幾何符合但兩端 Waler 都有歧義」與「暫定候選旁有共享柱」）
- [x] 1.2 為 `dxf_import/waler_contact_face.py` 的 Strut terminal outcome補足 focused tests，確認 ambiguity issue可穩定提供 member source identity、`start`／`end` terminal及 competing Waler source identities，且輸入順序／軸線方向反轉不改變等價 facts。（對應 spec「任一 terminal 尚未唯一」「輸入順序不改變結果」）
- [x] 1.3 在 recognition→importer boundary建立最小 typed terminal qualification projection，直接源自 `TerminalTopologyOutcome`，不得解析 `ValidationMessage.message`、CandidatePoint label或重新掃描 DXF；以unit test驗證 resolved、missing、ambiguous terminal資料完整，並確認既有 Waler contact-face tests通過。（對應 design Decision 1）
- [x] 1.4 在Strut recognition→pairing boundary明確投影可靠、source-supported的WCS axis；以tests驗證Waler unresolved但來源軸可靠時可供provisional geometry，來源軸不可靠時不建立pair，且不得由Waler candidates、Column／Beam或附近幾何fallback猜軸。（對應spec「Waler unresolved 時使用可靠來源軸線建立暫定候選」「Strut來源軸線本身不可靠」）

## 2. Candidate model 與 pure detection

- [x] 2.1 擴充 `dxf_import/models.py` 的 `DoubleSupportCandidate` qualification contract與typed issues，加入 formal accepted predicate並強制 `accepted ⇒ eligible`；以model tests涵蓋合法狀態、`pending_waler`／`incompatible_waler`強制non-accepted及malformed-state defensive behavior。（對應 spec「Waler topology 必須產生可區分的候選狀態」「暫定候選不得提前產生正式效果」）
- [x] 2.2 重構 `dxf_import/support_pairing.py`，只對具有可靠source-supported WCS axes的Strut pairs套用現有 angle／`1000 ± 150 mm` spacing／`>= 0.9` overlap／`<= 250 mm` length gates，再以typed terminal facts分類 `eligible`、`pending_waler`、`incompatible_waler`；以boundary tests驗證所有等號、各自越界、missing／ambiguous／same／different Waler pairs、unreliable-axis rejection及Column evidence不參與資格。（對應 spec前兩個 Requirements）
- [x] 2.3 保留 legacy／synthetic caller的resolved topology adapter，使只有合法 `from_waler/to_waler` 的既有 unit tests得到等價 eligible candidates；執行現有 `tests/test_double_support.py` detection cases確認 threshold、confidence與一般 acceptance未回歸。（對應 design Decision 1、Backward Compatibility）
- [x] 2.4 以包含`eligible`、`pending_waler`與`incompatible_waler`全部edges的完整geometry-qualified graph計算deterministic IDs／ordering與one-to-one ambiguity；加入eligible＋pending及eligible＋incompatible共用member tests，確認所有edges均標示ambiguity、eligible不得default自動接受、pending／incompatible永遠不可接受。（對應spec「候選結果必須deterministic並保守處理一對多歧義」）
- [x] 2.5 加入graph rebuild與permutation tests：pending／incompatible edge消失後重建graph，剩餘唯一eligible pair才可依explicit decision／default生效；Strut collection order、軸線方向及candidate iteration order改變時，graph、ambiguity與accepted result保持等價。（對應spec「衝突edge消失後重新判斷唯一性」「輸入順序不改變結果」）
- [x] 2.6 更新 `set_double_support_candidate_accepted()`、decision apply／preserve helpers，拒絕接受 non-eligible candidate，接受一個 eligible pair時只清除其他正式 accepted membership且保留pending／incompatible diagnostics；以pure tests驗證no-op／conflict semantics。（對應 spec「Review 必須呈現狀態、原因與操作限制」「接受一個合法 pair 不隱藏暫定診斷」）

## 3. 正式雙路效果隔離

- [x] 3.1 將 `dxf_import/candidate_points.py` 的共享 Column／Beam association切換至共同 formal accepted predicate；以C26等價案例驗證pending pair不共享association，升級且accepted後才對兩lane各自投影，降級後不殘留。（對應 spec「暫定候選旁有共享柱」「合法且已接受的候選保持既有下游效果」）
- [x] 3.2 將 `DXFImportResult` summary／`to_project_rows()` 與所有 `SharedLayoutGroup` consumers切換至共同 predicate；加入malformed `pending_waler + accepted=True` negative test，確認不輸出group且不需Project schema migration。（對應 spec「完成 Project row conversion 前仍未解決」）
- [x] 3.3 將 `dxf_import/initial_zoning.py` 的double-support ordering units切換至共同 predicate，驗證pending／incompatible pair維持兩支一般Struts或既有保守分組，只有eligible accepted pair成為不可拆分unit；執行 `tests/test_dxf_initial_zoning.py` 與相關 support-adjacency tests。（對應 spec「暫定候選不得提前產生正式效果」）
- [x] 3.4 搜尋所有 `candidate.accepted`／`double_support_candidates` consumers，逐一確認正式group count、validation、summary與Problem projection不把provisional pair當正式群組；為任何實際正式consumer補focused assertion，不進行無關重構。（對應 design Decision 3）

## 4. Workflow、重建與 decision lifecycle

- [x] 4.1 將 importer、CandidatePoint rebuild、Waler contact adjustment及source exclusion／restore的pairing入口接到最新structured terminal facts；每次canonical mutation後使用重新辨識的finalized Strut axes從零重建完整graph，重算angle、spacing、overlap、length difference、topology與ambiguity，禁止原地切換status或沿用provisional量測；以workflow tests驗證所有結果同步更新。（對應spec「Waler解決後必須重新計算幾何」「候選必須隨canonical Review state安全重建」）
- [x] 4.2 更新 `DXFReviewWorkflow.commit_double_support_candidates()`，只接受目前canonical且eligible的decision delta，pending row no-op且不寫入`double_support_decisions`；以headless workflow tests驗證繞過Dialog也不能接受provisional pair。（對應 spec「Presentation 不建立第二套資格判斷」與「暫定候選不得提前產生正式效果」）
- [x] 4.3 更新source-identity decision replay／preserve flow：current source identity唯一且eligible時先套用explicit accepted／rejected decision；沒有explicit decision時才使用既有eligible default，one-to-one ambiguity阻止default自動接受；以tests驗證顯示ID重新編號、source ID reuse、explicit rejection優先、eligible→pending／incompatible降級、pending→eligible不需再次人工確認，以及Waler修正本身不繞過重算或ambiguity。（對應spec「解決Waler ambiguity後依既有預設生效」「顯示ID重新編號不誤套決策」）
- [x] 4.4 驗證Pause／Resume、exact resume與compatible recovery在不新增durable provisional state及不升級Project schema下重建正確outcome；執行 `tests/test_dxf_review_recovery.py`、相關 persistence／project-service tests，確認舊`double_support_decisions`相容且stale acceptance不生效。（對應 design Decision 4、Backward Compatibility）

## 5. 雙路支撐 Review 介面

- [x] 5.1 更新 `dxf_import/dialog.py` 的雙路支撐Treeview，顯示兩支Strut、spacing、可理解狀態與warning摘要，並提供selected pending candidate的terminal／candidate Waler詳細原因；以Presentation stub／layout tests驗證資料只來自candidate projection且狀態不只靠顏色。（對應 spec「Review 必須呈現狀態、原因與操作限制」）
- [x] 5.2 讓toggle及Apply只對eligible rows產生decision draft／workflow command，pending row disabled或no-op，incompatible outcome不進一般可接受清單；以UI interaction tests驗證double-click、button、Apply及重新開啟視窗都不能接受pending pair。（對應 spec「S19 與 S36 類型的暫定候選可見」「正式候選維持既有操作」）
- [x] 5.3 驗證workflow rebuild後開啟或刷新設定視窗會取得最新status／issues且不保留stale Treeview draft；確認Dialog不從canvas距離、顯示文字或Problems tree重算qualification。（對應 spec「Presentation 不建立第二套資格判斷」）

## 6. 整合、文件與最終驗證

- [x] 6.1 將Y29 importer regression更新為：`S19`／`S36`以可靠source-supported WCS axes重算後出現為`pending_waler`、顯示上下端competing Waler identities、C26不被正式共享、pair不在accepted groups；另驗證等價terminal resolution後使用canonical finalized axes重新計算全部門檻，結果eligible時依explicit decision／既有default／one-to-one policy生效，且不要求再次人工確認。（對應本change全部主要流程）
- [x] 6.2 執行 `tests/test_double_support.py`、`tests/test_dxf_review_workflow.py`、`tests/test_dxf_review_layout.py`、`tests/test_dxf_waler_contact_adjustment.py`、`tests/test_dxf_initial_zoning.py`、`tests/test_dxf_review_recovery.py` 與受影響Project conversion／persistence tests，確認formal候選相容、provisional隔離與Review lifecycle全部通過。
- [x] 6.3 執行DXF module boundary tests，確認recognition／pure operations不依賴Workflow／Presentation、Dialog不擁有qualification truth，且沒有新增Solver或Project Domain對DXF provisional metadata的依賴。（對應 design「Architecture Alignment」）
- [x] 6.4 實作與測試通過後最小幅更新 `docs/WORKFLOW.md`，記錄geometry-qualified provisional double-support candidate、qualification rebuild及formal-effect boundary；確認不需修改`docs/ARCHITECTURE.md`、`docs/DOMAIN.md`或`docs/SOLVER.md`，若實際truth改變則停止並回報scope衝突。
- [x] 6.5 執行完整 test suite，不得刪除測試、降低assertion或以skip掩蓋failure；記錄pass／failure／skip及任何與本change無關的既有失敗。
- [x] 6.6 執行 `openspec validate surface-provisional-double-support-candidates --strict --no-interactive`，再執行 `$openspec-verify-change` 對照 proposal scope、完整spec scenarios、design decisions與tasks，確認implementation完整且未修改Waler identity、Project schema或Solver規則。
