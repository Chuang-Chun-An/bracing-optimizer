# Proposal：人工修補並正式採用暫定圍令工程線

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」、「不變事項」與「相關 change 狀態與實作順序」；先確認本 change 採用 Option A：合法人工線經明確採用後本身就是接觸面，不放寬自動辨識。
- **P0／現在必讀**：`openspec/specs/dxf-waler-contact-face-recognition/spec.md` 的「接觸側無法唯一決定時必須保守失敗」、「下游正式幾何與診斷必須使用同一接觸面 truth」及「Provisional axis 不得由確認動作升級」Scenario。
- **P0／現在必讀**：本 change 的 delta spec「暫定圍令可由明確人工工程線修補正式化」；它定義人工裁決與一般確認的差異。
- **P1／實作前閱讀**：本 change 的 `design.md` 中人工裁決 truth、原子提交、診斷消除範圍、材料寬度及 replay Decisions。
- **P2／需要時再讀**：修改 Pause／Resume 或 changed-content recovery 時再讀 `paused-dxf-review-source-relink`；修改背填／寬度調整時再讀 `dxf-waler-contact-adjustment`。可先跳過 Solver scoring、candidate search、Global Waler 與成果匯出 specs，本 change 不改那些行為。

## 快速摘要

- 現在 provisional Waler 即使由使用者套用候選點或 CAD 指定線，仍保留 envelope／contact-face 阻擋，無法成為 Solver 可用的正式圍令。
- 新增「人工採用為正式圍令」修補語意：候選點與 CAD 工程線都可作為輸入，但只有明確套用且通過驗證後才正式化。
- 任何通過既有 validation 的合法有限線，經人工明確採用後即成為該 Waler 唯一正式工程線兼接觸面；不要求位於 source envelope 的外側邊。
- 預覽與確認必須明確提示：「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」。
- 只解除由該來源工程線無法唯一提交所造成的幾何／接觸面阻擋；重疊來源、terminal identity 多解及其他獨立問題仍維持。
- 人工正式化後先以人工接觸線重建 Strut／Brace terminal relations，再依既有 unique-first precedence 判斷支撐側；兩側衝突或沒有證據時支撐側為 unknown，但 Waler 的人工正式化仍成立。
- 沿用既有 Review workflow、manual override、Pause／Resume 與 Project／Solver row contract，不改自動辨識規則或 Solver 評分。

## 現況與目標

本 change 中，「人工正式化」指使用者明確把一條已通過既有 validation 的候選點工程線或 CAD 指定工程線，裁決為該 Waler 的正式工程線與接觸面；它不是中心線、一般問題確認或自動辨識猜測，也不要求該線與任一 envelope 外側邊重合。

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 暫定 Waler 選線 | 可改起終點，但 `contact_face_state` 仍為 `provisional` | 明確執行人工修補後，合法選線成為 `formal` |
| Envelope／接觸面問題 | 人工更新後原 blocking diagnostic 仍存在 | 只移除已由該人工裁決完整取代的幾何／接觸面問題，留下人工 provenance |
| 候選來源 | 候選點與 CAD 指定線只屬於一般幾何編輯 | 兩者都可進入同一套正式化驗證與提交流程 |
| 支撐側與下游資料 | 未正式化的線不能完成匯入；舊 relations 可能仍基於 provisional axis | 正式化後從人工接觸線重建 terminal relations，再依既有 unique-first precedence 建立 `support_normal_world`、member connections、Project rows 與 Solver input |
| 支撐側 unknown | 接觸面未正式時不能進入尺寸調整 | 人工接觸面仍可正式成立，但背填／寬度調整依既有 `WALER_SUPPORT_SIDE_UNKNOWN` 原子阻擋，不猜測方向 |
| Review 恢復 | 只重播幾何座標，不會恢復正式化裁決 | same-fingerprint 可安全重播人工裁決；changed-content 不靜默轉移效果 |

## 主要流程

```text
選取 provisional Waler
  -> 以候選點組成工程線，或讀取 CAD 指定工程線
  -> 預覽及確認顯示「此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線」
  -> 明確執行「採用為正式圍令」
  -> 驗證 exact source identity、有限座標、長度與目前 Review revision
  -> 原子提交人工正式線
  -> 只消除被該裁決取代的 envelope／contact-face blocker
  -> 以人工接觸線重建 Strut／Brace terminal relations 與 Brace adjustment baseline
  -> 依既有 unique-first precedence 判斷支撐側
  -> 重建 association、diagnostics、Waler contact review 與匯入狀態
```

取消、驗證失敗、stale revision 或提交失敗時，現有 WCS result、確認與 committed Project／Solver state全部保持不變。

## 不變事項

- 自動 Waler envelope extraction、unique-first side evidence、容許值、來源分組及候選資格不變。
- 自動正式化仍由既有規則選擇支撐側最外實體表面；只有明確人工正式化採用 Option A，直接把合法人工線視為接觸面。
- 一般「確認」、Preview 選取或單純顯示 provisional line，仍不得把暫定線升級為正式線。
- 人工正式化一支 Waler 不會選擇重疊 Waler winner，也不會解除其他來源的 overlap competition 或 member terminal identity ambiguity。
- 原始 DXF 保持 immutable；正式 Review state 仍由 `DXFReviewWorkflow` 擁有，Dialog 不自行修改工程 truth。
- Project row、Solver input schema、Solver scoring、搜尋參數及材料最佳化規則不變。
- 既有 formal Waler、一般候選點編輯及 CAD 工程線編輯不得因本 change 自動改變狀態。

## Why

DXF Review 已能保留 provisional Waler 並提供候選點與 CAD 工程線，但目前人工更新只改座標，無法裁決「同一來源無法唯一提交」的阻擋結果。使用者即使已依工程判斷選定計算用圍令，仍沒有合法途徑把該線提交為正式工程 truth，因此需要一個可追溯、可重驗且不會掩蓋其他問題的人工修補流程。

## What Changes

- 為具有唯一 source identity 的 provisional Waler 提供明確的「採用為正式圍令」修補操作。
- 允許使用既有候選點配對或 CAD 指定工程線作為人工正式線來源，並使用一致的驗證與原子提交語意。
- 將已採用人工線設為該 Waler 的正式工程線兼接觸線，記錄人工裁決 provenance，並重建所有依賴正式 Waler geometry 的衍生結果。
- 由新人工接觸線重新建立 Strut／Brace terminal relations，丟棄 provisional axis 的舊證據；支撐側仍依既有 unique-first precedence 由構件本體位於人工線哪一側決定。
- 支撐側衝突或無證據時保留人工正式線，但將 `support_normal_world` 設為 unknown，後續背填／寬度調整沿用既有 `WALER_SUPPORT_SIDE_UNKNOWN` 阻擋。
- 精確區分「已由人工線取代的 Waler 幾何／接觸面阻擋」與「仍須保留的來源重疊、terminal identity、連接及其他診斷」。
- 將人工正式化 decision 納入既有 manual override、Pause／Resume、source exclusion／restore、confirmation invalidation 與 recovery lifecycle。
- 當候選 envelope 對代表寬度提供單一一致值時保留該值；若寬度也有歧義，人工線不猜測寬度或材料，既有自動材料配對必須失效並由使用者另行指定。

## In Scope

- 已形成 Waler review member、具有 exact source identity，且目前為 provisional，或已由 `manual_repair` 正式化而要重新採用另一條線的人工工程線修補。
- 候選點選線與 CAD 指定工程線兩種輸入路徑。
- 修補 eligibility、preview、明確採用、validation、atomic commit、rollback、diagnostic replacement 與 downstream rebuild。
- 人工裁決的 capture／replay、Pause／Resume、same-fingerprint restore、source exclusion／restore 及 changed-content recovery 分類。
- Y29 W14 source `58D` regression，以及一般 synthetic envelope unresolved／ambiguous cases。
- 人工正式化後的 Waler contact review baseline、Brace adjustment baseline、背填／寬度調整與 rigid-translation regression。

## Out of Scope

- 從完全沒有 Waler review member 的 unresolved raw source 新建一支或多支 Waler。
- 把一個 DXF source 自動或人工拆成多支 Project Waler，或支援折線／彎折 Waler domain model。
- 讓人工正式線自動解除 Waler source overlap、overlap competition、terminal identity ambiguity 或其他構件錯誤。
- 修改自動 envelope／contact-face recognition、geometry tolerance、材料寬度比對門檻或 Solver 規則。
- 由人工工程線推算不存在或仍有歧義的實體寬度、材料規格或 envelope。
- 提供「取消人工正式化」或恢復成 provisional／automatic 的操作；選錯時使用同一專用操作再次採用另一條合法線，原子取代舊人工 decision。
- 修改已封存的 `clarify-dxf-review-diagnostics` 白話投影 contract，或新增未納入其分類的新 diagnostic code。

## 相關 change 狀態與實作順序

截至 2026-10-06，本 change 依賴的三份 change 均已完成並封存，實作時以其已同步至 main specs／目前程式的行為為基線，不重播舊 delta：

1. `calculate-waler-width-orthogonally`：已於 `openspec/changes/archive/2026-10-05-calculate-waler-width-orthogonally/` 封存。先提供 `WalerEnvelopeFacts.source_width` 的正交 supporting-line 量測；本 change 的 `source_width_state` 只能評估這些既有量測結果的 unique／unknown／ambiguous，不重算另一套寬度。
2. `rigidly-translate-braces-on-waler-adjustment`：已於 `openspec/changes/archive/2026-10-05-rigidly-translate-braces-on-waler-adjustment/` 封存。已建立 formal Brace baseline、剛體平移及原子阻擋；本 change 必須在人工正式化後重建 baseline，後續調整直接沿用該能力。
3. `clarify-dxf-review-diagnostics`：已於 `openspec/changes/archive/2026-10-06-clarify-dxf-review-diagnostics/` 封存，16／16 tasks 完成。與本 change 重疊的主要檔案為 `dxf_import/models.py`、`dxf_import/validation.py`、`dxf_import/dialog.py`、`tests/test_dxf_review_layout.py`、`tests/test_dxf_review_workflow.py` 及 `tests/test_dxf_module_boundaries.py`；實作本 change 時必須保留其 problem projection、known-code inventory、白話 formatter 與 raw diagnostic identity。
4. 最後實作 `resolve-provisional-waler-manually`：先以目前已整合上述三份 change 的程式為基線，再加入人工正式化；不得覆蓋正交寬度、Brace 剛體平移或白話診斷投影。

## Capabilities

### New Capabilities

- `dxf-waler-engineering-line-repair`：定義 provisional Waler 如何由候選點或 CAD 工程線經明確人工裁決成為正式工程／接觸線，以及驗證、診斷、重建與 lifecycle 行為。

### Modified Capabilities

- `dxf-waler-contact-face-recognition`：澄清一般確認仍不得升級 provisional axis，但通過專用人工修補後，人工正式線可以成為 canonical contact-face truth；自動 identity competition 仍獨立保留。
- `paused-dxf-review-source-relink`：定義人工圍令正式化 decision 在 Exact Match、same-fingerprint resume 與 changed-content compatible recovery 中的保留、需重審及停用語意。

## Impact

- **DXF workflow／models**：`dxf_import/review_workflow.py`、`dxf_import/models.py`，新增人工正式化 use case、狀態與原子 mutation outcome。
- **Geometry editing／diagnostics**：`dxf_import/candidate_points.py`、`dxf_import/validation.py`，重用候選點與 CAD line validation，集中處理 formalization 後的 scoped diagnostic replacement 與 derived rebuild。
- **Contact adjustment**：`dxf_import/waler_contact_adjustment.py`，重建人工接觸線的 `support_normal_world`、Waler contact review baseline 與 formal Brace adjustment baseline；後續尺寸調整沿用既有剛體平移及 unknown-side 原子阻擋。
- **Manual replay／recovery**：`dxf_import/source_exclusion.py`、`dxf_import/review_recovery.py`、`dxf_import/review_recovery_planner.py`，保存並重驗明確正式化 decision，不以舊 `selection_source` 猜測使用者意圖。
- **Presentation**：`dxf_import/dialog.py`、Preview interaction，對 eligible provisional Waler 顯示專用採用動作、影響預覽及明確確認。
- **測試**：Waler contact-face recognition、candidate editing、Review workflow、source exclusion／replay、recovery、layout 與 Y29 fixture regressions。
- **長期文件**：若實作完成後人工 Review lifecycle 成為 long-term truth，更新 `docs/WORKFLOW.md`；不預期修改 Architecture、Solver 或 Project schema。

## 已確認決策與重新評估條件

- 已確認：候選點與 CAD 指定線只要經專用人工正式化提交並通過驗證，具有相同的正式線 authority。
- 已確認（Option A）：任何通過既有 validation 的合法線，經明確採用後本身就是接觸面，不要求落在 envelope 外側邊；unique-first 只再判斷支撐側，不另選外側面。
- 已確認：人工正式化只解決目標 Waler 的工程線／接觸面 authority，不代表整份 Review 或相關 terminal identity 都已合法。
- 已確認：一般確認與既有自動選線不得隱含觸發正式化；必須是可追溯的明確人工 decision。
- 已確認：本次不提供取消人工正式化；選錯時可再次透過專用操作採用另一條合法線，成功後取代舊人工 decision。
- 預設採用：沿用 Review state version 2 的 optional `manual_overrides` payload，不提升 Project schema；若實作 discovery 證明無法 backward-compatible 表達，必須停止並回報後重新評估 persistence scope。
- 預設採用：一致且唯一的來源寬度可保留；寬度多解時清除自動材料結果。若現有 recognition facts 無法可靠判斷「一致寬度」，實作不得自行選擇，須將材料留待人工處理。
