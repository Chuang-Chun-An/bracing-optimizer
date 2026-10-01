# Proposal

## 閱讀導航

- **現在必讀（P0）**：本文件的「摘要」、「What Changes」、「In Scope / Out of Scope」與「Capabilities」。
- **實作前閱讀（P1）**：`specs/support-shim-joint-validation/spec.md` 的全部 Requirements、`design.md` 的 Decisions、`tasks.md`。
- **需要時再讀（P2）**：`docs/DOMAIN.md` 的 Support layout hard rules、`docs/SOLVER.md` 的 11.1 SupportPlanEditing 與 14 Known Solver Gaps，以及既有 `dxf-double-support-recognition`、`support-editor-result-mutation` 規格。這些既有 capability 不在本 change 中改寫。

## 摘要

- 正式定義每個 Support ordered layout 只能有零塊或一塊非零 Shim；零長 Shim 不得成為 ordered piece。
- RC terminal Shim 與其第一段相鄰 Steel 的交界，是端部 `1600 mm` joint exclusion 的唯一例外；Column／Beam 禁區不豁免。
- 缺失、空白或無法辨識的 Waler 類型一律正規化為 Steel，因此不得使用 RC terminal 例外。
- 自動 Solver 與人工 Support 編輯共用同一套 Shim count、placement 與 joint validation；可解析但違規的人工排列仍可保存為 invalid。
- 固定錯誤優先順序，且不修改 scoring、搜尋參數、材料比例、候選數、Jack adjacency 或 persistence schema。

## 現況與目標

| 項目 | 現況 | 本 change 後 |
| --- | --- | --- |
| Shim 數量 | 自動生成通常只會產生最多一塊 Shim，但任意 ordered pieces 沒有完整契約 | 每個 layout 只能有零塊或一塊非零 Shim；超過一塊為可辨識的 invalid |
| Shim placement | 自動 Solver 的生成路徑與人工編輯驗證不完全一致 | 自動求解與人工編輯使用相同 validator |
| RC terminal 例外 | 程式已有部分 terminal RC 行為，但文件與 boundary 語意不完整 | 只豁免 RC terminal Shim 與第一段相鄰 Steel 的交界，且只豁免對應端的 `1600 mm` end zone |
| Waler 類型缺失 | 既有正規化實際上落為 Steel，但未形成完整 observable contract | 缺失、空白、未知值在相關驗證中一律視為 Steel |
| 錯誤 reason | 驗證來源及排列可能使診斷順序不清楚 | Jack 數量、Shim 數量及後續 issues 依固定優先順序產生 |
| 人工錯誤排列 | 可解析的工程錯誤可保存成 invalid | 沿用既有 invalid 保存語意，不改 transaction／commit 流程 |

`terminal Shim` 指 ordered piece sequence 最靠近某一端 Waler 的 Shim；`joint` 指兩個相鄰 pieces 的交界 station。

## 目標流程

```text
SupportConfig + normalized ordered pieces
  -> 正規化兩端 Waler 類型（缺失／空白／未知 => Steel）
  -> Jack 數量 gate
  -> Shim 數量 gate（0 或 1 塊非零 Shim）
  -> Shim placement 驗證
  -> piece boundary joint 驗證
       只有 RC terminal Shim <-> 第一段 Steel
       可忽略同端 1600 mm end zone
       Column／Beam 禁區永不忽略
  -> 產生固定順序的 valid／invalid reason
  -> 自動 Solver 與人工 staged recalculation 共用結果
```

## Why

RC terminal Shim 的 `1600 mm` 例外目前分散在程式行為與文件敘述中，人工 Support 編輯又沒有完整套用相同的 Shim placement 檢查。這會讓相同 ordered layout 因入口不同得到不同合法性結論，也讓錯誤原因不穩定。本 change 將數量、位置、Waler 類型正規化、端部例外與 issue ordering 收斂成單一契約，同時保留既有人工 invalid 保存流程。

## What Changes

- 將零塊或一塊非零 Shim 定義為唯一合法數量；`shim = 0` 表示沒有 Shim piece。
- 將 Steel／Steel、RC／Steel、Steel／RC、RC／RC 的 Shim placement 規則集中在共用 validator。
- 將缺失、空白或無法辨識的 Waler 類型一律視為 Steel。
- 僅允許 RC 端 terminal Shim 與第一段相鄰 Steel 的 boundary 豁免同端 `1600 mm` end zone；其他 joints 與 Column／Beam 禁區仍照原規則。
- 以固定優先順序組成診斷：Jack 數量錯誤時只回報 Jack 數量；Shim 超過一塊時只回報 Shim 數量；其餘 issues 依規定順序產生，且不受 piece 或執行順序影響。
- 人工 Support 編輯共用 Solver validator；可解析但不合法的排列仍保存為 invalid。
- 更新 `docs/DOMAIN.md` 與 `docs/SOLVER.md`，並補齊 focused、regression 與實際圖面 fixture 測試。

## In Scope

- Support ordered pieces 的 Shim count 與 placement hard validation。
- Waler 類型正規化在 Shim placement、RC terminal 例外中的一致行為。
- RC terminal Shim boundary 的唯一 `1600 mm` 例外及 Column／Beam 不豁免規則。
- Jack／Shim 數量 gate 與 deterministic issue ordering。
- 自動 Solver、人工 Support 編輯及其 invalid reason 的一致性。
- 舊結果載入與下次重算的相容性說明。
- Domain／Solver 文件與相關測試。

## Out of Scope

- 修改 Support scoring、penalty、材料比例、候選數、Beam Width、Random Seed、搜尋階段或其他搜尋參數。
- 修改 Jack adjacency、Jack 長度規則、Steel 長度、gap、Column／Beam 距離數值。
- 修改 SharedLayoutGroup 的 identity 契約、分組 transaction 或自動拆組行為。
- 修改 DXF 雙路支撐辨識。雙路仍要求兩支 Strut 對應相同的精確 Waler ID 配對，而非僅同一條 Waler chain；方向相反時沿用既有 canonical endpoint mapping。
- 修改 Waler Solver、Support adjacency、Project persistence schema 或 UI 流程。
- 載入舊結果時自動重新驗證或遷移既有資料。

## 既有雙路支撐契約（不變）

Characterization 已確認：

- DXF 幾何候選通過後，會取得兩端實際 Waler source identity；只有相同的精確 Waler ID pair 才是 eligible，identity 缺失／歧義或不同 pair 會保留既有診斷且不建立合法雙路群組。
- Strut 方向相反時，匯入流程會依共同 Waler ID pair 將 member 方向 canonicalize，因此比較的是共同排列的同一端，不直接依原始 start／end 欄位判斷。
- Main 可手動設定 SharedLayoutGroup；Support Solver 啟動前的 Project validation 已要求同組兩支 Strut 有相同 ordered `(FromWaler, ToWaler)` ID pair。
- 因相同 ID 解析到同一 Waler material，合法群組不會再出現「同端 Waler 類型不同」的獨立狀態。本 change 不新增第二套 type-only 雙路判斷。

## Capabilities

### New Capabilities

- `support-shim-joint-validation`：定義 Support Shim 數量、placement、Waler 類型正規化、RC terminal joint 例外、deterministic issue ordering，以及自動／人工驗證的一致行為。

### Modified Capabilities

無。`dxf-double-support-recognition` 的精確 Waler identity 配對及方向 canonicalization 均維持不變；`support-editor-result-mutation` 的 staged invalid／commit semantics 也不變。

## Impact

- **Algorithms**：`bracing_optimizer/algorithms/support.py` 的 Support piece validation、Waler type normalization、joint forbidden-zone evaluation 與 reason 組成。
- **Application**：`bracing_optimizer/application/plan_editing.py` 改用共用 verdict；不改 staged／commit boundary。
- **Tests**：補充 Shim count／placement、未知類型視為 Steel、RC exception、issue ordering、人工 invalid 保存，以及既有雙路 identity 契約的回歸測試；另以既有實際圖面 fixture 執行完整 Support 求解，確認合法案例的候選與最終結果不變。
- **Long-term truth**：必須更新 `docs/DOMAIN.md`；必須更新 `docs/SOLVER.md` 11.1，並將 Known Solver Gaps 的 Gap 4 標記為已解決。
- **Compatibility**：不變更資料 schema。載入已保存舊結果時不自動重新驗證；下次重算時才套用新規則。
- **Cache**：Phase 1 candidate cache 僅存在單次執行期間、不寫入 Project，因此不提升 policy version。

## 實作時可決定事項

- Invalid reason 的內部 issue code 與中文文字可依現有風格決定，但必須保留可辨識的 Shim count／placement 類別、固定優先順序，以及本提案定義的 observable behavior。
