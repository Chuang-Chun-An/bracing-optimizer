# Spec Delta

## 閱讀導航

### 必讀

- 「雙路幾何候選與正式工程資格必須分層」：定義哪些配對必須被保留為候選。
- 「Waler 尚未唯一時必須顯示暫定警告」：定義 S19／S36 類型案例的可見行為。
- 「暫定候選不得提前產生正式效果」：定義 Project、association、Zoning 與 Solver 的安全邊界。

### 條件式閱讀

- 修改雙路支撐設定視窗時，閱讀「Review 必須呈現狀態、原因與操作限制」。
- 修改 endpoint／Waler rebuild、Pause／Resume 或 decision replay 時，閱讀「候選必須隨 canonical Review state 安全重建」。
- 修改候選排序或多重配對時，閱讀「候選結果必須 deterministic 並保守處理一對多歧義」。

### 可先跳過

- 不修改 `dxf-waler-contact-face-recognition` 的 Waler identity／接觸面選擇規則。
- 不修改 `support-adjacency` 的 Solver adjacency、Jack spacing 或 initial Zoning 工程規則。
- 不修改材料辨識、一般 Strut recognition、Project schema 或匯出格式。

## Purpose

本 capability 定義 DXF Review 如何先保留符合既有雙路支撐幾何形式的 Strut 配對，再依 Waler topology 區分正式候選與暫定警告，使使用者能看見並處理尚未完成的工程關係，同時阻止未合法的候選進入 Project 與 Solver。

## ADDED Requirements

### Requirement: 雙路幾何候選與正式工程資格必須分層

系統 SHALL 先以兩支 Strut recognition outcome 中可靠、source-supported 的 WCS axes判定 geometry-qualified pair，再獨立評估其 Waler topology qualification。Waler identity 尚未唯一時，該 source-supported axis只可用於Review暫定提示；不得成為Project geometry或任何正式雙路效果。任一Strut沒有可靠、source-supported的WCS axis時，系統MUST NOT建立geometry-qualified pair。geometry-qualified pair MUST 沿用既有雙路幾何邊界：無方向性 axis angle difference `<= parallel_angle_tolerance_deg`、中心線間距與 `double_support_spacing_mm = 1000 mm` 的差值 `<= double_support_spacing_tolerance_mm = 150 mm`、projection overlap ratio `>= double_support_overlap_ratio = 0.9`，且 length difference `<= double_support_length_tolerance_mm = 250 mm`。

Waler identity 缺失或歧義 MUST NOT 使系統在上述幾何比較前直接捨棄 pair。Column／Beam proximity、位於兩支 Strut 中間或可同時投影至兩支 Strut，只能作為 Review 顯示用輔助 evidence，MUST NOT 建立、排除或合法化 geometry-qualified pair。

上述數值屬既有 DXF recognition eligibility setting；本 capability 不將其升級為 Solver Engineering Hard Constraint，也不修改其數值。

#### Scenario: 幾何符合但兩端 Waler 都有歧義

- **WHEN** 兩支 Strut 通過所有既有雙路幾何邊界
- **AND** 任一 Strut 的一端或兩端因多個合法 Waler identities 而尚未唯一連接
- **THEN** 系統 SHALL 保留該 geometry-qualified pair
- **AND** MUST NOT 因 `from_waler` 或 `to_waler` 尚為空白而完全略過該 pair

#### Scenario: Waler unresolved 時使用可靠來源軸線建立暫定候選

- **WHEN** 兩支 Strut 具有可靠且 source-supported 的 WCS axes
- **AND** 兩支通過既有雙路幾何門檻
- **AND** 任一必要 terminal 的 Waler identity 尚未唯一
- **THEN** 系統 SHALL 建立 `pending_waler` candidate
- **AND** 該 candidate SHALL 只作 Review 提示
- **AND** MUST NOT 產生任何正式雙路效果

#### Scenario: Strut 來源軸線本身不可靠

- **WHEN** 任一 Strut 在 Waler 未解決時沒有可靠的 source-supported WCS axis
- **THEN** 系統 MUST NOT 建立 geometry-qualified double-support pair
- **AND** MUST NOT 由 Waler candidates、Column／Beam proximity 或附近幾何猜測 Strut axis

#### Scenario: 幾何未通過不因共享柱而成為候選

- **WHEN** 兩支 Strut 未通過任一既有雙路幾何邊界
- **AND** 一支 Column 位於兩者中間或可投影至兩者
- **THEN** 系統 MUST NOT 將該配對建立為 geometry-qualified pair

#### Scenario: 幾何邊界等號仍合法

- **WHEN** pair 的 angle、spacing delta、overlap ratio 或 length difference 恰好位於上述合法等號邊界
- **THEN** 系統 SHALL 將該條件視為通過

### Requirement: Waler topology 必須產生可區分的候選狀態

每一個 geometry-qualified pair SHALL 由同一份 canonical Review result 判定下列互斥 outcome：

- `eligible`：兩支 Strut 的兩端均具有唯一 Waler identity，且兩支 Strut 連到相同的無方向性 Waler pair；
- `pending_waler`：至少一個必要 terminal 的 Waler identity 缺失或存在歧義，因此尚無法證明相同 Waler pair；
- `incompatible_waler`：兩支 Strut 的必要 terminal 均已唯一確定，但其無方向性 Waler pairs 明確不同。

`pending_waler` SHALL 提供穩定 reason code、受影響的 Strut identities、可取得的候選 Waler identities，以及可理解的使用者訊息。`incompatible_waler` SHALL 保留可診斷 outcome，但 MUST NOT 出現在一般可接受候選集合。系統 MUST NOT 以 Waler ID 排序、DXF entity order、最短距離微差或 Column／Beam evidence 將 `pending_waler` 猜成 `eligible`。

#### Scenario: 唯一且相同的 Waler pair 可以正式評估

- **WHEN** geometry-qualified pair 的兩支 Strut 都已唯一連到相同的無方向性 Waler pair
- **THEN** 系統 SHALL 將 outcome 分類為 `eligible`

#### Scenario: 任一 terminal 尚未唯一

- **WHEN** geometry-qualified pair 至少一個必要 terminal 沒有唯一 Waler identity
- **THEN** 系統 SHALL 將 outcome 分類為 `pending_waler`
- **AND** SHALL 指出待處理 terminal 與可取得的候選 Waler identities

#### Scenario: 唯一 Waler pairs 明確不同

- **WHEN** geometry-qualified pair 的所有必要 terminals 均已唯一確定
- **AND** 兩支 Strut 的無方向性 Waler pairs 不同
- **THEN** 系統 SHALL 將 outcome 分類為 `incompatible_waler`
- **AND** MUST NOT 將它提供為可接受的雙路支撐候選

### Requirement: Review 必須呈現狀態、原因與操作限制

雙路支撐 Review 介面 SHALL 顯示全部 `eligible` candidates，以及全部 `pending_waler` geometry-qualified pairs。每列 SHALL 至少顯示兩支 Strut、中心線間距、可理解的狀態及警告摘要；選取或展開 `pending_waler` 時，使用者 SHALL 可取得未唯一 terminal 與候選 Waler identities 的詳細原因。

`eligible` candidate SHALL 維持既有接受／不接受操作及 one-to-one membership policy。`pending_waler` SHALL 清楚標示為尚不可接受，且所有切換、套用或等價操作 MUST NOT 將它改為 accepted。`incompatible_waler` MAY 只存在 diagnostics／problem projection，不要求出現在一般雙路候選清單。

Presentation MUST 只投影 canonical candidate outcome，MUST NOT 自行重算幾何門檻、Waler topology 或 acceptance legality。

#### Scenario: S19 與 S36 類型的暫定候選可見

- **WHEN** 與 S19／S36 等價的兩支 Strut 通過雙路幾何邊界
- **AND** 上、下端各因重疊 Waler source identities 而無法唯一連接
- **THEN** 雙路支撐介面 SHALL 顯示該 pair 為警告狀態
- **AND** SHALL 說明必須先處理 Waler ambiguity
- **AND** 接受操作 SHALL 不可用或不產生任何 accepted mutation

#### Scenario: 正式候選維持既有操作

- **WHEN** candidate outcome 為 `eligible`
- **THEN** 使用者 SHALL 可依既有流程切換接受或不接受並套用

#### Scenario: Presentation 不建立第二套資格判斷

- **WHEN** candidate outcome、reason code 或 Waler details 改變
- **THEN** 介面 SHALL 顯示 workflow 提供的最新 projection
- **AND** MUST NOT 從畫布距離、顯示字串或 Treeview 順序重新推導狀態

### Requirement: 暫定候選不得提前產生正式效果

只有 outcome 為 `eligible` 且 accepted 的 candidate SHALL 被視為正式雙路支撐。`pending_waler` 與 `incompatible_waler` MUST 保持 non-accepted，且不得：

- 使 Column／Beam constraints 同時關聯至兩支 Strut；
- 建立或輸出 `SharedLayoutGroup`；
- 成為 initial Zoning 的不可拆分 ordering unit；
- 建立 Project 雙路支撐 rows 或進入 Support Solver；
- 使 DXF Review 被視為已解決 Waler blocking problem。

輔助 Column／Beam evidence MAY 顯示於候選詳細資料，但 MUST 使用既有 association truth，且不得因暫定候選而改寫正式 association。

#### Scenario: 暫定候選旁有共享柱

- **WHEN** `pending_waler` pair 的兩支 Strut 中間存在 C26 等價 Column
- **THEN** 系統 MAY 在 Review 詳細資料顯示該 Column 為輔助 evidence
- **BUT** MUST NOT 因此把 Column 正式共享給兩支 Strut或建立 `SharedLayoutGroup`

#### Scenario: 完成 Project row conversion 前仍未解決

- **WHEN** result 中仍存在 `pending_waler` 或 `incompatible_waler` pair
- **THEN** Project row conversion MUST 忽略該 pair 的雙路關係
- **AND** MUST NOT 產生任何由該 pair 衍生的 Solver input

#### Scenario: 合法且已接受的候選保持既有下游效果

- **WHEN** candidate outcome 為 `eligible` 且 accepted
- **THEN** 系統 SHALL 依既有 contract 建立共享 association、`SharedLayoutGroup` 與後續 initial-grouping input

### Requirement: 候選必須隨 canonical Review state 安全重建

當使用者修正 Strut endpoint、採用 Waler contact、排除／復原來源，或其他既有操作改變 canonical Review geometry／relationship 時，系統 SHALL 從重新辨識後的 canonical finalized Strut axes重建完整 geometry-qualified pairing graph，並重新計算 angle、spacing、overlap ratio、length difference、Waler topology及one-to-one ambiguity。系統 MUST NOT 只把既有 candidate 的 `qualification_status` 原地改值，亦MUST NOT沿用provisional階段的軸線或幾何量測。相同 physical pair 的對應 SHALL 使用兩支 Strut 的 normalized source identities，而非可重新編號的顯示 ID。

既有 explicit accepted／rejected decision 只有在相同 source pair 目前仍唯一對應一個 `eligible` candidate 時才可 replay，且explicit decision SHALL優先於eligible default。candidate 降級為 `pending_waler`、變成 `incompatible_waler`、不再通過幾何邊界、source identity不再唯一或具有one-to-one ambiguity時，系統MUST NOT以default自動接受。當從未具有 explicit decision 的 `pending_waler` 重建為 `eligible` 時，系統 SHALL 使用既有 eligible-candidate default 與 one-to-one ambiguity policy，不得把先前的不可接受狀態誤當成使用者 explicit rejection，也不要求使用者僅因先前曾為`pending_waler`而再次手動確認。

#### Scenario: Waler 解決後必須重新計算幾何

- **WHEN** `pending_waler` pair 的 Waler ambiguity 經合法 Review 操作解決
- **THEN** rebuild SHALL 使用目前 canonical finalized Strut axes 重新計算 angle、spacing、overlap、length difference 與 Waler topology
- **AND** MUST NOT 直接沿用 provisional 階段的幾何量測或 qualification
- **AND** 只有重新計算後仍符合全部條件，candidate 才可分類為 `eligible`

#### Scenario: 解決 Waler ambiguity 後依既有預設生效

- **WHEN** `pending_waler` pair 的 Waler identities 經合法 Review 操作後變為唯一且相容
- **AND** 使用目前 canonical axes 重新計算後仍通過全部雙路幾何門檻
- **THEN** rebuild SHALL 將同一 source pair 分類為 `eligible`
- **AND** SHALL 依既有 explicit decision、eligible default 與 one-to-one policy決定 accepted state
- **AND** 不要求使用者僅因先前曾為 `pending_waler` 而再次手動確認
- **AND** 解決 Waler ambiguity 本身 MUST NOT 繞過重新計算、explicit rejection 或 one-to-one ambiguity

#### Scenario: 正式候選降級時立即移除效果

- **WHEN** accepted `eligible` candidate 因目前 canonical state 改變而成為 `pending_waler` 或 `incompatible_waler`
- **THEN** rebuild MUST 使它不再 accepted
- **AND** SHALL 重建 association、grouping 與 derived Review state，使舊正式效果不殘留

#### Scenario: 顯示 ID 重新編號不誤套決策

- **WHEN** recognition rebuild 使 Strut IDs 或 candidate IDs 改變
- **THEN** 系統 SHALL 只以 normalized source identities replay 可安全沿用的 decision
- **AND** MUST NOT 將舊 decision 套到重用相同顯示 ID 的其他 physical pair

### Requirement: 候選結果必須 deterministic 並保守處理一對多歧義

等價 WCS geometry、source identities 與 Waler relationship 在 Strut collection order、source entity order、member start／end 方向或 candidate iteration order 改變時，SHALL 產生等價的 geometry-qualified pairs、outcomes、reason codes 與 accepted effects。

one-to-one ambiguity SHALL 從完整 geometry-qualified pairing graph計算；`eligible`、`pending_waler`與`incompatible_waler` edges都MUST參與衝突判斷。當任一 Strut 同時屬於兩個以上 geometry-qualified pairs 時，系統 SHALL 將所有相關 pair 標示為 one-to-one ambiguous，且 MUST NOT 因任一 edge目前為pending或incompatible而忽略它並自動接受另一個edge。使用者只能接受目前為 `eligible` 的其中一個 pair；`pending_waler`與`incompatible_waler`永遠不得accepted。該操作 SHALL 解除其他共享成員的 accepted state，但不得隱藏仍存在的 provisional或incompatible diagnostics。canonical state改變後，系統MUST重建完整graph再判斷ambiguity。

#### Scenario: 輸入順序不改變結果

- **WHEN** 等價 Struts、Walers 與 source entities 只改變輸入順序或軸線方向
- **THEN** candidate membership、qualification outcome、reason codes 與正式 accepted effects SHALL 保持等價

#### Scenario: 同一 Strut 有多個幾何 partner

- **WHEN** 一支 Strut 同時與兩支以上 Struts 通過雙路幾何邊界
- **THEN** 系統 SHALL 顯示可取得的候選與 one-to-one ambiguity
- **AND** MUST NOT 自動建立互相衝突的正式雙路群組

#### Scenario: Eligible 與 pending partner 同時存在

- **WHEN** 一支 Strut 同時具有一個 `eligible` partner與一個`pending_waler` partner
- **THEN** 兩個pairs SHALL都標示one-to-one ambiguity
- **AND** `eligible` pair MUST NOT依default自動接受
- **AND** `pending_waler` pair MUST NOT被接受

#### Scenario: Eligible 與 incompatible partner 同時存在

- **WHEN** 一支 Strut 同時具有一個 `eligible` partner與一個`incompatible_waler` partner
- **THEN** 系統 SHALL保留兩個geometry-qualified edges的衝突診斷
- **AND** MUST NOT以`incompatible_waler`不可接受為理由忽略該edge並自動接受`eligible` pair

#### Scenario: 衝突 edge 消失後重新判斷唯一性

- **WHEN** canonical rebuild後，原本共享同一Strut的`pending_waler`或`incompatible_waler` edge不再通過幾何門檻或不再存在
- **THEN** 系統 SHALL重建完整pairing graph並重新計算one-to-one ambiguity
- **AND** 剩餘唯一的`eligible` pair才可依explicit decision與既有eligible default決定accepted state

#### Scenario: 接受一個合法 pair 不隱藏暫定診斷

- **WHEN** 使用者接受一個 `eligible` pair，且其中一支 Strut 仍屬於另一個 `pending_waler` pair
- **THEN** 其他正式共享 pair MUST 保持未接受
- **AND** `pending_waler` pair SHALL 保持可見或可由 diagnostics 取得，但不得產生正式效果
