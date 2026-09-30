# Design

## 閱讀導航

### 現在必讀

- Decision 1：以獨立 `BeamBraceContact` 保存 Brace relationship，`BeamCrossing` 繼續只代表 Strut constraint。
- Decision 2：抽出一個共用 pure finite-perpendicular helper，BIM Joist 與一般 Beam 不各寫一套 eligibility。
- Decision 3：所有 association rebuild 以目前 formal Braces 重建 Brace contacts，再決定 `BEAM_NOT_ASSOCIATED`。
- Decision 4：利用既有 Beam dataclass signature 與 coordinate projection 維持 confirmation／WCS semantics。

### 遇到特定風險時再讀

- 修改 `associate_components_to_struts` 呼叫介面時，閱讀 Decision 3 與「Backward Compatibility」。
- 修改 Pause／Resume 或 confirmation 時，閱讀 Decision 4；不需另建持久化 contact cache。
- 若 implementation 想把 Brace 寫進 `BeamCrossing` 或 Project row，先閱讀 Decision 1 的 rejected alternatives；該做法違反 spec。

### 可先跳過

- Solver、材料配置、paired-axis recovery 與 Waler／Brace recognition 不在本設計範圍。

## 方案摘要

```text
finalized Beam path + current formal Braces
                  |
                  v
     shared finite-perpendicular helper
                  |
                  v
       tuple[BeamBraceContact, ...]
                  |
      +-----------+------------------+
      |                              |
      v                              v
connection validation       DXF runtime / confirmation
      |
      +-- beam.crossings non-empty ------+
      |                                  +--> connected
      +-- beam.brace_contacts non-empty -+
      `-- both empty ------------------------> BEAM_NOT_ASSOCIATED
```

正式 runtime predicate 只有一個：`Beam is connected iff beam.crossings is not empty or beam.brace_contacts is not empty.` `BeamBraceContact` 是 DXF runtime 的斜撐接觸事實；`BeamCrossing` 仍是 Beam 與 Strut 的既有 station constraint。兩者不互相轉型，也不新增第二份 Strut contact collection。

## 決策對照

| Decision | 對應 Spec | 對應 Tasks |
|---|---|---|
| D1：唯一 connected predicate，分離 Brace contact 與 Strut crossing | `beam-member-connection-validation`「斜撐接觸不得建立支撐限制」；`bim-joist-recognition`「Brace contact...」 | 1.1～1.3、2.1～2.2 |
| D2：共用有限垂直接觸 helper | 「正式支撐或斜撐接觸皆可滿足托梁連接狀態」及 `5.0°` scenarios | 1.1、2.1、2.3 |
| D3：Brace contact engineering identity、去重與 rebuild | 「Brace contact engineering identity...」、「重建流程必須保持相同連接結果」 | 3.1～3.3 |
| D4：既有 dataclass signature 與座標投影 | coordinate projection、stale confirmation scenarios | 1.3、3.2、3.3 |
| D5：警告仍使用既有 code、只修觸發條件與訊息 | 「Both member roles are absent」 | 2.2、2.3 |

## Context

動機見 `proposal.md` 的 Why。現況有三個直接影響方案的 constraint：

1. `joist_recognition.py` 已以 `JoistContact(member_role="brace")` 證明 BIM single Joist 的 Brace finite-perpendicular contact；角度容許值為 `5.0°`。
2. `importer._make_auxiliary` 目前只把 `member_role == "strut"` 映射成 `BeamCrossing`，所以 Brace contact 沒有進入 runtime `Beam`。
3. `candidate_points.associate_components_to_struts` 只收到 Struts；一般 Beam 沒有 crossings 時直接產生 `BEAM_NOT_ASSOCIATED`。`rebuild_component_associations` 與 Waler contact adjustment 都會重跑此流程。

`BeamCrossing` 的欄位與下游語意是 `strut_id`、`strut_station` 與 Project `BeamPositions`，不能承載 Brace。`review_confirmation_signature` 已對 Beam dataclass 執行 `asdict`，因此 Beam 新增的 immutable runtime engineering field 可自然參與 confirmation invalidation。

## Goals / Non-Goals

**Goals:**

- 建立一份可被 BIM 與一般 Beam 共用的 Brace finite-perpendicular contact eligibility 與去重 identity。
- 讓 runtime Beam 明確保存 Brace relationship，並在 rebuild 後更新為目前 formal Brace truth。
- 保持 Strut projection contract 完全不變。
- 讓 initial import、coordinate projection、source replay 與 Waler adjustment 得到一致 warning。

**Non-Goals:**

- 不泛化所有工程 contact 成大型 polymorphic hierarchy。
- 不修改 Project row／payload、Solver input 或 `ComponentAssociation` 的 Strut-only語意。
- 不新增 Brace face、gap snap、axis extension 或人工 contact override。
- 不藉機重新命名 `associate_components_to_struts` 或整理所有 call sites。

## Decisions

### Decision 1：唯一 runtime predicate 與獨立的 immutable `BeamBraceContact`

在 DXF model boundary 新增小型 immutable contact DTO，預期欄位為：

- `beam_id`
- `brace_id`
- `world_point`
- `local_point`
- `beam_segment_index`
- `recognition_method`（direct contact 使用 `finite_segment_intersection`）

`Beam` 新增 `brace_contacts: tuple[BeamBraceContact, ...]`。runtime validation MUST 只使用下列 predicate：

```python
is_connected = bool(beam.crossings) or bool(beam.brace_contacts)
```

runtime 所稱 Strut contact 就是既有 `BeamCrossing`。Strut contacts 仍只存在於 `Beam.crossings`／`DXFImportResult.beam_crossings`，不新增 generic `StrutContact`、`BeamMemberContact` 或其他第二份 collection。Pure recognition 的 Strut contact 繼續依既有 adapter 投影為 `BeamCrossing`；本 change 不修改 Joist Strut `endpoint_face_contact`、direct crossing eligibility、station 或 Project projection。Brace contact 不新增 result-level duplicated collection；需要全場彙整時由 `result.beams` 唯讀投影。

這兩個集合的 single source of truth 分工為：

```text
Beam.crossings       = Strut station / Project constraint truth
Beam.brace_contacts  = Brace relationship / connected-state truth
```

初次 BIM candidate projection 將 `JoistContact(member_role="brace")` 映射為 `BeamBraceContact`；`member_role="strut"` 仍映射為 `BeamCrossing`。association rebuild 會依目前 formal members 重新驗證並取代 derived contacts，故不沿用 stale identity。

**Rejected alternatives:**

- 把 Brace 塞入 `BeamCrossing.strut_id`：會污染 Project／Solver contract並產生不存在的 Strut station。
- 只在 warning 前臨時計算 boolean：無法讓 confirmation、debug 與 rebuild 保存可追溯工程關係，也會讓 BIM recognition contact 繼續遺失。
- 建立一個同時重複保存 Strut 與 Brace 的 `BeamContact` 集合：Strut truth 會與既有 `BeamCrossing` 形成兩份資料，增加 drift 風險。

### Decision 2：共用 pure finite-perpendicular geometry primitive

抽出一個 DXF recognition pure helper，輸入兩條 finite segments 與角度容許值，輸出實際交點與 member station（或 `None`）。helper 的 contract 為：

- 必須是兩條 finite segments 的真實交點。
- `abs(90° - angle_difference) <= 5.0°`，含等號。
- 不接受延長線、nearest point、gap snap 或 member width。
- finite segments 真實共用端點且角度資格成立時，intersection helper SHALL 回傳該 endpoint；這是 direct finite contact，不是 endpoint face projection。

`joist_recognition` 的 direct Strut／Brace contact 與一般 Beam 的 Brace contact 都呼叫這個 helper。Joist 的 Strut `endpoint_face_contact` 保持在原模組，因該 fallback 明確不適用 Brace。

helper 應位於 DXF recognition/model 下游、且不依賴 importer mutable state。實作可選擇一個窄幅模組（例如 `dxf_import/beam_contacts.py`）或等價現有 pure geometry owner；不得由 Presentation 或 Solver 提供。

**Rejected alternative:** 在 `candidate_points.py` 複製一份 `5.0°` 判定。這會形成兩套資格規則，日後容易讓 BIM 與 legacy Beam 結果分歧。

### Decision 3：Brace contact engineering identity、去重與集中重建

`BeamBraceContact` 的 engineering identity 為：

```text
(Beam identity, Brace identity, tolerance-equivalent WCS contact point)
```

WCS points 的 tolerance equivalence 重用 `GeometryTolerances.beam_crossing_duplicate_tolerance_mm`，目前為 `1.0 mm`，判定採 `distance <= tolerance`。`beam_segment_index` 只作 provenance，不參與 identity。

同一 Beam／Brace／equivalent point 的 raw contacts 先依 normalized segment geometry key（segment 兩端先正規化方向）、再依 segment index 排序，選 canonical 最小項的 segment index 作 provenance。不得用 segment iteration order、Brace collection order或 first match 決定 winner。相鄰 path segments 在共用頂點同時命中同一 Brace 時合併成一筆；同一 Beam／Brace 若在距離 `> tolerance` 的兩個 WCS points 真實相交，則保留兩筆。最終 contacts 依 Brace identity、WCS point 與 canonical provenance 穩定排序；Beam path 方向反轉或 internal iteration order 改變時，engineering contact集合與 connected/warning 結果必須等價。

#### Association API 與 rebuild

為避免破壞現有 positional callers，`associate_components_to_struts` 保留既有名稱與 positional 參數，新增 keyword-only `braces: Sequence[Brace] = ()`。函式對每支 Beam：

1. 依既有路徑建立／刷新 Strut crossings。
2. 對 finalized `world_path` 各 segment 與目前 formal Braces 建立 raw contacts，再按上述 identity 去重並 deterministic 排序為 `BeamBraceContact`。
3. 僅依 `bool(crossings) or bool(brace_contacts)` 判定 connected；兩者都空時加入 `BEAM_NOT_ASSOCIATED`。
4. 只將 `crossings` 寫入 `assignments` 與 `ComponentAssociation`。

所有持有完整 `DXFImportResult` 或 recognition pipeline state 的呼叫路徑都必須傳入其 staged／proposed Braces：初次 importer、`rebuild_component_associations`、Waler contact adjustment 與同類 derived rebuild。只用於預先建立 Column context、且 beams 為空的 caller 可保留預設空集合。

對 BIM Beam，不再以「有 `joist_assembly_key`」作為跳過 Brace validation 的理由；它仍使用預先驗證並投影完成的 `Beam.crossings`，Brace contacts 則由同一 finalized axis 與目前 formal Braces 得到等價重建。若發現重建結果與 pure recognition outcome 不等價，focused test 應先暴露差異，而不是新增第二套 Strut eligibility 或保留兩個 winner。

### Decision 4：座標與 confirmation 沿用既有 state ownership

`BeamBraceContact.world_point` 是 canonical engineering truth；`apply_coordinate_system` 只更新 `local_point`。Beam dataclass 進入既有 `review_confirmation_signature(... asdict(member) ...)`，因此 contact identity、WCS point 或有無改變會自然使 signature 改變，不另建 confirmation 規則或 cache。

Pause／Resume 仍依既有 fresh recognition rebuild，不將 Brace contacts 加入 Project persistence schema。debug dictionary 因 Beam `asdict` 自然包含 contact，便於驗證；`Beam.to_project_row()` 不輸出 Brace contact，維持 Project contract。

### Decision 5：保留 `BEAM_NOT_ASSOCIATED` code

為維持既有 validation 分類、Review filtering 與 downstream code compatibility，warning code 與 severity 不變。只修改觸發條件及顯示文字，例如：

> `BMx 的托梁路徑未與任何正式支撐或斜撐形成有效接觸，未建立支撐禁止點。`

Brace-only Beam 不產生替代 warning 或 info；其可追溯工程狀態由 `brace_contacts` 表達。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer 或 dependency direction：

- **DXF recognition／pure operations**：擁有 finite-contact eligibility 與 association rebuild。
- **DXF models**：擁有 immutable runtime `BeamBraceContact` 與座標投影。
- **DXF Review workflow／Presentation**：只消費 rebuilt result 與 validation messages，不自行判斷幾何。
- **Application／Domain／Algorithms**：不接收 Brace contact；既有 Project → Solver boundary不變。

依賴維持：

```text
DXF Presentation -> DXF Review Workflow
                 -> Recognition / Review Pure Operations
                 -> DXF Models / Geometry

Project / Solver boundary <- only existing Strut BeamCrossing projection
```

## Backward Compatibility 與 Persistence

- `associate_components_to_struts` 新參數為 keyword-only 且有空 tuple 預設，避免破壞尚未更新的窄幅 caller；正式完整流程必須傳入 Braces。
- 既有 Beam 建構不提供 `brace_contacts` 時使用空 tuple，測試 fixtures 與舊 runtime code 可漸進更新。
- 不修改 Project schema、saved Project payload 或 migration version。
- paused Review 仍由 source fresh recognition 重建 derived contacts；不需要把 runtime contact 另行序列化成 Project truth。
- `BeamCrossing`、`component_associations`、`BeamPositions` 與 `AssociatedBeamIDs` 的格式和數量只受既有 `Beam.crossings` 決定。

## Risks / Trade-offs

- **[Risk] 一般 Beam path 有多個 segments，可能在同一 Brace 上形成重複端點交點** → 依 Beam／Brace／`beam_crossing_duplicate_tolerance_mm` 等價 WCS point 去重；segment index 不參與 identity，同一 Brace 在兩個不等價真實位置的 contacts 不合併。
- **[Risk] 相鄰 segments 共用頂點，或 path／iteration order 改變造成重複或不穩定 provenance** → identity 明確排除 segment index，先以 Beam／Brace／tolerance-equivalent WCS point 分組，再以 normalized segment geometry 選 canonical provenance；測試正反 path 與 reversed iteration。
- **[Risk] formal Brace 被排除後沿用 stale contact** → 每次 rebuild 由目前 formal Brace collection 重建並取代 `brace_contacts`；空集合重新套用唯一 connected predicate。
- **[Risk] 只更新 importer，rebuild 後 warning 回來** → inventory 所有 `associate_components_to_struts` callers，focused tests 覆蓋 `rebuild_component_associations` 與 Waler adjustment。
- **[Risk] 共用 helper 抽取造成 BIM Joist regression** → 先以既有 contact boundary tests 固定 helper 行為，再切換 caller；執行完整 `test_dxf_bim_joist_recognition.py` regression。
- **[Risk] 新 Beam field 影響 confirmation hashes** → 這是預期行為；只要 contact 未變，deterministic ordering 必須保持相同 signature。
- **[Trade-off] runtime Beam model增加一個 DXF-only field** → 換取可追溯 relationship 與 rebuild 一致性；不向 Project／Solver 擴散。

## Migration Plan

1. 先加入 model 與 pure helper，保持既有 caller 行為。
2. 讓 BIM importer 映射 Brace contact，補 coordinate／confirmation tests。
3. 擴充 association rebuild 接收 formal Braces，切換 initial import 與各 derived rebuild caller。
4. 更新 warning 條件與文字，執行 focused／fixture regression。
5. 實作驗證成功後更新 `docs/DOMAIN.md` 的 Beam contact 與 Beam station 區分。

回滾時可同批回退新 model field、helper routing 與 caller keyword，不涉及資料 migration 或已保存 Project 轉換。
