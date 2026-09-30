# Design

## 閱讀導航

### P0｜現在必讀

- **D1｜單一寬度規則來源**：`minimum_brace_body_width_mm = 250.0` 與嚴格 `>` 判斷由 DXF recognition core 共用。
- **D2｜先合法化候選、再決定 authority**：全部 tiers 分別列舉，候選先驗證 supporting-side width 與 hard gate，再由最高合法 tier 判斷唯一性。
- **D3｜component-like body evidence 與 terminal outcome**：whole-source evidence 的成立條件固定；成立後不得回到 `not_applicable` 或一般 body route。
- 「決策對照」：確認每個 Decision 對應的 requirement 與實作任務。

### P1｜實作前閱讀

- `specs/bim-block-brace-recognition/spec.md` 的兩個 ADDED Requirements 與兩個 MODIFIED Requirements。
- `dxf_import/block_member_recognition.py`：`_recognize_component_like_member`、`_recognize_topology_guarded_member`、`_whole_root_envelope_candidates`、`_component_candidates`。
- `dxf_import/recognition.py`：`_route_component_like_member_block_with` 與 `_candidate_from_group`。
- `dxf_import/models.py`：`GeometryTolerances`；`tests/test_dxf_bim_block_recognition.py` 的 Brace policy、Y05 characterization 與 ordinary asset regressions。

### P2｜遇到特定風險時再讀

- `openspec/specs/bim-block-member-recognition/spec.md`：只有共享 Strut helper 或 regression 失敗時再讀。
- `openspec/specs/brace-axis-waler-extension/spec.md` 與 `tests/test_dxf_brace_waler_extension.py`：只有 connection regression 失敗時再讀。
- `docs/DOMAIN.md`：實作及測試完成後，更新已成立的 Brace Engineering Hard Constraint；實作前不可先把長期文件寫成完成狀態。
- Solver、Project persistence、CornerBrace repair 文件可先跳過；本 change 不改這些責任。

## 方案摘要

保留現有「Brace role layer → root source grouping → component-like probe → 一般 recognition fallback」入口，但先以 whole-source geometry 判定 component-like body evidence 是否成立。只有完整／connected body topology、共同支持主要 corridor 的 whole-root bands，或同時建立主要方向、可靠 terminal extent 與 body envelope 的既有 component-like evidence 才能成立；局部 pair／detail 不足以單獨成立。

Evidence 成立後，Brace path 分別列舉 topology、whole-root envelope、local rail pair 三層全部候選。每個候選先完成完整性、whole-source support、可靠 extent、supporting-side width 與 `width > 250.0 mm` gate，之後才找最高合法 tier 並在該 tier 內判斷唯一性。一般 MLINE、outline 與 parallel-edge 候選也在 selection 前使用同一 predicate；單一 LINE 的 `source_width == 0` 仍表示 unknown，不進入 body-width gate。

```text
Brace role source
  ├─ root INSERT component-like probe
  │    ├─ whole-source evidence 不成立 ──> not_applicable ──> general route
  │    └─ whole-source evidence 成立
  │         ├─ 分別列舉 TOPOLOGY 全部候選
  │         ├─ 分別列舉 WHOLE_ROOT_ENVELOPE 全部候選
  │         └─ 分別列舉 LOCAL_RAIL_PAIR 全部候選
  │                ↓ 各候選先驗證完整性／whole-source support／extent
  │                ↓ 由合格 supporting sides 量寬，再套 width > 250.0
  │                ↓ 移除不合法候選，找最高「合法」authority tier
  │                     ├─ 唯一 normalized axis ──> recognized
  │                     ├─ 多個不等價完整 axes ──> ambiguous，不降層
  │                     └─ 全部 tiers 無合法候選 ──> failed（terminal）
  └─ general MLINE／outline／parallel edges
           ↓ selection 前套相同 hard gate
       合法 candidate 或 blocking width diagnostic

centerline-only LINE：width unknown，維持既有流程
```

## 決策對照

| Decision | 影響的 Spec Requirement | 對應 Task |
|---|---|---|
| D1 單一具名 Brace body-width rule | `Brace 實體寬度 SHALL 通過正式 hard gate` | 建立具名 tolerance／共用 predicate；補 `250.0`、`250.001` 與 unknown-width 測試 |
| D2 候選先合法化、再決定 authority；closed outline 以 supporting sides 量寬 | `Brace 實體寬度 SHALL 通過正式 hard gate`、`Component-like Brace SHALL 依 whole-source center authority 選軸` | 補完整候選列舉／gate／tier selection 與 irregular-outline fixtures |
| D3 component-like body evidence 與 terminal outcome | `Component-like Brace body evidence SHALL require whole-source support`、`Brace recognition outcome SHALL fail safely and deterministically` | 補 classification 正反例、order independence 與 fallback-bypass 測試 |
| D4 沿用 Review 與資料 contract | `Brace BIM recognition SHALL preserve Review and persistence boundaries` | 驗證 root handle、Review problem、Project schema 與 manual lifecycle regression |
| D5 僅在成立後更新 long-term truth | Proposal 的 In Scope／Impact | focused/full regression 通過後更新 `docs/DOMAIN.md` |

## 專有名詞

- **component-like body evidence**：同一 Brace-role root 的 whole-source geometry 已共同支持實體 body／外包絡、主要 longitudinal corridor、主要方向與可靠 terminal extent；不是任一局部 pair 或兩條平行線的別名。
- **body-derived candidate**：中心與寬度由 MLINE rails、closed outline、parallel edges 或 component fragments 推導的自動 Brace 候選；只有在 width 可由合格 supporting sides 可靠量測時才可進入 hard gate。
- **centerline-only source**：來源本身只表達工程中心線，沒有可靠實體外包絡；現有 `source_width == 0.0` 僅在這個語意下代表 unknown。
- **outer supporting sides**：位於 engineering axis 相對兩側、方向與主要 longitudinal direction 相容、對主要 corridor 有足夠 coverage，且共同支持同一 body envelope 的兩側來源邊。
- **authority tier**：通過完整性、whole-source support、可靠 extent、可靠 width 與 hard gate 後，才取得的中心決策層級；不是原始候選一出現就取得 authority，也不是依分數跨層競賽。
- **whole-root outer-envelope**：同一 root 中，沿主要方向具有足夠 longitudinal coverage 的最外側 supporting bands 所界定的實體包絡。
- **terminal outcome**：`failed` 或 `ambiguous` 已經對該 root 作出阻擋判定，router 必須視為 handled，不能再交給一般 body recognition。

## Context

動機與目標見 `proposal.md`。現有 DXF subsystem 已具備所需的主要 boundary：`BlockMemberRecognitionInput` 封裝單一 root 的 WCS primitives；`BlockMemberRecognitionOutcome` 表達 `not_applicable`、`recognized`、`failed`、`ambiguous`；`_route_component_like_member_block_with` 將純 recognition outcome 轉成 `_Candidate` 或 `ValidationMessage`；`_candidate_from_group` 處理一般 MLINE、outline、parallel edges 與 single LINE。

目前偏移來自三個技術落差：

1. `_component_candidates` 以局部 fragment evidence 建候選，Brace 仍主要依 evidence ratio／coverage 選擇；已存在、供 contextual Strut 使用的 `_whole_root_envelope_candidates` 尚未成為非 contextual Brace 的正式 authority tier。
2. 現有 `collinear_tolerance_mm < width <= maximum_component_width_mm` 只描述 recognition eligibility，不是 Brace 的最小材料寬度。約 `160 mm` 的 pair 因此可以成為候選；一般 `_candidate_from_group` 也沒有一致的 Brace `> 250 mm` gate。
3. 現有文件未固定 component-like body evidence 與 closed-outline width 的幾何契約，實作者可能把局部 pair 當分類依據，或以 bounding box、最遠點、端板尺寸代替主要 supporting-side separation。

`GeometryTolerances.connection_tolerance_mm == 250.0`、`maximum_brace_axis_extension_mm == 600.0` 與 `maximum_component_width_mm == 600.0` 已各有不同用途。本設計不重用它們來代表材料寬度，避免數值相同或接近時混淆工程語意。

## Goals / Non-Goals

**Goals:**

- 在 DXF recognition core 中建立單一、具名且可直接測試的 Brace body-width hard gate。
- 讓 component-like Brace 以 whole-source 證據層級決定中心，而非讓局部窄 pair 以分數勝出。
- 固定 component-like classification evidence 與 closed-outline supporting-side width 的唯一語意。
- 在 component-like 與一般 body-derived route 保持相同的嚴格邊界與 deterministic outcome。
- 沿用既有 root provenance、Review problem、Project conversion 與 persistence contract。
- 讓 Strut、CornerBrace、Waler connection 與 single-line Brace regression 明確受保護。

**Non-Goals:**

- 不建立新的 BIM metadata classifier，也不以 block／family 名稱判定 Brace 或寬度。
- 不把 Waler context 引入 Brace center selection；connection 仍是 recognition 後的獨立階段。
- 不修改 `BlockMemberRecognitionOutcome` 的狀態集合、Project schema 或 Review lifecycle。
- 不抽取跨所有 member role 的新框架；現有 Strut authority logic 只重用適合的純幾何 helper。
- 不順帶整理 `recognition.py`、`block_member_recognition.py` 的其他 technical debt。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer boundary**。

| Layer／模組 | 本次責任 | Dependency direction |
|---|---|---|
| `dxf_import/models.py` | 保存具名 recognition setting `minimum_brace_body_width_mm`；不執行 UI 或 Solver 邏輯 | Recognition → Models |
| `dxf_import/block_member_recognition.py` | 擁有共用 width predicate、Brace authority enumeration／selection 與純 outcome | Recognition core → Geometry／Models |
| `dxf_import/recognition.py` | 一般 Brace candidate gate、route translation 與既有 `ValidationMessage` projection | Import pipeline → Recognition core／Models |
| `DXFReviewWorkflow`／Presentation | 只呈現既有 problem 與 candidate 結果，不重新計算寬度或中心 | Workflow／Presentation → Recognition result |
| Domain 文件 | 實作完成後記錄已成立的 Engineering Hard Constraint | Documentation only |

正式幾何 truth 仍由 WCS recognition result 擁有。Review、preview、summary 與 persistence 只使用 `source_width`、recognized axis、diagnostic code 與 root provenance 的 projection，不新增另一份 threshold 或重新判斷合法性。Algorithms／Solver 不接觸 DXF body-width gate。

## Decisions

### D1｜以具名 tolerance 與共用 predicate 作為寬度規則的 single source of truth

在 `GeometryTolerances` 新增 `minimum_brace_body_width_mm: float = 250.0`，並在 `block_member_recognition.py` 提供一個可由 `recognition.py` 直接匯入的 package-internal pure predicate。predicate 只接受「已可靠量測的正值寬度」，採用嚴格 `width > minimum_brace_body_width_mm`；不加入 `width_tolerance_mm`、epsilon 或 rounding 來改寫正式邊界。

`source_width == 0.0` 不直接丟進 predicate。呼叫端先依來源證據區分 measured body 與 centerline-only unknown：

- MLINE、closed outline、parallel-edge／rail-pair、whole-root envelope：measured，必須通過 gate。
- 有 outline 且另含 matching explicit centerline：中心可採 explicit line，但 outline width 仍是 measured，必須通過 gate。
- 只有單一 LINE／明確 centerline，沒有 body envelope：unknown，保留既有流程。

這個判斷不新增 Project 欄位。`_Candidate.source_width` 與 `BlockMemberRecognitionOutcome.representative_width` 維持既有 contract；unknown 仍為 `0.0`，但只在已知 centerline-only route 中解讀。

**理由：** 門檻名稱表達工程語意，共用 predicate 防止 component-like 與 general route 的 `>`／`>=` 漂移；保留現有資料 contract 可避免 persistence migration。

**Rejected alternatives：**

- 重用 `connection_tolerance_mm`：雖同為 `250.0`，但一個是端點連接容許距離，另一個是材料寬度 hard constraint，耦合後任一規則調整都會誤傷另一方。
- 重用 CornerBrace 的 `minimum_corner_brace_rail_separation_mm`：兩者目前數值相同但 role 與來源證據不同，會把兩個獨立 Domain rule 綁成隱性 contract。
- 以 `width_tolerance_mm` 放寬等號：違反使用者確認的嚴格大於邊界。
- 新增 persistence 欄位表示 unknown／measured：現有 route 已能由 construction context 區分，新增 schema 成本不符合本 change 範圍。

### D2｜全部候選先合法化，再由最高合法 authority tier 選軸

將 Brace 的 component-like selection 收斂到專用 pure path（可為 `_recognize_component_like_brace` 或等價的小型 helper），由既有入口依 `role` 分流。Strut 繼續使用現行 source-only／contextual 流程，避免把 Brace hard gate 套到合法的窄 Strut。

Brace path 具有三個固定 authority tiers：

1. **TOPOLOGY**：由完整 closed／connected topology 建立 axis 與唯一 component envelope width。
2. **WHOLE_ROOT_ENVELOPE**：重用 `_whole_root_envelope_candidates`，只接受足夠 longitudinal coverage 的主要 bands，以最外側 supporting bands 建立中心與寬度。
3. **LOCAL_RAIL_PAIR**：重用 `_component_candidates` 作最後 fallback。

唯一執行順序如下，實作不得合併成 first-match、先選 winner 再 gate，或在不同 route 使用不同順序：

1. 分別列舉 `TOPOLOGY`、`WHOLE_ROOT_ENVELOPE`、`LOCAL_RAIL_PAIR` 各 tier 的全部候選。
2. 每個候選先完成該 tier 的完整性、whole-source support 與 reliable terminal extent 驗證。
3. 每個仍合格的候選以該 tier 的正式來源證據量測 width；width 不可靠的候選視為不合法，不以 `0.0` 冒充 centerline unknown。
4. 對每個 measured candidate 套用 D1 的嚴格 `width > 250.0 mm` gate，移除過窄候選。
5. 找出仍有一個或多個合法候選的最高 authority tier。較高 tier 若只有不合法候選，繼續評估下一 tier。
6. 只在該最高合法 tier 內進行 normalized geometry grouping、幾何等價合併與 deterministic uniqueness judgment。
7. 該 tier 只有一個 normalized engineering axis 時採用；所有 lower tiers 停止參與，不能以分數、長度或 evidence ratio 覆寫。
8. 該 tier 有多個不等價完整 axes 時回報 blocking `ambiguous`；不得降到 lower tier 尋找單一解。
9. 三個 tiers 全部沒有合法候選時，才回報 blocking `failed`。

Authority 只屬於已合法化的候選集合。原始 topology candidate 即使 tier 較高，只要 width 為 `160 mm`、supporting sides 不唯一或 extent 不可靠，就不會阻止合法 `300 mm` whole-root envelope 被評估。反之，只要 topology tier 有唯一合法 `300 mm` candidate，lower tier 即使 evidence score 更高也不能覆寫。

Topology helper 目前可能在 envelope 不唯一時回傳 `representative_width == 0.0`；Brace 不把這個 unreliable body width 直接視為成功，也不把它解讀成 centerline-only unknown，而是將該 topology candidate 移除並繼續嘗試 whole-root envelope。若全部 tiers 最後仍無合法 width／axis，才回報 failure。這個行為只存在於 Brace 專用 path；Strut 可保留既有「中心唯一、寬度 unknown」語意。

#### Closed body outline 的 supporting-side width contract

Topology candidate 不得從 generic bounding box 或任意端點跨度直接取得 Brace width。系統須先確定主要 longitudinal direction 與 source-supported corridor，再從工程軸相對兩側找出共同支持該 corridor 的 outer supporting sides。兩側必須方向相容、具有既有完整性／coverage contract 所要求的 longitudinal support，並共同界定同一 body envelope；其正交 separation 才是 candidate width。

下列值不得成為替代 width：axis-aligned bounding-box width；未經 supporting-side 驗證的 rotated-box 短邊；斜端板或端板平均長度；任意最遠頂點距離；局部突出造成的最大外距；短區段內部 edge；內部 web／flange 或孔洞邊；軸向端點距離；longitudinal gap。若 supporting sides 不唯一，topology width 為 unreliable，依上述九步流程繼續 lower tier。

`_whole_root_envelope_candidates` 的 band eligibility 保留現有 coverage 基礎，並在 Brace selection 中要求候選完整支持主要 corridor。短 detail、branch 或內部線若未達 coverage，不得作為 outer band；同一 window 中的中間 bands 可作 evidence，但寬度與中心由 window 最外側 bands 決定。

**理由：** 直接沿用現有 `_CandidateAuthorityTier` 與 whole-root geometry helper，可把 Y05 B8 修正在純 recognition core 內完成，同時把 Strut 的既有行為隔離。

**Rejected alternatives：**

- 只把 `_component_candidates` 的排序改成寬度最大優先：最大寬度未必是完整外包絡，也可能是無關線；且仍缺少明確 evidence authority。
- 先選現有 winner 再檢查 `>250`：過窄 winner 會遮蔽同 root 內合法的 300 mm higher-authority candidate，與「gate 後 selection」規格相反。
- 只要 topology tier 產生任何候選就停止：不合法高 tier 會錯誤遮蔽合法 lower tier，違反 authority 只屬於合法候選的契約。
- 以 bounding box／最遠點／端板尺寸補 topology width：這些量測可能同時混入 axial length、突出 detail 或非 supporting edge，無法代表構件正交實體寬度。
- 直接把 contextual Strut recognizer套到 Brace：該流程使用 Waler span context，會讓 Waler 反向影響 Brace source recognition，破壞既有 stage responsibility。
- 全面重寫 fragment extractor：範圍過大，會同時改變 Strut 與其他已驗證行為。

### D3｜body evidence 一旦成立，寬度或中心失敗就是 terminal outcome

Component-like classification 是 authority candidate legality 之前的獨立 whole-source 判斷。Evidence 成立必須由同一 Brace-role root 的整體 WCS geometry 共同證明實體 body／外包絡：完整或 connected body topology；共同支持主要 longitudinal corridor 的 whole-root longitudinal bands；或其他能同時建立主要方向、可靠 terminal extent 與 body envelope 的既有 component-like classification evidence。

單一局部平行線組、短 detail、branch、內部 flange／web、孔洞邊或零散 fragments，即使可形成某個局部 pair，也不能單獨使 classification 成立。Classification 不依賴候選分數或 enumeration order；相同 WCS geometry 與 root identity 在 child order、handle order、LINE direction 改變後必須相同。

Component-like Brace path 明確區分：

- **無 component-like body evidence**：`not_applicable`，router 可交回一般 recognition。
- **存在 body evidence且依 D2 得到唯一合法 candidate**：`recognized`。
- **存在 body evidence但全部 tiers 的候選皆過窄／寬度或完整 extent 不可靠**：`failed`。
- **最高合法 authority tier 有多個不等價完整中心**：`ambiguous`。

Evidence 一旦成立，D2 的候選處理結果只能是 `recognized`、`failed` 或 `ambiguous`；不得因所有候選被 gate 移除、topology width unreliable 或最高合法 tier 多解而改回 `not_applicable`。只有 evidence 本身未成立，router 才可交回 general route。

新增穩定 diagnostic code `BRACE_BODY_WIDTH_TOO_SMALL`，用於 body evidence 已成立、各 tier 曾有可靠 measured width，但沒有任何候選嚴格大於門檻的情況。既有 `BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE` 與 `BIM_BLOCK_CONFLICTING_WHOLE_AXES` 繼續分別表達完整 extent／supporting-side width 不可靠與最高合法 tier 多解。`_route_component_like_member_block_with` 對新 code 提供 Brace 專用訊息，並沿用 `handled=True`、`ValidationMessage(severity="error", role="brace", source_handles=(root_handle,))`，因此不會落入一般 fallback。

一般 `_candidate_from_group` 也必須在各 body candidate 進入 winner／ambiguity selection前過濾寬度：

- 單一 MLINE 過窄：不建立 candidate，回傳 `BRACE_BODY_WIDTH_TOO_SMALL`。
- 多個 outlines／pairs：先剔除不合法候選，再對剩餘合法候選執行既有排序與 ambiguity；若原本有 measurable body evidence 但全部被剔除，回傳 blocking width diagnostic。
- single LINE：不產生 measurable body evidence，維持 `existing_centerline`。

**理由：** 這使 hard constraint 先於 heuristic scoring，且 component-like failure 能在 exact root scope 被 Review 處理。

**Rejected alternatives：**

- 讓 router 在 width failure 後回一般 recognition：同一窄 body 可被 outline／pair route 再次接受，形成規格明確禁止的 bypass。
- 只在正式 Project conversion 時驗證：太晚才失敗，Preview／Review 會先展示錯誤中心，並在不同入口形成第二套 legality logic。
- 靜默忽略過窄來源：使用者無法知道構件為何消失，也無法用既有 exclusion／restore workflow 處理。

### D4｜沿用既有 diagnostics、Review 與 persistence contract

不新增 outcome status、Review state 或 Project schema。Recognition 只輸出既有 `_Candidate` 或 `ValidationMessage`；Review 透過現有 root handle 建立 `ProblemRecord`／`ReviewItem`。排除、恢復、manual endpoint replay、Pause／Resume 與 completed import 的 owner 和流程都不變。

Y05 B8 成功後仍以 `bim_block_whole_axis` 進入既有 Brace-to-Waler connection；source-supported axis 可在後續依現有規格延伸，但 Waler 不參與 authority selection。一般 body route 成功時仍保留原 `recognition_method`，避免不必要的輸出 contract 變更。

**理由：** 本 change 改的是 source geometry truth，不是 workflow 或儲存格式。沿用既有 problem pipeline 可維持 exact source provenance 與 rollback 行為。

**Rejected alternatives：**

- 在 UI 額外標記「BIM Brace」並讓使用者選中心：會把 recognition truth 移到 Presentation，且使用者已要求的是新的自動辨識程序。
- 將 authority tier／全部 child geometry 寫入 Project：下游 Solver 不需要這些 provenance，會擴大 schema 與 migration 範圍。

### D5｜驗證以 synthetic boundary、authority／outline、Review 與真實資產四層進行

測試分四層，先小後大：

1. **Pure policy tests**：`250.0` 拒絕、`250.001` 接受、single LINE unknown、outline／MLINE／parallel pair 一致 gate，以及 component-like classification 的正例、局部 detail 反例與 order independence。
2. **Authority／outline tests**：高 tier 過窄而 lower tier 合法、高 tier 唯一合法、最高合法 tier 多解、全部 tiers 無解、先 gate 後 selection；矩形 supporting sides、斜端板、突出 detail、內部 web／flange、supporting sides 不唯一與 lower-tier recovery。
3. **Route／Review integration**：component-like 過窄回 blocking diagnostic且不回 `not_applicable`／general fallback；一般過窄 body 也可審查；root handle、role 與 source identity 保留。
4. **Real asset regression**：Y05 B8／`DD9`（若 repository fixture 使用重上傳 handle，透過既有 fixture mapping 取得同一來源）應拒絕約 `160.015 mm` local pair並使用約 `300 mm` outer-envelope center；其他 Y05 Brace、Y1A single-line Brace、Y29 合法 outline Brace、Strut、CornerBrace 與 Brace-to-Waler tests 保持預期。若 Y29 中確有 `<=250 mm` body，應依新 breaking rule更新為明確 rejected expectation，而不是保留舊計數。

不以 snapshot 大量重錄取代精確 assertions；Y05 case 應直接斷言 source handle、representative width、normalized source-supported axis 與正式 member provenance。

## Backward Compatibility and Persistence Impact

- **刻意 breaking**：所有可量測 body width `<= 250.0 mm` 的自動 Brace 不再成立。
- **保持相容**：single LINE／centerline-only Brace、人工指定工程線、manual endpoint、Strut、CornerBrace 與 Waler connection 規則不變。
- **Persistence**：無 schema migration；舊 project 既有已提交 rows 不在載入時重新辨識。只有重新匯入／恢復 DXF Review 並執行 recognition 時採用新規則。
- **Diagnostics**：新增 code 可由舊的通用 message fallback 顯示，但 implementation 應補明確中文描述；serialized review state 的既有結構不變。

## Risks / Trade-offs

- **[真實圖面有合法但寬度不大於 250 mm 的 Brace]** → 這是已確認 hard constraint 的刻意 breaking；測試應顯示 exact source，不能暗中放寬門檻。若 Domain 事實改變，另立 change。
- **[Whole-root envelope 把無關長線當外緣]** → 保留方向、coverage、最大寬度、slenderness 與 root scope filters；以 Y05 及 synthetic branch／detail tests 驗證。
- **[局部平行 detail 誤使 component-like classification 成立]** → classification 必須先證明 whole-root corridor、reliable extent 與 body envelope；加入局部 detail 反例及 order-independence tests。
- **[Closed outline 以 bounding box 或端板猜測 width]** → width extraction 僅接受相對軸兩側的主要 longitudinal supporting sides；不唯一時移除 topology candidate 並評估 lower tier。
- **[現有 source geometry 無法可靠區分 body evidence、supporting sides 或 authority tier]** → 停止實作並回報 Spec／code assumption 衝突；不得自行放寬 `> 250.0 mm`、加入 magic number、恢復 first-match 或讓 general fallback 繞過 terminal outcome。
- **[過早 gate 讓合法 300 mm candidate 被 160 mm candidate 遮蔽]** → 所有候選先列舉並過濾，再做 authority selection；禁止「先選 winner 再 gate」。
- **[共用 helper 誤傷 Strut]** → predicate 由呼叫端顯式以 Brace role 使用，增加 Strut regression；不修改 Strut threshold。
- **[浮點邊界不穩定]** → 正式判斷直接使用 `>`；測試涵蓋 `250.0` 與明確大於邊界的值，不以 display rounding 決定合法性。
- **[新 diagnostic 在 Review 顯示不完整]** → 沿用既有 `ValidationMessage` contract，route translation 補 code description，整合測試斷言 role／root handle／blocking state。
- **[真實 fixture handle 因檔案版本不同]** → 沿用現有 legacy／current handle mapping，但 geometry assertion 必須一致，不能只比 handle。

## Migration Plan

1. 先新增 failing pure tests，固定 component-like classification 正反例、嚴格 `>250.0`、unknown-width、closed-outline supporting-side width 與 authority order。
2. 新增具名 tolerance 與共用 predicate，實作獨立 classification，再讓 component-like Brace 專用 path依 D2 九步順序通過 pure tests；確認 Strut tests不變。
3. 實作 topology supporting-side width extraction；不可靠 topology 必須能繼續合法 whole-root envelope，而非猜寬或提前失敗。
4. 在一般 `_candidate_from_group` 的 body candidate enumeration 前套用相同 gate，串接 blocking diagnostic。
5. 加入 Y05 B8 與 fallback-bypass integration regression，再執行一般 Brace、Strut、CornerBrace、Review 與 Waler connection focused suites。
6. 擴大執行 DXF regression 與 architecture boundary tests；不得以刪除或放寬既有 assertions 讓測試通過。
7. 行為驗證完成後才更新 `docs/DOMAIN.md`，把 Brace `> 250.0 mm` 記為已成立的 Engineering Hard Constraint。

Rollback 不需要資料 migration：回退 recognition code、具名 tolerance、測試與對應 Domain 文件即可。已保存 Project schema 未變；但若使用者已用新規則重新匯入並排除過窄來源，回退不應自動改寫其已確認的 Review decision。

