# Proposal

## Why

目前 BIM Strut recognition 雖已能從同一 root `INSERT` 建立 topology、whole-root outer-envelope 與 local fragmented rail-pair 候選，topology point normalization、候選資格與採用順序仍可能造成錯誤 transverse center authority。Y05 S11 的有效四邊外框端點只有浮點微差，graph adjacency 已依 tolerance 視為同一節點，但後續以精確座標去重後留下重複角點，導致斜軸與錯誤寬度；S20 則在正確的 350 mm whole-root envelope 已存在時，仍由局部 rail-pair 鎖定偏移中心。

## What Changes

- 將 BIM Strut 中心軸候選採用語意明確化為：可驗證且無分支的完整外框優先，其次為唯一可靠的 whole-root outer-envelope，只有前兩者均不成立時才允許 local fragmented rail-pair fallback。
- 讓 topology graph 的節點等價與後續 outline geometry 使用同一既有 endpoint tolerance：中心與寬度必須從 canonical topology nodes 計算，不得因只有浮點微差的同一角點被重複加權。
- 收緊 topology envelope 資格：單純 connected 不等於有效外框；內部 detail rails 形成 branch／T-junction 時，不得把整個 branched graph 當成一個 component envelope 或用其推導中心與寬度。
- 明確分離 axis equivalence 與 width reconciliation：等價中心軸可合併為同一 center evidence group，但 `source_width` 必須再由該 group 的有效 envelopes 依 topology、whole extent、containment 與 component-envelope credibility 找到唯一實體外包絡；若中心唯一而寬度不唯一，保留 axis 並將寬度視為 unknown，不升級成 center ambiguity。
- 收緊 Tier 2 whole-root outer-envelope 資格：只有通過既有 direction、coverage、length、slenderness、width compatibility、same-root 與 whole-component completeness 的 component-boundary evidence 才能成為 outer face；不得直接對 root 內所有平行 longitudinal rails 取全域 transverse min/max。
- 在 local rail-pair 取得 transverse center authority 前，先完成 whole-root candidate reconciliation；若外側與內側 longitudinal evidence 共同支持唯一中心，採用該 whole-root center，不得因局部候選先出現就排除它。
- 若多個幾何不等價的中心皆通過相同完整性資格，維持 blocking ambiguity；不得依 score、距離、INSERT point、handle、entity order 或 candidate order 任選。
- Waler context 繼續只界定 longitudinal span／terminal intersections，不得替 Strut source geometry 猜測 transverse center；本 change 與 `unify-waler-contact-face-recognition` 的接觸面 finalization 保持分離。
- 以 Y05 S11、S20 與其鏡像 root `957` 建立 regression；`B05`／`957` 均改採來源支持的 350 mm whole-root outer-envelope center，同時保護 S10、S19 及其餘既有 Y05／一般 CAD recognition behavior。

### In Scope

- Strut-role BIM root `INSERT` 的 topology validity、whole-root outer-envelope 與 local fragmented rail-pair 候選優先順序。
- Topology endpoint clustering 與 outline axis／width 計算之間的 tolerance-consistent canonical node contract。
- 同一 root、同一主要長方向內的 transverse center grouping，以及與其分離的 `source_width` envelope reconciliation。
- Tier 2 component-boundary evidence eligibility；短 detail、branch rail、connection detail、局部 rail 可參與 completeness 診斷，但不得直接成為 outer face。
- failed／ambiguous outcome、diagnostics 與既有 Review lifecycle 的相容性。
- Y05 S11、S20，以及與 `B05` 幾何鏡像的 root `957` 真實來源 characterization 與 deterministic regression。

### Out of Scope

- Waler 支撐側或接觸面的選擇；由獨立 `unify-waler-contact-face-recognition` change 處理。
- 修改 Waler、Brace、CornerBrace、Column 或 Joist 的 recognition winner。
- 新增第四種中心算法、人工 handle／檔名／座標特例、直接採用 INSERT point，或修改原始 DXF。
- 修改既有 `bim_minimum_longitudinal_evidence_ratio = 0.5`、`minimum_projection_overlap_ratio = 0.8`、`ambiguous_candidate_score_delta = 0.03` 或 `maximum_component_width_mm = 600`。
- Solver、材料規則、Project schema、persistence 或 UI redesign。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `bim-block-member-recognition`: 明確規範 branched contour 的 envelope 資格、whole-root center reconciliation 與 local rail-pair 的最後 fallback 順序，並加入 Y05 S11／S20 行為案例。

## Impact

- 預計影響 `dxf_import/block_member_recognition.py` 的 topology extraction、whole-root candidate selection 與 contextual Strut orchestration，以及 `tests/test_dxf_bim_block_recognition.py`。
- Recognition pure service、Importer adapter、WCS/root provenance 與現有 Review contracts 維持既有 dependency direction。
- 預期補強 DXF recognition 的長期 engineering truth；不改變 Project、Solver 或 persistence contract。實作完成並驗證後，若長期文件需要反映候選優先順序，僅更新 `docs/DOMAIN.md`／`docs/ARCHITECTURE.md` 中直接相關段落。
