# Design

## Context

現行 STEP4 repair 的 pure planner 位於 `dxf_import/corner_brace_repair.py`。它從 exact target `SourceGeometry` 建立 residual axis hypotheses，列舉 Strut 與其 `from_waler`／`to_waler`，再以 axis 與兩支有限構件的交點形成 endpoints；eligible references 只比較 side、相對角度、fixed length 與 endpoint topology。`DXFReviewWorkflow` 在 Apply 前重建 plan 並以 revision／subject signature 防止 stale commit，成功後原子交換 world result、projected result、ReviewItems、confirmations 與 candidate store。Dialog 只顯示 plan 並提交使用者明確選取的 candidate。

Y05 現行資料重建顯示：FB7 是 `S-BEAM` 的 unresolved root source，automatic recognition 因 72.5 mm `COMPONENT_TOO_SHORT` 未建立正式 CornerBrace；目前 residual-axis planner 以一條約 45° 的長殘線建立 `W2 / S21`、2320.204 mm candidate，支持 references 為 CB64、CB20、CB52、CB1。實際最近的 CB58 距 target residual 中心約 1928 mm，且同樣連接 W2／S21，但位於對側，所以被現行 same-side reference match 排除。CB58 的 connection local values 約為 Waler-side offset 1712.030 mm、Strut inward station 1712.030 mm、fixed length 2421.177 mm；它是本 change 要支援的同關係鏡射模板。

既有 `CornerBraceRepairProvenance` 已保存 exact subject、adopted world line、target identities 與 primary／secondary references；version 2 `manual_overrides` 可選擇性保存 repair payload。Compatible-source recovery 已明確禁止 geometry-only transfer，本 change 不改變該規則。

## Goals / Non-Goals

**Goals:**

- 讓人工 repair 由 compatible automatic primary 的局部配置產生 endpoints，而不是要求不完整 residual 決定完整軸長。
- 將工程 compatibility、locality ranking、同側／鏡射 transfer 與 residual validation 分成可獨立測試的 pure steps。
- 保留 exact source identity、finite target geometry、Preview、explicit adoption、atomic commit 與安全 replay。
- 讓 FB7 類案例優先採用同一 Waler／Strut 的對側 reference（CB58），並能稽核 transfer 所用尺寸。

**Non-Goals:**

- 不更動 `_corner_brace_candidates_from_group()` 或 automatic `_refine_corner_brace_axis_intersections()` 的辨識／延伸策略。
- 不讓 manual repaired secondary 成為 geometry template。
- 不為本功能建立新的 Project entity、Solver input 或跨子系統 service。
- 不保證只要存在最近角撐就一定能修補；缺少 target direction、positional anchor 或 finite target relationship 時仍拒絕。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 dependency direction：

```text
DXFImportDialog (Presentation)
        ↓ preview / explicit Apply
DXFReviewWorkflow (state transition owner)
        ↓
corner_brace_repair.py (pure WCS planning + staged rebuild)
        ↓
DXFImportResult / CornerBraceConnection / GeometryTolerances
```

- `dxf_import/corner_brace_repair.py` 繼續擁有 repair evidence、template extraction、compatibility、ranking、transfer 與 hard validation。
- `DXFReviewWorkflow` 繼續是 live Review state 的唯一 mutation boundary。
- `DXFImportDialog` 只呈現 planner 已判定合法的 candidates，不自行計算 nearest reference 或局部尺寸。
- Automatic recognition 不依賴 repair module；repair 仍是單向讀取已完成 recognition truth。
- Solver、Project Domain 與 Application layer 不受影響。

Single source of truth 仍是 `DXFReviewWorkflow.world_result`。Candidate、template 與 overlay 都是 immutable staged projection；Dialog selection 不形成第二份工程 truth。Apply 後只有 adopted `CornerBrace` 與其 provenance 進入 live result。

## Decisions

### 1. 將 repair planning 拆成 evidence、template、transfer、validation 四個 pure 階段

Planner 依序執行：

1. 從 exact target source handles 擷取 `TargetRepairEvidence`：可靠方向 hypotheses 與 positional anchors。
2. 從每支 eligible automatic primary 的唯一 `CornerBraceConnection` 擷取 `CornerBraceLocalTemplate`。
3. 列舉 target Strut endpoint 與其有限 Waler relationship，建立 target local frame，依 same-side 或 mirrored mode transfer template。
4. 對 transferred endpoints 執行 finite-segment、target evidence、duplicate、connection 與既有 CornerBrace validation，只有全部通過才建立 Preview candidate。

這些型別保持 module-local immutable DTO；不把 target evidence 或 template 放進 Project Domain。

理由：目前 `plan_corner_brace_repair()` 同時產生 residual axis、列舉 relationship 與比對 references。拆成小型 pure helpers 可直接測試工程 contract，又不需要建立新 service/module。

替代方案：修改 automatic recognizer 讓 FB7 自動成功。拒絕，因來源缺失使 automatic 補全風險過高，且使用者已確認此能力必須是人工修補工具。

### 2. Target residual 從 geometry generator 改為 hard validation evidence

Target evidence 必須同時提供：

- direction：由 exact source 的可靠長線、可靠平行邊 midline 或可驗證的 partial rail 得到；
- positional anchor：優先重用 connection-plate topology 可得的 plate midpoint；若一端 plate topology 不完整，則使用與方向一致的 exact residual corridor 形成空間 anchor。

一端殘線足以驗證 transferred candidate；不要求 residual 延伸到 Strut attachment，也不再以每條長於 minimum length 的任意 segment 直接建立完整 candidate axis。連接板／外框若無法與方向及 target finite Waler 建立一致 topology，不得成為 anchor。

方向使用 `parallel_angle_tolerance_deg`；共線／corridor 與 endpoint／connection 比較只使用既有具名 `GeometryTolerances`。若實作發現現有 tolerance 無法表達 plate-anchor 語意，必須先回報並修訂 Spec，不得加入 magic number。

替代方案：完全忽略 residual，只依最近角撐鏡射。拒絕，因會在錯誤圖層、錯誤側或缺少實體來源時創造 ghost CornerBrace。

### 3. Reference local frame 使用 Waler／Strut 有限交點與 connection attachments

對 eligible automatic primary：

- `O_ref`：reference Waler finite engineering line 與 reference Strut centreline 的唯一交點；
- `v_ref`：由 reference 所屬 `from`／`to` endpoint 指向 Strut 內部的 unit vector；
- `waler_offset_mm`：`O_ref` 到 `baseline_waler_attachment` 沿 Waler 的側向距離 magnitude；
- `strut_station_mm`：`O_ref` 到 `baseline_strut_attachment` 沿 `v_ref` 的 inward station；
- `side`：由 inward axis 與 Waler attachment ray 的 cross-product sign；
- `fixed_length_mm`：保留作 template audit，正式 transferred length 由 target endpoints 重算。

Template extraction 必須驗證兩個 reference attachments 位於各自有限構件上，且 local values finite、非負並與現有 connection 一致；否則 reference 不可作 template。

Target 使用相同方式建立 `O_target`、`v_target` 與 Waler side rays：

- same-side transfer：沿 target evidence 支持的同側 ray 套用 `waler_offset_mm`；
- mirrored transfer：將 reference side 映射到 target evidence 支持的對側 ray，保留 `strut_station_mm`。

這是尺寸移植，不是複製 world coordinates。若 target Waler／Strut 夾角與 reference 不相容，或任何 endpoint 超出有限線段，candidate 直接拒絕，不做 clamp／snap。

替代方案：只複製 reference fixed length，再沿 residual axis 解一個圓線交點。拒絕，因它丟失 Waler-side offset 與 Strut hole station，且可能產生兩解或把 attachment 移到不符合附近施工做法的位置。

### 4. Compatibility 是 hard gate，locality 是排序規則

Automatic primary 先通過：

- unique valid `CornerBraceConnection` 與 active source；
- 相同 target endpoint topology（`from`／`to`）；
- reference／target Waler-Strut local included angle 在既有 angle tolerance 內；
- transferred endpoints 均在 target finite segments；
- transferred axis 通過 exact target direction 與 positional anchor；
- staged CornerBrace validation 全部通過。

通過後依 tier 排序：

1. 同一 target Waler identity + 同一 target Strut identity，且為 evidence 支持的對側 transfer；
2. endpoint topology 相同、local frame 相容的鄰近 Strut；
3. 其他相容 automatic primary。

同 tier 內使用 target anchor 至 reference engineering-line midpoint 的 WCS 距離。距離差在既有 `ambiguous_connection_delta_mm` 內且產生非等價 geometry 時，保留多個 candidates；不得以 member ID 或 entity order 選 winner。Unresolved create 仍要求所有 hard-eligible candidates 指向同一 target Waler／Strut relationship；recognized replace 才能在 Preview 顯示多個完整 relationships。

Manual repaired secondary 仍只追加 consistency／diagnostic evidence，不能升格為 template。這保留既有 anti-chaining contract。

### 5. Candidate 與 provenance 明確區分 selected template 和 supporting evidence

`CornerBraceRepairCandidate` 增加或等價表達：

- singular `template_reference`；
- `transfer_mode`（`same_side`／`mirrored`）；
- `reference_waler_offset_mm`；
- `reference_strut_station_mm`；
- target direction／anchor validation diagnostics。

既有 `primary_references` 可保留為 supporting automatic evidence，但 selected template 不得只靠 tuple 順序推定。

`CornerBraceRepairProvenance` 增加 optional template fields：selected automatic reference、transfer mode、local offset 與 station。`adopted_world_start/end` 與 target identities 繼續是 replay 的正式結果證據。Evidence signature 納入 selected template 與 transfer values，避免相同 endpoints 但不同推導來源無法稽核。

替代方案：只把 selected template 放在 `primary_references[0]`。拒絕，因排序改變會悄悄改變語意，也無法區分 template 與 supporting reference。

### 6. Preview 顯示推導過程，但不提供繞過 hard filter 的操作

Dialog 表格／detail 顯示：

- target Waler／Strut；
- selected template ID；
- same-side 或 mirrored；
- Waler offset、Strut station、result length；
- target direction／anchor validation summary；
- supporting automatic／manual secondary references。

Overlay 繼續顯示 exact residual 與 proposed engineering line；可額外標示 positional anchor，但不得讓使用者直接拖動 endpoint 或把 rejected hypothesis 強制 Apply。唯一 candidate 可預選，仍需按 Apply。

### 7. Atomic commit 與 stale-plan boundary 不變

`commit_corner_brace_repair()` 在 Apply 時依 current world result 重新 planning，並比較完整 candidate，包括 selected template identity、transfer mode、local dimensions 與 diagnostics-relevant evidence。Target subject、relationship、template connection 或 source evidence 任一改變即拒絕 stale plan。

成功後沿用現有 staged sequence：建立／取代 CornerBrace、重建 candidate points、Strut attachment、CornerBraceConnection、problems、ReviewItems、confirmations 與 projected result，最後一次交換 live fields。任何錯誤均不修改 live state。

### 8. Persistence 向後相容，不提升 Review state version

新 template fields 以 optional keys 加入既有 `manual_overrides.corner_brace_repair` payload；不修改 Project schema，也不需要 version 2 → version 3 migration。

- 新 payload same-fingerprint replay：必須定位 exact target、target Waler／Strut 與 selected template，重新產生等價 transfer candidate並與 adopted world line 核對；不得改選目前最近 reference。
- Legacy version 2 payload：缺少 template fields 時走既有 adopted-line + target identities + saved references replay；不套用新 nearest-template planning 改寫工程線。
- Changed-content compatible recovery：維持 `requires_review`／`disabled`，不轉移 repair geometry 或 template decision。

Deserializer 對 partial／invalid template fields 採 fail-safe：整組視為無效並要求 review，不把部分資料與 legacy path 混用。

## Risks / Trade-offs

- [最近角撐可能屬於不同施工細節] → compatibility gates 先於距離，Preview 明示 selected template 與局部尺寸，使用者必須明確 Apply。
- [殘線含連接板、外框與遮擋後碎片，anchor 可能多解] → 只接受 exact source、topology-supported anchors；多解不以 entity order 決定，零／多解提供 diagnostics。
- [同一 Waler／Strut 對側角撐未必完全對稱] → mirror 只產生 candidate，仍須 target direction、anchor、finite geometry 與 staged validation 通過。
- [現有 tests 假設 manual endpoints 來自 axis intersections] → 只改人工 repair tests；automatic centerline extension regression 必須保持原 assertion。
- [Optional provenance 擴充造成 replay 分支複雜] → 明確區分 new-template 與 legacy payload；禁止混合 fallback，加入 round-trip、missing-template、changed-reference 與 recovery tests。
- [Y05 原始 DXF 不一定是可攜 fixture] → 以 FB7／CB58 實測 local geometry 建立最小 deterministic WCS fixture；可另做 repository asset smoke check，但正式單元測試不依賴外部絕對路徑。

## Migration Plan

1. 先以 characterization tests 固定現有 FB7 錯誤模式、CB58 local template 及 automatic centerline regression。
2. 增加 pure evidence／template／transfer DTO 與 helpers，再切換 repair planner；在 planner 完成前不改 Dialog／commit。
3. 擴充 candidate／provenance 與 persistence round-trip，保留 legacy replay 分支。
4. 更新 Preview 顯示與 stale-plan comparison，維持原子 commit。
5. 執行 focused DXF repair、persistence、recovery、Waler-contact tests，再執行完整 regression。
6. 實作驗證完成後更新 `docs/WORKFLOW.md` 的 repair truth；`docs/ARCHITECTURE.md` 只有在 module ownership 實際改變時才更新。`docs/DOMAIN.md` 與 `docs/SOLVER.md` 不需修改。

Rollback 可回復 planner、DTO optional fields與 UI 顯示；舊 payload 未被改寫，新增 optional fields 被舊程式忽略時仍保留 adopted world line。不得用 Git reset/revert 覆蓋使用者其他修改。
