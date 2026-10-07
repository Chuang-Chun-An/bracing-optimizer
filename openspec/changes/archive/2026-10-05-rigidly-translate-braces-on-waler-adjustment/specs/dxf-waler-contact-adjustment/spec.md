# DXF Waler Contact Adjustment Specification

## Purpose

定義 DXF Review 修改圍令背填厚度或圍令寬度時，如何從兩端最終有限圍令幾何聯立重算一般斜撐接點，使斜撐只做剛體平移並保持原設計角度與長度，同時在無合法解時維持可診斷且無部分副作用的安全失敗。

## 閱讀導航

- **必讀**：「一般斜撐 SHALL 以共同平移維持原角度與長度」；定義本 change 的核心 Engineering Hard Constraint。
- **必讀**：「斜撐 SHALL 使用兩端最終圍令與同一 baseline 聯立重算」；定義單邊編輯仍移動兩端接點，以及重複編輯／replay 的順序無關性。
- **必讀**：「無唯一合法剛體解時 SHALL 原子失敗」；定義平行圍令、有限線段與 identity 失敗行為。
- **條件式閱讀**：「Preview、downstream geometry 與 Project projection SHALL 使用同一結果」；修改 preview、CandidatePoint、validation rebuild、Pause／Resume 或 Project conversion 時必讀。
- **可先跳過**：`brace-axis-waler-extension` 的 250 mm direct／600 mm extension 候選規則、Strut 與 CornerBrace 調整細節、Solver 與材料規格；本 capability 不修改這些行為。

## ADDED Requirements

### Requirement: 一般斜撐 SHALL 以共同平移維持原角度與長度

對已具有完整且不同 `FromWaler`／`ToWaler` identity 的一般 Brace，Waler 背填／寬度調整 SHALL 將該 Brace 視為剛體。若 baseline 兩端為 `A0`、`B0`，調整後兩端為 `A1`、`B1`，系統 MUST 使用同一有限平移向量 `t`，使 `A1 = A0 + t` 且 `B1 = B0 + t`。調整後差向量 `B1 - A1` MUST 在既有幾何 tolerance 內等價於 `B0 - A0`；系統 MUST NOT 固定另一端後只移動被編輯端、保留被編輯端舊 Waler station 而旋轉 Brace，或加長／縮短 Brace。

`A1` 與 `B1` MUST 分別落在兩端 identity 所指向的最終有限 Waler 接觸線上。即使只有一端 Waler 的採用尺寸改變，另一端接點仍 SHALL 依共同平移沿其最終 Waler 接觸線滑動。此 Requirement 是 DXF Engineering Hard Constraint，不是 Solver Preference 或 Temporary Solver Heuristic。

#### Scenario: 只有一端非平行圍令移動

- **WHEN** Brace 兩端連接兩支非平行有限 Waler，只有 `FromWaler` 的最終接觸線相對 baseline 移動，且存在唯一共同平移使兩端仍落在各自有限線段
- **THEN** 系統 SHALL 對 Brace 兩端套用同一平移向量
- **AND** `ToWaler` 端接點 SHALL 沿未移動的 `ToWaler` 滑動
- **AND** 調整後 Brace 角度與長度 MUST 與 baseline 等價

#### Scenario: 兩端圍令均有採用位移

- **WHEN** Brace 的 `FromWaler` 與 `ToWaler` 均具有相對 baseline 的最終位移，且兩條最終有限接觸線可形成唯一剛體平移解
- **THEN** 系統 SHALL 使用兩端最終接觸線共同求得一個平移向量
- **AND** MUST NOT 依最後被編輯的 Waler 單獨覆寫其中一端

#### Scenario: Brace 端點表示反轉

- **WHEN** 幾何等價的 Brace 以相反 start／end 表示，且 `FromWaler`／`ToWaler` identity 與端點一併等價反轉
- **THEN** 系統 SHALL 產生幾何等價的共同平移與兩端最終接點
- **AND** 結果 MUST NOT 依賴 start／end 或 Waler collection order

### Requirement: 斜撐 SHALL 使用兩端最終圍令與同一 baseline 聯立重算

系統 MUST 以本輪 canonical recognition、baseline-WCS manual endpoint replay 與正式 Waler connection 完成後，但任何背填／寬度人工調整尚未套用前的完整 formal Brace geometry 作為 adjustment baseline。Baseline 只可為兩端各自具有唯一且不同 Waler identity、且已通過既有完整 formal connection contract 的 Brace 建立；只具有 side-only／competing Waler evidence、identity 缺失／相同／ambiguous 或 provisional connection 的 Brace MUST NOT 建立 adjustment baseline。

人工 endpoint override MUST 以未套用 Waler adjustment 的絕對 WCS 保存。使用者在已調整的 Brace 上修改端點時，系統 MUST 先由該 Brace baseline 與目前兩端最終 Waler 求得目前共同平移 `t`，再保存「使用者點選 WCS − t」。每個換算後端點 MUST 落在其 identity 對應的 baseline Waler finite segment；任一端不合法時，系統 MUST 阻止此次人工修改、提示原因並保持整個 Review state 不變，且 MUST NOT clamp、吸附或保存不合法座標。

每次 recognition rebuild、preview、apply、重複編輯、same-source restore、Resume 或合法 replay MUST 固定依 `recognition → manual endpoint replay（baseline WCS）→ 建立 formal Brace baseline → 套用 Waler 尺寸 decisions` 的順序處理。系統 SHALL 從該 baseline Brace 及兩端目前採用尺寸所形成的最終 Waler 接觸線重新求解；MUST NOT 從上一次已平移的 Brace 增量累加、沿用只屬於單一 Waler 的舊 station、在 manual replay 前先套用 Waler 位移，或對同一尺寸 decision 重複套用位移。

Recognition rebuild、source exclusion／restore 或 manual endpoint replay 若改變 canonical Brace geometry 或任一端 Waler identity，系統 MUST 先依目前 active facts 建立新的 baseline，再重驗並 replay 可保留的尺寸決策；MUST NOT 把舊 source／identity 的 baseline 套用到新 geometry。

新保存的 Brace manual endpoint override SHALL 明確標記 baseline-WCS 語意，但 MUST NOT 因此提升 Project schema 或 DXF Review state version。舊 override 缺少該標記時，只有在目前沒有有效 Waler 位移、共同 `t` 為零的情況下才可安全視為 baseline WCS；若存在非零 Waler adjustment，系統 MUST 將舊人工 endpoint 標為需要重新確認並跳過該 geometry replay，不得猜測或反推舊演算法結果。可獨立安全重驗的 Waler 尺寸 decision SHALL 不因人工 endpoint 需重新確認而被重複套用或任意丟棄。

#### Scenario: 先改端點再調 Waler

- **WHEN** 使用者在 Waler adjustment 尚未套用前人工修改 formal Brace endpoint，且修改後兩端仍形成目前 Waler 上的合法 formal connection
- **THEN** 系統 SHALL 以人工修改後的 baseline-WCS geometry 建立新的 Brace adjustment baseline
- **AND** 後續 Waler 尺寸調整 SHALL 從該 baseline 對兩端套用共同平移
- **AND** 人工修改 MUST NOT 被 recognition 後的 baseline 建立或 dimension replay 覆蓋

#### Scenario: 先調 Waler 再改端點

- **WHEN** formal Brace 已由共同平移 `t` 顯示在調整後位置，且使用者在該畫面選取新的合法 endpoint
- **THEN** 系統 SHALL 將該 endpoint 以「點選 WCS − t」保存為 baseline WCS
- **AND** 依固定順序重新計算後，畫面上的該 endpoint MUST 在既有 tolerance 內等於使用者點選位置
- **AND** 同一 Waler displacement MUST 只套用一次

#### Scenario: 換算後端點不在 baseline Waler 有限線段

- **WHEN** 使用者在已調整畫面選取 endpoint，但「點選 WCS − t」不在對應 baseline Waler finite segment 上
- **THEN** 系統 MUST 阻止此次人工修改並提示端點未落在對應 baseline 有限線段
- **AND** endpoint、CandidatePoint、connection、confirmation、baseline、Waler dimension decision 與其他 Review state MUST 保持提交前狀態
- **AND** 系統 MUST NOT clamp、吸附或硬存該端點

#### Scenario: 人工端點、Waler 尺寸與 Resume replay 順序無關

- **WHEN** 相同的合法人工 endpoint 與相同 Waler 最終採用尺寸，分別經由「先改端點再改尺寸」、「先改尺寸再改端點」或 Resume／replay 取得
- **THEN** 各路徑 SHALL 產生幾何等價的 Brace endpoints、角度、長度與兩端 Waler stations
- **AND** 每條路徑 SHALL 以人工修改後的 baseline geometry 求解，Waler displacement 只套用一次

#### Scenario: 舊未標記人工端點的安全相容

- **WHEN** Resume／replay 讀到缺少 baseline-WCS 標記的舊 Brace manual endpoint override
- **THEN** 若目前共同平移為零，系統 SHALL 將該絕對 WCS 安全 replay 為 baseline geometry
- **AND** 若目前存在非零 Waler adjustment，該人工 geometry MUST 標為需要重新確認且不得 replay
- **AND** 系統 MUST NOT 升級 Project schema／Review state version，或為保存舊畫面位置而重複套用 Waler displacement

#### Scenario: 只有正式 Brace 建立 baseline

- **WHEN** Brace terminal 只有可供 Waler contact-face 判定的 side-only／competing evidence，或兩端 Waler identities 不是唯一且不同
- **THEN** 系統 MUST NOT 為該 Brace 建立 adjustment baseline
- **AND** side evidence MUST NOT 被升級為 formal terminal identity

#### Scenario: 同一 Waler 重複編輯

- **WHEN** 使用者對同一 Waler 連續輸入多組採用背填／寬度值
- **THEN** 每次 preview 與 apply SHALL 從同一 canonical baseline 及最新兩端最終 Waler 線重算
- **AND** 最終 Brace geometry MUST 等價於從 baseline 直接套用最後一組採用值

#### Scenario: 兩端 Waler 編輯順序相反

- **WHEN** 相同 baseline 與相同兩端最終採用尺寸分別以 `FromWaler -> ToWaler` 及 `ToWaler -> FromWaler` 順序套用
- **THEN** 兩條操作路徑 SHALL 產生幾何等價的 Brace endpoints、角度、長度與 Waler stations

#### Scenario: Source rebuild 改變正式連接

- **WHEN** source exclusion／restore 或 manual endpoint replay 使 Brace canonical geometry、source identity 或任一端 Waler identity 改變
- **THEN** 系統 SHALL 捨棄舊 adjustment baseline 並從目前正式結果重建
- **AND** 無法對目前 identities 安全重驗的舊尺寸決策 MUST NOT 靜默改寫新 Brace

### Requirement: 平行圍令 SHALL 只在位移約束相容時採用確定性共同平移

當 Brace 兩端最終 Waler 接觸線在既有平行 tolerance 內平行時，系統 MUST 先判斷兩端相對各自 baseline 的法向位移約束是否相容。若存在共同平移但沿 Waler 方向有無限多個解，系統 SHALL 採用滿足兩端約束的最小長度平移向量，等價地保持兩端 baseline longitudinal stations；系統 MUST NOT 依輸入順序任選沿線滑移量。

若平行兩端的位移約束不相容，例如只有其中一條平行 Waler 產生非零法向位移而另一條維持原線，則不存在同時保持 Brace 角度、長度與兩端接觸的解，系統 MUST 依「無唯一合法剛體解時 SHALL 原子失敗」處理。

#### Scenario: 兩條平行圍令具有相容共同位移

- **WHEN** Brace 兩端 Waler 平行，且兩端最終接觸線相對 baseline 的法向位移可由同一共同平移滿足
- **THEN** 系統 SHALL 採用唯一的最小長度共同平移
- **AND** 兩端 baseline longitudinal stations SHALL 在既有幾何 tolerance 內保持不變

#### Scenario: 只有一條平行圍令移動

- **WHEN** Brace 兩端 Waler 平行，只有一端具有非零且與另一端不相容的法向位移
- **THEN** 系統 MUST 判定沒有合法剛體平移解
- **AND** MUST NOT 旋轉、伸縮、脫離另一端 Waler 或吸附到任一 Waler 端點

### Requirement: 無唯一合法剛體解時 SHALL 原子失敗

共同平移只有在兩端 Waler identities 完整且不同、baseline Brace 非退化、兩端最終 Waler 接觸線有效、平移解唯一或符合相容平行規則，且兩個新接點均落在對應有限 Waler segment 內時才可採用。任一條件不成立時，系統 MUST 產生可定位 Brace 與原因的 blocking diagnostic，整次 Waler contact adjustment MUST 保留提交前的 Waler、Brace、Strut、CornerBrace、association、CandidatePoint、confirmation 與 Review state，不得部分套用成功構件。

失敗路徑 MUST NOT 回退到舊有「保留單端 station、旋轉並改變長度」行為，也不得以最近點、無限 Waler 延長線、Waler 端點 clamp、collection order 或浮點微差製造解。既有具名 geometry tolerances SHALL 用於平行、有限線段與等價判定；不得為了讓特定圖面通過而加入未命名門檻。

#### Scenario: 非平行最終線沒有合法有限交點

- **WHEN** 無限直線可形成共同平移解，但任一調整後 Brace endpoint 落在對應 Waler finite segment 之外
- **THEN** 系統 MUST 拒絕整次 adjustment 並保留提交前狀態
- **AND** MUST NOT 使用無限延長線結果或 clamp 至 Waler 端點

#### Scenario: Brace connection identity 不完整

- **WHEN** 受影響 Brace 缺少任一端 Waler identity、兩端指向同一 Waler，或任一端 identity 仍 ambiguous
- **THEN** 系統 MUST NOT 建立剛體平移結果
- **AND** SHALL 保留或產生對應的 blocking connection diagnostic

#### Scenario: 多支受影響構件中一支失敗

- **WHEN** 同一次 Waler adjustment 影響多支構件，其中至少一支 Brace 沒有合法剛體解
- **THEN** 整次 apply MUST 為零副作用
- **AND** 其他原本可求解的 Brace、Strut 或 CornerBrace MUST NOT 被部分提交

### Requirement: Preview、downstream geometry 與 Project projection SHALL 使用同一結果

Preview SHALL 顯示每支受影響 Brace 的共同平移、兩端 Waler station 變化，以及 baseline／proposed 角度與長度；合法剛體結果的角度與長度 SHALL 顯示為保持等價。Preview MUST 為 pure planning，不得修改 live Review state。

Apply 成功後，正式 Brace world／local endpoints、CandidatePoints、Beam／member contacts、connection diagnostics、Review projection 與 Project Brace row SHALL 使用同一組剛體平移後 endpoints。Project schema 與 Solver input 欄位 MUST NOT 因本 capability 新增第二組 Brace geometry。Pause／Resume 與 compatible recovery SHALL 只保存／replay 既有尺寸決策，並以目前 canonical baseline 重算，不得把 preview geometry 當成另一份正式 truth。

#### Scenario: Preview 顯示兩端滑移但不修改 state

- **WHEN** 使用者預覽一個合法 Waler contact adjustment
- **THEN** Preview SHALL 顯示 Brace 兩端舊／新 stations、共同平移及不變的角度與長度
- **AND** 關閉或取消 Preview MUST NOT 修改 live Waler、Brace 或 Review state

#### Scenario: Apply 後 downstream 使用剛體 endpoints

- **WHEN** 合法 adjustment 原子套用成功
- **THEN** CandidatePoint、connection validation、Preview 與 Project conversion SHALL 使用相同的調整後 Brace endpoints
- **AND** MUST NOT 同時保留單端旋轉結果或 baseline endpoints 作為第二份正式 geometry

#### Scenario: Strut 與 CornerBrace 行為不變

- **WHEN** 同一 Waler adjustment 同時影響 Strut、一般 Brace 與 CornerBrace
- **THEN** 一般 Brace SHALL 使用本 capability 的共同平移規則
- **AND** Strut 與 CornerBrace SHALL 分別沿用既有交點及固定長度規則

