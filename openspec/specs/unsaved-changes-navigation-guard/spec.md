# unsaved-changes-navigation-guard Specification

## 閱讀導航

- **必讀**：「Dirty Project 必須提供 Save Discard Cancel 決策」、「Destructive continuation 必須延後到 guard 成功之後」與「New 與 Open 必須共用相同 guard semantics」；三者定義 navigation safety 的共同契約。
- **條件式閱讀**：「Save 分支必須沿用目前 Project 的既有儲存路徑」、「儲存嘗試必須回報明確結果」與「Open 目標取消或缺失不得改變目前 Project」；修改 Save outcome 或 Open target selection 時必讀。
- **可先跳過**：Project persistence schema、DXF、Solver、Domain 與各 destination 成功後的專屬操作；本 capability 只定義 destructive navigation 的 guard 與 continuation 邊界。

## Purpose

定義 Main UI 在建立新專案或開啟其他專案前，如何保護未儲存修改、取得 Save／Discard／Cancel 決策，並確保 destructive navigation 只在安全條件成立後執行。

## Requirements

### Requirement: Clean Project 必須直接執行 navigation
當目前 Project 不為 dirty 時，系統 SHALL 直接執行使用者要求的 New 或 Open，不得顯示未儲存變更提示。

#### Scenario: Clean Project 執行 New
- **WHEN** 目前 Project 不為 dirty，且使用者執行 New
- **THEN** 系統不顯示未儲存變更提示
- **AND** 系統直接建立新 Project

#### Scenario: Clean Project 執行 Open
- **WHEN** 目前 Project 不為 dirty，且使用者已選定有效的 Open 目標
- **THEN** 系統不顯示未儲存變更提示
- **AND** 系統直接開始載入選定 Project

### Requirement: Dirty Project 必須提供 Save Discard Cancel 決策
當目前 Project 為 dirty 且使用者執行 New 或 Open 時，系統 MUST 在任何清空或取代目前 Project 的動作前，提供 Save、Discard、Cancel 三種互斥選擇。

#### Scenario: Dirty Project 選擇 Discard
- **WHEN** 使用者在 New 或 Open 的未儲存變更提示選擇 Discard
- **THEN** 系統不儲存目前修改
- **AND** 系統繼續執行原本的 New 或 Open

#### Scenario: Dirty Project 選擇 Cancel
- **WHEN** 使用者在 New 或 Open 的未儲存變更提示選擇 Cancel
- **THEN** 系統取消原本的 New 或 Open
- **AND** 目前 Project、dirty state、Project path、committed results 與 UI selection MUST 保持不變

### Requirement: Save 分支必須沿用目前 Project 的既有儲存路徑
當使用者在 dirty navigation guard 選擇 Save 時，系統 MUST 依目前 Project 是否已有正式路徑，分別執行既有 Save 或 Save As 流程；不得建立第二套 persistence 實作。

#### Scenario: 已有路徑的 Dirty Project 儲存後 New
- **WHEN** dirty Project 已有正式路徑，使用者在 New 前選擇 Save，且 Save 成功
- **THEN** 系統先將目前 Project 儲存至既有路徑
- **AND** 只有在儲存成功後才建立新 Project

#### Scenario: 已有路徑的 Dirty Project 儲存後 Open
- **WHEN** dirty Project 已有正式路徑，使用者在 Open 前選擇 Save，且 Save 成功
- **THEN** 系統先將目前 Project 儲存至既有路徑
- **AND** 只有在儲存成功後才載入選定 Project

#### Scenario: 未命名 Dirty Project Save As 後 New
- **WHEN** dirty Project 沒有正式路徑，使用者在 New 前選擇 Save，且完成 Save As
- **THEN** 系統先以 Save As 建立正式 Project
- **AND** 只有在 Save As 成功後才建立新 Project

#### Scenario: 未命名 Dirty Project Save As 後 Open
- **WHEN** dirty Project 沒有正式路徑，使用者在 Open 前選擇 Save，且完成 Save As
- **THEN** 系統先以 Save As 建立正式 Project
- **AND** 只有在 Save As 成功後才載入選定 Project

### Requirement: 儲存嘗試必須回報明確結果
navigation guard 使用的儲存流程 MUST 明確區分 `saved`、`cancelled` 與 `failed`；不得以同一個空值、truthy／falsy 判斷或未分類 exception 同時代表取消與失敗。Persistence 成功與否 MUST 以既有 persistence workflow 的正式成功結果或失敗為準，而非由對話框選擇直接推定。

#### Scenario: Save 成功
- **WHEN** 既有 Save 或 Save As workflow 完成正式 persistence commit
- **THEN** 儲存結果為 `saved`
- **AND** navigation guard 可繼續原本的 New 或 Open

#### Scenario: Save As 被取消
- **WHEN** 未命名 Project 進入 Save As，而使用者取消名稱選擇、拒絕覆蓋或未完成有效儲存目標
- **THEN** 儲存結果為 `cancelled`
- **AND** 原本的 New 或 Open MUST 被取消

#### Scenario: Save 發生 persistence failure
- **WHEN** Save 或 Save As 的 persistence workflow 失敗
- **THEN** 儲存結果為 `failed`
- **AND** 系統依既有 presentation error handling 顯示儲存失敗
- **AND** 原本的 New 或 Open MUST 被取消

### Requirement: Destructive continuation 必須延後到 guard 成功之後
系統 MUST 在 Save 結果為 `saved` 或使用者明確選擇 Discard 後，才可執行 New 的清空或 Open 的 Project 取代；在此之前不得修改目前正式 Project state。

#### Scenario: Save 尚未確認成功
- **WHEN** 使用者已選擇 Save，但 persistence workflow 尚未回報 `saved`
- **THEN** 系統不得清空或取代目前 Project

#### Scenario: Save As 取消時保留完整狀態
- **WHEN** Save As 回報 `cancelled`
- **THEN** 目前 Project object、dirty state、Project path、committed results 與 UI selection MUST 保持不變

#### Scenario: Save 失敗時保留完整狀態
- **WHEN** Save 或 Save As 回報 `failed`
- **THEN** 目前 Project object、dirty state、Project path、committed results 與 UI selection MUST 保持不變

#### Scenario: Discard 後執行 destructive continuation
- **WHEN** 使用者明確選擇 Discard
- **THEN** 系統可執行且只執行一次原本的 New 或 Open continuation

### Requirement: Open 目標取消或缺失不得改變目前 Project

系統 SHALL由「檔案 → 開啟專案…」顯示目前Project repository的單選視窗，並只在使用者選定一個有效Project目標後進入既有Open navigation guard。若使用者取消或關閉選擇視窗、repository沒有可選Project、沒有有效選取，或選定目標在進入guard前已失效，系統不得進入destructive navigation。這項要求以應用程式內repository selection取代既有工具列selector，但不新增任意filesystem Open file picker。

#### Scenario: Open 目標選擇被取消

- **WHEN** 使用者按Cancel或關閉「開啟專案」選擇視窗
- **THEN** 系統不得顯示會導致目前修改被放棄的確認流程
- **AND** 目前Project、dirty state、Project path、committed results與UI selection MUST保持不變

#### Scenario: Open 沒有有效選取專案

- **WHEN** 使用者執行Open，但repository為空、目前沒有有效單一選取，或選定目標已失效
- **THEN** 系統 SHALL留在或返回Project選擇流程並提供可理解的無可用目標狀態
- **AND** 不得儲存、清空或取代目前Project
- **AND** 不得執行未儲存變更guard

#### Scenario: Open 先取得目標再執行 guard

- **WHEN** 使用者在Project選擇視窗選定一個有效目標並執行Open
- **THEN** 系統 SHALL先固定該目標，再依目前Project dirty state執行既有navigation guard
- **AND** 只有guard回報可繼續後才可載入該目標

#### Scenario: Guard 取消後保留選定目標以外的正式狀態

- **WHEN** 使用者已選定有效Open目標，但後續Save As取消、Save失敗或navigation guard選擇Cancel
- **THEN** 目標Project MUST NOT被載入
- **AND** 目前Project、dirty state、Project path、committed results與UI selection MUST保持不變

### Requirement: New 與 Open 必須共用相同 guard semantics
New 與 Open MUST 使用同一套 clean bypass、Save／Discard／Cancel、明確 save outcome 與 continuation gate semantics；兩個入口不得各自定義互相漂移的未儲存變更規則。

#### Scenario: 相同決策產生相同 gate 結果
- **WHEN** New 與 Open 在相同 dirty state、相同使用者決策及相同 save outcome 下執行
- **THEN** 兩者對 continuation 的允許或阻止結果 MUST 相同
- **AND** 僅 navigation 成功後的 New reset 與 Open load 行為可以不同
