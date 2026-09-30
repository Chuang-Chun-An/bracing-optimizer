# Design

## 閱讀導航

| 優先級 | Decision | 何時必讀 |
| --- | --- | --- |
| P0 | Decision 1：單一候選使用方案摘要，多候選沿用選取表格 | 修改 preview window widget 結構與 selection state 前。 |
| P0 | Decision 2：UI 只投影 `CornerBraceRepairPlan`／candidate，不重算工程語意 | 修改任何顯示值、標籤或有效狀態前。 |
| P0 | Decision 3：既有 Review canvas 承載灰色 exact-source overlay | 修改 `_draw_corner_brace_repair_overlay` 與清理生命週期前。 |
| P0 | Decision 4：角撐修補預覽共用三位小數 formatter | 修改表格、摘要、座標或測試預期前。 |
| P1 | Decision 5：稽核／診斷預設收合但持續可取得 | 修改次要資訊顯示或視窗尺寸行為時。 |
| P2 | Architecture Alignment、相容性與風險 | 發現需要跨出 `dxf_import/dialog.py`、修改資料模型或 persistence 時；正常實作可先略讀。 |

## 方案摘要

此 change 沿用既有 `CornerBraceRepairPlan → Toplevel → Review canvas overlay → explicit commit` 流程，只重組 Presentation projection：單一候選直接成為目前方案；主要欄位以摘要區顯示；詳細 provenance 與 diagnostics 放入預設收合且可重新展開的區域；`plan.residual_segments` 以灰色畫回既有 Review canvas；工程長度與定位距離由同一組 formatter 輸出三位小數並帶 `mm`，座標分量輸出三位小數但維持無單位。

```text
CornerBraceRepairPlan（唯一工程 truth）
       ├─ candidates ──→ 候選選取／方案摘要／稽核明細
       └─ residual_segments ──→ Review canvas 灰色來源線
選定 candidate ──→ 藍色建議軸線＋定位錨點
明確按下套用 ──→ 既有 DXFReviewWorkflow commit
```

本 change 中「圍令端定位距離」是 `reference_waler_offset_mm` 的使用者可見名稱；「支撐端定位距離」是 `reference_strut_station_mm` 的使用者可見名稱。介面統一顯示：「量測基準：目標圍令與支撐的交會點；支撐端定位距離沿支撐內側方向量測。」名稱改變不建立新欄位、不更名 DTO／serialized key，也不改變 template transfer 計算。

## 決策對照

| Decision | 選擇原因 | 拒絕的替代方案 | 影響 spec／task |
| --- | --- | --- | --- |
| 1. 單一候選直接顯示摘要；多候選才保留現有選取表格 | 單一候選是常見流程，無需先理解比較表；多候選仍需明確選擇。 | 永遠保留九欄表格：主要與稽核資訊持續混雜；完全移除表格：會破壞既有多候選操作。 | Spec「唯一候選直接顯示建議方案」「使用者選擇多個候選之一」；Tasks 1、2。 |
| 2. 顯示層只讀 plan／candidate | 避免 UI 成為第二套角撐幾何或合法性邏輯。 | 在 UI 重新計算交點、長度或 validity：可能與 planner drift。 | Spec「主要資訊與稽核資訊分層」及不變行為；Tasks 1～3。 |
| 3. 來源線與建議線畫在既有 Review canvas | 現有 transform、zoom、selection 與 temporary overlay lifecycle 已集中於此；不必建立同步的第二張 canvas。 | 在 Toplevel 內新增小型 canvas：需複製座標轉換、縮放與場景資料，易產生兩個 visual truth。 | Spec「以灰色顯示目標來源線段」；Task 3。 |
| 4. 使用 feature-local formatter 固定三位小數 | 表格、摘要與座標得到一致輸出，且只改 presentation。 | 全域修改所有 `_review_display_value`：會擴大到其他 DXF Review 畫面；直接格式化 tuple：無法保證每個分量三位。 | Spec「預覽數值統一顯示三位小數」；Task 1。 |
| 5. 次要稽核區預設收合、可明確展開 | 主要決策保持簡潔，同時保存 provenance 與 diagnostics 可稽核性。 | 永久移除次要資訊：違反既有 preview contract；全部永久展開：仍造成資訊過載。 | Spec「主要資訊與稽核資訊分層」；Task 2。 |

## Context

參見 `proposal.md` 的 Why。目前 `_show_corner_brace_repair_window` 建立一個九欄 `Treeview`，單一候選會自動選取；`_on_corner_brace_repair_candidate_selected` 將相同資料再次組成多行文字；`_draw_corner_brace_repair_overlay` 把 `plan.residual_segments` 畫成橘色虛線、candidate 軸線畫成藍色粗線、錨點畫成橘色圓點。表格長度使用一位小數，明細尺寸使用三位小數，座標則直接輸出 tuple。

`CornerBraceRepairPlan.residual_segments` 已由 exact target source handles 對應的 `SourceGeometry` 產生，是本 change 所稱「該角撐全部來源線段」的既有資料來源；Presentation 不需重新掃描 `result.source_geometry`。`candidate.fixed_length_mm`、local offset／station、references、diagnostics 與位置證據亦已存在於 candidate。

## Goals / Non-Goals

**Goals:**

- 讓單一候選能直接閱讀與採用，但不自動 commit。
- 讓主要工程結果、定位尺寸與次要稽核資料有明確層級。
- 讓使用者能在既有 Review canvas 比較灰色來源線與建議軸線。
- 讓角撐修補預覽內的工程數值與座標一致顯示三位小數。
- 保留多候選既有選取行為與全部稽核資料。

**Non-Goals:**

- 不改動 planner、candidate dataclass、source extraction 或 validation。
- 不把任何顯示值轉成可編輯 input。
- 不建立新的 canvas、preview renderer 或通用 UI framework。
- 不修改其他 Review 頁面的欄位用語；本次新名稱只描述角撐 template transfer 的兩個端點定位尺寸。

## Decisions

### Decision 1：依候選數量切換入口，但共用同一個目前方案 projection

當 `len(plan.candidates) == 1` 時，不顯示候選比較表，直接把唯一 candidate 設為 `corner_brace_repair_candidate_id`，更新摘要、稽核與 overlay，並啟用「套用此修補」。這仍只是 UI selection，不是 explicit adoption；開窗不得呼叫 commit 或修改 live Review state，正式狀態只會在使用者按下「套用此修補」且既有 Apply callback 成功後改變。取消或關閉視窗維持零副作用。

當候選數量大於一時，保留 `Treeview` 與 browse selection；初始沒有 selected candidate，Apply button 維持 disabled。這次不另外設計新的多候選比較機制；表格僅配合新術語與三位小數格式，選取事件同步刷新主要摘要、稽核與診斷、overlay 及 Apply state。候選 ID 繼續作為 Treeview `iid`、selection 與 commit identity；不得使用三位小數顯示字串識別、合併、排序或自動選擇候選，也不得自動提交其中一個候選。

摘要區至少顯示：

- 目標關係：`target_waler_id / target_strut_id`。
- 選用模板：`template_reference.member_id`。
- 移植方式：既有 `corner_brace_transfer_mode_label()`。
- 結果長度：`fixed_length_mm`。
- 圍令端定位距離：`reference_waler_offset_mm`。
- 支撐端定位距離：`reference_strut_station_mm`。
- target direction 與 positional anchor 的有效狀態。

### Decision 2：`CornerBraceRepairPlan` 與 selected candidate 維持 single source of truth

Presentation 不從座標重新計算長度、offset、station、方向或 eligibility，也不自行找 reference。所有摘要、表格、稽核與 overlay 都直接讀取目前 plan 與 selected candidate。顯示名稱只是 label mapping；底層仍使用原有欄位與原始 double precision。

同一 candidate 的主要區與稽核區必須由同一個 update function／資料 projection 更新，避免 selection 改變後只刷新其中一區。若沒有 selected candidate，Apply button 維持 disabled，摘要與 overlay 清除或回到選取提示。顯示格式不得參與 candidate equality、identity、ranking 或 commit payload。

### Decision 3：灰色來源線使用既有 `plan.residual_segments`

`_draw_corner_brace_repair_overlay` 繼續透過既有 `coordinate_system.transform()`、`_project_preview_point()` 與 `preview_renderer.create_line()`。差異只在 source line styling：

- 每一條且僅限 `plan.residual_segments` 使用低干擾灰色、細線／虛線，以區分 raw source evidence 與正式工程構件；不得重複建立同一 residual overlay item。
- selected candidate 軸線維持高對比藍色粗線。
- positional anchor 維持與兩者可辨識的橘色 marker。
- 三者都維持 `temporary_overlay` tag，由 `_clear_corner_brace_repair_overlay` 在改選、取消與關閉時移除。

不重新從整張 DXF 或附近幾何挑線，也不把灰色 source line 當成新的 eligibility evidence。改選 candidate 時先清除舊 temporary overlay，再依同一 plan 重畫一次 residuals 與新 selected candidate；取消或關閉視窗同樣清除全部 repair temporary overlay。實作時用 focused rendering test／stub 檢查每個 residual 每次刷新只建立一個 overlay item。

### Decision 4：建立角撐修補專用的三位小數顯示 helper

在 Presentation boundary 建立最小的 feature-local helper，格式規則如下：

- scalar：`f"{value:.3f}"`。
- point：每個座標分量分別套用 scalar formatter，顯示為 `(x.xxx, y.yyy)`。
- engineering line：`(x.xxx, y.yyy) → (x.xxx, y.yyy)`。
- 結果長度、reference fixed length、「圍令端定位距離」與「支撐端定位距離」在數值後加 `mm`，例如 `1234.568 mm`、`350.125 mm`。
- positional anchor 與 candidate world engineering line 的每個座標分量固定三位小數，但維持既有無單位表示，例如 `(100.123, -200.456)` 與 `(100.123, 200.456) → (300.789, 400.012)`。
- 多候選表格中的工程數值使用相同 formatter；candidate ID 仍是 identity。

表格、方案摘要、reference fixed length、positional anchor 與 world engineering line 必須共用同一 helper。此 change 不修改通用 `_review_display_value`，避免連帶改變其他 Review sections。Formatter 只建立字串，不得量化、覆寫或回傳新的 candidate numeric value；底層 double precision、candidate eligibility、排序、candidate ID、工程幾何與提交值保持原樣。

### Decision 5：稽核／診斷區使用簡單可收合 Presentation state

主要區預設顯示摘要與量測基準說明。次要區預設收合，透過明確標示的「顯示稽核與診斷」／「隱藏稽核與診斷」操作切換；重新展開時必須完整取得 reference fixed length、world engineering line、automatic primary references、manual repaired secondary references 與 candidate／plan diagnostics。

收合狀態是 Toplevel 生命週期內的純 UI state，不進入 `DXFReviewWorkflow`、不持久化。收合或展開不得改變 selected candidate、Apply enabled state、candidate ID、overlay、live Review state 或 persistence。diagnostics 有內容時可顯示中性的「有診斷資料」提示，但 Presentation 不得自行重算或重新判斷 severity。使用 Tkinter 既有 `grid_remove()`／`grid()` 或同等簡單機制，不新增 widget framework。

## Architecture Alignment

這次 change 沿用既有 Architecture，不修改 layer boundary：

```text
DXFReviewWorkflow / CornerBraceRepairPlan
                  ↓ read-only projection
dxf_import/dialog.py（Presentation）
                  ↓ existing renderer calls
Review canvas temporary overlay
```

- **Presentation（受影響）**：Toplevel widgets、候選 selection、格式化、diagnostics visibility、canvas overlay style 與 refresh。
- **DXF workflow／models（不變）**：仍擁有 candidate eligibility、工程數值、source identity、commit 與 rollback。
- **Application／Domain／Algorithms／Infrastructure（不受影響）**：不新增依賴或資料流。

`CornerBraceRepairPlan` 與 selected `CornerBraceRepairCandidate` 是工程／候選資料的 single source of truth；UI summary、details 與 overlay 都是 projection，不保存另一份可提交幾何。顯示 helper 只處理字串格式，不回寫或量化原始值，因此不會形成第二個 numeric truth。

## Backward Compatibility 與 Persistence

- 沒有資料模型、JSON、paused review payload、Project schema 或 migration 變更。
- 現有 candidate IDs、internal transfer mode、provenance 與 explicit commit API 不變。
- 舊專案與 paused sessions 重新進入修補 preview 時，只會看到新版呈現。
- 關閉或取消 Toplevel 的 overlay cleanup 與零副作用 contract 維持不變。

## Risks / Trade-offs

- **[Risk]** 單一候選直接預選可能被誤解為已套用。→ **Mitigation**：標示為「建議修補方案」，正式按鈕使用「套用此修補」，並維持明確 click 才 commit。
- **[Risk]** 灰色 source overlay 與主場景既有線條重疊後可能不清楚。→ **Mitigation**：使用細線／虛線、將 candidate 軸線置頂，並以 render stub 驗證 overlay order 與 item count。
- **[Risk]** 收合 diagnostics 讓稽核資訊較不顯眼。→ **Mitigation**：toggle 使用清楚文字，主要區保留 valid states；diagnostics 有內容時仍可在 toggle 旁顯示「有診斷資料」等中性提示，但不新增 severity 判斷。
- **[Risk]** 固定三位小數可能讓極小差異在畫面上看起來相同。→ **Mitigation**：這是使用者指定的顯示精度；底層精度、candidate ID 與 commit data 不變，多候選不以顯示字串作 identity。
- **[Trade-off]** 不新增內嵌 preview canvas，Toplevel 與主 Review canvas 仍是兩個視覺區域。→ 接受此取捨以重用既有座標轉換、zoom 與場景生命週期，避免建立第二套 preview state。

## Migration Plan

1. 先加入 formatter 與 Presentation-focused tests，再重組 Toplevel widgets。
2. 調整 overlay style 並驗證 selection／cancel cleanup。
3. 執行角撐修補 focused tests 與 DXF Review layout regression。
4. 若新版 UI 發生問題，可回退 Presentation 變更；因無 schema 或持久化變更，不需資料 rollback。
