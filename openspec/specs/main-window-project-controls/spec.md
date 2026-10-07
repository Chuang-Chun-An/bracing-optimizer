# main-window-project-controls Specification

## 閱讀導航

- **必讀**：「主視窗專案操作必須集中於選單列」、「File 選單與快捷鍵必須使用相同命令」及「Open 必須使用 Project 單選視窗」；定義主視窗專案操作的主要入口與安全行為。
- **必讀**：「完整重新投影入口只在 stale 時顯示」；此 Requirement 只定義入口投影，不改 `project-state-transaction-consistency` 已成立的 mutation lock 與重新投影 transaction。
- **條件式閱讀**：「Project 選單必須投影目前專案狀態」與「刪除目前專案必須明確且安全」；修改 DXF status label、menu state 或刪除流程時必讀。
- **條件式閱讀**：「視窗標題必須成為目前 Project 的精簡狀態來源」；修改 title、dirty projection 或 Project rename／load refresh 時必讀。
- **可先跳過**：主／次分頁內容、下方情境工具列、Preview toolbar、DXF Review 內部 workflow、Solver、Domain、材料與 persistence schema；本 capability 不修改那些行為。

## Purpose

定義主視窗在移除重複的頂部 Project toolbar 後，如何以一致的「檔案／專案／說明」選單、Project 單選視窗、精簡狀態提示及條件式復原入口，安全承接既有 Project 操作。

## Requirements

### Requirement: 主視窗專案操作必須集中於選單列

主視窗 SHALL 移除位於應用程式選單列與工作區之間的頂部 Project toolbar，包括其中的 New、Project selector、Open、Save、Save As、完整重新投影按鈕與快速 Project／DXF 狀態文字。主視窗 SHALL 以「檔案」、「專案」與「說明」三個頂層選單承接這些 Project 操作及既有軟體資訊入口。

頂層「檔案」與「說明」的 label MUST 在主視窗生命週期內保持其 identity。Project／DXF 狀態刷新只能將 Project cascade 投影為「專案」、「專案 待儲存」或「專案 ⚠」，MUST NOT 改寫其他 cascade、產生第二個 Project cascade，或使使用者看到「專案／專案／說明」。

本 Requirement 只調整主視窗 Presentation。下方依工作區切換的情境工具列、Preview navigation toolbar、主／次分頁名稱、順序及內容 MUST 維持現有行為。

#### Scenario: 啟動主視窗不再顯示頂部 Project toolbar

- **WHEN** 主視窗完成建立
- **THEN** 選單列與主要工作區之間 MUST NOT 顯示原 Project toolbar、Project Combobox 或快速狀態文字
- **AND** 頂層選單 SHALL 依序提供「檔案」、「專案」與「說明」

#### Scenario: Project 狀態更新只改變 Project cascade

- **WHEN** Project／DXF 狀態使頂層 Project label 在「專案」、「專案 待儲存」或「專案 ⚠」之間切換
- **THEN** 系統 SHALL 只更新原本的 Project cascade
- **AND** 第一個頂層選單 MUST 仍為「檔案」
- **AND** 最後一個一般頂層選單 MUST 仍為「說明」
- **AND** 選單列 MUST NOT 同時出現兩個代表 Project 操作的 cascade

#### Scenario: 工作區控制保持不變

- **WHEN** 使用者切換工程配置、材料設定或分析結果及其既有次分頁
- **THEN** 下方情境工具列 SHALL 仍依目前區域提供既有操作
- **AND** `DXF 批次匯入`、`CAD 新增構件`及其他主／次分頁名稱與順序 MUST 維持不變

### Requirement: 主、次工作區頁籤必須具有可辨識的視覺層級

主視窗 SHALL 以一致的低彩度藍灰色系區分主工作區頁籤與其巢狀次頁籤。主頁籤的選取狀態 MUST 使用較強的視覺重點；次頁籤 MUST 使用同色系但較淡的層級。兩層頁籤的選取、未選取、滑鼠停留及 disabled 狀態 SHALL 保持文字可讀，且不得只以頁籤文字或順序表達目前選取狀態。

配色 MUST 透過兩組共享樣式一致套用：`工程配置／材料設定／分析結果` 使用主層樣式；這些工作區內的所有既有 Notebook 使用次層樣式。樣式變更 MUST NOT 改變頁籤文字、順序、內容、切換事件、命令可用狀態或其他 widget 的全域外觀。

#### Scenario: 主工作區顯示目前選取頁籤

- **WHEN** 使用者在「工程配置」、「材料設定」與「分析結果」之間切換
- **THEN** 目前選取的主頁籤 SHALL 使用深藍灰底與高對比淺色文字
- **AND** 其他主頁籤 SHALL 使用較淺的藍灰底與深色文字
- **AND** 頁籤文字、順序與切換後內容 MUST 維持既有行為

#### Scenario: 巢狀次頁籤與主頁籤形成層級

- **WHEN** 任一主工作區顯示其巢狀次頁籤
- **THEN** 次頁籤 SHALL 使用比主頁籤更淡的同系藍灰色
- **AND** 目前選取的次頁籤 SHALL 可與未選取次頁籤清楚區分
- **AND** 次頁籤的名稱、順序、內容與切換事件 MUST 維持既有行為

#### Scenario: 樣式不得污染其他 widget

- **WHEN** 主、次頁籤樣式完成套用
- **THEN** Treeview、Button、Entry、Dialog 及原生選單列 SHALL 繼續使用其既有或作業系統主題外觀
- **AND** 系統 MUST NOT 為了頁籤配色而切換造成全應用程式外觀變化的全域 theme

#### Scenario: 平台主題不接受背景色

- **WHEN** 目前 Windows ttk theme 無法可靠呈現自訂頁籤背景色
- **THEN** 系統 SHALL 保留主、次兩層的共享樣式與可辨識選取狀態
- **AND** SHALL 以該 theme 可可靠呈現的文字色、字重或 padding 維持視覺層級
- **AND** MUST NOT 降級為自繪選單列或全面修改其他 widget 主題

### Requirement: File 選單與快捷鍵必須使用相同命令

「檔案」選單 SHALL依序提供「新建專案」、「開啟專案…」、「儲存專案」、「另存新專案…」與「結束」，並以 separator 區分 navigation、save 與 exit。系統 SHALL提供 `Ctrl+N`、`Ctrl+O`、`Ctrl+S`及`Ctrl+Shift+S`，分別對應 New、Open、Save及Save As。

選單命令與快捷鍵 MUST呼叫同一個既有操作入口，且 MUST遵守相同的 navigation guard、save outcome、mutation guard、error handling與transaction semantics；不得為快捷鍵建立第二套流程。

這些快捷鍵 SHALL只在目前focus widget屬於主視窗root時生效。當DXF Review、Solver或其他child `Toplevel`取得focus時，快捷鍵 MUST NOT觸發主視窗New、Open、Save或Save As。實作 MUST NOT使用`bind_all`或其他process-global binding；主視窗表格的inline editor仍屬主視窗focus範圍。

Save與Save As在進入既有save workflow前 SHALL共用一個active-editor completion gate。若主視窗表格有尚未確認的inline edit，系統 MUST先以既有`_finish_edit()`相同的解析、validation、必要確認、commit與post-processing規則完成編輯；只有提交成功或no-op時才可繼續Save或Save As。實作不得依賴menu或快捷鍵自然觸發`FocusOut`。

#### Scenario: 選單與快捷鍵執行相同 New

- **WHEN** 使用者分別執行「檔案 → 新建專案」與`Ctrl+N`
- **THEN** 兩個入口 SHALL進入相同的New command及既有未儲存變更guard
- **AND** 在相同狀態與決策下 MUST產生相同結果

#### Scenario: 選單與快捷鍵執行相同 Open

- **WHEN** 使用者分別執行「檔案 → 開啟專案…」與`Ctrl+O`
- **THEN** 兩個入口 SHALL開啟相同的Project單選視窗
- **AND** MUST NOT繞過有效目標選擇或既有未儲存變更guard

#### Scenario: 選單與快捷鍵執行相同 Save

- **WHEN** 使用者分別由選單或快捷鍵執行Save或Save As
- **THEN** 系統 SHALL呼叫相同的既有Save或Save As workflow
- **AND** 儲存成功、取消與失敗 MUST維持既有明確outcome及dirty semantics

#### Scenario: 合法的未確認值必須納入 Save

- **WHEN** 主視窗表格inline editor含有尚未確認但合法的新值，使用者執行選單Save、選單Save As、`Ctrl+S`或`Ctrl+Shift+S`
- **THEN** 系統 SHALL先依既有cell-edit規則提交該值並關閉editor
- **AND** 只有完成提交後才可建立save payload或進入Save As命名流程
- **AND** 本次成功儲存的payload MUST包含剛提交的新值

#### Scenario: 不合法的未確認值必須取消 Save

- **WHEN** active inline editor中的pending值未通過既有cell-edit validation
- **THEN** 系統 SHALL顯示既有輸入錯誤提示並取消本次Save或Save As
- **AND** persistence及Save As命名流程 MUST NOT被呼叫
- **AND** 既有Project檔案、model與進入completion gate前的dirty state MUST維持不變
- **AND** editor SHALL保留pending文字並繼續可供使用者修正

#### Scenario: Edit 成功但後續 Save 未完成

- **WHEN** active edit已成功提交，但後續Save失敗，或使用者取消Save As
- **THEN** 已提交的新值 SHALL保留在model且Project SHALL維持dirty
- **AND** 系統 SHALL沿用既有save failure或cancel outcome，不得回滾已完成的cell edit

#### Scenario: 選單與快捷鍵的 active-editor 結果一致

- **WHEN** 相同active editor狀態分別由選單Save／Save As及`Ctrl+S`／`Ctrl+Shift+S`觸發
- **THEN** completion gate、validation提示、editor lifecycle、model／payload、persistence呼叫與dirty結果 MUST完全一致
- **AND** menu與shortcut MUST NOT各自實作不同的edit completion流程

#### Scenario: 子視窗取得焦點時不觸發主視窗快捷鍵

- **WHEN** DXF Review、Solver或其他child `Toplevel`已開啟且目前focus位於該子視窗
- **THEN** `Ctrl+N`、`Ctrl+O`、`Ctrl+S`與`Ctrl+Shift+S` MUST NOT觸發任何主視窗Project命令
- **AND** 子視窗既有按鍵行為 SHALL不被主視窗binding攔截

#### Scenario: 主視窗取得焦點時快捷鍵可用

- **WHEN** 目前focus widget的top-level為主視窗root，包括主視窗表格inline editor
- **THEN** 對應快捷鍵 SHALL依目前command state呼叫與File選單相同的handler
- **AND** 實作 MUST NOT依賴`bind_all`

### Requirement: Open 必須使用 Project 單選視窗

執行Open時，系統 SHALL顯示一個應用程式內的Project單選視窗，列出目前Project repository中的既有managed及legacy Projects。視窗 SHALL提供單選清單、Open與Cancel，並 SHALL允許雙擊一個有效項目執行Open；系統 MUST NOT以任意filesystem file picker取代此repository選擇。

Open按鈕 SHALL只在具有有效單一選取時可執行。視窗取消、關閉、空清單或沒有有效選取時，系統 MUST NOT進入未儲存變更guard，也 MUST NOT修改目前Project、dirty state、Project path、committed results或UI selection。

#### Scenario: 從非空清單選取 Project

- **WHEN** Project repository存在一筆或多筆Project，且使用者選取一筆後按Open或雙擊該筆
- **THEN** 選擇視窗 SHALL回傳該唯一Project目標並關閉
- **AND** 系統才可對該目標執行既有未儲存變更guard與load workflow

#### Scenario: 取消 Project 選擇

- **WHEN** 使用者按Cancel、關閉Project選擇視窗或在沒有有效選取時離開
- **THEN** 系統 SHALL取消Open命令
- **AND** MUST NOT顯示會導致目前修改被放棄的navigation guard
- **AND** 目前正式Project state MUST維持不變

#### Scenario: Repository 沒有可開啟 Project

- **WHEN** 使用者執行Open但Project repository為空
- **THEN** 選擇視窗 SHALL清楚顯示目前沒有可開啟的Project並保持Open不可執行
- **AND** Cancel或關閉 SHALL零副作用返回目前主視窗

### Requirement: Project 選單必須投影目前專案狀態

「專案」選單 SHALL提供「專案與 DXF 狀態…」、「重新連結 DXF…」及「刪除目前專案…」，並以separator區分狀態、DXF維護與destructive action。這些入口 SHALL沿用既有Project status及DXF relink workflow，不得建立第二份DXF狀態或relink規則。

頂層Project選單 SHALL只依目前`dxf_asset_status_report.status`投影下列三類互斥label：

- `MANAGED_COPY_MODIFIED`、`SOURCE_MODIFIED`、`MISSING`、`RELINK_REQUIRED`、`BINDING_REQUIRED`、`LEGACY_NO_STATE`、`INCOMPATIBLE`或`GEOMETRY_COMPATIBLE`：`專案 ⚠`
- `RUNTIME_READY`或`VERIFIED_PENDING_SAVE`：`專案 待儲存`
- `READY`、`NO_DXF`或尚無status report：`專案`

`待儲存`提示 MUST只依`DxfStatus`判斷，不得依賴`project_dirty`；即使dirty為False仍須顯示。這些label只是一個Presentation projection，詳細原因 SHALL以既有「專案與 DXF 狀態…」內容為準。實作 MUST使用明確allowlist，不得以「不是`READY`、也不是`NO_DXF`」等反向條件推導警示。

#### Scenario: DXF 狀態正常或不適用

- **WHEN** 尚無status report，或目前DXF status為`READY`或`NO_DXF`
- **THEN** 頂層Project選單 SHALL顯示「專案」且不附加warning或pending-save提示

#### Scenario: DXF 狀態等待儲存

- **WHEN** 目前DXF status為`RUNTIME_READY`或`VERIFIED_PENDING_SAVE`
- **THEN** 頂層Project選單 SHALL顯示「專案 待儲存」
- **AND** 即使`project_dirty=False`，該提示仍 MUST顯示
- **AND** 系統 MUST NOT將此狀態投影為`專案 ⚠`

#### Scenario: DXF 狀態需要注意

- **WHEN** 目前DXF status為`MANAGED_COPY_MODIFIED`、`SOURCE_MODIFIED`、`MISSING`、`RELINK_REQUIRED`、`BINDING_REQUIRED`、`LEGACY_NO_STATE`、`INCOMPATIBLE`或`GEOMETRY_COMPATIBLE`
- **THEN** 頂層Project選單 SHALL顯示「專案 ⚠」
- **AND** 使用者執行「專案與 DXF 狀態…」時 SHALL看到既有完整狀態與訊息

#### Scenario: 開啟軟體資訊不依賴 Project 狀態

- **WHEN** 使用者執行「說明 → 軟體資訊」
- **THEN** 系統 SHALL沿用既有軟體資訊流程
- **AND** Project menu warning、dirty state或Project selection MUST NOT阻止資訊視窗開啟

### Requirement: 視窗標題必須成為目前 Project 的精簡狀態來源

主視窗標題 SHALL顯示應用程式名稱與目前Project顯示名稱；目前Project為dirty時 SHALL附加`*`，clean時 MUST NOT顯示該dirty標記。未命名Project SHALL明確顯示「未命名專案」。系統 MUST NOT因移除工具列而另建第二份常駐Project快速狀態文字。

#### Scenario: 顯示 clean 的已命名 Project

- **WHEN** 目前Project已有正式路徑且dirty為False
- **THEN** 視窗標題 SHALL顯示該Project名稱
- **AND** MUST NOT附加`*`

#### Scenario: 顯示 dirty Project

- **WHEN** 目前Project dirty為True
- **THEN** 視窗標題 SHALL在Project顯示名稱後附加`*`
- **AND** Save成功清除dirty後 SHALL移除該標記

#### Scenario: 顯示未命名 Project

- **WHEN** 目前Project沒有正式路徑
- **THEN** 視窗標題 SHALL顯示「未命名專案」

### Requirement: 刪除目前專案必須明確且安全

「刪除目前專案…」 SHALL只在目前Project具有位於Project repository內、可驗證的正式managed或legacy路徑時可執行；未命名Project或路徑無效時 SHALL不可執行。系統 MUST在刪除前顯示目前Project名稱、正式路徑、是否包含managed DXF、是否有未儲存變更，以及動作不可復原的明確確認。

刪除流程 MUST呼叫與New相同的既有mutation guard，而不是複製其條件。只要該共用guard會阻擋New，刪除亦 MUST在任何filesystem mutation前被阻擋；不得為Delete另增或刪減guard條件。這項parity不等於套用New的Save／Discard／Cancel navigation guard；刪除仍以自身明確確認授權丟棄dirty runtime內容。

使用者取消或共用mutation guard拒絕時，filesystem與完整runtime Project state SHALL維持不變。確認後，系統 SHALL只刪除已驗證的目前Project目標；刪除失敗時 SHALL保留目前runtime Project及path並回報失敗。刪除成功後，系統 SHALL採用一個未命名、clean的新Project，且 MUST NOT讓runtime繼續指向已刪除路徑。

#### Scenario: 未命名 Project 不可刪除

- **WHEN** 目前Project沒有正式path
- **THEN** 「刪除目前專案…」 SHALL不可執行
- **AND** 系統 MUST NOT推測或選取其他Project作為刪除目標

#### Scenario: 使用者取消刪除

- **WHEN** 目前Project path有效但使用者取消刪除確認
- **THEN** Project檔案、managed DXF、runtime Project、results、dirty state及current path SHALL全部維持不變

#### Scenario: New mutation guard 阻擋時不得刪除

- **WHEN** 目前狀態會使New所用的共用mutation guard拒絕操作
- **THEN** 「刪除目前專案…」 SHALL在任何filesystem mutation前停止並回報同一guard原因
- **AND** Project檔案、managed DXF與完整runtime Project state MUST維持不變

#### Scenario: Delete 不得自創額外 mutation guard

- **WHEN** 某狀態不會被New的共用mutation guard阻擋
- **THEN** Delete MUST NOT僅因該狀態自行新增阻擋條件
- **AND** 是否允許刪除仍由current path validation、明確確認及其他既有delete前置條件決定

#### Scenario: 刪除失敗

- **WHEN** 已驗證的目前Project目標在filesystem刪除時失敗
- **THEN** 系統 SHALL回報失敗並保留目前runtime Project及current path
- **AND** MUST NOT採用部分的新Project state

#### Scenario: 成功刪除目前 Project

- **WHEN** 使用者確認刪除且已驗證的目前Project目標成功移除
- **THEN** 系統 SHALL切換為未命名、clean的新Project並刷新主畫面
- **AND** current path SHALL為空且 MUST NOT指向已刪除Project

### Requirement: 完整重新投影入口只在 stale 時顯示

當`projection_stale`為False時，主視窗選單列 MUST NOT顯示「⚠ 重新整理畫面」。當正式mutation已commit但UI projection失敗、使`projection_stale`成為True時，系統 SHALL在「專案」與「說明」之間顯示可直接執行的「⚠ 重新整理畫面」，並維持既有資料mutation lock。

該命令 SHALL呼叫既有完整重新投影workflow。只有全部必要畫面由committed state成功重建後，系統才可清除stale、解除mutation lock並移除命令；任一步驟失敗時 SHALL保留command與lock、顯示最新錯誤，且 MUST NOT回滾或部分修改committed state。

#### Scenario: 正常狀態不顯示 recovery command

- **WHEN** `projection_stale`為False
- **THEN** 選單列 MUST NOT顯示「⚠ 重新整理畫面」

#### Scenario: Projection stale 時顯示 recovery command

- **WHEN** 正式mutation已commit但後續UI projection失敗
- **THEN** 選單列 SHALL在「專案」與「說明」之間顯示「⚠ 重新整理畫面」
- **AND** 既有mutation lock SHALL保持生效

#### Scenario: 完整重新投影成功

- **WHEN** 使用者執行「⚠ 重新整理畫面」且全部必要projection成功
- **THEN** 系統 SHALL清除stale、解除mutation lock並移除該command

#### Scenario: 完整重新投影再次失敗

- **WHEN** 使用者執行「⚠ 重新整理畫面」但任一必要projection失敗
- **THEN** 系統 SHALL保留command與mutation lock並回報最新錯誤
- **AND** committed state MUST維持不變
