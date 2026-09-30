# Design

## 閱讀導航

### 現在必讀

- 「由 Codex archive skill 觸發」：此功能只保證在 Codex 執行 archive workflow 時自動更新；直接執行原生 `openspec archive` CLI 不會觸發它。
- 「受管理的封存紀錄區塊」：更新器只修改明確界定的區塊，避免覆寫使用者的起始歷史與人工補充。
- 「封存成功、補寫可重跑」：開發歷程更新失敗不回滾 archive，改以可重跑的待補寫狀態處理。

### 需要實作特定部分時再讀

- 實作條目產生與去重時，閱讀「唯一識別與冪等更新」。
- 修改 archive workflow 時，閱讀「archive skill 整合」。
- 撰寫失敗路徑測試時，閱讀「失敗與修復紀錄」。

## 方案摘要

```text
Codex archive skill
    ↓ archive 成功後
development-history updater
    ├─ 讀取 archived change artifacts
    ├─ 產生或確認唯一條目
    └─ 原子更新 DEVELOPMENT_HISTORY.md
             ↓ 失敗
       保留 archive 成功 + 建立待補寫線索 + 回報重跑方式
```

`docs/DEVELOPMENT_HISTORY.md` 是人類閱讀的長期總覽；archived change 仍是
完成內容的原始來源。更新器只將來源資訊整理為摘要，不重新解讀外部對話。

## 決策對照

| Decision | 選擇與原因 | 影響的 Requirement／task |
| --- | --- | --- |
| 觸發點 | archive skill 完成原有 archive move 後才呼叫更新器，避免未成功封存就留下正式條目 | 「成功封存必須新增可追溯條目」；archive workflow task |
| 管理邊界 | 用明確標記包住「Codex／OpenSpec 封存紀錄」；更新器只改該區塊 | 「建立並保留起始歷史紀錄」、「人工補充與外部對話維持分離」；文件／更新器 task |
| 唯一識別 | 以 archived change 的相對 archive 路徑作為條目 key，並寫入 Markdown 註解 | 「補寫與重跑不得產生重複條目」；更新器與測試 task |
| 失敗語意 | archive 已成功時不回滾；回報待補寫並寫入可重跑線索 | 「寫入失敗不得撤銷已完成封存」；archive skill 與失敗測試 task |
| 外部紀錄 | 不存取外部服務，保留人工補充區 | 「人工補充與外部對話維持分離」；文件格式 task |

## Context

目前 `openspec/changes/archive/` 已保存每個 change 的 planning artifacts，但沒有一份
可按時間快速回顧的總覽。現有 `.agents/skills/openspec-archive-change/SKILL.md` 由
Codex 協調 archive 的檢查、spec sync 與移動；原生 `openspec archive` CLI 沒有本專案的
post-archive hook。

這是 workflow 層級的輔助能力，不改變 `Presentation`、`Application`、`Domain`、
`Algorithms` 或 `Infrastructure` 的產品責任。

## Goals / Non-Goals

**Goals:**

- 建立以使用者提供內容為基準的長期開發歷程。
- 讓 Codex archive workflow 在成功後自動產生最上方的封存摘要。
- 讓補寫可重跑且不重複，並保護人工內容。

**Non-Goals:**

- 不為原生 OpenSpec CLI 增加全域 hook 或修改外部安裝套件。
- 不將外部 AI／通訊平台內容自動匯入。
- 不將開發歷程當成 archive artifact 的替代來源。

## Decisions

### 由 Codex archive skill 觸發

修改專案內的 `.agents/skills/openspec-archive-change/SKILL.md`，使它在 archive move
成功後執行專案內的更新器。這符合使用者所說「Codex 的就自動記完了」，且不需要修改
OpenSpec CLI 或建立常駐程序。

直接呼叫 `openspec archive` 不會自動更新開發歷程；archive skill 的輸出必須清楚說明
這個限制。

### 受管理的文件區塊

`docs/DEVELOPMENT_HISTORY.md` 使用下列穩定結構：

```text
# 開發歷程

## Codex／OpenSpec 封存紀錄
<!-- codex-archive-log:start -->
最新封存條目
...
<!-- codex-archive-log:end -->

## 人工補充紀錄

## 起始歷史紀錄（截至 2026/09/28 早上）
使用者提供的完整時間線

## AI 對話統計（截至 2026/09/28 早上）
使用者提供的統計
```

更新器只能替換 start／end 標記之間的內容。新條目放在該區塊最前方，因此維持倒序；
人工補充與起始歷史永遠不在可寫入範圍內。

### 唯一識別與冪等更新

新增一個專案內 helper，接收 archived change 目錄及 archive workflow 已知的驗證摘要。
它以 archive 相對路徑建立穩定 key，例如：

```text
<!-- codex-archive-log:key=2026-09-28-example-change -->
```

更新前先搜尋 key：存在且完整時不寫入第二筆；存在但條目不完整時只修復該條目；不存在時
才在管理區塊最上方新增。文件寫入使用暫存檔後取代，以避免部分 Markdown 寫入。

條目摘要以 archived `proposal.md` 的問題／變更內容與 delta specs 的 capability 名稱為
來源；驗證欄位只描述 archive workflow 實際已完成的檢查，不能杜撰測試結果。

### 失敗與修復紀錄

archive move 完成後，開發歷程更新失敗不回滾 archive。archive skill 回報：

- archive 已成功的目錄。
- 「開發歷程待補寫」狀態與錯誤原因。
- 可重新執行更新器的 archived change 路徑。

更新器應盡可能在 archived change 中建立只含機器可讀識別與錯誤摘要的 pending marker。
若 marker 也無法寫入，archive skill 的回報仍保留相同資訊；下次以 archived change
路徑重跑即可補寫。成功補寫後移除或標記 pending marker 為已解決。

### Architecture Alignment

此變更沿用既有架構：

- archive skill 是 workflow orchestration 的入口。
- helper 負責局部檔案讀寫與 Markdown 條目產生。
- `DEVELOPMENT_HISTORY.md` 是單一人類可讀總覽；archived artifacts 是內容的單一原始來源。

不新增產品 runtime state、Project persistence schema 或 Domain rule。

## Risks / Trade-offs

- [使用者直接執行原生 CLI archive，未產生紀錄] → 在 archive skill 與操作文件明確說明此能力只由 Codex workflow 保證。
- [歷史文件遭手動破壞標記] → 更新器偵測缺失或不成對標記時拒絕覆寫，回報可修正位置。
- [摘要品質不足或含未驗證推論] → 條目只引用 archived artifacts 的已寫內容，並保持原始檔案連結。
- [archive 成功後寫入失敗] → 保留 archive 成功、輸出待補寫資訊與 stable key，允許安全重跑。
- [AI 對話統計會隨時間過期] → 初始統計標示其截止時間；後續不自動宣稱為最新值。

## Migration Plan

1. 建立初始 `DEVELOPMENT_HISTORY.md`，逐字保留使用者提供的起始歷史與統計。
2. 實作更新器與單元測試，驗證新增、去重、補寫與保護人工內容。
3. 擴充 archive skill，在成功 archive 後呼叫更新器並回報結果。
4. 以暫存 archived change 執行一次更新，確認最新條目在管理區塊最上方。
5. 更新 workflow／archive 操作指引，說明 Codex archive 與原生 CLI 的差異。
