# Spec Delta

## 閱讀導航

- **現在必讀（P0）**：「有效 CAD mutation 使已登記的 Solver snapshot 失效」「三種 Solver 合作式結束」「stale operation 不得採用任何輸出」「取消後不自動重跑」。
- **條件式閱讀（P1）**：處理 CAD error／no-op 時讀「不改變 Project 的 CAD event 不影響 Solver lifecycle」；處理 Dialog lifecycle 時讀「stale Dialog 不得啟動或重用舊 input」。
- **可先跳過**：`solver-dialog-running-close-policy` 的其他 Requirement；本 capability 不改變使用者 close request。

## Purpose

確保有效 CAD add／update 能使三種 Solver 已持有或正在使用的舊 Project input snapshot 失效、要求 running worker 安全停止，並阻止任何晚到結果或 cache 回寫至已更新的 Project。

## ADDED Requirements

### Requirement: 有效 CAD mutation 使已登記的 Solver snapshot 失效

當 CAD add／update 已通過既有 validation、mapping 與 no-op 判斷，且即將改變 Project input 時，系統 SHALL 在 Project mutation 前，使所有已登記且尚未關閉的 Support、Single Waler 與 Global Waler input snapshot handles 不再具備啟動或 output adoption 資格。系統 SHALL 對其中正在執行的 operations 發出 cancellation request，且 SHALL NOT 等待 worker 結束才執行既有 CAD transaction。

#### Scenario: Active Solver 執行中套用有效 CAD add／update

- **WHEN** 一個有效且非 no-op 的 CAD add／update 即將改變 Project，且任一種 Solver operation 仍 active
- **THEN** 系統 SHALL 先使該 operation 的 output 不可採用並發出 cancellation request
- **AND** 系統 SHALL 立即繼續既有 CAD row／DXF state commit、ACK 與 input invalidation 流程

#### Scenario: 多個 active operations

- **WHEN** CAD mutation 前同時存在一個以上 active Solver operation
- **THEN** 系統 SHALL 對當下所有 active operations 套用相同的 stale 與 cancellation 行為

#### Scenario: 已開啟但尚未執行的 Dialog

- **WHEN** 有效且非 no-op 的 CAD add／update 即將改變 Project，而 Solver Dialog 已持有已登記的 input snapshot但尚未啟動 worker
- **THEN** 系統 SHALL 將該 snapshot handle 標成 stale
- **AND** SHALL NOT 為該 handle 發出不必要的 worker cancellation request

#### Scenario: CAD transaction 的 ACK 失敗

- **WHEN** 系統已要求取消 Solver，CAD commit 已包含 Project row／DXF state、input／result／cache invalidation 與 dirty outcome，但後續 ACK filesystem operation 失敗
- **THEN** 系統 SHALL 沿用既有 unresolved guard，保留 committed mutation且不得執行部分 rollback
- **AND** SHALL 沿用既有 unresolved guard標記 unresolved event、停止 CAD polling、阻止 save，並防止相同 event ID 重複套用
- **AND** 已失效的 Solver operation SHALL 保持不可採用且 SHALL NOT 自動恢復或重跑

本 Scenario 所稱既有 unresolved guard 由 `docs/WORKFLOW.md`「10.3 Staging and commit」、`main.py::_mark_cad_ack_unresolved`／`_schedule_cad_event_poll`／`_ensure_mutation_allowed`／`_apply_cad_event`，以及 `tests/test_cad_builder_integration.py::test_ack_failure_keeps_project_row_and_blocks_replay` 定義；停止 polling、阻止 save與 duplicate-event handling不是本 change新增的規則。

### Requirement: 不改變 Project 的 CAD event 不影響 Solver lifecycle

無效 event、CAD control cancel event，以及經判定不改變 Project geometry 的 no-op update SHALL NOT 使已登記的 Solver snapshot handle 失效、停用尚未執行之 Dialog 的 Run，或觸發 running worker 的 cancellation request。

#### Scenario: 無效 CAD event

- **WHEN** CAD event 未通過既有 validation 或 mapping，Project 未改變且 event 被保留
- **THEN** active Solver SHALL 繼續既有 lifecycle

#### Scenario: CAD control cancel event

- **WHEN** 系統收到並 ACK 既有 CAD control cancel event
- **THEN** Project 與 active Solver lifecycle SHALL 保持不變

#### Scenario: CAD update 是 no-op

- **WHEN** CAD update 經既有規則判定 geometry 未改變並直接 ACK
- **THEN** active Solver SHALL NOT 因該 event 被標成 stale 或要求取消

#### Scenario: 尚未執行的 Dialog 遇到不改變 Project 的 event

- **WHEN** Solver Dialog 已開啟但尚未按 Run，且系統處理無效 event、CAD control cancel event 或 no-op update
- **THEN** 該 Dialog 的 snapshot handle SHALL 保持可啟動
- **AND** Run action SHALL 維持既有可用狀態

### Requirement: 三種 Solver 合作式結束

Support、Single Waler 與 Global Waler SHALL 在不會提交部分正式 state 的安全 checkpoint 檢查 cancellation request，並以可與一般 failure 區分的 cancelled outcome 結束。系統 MUST NOT 強制終止 Python thread。

#### Scenario: Support Solver 偵測取消

- **WHEN** Support Solver 在候選生成或全域組合的安全 checkpoint 偵測到 cancellation request
- **THEN** 該 operation SHALL 以 cancelled outcome 結束
- **AND** SHALL NOT 提交部分 Support solution、diagnostics 或 candidate cache

#### Scenario: Single Waler Solver 偵測取消

- **WHEN** Single Waler Solver 在搜尋階段或 generation 安全 checkpoint 偵測到 cancellation request
- **THEN** 該 operation SHALL 以 cancelled outcome 結束
- **AND** SHALL NOT 提交部分 Top 5、diagnostics 或 solver memory

#### Scenario: Global Waler Solver 偵測取消

- **WHEN** Global Waler Solver 在 local candidate 或 exact global selection 的安全 checkpoint 偵測到 cancellation request
- **THEN** 該 operation SHALL 以 cancelled outcome 結束
- **AND** SHALL NOT 自動採用任何 partial 或 complete global solution

### Requirement: stale operation 不得採用任何輸出

每次 Solver 執行 SHALL 綁定唯一 operation identity。任何 result、diagnostics、summary、calculated time、dirty state 或 runtime cache 只有在該 operation 仍具 adoption 資格時才能提交；因 CAD mutation 失效後到達的 success、failure 或 cancelled callback 只能執行必要的 idempotent cleanup。

#### Scenario: CAD mutation 先於 success callback

- **WHEN** operation 已因 CAD mutation 失效，而 success callback 較晚到達
- **THEN** 系統 SHALL 丟棄該 operation 的 result、diagnostics 與 cache output
- **AND** SHALL NOT 修改已更新的 Project、`ProjectResultModel`、calculated time 或 dirty state

#### Scenario: success callback 先於 CAD mutation

- **WHEN** success callback 在 CAD mutation 開始前已完成既有 result commit
- **THEN** 後續 CAD input invalidation SHALL 依既有規則清除該 committed result 與 runtime caches
- **AND** CAD mutation 完成後 SHALL NOT 留下舊 input 的正式 result

#### Scenario: 重複或交錯 terminal callback

- **WHEN** 同一 operation 的 cleanup 被重複觸發，或舊 operation callback 在較新 lifecycle 後到達
- **THEN** terminal cleanup SHALL 保持 idempotent
- **AND** 舊 callback SHALL NOT 改變其他 operation 的 running state 或 output

### Requirement: 正式 Solver output 須同時通過 operation 與既有 mutation guard

Solver completion SHALL 只有在該operation仍可採用，且既有Project mutation guard允許正式state mutation時，才可寫入result、diagnostics、calculated time、dirty state或runtime cache。ACK unresolved SHALL NOT 阻止使用者開啟Solver Dialog或按Run，且系統 SHALL NOT 因registry仍判定operation可採用而繞過既有unresolved guard。

#### Scenario: unresolved狀態下完成的operation

- **WHEN** 使用者在CAD ACK unresolved期間開啟並執行Solver，且worker完成時registry仍判定該operation可採用
- **THEN** 既有unresolved guard SHALL 阻止正式result與diagnostics adoption
- **AND** Support candidate cache與Single Waler solver memory SHALL NOT 寫入
- **AND** calculated time、dirty state與既有committed result SHALL NOT 因該completion改變
- **AND** Dialog SHALL 完成terminal cleanup且不得產生未處理例外
- **AND** Dialog SHALL 將結果分類為未採用，而不是一般Solver failure
- **AND** 系統 SHALL NOT 在Dialog開啟或Run入口新增unresolved-only阻擋

### Requirement: stale Dialog 不得啟動或重用舊 input

Solver Dialog 持有的 input snapshot 一旦因 CAD mutation 失效，Dialog SHALL 顯示已因 CAD 更新停止並提示「請關閉後重新開啟 Solver」。尚未執行的 Dialog SHALL 立即停用 Run；正在執行的 Dialog SHALL 在 worker terminal cleanup 後離開 running state並恢復可關閉，但 SHALL NOT 允許以建立 Dialog 時的舊 input snapshot 再次啟動 Solver。

#### Scenario: Dialog 已開啟但尚未按 Run

- **WHEN** Solver Dialog 已持有 input snapshot但尚未啟動 worker，期間發生有效且非 no-op 的 CAD mutation
- **THEN** Dialog SHALL 將 Run action 設為不可用
- **AND** SHALL 顯示「請關閉後重新開啟 Solver」的提示
- **AND** 使用者 SHALL NOT 能以該 stale snapshot 啟動 worker

#### Scenario: CAD 更新取消後 Dialog 完成 cleanup

- **WHEN** stale operation 的 worker completion 已由 UI thread 處理
- **THEN** Dialog SHALL 恢復可關閉狀態並顯示 CAD 更新取消原因
- **AND** 原 Dialog 的 Run action SHALL 保持不可用

#### Scenario: 使用者要以新 Project 再次求解

- **WHEN** 使用者在 CAD 更新完成後決定重新求解
- **THEN** 使用者 SHALL 從目前 Project 重新開啟 Solver workflow，以建立新的 input snapshot 與 operation identity

#### Scenario: 舊 Waler worker 仍在合作式停止

- **WHEN** Single 或 Global Waler operation 已收到 cancellation request但 worker 尚未到達 checkpoint並釋放既有 busy lease，且使用者嘗試重新開啟 Single／Global Waler workflow
- **THEN** 系統 SHALL 拒絕啟動新的 Waler worker
- **AND** SHALL 顯示「前一次計算正在停止，請稍後再試」或語意相同的提示
- **AND** SHALL NOT 強制釋放既有 lease或允許兩個 Waler workers 同時執行

### Requirement: 取消後不自動重跑

CAD mutation 成功或失敗後，系統 SHALL NOT 因本 capability 自動建立新的 Solver operation、重新開啟 Dialog 或以更新後 input 重跑任何 Solver。

#### Scenario: CAD mutation 成功

- **WHEN** active Solver 已被要求取消且 CAD add／update 成功完成
- **THEN** 系統 SHALL 保持沒有自動替代 operation 的狀態

#### Scenario: CAD mutation 已提交但 ACK unresolved

- **WHEN** active Solver 已被要求取消，CAD mutation 已提交，但後續 ACK 進入既有 unresolved guard
- **THEN** 原 operation的 cancellation token SHALL 維持已設定且 operation SHALL 保持不可採用
- **AND** 系統 SHALL NOT 自動恢復原 operation或啟動替代 operation

#### Scenario: 使用者在沒有 CAD 更新時關閉執行中 Dialog

- **WHEN** 使用者對仍在執行的 Solver Dialog提出一般 close request，且沒有觸發本 capability 的 CAD mutation
- **THEN** 系統 SHALL 繼續遵守既有 running close policy
- **AND** SHALL NOT 將 close request 解讀為 cancellation request

