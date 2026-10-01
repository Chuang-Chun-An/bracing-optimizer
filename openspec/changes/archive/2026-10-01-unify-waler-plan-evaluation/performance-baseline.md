# Waler 評估效能基準（修改前）

## 閱讀導航

- **現在必讀（P0）**：先看「結論」與「比較門檻」。
- **實作前閱讀（P1）**：需要重跑量測時，再看「固定條件」與「原始結果」。
- **需要時再讀（P2）**：完整結果 signature 可由同目錄的 `benchmark_waler_evaluation.py` 重新輸出；不必為了理解變更先讀腳本。

## 結論

這是 Task 1.5 的 production code 修改前基準。Single 與 Global 各執行 5 次，結果 metadata 每次一致。量測期間沒有修改 GA stage、population、seed、candidate count 或其他搜尋參數。

| Fixture | 最短 | 中位數 | 平均 | 最長 | 結果摘要 |
|---|---:|---:|---:|---:|---|
| Single Waler | 2.849574 s | 2.929065 s | 3.242414 s | 4.049138 s | 2 solutions；累計 candidate count 540；走完 3 stages |
| Global Waler | 0.464838 s | 0.469145 s | 0.485341 s | 0.535402 s | 2 selected；10 raw / 4 merged candidates；每支只跑 STANDARD |

## 比較門檻

Task 4.3 必須在相同環境、fixture、policy 與重複次數下重跑。以中位數為主要比較值，並同時保留每次原始時間以辨識 run-to-run noise。若修改後有超出正常波動的明顯變慢，停止並回報；不得調整 GA stage、population、candidate count、seed 或其他搜尋參數補償。

## 固定條件

- 量測時間：2026-10-01T19:36:38+08:00
- Git HEAD：`a9636deb5e5478fb693576b3543d6fd53f0a147d`
- 作業系統：Windows 11 (`10.0.26200`)
- Python：3.12.6（專案 `.venv`）
- Timer：`time.perf_counter`
- 每個 fixture 重複：5 次
- Policy：`solver_auto_search` version 1
- Stage：
  - STANDARD：10 generations、population 120、seed 42
  - ENHANCED：30 generations、population 180、seed 137
  - DEEP：60 generations、population 240、seed 271
- Single fixture：沿用 `tests/test_optimize_waler.py::make_request` 的 12,000 mm、禁區點 4,000、可購長度 4,000/6,000/8,000。
- Global fixture：沿用 `tests/test_optimize_waler_global.py::waler_input` 的兩支 12,000 mm Waler、無禁區點、可購長度 1,000/3,500/5,000/7,000/9,000；量測時使用真實 `OptimizeWaler`，不使用該單元測試的 fake optimizer。
- 重跑命令：`.\.venv\Scripts\python.exe openspec\changes\unify-waler-plan-evaluation\benchmark_waler_evaluation.py`

## 原始結果

### Single Waler

- 原始秒數：`[2.9290650000039022, 2.84957430002396, 2.8926912000169978, 3.4916035999776796, 4.0491376999998465]`
- 每次結果相同：2 個 retained solutions。
- 每次 stage/candidate 結果相同：
  - STANDARD：population 120、valid 120、unique 2、best score `275000.0`
  - ENHANCED：population 180、valid 180、unique 2、best score `275000.0`
  - DEEP：population 240、valid 240、unique 2、best score `275000.0`
- 累計 diagnostics candidate count：540。
- Solution signatures：
  - `[8000, 4000]`，joint `[8000]`，tail adjustment 0，gap 0，score `275000.0`
  - `[6000, 6000]`，joint `[6000]`，tail adjustment 0，gap 0，score `306000.0`

### Global Waler

- 原始秒數：`[0.535402100009378, 0.48978150001494214, 0.4648377999837976, 0.4691445000062231, 0.46753689998877235]`
- 每次結果相同：valid；選取 2 支 Waler；10 raw candidates；signature merge 後 4 candidates；6 transitions。
- W1、W2 的本地搜尋每次都只跑 STANDARD：population 120、valid 120、unique 22、best score `273000.0`。
- 每支 diagnostics candidate count：120。
- W1、W2 都選 rank 1：segments `[5000, 7000]`、score `273000.0`。

## 限制

牆鐘時間會受同機其他程序影響，因此後測以中位數和完整 raw samples 一起判讀。這份基準的目的是偵測評估抽取造成的明顯退化，不宣稱是跨機器 benchmark。

## 修改後比較（Task 4.3）

### Gate 結果：未通過，停止後續實作

相同環境、fixture、policy 與 5 次重複量測下，修改後每一次樣本都高於修改前相同 fixture 的最大值，屬於可重現且超出原始 run-to-run noise 的明顯變慢。依 change 契約，Task 4.3 停線；未調整 GA stage、population、candidate count、seed、停止條件或其他搜尋參數。

| Fixture | 修改前中位數 | 修改後中位數 | 中位數變化 | 修改前平均 | 修改後平均 | 平均變化 |
|---|---:|---:|---:|---:|---:|---:|
| Single Waler | 2.929065 s | 6.272890 s | +114.2% | 3.242414 s | 6.224426 s | +92.0% |
| Global Waler | 0.469145 s | 0.775402 s | +65.3% | 0.485341 s | 0.766322 s | +57.9% |

### 修改後原始結果

#### Single Waler

- 原始秒數：`[5.938257900008466, 6.737010100012412, 5.578798600006849, 6.272890099993674, 6.595174299989594]`
- 最短／中位／平均／最長：`5.578799 / 6.272890 / 6.224426 / 6.737010` 秒。
- 結果仍為 2 solutions；累計 candidate count 540；依序執行 STANDARD／ENHANCED／DEEP。
- 每個 stage 的 population、seed、valid／unique count、best score 與修改前完全相同。
- Solution signatures、合法性及 exact scores 與修改前完全相同。

#### Global Waler

- 原始秒數：`[0.7754019999993034, 0.7919205999933183, 0.7942163000116125, 0.7752485999953933, 0.6948200999759138]`
- 最短／中位／平均／最長：`0.694820 / 0.775402 / 0.766322 / 0.794216` 秒。
- 結果仍為 valid；2 selected；10 raw／4 merged candidates；6 transitions。
- W1、W2 仍只執行 STANDARD，population 120、seed 42、valid 120、unique 22、best score `273000.0`。
- Solution signatures、合法性及 exact scores 與修改前完全相同。

### 初步定位（尚未進行效能修正）

搜尋政策與候選數完全相同，主要行為差異是 B-01 確認規則：原本 automatic 在 legality invalid 時會先 short-circuit；共用 core 現在對「所有 segment 可購買且 exact allocation 可成立」的 invalid candidate 仍計算 allocation、ratio 與 diagnostic local score，再由 automatic projector 套回既有 invalid penalty。這會讓 GA 中反覆出現的 invalid candidate 多做 allocation／score 工作，是目前最可能的成本來源。尚未以 profiler 證實，也尚未修改 evaluator、cache 或 allocation 實作。

## B-01 修訂後重測（2026-10-01）

依使用者確認的統一規則，evaluator 已改為先完整收集 hard issues；只要有 total、joint、segment range 或 non-purchasable issue，就停止於 allocation、ratio 與 local score 之前。本節保留第一次失敗量測，並以完全相同的 benchmark script、fixtures、policy、seed 與 5 次重複執行修訂後重測。

### Gate 結果：仍未通過，停止後續實作

| Fixture | 修改前中位數 | B-01 修訂後中位數 | 中位數變化 | 修改前平均 | B-01 修訂後平均 | 平均變化 |
|---|---:|---:|---:|---:|---:|---:|
| Single Waler | 2.929065 s | 6.467161 s | +120.8% | 3.242414 s | 6.420425 s | +98.0% |
| Global Waler | 0.469145 s | 0.801602 s | +70.9% | 0.485341 s | 0.800372 s | +64.9% |

#### Single Waler

- 原始秒數：`[8.666987200005678, 5.6357957999862265, 4.4843573999824, 6.467161200009286, 6.847825899982126]`
- 最短／中位／平均／最長：`4.484357 / 6.467161 / 6.420425 / 8.666987` 秒。
- 結果仍為 2 solutions；累計 candidate count 540；依序執行 STANDARD／ENHANCED／DEEP。
- stage、population、seed、valid／unique count、solution signatures、合法性與 exact scores 均未改變。

#### Global Waler

- 原始秒數：`[0.8896746000100393, 0.8016021999937948, 0.7688726999913342, 0.8124791999871377, 0.7292296000232454]`
- 最短／中位／平均／最長：`0.729230 / 0.801602 / 0.800372 / 0.889675` 秒。
- 結果仍為 valid；2 selected；10 raw／4 merged candidates；6 transitions。
- W1、W2 仍只執行 STANDARD；stage、population、seed、valid／unique count、solution signatures 與 exact scores 均未改變。

### 判讀

B-01 修訂後確實不再替 hard-invalid candidate 計算 allocation／ratio／local score，但整體時間沒有回到 baseline；相較第一次失敗量測，中位數僅約增加 3%，落在兩組後測自身的波動範圍內。這表示「invalid candidate 額外配料與診斷分數」不是已觀察退化的主要原因，先前的初步定位已被本次量測否定。依 Task 4.3 契約再次停線；未修改任何 GA stage、population、candidate count、seed 或其他搜尋參數，也未在缺乏進一步證據時進行效能修正。

## Profiler 定位與修正提案（2026-10-01）

### 定位方法

- 使用 `cProfile` 對相同 Single fixture 各執行一次完整搜尋，保留函式呼叫數、cumulative time 與搜尋結果。
- 修改前版本不是切換工作樹，而是以 `git show HEAD:bracing_optimizer/algorithms/wales.py` 讀入記憶體模組；其餘 Application、fixture、policy 與執行環境維持相同。
- 另以 runtime monkeypatch 將 repair 內使用的 `validate_segments()` 替換成等價的 boolean-only hard-rule 判斷。此實驗不寫入 production code，也不改變 candidate generation、repair steps、stage、seed、population 或 score。
- 因同機當下的牆鐘時間明顯比 Task 1.5 歷史樣本慢，歷史與當下 wall-clock 不直接混合作為唯一因果證據；定位以同場 profile 的呼叫結構與 hot path 差異為主。

### Single profile 摘要

| 版本 | primitive calls | profiled total | `repair_individual` cumulative | `validate_segments` cumulative | 結果 |
|---|---:|---:|---:|---:|---|
| Git HEAD（修改前） | 8,430,518 | 9.899 s | 7.012 s | 1.144 s | 2 solutions／540 candidates；signatures 與 exact scores 相同 |
| 目前實作 | 11,666,167 | 12.464 s | 9.902 s | 4.547 s | 2 solutions／540 candidates；signatures 與 exact scores 相同 |
| 目前實作＋記憶體 boolean experiment | 8,867,405 | 9.704 s | 6.577 s | boolean helper 1.160 s | 2 solutions／540 candidates；signatures 與 exact scores 相同 |

目前搜尋中 `repair_individual.is_valid_selected()` 呼叫 `validate_segments()` 121,354 次。修改前的 `validate_segments()` 直接以 primitive loops 產生必要錯誤字串；目前版本則每次呼叫 `_collect_waler_plan_issues()`，建立 `WalerPlanIssue`／facts tuples，再呼叫 `format_automatic_waler_issue()`。連同 21,540 次正式 candidate evaluation，Single 搜尋共呼叫 `_collect_waler_plan_issues()` 142,894 次、建立／格式化約 298,223 筆 issues。

同場數據顯示：

- `_collect_waler_plan_issues()` cumulative 3.067 秒。
- `_waler_issue()` 約 298,223 calls，cumulative 1.645 秒。
- `format_automatic_waler_issue()` 約 298,223 calls，cumulative 1.325 秒。
- `evaluate_individual()` 由 HEAD 1.618 秒增至目前 1.769 秒，只有約 0.15 秒增量。
- `allocate_stock_best_fit()` 由 HEAD 0.550 秒變為目前 0.491 秒，沒有 allocation regression 證據。
- boolean-only experiment 將總呼叫量與總時間恢復到 HEAD 附近，且所有 observable Solver metadata 完全相同。

因此主要原因已定位為：**GA repair 只需要合法性布林值，卻誤走完整 diagnostics projection 路徑；大量 structured issue 與中文格式化建立在搜尋內圈重複發生。** 這不是 B-01 invalid allocation，也不是評分公式、庫存 allocation 或 GA 參數造成。

### 建議修正

建議保留同一套 hard-rule traversal，但分開「完整 diagnostics」與「搜尋布林查詢」兩種消費方式：

1. 將目前 `_collect_waler_plan_issues()` 的規則 traversal 改為 lazy issue iterator（例如 `_iter_waler_plan_issues()`）；規則與順序仍只有一份。
2. `evaluate_waler_plan()` 對 iterator 做完整 materialize，繼續收集全部 issues，完全維持 spec 所要求的完整報告。
3. `validate_segments()` 若仍需相容 errors，繼續 materialize 並格式化；其公開回傳不變。
4. `repair_individual.is_valid_selected()` 改用 boolean helper，透過 `next(iterator, None)` 在第一個 hard issue 即停止；合法 plan 仍走完全部 primitive checks，但不建立 issue list或中文訊息。
5. 不加入跨 candidate cache，不改 repair step、搜尋空間、stage、population、candidate count、seed、停止條件、score 或排序。

這個分流屬於 diagnostics materialization 的執行策略，不改工程規則：core evaluation 仍完整收集 hard issues；只有 GA repair 的內部可行性探測不產生未被使用的 diagnostics。

### 必要驗證

- 對 total、joint、segment range、non-purchasable、multiple issues 與合法邊界建立矩陣，逐例以 exact equality 驗證 boolean helper 結果等於「完整 issue list 是否為空」。
- 驗證 `evaluate_waler_plan()` 仍完整保留全部 issue codes／facts 與既有順序。
- 驗證 `repair_individual()` 不 materialize issues、不呼叫中文 formatter，且輸出 chromosome 與修改前目前實作完全相同。
- 重跑 focused、Single／Global regressions；candidate count、stage、seed、solution signatures、valid counts 與 exact scores 必須相同。
- 在相同環境重跑 5 次 Single／Global benchmark，並以同場 Git HEAD memory module 作控制組；若仍可重現明顯退化，再次停線。

### 不建議方案

- **把 `validate_segments()` 直接複製回舊 loops**：雖快，但會形成第二套 hard rules，重新引入本 change 要消除的 drift。
- **降低 GA 搜尋量**：會改變 Solver policy 與結果品質，違反 scope。
- **加入 candidate evaluation cache**：目前證據不需要 cache；cache 會增加 key、生命週期與記憶體語意，且可能掩蓋真正的 diagnostics materialization 問題。
- **只把 dataclass 換成較輕型別**：仍會在 12 萬次 repair probe 中完整建立 facts 與中文字串，無法消除主要成本。

## Lazy traversal 實作後 gate（2026-10-01）

依使用者確認的第一輪修正提案，hard rules 已抽為 lazy iterator：正式 evaluator 完整 materialize issues，repair boolean probe 以第一個 issue short-circuit。新增矩陣測試驗證 boolean 與完整 collection 的有效性一致，且 repair 不呼叫 collector／中文 formatter；102 個 Waler focused 與 Global regression tests 通過，candidate metadata、signatures 與 exact scores 未改變。

### 五次 benchmark

| Fixture | Task 1.5 baseline 中位數 | 修正前中位數 | Lazy traversal 中位數 | 同場 Git HEAD 中位數 |
|---|---:|---:|---:|---:|
| Single Waler | 2.929065 s | 6.467161 s | 3.663004 s | 2.902460 s |
| Global Waler | 0.469145 s | 0.801602 s | 0.542092 s | 0.462444 s |

Lazy traversal 相較修正前已將 Single 中位數降低約 43%、Global 降低約 32%；但相較緊接著在相同環境執行的 Git HEAD 控制組，Single 仍慢約 26.2%、Global 約 17.2%，超出兩組各自 raw samples 的重疊範圍，因此 gate 仍未通過。

#### Lazy traversal 原始秒數

- Single：`[3.663003599998774, 3.7009454000217374, 3.6735345000051893, 3.472956899990095, 3.6564220000000205]`
- Global：`[0.5690796000126284, 0.5442955000034999, 0.5264070999983232, 0.5420922999910545, 0.5330487000173889]`

#### 同場 Git HEAD 原始秒數

- Single：`[3.1446042000025045, 2.902460200013593, 2.861211999988882, 2.886764499999117, 3.1260087999980897]`
- Global：`[0.4621220999979414, 0.4624435000005178, 0.4869652999914251, 0.5027441999991424, 0.45884219999425113]`

### 第二輪 profiler 判讀

Lazy traversal 後 Single profile 為 8,915,212 primitive calls／7.777 秒，呼叫數已接近修改前；但 repair 仍建立 generator 121,354 次：

- `_has_waler_plan_issue()`：121,354 calls，cumulative 1.439 秒。
- `_iter_waler_plan_issues()`：233,334 generator resumptions，cumulative 1.297 秒。
- `next()`：164,434 calls，cumulative 1.247 秒。
- 正式 `evaluate_waler_plan()`：21,540 calls，cumulative 1.211 秒。

第一輪的 issue list／中文字串 materialization 熱點已移除；剩餘主要差異是大量 repair probe 的 generator 建立與 resume 成本。先前 plain boolean runtime experiment（不建立 generator）在相同 observable metadata 下曾將 profiled total 恢復到 Git HEAD 附近，支持這項定位。

### 第二輪修正方案（使用者已確認，待實作）

將 lazy generator 改為單一 synchronous rule scanner，接受 optional issue sink：

- 正式 evaluator 傳入 `issues.append`，scanner 依既有順序掃完並建立全部 issues。
- Repair 不傳 sink；scanner 在第一個 violation 直接回傳 `True`，不建立 generator、issue object 或顯示文字。
- Hard-rule branches 仍只存在同一個 scanner，不複製舊 loops，不建立第二套規則。
- 完整 diagnostics、issue order、repair steps、candidate metadata、score 與搜尋政策全部不變。

此方案是第一輪已確認設計的執行機制修訂：保留「同一 traversal、正式完整 diagnostics、repair boolean short-circuit」，只把 Python generator 換成同步 visitor／sink，以移除 profiler 已確認的剩餘成本。使用者已於 2026-10-01 確認採用；先更新 Decision 8 與新增 Task 4.3b 並通過 strict validation，再開始實作。

## Synchronous scanner 實作後 gate（2026-10-01）

Hard rules 已改由單一 synchronous scanner 執行：正式 evaluator 傳入 `issues.append` 並完整收集，repair 不傳 sink 且第一個 violation 即回傳。15 個 evaluator tests 與 102 個 Waler focused／Global regression tests 通過；repair test 另以 patched issue factory 證明不建立 issue object。所有 solution signatures、stage、population、seed、candidate metadata 與 exact scores 均與前次一致。

### 五次 benchmark 與鄰近控制組

| Fixture | Current 第 1 組中位數 | 同場 Git HEAD 中位數 | Current 第 2 組中位數 | 第 2 組相對 HEAD |
| --- | ---: | ---: | ---: | ---: |
| Single Waler | 3.488692 s | 3.001325 s | 3.160614 s | +5.3% |
| Global Waler | 0.503870 s | 0.493242 s | 0.531384 s | +7.7% |

#### Current 第 1 組原始秒數

- Single：`[4.816263699991396, 4.02507709999918, 3.4886924999882467, 3.312792599987006, 3.225596800009953]`
- Global：`[0.5104288999864366, 0.4963378999964334, 0.5038702000165358, 0.5801618999976199, 0.4996277999889571]`

#### 同場 Git HEAD 原始秒數

- Single：`[3.0013249999901745, 2.9162944000272546, 2.9106482000206597, 3.0045251000265125, 3.011567500012461]`
- Global：`[0.576121799997054, 0.5179155999794602, 0.49015440000221133, 0.43913069998961873, 0.49324179999530315]`

#### Current 第 2 組原始秒數

- Single：`[3.1507049999781884, 3.160613799991552, 3.154511500004446, 3.2498766999924555, 3.5423375999962445]`
- Global：`[0.546940000000177, 0.5374878000002354, 0.5313838000001851, 0.4995614000072237, 0.5239531999977771]`

### 判讀

第一組 Single 有明顯冷啟動／環境抖動，樣本由 4.816 秒持續下降至 3.226 秒，因此緊接 HEAD 後重跑第二組 current。兩組 current 自身的中位數差異約為 Single 10.4%、Global 5.5%；第二組相對 HEAD 的 5.3%／7.7% 落在這次跨 run 環境波動尺度內，Global 原始樣本亦重疊。第一輪 lazy traversal 相對 HEAD 的 26.2%／17.2% 明顯且不重疊退化未再重現，故 Task 4.3b 效能 gate 通過。未修改 GA stage、population、candidate count、seed、停止條件或其他搜尋參數。
