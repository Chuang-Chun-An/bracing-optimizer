# Proposal

## 閱讀導航

### P0：現在必讀

- 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
- `specs/dxf-corner-brace-occluded-rail-recognition/spec.md` 的 RailTrack、逐關係 coverage 與完整／遮擋分類。
- `specs/dxf-corner-brace-centerline-extension/spec.md` 的每端 `600 mm` extension 邊界。
- `specs/dxf-corner-brace-repair-tool/spec.md` 的 relationship-selection Preview／Apply。

### P1：實作前閱讀

- `design.md` D1～D8，特別是 `BodyGeometryEvidence`／`BodyRelationshipAssessment` 的責任分界與 canonical-normal clustering。
- `tasks.md` 對應階段與 acceptance tests。
- 三份既有 main specs，確認 delta 修改的完整 Requirement context。

### P2：需要時再讀

- `docs/DOMAIN.md`：只在實作與驗證完成後同步已成立的 CornerBrace 工程規則。
- `docs/WORKFLOW.md`：只有修改 Review Preview／Apply transaction 時閱讀。
- 可先跳過 Solver、材料配置及其他 member recognizer specs；它們不在本 change 範圍。

## 快速摘要

- CornerBrace 先辨識不依賴 Waler／Strut 的本體幾何，再針對每一組有限 Waler／Strut 關係獨立評估 expected span、coverage、gaps、classification 與 extension。
- 完整與遮擋 CornerBrace 都要求兩條 selected rails 各自對該 relationship 的 expected span 達到 `50%` coverage；完整類別不得略過 coverage。
- 每端 outward extension `<= 600 mm` 與每軌 coverage `>= 50%` 是互相獨立且必須同時通過的 hard gates。
- RailTrack 以無方向性的 canonical direction／normal 與 `25 mm` normal spread 全候選列舉；禁止 first-seed、first-fit、entity order 或 fragment iteration order 決策。
- 唯一 body 只有一組 hard-valid relationship 時自動建立；多組時保持 unresolved，由使用者在 Preview 明確選擇並 Apply。

## 現況與目標

| 主題 | Before：目前／舊提案行為 | After：目標行為 |
|---|---|---|
| 本體與關係 | Body truth 混入 expected span、coverage、classification 等 relationship-dependent 資料 | `BodyGeometryEvidence` 只保存本體幾何；每組 Waler／Strut 建立獨立 `BodyRelationshipAssessment` |
| Coverage | 完整類別可能只因雙軌連續而成立；遮擋時才檢查部分軌道 | complete／occluded 都逐軌以 expected span 計算 union coverage，兩軌都須 `>= 50%` |
| Extension | 與 coverage 的責任可能混淆 | Waler 端與 Strut 端各自 `<= 600 mm`，不得補償 coverage 不足 |
| RailTrack | 可能以第一條 seed／representative line 吸附 fragments | 以 canonical normal offset 的整體 spread `<= 25 mm` 建立所有 competing hypotheses，結果與輸入順序無關 |
| 關係歧義 | Body 與 relationship ambiguity 容易混為一體 | Body 零解／多解不可選關係；唯一 body、多組 hard-valid relationships 才可進入 relationship-selection repair |

## 主要流程

```text
exact CornerBrace source finite geometry
  -> 建立無方向性 canonical rail direction / canonical normal
  -> 全列舉 normal spread <= 25 mm 的 RailTrack hypotheses
  -> 全列舉 separation (250, 600] 的 track-pair body hypotheses
  -> 只保存 BodyGeometryEvidence
  -> 對每個 body 列舉 active finite Waler / Strut relationships
  -> 每組建立 BodyRelationshipAssessment
       -> expected span / slenderness >= 3.0
       -> 每軌 union coverage >= 50%
       -> 每端 outward extension <= 600 mm
       -> 無 >50 mm gap：complete
       -> 有 >50 mm gap：occluded，逐 gap 驗證 finite occluder
  -> body 唯一 + hard-valid relationship 唯一：automatic connection
  -> body 唯一 + hard-valid relationships 多組：unresolved + Preview 選擇
  -> body 零解或多解：unresolved，不進入 relationship-selection repair
```

## 不變事項

- Rail separation 維持 `250 mm < separation <= 600 mm`，expected slenderness 維持 `>= 3.0`。
- Direction seed 維持 `>= 100 mm`、方向差 `<= 2°`、track normal spread `<= 25 mm`、seam `<= 50 mm`。
- Near-parallel occluder 與 gap overlap 維持 `>= 50%`；每個大 gap 都需要自己的 finite occluder evidence。
- 端板不是 complete 或 occluded 的必要資格，只能作 terminal evidence 或合法消歧。
- 不修改 Project schema、Solver、Waler identity、一般 Brace／Strut／Waler／Column／Beam／Joist recognition。
- Preview、明確 Apply、revision revalidation、atomic rollback 與 source exclusion lifecycle 維持既有 ownership。

## Why

現行與初版提案仍可能把本體幾何和 Waler／Strut 關係混在一起，並讓 complete 類別繞過逐軌 coverage，或讓 RailTrack 分群受 seed 與輸入順序影響。這會使同一角撐在不同 relationship 下的有效性互相污染，也可能將 600 mm extension 錯當成 coverage 的替代證據。

## What Changes

- **BREAKING**：建立 `BodyGeometryEvidence` 與 `BodyRelationshipAssessment` 兩層契約；complete／occluded classification 只存在於 relationship assessment。
- **BREAKING**：完整與遮擋候選都要求兩條 selected rails 各自 `coverage >= 50%`。
- 正式確認 CornerBrace Waler 端與 Strut 端 outward extension 各自 `<= 600 mm`；此限制與 coverage 必須同時通過。
- RailTrack 使用 canonical direction／normal 與全候選 normal-offset clustering；`max(offsets)-min(offsets) <= 25 mm`。
- 保留所有 competing track hypotheses；若後續 evidence 仍無法唯一消歧，回報 body ambiguity，不依輸入順序決定。
- Body 唯一且多組 hard-valid relationships 時，提供不解析 message 的 structured Preview candidates，由使用者明確 Apply 一組。
- 增加精確數值邊界、排列不變性及 Y05／Y29／Y1A regressions。

## In Scope

- CornerBrace RailTrack clustering、track-pair enumeration 與 relationship-independent body evidence。
- 每組有限 Waler／Strut relationship 的 expected span、slenderness、逐軌 coverage、gaps、occluders、extension、classification 與 hard-valid result。
- Unique-body relationship ambiguity 的 Preview、explicit Apply、revision revalidation 與 rollback。
- Synthetic boundaries 與 Y05 `104C`／`1081`／`F9E`／`FB7`、Y29 `4C`、Y1A regressions。

## Out of Scope

- 從只有一條 rail、任一軌 coverage 低於 `50%`、任一 extension 超過 `600 mm`，或 gap 無法逐一解釋的來源建立正式 CornerBrace。
- 讓使用者以 relationship selection 繞過 body 零解／多解。
- 建立 canonical Waler、合併不同 source identities、使用 first-match／first-fit 或解析 diagnostic message。
- 新增 Project schema、改變 Solver、材料庫、一般構件辨識或 DXF Review transaction ownership。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-corner-brace-occluded-rail-recognition`：分離 body geometry 與 relationship assessment，統一 complete／occluded 的逐軌 coverage，並定義順序無關 RailTrack clustering。
- `dxf-corner-brace-centerline-extension`：正式加入 CornerBrace 每端 `600 mm` outward-extension hard gate，且不得取代 coverage。
- `dxf-corner-brace-repair-tool`：只允許唯一 body 的多組 hard-valid relationships 進入 Preview／explicit Apply。

## Impact

- **Infrastructure／DXF recognition**：`dxf_import/recognition.py`、`dxf_import/models.py` 與必要的同層 private geometry helpers。
- **Review／repair workflow**：`dxf_import/validation.py`、`dxf_import/corner_brace_repair.py`、`dxf_import/review_workflow.py` 與既有 Preview projection。
- **Tests**：CornerBrace recognition／repair／Review tests及 Y05／Y29／Y1A regressions。
- **Long-term truth**：實作驗證後才更新 `docs/DOMAIN.md`；不預期修改 Architecture、Solver 或 Project schema。

## 尚未決定的事項

沒有會改變外部行為或 acceptance criteria 的未決事項。Internal type／helper 命名可依現有 style 調整，但不得改變兩層責任、全候選列舉、數值邊界與 repair eligibility。若實作需要新增 Project schema、改變 Waler identity、使用 first-match／first-fit 或解析 message 文字，必須停止並回報。
