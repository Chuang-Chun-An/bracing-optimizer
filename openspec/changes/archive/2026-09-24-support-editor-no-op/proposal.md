# Proposal

## Why

Support Editor 目前在視窗初始化時就重新評估並採用目前方案，即使使用者沒有改動任何支撐材料排列，也會更新結果時間並使 Project 進入 dirty。這使單純查看或關閉 Editor 被誤判為正式資料修改，增加不必要的儲存提示，也模糊了 manual edit 的 commit boundary。

## What Changes

- Support Editor 只有在正規化後的可編輯 Support pieces 與目前正式結果確實不同時，才採用 staged solution。
- 單純開啟後直接關閉，或在未改變任何值的情況下結束欄位編輯，皆視為 no-op。
- No-op 不替換 `ProjectResultModel` 中的 Support result、不更新 `last_calculated_time`／persisted result metadata，也不設定 Project dirty。
- 真正修改單支或 shared-layout group 的材料排列時，維持既有 immediate commit、工程重算、invalid-result 保留、時間更新、dirty、Results Tree 與 Preview refresh 行為。
- 保留既有 Application engineering boundary，不在 Tkinter callback 複製 Support normalization、shared-layout 或 Solver 規則。

**In Scope**：Support Editor 初始化與 edit event 的 no-op 判定、Application staged-edit outcome、Main adoption gate、時間／dirty side effects，以及對應 characterization、application 與 presentation tests。

**Out of Scope**：改成 Apply／Cancel 型 Editor、rollback 已完成的實際修改、修改 Waler Editor、Support Solver 搜尋或評分、工程合法性規則、Project schema、persistence 格式，以及與本問題無關的 UI／架構重構。

## Capabilities

### New Capabilities

- `support-editor-result-mutation`: 定義 Support Editor 的 no-op 與實際修改 commit boundary，以及 result timestamp、dirty 與 UI refresh 的 observable behavior。

### Modified Capabilities

- 無。

## Impact

- `bracing_optimizer/application/plan_editing.py`：讓 `SupportPlanEditing` 以明確 outcome 表達 normalized input 是否造成實際 Support result change，並保持 staging 不修改來源 solution。
- `main.py`：Support Editor 只在 changed outcome 時採用 staged result、更新時間、dirty 與正式結果顯示；no-op 只更新 Editor 內的唯讀呈現。
- `tests/test_plan_editing.py`、Support Editor presentation／interaction tests：補上初始化、相同輸入、shared-layout group 與實際修改的 commit-side-effect coverage。
- 不改變 Architecture、Domain、Solver 或 persistence truth；會把 `docs/WORKFLOW.md` 中已記錄的 Support editor no-op Product Gap 更新為已實作行為。
