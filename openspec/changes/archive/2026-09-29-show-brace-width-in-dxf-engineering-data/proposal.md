# Proposal

## 閱讀導航

- **P0／現在必讀**：本文件的「快速摘要」、「現況與目標」、「In Scope／Out of Scope」；先確認本次只改右側工程資料的顯示範圍。
- **P0／現在必讀**：`specs/dxf-review-engineering-data-presentation/spec.md` 的「斜撐與角撐寬度顯示」Requirement；確認可觀察行為與未知值處理。
- **P1／實作前閱讀**：`design.md` 的「Decisions」與「Data Flow」；確認寬度直接取自既有 `source_width`，且不改 Project row contract。
- **P1／實作前閱讀**：`tasks.md`；依 Presentation、測試、驗證順序執行。
- **P2／需要時再讀**：`openspec/specs/bim-block-brace-recognition/spec.md` 與 `openspec/specs/dxf-corner-brace-occluded-rail-recognition/spec.md` 中的寬度來源規則。若沒有修改辨識結果或寬度算法，可先跳過其他辨識、修補、Solver 與 persistence spec。

## 快速摘要

- DXF 匯入複核目前保存斜撐與角撐的可靠來源寬度，但右側「工程資料」沒有直接呈現。
- 選取正式斜撐或角撐後，右側工程資料將新增「構件寬度（mm）」列。
- 有可靠寬度時固定顯示三位小數；寬度未知或不可靠時顯示「—」，不猜測數值。
- 寬度沿用既有 `source_width`，不重新量測、不回寫資料，也不修改 Project schema、辨識、Solver 或左側清單／預覽。

## 現況與目標

| | Before | After |
|---|---|---|
| 斜撐 | 右側工程資料顯示編號、關聯、端點與長度，但沒有寬度 | 在既有資料列中增加「構件寬度（mm）」 |
| 角撐 | 右側工程資料顯示構件資料與長度，但沒有寬度 | 在既有資料列中增加「構件寬度（mm）」 |
| 未知寬度 | 使用者必須從辨識資料判讀，或可能誤把缺值當成零 | 工程資料明確顯示「—」，不製造工程數值 |

## 主要流程

```text
使用者在 DXF Review 選取斜撐或角撐
                    |
                    v
Presentation 讀取既有 member.source_width
                    |
          +---------+---------+
          |                   |
          v                   v
  有可靠正值寬度         無可靠正值寬度
  顯示 350.000            顯示 —
          |                   |
          +---------+---------+
                    v
        只更新右側工程資料顯示
```

## 不變事項

- 不改變斜撐、角撐的辨識方式、寬度推導、中心線、端點或關聯。
- 不改變 `source_width` 的資料語意，也不由 Presentation 重新計算寬度。
- 不改變 Project row、Project schema、序列化格式、Solver input 或材料規格。
- 不在左側構件清單、DXF 預覽、角撐修補預覽或匯出結果新增寬度標示。
- 人工修補角撐若沒有可靠來源寬度，仍顯示「—」，不繼承或猜測參考角撐寬度。

## Why

斜撐與角撐的寬度已由 DXF 辨識模型保存，但使用者在右側工程資料檢核構件時無法直接看到，必須跨區域查找。將可靠寬度放在工程資料中，可讓幾何尺寸在同一處完成檢核，同時保留未知值不推定的安全邊界。

## What Changes

- 正式斜撐與角撐的右側工程資料新增「構件寬度（mm）」列。
- 可靠正值寬度固定顯示至小數第 3 位；未知、零值或非可靠值顯示「—」。
- 顯示列使用既有 DXF member 的 `source_width`，不加入新的工程資料欄位或 persistence contract。
- 新增 Presentation-focused 測試，涵蓋兩種構件、格式、未知值與既有 Project row contract。

### In Scope

- DXF 匯入複核介面右側「工程資料」區。
- 正式 `Brace` 與 `CornerBrace`。
- 顯示格式與未知值 fallback。

### Out of Scope

- 左側構件清單、Preview canvas、角撐修補候選視窗及匯出檔案。
- 寬度辨識演算法、容許值、候選選擇及 repair width 推定。
- 斜撐或角撐材料規格選擇。
- Project schema、Domain、Application、Infrastructure、Solver 或資料遷移。

## Capabilities

### New Capabilities

- `dxf-review-engineering-data-presentation`: 定義 DXF Review 右側工程資料如何呈現斜撐與角撐的既有可靠寬度，以及缺少可靠寬度時的顯示行為。

### Modified Capabilities

- 無。

## Impact

- **預期受影響程式**：`dxf_import/dialog.py` 的工程資料列組裝；必要時使用 `bracing_optimizer/presentation/field_labels.py` 集中管理顯示名稱。
- **預期受影響測試**：`tests/test_dxf_review_layout.py` 或相鄰 DXF Review presentation tests。
- **相容性**：無 breaking change；既有 model、Project row、序列化與外部 API 不變。
- **長期 truth**：不預期改變 Architecture、Domain、Solver 或 Workflow 文件；本次是既有資料的 Presentation 行為新增。

## 尚未決定事項與重新評估條件

- 目前沒有阻擋提案的未決事項。
- 若後續要求修補角撐也必須顯示推定寬度、或要求寬度進入 Project／匯出資料，將超出本 change，必須重新評估工程規則與 persistence contract。
