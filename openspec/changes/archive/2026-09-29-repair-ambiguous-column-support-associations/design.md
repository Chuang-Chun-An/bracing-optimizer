# Design

## 閱讀導航

### 現在必讀

- Decision 1：候選清單直接重用自動柱關聯的有限軸線與容差計算。
- Decision 2：人工選擇覆寫該柱自動最近關聯；關聯紀錄與禁止點是衍生結果。
- Decision 2 的診斷段落：有效決策只解除它處理的距離歧義，撤銷與失效恢復未解決狀態。
- Decision 3：修補預覽以 revision 與來源身份防止過期提交。
- Decision 4：同來源保存／重建與不同來源恢復的安全邊界。

### 條件式閱讀

- 修改 `dialog.py` 時閱讀 Decision 5；畫面只投影 workflow 的候選與預覽。
- 修改雙路候選流程時閱讀 Decision 1、Decision 2 與「Risks / Trade-offs」；Column 修補不能替暫定雙路建立正式共享。

### 可先跳過

- Solver 搜尋、Waler contact face 與 CornerBrace repair template 的設計細節不在本 change。

## 方案摘要

```text
目前 WCS Review geometry
  → 共用 Column-to-Strut eligible option 計算
  → 雙候選修補 preview（Column、兩支 Strut、距離、stations）
  → 使用者明確選一支或兩支
  → Workflow 驗證並保存 source-bound decision
  → 覆寫該柱自動最近關聯，共用 rebuild 產生唯一 active association set
  → 移除該柱的未解決距離歧義，其他 problems 保留
  → Project rows 沿用現有轉換
```

「決策」是使用者確認哪些實體支撐要避開這根柱；「關聯紀錄」是決策在當前幾何上的投影；「禁止點」是各 Strut 的 Column station。這三者分開，才能避免端點改動後沿用舊站點。

## 決策對照

| Decision | 對應 Spec Requirement | 主要 Tasks |
| --- | --- | --- |
| 1. 共用候選計算與雙候選門檻 | 只讓明確的雙候選中間柱進入修補 | 1、2 |
| 2. Review 決策覆寫自動結果，並局部解除歧義 | 人工選擇決定各支撐的禁止點；有效人工決策解除原關聯歧義；修補不得改變一般關聯與雙路資格 | 2、3 |
| 3. Revision-bound staged preview／commit | 採用與撤銷必須可預覽且原子提交 | 3、4 |
| 4. Source-bound replay 與失效 | 人工決策須安全重建與續作 | 5 |
| 5. 修改工具的專用入口 | 只讓明確的雙候選中間柱進入修補；採用與撤銷必須可預覽且原子提交 | 4 |

## Context

動機見 `proposal.md` 的 Why。`associate_components_to_struts()` 已用 WCS Column reference、有限 Strut 投影與 section-aware tolerance 列舉選項；非正式雙路時只取最近一支，前兩支距離差 `<= 25 mm` 時發出 `AMBIGUOUS_COMPONENT_ASSOCIATION` warning。相同 code 也用於一支 Strut 同時參與多個 accepted pair，不可用 message text 或 code 單獨識別修補資格。Y29 C25 目前最近 S20 約 498.5 mm，S35 約 501.5 mm。現行 warning severity 不計入 `blocking_error_count`，但會列入完成匯入前的未解決警告確認；本 change 解除的是該柱的未解決 diagnostic，不變更全域 severity／完成門檻政策。

`rebuild_component_associations()` 會清掉舊關聯與 association messages，再由目前 geometry 重建；直接改 `Strut.column_positions` 或 `ComponentAssociation` 會在下一次重建消失。`DXFReviewWorkflow.world_result` 是正式 WCS Review state；`dialog.py` 僅持有 snapshot 與 draft。`to_project_rows()` 已把每支 Strut 的 `associated_columns`／`column_positions` 轉成現有 Project 欄位。

## Goals / Non-Goals

**Goals:**

- 用相同幾何判定建立警告、修補候選與 commit revalidation，避免三套結果漂移。
- 讓一根柱在兩支一般 Struts 上各有獨立 station；單選可明確覆蓋自動最近選擇。
- 有效決策清除該柱的未解決距離歧義，不觸及其他問題；撤銷或失效時恢復相應狀態。
- 在 Review mutation、同來源續作與座標切換後安全重建；失效時可被看見且不留下舊禁止點。

**Non-Goals:**

- 不把 Column proximity 變成雙路支撐資格，也不修改既有雙路群組的共享語意。
- 不開放無警告 Column 對任意 Strut 的人工連線。
- 不新建 Project 欄位或修改 Solver legality；Project 仍只消費 Strut station。

## Decisions

### Decision 1：單一 pure 候選計算服務同時提供自動關聯與修補資格

在 `dxf_import/candidate_points.py` 抽取小型 WCS Column option 計算，回傳每一有效 Strut 的 identity、有限 station、projection、距離與使用的 tolerance。既有自動關聯與新修補 planner 都讀這些 options。距離排序只供判斷前兩名；若第三名也與最近距離相差 `<= ambiguous_connection_delta_mm`，標示多候選但不提供雙候選 Apply。已 accepted 並共同共享該 Column 的雙路 pair 從待修清單排除；不得把 warning code 當唯一 eligibility 來源。

保留現有 `_column_association_tolerance` 的數值和含等號比較。候選包含兩支，但自動模式仍使用既有最近一支／正式雙路共享邏輯。多候選不新增工程尺寸門檻。

**Rejected alternatives:** 解析警告文字找 S20／S35，因文字會改、且同一 code 有其他成因；另寫畫面最近距離演算法，因會與正式重建分歧。

### Decision 2：Review 決策為 single source of truth，結果以一次 rebuild 產生

新增小型 immutable `ColumnAssociationDecision`，記錄 Column source identity、兩支候選 Strut source identities、選中 identity set 與當次 source fingerprint；顯示 ID 只供呈現。放在 `DXFReviewWorkflow` 的決策集合，並以 Review state version 2 的 optional `column_association_decisions` payload 保存。這是 DXF Review 子狀態，不修改 Project persistence schema；舊 payload 缺欄位表示沒有人工決策。候選與決策都必須能在同一來源內以一對一 source identity 對應 current Column／Struts，不用 StrutID 或距離在新辨識順序中重新猜測。

Workflow 在自動 recognition、double-support decision 與人工決策都確定後，呼叫單一 association rebuild。Rebuild 對未修柱維持既有結果；對有效人工決策，**以選中 options 完整取代該 Column 的自動最近 assignment**，先清除該 Column 在所有非共享 Struts 的舊 association／station，再僅由選中 options 建立 active `ComponentAssociation` set，重建每支 `associated_columns`／`column_positions`。不能在既有 nearest records 上追加人工單選；S20 自動最近而人工只選 S35 時，C25 只能留在 S35，active association 恰好一筆。Column 的既有 singular `associated_strut_id` 保持一個 primary 供舊 UI／序列化相容，並明示全部關聯以 `component_associations` 為準。若單選不是最近支撐，primary 必須是被選者；雙選時 primary 可沿既有最近支撐排序作顯示，但不得控制另一支的禁止點。`Beam` 路徑不變。

診斷與關聯由同一 rebuild 決定。有效人工決策只抑制該 Column 的「兩候選距離相近」未解決 warning，可另產生 info 級「已人工判定」provenance；不得按 `AMBIGUOUS_COMPONENT_ASSOCIATION` code 全域過濾，因多 accepted groups 也用同碼。其他 Waler、雙路、source identity 與無關 problems 原樣保留。Workflow 的完成狀態與警告計數從重建後的 active messages 計算，所以該 warning 不再出現於完成前確認；不改既有 `error`／`critical` 阻擋規則。撤銷時移除 decision 並從目前 geometry 重建 nearest 與 warning。決策失效時停用其效果，重建一般自動關聯與仍存在的距離 warning，同時給出 `requires_review`，不得顯示「已解決」或保留舊人工 station。

**Rejected alternatives:** 在 nearest 結果上追加人工單選，因會意外留下兩支禁止點；全域刪除同碼 warning，因會遮蔽其他歧義；直接保存 station／覆寫 Project row，因幾何與方向變更後會過期；把兩支塞入 `SharedLayoutGroup`，因會錯誤施加共用材料排列與 Jack 語意。

### Decision 3：修補 session 只預覽，Workflow 再驗證後原子採用

純規劃操作從 `world_result` 與當前決策產生 `ColumnAssociationRepairPlan`，包含 Column 與兩支 option、幾何顯示資料、source identities、Review revision、所選 draft。Dialog 可以更換單選／雙選與畫預覽 overlay，但不更動 workflow。按「套用」時，Workflow 重新計算候選，核對 revision、fingerprint、subject identities、幾何 signature 與選擇是否合法，先在 staged result 重建關聯與 diagnostics，核對只有目標柱的距離歧義解除、無關 problems 保留，成功後才同時交換決策及 `world_result`，呼叫 `_rebuild_derived_state()`、增加 revision。失敗或取消只丟棄 draft。撤銷也以 staged rebuild 操作；重建後才移除決策。

**Rejected alternatives:** Dialog 直接 `replace()` live result 或只在確認鈕重寫欄位，因預覽取消、重算與持久化會留下不同 truth。

### Decision 4：相同來源可重播；內容不同不得直接轉移人工禁止點

序列化時寫入 source-bound 決策而不是 `ComponentAssociation` 快照。相同 fingerprint 的 Pause／Resume、重新辨識、來源排除／復原、端點修改與座標切換，先用 current WCS 重建候選並逐筆驗證 decision 的 Column／兩支 Strut identity、有限 station、容差與雙候選資格。有效者重算 station 並套用；失效者保留可辨認的「需重新檢查」記錄但不套用舊關聯。來源改變且走 compatible recovery 時，不直接轉移任何已採用決策效果；exact role/source identities 可標示 `requires_review`，不存在或 role 改變標示 `disabled`，都不得放入 active association。Exact Match relink 仍保留原 Review state。保存與恢復應沿用現有 transaction／rollback boundary。

這會與 `source_exclusion.py` 的 member-local manual overrides 相鄰，但不把跨 Column 與兩支 Strut 的決策硬塞入單一 member override；使用獨立 optional Review key 避免三方 identity 被單一來源模型截斷。Legacy version 2 Review state 不含此 key 時正常走自動關聯。

**Rejected alternatives:** changed-content recovery 用相近幾何或顯示 ID 自動套用，因可能把禁止點錯配到另一支；保存衍生 `component_associations` 作正式決策，因 stale projection 無法驗證原選擇。

### Decision 5：在「修改工具」提供專用清單與預覽，不改警告頁互動

`dxf_import/dialog.py` 的既有 STEP4「修改工具」加入一項「中間柱關聯修補」，由 workflow snapshot 提供待修與已修清單。選柱後顯示兩支候選的 ID、距離、station 與畫布位置，提供「第一支／第二支／兩支」互斥選擇、「套用」「撤銷」「取消」。已修項目可重開查看與撤銷；過期 plan 顯示重新預覽提示。警告頁維持只讀，不新增點擊交互。Presentation 不自行計算 candidate eligibility。

**Rejected alternatives:** 從警告頁點擊打開工具，因目前頁面沒有這種互動 contract，且使用者已指定入口在修改工具。

## Architecture Alignment

沿用 `docs/ARCHITECTURE.md` 的 DXF 子系統方向：`dialog.py`（Presentation）→ `review_workflow.py`（session owner）→ pure Column option／association operation（`candidate_points.py` 或小型專用模組）→ DXF models／geometry。`review_recovery_planner.py` 只處理 compatible-source 決策分類；Project conversion 消費重建後的 Strut fields。Domain 與 Algorithms 不依賴本工具，Solver 不知道 decision payload。正式 WCS state 與人工決策只有 Workflow 一個 owner；Dialog、warnings、Project rows 均為投影。

## Backward Compatibility／Persistence

- 既有 Project Strut row 欄位與 Review state version `2` 維持；新增可選 Review state key，舊檔缺少時等同無決策。
- 既有 `Column.associated_strut_id` 的 singular contract 保留；完整多關聯從 `component_associations` 與每支 Strut 的衍生欄位取得。
- 同來源 fingerprint 的 saved Review 應能重新驗證並重播；不同 fingerprint 的 compatible recovery 不得靜默保存 active effect。
- 若回退到舊版程式，未知 optional Review key 的處理需以目前 Project loader 行為驗證；若 loader 會拒絕，應在本 change 的 Review-state serialization boundary 修正相容性，而非改 Project schema。

## Risks / Trade-offs

- [同碼警告有不同成因] → 用 typed candidate facts 判定工具資格，測試多 accepted groups 與第三支近距離案例。
- [重建清掉人工禁止點] → 在同一 rebuild boundary 注入已驗證決策，並測試重複重建 idempotence。
- [人工單選與 nearest 結果重疊] → 依 Column identity 替換整組 association，測試 S20→S35 只剩一筆 active record。
- [診斷抑制範圍過大] → 僅在產生目標 Column 的距離歧義分支處理有效 decision，測試 Waler／雙路／source problems 原樣保留。
- [失效後自動最近結果被誤認為人工結果] → 明示 needs-review 且禁止舊 decision effect；Review 清單顯示當前自動結果。
- [進行中的雙路候選 change 同改 association consumer] → 整合時固定 qualification／accepted guard；柱修補不改 double-support status 或一對一 policy。

## Migration Plan

先保留舊 Review state 可載入，再加入 optional 決策 key、workflow 重播與 UI。所有新行為僅在使用者明確採用後生效。回滾時不改舊 Project rows schema；尚未完成的 Review state 若含新 key，舊版忽略能力須先由相容性測試確認。
