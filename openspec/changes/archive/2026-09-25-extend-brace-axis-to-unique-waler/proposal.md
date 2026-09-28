# Proposal

## Why

Y05 的 BIM 斜撐圖塊可可靠重建正確軸向，但來源輪廓常在圍令前停止約 425～528 mm；現行連接只吸附距離端點 250 mm 內的有限 Waler，因此把可由軸向與有限圍令唯一判定的斜撐留成未連接待修。系統需要在不改變 Brace recognition 軸、不猜測圍令且不影響 Strut 的前提下，讓 Brace 端點沿既有軸向延伸至唯一合理的有限 Waler 交點。

## What Changes

- 保留既有端點在 `connection_tolerance_mm` 內直接吸附 Waler 的優先流程；只有未連接的 Brace 端點才進入軸向延伸判定。
- 從已可靠辨識的 Brace 工程軸，依各端點的向外半射線搜尋與有限 Waler segment 的實際交點；不得旋轉軸線、側向吸附或使用 Waler 無限延長線。
- 以沿向外半射線最先遇到的有限 Waler 交點作為候選；若最近位置有多支無法唯一區分的 Waler、兩端連到同一 Waler、或任一端仍找不到合法交點，維持既有 blocking connection problem，不任意猜測。
- 自動連接後，以交點更新正式 Brace endpoint 與 `FromWaler`／`ToWaler`，並讓 Candidate Points、Review、manual replay 與 diagnostics 使用同一連接結果。
- Y05 中由來源軸端向外約 425～528 mm 可唯一命中有限 Waler 的 Brace，應可建立完整 Waler-to-Waler formal Brace。

### In Scope

- 已有可靠正式軸的 Brace endpoint-to-Waler connection。
- 有限 Waler segment 的 outward-ray intersection、唯一性與 deterministic selection。
- Brace formal geometry、Candidate Points、connection diagnostics、Review lifecycle 與 Y05 regression。
- 修正既有 BIM Brace specification，使「recognition 不外插來源軸」與「下游 connection 可沿已確認軸延伸」有清楚邊界。

### Out of Scope

- Strut、CornerBrace 或其他 member 的端點延伸。
- 修改 BIM Block geometry classification、whole-axis winner、source-supported terminal extent 或一個 root 一支 Brace 規則。
- 使用 Waler 無限延長線、改變 Brace 軸角度、側向搜尋、猜測缺失 Waler，或跨 root 合併來源。
- 修改 `connection_tolerance_mm`、Waler recognition、CandidatePoint 工程規則以外的辨識流程、Project schema、Solver 或 optimization。
- Guided Recognition、人工畫輔助線或回寫 DXF entity。

## Capabilities

### New Capabilities

- `brace-axis-waler-extension`: 定義未連接 Brace 端點如何沿可靠軸向延伸至唯一有限 Waler、成功時如何提交正式連接，以及找不到或無法唯一判定時如何安全失敗。

### Modified Capabilities

- `bim-block-brace-recognition`: 保留 BIM recognition 軸只涵蓋 source-supported extent，但允許獨立的下游 Waler connection 階段沿該已確認軸建立有限 Waler 接點，取代目前完全禁止此類連接延伸的規則。

## Impact

- 主要影響 `dxf_import/candidate_points.py` 的 Brace-to-Waler connection 與 Candidate Point 建立；必要時新增小型 pure geometry helper，避免在 UI 或 BIM recognition service 複製規則。
- 影響 Brace connection validation／diagnostics、Review rebuild 與對應 DXF tests；不改變 `dxf_import/block_member_recognition.py` 的 recognition outcome。
- 不新增第三方 dependency，不修改 persistence／Project schema，不影響 Solver。
- Architecture 與 Domain boundary 不變；實作成立後需更新 `docs/WORKFLOW.md` 中「Brace whole-axis recognition 後只使用既有有限端點 tolerance」的 current behavior。
