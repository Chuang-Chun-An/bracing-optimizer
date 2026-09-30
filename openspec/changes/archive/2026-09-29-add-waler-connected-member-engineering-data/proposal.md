# Proposal

## 閱讀導航

### P0：現在必讀

- 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
- `specs/dxf-review-engineering-data-presentation/spec.md` 的「圍令直接連接構件顯示」Requirement；定義使用者可見內容與關聯邊界。
- `design.md` 的 D1～D3；定義 single source of truth、唯讀彙整與顯示格式。

### P1：實作前閱讀

- `tasks.md` 對應的 focused tests 與 regression 順序。
- main spec `openspec/specs/dxf-review-engineering-data-presentation/spec.md`，確認既有工程資料 Presentation contract。
- `docs/ARCHITECTURE.md` 的 DXF Import 與 Presentation 責任，以及 `dxf_import/models.py`、`dxf_import/dialog.py` 的現有資料流。

### P2：需要時再讀

- `openspec/changes/redesign-corner-brace-occlusion-recognition/`：只有在角撐正式 connection 結構於實作前發生變更時閱讀並重新核對整合點。
- `openspec/specs/dxf-waler-contact-face-recognition/spec.md`：只有修改 Waler connection finalization 時才需閱讀；本 change 不修改該流程。
- 可先跳過 Solver、材料配置、Project persistence 與 DXF recognition 其他 specs；它們不在本 change 範圍。

## 快速摘要

- 現在選取支撐或斜撐時可由工程資料看見兩端圍令，但選取圍令時看不到反向連接的構件。
- 本 change 讓 DXF Review 的圍令工程資料分別顯示已正式連接的支撐、斜撐與角撐 ID。
- 顯示只使用現有正式關聯保存的 Waler member identity：`FromWaler`／`ToWaler` 與正式 CornerBrace connection；不得以 Treeview item ID、顯示文字、source handle、距離、相交或候選關係猜測。
- CornerBrace 只有在目前 staged result 同時存在正式 member 與正式 adopted connection 時才可顯示；orphan／stale connection 與 Preview temporary selection 必須排除。
- 關聯摘要是即時計算的唯讀 Presentation 資料，不新增 Waler 欄位、Project schema、persistence 或 Solver input。

## 現況與目標

| 主題 | Before：目前行為 | After：目標行為 |
|---|---|---|
| 圍令工程資料 | 顯示 ID、座標、材料規格、備註與長度，沒有反向連接資訊 | 額外分組顯示「直接連接支撐」、「直接連接斜撐」與「直接連接角撐」 |
| 關聯來源 | Strut／Brace 保存 `FromWaler`、`ToWaler`；CornerBrace 有正式 connection，但圍令畫面未彙整 | 從同一份 `DXFImportResult` 的正式關聯唯讀反查，不建立第二份 truth |
| Identity | UI selection 與正式 member identity 在畫面流程中同時存在，但尚未明定反查只能使用哪一個 domain | 以目前選取正式 Waler member 的 identity，和 connection contract 保存的同類 Waler member identity 比對；禁止以 UI／來源 metadata 代替 |
| CornerBrace 完整性 | 正式 connection record 與目前 staged CornerBrace member 的共同存在尚未成為顯示條件 | 只有正式 member 與正式 adopted connection 同時存在且指向所選 Waler 才顯示 |
| 無關聯狀態 | 使用者無法由圍令工程資料判斷是沒有連接或只是未顯示 | 每一類沒有正式關聯時明確顯示 `—` |
| 候選與歧義 | Review 中可能存在尚未採用的候選或 unresolved 關係 | 未正式採用的候選、鄰近構件及幾何推測不得列入 |

「直接連接」在本 change 中是指構件已有正式 Waler identity 關係，不是幾何上靠近、相交、共線或屬於同一 Waler chain。

## 主要流程

```text
使用者在 DXF Review 選取 Waler
  -> 讀取目前 staged DXFImportResult
  -> 取得 selected formal Waler member identity
  -> 以同一 identity domain 反查 Strut / Brace 的 FromWaler、ToWaler
  -> 交集目前正式 CornerBrace members 與 adopted connections
  -> 依構件類型去重並建立穩定顯示順序
  -> 在右側工程資料顯示三個唯讀關聯列
```

## 不變事項

- 不修改 Strut、Brace、CornerBrace 或 Waler 的辨識、連接建立與 validation 規則。
- 不修改 Waler contact face、CornerBrace repair／selection 或 Review confirmation lifecycle。
- 不新增或修改 Project row、Project schema、序列化資料、匯出欄位或 Solver input。
- 不把 Column、Beam、相鄰 Waler、同一 Waler chain 或只有幾何鄰近的構件列為直接連接構件。
- 不讓顯示排序、構件 ID 或集合順序參與工程關聯判定。
- 不使用 Treeview item ID、畫面 label、collection index、source handle、entity order 或 format 後欄位值代替正式 Waler member identity。
- 不因 orphan／stale connection、已排除 CornerBrace 或任何 Preview temporary state 自行建立、修復或重新指派 connection。

## Why

DXF Review 已能從支撐與斜撐查看其連接圍令，但缺少由圍令反查直接連接構件的視角，使使用者無法在檢核圍令時快速確認連接拓撲是否完整。現有正式關聯資料已足以建立此摘要，因此應在不複製工程狀態的前提下補足可見資訊。

## What Changes

- 選取正式 Waler 時，在右側工程資料新增「直接連接支撐」、「直接連接斜撐」及「直接連接角撐」。
- 使用既有正式關聯反向彙整構件 ID，對重複關聯去重並提供 deterministic 顯示順序。
- 明定 selected Waler 與各類 formal connection 使用相同 Waler member identity domain 進行 exact equality；若未來 domain 不同，只能使用既有正式 mapping。
- 角撐摘要須同時驗證目前 staged result 存在正式 CornerBrace member 與對應 adopted connection，排除 orphan／stale records。
- 每一類沒有正式連接時顯示 `—`，不省略欄位，讓空集合狀態可辨識。
- 明確排除 unresolved／尚未採用的候選關係及任何 Presentation 幾何猜測。
- 保持工程資料顯示為唯讀投影，不回寫或擴張 Project／Solver contract。

## In Scope

- DXF Review 選取正式 Waler 時的右側工程資料內容。
- Strut、Brace 與正式 CornerBrace connection 的反向彙整、去重與顯示順序。
- 正式 Waler identity 與 UI／Treeview identity 的分離，以及 staged rebuild 後的重新投影。
- 正式 CornerBrace member 與 adopted connection 的交集過濾。
- 中文欄位名稱、空值表示與對應 Presentation tests。
- 既有非 Waler 構件工程資料的 regression coverage。

## Out of Scope

- 點擊關聯 ID 後跳轉或選取其他構件。
- 顯示連接位置、station、距離、方向、來源 handle 或候選信心。
- 建立 Waler chain、相鄰 Waler 或 Column／Beam 的新關聯語意。
- 修改 recognition、repair、validation、Project persistence、匯出或 Solver。
- 處理與本顯示需求無關的 `dialog.py` 重構或 UI cleanup。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `dxf-review-engineering-data-presentation`：新增圍令直接連接支撐、斜撐與角撐的唯讀工程資料顯示，並定義正式關聯、空集合及候選排除行為。

## Impact

- **DXF Review Presentation**：`dxf_import/dialog.py` 的工程資料列組裝，以及共用中文欄位標籤。
- **DXF Import read model**：唯讀使用 `DXFImportResult.walers`、`struts`、`braces` 與正式 `corner_brace_connections`；不改變 model contract。
- **Tests**：擴充 `tests/test_dxf_review_layout.py` 與必要的 field-label tests，涵蓋 identity domain 分離、rebuild／collection reorder、CornerBrace member＋connection 交集、orphan／stale 與候選排除、不可變性及非 Waler regression。
- **Architecture／Domain／Solver／Workflow truth**：不預期改變；這是既有正式關聯的 Presentation 擴充。

## 尚未決定的事項

沒有會改變外部行為或 acceptance criteria 的未決事項。彙整 helper 的具體函式名稱與放置位置屬 Implementation Choice；若實作需要新增持久化欄位、從 geometry 重新推導關係，或現行 CornerBrace 正式 connection contract 已被其他 change 改寫，必須停止並重新評估本 proposal 與 design。
