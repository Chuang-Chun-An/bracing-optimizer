# Proposal

## Why

Y05 的 S10（root `INSERT` handle `D17`）顯示：同一 BIM Strut Block 內可同時包含一個完整構件外框，以及同軸但不具封閉拓撲的內部 detail rails。現行一般平行邊 fallback 會跨越這些不同來源拓撲配對長邊，產生數條分數相同但橫向偏移的中心線；雖會留下歧義訊息，仍可能先採用其中一條錯誤工程線。

本 change 要讓同一 Strut root source 的外框拓撲成為配對證據的一部分：可驗證的同軸外框可以共同支持一支 Strut，但不同輪廓或無 companion provenance 的開放 rails 不得交叉配成工程中心線。構件寬度必須從唯一、完整且可靠的 component envelope 推導，不得把 Y05 D17 的約 350 mm 寬度硬編碼為所有 Strut 的固定寬度。

## What Changes

- 對位於 Strut role layer 的 root `INSERT`，建立以來源拓撲為基礎的 longitudinal rail／outline pairing 判定。
- 對同一 root 中幾何等價的同軸多層外框，重建唯一共同工程軸，而非跨外框產生偏移中線。
- 將工程軸與構件寬度分開判定：`source_width` 由唯一完整 component envelope 取得；內部開放 detail rails 不得覆寫寬度。若軸線唯一但寬度無法可靠判定，保留軸線並交由既有材料 Review 處理，不猜測材料寬度。
- 若同一 root source 仍支持多條不等價、無法唯一選出的完整工程軸，產生 blocking ambiguous ReviewItem，且不建立 formal Strut。
- 強化「一個 root Strut source 最多一支 formal Strut」為辨識前的 terminal 行為，而非只在後段檢查多個已建立模型。
- 增加 Y05 S10 (`D17`) 與合成 topology fixtures 的回歸保護。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `bim-block-member-recognition`: 補充 Strut root `INSERT` 的同源外框拓撲、parallel-rail pairing、可變構件寬度、唯一工程軸與 blocking ambiguity 行為。

## Impact

- 預期影響 `dxf_import/block_member_recognition.py`、`dxf_import/recognition.py`、`dxf_import/importer.py`、既有 validation／Review problem mapping，以及 `tests/test_dxf_bim_block_recognition.py` 與相關 DXF importer tests。
- 不變更 Project schema、Solver、CandidatePoint、Double Support 工程規則、原始 DXF、source fingerprint、材料規格定義或一般非 BIM DXF 的辨識契約。所有合法支撐寬度均小於現有 `maximum_component_width_mm = 600` 的辨識上限，本 change 沿用該具名設定，不調整數值。
- 不預期變更 Architecture、Domain 或 Solver 長期文件；完成後可能需要在 `WORKFLOW.md` 的 DXF recognition current behavior 補充已實作的可觀察行為。
