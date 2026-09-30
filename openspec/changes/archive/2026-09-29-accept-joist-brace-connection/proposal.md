# Proposal

## 閱讀導航

### P0 — 現在必讀

1. 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
2. `specs/beam-member-connection-validation/spec.md` 的托梁連接成立條件與警告行為。
3. `specs/bim-joist-recognition/spec.md` 的 Brace contact runtime 保留與 Project projection 邊界。
4. `design.md` 的 Decision 1～3：接觸單一 truth、Strut／Brace 語意分離與重建一致性。

### P1 — 實作前閱讀

- `openspec/specs/bim-joist-recognition/spec.md` 的「Joist contact SHALL preserve source axes...」、「Brace contact SHALL retain single-Joist semantics」與 legacy compatibility Requirements。
- `docs/ARCHITECTURE.md` 的「3.6 DXF Subsystem」、「6. State Ownership」；以及 `docs/DOMAIN.md` 的「Column / Beam station」。
- `tasks.md` 各 task group 指定的 Decision、Requirement 與 focused tests。

### P2 — 需要時再讀

- 修改 Review confirmation signature 或 Pause／Resume rebuild 時，再讀既有 paired assembly source lifecycle Requirement。
- 修改 Waler contact adjustment rebuild 時，再讀 `dxf_import/waler_contact_adjustment.py` 對 association rebuild 的呼叫路徑。
- 可先跳過 Support／Waler Solver、材料規則、Double Support、CornerBrace repair 與其他 recognition specs；本 change 不修改這些行為。

## 快速摘要

- 現在一般托梁的關聯流程只檢查 Strut，因此托梁即使與正式 Brace 有有效接觸，仍可能顯示 `BEAM_NOT_ASSOCIATED`。
- runtime 唯一判定明定為 `Beam is connected iff beam.crossings is not empty or beam.brace_contacts is not empty`；不新增第二份 Strut contact collection。
- Brace contact 必須是 finalized 托梁有限線段與正式 Brace 有實際且近似垂直的有限接觸，不接受延長線、nearest snap、小間隙吸附或 Brace 外緣投影。
- Brace contact 只解除未連接警告，不得建立 `BeamCrossing`、`BeamPositions`、`AssociatedBeamIDs` 或 Solver 禁止點。
- 同一 Beam／Brace／tolerance-equivalent WCS contact point 只能有一筆 contact；共用 path 頂點不得因相鄰 segments 重複計數，而兩個不等價真實交點可各自保留。
- 不修改 Project schema、persistence、Solver、材料規則或既有 Strut crossing 行為。

## 現況與目標

| 主題 | Before：目前行為 | After：目標行為 |
|---|---|---|
| 托梁連接判定 | 一般 Beam association 只檢查 Strut crossing | `beam.crossings` 或 `beam.brace_contacts` 任一非空即為 connected |
| 警告 | 只有 Brace contact 的托梁仍可能出現 `BEAM_NOT_ASSOCIATED` | 僅在兩個 runtime collections 都為空時顯示未連接警告 |
| Strut constraint | Strut crossing 建立 `BeamCrossing`、station 與 Project constraint | 維持不變 |
| Brace contact | BIM recognition 已能辨識，但轉成 runtime `Beam` 時沒有完整保留；一般 Beam association 不檢查 | 以明確 runtime contact 保存或重建，供 validation／Review lifecycle 使用 |
| Solver 投影 | `BeamPositions` 只代表 Beam 與 Strut 的交會 station | 維持只接受 Strut crossing；Brace 不偽裝為 Strut |

runtime validation 中的 Strut contact 就是既有流程已建立的 `BeamCrossing`；Brace contact 則是新的 `BeamBraceContact`。本 change 不新增另一份 runtime Strut DTO，也不改變 pure recognition Strut contact 投影成 `BeamCrossing` 的既有流程。

## 主要流程

```text
finalized Beam / Joist path
  -> 既有 Strut 流程建立 beam.crossings
  -> Brace finite-contact 流程建立並去重 beam.brace_contacts
  -> crossings 非空或 brace_contacts 非空：connected
  -> 兩者都空：產生 BEAM_NOT_ASSOCIATED
  -> Review rebuild／Waler adjustment 使用相同 contact truth 重建結果
```

## 不變事項

- 不把 Brace 當成 Strut，不對 Brace 產生 `strut_id`、`strut_station`、`BeamPositions` 或 `AssociatedBeamIDs`。
- 不修改 Strut crossing 的 segment intersection、既有 gap snap、duplicate filtering 或 station 計算。
- 不修改 Joist Strut `endpoint_face_contact` eligibility；pure recognition 的 Strut contact 仍依既有流程投影為 `BeamCrossing`。
- 不放寬 Joist／Brace contact：不接受無限延長線、nearest geometry、一般小間隙或 Brace face projection。
- Beam 與 Brace finite segments 真實共用端點且角度資格成立時，屬合法 direct contact；這不同於 endpoint face projection。
- 不修改 BIM paired-axis 的 `518 ± 5 mm`、Column midpoint `±2 mm`、terminal recovery 或 pair eligibility。
- 不修改 Project schema、Project persistence、Solver input、Solver scoring、材料規則或 Waler／Brace recognition。

## Why

現行警告把「沒有 Strut constraint」等同於「托梁未連接」，忽略已由正式 Brace 支承的托梁，造成誤導性的 Review 警告。既有 BIM Joist 規格已承認可靠的 Brace-only single Joist，因此 runtime association 與一般托梁 validation 應以一致、可追溯且不污染 Solver contract 的方式接受相同接觸語意。

## What Changes

- 新增共用的托梁連接 validation contract：`beam.crossings` 或 `beam.brace_contacts` 任一非空即滿足 runtime「已連接」。
- 將 `BEAM_NOT_ASSOCIATED` 的觸發條件改為上述兩個 collections 同時為空；訊息明確區分「未連接」與「沒有 Strut 禁止點」。
- 將 BIM recognition 已建立的 Brace contact 保留到 runtime Beam／DXF Review state，不在 importer projection 時遺失。
- 一般 LINE／MLINE／closed-outline Beam 使用與既有 Joist direct Brace contact 一致的有限、近似垂直接觸資格。
- 以 Beam identity、Brace identity 與 tolerance-equivalent WCS contact point 作為 Brace contact engineering identity；segment index 僅保留 provenance。
- 保持 Strut-only downstream projection：只有既有 `BeamCrossing` 進入 association 與 Project constraint；`BeamBraceContact` 不進入這些 consumers。
- 讓初次匯入、source exclusion／restore、Waler contact adjustment 與其他 derived rebuild 共用相同結果，避免警告在重建後重新出現。

### In Scope

- 正式 Beam／Joist 對 Strut 與 Brace 的連接狀態判定。
- `BEAM_NOT_ASSOCIATED` 的觸發條件與使用者可見訊息。
- BIM Joist Brace contact 到 runtime DXF model 的保存與座標轉換。
- 一般 Beam 對正式 Brace 的有限垂直接觸檢查。
- Review confirmation／rebuild 所需的 contact identity 與 regression tests。

### Out of Scope

- 以 Brace contact 建立新的 Solver constraint、forbidden point 或 Project 欄位。
- Brace endpoint face contact、軸線延長、nearest snap、gap snap 或人工補接工具。
- 改變 Beam／Joist recognition axis、BIM topology、Strut／Brace recognition 或 Waler connection。
- 修改警告嚴重度、全域 validation 分類或重新設計 Review UI。
- 與本需求無關的 model 泛化、命名整理或大型 refactor。

## Capabilities

### New Capabilities

- `beam-member-connection-validation`：定義正式托梁以 Strut／Brace contact 判定已連接、未連接警告，以及 Brace contact 不得投影成 Strut constraint 的邊界。

### Modified Capabilities

- `bim-joist-recognition`：要求已辨識的 Joist-to-Brace contact 在 runtime Beam／Review rebuild 中保留，並調整 legacy Beam compatibility，使一般 Beam 可採用同一個保守 Brace direct-contact contract。

## Impact

- **DXF models**：預期在 `dxf_import/models.py` 增加不冒充 `BeamCrossing` 的 runtime Beam contact 表示，並納入座標轉換與必要的 Review engineering signature。
- **Recognition／adapter**：`dxf_import/joist_recognition.py` 仍是 BIM contact truth；`dxf_import/importer.py` 需保留 Brace contact；`dxf_import/candidate_points.py` 的 association rebuild 需取得正式 Braces 並以共用規則判定一般 Beam contact。
- **Derived rebuild**：`dxf_import/waler_contact_adjustment.py` 與其他呼叫 `associate_components_to_struts` 的路徑需傳入同一 staged Brace 集合。
- **Tests**：擴充 `tests/test_dxf_input.py`、`tests/test_dxf_bim_joist_recognition.py`、`tests/test_dxf_waler_contact_adjustment.py`，以及必要的 Review lifecycle／coordinate tests。
- **Compatibility**：不新增 dependency、不修改 Project persistence schema；Solver、Domain 材料規則與既有 Strut station contract 不變。
- **Long-term truth**：實作完成後預期更新 `docs/DOMAIN.md` 的 Beam contact／Beam station 區分；Architecture 與 Workflow 責任不變，若實作未改變其 long-term truth 則不更新。

## 尚未決定與重新評估條件

- runtime contact DTO 的具體名稱與是否由既有 `JoistContact` 映射為較通用的 DXF model，屬 design／implementation choice；不得因此改變 Project schema。
- 若實作發現一般 Beam 無法取得可靠 finalized path，或必須放寬為非垂直接觸才能符合實際圖面，必須停止並重新確認工程資格，不可自行使用 nearest／gap snap。
- 若 Brace contact 需要持久化到 Project payload、影響 Solver，或要求新的人工編輯流程，視為 scope expansion，需另行修訂 proposal 與 spec。
