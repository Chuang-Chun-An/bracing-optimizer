# Spec Delta

## Purpose

定義正式 DXF 角撐在具有可靠中心軸證據時，如何沿用既有 Waler／Strut 選擇，將工程端點延伸至圍令內線與支撐中心線，而不在本 change 重新處理構件候選模糊問題。

## ADDED Requirements

### Requirement: 角撐工程端點校正以可靠中心軸證據為前提

系統 SHALL 只對已辨識為正式 `corner_brace`、且來源幾何可建立可靠中心軸的候選執行泛化後的自動端點校正。可靠性 MUST 由中心軸幾何證據判定，不得只因圖元位於角撐圖層或接近工程構件便視為成立。

既有連接板辨識 MUST 保留。`connection_plate_midpoints` 與 `parallel_edges_midline` 在能提供可靠中心軸時 MUST 使用相同的後續中心軸交點 refinement；其他既有辨識方法只有在能提供同等中心軸證據時才可加入。

#### Scenario: Y1A 連接板角撐維持既有校正

- **WHEN** 角撐以連接板與兩條主桿邊線辨識，且可建立可靠主桿中心軸
- **THEN** 系統 SHALL 保留該連接板辨識能力
- **AND** SHALL 以主桿中心軸計算工程端點

#### Scenario: Y29 類雙平行主桿可使用共用校正

- **WHEN** 正式角撐以 `parallel_edges_midline` 辨識，且已具有可靠雙主桿中心軸
- **THEN** 系統 SHALL 讓該角撐進入與連接板角撐相同的中心軸交點 refinement
- **AND** SHALL NOT 僅因 recognition method 不同而略過校正

#### Scenario: 沒有可靠中心軸的角撐不套用泛化規則

- **WHEN** 正式角撐只有單一斜線、暫定端點或其他不足以建立可靠中心軸的幾何
- **THEN** 系統 SHALL NOT 因本 change 對該候選執行新的中心軸延伸
- **AND** SHALL 保留既有 recognition／validation 行為

### Requirement: 中心軸延伸 SHALL 沿用既有 Waler 與 Strut 選擇

對具有可靠中心軸的角撐，系統 SHALL 沿用目前 recognition pipeline 已選定的 Waler、Strut 及端點方向，分別計算中心軸與 Waler 有限內線、Strut 有限中心線的交點。

本能力 MUST NOT 重新枚舉全場 Waler／Strut 配對、改變既有最近構件選擇、導入新的配對唯一性判定或新增 ambiguity winner policy。構件候選重複或配對模糊仍由既有流程或後續 change 處理。

#### Scenario: 既有直接端點方向被保留

- **WHEN** 現行流程已將角撐一端分派給 Waler、另一端分派給 Strut
- **AND** 可靠中心軸與兩支已選構件均有有效有限交點
- **THEN** 系統 SHALL 使用這兩支既有選定構件計算新端點

#### Scenario: 既有反向端點方向被保留

- **WHEN** 現行流程判定來源起終點順序需要反轉，才能對應 Waler 端與 Strut 端
- **THEN** 中心軸延伸 SHALL 沿用該方向判定
- **AND** SHALL NOT 因泛化中心軸規則重新選擇其他構件

#### Scenario: Competing member association remains outside this change

- **WHEN** 圖面存在重複或競爭的 Waler／Strut 候選
- **THEN** 本能力 SHALL NOT 新增 50/50、51/49、runner-up 或其他 ambiguity selection rule
- **AND** 角撐中心軸延伸的驗收 SHALL NOT 以解決該候選模糊為前提

### Requirement: 兩個校正端點必須同時通過有限幾何檢核

系統 MUST 將可靠角撐中心軸延長後，分別與既有選定 Waler 的有限內線及既有選定 Strut 的有限中心線求交。只有兩個交點都存在、位於各自有限構件範圍內，且新角撐長度不小於現行最小構件長度時，才可同時採用兩個新端點；校正 MUST 對單支角撐保持原子性。

#### Scenario: 兩個有限交點均有效

- **WHEN** 中心軸與既有選定 Waler 內線及 Strut 中心線均產生有效有限交點
- **AND** 校正後角撐長度合法
- **THEN** 系統 SHALL 同時採用兩個交點
- **AND** 兩端 SHALL 精確落在對應工程線上

#### Scenario: 其中一個交點不存在或超出有限構件

- **WHEN** 中心軸只與其中一支構件相交，或任一交點只落在有限構件延長線上
- **THEN** 系統 MUST NOT 只更新其中一端
- **AND** SHALL 保留整支角撐的原辨識幾何並產生既有類型的可追溯失敗診斷

#### Scenario: 校正後角撐過短或退化

- **WHEN** 兩個交點會形成零長度或短於現行最小構件長度的角撐
- **THEN** 系統 SHALL 拒絕該次校正
- **AND** SHALL 保留原辨識幾何且不得留下部分更新

### Requirement: 校正後工程線是所有角撐下游計算的唯一基準

端點校正成功後，系統 MUST 以校正後角撐工程線作為角撐候選點、支撐端部角撐衍生長度、`CornerBraceConnection`、支撐孔位站距、角撐固定長度及後續背填／圍令寬度調整的共同幾何基準。下游流程不得重新從連接板中點或未校正端點建立第二套角撐位置。

#### Scenario: 建立角撐與支撐衍生長度

- **WHEN** 角撐端點已成功校正至支撐中心線
- **THEN** 支撐端部角撐衍生長度 SHALL 以該支撐中心線交點計算

#### Scenario: 建立 Waler contact connection

- **WHEN** 系統為已校正角撐建立 Waler contact 的穩定連接資料
- **THEN** 圍令 attachment、支撐 attachment、孔位站距與固定長度 SHALL 全部取自校正後工程線

#### Scenario: 調整背填或圍令寬度

- **WHEN** 使用者在已校正角撐存在時預覽或套用背填／圍令寬度調整
- **THEN** 系統 SHALL 以校正後建立的孔位站距與固定長度重算角撐
- **AND** SHALL NOT 回退至來源連接板或支撐外緣端點

### Requirement: 一般構件辨識與既有安全邊界保持不變

此能力 MUST NOT 改變一般 `brace`、`strut`、Waler 材料、Solver、Project schema、構件 association 或既有 ambiguity policy，亦不得降低既有 Waler contact validation 的安全條件。

#### Scenario: 一般斜撐與支撐不受影響

- **WHEN** DXF 包含一般 `brace` 或 `strut`
- **THEN** 系統 SHALL 繼續使用既有辨識、連接及 validation 流程
- **AND** SHALL NOT 套用角撐中心軸延伸規則

#### Scenario: 既有連接板 regression

- **WHEN** 匯入目前可成功校正的 Y1A 類連接板角撐
- **THEN** 角撐數量、中心軸方向、圍令端點、支撐中心線端點及衍生長度 SHALL 維持既有正確結果
