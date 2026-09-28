# Proposal

## Why

BIM 圖塊轉成 DXF 時，角撐圖層可能被後繪構件遮蔽，只留下不足以通過現行自動辨識的局部殘線；角撐尺寸較小，直接放寬 recognizer 或憑空補齊容易把錯誤幾何變成正式工程資料。目前 DXF Review 對已辨識但中心軸錯誤的角撐、以及尚未形成正式構件的角撐來源，都缺少一個以人工確認為前提的專用修補流程。

## What Changes

- 在 DXF Review 的 STEP4 修改工具加入「修補角撐」，只對使用者選取的正式 CornerBrace 或 unresolved `corner_brace` 來源啟用。
- 系統以目標來源殘線作為位置／方向證據，以唯一有效的目標 Waler／Strut 有限幾何建立正式接點；reference fixed length、side 與 topology 只作一致性檢核，不得複製座標、覆寫交點或強迫目標採用參考長度。
- 第一版 reference 分為 automatic recognized primary 與 manual repaired secondary。每個合法候選至少需要一支來源與 connection 有效的 automatic primary；只有 provenance 完整、已明確採用、目前 confirmation／來源／connection 仍有效且不是 `requires_review` 的 repaired CornerBrace 才能補充為 secondary，不得形成 repaired-to-repaired 的無限制推測鏈。
- 只有通過全部 hard eligibility 的候選可進入 Preview。唯一候選仍需使用者明確採用；多個非等價但各自完整的候選可由使用者選擇；缺少必要 evidence 的 hypotheses 只產生拒絕原因，不得包裝成可 Apply 候選。
- 採用修補後，由 `DXFReviewWorkflow` 原子更新或建立正式 CornerBrace，保留目標 DXF provenance，並重建角撐關聯、Strut 角撐衍生長度、candidate points、validation 與 confirmation 狀態。
- 已採用修補可隨 paused Review 保存及在相同來源上安全重播；來源內容不同時不得把修補決策依一般幾何配對靜默轉移到另一來源。
- 既有可靠 CornerBrace 自動辨識及中心軸延伸維持不變；本 change 不修改自動 recognizer 的接受門檻。

## Capabilities

### New Capabilities

- `dxf-corner-brace-repair-tool`: 定義被遮蔽或中心軸錯誤之角撐的人工輔助候選、預覽、採用、失敗與重播行為。

### Modified Capabilities

- `dxf-corner-brace-centerline-extension`: 將使用者採用的 repaired axis 納入既有 Waler 內線／Strut 中心線端點校正與下游角撐關聯基準。
- `paused-dxf-review-source-relink`: 定義角撐修補決策在 Exact Match resume 與 content-changed compatible recovery 中的保存及失效語意。

## Scope

### In Scope

- STEP4 修改工具的 CornerBrace 專用入口、候選清單、幾何預覽、明確採用與取消。
- 已辨識但工程軸錯誤的 CornerBrace 修補。
- 具有 exact `corner_brace` source identity、target residual geometry、可靠方向 hypothesis、唯一有限 Waler／Strut 關係與有效 primary reference，但尚未形成正式 CornerBrace 的 unresolved 來源修補；建立前仍須通過既有 CornerBrace validation 並由使用者明確採用。
- 目標殘線、相鄰已驗證 CornerBrace、有限 Waler／Strut 幾何的保守證據組合及歧義處理。
- 修補採用後的關聯、衍生長度、validation、confirmation invalidation 與 paused Review persistence。
- CB71 類錯軸案例、殘線案例、證據不足與多解案例的 regression coverage。

### Out of Scope

- 放寬或重寫一般 CornerBrace automatic recognition、BIM block recognition 或既有 tolerance。
- 自動批次修補所有角撐、無人確認直接採用、或只因距離最近就吸附到 Waler／Strut。
- 從完全沒有目標 source geometry 的位置創造角撐。
- 讓 manual repaired CornerBrace 單獨支持下一支 repaired CornerBrace，或以 repaired reference chain 取代 automatic primary evidence。
- 修改一般 Brace、Strut、Waler recognition、Waler contact 位移公式或 Solver。
- 將 CornerBrace 加入 `ProjectDataModel` schema、修改 Main 編輯能力或新增 CAD/LSP 指令。
- 修補原始 DXF 檔案、回寫 BIM 圖塊，或建立通用 Guided Recognition framework。

## Impact

- **Architecture:** 沿用 `DXFImportDialog → DXFReviewWorkflow → pure DXF operation → DXF models/geometry` 的既有方向；新增小型 pure repair planning operation，不建立第二份正式 Review truth。
- **Domain:** 不改變 Project Domain。CornerBrace 仍是 DXF Review 中的工程輔助構件，其正式端點為 Waler 內線與 Strut 中心線的有效接點。
- **Solver:** 無影響；不修改 scoring、candidate generation、search 或 Solver input contract。
- **Workflow:** STEP4 增加 staged preview／explicit adoption；採用後才修改 live Review state，Pause／Resume 保存該人工決策，完成 Review 前不修改 Project。
- **Persistence:** 預期沿用現有 Review state version 與 Project schema，以既有 manual-decision serialization 擴充角撐修補資料；不新增 Project migration。若實作前證明既有 version 無法相容表達，必須停止並回到 OpenSpec 修正，不得自行升級 schema。
- **Affected modules:** `dxf_import/dialog.py`、`dxf_import/review_workflow.py`、新增的小型 CornerBrace repair pure operation、`dxf_import/models.py`／manual replay 邊界、角撐 association／validation 與其測試；長期完成後更新 `docs/WORKFLOW.md`，若模組責任清單改變則同步 `docs/ARCHITECTURE.md`。
