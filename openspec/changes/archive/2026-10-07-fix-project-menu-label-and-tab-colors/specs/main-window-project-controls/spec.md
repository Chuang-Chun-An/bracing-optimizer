# Spec Delta：主視窗選單識別與頁籤視覺層級

## 閱讀導航

- **必讀**：「主視窗專案操作必須集中於選單列」；本次補強動態 Project 狀態只能更新第二個 Project cascade，不能把「檔案」改名。
- **必讀**：「主、次工作區頁籤必須具有可辨識的視覺層級」；定義本次配色的可見結果與不變行為。
- **條件式閱讀**：既有 `main-window-project-controls` 的「Project 選單必須投影目前專案狀態」；只有修改 `DxfStatus` 對應文字時需要閱讀，本案不改其 allowlist。
- **可先跳過**：Open 單選視窗、Save／Save As active-editor gate、刪除目前專案及 stale recovery transaction；本案不改這些行為。Domain、Solver、DXF recognition 與 persistence specs 亦不受影響。

## MODIFIED Requirements

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

## ADDED Requirements

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
