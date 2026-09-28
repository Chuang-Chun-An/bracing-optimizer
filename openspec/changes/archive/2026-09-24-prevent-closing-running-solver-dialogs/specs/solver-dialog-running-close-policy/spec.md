# Spec Delta

## Purpose

本 capability 統一 Support、Single Waler 與 Global Waler Solver Dialog 的執行中關閉政策，避免關閉視窗破壞仍在進行的 Solver lifecycle，並確保運算結束後恢復正常關閉能力。

## ADDED Requirements

### Requirement: Three Solver Dialogs use one running-state close policy

Support Solver Dialog、Single Waler Solver Dialog 與 Global Waler Solver Dialog SHALL 以 Dialog 自身是否處於 running state，作為是否允許關閉的唯一 gate。三者 SHALL 對相同 lifecycle state 提供一致的關閉結果。

#### Scenario: Each Solver Dialog receives a close request while running

- **WHEN** Support、Single Waler 或 Global Waler Solver Dialog 處於 running state，且使用者提出 window close request
- **THEN** 該 Dialog SHALL 保持開啟

#### Scenario: Each Solver Dialog receives a close request while not running

- **WHEN** Support、Single Waler 或 Global Waler Solver Dialog 不處於 running state，且使用者提出 window close request
- **THEN** 該 Dialog SHALL 依其既有非執行中關閉行為正常關閉

### Requirement: Running close requests preserve the active Solver lifecycle

當任一 Solver Dialog 處於 running state 時，close request SHALL NOT destroy Dialog、關閉仍供該次執行使用的 UI callback 通道、中斷或取消 Solver lifecycle、修改 Solver result，或修改該次 operation state。拒絕關閉的使用者提示屬可選行為，提示本身不得取代關閉阻擋。

#### Scenario: Window manager requests close during execution

- **WHEN** window manager 在 Solver Dialog 處於 running state 時送出 close request
- **THEN** 系統 SHALL 拒絕關閉，且該次 Solver SHALL 繼續其原有 lifecycle

#### Scenario: Dialog close action is used during execution

- **WHEN** Solver Dialog 提供的 close action 在 running state 時被使用
- **THEN** 系統 SHALL 套用與 window manager close request 相同的阻擋政策

#### Scenario: Running close request does not alter results or operation state

- **WHEN** 使用者在 Solver Dialog 處於 running state 時提出一次或多次 close request
- **THEN** 系統 SHALL NOT 因這些 close request 採用、清除、回復或以其他方式修改 Solver result 或 operation state

### Requirement: Close permission returns after execution leaves running state

Solver Dialog SHALL 在該次執行的既有成功處理或失敗處理完成後離開 running state；離開後，後續 close request SHALL 恢復正常關閉能力。若背景 worker 無法啟動，Dialog SHALL 回復 non-running state。未啟動背景 worker 的既有流程 SHALL NOT 被標示為 running。

#### Scenario: Successful execution finishes

- **WHEN** Solver 成功完成，且該 Dialog 既有的結果顯示與 result adoption callback 處理已完成
- **THEN** Dialog SHALL 離開 running state，並允許後續正常關閉

#### Scenario: Solver execution fails

- **WHEN** Solver 失敗，且該 Dialog 既有的失敗處理已完成
- **THEN** Dialog SHALL 離開 running state，並允許後續正常關閉

#### Scenario: Background worker fails to start

- **WHEN** Dialog 已準備啟動 Solver，但背景 worker 啟動失敗
- **THEN** Dialog SHALL 回復 non-running state，並允許後續正常關閉

#### Scenario: Existing path completes without starting a worker

- **WHEN** Dialog 透過既有的同步或快取路徑完成操作，且未啟動背景 Solver worker
- **THEN** Dialog SHALL 保持 non-running，並依既有行為允許關閉

### Requirement: Running close protection does not provide worker cancellation

本 capability SHALL NOT 將 close request 解讀為取消要求，且 SHALL NOT 要求新增背景 worker cancellation、termination、join 或 result rollback 行為。

#### Scenario: User attempts to close while worker is active

- **WHEN** 使用者在背景 Solver worker 執行中提出 close request
- **THEN** 系統 SHALL 僅拒絕關閉，且 SHALL NOT 因該要求取消、終止或等待結束該 worker

### Requirement: Existing Global Waler protection remains effective

Global Waler Solver Dialog 既有的執行中 close guard SHALL 保持符合本 capability，且 SHALL 具備 regression coverage；本 change SHALL NOT 改變其 Solver result adoption 或 failure semantics。

#### Scenario: Global Waler close regression while running

- **WHEN** Global Waler Solver Dialog 處於 running state 並收到 close request
- **THEN** Dialog SHALL 保持開啟，且其既有 execution、completion、failure 與 result adoption 行為 SHALL 不受 close request 影響

