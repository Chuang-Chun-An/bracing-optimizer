# Tasks

## 實作前閱讀

- **Task Group 1 前**：讀 `proposal.md`「現況與目標／不變事項」、`design.md` Context與Decisions 1–2，以及兩份spec的全部Requirements。
- **Task Group 2 前**：讀 `design.md` Decisions 1–2及`project-input-row-schema`的「Project input 必須符合現行 table contract」「結構驗證必須先於 hydration」。
- **Task Group 3 前**：讀 `design.md` Decision 3及`project-input-row-schema`的「已載入資料不得再做 legacy migration」「正式儲存輸出必須可原樣重新驗證」，並區分Brace row大寫`Type`與CAD event外層lowercase`type`。
- **Task Group 4 前**：讀 `design.md` Decisions 4–5及`project-schema-compatibility` delta的兩項MODIFIED Requirements。
- **Task Group 5 前**：讀 `design.md`測試矩陣／Migration Plan，並回看proposal的Out of Scope防止擴張成persistence重寫。
- **可先跳過**：`docs/SOLVER.md`與Solver／DXF recognition specs；本change不修改其行為。

## 1. 鎖定現行格式與整合邊界

- [x] 1.1 確認 `centralize-legacy-strut-position-normalization` 尚未被apply，並檢查 `project_persistence.py`、`project_data.py`、`main.py` 與相關tests的既有未提交修改；以列出重疊區域且不覆寫其他change為驗證，若已實作舊change則停止並回報。
- [x] 1.2 不掃描任何既有Project檔；以`TABLE_SPECS`、serializer contract、正式產生路徑建立的測試payload及synthetic invalid payload，建立necessary／optional tables、canonical keys、missing key、extra key與unknown table的row-shape characterization。
- [x] 1.3 盤點new Project、DXF apply、CAD add／update、manual edit、`replace_table`／`replace_row`與save payload產生路徑，確認它們輸出的正式row keys；以每個production ingress都有現有或新增focused test，且無正式metadata落在`TABLE_COLUMNS`之外為完成條件。
- [x] 1.4 以new Project、DXF apply、CAD add／update與manual edit focused tests鎖定Brace正式row不產生或依賴大寫`Type`；另以CAD event tests證明外層lowercase`type: "brace"`分類不受cleanup removal影響。

## 2. 建立通用 Project row schema validation

- [x] 2.1 讓Infrastructure重用Application唯一的table／column contract；若直接import造成cycle，只抽出最小pure contract module並同步既有consumers，且以architecture boundary tests及`TABLE_COLUMNS` identity／equality tests證明沒有第二份欄位清單。
- [x] 2.2 在 `bracing_optimizer/infrastructure/project_persistence.py` 於Domain mapping與hydration前驗證allowed／required tables及每筆row的exact key set，統一回報table、row、missing與unsupported keys；以Task 1.2的canonical／invalid tests全部通過，且validator不含legacy field名稱為驗證。
- [x] 2.3 擴充Project service／navigation tests，證明missing／older version加canonical shape仍可載入，missing／older／current加invalid row shape均拒絕，future behavior不變，且任一失敗不修改committed input、results、DXF state、path或dirty state。
- [x] 2.4 驗證save boundary以同一current structure contract檢查輸出，並加入DXF／CAD／manual Project save後原樣reload的round-trip tests；以不需要任何migration即可成功載入為驗證。
- [x] 2.5 對row／table schema mismatch驗證兩份spec共用的訊息「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並確認同一錯誤附上table／row／field等底層驗證錯誤。

## 3. 移除 Application legacy field conversion與Presentation read-time mutation

- [x] 3.1 從 `bracing_optimizer/application/project_data.py` 移除`normalize_legacy_fields`、`_legacy_position_list`及其export，使`build_input_row()`／`normalize_project_row()`只投影current columns並套用runtime defaults，不再組合Strut legacy positions或清理Brace大寫`Type`；以Project model tests證明current rows不變、source mapping不被修改，且legacy conversion tests已移除或改為schema rejection tests。
- [x] 3.2 從 `main.py` 移除 `_migrate_strut_position_fields()`、其格式化專用helper與detail／Tree／Preview呼叫；以Main editing tests證明三個read paths只讀`BeamPositions`／`ColumnPositions`，重複執行後rows deep-equal且dirty state不變。
- [x] 3.3 執行Task 1.3列出的DXF／CAD／manual ingress focused tests，若發現current production mapping依賴legacy helper，只在該入口改為直接產生current fields；以所有正式runtime rows可儲存並通過Task 2 validator為驗證。
- [x] 3.4 使用`rg`確認production code不再引用`Beam1`、`Beam2`、`Column1`、`Column2`、`_legacy_position_list`、`normalize_legacy_fields`或`_migrate_strut_position_fields`；若命中CAD event外層lowercase`type`或其他domain無關的同名資料，逐筆確認而不做廣泛刪除。

## 4. 移除離線升級入口並更新相容指引

- [x] 4.1 先以repository search確認 `tools/upgrade_project_schema.py` 沒有production、packaging或automation caller，再刪除該tool與只驗證legacy upgrade的tests；以無有效code reference且正常test discovery成功為驗證，若發現正式caller則停止並回到proposal。
- [x] 4.2 更新Project compatibility錯誤stage／detail、README與`docs/WORKFLOW.md`，將舊結構指引改為「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，且附上底層驗證錯誤；完整保留missing／older／current／future矩陣，以Project service tests與文件搜尋不再出現Project schema upgrade指引為驗證。
- [x] 4.3 移除README tree與操作章節中的upgrade tool入口，並檢查其他文件是否宣稱legacy Strut positions可轉換；以相關文件與兩份delta specs一致、且未改Solver／DXF recognition文件為驗證。

## 5. 回歸與 OpenSpec 驗證

- [x] 5.1 執行Project persistence／service／navigation、Project data／domain、Main editing、CAD integration、DXF apply與architecture boundary focused suites；以全部通過且無無關測試降級或刪除為驗證。
- [x] 5.2 依focused結果擴大執行完整test suite；以所有相關回歸通過，或任何既有無關failure均有可重現證據與明確回報為驗證。
- [x] 5.3 執行`openspec validate remove-legacy-strut-position-normalization --strict`，再使用`$openspec-verify-change`對照proposal scope、`project-input-row-schema`全部scenarios、`project-schema-compatibility`修改及tasks；確認無未完成task、無舊change混用及無未回報限制。
