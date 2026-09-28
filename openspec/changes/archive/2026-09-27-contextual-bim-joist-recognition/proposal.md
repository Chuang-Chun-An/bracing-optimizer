# Proposal

## Why

Y05 的 Beam 圖層包含以單一 root `INSERT` 表達的 BIM 托梁。現行 generic Beam 辨識會把局部平行線誤當完整托梁，也假設一個 root 最多只形成一支 Beam，因而無法正確表達已由 whole-source geometry 證明、同一 root 內實際存在兩條托梁軸的雙 C 型 assembly。

## What Changes

- 為 Beam-role root `INSERT` 建立 role-correct、whole-source BIM Joist recognition；來源幾何仍是構件身分與軸線的必要證據，正式 Strut、Brace、Column 只提供 immutable contextual evidence。
- 將 root outcome 明確分成：一般 Joist root 最多一支 single-axis Joist；可靠雙 C root 最多一個 paired-axis Joist assembly，內含恰好兩條 source-supported Joist axes；不能唯一建立任一 outcome 時回報 `failed`／`ambiguous`，不得回退局部 parallel pair。
- 針對 whole-source geometry 已證明的雙 C 型 BIM Joist assembly，採用具名工程契約：兩條 Joist 軸與同一有限 Strut 的 crossing station 間距為 `518.0 ± 5.0 mm`（inclusive），pair midpoint 與 formal Column station 差異為 `±2.0 mm`（inclusive）。此規則不得泛化到所有 Joist 型式。
- 分離 source axis truth 與 contact finalization：Joist 軸忠實保留在主圖塊支持的有限端點；若端點以垂直方向唯一接觸 formal Strut 的實體外緣，且端點至中心線距離符合該 Strut 可靠來源寬度的一半與具名容許值，則建立 `endpoint_face_contact`，只將關聯站位投影至 Strut 中心線，不修改 Joist source axis。
- 將 paired assembly 映射為兩個 runtime Beam models／BM IDs、兩個 Strut crossing stations 與共同 root provenance；Review confirmation、source exclusion／restore 與重建必須維持 assembly 一致性。
- 保留 Brace 垂直接觸時的 single-Joist 語意；Strut／Column assembly 若缺少合格 pair 或存在多組無法唯一區分的合格 pair，產生 blocking problem，不以 nearest、ID 或 entity order 猜測。
- 保留既有 DXF Review lifecycle、source fingerprint safety、manual replay、Pause／Resume 與 Project schema；不修改 Solver、材料規則或 Beam exclusion `±550 mm`。

### In Scope

- Y05 Beam-role root `INSERT` 的 whole-source single-axis／paired-axis 辨識。
- `Waler → Strut → Brace → CornerBrace → Column → Joist` stage order 中，本 change 所需的 immutable Strut／Brace／Column context visibility。
- finite perpendicular crossing、Strut endpoint-face contact、雙 C pair eligibility、Column midpoint eligibility、ambiguity／unpaired diagnostics。
- paired assembly 到 runtime Beam、Review、排除／恢復、Project conversion 的一致映射。
- 目前 Y05 fixture 的完整來源、構件與關係 regression：84 個 Beam-layer root `INSERT` 中，38 個主構件 roots 形成 20 個雙 C paired assemblies（40 支實體 Joists）與六個角落各 3 支 Brace-contact single Joists（18 支），合計 58 支 formal Joists；其餘 46 個高度重疊的 L-angle detail／residual roots 不得另建 Beam；48 組 direct crossing 與 20 組 width-qualified endpoint-face contact 合計形成 68 組 paired-axis-to-Strut contact relations。

### Out of Scope

- 將 `518 ± 5 mm` 或 Column midpoint `±2 mm` 套用到非雙 C、未經 whole-source geometry 證明的 Joist。
- 任意 INSERT point、428 mm 淨距、441／443.5 mm web 間距、外框距離或 Joist width 作為 station spacing 替代值。
- 修改 Waler、Strut、Brace、CornerBrace 或 Column 的 source recognition truth。
- AI／模型訓練、Block 名稱白名單、任意最近距離吸附。
- Solver、Project schema、材料規則或既有 Beam exclusion rule 變更。

## Capabilities

### New Capabilities

- `bim-joist-recognition`: 定義 BIM Joist whole-source single／paired-axis outcome、上游 context、有限垂直接觸、雙 C pairing contract，以及 Review／Project projection。

### Modified Capabilities

- `bim-block-member-recognition`: 讓 Beam-role root `INSERT` 使用專屬 BIM Joist path，並允許已證明的 paired-axis assembly 從一個 root 建立恰好兩個 Beam models，而非誤走 Strut／Brace 或 generic local-pair path。

## Impact

- 預計影響 `dxf_import/importer.py`、`dxf_import/recognition.py`、新增的小型 pure Joist recognition service、`dxf_import/models.py`、`dxf_import/validation.py`、`dxf_import/review_confirmation.py`、`dxf_import/source_exclusion.py`、相關 DXF tests，以及實作完成後的 `docs/ARCHITECTURE.md`／`docs/DOMAIN.md`。
- Architecture direction 不變：Joist recognition 讀取已完成 upstream stages 的 immutable engineering context；pure recognition 不回查 importer mutable state，downstream relationship finalization 不反向改寫 upstream identity。
- Project/Solver truth 不變：Project 僅接收每支 Strut 的 validated `BeamPositions`／`AssociatedBeamIDs`；完整 Beam geometry 與 shared-root provenance 留在 DXF state。
