# Proposal

## 閱讀導航

### P0 現在必讀

1. 本文件「快速摘要」與「現況與目標」：確認 Y29 W18 的問題與預期結果。
2. 本文件「主要流程」與「不變事項」：確認只改變可靠 Waler envelope 的寬度量測，不改變接觸面或 Solver 規則。
3. `openspec/specs/dxf-waler-contact-face-recognition/spec.md` 的「Waler 來源辨識必須保留完整構件 envelope」：理解現有 envelope authority。

### P1 實作前閱讀

- `design.md` 的「Decision 1：以 supporting-line 正交間距作為 Waler 寬度」與「Decision 2：集中量測語意」；實作者需先確認 width helper 與 envelope 建立點。
- 本 change delta spec 的「可靠 Waler envelope 的代表寬度必須使用正交間距」Requirement，特別是 Y29 W18 與來源順序不變 scenarios。
- `dxf_import/geometry.py` 的 `_line_separation()`、`dxf_import/waler_contact_face.py` 的 `_canonical_pair()`，以及 `dxf_import/recognition.py` 的 Waler candidate／envelope 流程。

### P2 需要時再讀

- `dxf_import/material_recognition.py`：確認修正後的 `source_width` 仍沿用既有 `±1 mm` 唯一材料規格配對。
- `design.md` 的「相容性與 persistence 影響」：確認本 change 前建立的 paused Review 不保證相容，使用者須刪除並重新匯入。
- `openspec/specs/dxf-rc-waler-hatch-recognition/spec.md`：只有驗證 HATCH RC regression 時需要；HATCH 行為不是本次修改目標。
- 可先跳過 Solver、Waler plan evaluation、Brace terminal identity 與 overlap competition 的其他 Requirements；本 change 不改其規則。

## 快速摘要

- Y29 W18 的兩條縱向外側線正交間距約為 `400.000 mm`，但現行有限線段端點距離平均把斜端影響納入，得到 `404.682 mm`。
- Waler 寬度將與 Brace／CornerBrace 的正式寬度語意一致：使用兩條已選外側 supporting lines 的正交間距，不使用有限端點到另一線段的平均距離。
- 修正後 Y29 W18 應辨識為約 `400.000 mm`；在目前圍令材料規格中應改為自動匹配 `H400x400`，不再匹配 `H414x405`。
- Y05、Y29、Y1A 全 Waler characterization 顯示只有 Y29 W18 有實質寬度變化，且沒有既有材料最大寬度 gate 翻轉；Y29 W19 維持約 `400.000 mm` 與 `H400x400`。
- Waler envelope qualification、接觸側選擇、材料配對容差、Project schema 與 Solver 行為維持不變；但本 change 前建立的 paused Review 不保證相容，須刪除後重新匯入。

## 現況與目標

「Supporting line」是有限 rail 所在的無限直線；「正交間距」是兩條平行 supporting lines 之間沿法向量量得的距離。

| 項目 | Before | After |
|---|---|---|
| Waler envelope 寬度 | 四個有限 rail 端點到另一有限線段距離的平均 | 已選兩條外側 supporting lines 的對稱正交間距 |
| 斜端／縱向錯位 | 可能增加 `source_width` | 不影響同一對平行外側線的寬度 |
| Y29 W18（source `69F`） | 約 `404.682 mm`，自動匹配 `H414x405` | 約 `400.000 mm`，以相同規則匹配 `H400x400` |
| 材料規格配對 | 唯一規格寬度落在 `source_width ±1 mm` 才自動套用 | 不變，只消費修正後的 `source_width` |

## 主要流程

```text
qualified Waler component envelope
  → 選定兩條最外 longitudinal faces
  → 由 supporting lines 計算正交間距
  → 寫入唯一 source_width
  → 既有 contact-face finalization
  → 既有 ±1 mm 材料規格配對
```

## 不變事項

- 不放寬或縮緊 Waler component／envelope 的辨識資格、平行角度、projection overlap、最大一般構件寬度或 ambiguity 規則。
- 不改變哪兩條線被選為外側 faces，也不改變支撐側與正式接觸面選擇。
- 不改變 `material_width_tolerance_mm = 1.0`、H 型鋼第二尺寸作為 plan width、唯一匹配或人工改選規則。
- 不改變 HATCH RC 的分類優先權、單線 Waler 的 unknown width、Source Exclusion／Restore、Project schema 或 Solver input。
- 不提供本 change 前 paused Review 的 migration 或 replay 相容保證；使用者會刪除舊 paused Review 並重新匯入，新版建立的 Review 才以修正後 `source_width` 作為 baseline。

## Why

一般 Waler 已建立可靠的兩條外側縱向 faces 後，現行寬度仍受有限線段端點錯位或斜端影響，會把非橫向尺寸算進 `source_width`。Y29 W18 因此由實際約 `400 mm` 被高估為 `404.682 mm`，並意外觸發 `H414x405` 自動材料匹配；寬度需要改為一致且可解釋的正交量測。

## What Changes

- 將可靠 Waler envelope 的代表寬度定義為兩條已選外側 supporting lines 的正交間距。
- 讓縱向端點錯位、斜端長度及有限 segment overhang 不再改變同一外側 rail pair 的寬度。
- 新增 Y29 W18 source `69F` regression，固定約 `400.000 mm` 的寬度，以及在目前材料規格中改為匹配 `H400x400`、不再匹配 `H414x405` 的結果。
- 新增 Y29 W19 source `720` regression，固定約 `400.000 mm` 與 `H400x400`，並確認 W18／W19 overlap、competition 與 B15 source `71E` 端點歧義不受寬度公式修正影響。
- 在實作前 characterization Y05、Y29、Y1A fixture 的所有 Waler，比較新舊 `source_width`、材料自動配對與最大寬度 gate；若結果超出已記錄基準則停止並回報，不調整辨識規則。
- 新增乾淨對齊、任意旋轉、端點錯位、來源順序／方向反轉及既有 HATCH／MLINE 回歸驗證。
- 實作完成後更新 `docs/WORKFLOW.md`，把 Waler `source_width` 的正交量測寫入 long-term recognition truth。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-waler-contact-face-recognition`：補充可靠 Waler envelope 的代表寬度必須由已選外側 supporting lines 的正交間距計算，且不得受有限端點錯位或斜端影響。

## In Scope

- 一般 CAD／BIM／MLINE 路徑在已建立可靠 Waler outer faces 後的 `source_width` 計算。
- 共用純幾何 helper 的命名與責任調整，只限支援正交 supporting-line 間距。
- Y05、Y29、Y1A 全 Waler characterization，以及 Y29 W18／W19 material-recognition、overlap 與 B15 ambiguity regression tests。
- 與新 long-term truth 直接相關的 Workflow 文件更新。

## Out of Scope

- 改變 Waler outer-face candidate qualification、component splitting、接觸側、connection identity 或 overlap diagnostics。
- 修改材料規格名稱解析、`±1 mm` 配對容差或改成 nearest-match。
- 遷移、重播或修復本 change 前建立的 paused Review；這些舊狀態由使用者刪除並重新匯入。
- 修正 Y29 其他 Waler／Brace／Strut 問題或既有 168 項 Review 錯誤。
- 修改 Solver scoring、candidate count、beam width、搜尋階段、合法性或 Project persistence schema。

## Impact

- 主要受影響程式：`dxf_import/geometry.py`、`dxf_import/waler_contact_face.py`；必要時僅調整直接消費同一量測 helper 的 Waler recognition call sites。
- 主要受影響測試：`tests/test_dxf_waler_contact_face_recognition.py`、`tests/test_dxf_material_recognition.py`，以及使用 `assets/sample_dxf/Y29_test.dxf` 的 importer regression。
- 使用者可見影響：Y29 W18 的來源寬度與材料自動匹配結果會改變；其他幾何等價、端點對齊的 Waler 應維持既有結果。
- Review 相容性：本 change 前建立的 paused Review 不保證相容，也不提供 migration；重新匯入後，Waler contact review baseline 才會以修正後的 `source_width` 初始化。
- Architecture：不變，仍由 DXF subsystem 的 pure geometry／recognition 負責。
- Domain／Workflow truth：新增 Waler 代表寬度的正式正交量測定義；Solver truth 不變。

## 實作順序與相關 change

- `rigidly-translate-braces-on-waler-adjustment` 的 planning artifacts 已完成，但尚未開始 implementation；該 change 會直接修改 Waler contact adjustment、runtime baseline、replay 與下游 Brace 幾何。
- 本 change 先完成並固定修正後的 `source_width`、材料配對與新鮮匯入 baseline；之後才實作 `rigidly-translate-braces-on-waler-adjustment`。
- 兩份 change 的語意交集是 Waler contact review baseline，但本 change 不修改 Brace rigid-translation 規則，也不替舊 paused Review 提供相容處理。

## 已確認量測語意

- 完全平行的 faces 使用其 supporting lines 的固定正交間距。
- 在既有 `parallel_angle_tolerance_deg` 內但非完全平行的 faces，沿用 CornerBrace 已成立的對稱量測：分別量取每條 face 中點到另一條 supporting line 的正交距離，再取兩者平均。不得回退到有限 segment 距離、端點平均或最小／最大寬度。
