# Tasks

## 1. 固定 Y05 characterization 與工程 boundary

- [x] 1.1 在 focused BIM Joist test module 建立 whole-source double-C fixtures，逐 root 驗證兩個 C envelopes、兩條 envelope center axes 與 `518.000 mm` axis separation，並確認不使用 428 mm 淨距、441／443.5 mm web spacing、外框距離或 width。
- [x] 1.2 對目前 Y05 DXF 固定完整 characterization baseline：84 個 Beam-layer root `INSERT`，其中 38 個 member roots 形成 20 個 paired assemblies／40 支 paired-axis Joists與六個角落各 3 支共 18 支 Brace-contact single-axis Joists，合計 58 支 formal Joists；其餘 46 個高度重疊 L-angle detail／residual roots不得另建 Beam；另固定 48 組 direct crossing 加 20 組 width-qualified endpoint-face contact 所形成的 68 組 paired-axis-to-Strut relations，逐 relation 記錄 root handle、Strut ID、contact method、source／engineering points、兩個 crossing stations、Column ID、spacing 與 midpoint error，並驗證 observed spacing `518.000–518.001 mm`、midpoint absolute error `0–0.942 mm`。
- [x] 1.3 新增具名 constants 與 pure boundary tests，驗證 spacing 513.0／518.0／523.0 mm 通過、`<513.0`／`>523.0` 拒絕，midpoint -2.0／0／+2.0 mm 通過、absolute error `>2.0 mm` 拒絕，以及 Strut face-contact half-width difference 0／25.0 mm 通過、`>25.0 mm` 拒絕。
- [x] 1.4 新增規則防誤用測試，驗證未經 whole-source geometry 證明的普通 Joist、局部 parallel pair 或未知型式不會套用 double-C 518 mm contract。

## 2. 建立 pure BIM Joist recognition contract

- [x] 2.1 新增小型 pure Joist recognition module 與 immutable source／context／contact／outcome DTO，支援 `not_applicable`、`recognized_single`、`recognized_pair`、`failed`、`ambiguous`，並以 unit tests 驗證不依賴 importer mutable state、Review 或 Presentation。
- [x] 2.2 實作 Beam-role root source eligibility 與 root boundary，驗證不同 root 不跨 source merge、child layer 不改 role、Nested INSERT 使用既有 WCS transform 且保留 outer root provenance。
- [x] 2.3 實作 whole-source longitudinal direction、fragment continuation、terminal extent 與 deterministic normalization，並驗證大 interior gap 不截短完整 axis，child order／LINE direction／candidate order 不改 outcome。
- [x] 2.4 實作 ordinary single-axis outcome，驗證一般 root 最多一支 Beam，且 conflicting whole-source axes 產生 blocking ambiguity 而不回退 local pair。
- [x] 2.5 實作 double-C topology 與兩個 envelope center axes，驗證可靠 root 恰產生一個 paired assembly／兩條 axes，零／一／三條以上或不唯一 envelopes 均為 failed／ambiguous。
- [x] 2.6 更新 module-boundary tests，驗證 pure Joist service 只依賴核准的 DXF models／geometry contracts，未依賴 Tkinter、Dialog、Review Workflow、Application 或 importer instance state。

## 3. 接入 recognition dependency order 與 Beam router

- [x] 3.1 最小調整 `dxf_import/importer.py` staging，使 Joist stage 在 Waler、Strut、Brace、CornerBrace、Column recognition／deduplication／exclusion 完成後執行，並用 stage-order spy test 驗證順序。
- [x] 3.2 從 formal finite Strut／Brace／Column models 建立 immutable `JoistContextSnapshot`，並以 tests 驗證 unresolved、excluded、preview-only sources 不可見且 context 不會創造 Beam axis。
- [x] 3.3 將 Beam-role root `INSERT` 路由至 role-correct BIM Joist service，驗證不會進入 Strut／Brace recognizer；`not_applicable` 才可走 legacy Beam path，`failed`／`ambiguous` 不得 fallback。
- [x] 3.4 更新 `bim-block-member-recognition` regression，驗證 Strut／Brace 既有 restricted paths 與 other-role behavior 不受 Beam router 影響。

## 4. 映射 paired outcome 至 runtime Beam models

- [x] 4.1 將 `recognized_single` staging 為一個既有 Beam candidate，將 `recognized_pair` 原子 staging 為兩個帶共同 root provenance、assembly key 與 normalized axis slot 的 candidates，並驗證 staging 不會留下半個 assembly。
- [x] 4.2 依 normalized WCS axis order 建立兩個 runtime Beam models 與 deterministic BM IDs，驗證 entity reorder、LINE reversal 與 candidate reorder 不交換 sibling 的相對 geometry mapping。
- [x] 4.3 收斂 `_validate_one_model_per_source()` 例外：只放行同一已證明 paired outcome 的 exactly-two complete axis slots；驗證普通 duplicate Beam、缺 slot、第三支 Beam 與偽造相同 method 仍產生 blocking error。
- [x] 4.4 驗證兩個 Beam 各自保有 axis、line candidate、BM ID、crossings 與共同 root `source_handles`／Block provenance，且 Preview 可依 BM ID 分別定位。

## 5. 建立 finite contact 與 Strut／Column pairing

- [x] 5.1 實作 Joist finite axis 對 formal finite Strut／Brace 的 direct 垂直接觸，以及 terminal endpoint 對具可靠 source width formal Strut 的 `endpoint_face_contact`；contact 保存 source／engineering points且不修改 axis，並以 unit tests 驗證真實 segment intersection、精確半寬與 25.0 mm inclusive boundary 通過，一般 infinite extension、內部點 extension、nearest snap、缺寬度、超界、oblique contact、parallel overlap、Brace face contact與非有限交點拒絕，多個合格 Struts 回報 ambiguity。
- [x] 5.2 以兩條 envelope center axes 的 actual Strut crossing stations 計算 spacing，驗證 INSERT point、428 mm、441／443.5 mm、outline distance 與 source width 不會進入 spacing calculation。
- [x] 5.3 實作 same-Strut、opposite-side、`abs(spacing - 518.0) <= 5.0` 與 `abs(midpoint - column_station) <= 2.0` eligibility，並跑 1.3 的 inclusive／超界 boundary tests。
- [x] 5.4 實作 eligibility-first selection，驗證 nearest-but-ineligible pair 不會被選，較遠但唯一 eligible pair 會被採用；「各側最近」不會單獨構成資格。
- [x] 5.5 實作 blocking unpaired／ambiguity outcomes，驗證 missing eligible pair、same-side pair、midpoint 超界與 multiple eligible pairs 分別回報可追溯 problem，且不依 ID／entity order 任選。
- [x] 5.6 保留 Brace-only single-Joist route，驗證唯一 finite Brace contact 不要求第二支 Joist或 518 mm spacing，但不得掩蓋同 source 的 blocking Strut obligation。

## 6. Review、來源排除與恢復

- [x] 6.1 更新 diagnostics／ProblemRecord mapping，使 paired source-level problem 帶 root handle，能唯一歸屬時同時帶兩個 BM IDs；驗證 unresolved、failed、ambiguous、unpaired 與 recognized ReviewItems 顯示正確。
- [x] 6.2 讓 paired siblings 在構件清單維持兩個可選 BM rows，並調整預期 sibling shared-handle handling，驗證不會被誤報為一般來源 ownership conflict。
- [x] 6.3 將 paired confirmation signature 聚合兩個 normalized Beam states、共同 coordinate system 與 assembly problems；驗證確認任一 sibling 會使兩者一致為 confirmed，任一 axis／crossing／association／problem 改變會使兩者一起失效。
- [x] 6.4 維持 source exclusion／restore 的 root-atomic semantics，驗證從任一 sibling 排除會移除兩個 Beam 並只保存一個 excluded source decision，restore 只在 fresh recognition 得到唯一合法 pair 時恢復兩者。
- [x] 6.5 驗證 paired per-axis manual edit 在 live session 仍作用於所選 BM；fresh replay 無法由現有 source identity 唯一配對時回報 `needs_review`，不得依 BM ID、collection order 或 first member 套用。
- [x] 6.6 跑 Pause／Resume、same-fingerprint disk rebuild、changed-fingerprint safety、confirmation invalidation、source exclusion／restore 與 review recovery focused suites，驗證 paired assembly 未破壞既有 lifecycle。

## 7. Project conversion 與 Y05 regression

- [x] 7.1 由每個 validated Beam contact 建立既有 `BeamCrossing`／`ComponentAssociation`，驗證 paired assembly 對同一 Strut 產生兩個不同 BM IDs 與兩個 actual stations。
- [x] 7.2 驗證 `DXFImportResult.to_project_rows()` 將兩個 stations 寫入既有 `BeamPositions`、兩個 IDs 寫入 `AssociatedBeamIDs`，Beam rows 各自保留 crossings；不得輸出 midpoint、單一 assembly ID 或新增 Project schema 欄位。
- [x] 7.3 驗證 failed／ambiguous／unpaired outcome 不會投影 Beam constraint，且既有 Beam exclusion `±550 mm` 分別作用於兩個 validated stations。
- [x] 7.4 執行 Y05 integration regression，驗證 20 個 paired assemblies 映射為 40 支 paired-axis Joists，並逐一比對 68 組 relations 的 root／Strut／contact method／source 與 engineering points／stations／Column，不只比 aggregate count；特別驗證 E8F 大 root 單獨建立兩條 S5～S8 axes、四個重疊小 L-angle roots 不補軸或另建 Beam、E8F／S5 以 endpoint-face contact 投影站位且 source axes 不變，並確認不回退 428、441 或 443.5 mm proxy。
- [x] 7.5 執行六個角落各 3 支、合計 18 支 Brace-contact single-Joist regression，以及 Y05 non-double-C、angle pull rod、detail line 與 unsupported root regressions；驗證 formal Joist 總數為 58，且不會新增幽靈 Beam 或從 failed source 建立局部 Beam。

## 8. 相容性、文件與最終驗證

- [x] 8.1 執行 standalone LINE、MLINE、closed outline、legacy Beam association、BIM Strut、BIM Brace、coordinate transformation 與 candidate correction focused tests，確認非 BIM Joist 行為不變。
- [x] 8.2 執行 DXF input、validation、Review、source exclusion、review recovery、waler contact、double support、Project persistence／conversion suites，修正本 change 引入的 regression，不得降低 assertion 或 skip。
- [x] 8.3 在 implementation 與 tests 通過後更新 `docs/ARCHITECTURE.md`，記錄 production 已實作 Joist immutable upstream context 與 paired-source lifecycle；更新 `docs/DOMAIN.md`，記錄雙 C 518／5／2 mm 工程 contract 與兩個 Beam stations，並驗證文件與 code 一致。
- [x] 8.4 執行完整 test suite 與 `openspec validate contextual-bim-joist-recognition --strict`，確認全部通過後再執行 `openspec-verify-change`，不得修改 Solver 或 Project schema。
