# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：Project load、結果／設定採用、projection editing guard、CAD ACK 邊界與 managed DXF save rollback Requirements。
- **實作前閱讀（P1）**：`../../design.md` 的 stage → commit → project 決策及各 mutation 的 source of truth。
- **需要時再讀（P2）**：Global Waler 與 navigation guard specs；本 change 保留它們已成立的 transaction 行為。

## Purpose

定義 Project mutation 的一致交易邊界，避免 UI refresh、summary、CAD ACK 或 managed DXF rollback 失敗時留下模型、metadata、dirty state、結果、DXF 狀態或救援檔互相矛盾。

## ADDED Requirements

### Requirement: Project load 以完整 staged state 一次採用

Project load SHALL 在取代目前 Project 前完成可預先執行的解析、驗證與 runtime state 建立。正式採用時，Project model、results、metadata、DXF status、runtime caches、current path 與 dirty state SHALL 作為一個一致 state transition。

#### Scenario: Load 在 commit 前失敗

- **WHEN** Project 解析、驗證或 staged state 建立失敗
- **THEN** 目前 Project 的正式 state SHALL 完全保持不變
- **AND** 系統 SHALL 報告新 Project 未載入

#### Scenario: Load commit 成功但 UI projection 失敗

- **WHEN** 新 Project 已完整 commit，但後續 UI refresh 失敗
- **THEN** 正式 state SHALL 保持為完整的新 Project
- **AND** 載入後的 dirty state SHALL 為 `False` 且 dirty reason SHALL 為空
- **AND** 系統 SHALL 明確報告 Project 已載入但畫面更新失敗
- **AND** SHALL NOT 將新舊 Project state 混合或誤報為完全未載入

### Requirement: Support 與 Single Waler 結果採用不得部分提交

Support 與 Single Waler result adoption SHALL 先建立完整可提交 outcome，再一次更新 result model、summary 所需資料、calculated metadata、相關 cache invalidation 與 dirty state。可預先計算的轉換失敗 SHALL 發生在 commit 前。

#### Scenario: Result projection 在 commit 前失敗

- **WHEN** Solver output 無法轉換為完整的正式 result outcome
- **THEN** 既有 committed results、metadata 與 dirty state SHALL 保持不變

#### Scenario: Result 已 commit 後畫面 refresh 失敗

- **WHEN** 完整 result outcome 已 commit，但 result table 或 summary refresh 失敗
- **THEN** 正式 result、metadata 與 dirty state SHALL 保持一致的已提交狀態
- **AND** 系統 SHALL 將錯誤描述為顯示更新失敗，不得假裝結果未採用

### Requirement: Material Spec mutation 使用一致 commit 邊界

Material Spec 編輯 SHALL 將材料設定、受影響結果失效、runtime cache invalidation 與 dirty state 作為一個正式 transition。UI refresh 失敗 SHALL NOT 留下新設定搭配舊結果或錯誤的 clean state。

#### Scenario: Material Spec staged mutation 失敗

- **WHEN** 新材料設定在 commit 前無法建立完整 mutation outcome
- **THEN** 既有材料設定、結果、cache 與 dirty state SHALL 保持不變

#### Scenario: Material Spec commit 後 refresh 失敗

- **WHEN** 材料設定與 invalidation 已 commit，但 UI refresh 失敗
- **THEN** 正式 state SHALL 保持一致且為 dirty
- **AND** 系統 SHALL 報告顯示更新問題

### Requirement: Projection 失敗後禁止在 stale 畫面修改資料

任何正式 mutation 已 commit 但 UI projection 失敗時，系統 SHALL 將 projection 標記為 stale，並禁止 Project、Result、Material Spec、Solver result adoption 與 CAD event 等資料修改入口繼續修改正式 state。系統 SHALL 提供一個可由使用者執行的完整重新投影入口，從 committed state 重建所有受影響畫面。

#### Scenario: Commit 後 projection 失敗

- **WHEN** 正式 mutation 已完整 commit，但任一 UI projection 步驟失敗
- **THEN** committed state SHALL 保持不變
- **AND** 系統 SHALL 鎖住資料修改入口
- **AND** 系統 SHALL 明確顯示資料已更新但畫面未同步
- **AND** 唯讀狀態查看與完整重新投影入口 SHALL 保持可用

#### Scenario: 完整重新投影成功

- **WHEN** projection 為 stale，且使用者執行完整重新投影
- **AND** 輸入表、Results Tree、材料摘要、Preview、Project／DXF／CAD status 與 action state 全部成功由 committed state 重建
- **THEN** 系統 SHALL 清除 stale 狀態並解除資料修改鎖定

#### Scenario: 完整重新投影再次失敗

- **WHEN** projection 為 stale，且重新投影任一步驟失敗
- **THEN** 系統 SHALL 維持資料修改鎖定
- **AND** SHALL 報告最新 projection error
- **AND** SHALL NOT 回滾或部分修改 committed state

### Requirement: CAD ACK 只確認已完成的正式 mutation

CAD event SHALL 僅在對應 Project mutation 已成功 commit 後 ACK。ACK 後發生的 UI projection failure SHALL NOT 嘗試回復到 ACK 前的 Project state；系統 SHALL 保留已提交的 model、metadata、result invalidation、DXF status 與 dirty state，並明確報告畫面更新失敗。同一 event ID 的 mutation SHALL NOT 被重複套用。

#### Scenario: CAD mutation 在 ACK 前失敗

- **WHEN** CAD event 無法建立或 commit 完整 Project mutation
- **THEN** event SHALL 保持未 ACK，以便依既有流程重試或清除
- **AND** 目前 Project state SHALL 保持不變

#### Scenario: ACK 後 UI refresh 失敗

- **WHEN** CAD mutation 已 commit 且 event 已 ACK，之後 UI refresh 失敗
- **THEN** 系統 SHALL 保留 committed mutation
- **AND** status SHALL 區分「資料已更新」與「畫面更新失敗」

#### Scenario: Mutation 已 commit 但 ACK 寫入失敗

- **WHEN** CAD mutation 已完整 commit，但 ACK filesystem operation 失敗
- **THEN** 系統 SHALL 保留 committed mutation，不得執行部分 rollback
- **AND** SHALL 將該 event 標記為 ACK unresolved 並停止 CAD 監聽
- **AND** SHALL 阻止 Project save，直到 pending event 已由使用者明確清除或處理
- **AND** SHALL 回報「資料已更新，但 CAD event 尚未清除」

#### Scenario: ACK unresolved event 再次被偵測

- **WHEN** ACK unresolved 尚未解除，且 watcher 再次看見相同 event ID
- **THEN** 系統 SHALL NOT 再次套用該 mutation
- **AND** SHALL NOT 自動恢復 CAD 監聽或自動 ACK
- **AND** SHALL 繼續要求使用者處理 pending event

### Requirement: Managed DXF save rollback 失敗時保留 recovery artifact

Project save 在替換既有 managed DXF 後若後續步驟失敗，SHALL 嘗試依既有 rollback 流程復原 `source/source.dxf`。只有 managed DXF rollback 成功時才可刪除 `.rollback` recovery artifact；rollback 失敗時 SHALL 保留可取得的 recovery artifact 並向使用者報告其路徑。本 Requirement 不改變 Project JSON 的 temporary write、atomic replace 或 `.bak` 行為。

#### Scenario: 後續失敗但 rollback 成功

- **WHEN** save 後續步驟失敗，且舊檔成功復原
- **THEN** save SHALL 回報失敗
- **AND** rollback 完成後 MAY 清理不再需要的 recovery artifact

#### Scenario: rollback 本身失敗

- **WHEN** save 後續步驟失敗，且舊 managed DXF 無法自動復原
- **THEN** 系統 SHALL 保留 `.rollback` recovery artifact（若已建立）
- **AND** SHALL 回報自動復原失敗與 recovery path
- **AND** SHALL NOT 在 finally cleanup 中刪除該 artifact

#### Scenario: 下一次 save 發現既有 recovery artifact

- **WHEN** 新一次 save 開始前，目標 managed DXF 已存在 `.rollback` recovery artifact
- **THEN** 系統 SHALL 在建立 temporary file 或替換任何正式檔案前拒絕 save
- **AND** SHALL 回報既有 recovery artifact 與 managed DXF 的絕對路徑
- **AND** SHALL NOT 覆蓋、刪除或重新命名既有 recovery artifact
- **AND** SHALL NOT 修改 Project JSON、managed DXF 或 runtime dirty state
