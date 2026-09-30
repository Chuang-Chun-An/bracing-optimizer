# Design

## 閱讀導航

- **P0 現在必讀**：Decision 1「一份 canonical terminal relation 同時承載方向與 identity state」、Decision 2「contact-face 與 connection 使用不同 authority filter」、Decision 3「多解候選集合沿用既有資格」；這三項決定核心資料流與安全邊界。
- **P1 實作前閱讀**：Decision 4「diagnostics 與 Preview 投影」、Decision 5「rebuild 與 state ownership」；修改 `recognition.py`、Review workflow 或 overlap join 前必讀。
- **P2 條件式閱讀**：Backward Compatibility、Risks／Trade-offs 與 Migration Plan；處理 persistence、回滾或 Y29 fixture 差異時再讀。
- **可先跳過**：Solver、材料規則、CornerBrace、其他 BIM／HATCH recognition 細節；本 change 不修改其演算法或 contract。

## 方案摘要

目前 `build_member_terminal_evidence()` 在 terminal 多解時只產生 issue、不留下候選 relation，因此 `resolve_waler_contact_faces()` 看不到其實仍可靠的 member 來向。本設計不增加新的 proximity 規則，而是在既有 candidate ranking 已判定「合法且互相競爭」時，保存完整 candidate relations，並在同一份 immutable outcome 上套用兩種 authority filter：

```text
recognized member axis + provisional Waler facts
                    |
                    v
       canonical terminal relations
       - candidate Waler identity
       - provisional intersection
       - body direction
       - relation kind
       - identity state: unique | competing
                    |
          +---------+---------+
          |                   |
          v                   v
  contact-face filter   connection filter
  unique-first          unique only
          |                   |
          v                   v
  Waler formal face     member formal connection
  (if side agrees)      (atomic existing rules)
```

**Candidate relation** 是某 member terminal 依既有幾何規則對某 Waler 成立的候選關係。**Side-only evidence** 是 candidate relation 中由 Waler provisional intersection 朝 member 本體的向量，只能回答 Waler 哪一側面向 member。**Identity evidence** 是同一 relation 在該 terminal 唯一時取得的連接權限。三者不是三份獨立 truth，而是同一 canonical relation 的不同語意／authority。

## 決策對照

| Decision | 對應 spec | 對應 tasks |
| --- | --- | --- |
| D1. 以 canonical relation + identity state 避免兩份 truth | `dxf-waler-contact-face-recognition`「接觸面選擇必須先建立 member-to-Waler 關係」 | 1.1～1.3 |
| D2. Contact face 採 unique-first precedence；connection 只接受 unique | `dxf-waler-contact-face-recognition`「Waler 接觸面必須依 unique-first evidence precedence 判定」、`brace-axis-waler-extension`「候選方向證據必須與正式連接 identity 分權」 | 2.1～2.4 |
| D3. 沿用現有 direct／extension candidate qualification | `dxf-waler-contact-face-recognition`「支撐側必須由 member 軸線朝構件本體的方向判定」 | 1.2、3.1～3.3 |
| D4. Identity diagnostics 與 contact-face state 分開投影 | `dxf-waler-overlap-diagnostics`「競爭關係必須升級為 blocking error」 | 3.4、4.1～4.3 |
| D5. Rebuild 從 active sources 重建同一 outcome | 三份 delta specs 的 lifecycle scenarios | 4.4～4.6 |

## Context

動機見 `proposal.md` 的 Why。現行 pure geometry flow 位於 `dxf_import/waler_contact_face.py`：

- `build_member_terminal_evidence()` 先對每個 member terminal 排序 direct candidates；Brace 在沒有 direct candidate 時才使用既有 axis-extension candidates。
- 唯一候選會建立 `MemberTerminalEvidence`；數值等價或落在 `ambiguous_connection_delta_mm` 的多候選只建立 `TerminalTopologyIssue`，候選本身被丟棄。
- `resolve_waler_contact_faces()` 只依 `MemberTerminalEvidence.waler_source_handles` 分組，再以 `body_vector` 對 Waler normal 的正負選外側面；因此 identity ambiguity 會被間接轉成「沒有 side evidence」。
- `build_brace_terminal_verdicts()` 與 downstream apply 依 terminal evidence、formal contact face、有限交點與合法長度原子式建立正式 Brace。

這個 change 必須保留 immutable source recognition、existing candidate tolerance、Waler envelope truth、atomic member commit、Review staged mutation 與 Project transaction boundary。

## Goals / Non-Goals

**Goals:**

- 讓 terminal identity 多解與 Waler contact-side 可分別解析，避免一項 ambiguity 無條件抹除另一項可靠幾何事實。
- 讓 contact-face、Brace verdict、diagnostics、Preview 與 rebuild 消費同一 canonical terminal relation outcome。
- 維持輸入順序不變性、source provenance、fail-safe Project boundary 與既有 direct／extension boundary。

**Non-Goals:**

- 不建立新的全域 voting、nearest-member heuristic 或較寬 proximity search。
- 不讓 contact-face outcome 參與 identity ranking，也不新增人工 identity selection UI。
- 不改 Waler envelope／overlap qualification、Brace endpoint calculation、Project schema 或 Solver。

## Decisions

### Decision 1：以單一 canonical terminal relation 保存 candidate 與 authority

將現有只代表「已選定」的 terminal evidence 擴充／替換為 immutable canonical relation。每筆 relation 至少保留：

- member role 與 exact source identity；
- `terminal_name`；
- candidate Waler exact source identity；
- provisional intersection 與 member body point；
- `relation_kind`（沿用 `direct`、`axis_extension`、`selected_source_identity`）；
- terminal-level `identity_state`，至少能區分 `unique` 與 `competing`。

`TerminalTopologyOutcome` 是這些 relations 與 topology issues 的唯一 owner。若實作為兩個 typed views，兩者 MUST 從同一 canonical tuple filter 產生，不得各自重算 candidate geometry。現有 `MemberTerminalEvidence` 名稱是否保留屬 implementation choice；不能改變上述 single-source contract。

建立規則：

1. 唯一 best candidate：保存一筆 `unique` relation。
2. 數值等價或落在既有 `ambiguous_connection_delta_mm` 的 best + competitors：為 issue 中列出的每個 identity 保存一筆 `competing` relation，同時保留既有 blocking issue。
3. 排名較遠且未進入既有 competing set 的 candidates：不保存 side evidence。
4. 沒有 candidate：維持既有無 relation 行為。

這可避免 side-evidence builder 重新執行第二次幾何搜尋，也確保 issue 中的 competing identities 與可供 contact face 使用的候選完全一致。

**Rejected：另外建立寬鬆的 nearby-member 掃描。** 這會擴大 candidate eligibility，使無關支撐可能決定 Waler 內側，超出已確認 scope。

**Rejected：保留兩份獨立 `side_evidence` 與 `identity_evidence` collection。** 若兩者各自建構或排序，容易在 exclusion／manual replay 後 drift；canonical relation 加 typed filter 更安全。

### Decision 2：Contact-face 採 unique-first precedence，formal connection 仍只接受 unique

`resolve_waler_contact_faces()` 依 Waler identity 收集 `unique` 與 `competing` relations，每筆先通過現有非退化法向檢查，再依方案 A 分層選擇 authoritative evidence set：

1. 若 `reliable_unique` 非空，只檢查 `reliable_unique`：
   - signs 只有一側：選該側最外實體 face，結果為 formal。
   - signs 同時包含兩側：`WALER_CONTACT_FACE_AMBIGUOUS`。
   - `reliable_competing` 不參與選側；其中與 unique 結果相反者只產生 non-blocking、deterministic warning，建議 code 為 `WALER_COMPETING_SIDE_EVIDENCE_IGNORED`。
2. 若 `reliable_unique` 為空，才檢查 `reliable_competing`：
   - signs 只有一側：選該側最外實體 face，結果為 formal。
   - signs 同時包含兩側：`WALER_CONTACT_FACE_AMBIGUOUS`。
   - 沒有 sign：`WALER_CONTACT_FACE_UNRESOLVED`。

Warning 以 Waler 為 deterministic aggregation boundary，至少保存 Waler source identity、決定結果的 unique member source identities，以及方向相反而被忽略的 competing member source identities。相同方向的 competing evidence 不需 warning；warning 不阻擋 Review，也不改變 formal face。這不是加權投票：只要可靠 unique evidence 存在，competing evidence 的數量永遠不能推翻它。

Member connection／Brace verdict 只能消費 `unique` relations。任何 `competing` relation 即使其 Waler 已 formal，也沒有 connection authority。`build_brace_terminal_verdicts()`、candidate-point selection、connection mappings、forbidden points 與 Project conversion 必須共用同一 unique-only predicate，不能各自用「Waler formal」推導 identity。

這裡的 formal Waler contact face 表示「這支 Waler 的支撐側已確定」，不表示任何 ambiguous member 已連接它。Review 因 identity blocker 仍不可完成，因此不會把只有 side truth 的 staged result提交至 Project。

**Rejected：只要 candidate Waler 都選出相同幾何 face 就解除 identity ambiguity。** 幾何 face 相同不等於 source identity 相同，會破壞 provenance、forbidden point 與後續 repair。

**Rejected：把 unique 與 competing evidence 放在同一 sign set。** 這會讓尚未確認歸屬的候選方向推翻已唯一建立的工程關係，並造成既有 formal Waler regression。

**Rejected：以 evidence 數量作多數決。** Evidence count 不是 authority；多個 competing candidates 不能壓過一筆 reliable unique relation。

### Decision 3：Candidate eligibility 與方向幾何完全沿用既有規則

Side-only evidence 不新增 tolerance 或 magic number：

- Direct candidate 仍由現有 terminal-to-provisional-Waler qualification 產生。
- Brace axis-extension 仍只在沒有 direct candidates 時啟用，且沿用 `maximum_brace_axis_extension_mm` 等既有邊界。
- Competing set 仍由數值等價及 `ambiguous_connection_delta_mm` 決定。
- Side sign 仍以 provisional intersection 到 member interior／另一端的 `body_vector` 投影至該 Waler normal；法向分量絕對值 `<= endpoint_tolerance_mm` 視為 degenerate。
- Waler outer-face selection 仍只在該 Waler 自身 qualified envelope 內取支撐側 extreme face。

實作前必須先以 Y29 fixture characterization 確認使用者指出的 W17／W18 情境與既有已記錄的 W17／W20、W18／W19 source identities。若目標 pair 不在現有 competing set，本 change 必須停止回報，不能偷偷放寬 candidate search 來讓測試通過。

**Rejected：使用支撐 midpoint、drawing centroid 或所有 endpoints 直接選側。** 這些方法無法證明與特定 Waler 的 candidate relation，也會讓無關構件影響結果。

### Decision 4：Identity diagnostics 與 contact-face state 分開投影

Topology ambiguity issue 繼續是 connection identity 的 authoritative blocker，並保留 terminal、member sources 與完整 competing Waler identities。Overlap competition join 優先使用這份 direct terminal provenance；不得因兩支 Waler 已 formal 而移除 blocker。

Contact-face diagnostics 只回報每支 Waler 自身方向證據的 outcome。Identity ambiguity 不再自動產生該 Waler 的 `WALER_CONTACT_FACE_UNRESOLVED`；只有 authoritative evidence set 缺少可靠 sign、同層級兩側衝突或 envelope 問題才產生 contact-face issue。當 unique result 與 competing direction 相反時，另投影 `WALER_COMPETING_SIDE_EVIDENCE_IGNORED` warning，但不得降級 Waler 或移除 identity blocker。

Preview／Review 不新增幾何演算法，只投影 recognition outcome：

- formal Waler 使用既有 formal contact-face 樣式；
- ambiguous member 使用既有 unresolved／blocking 樣式與 problem record；
- details 可同時顯示「Waler contact face formal」及「terminal identity ambiguous」。

若目前 presentation 以任一 competition 全域強制 Waler provisional，實作時只移除該耦合；不得在 UI 重新計算 sign 或選 face。

**Rejected：新增一種半正式 Waler geometry。** Contact side 若已由一致可靠 evidence 決定，就是 formal Waler contact face；真正未完成的是 member identity。新增第三種 Waler state 會讓 Project boundary 更難理解。

### Decision 5：所有 lifecycle 從 active sources 重建 canonical outcome

Source exclusion／restore、fresh recognition、Pause／Resume、compatible recovery 與 manual override replay 都沿用既有 orchestration，從目前 active sources 重建：

```text
Waler facts
  -> member terminal candidates + identity states + issues
  -> Waler contact faces
  -> member-level verdicts
  -> Review projection
```

不得序列化 side-only relations至 Project，也不得在 resume 時只重播舊 contact face。Manual override 若已能以 exact source identity 安全重播，仍必須作用於 rebuild 後的 current relation；它不能把 `competing` relation直接升級為 `unique`，除非既有 override contract 本來就正式提供該 identity selection（目前 scope 假設沒有）。

## Architecture Alignment

本 change **沿用既有 Architecture，不修改 layer 或 dependency direction**。

| Layer／模組 | 責任 | 禁止事項 |
| --- | --- | --- |
| `dxf_import/waler_contact_face.py` pure recognition | 建立 canonical relations、side sign、contact resolution 與 Brace verdict | 不依賴 Tkinter、Project 或 Solver；不讀 UI selection 來猜 identity |
| `dxf_import/recognition.py` orchestration | 將同一 outcome 投影為 staged Waler／member geometry與 diagnostics | 不建立第二套 side／identity ranking |
| Review workflow／Presentation | 顯示 formal Waler 與 unresolved member，維持 blocking lifecycle | 不自行重算方向、選 face 或挑 connection winner |
| Project conversion | 只接受既有 completed、formal connection truth | 不接收 side-only relation 或新增 persistence 欄位 |
| Domain／Algorithms | 維持既有 Project entities 與 Solver input | 不接觸 DXF source handles、candidate relation 或 Review state |

Single source of truth 是 recognition rebuild 產生的 canonical terminal relations、contact outcomes 與 member verdicts。Presentation、candidate points、diagnostics 及 Project conversion只能讀取相應權限的 outcome／predicate，不能靠資料存在與否重新推論。

## Backward Compatibility 與 Persistence

- 不改 `ProjectDataModel`、saved project schema 或 Solver DTO，不需要 migration。
- Runtime-only relation type 可以調整，但 DXF source identities、Review problems 與既有 manual replay key 必須保持可追溯。
- 唯一 terminal、沒有 envelope 的單線 Waler、非重疊一般 CAD／BIM／HATCH 結果應維持等價。
- 既有測試中「identity competition 必然使 Waler provisional」的 assertions 是本 change 明確修改的舊 contract；應改驗證 identity 仍 blocking、contact face 依 side evidence獨立決定。
- 若實作失敗，可回滾 runtime relation分權與相關 tests／docs；因無 schema 或 persisted data change，不需資料 rollback。

## Risks / Trade-offs

- **[Risk] Candidate relation 被誤當正式 identity** -> 使用 explicit `identity_state`／typed unique-only view，並以 Project conversion、candidate points、forbidden points 的負向測試鎖定權限。
- **[Risk] 同一 ambiguous terminal 對多支 Waler 重複投票造成偏差** -> 每筆 evidence 只進入其 exact candidate Waler；contact side 看 sign 集合而非票數，不以多數決處理相反側衝突。
- **[Risk] Competing evidence 推翻既有 formal Waler** -> 先 partition `reliable_unique`／`reliable_competing`，只在 unique set 為空時啟用 competing fallback；以 Y05／Y1A／一般 CAD formal fixture regression 鎖定。
- **[Risk] 被忽略的 conflicting evidence 靜默消失** -> 產生 deterministic warning，保留 Waler、unique sources 與 competing sources provenance，並驗證 warning 不 blocking。
- **[Risk] 現有 Y29 編號與使用者口述 W17／W18 不一致** -> 先做 source-handle characterization；規格採通用行為，fixture assertion 使用實際 exact identities，禁止為符合名稱猜測 geometry。
- **[Risk] Formal Waler + unresolved member 的組合被 UI 誤解為可匯入** -> completed gate 仍以所有 blocking problems 為準，新增 Review integration test驗證 `can_import == false`。
- **[Risk] Extension candidate 來向不可靠** -> 沿用既有 intersection／body vector 與 degeneracy gate；若 fixture 顯示幾何語意不成立，停止並回修 spec，而非另加 heuristic。
- **[Trade-off] Waler 可以先 formal，但整批 Review 仍可能無法完成** -> 這是刻意分離可靠局部 truth 與未解連接，能讓診斷更精確，也不犧牲提交安全。

## Migration Plan

1. 先新增 pure characterization tests，鎖定目前 direct／extension competing sets、source identities 與 side signs，不改 production behavior。
2. 將 terminal outcome 改為 canonical relations + identity state，同步更新 topology unit tests，確保 issue provenance 與順序不變性。
3. 讓 contact-face finalization 依 unique-first precedence 消費 relations並產生 conflicting-competing warning；讓 connection／Brace verdict 明確過濾 unique-only relations。
4. 更新 overlap join、diagnostics、Preview／Review projection 與 lifecycle tests，驗證 formal Waler 不解除 blocking identity。
5. 跑 Y29、Y05、Y1A、一般 CAD／BIM／HATCH regressions、Project boundary 與 architecture boundary tests，確認原本 formal 的 Waler 全部維持 formal。
6. 實作驗證完成後，更新 `docs/DOMAIN.md` 的長期 evidence contract；只有實際 workflow 描述改變時才最小更新 `docs/WORKFLOW.md`。

