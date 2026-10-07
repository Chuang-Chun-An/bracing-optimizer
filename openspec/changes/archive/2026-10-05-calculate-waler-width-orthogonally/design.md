# Design

## 閱讀導航

### 現在必須理解

1. **Decision 1：共用 supporting-line 正交距離**——定義 Waler 與既有 CornerBrace 一致的量測公式。
2. **Decision 2：只在「實體 rail 寬度」語意使用新 helper**——保留有限 segment proximity／duplicate 判斷，避免擴大行為變更。
3. **Decision 3：`WalerEnvelopeFacts.source_width` 是唯一 truth**——材料配對、Review baseline 與顯示不得各自重算。

### 遇到特定模組或風險時再讀

- 修改一般 `LINE`／closed-outline candidate 建立時：閱讀 Decision 4。
- 修改 HATCH／MLINE 或 Pause／Resume 時：閱讀「相容性與 persistence 影響」。
- 測試出現大量非 Waler regression 時：閱讀 Risk 1，確認沒有把 `_line_separation()` 全面替換。

## 方案摘要

```text
outer-face qualification
  ├─ finite segment proximity / topology：保留既有 helper
  └─ physical width：shared supporting-line perpendicular helper
                          ↓
                WalerEnvelopeFacts.source_width
                          ↓
          Review baseline + material recognition
```

新增一個純幾何的 symmetric supporting-line separation helper，公式與目前 CornerBrace 正式寬度相同：`(distance(midpoint(A), line(B)) + distance(midpoint(B), line(A))) / 2`。Waler 只在代表實體 rail pair 寬度及相同寬度 gate 的位置使用此 helper；有限線段是否靠近、是否重疊或是否 duplicate 仍使用既有 segment distance。

## 決策對照

| Decision | 對應 spec | 對應 tasks |
|---|---|---|
| Decision 1：共用 supporting-line 正交距離 | 「可靠 Waler envelope 的代表寬度必須使用正交間距」及前三個 scenarios | 1.2、1.3、2.1 |
| Decision 2：限制新 helper 的使用語意 | 不變事項與 HATCH／MLINE regression scenario | 1.3、2.2、3.1 |
| Decision 3：單一 `source_width` truth | Requirement 第二段及 Y29 material scenarios | 1.1、2.1、2.3、2.4 |
| Decision 4：candidate 與 final envelope 使用同一寬度語意 | Y29、旋轉／順序、單線 scenarios | 1.1、2.2、2.3、2.4、3.1 |
| Decision 5：不新增 persistence 或 Solver contract | 單線與 HATCH／MLINE scenarios | 3.2、4.1 |

## Context

動機見 `proposal.md` 的「Why」。目前 `dxf_import.geometry._line_separation()` 計算四個有限端點到另一有限 segment 的距離平均，適合部分有限 segment proximity 判斷，但不等同兩條 physical rail supporting lines 的正交間距。`dxf_import.waler_contact_face._canonical_pair()` 將該值寫入 `WalerEnvelopeFacts.source_width`，因此 Y29 W18 的斜端殘差由 `400.000 mm` 放大為 `404.682 mm`。

CornerBrace 已在 recognition layer 以兩條 rail 中點到對方 supporting line 的正交距離平均定義正式寬度。Waler 可重用同一純幾何語意，不需要新增資料欄位、workflow state 或 UI 邏輯。

本 change 中：

- **supporting line**：一條有限 rail 所在的無限直線。
- **symmetric supporting-line separation**：兩條 rail 各自中點到另一 supporting line 的正交距離平均。
- **finite segment separation**：端點到另一有限 segment 的距離平均；只保留於 proximity／duplicate 等非 physical-width 語意。

現行 Waler 背填／寬度調整的接觸位移為：

```text
contact_displacement
  = adopted_backfill_mm - original_backfill_mm
  + adopted_waler_width_mm - original_waler_width_mm
```

`WalerContactReviewState.contact_displacement` 定義上述公式；`initialize_waler_contact_review()` 只在初始化時以 `Waler.source_width` 同時填入 `original_waler_width_mm` 與 `adopted_waler_width_mm`。`plan_waler_contact_adjustment()` 後續使用 Review 傳入的四個絕對值計算位移，不會再次動態讀取當下 `source_width`。相關位置為：

- `dxf_import/models.py`：`WalerContactReviewState.contact_displacement`。
- `dxf_import/waler_contact_adjustment.py`：`initialize_waler_contact_review()`、`plan_waler_contact_adjustment()` 與沿 `support_normal_world` 平移接觸線的邏輯。
- `dxf_import/source_exclusion.py`：manual contact override 的絕對值 capture／replay。
- `dxf_import/review_workflow.py`：paused Review 的 `manual_overrides` serialization 與重新辨識後 replay。

## Goals / Non-Goals

**Goals:**

- 讓所有可靠 Waler envelope 的 `source_width` 使用正交 supporting-line 間距。
- 讓 candidate width gate 與 final envelope width 使用相同物理寬度語意及既有數值邊界。
- 重用 CornerBrace 已成立的對稱公式，並以一個 pure geometry helper 避免兩套公式 drift。
- 以 Y29 W18 固定使用者可見的寬度與材料配對結果。

**Non-Goals:**

- 不重新設計 envelope topology、rail selection、contact-face finalization 或 material matching。
- 不全面改變 `_line_separation()` 的既有 call sites。
- 不新增 Waler width correction UI、材料 nearest-match、schema migration 或 Solver rule。

## Decisions

### Decision 1：新增共用 symmetric supporting-line separation helper

在 `dxf_import/geometry.py` 建立名稱明確的 private helper，接收兩條非退化 line segments，回傳：

```text
(第一條中點到第二條 supporting line 的正交距離
 + 第二條中點到第一條 supporting line 的正交距離) / 2
```

完全平行時兩項相等；在既有平行角度容許內略有夾角時，對稱平均避免結果依 first／second 選擇而改變。helper 不自行判斷角度、overlap 或工程 eligibility；caller 仍負責既有 gates。

CornerBrace 現有 local helper 改為呼叫此共用 helper或由新 helper直接取代，保持數值行為不變。這讓「與斜撐／角撐一樣使用正交方式」不只停留在兩份相似公式。

**Rejected alternative：**直接使用其中一條 rail 的單向 point-to-line distance。此方式對略不平行 rail 會依參數順序產生不同結果，不符合既有 order-independence。

**Rejected alternative：**把 `_line_separation()` 本身改成 supporting-line distance。該 helper 已被 duplicate、nearby、candidate proximity 等多種有限幾何語意使用，全面改義會造成無關 regression。

### Decision 2：以語意而非函式名稱決定替換範圍

下列位置使用新 helper：

- Waler rail-pair candidate 的實體 `separation`、`source_width` 與同一最大寬度 gate。
- Waler envelope hypothesis 的 physical-width gate。
- `_canonical_pair()` 寫入 `WalerEnvelopeFacts.source_width` 的 width。
- recognized component envelope 對最外 rails 套用最大寬度 gate。
- CornerBrace 正式 rail separation 的既有 wrapper／call site，以確保公式共用且結果不變。

下列位置保留 `_line_separation()`：

- duplicate／collinear／nearby segment 判斷。
- 對 finite geometry 是否落在另一有限線段附近的 qualification。
- 不屬於 Waler physical width 且未由本 change 規格化的 legacy recognition path。

數值 gates（`> collinear_tolerance_mm`、`<= maximum_component_width_mm`）不變，但當 gate 明確判斷 Waler 實體寬度時，輸入值改為正交寬度。

### Decision 3：`WalerEnvelopeFacts.source_width` 維持唯一正式寬度 truth

Waler candidate 的暫時 width 可用於 recognition qualification，但通過完整 envelope extraction 後，`_characterize_waler_candidate_envelope()` 必須繼續以 `WalerEnvelopeFacts.source_width` 覆寫 candidate width。`Waler` model、`initialize_waler_contact_review()`、Material Spec recognition 與 Presentation 只消費這個值，不新增重算公式。

如此可避免：

- candidate 階段與 final envelope 各有不同寬度；
- UI 顯示 `400`、材料配對仍使用 `404.682`；
- manual contact review baseline 保存另一套 width truth。

背填辨識的 `_waler_outer_line()` 會用 `source_width` 排序外側線候選。本次 characterization 中只有 Y29 W18 的寬度有實質變化，且該 Waler 只有一條 `recognized_boundary` 候選，所以修正後不會改變其外側線、背填厚度或正式接觸面。

### Decision 4：保留既有 envelope authority，只校正 width measurement

outer faces 仍由 closed outline、connected contour、MLINE qualified faces、recognized component faces 或 HATCH exterior authority 建立。新 helper不參與選哪兩條 faces，也不改 provisional axis 的 endpoint correspondence。這使接觸面與 connection geometry 保持既有行為，只改 `source_width` 及以 physical width 為目的的 gate。

Y29 regression 以 source handle `69F` 定位 W18，不依可變的顯示編號單獨尋找；測試同時提供 `H400x400` 與 `H414x405` 圍令材料選項，驗證最終自動材料規格為 `H400x400`。

### Decision 5：Architecture Alignment

本 change 沿用現有 Architecture，不修改 layer boundary：

- `dxf_import/geometry.py` 擁有純 WCS 幾何量測。
- `dxf_import/recognition.py` 與 `dxf_import/waler_contact_face.py` 擁有 source recognition、envelope qualification 與 `source_width` 建立。
- `dxf_import/material_recognition.py` 只消費 `source_width`，不解讀 Waler raw geometry。
- Presentation、Application、Domain、Algorithms、Infrastructure 不新增依賴。

依賴方向維持 `DXF Recognition → DXF Models / Geometry`。不建立新 public API；helper 維持 package internal。

## 相容性與 persistence 影響

- Project schema、DXF Review serialized schema 與 Solver input 均不變，不需要 migration。
- 新鮮匯入或因 Source Exclusion／Restore 觸發的 recognition rebuild 會得到修正後寬度與自動材料規格。
- 已完成並保存的 Project 不會被背景改寫；只有重新進行 DXF recognition／apply 才採用新結果。
- 既有 manual material choice 仍依原 contract 優先並可 replay；本 change 不以 corrected auto match 覆寫人工選擇。
- HATCH RC 維持 `auto_hatch` precedence；其矩形／長條 exterior 的正交寬度應與既有值數值等價。
- **已確認決策：本 change 前建立的 paused Review 不保證相容。** 使用者會刪除舊 paused Review 並重新匯入；本 change 不新增 migration、rebase、needs-review fallback 或舊狀態 replay 相容邏輯。
- 原因是 paused Review 保存 `original/adopted_backfill_mm` 與 `original/adopted_waler_width_mm` 四個絕對值；Resume 先重新辨識，再將舊絕對值原樣傳回 adjustment。當 `source_width` 改變時，重播仍保留舊的 `adopted_waler_width_mm - original_waler_width_mm`，不會以新 `source_width` 自動重算。
- 例如舊 W18 由 `404.681630 mm` 採用 `400.000000 mm` 時，保存的寬度位移是 `-4.681630 mm`；若原樣套到新基準 `400.000099 mm`，在背填不變的條件下仍會額外平移 `-4.681630 mm`，而不是以新基準重新得到約 `400 mm` 的採用結果。因此舊 paused Review 必須重新匯入。

以下相容方案已評估但依產品決策不採用：

1. 保留舊差值並接受保存的絕對寬度與新 `source_width` 不一致。
2. 保留舊 adopted 絕對寬度，改用新 `source_width` rebase original，因而改變既有已採用幾何。
3. 偵測 baseline 不一致並將 contact adjustment 標記為 needs-review。

由於舊 paused Review 由使用者刪除並重新匯入，delta spec 不新增 Pause／Resume 相容 Scenario，tasks 也不新增相關 regression。

## Fixture characterization baseline

characterization 使用既有 Y05、Y29、Y1A DXF fixture 的全部已辨識 Waler，比較目前有限 segment 公式與本 change 的 supporting-line 正交公式，並以現有材料 inventory、`width_tolerance_mm = 50.0`、`maximum_component_width_mm = 600.0` 與 `material_width_tolerance_mm = 1.0` 評估下游結果。結果沒有非預期變化，也沒有任何寬度差超過 `50 mm`。

### Y05：16 支

| Waler（source handle） | 舊 `source_width` | 新 `source_width` | 材料／gate 結果 |
|---|---:|---:|---|
| W1（`971`）、W4（`B1D`） | `312.000000` | `312.000000` | 無自動材料；一般 `600 mm` gate 維持通過 |
| W2（`97D`）、W3（`989`）、W5（`B29`）、W7（`C86`）、W8（`C90`） | `350.000000` | `350.000000` | 維持 `H350x350`；gate 維持通過 |
| W6（`B34`） | `331.000000` | `331.000000` | 無自動材料；gate 維持通過 |
| W9（`C72`）、W10（`CA2`） | `0.000000` | `0.000000` | 單線 unknown width；gate 不適用 |
| W11（`ABE`）、W12（`C97`） | `100.000000` | `100.000000` | HATCH `RC` precedence 不變；一般 gate 不適用 |
| W13（`E65`）～W16（`1650`） | `800.000000` | `800.000000` | HATCH `RC` precedence 不變；一般 gate 不適用 |

### Y29：20 支

| Waler（source handle） | 舊 `source_width` | 新 `source_width` | 材料／gate 結果 |
|---|---:|---:|---|
| W1（`74`） | `400.000056` | `400.000056` | 維持 `H400x400`；gate 維持通過 |
| W2（`76`）、W3（`F4`）、W4（`193`）、W5（`211`）、W6（`232`）、W9（`284`）、W11（`4BC`）～W17（`69C`）、W19（`720`）、W20（`721`） | `400.000000` | `400.000000` | 維持 `H400x400`；gate 維持通過 |
| W7（`25E`） | `400.010038` | `400.010038` | 維持 `H400x400`；gate 維持通過 |
| W8（`260`） | `400.009678` | `400.009678` | 維持 `H400x400`；gate 維持通過 |
| W10（`43F`） | `400.000128` | `400.000128` | 維持 `H400x400`；gate 維持通過 |
| W18（`69F`） | `404.681630` | `400.000099` | `H414x405` 改為 `H400x400`；gate 仍通過 |

Y29 只有 W18 有實質變化，差值為 `-4.681531 mm`。W19 維持 `400.000000 mm` 與 `H400x400`。

### Y1A：4 支

| Waler（source handle） | 舊 `source_width` | 新 `source_width` | 材料／gate 結果 |
|---|---:|---:|---|
| W1（`CE83A`）～W3（`CE83C`） | `350.000000` | `350.000000` | 維持 `H350x350`；gate 維持通過 |
| W4（`CE83D`） | `349.948428` | `349.948426` | 僅 `-0.000002 mm` 浮點差；維持 `H350x350`；gate 維持通過 |

W18／W19 overlap 使用 provisional axes、source identity 與有限投影範圍，不讀取 `source_width`；B15 source `71E` 的端點歧義使用同一組 Waler identity／接觸幾何。由於本 change 不改 outer faces、provisional axes 或 contact-face finalization，`WALER_SOURCE_OVERLAP`、`WALER_OVERLAP_COMPETITION` 與 B15 的 `AMBIGUOUS_WALER_CONNECTION` 結果應保持不變，並由 Y29 regression 固定。

## 與 rigid-translation change 的順序

`rigidly-translate-braces-on-waler-adjustment` 的 planning artifacts 已完成但 implementation 尚未開始。該 change 會直接修改 `plan_waler_contact_adjustment()`、runtime Brace baseline、Review replay 與 downstream geometry；本 change 則先改變 recognition 產生並供 contact review 初始化使用的 `source_width`。兩者修改同一條端到端流程，但本 change 的主要直接 call sites 位於 geometry／recognition，rigid-translation change 的主要 call sites 位於 contact adjustment／runtime baseline。

實作順序固定為：

```text
calculate-waler-width-orthogonally
  → 固定修正後 source_width、材料配對與新鮮匯入 baseline
  → rigidly-translate-braces-on-waler-adjustment
```

如此可避免 rigid Brace baseline 建立在之後仍會改變的 Waler width truth 上。

## Risks / Trade-offs

- **[Risk 1]** 誤把所有 `_line_separation()` call sites 全面替換，改變 duplicate 或 proximity behavior。→ 僅替換明確代表 physical rail width 的 call sites，並加入非 Waler regression。
- **[Risk 2]** candidate gate 與 final envelope 使用不同公式，造成先通過後變寬或先拒絕正確 envelope。→ 兩階段的 Waler width gate 與 `source_width` 共用同一 helper。
- **[Risk 3]** 旋轉、line direction 或 argument order 造成浮點差異。→ 使用 symmetric formula，加入 rotation／reversal／source order tests，assert 以適當浮點 tolerance 比較。
- **[Risk 4]** Y29 W18 改為 `H400x400` 後影響 downstream Project／Solver input。→ 這是修正後 `source_width` 經既有材料規則得到的預期結果；執行 targeted importer tests 與相關 DXF regression，且不修改 Solver 本身。
- **[Risk 5]** 本 change 前的 paused Review 以舊絕對寬度重播，可能把舊差值套到新 `source_width` baseline。→ 不提供相容 replay；使用者刪除舊 paused Review 並重新匯入，再以新 baseline 進行檢核。
- **[Trade-off]** 對容許角度內但不完全平行的 rail，代表寬度仍是平均值而非沿長度變化的完整 profile。這沿用 CornerBrace 的既有對稱定義，避免新增 tapered-member 資料模型。

## Migration Plan

1. 先以 Y05、Y29、Y1A characterization 固定全 Waler 的新舊寬度、材料配對與最大寬度 gate baseline；若結果偏離本文件則停止並回報。
2. 以 unit tests 固定 supporting-line helper 與 Waler envelope width。
3. 將 Waler physical-width call sites 切換至共用 helper，保留有限 proximity call sites。
4. 執行 Y29 W18／W19、overlap、B15 ambiguity 與 HATCH／MLINE／contact-face focused regressions。
5. 更新 `docs/WORKFLOW.md` 的 Waler recognition long-term truth。
6. 不進行舊 paused Review migration；使用者刪除舊狀態並重新匯入。若需要 rollback，回復 helper call-site 變更即可，既有 Project 檔案不需轉換。
