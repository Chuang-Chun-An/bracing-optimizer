# Design

## 閱讀導航

### 現在必讀

- Decision 1：將 geometry qualification 與 Waler topology qualification 拆成同一 pure operation 的兩個階段。
- Decision 2：由 `DoubleSupportCandidate` 保存單一 authoritative outcome，並強制 `accepted` invariant。
- Decision 3：所有正式衍生效果只消費 `eligible && accepted`。
- Decision 4：Review rebuild 與 decision replay 必須以 source identity 保持安全。

### 條件式閱讀

- 修改 Waler terminal recognition facts 時閱讀 Decision 1 的 structured terminal evidence 傳遞方式。
- 修改 Tkinter 視窗時閱讀 Decision 5；Presentation 只負責投影與操作 affordance。
- 修改 Pause／Resume 或 compatible recovery 時閱讀 Decision 4 與「Backward Compatibility／Persistence」。
- 遇到多 partner 或排序回歸時閱讀 Decision 6。

### 可先跳過

- Solver、Project Domain、材料與 Waler contact-face 演算法不在本 change 的實作範圍。
- 不需要閱讀一般 BIM／CornerBrace／Joist recognition 細節；只有共用 terminal topology contract 受到最小幅資料傳遞影響。

## 方案摘要

```text
reliable source-supported Strut WCS axes
  → geometry qualification（既有數值；pending階段只供Review）
  → Waler topology qualification（structured terminal facts）
  → DoubleSupportCandidate(status + issues + accepted invariant)
  → DXFReviewWorkflow authoritative result
      ├─ Dialog：顯示 eligible／pending_waler
      └─ Derived consumers：只讀 eligible && accepted
```

「geometry-qualified pair」只表示形狀符合雙路形式；「formal candidate」表示 Waler topology 已證明合法；「accepted pair」才是使用者／既有預設已採用並可產生正式工程效果的 pair。三者不得混為同一布林值。

## 決策對照

| Decision | 對應 Spec Requirement | 主要 Tasks |
| --- | --- | --- |
| 1. 分離幾何與 topology qualification | 「雙路幾何候選與正式工程資格必須分層」「Waler topology 必須產生可區分的候選狀態」 | 1、2 |
| 2. Candidate outcome 是 single source of truth | 「Waler topology 必須產生可區分的候選狀態」「Review 必須呈現狀態、原因與操作限制」 | 2、4 |
| 3. 正式 consumer 使用共同 predicate | 「暫定候選不得提前產生正式效果」 | 3 |
| 4. Rebuild／replay 以 source identity 安全轉移 | 「候選必須隨 canonical Review state 安全重建」 | 4、5 |
| 5. Presentation 只投影 workflow state | 「Review 必須呈現狀態、原因與操作限制」 | 6 |
| 6. One-to-one ambiguity 對全部幾何候選 deterministic 計算 | 「候選結果必須 deterministic 並保守處理一對多歧義」 | 2、7 |

## Context

動機見 `proposal.md` 的 Why。現行 `detect_double_support_candidates()` 先要求兩支 Strut 均有 `from_waler` 與 `to_waler`，再計算雙路幾何，因此 Waler ambiguity 會使 pair 完全消失。`DoubleSupportCandidate` 目前只有 `accepted`、`ambiguous` 與文字 `warnings`，不足以區分「使用者拒絕」與「工程關係尚不可接受」。

Waler terminal 的 authoritative ambiguity facts 已存在於 `waler_contact_face.build_member_terminal_evidence()` 的 `TerminalTopologyOutcome`：issue 含 member source identity、terminal-level reason 與 competing Waler source identities。現行 pipeline 最後只把 blocked 狀態與扁平 validation message 投影到 importer，沒有把足夠的 structured facts交給 double-support qualification。設計應重用該 outcome，不可從錯誤文字、CandidatePoint label 或畫布距離反向解析。

`DXFReviewWorkflow.world_result` 是 live Review canonical WCS state；Dialog 只能持有 snapshot／draft。`associate_components_to_struts()`、initial zoning 與 `to_project_rows()` 已以 accepted candidate 為下游入口，但加入 provisional candidates 後，單看 `accepted` 預設值將不再足夠，必須明確守住 qualification boundary。

## Goals / Non-Goals

**Goals:**

- 在不改變既有幾何 threshold 的前提下，保留 geometry-qualified provisional pairs。
- 使用 upstream structured Waler terminal facts建立可測試的 `eligible`／`pending_waler`／`incompatible_waler` outcome。
- 讓 workflow、Presentation、association、grouping 與 persistence replay 使用同一 outcome。
- 確保任何 provisional／incompatible pair 都不能滲入 Project 或 Solver。

**Non-Goals:**

- 不重新設計 Waler identity、contact face 或 terminal ambiguity policy。
- 不將 Column／Beam association 納入雙路 eligibility。
- 不新增可強制接受 provisional pair 的 override。
- 不重構整個 DXF recognition pipeline，也不修改 Project／Solver model。

## Decisions

### Decision 1：同一 pure pairing operation 先產生幾何 pair，再套用 structured topology facts

`support_pairing` 仍是 double-support engineering review operation 的 owner。偵測流程分為：

1. 只對具有可靠、source-supported WCS axis的Struts套用現有angle、spacing、overlap、length gates，建立deterministic geometry-qualified records；Waler尚未唯一時，這些axes與量測只供Review provisional提示。
2. 以每支 Strut 的 normalized source identity 查詢 terminal topology projection。
3. 將兩支 Strut 分類為 `eligible`、`pending_waler` 或 `incompatible_waler`，再建立 `DoubleSupportCandidate`。

Source-supported axis必須來自目前Strut recognition outcome中已有來源幾何支持的WCS長軸，不得由Waler candidates、Column／Beam proximity、附近幾何或UI canvas補推。任一Strut缺少此軸時，該Strut不參與geometry-qualified graph；系統仍以既有recognition／validation problem呈現其未解決狀態。

Recognition pipeline SHALL 將 `TerminalTopologyOutcome` 中與 Strut 有關的 evidence／issues，正規化成 pairing 所需的 read-only terminal qualification input。該 projection 至少保留 member source identity、terminal name、唯一 Waler source identity或 competing identities、reason code。它可以是 `support_pairing` 的小型 immutable input type，或等價的 typed mapping；不得讓 `support_pairing` 讀 Tk state、validation message text 或重新掃描 DXF geometry。

一般 legacy／synthetic 呼叫若只有 formal `Strut.from_waler/to_waler`，adapter 以這兩個欄位建立 resolved topology input，維持既有 unit tests 與 headless consumers。Production importer 有 structured terminal facts 時必須優先使用它們，避免空白 `from_waler/to_waler` 遺失 competing identities。

**理由：** 這保留 `support_pairing` 的 pure、可測試責任，同時讓 Waler ambiguity 只有一個來源。

**Rejected alternatives:**

- 從 `ValidationMessage.message` 或 `source_handles` 猜 terminal：扁平訊息缺少可靠 terminal 結構，且文字不是工程 contract。
- 從 CandidatePoint／Preview geometry 重新尋找 Waler：會建立第二套 terminal relationship 演算法，違反現有 Waler contact-face spec。
- 由暫定Waler交點或Column／Beam位置補造Strut axis：會把尚未證明的關係變成candidate evidence，並可能污染Project geometry。
- 直接刪除 `from_waler/to_waler` gate 而不建立狀態：會使 unresolved pair 使用預設 `accepted=True` 滲入下游。

### Decision 2：擴充 candidate outcome，並以 invariant 區分資格與選擇

`DoubleSupportCandidate` 增加 typed qualification fields，概念上包含：

- `qualification_status`: `eligible | pending_waler | incompatible_waler`
- `issues`: deterministic immutable issue records（reason code、terminal、member source／display identity、competing Waler source identities、message）
- 既有幾何量測、`ambiguous`、`warnings` 與 `accepted`

不論實作採 enum 或 validated string，construction、decision replay 與 setter 都必須維持：

```text
candidate.accepted implies candidate.qualification_status == "eligible"
```

`pending_waler`／`incompatible_waler` 一律建立為 `accepted=False`。既有 `ambiguous` 保留 one-to-one membership 衝突的意義，不能改成 Waler ambiguity 的替代欄位；Waler 問題由 qualification status／issues 表達。

Confidence 仍只描述既有幾何量測組合，不得因 Waler 狀態或 Column evidence被加權，以免同一欄位混合兩種語意。

**理由：** eligibility 是工程狀態，accepted 是 selection state。分開後才能顯示 provisional pair 且不冒充使用者拒絕或正式雙路。

**Rejected alternatives:**

- 只在 `warnings` 加一段文字並維持 `accepted=False`：無法可靠限制 setter、serializer 與 downstream consumer，也無法區分 explicit rejection。
- 另建第二份 provisional-pairs collection：UI 與 rebuild 容易在兩份集合間 drift，且 source decision replay 更複雜。

### Decision 3：集中定義 formal accepted predicate，所有 derived consumers 共用

在 `support_pairing` 或 model 上提供無 UI dependency 的共同 predicate／property，語意為 `qualification_status == eligible and accepted`。下列 consumer 必須改用同一語意，而非各自判斷文字或假設 `accepted` 足夠：

- `associate_components_to_struts()` 的共享 Column／Beam membership；
- `DXFImportResult.to_project_rows()` 的 `SharedLayoutGroup`；
- `initial_zoning` 的 accepted pair ordering units；
- decision serialization／replay 與 Review commit validation；
- summary／count 等所有宣稱「正式雙路群組」的 projection。

這是 defensive boundary：即使 malformed in-memory object 出現 `pending_waler + accepted=True`，正式 consumer 仍不得產生效果；construction／mutation 層同時應阻止該組合。

**理由：** 新 provisional state 會經過多條旁路；共同 predicate 防止只修 UI、漏掉 Project conversion。

**Rejected alternative:** 只依賴 Dialog 禁用按鈕。Headless import、resume、tests 或未來 consumer 可繞過 Presentation，不能以 UI 作為工程安全邊界。

### Decision 4：每次 canonical rebuild 重算 qualification，decision 只對目前 eligible pair replay

Importer、CandidatePoint rebuild、Waler contact adjustment、source exclusion／restore 等現有重新辨識入口，必須以重新辨識後的canonical finalized Strut axes及最新terminal qualification input重新呼叫同一pairing operation。每次rebuild都重建完整geometry-qualified graph，重新計算angle、spacing、overlap ratio、length difference、Waler topology與one-to-one ambiguity；不得只mutate舊status、沿用provisional量測或保留不存在的geometry edge。

Decision identity 繼續使用兩支 Strut 的 normalized source-handle sets。Replay 分兩層：

1. 先由目前 canonical facts 重建 candidate status；
2. 只有 identity 唯一且 status 為 `eligible` 時，才套用可安全replay的舊explicit decision；explicit accepted／rejected均優先於default。

若 pair 降級，當次 result 必須 `accepted=False` 並重建 derived associations。保存的 explicit decision 是否仍留在 session mapping 可沿用現有 lifecycle，但任何再次分類為`eligible`時都必須重新滿足source identity唯一、current geometry及topology eligibility；不得因stale candidate ID生效。對current eligible pair，先replay可安全套用的explicit decision；只有沒有explicit decision時才考慮既有eligible default。完整graph存在one-to-one ambiguity時，default不得自動接受；這不把Waler修正本身視為接受，也不要求pair僅因先前曾為pending而再次人工確認。

Pause／Resume state 不新增新的 durable decision type：provisional status 是由目前 recognition facts 重建的 derived state。既有 `double_support_decisions` 仍只保存 explicit accepted／rejected selection；開啟設定視窗或套用未變更 provisional rows不得製造 false rejection。

**理由：** 避免引入 Project schema migration，並維持 source-safe replay contract。

**Rejected alternatives:**

- 保存 provisional status 作為 authoritative durable state：可能與重新辨識後的 Waler facts漂移。
- 將 provisional 的 `accepted=False` 序列化為 rejection：會把「尚不可判定」誤寫成使用者決策。

### Decision 5：Dialog 顯示 workflow projection，pending row 不進入 decision draft

雙路設定 Treeview 增加狀態欄，並提供警告摘要；選取 pending row 時顯示 structured issue details。`eligible` row保留接受／不接受控制；`pending_waler` row 的 toggle disabled／no-op，且 Apply 只提交 eligible rows 的實際 decision delta。

Dialog 不從顏色、spacing 顯示字串、candidate point 或 Problems tree 推導 eligibility。狀態色彩與圖示只作 Presentation affordance，文字狀態及詳細原因仍須可讀，避免資訊只依賴顏色。

`incompatible_waler` 不進一般 candidate list；由既有 diagnostics/problem projection 或專用 diagnostic entry 保持可取得。本 change 不新增第二個可操作清單。

**理由：** 使用者能提前看到可處理的 pair，同時維持 workflow owner 與無障礙可讀性。

### Decision 6：one-to-one ambiguity 從完整 geometry-qualified graph 計算，接受只作用於 eligible edges

Pair IDs、排序與 occurrence 計算以 normalized deterministic keys 建立，不依輸入順序。`eligible`、`pending_waler`與`incompatible_waler`全部保留為geometry-qualified graph edges並參與occurrence／conflict計算。任何Strut在graph中有多個partner時，所有相關candidates都取得one-to-one ambiguity indication；不得因某個edge pending或incompatible而忽略它，導致另一edge被誤認成唯一。

Default自動接受只可能發生於`eligible`且沒有membership ambiguity的edge。可安全replay的explicit accepted／rejected decision先於default處理；使用者也只能操作目前eligible的edge。使用者接受某個eligible edge時，現有one-to-one rule取消共享成員的其他eligible accepted edges；pending／incompatible edges保留診斷但永遠不可能accepted。canonical rebuild使任何edge消失時，系統從零重建graph；剩餘唯一eligible edge才可在沒有explicit decision時依既有default接受。正式derived consumers最後仍依Decision 3 predicate過濾。

**理由：** 一對多本身是幾何配對 ambiguity，不因其中一條 edge 暫時缺 Waler 而消失。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 dependency direction。

| Layer／模組 | 責任變更 | Dependency |
| --- | --- | --- |
| DXF recognition／`waler_contact_face` | 提供既有 terminal outcome 的 structured read-only projection | 不依賴 pairing、workflow 或 UI |
| DXF pure operation／`support_pairing` | 建立 geometry pair、qualification outcome、issue 與 formal predicate | 依賴 DXF models／geometry，不依賴 Dialog |
| DXF models | 保存 immutable candidate outcome | 不依賴 workflow／Tkinter |
| `DXFReviewWorkflow` | 持有 canonical candidates、重建並提交合法 decision | 不依賴 Dialog |
| DXF Presentation／`dialog.py` | 顯示狀態、原因與合法操作 | 只消費 workflow snapshot／commands |
| Project／Solver boundary | 無新資料；只接收正式 accepted pair 的既有 rows | 不依賴 DXF provisional metadata |

Single source of truth 是 `DXFReviewWorkflow.world_result.double_support_candidates` 中由目前 WCS canonical facts計算的 outcome。`result` 是 coordinate projection，Dialog tree 是顯示 projection，Problems／summary 是 diagnostics projection；它們不得保存或推導另一份 qualification truth。

## Backward Compatibility／Persistence

- `DoubleSupportCandidate` 新欄位提供可安全的 defaults，使既有 synthetic construction 可漸進更新；production construction 必須明確填入 qualification。
- 對 Waler 唯一且相容的既有 drawing，候選 membership、接受預設、one-to-one rule、共享 association 與 Project rows保持等價。
- `double_support_decisions` 的 durable JSON shape維持 source-handle pair＋accepted bool，不升級 Project schema。
- Pause／Resume 重新辨識時重建 provisional outcome；exact-state hydration 若讀取舊 candidate payload，缺少 qualification fields時必須依 current facts重建或以相容 adapter處理，不得假設舊 `accepted=True` 可繞過 eligibility。
- Rollback 是回復本 change 的 code；沒有資料 migration需要回滾。

## Risks / Trade-offs

- [Risk] 幾何候選數增加，三條以上平行支撐可能增加 UI noise → 只顯示通過全部既有數值門檻的 pairs，以狀態排序並提供清楚警告；不把所有 Strut combinations列入。
- [Risk] Structured terminal issues 在 recognition 到 pairing 間遺失 terminal name → 建立 typed projection與 focused tests，不解析 validation文字。
- [Risk] pending階段的Strut axis其實沒有可靠來源支持 → qualification前要求明確source-supported axis；缺少時不建pair並保留既有recognition problem，不從周邊幾何fallback。
- [Risk] 某個下游仍只檢查 `accepted` → 集中 formal predicate，逐一測試 association、initial zoning、row conversion、summary及 malformed-state defense。
- [Risk] Expanded candidate graph 改變 `DG<n>` IDs → decision persistence繼續使用 source identity，測試 permutation與renumbering；UI ID只作當次session selection。
- [Risk] 舊 accepted pair暫時降級後的 decision lifecycle令人困惑 → UI顯示 current status；不讓stale decision生效，升級時只在current identity／eligibility合法下依既有 replay policy套用。
- [Trade-off] `incompatible_waler` 不在一般清單中，使用者可見性較低 → 保留 structured diagnostic；若實際使用需要再另案增加收合區，不把 rejection混入可操作候選。

## Migration Plan

1. 先加入 typed qualification model與 pure characterization tests，保持 production behavior未接線。
2. 接入 importer／rebuild structured terminal projection，驗證pending只使用可靠source-supported axes，且每次canonical rebuild都重新計算完整graph與全部幾何量測。
3. 將所有 derived consumers切換至 formal predicate並加入 negative tests。
4. 更新 workflow與Dialog projection，加入 S19／S36 regression及UI操作限制。
5. 執行 Pause／Resume、recovery、initial zoning、Project conversion及完整 DXF regression。

本 change無外部部署migration；若任一步發現必須持久化 provisional truth、修改 Waler identity contract或變更 Solver input，停止實作並回到 Spec／Design重新評估。
