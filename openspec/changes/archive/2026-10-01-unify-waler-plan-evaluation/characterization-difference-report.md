# Automatic／Manual Waler Characterization 差異報告

## 閱讀導航

### P0｜現在必讀

- 「結論與 gate 狀態」：五項 B 類差異均已由使用者確認，並記錄最後採用的統一規則。
- 「B 類差異」：保留各項原始輸入、兩邊結果、來源與當時建議，供追溯決策背景。
- 「最終確認結果」：列出取代早期建議的正式決策與目前實作狀態。

### P1｜實作／驗證時再讀

- `proposal.md`「已確認統一規則／不變事項／Impact」與 `specs/waler-plan-evaluation/spec.md`：已納入最終決策，作為目前 normative contract。
- `design.md` Decision 1～3、7、8：說明最後 evaluation sequence、完整 issue projection 與效能修正。

### P2｜需要時再讀

- `tests/test_waler_plan_evaluation_characterization.py`：可重現本報告的 exact payload 與比較案例。
- `tests/test_plan_editing.py`：人工編輯既有欄位順序、score、errors 與 legality 顯示 baseline。
- `performance-baseline.md`：記錄修改前 baseline、兩次停線、profiler 與最後 synchronous scanner gate。

## 結論與 gate 狀態

> **最終決策更新（2026-10-01）**：五項 B 類差異均已由使用者逐項確認。B-01 最初依本報告建議實作為「可 allocation 的 invalid plan 仍計 diagnostic components」，但同 fixture 效能 gate 測得 Single 中位數增加 114.2%、Global 增加 65.3%；使用者重新確認為：core 先完整收集全部 hard issues，只要有任一 total／joint／segment range／non-purchasable issue，automatic 與 manual 都停止 allocation、ratio 與 local score。B-02 採 automatic 的 unavailable allocation 語意；B-03／B-04 的 core 與人工畫面都保留並顯示全部 issues；B-05 由使用者確認的新工程規則取代兩邊舊行為：Waler 不使用 adjustment block，鋼材總長採 `[required_length - 200, required_length]` 閉區間，超界分別顯示總長不足／太長。這些最終決策取代下方各節的早期建議。

比較確認合法方案在相同 context 與庫存下的 legality、allocation、score components 與 local score 相同；Qty 限制與 material spec 空白 fallback 也相同。另有三項只涉及 payload／文字呈現的 A 類差異。

比較階段發現五項 B 類差異：

1. 工程不合法但仍可精確配料時，automatic 立即 short-circuit，manual 仍計算 allocation 與 local score。
2. segment 不可購買時，automatic 不產生 allocation components，manual 產生 fallback components 與數值 score。
3. 同一 plan 有多個 joint-clearance 違規時，automatic 回報全部，manual 只保留第一個。
4. 同一 plan 有多個不可購買 segment 時，automatic 回報全部，manual 只保留第一個。
5. 防禦性 total mismatch 的核心 issue 種類不同：automatic 是 resolved steel total mismatch，manual 是 tail completion invalid。

依 Task 1.4，當時曾在此停線。使用者完成確認、artifacts 更新並通過 strict validation 後才開始 Group 2；目前實作與回歸驗證已完成。

## 比較方法與共用輸入

兩條路徑均由同一份 `InventoryLookup` 語意取得 purchasable lengths 與 stock items。material spec 有值時保留實際 `Qty`；空白規格時兩條路徑都使用既有 `UNLIMITED-*` fallback（每個可購買長度 Qty 99）。

本報告的共用庫存 I-1：

| ItemCode | Spec | Usage | Length | Qty |
| --- | --- | --- | ---: | ---: |
| W-4000 | H400 | 圍令 | 4000 | 3 |
| W-6000 | H400 | 圍令 | 6000 | 2 |
| W-8000 | H400 | 圍令 | 8000 | 2 |

共用預設 config C-1：

- required／resolved steel length：12000 mm
- min piece：1000 mm；max piece：10000 mm
- joint clearance：300 mm
- purchasable lengths：`[4000, 6000, 8000]`
- ratio targets：short `0.2`、mid `0.5`、long `0.3`
- material spec：`H400`
- stock items：由 I-1 及其 Qty 原樣解析

比較測試位置：`tests/test_waler_plan_evaluation_characterization.py`。focused baseline 同時執行 `tests/test_plan_editing.py`，共 39 tests 通過。

## A 類差異

### A-01｜合法 payload 欄位與顯示結構不同

- 輸入：segments `[6000, 6000]`、joints `[6000]`、C-1、I-1、無 forbidden point。
- 共用核心結果：兩邊均 valid；assignments 均為 `W-6000#1/#2`；`buy_count=0`、`distinct_groups=1`、`length_variation=0`、`under_4000=0`、`ratio_penalty=100000.0`、`joint_count=1`、`score=106000.0`。
- 格式差異：automatic 有 `individual` 與平面 `errors`；manual 另有 `pieces`、`required_length`、`steel_length` 與巢狀 `legality.summary/details/warnings`，欄位順序也不同。
- 處理：由 automatic／manual compatibility projector 分別保留，無需改工程規則。

### A-02｜同一 joint-clearance issue 的文字與欄位名稱不同

- 輸入：segments `[6000, 6000]`、joints `[6000]`、C-1 加 forbidden points `[6200]`、I-1。
- automatic 顯示：`errors=["接頭 6000 距支撐過近"]`。
- manual 顯示：`summary="❌ 接頭落入禁止區"`，details 額外列出 joint 與禁止區範圍。
- 分類理由：兩邊都將同一 joint 判為 invalid，底層語意相同；單筆差異只在文字、欄位與 detail 格式。
- 處理：具名 code／facts 統一後，由兩個 projector 保留現有文字。

### A-03｜空白 material spec 的 assignment 識別格式

- 輸入：segments `[4000, 8000]`、joints `[4000]`、C-1 但 material spec 為空白、I-1。
- 共用核心結果：兩邊均使用同一 fallback purchasable lengths 與 Qty 99 stock items；assignments、components 與 `score=75000.0` exact equal。
- 格式特徵：stock id／group 使用既有 `UNLIMITED-4000`、`UNLIMITED-8000` 命名；這是 compatibility data，不是工程差異。
- 處理：保留既有命名。

## B 類差異

### B-01｜可配料的工程不合法 plan：evaluation sequence 不同

**具體輸入**

- segments：`[6000, 6000]`
- joints：`[6000]`
- config：C-1，forbidden points `[6200]`
- 庫存：I-1（W-6000 Qty 2）

**Automatic Solver 結果**

- `valid=False`
- `errors=["接頭 6000 距支撐過近"]`
- `assignments=[]`、`total_waste=None`、`ratio_penalty=None`
- 不提供 `buy_count`、`distinct_groups`、`length_variation`、`under_4000_segment_count`
- compatibility penalty `score=1050000`

**人工編輯結果**

- `valid=False`，`legality.violations=["接頭落入禁止區"]`
- 仍配置兩根 W-6000：`buy_count=0`、`distinct_groups=1`、`length_variation=0`、`under_4000=0`
- `ratio_penalty=100000.0`、`joint_count=1`、`score=106000.0`
- `errors=[]`

**來源位置**

- automatic：`bracing_optimizer/algorithms/wales.py:452` 在 legality invalid 時立即回傳；`:453` 建立 invalid penalty，allocation 位於 `:471` 之後而不會執行。
- manual：`bracing_optimizer/application/plan_editing.py:875` 先 allocation、`:901` 計分，直到 `:947` 之後才執行人工 legality projection。

**建議統一規則**

建議以 **manual 的核心 evaluation sequence** 為準：只要所有 segment 都可購買且 exact-length allocation 可成立，即使另有 joint clearance／min-max 等 legality issue，core 仍產生 allocation 與同一套 score components；`valid` 仍為 false，絕不放寬合法性。Automatic projector 繼續輸出既有 invalid-candidate penalty 與空 assignments，不把 core diagnostic local score 用於 GA 排序。

理由：這能讓同一 plan 的核心 facts 完整、保留人工編輯診斷價值，且不需在 manual projector 複製 score 公式。對 Solver 的既有候選 score／排序可由 automatic projector 保持；代價是 automatic invalid candidate 也會執行 allocation／components，因此必須由 Task 1.5／4.3 證明無明顯效能退化。

**若採用建議，改變的既有行為**

- automatic 對外 payload、penalty 與排序：不變。
- manual 對外 score／allocation：不變。
- automatic 的 internal core result：會多出 allocation 與 diagnostic components；執行成本可能增加，需效能 gate。

### B-02｜不可購買 segment：allocation failure components 不同

**具體輸入**

- segments：`[5000, 7000]`
- joints：`[5000]`
- config：C-1，無 forbidden point
- 庫存：I-1；可購買長度只有 `[4000, 6000, 8000]`

**Automatic Solver 結果**

- `valid=False`
- 兩筆 non-purchasable errors
- `assignments=[]`、`total_waste=None`、`ratio_penalty=None`
- 不提供 allocation components
- compatibility penalty `score=1100000`

**人工編輯結果**

- `valid=False`、`assignments=[]`、`total_waste=0`
- fallback 產生 `buy_count=2`、`distinct_groups=2`、`length_variation=2000`、`under_4000=0`
- `ratio_penalty=60000.0`、`joint_count=1`、`score=273000.0`
- `errors=["部分料長不在庫存可購買長度內，材料配置未完成。"]`

**來源位置**

- automatic：`bracing_optimizer/algorithms/wales.py:273` 先產生 purchasable-length errors，`:452` short-circuit。
- manual：`bracing_optimizer/application/plan_editing.py:875` allocation 回傳 `None` 後，在其後的 fallback branch 以 segment 數量與長度自行組 components，再於 `:901` 計分。

**建議統一規則**

建議以 **automatic 的 allocation 語意** 為準：任何 segment 不可購買時，core allocation 為 unavailable，不得把不可購買的 segment 計成 `buy_count`，也不產生虛構的 stock groups／variation／local score。這不是較寬鬆規則；plan 仍為 invalid，而且避免把「不可購買」錯記為「可採購」。

理由：`buy_count` 應只代表可購買長度的實際 fallback，manual 現行 `buy_count=len(segments)` 與 allocation truth 不一致。採 automatic 語意也避免把一套只服務 manual invalid payload 的 fallback score 公式帶入共用 evaluator。

**若採用建議，改變的既有行為**

- manual 的 non-purchasable invalid plan 不再顯示 `buy_count=2`、`distinct_groups=2`、`length_variation=2000`、`total_waste=0` 與 `score=273000.0`；建議這些 unavailable 欄位投影為 `None`。
- automatic 對外結果不變。
- 這是 manual 既有結果契約變更；確認後必須明寫進 proposal「不變事項」例外、Impact 與 spec Scenario。因為是 allocation／score pipeline 語意，需更新 `docs/SOLVER.md`，不需要改 `docs/DOMAIN.md` 的材料合法性規則。

### B-03｜多個 joint-clearance 違規：issue facts 數量不同

**具體輸入**

- segments：`[4000, 4000, 4000]`
- joints：`[4000, 8000]`
- config：C-1，forbidden points `[4200, 8200]`
- 庫存：I-1（W-4000 Qty 3）

**Automatic Solver 結果**

- `valid=False`
- errors 完整包含 `接頭 4000 距支撐過近`、`接頭 8000 距支撐過近`
- invalid penalty `score=1100000`

**人工編輯結果**

- `valid=False`
- `legality.violations` 只有一筆 `接頭落入禁止區`
- details 只包含 joint 4000 與禁止區 `3900 ~ 4500 mm`，joint 8000 的 facts 遺失
- manual score `167000.0`（同時受 B-01 影響）

**來源位置**

- automatic：`bracing_optimizer/algorithms/wales.py:286` 附近逐一走訪全部 joints 並 append error。
- manual：`bracing_optimizer/application/plan_editing.py:1007` 設定單一 `forbidden_joint`，找到第一筆後即 break。

**建議統一規則**

建議以 **automatic 的完整 issue coverage** 為準：core 對每個違規 joint 產生同一具名 code 加各自 facts，不因中文訊息相同而合併。Manual projector 仍只顯示現有第一筆 summary/details，以維持 UI 格式與順序。

理由：結構化 core 必須 lossless，否則 code／facts 無法可靠去重或診斷；完整收集不改變合法性，也不是較寬鬆規則。

**若採用建議，改變的既有行為**

- manual internal core issues 由一筆增加為兩筆；公開 `legality` 顯示不變。
- automatic 行為不變。
- 只需在 `docs/SOLVER.md` 記錄 runtime issue model；不改 `docs/DOMAIN.md`。

### B-04｜多個不可購買 segment：issue facts 數量不同

**具體輸入**

- segments：`[5000, 7000]`
- joints：`[5000]`
- config：C-1，無 forbidden point
- 庫存：I-1

**Automatic Solver 結果**

- errors 有兩筆：5000 與 7000 各一筆 non-purchasable issue。

**人工編輯結果**

- `legality.violations=["無此料長"]`
- details 只保留 `料長：5000 mm`，7000 的 facts 遺失。

**來源位置**

- automatic：`bracing_optimizer/algorithms/wales.py:294` 附近逐一走訪全部 segments。
- manual：`bracing_optimizer/application/plan_editing.py:1029` 使用 `next(...)`，只取第一個 missing length；`:1037` 再用中文 substring 排除 automatic 原始 errors。

**建議統一規則**

建議以 **automatic 的完整 issue coverage** 為準：每個不可購買 segment 形成同 code、不同 length／index facts 的 issue。Manual projector 仍維持現有第一筆 `無此料長` 顯示。

理由：這與具名 issue 的 `(code, normalized facts)` 契約一致，避免資料遺失，也移除中文 substring 分類依賴；不改 purchasable-length 合法性。

**若採用建議，改變的既有行為**

- manual internal core issues 會包含全部 offending segments；公開 summary/details 不變。
- automatic 行為不變。
- 只需更新 `docs/SOLVER.md` 的 issue pipeline，不改 `docs/DOMAIN.md`。

### B-05｜防禦性 total mismatch：issue 種類不同

**具體輸入**

- segments：`[6000]`
- joints：`[]`
- resolved config：required length 12000、resolved steel target 12000、其餘同 C-1
- 庫存：I-1
- automatic 的正常 GA decode 會保證 segments 加總為 target；為測試既有 defensive branch，此案例以 stub decoder 回傳上述 segments。

**Automatic Solver 結果**

- `valid=False`
- issue：`steel segment total does not match the resolved Waler steel length`
- `assignments=[]`、`ratio_penalty=None`、`score=1050000`

**人工編輯結果**

- `valid=False`
- issue／display 種類是 `尾端調整量不合法`，errors 為無法用一塊 adjustment 與 0..199 mm gap 完成
- 仍配置一根 W-6000，`ratio_penalty=100000.0`、`score=105000.0`

**來源位置**

- automatic：`bracing_optimizer/algorithms/wales.py:280` 附近直接比較 `sum(segments)` 與 `cfg.steel_target_length`。
- manual：`bracing_optimizer/application/plan_editing.py:845` 附近以 `resolve_tail_adjustment(required_length, steel_length=...)` 判斷 completion；`validate()` 又以 `total_length=current_length` 建 config，因此不會產生 resolved-target mismatch。

**建議統一規則**

建議以 **automatic 的 resolved steel target** 為核心 legality truth：core issue code 應是 total mismatch，facts 包含 expected target 12000 與 actual total 6000。Manual projector 可把這個 code 映射回既有 `尾端調整量不合法` summary/details；若另需保留 adjustment failure 診斷，應作為同 issue 的顯示 facts，不另創互斥合法性規則。

理由：resolved config 已明確提供 steel target，共用 evaluator 不應在 manual 路徑把 `total_length` 改寫成實際 segments 加總而掩蓋 mismatch。這維持較嚴格且已存在的 automatic hard constraint。

**若採用建議，改變的既有行為**

- manual internal issue kind 從 tail-completion-only 改為 resolved total mismatch；公開中文 summary/details 可由 projector 保持。
- score／allocation 行為同時依 B-01 的決策；automatic defensive payload 不變。
- 這是 evaluator 對既有 hard constraint 的統一，不新增或放寬工程門檻；需在 `docs/SOLVER.md` 說明 resolved context，`docs/DOMAIN.md` 不需改規則。

## 未發現差異的重點

- 合法方案 exact score 與全部 components：全庫存、需採購、under-4000、ratio、stock group、length variation、joint count 均已鎖定。
- `distance == clearance` 合法，`distance < clearance` 不合法。
- `segment == min`、`segment == max` 合法；低於 min、高於 max 不合法。
- material spec 有值時，兩條路徑使用相同 Qty；W-6000 Qty 1、segments `[6000, 6000]` 時兩邊均 `buy_count=1`、`score=211000.0`。
- material spec 空白時，兩條路徑使用相同 purchasable-length 與 unlimited stock fallback。
- 未觀察到合法方案的分數、component 型別或運算結果差異。

## 最終確認結果

以下正式決策已取代上方各 B 類章節中的早期建議：

1. B-01：任何 hard issue 都使 allocation／ratio／score components／local score unavailable；automatic 外部 invalid penalty 不變。
2. B-02：不可購買或 allocation unavailable 時，以 automatic 語意為準，不虛構 allocation components／local score；manual non-purchasable payload 改為 unavailable。
3. B-03／B-04：core 以 exhaustive issues 為準；manual projector 依固定順序顯示全部 joint-clearance 與 non-purchasable issues，summary 顯示違規總數。
4. B-05：Waler 不使用 adjustment block；鋼材總長合法閉區間為 `required_length - 200 <= steel_length <= required_length`，低於下界顯示「鋼材總長不足」，高於上界顯示「鋼材總長太長」。

上述規則已同步到 proposal／spec／design／tasks、`docs/DOMAIN.md` 與 `docs/SOLVER.md`，並完成實作、效能 gate 與回歸驗證。
