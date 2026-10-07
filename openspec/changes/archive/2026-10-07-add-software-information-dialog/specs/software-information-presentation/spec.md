# Spec Delta

## 閱讀導航

- **必讀**：「可從主視窗開啟軟體資訊」、「顯示可辨識的軟體身分」與「完整顯示起始歷史紀錄」；三者定義主要使用流程與必要內容。
- **條件式閱讀**：「資源異常時保留基本資訊」在處理 release resource 或錯誤顯示時必讀；「資訊視窗不得修改 Project」在 wiring 主視窗 lifecycle 時必讀。
- **可先跳過**：Project persistence、DXF、Solver、Domain 與材料規則；本 capability 只新增產品資訊的唯讀呈現。

## Purpose

讓桌面程式使用者能在單一、穩定且唯讀的入口確認目前軟體名稱、版本、指定作者，以及 `docs/DEVELOPMENT_HISTORY.md` 的起始歷史紀錄，並在原始碼與正式封裝環境獲得一致且可辨識的資訊。

## ADDED Requirements

### Requirement: 可從主視窗開啟軟體資訊

系統 SHALL 在主視窗提供「說明」選單，並在其中提供「軟體資訊」命令。使用者執行命令後，系統 SHALL 開啟一個標題可辨識、可關閉且內容可閱讀的獨立資訊視窗；開啟過程 MUST NOT 要求先建立、開啟或儲存 Project。

#### Scenario: 尚未建立 Project 時開啟資訊

- **WHEN** 使用者在沒有目前 Project 的情況下執行「說明 → 軟體資訊」
- **THEN** 系統 SHALL 開啟軟體資訊視窗
- **AND** SHALL 不要求使用者建立或選取 Project

#### Scenario: 從既有 Project 開啟資訊

- **WHEN** 使用者在已開啟 Project 的情況下執行「說明 → 軟體資訊」
- **THEN** 系統 SHALL 在主視窗上方開啟軟體資訊視窗
- **AND** 使用者關閉資訊視窗後 SHALL 回到同一個 Project

### Requirement: 顯示可辨識的軟體身分

軟體資訊視窗 SHALL 以清楚標籤顯示非空白的產品名稱、release 版本與作者 `莊竣安（Chuang Chun An）`。顯示版本 SHALL 與該次 source run 或正式發行包所宣告的 release 版本一致，不得顯示 Project schema、DXF 格式或 Solver policy version 代替產品版本。

#### Scenario: 顯示目前 release 身分

- **WHEN** 軟體資訊視窗成功開啟
- **THEN** 系統 SHALL 顯示產品名稱、產品版本與作者 `莊竣安（Chuang Chun An）`
- **AND** 產品版本 SHALL 可供使用者逐字辨識及回報

#### Scenario: 不混淆其他版本號

- **WHEN** 目前 Project、DXF 或 Solver 同時具有自己的版本欄位
- **THEN** 軟體資訊視窗的主要版本欄位 SHALL 仍只代表產品 release 版本

### Requirement: 完整顯示起始歷史紀錄

軟體資訊視窗 SHALL 提供唯讀且可捲動的開發歷程。其唯一內容來源 SHALL 是 `docs/DEVELOPMENT_HISTORY.md` 中「起始歷史紀錄（截至 2026/09/28 早上）」標題之後、下一個同層標題之前的全部表格紀錄。系統 SHALL 完整保留每筆日期文字、紀錄文字及文件中的原始先後順序；UI MAY 改變表格排版以利閱讀，但 MUST NOT 摘要、刪減、重新排序或加入來源區段以外的歷程。

#### Scenario: 逐筆呈現完整起始歷史紀錄

- **WHEN** 使用者開啟軟體資訊視窗
- **THEN** 系統 SHALL 顯示起始歷史紀錄中的每一筆日期與紀錄文字
- **AND** 顯示順序 SHALL 與 `docs/DEVELOPMENT_HISTORY.md` 的起始歷史紀錄相同
- **AND** 使用者 SHALL 能捲動閱讀超出視窗範圍的內容

#### Scenario: 排除其他開發歷程區段

- **WHEN** `docs/DEVELOPMENT_HISTORY.md` 同時包含「Codex／OpenSpec 封存紀錄」、「人工補充紀錄」與「AI 對話統計」
- **THEN** 軟體資訊視窗 MUST NOT 顯示這三個區段的內容
- **AND** MUST NOT 顯示起始歷史紀錄範圍外的其他同層區段

#### Scenario: 離線閱讀歷程

- **WHEN** 執行環境沒有網路連線
- **THEN** 系統 SHALL 仍能顯示隨目前 release 交付的完整起始歷史紀錄

### Requirement: 資源異常時保留基本資訊

若使用者可讀開發歷程缺少、無法讀取或內容無法解譯，系統 SHALL 保持資訊視窗可開啟並繼續顯示產品名稱、release 版本與作者。歷程區 SHALL 顯示可理解的「開發歷程目前無法取得」類訊息，且 MUST NOT 顯示未處理的例外或使主程式結束。

#### Scenario: 歷程資源缺少

- **WHEN** 使用者開啟軟體資訊，但歷程資源不存在
- **THEN** 系統 SHALL 顯示產品名稱、release 版本與作者
- **AND** SHALL 在歷程區顯示資源目前無法取得的訊息
- **AND** MUST NOT 關閉主程式或改變目前 Project

#### Scenario: 歷程資源內容無法解譯

- **WHEN** 使用者開啟軟體資訊，但歷程資源無法依支援格式解譯
- **THEN** 系統 SHALL 使用與資源缺少相同的可理解 fallback
- **AND** MUST NOT 向使用者顯示原始 traceback

### Requirement: 資訊視窗不得修改 Project

開啟、閱讀、捲動或關閉軟體資訊視窗 MUST NOT 修改 Project input、結果、DXF state、目前 Project path、dirty state 或儲存提示狀態。資訊視窗 MUST NOT 提供修改產品 metadata 或開發歷程的控制項。

#### Scenario: 從乾淨 Project 開啟後關閉

- **WHEN** 使用者從未修改的乾淨 Project 開啟並關閉軟體資訊視窗
- **THEN** Project SHALL 維持乾淨
- **AND** 系統 MUST NOT 顯示未儲存變更提示

#### Scenario: 從已有未儲存變更的 Project 開啟後關閉

- **WHEN** 使用者從已具有未儲存變更的 Project 開啟並關閉軟體資訊視窗
- **THEN** 原 dirty state 與 dirty reason SHALL 保持不變

