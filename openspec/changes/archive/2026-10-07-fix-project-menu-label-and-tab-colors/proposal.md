# Proposal：修正重複「專案」選單並調整頁籤配色

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」及「不變事項」；先確認本案只修正主視窗選單標籤投影與兩層頁籤的視覺層級。
- **P0／現在必讀**：`main-window-project-controls` 的「主視窗專案操作必須集中於選單列」與「Project 選單必須投影目前專案狀態」；本案會補強「檔案」不得被 Project 狀態改名的契約。
- **P0／現在必讀**：本 change 的 `specs/main-window-project-controls/spec.md`；確認三個頂層選單始終可辨識，且主、次頁籤採用不同但一致的藍灰視覺層級。
- **P1／實作前閱讀**：`design.md` 的 D1「以穩定識別更新 Project cascade」與 D2「集中式 ttk 頁籤樣式」；另讀 `tests/test_main_window_project_controls.py` 的 menu projection 測試。
- **P2／需要時再讀**：`docs/ARCHITECTURE.md` 的 Presentation 責任與 `docs/WORKFLOW.md` 的主視窗 Project 操作。可先跳過 DXF Review、persistence、Domain、Algorithms、Solver、材料規則與結果 lifecycle，本案不改那些行為。

## 快速摘要

- 畫面出現兩個「專案」，不是兩個 Project，而是狀態更新以固定 menu index 寫錯目標，把原本的「檔案」改名為「專案」。
- 修正後頂層選單固定維持「檔案／專案（或其狀態文字）／說明」，只有第二個 Project cascade 可顯示「待儲存」或警示。
- 主工作區與次工作區頁籤改用克制的藍灰配色：主頁籤較強、次頁籤較淡，選取、未選取與 hover 狀態均可辨識。
- 選單命令、頁籤名稱與順序、Project／DXF transaction、Domain 與 Solver 全部不變。

## 現況與目標

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 頂層選單 | 狀態刷新可能把「檔案」改成「專案」，形成「專案／專案／說明」 | 始終保留「檔案」與「說明」；只有 Project cascade 顯示「專案」、「專案 待儲存」或「專案 ⚠」 |
| 選單定位 | 以假設性的固定數字 index 更新 label，實際 index 受 Tk menu 結構影響 | 建立選單時記住 Project cascade 的穩定位置或識別，不再猜測 index |
| 主頁籤 | `工程配置／材料設定／分析結果` 沿用 Windows 預設灰色，選取層級不突出 | 使用深藍灰選取色與高對比文字，清楚表示目前主工作區 |
| 次頁籤 | `配置結果／材料統計／Solver 診斷／成果匯出` 等與主頁籤外觀近似 | 使用較淡的同系藍灰色，保留巢狀層級並清楚顯示選取狀態 |
| 原生選單配色 | 由 Windows／Tk 原生主題控制 | 維持原生系統配色；本案不以不穩定的自繪或平台限定方式覆寫 |

## 主要流程

```text
建立主視窗
  -> 建立「檔案」cascade
  -> 建立並記錄 Project cascade 的穩定識別
  -> 建立「說明」cascade
  -> 套用主／次 Notebook 專用樣式

Project／DXF 狀態更新
  -> 只更新已記錄的 Project cascade label
  -> 驗證「檔案」與「說明」名稱不變
  -> 不改任何命令 handler 或 transaction
```

## 不變事項

- 「檔案」仍提供新建、開啟、儲存、另存與結束；「專案」仍提供 Project／DXF 狀態、重新連結與刪除目前專案；「說明」仍提供軟體資訊。
- `專案 待儲存` 與 `專案 ⚠` 的 `DxfStatus` allowlist、`projection_stale` 復原入口及 mutation lock 不變。
- 主、次頁籤的文字、順序、內容、切換事件與下方情境工具列不變；只改 Presentation 樣式。
- 不修改 Application、Infrastructure、Domain、Algorithms、Solver、Project schema、persistence 或工程規則。
- 配色以可讀性和 Windows ttk 相容性為優先，不重做整套應用程式主題，也不承諾覆寫 OS 原生選單列顏色。

## Why

目前 Project 狀態投影使用固定選單 index，實際執行時誤改第一個「檔案」cascade，造成畫面看似有兩個「專案」且使用者無法直接辨識檔案操作入口。同時，兩層 Notebook 完全沿用預設灰色，主工作區與次工作區的層級及目前選取狀態不夠清楚，因此需要一個聚焦且可回歸驗證的 Presentation 修正。

## What Changes

- 將 Project cascade 的動態 label 更新改為穩定識別，不再依賴未驗證的固定數字 index。
- 保證狀態刷新前後頂層選單仍只有一個 Project cascade，且「檔案」與「說明」名稱不被改寫。
- 為主 Notebook 與巢狀次 Notebook 定義不同 ttk style，採用低彩度藍灰色；選取狀態使用較深底色與白字，次層使用較淡色階，並保留 disabled／focus 可讀性。
- 將樣式集中於 Presentation 初始化，避免逐一對頁籤寫入散落色碼。
- 補上能重現 Tk menu index 語意的回歸測試，以及主／次 Notebook 使用正確 style 的測試。

## In Scope

- `main.py` 的主選單建立、Project cascade label 投影與相關 Presentation state。
- 主 Notebook（工程配置／材料設定／分析結果）及其巢狀次 Notebook 的 ttk style 建立與套用。
- `tests/test_main_window_project_controls.py` 與相鄰 UI wiring／Tk smoke tests。
- 必要時更新 `main-window-project-controls` 長期 spec，使其明確保護頂層 label identity 與頁籤視覺層級。

## Out of Scope

- 重新命名、增刪或重排任何主／次頁籤或選單命令。
- 修改 Windows 原生 title bar、原生 menu bar 的系統配色，或改成自繪選單列。
- 全應用程式 dark mode、使用者可選 theme、Treeview／Button／Dialog 的全面換色。
- 修改 Project／DXF 狀態判斷、navigation guard、persistence、transaction 或 recovery semantics。
- 修改 Domain、Algorithms、Solver、材料政策或任何工程限制。
- 為了整理 `main.py` 而進行不相關重構。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `main-window-project-controls`：補強頂層選單 identity，確保動態 Project 狀態只更新 Project cascade；新增主、次工作區頁籤的可辨識視覺層級要求。

## Impact

- **Presentation**：主要影響 `main.py` 的 `_build_project_menu_and_toolbar()`、`_sync_main_menu_projection()`、主／次 Notebook 建立及新增的小型樣式初始化 helper。
- **Tests**：擴充 `tests/test_main_window_project_controls.py`，並視環境能力增加真正 Tk menu index／Notebook style smoke coverage，避免 MagicMock 再次掩蓋 index 語意。
- **Architecture**：不改 layer 或 dependency direction；所有變更仍在 Presentation。
- **Workflow／Domain／Solver／Persistence**：無真值、規則、資料格式或 transaction 變更。

## 暫定配色與重新評估條件

- 暫定主頁籤選取色為深藍灰、白字；未選取使用淺藍灰、深色字。
- 暫定次頁籤使用同色系但更淡的選取與未選取色，避免與主層競爭。
- 實作時應以 Windows 目前可用 ttk theme 做實機 smoke；若 theme 忽略背景色，允許選用支援 custom style 的既有 ttk theme，但不得因此全面改變其他 widget 外觀。
- 若切換 ttk theme 會改變全應用程式 widget 且無法隔離，停止並回報，改以該平台可可靠套用的字重、padding 與文字色維持層級，不自行擴大成全域主題重製。
