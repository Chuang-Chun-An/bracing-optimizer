# Design

## Context

See [proposal.md](./proposal.md) for motivation and [the capability spec](./specs/paused-dxf-review-source-relink/spec.md) for observable behavior.

目前 `main.py::_relink_dxf()` 在 workflow 為 `REVIEW` 時直接拒絕操作；`_review_resume_source()` 又要求來源存在，且保存的 fingerprint 必須與檔案一致，因此同一份 DXF 被移動、改名或換電腦後會形成 resume dead-end。

既有完成匯入後 Relink 由 `ProjectService.try_exact_relink()`／`relink_dxf()` 協調，但 Exact 判定優先使用 `dxf_asset` 或 runtime report 的 hash，而內容不同時會進入依賴 Project rows 的 geometry compatibility。Paused Review 尚未套用至 Project，不能直接沿用這套真相與 fallback。

Paused Review 已將 `source_path`、`source_fingerprint` 與完整 Review state 保存於 `dxf_import_state`。第一版只接受 fingerprint 完全相同的來源，因此不需要重新辨識，也不需要建立 handle rebinding 或 partial recovery 機制。

## Goals / Non-Goals

**Goals:**

- 以 paused Review state 的 `source_fingerprint` 作為 Exact Match 的 single source of truth。
- 在 Application 集中 workflow guard、候選驗證與 commit contract。
- 候選完全相同時只替換來源參照，保證其餘 Review state 位元等價地保留。
- 內容不同、驗證失敗或取消時保持零副作用。
- 沿用現有 asset status、Save transaction 與 Review resume path。

**Non-Goals:**

- 不支援不同 hash 的 Compatible Source、geometry matching 或 recovery summary。
- 不執行 DXF recognition、association rebuild、manual override replay 或 confirmation pruning。
- 不修改既有 `COMPLETED`／legacy Relink。
- 不修改 ProjectData、ProjectResult、Solver 或任何 Solver cache。
- 不新增 Project schema、Review state version 或 UI step persistence。

## Architecture Alignment

本 change 沿用現有 Architecture，不引入新的 layer 或 dependency direction：

```text
Presentation (main.py)
    選擇候選、顯示結果、採用 Application result、恢復 Review
                    ↓
Application (ProjectService)
    REVIEW guard、Exact evaluation、commit/stale guard
                    ↓ injected existing dependency
Infrastructure (DxfAssetManager)
    檔案存在性、DXF validity、SHA-256、asset status
```

- Presentation 不計算 hash，也不判斷候選是否相同。
- Application 不依賴 Tkinter，並且只回傳 staged／committed adoption data，不直接修改 Main state。
- Infrastructure 不解讀 Review 工程語意；它只提供既有檔案驗證能力。
- Domain、Algorithms 與 `dxf_import` recognition subsystem 不受影響。
- `dxf_import_state.source_fingerprint` 是 paused Review 來源內容的唯一真相；`dxf_asset.sha256` 與 runtime report 只描述管理副本／目前可用來源，不得覆蓋它。

## Decisions

### 1. 第一版只有 Exact Match，不建立 compatibility adapter

`ProjectService` 增加小型的 paused Review Relink request／status／evaluation／commit result contract。Application 結果只需要表達：

- `EXACT_MATCH`：可提交
- `SOURCE_CONTENT_MISMATCH`：有效 DXF，但內容不同，不可提交
- `VALIDATION_FAILED`：候選或保存狀態無法完成驗證

檔案選擇器取消發生在 Application 呼叫之前，因此不建立虛假的 `VALIDATION_CANCELLED` application result。

現有 `DxfAssetManager.file_info()` 已能檢查檔案、解析 DXF 並計算 SHA-256，直接注入 `ProjectService` 重用即可；不新增 DXF recovery adapter、port 或辨識 workflow。

**Rejected alternatives：**

- 移除 Main 的 REVIEW guard 後直接呼叫既有 Project Relink：會在 hash 不同時進入 Project geometry compatibility，語意錯誤。
- 為未來第二版預先建立 generic compatibility port：第一版沒有 consumer，會增加沒有行為價值的 abstraction。
- 不同 hash 時嘗試保留「看起來相同」的 state：現有機制不足以安全處理 exclusions、雙路支撐 decisions 與 confirmations。

### 2. Exact 判定只讀 saved Review fingerprint

Evaluation 先確認：

1. workflow 是 `REVIEW`。
2. saved Review state 存在。
3. `source_fingerprint` 是非空 SHA-256 值。
4. 候選可由既有 DXF file validator 正常讀取。

候選 SHA-256 正規化大小寫後必須與 saved Review fingerprint 完全相同。不得 fallback 到 `existing_asset.sha256`、active source hash、檔名、路徑、檔案大小或修改時間。

Exact staged state 是 saved Review state 的 deep copy，只將 `source_path` 改為候選的 resolved path；`source_fingerprint` 保持相同的正規化值。converted data、layer classification、coordinate system、manual overrides、exclusions、double-support decisions、confirmations、validation messages 與 pending state 均不重算、不篩除。

**原因：** 相同 bytes 足以證明 DXF handles 與所有辨識輸入相同，因此任何重新辨識都只會增加回歸風險。

### 3. 選檔是 Exact Match 的採用授權

Review Relink 沒有 recovery choices：驗證成功只代表「同一份檔案的新位置」。使用者在檔案選擇器中選擇候選後，Application 驗證成功即可提交，不顯示第二個 Yes／No 視窗。

UI 行為為：

```text
選擇檔案
  ├─ Cancel → 不呼叫 Application、不修改狀態
  └─ 選定 → evaluate
               ├─ mismatch / failed → 顯示原因，重試或取消
               └─ exact → commit → atomic UI adoption → resume Review
```

`SOURCE_CONTENT_MISMATCH` 的訊息明確說明第一版只支援內容完全相同的 DXF，不將它誤稱為解析失敗，也不自動開始新的 Import。

### 4. Evaluation 與 commit 分離，但不插入額外使用者決策

Evaluation 是 copy-on-write，只產生 immutable success plan 或非成功結果。Exact plan 至少保存：

- candidate resolved path 與 fingerprint
- base Review state token
- staged relinked Review state

UI 收到 Exact plan 後立即呼叫 Application commit。Commit 再次執行 candidate file validation／hash，並確認 current workflow 仍為 `REVIEW`、current Review state token 仍等於 base token。任何差異都回傳 failure，且不提供可採用 state。

這個兩階段是 internal transaction guard，不是第二個使用者確認。它避免候選檔在 evaluation 與採用之間被外部程式替換，也防止 stale plan 蓋過較新的 Review state。

State token 由 Application 對 normalized saved Review state 做 deterministic digest；Presentation 不自行計算或解讀。

### 5. Main 以單一 adoption helper 原子更新 runtime state

成功 commit result 包含完整 relinked Review state、accepted runtime asset report、workflow `REVIEW` 與 dirty reason。Main 在採用前保存受影響欄位，集中完成：

- `dxf_last_import_debug` → relinked state
- `dxf_asset_status_report` → candidate accepted／pending-save report
- `last_dxf_compatibility_report` → `None`
- project dirty → `True`

因候選 fingerprint 完全相同，現有 `dxf_review_session.world_result` 仍對同一內容有效，成功時可保留；失敗與取消必須保留。正式 `dxf_asset` metadata 與 managed copy 不在 Relink evaluation／commit 時覆寫，等使用者 Save 時再由既有 transaction 更新。

若 adoption 或必要 UI refresh 發生例外，Main 回復上述欄位與原 dirty 狀態。成功後呼叫既有 `_continue_dxf_import()`／`_run_dxf_review_dialog(..., resume_review=True)`，不得走 completion path。

### 6. 兩個 UI 入口共用同一 Application flow

`_relink_dxf()` 遇到 `REVIEW` 時改路由至 paused Review Exact Relink；`_review_resume_source()` 因來源缺失或 fingerprint 不符而阻擋時，也提供進入同一 flow 的選項。兩個入口不得各自實作 hash 或 state update。

候選 mismatch 或 validation failure 後，UI 只負責顯示 Application message 並詢問重試／取消。重試必須重新從原 saved Review state 開始。

### 7. Persistence 沿用現行 schema

成功 adoption 只讓 Project 成為 dirty。下一次 Save 仍由既有 managed-copy transaction 將已驗證候選保存到 `source/source.dxf`，並更新 `dxf_asset` metadata；重新載入後仍 hydration 為 `REVIEW`。

不新增 schema 欄位或 migration。舊 paused Review state 若沒有 fingerprint，第一版無法證明不同路徑的候選相同，因此以 `VALIDATION_FAILED` 保守拒絕；不修改舊 state，也不猜測。

## State Ownership and Commit Contract

| State | Evaluation | Commit／adoption | Rule |
|---|---|---|---|
| Current paused Review state | Application 唯讀並建立 token | Application 驗證 token，Main 採用 deep copy | 不可原地修改 |
| Candidate file/fingerprint | Infrastructure transient validation | commit 前重新驗證 | mismatch／failure 零提交 |
| Re-linked Review state | Application staged copy | Main 單次採用 | 除 `source_path` 外保持原值 |
| Same-session Review cache | 不讀寫 | fingerprint 相同故保留 | failure/cancel 亦保留 |
| Managed DXF copy | 不讀寫 | 後續 Save transaction 更新 | Relink 不提前覆寫 |
| ProjectData/ProjectResult/Solver | 不讀寫 | 不讀寫 | 完全不參與 |

## Risks / Trade-offs

- **[同一工程圖另存後 metadata 改變，hash 不同]** → 第一版會拒絕，即使幾何看似相同；這是刻意的安全限制，第二版另行設計。
- **[候選在 evaluation 後被外部修改]** → commit 前重新解析與 hash；差異即失敗且不採用。
- **[saved Review 缺少 fingerprint]** → 不以較弱證據猜測，回報 validation failure 並保留原狀。
- **[Main adoption 途中 UI 例外]** → 使用集中 helper 與 snapshot rollback，測試所有受影響 runtime 欄位。
- **[成功後 managed copy 仍是舊位置／內容]** → runtime report 標示 pending save；既有 Save transaction 才是持久化 commit boundary。

## Migration Plan

1. 增加 Application Exact evaluation／commit contract 與單元測試。
2. 接上 Main 的 Review Relink 與 resume-dead-end 入口，補零副作用及 rollback 測試。
3. 補成功後 Save／Load round trip 與非 Review Relink regression。
4. 實作驗證完成後更新 `docs/WORKFLOW.md` 的第一版現況；第二版 Compatible Source recovery 保留為明確待辦，不寫成已成立行為。

Rollback 可直接移除新入口與 Application methods；成功保存的資料仍使用現行 Review state／Project schema，不需要資料 downgrade。
