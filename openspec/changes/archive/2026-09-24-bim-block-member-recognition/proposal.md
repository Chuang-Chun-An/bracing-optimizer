# Proposal

## Why

BIM 匯出的 DXF 常把一支實體支撐包成一個 root `INSERT`，但其可見輪廓可能因投影、遮蔽或重疊而被切成多個短線與封閉片段。現有一般辨識會在這類來源中選取局部外框或平行邊，可能把實際完整的長支撐縮成其中一小段，因此需要一條受嚴格條件限制、以整個 Block 幾何為證據的特殊辨識路徑。

## What Changes

- 對位於 Strut role layer 的 root `INSERT` 增加 component-like BIM Block 判定；`INSERT` 身分只建立 source scope，不直接等同正式構件。
- 僅在整個 root Block 顯示單一主要長方向、細長整體形態、共同軸對齊與合理寬度一致性時，才從全體 geometry 重建一支完整 Strut 的工程軸。
- 允許同一 root `INSERT` 中由遮蔽或輪廓切割造成的多個共軸 fragments 與較大內部 gap 共同支持一支構件；不因局部 fragment 或單一短平行邊縮短正式工程軸。
- root `INSERT` 不符合特殊路徑資格時維持現有一般 recognition；已判定為 component-like 但無法唯一、可靠重建完整工程軸時，改回報 unresolved ambiguous／error，不再以一般局部候選強行成功。
- Nested `INSERT` 繼續遞迴展開並套用 insertion／rotation／scale 到既有 WCS boundary；正式候選與 Review provenance 保留 root source handle，且不同 root `INSERT` 的 fragments 不互相合併。
- 保留 root layer role contract：child entity（包含 Layer 0）只提供形狀證據，不重新決定 role。
- 維持既有 Review、source exclusion／restore、manual override replay、confirmation invalidation、pause／resume 與 import completion lifecycle；本 change 只改變特定 source geometry 產生 member candidate 的方式。
- 第一版只啟用 Strut BIM Block recognition。幾何分析元件可保持可延伸性，但 Brace 尚有其既有斜撐辨識與連接語意，本 change 不改變 Brace recognition rule。

### In Scope

- Strut role 的 root `INSERT` component-like eligibility、唯一完整工程軸重建與 deterministic 結果。
- fragmented rectangles、detail geometry、large interior gaps、Nested Block WCS transform 與 root provenance。
- 特殊路徑的 not-applicable fallback，以及 component-like recognition failed／ambiguous 的 Review 問題呈現。
- 一般中心線、MLINE、完整 closed outline、完整平行邊及非 component-like geometry 的 regression protection。
- immutable original DXF、source fingerprint、source exclusion／restore、staged Review mutation、manual replay、confirmation、pause／resume、Project row boundary與 completed import lifecycle 的相容性驗證。

### Out of Scope

- Brace BIM Block recognition、Waler recognition redesign、Continuous Wall、Column、Beam、CornerBrace 與 material recognition。
- Guided Recognition、人工輔助線、直接由人工標記建立 Project component。
- AI／ML、model training、image recognition、cloud recognition。
- CandidatePoint 與 Double Support 工程規則、Project schema、Solver、optimization。
- 原始 DXF 寫回、跨 root `INSERT` fragment 合併，以及無關的 DXF Import UI 或 recognition framework 重構。

## Capabilities

### New Capabilities

- `bim-block-member-recognition`: 定義 Strut component-like BIM root Block 的觸發條件、whole-geometry 軸重建、fallback／ambiguity、WCS／provenance 與 Review lifecycle 相容行為。

### Modified Capabilities

- 無。

## Impact

- `dxf_import/importer.py`：在既有 root entity grouping 與 WCS extraction 後協調受限的 BIM Strut Block recognition，不改變 Project 寫入責任。
- `dxf_import/recognition.py` 與一個小型、可單元測試的 geometry/service module：保留一般辨識，新增 whole-block component evidence 分析及候選結果 contract。
- `dxf_import/models.py`、`validation.py`、`source_exclusion.py`、`review_workflow.py`：優先沿用現有 model、problem、root-handle identity 與 staged workflow；若需新增 recognition diagnostic，只做 backward-compatible runtime extension，不改 persistence schema。
- 相關 DXF recognition、WCS、Review、exclusion／restore、manual replay、confirmation 與 lifecycle tests 增加新案例及 regression coverage。
- 不新增第三方 dependency，不改 Architecture、Domain 或 Solver truth。實作完成後應更新 `docs/WORKFLOW.md` 的 DXF recognition current behavior；已記錄的 Future Guided Recognition requirement 保持獨立且不納入本 change。
