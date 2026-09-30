# 工程領域模型

## 1. Purpose

本文件定義 SupportOptimizer 所處理之工程問題的共同語言、概念關係與已確認規則。

目的如下：

- 讓工程人員、開發者與 AI 對 Waler、Strut、Brace、Material 等名詞有一致理解。
- 區分不可違反的工程限制、使用者偏好、Solver 搜尋／評分政策與程式 fallback。
- 說明 DXF 辨識資料進入 Project 後，哪些資訊具有工程語意。
- 避免把目前演算法、UI 欄位或暫時 workaround 誤認為正式工程規則。

本文件不是 Python class reference、Solver 演算法說明、UI 操作手冊或架構文件。模組責任與依賴方向見 `ARCHITECTURE.md`；搜尋流程與評分細節應記錄於 `SOLVER.md`。

---

## 2. Domain Model Overview

```text
Project
├─ Waler（圍令）
│  ├─ Axis
│  ├─ Strut / Brace connection
│  └─ Material Spec
├─ Strut（支撐）
│  ├─ FromWaler / ToWaler
│  ├─ Column / Beam stations
│  ├─ Zoning
│  ├─ SharedLayoutGroup
│  ├─ TargetJackRegion
│  └─ Support material layout
├─ Brace（斜撐）
│  └─ Waler connection
└─ Material / Inventory
   ├─ Purchasable Length
   ├─ Inventory Qty
   └─ Steel Piece / Jack / Shim
```

Project 以 Waler、Strut 與 Brace 表達正式工程幾何；材料與庫存資料提供可用規格、合法料長及最佳化依據。Column、Beam 與 Corner Brace 的完整來源幾何主要存在於 DXF 辨識階段，Project 僅保留後續工程計算所需的衍生資訊。

---

## 3. Core Engineering Entities

### 3.1 Point / Axis

`Point` 表示 Project 座標系中的平面位置。`Axis` 由起點與終點形成，代表 Waler、Strut 或 Brace 的中心軸線及方向。

軸線方向會影響 station 的量測基準；幾何長度則是材料配置與 Solver input 的基礎。

### 3.2 Waler（圍令）

Waler 是沿工程邊界配置的構件，以軸線、識別碼及材料規格表示，也是 Strut／Brace 的正式連接對象。RC Waler 仍完整保留幾何與連接關係，並提供 Support Solver 判定 RC／Steel 接觸面；但 RC 不是鋼圍令材料分段與接頭配置的計算對象。

對參與 Waler 材料配置的 non-RC Waler，接頭必須避開由 Strut 或 Brace 連接位置形成的 forbidden point，且每一段材料必須符合對應材料規格的可購買料長。`not RC` 只是最佳化排除判斷，不取代既有材料規格與資料合法性驗證。

### 3.3 Strut（支撐）

Strut 是主要支撐構件。它由軸線、`FromWaler` 與 `ToWaler` 關係、材料規格及支撐配置屬性組成。

Strut 的起點是 station 零點；`ColumnPositions`、`BeamPositions` 與 Support material joint 都沿 Strut 軸線量測。Strut 在平面上可能有不同方向，因此不限定為水平構件。

### 3.4 Brace（斜撐）

Brace 是連接 Waler 的斜向構件。它的連接位置會成為 Waler 分段時必須避讓的工程位置。

DXF 辨識中的正式 Brace connection 是 Engineering Hard Constraint：起點與終點必須各自
唯一對應一支 Waler、兩端 Waler identity 必須不同，且兩支 Waler 的 contact face 都已正式
完成；Brace 來源軸必須分別與兩個 selected contact faces 形成合法有限交點，提交後長度也
必須合法。上述條件必須全數成立才形成正式 Brace。任一端零解、多解、接觸面仍為
provisional、交點無效、兩端同一 Waler 或結果長度不合法時，整支 Brace 維持 unresolved，
不得保留單端正式 connection、forbidden point、Project row 或 Solver-facing 資料。

端點 relation 與 member verdict 是單向依賴。每個合法 terminal-to-Waler 候選都保留同一份
canonical relation，並標示為 `unique` 或 `competing`：只有 `unique` relation 能建立正式
Brace endpoint、`FromWaler`／`ToWaler` 與 forbidden point；`competing` relation 不具連接權限，
但可提供 Waler 判斷接觸側所需的方向證據。Waler 若有任何可靠 `unique` 方向證據，只採用
`unique` evidence；方向相反的 `competing` evidence 僅產生可追溯 warning，不得推翻正式
接觸面或使其 ambiguous。只有在沒有可靠 `unique` evidence 時，才以 `competing` evidence
判側；同側可完成正式接觸面，兩側衝突則維持 contact-face ambiguous。member verdict 只決定
Brace 能否成為正式構件，不反向撤銷 Waler 已消費的側向 evidence。

Brace 與 Corner Brace 不應混為同一概念：Brace 是 Project 中的正式構件；DXF 中的 Corner Brace 幾何主要用來推導與 Strut 端部相關的工程限制。

### 3.5 SupportGroup（支撐群組）

SupportGroup 表示需要使用同一 ordered piece layout 的實體 Strut 集合。目前對應的工程情境是 `SharedLayoutGroup` 所代表的雙路支撐，固定由兩支並列 Strut 組成。

群組共享材料排列方式，但每支 Strut 的材料數量仍分別計算。

---

## 4. Support Geometry and Constraints

### 4.1 FromWaler / ToWaler 與方向

`FromWaler` 與 `ToWaler` 定義 Strut 軸線兩端所連接的 Waler，也確立起點到終點的方向。所有 station 均以 Strut 起點為零，沿此方向量測。

方向改變時，station 必須依新方向重新解讀；不能只交換端點而保留原 station 數值。

### 4.2 Column / Beam station

`ColumnPositions` 與 `BeamPositions` 分別代表中間柱／托梁與 Strut 交會位置的 station。它們不是完整 Column 或 Beam 幾何，而是 Support 配置所需的軸向位置。

DXF 中已由 whole-source geometry 證明的雙 C 型 BIM Joist assembly，可以由一個 root
表示兩支實體 Joist axes。兩軸必須與同一有限 Strut 建立實際垂直接觸，且位於同一
formal Column station 的相反兩側；其 station spacing 採 `518 ± 5 mm`（含邊界），pair
midpoint 與 Column station 的差採 `±2 mm`（含邊界）。這組數值只適用於已證明的雙 C
型式，不泛化為所有托梁。

若 Joist source axis 終點停在具有可信 `source_width` 的 Strut 外緣，可在近乎垂直、
唯一有限 Strut 且 `abs(投影距離 - source_width / 2) <= 25 mm` 時建立工程接觸：來源軸與
外緣接觸點保持不變，只有 relationship crossing point 投影到 Strut 中心線以計算 station。
一般無限延長、nearest snap、Brace 外緣或多個同樣合格的 Strut 均不可套用此規則。

在 DXF runtime validation 中，Beam 的連接狀態只由兩種既有事實組成：
`beam.crossings` 中的 `BeamCrossing`，或 `beam.brace_contacts` 中的
`BeamBraceContact`。任一集合非空即視為已連接；兩者皆空才是未連接。
Strut contact 仍只投影為 `BeamCrossing`，不建立第二份 Strut contact collection。

`BeamBraceContact` 只表示 Beam 與正式 Brace 有近乎垂直的有限線段真實交點；真實共用
端點可成立，但 endpoint face projection、nearest point、有限 gap 與無限延長線交點均
不成立。其工程 identity 為 Beam、Brace 與 tolerance-equivalent WCS contact point；
Beam path segment index 僅為 provenance。Brace contact 不產生 Strut station，亦不增加
`BeamPositions`、`AssociatedBeamIDs`、`ComponentAssociation` 或 Solver input constraint。

Support material joint 必須避開：

- Column station 左右各 `830 mm`。
- Beam station 左右各 `550 mm`。

這兩個 exclusion half-width 是固定 Engineering Hard Constraint。它們以較大構件尺寸作保守簡化，使不同構件的避讓判斷一致；不是 Solver scoring preference。

### 4.3 端部 exclusion

Strut 兩端各 `1600 mm` 內不得配置 Support material joint。`1600 mm` 是考量角撐影響距離後採用的固定 Engineering Hard Constraint。

### 4.4 Piece sequence、Joint 與 Gap

一個 Support material layout 是沿 Strut 軸線排列的 ordered piece sequence，內容可包含 Steel Piece、Jack 與 Shim。相鄰 piece 的交界形成 joint。

`Gap` 是配置完成後允許的支撐餘量：

- 合法範圍為 `0～150 mm`，屬 Engineering Hard Constraint。
- `80 mm` 是 Solver Preference；合法方案中越接近 `80 mm` 越受偏好。

Support gap 與 Waler tail remainder 是不同概念；Waler 的 `0～199 mm` 規則不適用於 Support。

### 4.5 Jack、Jack center 與 Jack region

Jack 是 Support piece sequence 中的調整構件。`Jack center` 是 Jack 在 Strut 軸線上的中心位置；`Jack region` 用來描述其所在區域。

`TargetJackRegion` 是使用者指定的 Jack 配置偏好／自動搜尋條件，不是人工方案合法性的 hard constraint。自動 Solver 可以依此限制或引導候選搜尋，但 Jack 位於其他 region 本身不使人工方案失效。

同一 Zoning 中，相鄰且不屬於雙路支撐的 Strut，其 Jack center 最小間距為 `500 mm`。小於 `500 mm` 不合法；這是固定 Engineering Hard Constraint。

此處距離是兩支幾何相鄰 Strut 各自從起點量測之 `jack_center` station 的縱向差，不是平面上的二維 Jack 距離。

### 4.6 Shim placement

Shim 的配置依 Strut 兩端接觸的 Waler 類型決定：

- 兩端皆為 Steel Waler 時，非零 Shim 必須與 Jack 相鄰。
- 接觸 RC Waler 時，Shim 放在 RC 接觸面。
- 兩端皆為 RC Waler 時，一塊 Shim 可放在任一 RC 端。
- 位於 RC 端部的 Shim 不會解除 Column／Beam exclusion zone，相關 joint 仍須符合避讓規則。

### 4.7 SharedLayoutGroup

`SharedLayoutGroup` 的工程意義是雙路支撐。同一群組：

- 固定代表兩支並列 Strut。
- 兩支必須使用相同 ordered piece layout。
- 材料數量仍按兩支 Strut 分別計算。
- Column 與 Beam constraint 在工程概念上都必須讓兩支共同避讓。

目前 Beam station 未額外跨 lane 合併，是因既有工程／辨識規則下，托梁會通過雙路支撐的兩支 Strut，使兩支各自取得相對應 crossing；這不表示 Beam 不需共同避讓。

### 4.8 Zoning 與 adjacent Strut

`Zoning` 是使用者把「同一排、需要共同協調 Jack placement 的 Strut」組成同一個 Support optimization group。它不是樓層、施工區或單純 UI 分組。

不同方向、不同排的 Strut 應分屬不同 Zoning，因為其 Jack placement 不應互相比較。同一 Zoning 內會進行 Jack placement 的全域協調。

相鄰 Strut 的正式工程意義應依現場幾何位置判斷，而不是依 Project row 或 optimization unit 的輸入順序。

進入 Support Phase 2 前，同一 Zoning 的 physical Struts 必須符合：

- 任兩支無向軸線的方向差 `<= 5°`。
- 任兩支長度差 `<= 5 mm`。
- 以全組幾何建立共同 Strut direction，再以垂直方向投影各 adjacency unit；任兩個 unit 的投影差 `<= 1 mm` 時無法建立唯一線性順序，視為 invalid。

一般 Strut 的代表位置是軸線 midpoint。已確認的 `SharedLayoutGroup` 在排序及對外 adjacency 中是一個 unit，其代表位置是兩 lane midpoint 的中心；兩支 physical Struts 與材料數量仍分別保留，組內不套用一般 500 mm spacing。共同 Jack station 必須一致，group-level Jack region 仍以該 station 與兩 lane 合併後的 Column stations 套用既有規則。

上述 tolerance 是 Solver 前置驗證，不限制 Main 編輯或保存。使用者可保留 invalid Zoning；求解時系統回報錯誤、不自動拆組、改名或覆寫 Zoning，且不進入 Phase 2。

DXF Review 完成並匯入 Main 時，系統會依最終 reviewed Waler／Strut world geometry、連續 Waler chain topology 與橫向空間連續性建立 deterministic initial Zoning suggestion。這只設定新匯入 rows 的初始值；進入 Main 後，Project Zoning 由使用者控制。Append 不重新分組或覆寫既有 Project rows。

### 4.9 CornerBrace 本體 rail 寬度

CornerBrace 的正式本體寬度是 recognition 已選定兩條 body rails 各自所在 supporting line
之間的正交間距。正式 CornerBrace 的 rail separation 必須位於 `(250.0, 600.0] mm`；
恰好 `250.0 mm` 或更小、以及大於 `600.0 mm` 均不合格。

此寬度不得由端板長度、兩端板平均值或有限 rail 端點到另一有限線段的平均距離取代。
斜切或梯形 CornerBrace 的兩條有限 rail 可能長度不同；有限端部 overhang 不屬於本體
正交寬度。例如 supporting lines 相距 `300 mm` 時，即使有限線段端點平均距離較大，正式
`source_width` 仍是 `300 mm`。

`> 250.0 mm` 是已確認的正式材料／工程規則，目前由 DXF automatic CornerBrace
recognition 執行；它不是 Solver scoring、Solver preference 或 DXF candidate ranking
參數。此規則只適用於 CornerBrace 本體；一般 Brace 另依下一節的獨立規則判斷，兩者
目前雖同為 `250.0 mm`，仍不得共用同一設定。Strut、Waler、Column 與 Beam 不受影響。

CornerBrace 辨識分成兩層不可混用的 evidence：

- `BodyGeometryEvidence` 只保存 exact source、canonical direction／normal、RailTrack、
  selected track pair、midline、separation、source intervals 與端板證據。
- `BodyRelationshipAssessment` 才保存特定有限 Waler／Strut identities 的 expected span、
  slenderness、coverage、gaps、occluders、extension、classification 與 hard-valid 結果。

RailTrack 由方向差 `<= 2°`、整組 normal spread `<= 25 mm` 的 fragments 建立；長度
`>= 100 mm` 的 fragment 可建立方向，其他同方向短 fragments 可在方向成立後加入。
同軌 intervals 的 overlap 與 `<= 50 mm` seam 合併。Track pair 不使用固定 80% 投影
重疊、first-fit 或 DXF entity order 決定。

每一組 relationship 必須同時符合：expected span／separation `>= 3.0`、兩條 selected
rails 各自對 expected span 的 union coverage `>= 50%`，且 Waler 端與 Strut 端 outward
extension 各自 `<= 600 mm`。Extension 不得補償 coverage。沒有 `> 50 mm` gap 時分類為
`complete`；存在大 gap 時分類為 `occluded`，且每個 gap 都必須有自己的 finite occluder
evidence。Near-parallel occluder 另須覆蓋該 gap 至少 `50%`。端板可作 terminal evidence，
但零、一或兩端板本身都不是資格條件。

唯一 body 加唯一 hard-valid relationship 才自動建立；唯一 body 加多組 hard-valid
relationships 保持 unresolved，交由 Review 明確選擇 exact Waler／Strut identities。Body
零解或多解不可用 relationship selection 繞過。

### 4.10 Brace 本體寬度與中心 authority

任何由 MLINE、closed outline、parallel edges、rail pair 或 whole-root envelope 實測本體
而建立的自動 Brace，其實體寬度必須嚴格大於 `250.0 mm`。恰好 `250.0 mm` 或更小均
不合格；此邊界不套用 `width_tolerance_mm`、epsilon 或顯示值四捨五入。只有來源確實是
單一工程中心線、沒有可量測 body envelope 時，`source_width == 0.0` 才表示 unknown，
並維持既有 single-line 流程。

Closed outline 的正式寬度必須由主要工程方向兩側、共同支持 longitudinal corridor 的
outer supporting sides 之正交間距取得。Axis-aligned／rotated bounding box、端板長度、
最遠點、短突出 detail、內部 web／flange 或孔洞邊均不得替代 supporting-side width；
兩側不唯一或 coverage 不足時，該 topology width 不可靠。

完整、無分支且可唯一解讀的斜切 closed outline，可由「兩條 outer longitudinal rails
加兩個有限 terminal cuts」的封閉拓撲證明 body 完整性，不要求兩條 rails 各自覆蓋
整個 outline longitudinal extent 的 `80%`。其 source-supported axis 位於兩條 rail
supporting lines 的正中位置，兩端分別由該 midline 與兩個有限 terminal cuts 的交點
界定；不得再以所有 outline vertices 的最小／最大投影把軸線外伸到實體端面之外。

此 closed-topology 例外仍要求兩條 rails 各自長度 `>= 100 mm`、沿主要方向具有正的
longitudinal overlap，且 terminal cut 不得在既有 `2°` 平行角度 tolerance 內與 rails
平行。寬度仍須位於 `(250.0, 600.0] mm`，axis 仍須通過既有 minimum length 與
slenderness。開放 rail pair、fragmented evidence、whole-root envelope 與 local rail-pair
fallback 的 `minimum_projection_overlap_ratio == 0.8` 不變；不得為退化外框另加匿名
角度、比例或長度門檻。

Component-like Brace 必須由同一 root source 的完整／connected body topology、whole-root
longitudinal bands，或能同時支持主要方向、可靠 terminal extent 與 body envelope 的整體
證據成立；單一局部 pair、短 detail、branch 或零散 fragments 不足以成立。成立後，候選
依 `TOPOLOGY → WHOLE_ROOT_ENVELOPE → LOCAL_RAIL_PAIR` 分層，但每個候選必須先完成
完整性、extent、寬度量測及 `> 250.0 mm` hard gate，authority 才屬於最高仍有合法候選
的 tier。該 tier 多解時阻擋；所有 tiers 無合法候選時失敗，不得回一般 route 繞過限制。

此規則屬 DXF recognition 的 Engineering Hard Constraint，不是 Solver scoring 或 candidate
偏好。`connection_tolerance_mm == 250.0` 是端點連接容許距離，
`maximum_brace_axis_extension_mm == 600.0` 是辨識後連到 Waler 的延伸上限；兩者都不得
作為 Brace 本體寬度門檻。

---

## 5. Waler Geometry and Constraints

### 5.1 Waler axis 與 connection

Waler axis 定義 Waler 的起終點、方向與總長度。Strut 與具有完整正式 connection 的 Brace 才會把連接位置投影為沿 Waler 軸線量測的 forbidden point；unresolved Brace 不產生 forbidden point。

### 5.2 Forbidden point 與 Waler joint

Waler joint 是兩段 Waler 材料的接合位置。每一 joint 與任一 forbidden point 的最小避讓距離為 `300 mm`：

- 距離 `< 300 mm` 不合法。
- 距離 `= 300 mm` 可接受。

這是固定 Engineering Hard Constraint，不是評分偏好。

### 5.3 Segment 與可購買料長

Waler segment 是相鄰 joint 或端部之間的一段材料。正式材料長度範圍為 `1000～10000 mm`；實際 segment 同時必須存在於該 Material Spec 對應的 `Purchasable Length` 集合。

僅落在數值範圍內，並不代表該長度對所有材料規格都合法。

### 5.4 Tail adjustment 與 remainder

Waler 尾端可使用 adjustment block 處理材料分段後的尾端差額：

- adjustment block 可為 `0、100、150、200、300 mm`。
- `100、150、200、300 mm` 是固定工程材料尺寸。
- 一個 Waler 方案最多只能使用一塊 adjustment block。
- Waler 現場處理餘量（tail remainder）的合法範圍為 `0～199 mm`。

以上均為正式 Waler Domain rule。Waler tail remainder 不等於 Support gap；Support gap 的合法範圍是 `0～150 mm`，且其偏好值為 `80 mm`。

---

## 6. Material Domain

### 6.1 Material Spec

Material Spec 識別構件使用的材料規格。它決定該 Usage 下可取得的標準料長集合，並作為查詢庫存的條件之一。

### 6.2 Purchasable Length 與 Inventory Qty

`Purchasable Length` 表示特定 Usage／Material Spec 允許取得或購買的標準料長，是材料合法性條件。

`Inventory Qty` 表示該標準料長目前的庫存數量。即使某料長 Qty 為零，只要它仍在 Purchasable Length 集合中，就仍是合法且可採購的材料。

因此：

- 庫存不足不使方案非法。
- Solver 應偏好使用現有庫存並減少新增採購。
- 可購買料長與現有數量不可互相取代。

### 6.3 Steel Piece、Jack 與 Shim

- `Steel Piece`：構成 Support 或 Waler 主要長度的標準鋼材。
- `Jack`：Support 中可調整長度並形成 Jack center 的構件。
- `Shim`：依端部 Waler 類型配置的固定尺寸調整材料。
- `Adjustment Block`：Waler 尾端使用的固定尺寸調整材料，與 Support Shim／gap 分屬不同規則。

### 6.4 Short / Mid / Long / Out

材料長度分類是正式 Engineering Policy：

| Category | Length |
| --- | --- |
| Short | `4000 ≤ L < 6000 mm` |
| Mid | `6000 ≤ L ≤ 8000 mm` |
| Long | `8000 < L ≤ 10000 mm` |
| Out | 其他長度 |

Short 不代表所有小於 `4000 mm` 的材料；Solver 對 under-4000 material 的 penalty 是另一個概念。

### 6.5 Domain policy、Solver preference 與 fallback

以下三類資訊不可混淆：

- Domain／Engineering Policy：標準可購買料長、合法材料組合、Short／Mid／Long 分類及庫存不足仍可採購。
- Solver Preference：偏好現有庫存、減少採購，以及目前用來平衡材料分布的比例 scoring。
- Implementation Fallback：Material Spec 空白時，以 Usage 下的料長及每種 `99` 根近似無限庫存，使資料不完整時仍可執行。

Support Solver 現行 Short／Mid／Long 目標比例 `38% / 40% / 22%` 是 Temporary Solver Heuristic，不是固定工程政策。Material Spec 空白時的 `99` 根也不是正式 Domain rule。

---

## 7. DXF → Project Domain Boundary

DXF Import／Review 負責把圖面來源轉成可確認的工程資訊。以下資料是辨識 provenance 或 Review workflow 資料，不屬於 Core Project／Solver Domain：

- DXF handle、layer、block／entity 來源。
- recognition confidence、recognition method 與 validation message。
- CandidatePoint、ReviewItem、ProblemRecord 與 manual override 狀態。
- source geometry、world／local alternatives 與 selection state。

經使用者確認及座標投影後，真正跨入 Project 的工程資訊包括：

- Waler、Strut、Brace 的正式軸線與連接關係。
- Strut 上的 Column／Beam station。
- 由 Corner Brace 推導並保留的端部限制資訊。
- Material Spec、Zoning、SharedLayoutGroup 與 TargetJackRegion。

Solver input 會再把 Project 資訊整理成特定求解問題，例如 Strut 總長、forbidden zones、可購買料長、庫存項目及 Waler forbidden points。這些 Solver DTO 不應反向成為 Project 的資料定義。

---

## 8. Domain Vocabulary

| Term | 中文名稱 | Engineering Meaning | Scope |
| --- | --- | --- | --- |
| Point | 點位 | Project 平面座標中的位置 | Core Domain |
| Axis | 軸線 | 構件起終點、方向與長度基準 | Core Domain |
| Waler | 圍令 | 與 Strut／Brace 連接的正式構件；non-RC 可進行鋼材分段，RC 保留連接與 Support 接觸語意 | Core Domain |
| Strut | 支撐 | 主要支撐構件及 Support layout 的幾何主體 | Core Domain |
| Brace | 斜撐 | 連接 Waler，並形成 Waler 避讓位置的構件 | Core Domain |
| SupportGroup | 支撐群組 | 必須共用 ordered piece layout 的 Strut 集合 | Core Domain |
| Column station | 中間柱樁號 | Column 與 Strut 交會的軸向位置 | Project/Application Model |
| Beam station | 托梁樁號 | Beam 與 Strut 交會的軸向位置 | Project/Application Model |
| Zoning | 支撐最佳化分區 | 同一排且需共同協調 Jack 的 Strut 群組 | Project/Application Model |
| SharedLayoutGroup | 雙路支撐群組 | 兩支並列且共用材料排列的 Strut | Project/Application Model |
| CornerBrace rail separation | 角撐本體寬度 | selected body rail supporting lines 的正交間距，正式值須嚴格大於 `250.0 mm` | Engineering Policy / DXF Recognition |
| Brace body width | 斜撐本體寬度 | body-derived Brace 兩側 outer supporting sides 的正交間距，正式值須嚴格大於 `250.0 mm`；centerline-only 為 unknown | Engineering Policy / DXF Recognition |
| TargetJackRegion | 目標千斤頂區域 | 使用者指定的搜尋／配置偏好 | Solver Preference |
| Piece sequence | 構件排列 | 沿 Strut 依序配置的 Steel、Jack、Shim | Solver Concept |
| Joint | 接頭 | 相鄰材料 piece 的交界位置 | Core Domain |
| Support gap | 支撐餘量 | 合法 `0～150 mm`，偏好接近 `80 mm` | Core Domain / Solver Preference |
| Jack center | 千斤頂中心 | Jack 在 Strut 軸線上的中心位置 | Core Domain |
| Forbidden point | 禁止點 | Waler joint 必須避開的連接位置 | Core Domain |
| Tail remainder | 圍令尾端餘量 | Waler 現場處理餘量，合法 `0～199 mm` | Core Domain |
| Material Spec | 材料規格 | 決定可購買料長及庫存查詢範圍 | Project/Application Model |
| Purchasable Length | 可購買料長 | 合法可取得的標準料長集合 | Core Domain |
| Inventory Qty | 庫存數量 | 目前現有數量；不足時仍可採購 | Project/Application Model |
| Short / Mid / Long | 短／中／長料分類 | 依正式長度區間分類材料 | Core Domain |
| Source handle | 來源圖元代碼 | DXF 辨識來源與 provenance | DXF Recognition |
| ReviewItem | 審查項目 | 匯入階段等待確認或修正的辨識結果 | DXF Recognition |
| 99-piece fallback | 99 根 fallback | Material Spec 空白時的暫時執行策略 | Implementation Fallback |

---

## 9. Hard Rules vs Preferences

| Rule / Concept | Classification | Meaning |
| --- | --- | --- |
| Strut 端部 exclusion `1600 mm` | Engineering Hard Constraint | 端部範圍內不得配置 Support material joint |
| Column exclusion `±830 mm` | Engineering Hard Constraint | Column 附近不得配置 Support material joint |
| Beam exclusion `±550 mm` | Engineering Hard Constraint | Beam 附近不得配置 Support material joint |
| Support gap `0～150 mm` | Engineering Hard Constraint | 超出範圍的 Support layout 不合法 |
| Support gap 目標 `80 mm` | Solver Preference | 合法範圍內偏好接近此值 |
| 非雙路相鄰 Jack center 間距 `≥ 500 mm` | Engineering Hard Constraint | 同一 Zoning 的相鄰 Strut 必須維持最小間距 |
| Zoning 方向差 `<= 5°`、長度差 `<= 5 mm` | Engineering Hard Constraint | 求解前驗證同一排的 physical Struts；超出時不進入 Phase 2 |
| Zoning unit 投影差 `> 1 mm` | Engineering Hard Constraint | `<= 1 mm` 無法建立唯一幾何順序，求解前拒絕 |
| TargetJackRegion | User / Solver Preference | 引導自動搜尋，不單獨決定人工方案合法性 |
| SharedLayoutGroup 共用排列 | Engineering Hard Constraint | 雙路支撐兩支 Strut 必須使用相同 ordered layout |
| CornerBrace rail separation `> 250.0 mm` | Engineering Hard Constraint | 以 selected rail supporting lines 的正交間距判斷；`= 250.0 mm` 不合格，端板長度與有限端點平均不得替代 |
| Body-derived Brace width `> 250.0 mm` | Engineering Hard Constraint | 先由 outer supporting sides 可靠量寬再做嚴格比較；`= 250.0 mm` 不合格，centerline-only unknown 不套用 |
| Waler joint clearance `≥ 300 mm` | Engineering Hard Constraint | `< 300 mm` 不合法，`= 300 mm` 可接受 |
| Waler segment `1000～10000 mm` 且屬可購買集合 | Engineering Hard Constraint | 數值範圍與對應 Purchasable Length 都必須符合 |
| Waler adjustment block 尺寸及最多一塊 | Engineering Hard Constraint | 僅可用 `0、100、150、200、300 mm`，且最多一塊 |
| Waler tail remainder `0～199 mm` | Engineering Hard Constraint | 正式現場處理餘量範圍 |
| RC / Steel Shim placement | Engineering Hard Constraint | Shim 位置依兩端 Waler 類型決定 |
| 庫存不足仍可採購 | Engineering Policy | Inventory Qty 不直接限制材料合法性 |
| 優先庫存、減少採購 | Solver Preference | 在合法方案間影響選擇 |
| Short／Mid／Long 長度區間 | Engineering Policy | 固定材料分類，不是評分權重 |
| `38 / 40 / 22` 材料比例 | Temporary Solver Heuristic | 暫時平衡材料分布，未來可被其他 scoring policy 取代 |
| 空白 Material Spec → 每種 `99` 根 | Implementation Fallback | 讓資料不完整時仍可執行，不是工程規則 |

---

## 10. Known Domain–Implementation Gaps

Known Gap 表示 Domain 已確認，但目前程式尚未完全符合；它不等同於自動待辦事項，後續修改仍須獨立定義 Feature Spec。

### Gap 1 — Support Inventory Preference

- Domain：庫存不足仍可採購，但 Solver 應偏好使用現有庫存並減少採購。
- Current implementation：Waler Solver 已部分考慮庫存與採購；Support Solver 尚未把 Inventory Qty／purchase quantity 納入 scoring。
- Future：以獨立 Feature Spec 定義 Support 的庫存與採購偏好。

### Gap 2 — Empty Material Spec fallback

- Domain：Material Spec 應決定合法可購買料長及庫存來源。
- Current implementation：Material Spec 空白時，以 Usage 下料長及每種 `99` 根近似無限庫存。
- Future：資料完整性機制成熟後，重新評估此 fallback。

### Gap 3 — Temporary Material Ratio Heuristic

- Domain：Short／Mid／Long 分類正式有效；庫存不足仍允許採購。
- Current implementation：Support Solver 使用 `38 / 40 / 22` 比例 scoring 暫時避免材料過度集中。
- Future：庫存模型與庫存導向 Solver 成熟後，重新評估或取代此 heuristic。

---

## 11. Out of Scope

本文件不展開下列內容：

- Beam Search、Genetic Algorithm、Dynamic Programming。
- Candidate generation、candidate cache、search escalation。
- score formula、penalty weight、candidate count 與 random seed。
- Tkinter 畫面、Dialog 操作與 UI state。
- Project persistence、managed DXF asset 與檔案格式。
- DXF Import／Review 的操作流程與 recognition implementation。

Solver 搜尋與評分細節屬於 `SOLVER.md`；使用流程屬於 `WORKFLOW.md`；模組責任、資料流與 persistence boundary 屬於 `ARCHITECTURE.md`。
