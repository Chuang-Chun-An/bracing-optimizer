# Design

## Context

本設計處理 proposal.md 所述的 BIM Strut transverse center 候選資格與採用順序。現有 pure recognition service 已有三類可用 evidence：`Topology / connected contour`、`Whole-root outer-envelope`、`Local fragmented rail-pair`，但目前有兩個關鍵缺口：

1. `_connected_line_contours()` 以 endpoint tolerance 建立 topology nodes，但 `_topology_member_from_contour()` 後續以 raw floating-point coordinates 的精確 `set()` 重新去重。Y05 S11 `D19` 的有效四邊外框因此留下 5 個 point samples，其中一個角點被重複加權，造成傾斜中心與約 408.34 mm 寬度。
2. `_recognize_contextual_strut()` 先取得 source-only outcome；只要 local rail-pair 已被判為 recognized，後續所有不等價的 whole-root candidates 就會被 authority guard 過濾。Y05 S20 `B05` 因而保留約 `X=53379.0` 的局部中心，而未採用已存在的約 `X=53469.5` whole-root envelope。

Y05 root `957` 與 `B05` 的 whole-source geometry 互為鏡像：兩者皆具有 350 mm 的合格 whole-root outer-envelope，也皆具有偏向內側約 90.5 mm、寬約 204 mm 的 local rail-pair。舊 regression 只保護 `957` 的 local center，造成鏡像來源得到不對稱結果；這不是可用的幾何判別。因此本 change 明確把兩者都交由相同 Tier 2 authority contract，分別得到約 `X=-53469.5` 與 `X=53469.5`。

Waler context 已可建立有限 longitudinal span 並驗證 corridor completeness。它不應成為 transverse center 的來源，也不應與獨立 change `unify-waler-contact-face-recognition` 的接觸面 finalization 混合。

## Goals / Non-Goals

**Goals:**

- 對 Strut contextual recognition 建立明確、可測試且 deterministic 的三層 center authority。
- 讓 topology adjacency 與 outline axis／width 使用同一組 canonical tolerance-clustered nodes。
- 阻止 branched connected graph 直接取得完整外框資格。
- 分離 axis equivalence grouping 與 envelope width reconciliation，使 center 唯一、width 未知可以成為合法結果。
- 確保 Tier 2 只由通過完整構件資格的 boundary evidence 建立，不使用 raw transverse extremes。
- 在 local rail-pair 鎖定中心前，讓唯一可靠的 whole-root envelope 參與 reconciliation。
- 保留現有 terminal outcome、WCS/root provenance、diagnostics 與 importer lifecycle contract。

**Non-Goals:**

- 不新增第四種中心算法，也不以 Waler、`INSERT` point 或個別 DXF handle 猜中心。
- 不調整既有 credibility、overlap、ambiguity 或 maximum width 數值。
- 不修改 Brace、CornerBrace、Column、Joist、Solver、Project schema、persistence 或 UI。
- 不處理 Waler contact face／backfill side 的選擇。

## Architecture Alignment

本 change 沿用既有 Architecture，不建立新的 layer 或跨層 dependency。

- **Infrastructure / DXF recognition**：`dxf_import/block_member_recognition.py` 繼續接收單一 root 展開後的 WCS primitives 與 immutable formal Waler context，回傳 pure `BlockMemberRecognitionOutcome`。
- **Importer adapter**：維持 root `INSERT` 邊界、role routing、diagnostic conversion 與 Review lifecycle；不在 importer 重新計算中心。
- **Domain / Algorithms / Presentation**：不受影響；不複製 recognition 規則。

依賴方向仍為：

```text
same-root WCS source geometry + immutable upstream Waler context
    → pure Strut recognition outcome
    → importer / review conversion
```

唯一工程 truth 仍是 pure recognition outcome 內的 canonical source axis，以及經獨立 envelope reconciliation 後得到的 `representative_width`／既有 unknown-width 表示。兩者不得因候選資料結構方便而被視為不可分割的同一 winner 欄位。Waler contact finalization 只能消費此 axis，不得另建第二套 transverse center truth。

## Decisions

### 1. 將 candidate family 與 candidate qualification 分開

保留現有三種 candidate generation，不新增幾何算法；在 Strut contextual route 中加入內部 evidence tier／qualification 語意：

| 優先層 | 現有 candidate family | 取得 authority 的條件 |
|---|---|---|
| 1 | Topology / connected contour | 候選 boundary 可獨立驗證為完整、無分支的外框；其 center 與 width 由該 boundary 自身支持 |
| 2 | Whole-root outer-envelope | 沒有 tier 1 winner，且同一 root 的 outermost longitudinal evidence 在 Waler-bounded corridor 內唯一支持完整中心與 envelope |
| 3 | Local fragmented rail-pair | tier 1、2 均無合格候選，且既有 local eligibility 與 ambiguity rules 可唯一辨識 |

「優先」不是額外加分。每一層先只按既有 axis-equivalence 規則合併等價候選；第一個具有合格候選的 tier 即成為 authority tier。該層只有一個 center equivalence group 才能 recognized；若有多個不等價 group，回傳既有 blocking center ambiguity，不得退到較低層。

Center grouping 不同時決定 width。同一 center group 內的候選即使 `representative_width` 不同，仍是同一個 center evidence group；其所有有效 envelopes 交由 Decision 5 的獨立 width reconciliation。分組過程不得以 first occurrence 或 candidate method 預先留下某一個 width。

**理由：** 三種方法代表 source evidence 完整度，而不是彼此可自由競價的相同品質候選。局部候選先被找到不代表它更能代表整支構件。

**拒絕方案：** 對各方法重調 confidence 或加入 runner-up threshold。這會把 evidence provenance 問題變成調分問題，也會改變使用者已排除在 scope 外的既有數值與 ambiguity semantics。

### 2. Connected graph 不再等同完整外框

Topology candidate 的資格以「候選 boundary traversal」判斷，不以整個 connected component 判斷：

- 用既有 endpoint tolerance 建立 topology adjacency，並為每個 clustered node 選出 deterministic canonical point；boundary center、direction 與 width 只使用這些 canonical nodes，不再對 raw endpoint coordinates 做 exact-value `set()`。
- Canonical point 可由同一 node 內座標的 deterministic aggregate 或既有 graph representative 取得，但必須與 segment direction、entity order、root rotation／translation 無關；不得改變 tolerance 或合併不同 graph nodes。
- 可取得 tier 1 authority 的 boundary，其 traversal 節點須形成無分支的完整邊界；同一 traversal 不可依賴 degree 大於 2 的 branch 節點來把內部 detail rail 當成外框的一部分。
- 若 graph 含 branch／T-junction，整個 graph 不得直接送入 consolidated center／width 計算。
- 若 branched graph 中仍能獨立、唯一驗證一個不使用 branch edges 的完整 boundary，該 boundary 可保留；否則 topology tier 無 winner，交由 whole-root outer-envelope 判定。
- branch/detail edges 可作 whole-root completeness evidence，但不得成為 topology envelope boundary 或改寫 `source_width`。

此檢查只套用於本 change 的 Strut center authority。共用 helper 若需參數化，應由 role／route 明確傳入，避免暗中改變 Brace recognition。

**理由：** S11 的 topology graph 已正確證明是一個四段無分支外框；錯誤發生在 graph node identity 沒有延續到幾何計算，使同一角點因約 `1e-12 mm` 級 raw coordinate 差異被當成兩點。Branch qualification 仍處理另一類 generic invalid-contour 問題，但不是 S11 的修正來源。

**拒絕方案：** 只針對 S11 的角度、handle 或座標修正。該作法無法處理不同作者畫出的等價 branch topology。

### 3. Tier 2 先驗證 component-boundary evidence，再形成 outer-envelope

Tier 2 不得把 `_longitudinal_bands()` 或等價來源中的所有平行 rails 直接取 transverse minimum／maximum。實作應先對可能的 boundary band／face 套用既有具名資格，再形成 envelope interpretation：

1. 每個 boundary face 必須來自同一 root，方向相容，並通過既有 minimum length、slenderness 與 longitudinal coverage。
2. 成對 faces 的 separation 必須通過既有 width compatibility，且兩者必須共同支持同一個 Waler-bounded whole-component corridor。
3. 由該 pair 建立的 axis 必須通過既有 whole-root completeness；主要 component evidence 必須能由該 interpretation 解釋。
4. 短 detail、branch rail、connection detail 或局部 rail 若未通過上述資格，只能進入 completeness／conflict diagnostics，不得成為 outer face，也不得改寫 center 或 width。
5. 所有通過資格的 envelope interpretations 均須保留到 reconciliation：不等價 centers 依既有規則形成 ambiguity；等價 centers 則進入獨立 width reconciliation。

這個流程使用既有 tolerances 與 eligibility contract，不新增「最外面就是構件邊界」的 heuristic。因此即使 raw global extremes 位於更外側，只要它們無法共同支持完整 corridor，就不能擴張 Tier 2 envelope。

**理由：** 其他 BIM block 可能在真實支撐外側具有短 connection lines，或在 envelope 內含 branch/detail evidence。先取全域 extremes 會把這些繪圖細節誤當物理寬度；S11 本身則由 tolerance-normalized Tier 1 outline 解決。

**拒絕方案：** 對所有 parallel rails 取 min/max 後再依 maximum width 截斷。這只能阻止過寬結果，無法證明兩個 extremes 是同一完整 component 的 boundary。

### 4. 在 source-only authority guard 前完成 whole-root reconciliation

`_recognize_contextual_strut()` 不再讓任意 source-only recognized 結果一律先取得 transverse authority。實作應先保留候選 provenance，再執行以下順序：

1. 從同一 root 建立 qualified topology、whole-root envelope 與 local candidates。
2. 對候選使用既有有限 Waler span 選擇與 whole-root completeness 檢查；Waler 只裁定 longitudinal corridor 是否有效。
3. 依 evidence tier 合併等價軸並選擇第一個合格 center tier。
4. 對 winner center group 獨立 reconcile width。
5. 將 winner axis 延伸至既有唯一 Waler intersections，建立現有 `BlockMemberRecognitionOutcome`。

原本 source-only guard 的安全意圖保留，但 authority 僅能由已完成 tier qualification 的 winner 取得；local candidate 不得在 tier 2 尚未評估前先排除 whole-root candidate。對沒有 Waler context 的 compatibility entry，維持既有 source-only／generic fallback contract，本 change 不把 Waler 變成所有 recognition 的必要輸入。

**理由：** S20 已經產生正確 whole-root candidate，缺陷位於 orchestration 的過濾時機，不需要新增幾何推導方式。

**拒絕方案：** 完全移除 source-only route 或全面改寫 recognizer。既有一般 CAD、Brace 與無 contextual input 流程仍依賴該相容路徑。

### 5. Axis equivalence 與 width reconciliation 使用不同終止條件

Center authority 決定後，系統對該 center equivalence group 內的有效 envelopes 執行第二階段 reconciliation：

1. 只保留已通過所屬 tier topology／whole extent／component-boundary credibility 的 envelopes。
2. 將幾何等價的 envelopes 合併，不能以 candidate order、first occurrence 或 recognition method 挑選 width。
3. 若多個同軸完整 envelopes 呈可靠 containment，且其中一個可唯一證明為包含其餘有效 component envelopes 的實體外包絡，使用該 envelope width。
4. 若有效 envelopes 無法形成唯一物理外包絡，保留 canonical axis，並使用既有 unknown-width 表示；這不是 center ambiguity，也不得阻止 recognized axis outcome。

Tier 1 的 width 來自有效 boundary envelopes；Tier 2 的 width 來自 Decision 3 已通過資格的 whole-root envelope interpretations。Tier 3 local fallback 只有在既有規則足以證明 local pair 為 component envelope 時才沿用寬度。任何 tier 都不得由任意 local separation 或 candidate 排名補入 width。

350 mm 僅是 Y05 S11／S20 regression fixture 的實際量測，不是新的材料規格或 hard-coded recognition width。

### 6. 保留 terminal outcome 與 diagnostics contract

- recognized：只輸出一條 canonical axis；不暴露 competing axis。
- ambiguous：最高合格 tier 存在多個不等價 center groups 時，使用既有 blocking ambiguity contract；只有 width 無法唯一決定時不得回報 center ambiguity。
- failed：有 component-like evidence，但沒有 candidate 能通過既有完整性／span gate。
- not_applicable：維持既有 non-component fallback eligibility。

不新增以 member ID、handle 或 entity order 解開 ambiguity 的旁路。Importer 仍以現有方式把 terminal diagnostic 轉為 Review problem。

## Backward Compatibility and Persistence Impact

- `BlockMemberRecognitionInput`、`BlockMemberRecognitionOutcome`、Project schema 與 persisted review payload 不變。
- source fingerprint、exclusion／restore、pause／resume 與 manual override replay 不變。
- Y05 S2 root `957` 的舊 local center 是本 change 明確修正的既有錯誤；它與 `B05` 應對稱採 350 mm whole-root outer-envelope center。S10、S19、一般 CAD 與 Brace behavior 則必須由 regression tests 保護。
- 正確修復後重新匯入可能使受影響 Y05 source 的 canonical axis／width 改變；這是 recognition correction，不是資料 migration。既有已儲存專案不做 schema migration。

## Risks / Trade-offs

- **[Canonical node normalization 改變合法外框幾何]** → 只合併 graph adjacency 已按既有 endpoint tolerance 判定為同一 node 的 endpoints；以 permutation、reverse、rotation／translation tests 驗證 deterministic。
- **[Branch 判斷過嚴，拒絕仍可辨識的外框]** → 只拒絕把整個 branched graph 當 envelope；允許獨立驗證、不使用 branch edges 的完整 boundary，並保留 tier 2／3 fallback。
- **[Whole-root extremes 其實屬於同一 root 內兩支構件]** → 維持一個 root 一個 member-or-problem、既有 width／coverage gates 與同 tier ambiguity；不得強行合併。
- **[短 detail 或 connection line 成為 raw extreme]** → outer face 必須先獨立通過 direction、coverage、length、slenderness 與 whole-corridor eligibility；raw min/max 沒有 authority。
- **[同軸 nested envelopes 產生不同 width]** → center 先合併，width 再依 topology、whole extent、containment 與 credibility 尋找唯一物理外包絡；無法唯一時保留 axis 並回傳 unknown width。
- **[調整共用 topology helper 影響 Brace]** → 以 Strut contextual route 的明確參數或私有 qualifier 限定新語意，並跑 Brace regression。
- **[候選生成順序改變結果]** → 先按幾何 canonical key 分組，再依 evidence tier 決策；以 entity permutation／reverse direction tests 驗證 deterministic。
- **[既有 S2 regression 與鏡像來源矛盾]** → 以 `957`／`B05` 同 root-source 資格的鏡像 characterization 證明舊 expected value 不具幾何依據，並同步修改主 requirement，而不是在 production code 加 handle 特例。
- **[與 Waler contact-face change 混淆]** → 本 change 到 canonical source axis 為止；contact face、backfill side 與 endpoint finalization 留在獨立 change。

## Migration Plan

1. 先加入 synthetic 與 Y05 focused characterization／regression，固定 S11 的 tolerance-equivalent duplicate corner、S20 的 authority ordering 與目前錯誤模式。
2. 最小幅度加入 topology canonical node normalization、Strut topology boundary qualification與 candidate provenance/tiering。
3. 調整 contextual Strut reconciliation，再跑 focused DXF tests。
4. 跑完整 test suite 與 OpenSpec strict validation；若發現非 Strut 行為改變，回退該共用 helper 改動並改為 Strut-local qualifier。

此 change 沒有 persistence migration。若實作需要 rollback，可回復 recognition 內部變更；資料格式與既有專案檔不需回復或轉換。
