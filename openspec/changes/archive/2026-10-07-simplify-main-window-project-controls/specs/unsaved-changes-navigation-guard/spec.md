# Spec Delta：未儲存變更導覽保護

## 閱讀導航

- **必讀**：「Open 目標取消或缺失不得改變目前 Project」；本 change 只把目標來源由工具列選取改為「開啟專案…」單選視窗。
- **條件式閱讀**：主規格的「Dirty Project 必須提供 Save Discard Cancel 決策」、「Destructive continuation 必須延後到 guard 成功之後」與「New 與 Open 必須共用相同 guard semantics」；修改selection後的navigation時必須維持這些既有規則。
- **可先跳過**：Save／Save As persistence細節、Project schema、DXF、Solver及Domain；本delta不修改其正式行為。

## MODIFIED Requirements

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
