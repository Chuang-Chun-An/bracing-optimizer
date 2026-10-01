# Design

## 閱讀導航

- **現在必讀（P0）**：Context 的 characterization、Decision 1～5、Backward Compatibility。
- **實作前閱讀（P1）**：`specs/support-shim-joint-validation/spec.md` 全部 Requirements 與 `tasks.md`。
- **需要時再讀（P2）**：`docs/SOLVER.md` 的 Support evaluation／SupportPlanEditing、`docs/DOMAIN.md` 的 Support hard rules，以及既有 DXF double-support／Project validation tests。DXF 辨識與 SharedLayoutGroup identity 不在本 change 中改寫。

## Summary

本 change 在 Support calculation boundary 建立共用、純函式式的 Shim legality verdict。它接收 normalized ordered pieces、`SupportConfig` 與兩端 Waler 類型，先正規化類型，再依固定 gate 檢查 Jack count、Shim count、Shim placement 與 boundary joints。自動 Solver 與人工編輯共同消費此 verdict；Presentation 不複製規則。

```text
raw endpoint types + normalized pieces + SupportConfig
  -> normalize Waler type (recognized RC only; otherwise Steel)
  -> complete evaluation / legacy scoring inputs (always runs)
       -> count_forbidden_piece_joints and existing penalties
  -> reason issue collection
       -> Jack count gate
       -> Shim count gate
       -> Shim placement / gap / forbidden joint / Steel length
       -> stable ordered reason
  -> evaluate_single_support / SupportPlanEditing
```

## Context and Characterization

實作前 characterization 已確認下列現況：

1. `generate_waler_rule_layouts` 目前產生最多一塊 Shim，`shim = 0` 時不產生 Shim piece；但 `evaluate_single_support` 對任意 ordered pieces 尚未完整檢查 Shim count／placement。
2. `count_forbidden_piece_joints` 已有 terminal RC 的部分例外，但主要依 boundary index，未完整要求「terminal Shim 緊接第一段 Steel」；`SupportPlanEditing.find_forbidden_zone_hit` 也可能與 Solver verdict 漂移。
3. `SupportPlanEditing.stage_edit` 已呼叫 `evaluate_single_support`，工程上 invalid 的可解析排列會成為 staged invalid result；basic normalization 則拒絕非正長 piece。
4. `normalize_waler_type` 目前只將可辨識的 `RC`／`RC WALER` 正規化為 RC，其餘值（包含缺失、空白、未知）都落為 Steel；Solver input 在找不到 Waler type 時也預設 Steel。本 change 將此現況正式化，不保留第二套 fallback。
5. DXF 雙路辨識在幾何條件後比較 terminal Waler source identity 的精確 unordered pair；不同 pair 為 incompatible，缺失／歧義為 pending。匯入 Project rows 時，方向相反的 member 會依共同 `(FromWaler, ToWaler)` pair canonicalize。
6. Main 可以手動設定 SharedLayoutGroup。Support Solver 啟動前的 `ProjectDataValidator` 已要求每組正好兩支、同 Zoning、同 Strut material spec，且有相同 ordered `(FromWaler, ToWaler)` ID pair。因此合法群組的同端 type 由相同 ID 自然保證，不需要新增 type-only validator。
7. Phase 1 `support_candidate_cache` 是執行期間記憶體資料，建立新專案、載入專案或輸入改變時會清除，且不寫入 Project persistence。

## Goals / Non-Goals

**Goals**

- 讓任意 ordered pieces 與自動 candidates 使用同一 Shim legality contract。
- 將缺失／空白／未知 Waler type 視為 Steel 的行為正式化。
- 以 typed boundary 明確限制 RC terminal `1600 mm` 唯一例外。
- 以固定 gate 與排序產生可重現的 invalid reason。
- 保留人工可解析 invalid result 的既有保存流程。

**Non-Goals**

- 不改 DXF double-support recognition、精確 Waler identity pair、direction canonicalization 或 SharedLayoutGroup validation。
- 不新增「同 Waler chain」或「type-only」的雙路配對規則。
- 不改 scoring、候選數、搜尋流程、材料比例、Jack adjacency 或 persistence schema。
- 不把整個 Support hard-rule ownership 搬移到新的 Domain service。
- 不修改人工編輯的 transaction／commit contract。

## Decision Matrix

| Decision | 對應 Requirements | 對應 Tasks |
| --- | --- | --- |
| 1. 共用 normalization 與 Shim validator | Shim count、placement、missing type | 1.1、2.1、2.2 |
| 2. Typed boundary walk | RC terminal 唯一例外 | 1.2、2.3、3.2 |
| 3. Deterministic reason gates, scoring 獨立 | Issue priority、invalid score stability | 1.3、1.4、2.1、3.1 |
| 4. 保留 staged invalid semantics | Automatic/manual、saveable invalid、legacy results | 3.1、3.3、4.1 |
| 5. 不改 optimization identity | Optimization unchanged | 2.4、3.4、5.1 |

## Decisions

### Decision 1: 在 Support calculation boundary 共用 Waler normalization 與 Shim validator

新增或抽取純函式式 validator，輸入為 normalized ordered pieces、`SupportConfig` 及 raw From／To Waler types，輸出穩定的 structured issues。它 SHALL：

- 共用既有 `normalize_waler_type` 語意：只有可辨識 RC 為 RC，其餘皆為 Steel。
- 計算非零 Shim 數量；零長 piece 仍由既有 basic normalization 擋下。
- 在數量 gate 通過後，檢查 Steel／Steel、RC／Steel、Steel／RC、RC／RC placement。
- 被 `evaluate_single_support` 與 `SupportPlanEditing` 消費，而不是在 Presentation 重寫規則。

validator 保留在 `bracing_optimizer.algorithms.support` 的 brownfield boundary，避免此 focused change 同時進行大規模 ownership migration。

拒絕方案：

- **只在 Editor 驗證**：自動 candidate 與人工 ordered pieces 仍可能產生兩套 truth。
- **只靠 candidate generator 保證**：無法涵蓋手動或歷史 ordered pieces。
- **另建 type-only 雙路 validator**：會與 exact Waler ID contract 重複，且可能製造兩套不一致規則。

### Decision 2: 以 typed piece boundary 判斷 RC terminal 唯一例外

joint evaluation SHALL 走訪 `pieces[index]` 與 `pieces[index + 1]`，同時保留 boundary station 與左右 piece kind。只有以下 boundary 可忽略 matching end zone：

- From RC：`index == 0` 且 boundary 為 `shim -> steel`。
- To RC：`index == len(pieces) - 2` 且 boundary 為 `steel -> shim`。

忽略範圍只包含該端 `1600 mm` end zone。Column、Beam 與另一端 end zone 都不移除。既有 inclusive comparison 保持不變，因此非豁免 joint 恰在 `1600 mm` 仍為 invalid。

`find_forbidden_zone_hit` 不再用無 piece context 的 raw station 自行推論；它應消費相同的 boundary-aware verdict 或共用 helper，讓 UI 診斷與 plan validity 一致。

### Decision 3: Reason 使用 precedence gates，但 scoring pipeline 不得被 gate

reason issue pipeline SHALL 依下列順序組成：

1. Jack count。
2. Shim count。
3. Shim placement。
4. gap。
5. forbidden joint。
6. Steel length。

Jack count 不合法時，reason 只回傳 Jack count issue。Jack count 合法但 Shim 超過一塊時，reason 只回傳 Shim count issue。兩個 gate 都通過後，其餘可同時存在的 issues 依 3～6 順序輸出；同一類別若有多筆，使用穩定 station／piece key 排序，不依 set、dict 或執行順序。

這兩個 gate **只作用於 reason projection**，不得成為完整 evaluation 或 scoring pipeline 的 early return。無論 reason 最後顯示幾個 issues，修改前會執行的扣分資料收集與計算都 SHALL 繼續執行，包含 `count_forbidden_piece_joints`、既有 invalid penalty 與 score breakdown。實作可先完成完整 evaluation，再把結果投影成符合 gate 的 reason；也可使用兩條明確分離的 pipeline，但兩者不得共享會短路 scoring 的 control flow。

實作前先以代表性不合法 candidates 固定修改前的精確 score、penalty、score breakdown 與相對排序。修改後必須逐值完全相同，不使用浮點容差。若現有架構無法同時做到 reason 簡化與扣分不變，apply SHALL 停止並回報，不得自行選擇犧牲其中一項。

內部 issue code 與中文訊息可沿用現有風格，但 structured category 與排序須可測試，最後再組成 `SupportPlan.reason`。

### Decision 4: 保留人工 staged invalid 與 legacy result 語意

`SupportPlanEditing.stage_edit` 流程維持 normalize、basic validation、deep-copy stage、`evaluate_single_support`、global recalculation、adopt staged result。Shim count／placement／joint failure 是 engineering invalid，不是 parse failure，因此 SHALL 保存 invalid result、reason、calculated time、metadata 與 dirty state。

零長／負長 piece 或不可解析輸入仍在 basic normalization 階段拒絕，committed result 不變。

Project 載入既有 Support result 時不主動執行新 validator，也不改寫 persisted valid／invalid。使用者下一次執行完整重算或 staged recalculation 時，才套用新規則。

### Decision 5: 不改 optimization identity，runtime cache 不升 policy version

不得修改合法或不合法 candidate 的 scoring constants、penalty inputs、score breakdown、candidate limits、Beam Width、Random Seed、search stages、material ratio、Jack adjacency、relative ordering 或 selection behavior。新規則只影響 legality verdict 與 reason；reason gate 不得略過原有 scoring work。

Phase 1 candidate cache 只存在該次程式執行的記憶體，不保存到 Project；它也會在專案／輸入變動時清除。因此本 change 不需要提升 persisted policy version，也不新增 migration 欄位。實際圖面 fixture 的完整求解回歸負責證明合法案例的 candidates 與 final result 未改變。

## Architecture Alignment

| Layer | 責任 | Dependency direction |
| --- | --- | --- |
| Algorithms | Waler type normalization、Shim legality、typed boundary joint evaluation、ordered issues | 不依賴 Application／Presentation |
| Application | normalize manual input、staging、global recalculation、消費 Algorithms verdict | Application → Algorithms |
| Presentation | 顯示 `SupportPlan.valid` 與 reason | Presentation → Application |
| Domain docs | 記錄穩定工程契約 | 不新增 runtime dependency |

Single source of truth 是 Algorithms 的共用 validator 與 boundary helper。Candidate generation 可繼續產生原有合法 layouts，但不得被當成唯一 legality 保證。

## Backward Compatibility / Persistence Impact

- `SupportConfig`、`SupportPlan`、`GlobalSolution` 與 Project JSON schema 不變，無 migration。
- 已保存結果在 load 時不重新驗證；下次完整重算或 staged recalculation 才套用新規則。
- 既有人工 invalid mutation semantics 不變。
- 既有 exact Waler ID double-support contract、manual SharedLayoutGroup 欄位與 pre-solve validation 不變。
- Phase 1 cache 不持久化，因此無 policy version change。

## Risks / Trade-offs

- **Reason 相容性**：固定排序可能改變同一 invalid layout 的文字排列；以 structured category 測試 observable priority，文字維持既有風格。
- **診斷漂移**：若 UI helper 自行判斷 raw joints，可能和 Solver 不同；改為消費共用 boundary-aware result。
- **既有非法資料**：load 時刻意不改寫，只有重算後才可能由舊 valid 變成 invalid；文件必須明確說明。
- **回歸範圍**：legality 改動可能意外影響 candidate selection；以 focused tests 加實際圖面完整求解固定範圍，不藉機調參。

## Migration and Verification Plan

1. 先記錄代表性不合法 candidates 的修改前精確 score／penalty／breakdown／排序，再以 tests 鎖定 Shim count／placement、missing type、typed boundary、issue priority 與 manual invalid semantics。
2. 實作共用 validator 與 Waler normalization contract，接入 `evaluate_single_support`。
3. 讓 `SupportPlanEditing` 與 forbidden-zone diagnostics 消費相同 verdict。
4. 執行 Support focused tests、manual workflow、adjacency regression、雙路 identity regression 與 architecture boundary tests。
5. 以既有實際圖面 fixture 執行完整 Support 求解，比對合法案例 candidates 與 final result。
6. 更新 `docs/DOMAIN.md` 與 `docs/SOLVER.md` 11.1／Gap 4，最後執行 strict OpenSpec validation。

## Open Questions

無契約層級未決事項。內部 issue code 與中文文字可在實作時依現有風格命名，但不得改變 category、priority 或可辨識性。
