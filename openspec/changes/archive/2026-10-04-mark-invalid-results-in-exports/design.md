# Design

## 閱讀導航

| 優先級 | 文件／Decision | 何時閱讀 | 閱讀目的 |
| --- | --- | --- | --- |
| P0 現在必讀 | Decision 1 | 所有實作者 | 先建立唯一的 export legality projection，避免兩個 exporter 各自解讀結果 |
| P0 現在必讀 | Decision 2 | 修改 Excel contract／tests 前 | 確認新增欄位、原因 fallback 與 staged workbook 驗證 |
| P0 現在必讀 | Decision 3 | 修改 DXF contract／tests 前 | 確認 warning layer、文字、定位與暫存檔重讀驗證 |
| P1 實作前閱讀 | 兩份 delta specs 與 `tasks.md` 第 1～3 節 | 開始對應 task group 前 | 對照精確行為與驗證條件 |
| P2 條件式閱讀 | 主 `dxf-result-export` spec 的來源保護、result-only 結構與 atomic write Requirements | 觸及 source-backed／result-only 共用 pipeline 時 | 保持既有座標與失敗安全 |

**可先跳過**：Solver legality 計算、DXF recognition／Review 與 Project persistence；本 change 只投影已 committed 結果，不改這些 owner。

## 方案摘要

由 Application 將 Support／Waler 正式結果轉成共用 export legality projection，包含 member identity、valid 與 ordered reasons。Excel 與 DXF exporter 只負責格式呈現：Excel 在材料明細末端增加兩欄；DXF 對每個 invalid member 建立 `SD_WARNING_INVALID_RESULT` 紅色 warning text，並以 `SD_WARNING_CJK` 文字樣式引用新細明體。兩種 exporter 都不重算工程規則。

## 決策對照

| Decision | 選擇理由 | 被拒絕替代方案 | 對應 Requirement | 對應 task |
| --- | --- | --- | --- | --- |
| D1. Application 建立 export legality projection | `ProjectResultModel` 擁有 committed result，最適合統一 Support／Waler 差異 | 由 Excel、DXF 各自讀任意 result dict；會形成兩套 truth | Excel「沿用正式結果合法性」、DXF「兩種模式使用相同警告契約」 | 1.1～1.2 |
| D2. Excel 在材料明細末端增加兩欄 | 保留既有前十欄順序，並讓每個實體材料列可追溯所屬方案風險 | 只在彙總表寫一次；無法對應個別構件 | Excel「每筆匯出配置包含合法性欄位」 | 2.1～2.2 |
| D3. DXF 使用獨立紅色 annotation layer | 警告可切換、可檢索，且不改變工程幾何語意 | 將既有成果幾何改紅或複製整支構件；會混淆成果與警告 | DXF「不合法配置在專用警告圖層標示」 | 3.1～3.2 |

## Context

`ProjectResultModel` 已保存 Support plan 的 `valid`／`reason`；人工修改後的 Waler `selected_plan` 則保存 `legality.valid`／`legality.violations`。Support persistence 在 `valid` 缺失時補為 false；Waler payload 維持原樣，但結果樹在顯示人工結果時以 `legality.valid` 優先、`plan.valid` fallback，兩者皆缺失則視為 false。材料摘要不解讀 validity，而是持續彙總所有可見方案。現有 Excel exporter 接收材料明細，DXF exporter 接收 `MemberExportPlan` 並已具備 result geometry、圖層與 source-backed／result-only 分流，但兩者未攜帶 invalid 狀態。

本 change 中：

- **export legality projection**：Application 從 committed result 建立的唯讀、逐構件合法性資料，不是新的工程判斷。
- **ordered reasons**：依 committed payload 原有順序正規化的可顯示原因；不排序、不重新執行 evaluator。
- **warning annotation**：位於專用 DXF layer 的文字實體，不是構件幾何，也不改變原成果顏色。

## Goals / Non-Goals

**Goals:**

- 讓每個匯出構件使用相同的 committed validity 與原因。
- 保留 invalid result 可匯出的現行 workflow。
- 保持現有 atomic output 與來源 DXF 不變性。

**Non-Goals:**

- 不修改 Solver issue taxonomy 或合法性。
- 不新增匯出前確認、阻擋或 Project schema 欄位。
- 不在 DXF 改變構件顏色或幾何以代表 invalid。

## Architecture Alignment

本 change 沿用既有 Architecture。Application／ProjectResultModel 負責把正式結果轉成 exporter contract；Infrastructure 的 Excel／DXF adapters 負責檔案格式。Presentation 只選擇輸出範圍與回報成功／失敗。工程合法性不下放到 Infrastructure。

| Layer | 本次責任 | Dependency direction |
| --- | --- | --- |
| Presentation（`main.py`） | 選擇目前可見成果、取得 Application projection、呼叫 terminal exporter、顯示 outcome | 沿用 `Presentation → Application`，以及既有 `Presentation → terminal Infrastructure adapter` 例外 |
| Application（`ProjectResultModel`） | 從 committed result 建立逐構件 legality projection | 只讀既有 Algorithms result payload；不依賴檔案格式 |
| Infrastructure（Excel／DXF exporter） | 將 projection 呈現為 workbook 欄位或 DXF annotation，並驗證 staged file | 沿用 Infrastructure 使用 selected Application DTO 的既有例外；不反向定義工程規則 |

Manual editing 仍只負責產生並 commit validity payload；結果 diagnostics 與材料 summary 仍是 read-only projection。它們與 exporter 都不得另建合法性 evaluator，因此不形成第二套 truth。

## Decisions

### Decision 1: 建立共用且唯讀的 export legality projection

projection 對每個實際匯出 member 提供 `member_kind`、stable identity、`valid` 與 ordered display reasons。single source of truth 是 committed result payload；projection 只做正規化與關聯，不重新呼叫 evaluator。幾何 anchor 仍由 DXF exporter 的既有 `MemberBinding` 計算，Application 不建立第二份座標 truth。

Support group-level result 與 individual plan validity 需分開：文字標示以實際輸出 member plan 為準，不能只用整組 summary。Support 沿用現有結果樹語意：`valid` 缺失等同 false；只有 `bool(valid)` 為 true 且 `reason` 為空時才是合法，`valid=True` 但 `reason` 非空仍是不合法。

Waler 沿用現有結果樹語意：若 `legality` mapping 明確包含 `valid` key，`legality.valid` 是 authoritative value；只有該 key 缺失時才 fallback 到 `plan.valid`，兩者都缺失時視為 false。當 `legality.valid` 與 `plan.valid` 同時存在但互相矛盾時，必須以 `legality.valid` 為準。原因優先使用 `legality.violations`；只有相容既有 payload 時才 fallback 到 plan 的 `errors`。這些 fallback 只解讀已保存資料，不推導工程規則。

材料摘要與既有 export scope 仍包含所有可見方案，不因合法、非法或 `valid` 缺失而篩除構件；legality projection 只增加狀態與原因，不改變材料數量或匯出範圍。

原因正規化會去除空白項目、保留首次出現順序並移除完全重複文字。若 `valid` 為 false 但沒有可顯示原因，projection 使用固定文字「未提供不合法原因」；它明確表示資料缺失，不猜測原因，也不阻擋原本可匯出的 invalid result。

拒絕讓兩個 exporter 各自讀任意 dict 欄位，因為會形成兩套 fallback 與 reason 排序。

### Decision 2: Excel 欄位加在逐構件明細

「是否合法」與「不合法原因」附加在材料明細既有十欄之後；同一 member 的每個材料列沿用相同 legality projection。材料彙總不重複推導合法性。合法列輸出「合法」且原因留白；invalid 列輸出「不合法」並以換行合併完整 ordered reasons。既有欄位名稱與順序保留，新增欄位屬 additive compatibility change。

Excel exporter 繼續先完成 workbook staging，再重讀確認欄名、列數、合法性值與原因內容，最後才取代目的檔。任何 contract 或寫檔錯誤不得留下部分檔案。

### Decision 3: DXF warning 是獨立 annotation layer

新增 `SD_WARNING_INVALID_RESULT` layer，layer ACI color 設為 `1`（red），annotation entity 使用 `BYLAYER`。現有 `SUPPORT_SEGMENT` dimension style 沒有明確中文字型，而且實際 render 的 MTEXT 使用 `OpenSansCondensed-Light`，因此不可宣稱它支援中文。Warning annotation 改用專用 `SD_WARNING_CJK` text style，font family 為新細明體（`PMingLiU`）、DXF font file reference 為 `mingliu.ttc`。字型檔不嵌入 DXF；目標 Windows／CAD 環境必須安裝新細明體。

每個 invalid member 產生恰好一個可閱讀的 MTEXT annotation，內容含 member identity 與 ordered reasons。雙路支撐仍是兩支實體 Strut，因此每支 invalid Strut 依自己的 member identity 與 `MemberBinding` 各產生一筆 warning，不得用 shared-layout group 合併。

基準 anchor 使用 `MemberBinding` 工程線中點。令正規化 member direction 為 `(dx, dy)`，固定使用其左法向 `(-dy, dx)` 作為偏移方向，基準位置為中點加上 `WARNING_TEXT_OFFSET_MM`。Warning 依 `(role, member_id, result_id)` 穩定排序；若候選文字位置落入先前 warning 的 `WARNING_TEXT_COLLISION_RADIUS_MM`，沿同一左法向以 `WARNING_TEXT_STACK_SPACING_MM` 的整數倍逐步外移，直到不再衝突。所有偏移量與碰撞距離都必須是具名常數，不得在 builder 或測試中散落匿名數字。

無法取得 binding／anchor 或 member 長度為零時 export 應明確失敗，不可把警告放到任意原點而誤導。全部構件合法時不建立 warning layer 或 warning entity。

source-backed 與 result-only 共用同一 annotation builder。annotation 帶有可驗證的 app XDATA identity；builder 同時建立 expected anchor，暫存 DXF 重讀後以具名 `WARNING_ANCHOR_TOLERANCE_MM` 驗證實際 insertion point，並驗證 layer、有效紅色、member identity、文字內容、entity 數量、entity 使用的 text style，以及 `SD_WARNING_CJK` style 的 `mingliu.ttc` font reference。驗證與碰撞處理不得共用匿名 tolerance。驗證失敗沿用既有 diagnostic-temp 與不取代 destination 語意。Source-backed 只改輸出 document，不讀寫原始 DXF；result-only 在新 drawing 建立相同 layer、style 與文字。

## Source of Truth

- valid／issues：ProjectResultModel 中的 committed result。
- member geometry anchor：DXF exporter 已解析的 `MemberBinding`。
- layer name／color／text style／offset／collision spacing／anchor tolerance：DXF exporter 具名常數與單一 builder。

## Backward Compatibility / Persistence

Project JSON 不變，也不做 schema migration。Excel 在現有欄位後增加欄位，既有消費者若依欄名讀取不受影響；依固定總欄數的外部流程需在 release note 說明。DXF 只在存在 invalid member 時新增 annotation layer 與 `SD_WARNING_CJK` text style，不更改既有 result layers、dimension style、成果幾何或來源實體；字型不隨 DXF 封裝，開檔環境缺少新細明體時由 CAD 的字型替代政策處理。

## Risks / Trade-offs

- [長 reason 遮住圖面] → 使用 MTEXT 寬度與穩定 offset，測試多原因輸出。
- [相鄰或雙路構件的 warning 重疊] → 以穩定排序及具名 spacing 常數沿各自左法向逐步外移，並測試輸出 deterministic。
- [group validity 誤套到 member] → projection 測試混合合法／不合法 plans。
- [Excel 列重複導致狀態不一致] → 同一 member identity 的所有材料明細沿用同一 projection。
- [legacy invalid payload 沒有原因] → 使用固定缺失提示，不重算或捏造工程原因。
- [目標 CAD 缺少新細明體] → DXF 明確保存 `SD_WARNING_CJK`／`mingliu.ttc` contract；不嵌入 Microsoft 字型，部署說明列出目標環境依賴。

## Migration Plan

先新增 projection 與單元測試，再接 Excel，最後接兩種 DXF 模式及重讀驗證。沒有資料 migration；rollback 僅移除新增欄位與 annotation builder，不轉換 Project 檔。
