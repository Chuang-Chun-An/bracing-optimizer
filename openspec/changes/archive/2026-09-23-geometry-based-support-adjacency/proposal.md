# Proposal

## Why

目前 DXF Import 不會依辨識出的 Strut 幾何建立有工程意義的初始 `Zoning`，而 Support Phase 2、人工重算與診斷又以 Project／optimization input order 判定相鄰 Strut，與已確認的現場幾何語意不一致。這會使初始分組需要人工重建，且 row reorder 可能改變 Jack spacing 合法性、region penalty、最小相鄰距離與 diagnostics，因此需建立從 DXF 初始分組到 Solver 驗證與使用的一致 geometry-based adjacency contract。

## What Changes

- DXF Import 在完成 Strut recognition 後，依實際 geometry、連續 Waler chain 與橫向空間順序自動建立初始 `Zoning`；一般 DXF 構件辨識行為不變。
- DXF 初始分組只提供 suggestion：`5° / 5 mm` 是同組資格而非充分條件；同組成員必須在幾何順序上連續，不得跳過中間支撐。相鄰成員之間不另設固定最大距離。
- Main 中的 `Zoning` 保持為使用者可自由修改及保存的 Project 資料；編輯與儲存不因幾何容差而被拒絕，且系統不會自動改回 DXF 初始分組。
- 在進入 Support Phase 2 前驗證同一 Zoning 的無方向性 axis 角度、Strut 長度與橫向 projection。
- 由全組 geometry 建立 deterministic common direction、row direction、unit projection 與 consecutive adjacency pairs，不使用 row／UI／input order fallback。
- 將普通 Strut 的 axis midpoint 作為代表位置，並將 `SharedLayoutGroup` 的兩支 lane 合為一個 adjacency unit。
- 讓 Phase 2、Jack spacing、Jack region consistency、manual editing、neighbor checks、`min_jack_distance` 與 diagnostics 共用同一 adjacency semantics。
- 保留 SharedLayoutGroup 的 shared Jack station invariant，並以 shared `jack_center` 與 merged `pile_centers` 套用既有 `get_jack_region_id()`。
- Solver 以 Main 當下的 `Zoning` 作為驗證資料；Geometry validation 失敗時不進入 Phase 2、不 commit 新結果，並保留前一個 committed result。

## In Scope

- DXF Import 對已辨識 Struts 的初始 `Zoning` 自動判定；同組資格使用 angle difference `<= 5°` 與 length difference `<= 5 mm`，並以連續 Waler chain 或拓撲不明時的橫向空間相鄰關係建立 initial support row。
- Initial Zoning membership 必須是橫向幾何順序中的連續區段；不得跳過中間 Strut，同時不因兩個連續候選的絕對距離較大而自行拆組。
- Main 中 `Zoning` 的人工修改、保存與其作為後續 Solver 驗證輸入的語意。
- Zoning geometry validation：angle difference `<= 5°`、length difference `<= 5 mm`、projection difference `<= 1 mm` 為 ambiguous／invalid。
- Geometry-based optimization-unit ordering 與 adjacency pairs。
- `SharedLayoutGroup` unit identity、代表位置、shared Jack station 與 group-level Jack region。
- 幾何相鄰 units 之間的 Jack 縱向 station offset `>= 500 mm`。
- Initial solve、search stages、manual recalculation、neighbor checks、score summary、`min_jack_distance` 與 diagnostics 的一致性。
- Validation feedback 與 failure-before-commit result preservation。

## Out of Scope

- Support Phase 1 candidate generation、candidate retention、cache policy 與個別 `SupportPlan` legality。
- Jack／Shim／Steel 排列、`TargetJackRegion`、材料比例、庫存、Beam Width、search escalation 或 score weight。
- Jack region formula、region boundary semantics、Phase 1 region behavior 或 region penalty weight。
- Canonical Jack station transformation、2D Jack distance、`representative_length` 或 length-based Jack region。
- Waler Solver、DXF member／line recognition、CandidatePoint、Project row UI ordering 與 persistence schema；但已辨識 Struts 的初始 `Zoning` 判定屬於本次範圍。
- Main 中自動修改／拆分使用者指定的 Zoning，或重新指派 `FromWaler`／`ToWaler`。

## Affected Capability

- **New capability — `support-adjacency`**：定義 DXF 初始 Zoning 判定、Main 人工分組 ownership、同一 Zoning 的求解前幾何有效性、adjacency unit、deterministic ordering、SharedLayoutGroup 邊界語意，以及所有 Support 全域流程共用的相鄰契約。
- 目前 `openspec/specs/` 沒有既有 capability，因此本 change 不修改現有 OpenSpec capability。

## Expected long-term documentation impact

- 本次遷移不修改 `ARCHITECTURE.md`、`DOMAIN.md`、`SOLVER.md` 或 `WORKFLOW.md`。
- 實作完成並驗證後，應將 `DOMAIN.md` 與 `SOLVER.md` 的 Adjacent Strut known gap 更新為已實作行為，並檢查 `WORKFLOW.md` 的 validation／result lifecycle 敘述是否需要同步。
- 只有最終責任邊界與現有架構文件不同時，才需更新 `ARCHITECTURE.md`。
