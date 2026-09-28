# Design

## Context

動機與行為範圍見 [proposal.md](proposal.md)。目前 `DXFImporter.convert()` 先建立 Brace candidate，再由 `connect_components_to_walers()` 對 Brace 兩端分別尋找距離端點 `connection_tolerance_mm = 250` 內的最近有限 Waler segment；連接後才建立 Candidate Points、validation messages 與 Review derived state。

Y05 characterization 顯示 BIM whole-axis recognition 已正確工作，但部分來源只畫到實體斜撐的一段：root `9E9` 兩端沿軸向各約 425 mm 可命中 W1／W2，現況為 `BRACE_NOT_CONNECTED`；root `B9C` 一端已連 W4，另一端沿軸向約 528 mm 可命中 W5，現況為 `BRACE_ONE_END_NOT_CONNECTED`。這些是 finite-segment intersections，不是 Waler 無限延長線交點。

`CandidatePointBuilder` 已有計算 axis／Waler intersection 的局部邏輯，但把候選限制在原端點前後 `connection_tolerance_mm`；正式連接函式則只做 endpoint-to-segment distance。若直接在兩處各自放寬條件，會形成兩套不同的 connection truth。

既有 `bim-block-brace-recognition` 要求 recognition 不得為了碰到 Waler 而越過 terminal source evidence。新規格將此責任切清楚：BIM recognition axis 仍完全由 source geometry 決定；只有後續 connection operation 可以沿該軸向建立 finite-Waler formal endpoint。

## Goals / Non-Goals

**Goals:**

- 讓 Brace direct connection 與 outward-axis extension 共用一個 pure resolution contract。
- 對每個未連接端只採用 outward ray 上最先且唯一的 finite Waler intersection。
- 讓 formal geometry、`FromWaler`／`ToWaler`、Candidate Points、diagnostics 與 Review rebuild 使用同一 resolution。
- 保持 source-supported recognition axis、root provenance 與 connection-adjusted formal geometry 的責任界線。
- 以 Y05 真實 root handle 建立 regression，並保護一般 Brace、Strut 與 BIM recognition 行為。

**Non-Goals:**

- 不修改 component-like classification、whole-axis scoring、width、material 或 ambiguity policy。
- 不讓 Strut 或 CornerBrace 使用新的軸向延伸。
- 不新增 Project／paused Review persistence schema，也不保存 BIM child topology 至 Project。
- 不新增 UI、人工 Guided Recognition、Solver 行為或 Waler recognition 規則。

## Architecture Alignment

本 change 沿用既有 DXF subsystem architecture，不修改 layer boundary：

既有 recognition stage order `Waler → Strut → Brace → CornerBrace → Column → Joist` 表示 stage ordering 與 cumulative upstream context visibility，不是只能消費緊鄰 stage。Brace 是 Waler 的 downstream stage，因此完成自身 recognition 後，可以直接讀取已完成 upstream Waler 的 formal immutable engineering context，不需要透過 Strut 間接取得；雖然 Brace 也可看見適用的 Strut context，本 change 實際只使用 Waler geometry 完成 connection／canonical finalization，且不擴大至 Strut → Brace contextual recognition，也不建立 generic dependency framework。

本 change 的責任界線為：

```text
Brace source geometry
    → Brace recognition outcome

recognized Brace + applicable upstream formal immutable Waler context
    → connection / canonical finalization outcome
```

Waler context 不進入 Brace recognition winner selection。Connection／finalization 只能在 recognition 完成後採用有限 Waler 交點，不得反向改變 `component-like` classification、recognition winner、recognized axis、representative／source width 或 root provenance。這是既有單向 stage contract 允許的 downstream context consumption，不是新的反向 dependency。

```text
DXFImporter / recognition pipeline
        ↓
pure Brace-Waler connection resolution
        ↓
DXFImportResult formal Brace + diagnostics
        ↓
DXFReviewWorkflow snapshot / manual replay
        ↓
DXFImportResult.to_project_rows()
```

- `dxf_import/geometry.py` 或 `candidate_points.py` 內的 pure helper 負責 WCS ray／finite-segment intersection 與 deterministic ordering。
- `dxf_import/candidate_points.py` 的 connection operation 負責把 pure resolution 映射為 immutable `Brace` replacement 與 `ValidationMessage`。
- `DXFReviewWorkflow` 繼續只主持 staged mutation、manual replay 與 confirmation invalidation，不自行解讀射線幾何。
- `dialog.py` 只顯示既有 member、Candidate Point 與 message projection，不加入工程判斷。
- `block_member_recognition.py` 不接收 Waler collection，避免 Waler context 反向影響 BIM recognition winner。

依賴方向維持 `DXF Presentation → DXFReviewWorkflow → pure recognition/review operations → models/geometry`。沒有新的跨層 shortcut。

## Decisions

### 1. Recognition axis 與 formal connection geometry 分開

BIM service 輸出的 `whole_axis` 仍是 source-supported recognition result。Connection operation 收到既有 `Brace` 後，才可由該直線的兩個 outward rays 求 Waler 交點並更新 formal endpoints。

這表示：

- Waler 數量、位置或順序不得改變 `recognized`／`failed`／`ambiguous`、recognition axis、`source_width` 或 root provenance。
- formal Brace 的 `start`／`end` 可以在合法 connection 後位於 terminal source evidence 外，但必須仍在相同無限軸線上。
- `recognition_method` 維持來源辨識方法，例如 `bim_block_whole_axis`；connection method 透過 runtime diagnostic 與 Candidate Point provenance 表達，不偽裝成另一種 recognition。

拒絕方案：在 `block_member_recognition.py` 內加入 Waler geometry。這會讓 Waler context 選擇 recognition winner，違反已封存的 BIM source contract。

### 2. 建立單一 pure Brace connection resolution

新增一個小型、無 UI／workflow dependency 的 internal resolution function。概念輸入為：

- 一支 Brace 的 WCS start／end、source identity 與 `selection_source`；
- 目前正式 Walers 的 WCS finite segments；
- `GeometryTolerances`。

概念輸出為兩個 endpoint resolutions，每端至少包含：

- original endpoint；
- `direct`、`axis_extension`、`missing` 或 `ambiguous` status；
- adopted point、Waler ID、extension distance；
- competing Waler IDs（若 ambiguous）。

此 DTO 為 internal runtime value，不加入 `DXFImportResult` persistence。`connect_components_to_walers()` 與 Candidate Point／diagnostic mapping 都消費同一 resolution，避免各自重算選擇規則。

Strut 繼續使用現有 `connect(point, ...)` finite-distance 流程。只有 Brace 走新增 resolution。

### 3. Direct connection 優先，extension 只處理未連接端

每端依序：

1. 使用現有 endpoint-to-finite-segment 距離與 `connection_tolerance_mm` 嘗試 direct connection。
2. direct 成功即固定該端，不再比較遠方 ray intersections。
3. direct 失敗時，建立從該端遠離另一端的 unit outward direction。
4. 求 outward ray 與每一有限 Waler segment 的真實交點。
5. 只保留 ray parameter `t > 0` 且 segment parameter 落在既有 endpoint numeric tolerance 內的候選。

`connection_tolerance_mm` 不再限制 extension distance。這是刻意的 contract：Y05 需要 425～528 mm，而新增另一個任意固定上限只會把同一問題換成另一個 magic number。安全性由可靠軸向、outward direction、finite segment、nearest boundary 與 ambiguity rejection共同提供。

拒絕方案：把 `connection_tolerance_mm` 從 250 mm 全域放大。這會同時放寬 Strut 與側向 nearest-point 連接，且無法表達「只能沿 Brace 軸」。

拒絕方案：新增 600 mm／1000 mm 等未經工程確認的 extension cap。本 change 沒有得到此工程 boundary；Y05 fixture 距離只作 regression，不升級為全域 tolerance。

### 4. 最先有限交點是 boundary，近距多解則 blocking

合法 intersections 以 `(extension_distance, normalized intersection point, stable Waler geometry identity)` deterministic 排序。工程選擇只使用 distance：

- 最近位置只有一支 Waler：採用它。
- 後方其他 Waler：視為已被第一個有限 Waler boundary 擋住，不參與競爭。
- 最近兩個 distance 的差值 `<= ambiguous_connection_delta_mm`：回傳 `ambiguous`，不以 ID 或 input order 強行選擇。

Stable Waler geometry identity 僅用於讓輸出與 diagnostics 排序穩定，不得打破工程 ambiguity。

若兩端最終指向同一 Waler，回報 blocking `BRACE_SAME_WALER_CONNECTION`。合法完成仍要求兩支不同 Waler。

建議 diagnostics：

- `BRACE_AXIS_EXTENDED_TO_WALER`：info，包含 Brace、端別、Waler 與 extension distance。
- `AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION`：error，列出最近 competing Waler IDs。
- `BRACE_SAME_WALER_CONNECTION`：error。
- 找不到交點時沿用 `BRACE_NOT_CONNECTED`／`BRACE_ONE_END_NOT_CONNECTED`，避免建立重複 failure truth。

### 5. 每端獨立 resolution，整支 Brace 仍需兩端完整才可完成 import

現有 workflow 允許一端 snapped、另一端未連接，並用 `BRACE_ONE_END_NOT_CONNECTED` 阻擋完成。本 change 保留此行為：

- 某端 direct／extension 成功，就更新該端 endpoint 與 Waler ID。
- 另一端 missing／ambiguous 時保留其 source-supported endpoint。
- world／local coordinates 在 WCS connection 階段保持一致，之後再由既有 `CoordinateSystem` projection 建立 local result。
- 只有兩端都成功且 Waler 不同，才不產生 not-connected blocking problem。

這不是跨 Project 的 transaction；所有變更仍位於 staged `DXFImportResult`，完成 Review 前不會寫入 `ProjectDataModel`。

### 6. Candidate Points 與 diagnostics 不建立第二套選擇邏輯

Candidate Point mapping 使用已採用 resolution：

- adopted endpoint 仍是 selected／recommended point；
- source handles 同時包含 Brace root 與 Waler source；
- label／point type 表達 finite Waler intersection；
- `BRACE_AXIS_EXTENDED_TO_WALER` 提供 direct 與 extension 的可診斷差異。

其他未採用的 axis/Waler intersections 可以作為 Review 選項，但必須由同一 pure intersection enumeration 產生；不得由 `CandidatePointBuilder` 另外套一套 250 mm gate 或排序規則。

手動 endpoint selection 後，既有 direct snap 仍可執行；新的 auto axis extension 只套用於 `selection_source == "auto"` 的 Brace。如此 manual candidate／CAD manual line 不會被自動延伸靜默覆寫，manual replay 仍是 authoritative user decision。

### 7. Review lifecycle 與 state ownership 不變

`DXFReviewWorkflow.world_result` 仍是 live session 的 WCS authoritative state。Source exclusion／restore、Waler contact adjustment 或其他 recognition rebuild 後，由既有 rebuild pipeline 重新計算 connection resolution、messages 與 Candidate Points；不保存指向已排除 Waler 的獨立 cache。

Confirmation invalidation 依既有 member geometry／problem mutation 處理。Pause／Resume 儲存既有 Review state與 manual decisions，不新增 required field；重新辨識後的 auto connection可由目前 geometry deterministic 重建。

### 8. Backward compatibility 與 persistence

- `Brace.to_project_row()` contract 不變；成功後只輸出既有 `StartX/Y`、`EndX/Y`、`FromWaler`、`ToWaler`。
- 不新增 Project schema、DXF managed asset schema或 migration。
- 舊 paused Review 沒有 extension metadata 仍可載入；auto result 由目前 source geometry 重建，manual replay 依既有 identity 套用。
- 一般非 BIM Brace 只要已形成 reliable straight candidate，也使用相同連接 contract；這是刻意的 role-level行為。一般端點已在 tolerance 內者會走 direct path，結果不變。
- Strut、CornerBrace、Waler contact adjustment 及 Solver contracts不變。

## Single Source of Truth

| Concern | Authoritative source |
| --- | --- |
| BIM Brace recognition axis | `block_member_recognition` 的 source-supported outcome |
| Brace endpoint-to-Waler selection | pure Brace connection resolution |
| Live formal WCS Brace geometry | `DXFReviewWorkflow.world_result` 中的 `Brace` |
| Manual endpoint decision | 既有 Review manual override／replay state |
| Project Brace geometry | Review 完成後由 `DXFImportResult.to_project_rows()` commit 的 row |

Recognition axis 與 formal connection endpoint 是先後不同責任，不是兩份互相競爭的正式 state。Runtime diagnostic 可記錄 extension distance，但 Project 只保存最後採用的正式工程幾何。

## Risks / Trade-offs

- [沿射線很遠處的第一支 Waler 可能不是設計意圖] → 僅允許 reliable Brace 軸、outward finite intersection，最近位置多解即阻擋，並在 Review 顯示 extension diagnostic；不發明未確認距離上限。
- [Waler 端點或相接 Waler 造成幾乎同位置的多解] → 使用既有 `ambiguous_connection_delta_mm` 作為 recognition tuning boundary並回報 blocking ambiguity，不以 ID 選擇。
- [Candidate Points 與正式 connection 再次漂移] → intersection enumeration／resolution 只實作一次，Candidate mapping 消費其結果。
- [人工 endpoint 被重建流程覆寫] → 新 extension 僅用於 `selection_source == "auto"`，manual replay 後只沿用既有 direct validation。
- [修改共同連接函式意外影響 Strut] → 保留 Strut 原路徑，新增 role-specific Brace tests 與 Strut regression。

## Migration Plan

1. 先以 pure synthetic fixtures 鎖定 outward ray、finite intersection、nearest／ambiguous 與 start/end reversal。
2. 將 Brace connection 接到 pure resolution，保留 Strut direct path。
3. 讓 Candidate Points 與 Review rebuild 使用同一 resolution，補 manual replay regression。
4. 加入 Y05 `9E9`、`B9C` 及一般 Brace regression。
5. focused／full regression 與 OpenSpec verification 通過後，更新 `docs/WORKFLOW.md` current behavior。

若需 rollback，移除 Brace-specific extension route即可恢復既有 endpoint tolerance 行為；無 persistence migration需要回復。
