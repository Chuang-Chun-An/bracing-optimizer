# Design

## 閱讀導航

- **P0／現在必讀**
  - 「方案摘要」與「決策對照」。
  - Decision 1（共用 canonical row contract）、Decision 2（validation before hydration）及 Decision 3（移除 legacy conversion）。
  - Decision 5（保留版本政策、更新復原指引）。
- **P1／實作前閱讀**
  - Decision 4（移除 offline tool）、Architecture Alignment、測試矩陣與 Migration Plan。
  - 兩份 delta specs 的全部 Requirements。
- **P2／需要時再讀**
  - 修改 Main 時閱讀 Presentation read-only 風險。
  - 發現 dependency cycle 時閱讀 Decision 1 的 fallback。
- **本次可先跳過**
  - Solver、DXF recognition、CAD transport與export設計；本 change 不修改它們。

## 方案摘要

```text
Project JSON
    |
    v
version compatibility validation
    |
    v
canonical table/row shape validation
    |
    v
Domain validation --> hydrate staged Project --> adopt

DXF/CAD/manual runtime input --> Application defaults --> canonical Project rows
```

`canonical row` 是欄位集合與 Application 正式 table contract完全一致的 persisted row；`runtime defaults` 是新建 row 時的 Application convenience，不是 Project load migration。兩者以 hydration boundary 明確分開。

## 決策對照

| Decision | 影響的 Spec Requirement | 對應 Tasks |
| --- | --- | --- |
| 1. Persistence重用唯一 canonical row contract | Project input 必須符合現行 table contract | 1.1、2.1 |
| 2. Row shape validation先於Domain與hydration | 結構驗證必須先於 hydration | 2.1、2.2 |
| 3. 移除Application legacy field cleanup與Main的Strut read-time conversion | 已載入資料不得再做legacy migration；runtime builder不得包含legacy-specific cleanup；正式儲存輸出必須可原樣重新驗證 | 3.1–3.3 |
| 4. 移除offline upgrade tool | project-schema-compatibility old-structure guidance | 4.1、4.2 |
| 5. 保留版本矩陣，只更新復原指引 | 以版本上限與現行結構共同判斷；拒絕時提供可行下一步 | 2.3、4.2 |

## Context

動機見 `proposal.md` 的 Why。已封存的 `project-schema-compatibility` 明定 load path 不得猜測欄位、補值或轉換資料，但目前 `ProjectSerializer` 只檢查必要 Domain tables、row object、ID uniqueness 與 Domain mapping；缺少正式 position fields 或含額外 legacy fields 的 row 可能通過此階段。之後 `ProjectDataModel.from_case_data()` 會經 `normalize_legacy_fields()` 修補 row，Main 的 detail／Tree／Preview 又有 `_migrate_strut_position_fields()`，因此實際行為與正式 spec 不一致。

Application 已以 `TABLE_SPECS`／`TABLE_COLUMNS` 定義 walers、struts、braces、inventory與material_specs 的正式欄位及 runtime defaults。Infrastructure目前也已依賴 Application 的 `ProjectRowMapper` 執行 Domain validation，所以重用無副作用的 row contract不會新增依賴方向類型。

## Goals / Non-Goals

**Goals:**

- 讓 persisted Project row shape 在 hydration前可被完整、通用且可診斷地驗證。
- 消除 load、Application model與Presentation中的legacy Strut position migration。
- 保留 runtime新建資料使用defaults的便利，但阻止它掩蓋persisted schema錯誤。
- 移除試行期舊Project的upgrade入口；格式不符時提供重新匯入DXF或重新輸入資料的明確下一步。

**Non-Goals:**

- 不把所有 top-level Project fields 改成exact-key validation。
- 不改 optional Project setting tables目前是否可缺少的政策。
- 不改 position value parser、Domain validation或工程語意。
- 不批次刪除既有 Project case files，也不建立新 migration framework。
- 不掃描、盤點或判讀既有 Project JSON；舊檔由使用者自行刪除。
- 不決定未來新增 row 欄位時要提升 schema version、補預設值或拒絕舊檔；既有政策未定義此事。

## Decisions

### Decision 1：共用 Application canonical row contract，不建立 legacy 黑名單

Persistence structure validation重用 Application既有的 table／column definitions作為single source of truth：

- 保留既有必要 tables規則。
- 保留目前允許缺少的 optional tables規則。
- `input_data` 中出現 contract未知的 table即拒絕。
- 每個已提供 table的每筆 row必須具有與該 table完全相同的 key set；回報 missing與unsupported keys。

Validator不詢問未知 key是否為 `Beam1`、`Type` 或其他歷史名稱，也不選擇 migration。這讓 legacy欄位與任意拼錯／未支援欄位走同一規則。

這項完全比對只鎖定本 change 實作時的固定 schema 3 contract。既有主 spec、封存 design、`docs/WORKFLOW.md` 與 README 均未定義未來新增 row 欄位時的版本提升、預設值或拒絕策略；因此本 decision 不得被延伸解讀為欄位演進政策。未來欄位集合若改變，須先另行決定相容策略。

若直接 import `TABLE_COLUMNS` 造成未預期 circular dependency，fallback是把 `TABLE_SPECS`／`TABLE_COLUMNS` 移到最小、無 Infrastructure依賴的 Application contract module，讓 `project_data`、persistence、CAD adapter與Main共用；不得在persistence複製另一份columns常數。

拒絕方案：在serializer中列出四個legacy position keys。這只修一種舊格式，無法保證「目前格式」是唯一真相。也拒絕只檢查missing fields而忽略extra fields，因為舊資料可能同時帶current與legacy欄位，仍會形成模糊輸入。

### Decision 2：Structure validation先於Domain validation與hydration

`validate_for_load()` 維持既有version檢查順序，missing／older／current進入同一current-structure validator。該validator先驗證input tables與row key sets，再執行既有ID、Domain與DXF asset validation。所有驗證成功後，`ProjectService`才呼叫hydration。

Save path也使用相同current-structure validator，確保正式輸出可原樣round-trip。Runtime `ProjectDataModel`仍可用defaults建立new／DXF／CAD／manual rows；但這只發生在runtime creation boundary，不得用於修補load payload。

拒絕方案：先hydrate再檢查normalized output。那會丟失原始schema mismatch證據，且使validation實際驗證的是Application猜測後的資料，而不是使用者提供的Project。

### Decision 3：移除Application legacy field cleanup與Strut read-time mutation

`normalize_project_row()` 與 `build_input_row()` 保留 current columns projection與runtime defaults，但不再呼叫legacy-specific normalizer。移除Application中的 `Beam1`／`Beam2`、`Column1`／`Column2` assembly，以及Brace row大寫 `Type` cleanup；目前正式runtime ingress若提交非canonical欄位，應在其自己的current contract修正，而不是恢復通用legacy migration。

Main移除 `_migrate_strut_position_fields()` 與detail、Tree、Preview呼叫。這些路徑只解析及顯示 `BeamPositions`／`ColumnPositions`，不得原地mutation。

Brace legacy `Type` cleanup目前在 `normalize_legacy_fields("braces", row)` 移除brace row的大寫 `Type`，並可由CAD add的`build_input_row()`，以及Project load hydration、DXF apply、`replace_table()`、`replace_row()`共用的`normalize_project_row()`路徑執行。調查顯示new Project不建立brace row；DXF `Brace.to_project_row()`、CAD row data及manual edit均不產生或依賴大寫 `Type`。因此移除該cleanup；CAD event外層lowercase `type: "brace"`只是事件分類，必須保持不變。

拒絕方案：保留Main helper作為保險。它會讓Presentation再次成為schema migration owner，並讓顯示順序影響正式Project state。

### Decision 4：刪除offline schema upgrade工具與對應承諾

刪除 `tools/upgrade_project_schema.py`、僅驗證該工具的tests及README命令。因試行期舊Project可重建，系統不維護無正式資料保存承諾的schema 1／2轉換。刪除前以repository search確認沒有production code、packaging或automation依賴該tool；若發現正式用途，停止apply並回到proposal重新定界。

拒絕方案：留下移除Strut conversion後的半套tool。現有tool的責任正是把舊結構改為schema 3；保留只會讓使用者誤以為舊格式仍受支援。

### Decision 5：版本標籤相容矩陣不變，統一row／table mismatch recovery

保留主 spec中valid integer、missing、older、current、future及save-to-current行為。missing／older的old-structure，以及missing／older／current的row／table schema mismatch，均使用「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並附上底層驗證錯誤。這只統一格式不符的復原指引，不改變版本接受矩陣。

這表示 `schema_version: 2` 只要內容已完全是current shape仍可開啟；它不是legacy data migration。版本標籤與資料shape仍分開判斷。

拒絕方案：趁本change改成只接受version 3。那會推翻已封存、已apply的版本政策，且不是移除legacy Strut normalization所必需。

## Architecture Alignment

本 change沿用既有Architecture，不修改dependency direction：

- **Infrastructure**：擁有Project JSON與current structure validation，重用Application的pure row contract。
- **Application**：擁有runtime row defaults、Project hydration與`ProjectDataModel`；不再擁有legacy persisted-row conversion。
- **Presentation**：只顯示canonical rows，不執行migration或Project mutation。
- **Domain／Algorithms／DXF subsystem**：不變。

Single source of truth是Application table／column contract；Infrastructure驗證它，Application建立它，Presentation消費它。不得在三層各保存一份欄位清單或legacy rules。

## Backward Compatibility 與 Persistence Impact

- 這是刻意的breaking change：不符合current table／row shape的試行Project無法再透過tool或lazy migration使用。
- missing／older version labels仍可載入，但payload shape必須current。
- `schema_version`仍為3，saved JSON的current fields與position values不變。
- 現有合法Project不需轉檔；格式不符時顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」及底層驗證錯誤。
- Load failure維持零副作用，不刪除或改寫來源檔。

## 測試矩陣

| Boundary | Cases | 驗證 |
| --- | --- | --- |
| Row schema | canonical、missing field、extra field、unknown table、optional table absent | 通用contract判斷與可診斷錯誤 |
| Version compatibility | missing／older＋canonical、missing／older＋invalid、current invalid、future | 保留既有矩陣，只更新recovery message |
| Hydration | invalid payload帶有可被runtime default補足的欄位缺失 | hydration不執行、current state不變 |
| Runtime ingress | new、DXF、CAD、manual、row replacement | 儲存前得到canonical rows，未依賴legacy conversion |
| Presentation | detail、Tree、Preview重複執行 | rows deep-equal、dirty不變 |
| Offline tool removal | repository references、README、tests | 無production／docs殘留入口 |

## Risks / Trade-offs

- **[Risk] Contract定義與正式產生路徑不一致** → 不掃描既有Project檔；改以`TABLE_SPECS`、serializer contract及new／DXF／CAD／manual現行產生路徑的focused tests驗證。若來源契約不一致，回到proposal處理，不以legacy exception放行。
- **[Risk] Optional tables政策被誤改** → 明確保留目前required／optional table distinction，只收緊已提供row的shape。
- **[Risk] Runtime ingress依賴legacy helper** → 逐一跑new／DXF／CAD／manual focused tests；只修正current ingress mapping，不恢復load migration。
- **[Risk] Active `centralize-...` change造成衝突** → apply前確認它未被實作，並只套用本change；後續由使用者決定如何清理superseded artifacts。
- **[Trade-off] 舊試行Project無法就地復原** → 這是已確認產品政策；錯誤訊息提供重新建立與DXF匯入的可行下一步。

## Migration Plan

1. 不掃描既有Project檔；以正式contract產生的測試payload與synthetic invalid payload建立canonical／invalid characterization tests。
2. 加入共用row-shape validator，先在load與save boundary驗證，再執行既有Domain／asset checks。
3. 移除Application的Strut position legacy conversion、Brace `Type` cleanup與Main lazy migration，逐一路徑跑runtime／Presentation tests，並確認CAD event外層lowercase `type`分類維持不變。
4. 確認offline tool沒有production caller後，刪除tool、專用tests與文件入口；同步更新compatibility error guidance。
5. 執行Project service／persistence、Main editing、CAD／DXF apply、architecture boundary與OpenSpec verification。

不執行舊資料批次migration或檔案刪除。Rollback若必要，應回復code與spec guidance至同一版本；不得只恢復tool或Main helper而重新產生隱性相容路徑。
