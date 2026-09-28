# Proposal

## Why

已暫停且尚未套用至 Project 的 DXF Review，在原始 DXF 被移動、改名或由其他電腦開啟時，目前會因來源不可用而無法繼續，且既有 Relink 明確拒絕 `REVIEW` workflow。第一版需要提供一條範圍明確的安全恢復路徑，讓內容完全相同的 DXF 可以重新連結，同時避免錯誤採用已變更的圖面。

## What Changes

- 當 workflow 為 `REVIEW` 且來源缺失、不可讀或 fingerprint 不符時，提供 Review 專用 Relink 入口。
- 使用 paused Review state 保存的 `source_fingerprint` 驗證使用者所選候選 DXF。
- 候選是有效 DXF 且 SHA-256 完全相同時，更新來源參照、完整保留 paused Review state、維持 `REVIEW`，並從既有 Review 恢復流程繼續工作。
- 使用者選擇候選檔案即代表授權系統在 Exact Match 驗證成功後採用該來源；Exact Match 不再增加第二個確認視窗。
- 候選內容不同時回報 `SOURCE_CONTENT_MISMATCH`，不嘗試重新辨識、物件配對、handle rebinding 或 partial recovery，也不提交任何變更。
- 選檔取消、候選無法讀取、DXF 無效或提交前檔案內容改變時，保留原來源、Review state、Project、Solver 結果及所有 cache。
- **In Scope**：paused `REVIEW` 的候選選擇、DXF／SHA-256 驗證、Exact Match 原子採用、重試／取消、保存與載入回歸測試。
- **Out of Scope**：不同內容 DXF 的 Compatible Source recovery、重新辨識、新舊物件配對、handle rebinding、partial recovery／recovery summary、完成匯入後的既有 Relink、Project geometry 更新、Solver／結果／cache 變更，以及 Project schema 升版。

不同內容 DXF 的安全恢復將作為第二版獨立 change 規劃，避免第一版同時引入來源對應與人工決策失效判斷。

## Capabilities

### New Capabilities

- `paused-dxf-review-source-relink`: 以完全相同的 DXF 來源重新連結 paused Review，並保證內容不同、失敗或取消時零提交。

### Modified Capabilities

- 無。現有 OpenSpec capability inventory 沒有可修改的 DXF Review workflow capability。

## Impact

- 受影響區域預期為 `bracing_optimizer/application/project_service.py` 的 Review Relink use-case／commit contract、`bracing_optimizer/infrastructure/project_persistence.py` 既有的 DXF 檔案驗證與 asset status，以及 `main.py` 的來源選擇與 Review 恢復互動。
- 需補強 `tests/test_project_service.py`、`tests/test_dxf_review_workflow.py`、`tests/test_project_persistence.py` 與 presentation boundary／workflow 測試。
- 不新增外部依賴，不改 DXF recognition、Domain、Solver 或正式 Project geometry contract。
- Architecture 分層不改變；Application 擁有 orchestration 與 commit boundary，Infrastructure 驗證檔案，Presentation 只負責選檔與顯示。Workflow truth 會由「REVIEW 禁止 Relink」改為「REVIEW 可在來源內容完全相同時 Relink」。
