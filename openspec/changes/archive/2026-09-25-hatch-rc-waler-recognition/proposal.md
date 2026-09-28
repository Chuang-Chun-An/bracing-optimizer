# Proposal

## Why

目前 DXF Import 不讀取 `HATCH`，因此像 Y05 以填充區域表示 RC 圍令的圖面，只剩外框 `LINE` 進入一般辨識；相接的水平與垂直外框可能被合併成無法解讀的 L 形來源，既不能建立正確圍令，也不能自動帶入 `RC` 材料類型。使用者已確認會在 CAD 匯入前維護填充，因此圍令角色圖層中的有效填充可作為明確的 RC 來源語意。

## What Changes

- DXF Import 在使用者指定為 Waler 的圖層中讀取 `HATCH`，不限制 pattern 名稱或是否為實心填充。
- 將每個具有唯一、封閉、可支持單一直線圍令範圍的 HATCH 外邊界視為一個 RC Waler 候選來源；相接但分屬不同 HATCH 的填充區域不得因端點接觸而合併。
- 從 HATCH 邊界推導完整圍令候選，再沿用既有 Waler support-side／inner-contact-face 選擇，正式 Project geometry 仍是既有直線 Waler contract。
- HATCH 辨識成功的 Waler 自動取得 `material_spec = RC`；既有寬度材料辨識不得把它覆寫成鋼材規格。
- HATCH 邊界不完整、非直線型、存在多個互相衝突的完整圍令解，或無法唯一建立工程線時，建立可追溯的 blocking Review 問題，不製造構件。
- HATCH 作為權威來源時，與其邊界等價的獨立 LINE 僅作幾何佐證，不得再被一般 Waler recognition 建立重複構件或重複待修項目。
- 保留既有 Source Exclusion／Restore、fingerprint、Review staged mutation、confirmation invalidation、WCS boundary 與 Project completion lifecycle。

### In Scope

- Waler role layer 的 HATCH boundary extraction、RC Waler candidate recognition 與來源追溯。
- Patterned HATCH 與 solid HATCH 的一致 RC 分類。
- 直線長條型、單一外邊界 RC Waler，以及相接但應分開的多個 HATCH。
- Y05 `1647`／`1650` 與 `E65`／`163D` 類型的回歸案例。
- DXF Review 中的成功辨識、blocking problem、排除、復原、確認及材料顯示。

### Out of Scope

- 依 HATCH pattern 名稱建立材料對照表或新增相關 UI。
- 曲線圍令、L 形單一 HATCH 自動拆段、多個互不連續外邊界共用同一 HATCH 的自動拆件。
- 一般 Steel Waler recognition、BIM Block recognition、Guided Recognition 或其他 member role 的 HATCH 辨識。
- Project schema、Solver、Waler 最佳化規則、Waler contact adjustment 工程公式或原始 DXF 寫回。

## Capabilities

### New Capabilities

- `dxf-rc-waler-hatch-recognition`: 定義 Waler 圖層 HATCH 的有效來源條件、RC 材料分類、正式工程線推導、重複來源抑制及 Review failure behavior。

### Modified Capabilities

無。既有 `rc-waler-optimization-exclusion` 對正式 `material_spec = RC` 的處理保持不變，本 change 僅新增其上游 DXF 辨識來源。

## Impact

- 主要影響 `dxf_import/importer.py`、Waler recognition supporting logic、`material_recognition.py`、Review／source exclusion 的來源身分處理及其相關測試。
- 預期新增小型、可單元測試的 HATCH boundary／RC Waler recognition service，避免把特殊辨識規則加入 Presentation。
- `DXFImportResult`、Project rows 與 Project persistence schema 不變；辨識結果仍透過既有 `Waler` model 與 `material_spec` contract 進入 Main。
- 不新增第三方 dependency；使用現有 `ezdxf` 讀取 HATCH boundary。
- Architecture 與 Solver truth 不變。完成後若此辨識行為成為長期現況，僅需評估是否在 `WORKFLOW.md` 或相關 DXF 文件補充，不改變 `DOMAIN.md` 的 RC Waler／Solver 定義。
