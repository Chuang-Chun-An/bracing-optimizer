# `bracing_optimizer.algorithms.wales` 函式與架構說明

本文件以函式為最小單位，說明 `wales.py` 目前的資料結構、接頭位置型遺傳演算法、材料配置、修補流程與診斷工具。

更新日期：2026-07-30

## 1. 核心概念

`wales.py` 使用的是「接頭位置型 GA」，不是段長型 GA。

```text
candidate_joint_points
↓
individual（0/1）
↓
decode_individual()
↓
joints
↓
segments
↓
validate_segments()
↓
allocate_stock_best_fit()
↓
evaluate_individual()
↓
score
↓
selection / crossover / mutation / repair
↓
下一代
```

每一個 gene 對應一個候選接頭位置：

```text
0：不選擇該接頭
1：選擇該接頭
```

例如：

```python
candidate_joint_points = [4000, 6000, 8000]
individual = [1, 0, 1]
total_length = 12000
```

解碼結果：

```text
選用接頭：4000、8000
完整節點：0、4000、8000、12000
分段長度：4000、4000、4000
```

起點 `0` 與終點 `total_length` 是固定端點，不會放進染色體。

## 2. 建議閱讀順序

第一次閱讀時，建議依序理解：

1. `Config`
2. `generate_candidate_joint_points()`
3. `decode_individual()`
4. `validate_segments()`
5. `allocate_stock_best_fit()`
6. `evaluate_individual()`
7. `is_joint_path_feasible()`
8. `find_valid_joint_sequence()`
9. `repair_individual()`
10. `_run_generations()`
11. `evolve()`

舊版獨立 GUI 與診斷函式可以最後再看。

## 3. 全域狀態與輸出

### `debug_print(*args)`

用途：輸出詳細除錯訊息。

只有以下設定開啟時才會真正輸出：

```python
DEBUG = True
```

預設：

```python
DEBUG = False
```

因此 DFS、repair、individual 建立等大量細節不會進入正式 GUI。

### `set_logger(func)`

用途：指定正式進度訊息的接收函式。

`main.py` 執行 Solver 前會把 GUI logger 傳入：

```python
wales.set_logger(gui_logger)
```

之後 `wales.py` 使用：

```python
logger("第 1 代...")
```

訊息就會進入 GUI，而不是直接印到終端機。

### 效能 counters

全域變數：

```python
evaluate_count
evaluate_total_time
allocate_call_count
allocate_total_time
```

用途：

- 統計評估次數與時間
- 統計材料配置次數與時間
- Solver 結束後計算平均耗時

每次 `evolve()` 開始時都會歸零。

## 4. 設定與候選接頭

### `generate_candidate_joint_points(total_length, min_piece_length, step=500)`

用途：依固定間距產生染色體對應的候選接頭位置。

輸入：

- `total_length`：圍令總長度
- `min_piece_length`：硬性最小段長
- `step`：候選接頭間距

輸出：整數位置清單。

候選範圍：

```text
min_piece_length
到
total_length - min_piece_length
```

如果：

```text
total_length < 2 × min_piece_length
```

表示連一個中間接頭都無法合理放置，函式會回傳空清單。

### `Config`

`Config` 是圍令 Solver 的集中設定物件。

#### 幾何欄位

```python
total_length
support_points
candidate_joint_points
```

#### 段長與材料欄位

```python
min_piece_length
preferred_min_piece_length
max_piece_length
joint_clearance_to_support
candidate_joint_step
purchasable_lengths
```

`min_piece_length` 是硬限制；`preferred_min_piece_length` 是偏好值，主要用於 repair 與評分方向。

#### 短中長分類

```python
short_segment_min
short_segment_max
mid_segment_min
mid_segment_max
long_segment_min
long_segment_max
```

#### 比例目標

```python
short_segment_ratio_target
mid_segment_ratio_target
long_segment_ratio_target
ratio_penalty_weight
```

#### GA 參數

```python
population_size
generations
crossover_rate
mutation_rate
elite_size
tournament_k
top_n
```

### `Config.__post_init__()`

建立 `Config` 後自動執行。

如果沒有傳入 `candidate_joint_points`，就呼叫：

```python
generate_candidate_joint_points()
```

如果沒有傳入 `purchasable_lengths`，就依最小段長、最大段長與候選間距產生預設材料長度清單。

正式 `main.py` 會明確傳入 Inventory 表內的所有有效 `Length`，因此正式執行通常不依賴這個預設清單。

## 5. GUI 邊界

正式實作位於 `bracing_optimizer.algorithms.wales`，不包含 Tkinter、輸入視窗或
獨立執行流程。GUI 輸入由 `bracing_optimizer.presentation` 負責，再透過
`bracing_optimizer.application.optimize_waler` 呼叫演算法。

## 6. 接頭、段長與庫存工具

### `classify_length(length, cfg)`

把段長分為：

```text
short：4000 <= length < 6000
mid：  6000 <= length <= 8000
long： 8000 < length <= 10000
out：  其他
```

實際範圍由 `Config` 欄位控制。

邊界注意事項：

- `6000` 屬於中段
- `8000` 仍屬於中段
- 大於 `8000` 才進入長段

### `is_joint_allowed(point, cfg)`

用途：檢查中間接頭是否距離支撐／禁止點太近。

禁止條件：

```python
abs(point - support) < cfg.joint_clearance_to_support
```

例如安全距離為 `300`：

```text
距離 299：禁止
距離 300：允許
```

起點 `0` 與終點 `total_length` 不使用這個函式判斷；只有中間候選接頭需要檢查。

### `expand_stock_items(stock_items)`

把材料數量展開成「一支材料一筆資料」。

輸入：

```python
[
    {"id": "A9500", "length": 9500, "qty": 2}
]
```

輸出：

```python
[
    {
        "stock_id": "A9500#1",
        "stock_group": "A9500",
        "stock_length": 9500,
    },
    {
        "stock_id": "A9500#2",
        "stock_group": "A9500",
        "stock_length": 9500,
    },
]
```

材料配置時會使用 `used` 清單，確保同一支庫存不會被重複使用。

## 7. 染色體與分段

### `decode_individual(individual, cfg)`

這是接頭型 GA 的核心解碼函式。

輸入：

- 0/1 染色體
- `Config`

輸出：

```python
(selected_joints, segments)
```

流程：

1. 將 gene 與 `candidate_joint_points` 一一配對。
2. 取出 gene 等於 `1` 的位置。
3. 對接頭排序並去重。
4. 在前後加入 `0` 與 `total_length`。
5. 相鄰位置相減，得到段長。

此函式只做轉換，不負責判斷是否合法。

### `validate_segments(joints, segments, cfg)`

用途：執行所有基本硬限制。

檢查項目：

1. 每個中間接頭必須通過 `is_joint_allowed()`。
2. 每段不得小於 `min_piece_length`。
3. 每段不得大於 `max_piece_length`。
4. 每段必須存在於 `purchasable_lengths`。

第四項代表目前材料不可裁切：

```text
需要 9200
可購買清單沒有 9200
→ 不合法
```

即使存在更長的 `9500`，也不能把它裁成 `9200`。

輸出：

```python
(valid, errors)
```

例如：

```python
(
    False,
    [
        "接頭 5000 距支撐過近",
        "段長 3200 不在可用材料長度清單中",
    ],
)
```

## 8. 短中長比例

### `segment_ratio_summary(segments, cfg)`

逐段呼叫 `classify_length()`，計算：

- 短段數
- 中段數
- 長段數
- 三類各自比例

回傳：

```python
(bucket_count, bucket_ratio)
```

分類為 `out` 的段不會放入三個 bucket，也不會計入比例分母。

### `calculate_ratio_penalty(segments, cfg)`

比較實際比例與目標比例。

公式：

```text
比例懲罰 =
(
  |實際短段比例 - 目標短段比例|
+ |實際中段比例 - 目標中段比例|
+ |實際長段比例 - 目標長段比例|
)
× ratio_penalty_weight
```

差距越大，分數越高。

## 9. 材料配置

### `allocate_stock_best_fit(segments, stock_items, purchasable_lengths)`

用途：替每一段選擇庫存料或購買料。

目前實際流程：

1. 呼叫 `expand_stock_items()` 展開庫存。
2. 將 segments 由長到短處理。
3. 尋找尚未使用且長度完全相同的庫存。
4. 有相同庫存就優先使用。
5. 沒有庫存，但段長在可購買清單中，就建立購買料。
6. 段長不可購買時回傳 `None`。

購買料 ID 例如：

```text
BUY-9500#1
```

目前判斷庫存的實際條件是：

```python
stock["stock_length"] == segment_length
```

雖然函式名稱是 `best_fit`，舊註解提到材料長度可大於段長，但目前工程規則不允許裁切，因此實作採完全等長配置。

回傳內容：

```python
{
    "assignments": ...,
    "total_waste": ...,
    "total_bought": ...,
    "distinct_groups": ...,
    "length_variation": ...,
    "under_4000_segment_count": ...,
}
```

在完全等長配置下，合法 assignment 的 `waste` 通常為 `0`。

## 10. 個體評分

### `evaluate_individual(individual, cfg, stock_items)`

這是 GA 的評分中心。

```text
decode_individual()
↓
validate_segments()
↓
allocate_stock_best_fit()
↓
calculate_ratio_penalty()
↓
計算 score
```

分數越低越好。

### 幾何或材料長度無效

```text
score = 1,000,000 + 錯誤數 × 50,000
```

### 無法配料

```text
score = 800,000 + 接頭數 × 1,000
```

### 有效方案

目前公式：

```text
score =
  購買數 × 100,000
+ 比例懲罰
+ 小於 4000 的段數 × 100,000
+ 材料種類數 × 5,000
+ 最大與最小料長差
+ 接頭數 × 1,000
```

主要方向：

1. 優先減少購買。
2. 避免小於 4000 的段。
3. 接近短中長目標比例。
4. 減少材料種類。
5. 減少料長差異。
6. 減少接頭。

輸出是一個完整結果 dict，包含：

```text
individual
joints
segments
valid
errors
assignments
buy_count
distinct_groups
length_variation
under_4000_segment_count
segment_ratios
ratio_penalty
joint_count
score
```

此函式也會更新評估次數與時間 counters。

## 11. 個體修補

### `repair_individual(individual, cfg, max_iters=80)`

用途：修補 crossover 或 mutation 產生的不合法染色體。

先將染色體轉為接頭清單：

```python
selected = [
    point
    for gene, point in zip(individual, cfg.candidate_joint_points)
    if gene == 1
]
```

### 內部 `to_individual(selected_joints)`

將接頭清單轉回與 `candidate_joint_points` 等長的 0/1 染色體。

### 內部 `get_points(selected_joints)`

加入固定端點：

```python
[0] + selected_joints + [total_length]
```

### 內部 `get_segments(selected_joints)`

將相鄰節點相減，產生段長。

### 內部 `is_valid_selected(selected_joints)`

把接頭轉成染色體，再呼叫：

```text
decode_individual()
validate_segments()
```

確認整體是否合法。

### 內部 `count_preferred_short(selected_joints)`

計算小於 `preferred_min_piece_length` 的段數。

預設偏好最小段長為 `4000`。這是偏好，不是硬限制。

### 內部 `remove_invalid_support_joints(selected_joints)`

移除所有無法通過 `is_joint_allowed()` 的接頭。

### 內部 `try_remove_joint(selected_joints, joint_to_remove)`

嘗試刪除指定接頭。

刪除後整體仍合法才回傳新接頭清單，否則回傳 `None`。

目前 repair 主流程沒有實際呼叫這個 helper。

### 內部 `fix_hard_short_once(selected_joints)`

尋找第一個：

```text
segment < min_piece_length
```

嘗試：

- 刪除短段右側接頭
- 刪除短段左側接頭
- 將短段與相鄰段合併

如果有多個可行方案，選擇合併後最接近 `preferred_min_piece_length` 的方案。

每次只修正一個短段，然後回到 repair 主迴圈重新檢查。

### 內部 `fix_hard_long_once(selected_joints)`

尋找第一個：

```text
segment > max_piece_length
```

在長段內尋找可新增的合法候選接頭，將它拆成兩段。

候選排序優先級：

1. 拆分後偏好短段數較少。
2. 接頭越接近長段中點越好。

### 內部 `improve_preferred_short_once(selected_joints)`

處理：

```text
min_piece_length <= segment < preferred_min_piece_length
```

這些段符合硬限制，但不是偏好的長度。

函式會嘗試刪除左右相鄰接頭進行合併；只有偏好短段總數真正下降才接受。

### 內部 `simplify_joints_once(selected_joints)`

當方案已合法，而且沒有偏好短段時，嘗試刪除一個不必要接頭。

接受條件：

- 刪除後整體仍合法
- 不增加偏好短段數

### repair 主流程

```text
移除 forbidden/support joint
↓
修硬性短段
↓
修硬性長段
↓
改善偏好短段
↓
簡化接頭
↓
重新驗證
```

最多迴圈 `max_iters` 次。

最後若合法：

```python
return to_individual(selected)
```

最後仍不合法：

```python
return build_valid_individual(cfg)
```

也就是放棄局部修補，重新搜尋合法個體。

### repair 目前的限制

目前沒有專門處理：

> segment 已在 min/max 內，但不在 `purchasable_lengths`。

這種情況會使 `is_valid_selected()` 失敗；局部操作無法解決時，最後會 fallback 到 `build_valid_individual()`。

## 12. 合法路徑搜尋

### `is_joint_path_feasible(cfg)`

用途：快速判斷是否存在至少一條合法分段路徑。

建立的節點：

```text
[0] + 合法候選接頭 + [total_length]
```

中間候選接頭先經過：

```python
is_joint_allowed()
```

兩個節點之間只有符合以下條件才可連線：

- 段長不小於 `min_piece_length`
- 段長不大於 `max_piece_length`
- 段長存在於 `purchasable_lengths`

函式使用 stack 搜尋終點是否可達。

只回傳：

```python
True
False
```

不回傳實際接頭位置。

### `find_valid_joint_sequence(cfg, randomize=False)`

用途：真正找出一條從 `0` 到 `total_length` 的合法接頭路徑。

流程：

1. 排除 forbidden/support 候選接頭。
2. 建立 nodes。
3. 建立合法鄰接表。
4. 以 DFS 搜尋終點。
5. 使用 memo 避免重複搜尋。
6. 移除固定起點與終點。
7. 回傳中間接頭位置。

### 內部 `dfs(idx)`

輸入：目前節點 index。

成功時回傳：

```python
[目前節點, ..., total_length]
```

失敗時回傳：

```python
None
```

`memo` 會記住某個 index 能否到達終點。

當：

```python
randomize=True
```

會打亂下一個節點的嘗試順序，使不同初始個體可能取得不同合法路徑。所有路徑仍然符合硬限制。

## 13. 初始族群

### `build_valid_individual(cfg, max_attempts=100)`

用途：建立一條合法的 0/1 染色體。

流程：

1. 呼叫 `is_joint_path_feasible()`。
2. 完全不可行時提前回傳全 0 染色體。
3. 呼叫 `find_valid_joint_sequence(randomize=True)`。
4. 將接頭清單轉成染色體。
5. 隨機搜尋失敗時，以 `randomize=False` 再做 deterministic fallback。

### `create_individual(cfg)`

建立單一初始個體：

```text
build_valid_individual()
↓
repair_individual()
```

路徑搜尋本來就應該產生合法方案，repair 在這裡是額外保險與簡化。

### `initial_population(cfg)`

重複呼叫：

```python
create_individual(cfg)
```

直到數量等於：

```python
cfg.population_size
```

完成後用正式 `logger()` 輸出族群數量與耗時。

## 14. 遺傳演算法操作

### `tournament_selection(population, evaluated, k)`

從 population 隨機抽出 `k` 個 index。

利用與 population index 對齊的 `evaluated` 找到最低分個體，再複製該染色體作為父代。

重要條件：

```text
population[i]
```

必須和：

```text
evaluated[i]
```

保持對齊。

### `crossover(parent1, parent2, rate)`

使用單點交配。

例如：

```text
parent1：AAA|BBB
parent2：CCC|DDD

child1：AAA|DDD
child2：CCC|BBB
```

以下情況不交配：

- 隨機值沒有通過 `rate`
- 染色體長度小於等於 1

不交配時仍會回傳父代的複本，不直接修改父代。

### `mutate(individual, rate)`

逐一檢查每個 gene。

通過突變率時進行 bit flip：

```text
0 → 1
1 → 0
```

突變後可能產生：

- forbidden joint
- 過短段
- 過長段
- 不可購買段長

因此後續必須呼叫 `repair_individual()`。

### `_reset_performance_counters()`

將四個效能統計值重設為零。

每次 `evolve()` 都會重新統計，不會累積上一次執行結果。

### `_run_generations(...)`

這是每一代演化的主迴圈。

每代流程：

```text
依 score 排序
↓
保留 elite
↓
tournament 選父代
↓
crossover
↓
mutate
↓
repair
↓
建立新 population
↓
評估新 population
↓
輸出本代最佳方案
```

兩份評估資料用途：

#### `evaluated_for_population`

保持與 population index 對齊，供 tournament selection 使用。

#### `sorted_evaluated`

依 score 排序，用於取得 elite。

初始 population 先評估一次，之後每一代的新 population 再評估一次。

總評估次數約為：

```text
population_size × (generations + 1)
```

同一代的新 population 不會被重複評估兩到三次。

### `_log_performance_statistics()`

輸出：

- evaluate 次數
- evaluate 總耗時
- evaluate 平均耗時
- allocate 次數
- allocate 總耗時
- allocate 平均耗時

呼叫次數為零時，平均值使用 `0.0`，避免除以零。

### `_top_results(final_evaluated, cfg)`

整理最終結果。

流程：

1. 如果存在有效方案，只保留有效方案。
2. 依 `segments` 去重。
3. 相同 segments 保留較低分方案。
4. 依 score 由低到高排序。
5. 取前 `cfg.top_n`。

去重 key：

```python
tuple(item["segments"])
```

因此段長順序不同會被視為不同方案。

### `evolve(cfg, stock_items, seed=42)`

正式 Solver 的主要入口。

流程：

```text
_reset_performance_counters()
↓
random.seed(seed)
↓
initial_population()
↓
_run_generations()
↓
_log_performance_statistics()
↓
_top_results()
```

固定 `seed` 可以讓相同輸入較容易重現相同結果。

目前 `main.py` 執行圍令 Solver 時，主要就是：

1. 建立 `Config`
2. 建立 `stock_items`
3. 設定 GUI logger
4. 呼叫 `evolve()`

## 15. 診斷工具

### `build_neighbors(cfg)`

建立診斷用節點與鄰接表。

它會檢查：

- min/max 段長
- purchasable lengths

但目前不會先排除 forbidden/support 候選點。

因此這個函式描述的是「材料長度形成的搜尋空間」，不等同正式 `find_valid_joint_sequence()` 的完整合法圖。

### `diagnose_search_space(cfg, stock_items, sample_population_size=120)`

輸出搜尋空間與族群診斷：

- 候選接頭總數
- 合法候選接頭比例
- 平均、最大、最小分支數
- 死路節點數
- repair 前後有效率
- 初始族群有效率
- 分段多樣性
- 最佳、平均、最差分數
- 接頭數統計
- 前十名不同分段

這是命令列診斷工具，正式 `main.py` 不會呼叫。

### `print_results(results)`

將結果輸出到終端機：

- 是否有效
- 分段長度
- 接頭位置
- 接頭數
- 購買數
- 短中長比例
- 比例懲罰
- 綜合分數
- 材料配置

正式 GUI 有自己的結果顯示方式，不使用這個函式。

## 16. 模組執行方式

`bracing_optimizer.algorithms.wales` 是由 Application Use Case 呼叫的演算法模組，
不再提供獨立 GUI 或直接執行入口。正式程式由根目錄 `main.py` 啟動。

## 17. 正式 GUI 呼叫流程

目前主程式的大致流程：

```text
main.py
↓
讀取圍令幾何與 forbidden points
↓
讀取 Inventory
↓
purchasable_lengths = 所有有效 Length
↓
stock_items = Qty > 0
↓
建立 wales.Config
↓
wales.set_logger(gui_logger)
↓
wales.evolve(cfg, stock_items)
↓
取得 Top N
↓
加入 main.py 結果模型與預覽
```

## 18. 最重要的硬限制與偏好

### 硬限制

- forbidden/support point 不得設接頭
- 段長不得小於 `min_piece_length`
- 段長不得大於 `max_piece_length`
- 段長必須存在於 `purchasable_lengths`
- 材料不可裁切

違反硬限制的方案會被判定為 invalid。

### 軟性偏好

- 優先使用現有庫存
- 減少購買數量
- 避免小於 4000 的段
- 接近短中長目標比例
- 減少材料種類
- 減少料長變化
- 減少接頭數

軟性偏好不會直接使方案 invalid，而是透過 score 排序。

## 19. 建議深入研究的五個函式

如果要逐行閱讀，建議依序從以下函式開始：

1. `decode_individual()`：染色體如何變成接頭與段長
2. `validate_segments()`：合法方案的定義
3. `evaluate_individual()`：方案如何被評分
4. `find_valid_joint_sequence()`：合法初始方案如何產生
5. `_run_generations()`：GA 如何產生下一代

理解這五個函式後，再深入 `repair_individual()`，會比較容易掌握其中的局部修補邏輯。
