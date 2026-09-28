# Proposal

## Why

BIM 匯出的斜撐常以一個 root `INSERT` 表示一支實體 Brace，但可見輪廓會被投影、遮蔽與細部構造切成多個 fragments。現有 Brace 路徑仍由一般 local parallel-edge recognition 選線，可能只取得局部短段、產生錯誤歧義，或使原本應由 Waler 連到 Waler 的斜撐無法建立正式連接。

## What Changes

- 將已建立的 BIM whole-block geometry interpretation 擴展至使用者分類為 Brace role 的 root `INSERT`，但保留 Strut 與 Brace 各自的 role、diagnostic 與 downstream contract。
- 將一個 Brace root `INSERT` 視為一個獨立 source scope；只有整體 geometry 唯一支持一支實體斜撐時，才從同一 root 的 fragments 重建一條完整、source-supported 的 Brace 工程軸。
- 允許同一 root 內共軸、寬度相容且拓撲一致的 fragments 跨越 interior gaps 共同支持完整軸；不得以局部短平行邊、最長單線、entity order 或跨 root geometry 決定正式 Brace。
- component-like Brace 能可靠建立唯一完整軸時只產生一支 formal Brace；完整 extent 不可靠或存在多個不等價完整軸時，回報以 root handle 為 identity 的 blocking Review problem，且不得退回局部 candidate 強行成功。
- 成功辨識的 Brace 繼續交由既有 Waler connection 流程確認並 snap `FromWaler`／`ToWaler`。Brace 的正式工程關係仍是 Waler-to-Waler；本 change 不以無來源外插、放寬既有 tolerance 或猜測缺失 Waler 來製造連接。
- 保留一般 LINE、MLINE、完整 outline、非 component-like `INSERT`、Nested WCS transform、source exclusion／restore、manual replay、confirmation、Pause／Resume 與 Project conversion 的既有行為。
- 本 change 以 `bim-strut-outline-topology` 完成、同步並成為 current main spec／code 為實作前置條件；不在兩個 change 中維護兩套 topology 真相。

### In Scope

- Brace role root `INSERT` 的 component-like eligibility、root-local fragment consolidation、唯一 whole-axis recognition 與 deterministic outcome。
- 一個 root source 對應最多一支 formal Brace，以及 recognized／not-applicable／failed／ambiguous 的 terminal semantics。
- Brace-specific importer routing、diagnostics、ReviewItem、source identity 與既有 Waler-to-Waler connection regression。
- Y05 BIM Brace sources 的 characterization 與代表性 importer-level regression；明確區分 fragment recognition failure 與既有 Waler recognition／connection failure。
- Strut BIM recognition 與普通 Y1A／Y29 Brace recognition 的 regression protection。

### Out of Scope

- 修改 Waler recognition、Waler connection tolerance、端點 snap 規則或以遠距離無來源外插強制建立 Waler 連接。
- CornerBrace centerline／連接板規則、Strut topology 行為、Double Support、CandidatePoint、材料辨識、Solver 或 optimization。
- Guided Recognition、人工輔助線、AI／影像辨識、跨 root `INSERT` fragment 合併。
- Project schema／persistence migration、原始 DXF 寫回或大型 DXF recognition framework 重構。
- 保證所有 Y05 Brace source 都自動成功；缺乏唯一完整軸或缺少有效 Waler 連接者仍應留在 Review。

## Capabilities

### New Capabilities

- `bim-block-brace-recognition`: 定義一個 BIM Brace root `INSERT` 如何由 fragments 重建唯一完整斜撐工程軸、形成 Waler-to-Waler formal Brace，或以 blocking problem 安全失敗。

### Modified Capabilities

- `bim-block-member-recognition`: 將既有 restricted Strut-only role boundary 擴展為 Strut 與 Brace 各自受限的 BIM root recognition path，同時保留其他 role 與普通 CAD fallback。

## Impact

- `dxf_import/block_member_recognition.py`：在 `bim-strut-outline-topology` 成為 current truth 後，將共用 pure topology／whole-axis primitives 改為 role-neutral contract；Brace-specific policy 不得回寫成第二套 fragment 演算法。
- `dxf_import/recognition.py`、`dxf_import/importer.py`：新增 Brace root routing 與 role-correct candidate／diagnostic mapping，保留一般 recognition fallback 與既有 Waler connection ordering。
- `dxf_import/models.py`、`validation.py`、`review_workflow.py`：優先沿用既有 runtime result、problem 與 root-handle identity；不預期新增 persistence 欄位。
- `tests/test_dxf_bim_block_recognition.py` 與相關 DXF input／validation／review tests：新增 synthetic Brace topology、Y05 characterization、Waler-to-Waler、determinism、failure 與 Strut／普通 Brace regressions。
- `docs/WORKFLOW.md`：實作成立後，將 BIM special recognition current behavior由 Strut-only更新為 Strut／Brace role-aware 路徑。Architecture、Domain 與 Solver truth 不預期改變。
- 不新增第三方 dependency，不修改 Project／Solver API，也不構成 breaking persistence change。
