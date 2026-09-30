# Tasks

## 實作前閱讀

- **Group 0～1**：先讀 `proposal.md` 的「不變事項／尚未決定與重新評估條件」、`design.md` Decision 1 與 Decision 3，以及 `dxf-waler-contact-face-recognition` 的「接觸面選擇必須先建立 member-to-Waler 關係／支撐側必須由 member 軸線朝構件本體的方向判定」。目標是先確認實際 Y29 identities 與現有 candidate eligibility，不得為了測試擴張搜尋範圍。
- **Group 2**：讀 `design.md` Decision 2，以及 `dxf-waler-contact-face-recognition` 的「Waler 接觸面必須依 unique-first evidence precedence 判定」和 `brace-axis-waler-extension` 的「候選方向證據必須與正式連接 identity 分權」。目標是採方案 A 分開 side authority 與 connection authority，且 competing evidence 不得推翻 unique 結果。
- **Group 3**：讀 `design.md` Decision 4，以及 `dxf-waler-overlap-diagnostics` 的「競爭關係必須升級為 blocking error」。目標是保留 identity blocker，不再用它強迫 Waler provisional。
- **Group 4**：讀 `design.md` Decision 5 與三份 delta specs 的 exclusion／restore／順序不變 scenarios。目標是所有 staged state 都從 active sources 重建。
- **Group 5**：回讀 `proposal.md` 的 Impact／Out of Scope、`design.md` Architecture Alignment／Backward Compatibility，以及三份 delta specs 全文，再做文件、回歸與 OpenSpec verification。
- **可先跳過**：`docs/SOLVER.md`、Solver regression、材料規則與 CornerBrace specs；本 change 不修改 Solver 或那些工程規則。若實作意外碰到這些區域，應停止確認 scope，而不是自行擴張。

## 0. Y29 身分與候選集合 characterization

- [x] 0.1 在 `tests/test_dxf_waler_contact_face_recognition.py` 新增不改 production behavior 的 Y29 characterization，列出使用者所指 W17／W18 情境及既有 W17／W20、B15 W18／W19 regression 的 exact source handles、terminal、relation kind 與 competing set；驗證 fixture 中的真實映射並記錄 assertion，不以顯示編號猜測 geometry。
- [x] 0.2 以現有 direct／axis-extension candidate builder 驗證目標 terminal 已把需要的 Waler 列入相同 competing set；若沒有，停止實作並回報 proposal「重新評估條件」，不得放寬 `ambiguous_connection_delta_mm`、`endpoint_tolerance_mm`、`maximum_brace_axis_extension_mm` 或新增 proximity heuristic。

## 1. 建立 canonical terminal relations

- [x] 1.1 在 `dxf_import/waler_contact_face.py` 為 canonical terminal relation 加入明確 `unique`／`competing` identity state，並讓 `TerminalTopologyOutcome` 成為 relation 與 issue 的單一 owner；以 pure unit tests 驗證欄位、排序、immutability 與 typed unique-only view 不會產生第二份幾何 truth。
- [x] 1.2 修改 `build_member_terminal_evidence()` 的既有 candidate handling：唯一 best 產生 `unique` relation；數值等價或位於既有 ambiguity delta 的 best + competitors 各產生 `competing` relation並保留同一 blocking issue；較遠 candidates 不產生 relation。以 direct、axis-extension、selected upstream identity、零解與輸入順序反轉測試驗證。
- [x] 1.3 補上 provenance consistency tests，驗證 ambiguity issue 的 `terminal_name`／competing identities 與 canonical competing relations 完全相符，且 Waler ID、handle lexical order、entity order、axis direction 或 collection order 不改變 outcome。

## 2. 分離 Waler side authority 與 member connection authority

- [x] 2.1 修改 `resolve_waler_contact_faces()` 採 unique-first precedence，仍沿用現有法向投影與 `abs(component) <= endpoint_tolerance_mm` degeneracy gate；在 `tests/test_dxf_waler_contact_face_recognition.py` 新增並驗證：(a) Waler A 有上側 reliable unique 與下側 conflicting competing 時維持上側 formal 並產生 non-blocking provenance warning；(b) 只有同側 competing 時可完成 formal；(c) 只有兩側 competing 時為 `WALER_CONTACT_FACE_AMBIGUOUS`；(d) Y05／Y1A／一般 CAD fixtures 中原本 formal 的 Waler 全部維持 formal 且 selected face 幾何等價。
- [x] 2.2 修改 Brace terminal verdict／formal apply path，只允許 `unique` relations 建立 endpoint、`FromWaler`／`ToWaler` 與 atomic formal Brace；以 W18／W19 均已有 formal contact face 但 B15 仍 unresolved 的測試驗證 contact face 不會挑 identity winner。
- [x] 2.3 檢查並調整 `dxf_import/candidate_points.py`、connection mapping、Waler forbidden-point projection 與 DXF result-to-project conversion 的 relation consumers，統一使用 unique/formal predicate；新增負向測試，驗證 side-only competing relation 不會產生 adopted Candidate Point、正式 connection、forbidden point、Project row 或 Solver-facing geometry。
- [x] 2.4 保留唯一 terminal、單線 Waler、一般 Strut 與既有合法 Brace axis-extension behavior；執行相關 focused tests並驗證沒有改變既有 `<= 600 mm` extension boundary或正式 endpoint 交點規則。

## 3. 調整 diagnostics 與 staged geometry orchestration

- [x] 3.1 在 `dxf_import/recognition.py` 將 canonical relations依序交給 contact-face resolution 與 unique-only member finalization，移除「只因 terminal identity competition 就強制候選 Waler provisional」的耦合；驗證 pure outcome 與 staged `Waler.contact_face_state` 一致。
- [x] 3.2 調整 contact-face diagnostics，使 `WALER_CONTACT_FACE_UNRESOLVED` 只代表 authoritative evidence set 缺乏可靠方向、同層級方向衝突、envelope 或幾何問題；新增 `WALER_COMPETING_SIDE_EVIDENCE_IGNORED`（或實作前確認的等價通用 code）warning，驗證它 deterministic、non-blocking，且保留 Waler、unique member sources 與 conflicting competing member sources provenance；terminal identity ambiguity 仍產生既有 blocker但不偽裝成 contact-face failure。
- [x] 3.3 調整 overlap competition join，使 direct terminal provenance 持續產生 `WALER_OVERLAP_COMPETITION`，且兩支 Waler即使都 formal 仍保持 blocking；驗證 generic unresolved、錯誤 pair A／B vs A／C 與順序不變 cases 不被錯誤升級。
- [x] 3.4 更新 Y29 regressions：W17／W20 overlap warning與 blocking competition 保留、各 Waler contact-face state 依實際 side evidence 判定；B15 W18／W19 ambiguity 保留、P02／P07 不成為正式 endpoint；若只剩唯一 W19，仍依 Brace axis 與 selected formal contact face 的有限交點得到既有 P07 等價結果。

## 4. Review／Preview 與 lifecycle 一致性

- [x] 4.1 檢查 `dxf_import/review_workflow.py` 與 Review problem projection，讓 formal Waler contact face 和 unresolved member identity 可同時存在；新增 integration test驗證 blocking problem 仍使 `can_import == false`，confirmation 不得把 competing relation 升級為 unique。
- [x] 4.2 檢查 Preview／detail panel 的既有 state projection，確保 Waler 使用 recognition outcome 的 formal face、ambiguous member 使用 unresolved 樣式，且 Presentation 不重算 side 或 identity；只在現有 projection 無法表達時做最小修改並以 `tests/test_dxf_review_layout.py` focused test驗證。
- [x] 4.3 新增 source exclusion／restore／rebuild tests：排除競爭 Waler 後從 active relations 建立唯一 connection；復原後重建 competing relations與 blocker；每支 Waler contact-face state 由當次 side evidence 決定，不沿用 stale outcome。
- [x] 4.4 新增 Pause／Resume、compatible recovery、manual override replay與 input-order tests，驗證 exact source provenance、identity state、contact face、blocking diagnostics及 confirmation invalidation在等價 active sources 下保持一致。

## 5. 長期文件與完整驗證

- [x] 5.1 實作與 focused tests通過後，更新 `docs/DOMAIN.md` 的 DXF recognition boundary，明定 candidate side evidence 只決定 Waler 支撐側、唯一 identity 才能形成正式 member connection；若實際 Review lifecycle 說明改變，再最小更新 `docs/WORKFLOW.md`，不得修改 Solver 或材料章節。
- [x] 5.2 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_waler_contact_face_recognition.py tests/test_dxf_brace_waler_extension.py tests/test_dxf_input.py`，驗證 unique-first a～d、pure geometry、Y29、Y05、Y1A、一般 CAD Strut／Brace、Project boundary 與既有 extension regression 全數通過。
- [x] 5.3 執行 `\.venv\Scripts\python.exe -m pytest tests/test_dxf_review_workflow.py tests/test_dxf_review_layout.py tests/test_dxf_review_settings.py`，驗證 Review blocking、Preview projection、exclusion／restore、Pause／Resume 與 confirmation lifecycle。
- [x] 5.4 依實際受影響範圍執行完整 DXF import suite及 architecture boundary tests，確認一般 CAD、BIM、HATCH RC Waler、CornerBrace 與 persistence schema 沒有 regression；不得以刪除測試或降低 assertion 解決失敗。
- [x] 5.5 執行 `openspec validate decouple-waler-side-evidence-from-terminal-identity --strict`，再以 OpenSpec verify workflow 對照 proposal scope、三份 delta specs、design decisions 與本 task checklist；確認沒有修改 overlap `50%`、Brace `600 mm`、Project schema或 Solver truth後才可準備 archive。

