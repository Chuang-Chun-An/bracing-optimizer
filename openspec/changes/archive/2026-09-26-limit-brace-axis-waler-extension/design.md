# Design

## Context

動機與行為範圍見 [proposal.md](proposal.md)。目前 Brace-to-Waler connection 先以 `GeometryTolerances.connection_tolerance_mm = 250.0` 做端點到有限 Waler segment 的 direct snap；對仍未連接且 `selection_source == "auto"` 的 Brace，`dxf_import/brace_waler_connection.py` 會沿端點 outward axis 列出所有有限 Waler 真實交點，採用最近唯一交點，但沒有最大延伸距離。

`CandidatePointBuilder` 直接呼叫同一個 `outward_waler_intersections()`，因此目前也會把任意遠的交點顯示為 `extended_axis_waler_intersection`。正式連接與 Review 候選雖共用 enumeration，仍需在同一 contract 加入上限，否則只修其中一條路徑會再次形成兩套 truth。

本 change 修正既有 `brace-axis-waler-extension` capability；不改變 Brace source recognition、stage ordering或 Project commit boundary。

## Goals / Non-Goals

**Goals:**

- 保留 250 mm direct snap，並把自動 outward-axis extension 限制為 `<= 600 mm`。
- 讓 pure resolution、Candidate Points、diagnostics 與 Review rebuild 共用同一個 Brace 專用距離設定。
- 保護 Y05 約 425 mm 與約 503 mm（歷史觀測約 528 mm）的有效延伸，同時拒絕長距離猜測。
- 對超距離端點保留來源幾何及既有 blocking validation，不產生半套正式連接。

**Non-Goals:**

- 不把 direct snap 改為 600 mm，也不修改全域 `connection_tolerance_mm`。
- 不修改 Brace recognition winner、whole axis、source width、provenance 或 component-like classification。
- 不修改 Strut、CornerBrace、Waler、Solver、Project schema或人工 endpoint contract。
- 不新增 UI 設定、generic connection framework或其他 recognition refactor。

## Architecture Alignment

本 change 沿用既有 DXF subsystem architecture，不修改 Architecture boundary：

```text
Brace source geometry
    → Brace recognition outcome

recognized Brace + upstream immutable Waler geometry
    → pure Brace-Waler connection resolution
    → formal Brace / Candidate Points / diagnostics
    → DXFReviewWorkflow staged state
    → completed import
```

- Recognition 仍只由 Brace source geometry 決定；600 mm 僅限制 recognition 完成後的 connection／canonical finalization。
- `dxf_import/brace_waler_connection.py` 持有 pure、Brace-specific 的候選合法性與 deterministic selection。
- `candidate_points.py` 只映射同一 pure候選／resolution，不自行複製距離規則。
- `DXFReviewWorkflow` 繼續持有 live staged WCS result、manual replay 與 confirmation invalidation；Presentation 只顯示結果。
- 依賴方向仍為 `DXF Presentation → DXF Review application → recognition/connection operations → models/geometry`。

這是沿用既有 Architecture 的局部安全邊界修正，不是新的 architecture change。

## Decisions

### 1. 250 mm direct snap 與 600 mm axis extension 是兩個不同 contract

每個自動 Brace endpoint 仍依序執行：

1. 以既有 `connection_tolerance_mm = 250 mm` 做 endpoint-to-finite-Waler direct snap。
2. direct 成功即採用，不進入軸向延伸。
3. direct 失敗才沿 outward axis 列舉 finite-Waler intersections。
4. 只保留 extension distance `> 0` 且 `<= 600 mm` 的交點。
5. 在合法交點內套用既有 nearest 與 ambiguity 規則。

600 mm 是 Brace 自動辨識／連接的保守安全設定，不是所有 member 共用的工程接觸容許值，也不改變 direct snap 的側向最近點行為。

拒絕方案：把全域 `connection_tolerance_mm` 從 250 改為 600。這會放寬 Strut、CornerBrace及其他 association／validation，且允許 Brace 沿側向改變方向，不符合本需求只補足短距離軸向缺口的目的。

拒絕方案：完全回到 direct snap 並只把 Brace direct tolerance 改成 600。即使做成 role-specific，也會採用 endpoint 到 segment 的最短二維投影而非 Brace 軸線交點，可能改變 Brace 方向。

### 2. 新增具名且只由 Brace extension 消費的 recognition setting

在 `GeometryTolerances` 新增：

```python
maximum_brace_axis_extension_mm: float = 600.0
```

此欄位是 internal recognition setting。它控制自動 Brace outward-axis intersection 是否可成為 connection candidate；不屬於 Project persistence、Solver input或材料／結構 Domain rule。

此欄位是 600 mm 的 single source of truth。Production code不得另寫未命名的 `600.0`，Candidate Points也不得建立第二個相同常數。

### 3. 在共用 outward-intersection enumeration 套用上限

`outward_waler_intersections()` 已只屬於 Brace-Waler connection service，且同時被正式 endpoint resolver 與 `CandidatePointBuilder` 使用。它應以 `GeometryTolerances.maximum_brace_axis_extension_mm` 篩除超距離交點，再回傳依 `(extension_distance, stable geometry key)` 排序的合法候選。

正式 connection 呼叫時的 origin 是尚未調整的 source-supported Brace endpoint。`CandidatePointBuilder` 接收到的 member 可能已完成 formal connection，因此列舉額外候選時 MUST 從既有 `selected_candidate_id` 對應的 recognition line 還原 source-supported endpoints，並依目前 start/end orientation 對齊方向；不得從已延伸後的 formal endpoint 再量 600 mm。若已連接的 legacy/runtime Brace 無法取得 source line，採保守策略不再產生 outward extension 候選，避免形成連續延伸。

如此可保證：

- resolver 不會採用 `> 600 mm` 的 Waler；
- Candidate Points 不會顯示 formal resolver 不可能採用的超距離自動候選；
- source exclusion／restore 與 recognition rebuild 自然重算相同行為；
- 沒有第二套 UI 或 diagnostics 距離判斷。

`= 600 mm` 合法，`> 600 mm` 不合法。距離上限本身不使用 `endpoint_tolerance_mm` 擴張，避免把明確的 600 mm 邊界變成隱含 650 mm。

### 4. 先做合法性篩選，再做 nearest／ambiguity

Selection 順序為：

1. finite segment 真實交點；
2. outward direction；
3. extension distance `<= 600 mm`；
4. nearest boundary；
5. 既有 `ambiguous_connection_delta_mm`。

因此 590 mm 的唯一合法 Waler可被採用；605 mm 的另一支 Waler即使距離差只有15 mm，也不參與 ambiguity，因為它本身不是合法延伸候選。若兩支 Waler 都在 600 mm 內且距離差落入既有 ambiguity boundary，結果仍是 blocking `ambiguous`。

Stable geometry key 只讓相同輸入在不同 collection order 下得到一致排序，不得用來打破工程 ambiguity。

### 5. 超距離沿用既有 missing／not-connected lifecycle

若一端沒有 600 mm 內合法交點：

- endpoint resolution 維持 `missing`；
- adopted point維持 source-supported endpoint；
- 不產生 `BRACE_AXIS_EXTENDED_TO_WALER`；
- 整支 Brace 依另一端狀態沿用 `BRACE_NOT_CONNECTED` 或 `BRACE_ONE_END_NOT_CONNECTED`；
- unresolved item 留在 staged DXF Review，不能完成 import；
- 既有 committed Project 與 Solver result 不受影響。

本 change 不新增專用 persisted status或 required schema field。若未來需要在 UI 區分「完全無交點」與「最近交點超過 600 mm」，應另行提出可觀察行為；本次以既有 blocking message為安全結果。

### 6. 人工端點與 recognition source truth 不變

自動 axis extension 仍只套用於 `selection_source == "auto"`。Manual endpoint replay／人工選點不會被 600 mm 自動延伸規則覆寫；使用者可透過既有 Review 操作修正 source／endpoint，但超距離交點不得被列為自動推薦候選。

Connection/finalization 不得反向修改：

- Brace recognition status或 winner；
- recognized whole axis；
- representative/source width；
- root source handles與 provenance。

### 7. Backward compatibility 與 persistence

- `Brace.to_project_row()`、`DXFImportResult`、paused Review與 Project schema皆不變。
- 舊檔案可照常開啟；行為只在重新執行 DXF recognition／Review rebuild 時依新 setting計算。
- 已在 250 mm 內 direct-connected 的 Brace不變。
- 250～600 mm 內且唯一的 outward-axis intersection仍可完成連接。
- 原本自動延伸超過 600 mm 的 Brace將改為 unresolved；這是本 change刻意的安全收斂。

## Single Source of Truth

| Concern | Authoritative source |
| --- | --- |
| Direct snap 距離 | `GeometryTolerances.connection_tolerance_mm` |
| Brace axis extension 最大距離 | `GeometryTolerances.maximum_brace_axis_extension_mm` |
| 合法 axis/Waler 候選與 deterministic ordering | `outward_waler_intersections()` |
| 每端採用結果 | pure Brace connection resolution |
| Live formal WCS Brace geometry | `DXFReviewWorkflow.world_result` 中的 `Brace` |
| Manual endpoint decision | 既有 Review manual override／replay state |

## Risks / Trade-offs

- [實際有效缺口略大於 600 mm 時會被拒絕] → 採保守 blocking行為，保留 source endpoint並讓使用者在 Review／CAD修正；不以長距離自動猜測換取較高完成率。
- [使用者誤以為 direct snap 已改為 600 mm] → Spec、diagnostic tests與文件明確分開 250 mm direct與600 mm axis extension。
- [Candidate Points 與正式 resolution 漂移] → 在共用 enumeration套用 named setting，兩個 consumer不得各自過濾。
- [Y05 asset版本或 handle 改變使真實檔 regression脆弱] → 同時建立精確 600 mm synthetic boundary tests；真實案例驗證工程結果與距離範圍，不以 collection order決策。

## Migration Plan

1. 先補 pure service characterization，鎖定 250 mm direct不變、`= 600 mm` 接受、`> 600 mm` 拒絕與合法候選後方超距離 Waler不造成 ambiguity。
2. 新增 named setting並在共用 outward intersection enumeration套用。
3. 驗證 formal resolution、Candidate Points、diagnostics與Review rebuild結果一致。
4. 執行 Y05有效短距離案例、超距離案例及Strut／manual regression。
5. 完成 focused與完整回歸後，才把新 current behavior同步至 `docs/WORKFLOW.md`。

Rollback只需移除 Brace-specific上限篩選與 named setting；沒有 persistence migration或資料回復作業。
