# Design

## 閱讀導航

### P0｜實作者現在必須理解

- Decision 1：base axis 與 terminal recovery 分成同一 pure service 內的兩階段，preliminary relation 只作 eligibility seed。
- Decision 2：700 mm 只建立 Column terminal window，residual 仍須匹配既有 rail bands。
- Decision 3：以「每個 sibling envelope 至少兩個 rail bands」與 endpoint tolerance 確認同一 terminal event，但每支 axis 保留自身 source-supported extent。
- Decision 4：finalized axes 完成後重新建立 contacts／pair relations，避免 preliminary 與 final 形成兩份 truth。

### P1｜修改相關模組時閱讀

- 修改 `dxf_import/joist_recognition.py`：閱讀 Decisions 1～5。
- 修改 `dxf_import/recognition.py` 或 diagnostics：閱讀 Decisions 4、6。
- 修改 tests：閱讀 Decision 7 與 Risks／Trade-offs。
- 更新長期文件：閱讀 Architecture Alignment 與 Migration Plan。

### P2｜需要時再讀

- Persistence、Review replay 或 confirmation regression 異常時閱讀 Decision 6。
- 一般 MLINE／closed-outline Beam regression 異常時閱讀 Backward Compatibility。
- 本次不修改 Solver、Project schema、材料辨識或 Brace-guided terminal recovery，可先跳過相關模組。

## 方案摘要

```text
同一 Beam root 的全部 primitives
        |
        v
現有強 evidence --> base paired axes
        |
        v
preliminary contacts + Column pair relation
        |
        v
Column center 朝 terminal outward 的 signed 0～700 mm window
        |
        v
短 fragments 對齊既有 6 個 rail bands
        |
        v
每個 sibling >= 2 bands + sibling terminals 相容
        |
        v
finalized paired axes（各自 source-supported terminal extent）
        |
        v
contacts / pair relations 全部重算並輸出唯一 final truth
```

`base axis` 是依現行一般 longitudinal evidence 門檻建立的初步完整方向、兩個 envelope centers 與主體 extent。`terminal residual` 是未通過一般相對長度門檻，但在已證明 Column corridor 內可對齊 base envelope rail bands 的同 root 來源線。`preliminary relation` 只用來證明是哪一個 Column／Strut corridor 可以開啟恢復，不會寫入 candidate、DXF result 或 Project row。

## 決策對照

| Decision | 影響的 Spec | 對應實作／驗證工作 |
|---|---|---|
| 1. pure service 內兩階段 finalization | ADDED residual Requirement；MODIFIED contact Requirement | Tasks 1、3 |
| 2. 700 mm contextual window + rail-band matching | ADDED residual Requirement | Tasks 1、2 |
| 3. 每 sibling 至少兩 bands、50 mm terminal compatibility | ADDED collective／isolated／conflict scenarios | Tasks 1、2 |
| 4. final axis 後重算 contacts | MODIFIED contact Requirement | Tasks 3、4 |
| 5. 不降低全域 20% 門檻 | ADDED residual Requirement；legacy compatibility | Tasks 1、5 |
| 6. 不新增 persistence truth | Review／Project 既有 Requirements 不變 | Tasks 4、5 |
| 7. Y05、Y1A、Y29 regression matrix | MODIFIED Y05 Requirement | Tasks 2、5、6 |

## Context

見 [proposal.md](proposal.md) 的 Why。現行 `_cluster_longitudinal_evidence()` 先取 root 內最長 segment，並以 `max(minimum_component_length_mm, maximum_length * 0.20)` 排除短 fragments；之後 `_source_axes()` 才從六個 longitudinal offset clusters 建立雙 C axes。這能阻止局部 L-angle detail 主導 whole axis，但也使 Column context 尚未參與前，Y05 柱外 500 mm terminal rails 已經消失。

Y05 E8F 的 base axes 目前從 `X=-35323.5` 開始；同 root 在 `X=-36173.5 → -35673.5` 仍有六條 500 mm aligned terminal rails。Column／Strut center 約在 `X=-35498.5`，殘線最外端距中心 675 mm。F2A 的一個 C envelope 保留三條 500 mm rails，另一個 envelope 因斜撐投影只留下約 156、182 與 2.5 mm fragments，但這些 fragments 仍落在既有三個 rail offsets 上。完整 Y05 corpus 的 20 個 paired roots 均呈現同一 terminal pattern。

現有 `JoistContextSnapshot` 已包含 finite Strut geometry與 `JoistColumnStationReference(strut_id, station)`；Column WCS center 可由該 Strut 起點、方向與 station 重建，不需要新增 Project schema 或 importer mutable lookup。

## Goals / Non-Goals

**Goals:**

- 在不放寬一般 whole-source evidence 門檻的前提下，恢復可由既有 paired Joist／Column relation 與同 root rail alignment 證明的端部殘線。
- 讓完整與被斜撐切碎的 terminal rail sets 使用同一 deterministic evidence contract。
- 讓 paired siblings 各自保留 source-supported extent，以 `50 mm` tolerance 只確認同一 terminal event，並使 contact、association、diagnostic 與 Project projection只消費 finalized axes。
- 以 pure WCS service 實作，不讓 Dialog、Review workflow 或 Project mapping重新推導幾何。

**Non-Goals:**

- 不建立 Brace-guided residual recovery，也不修改 Brace-contact single Joist eligibility。
- 不將任何 Column 周圍短線自動視為 Joist，不跨 root 拼接。
- 不修改雙 C spacing、Column midpoint、材料尺寸、Solver exclusion 或 Project schema。
- 不重構一般 Beam recognition 或共用 geometry framework。

## Decisions

### Decision 1：在 `recognize_bim_joist()` 內建立 base → recovery → final 三段流程

pure service 先沿用現行 `_source_axes()` 建立 base axes；若不是合法 paired outcome，維持現況，不進入 Column residual recovery。對 base paired axes，先以現行 contacts／pair logic 建立 ephemeral preliminary relations，只用來取得唯一的 `(Strut, Column, terminal side)` eligibility。

符合 eligibility 時執行 terminal recovery，產生新的 finalized axes；之後丟棄 preliminary contacts／relations並從 finalized axes 重算正式結果。任何 importer candidate、`JoistContact`、`BeamCrossing`、association 或 Project row 都只能來自 final pass。

**理由：** Column pair relation 需要先有兩條 axes 與 Strut contacts，但是否能看到柱外殘線又會改變 axis extent。兩階段 pure calculation 可解開順序依賴，同時避免持久化兩份 truth。

**拒絕方案：** 先在 importer 建 Beam，再由 `candidate_points.py` 延長。這會讓 recognition axis 與 downstream association 各有一套幾何，並使 Review／persistence drift。

**拒絕方案：** 直接讓所有短 fragments 進入 base clustering。這會改變 84 個 Y05 raw roots 的一般 eligibility，可能讓 46 個 L-angle detail roots 升格。

### Decision 2：從既有 rail offsets 回看短 fragments，不重新猜方向或 envelope

base paired outcome 已提供 canonical direction 與六個 longitudinal offset clusters。Recovery 重新走訪同 root primitives 的所有非零 segments，包括未通過一般 20% 門檻者，但只接受：

1. 與 base direction 的角度差不超過既有 `parallel_angle_tolerance_deg`；
2. transverse offset 可在既有 `JOIST_LONGITUDINAL_OFFSET_CLUSTER_TOLERANCE_MM` 內唯一匹配六個 rail bands 之一；
3. segment 位於某個 preliminary Column relation 所對應的 terminal side／Column occlusion corridor；
4. 以既有 axis 朝該 terminal 外側定義正方向，segment 最外 longitudinal signed projection 距 reconstructed formal Column center 位於 `0～JOIST_COLUMN_TERMINAL_WINDOW_MM = 700.0`（含邊界）；
5. segment 與 retained main body 分處 Column corridor 兩側或確實向該 terminal 外側提供新增 source extent。

Recovery 不從 residual 重新計算 direction、axis offset、axis count 或 C-pair identity。未匹配、匹配多個 bands、橫向／斜向、不同 root 或只在 main-body interior 的 segments 仍是 detail。

**理由：** 700 mm 是 context gate；真正的構件語意仍由已成立的 whole-source envelope rail bands提供。這能接受 E8F 的 500 mm rails，也能拒絕距離近但不屬於 envelope 的線。

**拒絕方案：** 只用離 Column center 最近或在圓形 700 mm 半徑內。距離不能證明 role，且本需求是沿 Joist 軸向的 terminal extent，不是 Euclidean proximity。

### Decision 3：使用 per-sibling rail-band quorum、source-supported extent 與 paired terminal-event compatibility

六個 rail bands 依既有 transverse order 分為兩個 sibling envelopes，每組三 bands。每個 envelope 在 terminal side 必須至少有兩個相異 bands 提供 residual endpoints。實作依 longitudinal terminal 方向對 endpoint stations 分群；同一 envelope 至少兩個 bands 的 endpoints 位於既有 `endpoint_tolerance_mm = 50.0` 內，才能形成該 envelope 的 source-supported terminal station。每個 sibling 的候選 station 只從自己的相容 rail-band 群組取最外實際來源 endpoint，不平均、不外插，也不引用另一個 sibling 的 endpoint。

兩個 sibling envelope stations 也必須相差 `<= 50.0 mm`。此 tolerance 只確認兩組 evidence 屬於同一 terminal recovery event，不把兩個 station 合併成共同座標。每支 finalized axis 以自身 envelope 的 source-supported station 作為端點，不得延伸至另一支 sibling 較外的 station。這使 F2A 可同時接受完整 sibling 的 `-36173.5` 與被切碎 sibling 約 `-36127` 的證據，又不會替後者補出約 46.5 mm 無來源線段，也不會讓單一約 2.5 mm 線自行控制 extent。

若任一 sibling 不足兩 bands，該 terminal 不恢復並保留 base axes；若同一 envelope 或 sibling pair 出現多組彼此超過 50 mm、且各自均達 quorum 的完整 interpretations，回傳新的 blocking terminal ambiguity diagnostic。

**理由：** 兩 bands 是建立一個 envelope terminal 的最低 collective evidence；50 mm 表示兩支 sibling 對同一實體端部的繪圖差異可接受，但不是外插授權。paired identity、spacing 與 relation 可共享，幾何端點仍各自由來源證據負責。

**拒絕方案：** 每一個 C 的三 bands 必須全部完整且等長。F2A 顯示斜撐會切碎個別 rails，會重現本次要解決的漏辨識。

**拒絕方案：** 任一短線可延伸兩條 axes。單一 detail 對 paired assembly 的證據不足。

### Decision 4：finalized axes 後重算 contact，direct crossing 優先

Recovery 完成後，對 finalized axes 重新呼叫既有 finite contact、endpoint-face contact與 pair-relation邏輯。`_finite_perpendicular_contact()` 先判定；同一 Strut 已有 direct contact 時，既有 `direct_member_ids` 機制自然阻止 endpoint-face duplicate。

Final pass 必須仍得到與 preliminary seed 相同的 Strut／Column pair identity、合法 spacing 與 midpoint。若 recovery candidate 只因證據不足而無法重新建立 relation，丟棄 recovery candidate、保留 base axes，並由 base axes 重建正式結果；若 finalized candidate 明確改指其他 Strut／Column、同時符合多個 identity，或產生多個完整且不相容的解，才回傳 blocking context-drift／ambiguity diagnostic。任何情況都不得提交 preliminary contacts／relations。

Y05 20 組第一主 Strut relations 因軸已跨越中心線，預期由 40 個 endpoint-face axis contacts 改成 40 個 finite contacts；68 組 paired relations、136 個 axis crossings、stations 與 Column identities保持不變。

**理由：** Contact method 必須描述 finalized finite geometry。繼續保留 endpoint-face會讓同一軸同時「停在外緣」又「穿越中心線」。

### Decision 5：保留一般 20% 門檻與非 contextual routes

`JOIST_MINIMUM_LONGITUDINAL_LENGTH_RATIO = 0.20` 繼續負責 base direction／rail cluster credibility。700 mm recovery 是 base paired outcome 成功後的窄路徑，不能讓失敗 root、single-axis root 或 non-BIM Beam通過。

Y1A MLINE、Y29 MLINE／closed outline 不呼叫此 recovery；六個角落 Brace-only single Joists也維持現況。

**理由：** 現行門檻同時保護 Y05 46 個 detail／residual roots。局部解例外不能改成全域放寬。

### Decision 6：只擴充 runtime diagnostic，不新增 persistence schema

需要時新增 DXF-internal outcome diagnostic code，例如：

- `BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS`
- `BIM_JOIST_TERMINAL_CONTEXT_DRIFT`

成功結果仍只透過既有 Beam `start/end/path`、contacts、root provenance 與 candidate points 投影。原始 residual primitives 已存在 `source_geometry`／root source scope，不另存 duplicated terminal-decision state。Pause／Resume 依 source fingerprint fresh recognition 重建；confirmation signature自然因 Beam geometry／contacts 改變而失效。

**理由：** finalized Beam geometry是唯一 downstream truth；另存 recovery decision 會與來源 DXF 漂移。

### Decision 7：以 synthetic boundary + 三圖 regression 驗證

測試分層：

- Pure synthetic：699.999／700／700.001 mm boundary、root mismatch、angle mismatch、offset mismatch、單 band、兩-band quorum、sibling 50 mm inclusive／exclusive、competing extents、final relation drift。
- Y05 source characterization：鎖定 20 paired roots 的 terminal residual inventory；E8F／BM18 恢復 `-36173.5`；F2A 接受被切碎但對齊的三個 bands；46 detail roots仍 failed。
- Y05 importer：58 Beams、20 paired assemblies、18 single Joists、68 pair relations與136 crossings不變；paired first-main-Strut contacts 改為 direct，stations不變。
- Y1A／Y29：Beam count、recognition method、path endpoints與 associations等價。

## Architecture Alignment

本 change 沿用既有 Architecture，不修改 dependency direction：

```text
Importer 建 immutable JoistContextSnapshot
        |
        v
joist_recognition.py pure service
  source primitives + Strut/Column context
        |
        v
single final JoistRecognitionOutcome
        |
        v
recognition.py candidate adapter
        |
        v
association / Review / Project projection
```

- `dxf_import/joist_recognition.py` 擁有 residual qualification、terminal finalization與 contact rebuild。
- `dxf_import/importer.py` 繼續只組裝 immutable upstream context；Column center由既有 Strut geometry＋station推導，預期不需擴充 DTO。
- `dxf_import/recognition.py` 只把 final outcome轉為 `_Candidate`，不重新判斷700 mm或 rail quorum。
- Presentation、Application、Domain、Algorithms不新增 dependency。

Single source of truth 是 final `JoistRecognitionOutcome.axes/contacts/pair_relations`。Preliminary relation僅為 pure function內區域變數，不得外洩；diagnostics、Preview、CandidatePoint、association與Project rows皆使用 final outcome。

## Backward Compatibility and Persistence

- Y1A、Y29 與所有 legacy non-BIM Beam維持既有結果。
- Y05 Beam IDs仍依 normalized finalized WCS geometry deterministic排序；兩 sibling 仍共享 root identity。
- Y05 的 contact method metadata會刻意由 endpoint-face改為finite crossing，但 Project `BeamPositions`／`AssociatedBeamIDs`及stations維持等價。
- Project schema與saved DXF review schema不變，無 migration。
- 舊 paused Review載入相同DXF時以fresh recognition得到新 geometry；既有 confirmation因signature改變而失效，需重新確認，沿用既有安全契約。

## Risks / Trade-offs

- **[Risk] 700 mm 把附近 detail 納入** → 必須先有paired Column relation，再要求same-root、direction、unique rail-band matching與per-envelope quorum；距離不單獨成立。
- **[Risk] Preliminary relation與final relation形成循環或漂移** → preliminary只作seed；final axes後完整重算。單純證據不足回退base axes，identity矛盾或多解才blocking，且只輸出final outcome。
- **[Risk] F2A極短fragment對extent權重過大** → 單band無效；每envelope至少兩bands，station cluster需在50 mm內，paired sibling也需相容。
- **[Risk] 以較外 sibling extent替另一支補長** → 50 mm只判定同一terminal event；兩支finalized axes各自停在自身source-supported station，不產生跨sibling外插。
- **[Risk] Y05既有endpoint-face regression大量變動** → 明確更新spec並鎖定relations、crossings、stations與Column identities不變，只改正contact method與axis terminal。
- **[Trade-off] 只有一個sibling留下可靠殘線時不恢復** → 保守保留base axes，不以paired identity替缺證據的sibling猜測完整長度。

## Migration Plan

1. 先加入pure characterization與boundary tests，固定目前base axes、residual inventory與預期final extents。
2. 實作runtime-only recovery與final contact rebuild，不修改persistence。
3. 執行Y05 focused importer regression，再執行Y1A／Y29與完整DXF tests。
4. 驗證完成後更新`docs/WORKFLOW.md`的current behavior；Architecture ownership未改則不更新`docs/ARCHITECTURE.md`。
5. Rollback為code／spec change rollback；由於無schema migration，既有Project檔不需資料回復。
