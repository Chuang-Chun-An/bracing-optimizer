# Archive Development History Specification

## 閱讀導航

### 必讀

- 「建立並保留起始歷史紀錄」：確認文件的基準內容與排序。
- 「成功封存必須新增可追溯條目」：確認每次 archive 應留下的資訊。
- 「寫入失敗不得撤銷已完成封存」：確認已採納的失敗語意。

### 條件式閱讀

- 「補寫與重跑不得產生重複條目」：實作復原或補寫機制時必讀。
- 「人工補充與外部對話維持分離」：處理文件更新範圍時必讀。

### 可先跳過

- 本 capability 不涉及任何 DXF、Solver 或產品 runtime 規格。

## Purpose

讓成功封存的 OpenSpec change 自動形成可追溯的開發歷程條目，同時保留使用者提供的既有歷史與人工補充內容。

## Requirements

### Requirement: 建立並保留起始歷史紀錄

系統 SHALL 在 `docs/DEVELOPMENT_HISTORY.md` 建立長期開發歷程。文件 SHALL
保留使用者提供、截至 2026/09/28 早上的歷史時間線與 AI 對話統計，作為不可由
archive workflow 自動改寫的起始歷史紀錄。文件 SHALL 在起始歷史紀錄之前設置
「Codex／OpenSpec 封存紀錄」區塊，供後續自動條目以倒序排列。

#### Scenario: 首次建立開發歷程

- **WHEN** 系統第一次建立 `docs/DEVELOPMENT_HISTORY.md`
- **THEN** 文件 SHALL 包含使用者提供的完整起始歷史紀錄與 AI 對話統計
- **AND** SHALL 建立空白的「Codex／OpenSpec 封存紀錄」區塊於起始歷史紀錄上方

#### Scenario: 後續封存不改寫起始歷史

- **WHEN** 系統為新的 archived change 更新開發歷程
- **THEN** 系統 MUST NOT 修改起始歷史紀錄的內容或時間範圍
- **AND** SHALL 只在「Codex／OpenSpec 封存紀錄」區塊新增或確認條目

### Requirement: 成功封存必須新增可追溯條目

每次 Codex 的 OpenSpec archive workflow 成功封存一個 change 後，系統 SHALL
在「Codex／OpenSpec 封存紀錄」區塊最上方新增該 change 的唯一條目。條目 SHALL
包含封存日期、change 名稱、archived change 路徑、完成摘要、受影響 capability
與 archive 前已完成的驗證狀態。

#### Scenario: 成功封存後新增最新條目

- **WHEN** OpenSpec change 已成功移至 archive 位置
- **THEN** 系統 SHALL 將該 change 的開發歷程條目加入封存紀錄區塊最上方
- **AND** 條目 SHALL 指向實際 archive 路徑與對應 change 名稱

#### Scenario: 條目摘要可回溯來源

- **WHEN** 系統建立 archived change 的開發歷程條目
- **THEN** 完成摘要與 capability 資訊 SHALL 可從 archived change 的 planning artifacts 回溯
- **AND** 系統 MUST NOT 將未出現在 Codex／OpenSpec artifacts 的外部對話內容寫入條目

### Requirement: 寫入失敗不得撤銷已完成封存

若 archived change 已成功封存，但開發歷程更新失敗，系統 SHALL 將 archive 視為
成功完成。系統 SHALL 回報「開發歷程待補寫」、archived change 路徑與可辨識的失敗
原因，並保留足以安全重跑補寫的識別資訊。

#### Scenario: 封存後開發歷程寫入失敗

- **WHEN** change 已成功移至 archive 位置但開發歷程條目無法寫入
- **THEN** 系統 SHALL 回報 archive 成功
- **AND** SHALL 回報「開發歷程待補寫」與 archived change 路徑
- **AND** MUST NOT 將已封存的 change 移回 active changes

### Requirement: 補寫與重跑不得產生重複條目

系統 SHALL 能以 archived change 的唯一識別確認開發歷程是否已包含該條目。對相同
archived change 重跑更新時，系統 MUST NOT 建立第二筆條目；若既有條目不完整，系統
SHALL 修復該條目或回報無法安全修復的原因。

#### Scenario: 對已記錄的 archive 重跑更新

- **WHEN** 系統再次處理已存在開發歷程條目的 archived change
- **THEN** 系統 MUST NOT 新增重複條目
- **AND** SHALL 回報條目已存在或已完成必要修復

#### Scenario: 補寫先前失敗的 archive

- **WHEN** 系統重新處理先前回報「開發歷程待補寫」的 archived change
- **THEN** 系統 SHALL 在封存紀錄區塊建立或修復該 change 的唯一條目
- **AND** SHALL 回報補寫結果

### Requirement: 人工補充與外部對話維持分離

開發歷程 SHALL 保留可由使用者手動補充外部 GPT、Copilot、LINE、會議或其他來源
的紀錄區塊。Codex archive workflow MUST NOT 存取外部服務，且更新自動封存條目時
MUST NOT 覆寫人工補充內容。

#### Scenario: 使用者保留人工補充內容

- **WHEN** 使用者已在開發歷程加入人工補充
- **THEN** 系統更新自動封存條目時 MUST NOT 修改該人工補充內容
