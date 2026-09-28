# Tasks

## 1. Characterization 與測試基線

- [x] 1.1 在 `tests/test_dxf_bim_block_recognition.py` 增加 Y05 S19 root `D4B` 的來源幾何 characterization，固定主要 X stations、現行局部 `X = 29411` 偏移原因，並驗證目前上游流程已提供兩端正式有限 Waler；若 dependency regression 造成 Waler 缺漏，測試必須直接失敗而非採用替代驗收路徑。
- [x] 1.2 建立具有兩端有限 Waler 的 S19-like synthetic fixture，固定期望中心 `X = 29501.5`、拒絕 `X = 29411` 與拒絕 `186.5 mm` 局部 rail separation；確認新測試在功能實作前能重現失敗。
- [x] 1.3 補齊現有一般人工 CAD `INSERT`、完整 outline BIM Strut 與 Y05 S2 約 `18,900 mm` whole-axis 的 characterization tests，確認後續重構不能改變非目標 fallback 或讓 S2 退回約 `6,978 mm` 局部軸。

## 2. 單向 Waler → Strut Staging Contract

- [x] 2.1 在 `dxf_import` 既有 models／recognition 邊界新增小型 immutable Waler span reference contract，包含正式 Waler identity、有限 reference segment、boundary alternatives 與 provenance；以單元測試確認 excluded、unresolved、preview-only geometry 不會進入 context。
- [x] 2.2 在 `dxf_import/importer.py` 將既有流程明確分成 Waler source stage、immutable Waler context snapshot 與 Strut stage；以 importer regression 驗證 Strut 只能消費已完成的 Waler context，Waler candidates、source counts 與 diagnostics 不因 Strut outcome 被反向修改。
- [x] 2.3 保留 `_select_waler_inner_lines()` 作為唯一 final contact-face 路徑，新增 stage-order／identity consistency tests，確認前段 context 不建立第二套內線 truth，且 final contact geometry 不得默默換成另一支 Waler。
- [x] 2.4 增加 architecture／boundary tests，驗證 pure Strut recognition 只接受 `source geometry + applicable immutable Waler context`、不回查 importer／`candidates_by_role`／workflow state；同時確認本 change 未替 Brace、CornerBrace、Column、Joist 新增 DTO、router modification、callback 或通用 recognition framework。

## 3. Axis Hypothesis 與既有 Gate 保留

- [x] 3.1 在 `dxf_import/block_member_recognition.py` 將 component-like Strut 的 topology、legacy full-span 與 fragmented BIM 成功結果整理成 internal deterministic axis hypotheses，保留 root／primitive provenance 與既有 credibility inputs；以既有 path-specific tests 驗證來源證據沒有遺失。
- [x] 3.2 調整 `dxf_import/recognition.py` 的 Strut root router，使其接收並傳遞 Waler context，但 Brace 與其他角色維持原 contract；以 router tests 驗證 root entity 必須為 `INSERT`、role 必須為 `strut` 且每個 root 獨立處理。
- [x] 3.3 維持 `bim_minimum_longitudinal_evidence_ratio = 0.5`、`minimum_projection_overlap_ratio = 0.8` 與 `ambiguous_candidate_score_delta = 0.03` 的既有數值與 runner-up semantics；以現有 threshold boundary tests 及新增 ordering assertions 驗證 contextual filter 位於既有 gates 之前但未改寫 gates。

## 4. Finite Waler Span Selection

- [x] 4.1 在 pure recognition service 實作 axis line 與有限 Waler segment 的交點、signed station 與 outward-side eligibility；以幾何單元測試驗證真正有限交點可用、只碰到 Waler 無限延長線不可用。
- [x] 4.2 對每個方向只在通過正式 Waler 與有限交點資格後選擇 nearest outward Waler，並在缺少任一側或同側無法唯一決定時產生 typed failed／ambiguous reason；以 tests 覆蓋唯一兩端、一端缺漏及 competing outward Walers。
- [x] 4.3 將選定 Waler identities、交點與 failure provenance 帶回既有 recognition outcome／ValidationMessage contract；以 ReviewItem integration test 驗證 source handle 與 Waler context 可追溯，且不新增第二套錯誤 navigator。

## 5. Waler-Bounded Whole-Root Completeness

- [x] 5.1 在 `dxf_import/block_member_recognition.py` 以兩端 Waler span 建立 longitudinal corridor，僅納入同 root 且通過既有 direction、transverse component、width、length／slenderness eligibility 的 evidence；以負面測試確認短裝飾線、錯向線、寬度不相容線與不同 root 不會被合併。
- [x] 5.2 實作 whole-root completeness，拒絕只解釋單側 rail 而留下大量主要 longitudinal evidence 的 half-section hypothesis，並以 S19-like fixture 驗證唯一選出約 `X = 29501.5` 的完整中心軸。
- [x] 5.3 讓 fragmented BIM continuation 可跨 large interior gap，但同方向有多個合格 continuation 時只以 longitudinal gap 最近者排序；以 tests 驗證 eligibility 先於 nearest、不得跨 root，且 Y05 S2 保留約 `18,900 mm` whole axis。
- [x] 5.4 將唯一通過 completeness 的 hypothesis 再交給既有 credibility／ambiguity gates；以 tests 驗證兩個近似可信的完整 axes 仍為 blocking ambiguity，而非新增 runner-up policy 或任意 first occurrence 選擇。

## 6. Importer 整合與 Downstream 一致性

- [x] 6.1 將 contextual Strut outcome 整合回 `_Candidate` 建立流程：`recognized` 建立唯一正式 Strut，`failed/ambiguous` 保留 root source 並阻擋 generic fallback，`not_applicable` 才回到一般 recognition；以三態 integration tests 驗證每個 root 最多一個 formal model。
- [x] 6.2 以選定 Waler pair 的 canonical contact geometry finalize 正式 Strut endpoints，並讓 candidate points、`connect_components_to_walers()`、工程關聯、材料辨識與 Project row conversion 消費同一 candidate；以 endpoint／association tests 驗證沒有第二次軸線推導。
- [x] 6.3 驗證 actual Y05 使用目前上游已提供的兩端正式 Waler context，S19 產生約 `X = 29501.5` 的完整中心軸、保留兩端 Waler provenance，且不得產生約 `X = 29411` 的偏移 formal Strut；上游 Waler 缺漏應視為 regression 並使測試失敗。
- [x] 6.4 執行 exclusion／restore、manual override replay、confirmation invalidation、pause/resume 與 source fingerprint tests，確認 contextual recognition 重建仍沿用既有 `DXFReviewWorkflow` lifecycle，且 persistence schema 無變更。

## 7. 文件、回歸與 OpenSpec 驗證

- [x] 7.1 在功能與測試成立後更新 `docs/ARCHITECTURE.md`，記錄 `Waler → Strut → Brace → CornerBrace → Column → Joist` 代表 stage ordering 與累積 upstream context visibility、不是僅能依賴相鄰前一 stage；每階段遵守 `source geometry + applicable immutable upstream context → pure outcome`，實際使用的 context 由各 member 未來 change 定義，並明確註記目前 production 只落實 `Waler → Strut`、後續 stages 尚未實作。
- [x] 7.2 執行 `tests/test_dxf_bim_block_recognition.py`、`tests/test_dxf_input.py` 與相關 waler contact／review workflow／architecture boundary tests，修正本 change 造成的 regression，且不得刪除測試、降低 assertion 或以 skip 排除失敗。
- [x] 7.3 執行完整 test suite，確認 Solver、材料、Project persistence 與非 BIM DXF import 均維持綠燈，並記錄任何不屬於本 change 的既有失敗。
- [x] 7.4 執行 `openspec validate waler-constrained-bim-strut-recognition --strict` 與 OpenSpec implementation verification，逐項核對 proposal、delta spec、design、tasks 與實際測試證據後再交付。
