# Design

## 閱讀導航

- **P0 現在必讀**：「方案摘要」、「決策對照」與 Decisions 1～4；它們定義 overlap qualification、warning／blocking 分層、正式線狀態與責任邊界。
- **P1 實作前閱讀**：[dxf-waler-overlap-diagnostics](specs/dxf-waler-overlap-diagnostics/spec.md) 全文，以及 [dxf-waler-contact-face-recognition](specs/dxf-waler-contact-face-recognition/spec.md) 的「Unresolved Waler 不得產生正式接觸面」。
- **P1 實作前閱讀**：`dxf_import/waler_contact_face.py`、`dxf_import/recognition.py::_resolve_waler_contact_geometry()`、`dxf_import/importer.py::_make_waler()` 與 `dxf_import/dialog.py::_preview_member_styles()`。
- **P2 需要時再讀**：`dxf_import/review_workflow.py` 與 [dxf-review-engineering-data-presentation](specs/dxf-review-engineering-data-presentation/spec.md)；只有修改 exclusion／Pause／Resume／Review projection 時才需要。
- **可先跳過**：Solver、Project schema、材料規則與 CornerBrace repair；本 change 不改這些 contract。

## 方案摘要

在既有 Waler contact-face resolution 前後加入一條單一、可追溯的 staged truth：純幾何層只從各 Waler 的可靠、非零長度 source-supported provisional axis 建立 pairwise overlap facts，並以正有限投影重疊長度除以較短 provisional axis 的有限長度。既有 terminal topology／contact-face resolution 再以 direct identity provenance 決定 overlap 是否真的造成 competition。所有合格 overlap 產生 warning；只有同一 terminal 或同一 contact-face finalization 明確把 overlap pair 的兩個完整 identities 列為實際競爭者時，才另產生 blocking error。

Contact-face resolution 是否成功會明確寫成 DXF Review model 的 `formal`／`provisional` 狀態。Preview 只依這個狀態選擇樣式，不從 handle、辨識方法、selected candidate 或錯誤文案重新推理。排除、還原與 rebuild 均重新跑同一 recognition pipeline；不保存或重播 stale overlap pair。

此設計不合併 Waler、不挑選 winner、不放寬既有 ambiguity，亦不改 Project row 或 Solver input。新增的狀態只存在 DXF import／Review staging model 與其 debug snapshot。

## 決策對照

| Decision | 對應 Spec Requirements | 對應 Tasks |
| --- | --- | --- |
| D1. 只以可靠有限 provisional axis 建立 canonical overlap fact | `dxf-waler-overlap-diagnostics`：重大共線重疊必須產生來源診斷 | 1.1、2.1、2.2 |
| D2. 以 direct identity provenance 區分 warning 與 blocking competition | `dxf-waler-overlap-diagnostics`：競爭關係必須升級為 blocking error | 1.2、2.3、3.2 |
| D3. Contact-face resolution 是 formal／provisional 的唯一權威 | `dxf-waler-contact-face-recognition`：Unresolved Waler 不得產生正式接觸面 | 1.3、3.1、3.3 |
| D4. Preview／Review 僅投影 staged truth | `dxf-review-engineering-data-presentation`：Preview 必須區分正式接觸面與 provisional axis；Review 必須呈現重疊來源與重建資訊 | 1.4、4.1、4.2 |
| D5. Lifecycle 一律從 active sources 重建 | `dxf-waler-overlap-diagnostics`：診斷必須隨 Review truth 重建；`dxf-waler-contact-face-recognition`：排除競爭來源後必須重新 finalization | 4.3、4.4 |
| D6. 以純幾何邊界、identity provenance 與 Y29 regression 鎖定行為 | 三個 capability 的所有 Scenarios | 1.1～1.4、5.1～5.4 |

## Context

Y29 的 W17（source handle `69C`）與 W20（`721`）具有近乎相同的上下邊界與中心軸，只有水平起訖略有差異。現行 `build_member_terminal_evidence()` 已保守地建立 `AMBIGUOUS_WALER_CONNECTION`，而 `resolve_waler_contact_faces()` 也會產生 `WALER_CONTACT_FACE_UNRESOLVED`；因此目前的工程判定沒有任意選擇 winner。

缺口有兩個：第一，Review 沒有一個直接描述 W17／W20 幾何重疊的來源級診斷，使用者只能由下游 terminal ambiguity 反推根因。第二，`_Candidate` 與 `Waler` 沒有表達 contact-face finalization 狀態，`dialog.py` 因而把所有 Waler 都以相同的綠色實線繪製；`recognition_method == "closed_outline_axis"` 與 `selected_candidate_id` 也不足以判斷正式性，因為成功選面後仍可能保留相同辨識方法。

相關架構的既有責任如下：

```text
Presentation (dialog / preview)
  -> DXFReviewWorkflow snapshot / DXFImportResult
  -> recognition orchestration
  -> waler_contact_face pure geometry and topology facts
  -> models / geometry
```

`DXFReviewWorkflow` 擁有目前 active sources、WCS `world_result`、problems 與 review items；Presentation 只讀 snapshot。`DXFImporter.convert()` 雖同時協調 reader 與 recognition，是既有 accepted debt，本 change 不藉機重構。Project／Solver 只應接收完成 Review 後的正式 Waler engineering line。

## Goals / Non-Goals

**Goals**

- 對不同 Waler source identities，只以各自可靠且非零長度的 source-supported provisional axis 計算有限共線重疊，並對 ratio `>= 50%` 建立 deterministic、source-localized fact 與 warning。
- 只在同一 terminal／contact-face finalization 的 direct provenance 同時列出 overlap pair 的兩個完整 identities 時，新增 blocking competition error。
- 讓 formal contact face 與 provisional axis 成為明確、單一來源的 staged state，供 validation 與 Preview 共用。
- 讓排除／還原、Pause／Resume、rebuild 與 manual override replay 只反映目前 active facts。
- 用 Y29 W17／W20、50% 邊界與非重疊案例鎖定行為及順序不變性。

**Non-Goals**

- 不自動合併、刪除、重命名或挑選任何重疊 Waler。
- 不以 ID、handle 排序、entity order、距離微差、first match 或 Preview selection 解決 ambiguity。
- 不變更 terminal ranking、contact-face 選面規則、Project schema、Solver input 或 Solver 行為。
- 不把所有平行、相交、相鄰 envelope 或低於 50% 的短重疊都視為本診斷。
- 不在本 change 重構 `DXFImporter.convert()` 或建立新的持久化資料庫格式。

## Decisions

### Decision 1：由純幾何層建立 canonical Waler overlap fact

在 `dxf_import/waler_contact_face.py` 新增 immutable overlap fact 與純函式。輸入沿用 `build_waler_envelope_facts()` 已建立的 `WalerEnvelopeFacts`，但只有其 `provisional_axis` 有來源幾何支持、可靠且非零長度時才能參與。若任一方不符合，該 pair 不建立本 capability 的 overlap fact；既有 recognition、terminal topology 與 contact-face diagnostics 照常保留。

本 decision 中的長度具有唯一來源：

```text
overlap_ratio =
    positive finite projected overlap length
    / min(provisional_axis_length_a, provisional_axis_length_b)
```

分子與兩個分母都由兩支 source-supported provisional axes 的有限區段導出。Finalized contact face、envelope 周長、outer-face／外框單邊、bounding box、Project row engineering line 與無限 supporting line 均不得代替任何長度。Supporting line 只用來測試共線性，沒有可作為 overlap 分子或分母的無限長度。

每一 pair 的計算順序為：

1. 排除相同或共享 source identity，以及缺少來源支持、可靠性不足或 provisional axis 有限長度為零的 facts；不建立 overlap fact，但不吞掉既有 diagnostics。
2. 以既有平行角度容差判斷方向平行，並以既有共線距離容差判斷 supporting lines 共線。
3. 將兩有限區段投影到 canonical unit axis，計算正 overlap interval。
4. 以 `positive_finite_projected_overlap_length / min(provisional_axis_length_a, provisional_axis_length_b)` 計算比例；`>= 0.50` 合格，零長度與 `< 0.50` 不合格。
5. 回傳 canonical pair key、兩方完整 source identities、有限 overlap segment、長度與比例。端點方向反轉或輸入 collection 排序只能改變顯示順序，不得改變工程結果。

pair enumeration 可用 identity 的穩定排序消除重複輸出，但該排序只用於 canonical serialization／diagnostics，不用來選擇 winner。容差由現有 `RecognitionTolerances` 傳入，不新增未命名 magic number；`0.50` 以具名 overlap ratio threshold 表達。

這個 pure function 不依賴 Review、Tkinter、Project 或 Solver，並以單元測試直接覆蓋 provisional-axis 分母、exact-50%、略低於門檻、端點相接、零長度、unreliable／unsupported axis、非共線相交、橫向相鄰、端點反轉及 pair permutation。

### Decision 2：Overlap warning 與 competition blocking error 使用同一組事實，但分開判定

每個合格 `WalerOverlapFact` 都投影成一筆例如 `WALER_SOURCE_OVERLAP` 的 warning，包含雙方 source handles、overlap segment、length 與 ratio。Warning 單獨存在時不影響 `can_import`。

Blocking 不重新執行另一套 proximity 或 terminal matching。`_resolve_waler_contact_geometry()` 會將每個 overlap pair 的兩個**完整 Waler source identities**與既有 direct provenance 做 identity-set join。只有以下任一證據成立，才投影例如 `WALER_OVERLAP_COMPETITION` 的 error：

1. 同一筆 `TerminalTopologyIssue` 具有明確 terminal identity，且其 `competing_waler_source_handles` 同時包含 overlap pair 的兩個完整 identities。
2. 同一筆 contact-resolution outcome 具有明確 finalization context，且直接列出 overlap pair 的兩個完整 identities 同時為該次 finalization 的實際 competitors。

Join 條件是「pair 的 A 與 B 同時屬於同一 direct competing identity set」，不是「A／B overlap 且附近或同批存在 unresolved」。若 contact-resolution issue 只說 unresolved、沒有同一 finalization 的兩方 identity provenance，它不能升級任何 pair。若 A／B overlap、實際 competing set 是 A／C，A／B 只保留 warning；只有另有合格 A／C overlap fact 時，A／C 才可能依 direct provenance 升級。

Error 保留兩方 Waler identities、同一 terminal／finalization identity 與受影響 member source handles，同時保留既有 `AMBIGUOUS_WALER_CONNECTION` 和 `WALER_CONTACT_FACE_UNRESOLVED`，不取代或吞掉原診斷。

如此 overlap geometry 與 terminal topology 各自只有一套判定邏輯；blocking 是 exact identity provenance join，而不是第三套 candidate ranking。沒有 direct pair provenance、由其他原因造成的 unresolved，或不同 pair 的 competition，均保持 A／B warning-only。

診斷排序以 severity、code、canonical source identity、terminal／finalization identity 與幾何位置穩定化，確保 input/source/entity collection 順序不改變等價結果。排序仍不得影響辨識決策。

### Decision 3：Contact-face resolution 結果是正式線狀態的唯一權威

新增 DXF-review-only 的明確狀態，例如 `WalerContactFaceState`，至少包含：

- `formal`：該 Waler source identity 有成功的 `WalerContactResolution`，且 selected face 已原子地套用至 staged candidate。
- `provisional`：目前只保有來源支持的 provisional axis／envelope，沒有成功 finalization；包含 identity competition、contact-face ambiguity 或其他 unresolved outcome。

`_resolve_waler_contact_geometry()` 在 staged copy 上，依 successful resolutions 設定候選狀態；`_make_waler()` 再將狀態寫入 immutable `Waler` Review model。不得由 `recognition_method`、`selected_candidate_id`、線的位置、warning 字串或 UI selection 推論。這個欄位會進入 `DXFImportResult.to_debug_dict()` 的 Review/debug snapshot，但 `Waler.to_project_row()` 不新增欄位，Project schema 與 Solver input 維持不變。

正式性與 geometry 必須原子一致：只有 resolution 成功、selected face 已套用後才能標為 `formal`；若 recognition 階段發生例外而保留原 staged candidate，狀態必須保持 `provisional`。Validation 仍以既有 blocking messages 控制完成；狀態本身不提供繞過 error 的確認入口。

為避免破壞既有 fixtures 或舊 snapshot recovery，model 需要有明確的相容預設與 hydration 行為，但 recognition 產生的新結果必須一律顯式填入。相容預設只服務舊資料讀取，不能讓新 unresolved Waler 被誤標為 `formal`。

### Decision 4：Recognition 建立 truth，Review／Preview 只做唯讀投影

責任配置如下：

| Layer / module | 責任 | 不負責 |
| --- | --- | --- |
| `waler_contact_face.py` | overlap geometry facts、既有 terminal evidence 與 contact-face resolution | UI wording、Treeview identity、Project/Solver |
| `recognition.py` | 協調 overlap facts 與 topology/resolution outcome、設定 staged contact-face state、建立 validation messages | Preview style、source exclusion workflow |
| `importer.py` / `models.py` | 將 staged candidate 投影為 typed `Waler` 與 `DXFImportResult`，維持 Project row contract | 重算 overlap 或 ambiguity |
| `validation.py` / `review_workflow.py` | 將目前 messages 投影成 problems/review items，依 active source rebuild | 以顯示 ID 推理工程關係 |
| `dialog.py` / Preview | 依 `contact_face_state` 選擇正式或 provisional 樣式，顯示來源、比例、受影響 terminal 與 rebuild 提示 | 幾何 qualification、winner selection、來源排除建議、truth mutation |

Preview 的具體顏色與 dash pattern 保留為 Presentation 細節，但 provisional 樣式必須與正式綠色工程線有清楚差異，且 detail panel 明示「暫定中心軸／尚未完成接觸面」。選取、縮放、平移與 redraw 只能改變顯示，不得修改 `DXFImportResult`。

Review problem 使用 `ValidationMessage.source_handles`／member provenance 定位來源，不使用 Waler display ID、Treeview item ID 或 collection index 當工程 identity。若 warning 與 blocking error 同時存在，兩者可個別呈現或在 UI 群組化，但不得遺失 warning 的 overlap facts、error 的 blocking status、受影響 terminal 或既有 ambiguity codes。Review 只能中性說明 active sources 變更後會重新辨識，不得推薦刪除、排除或保留 overlap pair 的任一方。

### Decision 5：Exclusion、Resume 與 manual replay 都以 active source truth 重建

沿用 `DXFReviewWorkflow` 的既有 rebuild 路徑：source exclusion／restore 改變 active geometry 後重新呼叫 importer／recognition，重新列舉 overlap facts、terminal topology、contact-face resolutions 與 formal/provisional state。不得從上一輪複製 overlap pairs 或因上一輪曾成功 finalization 而保留正式線。

Pause snapshot 可序列化新的 Review-only state 以供顯示與診斷；Resume／compatible recovery 的工程 truth 仍由目前 active sources 重新辨識。Manual override replay 只對目前 canonical members 套用既有、仍相容的使用者決策，不能把舊的 provisional axis 升級為 formal，也不能重建已排除來源的 identity。

排除 `69C` 時，pair diagnostics 消失且 `721` 由目前側向證據重新選面；排除 `721` 時反之。還原來源後必須重新出現目前可證明的 overlap／competition 與 unresolved state。

### Decision 6：以兩層 regression 驗證，且不改 Solver／Project contract

第一層是 `waler_contact_face.py` 的純單元測試，鎖定 provisional-axis 長度來源、reliability gate、exact-50%、略低於門檻、endpoint-only、零長度、容差、canonicalization 及順序不變性，並加入 A／B overlap + unrelated unresolved、A／B overlap + A／C competition、A／B direct competition 三組 identity provenance cases。第二層是 importer／Review integration regression，直接使用 `Y29_test.dxf` 驗證 handles `69C`／`721` 同時存在與 active source 變更後的結果，並確認 Preview projection 與 blocking semantics。

一般非重疊 contact-face fixtures、Y05／Y1A 既有案例仍需執行，確保沒有因新增 state 或 warning 改變正式選面。Project row regression 應確認 `to_project_row()` key set 不變；不執行或修改 Solver algorithm 測試以掩蓋 DXF 問題。

## Architecture Alignment

- **Dependency direction**：Presentation 仍只依賴 Review snapshot／models；recognition 與 pure geometry 不依賴 Tkinter、Review widget 或 Project UI。
- **Canonical truth**：WCS envelope／provisional axis、terminal topology、contact resolution 與 active source identities 是唯一工程來源；overlap fact 和 `contact_face_state` 是其明確衍生結果。
- **No second truth**：Preview 不由畫面線段或 messages 重算正式性；validation 不另做 geometry matching；blocking join 不重跑 terminal ranking。
- **Reuse over restructure**：沿用 `WalerEnvelopeFacts`、`TerminalTopologyIssue`、`WalerContactResolution`、`ValidationMessage`、`DXFReviewWorkflow` rebuild 與既有 problem projection，只加最小 typed facts／state。
- **Boundary preservation**：新增欄位停留在 DXF import／Review model；`Waler.to_project_row()`、Project schema、Solver input 與 scoring 不變。
- **Accepted debt**：不處理 `DXFImporter.convert()` 的既有協調責任，也不藉機拆分整個 recognition pipeline。

## Alternatives Considered

### 以 `recognition_method == "closed_outline_axis"` 判斷 provisional

拒絕。排除其中一個來源後，成功選出外側接觸面時 recognition method 仍可能保持 `closed_outline_axis`；此方法會把辨識來源與 finalization outcome 混為一談。

### 由 Preview 搜尋 `WALER_CONTACT_FACE_UNRESOLVED` messages

拒絕。Presentation 會建立第二套 source-to-message 關聯，容易在 rebuild、ID renumber 或新 error code 時失真，也讓 UI 決定工程 truth。

### 任何 50% overlap 一律 blocking

拒絕。幾何重疊可能沒有 terminal competition；一律阻擋與已確認的 warning／error 分層不符。Blocking 必須有既有 topology／contact-face outcome 支持。

### 對重疊 Waler 自動合併或挑一支

拒絕。來源 identities 是不同 DXF evidence，handle、順序、距離微差與 first match 都不是可接受的工程證據，且會掩蓋使用者應審查的 ambiguity。

### 比較 finalized contact faces 判定 overlap

拒絕。Overlap 是 contact-face finalization 的上游根因；使用下游 selected face 會形成循環，並使 unresolved Waler 無法產生診斷。應使用來源支持的 provisional axes。

### 以 envelope、bounding box 或無限 supporting line 決定 ratio 分母

拒絕。這些長度不等於 source-supported provisional axis 的有限工程範圍，會讓相同來源因外框表示法或下游投影不同而改變門檻。Supporting line 只用於共線測試；ratio 的分子與分母都必須回到兩條有限 provisional axes。

### 以 overlap 加 generic unresolved 推論 blocking

拒絕。Unresolved 可能來自缺乏側向證據、其他 Waler pair 或其他 recognition failure。沒有同一 terminal／finalization 同時列出 A、B 的 direct identity provenance，不得把 A／B warning 升級。

## Risks / Trade-offs

- **Tolerance 邊界可能放大浮點誤差**：沿用現有平行／共線 tolerance，投影前 normalize direction，分子與分母均從原始有限 provisional axes 計算，測試 exact 50% 與門檻兩側 epsilon；不得用 round-to-display 值做資格判斷。
- **同一根因產生多筆既有錯誤**：保留 overlap、terminal ambiguity、contact unresolved 的不同語意，透過 deterministic code／source keys 允許 UI 群組，而不是刪除資訊。
- **新增 model state 影響 debug serialization**：使用穩定字串值與相容 hydration/default，並以 round-trip／Resume focused test 驗證；Project row 明確排除該欄位。
- **大型圖面 pairwise 比較成本**：先以現有 Waler 數量採 deterministic pair enumeration；若實測成為瓶頸，未來可在不改 contract 下加入 bounding projection broad phase。本 change 不先引入空間索引複雜度。
- **Contact unresolved 原因不一定是 overlap**：blocking join 僅接受同一 terminal／finalization 同時列出 pair 兩個完整 identities 的 direct provenance；A／B 與 unrelated unresolved、A／C competition 都以負向測試避免誤歸因。

## Migration Plan

1. 先加入 pure overlap fact 與邊界測試，不連接 UI；現行 importer 行為維持。
2. 將 overlap facts、warning／blocking join 與 explicit contact-face state 接入 staged recognition，補 Y29 importer regression。
3. 將 ValidationMessage 投影與 Preview／detail style 改為消費新 state，補 Review lifecycle 與 presentation tests。
4. 執行非重疊 contact-face、Y05／Y1A、Pause／Resume、manual replay、Project row 與 architecture boundary regressions。
5. 若需 rollback，可先撤回 Preview 消費與 diagnostics projection，再撤回 typed state／overlap helper；因 Project schema 與 Solver input 未變，不需要資料 migration 或 Solver rollback。

沒有資料庫 migration。舊的 Pause/debug snapshot 若缺少新 state，走相容讀取後仍須以目前 active sources 重新辨識；不得把相容 default 當成完成正式接觸面的證據。

