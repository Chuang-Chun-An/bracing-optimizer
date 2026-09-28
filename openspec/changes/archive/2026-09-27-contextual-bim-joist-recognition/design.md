# Design

## Context

見 [proposal.md](./proposal.md) 的問題背景。現行 `DXFImporter.convert()` 依 role 建立 geometry groups，再由 generic Beam path 將一個 candidate 轉成一個 `Beam`。`_validate_one_model_per_source()` 原則上禁止同一 source handle 產生多個工程模型；`build_review_items()` 則為每個 `Beam` 建立一個以 BM ID 選取的 `ReviewItem`。`DXFImportResult.to_project_rows()` 已能把多個 `BeamCrossing` 投影為 Strut 的 `BeamPositions`／`AssociatedBeamIDs`，因此 Project schema 不需要新增 assembly entity。

本次 characterization 重新以目前 local Y05 DXF whole-source geometry 驗證 Beam roots：

- 目前 fixture 有 84 個 Beam-layer root `INSERT`。其中 38 個是主構件 roots：20 個雙 C roots 與 18 個完整 C 型角落 single-Joist roots。其餘 46 個是 L-75×75×9 detail／residual roots；幾何取樣皆落在某個主構件 root 的 20 mm 範圍內，不得另建 Beam。generic path 目前產生 39 個 Beam：20 個雙 C roots 被錯誤壓成各一支、18 個完整 C 型 roots 各一支，另將殘線 root `16DE` 誤認成一支。
- 找到 20 個 whole-source double-C roots。每個 root 的六條主要 longitudinal lines 可由 topology 唯一分為兩個 C envelopes；每個 root 應建立兩支實體 Joists，共 40 支。
- 另有六個角落各 3 個 Brace-contact single-Joist roots，共 18 支；完整 Y05 formal Joist baseline 因此為 58 支。
- 兩個 envelope center axes 的 transverse separation 在 20 個 double-C roots 都是約 `518.000 mm`。
- `428.000 mm` 是 inner clear gap；`441.0 mm`／`443.5 mm` 是不同 C 規格的 web-center spacing，均不是實體 Joist 軸的 station spacing。
- E8F 顯示 source truth 與 engineering contact 必須分離：一個大 C250 root 橫跨 S5～S8並支持兩條完整軸；四個分別位於 S5～S6、S7～S8 的 L-angle roots（16BC、16C6、16DF、16E0）只是高度重疊細節，不補畫軸也不另建 Beam。E8F 的 terminal axes 停在 S5 外緣，距 S5 中心線 `175.0 mm`，恰為可靠 `350.0 mm` Strut width 的一半。
- 20 個 paired assemblies 可能各自跨越多支 Struts；在目前正式 Strut／Column context 下，48 組 direct crossings 加上 20 組 width-qualified terminal face contacts，合計形成 68 組有效 paired-axis-to-Strut contact relations。這是 relationship count，不是 Joist 或 assembly count。實際 station spacing 為 `518.000–518.001 mm`；Column midpoint absolute error為 `0–0.942 mm`。先前 planning 的 53 組是只補入 5 組 terminal contacts 的不完整 characterization；逐 root 執行相同 eligibility 後，20 個 paired roots 均各有一組合法 terminal face relation。

使用者據此確認正式 contract：

```text
joist_pair_nominal_station_spacing_mm = 518.0
joist_pair_station_spacing_tolerance_mm = 5.0
joist_pair_column_midpoint_tolerance_mm = 2.0
joist_strut_face_contact_tolerance_mm = 25.0

abs(actual_spacing - 518.0) <= 5.0
abs(pair_midpoint - column_station) <= 2.0
```

四個設定皆使用 inclusive boundary；前三個只適用於 whole-source geometry 已證明的雙 C 型 BIM Joist assembly，face-contact tolerance 只適用於具有可靠 source width 的 formal Strut terminal contact。

## Goals / Non-Goals

**Goals:**

- 以 pure whole-source recognition 明確產生 single-axis 或 paired-axis outcome。
- 讓可靠 double-C root 代表兩支實體 Joists，而不是一條總中心軸或局部 rail pair。
- 使用 formal immutable Strut／Brace／Column context 建立 finite perpendicular contacts 與兩支托梁 assembly。
- 讓 paired root 可靠映射為兩個 Beam models、兩個 deterministic BM IDs、兩個 Strut stations 與共同 root provenance。
- 維持 Review、source exclusion／restore、manual replay safety、Pause／Resume 與 Project conversion 的既有 lifecycle。

**Non-Goals:**

- 不把 518 mm 規則套到一般 Joist、未知型式或只看起來像兩條平行線的來源。
- 不修改 upstream Waler／Strut／Brace／CornerBrace／Column recognition identity。
- 不新增通用 contextual-recognition framework，也不修改 future member DTO。
- 不修改 Solver、材料規則、Beam exclusion `±550 mm`、Project schema 或 DXF persistence file format。
- 不用 Block name、INSERT point、外框最近距離或任意 nearest snap 當工程證據。

## Architecture Alignment

本 change 沿用現有 DXF vertical subsystem 與長期 dependency direction：

```text
Waler → Strut → Brace → CornerBrace → Column → Joist
```

箭頭表示 recognition stage ordering 與 upstream context visibility，不表示每個 stage 只能依賴緊接前一個 type。Joist stage 可以讀取本 capability 明確需要的 Strut、Brace、Column formal context；不得反向修改 upstream source recognition truth。

責任分配：

- `dxf_import/joist_recognition.py`（新增的小型 pure module）：whole-source topology、single／paired outcome、finite contact 與 pairing rule。輸入只含 immutable DTO，不依賴 importer、workflow 或 UI。
- `dxf_import/importer.py`：維持 reader／pipeline adapter 責任，完成 upstream stages 後建立 immutable Joist context，路由 Beam roots，將 outcomes 轉成既有 candidates／models。
- `dxf_import/models.py`：沿用 `Beam`、`BeamCrossing`、`ComponentAssociation` 與 Project row conversion；不新增 Project entity。
- `dxf_import/validation.py`、`review_confirmation.py`、`source_exclusion.py`：投影 diagnostics、paired source-level confirmation／exclusion semantics 與 replay safety，不重新實作幾何規則。
- Presentation 只顯示兩個 BM IDs、共同來源與 problems，不計算 spacing 或配對。

Single source of truth：axis truth 來自 Beam root whole-source WCS geometry；contact／pair truth 來自 pure Joist outcome；Project 僅接收 finalized crossings。UI、Review 與 conversion 不得各自重算第二套 518 mm 規則。

## Decisions

### 1. 使用 tagged outcome 表達 single-axis 與 paired-axis

Pure service 使用 immutable input／outcome，概念上包含：

```text
JoistRecognitionInput
  root identity, WCS primitives, role
  + JoistContextSnapshot(formal Struts, Braces, Columns)

JoistRecognitionOutcome
  not_applicable
  recognized_single(axis, contacts, provenance)
  recognized_pair(assembly, exactly two axes, contacts, provenance)
  failed(diagnostics)
  ambiguous(diagnostics)
```

`recognized_pair` 必須由一個 source-level assembly 擁有兩條 axes；它不是兩次獨立 recognition 恰巧得到兩支 Beam。這讓 importer 能對 one-source safety rule 開啟窄例外，並阻止第三條 model 或未證明的 duplicate。

一般 root 仍最多一支 single-axis Beam。Component-like root 一旦進入 `failed`／`ambiguous`，不得回到 generic local parallel-pair fallback；只有不符合 BIM eligibility 的 `not_applicable` 可維持 legacy path。

### 2. Double-C eligibility 由 whole-source topology 證明

辨識順序：

1. 由同一 root 的全部 WCS primitives 建立穩定 longitudinal direction，排除短橫線與 detail geometry 主導方向。
2. 依 connectivity、outline topology、transverse location、width compatibility 與 longitudinal coverage 建立 C-envelope hypotheses。
3. 只有恰有兩個完整、互不重疊且可唯一區分的 C envelopes 時，建立 paired hypothesis。
4. 每一實體 Joist axis 取該 envelope 的 center axis，terminal extent 由其 whole-source longitudinal evidence 決定。
5. 對 normalized WCS axes 做 geometry-derived 排序；排序不依 child order、LINE direction 或 enumeration order。

大 interior gap 不自動截短 axis，只要相同 root、方向、transverse alignment、width 與 topology 的 whole-source evidence 仍連續解釋同一 envelope。反之，不得跨 root 或把方向／寬度不相容 fragments 拉入。

### 3. Joist context 在 upstream recognition 完成後建立

Importer 先完成 Waler、Strut、Brace、CornerBrace、Column 的 recognition、deduplication 與 exclusion，再建立只含 formal finite WCS geometry 的 `JoistContextSnapshot`。Unresolved、excluded、preview-only geometry 不進 snapshot。

Pure service contract 固定為：

```text
member source geometry
  + applicable immutable upstream engineering context
  → pure recognition outcome
```

Upstream context 只能驗證 span、finite contact、support 與 assembly；不能創造 Beam axis。Contact／association 的 canonical finalization 可以建立 downstream relation，但不得重新辨識或改寫 upstream member identity。

### 4. Crossing station 來自有限直接相交或具寬度證據的端面接觸

每一 axis 與每一 formal Strut／Brace finite segment 先做實際 segment intersection，並用具名 perpendicular angular tolerance 判斷垂直接觸。有效 direct contact 保存：root／axis identity、upstream member ID、WCS intersection、沿 Strut 的 station 與 Joist segment index。

Strut 另允許嚴格的 `endpoint_face_contact`：只檢查 source-supported axis 的 terminal endpoint；endpoint 沿 axis outward direction 投影必須唯一命中有限 Strut 中心線，Joist／Strut 必須近似垂直，Strut 必須有可靠正值 source width，且 `abs(projection_distance - source_width / 2) <= 25.0 mm`。Contact 同時保存外緣 `source_contact_point` 與中心線 `engineering_crossing_point`；axis geometry 不延伸、不改寫，station 只由 engineering point 計算。多支 Strut 同時合格時為 blocking ambiguity。

一般 infinite-line intersection、內部點 extension、外框 nearest distance、INSERT point 與 Brace endpoint-face contact 均不合法。如此 518 mm 的輸入仍來自兩條實體 axis 對同一 Strut 的工程站位，而不是圖塊內其他尺寸或任意吸附。

### 5. Pair eligibility 先過硬條件，再使用 nearest 排序

對每一 formal Strut／Column relation：

1. 取得與同一有限 Strut 實際垂直接觸的 paired-axis contacts。
2. 驗證兩個 stations 位於同一 Column station 的相反兩側；等於 Column station 不算任何一側。
3. 計算 `actual_spacing = abs(station_b - station_a)`，要求 `abs(actual_spacing - 518.0) <= 5.0`。
4. 計算 `pair_midpoint = (station_a + station_b) / 2`，要求 `abs(pair_midpoint - column_station) <= 2.0`。
5. 僅在全部通過的 eligible pairs 中，以各側 longitudinal distance 作 deterministic 排序。
6. 無 eligible pair 回報 blocking unpaired；有多組工程上等價、無法唯一區分的 eligible pairs 回報 blocking ambiguity，不使用 ID 或 entity order tie-break。

513 mm、523 mm 與 midpoint ±2 mm 都合法；任何嚴格超界值都不合法。這三個值以具名 Joist constants 集中定義，不沿用 geometry epsilon 或其他 member tolerance。

### 6. 一個 paired root 產生兩個 Beam models 與 BM IDs

`recognized_pair` 在 importer staging 中展開為兩個 `_Candidate`／`Beam`：

- 各 Beam 使用自己的 envelope-center axis、line candidate、crossings 與 deterministic BM ID。
- 兩者保留相同 root `source_handles`、Block provenance 與 paired recognition method。
- staging 同時帶有 ephemeral assembly key 與 normalized axis slot（0／1），供 one-source validation、排序與 sibling 聚合使用；不寫入 Project schema。
- `_validate_one_model_per_source()` 只在兩個 candidates 來自同一成功 `recognized_pair`、axis slots 完整且數量恰為 2 時放行。只靠相同 `recognition_method` 或相同 handle 不足以取得例外。
- 全域 BM numbering 在 geometry-derived candidate order 後執行，確保 entity reordering 不交換 sibling axes 的相對 mapping。

這個決策比「一個 Beam model 內藏兩條 axis」更符合現有模型：Preview、Review、`BeamCrossing`、Strut `AssociatedBeamIDs` 與 `BeamPositions` 都以一條實體 Beam 為單位，也不需新增複合 Project entity。

### 7. Review 保留兩個 BM rows，但 source lifecycle 以 assembly 為原子

`build_review_items()` 仍為兩個 Beam models 建立兩個可選取的 `ReviewItem`，使用不同 BM IDs 定位各自 geometry。兩者顯示同一 root provenance。

目前 confirmation identity 是 `role + source_handles`；paired siblings 因此天然共享 identity，但現行 signature 只 hash 單一 member，會互相覆寫。本 change 將 paired source 的 signature 改為 deterministic aggregate：包含兩個 normalized Beam states、共同 coordinate system 與該 assembly 的 problems。兩個 ReviewItems 對同一 identity 取得相同 signature，所以確認任一 row 即代表確認整個 source-level assembly；任一 sibling 或 relation 改變時一起失效。一般單模型 source 維持原 signature 行為。

Source exclusion 仍保存 root source identity。因兩個 Beam 共用 root，從任一 row 排除時 staging impact 應明示兩個 BM IDs，commit 後兩者一起移除；restore 對 root 重新辨識並只在 paired outcome 再次唯一合法時恢復兩支。Shared-handle conflict 檢查需將同一已證明 paired assembly 視為預期 siblings，不顯示為意外 ownership conflict；其他 shared-handle collision 仍照舊阻擋／提示。

現有 manual override persistence 只以 `role + exact source_handles` 識別，沒有 axis slot。為避免 schema migration與錯誤套用，fresh rebuild 若存在 per-axis override 而無法以兩條 normalized geometry 唯一配對，沿用 `needs_review` safety outcome，不使用 BM ID 或 collection order 猜測。Live session 中針對指定 BM 的 edit 仍可操作；本 change 不把不具唯一 replay identity 的輸入宣稱為可自動恢復。

### 8. Project conversion 沿用既有 Beam rows 與 Strut fields

每一 Beam 產生自己的 existing auxiliary row，並以 `BeamCrossing` 記錄對應 Strut station。成功 paired assembly 對同一 Strut 產生兩個 crossings：

- Strut `BeamPositions` 含兩個 station。
- Strut `AssociatedBeamIDs` 含兩個 BM IDs。
- 每個 Beam row 保留自己的 `AssociatedStrutIDs`／`Crossings`。
- DXF debug／review state 保留 shared root provenance 與 recognition diagnostics。

不輸出 518、midpoint 或 paired assembly 作為新的 Project 欄位；它們是 DXF relationship finalization 的 derived evidence。失敗／模糊／未配對 outcome 不得滲入 Project rows。既有 `±550 mm` exclusion 對兩個 station 分別生效。

### 9. Brace-only Joist 保持 single-axis route

可靠 single-axis Joist 與 formal Brace 形成唯一有限垂直接觸，且沒有未完成的 Strut／Column assembly obligation 時，可以保留一支 Beam。它不套用 518 mm pair rule，也不產生假的第二支 Beam。若同一來源同時有 blocking Strut relation，Brace contact 不得掩蓋錯誤。

### 10. Diagnostics 以 source outcome 與 member impact 分層

Axis failed／ambiguous、paired topology invalid、spacing invalid、same-side、Column midpoint invalid、unpaired 與 multiple eligible pairs 均產生具 root handle 的 `ValidationMessage`。能唯一指出 paired members 的 relationship problem 同時填入兩個 `member_ids`，避免 `build_problem_records()` 因 shared root owners 無法歸屬。

Blocking outcome 保持 Error／Critical gate；成功但值得注意的來源細節才可是 Warning。Presentation 只顯示 code、描述、BM IDs 與 provenance，不自行判斷 eligibility。

## Characterization and Boundary Test Matrix

| 類別 | 輸入 | 預期 |
|---|---:|---|
| spacing lower boundary | 513.0 mm | eligible |
| spacing nominal | 518.0 mm | eligible |
| spacing upper boundary | 523.0 mm | eligible |
| spacing below | `< 513.0 mm` | reject |
| spacing above | `> 523.0 mm` | reject |
| midpoint lower boundary | -2.0 mm | eligible |
| midpoint center | 0.0 mm | eligible |
| midpoint upper boundary | +2.0 mm | eligible |
| midpoint outside | absolute error `> 2.0 mm` | reject |
| side qualification | both crossings same side | reject |
| selection ordering | nearest pair ineligible, farther pair uniquely eligible | choose eligible pair |
| ambiguity | multiple eligible pairs remain | blocking ambiguity |
| proxy geometry | 428 / 441 / 443.5 / width / INSERT point | never substitute for 518 |
| Y05 source inventory | 84 raw roots = 38 member roots + 46 overlapping detail／residual roots | detail roots produce no Beam |
| Y05 component inventory | 20 paired assemblies／40 paired axes + 18 corner single axes | 58 formal Joists |
| endpoint-face exact | distance = Strut width / 2 | eligible, preserve source axis |
| endpoint-face inclusive boundary | half-width difference = 25.0 mm | eligible |
| endpoint-face outside | half-width difference > 25.0 mm | reject |
| endpoint-face ambiguous | multiple eligible Struts | blocking ambiguity |
| Y05 relationship inventory | 68 characterized paired-axis-to-Strut contact relations | all valid |

Y05 integration assertion 除構件總數外，應逐一比對 root、Strut、contact method、source／engineering contact points、兩個 stations、spacing、Column 與 midpoint error，避免「剛好仍有 68 組 relation 但配錯」通過測試；E8F／S5 必須走 endpoint-face contact，六個角落也應逐角落確認恰有 3 支 Brace-contact single Joists。

## Rejected Alternatives

- **一個 root 永遠只能一支 Beam**：與已 characterization 的雙 C physical axes 衝突，會遺失一個 station。
- **一個 compound Beam model 內藏兩條 axes**：破壞現有一 Beam／一軸／一 BM ID 的 Preview、Review 與 Project conversion contract。
- **以全部 rails 的總中心作一條 axis**：把兩支實體 Joists 合併，且 station 會落在 Column 中心。
- **使用 428 mm、441／443.5 mm 或 width**：這些是不同幾何尺寸，不是兩個 envelope center axes 的 Strut crossing station spacing。
- **先取 Column 各側最近再檢查**：可能選到不合 spacing／midpoint 的 pair；nearest 只能是 eligibility 後排序。
- **以 BM ID／entity order 解 ambiguity**：不是工程證據且會使重建不穩定。
- **為 paired axis 新增 Project assembly schema**：現有 Beam rows 與 Strut fields 足以表達兩個實體 crossings，沒有 migration 必要。

## Risks / Trade-offs

- **[雙 C topology 過度泛化]** → eligibility 必須先由 whole-source envelope topology 證明；518 contract 不參與一般 root 的型式猜測。
- **[Shared root 打破一來源一模型假設]** → 只接受 pure outcome 明示的 exactly-two paired batch，並補 one-source validator、Review sibling 與 regression tests。
- **[同一 confirmation identity 的兩個 rows 互相覆寫]** → 使用 assembly aggregate signature，兩 row 得到相同 signature，source-level 一起確認／失效。
- **[Manual replay 無 axis sub-identity]** → 不新增 persistence schema；不能由 normalized geometry 唯一重配時回報 needs review，絕不依 ID 猜測。
- **[Y05 fixture 更新造成 brittle count]** → 同時保留 pure boundary fixtures；Y05 regression 逐組驗證 root／Strut／stations 而非只看 aggregate count。
- **[Upstream context 不完整]** → 只消費 formal snapshot；缺少必要 Strut／Column 時產生可追溯 blocking outcome，不修改 upstream recognition。

## Migration Plan

1. 先加入 pure topology、axis、direct／endpoint-face contact、spacing、midpoint 與 ambiguity characterization tests，固定 Y05 的 20 個 paired assemblies／40 支 paired Joists、18 支 corner single Joists、58 支 formal Joists與 68 組 paired-axis-to-Strut relations baseline。
2. 實作 immutable Joist DTO／service，再接入 Beam role router；每一步保持 legacy Beam tests 綠燈。
3. 接入 importer staging 與 exactly-two one-source validation，建立兩個 Beam models／BM IDs。
4. 接入 finite direct contacts、width-qualified endpoint-face contacts、pair finalization、diagnostics 與 Project projection。
5. 更新 Review aggregate confirmation、source-atomic exclusion／restore 與 manual replay safety。
6. 跑 focused DXF suites、Review／persistence suites及 full suite；實作驗證完成後才更新長期 Architecture／Domain 文件。

Rollback 可移除 Beam-role BIM router，恢復 legacy Beam path；沒有 Project schema 或資料 migration 需要回滾。
