# Design

## 閱讀導航

- **P0 現在必讀**：Decision 1「共用術語集中在既有 Presentation label boundary」、Decision 2「完整句子留在最窄責任邊界」、Architecture Alignment。
- **P1 實作前閱讀**：Decision 3「以聚焦測試鎖定中文介面與行為不變」；`specs/dxf-corner-brace-repair-tool/spec.md` 的新增 Requirement。
- **P2 條件式閱讀**：只有修改 planner diagnostics／exceptions 時才需閱讀 `dxf_import/corner_brace_repair.py`；只有調整視窗與欄位時才需閱讀 `dxf_import/dialog.py` 的 CornerBrace repair methods。
- **可先跳過**：recognition、geometry transfer、Pause／Resume replay 與 Solver 文件；這些 contract 不變。

## 方案摘要

沿用現有候選 DTO 與 workflow，並擴充既有 `bracing_optimizer/presentation/field_labels.py` 作為穩定、可重複術語的 Presentation label boundary。角色與移植方式由共用 helper 轉為中文；完整的視窗說明與操作句子留在 `dxf_import/dialog.py`，repair-specific diagnostics／exceptions 留在其既有產生位置改為中文。UI 仍只讀候選資料，不重新計算 compatibility、ranking 或 eligibility。

```text
CornerBrace repair planner（工程 truth 不變）
                ↓ candidate DTO / diagnostics
共用 Presentation labels ──→ 角色與移植方式
                ↓
DXF dialog 就地文案 ───────→ 說明、提示與操作句子
                ↓
繁體中文預覽、拒絕原因與錯誤訊息
```

本 change 中，「顯示轉換」只把內部識別值轉為人可讀中文；「工程 contract」則指 candidate DTO、enum 值、幾何、排序與提交時使用的原始資料。

## 決策對照

| Decision | 對應規格 | 對應工作 |
|---|---|---|
| 1. 共用術語集中在既有 Presentation label boundary | 「顯示移植方式」及「重複概念使用一致術語」 | 擴充共用 label helper、讓 repair UI 消費同一術語；驗證原始 candidate 值未改 |
| 2. 完整句子留在最窄責任邊界 | 「預覽合法候選」及「修補不可執行或提交失敗」 | 翻譯 dialog 文案與 repair-specific diagnostics／exceptions，不建立全域整句字典 |
| 3. 聚焦測試同時鎖定中文與行為不變 | 全部新增 Scenario | 擴充 layout／repair tests，執行相關回歸測試 |

## Context

動機見 `proposal.md` 的 Why。現有 `dxf_import/dialog.py` 已使用中文視窗標題與按鈕，但說明文字、Treeview 欄位、detail 內容及 `same_side`／`mirrored` 顯示仍為英文；`dxf_import/corner_brace_repair.py` 產生的 diagnostics 與 `DXFImportError` 也會由 dialog 原樣呈現。專案已有 `bracing_optimizer/presentation/field_labels.py` 集中 table column、DXF engineering field、recognition method 與 entity type 的顯示名稱，因此新增穩定術語應沿用此 boundary，而不是在 repair dialog 建立另一份 mapping。

架構上，`dialog.py` 是 DXF Presentation；`review_workflow.py` 擁有 session 與 commit；`corner_brace_repair.py` 擁有 pure planning、hard filtering 與 staged rebuild。這次不改後兩者的工程責任或 dependency direction。

## Goals / Non-Goals

**Goals:**

- 讓角撐修補流程中實際呈現給使用者的文字一致使用繁體中文。
- 讓角色與修補移植方式等可重複術語沿用既有 Presentation label boundary，供其他 Presentation consumer 逐步重用。
- 保持候選 DTO 與 persistence 使用既有英文識別值，避免翻譯成為第二份狀態 truth。
- 讓測試能發現主要英文標籤回歸，並持續保證 UI 不承接工程計算。

**Non-Goals:**

- 不新增通用翻譯資源系統或 runtime locale 切換。
- 不把既有 repair-specific diagnostics 改造成 diagnostic code、typed payload 或新的 cross-layer contract。
- 不一次重構主畫面或 DXF 匯入介面內所有既有角色顯示程式。
- 不翻譯 Python API、資料欄位、enum、selection source 或 serialized payload。
- 不改 CornerBrace repair 的工程規則、流程狀態或其他 DXF Review 介面。

## Decisions

### Decision 1：共用術語集中在既有 Presentation label boundary

在既有 `bracing_optimizer/presentation/field_labels.py` 新增小型、具名且純顯示用途的共用術語 mapping／helper，至少涵蓋角色 `corner_brace → 角撐`，以及移植方式 `same_side → 同側移植`、`mirrored → 鏡射移植`。`dxf_import/dialog.py` 的角撐修補表格與 detail 透過 helper 取得顯示值；候選選取與提交仍傳遞原 candidate ID 與原始 enum 值。未知值採可診斷 fallback，例如顯示原值，不靜默誤譯為其中一個已知模式。

理由是 `field_labels.py` 已是主畫面與 DXF dialog 共用的 Presentation 翻譯 boundary。把穩定術語放在此處，可避免 repair dialog 產生新的重複對照，也讓其他介面未來能逐步採用；內部值仍參與 provenance、replay 與驗證，不得改名。

拒絕方案一：直接將 DTO／serialized enum 改為中文。此方案會擴大 persistence 與 backward compatibility 範圍，且沒有使用者價值上的必要性。

拒絕方案二：只在 repair dialog 內新增 mapping。它雖能完成畫面中文化，但會延續同一術語在多個畫面各自定義的問題。

### Decision 2：完整句子留在最窄責任邊界

純 UI 的 disabled reason、視窗說明與操作引導留在 `dialog.py` 中文化，不放進共用 labels。由 repair planner 或 apply operation 產生、且語意專屬於 CornerBrace repair 的 diagnostics／exceptions，在 `corner_brace_repair.py` 原產生位置改成繁體中文，讓所有既有呼叫端取得一致訊息，避免 UI 依完整英文句子建立脆弱的翻譯表。

本 change 將這些既有 diagnostics 視為人類可讀文字，而非穩定的 machine-readable contract，因此直接修改文字屬於現況相容性修改，不另建 structured diagnostic code。實作前必須確認 production code 沒有以完整訊息文字控制分支；測試可驗證預期文案，但不得讓工程行為依賴特定中文或英文句子。若未來同一診斷需要被多個 Presentation consumer、多語系資源或程式邏輯穩定消費，再以獨立 change 設計 code、parameters 與 rendering boundary。

若實作發現某訊息來自共用 validation 且同時服務其他流程，則不直接改寫共用來源；改在角撐修補的呈現邊界處理，避免本 change 擴張到其他介面。訊息文字不是 eligibility input，不得被工程邏輯解析。

拒絕方案：在 dialog 建立英文整句對繁中整句的大型字典。它容易隨診斷細節變動而漏翻，也會讓 Presentation 必須理解 planner 的所有拒絕分支。

延後方案：現在就將所有 repair diagnostics 改造成 structured diagnostic objects。現況只有既有角撐修補路徑顯示這些文字，導入新 contract 會擴大 models、workflow、persistence／replay 與測試範圍，超出本次中文化所需。

### Decision 3：以聚焦測試鎖定中文介面與行為不變

擴充既有 layout/source-inspection tests，檢查角撐修補視窗的關鍵標籤、表頭、提示與 detail 使用預期中文，並確認 detail handler 仍只讀 candidate DTO。對 planner diagnostics／exceptions 的既有行為測試只更新顯示文字 assertion，必要時補充候選數量、ID、排序或幾何未因中文化改變的 assertion；另以來源搜尋或針對性測試確認 production code 不解析完整診斷句子。

不以「整個檔案不得出現英文字母」作驗收，因構件 ID、單位、程式識別字與部分工程縮寫需保留；測試應鎖定使用者可見的已知英文 UI 詞句及中文替代內容。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 Architecture 本身**。

- **Shared Presentation labels (`bracing_optimizer/presentation/field_labels.py`)**：擁有跨 Presentation consumer 可重用的穩定術語與純顯示 helper。
- **DXF Presentation (`dxf_import/dialog.py`)**：擁有角撐修補的完整 UI 句子，並消費共用術語 helper。
- **Review pure operation (`dxf_import/corner_brace_repair.py`)**：只調整專屬 diagnostics／exception 的人類可讀文字，不改 planning、eligibility 或 rebuild。
- **Dependency direction**：維持 `DXF Presentation → DXFReviewWorkflow → Review Pure Operations → Models / Geometry`。
- **Single source of truth**：候選 DTO、原始 transfer mode、candidate ID 與 workflow state 仍是唯一工程 truth；`field_labels.py` 是共用中文術語的單一顯示來源，中文顯示字串不回寫 DTO、不進入 persistence，也不參與判斷。
- **旁路一致性**：Preview、無候選 warning 與 commit error 都消費既有 workflow／planner 結果，不新增另一套 manual editing、diagnostic 或 summary 邏輯。

## Backward Compatibility / Persistence

不修改 Review state version、Project schema、manual override payload 或任何 serialized key/value。既有 paused project、legacy version 2 repair payload 與 current template-transfer payload 均照原 contract 載入；差異只存在於執行時顯示文字。無 migration。

## Risks / Trade-offs

- **[Risk] repair-specific diagnostics 未完整盤點，仍殘留英文** → 以來源搜尋加上無候選、stale plan、invalid candidate 等代表性測試覆蓋實際 UI 路徑。
- **[Risk] 現有程式以完整英文 diagnostic 作為隱性控制 contract** → 實作前搜尋 diagnostics 的比較、substring 與 suffix 判斷；若 production logic 確實依賴文案，停止直接改字並回到 OpenSpec 評估 structured diagnostic boundary，不以同步替換成中文字串掩蓋依賴。
- **[Risk] 共用 labels 逐漸收納完整句子而變成難維護的翻譯倉庫** → 僅接受穩定、可重複的名詞或短狀態名稱；含上下文的句子維持在擁有該互動的 UI／operation boundary。
- **[Risk] 將工程 ID 或內部值誤當文案翻譯** → 限定 mapping 僅輸出 display label，提交與 persistence 繼續使用原 DTO 欄位。
- **[Risk] 中文表頭較寬造成 Treeview 擠壓** → 實作時依既有視窗寬度調整欄寬，並執行 layout 測試；不藉此重做整個視窗。
- **[Trade-off] 不導入通用 i18n framework** → 本次改動較小且符合單一繁中桌面應用現況，但未提供未來多語切換能力。

## Migration Plan

1. 擴充既有共用 Presentation labels，加入角色與修補移植方式的顯示 helper。
2. 更新角撐修補專屬文案，並讓表格與 detail 消費共用術語。
3. 執行聚焦 label、layout 與 repair tests，再依影響範圍執行 DXF Review 相關回歸測試。
4. 此變更無資料 migration；若需 rollback，可回復文案與 mapping，既有專案資料不受影響。
