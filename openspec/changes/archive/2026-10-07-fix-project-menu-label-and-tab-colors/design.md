# Design：穩定選單識別與雙層 Notebook 配色

## 閱讀導航

- **P0／現在必讀**：D1「建立時記錄 Project cascade 的實際 index」；這是修正「專案／專案／說明」的核心，並同時處理 conditional recovery command 的相對位置。
- **P0／現在必讀**：D2「使用兩組局部 ttk Notebook styles」；定義主、次頁籤的 palette、style name 與套用範圍。
- **P1／實作前閱讀**：D3「以 headless contract test 加 Windows Tk smoke 驗證」及 Single Source of Truth；避免 MagicMock 再次掩蓋 Tk index 語意。
- **P2／遇到平台外觀差異時再讀**：Risks／Trade-offs 的 ttk theme fallback。可先跳過 persistence、DXF workflow、Domain 與 Solver 文件，本案不觸及那些模組。

## 方案摘要

本 change 中的 **Project cascade identity** 是指建立主選單時，實際承載 `project_menu` 的那一個頂層 entry；它不等同於寫死的整數 `1`，也不以目前顯示文字反向搜尋。**主層 Notebook** 是 `工程配置／材料設定／分析結果`；**次層 Notebook** 是三個工作區內既有的 `engineering_notebook`、`materials_notebook` 與 `analysis_notebook`。

```text
Menu 建立
  -> menu_bar 使用 tearoff=False
  -> 加入 File
  -> 加入 Project
  -> 立即從 menu_bar 取得並保存 Project entry 的實際 index
  -> 加入 Help

狀態投影
  -> 用保存的 Project index 更新 Project label
  -> stale command 插入 Project 之後
  -> File / Help identity 不變

UI style 初始化
  -> 設定 Primary.TNotebook(.Tab)
  -> 設定 Secondary.TNotebook(.Tab)
  -> 主 Notebook 套 Primary
  -> 三個巢狀 Notebook 套 Secondary
```

## 決策對照

| Decision | 解決的問題 | 對應 spec／主要 task |
| --- | --- | --- |
| D1. 建立時記錄 Project cascade 的實際 index | 避免 Tk tear-off／entry index 差異把 File 改名 | `主視窗專案操作必須集中於選單列`；menu construction、projection 與 regression tasks |
| D2. 使用兩組局部 ttk Notebook styles | 建立主／次層級而不改全應用程式 theme | `主、次工作區頁籤必須具有可辨識的視覺層級`；style helper 與 notebook wiring tasks |
| D3. contract test 加 Windows Tk smoke | 同時驗證程式 wiring 與真實 Tk entry semantics／可見配色 | 兩項 Requirements 的全部 scenarios；focused unit、Tk smoke 與手動截圖確認 tasks |

## Context

動機與範圍見 [proposal.md](./proposal.md)。目前 `main.py` 的 `_build_project_menu_and_toolbar()` 以 `tk.Menu(self.root)` 建立最上層 menu bar，未明確關閉 tear-off；`_sync_main_menu_projection()` 之後直接呼叫 `menu_bar.entryconfigure(1, ...)`。實際 Tk menu entry index 與單元測試中的 `MagicMock` 假設不同，導致 index `1` 對應到 File cascade，於是 File 被 Project 狀態文字覆蓋。現有測試只驗證呼叫了 `entryconfigure(1, ...)`，因此把錯誤實作當成預期行為。

主視窗目前沒有集中式 ttk style 初始化。`self.notebook`、`self.engineering_notebook`、`self.materials_notebook` 與 `self.analysis_notebook` 都使用預設 `TNotebook`，因而在 Windows 上呈現近似的灰色層級。其他 widget 已有零星語意色碼，本 change 不把它們納入主題重構。

## Goals / Non-Goals

**Goals:**

- 讓 Project status label 永遠只更新 Project cascade，並讓 recovery command 仍穩定出現在 Project 與 Help 之間。
- 用兩個具名、局部的 Notebook style 呈現主／次工作區層級。
- 用現有架構可負擔的測試同時覆蓋 headless wiring 與真實 Tk 語意。

**Non-Goals:**

- 不建立通用 menu registry、theme framework、design-token package 或自繪 widget 系統。
- 不調整選單命令、Project status allowlist、頁籤 navigation 或任何資料／交易行為。
- 不切換全域 ttk theme，也不重做 Dialog、Treeview、Button 或原生 menu bar 的外觀。

## Decisions

### D1. 建立時記錄 Project cascade 的實際 index

最上層 menu bar 明確使用 `tearoff=False`。在 `project_menu` 以 `add_cascade()` 加入後，立即由 `menu_bar.index("end")` 取得該 entry 的實際 index，保存為僅供 Presentation 使用的 `project_menu_index`。`_sync_main_menu_projection()` 只以此欄位更新 Project label，不再寫死 `1`。

`projection_stale` 的 recovery command 使用 `project_menu_index + 1` 作為插入與刪除位置。它永遠位於 Project 後方，因此不會使 Project index 漂移；Help 可在插入期間向後移動，移除後回到原位。若 menu 尚未完整建立或 index 不可用，projection helper 沿用現有防禦式 no-op／`TclError` 邊界，不改正式 Project state。

選擇這個方案的理由：Tk menu API 的 entry identity 本質上仍以 index／pattern 操作；在建立當下從真實 widget 取得 index，可把平台細節限制在 menu construction，而不依賴 label 當 locator。

**Rejected alternatives:**

- 固定使用 `1` 或 `2`：其正確性依賴 tear-off 與建立順序，正是本次缺陷來源。
- 以顯示文字 `專案` 查找：label 會動態變成 `專案 待儲存` 或 `專案 ⚠`，本身不是穩定 identity。
- 每次狀態更新重建整條 menu bar：會增加 command state、shortcut 與 recovery entry 漂移風險，超出小型修正需求。

### D2. 使用兩組局部 ttk Notebook styles

在 `SupportInputApp` 的 UI 建立早期加入一個小型 Presentation helper，透過 `ttk.Style(master=self.root)` 設定下列具名樣式，不呼叫 `theme_use()`：

| Role | Style | 未選取 | 選取 | Hover | Disabled | Padding |
| --- | --- | --- | --- | --- | --- | --- |
| 主層 | `Primary.TNotebook`／`Primary.TNotebook.Tab` | 背景 `#DCE6ED`、文字 `#253746` | 背景 `#2F5D7C`、文字 `#FFFFFF` | 背景 `#BFD2DF`、文字 `#173B57` | 背景 `#ECEFF1`、文字 `#90A4AE` | `(12, 6)` |
| 次層 | `Secondary.TNotebook`／`Secondary.TNotebook.Tab` | 背景 `#EEF3F6`、文字 `#425466` | 背景 `#C8DDEA`、文字 `#173B57` | 背景 `#DDEAF2`、文字 `#264A60` | 背景 `#F4F6F7`、文字 `#9AA7AF` | `(10, 4)` |

Palette 以具名 module-level mapping 或不可變常數保存，避免在四個 Notebook 建立點散落 magic color。主 `self.notebook` 使用 `Primary.TNotebook`；三個巢狀 Notebook 一律使用 `Secondary.TNotebook`。style helper 只 configure／map 這四個 style name，不修改 `TNotebook`、`TNotebook.Tab` 或其他全域 widget style。

目前選取狀態由 ttk widget state `selected` 提供，hover 由 `active` 提供；disabled 使用 `disabled`。主選取色與白字、次選取淺色與深字都保持清楚對比。若目前 Windows theme 視覺上忽略 tab background，先保留兩組 style name與 foreground／padding 層級；不得為此切換全域 theme。是否需要在既有 theme 下增加字重，只能在 Windows smoke 顯示背景確實無效時採用，且仍限制於兩個 `.Tab` style。

**Rejected alternatives:**

- 修改全域 `TNotebook.Tab`：會讓非本次範圍的 Dialog／子視窗 Notebook 一併改色。
- 呼叫 `theme_use("clam")` 強制顯色：會改變 Button、Treeview、Entry 等全應用程式外觀。
- 逐一在 tab 建立點設定色碼：ttk 的顏色由 style 控制，散落設定也會形成多份 palette truth。
- 自繪 tabs 或 menu bar：維護成本及 keyboard／accessibility 風險遠大於本次需求。

### D3. contract test 加 Windows Tk smoke

Focused unit tests 應驗證：menu bar 建立時 `tearoff=False`、`project_menu_index` 來自實際建立後的 `index("end")`、三類 Project label 都只對該 index 執行、stale command 以相同基準插入／移除、四個 Notebook 分別使用主／次 style，以及 style map 只修改具名 style。

另加或擴充可在 Windows Tk 環境執行的 smoke test：建立 withdrawn root 與真實 menu，讀回三個 cascade label，在 normal、pending-save、warning 投影後確認 File／Help 不變且僅一個 Project cascade；讀回兩組 style 的 `selected`／default 顏色與 padding。若 CI 無圖形環境，smoke test可依既有專案慣例 skip，但 focused headless contract tests必須執行。

實作完成後應啟動主程式做一次視覺確認：選單列顯示「檔案／專案／說明」，切換主與次頁籤時層級清楚，且其他 widget 未被全域換色。

## Single Source of Truth

| 資訊 | 唯一來源 | Presentation projection |
| --- | --- | --- |
| Project cascade entry | 建立 menu bar 時取得的 `project_menu_index` | 動態 Project label 與 recovery command 相對位置 |
| Project label 內容 | 既有 `_project_menu_label()` 與 `DxfStatus` allowlist | `專案`／`專案 待儲存`／`專案 ⚠` |
| 主／次頁籤 palette | 一組具名 Presentation 常數 | `Primary.*`／`Secondary.*` ttk style |
| 目前選取頁籤 | 各 Notebook 的既有 selected state | style map 的 `selected` 外觀 |

不得另外保存目前顯示中的 Project label 或目前選取頁籤顏色。狀態刷新只重新投影既有 truth，避免 label、widget state 與額外 cache 漂移。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改架構本身。

- **Presentation／`main.py`**：擁有 Tk menu entry、ttk styles、Notebook wiring 與 UI smoke；所有修改集中於此層。
- **Application／Infrastructure／Domain／Algorithms／DXF subsystem**：不變，也不新增對 Presentation 的依賴。
- **Dependency direction**：維持 Presentation → Application；配色與 menu identity 不下推到 Application 或 Domain。

不新增 cross-layer contract、repository abstraction 或 persistence adapter。Style palette 是 UI-only constant，不是 Domain rule。

## Backward Compatibility 與 Persistence Impact

- Project JSON、managed DXF、UI state persistence、schema version與既有資料完全不變，無 migration。
- Menu handlers、accelerators、command enabled state、`DxfStatus` mapping與 recovery transaction不變。
- 頁籤名稱、順序、widget ownership與 event binding不變；只新增 style option。
- 回退可單獨移除具名 styles 與 index capture，沒有資料 rollback；但若只回退 index 修正，重複「專案」缺陷會重新出現。

## Risks / Trade-offs

- **[Risk] 不同 Windows／Tk theme 對 tab background 的呈現不同** → 不切換全域 theme；以具名 style 的 foreground、padding與必要時局部字重作 fallback，並執行實機 smoke。
- **[Risk] conditional recovery command 插入後 index 漂移** → Project entry 永遠位於插入點之前；插入／刪除都由 `project_menu_index + 1` 推導，並測試重複同步不產生 duplicate。
- **[Risk] 測試再次只驗證 mock call 而沒有驗證真實 label** → unit contract與 real Tk smoke 分層，後者直接讀回 menu entry label。
- **[Trade-off] 原生 menu bar 保持系統顏色** → 換取 Windows keyboard、accessibility與平台一致性；本案把視覺重點放在可可靠控制的 Notebook。

## Migration Plan

1. 先更新 menu 與 style focused tests，使舊的固定 index 行為可重現失敗。
2. 實作 Project entry index capture 與 recovery command 相對定位，執行 menu focused tests。
3. 實作具名 palette／style helper，套用到一個主 Notebook 與三個次 Notebook，執行 style focused tests。
4. 執行 Windows Tk smoke 與主程式視覺確認；確認其他 widget 未受全域 theme 影響。
5. 執行相鄰 Project transaction／software information tests及 architecture boundary tests，再執行完整測試套件。

Rollback 不涉及資料：若 style 在目標 Tk 版本造成不可接受的顯示，可先回退 style wiring但保留 menu identity 修正；若 menu index capture 發生未預期 Tcl 行為，停止發布並回報，不得回到未測試的固定 index。
