# Proposal

## 閱讀導航

### P0｜現在必讀

1. 本文件「快速摘要」與「現況與目標」：確認為何幾何上成立的雙路支撐目前會完全消失。
2. 本文件「主要流程」與「不變事項」：確認暫定候選何時可見、何時才可正式生效。
3. `specs/dxf-double-support-recognition/spec.md`（建立後）的「幾何候選與工程資格必須分層」及「暫定候選不得提前產生正式效果」。

### P1｜實作前閱讀

- `design.md` Decision 1～4：候選狀態模型、重建流程、Review 呈現及下游隔離。
- `dxf_import/support_pairing.py` 的 `detect_double_support_candidates()`：現行幾何與 Waler topology gate。
- `dxf_import/dialog.py` 的雙路支撐設定視窗，以及 `dxf_import/review_workflow.py` 的 candidate commit／rebuild 流程。
- `openspec/specs/dxf-waler-contact-face-recognition/spec.md` 的「接觸面選擇必須先建立 member-to-Waler 關係」與「接觸側無法唯一決定時必須保守失敗」。
- `openspec/specs/support-adjacency/spec.md` 中已確認 `SharedLayoutGroup` 才可成為 initial-grouping ordering unit 的規則。

### P2｜需要時再讀

- `openspec/specs/paused-dxf-review-source-relink/spec.md`：只有修改 Pause／Resume 或 compatible-source recovery 時才需檢查。
- `docs/WORKFLOW.md` 的 DXF Review lifecycle：只有處理 staged mutation、confirmation invalidation 或保存邊界時再讀。
- 可先跳過 Support／Waler Solver 搜尋、評分、材料比例與 candidate cache 章節；本 change 不修改 Solver。

## 快速摘要

- 現行流程在雙路幾何計算前要求兩支 Strut 都具有唯一 Waler 連接，因此像 S19／S36 這種間距、平行、重疊與長度均符合，但 Waler 尚有歧義的配對，不會出現在雙路支撐介面。
- 本 change 將「幾何上可能是雙路」與「已具備正式工程資格」分開；Waler 缺失或歧義時，只以可靠、source-supported 的 WCS Strut axes建立帶原因的暫定候選，任一 Strut 缺少可靠來源軸線時不建立候選。
- Waler 問題解決後，系統使用目前 canonical finalized Strut axes重新計算全部幾何門檻與 topology；若結果為 `eligible`，依 explicit decision、既有 eligible default 與 one-to-one policy決定 accepted state，不要求僅因先前為 pending而再次手動確認。
- 暫定候選不得建立 `SharedLayoutGroup`、共享 Column／Beam constraints、進入 initial Zoning ordering unit 或影響 Solver。
- 本 change 不放寬既有雙路幾何數值，也不以 Column 位於兩支 Strut 中間取代 Waler 一致性要求。

## 現況與目標

本文件所稱「暫定雙路候選」，是指兩支 Strut 已通過既有雙路幾何門檻，但尚未證明具有相容且唯一的 Waler topology，因此只能供 Review 提示，不能成為正式雙路支撐。

| 面向 | Before｜現況 | After｜目標 |
| --- | --- | --- |
| 候選建立 | 缺少任一端唯一 Waler 連接時，在幾何比較前直接略過 | 可靠、source-supported 的 WCS Strut axes先通過既有幾何門檻，再獨立判定 Waler topology；缺少可靠軸線者不建立 pair |
| Review 可見性 | 幾何高度符合但 Waler ambiguous 的配對完全不顯示 | 雙路支撐介面顯示暫定候選及具體警告原因 |
| 使用者理解 | 只能從其他 problem 推測為何沒有雙路候選 | 可直接看到配對、幾何量測、目前狀態及待處理 Waler 問題 |
| Waler 修正後 | 重建後才可能突然出現新候選 | 以目前 canonical finalized axes重建完整 pairing graph並重算所有門檻；`eligible` 結果依 explicit decision、既有 default及one-to-one policy決定accepted state |
| 下游效果 | 只有 accepted candidate 產生共享關係 | 維持只有工程資格成立且 accepted 的候選能產生正式效果 |

## 主要流程

```text
辨識 Struts
  → 只有可靠、source-supported 的 WCS axes 可套用既有角度／間距／重疊／長度門檻
  → 評估兩支 Struts 的 Waler topology
      ├─ 唯一且相容：eligible candidate
      ├─ 缺失或歧義：暫定候選＋可理解警告
      └─ 已唯一但明確不相容：不提供為可接受候選，保留診斷
  → 使用者修正端點或 Waler 關係
  → 從目前 canonical Review state 重建整張 pairing graph，重新計算幾何與 topology
  → eligible candidate 依 explicit decision、既有 eligible default 與 one-to-one policy 決定 accepted state
  → 只有 eligible && accepted 的候選產生 SharedLayoutGroup 與下游關聯
```

## 不變事項

- 既有 `double_support_spacing_mm = 1000`、間距容差 `150 mm`、投影重疊率 `0.9`、長度差容差 `250 mm` 與平行角容差維持不變。
- Waler identity／contact face 多解仍是 blocking Review problem；本 change 不任選 Waler、不合併不同 source identities，也不繞過既有 Waler 規格。
- `pending_waler` 的 provisional axes及量測只供Review提示；不得成為Project geometry或任何正式雙路效果。canonical state改變後不得原地切換status，必須以重新辨識結果完整重算。
- Column／Beam 只作為顯示用輔助 evidence；不得單獨建立或合法化雙路支撐。
- `eligible`、`pending_waler`與`incompatible_waler`都保留在完整geometry-qualified pairing graph的one-to-one conflict判斷中；只有`eligible && accepted`可共享Column／Beam constraints、建立`SharedLayoutGroup`、參與initial Zoning或進入Solver。
- 原始 DXF immutable、source provenance、Project schema、Solver 規則、材料規則及完成匯入 transaction boundary 不變。

## Why

目前雙路支撐偵測把唯一 Waler 連接當成建立候選前置條件，使使用者看不到幾何已高度符合、但仍待解決 Waler 歧義的配對。這會隱藏可操作的工程線索，也無法清楚引導使用者先修正 Waler 關係再完成雙路確認。

## What Changes

- 只以可靠、source-supported 的 WCS Strut axes套用既有雙路幾何門檻建立 geometry-qualified pair，並另外計算其 Waler topology qualification。
- 為候選提供可觀察狀態與 reason codes，至少區分可確認、Waler 待處理，以及已明確不相容。
- 在雙路支撐設定介面顯示 geometry-qualified 暫定候選、警告原因與幾何量測，並禁止暫定候選被接受。
- Waler／端點修正造成 Review rebuild 時，以目前 canonical finalized axes重建完整 pairing graph，重新計算angle、spacing、overlap、length difference、topology及one-to-one ambiguity；不得沿用provisional量測或原地升級status。
- pending pair重算為`eligible`時，依source-safe explicit decision、既有eligible default及one-to-one policy決定accepted state；explicit rejection與one-to-one ambiguity均優先阻止default acceptance。
- 嚴格隔離暫定候選與正式 accepted candidate 的衍生效果。
- 加入 S19／S36／C26 等價案例的 importer、workflow、UI 與下游隔離 regression coverage。

### In Scope

- DXF 雙路支撐候選偵測、狀態與 diagnostics contract。
- DXF Review 雙路支撐設定視窗的候選狀態、警告與操作限制。
- 幾何或 Waler relationship rebuild 後的候選升級、降級及決策安全。
- `SharedLayoutGroup`、Column／Beam association、initial Zoning 與 Project row conversion 的隔離驗證。

### Out of Scope

- 修改任何雙路幾何數值門檻或新增未確認的工程尺寸。
- 在缺乏可靠、source-supported Strut axis時，由Waler candidates、Column／Beam proximity或附近幾何猜測支撐軸線。
- 自動合併 W17／W20、W18／W19 等不同 Waler source identities，或改寫 Waler contact-face recognition。
- 允許使用者在 Waler topology 未解決時強制建立正式雙路群組。
- 以 C26 或其他 Column／Beam proximity 作為雙路支撐必要或充分條件。
- 修改 Support Solver、Waler Solver、Project persistence schema、材料辨識或一般 Strut recognition。

## Capabilities

### New Capabilities

- `dxf-double-support-recognition`: 定義雙路支撐的幾何候選、Waler topology qualification、Review 警告、狀態轉換與正式效果隔離。

### Modified Capabilities

- 無。`dxf-waler-contact-face-recognition` 的保守 ambiguity 規則與 `support-adjacency` 的已確認 `SharedLayoutGroup` 規則維持不變，作為本 capability 的上、下游約束。

## Impact

- 主要影響 `dxf_import/support_pairing.py`、`dxf_import/models.py`、`dxf_import/dialog.py`、`dxf_import/review_workflow.py` 與候選 rebuild／serialization helper。
- 下游需檢查 `dxf_import/candidate_points.py`、`dxf_import/initial_zoning.py` 及 `DXFImportResult.to_project_rows()` 仍只消費正式 accepted candidate。
- 測試主要影響 `tests/test_double_support.py`、DXF Review layout／workflow／recovery tests，以及 Y29 `S19`／`S36` regression。
- 預期沿用既有 Architecture，不修改 Domain 或 Solver truth；實作完成後應最小幅更新 `docs/WORKFLOW.md`，記錄 DXF Review 可見的 provisional double-support lifecycle。若實作發現必須改變 Project schema 或 Waler identity 規則，須先停止並重新評估 scope。

## 尚未決定的事項

- 暫定候選在介面中的視覺形式（獨立狀態欄、警告圖示或詳細說明區）屬 Presentation implementation choice，但必須同時做到狀態可辨識、原因可讀、不可接受。
- 已唯一但明確連到不同 Waler topology 的 geometry-qualified pair，預設只保留為 diagnostics，不列入一般可操作清單；若實作調查顯示使用者需要在同一視窗檢視，才重新評估是否提供預設收合的「不相容候選」區。
