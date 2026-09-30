# Tasks

## 1. 現況與實際圖檔 Characterization

- [x] 1.1 在 DXF focused tests 補充 Y05 W7 root `C86` 的 source characterization，鎖定四條主要 longitudinal rails（約 `y=8800/8781/8469/8449`）、provisional axis、W7／W12 source identities 與既有 contextual Strut facts；執行該 focused test確認 fixture 能穩定重現，不把目前錯誤 selected face 寫成期望行為。
- [x] 1.2 補充 Y1A W1～W4 一般 CAD contact-face baseline，以及 single-line、一般 outline、HATCH RC、BIM contextual Strut 與 Brace direct／extension 的現況 characterization；執行相關 `tests/test_dxf_input.py`、`tests/test_dxf_hatch_waler_recognition.py`、`tests/test_dxf_bim_block_recognition.py` 與 `tests/test_dxf_brace_waler_extension.py` focused cases確認 baseline。
- [x] 1.3 建立 envelope component-scope synthetic corpus，涵蓋同 group 相接雙 Waler、同方向多 component、跨 component raw min/max、兩個以上不等價完整 envelope interpretations及 W7／W12 分離案例；驗證 fixtures可證明「分離 interpretations或blocking ambiguity」，且不把同 layer／GeometryGroup／相接／平行／等長／coverage重疊單獨當成component identity。
- [x] 1.4 建立 side-evidence characterization corpus，量測垂直 body vector、平行 body vector、長 member 且normal component略高於 `endpoint_tolerance_mm`、短 member 且normal component略低於該值，以及Y05 W7／Y1A實際 body-vector total length／normal component ranges；輸出可重複測試資料，先不把 `endpoint_tolerance_mm` 宣告成正式side threshold。
- [x] 1.5 建立 synthetic 等價 CAD／BIM、多 rail、相反 start/end、entity order permutation、無 side evidence與兩側衝突 fixtures；確認 fixtures只表達 Spec geometry，不依賴 production candidate enumeration order。

## 2. Pure Waler Envelope Facts

- [x] 2.1 在 `dxf_import` 新增小型 pure contact-face module及 runtime-only frozen records，分離 Waler provisional reference、完整 envelope outer faces、single-line contact與 provenance；以 import／type-focused tests確認沒有 Presentation、Project、persistence 或 Solver dependency。
- [x] 2.2 在一般 Waler parallel-pair collapse前，先由 normalized WCS evidence建立並驗證一個或多個 qualified component scopes，再只於各scope內建立完整 envelope；使用既有具名 tolerances，並以 synthetic four-rail、internal-detail、short-local-pair、fragment／duplicate及 HATCH exterior tests驗證 outer faces不被縮小。
- [x] 2.3 驗證同 group 相接雙 Waler、同方向多 component、跨 component raw min/max及多個完整 envelope interpretations不會被合成假 envelope；能唯一分離時輸出多個component facts，不能唯一分離時輸出blocking ambiguity，並確認W7／W12 extraction scopes保持分離。
- [x] 2.4 實作 deterministic geometry normalization，並以 LINE start/end、POLYLINE traversal、source entity order、duplicate evidence及 canonical normal反轉 permutations驗證等價 geometry產生等價 envelope facts。
- [x] 2.5 保留 standalone Waler LINE 的 single-contact-line compatibility及 HATCH RC 不受一般 `maximum_component_width_mm` 限制的 contract；執行 focused tests確認不製造虛構 envelope或修改 material classification。

## 3. Pure Terminal Topology 與 Contact Resolver

- [x] 3.1 建立 pure `MemberTerminalEvidence`／terminal-to-Waler topology adapter：保留 BIM contextual Strut 已選 source identity，一般 Strut只沿用既有 direct relation，Brace沿用既有 250 mm direct與600 mm outward extension／ambiguity policy；以 role-focused unit tests驗證不新增 Strut extension或改派既有 identity。
- [x] 3.2 根據Task 1.4結果完成side-evidence setting mapping：只有 `endpoint_tolerance_mm` 可穩定區分valid／degenerate時才重用；否則先建立具名internal recognition setting、以characterization選定可解釋預設值並同步更新Spec／Design，禁止magic epsilon或未命名ratio。
- [x] 3.3 實作由 provisional Waler intersection朝 member body的向量與 canonical Waler normal判定支撐側；以perpendicular／parallel、長短member邊界、Y05 W7／Y1A ranges、等價CAD／BIM、member start/end反轉、Waler direction反轉及無關member增刪 tests驗證結果與來源路徑／輸入順序無關。
- [x] 3.4 實作支撐側 outermost physical face resolution，並以 W7 synthetic four-rail案例驗證選 `y=8449`、不選 `8469/8781`，同時以反側案例驗證選相反 outer face。
- [x] 3.5 實作 `WALER_ENVELOPE_UNRESOLVED`、`WALER_ENVELOPE_AMBIGUOUS`、`WALER_CONTACT_FACE_UNRESOLVED` 與 `WALER_CONTACT_FACE_AMBIGUOUS` pure outcomes；以多完整envelope interpretations、no-evidence、opposite-side evidence、degenerate vector及多Waler topology tests驗證blocking behavior且沒有majority／order／centroid fallback；no-evidence時provisional reference axis只供diagnostic、不得成為formal contact face，Import維持blocked。
- [x] 3.6 執行 pure module完整 unit suite，確認全部通過後才開始 production importer routing；若characterization要求現有 `GeometryTolerances` 以外的 threshold，確認Task 3.2的具名setting與planning更新已完成，不得加入未命名magic number。

## 4. Recognition Pipeline 與 Staged Finalization

- [x] 4.1 調整 Waler candidate建立，讓 source recognition保留 provisional axis與完整 envelope facts而不先選 contact face；執行 Waler recognition tests確認 recognition winner、source width、method、handles與root provenance不被 contact logic改寫。
- [x] 4.2 在 Column source recognition完成後、Joist context建立前，以 staged方式接上 terminal topology與contact resolver，取代 `_select_waler_inner_lines()` 的 global endpoint-distance scoring；以 orchestration tests驗證 `Waler → Strut → Brace → CornerBrace → Column → Joist` 單向 ordering且沒有 finalization-to-recognition回邊。
- [x] 4.3 以單一 `WalerContactResolution` map原子套用正式 Waler faces與 contextual Strut endpoints；以成功、部分 resolver failure及 apply exception tests驗證不留下 Waler已換 face但Strut仍指向 provisional axis的半更新狀態。
- [x] 4.4 將 Brace direct／extension connection改為先取得 provisional Waler identity、再使用同一 selected face完成正式 endpoint；執行既有 Brace 250／600 mm boundary與ambiguity regression，確認不改變 Brace recognition axis、width或provenance。
- [x] 4.5 保留 CornerBrace canonical refinement與Joist context在contact finalization之後消費正式 geometry；執行相關 focused tests確認 source recognition winner不被重跑或改派。

## 5. Review、CandidatePoint 與 Downstream Consistency

- [x] 5.1 將 resolver failures映射至既有 `ValidationMessage`／ProblemRecord／ReviewItem，包含 Waler及衝突 member provenance；執行 Review validation tests確認 unresolved contact阻止完成 import但仍可預覽來源。
- [x] 5.2 讓 Waler formal model、Strut／Brace connection、CandidatePoint、association與diagnostics只消費已提交的 contact resolution，不各自重算 side；以 cross-output assertions確認同一 Waler identity與同一 WCS contact point。
- [x] 5.3 驗證 Source Exclusion／Restore、manual override replay、confirmation invalidation與recognition rebuild會重建resolution且不保留 stale relation；執行對應 workflow focused tests。
- [x] 5.4 驗證 Pause／Resume、fingerprint safety與completed DXF → Project conversion沿用既有 contract，且 Project payload／Solver input沒有新增 envelope或diagnostic欄位；執行 round-trip及metadata-isolation tests。

## 6. 實際案例與 Regression

- [x] 6.1 以指定 Y05 DXF 執行 W7／W12 regression：envelope extraction先維持兩個qualified component scopes，W7選支撐側 outer face `y≈8449`、W12保留獨立 identity，且W7 endpoint不再因舊19 mm假接近產生W12競爭warning；保存可重複的 focused assertion。
- [x] 6.2 執行 Y1A W1～W4 regression，確認一般 CAD最終 contact faces與原本正確結果等價，並驗證 CAD／BIM不同來源畫法不會改變共用 side rule。
- [x] 6.3 執行 HATCH RC、BIM Strut、BIM Brace、Brace extension、CornerBrace、CandidatePoint、double-support與一般非 BIM DXF regression，確認本 change沒有擴大至來源 recognition、材料、CandidatePoint工程規則或Project schema。
- [x] 6.4 補充 deterministic final-outcome permutations，涵蓋 Waler／member collection order、source entity order、LINE start/end、POLYLINE traversal與等價 duplicate，確認status、selected face、connections與diagnostics等價。

## 7. 文件與最終驗證

- [x] 7.1 實作與 regression穩定後，最小幅度更新 `docs/WORKFLOW.md` 的 DXF recognition／contact finalization現況，記錄 source recognition先完成、共用 support-side outer-face resolution與blocking ambiguity；確認不提前修改 Domain／Solver truth。
- [x] 7.2 重讀 `docs/ARCHITECTURE.md`，確認現有 cumulative upstream visibility與post-recognition canonical finalization描述仍準確；若實作未改變 architecture truth則不修改該文件，並以 architecture boundary tests驗證 pure service不依賴Presentation／Project／Solver。
- [x] 7.3 先執行全部受影響 DXF focused tests，再執行專案完整 regression suite，記錄指令、通過／失敗數與任何既有 failure；不得降低 assertion或刪除測試。
- [x] 7.4 執行 `openspec validate unify-waler-contact-face-recognition --strict`，逐項核對 Spec scenarios、Design boundaries與本 Tasks完成狀態，並使用 OpenSpec implementation verification流程確認沒有 unresolved blocker後才允許封存。
