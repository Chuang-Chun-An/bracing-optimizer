# Proposal

## Why

Main UI 在 dirty Project 執行 New 或 Open 時，目前只能選擇放棄修改或取消操作；使用者若想先保存，必須中斷 navigation、另外儲存，再重新操作。這項變更加入一致的 Save／Discard／Cancel guard，確保只有儲存成功或使用者明確放棄修改後，才會清空或切換目前 Project。

## What Changes

### In Scope

- New Project 與 Open Project 共用同一套 dirty navigation guard 語意。
- Dirty Project 顯示 Save／Discard／Cancel 三種選擇；clean Project 直接繼續，不顯示提示。
- Save 分支沿用既有 Save／Save As：已有 Project path 時直接 Save，未命名時進入 Save As。
- 將 navigation 使用的儲存結果明確區分為 saved、cancelled、failed，避免把取消與錯誤混為 `None` 或 truthy／falsy。
- Save As 取消、儲存失敗或 navigation 取消時，不執行 New／Open 的 destructive continuation，並保留 Project input、committed results、dirty state、Project path 與 UI selection。
- Open 沿用目前「開啟選取專案」入口；沒有選取目標時維持現況，不新增另一套檔案選擇器。
- 補上 New／Open／Save／Save As／dirty prompt 的 characterization 與 navigation regression tests。
- 實作驗證完成後，更新 `docs/WORKFLOW.md` 中仍描述 New／Open 僅有 Discard／Cancel 的長期流程。

### Out of Scope

- Solver、Domain geometry、optimization algorithm、material rules 或 Project schema。
- Project JSON／managed DXF 格式與既有 persistence transaction。
- 自動儲存、復原被 Discard 的修改，或新增 Open file picker。
- 改變 dirty state 的定義。
- 改變 Close Application 的可見提示行為；若共用明確 save outcome 所需，只調整其內部判斷而不新增選項或改變關閉語意。
- 大規模重構 Project persistence 或 Main UI。

## Capabilities

### New Capabilities

- `unsaved-changes-navigation-guard`: 定義 Main UI 在 New／Open 前處理 clean／dirty Project、Save／Discard／Cancel、Save As 取消、儲存失敗與 destructive continuation 的正式行為。

### Modified Capabilities

- 無；現有 OpenSpec 主規格沒有涵蓋 Project navigation 或未儲存變更保護。

## Impact

- 主要影響 `main.py` 的 New、Open、Save、Save As 與既有 Close save-result consumption，以及可能新增一個小型 presentation/application-neutral outcome type。
- 沿用 `ProjectService.save_project()`／`load_project()` 與現有 Infrastructure atomic persistence；不改變其 payload 或檔案格式。
- 預計新增以 continuation 是否被呼叫及完整 state snapshot 是否保持為主的 Main lifecycle tests；既有 persistence、manual-edit immediate commit 與 architecture boundary tests須維持通過。
- 這項變更沿用既有 Architecture，不改變 Domain 或 Solver truth；它會改變 `docs/WORKFLOW.md` 所描述的 Project navigation workflow truth。
