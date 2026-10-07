# DXF 重新連結需求前期調查

> 狀態：需求已初步確認，暫不建立 OpenSpec proposal。未來準備實作時，應重新核對當時 code、主 spec 與 tests，再以本文件作為提案輸入。

## 1. 問題界線

「是否已完成 DXF 匯入」是正式切分點：

- 從未匯入 DXF 的手動 Project 沒有來源 fingerprint、Review state 或可驗證的來源身分，不提供「重新連結 DXF」。若未來需要在手動 Project 附加圖面，應另立功能，不屬於 relink。
- `dxf_workflow_status = COMPLETED` 的 Project 只提供來源遺失／無效補救，不允許重新連結改變 Project 工程內容，也不返回 DXF Review。
- `dxf_workflow_status = REVIEW` 的 Project 可以對內容不同的候選重新辨識、比較差異、選擇性恢復人工 state，並返回 DXF Review 繼續修正。
- 使用者介面維持一個「重新連結 DXF」入口，內部依 workflow status 使用兩個不同 contract。

## 2. 現況證據

- 主選單入口：`main.py::_relink_dxf()`。
- Completed relink：raw SHA-256 exact match 可直接更新來源；非 exact 時目前以 Waler／Strut／Brace 數量、唯一幾何配對、座標系統及 Project rows 執行 compatibility gate。
- Paused Review recovery：已有隔離重新辨識、`preserved`／`requires_review`／`disabled` summary、明確接受及原子提交 contract。
- 目前 raw source fingerprint 是整個檔案 bytes 的 SHA-256；CAD 重新儲存可能只因 header、視圖、時間、格式或排列改變而得到不同 hash，不能單獨代表工程內容改變。

## 3. 已確認需求：Completed Project

### 3.1 允許的來源恢復

1. 候選 raw SHA-256 與保存值相同時，直接恢復來源連結。
2. SHA-256 不同時，只允許唯讀的「工程內容等價」驗證。
3. 工程內容等價驗證應忽略非工程差異，例如視角、保存時間及不影響工程內容的檔案序列化差異。
4. 只有來源幾何、角色圖層、必要 block／entity properties 與既有來源身分能安全且唯一對應時，才可視為工程內容等價。
5. 等價通過後只更新來源參照與必要 provenance，不修改 Project rows、人工修改、Solver results 或材料配置。

### 3.2 必須拒絕的情況

- 候選有任何實質工程內容差異。
- 來源構件缺少唯一配對、出現歧義或無法證明與原圖等價。
- 座標系統、尺度或其他定位條件不相容。
- 使用者不得人工略過 compatibility gate 或強制採用。
- 拒絕時顯示具體差異與原因，但不開啟 DXF Review、不修改目前 Project。
- 若確實需要採用修改後圖面，使用者另建 Project 並重新走 DXF 匯入。

## 4. 已確認需求：Paused Review

### 4.1 候選差異

- 內容不同時必須在隔離狀態重新辨識，不直接複製舊 recognition result。
- 新增構件列為 `requires_review`。
- 消失構件列為已移除；相關舊決定分類為 `disabled`。
- 幾何或工程關聯改變的構件列為 `requires_review`。
- 使用者檢視完整差異並明確接受後，才採用候選來源與 recovered Review state，繼續 DXF Review。
- 依可靠工程對應判斷是否為同一張圖，不使用固定差異百分比。缺少可靠共同基準、座標不相容或可能是另一張圖時拒絕。

### 4.2 人工 state 安全恢復

- 材料規格、人工端點、Waler 接觸輸入：唯一重新綁定且 replay 後仍有效才 `preserved`，否則 `requires_review`。
- Source exclusion：只有 exact source identity 對相同 role 仍有效才 `preserved`；geometry-only match 不轉移 exclusion，舊決定改為 `disabled`。
- 雙路支撐：兩支 Strut 都唯一 rebind 且候選仍有同一配對時才 `preserved`，否則 `requires_review`。
- Confirmation：candidate current-state signature 仍相同才 `preserved`，否則移除並 `requires_review`。
- CornerBrace repair：changed-content candidate 不自動轉移 repair geometry 或 reference eligibility；exact subject 仍存在時 `requires_review`，否則 `disabled`。
- 無法安全恢復的 state 必須列出原因，不得靜默消失或套到其他構件。

## 5. 未來提案前仍須完成的技術調查

- 定義「工程內容等價 fingerprint」涵蓋的 DXF entity、block、layer property，以及明確忽略的 volatile header／view fields。
- 確認 handle 改變但幾何與屬性等價時的唯一 rebind 規則，避免重複構件誤配。
- 比較 completed relink 現有 `DxfCompatibilityChecker` 與 paused Review `ReviewRecoveryPlanner` 可共用的 evidence／summary contract，避免第二套 matching logic。
- 確認 completed relink 更新 provenance 後，source-backed export、background、managed copy 與 persisted state 仍一致。
- 修改 paused Review 目前「任一既有 critical member 缺失即拒絕」的規格，使合法刪除能進入 `disabled`／`requires_review` 流程，同時保留 wrong-drawing gate。
- 建立 exact、metadata-only resave、handle churn、少量新增／刪除／修改、錯圖、歧義、取消與 commit failure fixtures。

## 6. 未來 change 的建議範圍

未來 proposal 應聚焦「strengthen DXF relink recovery」，而非新增「更新 Project 來源 DXF」：

- Completed：exact 或工程內容等價的 source recovery。
- Review：內容差異 summary、安全 replay 與回到 Review。
- Manual Project attach、completed Project reconciliation、Project 構件自動增刪及 Solver result migration 均為 Out of Scope。
