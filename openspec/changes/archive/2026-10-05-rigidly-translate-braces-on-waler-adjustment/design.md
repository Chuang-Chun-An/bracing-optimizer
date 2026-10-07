# Design

## 閱讀導航

| 優先級 | Decision | 何時必讀 |
| --- | --- | --- |
| P0 現在必讀 | Decision 1：以兩端最終 Waler 聯立共同平移 | 實作任何一般 Brace adjustment 前 |
| P0 現在必讀 | Decision 2：formal Brace baseline 與 baseline-WCS manual override 是 single source of truth | 修改初始化、人工端點、重複編輯或 replay 前 |
| P0 現在必讀 | Decision 3：平行、無解與有限線段採 fail-closed | 實作 geometry validation 與 diagnostics 前 |
| P1 實作前閱讀 | Decision 4：沿用既有 pure preview／atomic apply boundary | 修改 workflow、CandidatePoint 或 confirmation invalidation 前 |
| P1 實作前閱讀 | Decision 5：runtime baseline 不建立 Project／persistence 第二份 geometry | 修改 model、debug state 或 Pause／Resume 前 |
| P2 需要時再讀 | Decision 6：Preview data 明確呈現兩端 stations 與共同平移 | 修改 dialog 顯示或摘要格式時 |

可先跳過 Solver、材料配置、CornerBrace repair 與 Brace recognition candidate enumeration；本設計只消費已完成的 formal Brace／Waler identities，不修改這些上游規則。

## 方案摘要

```text
canonical recognition result
  -> replay manual endpoints in baseline WCS
  -> 重建正式連接，只為 canonical formal Brace 建立 immutable baseline
  -> 使用各 Waler baseline + adopted dimensions 得到最終有限線 Lf、Lt
  -> 求 A1 in Lf、B1 in Lt，且 B1 - A1 = B0 - A0
  -> 驗證唯一性／平行相容性／有限線段／identity
  -> pure plan 顯示 t、兩端 stations、角度與長度
  -> atomic apply 後重建既有 downstream facts
```

「共同平移」是同時套用到 Brace 兩端的單一 WCS 向量 `t`；「baseline」是本輪 recognition 與 baseline-WCS 人工端點 replay 完成、正式 Waler connection 重新建立後，但任何背填／寬度 adjustment 尚未套用前的 formal Brace geometry。「baseline WCS」不是另一套座標系，而是同一絕對 WCS 在未套用 Waler adjustment 時的座標語意。這些詞分別對應 proposal 的「斜撐保持原設計角度與長度」、「兩端接點共同滑移」及「人工端點不被重算覆蓋」。

## 決策對照

| Decision | 選擇原因 | 拒絕的替代方案 | 對應 spec／task |
| --- | --- | --- | --- |
| 1. 聯立兩端 Waler 求共同平移 | 直接保證兩端仍接觸且 Brace 向量不變 | 固定另一端或保留被編輯端 station；會旋轉／伸縮 | Spec「一般斜撐 SHALL 以共同平移…」；Task 2 |
| 2. 從 baseline-WCS manual override 建立 immutable formal baseline，再與兩端 final lines 重算 | 保留人工幾何、避免累積誤差、double-application 與 replay 順序差異 | 保存 adjusted WCS 或從 current Brace 做逐端增量更新；無法辨識已套用位移且容易 drift | Spec「斜撐 SHALL 使用兩端最終圍令…」；Task 1、3 |
| 3. 平行相容取最小平移，其他無解 fail-closed | 對多解提供唯一、可解釋結果；不破壞工程限制 | 任選 station、旋轉、伸縮、clamp 或 nearest snap | Spec 平行與原子失敗 Requirements；Task 2、3 |
| 4. 重用既有 plan／apply transaction | 維持 Preview pure、Apply atomic 與 rollback 語意 | 在 UI 或逐構件 mutation 時計算；會形成第二套工程邏輯 | Spec Preview／downstream Requirement；Task 3、4 |
| 5. Baseline 只屬 DXF Review runtime truth | 不擴張 Project／Solver schema，rebuild 時可從 canonical result 重建 | 把 baseline 或第二組 endpoints 寫入 Project row；會造成雙重 truth | Spec baseline 與 downstream Requirements；Task 1、4 |
| 6. 擴充既有 adjustment summary | 使用者需看見另一端也移動且長度／角度不變 | 只顯示被編輯端或靜默更新另一端 | Spec Preview Requirement；Task 4 |

## Context

動機見 `proposal.md` 的「Why」。目前 `plan_waler_contact_adjustment()` 會從單一 Waler baseline 計算平行位移；Strut 以原中心線與新 Waler 求交，CornerBrace 以既有固定長度／孔位約束重算，而一般 Brace 則保存被編輯 Waler 的 longitudinal station、只更新該端 endpoint。後者直接造成 Brace 向量改變，且 `BraceAdjustment` 目前只記錄單一 station。

`DXFReviewWorkflow` 已提供 pure preview 與 atomic apply boundary；apply 成功後會重建 association、CandidatePoint、validation 與 confirmation state。`DXFImportResult.to_project_rows()` 只輸出一組 Brace endpoints，因此新方案必須讓剛體平移後 endpoints 繼續成為唯一正式 geometry，不能另加僅供 Project 或 Solver 使用的第二組座標。

現有 `SourceManualOverride` 以 `world_start`／`world_end` 保存絕對 WCS，沒有 baseline／adjusted 語意標記；capture 直接擷取當下構件座標。現行 replay 先套用 Waler dimension inputs，再 replay 非 Waler geometry，因此在已調整畫面保存的 Brace endpoint 其實包含 adjustment。新規則可以沿用絕對 WCS 欄位，但必須把新 Brace override 的語意明定為 baseline WCS，並為舊資料提供可辨識且保守的相容路徑。

## Goals / Non-Goals

**Goals:**

- 在 WCS 中對一般 formal Brace 求出可驗證的共同平移，並讓 world／local projection 使用同一結果。
- 讓相同 baseline 與相同兩端最終 Waler 狀態產生相同結果，不受 preview、apply、Waler 編輯或 replay 順序影響。
- 讓 adjustment 前後的 Brace 人工端點都轉成同一 baseline-WCS truth，且非法換算不改變 Review state。
- 重用現有 DXF Review transaction、diagnostic 與 downstream rebuild boundary。
- 對平行、多解、無解及有限 segment 失敗提供 deterministic、fail-closed 行為。

**Non-Goals:**

- 不修改上游 Brace recognition、direct／extension candidate 或 Waler identity 選擇。
- 不把 Strut／CornerBrace 改成相同剛體規則。
- 不新增 Project row、Solver input 或 JSON schema migration。
- 不藉本 change 重構整個 `waler_contact_adjustment.py` 或通用 geometry library。

## Decisions

### Decision 1：以 baseline Brace 向量聯立兩端最終 Waler

令 baseline endpoints 為 `A0`、`B0`，固定向量為：

```text
v = B0 - A0
```

兩端最終有限 Waler supporting lines 分別為 `Lf`、`Lt`。非平行情況可將 `Lt` 反向平移 `v`：

```text
Lt_minus_v = { p - v | p in Lt }
A1 = intersection(Lf, Lt_minus_v)
B1 = A1 + v
t  = A1 - A0
```

這個 construction 直接保證 `B1 - A1 = v`。實作亦可使用兩條 Waler 單位法向 `nf`、`nt` 聯立：

```text
nf dot t = df
nt dot t = dt
```

其中 `df`、`dt` 是兩端 final lines 相對各自 baseline line 的 signed normal displacement。兩種算法必須在 tolerance 內等價；建議以既有 line-intersection primitive 為主要路徑，法向方程用於清楚處理平行相容性與測試 oracle。

求得無限線解後，仍須驗證 `A1`、`B1` 分別落在對應 final finite segment。不得將 infinite-line solution clamp 到端點。

### Decision 2：以 baseline-WCS manual override 建立最小 formal Brace adjustment baseline

Baseline builder 只消費 canonical result 中已成立的 formal Brace。最低 identity gate 為 `Brace.has_formal_connection` 所表達的兩端 identity 皆存在且不同；同時仍須符合 `enforce-unique-brace-waler-terminals` 已同步至 main spec 的完整 formal connection contract，包括兩端各自唯一、selected contact faces 正式完成及有限交點合法。`decouple-waler-side-evidence-from-terminal-identity` 所允許的 side-only／competing evidence 只可協助 Waler contact-face finalization，不能單獨建立 Brace baseline。

對每支符合上述條件的 formal Brace 建立不可變 baseline，最少包含：

- `brace_id` 與 source identity；
- baseline `start`／`end` WCS endpoints；
- `from_waler_id`／`to_waler_id`；
- 必要時保存端點與 identity 的明確對應。

此 baseline 是 adjustment 計算的 single source of truth。每次計畫 target Waler 時，先用 proposed target line 取代目前 target line，再與另一端目前 final Waler line共同求解；不得把 current moved Brace 當新 baseline。

Baseline 應位於 DXF Review runtime model，而不是 Project Domain。Recognition rebuild、source exclusion／restore 或 manual endpoint replay 完成後，由新的 canonical formal result 重建整組 baseline；舊 baseline 不做 ID 猜測或幾何近似 rebind。

Brace 人工端點 override 一律保存「未套用 Waler 尺寸 adjustment」的 baseline WCS。若使用者在已調整畫面修改端點：

1. 從既有 immutable baseline 與目前採用尺寸形成的兩端 final Waler lines，使用 Decision 1 的同一 pure solve 取得該 Brace 目前共同平移 `t`；不得由可能已 drift 的 current Brace 猜測 `t`。
2. 對要保存的可見端點套用 `p_baseline = p_clicked - t`；未被拖動但屬於同一人工 endpoint pair 的另一端，也以其目前可見位置減去相同 `t`，使整組 override 只有一種座標語意。
3. 換算後每一端必須落在其 identity 對應的 baseline Waler finite segment，並通過既有具名 tolerance。任一端失敗即拒絕整次人工修改，顯示可理解原因，且不改動 endpoint、CandidatePoint、connection、confirmation、baseline 或其他 Review state；不得 clamp、nearest snap 或硬存。
4. 在尚未套用有效 adjustment 時 `t = (0, 0)`，因此 adjustment 前的人工點可直接成為 baseline WCS。若畫面上已有 adjustment、但缺少可驗證的 formal baseline 或共同 `t`，也必須拒絕換算而不是假設零位移。

所有 rebuild／Resume／replay 固定使用下列順序：

```text
recognition
  -> replay Waler 與 member manual geometry（Brace endpoints 為 baseline WCS）
  -> 重建 contact faces／terminal identities，建立 formal Brace baselines
  -> 套用或 replay Waler dimension decisions
  -> 重建 downstream derived state
```

這個順序讓「先改端點再調 Waler」與「先調 Waler 再改端點」都以人工修改後的 baseline geometry 求解；Waler displacement 只在 baseline 建立後套用一次。不得先套用 dimension decision、再把 baseline-WCS override 當 adjusted WCS 重播，也不得從已平移結果再次建立 baseline。

為辨識新舊保存語意，`SourceManualOverride` 可增加 optional `geometry_coordinate_space`，新 Brace geometry 使用值 `baseline_wcs`。此欄位位於既有 version 2 `manual_overrides` item，不提升 `review_state_version`，也不是 Project schema。舊 Brace override 缺少標記時採保守相容：若目前沒有有效 Waler 位移、共同 `t` 為零，可將既有絕對 WCS 安全視為 baseline WCS；若存在非零位移，舊座標可能已包含舊演算法的旋轉／伸縮，人工 geometry 必須列入 `needs_review` 並跳過，尺寸 decision 仍可獨立安全 replay。非 Brace override 不因本 Decision 改變語意。

拒絕只保存「每支 Brace 在單一 Waler 的 station」，因為同一剛體解依賴兩端線，單端 station 不是足夠或 authoritative 的狀態。

### Decision 3：平行與退化情況使用既有 tolerances 並 fail-closed

若 `Lf` 與 `Lt` 在既有 parallel tolerance 內平行：

1. 以兩端 baseline／final line 的 signed normal constraint 判斷是否存在共同 `t`。
2. 不相容時產生新的 blocking diagnostic，例如 `BRACE_RIGID_TRANSLATION_UNRESOLVED`。
3. 相容但沿線方向有無限解時，取滿足 constraints 的 minimum-norm `t`；這等價於不加入任意 tangential slide，並保持 baseline longitudinal stations。

非平行解若落在任一 finite segment 外、baseline Brace 退化、identity 缺失／相同／drift，或結果不滿足共同向量 invariant，均進入同一 fail-closed family，但 diagnostic detail 應區分 `parallel_incompatible`、`outside_finite_segment`、`identity_invalid` 與 `baseline_drift`，方便 Review 定位。

Tolerance 必須沿用 `GeometryTolerances` 中現有具名 angle、distance 與 finite-contact 邊界。若現有欄位語意不足，實作應先回報而非新增藏在 helper 內的 magic number。

### Decision 4：在既有 pure plan 中完成全構件驗證，再 atomic apply

`plan_waler_contact_adjustment()` 繼續是唯一工程 planning boundary：

- 建立 target Waler proposed line；
- 保留既有 Strut 與 CornerBrace paths；
- 對所有連接 target Waler 的 formal Braces，以 baseline 與兩端 final lines 重算兩個 endpoints；
- 收集 blocking diagnostics；
- 只有完整 proposed result 無 blocking error 時，`apply_waler_contact_adjustment()` 才回傳新 result。

不能在 `dialog.py`、summary formatter、CandidatePoint rebuild 或 Project conversion 重新求解共同平移。這些 consumers 只讀 plan／proposed result，以避免形成第二套 truth。

### Decision 5：重建 baseline，不持久化第二組正式 geometry

Project row 繼續只輸出調整後的單一 `Brace.start/end`；不新增 baseline、translation 或 connection-point 欄位。Pause／Resume 與 compatible recovery 已保存 Waler dimension decisions，恢復時應依 Decision 2 先 replay baseline-WCS manual endpoints、重建 canonical formal baselines，再按目前有效 decisions 重算。

若 runtime model 需要 `BraceContactAdjustmentBaseline` 欄位，它是可重建 state：

- 不成為 Solver input 或 Project schema；
- 不作為 changed-content recovery 的 transferable geometry；
- 舊保存資料沒有此欄位時，應由當前 canonical recognition 重建，不做 schema migration；
- 若當前 result 已無法證明是 adjustment 前 baseline，則不得從已旋轉／伸縮的舊 Brace 猜測，應將相關 replay 標為需重新檢查。

現有 runtime 已有 `ManualReplayReport`，Source Exclusion／Restore 與 compatible recovery 可顯示 `preserved`／`needs_review`／`disabled` 摘要；但一般 same-source Resume 目前沒有「依新規則重算後 Brace 位置可能不同」的專用提示。依本 change scope 不新增 UI。實作驗證完成後只在 `docs/WORKFLOW.md` 的 Pause／Resume 契約記錄：Resume 會依目前 canonical facts 與新順序重算，Brace 位置可能不同於舊版曾採用的結果；無法安全 replay 的人工端點仍使用既有 `needs_review` report semantics。

### Decision 6：Adjustment preview 顯示雙端變化

`BraceAdjustment` 應從單一 `waler_station_mm` 擴充為能表達：

- 共同 translation vector；
- From／To 兩端 old／new Waler stations；
- baseline／proposed endpoints；
- baseline／proposed length 與 angle（合法結果應在 tolerance 內相等）。

`format_adjustment_plan()` 與既有 dialog preview 只格式化這份資料。這不要求重新設計 UI layout，但必須避免仍顯示「單端 station 不變」的誤導訊息。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 layer responsibility 或 dependency direction。

| Layer／subsystem | 責任與變更 |
| --- | --- |
| `dxf_import` models／geometry | 保存可重建的 runtime baseline，提供 pure rigid-translation calculation／validation |
| `dxf_import` Waler contact workflow | 協調 target Waler proposed line、兩端 Brace solve、diagnostics 與 proposed result |
| `DXFReviewWorkflow` | 維持 preview、revision、atomic apply、confirmation invalidation 與 derived-state rebuild owner |
| Presentation | 只顯示 plan；不得自行推導另一套 Brace 平移 |
| Project／Application／Solver | contract 不變，只接收唯一正式 Brace endpoints |

依賴仍停留在 DXF Import subsystem 內，沒有 `Domain -> Infrastructure`、`Algorithms -> UI` 或新的跨 layer dependency。

## Backward Compatibility 與 Persistence Impact

- 既有尚未調整 Waler 的 DXF recognition 結果不變。
- 舊 same-source paused Review 的 dimension decisions 可在新 canonical baseline 上 replay；結果會依新規則重算，這是預期行為變更。
- 新保存的 Brace manual endpoint override 以 optional `geometry_coordinate_space = "baseline_wcs"` 表明座標語意；仍使用 review state version 2。
- 舊未標記 Brace override 在 `t = 0` 時可安全視為 baseline WCS；存在非零 Waler adjustment 時只將人工 geometry 標為 `needs_review`／skip，不猜測成功或反推舊旋轉，且不阻止可獨立重驗的尺寸 decision。
- Project rows、Project JSON schema、Solver input 與材料資料沒有 migration。
- Debug／preview 可新增非 authoritative 的 baseline／translation 資訊，但不得讓舊 payload 缺少該資訊就被當成錯誤；authoritative baseline 必須由目前 canonical result建立。

## Risks / Trade-offs

- **[Risk] 接近平行的 Waler 會產生很大的沿線滑移。** → 使用既有 parallel tolerance 分類並一律驗證 finite segments；超出即 blocking，不新增自動截斷。
- **[Risk] 單一 Waler 編輯會移動 Brace 的另一端，影響 CandidatePoint 或 Beam contact。** → 將整支 Brace 列為 changed component，沿既有 downstream rebuild 一次重算並做 focused regression。
- **[Risk] Sequential replay 若仍逐筆增量套用可能 order-dependent。** → 每筆 apply 只更新 dimension decision；所有受影響 Brace 都從 immutable baseline 與目前兩端 final lines 重算，並加入兩種順序的等價測試。
- **[Risk] 舊 paused state 可能帶有舊演算法已旋轉的 Brace geometry。** → Resume 以新 recognition result 建 baseline，再 replay dimensions；無法證明 baseline 時要求 review，不反推原幾何。
- **[Risk] 在 adjusted view 保存可見端點會把 Waler 位移寫入 override，造成 Resume double-application。** → 保存前使用同一 rigid solve 扣除共同 `t`，以 optional marker 區分新舊語意，並以固定 replay 順序測試位移恰好套用一次。
- **[Trade-off] 不相容平行 Waler 將從可套用變成 blocking。** → 這是維持角度、長度及兩端接觸三項 hard constraints 的必要結果；不得靜默退回舊行為。

## Migration Plan

1. 先加入 pure geometry／formal-only baseline model、baseline-WCS override marker 與相容性 tests，不改 UI。
2. 將一般 Brace planning 切換為共同平移，並讓 adjusted-view manual endpoint 在 atomic commit 前完成 `p - t` 與 baseline finite-segment validation；保留現有 Strut／CornerBrace paths。
3. 將 workflow replay 固定為 manual geometry → baseline → Waler dimensions，擴充 plan summary、Resume／recovery 與 downstream rebuild tests。
4. 執行 focused DXF contact tests、Review／recovery regression、Project conversion 與完整測試。
5. 驗證完成後更新 `docs/DOMAIN.md` 與 `docs/WORKFLOW.md` 的 long-term truth；不修改 `docs/SOLVER.md`。

Rollback 可回復本 change 的 runtime baseline與共同平移路徑；沒有 Project／persistence migration 需要反向轉換。已保存的尺寸 decisions仍可由舊版既有欄位讀取，但回到舊版會恢復舊的旋轉／伸縮行為，因此版本回退不保證相同 preview geometry。

