# Proposal

## Why

目前 BIM Strut root `INSERT` 主要只用圖塊內部線段決定工程軸與長度；Y05 S19 類 H 型、重複且分段的圖塊因此可能把局部外緣／內緣誤配成完整支撐，產生偏移且截短的正式軸。實際工程判斷還會利用支撐兩端的正式圍令：圍令交點應先界定預期支撐跨度，再由同一 root INSERT 在該跨度內的整體幾何確認哪條候選軸能完整解釋一支支撐。

## What Changes

- 將 DXF Import 改為先完成 Waler source recognition，保留其有限 reference axis 與可用 boundary/contact-line alternatives，再執行需要 Waler context 的 BIM Strut recognition；正式 Strut 選定後仍沿用同一套 Waler contact-face selection 產生最終端點，避免形成兩套接觸面 truth。
- Topology、legacy full-span 與 fragmented BIM 幾何不再各自過早產生正式 Strut；它們先提供 deterministic axis hypotheses。
- 對每條合格候選軸沿長方向延伸，僅使用與該無限軸實際相交的有限正式 Waler engineering segments，尋找包住來源幾何的起點側與終點側最近交點。
- 以兩端 Waler 交點建立預期支撐跨度／長度，再檢查同一 root INSERT 在此 corridor 內的 longitudinal evidence、橫向配置、寬度相容性與未解釋主要幾何，選出能完整解釋該 source 的唯一 whole axis。
- 允許相同 root、方向／橫向位置／寬度相容的分段證據跨越 interior gaps；gap 不單獨造成截短或拆件。
- Component-like BIM source 若缺少任一側唯一正式 Waler、存在多個無法唯一決定的包圍 Waler，或沒有候選軸能完整解釋 root geometry，保留 root provenance 並產生 blocking Review problem；不得退回一般局部平行線辨識製造看似合法的偏移構件。
- 保留簡單非 component-like `INSERT` 的 generic fallback，以及現有一般 LINE、MLINE、closed outline、Brace、CornerBrace、Column、Beam 行為。
- Y05 S19 納入 regression：使用目前上游流程已建立的兩端正式 Waler context，應建立幾何中心約 `X = 29501.5` 的 whole axis，不得採用約 `X = 29411` 的左半斷面軸。

### In Scope

- Strut role 的 root `INSERT`、其 WCS child geometry 與正式 Waler engineering lines 的 contextual recognition。
- Waler-first recognition staging、axis hypothesis、有限 Waler intersection、expected span／corridor 與 whole-root completeness。
- Y05 S19 類多縱線、重複線、內部斷點與 H 型斷面 evidence。
- 一端／兩端缺少唯一 Waler、Waler intersection ambiguity、無完整 root explanation 的 blocking diagnostics。
- 既有 exclusion／restore、manual override replay、confirmation invalidation、Pause／Resume 與 ReviewItem lifecycle regression。

### Out of Scope

- HATCH／RC Waler 的來源辨識；其 Waler 缺漏已由其他 change 處理，本 change 只消費上游已建立的正式 Waler context。
- 調整 `bim_minimum_longitudinal_evidence_ratio = 0.5`、`ambiguous_candidate_score_delta = 0.03` 或一般 candidate duplication／runner-up policy。
- 以 block insertion point、block name、固定 350 mm 寬度或單純最近距離直接決定支撐軸。
- 跨 root INSERT 合併、人工 Guided Recognition、影像／AI 辨識。
- 一般 Brace／CornerBrace recognition、Solver、材料規則、Project schema 或原始 DXF 寫回。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `bim-block-member-recognition`: 將正式 Waler context 納入 BIM Strut whole-axis／whole-span 判斷，修改 source-supported terminal extent、legacy fallback 與 component-like failure semantics。

## Impact

- 主要影響 `dxf_import/importer.py` 的 recognition staging、`dxf_import/block_member_recognition.py` 的 pure BIM Strut service contract、`dxf_import/recognition.py` 的 root INSERT router，以及 `tests/test_dxf_bim_block_recognition.py`、`tests/test_dxf_input.py` 與相關 DXF workflow regression。
- 既有 `connect_components_to_walers()` 保留作為正式 member 建立後的關聯／驗證；長距離 axis extension 不由其目前的 endpoint proximity snap 取代。
- `DXFImportResult`、Project rows、persistence schema、Solver 與 Presentation ownership 不變，無新增第三方 dependency。
- 本 change 沿用既有 DXF subsystem Architecture，但把 recognition pipeline 定義為單向 context dependency：`Waler → Strut → Brace → CornerBrace → Column → Joist`。本 change 的 production scope 只實作 `Waler → Strut`；後續階段僅記錄 architecture direction，不提前實作。完成後應更新 `docs/ARCHITECTURE.md` 的 DXF recognition data flow，且不改變 Core Domain 或 Solver truth。
