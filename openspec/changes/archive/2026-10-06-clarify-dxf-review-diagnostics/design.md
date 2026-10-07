# Design：DXF Review 診斷文字白話化

## 閱讀導航

- **P0／現在必讀**：Decision 1「以原始 code 為真相、顯示投影為白話介面」與 Decision 2「由既有問題投影集中產生文案」；這兩項決定資料邊界。
- **P0／現在必讀**：Decision 3「固定 code 分類與安全 fallback」；列出目前 88 個 `ValidationMessage` code、固定文案來源及 fallback A。
- **P1／實作前閱讀**：Decision 4「同一份投影供兩個問題區域使用」與「驗證策略」；實作 `dialog.py` 及測試時必讀。
- **P2／需要時再讀**：「相容性與 persistence」及「Rejected alternatives」；只有碰到 model serialization、診斷來源模組或想另建 abstraction 時再讀。
- **可先跳過**：Solver、Project persistence、DXF export 與 recognition tolerance 文件；本 change 不修改這些 contract。

## 方案摘要

```text
ValidationMessage（診斷真相）
  ├─ severity／code／role／handles／member IDs ── 原樣保留
  └─ message ──┐
               ▼
       ProblemRecord 顯示投影
       ├─ 中文問題類型
       ├─ 白話說明
       └─ 適用的處理建議
               ▼
       全部問題清單 + 選取項目明細
```

本 change 中，「診斷真相」是 recognition／validation 已產生的 structured fields；「顯示投影」是使用者看到的中文類型、說明與建議。前者決定 severity、blocking 與定位，後者只能讀取前者，不可反向修改。

## 決策對照

| Decision | 影響的 spec Requirement | 對應 tasks |
| --- | --- | --- |
| D1. 原始 `code` 持續作為診斷 identity | 「白話顯示不得改變診斷真相」 | 1.1、2.2、3.2 |
| D2. 在既有 `ProblemRecord` 投影集中產生使用者文案 | 「DXF Review 診斷須使用白話中文」、「兩個問題區域使用同一份投影」Scenario | 1.1、2.1、2.2 |
| D3. 88 個已知 code 固定分類，未知 code 使用 fallback A | 「保留定位與量測資訊」、「未知代碼使用安全 fallback」Scenario | 1.2～1.4、2.1～2.3、3.1 |
| D4. Dialog 只呈現投影，不自行翻譯或判斷 | 「白話顯示不得改變診斷真相」 | 2.2、3.2 |

## Context

動機見 `proposal.md` 的「Why」。目前 `ValidationMessage` 保存 severity、code、message、role、source handles 與 member IDs；`build_problem_records()` 將它轉成 `ProblemRecord`，並處理正式 ID／來源 handle 的可定位格式。`DXFImportDialog` 的全部問題清單與選取項目明細都消費 `ProblemRecord`，但目前直接把 `record.code` 顯示為類型，說明也可能保留診斷來源模組中的內部術語。`review_item_guidance()` 已依 code 群組與 item 狀態提供建議。

既有 Architecture 將 DXF problems／ReviewItems 的 authoritative owner 放在 `DXFReviewWorkflow`，Dialog 只持有 Treeview projection。`validation.py` 已是從 structured diagnostic 建立 presentation-facing `ProblemRecord` 與 guidance 的既有邊界；本設計沿用該邊界，不把工程判斷移入 Dialog。

## Goals / Non-Goals

**Goals:**

- 讓問題類型、說明與處理建議使用一致的繁體中文詞彙。
- 保留現有 structured diagnostic、定位資料與 blocking behavior。
- 讓已知 code 有專用顯示，未知 code 也能安全、穩定地出現在清單。
- 以單一投影供兩個問題區域使用，避免文案 drift。

**Non-Goals:**

- 不建立一般化 i18n framework 或全應用程式訊息 catalog。
- 不重命名 code、不改診斷產生條件，也不重寫 recognition pipeline。
- 不增加新的修正工具、技術 log 視窗或 persistence 欄位。

## Decisions

### Decision 1：原始 code 是 single source of truth

`ValidationMessage.code` 與 `ProblemRecord.code` 保持原值，繼續供 code grouping、測試、定位與問題追查使用。新增或計算出的中文類型只屬於非持久化顯示欄位，不能取代 `code`，也不能參與 severity 或 blocking 判斷。

原因：既有多個 workflow 與 tests 以 code 做穩定識別；文案會隨可讀性調整，不適合作為 identity。這也避免出現「改一句話就改變工程行為」的第二份 truth。

### Decision 2：沿用 `ProblemRecord` 作為集中顯示投影

在 `dxf_import/validation.py` 的既有 problem projection boundary 集中形成：

- 使用者可見的中文問題類型。
- 已完成來源 handle → 正式 ID 投影的白話說明。
- 由既有 code group、role 與 item status 決定的處理建議。

預期對 presentation-facing `ProblemRecord` 增加獨立的顯示類型欄位；原有 `code` 保留。若實作時可由純函式穩定計算且不造成 Dialog 重複呼叫，也可不保存欄位，但兩個問題區域必須消費同一個 helper 結果。

專用文案函式只根據 structured diagnostic fields 與既有 message 中的工程事實組合文字，不做 proximity、geometry、connection 或 severity 推導。既有 `_format_problem_description()` 的正式 ID／來源 handle 規則仍在最後顯示階段套用，避免破壞 main spec 的定位 contract。

原因：此處已是 workflow diagnostics 到 Dialog 的明確 projection boundary。另建跨 package service 對單一畫面沒有收益；把 mapping 放在 Dialog 則會讓兩個 Treeview 與 guidance 形成多個文案 owner。

### Decision 3：固定 code 分類與安全 fallback

文案來源只由 `ValidationMessage.code` 的明確分類決定，不檢查 message 使用的語言、字元、關鍵字或「看起來是否已經清楚」。實作 SHALL 建立三個互斥集合：保留原始 message、專用 formatter、已知 fallback；三者聯集必須等於目前所有會形成 `ValidationMessage` 的已知 code。收到不在已知集合中的新 code 時，一律走與已知 fallback 相同的安全路徑，但 producer inventory 測試必須失敗，要求開發者補上正式分類。

所有已知 code 仍應有中文問題類型與適用 guidance；下列三分類專指 description 的來源。專用 formatter 可以使用 structured fields，或對該 code 的穩定來源格式做有測試的精確資料擷取，以保留量測值；不得使用跨 code 的全域字串替換，也不得猜測任意 exception 文字。

#### 已知 code 的產生位置

| 產生或轉換位置 | 會形成 `ValidationMessage` 的 code |
| --- | --- |
| `dxf_import/candidate_points.py:713-943` | `AMBIGUOUS_WALER_CONNECTION`、`AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION`、`STRUT_NOT_CONNECTED`、`STRUT_ONE_END_NOT_CONNECTED`、`BRACE_NOT_CONNECTED`、`BRACE_ONE_END_NOT_CONNECTED`、`BRACE_SAME_WALER_CONNECTION`、`BRACE_AXIS_EXTENDED_TO_WALER` |
| `dxf_import/candidate_points.py:1193-1565` | `COLUMN_ASSOCIATION_REQUIRES_REVIEW`、`COLUMN_ASSOCIATION_MANUALLY_RESOLVED`、`COLUMN_NOT_ASSOCIATED`、`AMBIGUOUS_COMPONENT_ASSOCIATION`、`BEAM_NOT_ASSOCIATED`、`BEAM_OVERLAPS_STRUT`、`BEAM_CROSSING_SNAPPED` |
| `dxf_import/candidate_points.py:1972-1987` | `CAD_MANUAL_LINE_SELECTION`、`MANUAL_POINT_SELECTION` |
| `dxf_import/importer.py:570-745,1503-1510` | `TEXT_SKIPPED`、`ZERO_LENGTH_COMPONENT`、`COMPONENT_TOO_SHORT`、`MULTIPLE_MODELS_FROM_ONE_SOURCE`；依 `waler`、`strut`、`brace`、`corner_brace`、`column`、`beam` 動態展開 6 個 `*_RECOGNITION_FAILED`；另展開 `WALER_ENGINEERING_LINE_FAILED` 與 5 個非圍令 `*_CENTERLINE_FAILED` |
| `dxf_import/hatch_waler_recognition.py:442-471`，由 `dxf_import/importer.py:488-495` 轉換 | `HATCH_WALER_BOUNDARY_INVALID`、`HATCH_WALER_UNSUPPORTED_BOUNDARY`、`HATCH_WALER_AMBIGUOUS_BOUNDARY`、`HATCH_WALER_ENGINEERING_LINE_FAILED` |
| `dxf_import/block_member_recognition.py:1931-3061`，由 `dxf_import/recognition.py:395-444` 轉換 | `BIM_BLOCK_CONFLICTING_WHOLE_AXES`、`BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE`、`BIM_BLOCK_WALER_SPAN_INCOMPLETE`、`BIM_BLOCK_WALER_SPAN_AMBIGUOUS`、`BRACE_BODY_WIDTH_TOO_SMALL` |
| `dxf_import/joist_recognition.py:331-992`，由 `dxf_import/recognition.py:286-320` 轉換 | `BIM_JOIST_CONFLICTING_WHOLE_AXES`、`BIM_JOIST_PAIR_AMBIGUOUS`、`BIM_JOIST_PAIR_SPACING_INVALID`、`BIM_JOIST_PAIR_UNPAIRED`、`BIM_JOIST_SINGLE_NO_BRACE_CONTACT`、`BIM_JOIST_SINGLE_STRUT_OBLIGATION`、`BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS`、`BIM_JOIST_TERMINAL_CONTEXT_DRIFT`、`BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS`、`BIM_JOIST_DETAIL_IGNORED`、`BIM_JOIST_RECOGNITION_FAILED` |
| `dxf_import/recognition.py:931-2039,2161-2173,2442-2464,2747-2789,3002-3023` | `AMBIGUOUS_CENTERLINE`、`AMBIGUOUS_INNER_LINE`、`WALER_ENVELOPE_UNRESOLVED`、`WALER_ENVELOPE_AMBIGUOUS`、`DUPLICATED_COMPONENT`、`BRACE_TERMINAL_VERDICT_MISSING`、`BIM_BLOCK_WALER_FINALIZE_FAILED`、`WALER_CONTACT_FINALIZE_FAILED`、`WALER_SOURCE_OVERLAP`、`WALER_OVERLAP_COMPETITION`、`CORNER_BRACE_BODY_UNRESOLVED`、`CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED`、`CORNER_BRACE_RELATIONSHIP_UNRESOLVED`、`CORNER_BRACE_CONNECTION_POINT_FAILED` |
| `dxf_import/waler_contact_face.py:601-1488`，由 `dxf_import/recognition.py:1472-1493,1922-1994` 轉換 | `WALER_CONTACT_FACE_UNRESOLVED`、`WALER_CONTACT_FACE_AMBIGUOUS`、`WALER_COMPETING_SIDE_EVIDENCE_IGNORED`、`AMBIGUOUS_WALER_CONNECTION`、`AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION`、`WALER_ENVELOPE_UNRESOLVED`、`WALER_ENVELOPE_AMBIGUOUS` |
| `dxf_import/validation.py:777-793,849-971` | `DUPLICATE_ENGINEERING_COMPONENT`、`CANDIDATE_POINT_MISSING`、`CANDIDATE_POINT_INVALID`、`ZERO_LENGTH_CANDIDATE_LINE`、`CANDIDATE_LINE_TOO_SHORT`、`CANDIDATE_LINE_DIRECTION_CHANGED`、`POSSIBLE_COMPONENT_SHORT_SIDE`、`WALER_CANDIDATE_LINE_UNUSUAL`、`CANDIDATE_ENDPOINT_NOT_NEAR_WALER` |
| `dxf_import/waler_contact_adjustment.py:673-1547` | `CORNER_BRACE_CONNECTION_INVALID`、`CORNER_BRACE_DERIVED_FIELD_CONFLICT`、`WALER_SUPPORT_SIDE_UNKNOWN`、`WALER_CONTACT_BASELINE_CHANGED`、`STRUT_WALER_INTERSECTION_FAILED`、`BRACE_RIGID_TRANSLATION_UNRESOLVED`、`CORNER_BRACE_INTERSECTION_FAILED`、`CORNER_BRACE_INTERSECTION_AMBIGUOUS`、`WALER_CONTACT_ADJUSTED` |

`HATCH_WALER_RECOGNIZED` 是成功 outcome；`BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED` 會先轉為 `BIM_JOIST_DETAIL_IGNORED`；`BRACE_STATION_INVALID`、`INVALID_WALER_CONTACT_VALUE`、`MANUAL_LINE_SELECTION` 目前只存在於常數或過濾條件。這五個值未形成目前的 `ValidationMessage`，不納入 88-code 分類；若日後成為 producer code，完整性測試必須要求分類。

#### 分類一：保留原始 message（63 個）

```text
AMBIGUOUS_CENTERLINE
AMBIGUOUS_INNER_LINE
BEAM_CROSSING_SNAPPED
BEAM_NOT_ASSOCIATED
BEAM_OVERLAPS_STRUT
BIM_BLOCK_CONFLICTING_WHOLE_AXES
BIM_BLOCK_WALER_FINALIZE_FAILED
BIM_BLOCK_WALER_SPAN_AMBIGUOUS
BIM_BLOCK_WALER_SPAN_INCOMPLETE
BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE
BIM_JOIST_CONFLICTING_WHOLE_AXES
BIM_JOIST_PAIR_AMBIGUOUS
BIM_JOIST_PAIR_SPACING_INVALID
BIM_JOIST_PAIR_UNPAIRED
BIM_JOIST_SINGLE_NO_BRACE_CONTACT
BIM_JOIST_SINGLE_STRUT_OBLIGATION
BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS
BIM_JOIST_TERMINAL_CONTEXT_DRIFT
BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS
BRACE_AXIS_EXTENDED_TO_WALER
BRACE_BODY_WIDTH_TOO_SMALL
BRACE_NOT_CONNECTED
BRACE_ONE_END_NOT_CONNECTED
BRACE_SAME_WALER_CONNECTION
CAD_MANUAL_LINE_SELECTION
CANDIDATE_ENDPOINT_NOT_NEAR_WALER
CANDIDATE_LINE_DIRECTION_CHANGED
CANDIDATE_LINE_TOO_SHORT
CANDIDATE_POINT_INVALID
CANDIDATE_POINT_MISSING
COLUMN_ASSOCIATION_MANUALLY_RESOLVED
COLUMN_ASSOCIATION_REQUIRES_REVIEW
COLUMN_NOT_ASSOCIATED
COMPONENT_TOO_SHORT
CORNER_BRACE_CONNECTION_INVALID
CORNER_BRACE_CONNECTION_POINT_FAILED
CORNER_BRACE_DERIVED_FIELD_CONFLICT
CORNER_BRACE_INTERSECTION_AMBIGUOUS
CORNER_BRACE_INTERSECTION_FAILED
DUPLICATED_COMPONENT
DUPLICATE_ENGINEERING_COMPONENT
MANUAL_POINT_SELECTION
MULTIPLE_MODELS_FROM_ONE_SOURCE
POSSIBLE_COMPONENT_SHORT_SIDE
STRUT_NOT_CONNECTED
STRUT_ONE_END_NOT_CONNECTED
STRUT_WALER_INTERSECTION_FAILED
TEXT_SKIPPED
WALER_CANDIDATE_LINE_UNUSUAL
WALER_CONTACT_ADJUSTED
WALER_CONTACT_BASELINE_CHANGED
WALER_CONTACT_FACE_AMBIGUOUS
WALER_ENVELOPE_AMBIGUOUS
WALER_ENVELOPE_UNRESOLVED
WALER_SUPPORT_SIDE_UNKNOWN
ZERO_LENGTH_CANDIDATE_LINE
ZERO_LENGTH_COMPONENT
WALER_ENGINEERING_LINE_FAILED
STRUT_CENTERLINE_FAILED
BRACE_CENTERLINE_FAILED
CORNER_BRACE_CENTERLINE_FAILED
COLUMN_CENTERLINE_FAILED
BEAM_CENTERLINE_FAILED
```

這些 code 的 description 直接使用原始 message，再套用既有正式 ID／來源 handle 格式化。此分類是固定清單，不代表系統在 runtime 檢查 message 是否為繁體中文。

#### 分類二：專用 formatter（23 個）

```text
AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION
AMBIGUOUS_COMPONENT_ASSOCIATION
AMBIGUOUS_WALER_CONNECTION
BIM_JOIST_DETAIL_IGNORED
BRACE_RIGID_TRANSLATION_UNRESOLVED
CORNER_BRACE_BODY_UNRESOLVED
CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED
CORNER_BRACE_RELATIONSHIP_UNRESOLVED
HATCH_WALER_AMBIGUOUS_BOUNDARY
HATCH_WALER_BOUNDARY_INVALID
HATCH_WALER_ENGINEERING_LINE_FAILED
HATCH_WALER_UNSUPPORTED_BOUNDARY
WALER_COMPETING_SIDE_EVIDENCE_IGNORED
WALER_CONTACT_FACE_UNRESOLVED
WALER_CONTACT_FINALIZE_FAILED
WALER_OVERLAP_COMPETITION
WALER_SOURCE_OVERLAP
WALER_RECOGNITION_FAILED
STRUT_RECOGNITION_FAILED
BRACE_RECOGNITION_FAILED
CORNER_BRACE_RECOGNITION_FAILED
COLUMN_RECOGNITION_FAILED
BEAM_RECOGNITION_FAILED
```

這些 code 至少有一條現有來源包含 `primary`、`provisional`、`identity`、`unique`／`competing`、`staged finalization`、reason token、exception representation 或除錯欄位，或使用動態英文 role。Formatter 必須提供穩定白話文案，並保留該 code 可取得的構件 ID、來源 handle、量測值與單位。

#### 分類三：已知 fallback（2 個）

```text
BIM_JOIST_RECOGNITION_FAILED
BRACE_TERMINAL_VERDICT_MISSING
```

`BIM_JOIST_RECOGNITION_FAILED` 是 joist router 缺少更具體 code 時的防禦性診斷；`BRACE_TERMINAL_VERDICT_MISSING` 代表內部流程未產生可供使用者判讀的 terminal verdict。兩者沒有足夠穩定的使用者工程事實，採安全 fallback。

#### Fallback 決策：採選項 A

| 選項 | 量測值保留 | 內部術語外露 | 決定 |
| --- | --- | --- | --- |
| A. 通用說明＋構件 ID＋來源 handle | 原始 message 中未結構化的量測值不顯示；定位資訊保留 | 最低，不顯示 reason token、exception 或程式詞彙 | **採用** |
| B. 通用說明＋原始 message | 可保留原始 message 內的量測值與除錯細節 | 可能暴露內部狀態、英文詞彙及例外內容 | 不採用 |

Fallback 使用 `role + severity` 形成一般中文類型，例如「圍令檢核錯誤」或「構件檢核警告」，並顯示通用說明、可取得的構件 ID、來源 handle 與現有工具範圍內的建議。Fallback 不附原始 message，也不顯示 raw code；診斷仍建立 `ProblemRecord`，原始 structured fields 繼續供程式判斷與內部追查。

原因：固定分類可讓文案選擇可 review、可測試，避免相同 code 因不同 message 字串走不同路徑。Fallback A 優先避免將未知例外或內部術語帶回使用者介面；代價是未知診斷若只把量測值寫在原始 message 中，畫面不會顯示該量測值。

### Decision 4：Dialog 只呈現投影

`DXFImportDialog` 的全部問題清單與選取項目明細都顯示同一個 `ProblemRecord` 的中文類型與 description；不得在兩個 refresh path 各自建立 mapping。等級欄仍由既有 severity 決定，component／source 定位仍使用 record 的 structured identity。

`review_item_guidance()` 繼續以 record code、item role 與 item status 選擇建議，但輸出必須通過相同用語規範。Dialog 不解析 code 名稱、不從中文文字判定可用工具，也不保存另一份 description。

原因：Dialog 的責任是 Treeview projection 與 interaction；把語意 mapping 留在問題投影，可維持 `DXF Presentation → DXFReviewWorkflow → Recognition／Pure Operations` 的既有方向。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer responsibility 或 dependency direction**。

- **DXF recognition／validation**：仍產生 authoritative `ValidationMessage`；不因 UI 文案重算工程狀態。
- **DXF workflow／models**：仍擁有 problems／ReviewItems；若 `ProblemRecord` 增加顯示欄位，它是 runtime-only projection DTO，不是新的正式 state。
- **DXF Presentation**：`dialog.py` 只讀取顯示欄位，不新增 code-to-behavior 判斷。
- **Dependency direction**：Dialog 依賴 workflow projection；projection 讀取 structured diagnostics。Recognition 不依賴 Dialog、Tkinter 或新的 Presentation module。

問題類型 catalog 與 formatter 不得 import Dialog／Tkinter，也不得讀取 Project、Solver 或 persistence state。Boundary tests 應確認本 change 未新增反向依賴。

## 相容性與 persistence

- `ValidationMessage` 的既有 fields、code values 與 `DXFImportResult` 行為保持相容。
- `ProblemRecord` 若增加欄位，應以 repository 內所有直接建構點及 tests 一併更新；它不是公開 persistence schema。
- Paused Review state、Project JSON、DXF source metadata 與 exported files 不增加欄位，也不需要 migration。
- 舊 Project／paused Review 載入後會以目前 code 重新建立顯示投影，因此自然取得新文案；durable engineering data 不變。

## 其他顯示位置調查（只回報，不納入本 change）

本次 scope 仍只包含「全部問題清單」與選取項目的問題／處理建議。下列位置可能顯示相同 diagnostic code 或 message，但本 change 不修改：

| 類型 | 調查結果 | 程式位置 |
| --- | --- | --- |
| 圍令接觸調整狀態與對話框 | 預覽狀態列、錯誤對話框與調整報告會直接使用 `ValidationMessage.message` | `dxf_import/dialog.py:4506-4580`、`dxf_import/waler_contact_adjustment.py:1729-1797` |
| 候選點套用狀態與對話框 | 驗證失敗及 warning 確認會直接顯示原始 message | `dxf_import/dialog.py:4885-4905` |
| 構件「辨識警告」欄 | `member.warnings` 直接顯示；目前 `DUPLICATED_COMPONENT` 會以 raw code 寫入 | `dxf_import/recognition.py:1576`、`dxf_import/dialog.py:4054-4057` |
| 開發者模式原始 JSON | 顯示 `to_debug_dict()`，其中 `validation_messages` 同時包含 code 與 message | `dxf_import/dialog.py:1982-1984,2221`、`dxf_import/models.py:1439-1464` |
| Project／paused Review persistence | `dxf_import_state.validation_messages` 保存原始 code 與 message；這是既有 persistence，不是新的使用者顯示入口 | `dxf_import/review_workflow.py:1290-1314`、`bracing_optimizer/application/project_service.py:409-415` |
| `DXFImportResult.warnings` helper | 會組成 `code: message`；目前 repository 內未找到正式 UI caller | `dxf_import/models.py:1180-1186` |
| 阻擋匯入的 row mapping 例外 | `to_project_rows()` 在被錯誤呼叫時會列出 raw error codes | `dxf_import/models.py:1292-1294` |
| 問題統計、狀態列、匯入前確認 | 全部問題標頭、底部狀態及「完成匯入前確認」只顯示 severity 數量與未確認數量，不顯示 diagnostic code/message | `dxf_import/dialog.py:2023-2040,2592-2623,6651-6667`、`dxf_import/review_workflow.py:1277-1288` |
| 成果匯出 | 未發現 Excel／成果 DXF 匯出 diagnostic code 或 message；Project JSON persistence 如上另列 | `main.py:3486-3738`、`bracing_optimizer/infrastructure/dxf_result_export.py` |
| Log／console | `dxf_import` 未發現把 `ValidationMessage` 寫入 logger、console 或獨立 log 檔的路徑 | `dxf_import/` 全模組搜尋結果 |

這些旁路不改用本 change 的投影，也不因本次實作順便整理。若後續希望統一其中任一位置，應另立 change，重新確認該位置是否需要 raw diagnostic 資訊。

## 驗證策略

- Producer inventory tests：收集直接 `ValidationMessage` code、間接 recognition outcome code 與 importer role 動態展開，斷言 88 個已知 code 與三分類聯集完全相等、三集合互斥；加入未分類 code 時測試必須失敗。
- Projection unit tests：固定分類不依 message 內容改變；已知 code 的中文類型、專用 formatter 內部術語移除、保留原文／formatter 定位與量測資訊，以及 fallback A 的通用說明、構件 ID、來源 handle。
- Shared rendering tests：全部問題清單與選取項目明細顯示相同 type／description，且不直接顯示 raw code。
- Invariance tests：投影前後 severity、code、role、handles、member IDs、排序與 blocking count 不變。
- Focused regression：`tests/test_dxf_review_items.py`、`tests/test_dxf_review_layout.py`、`tests/test_dxf_review_workflow.py`。
- Boundary regression：`tests/test_dxf_module_boundaries.py`。
- OpenSpec：對本 change 執行 strict validation，再視影響範圍執行既有 DXF Review regression。

## Risks / Trade-offs

- **[文案 catalog 漏掉新 code]** → Runtime 使用 fallback A 保留診斷與定位；producer inventory test 同時失敗，要求開發者正式分類。
- **[白話化時遺失重要數值或定位資訊]** → formatter 優先使用 structured fields；必要時只允許對該 code 的穩定來源格式做具測試的精確擷取，並保留正式 ID／來源 handle／量測值投影測試。
- **[來源 message 與 catalog 漂移]** → code 仍是 identity；專用 formatter 測試以 structured inputs 驗證，不解析不穩定 exception 文字。
- **[過度抽象造成維護負擔]** → 限定在既有 `validation.py` projection boundary，不導入 i18n framework 或跨應用訊息系統。
- **[Fallback A 不顯示只存在原始 message 的量測值]** → 保留 component／source 定位、severity 與 code 供內部追查；需要量測值的高頻 code 必須改列專用 formatter，不得把 raw message 帶回 UI。

## Migration Plan

1. 先加入 producer inventory、三分類完整性、顯示 projection 與 fallback A tests，再建立中文類型／說明 mapping。
2. 切換兩個問題區域使用同一份投影，保留所有 structured diagnostic fields。
3. 執行 focused、boundary 與 OpenSpec regression；確認數量、分級、blocking 與定位不變。
4. 本 change 無資料 migration。若需要 rollback，只需還原顯示投影與 Dialog 欄位取值；已保存 Project／Review state 不受影響。

## Rejected Alternatives

- **直接把所有 diagnostic code 改成中文**：拒絕，會破壞穩定 identity、測試與問題追查。
- **只逐一修改診斷來源的 message 字串**：拒絕，無法處理 UI 直接顯示 raw code，也無法為未來 code 提供一致 fallback。
- **在兩個 Treeview refresh path 各自翻譯**：拒絕，會產生兩份 mapping 並造成顯示 drift。
- **以 regex 全域替換英文術語**：拒絕，可能誤改構件 ID、source handle、數值或不同語境下的工程詞彙。
- **導入完整 i18n／localization framework**：拒絕，本次只有單一 DXF Review 診斷介面，收益不足且超出 scope。
