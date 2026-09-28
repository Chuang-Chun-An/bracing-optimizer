# Proposal

## Why

Phase 1 只能在候選 DXF 的 SHA-256 完全相同時恢復 paused Review；只要圖檔經另存、圖層或 handle 改變、或新增工程物件，即使仍屬同一工程，使用者也只能放棄既有 Review 狀態。Phase 2 需要在不誤套人工決策的前提下，辨識內容已變更但仍可證明相容的來源，並讓使用者先看見 recovery 影響再決定是否採用。

## What Changes

- 保留既有 Exact Match 快速路徑；SHA-256 相同時仍直接採用，不增加確認視窗或重新辨識。
- 當候選為有效 DXF 但 fingerprint 不同時，提供 paused Review 專用的 staged compatible recovery，而不是直接回報第一版不支援。
- 以候選重新辨識結果和 saved Review state 建立一對一構件配對；所有既有 Waler／Strut／Brace 必須能以來源 identity 或既有幾何容差唯一配對。候選可新增構件，但缺少或歧義的既有關鍵構件會拒絕 recovery。
- 以候選辨識結果作為新的 DXF Review 基底，重新計算 association 與 validation；不得把舊候選點、舊 association 或舊辨識結果直接複製到新來源。
- 對既有 layer classification、coordinate system、import mode、人工端點、材料規格、Waler 接觸輸入、source exclusion、雙路支撐 decision 與 confirmation 逐項判斷能否安全保留、需要重新確認或必須停用。
- 在提交前顯示 recovery summary，至少分為 `preserved`、`requires_review`、`disabled`；Compatible Source 必須取得使用者明確接受，拒絕或取消均保持零提交。
- 接受後重新驗證候選 fingerprint 與 paused Review base state，再原子採用 recovered Review state；workflow 維持 `REVIEW`，Project geometry、Solver results、Solver memory 與 Solver candidate cache 不變。
- 內容已改變時淘汰舊的 same-session DXF `world_result` cache，改以候選辨識結果建立新的 Review session；Relink 本身仍不更新 managed DXF，Save 才沿用既有 transaction 保存。
- 沿用既有 Project schema 與 Review state version，不新增 migration。

**In Scope**：paused `REVIEW` 的 changed-content candidate recognition、關鍵構件 compatibility gate、來源 re-binding、人工決策 selective recovery、recovery summary、明確接受／拒絕、原子 commit／rollback、Save／Load 與 regression tests。

**Out of Scope**：任意不同工程圖的強制恢復、缺少或歧義既有 Waler／Strut／Brace 時的人工 mapping UI、修改現有幾何 matching tolerance、完成匯入後的既有 Relink、Project geometry apply、Solver／scoring 變更、Project schema 升版，以及建立第二套 DXF Editor。

## Capabilities

### New Capabilities

- 無。

### Modified Capabilities

- `paused-dxf-review-source-relink`: 在既有 Exact Match 行為之外，新增內容不同但關鍵構件可唯一配對時的 staged partial recovery、決策失效摘要與使用者明確接受流程。

## Impact

- `bracing_optimizer/application/project_service.py`：擴充 paused Review Relink evaluation／commit contract，處理 compatible plan、base-state token 與 commit-time fingerprint revalidation。
- `dxf_import/`：新增或擴充純資料 recovery planning，重用現有 recognition、manual replay、confirmation signature 與 double-support identity；不把 matching 邏輯放進 Tkinter。
- `dxf_import/dialog.py` 與 `main.py`：提供 staged recovery 與 summary／accept interaction，沿用同一個 DXF Review workspace，不建立平行 Editor。
- `bracing_optimizer/infrastructure/project_persistence.py`：只在必要時抽取或重用既有 geometry match primitive；不改 managed-copy 或 Project schema contract。
- 測試將涵蓋配對成功、增加候選構件、缺少／歧義關鍵構件、各類 decision recovery、拒絕／取消、stale commit、rollback、Save／Load 與 Exact Match regression。
- 不改 Architecture、Domain 或 Solver truth；會改變 paused Review Relink 的 Workflow truth，因此實作完成後需更新 `docs/WORKFLOW.md`。
