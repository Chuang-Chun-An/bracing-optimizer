# Proposal

## 閱讀導航

| 優先級 | 要回答的問題 | 閱讀位置 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | 是否要保留一份由 Codex 封存流程自動追加的專案開發歷程？ | 本文件的「快速摘要」、「現況與目標」、「不變事項」 | 確認目標與紀錄邊界 |
| P1 實作前閱讀 | 每次 archive 必須寫入什麼資訊，以及失敗時如何處理？ | `archive-development-history` spec | 固定可驗證的封存紀錄行為 |
| P1 實作前閱讀 | 如何讓 archive skill 呼叫可重跑、不重複的更新流程？ | `design.md` 的決策與風險章節 | 確認自動化與復原方式 |
| P2 需要時再讀 | 實作與驗證要依什麼順序完成？ | `tasks.md` | 開始執行時使用 |

本次可以先跳過所有 DXF、Solver 與既有產品 capability specs；它們不會改變。

## 快速摘要

- 在 `docs/` 新增一份長期開發歷程，初始內容完整採用使用者提供、截止於 2026/09/28 早上的歷史紀錄與 AI 對話統計。
- 每當 Codex 透過 OpenSpec archive workflow 成功封存一個 change，系統自動在該文件最上方追加一筆可追溯紀錄。
- 封存紀錄會連結 archived change，摘要本次完成內容、影響 capability 與驗證狀態；外部 GPT、Copilot、LINE 對話仍由使用者自行補充。
- archive 完成後若寫入失敗，archive 仍為成功，但必須回報「開發歷程待補寫」並保留可安全重跑的修復線索。
- 不修改產品功能、Git 操作或任何外部對話平台。

## 現況與目標

| 項目 | 現況 | 目標 |
| --- | --- | --- |
| 開發歷程 | 歷史資訊分散在使用者與不同 AI 的對話中 | `docs/DEVELOPMENT_HISTORY.md` 保留使用者提供、截至 2026/09/28 早上的起始紀錄，並成為可提交、可追溯的長期總覽 |
| Codex 封存成果 | 封存內容保留在 `openspec/changes/archive/`，但沒有總覽索引 | 每個成功 archive 都在「Codex／OpenSpec 封存紀錄」區塊最上方新增摘要與來源連結 |
| 外部 AI／通訊紀錄 | 由使用者自行整理 | 維持人工補充，不嘗試存取 GPT、Copilot 或 LINE |
| archive 重試 | 可能需要人工判斷是否已寫入紀錄 | 更新器可辨識既有 archive，避免重複追加 |

## 主要流程

```text
Codex archive request
    ↓
完成既有 artifact、task 與 spec sync 檢查
    ↓
封存 change 至 openspec/changes/archive/
    ↓
讀取 archived change 的 proposal、specs、design、tasks 與驗證結果
    ↓
在 docs/DEVELOPMENT_HISTORY.md 的封存紀錄區塊最上方追加或確認唯一紀錄
    ↓
回報 archive 與開發歷程更新結果；若寫入失敗，標示待補寫並提供重跑線索
```

## 不變事項

- `openspec archive` 原本的 completion、sync 與使用者確認規則維持不變。
- Git commit、push 與外部帳號／對話平台存取仍需由使用者明確要求。
- 開發歷程是摘要與索引，不取代 archived change 的原始 proposal、design、spec 與 tasks。
- 不回填或臆測未出現在 Codex／OpenSpec artifact 中的外部對話內容。
- 使用者提供的起始歷史紀錄維持原有內容與時間範圍；新的 Codex 封存紀錄只新增於其上方，不改寫既有歷史。

## 已確認決策

- `DEVELOPMENT_HISTORY.md` 的起始歷史紀錄完整採用使用者本次提供的版本，資料截至 2026/09/28 早上。
- 新的 Codex／OpenSpec 封存條目採倒序排列，每次成功 archive 都新增於封存紀錄區塊最上方。
- archive 成功但開發歷程寫入失敗時，archive 回報仍為成功；回報必須明確標示「開發歷程待補寫」、保留 archived change 路徑與錯誤原因，並提供可重跑的補寫方式。

## Why

目前 Codex 的開發脈絡散落於 OpenSpec archived changes，無法像使用者自行整理的
GPT、Copilot 與 LINE 紀錄一樣快速回顧。建立一份由 archive workflow 自動更新的
開發歷程，可讓 Codex 完成的工作持續累積成可閱讀、可追溯的專案紀錄。

## What Changes

- 新增 `docs/DEVELOPMENT_HISTORY.md`，以使用者提供、截止於 2026/09/28 早上的歷史時間線與 AI 協作統計作為不可自動回填的起始內容。
- 新增可從 archived OpenSpec change 產生固定格式紀錄的更新器，至少包含封存日期、change 名稱、archive 路徑、完成摘要、受影響 capability 與驗證狀態。
- 擴充 Codex 的 OpenSpec archive workflow：archive 成功後必須呼叫更新器，將新條目加在封存紀錄區塊最上方，並在完成回報中說明開發歷程是否已更新。
- 提供可重跑與去重行為；若 archive 後更新失敗，保留 archive 成功狀態並回報待補寫的修復線索。
- 保留人工補充區，讓使用者日後把 GPT、Copilot、LINE 或會議紀錄整併到同一份文件。

### In Scope

- 開發歷程 Markdown 的格式、初始內容與 Codex／OpenSpec 自動條目。
- archive workflow 的更新時機、失敗回報、可重跑與去重規則。
- 與 archive workflow 相關的 helper、測試與操作指引。

### Out of Scope

- 存取、擷取或同步 GPT、Copilot、LINE、Email 或其他外部服務的對話。
- 自動建立 Git commit、push、release 或變更 Git 歷史。
- 重新整理既有 archived changes 的所有內容；除非使用者後續明確要求回填。
- 修改產品 runtime 行為、工程規則、Solver 或 DXF 匯入流程。

## Capabilities

### New Capabilities

- `archive-development-history`: 將成功封存的 OpenSpec change 以可追溯且可安全重跑的條目寫入長期開發歷程。

### Modified Capabilities

無。

## Impact

- 新增 `docs/DEVELOPMENT_HISTORY.md` 與其更新器／測試。
- 修改 `.agents/skills/openspec-archive-change/SKILL.md`，讓 Codex archive workflow 在成功封存後更新開發歷程。
- 補充 `openspec/config.yaml` 與相關長期文件的 archive 操作規則。
- 不影響現有產品 capability 或既有 archived change 的原始內容。

