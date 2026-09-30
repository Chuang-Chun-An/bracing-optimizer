# Design

## 閱讀導航

### P0：實作者現在必須理解

- D2：canonical direction／normal 與不依賴順序的 RailTrack hypotheses。
- D3：`BodyGeometryEvidence` 與 `BodyRelationshipAssessment` 的責任邊界。
- D4～D6：逐關係 coverage、complete／occluded 分類、extension 與唯一性。
- D7：relationship-selection repair 的資格與 transaction boundary。

### P1：實作對應模組前閱讀

- `proposal.md` 的主要流程與不變事項。
- 三份 delta specs 的完整 Requirements 與 scenarios。
- `tasks.md` 的測試順序；實作不可早於對應 boundary tests。

### P2：需要時再讀

- `docs/WORKFLOW.md`：修改 Preview／Apply、revision 或 rollback 時閱讀。
- `docs/DOMAIN.md`：所有行為完成驗證後才同步正式工程規則。
- 可先跳過 Solver、Project material 與非 CornerBrace recognizer 文件。

## 方案摘要

```text
finite source fragments
  -> canonical direction / canonical normal
  -> all valid RailTrack hypotheses
  -> all valid track-pair BodyGeometryEvidence
  -> each active finite Waler/Strut pair
       -> one BodyRelationshipAssessment
       -> expected span + slenderness
       -> per-rail coverage + gaps + occluders
       -> per-end extension
       -> complete / occluded / hard-invalid
  -> resolve body first, relationship second
       -> unique body + one hard-valid assessment: automatic
       -> unique body + multiple hard-valid assessments: Preview selection
       -> zero/multiple bodies: unresolved; no relationship-selection repair
```

本設計不讓 relationship-dependent 結果回寫或污染 body geometry。相同 body 對 relationship A 可有 60% coverage、對 relationship B 可有 45%；兩個 assessment 必須獨立保存與判定。

## 決策對照

| Decision | 結論 | 對應 tasks |
|---|---|---|
| D1 | CornerBrace 專用具名 hard gates | 1 |
| D2 | canonical-normal clustering、全 hypotheses、順序不變 | 2 |
| D3 | BodyGeometryEvidence／BodyRelationshipAssessment 分層 | 3、4 |
| D4 | complete／occluded 都逐軌 coverage `>= 50%` | 3 |
| D5 | 每個 `>50 mm` gap 個別綁定 finite occluder | 3 |
| D6 | body first、relationship second 的唯一性 | 4 |
| D7 | unique-body relationship-selection Preview／Apply | 5 |
| D8 | synthetic boundaries 與 Y05／Y29／Y1A regressions | 1～6 |

## Context

現有 CornerBrace recognizer 以有限 LINE pairs 與端板為核心，且工作區中的初版 redesign 仍把 expected span、coverage、classification 與 extension 放入一份 body truth。這使 body 是否「完整」依賴所選 Waler／Strut，也讓 complete 類別可能繞過 coverage。RailTrack 若以第一條線為 seed／representative，也會使 offsets `0,20,40 mm` 隨 fragment order 得到不同結果。

既有共用 tolerances 仍服務其他 recognizers。本 change 只新增或重用具名 CornerBrace settings，不全域修改非目標行為。

## 專有名詞

- **Rail fragment**：exact source 中可支持角撐長向的一條有限線段。
- **Canonical direction**：把平行方向視為無方向軸後得到的 deterministic 單位方向；line start／end 反轉不改變它。
- **Canonical normal**：由 canonical direction 以固定旋轉規則導出的 deterministic 法向。
- **Normal offset**：fragment supporting line 沿 canonical normal 的法向位置。
- **RailTrack hypothesis**：normal-offset spread、方向與 interval 規則均合格的一組 fragments；可與其他 hypothesis 共用 fragment。
- **BodyGeometryEvidence**：只保存不因 Waler／Strut relationship 改變的本體幾何。
- **BodyRelationshipAssessment**：一個 body 對一組 active finite Waler／Strut identities 的完整 hard-gate 評估。
- **Expected span**：body midline 與該 relationship 的有限 Waler 內線、有限 Strut 中心線交點之間的距離。

## Goals / Non-Goals

**Goals:**

- 讓 rail clustering 與輸入順序、first seed、line orientation 無關。
- 讓同一 body 的不同 relationships 各自擁有 coverage、gaps、classification 與 extension。
- 讓完整與遮擋候選使用相同 coverage／extension 基本資格。
- 讓 relationship ambiguity 可安全 Preview／Apply，但不能掩蓋 body ambiguity。

**Non-Goals:**

- 不建立通用 CAD clustering framework。
- 不建立 canonical Waler 或更改 source identity。
- 不修改 Project schema、Solver 或一般構件辨識。
- 不把 repair 擴張為 body selection UI。

## Decisions

### D1：CornerBrace 專用具名設定

使用具名 recognition settings 表達下列規則：

- rail separation：`250.0 < separation <= 600.0 mm`
- expected slenderness：`expected span / separation >= 3.0`
- direction seed length：`>= 100.0 mm`
- direction difference：`<= 2°`
- RailTrack normal spread：`<= 25.0 mm`
- seam：`<= 50.0 mm`
- per-rail coverage：`>= 0.5`
- near-parallel occluder gap overlap：`>= 0.5`
- Waler 與 Strut 每端 outward extension：`<= 600.0 mm`

`600 mm rail separation` 與 `600 mm extension` 是不同維度、不同判定，不得共用結果或互相補償。可以重用既有數值設定，但欄位名稱／文件必須清楚表達 CornerBrace 語意，避免再次把 Brace-only 歷史規則誤當成已成立的角撐規則。

### D2：以 canonical normal 全列舉 RailTrack hypotheses

1. 從所有長度 `>=100 mm` 的 eligible fragments 建立無方向性的 canonical direction hypotheses；方向正負使用固定排序正規化。
2. 每個 direction hypothesis 產生固定 canonical normal，將所有方向差 `<=2°` 的 fragments 轉為 normal offsets 與一維軸向 intervals。
3. 一組 RailTrack fragments 必須整體符合 `max(normal_offsets)-min(normal_offsets) <=25 mm`。不得只檢查 fragment 對第一條 seed 的距離。
4. 對所有可成立的 maximal／非等價 fragment subsets 建立 hypotheses，再以 normalized supporting-line identity、fragments 與 merged intervals 合併真正等價結果。
5. Representative supporting line 由整組 offsets 以 deterministic、order-independent 方式取得；不得直接採用第一條 supporting line。
6. 同一 fragment 可暫時支持 competing hypotheses。若 offsets 為 `0,20,40 mm`，至少保留 `{0,20}` 與 `{20,40}`，不得建立 spread 40 mm 的 `{0,20,40}`。
7. Fragment iteration、DXF entity order 與 line start／end 反轉不得改變 hypothesis 集合或 diagnostics。
8. 每個 hypothesis 將 intervals 排序並合併 overlap 與 `<=50 mm` seam；union length 不重複計數。短於 100 mm 的 fragment不能建立方向，但可在方向成立後加入合格 track。

Track-pair 必須全列舉 separation 位於 `(250,600]` 的平行 tracks；不得使用 longest-first、first-fit、固定 80% projection gate 或 handle order 提前決定。

### D3：BodyGeometryEvidence 與 BodyRelationshipAssessment 分層

`BodyGeometryEvidence` 只保存：

- exact source identity
- rail fragments 與 RailTracks
- selected track pair
- normalized supporting-line identities
- canonical direction／normal
- midline 與 rail separation
- merged source intervals
- terminal-plate evidence

它不得保存 expected span、expected slenderness、coverage、gaps、occluder assignments、extension、complete／occluded classification 或 hard-valid outcome。

每一組 active finite Waler／Strut identities 建立獨立 `BodyRelationshipAssessment`，保存：

- Waler／Strut source identities
- midline 的有限 intersections
- expected span 與 expected slenderness
- 每軌 union coverage
- internal／terminal gaps
- 每個 gap 的 occluder assignment
- Waler 端與 Strut 端 extension
- complete／occluded classification
- hard-valid outcome 與 structured rejection reasons

Body geometry 可被多個 assessments 引用，但 assessment 結果不得回寫 body。Diagnostics、repair planner 與 Presentation 只讀 structured fields，不解析 message。

### D4：逐 relationship 同時檢查 coverage、extension 與 classification

每個 assessment 先由 body midline 與有限 Waler／Strut 求交建立 expected span，再依相同 expected span 計算兩條 selected rails 的 interval union coverage。兩條 rail 都必須 `>=50%`；不只檢查較短軌或被標記為受遮擋的軌。

以下 hard gates 必須同時成立：

- rail separation 位於 `(250,600] mm`
- expected slenderness `>=3.0`
- rail A coverage `>=50%`
- rail B coverage `>=50%`
- Waler 端 extension `<=600 mm`
- Strut 端 extension `<=600 mm`
- 有效有限交點、唯一 identity 與其他既有 validation

分類在通過共同 gates 後進行：

- `complete`：沒有需要遮擋證據的 `>50 mm` internal／terminal gap。
- `occluded`：存在至少一個 `>50 mm` gap，且每個 gap 都有合格 finite occluder evidence。
- 任一共同 gate 失敗或任一大 gap 無法解釋：hard-invalid。

100 mm 只表示 fragment 足以建立方向，不表示 coverage 合格。以 expected span `sqrt(1500²+1500²)=2121.320 mm` 為例，每軌 50% 是約 `1060.660 mm`。兩端各 extension 600 mm 時，即使 extension 等號合法，coverage 約 43.4% 仍須拒絕；反之 coverage 通過但單端 extension 800 mm 也須拒絕。

### D5：每個大 gap 必須有自己的 finite occluder

Gap evidence 只接受已辨識 Brace／Strut／Waler／Column／Beam 的有限來源幾何，以及同一 exact source 的其他有限線。文字、尺寸、HATCH pattern、draw metadata、顏色、draw order 或無限延長線不得成為 evidence。

- 正交／斜交 occluder：有限 segment-to-gap-corridor distance `<=25 mm`，且有限投影進入該 gap interval。
- 方向差 `<=2°` 的 near-parallel occluder：除 corridor 條件外，與 gap interval 的一維 overlap／gap length 必須 `>=50%`。
- 每個 `>50 mm` internal／terminal gap 必須各自綁定 evidence；一條只解釋某 gap 的 occluder 不能替其他 gap 背書。

Terminal plates 不是資格，只作 terminal evidence 或在唯一連接特定 pair 時協助消歧。

### D6：先解 body，再解 relationships

1. 全列舉 RailTracks 與 track pairs，移除 hard-invalid body geometry，保留 structured reasons。
2. 合併真正幾何等價的 body hypotheses；對共用 evidence 的非等價 bodies 建立 conflict sets。
3. 若 body 零解或存在多個非等價最大解，回報 body unresolved；不得進入 relationship-selection repair。
4. Body 唯一後才查看該 body 的 hard-valid `BodyRelationshipAssessment`。
5. 零組 hard-valid relationship：relationship unresolved。
6. 一組：automatic 建立唯一 Waler／Strut connection。
7. 多組：automatic unresolved，保留所有 active source identities，建立 structured repair candidates。

不同 Waler sources 即使有限幾何重合仍是不同 relationships，不得合併為 canonical Waler。排除 source 後必須依 current active facts 重建 assessments；不得重播先前暫時選擇。

### D7：Relationship-selection repair 只消解唯一 body 的關係多解

Repair 增加 `body_relationship_selection` mode，與既有 `reference_template` mode 分離：

- 只接受一份唯一 `BodyGeometryEvidence` 及其多組 hard-valid assessments。
- 每個 Preview candidate 綁定一組 exact active Waler／Strut source identities、finite endpoints、coverage、classification、extensions 與 validation result。
- 不需要 template，不改選 tracks，不重算 body，不解析 diagnostic message。
- Preview 未明確選擇時 Apply disabled；開啟、改選、取消或關閉均不得改變 live state。
- Apply 前以 current revision、body signature、active identities 與完整 assessment hard gates 重驗。
- 成功後原子建立 CornerBrace、connection、candidate points、problems／ReviewItems與 derived values；任一步失敗完整 rollback。

現有 manual override／repair provenance 只能使用 backward-compatible optional fields；若需要 Project schema migration，停止並回報。

### D8：驗證層次

- **Pure geometry**：`2°`、`25 mm` normal spread、`100 mm` seed、`50 mm` seam、`(250,600]` separation、`3.0` slenderness、`50%` per-rail coverage、near-parallel `50%`、每端 `600 mm` 等號兩側。
- **Determinism**：offsets `0,20,40` 的所有排列、line reversal、shared fragment competing hypotheses 與無法消歧時的 body ambiguity。
- **Relationship isolation**：同一 body 對 A 為 60%、對 B 為 45%；多組 hard-valid relationships；source exclusion 後唯一自動建立。
- **Coverage／extension independence**：2121.320 mm span 的 50% 等號、雙端各 600 但 coverage 43.4%、coverage 通過但單端 800。
- **Gap classification**：coverage 合格且有大 gap 時必須進 occluded；每個 gap 分別驗證。
- **Workflow**：Preview、explicit Apply、revision revalidation、tampered candidate 與 rollback。
- **Real regressions**：Y05 `104C`、`1081`、`F9E`、`FB7`；Y29 `4C`；Y1A；既有 Y05 60／60、Y29 52／52 slenderness population。

## Architecture Alignment

```text
DXF source geometry
  -> dxf_import recognition / private geometry helpers
  -> immutable BodyGeometryEvidence + BodyRelationshipAssessment
  -> validation / Review workflow
  -> Presentation Preview
  -> explicit workflow Apply
```

- `recognition.py` 或同層 helper 負責 clustering、intervals、body／relationship assessments 與 selection。
- `models.py` 只承載具名 settings 與 immutable structured data，不放演算法。
- `validation.py` 將 structured outcomes 投影成 problems，不重算幾何。
- `corner_brace_repair.py` 從 structured hard-valid assessments 建立 candidates。
- `review_workflow.py` 維持 revision check 與 atomic Apply。
- Presentation 只顯示資料，不重算或決定工程關係。

## Risks / Trade-offs

- **候選數增加**：先合併真正等價 tracks／bodies，再評估 finite relationships；不得用 first-fit 限量。
- **相鄰細節誤分群**：使用整組 normal spread、方向、interval 與 body gates，並以 permutation tests 鎖定。
- **Body／assessment 漂移**：兩個 immutable layers 以 body signature 關聯，下游不得重新列舉。
- **人工選擇增加**：只在 body 已唯一且多組 relationships 都 hard-valid 時出現，換取不猜測 Waler ownership。

## Migration Plan

1. 先建立 settings、canonical clustering 與 pure tests，不切換 production route。
2. 建立兩層 immutable evidence 與逐 relationship assessment。
3. 切換 complete／occluded selection 與 diagnostics，加入真實 cases。
4. 擴充 relationship-selection Preview／Apply 與 provenance。
5. 執行 focused、boundary、module、Y05／Y29／Y1A及完整 regression；通過後才更新 `docs/DOMAIN.md`。

Rollback 必須整體停用新 route；不得保留只套用 coverage、extension 或新 repair mode 的半套行為。

## Open Questions

沒有會改變 spec 或 acceptance criteria 的未決問題。Internal class／helper 名稱屬實作選擇。若需要新增 Project schema、改變 Waler identity、使用 first-match／first-fit 或解析 message，必須停止並回報。
