# Proposal：改善 DXF 單筆來源排除效能

## 閱讀導航

- **P0／現在必讀**：本文件「快速摘要」、「現況與目標」、「主要流程」與「不變事項」；先確認本案維持單筆操作，不新增多選或批次排除。
- **P0／現在必讀**：本 change 的 delta spec `dxf-source-exclusion-workflow`；定義單筆排除的完整重建、人工修補 replay 等價性、原子提交與畫面一致性。
- **P0／現在必讀**：`openspec/specs/dxf-corner-brace-repair-tool/spec.md` 的「修補決策必須可追溯且安全重播」；效能改善不得降低 repair provenance 或重新檢核。
- **P1／實作前閱讀**：本 change `design.md` 的方案 D（單次 `plan_corner_brace_repair()` 內局部驗證與預建索引）、transaction、render invalidation 與 lazy debug Decisions；另確認已封存的 `resolve-provisional-waler-manually` 與 active change `separate-waler-positioning-from-formal-adoption` 是否碰觸同一 replay 路徑。
- **P2／需要時再讀**：修改 hit index 時再讀 `dxf-review-preview-error-selection`；驗證 paired Joist 時再讀 `bim-joist-recognition` 的 source-atomic requirement。可先跳過 Solver、Project schema、材料規格、DXF recognition 幾何門檻與成果匯出 specs，本案不改那些行為。

## 快速摘要

- 目前 Y05 單次排除一個來源約需 19 秒；主要時間不是 UI 選取，而是 11 筆 CornerBrace repair 逐筆安全 replay 時重複建立全量問題與 ReviewItems 投影。
- 維持現在一次選一個構件／來源的操作，不新增多選清單、批次 identity、合併 impact 或批次 persistence。
- 每次排除仍執行一次完整 canonical recognition；人工修補仍逐筆、依原順序重新 planning 與 apply。效能改善只發生在單次 `plan_corner_brace_repair()` 內：以候選局部驗證取代全場重算，並預建該次呼叫可安全重用的 lookup／幾何索引，呼叫結束即丟棄。
- 提交維持 revision-bound 且全有或全無；畫面只刷新必要 layer，隱藏的開發者 debug payload 延後到實際查看時產生。
- 無法證明局部 replay 或局部畫面刷新等價時，必須回退現有完整重建，不以速度交換工程正確性。

## 現況與目標

本案中的「replay projection」是人工決策重播期間，用來尋找 repair target、problem 與 ReviewItem 的暫存衍生資料。它只能由目前 staged result 建立，不是新的工程 truth，也不會寫入 Project。

| 項目 | Before（現況） | After（目標） |
| --- | --- | --- |
| 使用者操作 | 一次選一個構件並預覽／確認來源排除 | 完全維持單筆操作，不新增多選 UI |
| Canonical 重建 | 單筆排除執行一次完整 recognition | 仍執行一次完整 recognition，不沿用 stale result |
| CornerBrace replay | 每筆 repair 內每個候選都重建全場 CornerBrace connections 與 duplicate diagnostics | 每筆 repair 仍完整 planning，但在單次呼叫內只驗證暫時候選自身的 connection，並逐一和既有角撐比較 duplicate；預建 lookup／template／frame／方向與 anchor 索引，且不跨 repair 共用 |
| 提交 | revision guard 後仍有部分衍生資料在 live state 上重建 | 所有可能失敗的衍生資料先在 plan 完成，再原子採用一次 |
| 畫面刷新 | 重建整張 source scene，並同步產生大型 debug JSON | 更新必要 layer、保留 viewport；debug 內容按需產生 |

## 主要流程

```text
使用者選取一個目前可排除的 ReviewItem
  -> 沿用既有 eligibility、source identity 與 shared-handle 檢查
  -> 以目前 exclusions 加上該來源建立一份 staged plan
  -> 執行一次 full recognition
  -> 依既有順序與相依性處理全部 manual decisions
       -> 每次 plan 內以等價的候選局部驗證取代全場 validation
       -> 每次 plan 內預建 Waler／Strut lookup、template、relationship frame、方向／anchor 索引
       -> 呼叫結束即丟棄所有暫存資料，不跨 repair 沿用
  -> 完成 validation、problem／ReviewItem 與 candidate projection
  -> 顯示既有單筆 impact，使用者確認
  -> revision guard 後原子提交
  -> 局部刷新畫面；hidden debug 只標為 dirty
```

取消、來源不合法、replay／staging 失敗、revision stale 或 commit 失敗時，現有 Review result、exclusions、manual decisions、confirmations、viewport、Project 與 Solver state全部維持提交前狀態。

## 不變事項

- 一次只能由使用者明確選取並確認一個來源排除；不提供多選、批次排除或自動排除全部紅色警告。
- 每份 exclusion plan 仍須由排除後的 active sources 完整重建 recognition、connections、associations、diagnostics、ReviewItems 與 completion truth。
- CornerBrace repairs、Waler decisions、材料與幾何人工輸入仍逐筆重新驗證；`preserved`、`needs_review`、`disabled` 語意與 repair 相依順序不變。
- 不沿用排除前或前一筆 repair 的 planning outcome、validation結果或 cache；每筆 repair 仍以當下 staged result 重新執行 `plan_corner_brace_repair()`。
- paired BIM Joist 的 shared root 仍是 source-atomic 排除單位；既有 restore、Pause／Resume、compatible recovery 與 changed-content classification 不變。
- 原始 DXF、source fingerprint、Review persistence、Project schema、Project rows、Solver input／scoring、recognition geometry tolerance 與工程規則不變。

## Why

Y05 的來源幾何與人工修補量較大，早期量測曾有單筆來源排除約 19 秒、其中 manual repair replay 約 14.2 秒；目前 fixture 已演進，詳細重測與差異記錄於 `design.md` Context。新增批次 UI 不能改善單筆等待，因此本案直接處理安全 replay 內可避免的重複工作。

## What Changes

- 維持現有單一 `ReviewItem` 來源排除入口與確認流程，不新增多選或 batch state。
- CornerBrace replay 採方案 D：只加速單次 `plan_corner_brace_repair()`。候選 validation 使用相同工程規則，只計算暫時角撐自身的 connection，並以相同 duplicate predicate逐一比較既有角撐；同次呼叫另預建 Waler／Strut lookup、template、relationship frame與方向／anchor索引。
- 所有方案 D 暫存資料在單次 plan 結束後丟棄，不跨 repair 共用，不建立 dependency footprint或 repair input fingerprint，也不沿用舊 repair outcome。
- 延後 validation、找到第一個通過候選即停止的做法暫不採用；現有互動修補工具會列出 `plan.candidates` 的全部合法候選，提前停止會改變對外輸出。
- 保留 repair 的 deterministic ordering、secondary-reference dependency pass、provenance、candidate validation 與 `preserved`／`needs_review`／`disabled` 結果；優化前後必須與 canonical sequential replay 等價。
- 將 confirmations、candidate store、problem／ReviewItems 等可能失敗的 commit projection 在 plan 階段完成，成功 commit 只採用同一份 revision-bound plan並增加一次 revision。
- Review refresh 依 changed layers 更新正式構件、問題、來源樣式、selection／hit index，且在 source geometry 未變時保留 viewport；不安全時使用 full-scene fallback。
- 開發者 debug payload 改為在面板實際顯示或刷新時，依目前 committed revision 產生；隱藏狀態不再阻擋一般排除完成。
- 以 deterministic work-count、optimized-vs-canonical replay equivalence 與 Y05／Y29 regression驗證，不以不穩定 wall-clock 秒數作 correctness assertion。

## In Scope

- 現有單筆來源排除的 staging、manual replay、impact、revision-bound commit 與 restore 相容性。
- `plan_corner_brace_repair()` 單次呼叫內重複的候選 connection／duplicate validation、Waler／Strut lookup、template、relationship frame與方向／anchor計算。
- Waler、材料、工程線與 CornerBrace manual decisions 共用同一 replay report；不得建立 CornerBrace 專用的第二套 outcome truth。
- source geometry 未改變時的局部 render invalidation、viewport 保留與 source hit index 正確失效／重建。
- hidden developer debug payload 的 lazy generation 與 revision-aware cache invalidation。
- Y05 多 repair、paired Joist source-atomic、Y29 legacy source，以及取消／stale／失敗 regression。

## Out of Scope

- 多選構件、多來源批次排除、批次 impact summary、批次 restore 或任何 batch UI／persistence state。
- 自動排除全部 error／critical、紅色來源或替使用者選擇排除 winner。
- 改變 CornerBrace repair eligibility、candidate ranking、reference priority、dependency semantics、diagnostic severity 或完成條件。
- 省略 full recognition、manual decision validation、association rebuild 或 confirmation validation。
- 快取 `INSERT.virtual_entities()`／`_GeometryGroup` extraction；這可作為後續獨立效能 change。
- 將 staging 移至 background worker、提供進度取消或制定固定秒數 SLA。
- source relink、changed-content recovery、Project apply、persistence schema migration、Solver 或工程 Domain rule。
- CornerBrace repair reference 改用穩定 source identity／subject key，而不依賴依順序產生的顯示 member ID；S14／D1A反例由 `stabilize-corner-brace-repair-reference-identity` 另案處理。

## Capabilities

### New Capabilities

- `dxf-source-exclusion-workflow`：定義單筆來源排除必須維持完整 canonical rebuild、安全且結果等價的人工決策 replay、revision-bound 原子提交，以及不改變工程 truth 的局部刷新與 lazy debug 行為。

### Modified Capabilities

- 無。既有 `dxf-corner-brace-repair-tool`、`bim-joist-recognition`、`dxf-review-preview-error-selection` 與 `dxf-review-engineering-data-presentation` 的既定 Requirements 作為相容性邊界，不修改其工程語意。

## Impact

- **Manual replay**：`dxf_import/source_exclusion.py` 仍逐筆呼叫既有 plan／apply contract；效能修改限於 `dxf_import/corner_brace_repair.py` 單次 planning內部，不改 eligibility、ranking或輸出。
- **Workflow**：`dxf_import/review_workflow.py` 的 `SourceExclusionPlan`／commit 預建 confirmation、candidate 與 UI-neutral mutation projection；`DXFReviewWorkflow` 仍是唯一正式 state owner。
- **Presentation**：`dxf_import/dialog.py` 保留單筆來源排除 UI，將 result refresh 拆成必要 dirty layers並延遲 debug serialization。
- **Preview**：scene／hit index 依 committed revision與 changed layers 更新，不建立第二份 source visibility truth。
- **Tests**：`tests/test_dxf_source_exclusion.py`、`tests/test_dxf_corner_brace_repair.py`、`tests/test_dxf_review_workflow.py`、Review layout／render tests，以及 Y05／Y29 fixture regressions。
- **Architecture／Domain／Solver**：沿用既有 architecture，不修改 Domain 或 Solver。實作完成後預期只更新 `docs/WORKFLOW.md` 的來源排除 transaction／replay lifecycle。

## 相關 change 與實作順序

- `resolve-provisional-waler-manually` 已於 2026-10-06 封存，其 Waler replay 分支已成為目前 baseline，歷史上確實修改 `replay_manual_overrides()` 同一路徑。
- Active change `separate-waler-positioning-from-formal-adoption` 目前為 0/19 tasks，規劃集中於 `dxf_import/dialog.py` 的 UI／Preset 行為，明確不修改 `manual_overrides` 或 `waler_engineering_line_formalized`，目前不會修改 `source_exclusion.py` 的 replay loop。
- `expand-global-waler-candidate-pool` 與 `deduplicate-global-waler-local-solves` 屬 Solver change，與本案沒有行為依賴。
- `stabilize-corner-brace-repair-reference-identity` 專責修正 S14 所揭露的顯示 member ID漂移問題；本 change 不修改 reference identity或 recovery語意。

## 已確認決策與重新評估條件

- 已確認：維持單筆來源排除，不新增多選或 batch state；原提案中的批次 identity、batch planner、合併 impact 與相關 UI 全部移除。
- 已確認：第一階段處理 replay 重複投影、atomic commit、局部刷新與 lazy debug；DXF geometry extraction cache 與 background worker 不納入。
- 已確認：不以固定 wall-clock 秒數作 spec boundary；以 full-projection rebuild 次數、結果等價與 regression 作正式驗證，再用 benchmark 記錄實際改善。
- 已確認：A、B、C皆不採用；採方案 D，且 cache生命週期只限單次 `plan_corner_brace_repair()`，不跨 repair 共享。
- 已確認：候選局部 connection／duplicate validation必須以逐候選 differential test證明與目前全場 validation完全等價；若無法證明，該候選仍走既有全場 validation，不得弱化 repair validation。
- 已確認：延後 validation、第一個合法候選即停止暫不採用，因現有互動工具會列出全部合法候選。
- 若局部重繪無法維持 visibility／selection／hit-test 等價，必須使用 full-scene fallback並保留 viewport，不得犧牲點選正確性換取速度。
