# Design

## Context

動機與使用者行為見 [proposal.md](./proposal.md)。目前 CornerBrace automatic recognition 位於 `dxf_import/recognition.py`：一般 compound block 需要成對 longitudinal rails 與兩端 connection plates，後續 `_refine_corner_brace_axis_intersections()` 才把可靠中心軸延伸至 Waler 內線及 Strut 中心線。當 BIM 遮蔽使小型角撐只剩局部線段時，現行 recognizer 拒絕建立正式構件是正確的安全行為。

現有人工修改能力有三個與本 change 直接相關的限制：

- `apply_candidate_point_selection()` 可改已存在的 CornerBrace 端點，但不能把 unresolved source 建成正式 CornerBrace。
- STEP4 的 CAD engineering-line action 只支援 Waler／Strut／Brace；CornerBrace 沒有專用候選推導與預覽。
- generic candidate endpoint apply 會重建 Strut 角撐衍生長度，但目前不把 CornerBrace repair、`CornerBraceConnection`、參考 provenance 與 unresolved-to-formal transition 視為一個原子 use case。

`DXFReviewWorkflow` 已是 live Review state owner，`world_result` 是 WCS canonical truth，`result` 是 coordinate projection。Review state version 現為 `2`，人工材料、工程線與 Waler contact 透過 `manual_overrides` 以 exact source evidence replay；compatible source recovery 另有 `preserved`／`requires_review`／`disabled` 分類。本 change 應重用這些 boundary，不讓 Dialog 保存第二份 repaired geometry。

## Goals / Non-Goals

**Goals:**

- 在不修改 automatic recognizer 的前提下，建立人工觸發、pure planning、preview-first、atomic commit 的 CornerBrace repair path。
- 讓正式 CornerBrace 與 unresolved `corner_brace` source 共用一套候選規則及 workflow command。
- 以 target residual geometry 為必要證據、至少一支 automatic recognized primary CornerBrace 為必要先驗，並以有限 Waler／Strut 工程幾何建立正式端點；manual repaired CornerBrace 只可作為具完整 provenance 的 secondary evidence。
- 修補後只保留一份 authoritative CornerBrace geometry，所有 connection、Strut length、candidate point、validation 與 confirmation 由它重新推導。
- 讓相同來源 Pause／Resume 可安全 replay，同時阻止 changed-content recovery 靜默搬移 repaired axis。

**Non-Goals:**

- 不把此工具泛化成 Strut／Brace Guided Recognition framework。
- 不改寫 `_corner_brace_candidates_from_group()`、`_corner_brace_center_axis()` 或既有 recognition tolerance。
- 不新增自動 winner score、機器學習、影像辨識或 batch repair。
- 不修改 Project row mapping、Solver input、Waler contact displacement 公式或 CAD/LSP command。
- 不處理「完全沒有 target source geometry」或只能靠工程師憑空畫線的角撐；這需要另一個明確授權的 manual-create workflow。

## Architecture Alignment

本 change 沿用、而非修改現有 Architecture：

```text
DXFImportDialog (Presentation)
        │ selected subject / preview / explicit accept
        ▼
DXFReviewWorkflow (live Review use-case owner)
        │ plan / commit / replay
        ▼
corner_brace_repair.py (pure WCS planning + rebuild operation)
        │
        ├─ models.py / geometry.py
        ├─ candidate_points.py targeted rebuild
        └─ waler_contact_adjustment.py connection builder
```

- `dialog.py` 只保存 selection、目前候選與 overlay 等 UI draft，不自行計算工程候選。
- `review_workflow.py` 驗證 revision、建立 plan、提交 staged state、管理 confirmation 與 serialization。
- 新增 `dxf_import/corner_brace_repair.py` 作為小型 pure operation owner；它不依賴 Tkinter、Dialog、Project 或 Solver。
- `DXFImportResult.world_result` 中的 CornerBrace 仍是 live repaired geometry 的 single source of truth。Preview candidate 與 serialized replay record 都只是 staged／derived data，不是第二份 active truth。
- Project Domain 與 Algorithms 無變更；CornerBrace 仍停留在 DXF import subsystem。

## Decisions

### 1. 修補是獨立人工 use case，不是 automatic recognition fallback

Importer 不會在 recognition failure 時自動呼叫 repair planner。只有使用者在 STEP4 選取一個正式 CornerBrace 或 unresolved `corner_brace` subject 並按下「修補角撐」後，Workflow 才建立 `CornerBraceRepairPlan`。

Plan 至少包含：

- `base_revision`；
- 穩定的 repair subject key；
- target source geometry 摘要；
- 零至多個 immutable `CornerBraceRepairCandidate`；
- 每個 candidate 的 WCS endpoints、target Waler／Strut、reference CornerBrace identities、evidence summary 與 rejection／warning diagnostics。

**理由：** automatic recognition 的失敗代表 source evidence 不足，不應因存在鄰近構件便偷偷降低可靠性。人工 workflow 可以呈現不確定性並取得明確工程師決策。

**Rejected alternative — 在 recognizer 中增加 nearby-copy fallback：** 會讓大量匯入階段把推測直接變成正式資料，且無法區分使用者是否看過候選。

### 2. Repair subject identity 必須能區分同來源的多支 CornerBrace

現有 canonical source identity 主要由 role + normalized source handles 組成，但一個 compound INSERT 可合法產生多支 CornerBrace，因此 handles 本身不一定能唯一定位 formal member。新增的 repair subject key 使用：

1. source fingerprint（由 Review state context 提供）；
2. role=`corner_brace`；
3. normalized source handles；
4. target kind（`recognized` 或 `unresolved`）；
5. target discriminator。

Formal target 的 discriminator 是修補前 source-supported base axis／member signature；unresolved target 則使用 ReviewItem key 加上其 source-problem／source-geometry signature。Signature 使用既有 geometry tolerance 做 canonical comparison，不以 raw float string 或 UI display ID 作唯一證據。

Formal repair 保留原 CornerBrace ID。Unresolved repair 在 commit 時採用目前最小可用的 `CB<n>`，並把 preferred display ID 寫入 repair provenance；相同來源 replay 只有在該 ID 不衝突且 subject key 仍唯一時才恢復，否則分類為需要重新檢查，不靜默重新編號或套到另一支角撐。

**理由：** 只靠 handles 會讓同一 block 內兩支角撐互相覆寫；只靠 `CB71` 則無法證明來源。組合 identity 同時保留 source safety 與 subject uniqueness。

**Rejected alternative — 永久以 current member ID 當 identity：** ID 是辨識排序產物，不能獨立證明 DXF source ownership。

### 3. Reference pool 分級，且每個候選都必須有 automatic primary

Planner 建立 reference pool 時先依目前 formal CornerBrace、`CornerBraceConnection`、Review confirmation／problem state 與 repair provenance 分類：

- `automatic primary`：`selection_source`／recognition provenance 證明它來自 automatic recognition，source 目前 active，且 `CornerBraceConnection` 唯一有效。
- `manual repaired secondary`：使用者已明確採用 repair、`CornerBraceRepairProvenance` 完整、目前 confirmation signature 有效、source 仍 active、未被 recovery 標為 `requires_review`，且 connection 仍唯一有效。
- 其他 CornerBrace：不進入 reference pool。Generic candidate-point／CAD manual geometry 不因 connection 存在就自動升級成 primary 或 secondary。

每一個 candidate 的 evidence set 至少包含一支 automatic primary。Secondary 只能對已由 primary 支持的候選補充 consensus，不得單獨建立候選。Planner 不遞迴讀取 secondary provenance 中的 repaired reference graph，也不把「secondary 曾由另一支 repaired CornerBrace 支持」視為額外 confidence；provenance 只供顯示、replay safety 與 audit。如此即使 repaired CB1 被用於 CB2，CB2 日後也不能再脫離新的 automatic primary 單獨支持 CB3。

**理由：** 人工 repair 可以成為有價值的局部佐證，但若允許 repaired-only chain，推測誤差會逐支累積並失去原始 automatic evidence anchor。

**Rejected alternative — 所有 connection valid 的 CornerBrace 等價作 reference：** 會讓 manual、unconfirmed 或 recovery requires-review geometry 與 automatic recognition 具有相同可信度，無法限制推測鏈。

### 4. 候選規劃採 evidence pipeline，reference length 不改寫目標幾何

`corner_brace_repair.py` 以 WCS immutable input 執行下列流程：

1. 從 target exact source geometry 擷取、canonicalize 可用 residual segment hypotheses；沒有可用殘線即 terminal no-candidate。
2. 依前述 eligibility 建立 reference pool；至少一支 automatic primary 才繼續，合格 secondary 可選擇性加入。Reference 可來自同一 Strut、另一側或鄰近 Strut。
3. 由目前正式 Waler／Strut 有限幾何建立 possible target relationship；每個 proposal 都必須明確綁定一支 Waler 與一支 Strut。
4. Reference 只提供 consistency evidence，例如 fixed length、相對 Waler／Strut 的 signed orientation、連接側、topology 與多筆 consensus；不得複製 absolute endpoints。
5. Proposal 的正式 endpoints 只由 candidate axis 與 target Waler finite inner line、target Strut finite centreline 求交；再以 residual angle、offset、projection coverage、reference length／topology consistency 進行 hard validation。Reference length 不一致時淘汰 hypothesis，不沿軸移動交點、不裁切或延長 target line，也不把 reference length 寫成 target fixed length。Target fixed length 永遠由兩個正式交點距離重新計算。
6. 以既有 `GeometryTolerances` 去除幾何等價候選，並用 canonical geometry key 排序，確保 entity order 不影響輸出。

Evidence priority 為：target residual fit（必要）→ finite target relationship（必要）→ automatic primary topology／length support（必要）→ optional secondary／multiple-reference consensus → proximity。Proximity 只可排序已通過全部 hard filters 的 candidates，不可單獨讓 hypothesis 成立，也不可在多個非等價 candidates 間自動勝出。

第一版不新增數值權重或 repair-specific magic number。若 implementation discovery 證明現有 named tolerance 無法表達必要判斷，必須先回到 OpenSpec 補上具名設定、邊界與測試，不得在 production code 私自加入常數。

**理由：** 使用者要的是可審核的修補建議，不是另一個較寬鬆且不透明的 recognizer。

**Rejected alternative — 最近 reference + 最低距離直接採用：** 在兩側、鏡像或密集支撐處很容易選錯，且無法表達多解。

### 5. Hard filter 完成後才建立 Preview candidates

Planner 內部可保留 residual axis、reference pairing 與 target relationship 的 hypotheses 來產生 diagnostics，但 `CornerBraceRepairPlan.candidates` 只包含通過全部 hard eligibility 的項目。Hard filters 至少涵蓋：

- target subject identity 可安全定位；
- target residual geometry 存在；
- residual direction 唯一可靠，或 hypothesis 是有限、可獨立檢核的集合；
- candidate 具有一組明確 Waler／Strut relationship 與兩個 finite intersections；
- 至少一支 automatic primary reference，optional secondary 亦各自有效；
- reference length／side／topology consistency 通過；
- 全部既有 applicable CornerBrace validation 通過；diagnostic 是否代表 failure 沿用該 validator 的既有 contract，不以 Presentation 自行判斷。

Rejected hypotheses 不出現在可選 candidate list，也沒有 Apply action；UI 只顯示彙整拒絕原因。若零 eligible candidates，Preview 顯示 rejection state。若一個，仍須 explicit Apply。若多個非等價且各自完整，全部顯示供使用者選擇。Proximity 只影響這些 eligible candidates 的顯示順序。

**理由：** 讓使用者在多個完整工程解中選擇，與把多個缺證據猜測包裝成選項，是不同的安全邊界；後者會把 validation 責任錯誤地推給 UI。

**Rejected alternative — 將所有 hypothesis 顯示並以警告區分：** 可 Apply 與不可 Apply 的視覺差異容易被誤解，也讓 Presentation 決定工程 eligibility。

### 6. Preview candidate 與正式採用完全分離

Dialog 呼叫 `workflow.plan_corner_brace_repair(review_item_key)` 取得 immutable plan，將 candidates 交給現有 preview renderer 的 overlay path 顯示。Overlay 清楚區分：

- target residual source geometry；
- proposed repaired axis；
- target Waler 與 Strut；
- reference CornerBrace；
- candidate-specific diagnostics。

沒有 eligible candidate 時顯示 planner 的拒絕原因，不建立假 candidate。只有一個 candidate 仍顯示預覽與 Apply；多個 candidates 代表每一個都已通過 hard filters，由 selection controller 保存目前 UI selection。Cancel／關閉只丟棄 Dialog draft。

Apply 呼叫 `workflow.commit_corner_brace_repair(plan, candidate_id)`。Workflow 檢查 `plan.base_revision == workflow.revision` 且 subject signature 未改變；stale plan 必須拒絕並要求重新預覽。

**理由：** Preview 是 Presentation draft，正式 mutation 仍只有 Workflow 可以提交，符合目前 live Review ownership。

**Rejected alternative — Dialog 直接 replace CornerBrace 後 refresh：** 會繞過 workflow revision、confirmation invalidation、serialization 與 rollback boundary。

### 7. Unresolved create path 比 recognized replace path多一層 eligibility gate

Planner 與 apply operation 明確保留兩種 target kind：

- `recognized`：subject key 唯一定位目前 formal CornerBrace，commit 只 replace 該 member並保留 ID。
- `unresolved`：尚無 formal member；在一般 candidate hard filters之外，所有 surviving hypotheses 必須指向同一組唯一 finite target Waler／Strut relationship。多條完整 axis hypotheses 可以在這組唯一 relationship 內交由使用者選擇，但不同 relationship 不能交由 UI 猜選。

Unresolved create 在 staged member 建立後必須執行全部現有 applicable CornerBrace validation。任一 validation 依其既有 contract 判定未通過，就拒絕整個 commit並保留 unresolved state；Presentation 不得以 severity label 自行放行。Layer、INSERT、附近構件或 references 只能協助定位／檢核，不能在 target residual geometry 缺失時取代它。

**理由：** Replace 至少有一支已存在的 formal member 可限制 target；Create 會新增工程構件，必須用更嚴格且唯一的 relationship boundary 防止從附近資訊憑空造物件。

**Rejected alternative — unresolved 多組 relationship 全部交給使用者選：** 即使人工點選，也沒有足夠 target source evidence 證明哪一組關係屬於原構件，超出本 change 的保守 repair scope。

### 8. Commit 先建立完整 staged projection，再一次交換 Workflow state

Pure apply operation 先以選定 candidate 建立 staged `DXFImportResult`：

1. replace 既有 CornerBrace，或 append 一支新 CornerBrace；
2. 設定 `recognition_method`／`selection_source` 為明確的 manual repair value，並附帶 `CornerBraceRepairProvenance`；
3. 使用 `rebuild_candidate_points_for_components()` 只重建 target CornerBrace，保留所有其他 member 的人工 candidate choices；
4. 使用 `attach_corner_braces_to_struts()` 從全部目前正式 CornerBrace 重算 Strut 四個角撐長度欄位；
5. 使用 `build_corner_brace_connections()` 重建全部 `CornerBraceConnection` 與對應 diagnostics，但保留既有 Waler contact review input，不重新 initialize／覆寫使用者已採用的背填與寬度；
6. 移除過時的 target／corner-connection diagnostics，加入本次 rebuild diagnostics，再執行既有 duplicate／validation projection。

Workflow 再以 staged world result 在 local variables 中建立 coordinate projection、ProblemRecords、ReviewItems、有效 confirmations 與新的 CandidatePointStore。全部成功後才一次更新 `world_result`、`result`、`problem_records`、`review_items`、`review_confirmations`、`candidate_point_store` 與 `revision`。任何 exception 發生時不交換 state，因此不需要以反向 mutation 嘗試修補半成品。

採用後沿用 `_mutation_result()` 回報失效 confirmation。修補 target 由 unresolved 轉 formal 時，ReviewItems 完全從 staged result 重建；不得保留一個手工刪除的 ghost unresolved row。

**理由：** 現有 models 多為 immutable dataclass，適合 copy-on-write staging；這也避免 repair 中途造成 world/projected state 混合 truth。

**Rejected alternative — 依序修改 member、length、connection 再遇錯 rollback：** rollback 欄位容易漏掉 candidate store、projection 或 confirmation，風險高於一次交換 immutable stage。

### 9. Repair provenance 放在 CornerBrace，serialized record 由正式 result 推導

新增小型 immutable `CornerBraceRepairProvenance`（或等價 value object），由 repaired CornerBrace 持有，至少包含：

- repair subject key 與 preferred display ID；
- adopted WCS endpoints；
- target Waler／Strut source identities（另保留 display IDs 供診斷）；
- automatic primary 與 manual repaired secondary 的 CornerBrace subject identities及 reference class；
- selection source 與必要 evidence signature。

Live session 不另維護一份可漂移的 `repair_decisions` mapping。`serialize_review_state()` 從 repaired CornerBrace capture provenance，擴充現有 `manual_overrides` entry 的 optional repair payload；舊 state 沒有該 payload 時照常讀取。Review state 仍為 version `2`，Project persistence schema 不升級。

相同 fingerprint 的 normal Resume replay 順序為：base recognition → 既有 exclusions／double-support base → CornerBrace repairs → 其他依賴 repaired geometry 的 confirmation validation。每筆 repair 必須重新找到唯一 repair subject、target Waler／Strut exact identities，確認至少一支保存的 automatic primary 仍符合 primary eligibility，並確認每支採用的 secondary 仍符合 secondary eligibility，再重新執行 current validation。Reference 失效時不得尋找新的近鄰替代，也不得沿 repaired provenance graph補 primary。成功後衍生資料一律重建，不從 saved debug 複製 connection、reference eligibility 或 Strut lengths。

Compatible content-changed recovery 將 repair payload 與一般 manual endpoint 分開分類：

- exact role/source subject 仍存在：不 replay，candidate-based subject 保留，entry=`requires_review`；
- exact subject 不存在或角色不符：不 replay，entry=`disabled`；
- geometry-only matched CornerBrace：不得接收舊 repair。

Compatible recovery 中 `requires_review`／`disabled` 的 repaired decision 同時失去 secondary eligibility；只有使用者在 recovered Review 重新完成 repair、explicit adoption 與 confirmation 後，新的 repaired member 才能重新成為 secondary。

Exact Match Relink 不重新辨識，依既有 contract 完整保留 serialized state。

**理由：** repaired CornerBrace 是 active truth，serialization 只是可重建 decision。將 repair payload 混成一般 endpoint override 會讓 changed-content recovery 依 geometry rebind，違反本 change 的 source safety。

**Rejected alternative — 新增 Project-level repair repository：** CornerBrace 不是 Project Domain entity，會造成 Project 與 DXF Review 各持一份 truth。

### 10. 現有自動與人工路徑保持隔離

既有 automatic CornerBrace regression 必須證明：沒有點擊修補時，recognition count、method、endpoint refinement、connection 及 Strut derived lengths 完全不受影響。Generic candidate point 工具仍可處理其現有 supported member；本 change 不把 repair planning 塞入 `apply_candidate_point_selection()`，只重用 targeted candidate rebuild 與共同 association helpers。

Recognition code 不 import Workflow 或 repair module。Repair module只消費 recognition 已完成的 immutable result，維持 `recognition → review operation` 方向。

## Data and Control Flow

```text
selected recognized CornerBrace / unresolved corner_brace source
        │
        ▼
DXFReviewWorkflow.plan_corner_brace_repair()
        │ current WCS result + target key + revision
        ▼
pure repair planner
        ├─ exact target residual evidence (required)
        ├─ automatic primary reference (required)
        ├─ valid repaired secondary reference (optional)
        ├─ finite target Waler / Strut relationships
        ├─ reference consistency only; never rewrite intersections
        └─ hard-filter + deduplicate deterministic candidates
        │
        ▼
Dialog preview (zero formal mutation)
        ├─ cancel → discard UI draft
        └─ explicit candidate Apply
                │
                ▼
workflow stale check + staged apply
        ├─ repaired/new CornerBrace + provenance
        ├─ targeted candidate-point rebuild
        ├─ Strut corner-length rebuild
        ├─ CornerBraceConnection rebuild
        ├─ validation / ReviewItems / confirmations projection
        └─ all valid → one state swap + revision increment
```

## Backward Compatibility and Persistence

- 舊 DXF、舊 Review state 與沒有 repair payload 的 Project 不需 migration。
- 新 optional repair payload 只存在既有 `manual_overrides` serialization boundary；舊 reader path 必須忽略不存在欄位，新 code 必須接受舊 state。
- Review state version 維持 `2`。若 tests 證明 existing deserializer 無法 backward-compatibly接受 optional payload，implementation 必須停止並回到 planning，不得自行 bump version。
- CornerBrace repair details不進入 `ProjectDataModel`；Review complete 的 Project row mapping維持既有行為。
- Rollback feature code 後，含 optional repair payload 的 paused state 應由舊 parser忽略未知欄位而不破壞 Project load；已完成 Project geometry不受影響。

## Risks / Trade-offs

- **[Risk] 局部殘線太短，方向對雜訊敏感** → 使用既有 length／angle／projection tolerances；不能形成可靠 hypothesis 時拒絕，不靠 reference 單獨補線。
- **[Risk] 鄰近角撐屬於不同型式或鏡像側** → primary／secondary 都需有效 connection，將 topology／signed side 納入 hard evidence；只有各自完整合法的非等價解才保留給使用者選擇。
- **[Risk] repaired reference 形成信心累積鏈** → 每個 candidate 必須重新具有 automatic primary；secondary 不遞迴傳遞自己的 repaired reference evidence，unconfirmed／requires-review secondary直接排除。
- **[Risk] reference fixed length 反向扭曲目標端點** → fixed length只作 pass／reject consistency check；正式 endpoints與 target fixed length一律由 target finite intersections推導。
- **[Risk] 多個缺證據 guesses 被當成可選方案** → planner先執行完整 hard filters，Plan candidates不含 rejected hypotheses；UI只能顯示 rejection summary。
- **[Risk] 同一 root handle 產生多支角撐** → repair subject key 加入 base geometry discriminator，不以 handles 單獨定位。
- **[Risk] 重建 CornerBraceConnection 時洗掉 Waler contact input** → 只重建 connections，不重新呼叫會 reset review values 的初始化流程；加入已採用背填／寬度的 regression。
- **[Risk] 全場 candidate rebuild 洗掉其他人工端點** → 使用現有 targeted rebuild helper，只處理 repaired member。
- **[Risk] 新建 unresolved CornerBrace 的 ID 影響 UI reference** → deterministic smallest-unused allocation + persisted preferred ID；衝突時停止 replay並要求 review。
- **[Risk] changed-content recovery把舊 repair套到相似幾何** → repair使用獨立 recovery classification，禁止 geometry-only transfer。
- **[Risk] Y05 實例檔不適合 CI** → pure planner以 synthetic WCS fixtures驗證正式 contract；repo內穩定可取得時才加 Y05／CB71 smoke regression，不把外部絕對路徑當測試依賴。

## Migration Plan

1. 先建立 pure WCS fixtures與現行 automatic CornerBrace characterization。
2. 新增 repair DTO／planner，只產生候選，不接 UI或 mutation。
3. 加入 staged apply與完整 derived-state rebuild，完成 headless workflow tests。
4. 加入 serialization／same-source replay與 compatible recovery classification。
5. 最後接上 STEP4 button、candidate list與 preview overlay。
6. 更新 `docs/WORKFLOW.md`；若實際新增模組成為長期責任 owner，再同步 `docs/ARCHITECTURE.md` 的 DXF module inventory。

回退時可移除 UI入口與 repair planning／commit path；沒有 Project schema migration。已保存的 optional repair payload 不得造成 load failure，回退版可忽略它。若回退後重新辨識 paused Review，repair effect不再重播，使用者須重新檢查該角撐。
