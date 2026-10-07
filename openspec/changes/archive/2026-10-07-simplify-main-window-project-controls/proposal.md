# Proposal：簡化主視窗專案控制並整合至選單列

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認本案只移除頂部專案工具列，不移除下方情境工具列、Preview 導覽列，也不改任何次分頁名稱。
- **P0／現在必讀**：本 change 的新 capability `main-window-project-controls`，尤其「主視窗專案操作必須集中於選單列」、「Open 必須先取得有效目標」與「完整重新投影入口只在 stale 時顯示」。
- **P0／現在必讀**：本 change 對 `unsaved-changes-navigation-guard` 的 delta；Open 目標入口會由工具列下拉選單改為「開啟專案」單選視窗，但既有 Save／Discard／Cancel 與 continuation gate 不變。
- **P1／實作前閱讀**：`design.md` 的 D1 選單責任、D2 Open 選擇視窗、D3 狀態投影、D4 conditional recovery command 與 D5 刪除目前專案；另讀 `docs/WORKFLOW.md` 的 New／Open 與 `projection_stale` 段落。
- **P2／需要時再讀**：修改「說明」選單時讀 `software-information-presentation`；處理 Project load transaction 時讀 `project-state-transaction-consistency`。可先跳過 DXF Review 內部操作、Solver、Domain、材料、成果匯出及所有辨識規格，本案不改那些行為。

## 快速摘要

- 現行頂部專案工具列與「檔案」選單重複提供 New／Open／Save／Save As，且把專案選擇、DXF 維護、狀態與異常復原擠在同一列。
- 本案移除整條頂部專案工具列，將命令依責任整理到「檔案」、「專案」、「說明」三個主選單；使用者稱為「標題列」的區域，在本文件中統一稱為應用程式選單列。
- Open 改由「檔案 → 開啟專案…」開啟單選視窗；只有選定有效 Project 後才進入既有未儲存變更 guard。
- 視窗標題持續顯示目前 Project 與 `*` dirty 標記；Project選單依`DxfStatus`顯示普通「專案」、獨立的「專案 待儲存」或「專案 ⚠」，不依賴dirty推導DXF提示；完整重新投影只在 `projection_stale` 時暫時顯示為選單列上的直接命令。
- 主工作區、所有主／次分頁名稱、下方情境工具列、Preview 工具列、Project persistence、DXF workflow、Domain 與 Solver 行為全部維持不變。

## 現況與目標

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 頂部配置 | 「檔案／說明」選單下方另有一整列 Project toolbar | 移除頂部 Project toolbar，只保留「檔案／專案／說明」選單列 |
| 專案命令 | New／Open／Save／Save As 同時出現在選單與工具列 | 日常檔案生命週期只由「檔案」選單及鍵盤快捷鍵進入 |
| Open 目標 | 先在工具列 Combobox 選 Project，再按「開啟」 | 執行「開啟專案…」後在單選視窗選定 Project，再按開啟或雙擊 |
| Project／DXF 維護 | 重新連結、狀態與刪除混在「檔案」選單 | 移至獨立「專案」選單，與一般檔案生命週期分離 |
| 目前 Project | 工具列右側長文字與視窗標題重複顯示 | 視窗標題顯示 Project 名稱與 dirty `*`；完整狀態由「專案與 DXF 狀態…」查看 |
| DXF 注意狀態 | 工具列狀態文字可能在窄視窗被擠壓 | 8個需處理狀態顯示「專案 ⚠」；`RUNTIME_READY`／`VERIFIED_PENDING_SAVE`顯示「專案 待儲存」；正常或無DXF時顯示「專案」 |
| 完整重新投影 | disabled 的「重新整理全部畫面」按鈕長期占用工具列 | 正常時不顯示；`projection_stale` 時才在選單列出現「⚠ 重新整理畫面」直接命令 |
| 分頁與工作區操作 | 主／次分頁及下方情境工具列 | 名稱、順序及功能全部不變 |

## 主要流程

```text
使用者在選單列選擇命令
  ├─ 檔案 → 新建／儲存／另存／結束
  ├─ 檔案 → 開啟專案…
  │    -> 顯示 Project 單選視窗
  │    -> 使用者選定有效目標
  │    -> 進入既有 Save／Discard／Cancel navigation guard
  │    -> guard 允許後才載入該 Project
  ├─ 專案 → 狀態／重新連結 DXF／刪除目前專案
  └─ 說明 → 軟體資訊

若 committed state 已更新但 UI projection 失敗
  -> 選單列暫時出現「⚠ 重新整理畫面」
  -> 使用者執行既有完整重新投影
  -> 全部成功才移除命令並解除 mutation guard
```

## 不變事項

- `New`、`Open`、`Save`、`Save As`、`Exit`、DXF relink、Project status 與 software information 仍呼叫既有 use case／handler；本案不建立第二套 persistence、DXF 或 navigation transaction。主視窗快捷鍵只在主視窗持有焦點時生效，不使用 `bind_all`，子視窗持有焦點時不得觸發主視窗命令。
- 主視窗表格儲存格編輯中，選單Save、Save As、`Ctrl+S`與`Ctrl+Shift+S`在儲存前都先依既有`_finish_edit()`相同的驗證與提交規則完成編輯。驗證失敗時保留editor供修正、顯示既有錯誤、取消該次儲存，且不得改變檔案或dirty；成功後才進入既有save workflow。
- 刪除目前 Project 重用 New 的同一個 mutation guard；New 被該 guard 阻擋時刪除也不得執行，不另外新增 Solver operation 或 DXF Review 狀態規則。
- Open 仍必須先取得有效目標才可顯示 destructive navigation guard；取消選擇或空清單不得修改目前 Project，也不得要求使用者處理未儲存變更。
- `projection_stale` 期間的 mutation lock、完整重新投影涵蓋範圍、成功／失敗語意及 committed state 保留規則不變；只改變入口位置與可見時機。
- 下方 `context_toolbar` 仍依目前分頁提供新增列、刪除列、排序、驗證、更新圖面與 Solver 操作；Preview navigation toolbar 亦不受影響。
- `DXF 批次匯入`、`CAD 新增構件` 與其他主／次分頁名稱及順序不變。
- Project JSON、managed DXF、dirty state、DXF lifecycle、Solver result、Domain rule 與 Architecture dependency direction不變。

## Why

主視窗頂部同時存在原生選單、Project toolbar 與多層工作區分頁，日常命令重複、狀態文字容易被擠壓，且異常復原按鈕在絕大多數時間以 disabled 狀態占據空間。將專案操作集中到既有選單列，可減少視覺層級並釋放內容高度，同時保留安全交易與工程行為。

## What Changes

- 移除主視窗頂部 Project toolbar，以及其中的 New、Project Combobox、Open、Save、Save As、完整重新投影按鈕與快速狀態文字。
- 將「檔案」選單整理為：新建專案、開啟專案…、儲存專案、另存新專案…、結束，並提供 `Ctrl+N`、`Ctrl+O`、`Ctrl+S`、`Ctrl+Shift+S`。
- Save與Save As新增共用的active-editor completion gate：合法pending值先提交並納入本次payload；不合法時保留editor並取消儲存，不執行任何persistence。
- 新增「專案」選單，提供：專案與 DXF 狀態…、重新連結 DXF…、刪除目前專案…；頂層label依明確`DxfStatus` allowlist投影為「專案」、「專案 待儲存」或「專案 ⚠」。
- 新增 Project 單選視窗取代工具列 Combobox；顯示既有 managed／legacy Project 名稱，支援單選、雙擊開啟、Open／Cancel，且不新增任意 filesystem file picker。
- 「刪除目前專案…」只對目前已有正式 Project path 的專案啟用，並在刪除前套用與 New 完全相同的既有 mutation guard；確認內容顯示 Project 名稱、路徑、managed DXF 與未儲存狀態。取消或 guard 拒絕時零副作用；成功刪除後切換為未命名的新 Project，避免 runtime 繼續指向已刪除路徑。
- 視窗標題維持 `應用程式名稱 - Project 名稱`，dirty 時附加 `*`；不再建立第二份快速狀態文字。
- `projection_stale` 為 `True` 時，選單列暫時加入「⚠ 重新整理畫面」直接命令；重新投影成功後移除，失敗時保留並回報最新錯誤。

## In Scope

- 主視窗頂部 Project toolbar 的移除與主選單重新分組。
- File／Project／Help 選單 wiring、命令狀態與鍵盤快捷鍵。
- Project 單選視窗，以及 target selection 與既有 navigation guard 的先後順序。
- 視窗標題 dirty 投影、Project menu DXF warning 投影與 conditional projection-recovery command。
- 目前 Project 刪除入口的可用狀態、確認、成功後安全 reset 與相關 Presentation tests。
- 實作完成後更新 `docs/WORKFLOW.md` 中 Open target selection 與完整重新投影入口的位置描述。

## Out of Scope

- 修改任何主／次分頁名稱、順序、內容或 Notebook 階層。
- 移除或重新設計下方情境工具列、Preview navigation toolbar、DXF Review toolbar 或 Dialog 內部操作列。
- 增加最近使用專案、搜尋、排序、釘選、縮圖、filesystem 任意選檔或 Project 管理中心。
- 修改 Save／Save As persistence、New／Open transaction、DXF relink、Project schema、managed DXF、dirty rule 或 projection rebuild內容。
- 修改 Application、Domain、Algorithms、Solver、工程限制或 recognition 規則。
- 為了拆分 `main.py` 而進行與本次 UI 行為無關的重構。

## 已知問題與後續 Change

- `RUNTIME_READY`與`VERIFIED_PENDING_SAVE`目前可能先寫入`dxf_asset_status_report`，之後才設定`project_dirty=True`；兩者不是同一次atomic runtime commit，中途projection失敗時可能留下pending-save status搭配`dirty=False`。
- 本change以`DxfStatus`直接投影「專案 待儲存」，因此不依賴上述dirty invariant，也不在本change調整DXF adoption transaction。
- 將「status設定」與「dirty標記」改成atomic commit需另立change處理，並補failure-injection與rollback測試；不得在本change順便重構。

## Capabilities

### New Capabilities

- `main-window-project-controls`：定義主視窗以「檔案／專案／說明」選單承接 Project 操作、Project 單選視窗、狀態投影、鍵盤快捷鍵、目前 Project 刪除，以及 stale 時才顯示的完整重新投影入口。

### Modified Capabilities

- `unsaved-changes-navigation-guard`：將 Open target selection 由既有工具列選取改為「開啟專案…」單選視窗，並保留「先選定有效目標，再進入 Save／Discard／Cancel guard」的 transaction semantics。

## Impact

- **Presentation**：主要影響 `main.py` 的 `_build_project_menu_and_toolbar()`、Project list／selection、menu state、window title、DXF status projection、projection recovery UI 與 delete wiring；可能新增一個位於 `bracing_optimizer/presentation/dialogs/` 的 UI-only Project 選擇 Dialog。
- **Tests**：更新 `tests/test_project_navigation_guard.py`、`tests/test_project_state_transactions.py`、`tests/test_software_information.py`，並新增或擴充主選單、快捷鍵、Project chooser、conditional recovery command 與 delete-current 行為測試。
- **Workflow 文件**：實作完成後更新 `docs/WORKFLOW.md` 對 Open target selection 與「重新整理全部畫面」工具列入口的舊描述。
- **Architecture**：沿用既有 Presentation → Application 邊界；Project listing／選取與 menu projection 留在 Presentation，不把 Tkinter 或選單狀態下推到 Application／Domain。
- **Domain／Solver／Persistence**：無規則、演算法、schema 或資料格式變更。

## 已確認決策與重新評估條件

- 已確認：移除的是頂部 Project toolbar；下方情境工具列及 Preview toolbar 保留。
- 已確認：所有次分頁名稱維持現況。
- 已確認：Open 使用應用程式內的 Project 單選視窗，不新增任意 filesystem picker。
- 已確認：完整重新投影入口只在 `projection_stale` 時顯示於選單列。
- 已確認：專案名稱與 dirty 狀態由視窗標題提供；詳細 Project／DXF 狀態由「專案」選單開啟。
- 已確認：快捷鍵只在主視窗持有焦點時生效，不使用 `bind_all`；Save／Save As採選項A，在active inline editor驗證並提交成功後才可儲存，失敗時保留editor並取消該次儲存。
- 已確認：刪除目前Project重用New的既有mutation guard，不自行新增Solver operation或DXF Review規則。
- 已確認：`MANAGED_COPY_MODIFIED`、`SOURCE_MODIFIED`、`MISSING`、`RELINK_REQUIRED`、`BINDING_REQUIRED`、`LEGACY_NO_STATE`、`INCOMPATIBLE`及`GEOMETRY_COMPATIBLE`顯示「專案 ⚠」；`RUNTIME_READY`、`VERIFIED_PENDING_SAVE`顯示「專案 待儲存」；`READY`、`NO_DXF`及無report顯示「專案」。
- 若實作驗證顯示特定 Windows／Tk 版本不支援在 menu bar 上安全動態加入／移除 command，允許保留固定位置但在正常狀態隱藏其可見文字；不得退回長期 disabled 的頂部工具列按鈕。
- 若目前 Project 刪除後無法以既有 reset transaction 安全回到未命名 Project，必須停止並回報，不得留下指向已刪除路徑的 runtime state。
