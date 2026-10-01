# 移除 Legacy Strut Position 相容轉換提案

## 閱讀導航

- **P0／現在必讀**
  - 本文件的「快速摘要」、「現況與目標」、「主要流程」與「不變事項」。
  - `specs/project-input-row-schema/spec.md` 的「Project rows 必須符合現行欄位契約」與「載入後不得再轉換資料列」。
  - `specs/project-schema-compatibility/spec.md` 修改後的 old-structure 與 failure guidance scenarios。
- **P1／實作前閱讀**
  - `design.md` Decisions 1–5、驗證順序與測試矩陣。
  - `tasks.md` 的實作順序與驗證項目。
  - 主 spec `openspec/specs/project-schema-compatibility/spec.md`，確認已封存的版本標籤政策不被推翻。
- **P2／需要時再讀**
  - `bracing_optimizer/application/project_data.py`、`bracing_optimizer/infrastructure/project_persistence.py` 與 `main.py` 的現有 row normalization／load／display 路徑。
  - `tools/upgrade_project_schema.py` 與 README 升級說明，只在移除舊升級入口時閱讀。
- **本次可先跳過**
  - Solver、DXF recognition、CAD event、結果輸出與材料政策 specs；本 change 不改其工程行為。

## 快速摘要

- 已封存的版本相容政策規定 load path 不得猜測、補值或轉換舊結構，但目前 Project validation 後仍可能由 Application／Main 將 legacy Strut position 欄位轉成現行欄位。
- 本 change 不再辨識 `Beam1` 等特定舊欄位；所有 Project rows 一律以共用的現行欄位契約驗證，任何缺少必要欄位或含不支援欄位的 row 都視為格式不符。
- Application 與 Main 移除 legacy position migration；Tree、Preview、detail 直接使用 `BeamPositions`／`ColumnPositions`。同時移除 Application 中未被現行入口依賴的 Brace row legacy `Type` cleanup。
- 試行期舊 Project 不再提供離線升級，移除 upgrade tool；不掃描既有 Project 檔。格式驗證失敗時回報「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並附上底層驗證錯誤。
- missing／older／current／future 的既有版本標籤政策、schema version 3、Domain validation 與儲存 transaction 保持不變。
- 已封存政策只規定固定 schema 3 的載入驗證，不曾決定未來新增 row 欄位時應升版、補預設值或拒絕舊檔；此項政策目前為「未定義」，本 change 不自行補定。

## 現況與目標

此處的「現行欄位契約」是 Application 已定義、目前正式儲存所使用的各 Project table column set；它不是針對某組 legacy key 的黑名單。

| 面向 | Before（現況） | After（目標） |
| --- | --- | --- |
| Project row 驗證 | 驗證 table、ID 與 Domain 值，但未完整比對現行欄位集合 | Persistence 在 hydration 前以共用 table contract 驗證必要欄位與不支援欄位 |
| 舊 position 欄位 | Application、Main、offline tool 各自轉換 | 不辨識、不轉換；整列依現行格式判定合法性 |
| UI 讀取 | Tree、Preview、detail 可能原地 migration | 只讀 `BeamPositions`／`ColumnPositions`，不得改寫 row |
| 舊 Project 處理 | 提示並提供 offline upgrade tool | 不掃描或轉換既有檔；格式不符時明確拒絕，顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」及底層驗證錯誤 |
| 版本相容 | missing／older 標籤只要現行結構合法即可載入 | 完全保留；版本標籤相容不等於舊資料格式相容 |

## 主要流程

1. 讀取 Project JSON，先依既有政策驗證與分類 `schema_version`。
2. 對 missing／older／current 版本使用同一現行 Project 結構驗證。
3. 以正式 table column contract 檢查每筆 Project row：必要欄位完整且沒有不支援欄位後，才執行 Domain validation。
4. 驗證成功才 hydrate `ProjectDataModel`；Application 與 Presentation 不再補救或轉換已載入 rows。
5. 格式不符時維持既有 Open transaction 零副作用，顯示「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並附上底層驗證錯誤。

## 不變事項

- `schema_version` 仍為 `3`；不新增 schema 4，也不改 missing／older／current／future 的版本分類。
- 正式 position 欄位仍是 `BeamPositions`／`ColumnPositions`，其 Domain parse 與工程語意不變。
- DXF import、CAD event 與手動建立等 runtime ingress 仍可由 Application 依正式 defaults 建立 canonical rows；本 change 只禁止 Project load 以 legacy migration 補救不合法 persisted rows。
- Project Open 仍先完整 hydrate staged state，成功後才採用；失敗時目前 Project、results、DXF state、path 與 dirty state不變。
- 不重寫 persistence、Solver、DXF lifecycle 或 Project transaction。

## 版本相容政策調查結論

結論：**未定義**「未來新增 row 欄位時，舊 Project 應提升 schema version、補預設值，或視為格式不符」。本 change 不補上這項版本演進政策。

- 主 spec `openspec/specs/project-schema-compatibility/spec.md` 的「以版本上限與現行結構共同判斷是否可載入」只規定：missing／older／current 必須「完整通過現行 schema 3 結構與 Domain 驗證」，且 load 「不得偵測舊格式特徵、猜測欄位、補值或轉換資料結構」。
- 已封存 change `openspec/changes/archive/2026-10-01-define-project-schema-compatibility-policy/design.md` 的 Non-Goals 明載：「不設計 schema 4，不改 schema 3 欄位，也不加入 migration registry。」Decision 2 只要求 load/save 共用 current structure validation，沒有定義欄位演進方式。
- `docs/WORKFLOW.md` 的 Project schema compatibility 段落重述 fixed schema 3 的載入規則與「不在 load path 自動轉換」，沒有新增欄位政策。
- `README.md` 的載入相容政策同樣只描述 schema 3；「16.7 要修改資料欄位」只列出以 `project_data.TABLE_SPECS` 為起點及需同步檢查的模組，沒有規定版本提升、預設值或拒絕策略。

本 change 的 row key 完全比對僅定義**目前固定 schema 3 contract** 的驗證方式，與既有「載入不得補值或轉換」一致。它不得被解讀為未來欄位演進政策；未來若要變更 `TABLE_SPECS` 欄位集合，必須先另行決定版本與相容策略。本次調查未發現與既有政策直接不一致之處。

## Why

版本相容 change 已確立「舊版本標籤可相容、舊資料結構不可在 load path 轉換」，但現有 legacy Strut normalization 讓不符合現行 row shape 的資料仍可能在 validation 後被修補。試行期資料可重新由 DXF 建立，因此應移除這條隱性相容路徑，讓現行格式驗證成為唯一載入門檻。

## What Changes

- 新增 Project input row 的通用現行欄位驗證，依 table contract 回報缺少及不支援欄位，不針對特定 legacy key 寫特例。
- **BREAKING**：移除 `Beam1`／`Beam2`、`Column1`／`Column2` 等 legacy Strut position 的 Application normalization、Brace row legacy `Type` cleanup 與 Main lazy migration；不符合現行 row schema 的 persisted Project 不再可藉由載入或顯示流程轉換，runtime row builders也不再包含legacy-specific cleanup。
- 移除 `tools/upgrade_project_schema.py` 及其 legacy upgrade tests／文件入口；試行期不掃描或轉換既有 Project 檔，舊檔由使用者自行刪除。
- 修改既有 `project-schema-compatibility` capability 的 old-structure 與錯誤指引，移除「執行升級工具」，保留版本分類與 transaction semantics。
- 新增 canonical／missing-field／unsupported-field、older-label-current-shape、load failure零副作用及 UI read-only regression tests。
- 本 change 取代尚未實作的 `centralize-legacy-strut-position-normalization`；兩者不得同時 apply。

## Scope

### In Scope

- Persisted Project `input_data` rows 的現行欄位集合驗證。
- Application 與 Main 中直接相關的 legacy Strut position conversion removal。
- Application 中 Brace row legacy `Type` cleanup removal；CAD event外層 lowercase `type`分類不受影響。
- Offline Project schema upgrade tool、其測試與文件入口的移除。
- `project-schema-compatibility` 的 old-structure recovery guidance 更新。
- README／WORKFLOW 中 Project load 與試行期舊資料處理說明。

### Out of Scope

- 改變 `schema_version: 3` 或 missing／older／current／future 分類。
- 為 legacy keys 建立黑名單、個別錯誤類型或專用 migration。
- 要求 DXF／CAD／manual runtime input 必須攜帶完整 persisted row；它們仍由 Application 建立正式 row。
- 全面要求 Project JSON 所有 top-level optional fields 改為 required。
- Persistence framework 重寫、通用 migration registry、Project cases 批次刪除或轉檔。
- 掃描、盤點或判讀 workspace 中的既有 Project JSON；舊檔由使用者自行刪除。
- Solver、DXF recognition、材料規則與 export 行為。

## Capabilities

### New Capabilities

- `project-input-row-schema`: 定義 persisted Project table rows 必須符合現行 canonical column contract，並禁止 hydration／Presentation 對不合法 rows 做 legacy migration。

### Modified Capabilities

- `project-schema-compatibility`: 保留既有版本標籤相容矩陣，但將無法通過現行結構驗證時的下一步改為「無法以現行格式讀取；請建立新專案，並重新匯入 DXF 或重新輸入資料」，並附上底層驗證錯誤。

## Impact

- **預期程式範圍**：`bracing_optimizer/infrastructure/project_persistence.py`、`bracing_optimizer/application/project_data.py`、`main.py`，並刪除 `tools/upgrade_project_schema.py`。
- **預期測試範圍**：Project schema／service／persistence、Project domain／Main editing，以及最接近的 CAD／DXF apply regression tests。
- **文件與 specs**：新增 `project-input-row-schema`；修改 `project-schema-compatibility` delta；更新 README 與必要的 WORKFLOW truth。
- **既有 change**：`centralize-legacy-strut-position-normalization` 被本 change 取代但不在本次 proposal workflow 中刪除，避免未授權的破壞性操作。
- **Architecture／Domain／Solver／Workflow truth**：沿用既有 Architecture 與 Domain；修改 Project Open workflow 的格式拒絕與復原指引，不影響 Solver。

## 尚未決定與重新評估條件

- 現行 row contract 應重用 Application 已有的 table column definitions；若 implementation 發現 persistence 匯入它會造成 circular dependency，應抽出最小的無副作用 Application contract module，而不是在 Infrastructure 複製欄位清單。
- 若 production fixture 證明某個正式 DXF／CAD ingress 仍會把 raw legacy keys 寫入 `ProjectDataModel`，應先確認該 ingress 是否仍屬現行產品契約；只有現行入口才在 Application boundary修正，不得恢復 Project load migration。
- 若離線工具仍有非 legacy Project 的正式使用情境，必須回到 proposal 重新界定工具責任；不得保留部分舊格式猜測轉換作為隱性相容層。
