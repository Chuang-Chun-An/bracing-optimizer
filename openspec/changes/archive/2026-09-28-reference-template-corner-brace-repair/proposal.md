# Proposal

## Why

目前 STEP4 角撐修補以目標殘線推導完整軸線，再用其他角撐的長度、side 與 topology 作一致性驗證；當 BIM 遮擋已移除角撐大部分幾何時，殘線不足以可靠決定完整配置，且可能忽略最接近、同一 Waler／Strut 的鏡射角撐。Y05 FB7 即為此情境：可相信的主要是圍令連接板位置與角撐方向，完整端點應優先比照附近已成功辨識角撐的局部配置。

## What Changes

- 將人工 CornerBrace repair 的 candidate generation 改為 reference-template transfer：先辨識目標有限 Waler／Strut 關係，再從相容的已成功角撐擷取相對於 Waler／Strut 交點的局部配置尺寸，移植或鏡射到目標關係。
- 定義 reference 相容性與優先順序：同一 Waler／Strut 的另一側優先，其次為相同 endpoint topology、相近 Waler／Strut 局部幾何的鄰近 Strut；空間距離只在通過相容性後排序，不得使 reference 合法。
- 將 exact target residual 的角色改為必要驗證證據：至少須能支持圍令端連接板位置或角撐軸方向，並驗證 transferred candidate 與殘線 corridor 一致；不得再要求殘線自行提供完整角撐長度或兩端交點。
- 允許 automatic primary reference 的 Waler offset、Strut station 與 same-side／mirrored mode，配合 target local frame，完整決定人工修補候選端點；candidate fixed length 一律由 transferred endpoints 重算。Reference fixed length 只供 Preview、provenance 與 diagnostic comparison，不得影響端點或單獨決定 eligibility。
- 統一 target relationship 唯一性：每個 candidate 必須唯一綁定一組 target Waler／Strut；recognized replace 的 plan 可包含多組各自完整且 hard-valid 的 relationship candidates 供使用者選擇，unresolved create 則只允許所有 hard-eligible candidates 指向同一組 relationship，否則 blocking。
- Preview 顯示選用的 reference、同側／鏡射 transfer、局部偏移、目標端點及 residual validation 結果；使用者仍須明確 Apply。
- 保留既有 atomic commit、replace／unresolved create、provenance、Pause／Resume replay、confirmation invalidation 與 changed-content recovery 安全規則。
- 以 Y05 FB7／CB58 建立 regression：CB58 是同一 W2／S21 的最近完整對側角撐，FB7 候選應由其局部配置鏡射產生，而不是由殘線延伸後再以較遠 references 驗證。

### In Scope

- STEP4 人工 CornerBrace repair 的 planning、reference selection、candidate geometry、Preview diagnostics、provenance 與相關測試。
- 人工 repaired CornerBrace 的正式端點語意，以及其既有 downstream CornerBraceConnection／Waler contact 基準重建。
- 完成實作後更新角撐修補的長期 Workflow 文件；若 model／module ownership 改變，再同步 Architecture 文件。

### Out of Scope

- 不放寬或重寫 CornerBrace automatic recognition。
- 不修改一般 Brace、Strut、Waler、Beam recognition。
- 不修改 Solver、材料規則或 Project schema。
- 不由附近角撐在完全沒有 target source geometry 時創造 CornerBrace。
- 不自動 Apply、不中止 Preview／confirmation／rollback 安全機制，也不建立大型 DXF Review framework refactor。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `dxf-corner-brace-repair-tool`: 將人工修補候選從 residual-axis-first 改為 compatible nearest reference 的局部配置移植／鏡射，並重新定義 residual hard validation 與 Preview evidence。
- `dxf-corner-brace-centerline-extension`: 區分 automatic recognition 的 finite-axis intersection 語意與人工 repair 的 reference-template endpoint 語意；人工修補端點不再必須完全由殘線軸與有限構件求交決定。

## Impact

- 主要受影響模組：`dxf_import/corner_brace_repair.py`、`dxf_import/models.py`、`dxf_import/review_workflow.py`、`dxf_import/dialog.py`、`dxf_import/source_exclusion.py`。
- 主要受影響測試：`tests/test_dxf_corner_brace_repair.py`、`tests/test_dxf_review_layout.py`、相關 Pause／Resume、recovery 與 Waler contact regression。
- 既有 persisted repair payload 需維持可讀；新修補 provenance 需可稽核 template reference、transfer mode 與局部尺寸，但不改 Project persistence schema。
- Architecture layer 不變：pure WCS planning 留在 DXF import operation，Workflow 擁有 atomic state transition，Dialog 只負責選取、預覽與 Apply。
- Domain 與 Solver truth 不變；DXF Review workflow 的人工 CornerBrace repair truth 會改變。
