# Design

## Context

目前 `DXFImporter.convert()` 依序處理各工程角色，但 Strut 辨識時只把單一 `_GeometryGroup` 與 `GeometryTolerances` 交給 `recognition.py` 的 root `INSERT` router，再由 `block_member_recognition.py` 以該 root 內的 WCS 子幾何決定正式軸線。Waler 候選雖然較早被放入 `candidates_by_role`，現行 Strut router 並沒有收到 Waler context；而 `_select_waler_inner_lines()` 要到所有角色辨識完後才執行，且會參考 Strut／Brace 端點選擇內側線。因此不能直接把現行的「最終圍令內線」步驟搬到 Strut 辨識之前，否則會形成 Strut 與 Waler contact-face 互相依賴。

`block_member_recognition.py` 現有 topology、legacy full-span、fragmented BIM 與 generic fallback 路徑都以來源幾何本身為主要證據。這對 Y05 S19 的 H 型 BIM block 會產生局部最佳解：root handle `D4B` 的主要橫向站位為 `X = 29326.5、29495.5、29507.5、29676.5`，現行結果採用左半部 `X = 29411`、寬度 `186.5 mm`，而不是整體對稱中心 `X = 29501.5`。這不是單純延長既有局部軸線即可解決，因為圍令只能界定 longitudinal span，不能自行決定正確的 transverse center。

正式構件建立後，`candidate_points.py::connect_components_to_walers()` 只在既有端點附近做關聯／吸附；它不是長距離探索另一端圍令的辨識服務，也不應承擔 source interpretation。Live Review 的 authoritative state 仍由 `DXFReviewWorkflow` 持有，本 change 不改變 Review、Project 或 persistence ownership。

## Goals / Non-Goals

**Goals:**

- 將 DXF member recognition 的長期單向 context dependency 明確定義為 `Waler → Strut → Brace → CornerBrace → Column → Joist`，並以一致的 staged contract 約束後續擴充。
- 在 DXF recognition pipeline 內先建立可供 Strut 使用的正式有限 Waler context，再辨識 component-like BIM Strut。
- 將 topology、legacy full-span 與 fragmented BIM 路徑產生的結果視為可比較的 axis hypotheses；先以兩端有限 Waler 界定預期跨距，再以同一 root `INSERT` 的整體幾何完整性選擇中心軸。
- 容許通過既有 direction、transverse component、width compatibility 與相同 root 邊界檢核的碎片跨越 large interior gap，且不得跨 root 合併。
- 將「缺少第二端圍令」、「圍令配對不唯一」與「沒有完整 root 解釋」保留成可追溯、可 Review 的 blocking outcome，不以 generic fallback 隱藏失敗。
- 保持最終 Waler contact face、構件關聯與後續 candidate point 使用同一份正式幾何 truth。

**Non-Goals:**

- 本 change 不提前實作 `Strut → Brace`、`Brace → CornerBrace`、`CornerBrace → Column` 或 `Column → Joist` 的 contextual recognition；它們只作為 architecture direction。
- 不在本 change 新增 HATCH／RC Waler source recognition；若另一 change 提供額外正式 Waler，本設計只消費其一般 Waler contract。
- 不修改 `bim_minimum_longitudinal_evidence_ratio`、`minimum_projection_overlap_ratio`、`ambiguous_candidate_score_delta` 或既有 candidate credibility／runner-up semantics。
- 不處理重複 Waler／Strut geometry 的一般 duplication policy，也不以新的 50/50、51/49 規則化解 competing axes。
- 不修改一般 LINE／LWPOLYLINE Strut、Brace、CornerBrace、Solver、材料規則、Project schema 或 UI interaction。
- 不以圍令最近距離直接吸附任意斜線，也不允許跨 root `INSERT` 蒐集幾何。

## Architecture Alignment

本 change 沿用既有 DXF subsystem architecture，不改變 Presentation、Application、Domain、Algorithms 或 Infrastructure 的 dependency direction：

```text
DXFImporter（pipeline orchestration）
    → recognition.py（root routing / candidate integration）
        → block_member_recognition.py（pure geometry recognition）
            → models.py / geometry.py
```

在 DXF recognition subsystem 內，member stages 的 dependency direction 定義為：

```text
Waler → Strut → Brace → CornerBrace → Column → Joist
```

這個箭頭代表 recognition stage ordering 與 upstream context visibility，而不只是 importer loop 的排列，也不表示每個 stage 只能依賴緊接在前面的 member type。每個 downstream stage 都可以看到所有已完成 upstream stages 所提供的正式 immutable engineering context：Strut 可使用 Waler；Brace 未來可依需求使用 Waler、Strut；CornerBrace 未來可依需求使用 Waler、Strut、Brace；Column 與 Joist 亦可依需求使用其前方已完成 stages 中適用的 context。這只是允許向前讀取，不要求 recognizer 使用全部 upstream context；各 member 實際採用哪些 context，必須由該 member 未來自己的 OpenSpec change 定義。

前一階段不得依賴、回查或因後一階段的辨識結果而改變其 source recognition truth。每一階段共同遵守：

```text
member source geometry + applicable immutable upstream engineering context
    → pure recognition outcome
```

上游 context 只能提供 span、boundary、connection、support 等 contextual evidence；構件本身的 identity、方向、中心軸、寬度與其他 source-supported facts 仍須由該構件自己的 source geometry 支持。Importer 擁有 staging 與 immutable context snapshot 的組裝責任；pure recognition service 不得回查 `candidates_by_role`、importer global state、`DXFReviewWorkflow` 或 Presentation state。

本 change 只把上述 contract 落實到 `Waler → Strut`。Brace、CornerBrace、Column、Joist 仍沿用目前 behavior；不得為了預留未來而建立通用 framework、修改其 router 或增加 production dependency。

受影響責任如下：

- `dxf_import/importer.py`：負責 Waler-first staging、建立 immutable recognition context、依序協調 Strut recognition 與既有後處理。
- `dxf_import/recognition.py`：負責將單一 Strut root 與該次 import 的 Waler context 傳入 pure service，並把 outcome 轉成既有 candidate／validation contract。
- `dxf_import/block_member_recognition.py`：負責 axis hypothesis、有限交點、Waler-bounded corridor 與 whole-root completeness 等 pure geometry rule；不得依賴 importer、Review workflow 或 Tkinter。
- `dxf_import/models.py`（僅在需要具名 tolerance 或 immutable DTO 時）：提供 DXF recognition 的資料 contract，不建立 Project schema 欄位。

這是既有 layer architecture 內的 pipeline refinement，同時新增 DXF subsystem 內正式的單向 recognition dependency order，不建立跨 layer dependency。實作完成且驗證後應更新 `docs/ARCHITECTURE.md`：記錄完整 dependency direction，但清楚區分目前只落實 `Waler → Strut`；在 implementation 成立前不先把長期文件寫成既定事實。

重要 single source of truth：

- root source geometry：該 `_GeometryGroup` 內經 OCS/WCS 正規化的 child geometry 與 root provenance。
- Waler identity／finite geometry：`candidates_by_role["waler"]` 中已辨識、未排除、去重後的 Waler candidates。
- 最終 Waler contact geometry：沿用同一個既有 contact-face selection／adjustment path 產生的 canonical Waler geometry；不得另存一套僅供 BIM Strut 使用且會與正式 Waler 漂移的「內線」。
- 正式 Strut axis：contextual recognition 成功後產生的唯一 `_Candidate`；diagnostics、ReviewItems、關聯與 Project rows 都從這個 candidate 投影，不各自重算。

## Decisions

### 1. Recognition dependency 是單向 staged contract

`DXFImporter` 以固定 dependency order 協調各 member recognition stage。每一 stage 只接收自己的 source geometry、tolerances，以及從所有已完成 upstream formal outcomes 中選出的 applicable immutable context snapshot；這不是只能接收相鄰上一 stage 的 context，也不代表必須接收全部可見 context。stage 內的 pure service 不持有共享 mutable candidate map，也不能觸發其他 stage 重跑。

本 change 實際建立的 stage boundary 為：完成 Waler source recognition、exclusion 與 deduplication後，凍結 Waler context snapshot，再辨識 Strut。未來若個別 change 導入後續 contextual dependency，必須依序擴充同一 contract，而不能建立反向捷徑。

downstream result 若影響接觸面、端點或關聯，統一交由 recognition stages 之後的 canonical finalize／relationship stage 處理。該 stage 可以從已辨識 identities 計算 derived connection geometry，但不得偷偷重新辨識、替換或刪除 upstream member identity，也不得把 derived relation 回灌成上游 source truth。

**拒絕方案：** 只把 dependency order 當成 `for role in ...` 的執行順序。若沒有 immutable context contract 與禁止反向 mutation 的規則，未來仍會形成隱性 global-state dependency。

**拒絕方案：** 為六個階段立即建立抽象 pipeline framework。現階段只有 `Waler → Strut` 有 production requirement，提前抽象會擴大 scope 並迫使其他 recognizers 改動。

### 2. 將 Waler recognition 與 contact-face finalize 拆成兩個明確階段

Importer 先完成 Waler source recognition、exclusion 與 deduplication，建立每支正式 Waler 的有限 reference geometry 及可用 boundary/contact alternatives；接著才處理 Strut root `INSERT`。Strut contextual recognition 以這些有限幾何判定哪兩支 Waler 能 bracket source，並記錄選定的 Waler identities。待 Strut／Brace candidates 已存在後，再呼叫既有共用 Waler inner/contact-face selection，得到正式接觸面與最終交點。

為避免兩份 truth，前段 context 只負責「有限交點資格、bracketing 與 Waler identity」，後段仍是唯一的 contact-face finalizer。整合時必須確認 finalizer 選到的 contact geometry 仍屬於前段選定的兩支 Waler；若不一致，回報 blocking diagnostic，不可默默更換配對。

**拒絕方案：** 在 Strut 之前直接執行現有 `_select_waler_inner_lines()`。該函式目前以 Strut／Brace 端點作為主要 interior reference，提前執行會改變既有 Waler 行為並製造循環依賴。

**拒絕方案：** 讓 `connect_components_to_walers()` 負責延伸。它位於正式構件建立後，且語意是 proximity association，不足以判斷完整 BIM source。

### 3. 以 immutable Waler context 傳入 pure recognition service

新增小型、DXF-internal 的 immutable context DTO（名稱可依現有命名調整，例如 `WalerSpanReference`），至少包含 Waler candidate identity、有限 reference segment，以及選擇最終 contact face 所需的 boundary alternatives／provenance。Router 只會把同一次 import 中正式、未排除、已去重的 Waler context 傳入 Strut service。

`block_member_recognition.py` 不查詢 importer global state，也不讀 `candidates_by_role`；輸入與輸出保持可單元測試。若既有 `BlockMemberRecognitionInput` 不適合承載場域 context，建立一個窄的 request/context 參數即可，不建立通用 recognition framework。

**拒絕方案：** 在 pure service 內回呼 importer 或 Review workflow 取得 Waler。這會逆轉 DXF subsystem dependency，並讓 headless tests 與 replay 不可重現。

### 4. 先產生 axis hypotheses，再套用 Waler 與 whole-root constraint

現有 topology、legacy full-span 與 fragmented BIM 路徑保留各自的 source eligibility 與證據計算，但 component-like Strut 不再由第一條成功路徑立即定案。各路徑輸出 deterministic axis hypothesis，至少保留：

- longitudinal direction 與 transverse center；
- source-supported width／rail evidence；
- 使用的 primitive identities 與 root identity；
- 既有 credibility inputs 與 recognition method provenance。

Waler-bounded filtering 完成後才把唯一合法 hypothesis 轉成正式 outcome。現有 0.5 evidence ratio、0.8 projection overlap 與 0.03 ambiguity tolerance 的定義與順序不改；本 change 增加的是這些 gate 之前的場域 eligibility／completeness constraint。

非 component-like INSERT 維持 `not_applicable`，可走原本 generic recognition。已判定為 component-like 的 root 若 contextual stage 失敗，必須得到 `failed/ambiguous`，不可退回 generic local pair。

**拒絕方案：** 保持「topology 成功就 return、否則 legacy、fragment、fallback」的 first-success routing。S19 的錯誤正是局部 hypothesis 過早變成正式結果，後續已無法比較整體解釋。

### 5. Waler span 只由候選軸與有限 Waler segment 的有效交點建立

對每個 axis hypothesis，沿其 longitudinal line 計算與每支正式 Waler 有限 reference segment 的交點及 signed longitudinal station。只接受實際落在有限 segment（含既有數值 tolerance）的交點；不得以 Waler 無限延長線或單純 Euclidean nearest distance 代替。

以 root source longitudinal projection 為中心，在正、負兩個 outward direction 各選最近且唯一的一支 Waler。`nearest` 只在候選先通過正式 Waler、有限交點、方向與外側資格後使用。任一側沒有候選，或同一側在既有數值容差內出現不可唯一決定的候選，該 hypothesis 不能形成正式 span，並產生具 Waler／root provenance 的 blocking reason。

兩端 Waler intersection 建立 expected longitudinal span；它不決定 transverse center。這可避免 Waler 本身「支持」任一條平行偏移軸而誤選 S19 左半部。

### 6. 以 Waler-bounded corridor 驗證 whole-root completeness

對已建立兩端 Waler span 的 hypothesis，在同一 root `INSERT` 內形成沿 axis 的 corridor，重新評估可歸屬於該 Strut 解釋的 longitudinal evidence。幾何片段必須先通過現有方向、transverse component、width compatibility、minimum length／slenderness 等 eligibility，才可納入；不得為了填滿 corridor 放寬既有工程門檻。

completeness 至少驗證：

- corridor 兩側的主要 rail／outline evidence 是否能以同一 transverse center 與合理 envelope 成對解釋；
- 從第一支到第二支 Waler 的主要 longitudinal evidence 是否達到既有 coverage gate；
- 是否存在與候選同方向、足夠長、屬於同一結構截面但落在 envelope 外的大量未解釋 evidence；
- large interior gap 是否只是已通過 eligibility 的同一組 rail fragments 之間缺線，而不是跨 component／跨 root 拼接。

S19 的 `X = 29411` hypothesis 只解釋左側 rail pair，會留下右側主要 longitudinal rails，因而被 whole-root completeness 淘汰；`X = 29501.5` 能對稱解釋 `29495.5／29507.5` 內側細節與 `29326.5／29676.5` 外側截面證據，才可進入既有 credibility gates。`186.5 mm` 的內部 rail separation 不得直接成為正式支撐 envelope width。

**拒絕方案：** 只把現行 S19 軸沿 longitudinal direction 延長到兩端 Waler。這會保留錯誤的 `X = 29411` transverse center，只修長度、不修偏移。

**拒絕方案：** 選離 Waler 中心最近的平行軸。兩端圍令提供 span 約束，沒有足夠資訊單獨決定 H 型截面的中心。

### 7. Fragment continuation 保持 source eligibility 優先

fragmented BIM 路徑可沿 longitudinal direction 持續加入同 root 的 eligible fragments，large interior gap 不再直接截斷 whole span。若同一延伸方向有多個已通過 eligibility 的 continuation，才以 longitudinal gap 最近者作 deterministic selection；「最近」不得越過 direction、transverse component、width compatibility 或 root boundary。

此選擇只處理單一 hypothesis 內的 fragment continuation，不修改不同 complete hypotheses 之間的 ambiguity policy，也不處理重複 Waler／Strut geometry。

### 8. Outcome、diagnostics 與 downstream geometry 使用同一正式結果

contextual service 維持三態語意：

- `not_applicable`：不是 component-like BIM Strut，可走一般流程；
- `recognized`：有唯一 Waler pair、唯一 whole-root axis，且既有幾何 gate 全部通過；
- `failed/ambiguous`：缺少有效 Waler span、Waler pairing 不唯一、root completeness 不足或完整 axes 仍衝突。

失敗 outcome 必須帶 root handle、source handles、候選 Waler identities 與 reason code，使 importer 透過既有 ValidationMessage／ReviewItem lifecycle 顯示，不增加第二套 navigator。exclusion、restore、manual override replay、confirmation invalidation、pause/resume 仍由既有 workflow 根據 source fingerprint 與正式 result 重建。

正式 Strut candidate 的端點以選定 Waler pair 的 canonical contact geometry 為準；後續 candidate points、`connect_components_to_walers()`、構件關聯、材料辨識與 Project row conversion 只讀這份 candidate，不重新推導另一條軸。

### 9. Y05 S19 直接驗證 Waler-constrained whole-root recognition

S19 的 Waler 缺漏已由其他 change 解決，因此本 change 的 actual-file integration test 直接消費目前 pipeline 提供的兩端正式有限 Waler，驗證 S19 H geometry 選到 `X = 29501.5` 且不回退 `X = 29411`。此外保留 pure service／synthetic fixture，以隔離驗證 whole-root completeness，不讓測試只依賴特定 DXF 檔案狀態。

本 change 不重複實作或特判上游 Waler source recognition。若 actual-file fixture 無法提供兩端正式 Waler，這代表依賴的 upstream change 尚未整合或發生 regression，測試應直接失敗並回報 dependency，不把它改寫成本 change 的 alternate acceptance path。

## Backward Compatibility and Persistence

- 非 component-like INSERT 與一般 line/polyline recognition 保持原行為。
- 已能由唯一 whole-root axis 與兩端 Waler 支持的 BIM Strut，其 public `DXFImportResult`／Project rows contract 不變；recognition method metadata 可新增具體值，但不改 schema。
- component-like BIM Strut 若沒有兩端正式 Waler，會由過去可能產生局部 formal member 改成 blocking unresolved item；這是刻意的安全性收緊，避免錯誤幾何進入工程模型。
- 不新增或修改 Project persistence 欄位，不需要 migration。Paused review 從 DXF source 與既有 persisted decisions 重建 derived recognition，沿用現行 source fingerprint safety。
- Manual correction、diagnostics 與 preview 均消費既有 candidate／ReviewItem contract，不各自實作 Waler-bounded 判斷。

## Risks / Trade-offs

- **[Waler reference geometry 與最終 contact face 可能不一致]** → 前段只鎖定有限 Waler identity，後段沿用單一 canonical contact-face helper；identity 或有效交點不一致時 fail closed。
- **[whole-root completeness 可能把裝飾線誤當主要 evidence]** → 只有通過既有 direction、length、transverse、width 與 component eligibility 的 longitudinal evidence 能參與 completeness；針對短 detail lines 加負面測試。
- **[大型 gap 的容許可能誤連不相干片段]** → 嚴格限制同 root、相容 transverse component／width 與兩端 Waler corridor；nearest gap 只用於合格候選排序。
- **[staged importer 改動可能影響既有 Waler inner-line 選擇]** → 保留現行 finalizer 與既有 Waler/contact tests，新增 stage-order regression，確認只有 Strut recognition 多收到 context。
- **[完整 dependency order 被誤解為本 change 要實作所有 contextual recognizers]** → tasks 與 tests 只修改 `Waler → Strut`；其餘 stages 只更新 architecture direction，不建立 production callback、DTO 或 fallback。
- **[downstream finalize 反向改寫 upstream recognition truth]** → 將 recognition outcome identity 與 derived relationship geometry 分離；finalize 只能引用既有 identities 並產生 canonical relation，不得觸發 upstream re-recognition。
- **[候選數增加造成效能下降]** → hypothesis 與 corridor 評估限定單一 root INSERT，Waler context 先以 bounding box／方向作 deterministic prefilter；不建立全圖跨 root 組合搜尋。

## Migration Plan

1. 先以 characterization tests 固定現行一般 block、Y05 S2、S19 偏移原因，以及上游已提供兩端正式 Waler 的整合前提。
2. 引入 internal Waler context contract 與 finite-intersection tests，不改 public result schema。
3. 將 importer 調整為 Waler source stage → immutable Waler context snapshot → contextual Strut stage → existing canonical contact／relationship finalize → existing downstream stages，並以測試禁止反向 mutation。
4. 將 component-like Strut router 接到 hypothesis／corridor service，保留非 component fallback。
5. 執行 DXF focused tests、workflow／persistence regressions與完整 suite；實作成立後在 `docs/ARCHITECTURE.md` 記錄完整 dependency direction及目前僅落實 `Waler → Strut`。

Rollback 可移除 staged context wiring 與 pure contextual filter，恢復既有 source-only router；因無 persistence migration，既有 Project 檔不需資料回復。
